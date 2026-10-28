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
    assert quota[0].attrib == {"calls": "1000", "renewal-period": "86400",
                                "counter-key": '@("project-demo:" + context.Subscription.Id)'}
    assert ET.canonicalize(xml, strip_text=True) == ET.canonicalize(
        Path("gateway/policies/poc-settings-defaults.xml").read_text(), strip_text=True)
    assert root.find("set-variable[@name='aiflux-poc-rpm']").get("value") == "@(60)"
    assert root.find("set-variable[@name='aiflux-poc-tpm']").get("value") == "@(2048)"
    assert root.find("set-variable[@name='aiflux-poc-request-quota']").get("value") == "@(1000)"
    assert root.find("set-variable[@name='aiflux-poc-token-quota']").get("value") == "@(10000)"


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


@pytest.mark.parametrize("field, value", [("rpm", 61), ("tpm", 2049), ("token_quota", 10001),
                                         ("request_quota", 1001), ("rpm", True), ("tpm", "20")])
def test_operator_ceilings_strict_types(field, value):
    with pytest.raises(ValidationError):
        PocLimits.model_validate({field: value})


def test_empty_read_does_not_initialize_or_require_gateway_page(env, poc):
    row = env.client.get("/api/admin/content-safety-settings", headers=env.admin).json()["items"][0]
    assert row["version"] == 0 and row["desired"] is None
    assert row["max_rpm"] == 60 and row["max_tpm"] == 2048
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
    assert [n.get("calls") for n in quota_choice.findall(".//quota-by-key")] == ["50", "900", "1000"]
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