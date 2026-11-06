"""Synthetic publisher diagnostics: no credentials, ARM requests or deployment."""
from types import SimpleNamespace

import httpx
import pytest
from azure.core.exceptions import ClientAuthenticationError

from aiflux.apim import ApimError, safe_apim_diagnostics
from test_fragment_encoding import client

POISON = 'POISON-key-token-<fragment secret="payload"/>\nhttps://evil.invalid/?sig=secret'
DESIRED = '<fragment><set-variable name="x" value="1" /></fragment>'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected real credential or HTTP request")
    monkeypatch.setattr("aiflux.apim.DefaultAzureCredential", forbidden)
    monkeypatch.setattr(httpx, "request", forbidden)
    monkeypatch.setattr("aiflux.apim.time.sleep", lambda _: None)
    monkeypatch.setattr("aiflux.apim.time.monotonic", lambda: 0)


def response(state="Succeeded", value=DESIRED, etag='"next"', **kwargs):
    properties = {"value": value}
    if state != "omit":
        properties["provisioningState"] = state
    return httpx.Response(200, json={"properties": properties},
                          headers={"ETag": etag} if etag else {}, **kwargs)


def drive(monkeypatch, c, replies):
    calls = []
    iterator = iter(replies)
    def send(method, url, body=None, etag=None):
        calls.append((method, url, body, etag))
        reply = next(iterator)
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(c, "_send", send)
    return calls


def assert_safe(error):
    assert str(error) == "APIM management operation failed"
    assert POISON not in repr(error.diagnostics)
    assert "secret" not in repr(error.diagnostics)
    assert error.diagnostics == safe_apim_diagnostics(error.diagnostics)


def test_diagnostic_filter_is_closed_typed_bounded_and_backwards_compatible():
    class Dangerous:
        def __str__(self):
            pytest.fail("Never stringify caller data")
        def __repr__(self):
            pytest.fail("Never represent caller data")
    class StringSubclass(str):
        pass
    candidate = {"reason": POISON, "substage": Dangerous(), "status": 200,
                 "response_status": True, "error_status": StringSubclass("409"),
                 "elapsed_ms": 3600001, "poll_count": 13, "state": POISON,
                 "etag_present": 1, "canonical_match": POISON, "operation_path": POISON,
                 "location_path": StringSubclass("exact_resource"),
                 "operation_present": False, "state_present": True, "xml": Dangerous(),
                 POISON: POISON, "headers": {"Authorization": POISON}}
    assert safe_apim_diagnostics(candidate) == {"operation_present": False, "state_present": True}
    assert safe_apim_diagnostics(Dangerous()) == {}
    assert safe_apim_diagnostics({"response_status": 99, "error_status": 600,
                                  "elapsed_ms": -1, "poll_count": -1}) == {}
    assert safe_apim_diagnostics({"response_status": 600, "error_status": False, "poll_count": False}) == {}
    assert safe_apim_diagnostics({"response_status": 200, "error_status": 599,
                                  "elapsed_ms": 3600000, "poll_count": 12}) == {
        "response_status": 200, "error_status": 599, "elapsed_ms": 3600000, "poll_count": 12}
    error = ApimError(504, POISON)
    assert error.status_code == 504 and error.pending_operation == POISON
    assert_safe(error)


@pytest.mark.parametrize("state,reason,present,label", [
    ("omit", "missing_state", False, "missing"),
    (None, "missing_state", True, "null"),
    ("Failed", "terminal_failure", True, "Failed"),
    ("Canceled", "terminal_failure", True, "Canceled"),
    ("Cancelled", "terminal_failure", True, "Cancelled"),
    (POISON, "unknown_state", True, "unknown"),
    ([POISON], "unknown_state", True, "unknown"),
])
def test_resource_state_failures_remain_rejected(monkeypatch, state, reason, present, label):
    c = client()
    resource = c._fragment_url("dev-unified")
    operation = resource.split("/policyFragments/")[0] + "/entityOperationResults/abc?sig=secret"
    calls = drive(monkeypatch, c, [httpx.Response(200, headers={"Azure-AsyncOperation": operation}),
                                 response(state)])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    error = caught.value
    assert error.status_code == 409
    assert error.diagnostics.items() >= {"reason": reason, "substage": "resource_readiness",
        "state_present": present, "state": label, "poll_count": 1, "etag_present": True,
        "operation_present": True, "operation_path": "service_operation", "elapsed_ms": 0,
        "response_status": 200, "error_status": 409}.items()
    assert calls == [("PUT", resource, calls[0][2], '"before"'),
                     ("GET", resource + "&format=xml", None, None)]
    assert_safe(error)


