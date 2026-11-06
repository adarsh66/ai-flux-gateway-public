"""Synthetic/offline only: never sends gateway traffic."""
import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from aiflux.gateway_settings import subscription_access
from aiflux.models import TeamSubscription
from aiflux.poc_controls import effective, render
from aiflux.schemas import PocGatewayConfiguration, PocLimits, PocOverride, poc_safety
from pydantic import ValidationError
from sqlalchemy.orm import Session
from test_gateway_settings import FragmentApim

URL = "/api/admin/gateway-settings/dev-unified"
SAFETY = "/api/admin/content-safety-settings/dev-unified"


@pytest.fixture
def poc(env):
    env.settings.gateway_controls_poc_enabled = True
    env.settings.gateway_settings_scopes = ["dev-unified"]
    apim = FragmentApim()
    apim.values["dev-unified"] = render(PocGatewayConfiguration(), [])
    env.app.state.apim = apim
    return apim


def save(env, config=None, version=0):
    return env.client.put(URL, headers=env.admin, json={
        "expected_version": version, "configuration": config or PocGatewayConfiguration().model_dump(mode="json"),
        "reason": "Explicit audited POC release / optional controls",
    })


def test_default_first_fragment_has_one_stable_literal_quota_not_membership_gate():
    xml = render(PocGatewayConfiguration(), [])
    root = ET.fromstring(xml)
    assert {n.tag for n in root.iter()} == {"fragment", "set-variable", "quota-by-key"}
    assert not any(v in xml for v in ("403", "return-response", "aiflux:v2", "rate-limit"))
    quota = root.findall("quota-by-key")
    assert len(quota) == 1
    assert quota[0].attrib == {"calls": "50000", "renewal-period": "86400",
                                "counter-key": '@("project-demo:" + context.Subscription.Id)'}
    assert ET.canonicalize(xml, strip_text=True) == ET.canonicalize(
        Path("gateway/policies/poc-settings-defaults.xml").read_text(), strip_text=True)
    assert root.find("set-variable[@name='aiflux-poc-rpm']").get("value") == "@(60)"
    assert root.find("set-variable[@name='aiflux-poc-tpm']").get("value") == "@(300000)"
    assert root.find("set-variable[@name='aiflux-poc-request-quota']").get("value") == "@(50000)"
    assert root.find("set-variable[@name='aiflux-poc-token-quota']").get("value") == "@(20000000)"


def test_precedence_is_independent_for_limits_and_safety_and_unknown_uses_defaults():
    org, sub = uuid4(), uuid4()
    safety = poc_safety().model_copy(update={"hate": 0})
    config = PocGatewayConfiguration(overrides=[
        PocOverride(organization_id=org, limits=PocLimits(rpm=25), safety=safety),
        PocOverride(organization_id=org, subscription_id=sub, limits=PocLimits(rpm=5)),
    ])
    assert effective(config, str(org), str(sub))[0].rpm == 5
    assert effective(config, str(org), str(sub))[1].hate == 0
    assert effective(config, str(org), str(uuid4()))[0].rpm == 25
    assert effective(config, None, str(sub))[0].rpm == 60
    xml = ET.fromstring(render(config, [{"organization_id": str(org), "subscription_id": str(sub)}]))
    assert not xml.findall(".//return-response")
    assert len(xml.findall("choose")) == 2


@pytest.mark.parametrize("field, value", [("rpm", 61), ("tpm", 300001), ("token_quota", 20000001),
                                         ("request_quota", 50001), ("rpm", True), ("tpm", "20")])
def test_operator_ceilings_strict_types(field, value):
    with pytest.raises(ValidationError):
        PocLimits.model_validate({field: value})


