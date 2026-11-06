"""Synthetic ARM responses only; never credentials, writes or live inference."""
from types import SimpleNamespace

import httpx
import pytest

from aiflux.apim import ApimClient, ApimError


@pytest.fixture
def client(env, monkeypatch):
    env.settings.gateway_settings_scopes = ["dev-unified"]
    env.settings.gateway_controls_poc_enabled = True
    result = ApimClient(env.settings)
    result._credential = SimpleNamespace(get_token=lambda _: SimpleNamespace(token="synthetic"))
    monkeypatch.setattr("aiflux.apim.time.sleep", lambda _: None)
    return result


@pytest.mark.parametrize("status", [200, 201, 202])
def test_documented_service_operation_uses_exact_fragment_readiness_not_broader_rbac(client, monkeypatch, status):
    url = client._fragment_url("dev-unified")
    operation = url.split("/policyFragments/")[0] + "/tenant/operationResults/synthetic?api-version=2024-05-01"
    desired = '<fragment><set-variable name="x" value="@(59)" /></fragment>'
    calls = []
    replies = iter([
        httpx.Response(status, headers={"Azure-AsyncOperation": operation, "Location": url + "&asyncId=synthetic"}),
        httpx.Response(200, json={"properties": {"value": "<fragment />", "provisioningState": "InProgress"}}, headers={"ETag": '"old"'}),
        httpx.Response(200, json={"properties": {"value": desired, "provisioningState": "Succeeded"}}, headers={"ETag": '"new"'}),
    ])
    def request(method, target, **kwargs):
        calls.append((method, target, kwargs))
        return next(replies)
    monkeypatch.setattr(httpx, "request", request)
    client.put_settings_fragment("dev-unified", desired, '"old"')
    assert len(calls) == 3
    assert calls[0][2]["headers"]["If-Match"] == '"old"'
    assert all(method == "GET" and target == url + "&format=rawxml" for method, target, _ in calls[1:])


def test_accepted_without_operation_header_waits_for_exact_succeeded_content(client, monkeypatch):
    desired = '<fragment><set-variable name="x" value="@(59)" /></fragment>'
    replies = iter([
        httpx.Response(202),
        httpx.Response(202),
        httpx.Response(200, json={"properties": {"value": desired, "provisioningState": "Succeeded"}}, headers={"ETag": '"new"'}),
    ])
    monkeypatch.setattr(httpx, "request", lambda *a, **k: next(replies))
    client.put_settings_fragment("dev-unified", desired, '"old"')


@pytest.mark.parametrize("defect", ["Failed", "Canceled", "mismatch", "missing_etag", "missing_state"])
def test_readiness_never_claims_success_without_exact_successful_resource(client, monkeypatch, defect):
    calls = []
    def request(method, url, **kwargs):
        calls.append(method)
        if method == "PUT":
            return httpx.Response(202)
        state = None if defect == "missing_state" else (defect if defect in ("Failed", "Canceled") else "Succeeded")
        return httpx.Response(200, json={"properties": {"value": "<fragment />" if defect == "mismatch" else "<fragment><base /></fragment>", "provisioningState": state}},
                              headers={} if defect == "missing_etag" else {"ETag": '"new"'})
    monkeypatch.setattr(httpx, "request", request)
    with pytest.raises(ApimError):
        client.put_settings_fragment("dev-unified", "<fragment><base /></fragment>", '"old"')
    assert calls.count("PUT") == 1
    assert len(calls) <= 13


@pytest.mark.parametrize("header", ["Azure-AsyncOperation", "Location"])
@pytest.mark.parametrize("url", ["https://evil.invalid/path", "https://management.azure.com/another-resource", "https://management.azure.com@evil.invalid/path"])
def test_untrusted_polling_headers_never_receive_token_or_trigger_another_write(client, monkeypatch, header, url):
    calls = []
    def request(*args, **kwargs):
        calls.append(args)
        return httpx.Response(202, headers={header: url})
    monkeypatch.setattr(httpx, "request", request)
    with pytest.raises(ApimError):
        client.put_settings_fragment("dev-unified", "<fragment />", '"old"')
    assert len(calls) == 1