@pytest.mark.parametrize("value,etag,reason", [
    ("<fragment>" + POISON, '"next"', "malformed_xml"),
    (DESIRED, None, "invalid_fragment"),
    (DESIRED, "*", "invalid_fragment"),
    (DESIRED, "x" * 201, "invalid_fragment"),
])
def test_readiness_xml_and_etag_failures(monkeypatch, value, etag, reason):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(202), response(value=value, etag=etag)])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.diagnostics["reason"] == reason
    assert caught.value.diagnostics["substage"] == "resource_readiness"
    assert len(calls) == 2
    assert_safe(caught.value)


@pytest.mark.parametrize("state,value,match", [
    ("Succeeded", "<fragment />", False), ("InProgress", DESIRED, True),
])
def test_readiness_timeout_keeps_twelve_poll_budget_and_no_put_retry(monkeypatch, state, value, match):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(202), *[response(state, value) for _ in range(12)]])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.status_code == 504
    assert caught.value.diagnostics.items() >= {"reason": "readiness_timeout", "poll_count": 12,
        "canonical_match": match, "state": state}.items()
    assert [call[0] for call in calls] == ["PUT"] + ["GET"] * 12
    assert all(url.split("?")[0] == c._fragment_url("dev-unified").split("?")[0]
               for _, url, _, _ in calls)


@pytest.mark.parametrize("header", ["Azure-AsyncOperation", "Location"])
@pytest.mark.parametrize("target", ["https://evil.invalid/?sig=secret", "https://[bad/?sig=secret",
                                     "https://management.azure.com/another-resource?sig=secret"])
def test_invalid_headers_never_follow_or_log_targets(monkeypatch, header, target):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(200, headers={header: target})])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    kind = "operation" if header == "Azure-AsyncOperation" else "location"
    assert caught.value.diagnostics.items() >= {"reason": "invalid_header", "substage": "header_validation",
        kind + "_present": True, kind + "_path": "invalid"}.items()
    assert len(calls) == 1
    assert_safe(caught.value)


@pytest.mark.parametrize("kind,reason,status,pending", [
    ("auth", "authentication_error", None, None),
    ("transport", "transport_error", None, "unknown"),
    ("http", "http_error", 503, "unknown"),
    ("forbidden", "http_error", 403, None),
    ("cas", "http_error", 412, None),
])
def test_conditional_put_send_errors_are_safe_and_not_retried(monkeypatch, kind, reason, status, pending):
    c = client()
    def token(scope):
        if kind == "auth":
            raise ClientAuthenticationError(POISON)
        return SimpleNamespace(token=POISON)
    c._credential = SimpleNamespace(get_token=token)
    calls = []
    def request(method, url, **kwargs):
        calls.append(method)
        assert kwargs["headers"]["If-Match"] == '"before"'
        if kind == "transport":
            raise httpx.ConnectError(POISON)
        return httpx.Response(status, text=POISON, headers={"x-ms-request-id": POISON})
    monkeypatch.setattr(httpx, "request", request)
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.status_code == status and caught.value.pending_operation == pending
    assert caught.value.diagnostics["reason"] == reason
    assert caught.value.diagnostics["substage"] == "conditional_put"
    if kind in ("http", "forbidden", "cas"):
        assert caught.value.diagnostics["response_status"] == status
        assert caught.value.diagnostics["error_status"] == status
    else:
        assert "response_status" not in caught.value.diagnostics
        assert "error_status" not in caught.value.diagnostics
    assert calls == ([] if kind == "auth" else ["PUT"])
    assert_safe(caught.value)


@pytest.mark.parametrize("reply,reason", [
    (httpx.Response(200, text=POISON), "invalid_json"),
    (httpx.Response(200, json=[POISON]), "invalid_json"),
    (httpx.Response(200, json={"properties": POISON}), "invalid_fragment"),
    (httpx.Response(200, json={"properties": {"value": DESIRED}}), "invalid_fragment"),
])
def test_fragment_get_invalid_json_and_shape(monkeypatch, reply, reason):
    c = client()
    calls = drive(monkeypatch, c, [reply])
    with pytest.raises(ApimError) as caught:
        c.get_settings_fragment("dev-unified")
    assert caught.value.diagnostics.items() >= {"reason": reason, "substage": "fragment_get"}.items()
    assert len(calls) == 1
    assert_safe(caught.value)