def test_empty_read_does_not_initialize_or_require_gateway_page(env, poc):
    row = env.client.get("/api/admin/content-safety-settings", headers=env.admin).json()["items"][0]
    assert row["version"] == 0 and row["desired"] is None
    assert row["max_rpm"] == 60 and row["max_tpm"] == 300000
    assert row["effective_defaults"]["defaults"]["rpm"] == 60
    assert row["effective_defaults"]["safety"]["protected_material"] is False
    assert poc.writes == []
    response = env.client.put(SAFETY, headers=env.admin, json={"expected_version": 0,
        "configuration": poc_safety().model_dump(), "reason": "Explicit release bootstrap"})
    assert response.status_code == 200, response.text
    assert response.json()["published_version"] == 1


def test_publish_etag_history_stale_versions_and_failed_edit_preserves_published(env, poc):
    assert save(env).status_code == 200
    assert save(env).status_code == 409
    config = PocGatewayConfiguration(defaults=PocLimits(rpm=59)).model_dump(mode="json")
    poc.fail = True
    assert save(env, config, 1).status_code == 502
    row = env.client.get("/api/admin/gateway-settings", headers=env.admin).json()["items"][0]
    assert row["published_version"] == 1 and row["version"] == 2
    assert row["published"]["configuration"]["defaults"]["rpm"] == 60
    assert row["desired"]["state"] == "failed"
    assert save(env, config, 2).status_code == 409
    poc.fail = False
    assert env.client.post(URL + "/reconcile", headers=env.admin, json={"expected_version": 2}).status_code == 200
    assert env.client.get(URL + "/history", headers=env.admin).json()["total"] == 2


def test_ownership_safety_floors_and_orthogonal_saves(env, poc):
    org = env.orgs["customer"]
    config = PocGatewayConfiguration().model_dump(mode="json")
    config["overrides"] = [{"organization_id": org, "subscription_id": str(uuid4()),
                            "limits": {"rpm": 2}, "safety": None}]
    assert save(env, config).status_code == 422
    config["overrides"][0]["subscription_id"] = None
    assert save(env, config).status_code == 200
    response = env.client.put(SAFETY, headers=env.admin, json={"expected_version": 1,
        "organization_id": org, "configuration": poc_safety().model_dump() | {"hate": 2},
        "reason": "Reviewed threshold", "acknowledge_relaxation": False})
    assert response.status_code == 422
    body = {"expected_version": 1, "organization_id": org,
            "configuration": poc_safety().model_dump() | {"hate": 2},
            "reason": "Reviewed APIM only relaxation", "acknowledge_relaxation": True}
    response = env.client.put(SAFETY, headers=env.admin, json=body)
    assert response.status_code == 200, response.text
    new = response.json()["desired"]["configuration"]
    assert new["overrides"][0]["limits"]["rpm"] == 2
    assert save(env, config, 2).status_code == 409  # cannot erase the safety page's work
    body.update(expected_version=2, inherit=True)
    assert env.client.put(SAFETY, headers=env.admin, json=body).status_code == 200
    body.update(expected_version=3, inherit=False,
                configuration=poc_safety().model_dump() | {"prompt_attack": False})
    assert env.client.put(SAFETY, headers=env.admin, json=body).status_code == 422


def test_unknown_new_subscription_is_ready_without_settings_publication(env, poc):
    with Session(env.db_engine) as db:
        assert subscription_access(db, env.settings, str(uuid4()))[0] == "ready"
    assert poc.writes == []


def test_unknown_new_org_subscription_stays_ready_during_failed_optional_publication(env, poc):
    assert env.settings.gateway_controls_v2_enabled is False
    assert save(env).status_code == 200
    last_published = poc.values["dev-unified"]
    poc.fail = True
    config = PocGatewayConfiguration(overrides=[PocOverride(
        organization_id=UUID(env.orgs["customer"]), limits=PocLimits(rpm=59))])
    assert save(env, config.model_dump(mode="json"), 1).status_code == 502
    assert poc.values["dev-unified"] == last_published
    with Session(env.db_engine) as db:
        for _ in range(3):
            assert subscription_access(db, env.settings, str(uuid4()))[0] == "ready"
            limits, safety = effective(config, str(uuid4()), str(uuid4()))
            assert limits == PocLimits() and safety == poc_safety()
    assert "return-response" not in render(config, [])


