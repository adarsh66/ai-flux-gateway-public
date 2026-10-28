import httpx
import pytest

from gateway.tools.probe_cors import preflight_result, probe

ORIGIN = "https://poc-ids-token-ex-customer.azurewebsites.net"
BASE = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"
HEADERS = {
    "Access-Control-Allow-Origin": ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST",
    "Access-Control-Allow-Headers": "Content-Type, Ocp-Apim-Subscription-Key",
}


@pytest.mark.parametrize(
    ("status", "diagnosis"),
    [
        (404, "route_not_found"),
        (503, "gateway_unavailable"),
        (401, "request_intercepted"),
        (403, "request_intercepted"),
        (302, "http_failure"),
        (500, "http_failure"),
    ],
)
def test_http_failure_is_not_misreported_as_origin_rejection(status, diagnosis):
    result = preflight_result(httpx.Response(status, headers=HEADERS), ORIGIN)
    assert not result["passed"]
    assert result["diagnosis"] == diagnosis


@pytest.mark.parametrize(
    ("overrides", "diagnosis"),
    [
        ({}, "preflight_allowed"),
        ({"Access-Control-Allow-Origin": "https://untrusted.invalid"}, "origin_not_allowed_or_cors_missing"),
        ({"Access-Control-Allow-Origin": "*"}, "origin_not_allowed_or_cors_missing"),
        ({"Access-Control-Allow-Methods": "GET"}, "post_not_allowed"),
        ({"Access-Control-Allow-Headers": "Content-Type"}, "headers_not_allowed"),
        ({"Access-Control-Allow-Headers": "Content-Type,Ocp-Apim-Subscription-Key,*"}, "overbroad_cors"),
        ({"Access-Control-Allow-Methods": "GET,POST,*"}, "overbroad_cors"),
        ({"Access-Control-Allow-Methods": "GET,POST,DELETE"}, "overbroad_cors"),
        ({"Access-Control-Allow-Credentials": "true"}, "overbroad_cors"),
    ],
)
def test_exact_origin_methods_headers_and_no_credentials(overrides, diagnosis):
    result = preflight_result(httpx.Response(200, headers={**HEADERS, **overrides}), ORIGIN)
    assert result["diagnosis"] == diagnosis
    assert result["passed"] == (diagnosis == "preflight_allowed")


def test_empty_200_without_cors_is_not_success():
    assert not preflight_result(httpx.Response(200), ORIGIN)["passed"]


def test_probe_sends_only_anonymous_options_and_reports_no_body_or_keys():
    requests = []

    def respond(request):
        requests.append(request)
        assert request.method == "OPTIONS"
        assert str(request.url) == BASE + "/chat/completions"
        assert request.headers["Origin"] == ORIGIN
        assert request.headers["Access-Control-Request-Method"] == "POST"
        assert request.headers["Access-Control-Request-Headers"] == "content-type,ocp-apim-subscription-key"
        assert "Authorization" not in request.headers
        assert "Ocp-Apim-Subscription-Key" not in request.headers
        return httpx.Response(200, headers={**HEADERS, "Set-Cookie": "not-for-report"}, text="not-for-report")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = probe(BASE, ORIGIN, client)
    assert len(requests) == 1
    assert result["passed"]
    assert "not-for-report" not in str(result)


@pytest.mark.parametrize("origin", [ORIGIN + "/admin", ORIGIN + "/", "*", "http://example.com"])
def test_reject_non_origin_values_without_a_request(origin):
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected request"))) as client:
        with pytest.raises(ValueError):
            probe(BASE, origin, client)


def test_redirect_is_not_followed():
    def respond(request):
        assert request.method == "OPTIONS"
        assert str(request.url).startswith(BASE)
        return httpx.Response(302, headers={"Location": "https://untrusted.invalid"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert probe(BASE, ORIGIN, client)["diagnosis"] == "http_failure"