@pytest.mark.parametrize("state,reason", [(None, "missing_state"), ("Failed", "terminal_failure"),
                                         (POISON, "unknown_state")])
def test_exact_resource_operation_status_failure(monkeypatch, state, reason):
    c = client()
    operation = c._fragment_url("dev-unified") + "&sig=secret"
    calls = drive(monkeypatch, c, [httpx.Response(200, headers={"Azure-AsyncOperation": operation}),
                                 httpx.Response(200, json={"status": state})])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.diagnostics.items() >= {"reason": reason, "substage": "operation_poll",
                                               "poll_count": 1, "operation_path": "exact_resource"}.items()
    assert len(calls) == 2 and calls[1][1] == operation
    assert_safe(caught.value)


def test_operation_timeout_is_distinct_from_readiness_timeout(monkeypatch):
    c = client()
    operation = c._fragment_url("dev-unified") + "&sig=secret"
    calls = drive(monkeypatch, c, [httpx.Response(200, headers={"Azure-AsyncOperation": operation}),
        *[httpx.Response(200, json={"status": "Running"}) for _ in range(12)]])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.diagnostics.items() >= {"reason": "operation_timeout", "substage": "operation_poll",
                                               "poll_count": 12, "state": "Running"}.items()
    assert len(calls) == 13


def test_success_does_not_add_readback_or_change_cas(monkeypatch):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(202), response()])
    assert c.put_settings_fragment("dev-unified", DESIRED, '"before"') is None
    assert len(calls) == 2 and calls[0][3] == '"before"'
    assert calls[0][2]["properties"]["value"] == DESIRED


@pytest.mark.parametrize("mode", ["readiness", "operation"])
@pytest.mark.parametrize("reply,reason", [
    (httpx.Response(200, text=POISON), "invalid_json"),
    (httpx.Response(200, json=[POISON]), "invalid_json"),
    (ApimError(reason="transport_error"), "transport_error"),
    (ApimError(403, reason="http_error"), "http_error"),
    (ApimError(reason="authentication_error"), "authentication_error"),
])
def test_later_poll_errors_have_current_context_not_stale_success(monkeypatch, mode, reply, reason):
    c = client()
    if isinstance(reply, ApimError):
        reply = ApimError(reply.status_code, reason=reason)
    resource = c._fragment_url("dev-unified")
    if mode == "readiness":
        first = httpx.Response(202)
        previous = response("InProgress")
    else:
        first = httpx.Response(200, headers={"Azure-AsyncOperation": resource + "&sig=secret"})
        previous = httpx.Response(200, json={"status": "Running"})
    calls = drive(monkeypatch, c, [first, previous, reply])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    diagnostic = caught.value.diagnostics
    assert diagnostic["reason"] == reason and diagnostic["poll_count"] == 2
    assert diagnostic["substage"] == ("resource_readiness" if mode == "readiness" else "operation_poll")
    assert not {"state", "state_present", "canonical_match"} & diagnostic.keys()
    if reason in ("transport_error", "authentication_error"):
        assert "response_status" not in diagnostic and "etag_present" not in diagnostic
        assert "error_status" not in diagnostic
    assert len(calls) == 3
    assert_safe(caught.value)


def test_invalid_readiness_properties_is_not_missing_state(monkeypatch):
    c = client()
    drive(monkeypatch, c, [httpx.Response(202), httpx.Response(200, json={"properties": POISON})])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.diagnostics["reason"] == "invalid_properties"
    assert "state" not in caught.value.diagnostics
    assert_safe(caught.value)


def test_malformed_desired_xml_does_not_issue_readiness_get(monkeypatch):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(202)])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", "<fragment>" + POISON, '"before"')
    assert caught.value.diagnostics["reason"] == "malformed_xml"
    assert caught.value.diagnostics["poll_count"] == 0
    assert len(calls) == 1
    assert_safe(caught.value)