def test_existing_zero_version_head_initializes_using_default_fragment(env, poc):
    from aiflux.models import GatewaySettings
    with Session(env.db_engine) as db:
        db.add(GatewaySettings(scope="dev-unified", version=0))
        db.commit()
    response = save(env)
    assert response.status_code == 200, response.text
    assert response.json()["published_version"] == 1


def test_drift_never_overwrites_current_fragment_and_customer_cannot_publish(env, poc):
    poc.values["dev-unified"] = '<fragment><set-variable name="unknown" value="1" /></fragment>'
    assert save(env).status_code == 409
    assert poc.writes == []
    assert env.client.put(URL, headers=env.customer, json={"configuration": {}, "expected_version": 0,
        "reason": "not authorized"}).status_code == 403


def test_compiler_capacity_is_bounded():
    from fastapi import HTTPException
    bindings = [{"organization_id": str(uuid4()), "subscription_id": str(uuid4())} for _ in range(1000)]
    with pytest.raises(HTTPException) as exc:
        render(PocGatewayConfiguration(), bindings)
    assert exc.value.status_code == 422


def test_literal_quota_branches_preserve_one_increment_key_window_and_epoch():
    config = PocGatewayConfiguration(defaults=PocLimits(request_quota=900), overrides=[
        PocOverride(organization_id=uuid4(), limits=PocLimits(request_quota=50)),
        PocOverride(organization_id=uuid4(), limits=PocLimits(request_quota=50)),
    ])
    root = ET.fromstring(render(config, []))
    quota_choice = root.findall("choose")[-1]
    assert [n.get("calls") for n in quota_choice.findall(".//quota-by-key")] == ["50", "900"]
    assert quota_choice.find("otherwise/quota-by-key").get("calls") == "900"
    assert quota_choice.find("when").get("condition") == '@((int)context.Variables["aiflux-poc-request-quota"] == 50)'
    assert len(quota_choice.findall("otherwise/quota-by-key")) == 1
    for branch in quota_choice:
        assert len(branch) == 1 and branch[0].tag == "quota-by-key"
        assert branch[0].get("counter-key") == '@("project-demo:" + context.Subscription.Id)'
        assert branch[0].get("renewal-period") == "86400"
        assert set(branch[0].attrib) == {"calls", "renewal-period", "counter-key"}


def test_new_subscription_without_initialization_or_failed_refresh_is_active_and_ready(env, poc):
    from test_admin_subscriptions import SubscriptionApim, create
    apim = SubscriptionApim()
    apim.values["dev-unified"] = render(PocGatewayConfiguration(), [])
    env.app.state.apim = apim
    first = create(env)
    assert first.status_code == 201
    assert first.json()["state"] == "active" and first.json()["gateway_access"] == "ready"
    assert apim.writes == []
    assert save(env).status_code == 200
    apim.fail = True
    second = create(env)
    assert second.status_code == 201, second.text
    assert second.json()["state"] == "active" and second.json()["gateway_access"] == "ready"
    assert "optional" in second.json()["gateway_message"].lower()


def test_new_subscription_automatically_publishes_existing_organization_override(env, poc):
    from test_admin_subscriptions import SubscriptionApim, create
    apim = SubscriptionApim()
    apim.values["dev-unified"] = render(PocGatewayConfiguration(), [])
    env.app.state.apim = apim
    config = PocGatewayConfiguration(overrides=[PocOverride(
        organization_id=UUID(env.orgs["customer"]), limits=PocLimits(rpm=10))])
    assert save(env, config.model_dump(mode="json")).status_code == 200
    created = create(env)
    assert created.status_code == 201 and created.json()["gateway_access"] == "ready"
    root = ET.fromstring(apim.values["dev-unified"])
    assert created.json()["id"] in root.find("set-variable[@name='aiflux-poc-organization']").get("value")
    assert root.find(".//when/set-variable[@name='aiflux-poc-rpm']").get("value") == "@(10)"


