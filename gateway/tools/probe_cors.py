"""Anonymous OPTIONS-only diagnostic. No keys, login, inference calls, or Azure writes."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

REQUEST_HEADERS = frozenset({"content-type", "ocp-apim-subscription-key"})


def tokens(value: str) -> set[str]:
    return {part.strip().lower() for part in value.split(",") if part.strip()}


def preflight_result(response: httpx.Response, origin: str) -> dict:
    """Report sanitized evidence, never response bodies or authentication headers."""
    headers = response.headers
    allowed_origin = headers.get("access-control-allow-origin")
    methods = tokens(headers.get("access-control-allow-methods", ""))
    allowed_headers = tokens(headers.get("access-control-allow-headers", ""))
    credentials_present = "access-control-allow-credentials" in headers
    if response.status_code == 404:
        diagnosis = "route_not_found"
    elif response.status_code == 503:
        diagnosis = "gateway_unavailable"
    elif response.status_code in (401, 403):
        diagnosis = "request_intercepted"
    elif not response.is_success:
        diagnosis = "http_failure"
    elif allowed_origin != origin:
        diagnosis = "origin_not_allowed_or_cors_missing"
    elif "post" not in methods:
        diagnosis = "post_not_allowed"
    elif not REQUEST_HEADERS <= allowed_headers:
        diagnosis = "headers_not_allowed"
    elif not methods <= {"get", "post"} or allowed_headers != REQUEST_HEADERS or credentials_present:
        diagnosis = "overbroad_cors"
    else:
        diagnosis = "preflight_allowed"
    return {
        "http_status": response.status_code,
        "origin": origin,
        "allow_origin": allowed_origin,
        "allow_methods": sorted(methods),
        "allow_headers": sorted(allowed_headers),
        "credentials_header_present": credentials_present,
        "diagnosis": diagnosis,
        "passed": diagnosis == "preflight_allowed",
    }


def probe(base: str, origin: str, client: httpx.Client) -> dict:
    parsed_base, parsed_origin = urlsplit(base), urlsplit(origin)
    for parsed in (parsed_base, parsed_origin):
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or "*" in parsed.netloc
        ):
            raise ValueError("Use exact HTTPS URLs without credentials, queries, fragments or wildcards.")
    if parsed_origin.path:
        raise ValueError("Origin must not contain a path or trailing slash.")
    response = client.options(
        base.rstrip("/") + "/chat/completions",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": ",".join(sorted(REQUEST_HEADERS)),
        },
        follow_redirects=False,
    )
    return preflight_result(response, origin)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Exact HTTPS gateway API base including path")
    parser.add_argument("--origin", required=True, help="Exact browser origin, no path")
    args = parser.parse_args()
    with httpx.Client(timeout=30) as client:
        result = probe(args.base, args.origin, client)
    print(json.dumps({"checked_at": datetime.now(UTC).isoformat(), **result}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()