@pytest.mark.parametrize("mode", ["readiness", "operation"])
def test_existing_sixty_second_deadline_still_stops_polling(monkeypatch, mode):
    c = client()
    clock = [0]
    monkeypatch.setattr("aiflux.apim.time.monotonic", lambda: clock[0])
    first = httpx.Response(202) if mode == "readiness" else httpx.Response(200,
        headers={"Azure-AsyncOperation": c._fragment_url("dev-unified") + "&sig=secret"})
    calls = []
    def send(method, url, *args):
        calls.append((method, url))
        if method == "PUT":
            return first
        clock[0] = 60
        return response("InProgress") if mode == "readiness" else httpx.Response(200, json={"status": "Running"})
    monkeypatch.setattr(c, "_send", send)
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.diagnostics["poll_count"] == 1
    assert caught.value.diagnostics["elapsed_ms"] == 60000
    assert caught.value.diagnostics["reason"] == ("readiness_timeout" if mode == "readiness" else "operation_timeout")
    assert len(calls) == 2


def test_signed_exact_location_is_categorized_without_exposing_query(monkeypatch):
    c = client()
    location = c._fragment_url("dev-unified") + "&asyncId=POISON&asyncCode=200&sig=secret"
    calls = drive(monkeypatch, c, [httpx.Response(200, headers={"Location": location}), response("omit")])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.diagnostics.items() >= {"reason": "missing_state", "operation_present": False,
        "operation_path": "absent", "location_present": True, "location_path": "exact_resource"}.items()
    assert len(calls) == 2 and calls[1][1] == c._fragment_url("dev-unified") + "&format=xml"
    assert "POISON" not in repr(caught.value.diagnostics)


def test_location_cannot_expand_to_service_operation_scope(monkeypatch):
    c = client()
    location = c._fragment_url("dev-unified").split("/policyFragments/")[0] + "/entityOperationResults/abc?sig=secret"
    calls = drive(monkeypatch, c, [httpx.Response(200, headers={"Location": location})])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.diagnostics["reason"] == "invalid_header"
    assert caught.value.diagnostics["location_path"] == "invalid"
    assert len(calls) == 1


@pytest.mark.parametrize("state", ["InProgress", "Running", "Accepted", "Updating"])
def test_exact_pending_content_waits_for_explicit_succeeded(monkeypatch, state):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(202), response(state), response()])
    c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert [call[0] for call in calls] == ["PUT", "GET", "GET"]
    assert calls[0][3] == '"before"'
    assert all(call[1] == c._fragment_url("dev-unified") + "&format=xml" for call in calls[1:])


@pytest.mark.parametrize("state", ["omit", None, "Failed", "Canceled", "Cancelled", "unrecognized"])
def test_exact_content_after_pending_never_overrides_bad_state(monkeypatch, state):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(202), response("InProgress"), response(state)])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    diagnostic = caught.value.diagnostics
    assert diagnostic["poll_count"] == 2
    assert diagnostic["response_status"] == 200 and diagnostic["error_status"] == 409
    assert diagnostic["state_present"] is (state != "omit")
    if state is None:
        assert diagnostic["state"] == "null"
    assert [call[0] for call in calls] == ["PUT", "GET", "GET"]
    assert_safe(caught.value)


@pytest.mark.parametrize("state,value", [("Succeeded", "<fragment />"), ("InProgress", DESIRED)])
def test_timeout_separates_successful_get_from_synthetic_error(monkeypatch, state, value):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(202), *[response(state, value) for _ in range(12)]])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    assert caught.value.diagnostics.items() >= {
        "response_status": 200, "error_status": 504, "poll_count": 12}.items()
    assert "status" not in caught.value.diagnostics
    assert len(calls) == 13


def test_202_discards_previous_state_and_mismatch_facts(monkeypatch):
    c = client()
    calls = drive(monkeypatch, c, [httpx.Response(202), response("Succeeded", "<fragment />"),
        *[httpx.Response(202) for _ in range(11)]])
    with pytest.raises(ApimError) as caught:
        c.put_settings_fragment("dev-unified", DESIRED, '"before"')
    diagnostic = caught.value.diagnostics
    assert diagnostic["response_status"] == 202 and diagnostic["error_status"] == 504
    assert not {"state", "state_present", "canonical_match"} & diagnostic.keys()
    assert len(calls) == 13


@pytest.mark.parametrize("field", ["response_status", "error_status"])
@pytest.mark.parametrize("value", [True, 99, 600, "200", POISON])
def test_split_status_fields_remain_closed_typed_redacted(field, value):
    assert safe_apim_diagnostics({field: value}) == {}