@pytest.mark.parametrize("reason,substage,status", [
    ("missing_state", "resource_readiness", 409),
    ("terminal_failure", "resource_readiness", 409),
    ("malformed_xml", "resource_readiness", 200),
    ("readiness_timeout", "resource_readiness", 504),
    ("invalid_header", "header_validation", None),
    ("transport_error", "conditional_put", None),
    ("authentication_error", "conditional_put", None),
    ("http_error", "conditional_put", 503),
    ("invalid_json", "operation_poll", 200),
])
def test_safe_publisher_diagnostics_keep_public_502_and_same_version_reconcile(
        env, poc, monkeypatch, caplog, reason, substage, status):
    from aiflux.apim import ApimError
    assert save(env).status_code == 200
    poison = 'POISON-key-token-<fragment secret="payload"/>https://evil.invalid/?sig=secret'
    attempts = []
    def uncertain(scope, value, etag):
        attempts.append((scope, etag))
        # Model the historical stored-content/failed-response case. Reconcile
        # must independently read it, not blindly replay this PUT.
        poc.values[scope] = value
        poc.versions[scope] += 1
        error = ApimError(status, poison, reason=reason, diagnostics={"substage": substage})
        error.diagnostics.update({"url": poison, "headers": poison, "xml": poison,
                                  "state": poison, "elapsed_ms": poison, "poll_count": 999999})
        raise error from ValueError(poison)
    monkeypatch.setattr(poc, "put_settings_fragment", uncertain)
    config = PocGatewayConfiguration(defaults=PocLimits(rpm=59)).model_dump(mode="json")
    result = save(env, config, 1)
    assert result.status_code == 502
    assert result.json() == {"detail": "Optional overrides publication incomplete; reconcile to retry. Default access is not gated."}
    row = env.client.get("/api/admin/gateway-settings", headers=env.admin).json()["items"][0]
    assert row["version"] == 2 and row["published_version"] == 1 and row["desired"]["state"] == "failed"
    assert row["published"]["configuration"]["defaults"]["rpm"] == 60
    assert save(env, config, 2).status_code == 409
    records = [r for r in caplog.records if r.name == "aiflux.gateway_settings"]
    assert len(records) == 1
    record = records[0]
    assert record.apim_diagnostics["reason"] == reason
    assert record.apim_diagnostics["substage"] == substage
    assert "conditional_put_and_readiness" in record.getMessage()
    assert not record.exc_info
    assert "POISON" not in caplog.text and "sig=secret" not in caplog.text
    assert poison not in repr(record.__dict__) and poison not in result.text
    retry = env.client.post(URL + "/reconcile", headers=env.admin, json={"expected_version": 2})
    assert retry.status_code == 200
    assert retry.json()["version"] == retry.json()["published_version"] == 2
    assert retry.json()["desired"]["state"] == "published"
    assert len(attempts) == 1
    assert env.client.get(URL + "/history", headers=env.admin).json()["total"] == 2


@pytest.mark.parametrize("failure", ["drift", "readback"])
def test_outer_poc_drift_and_readback_have_distinct_safe_diagnostics(env, poc, caplog, failure):
    assert save(env).status_code == 200
    config = PocGatewayConfiguration(defaults=PocLimits(rpm=59)).model_dump(mode="json")
    if failure == "readback":
        poc.bad_readback = True
        assert save(env, config, 1).status_code == 502
        expected = {"reason": "readback_mismatch", "substage": "strict_readback", "error_status": 409,
                    "canonical_match": False}
    else:
        poc.fail = True
        assert save(env, config, 1).status_code == 502
        poc.fail = False
        writes = len(poc.writes)
        poc.versions["dev-unified"] += 1
        assert env.client.post(URL + "/reconcile", headers=env.admin,
                               json={"expected_version": 2}).status_code == 502
        assert len(poc.writes) == writes  # CAS drift never sends another PUT.
        expected = {"reason": "drift_conflict", "substage": "baseline_read", "error_status": 412,
                    "etag_present": True, "canonical_match": False}
    records = [r for r in caplog.records if r.name == "aiflux.gateway_settings"]
    assert records[-1].apim_diagnostics == expected


def test_poc_log_sink_refilters_mutated_status_reason_and_stage(env, poc, monkeypatch, caplog):
    from aiflux.apim import ApimError
    assert save(env).status_code == 200
    poison = "POISON-https://evil.invalid/?sig=secret-<fragment/>"
    def fail(*args):
        error = ApimError()
        error.status_code = poison
        error.diagnostics = {"reason": poison, "substage": poison, "status": poison,
                     "response_status": poison, "error_status": poison,
                             "canonical_match": poison, "pending_operation": poison}
        raise error
    monkeypatch.setattr(poc, "put_settings_fragment", fail)
    config = PocGatewayConfiguration(defaults=PocLimits(rpm=59)).model_dump(mode="json")
    assert save(env, config, 1).status_code == 502
    record = next(r for r in caplog.records if r.name == "aiflux.gateway_settings")
    assert record.apim_diagnostics == {"reason": "operation_failed"}
    assert "POISON" not in caplog.text and poison not in repr(record.__dict__)


@pytest.mark.parametrize("reason", ["missing_state", "null_state", "terminal_failure", "malformed_xml",
                                   "readiness_timeout", "invalid_header", "invalid_json"])
def test_real_fragment_publisher_failure_through_public_api_remains_reconcilable(
        env, poc, monkeypatch, caplog, reason):
    import httpx
    from aiflux.apim import ApimClient
    assert save(env).status_code == 200
    publisher = ApimClient(env.settings)
    env.app.state.apim = publisher
    resource = publisher._fragment_url("dev-unified")
    state = {"desired": None, "reconcile": False}
    calls = []
    def send(method, url, body=None, etag=None):
        calls.append((method, url))
        assert url in (resource, resource + "&format=xml")
        if method == "PUT":
            assert not state["reconcile"]  # Never replay a PUT after stored-content failure.
            assert etag == '"1"'
            state["desired"] = body["properties"]["value"]
            if reason == "invalid_header":
                return httpx.Response(200, headers={"Location": "https://evil.invalid/?sig=POISON"})
            return httpx.Response(202)
        if state["desired"] is None:
            return httpx.Response(200, json={"properties": {"value": poc.values["dev-unified"]}},
                                  headers={"ETag": '"1"'})
        if reason == "invalid_json" and not state["reconcile"]:
            return httpx.Response(200, text="POISON-key-token-<fragment/>")
        properties = {"value": state["desired"], "provisioningState": "Succeeded"}
        if not state["reconcile"]:
            if reason == "missing_state":
                properties.pop("provisioningState")
            elif reason == "null_state":
                properties["provisioningState"] = None
            elif reason == "terminal_failure":
                properties["provisioningState"] = "Failed"
            elif reason == "malformed_xml":
                properties["value"] = "<fragment>POISON-key-token"
            elif reason == "readiness_timeout":
                properties["value"] = "<fragment />"
        return httpx.Response(200, json={"properties": properties}, headers={"ETag": '"2"'})
    monkeypatch.setattr(publisher, "_send", send)
    monkeypatch.setattr("aiflux.apim.time.sleep", lambda _: None)
    monkeypatch.setattr("aiflux.apim.time.monotonic", lambda: 0)
    config = PocGatewayConfiguration(defaults=PocLimits(rpm=59)).model_dump(mode="json")
    result = save(env, config, 1)
    assert result.status_code == 502 and "POISON" not in result.text
    record = next(r for r in caplog.records if r.name == "aiflux.gateway_settings")
    assert record.apim_diagnostics["reason"] == ("missing_state" if reason == "null_state" else reason)
    assert record.apim_diagnostics["response_status"] == 200
    if reason == "invalid_header":
        assert "error_status" not in record.apim_diagnostics
    else:
        expected_status = (504 if reason == "readiness_timeout" else
                           200 if reason in ("invalid_json", "malformed_xml") else 409)
        assert record.apim_diagnostics["error_status"] == expected_status
    if reason in ("null_state", "missing_state"):
        assert record.apim_diagnostics["state_present"] is (reason == "null_state")
        assert record.apim_diagnostics["state"] == ("null" if reason == "null_state" else "missing")
    assert "POISON" not in caplog.text and not record.exc_info
    assert [method for method, _ in calls[:3]] == ["GET", "GET", "PUT"]
    polls = 0 if reason == "invalid_header" else 12 if reason == "readiness_timeout" else 1
    assert len(calls) == 3 + polls
    assert [method for method, _ in calls].count("PUT") == 1
    state["reconcile"] = True
    result = env.client.post(URL + "/reconcile", headers=env.admin, json={"expected_version": 2})
    assert result.status_code == 200
    assert result.json()["version"] == result.json()["published_version"] == 2
    assert [method for method, _ in calls[-2:]] == ["GET", "GET"]
    assert [method for method, _ in calls].count("PUT") == 1
    from sqlalchemy import select
    from aiflux.models import AuditEvent
    with Session(env.db_engine) as db:
        actions = [event.action for event in db.scalars(select(AuditEvent))]
    assert actions.count("gateway.settings.requested") == 2
    assert actions.count("gateway.settings.failed") == 1
    assert actions.count("gateway.settings.published") == 2
    assert len(actions) == 5


@pytest.mark.parametrize("bad_final_readback", [False, True])
def test_delayed_readiness_still_requires_independent_final_readback_and_cas(
        env, poc, monkeypatch, bad_final_readback):
    import httpx
    from aiflux.apim import ApimClient
    assert save(env).status_code == 200
    publisher = ApimClient(env.settings)
    env.app.state.apim = publisher
    resource = publisher._fragment_url("dev-unified")
    calls = []
    desired = None
    reads = 0
    def send(method, url, body=None, etag=None):
        nonlocal desired, reads
        calls.append((method, url))
        if method == "PUT":
            assert etag == '"1"'
            desired = body["properties"]["value"]
            return httpx.Response(202)
        assert url == resource + "&format=xml"
        if desired is None:
            value = poc.values["dev-unified"]
            state = "Succeeded"
        else:
            reads += 1
            state = "InProgress" if reads == 1 else "Succeeded"
            value = "<fragment />" if reads == 3 and bad_final_readback else desired
        return httpx.Response(200, json={"properties": {"value": value, "provisioningState": state}},
                              headers={"ETag": '"1"' if desired is None else '"2"'})
    monkeypatch.setattr(publisher, "_send", send)
    monkeypatch.setattr("aiflux.apim.time.sleep", lambda _: None)
    monkeypatch.setattr("aiflux.apim.time.monotonic", lambda: 0)
    config = PocGatewayConfiguration(defaults=PocLimits(rpm=59)).model_dump(mode="json")
    result = save(env, config, 1)
    assert result.status_code == (502 if bad_final_readback else 200)
    assert [method for method, _ in calls] == ["GET", "GET", "PUT", "GET", "GET", "GET"]
    row = env.client.get("/api/admin/gateway-settings", headers=env.admin).json()["items"][0]
    assert row["version"] == 2
    assert row["published_version"] == (1 if bad_final_readback else 2)
    assert row["desired"]["state"] == ("failed" if bad_final_readback else "published")
    assert save(env, config, 1).status_code == 409
    assert len(calls) == 6  # Stale CAS cannot publish or re-read ARM.