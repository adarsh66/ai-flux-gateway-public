import re
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential

from aiflux.config import Settings

API_VERSION = "2024-05-01"


def safe_apim_diagnostics(context: object) -> dict:
    """Closed vocabulary only: never stringify caller/ARM values or exceptions."""
    enums = {
        "reason": ("operation_failed", "authentication_error", "transport_error", "http_error",
                   "invalid_json", "invalid_fragment", "invalid_input", "invalid_header",
                   "invalid_properties", "missing_state", "terminal_failure", "unknown_state",
                   "malformed_xml", "readiness_timeout", "operation_timeout", "drift_conflict",
                   "readback_mismatch"),
        "substage": ("fragment_get", "conditional_put", "header_validation", "operation_poll",
                     "resource_readiness", "baseline_read", "strict_readback"),
        "state": ("missing", "null", "unknown", "Succeeded", "Failed", "Canceled", "Cancelled",
                  "InProgress", "Running", "Accepted", "Updating"),
        "operation_path": ("absent", "exact_resource", "service_operation", "invalid"),
        "location_path": ("absent", "exact_resource", "invalid"),
    }
    result = {}
    if type(context) is not dict:
        return result
    for key, values in enums.items():
        value = context.get(key)
        if type(value) is str and value in values:
            result[key] = value
    for key in ("state_present", "etag_present", "canonical_match", "operation_present", "location_present"):
        value = context.get(key)
        if type(value) is bool:
            result[key] = value
    for key, lower, upper in (("response_status", 100, 599), ("error_status", 100, 599),
                              ("elapsed_ms", 0, 3600000), ("poll_count", 0, 12)):
        value = context.get(key)
        if type(value) is int and lower <= value <= upper:
            result[key] = value
    return result


def _state_diagnostics(state: object, present: bool) -> dict:
    known = ("Succeeded", "Failed", "Canceled", "Cancelled", "InProgress", "Running", "Accepted", "Updating")
    label = ("null" if present else "missing") if state is None else "unknown"
    if type(state) is str and state in known:
        label = state
    return {"state_present": present, "state": label}


def _state_failure(state: object) -> str:
    if state is None:
        return "missing_state"
    if state in ("Failed", "Canceled", "Cancelled"):
        return "terminal_failure"
    return "unknown_state"


class ApimError(RuntimeError):
    def __init__(self, status_code: int | None = None, pending_operation: str | None = None,
                 *, reason: str = "operation_failed", diagnostics: dict | None = None):
        super().__init__("APIM management operation failed")
        self.status_code = status_code
        self.pending_operation = pending_operation
        # status_code is the existing error classification (sometimes synthetic),
        # never evidence that ARM returned that HTTP status.
        self.diagnostics = safe_apim_diagnostics({**(safe_apim_diagnostics(diagnostics)),
                              "reason": reason, "error_status": status_code})


@contextmanager
def _fragment_diagnostics(substage: str, **metadata):
    """Attach nested failure context without changing requests, retries or causes."""
    started = time.monotonic()
    context = {"substage": substage, **metadata}
    try:
        yield context
    except ApimError as exc:
        elapsed = max(0, min(3600000, int((time.monotonic() - started) * 1000)))
        nested = safe_apim_diagnostics(exc.diagnostics)
        if nested.get("substage", substage) != substage:
            # Request/response facts from an outer stage are not poll facts.
            context.pop("etag_present", None)
            context.pop("response_status", None)
        exc.diagnostics = safe_apim_diagnostics({**context, "elapsed_ms": elapsed,
                                                **nested})
        raise


class ApimClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._credential: DefaultAzureCredential | None = None
        self._local_keys: dict[tuple[str, str], str] = {}
        self._local_states: dict[str, str] = {}

    def _is_local_sandbox(self) -> bool:
        return self.settings.local_auth_enabled and not self.settings.apim_resource_id.strip()

    def _url(self, subscription_id: str, action: str = "") -> str:
        resource = self.settings.apim_resource_id.rstrip("/")
        if not re.fullmatch(
            r"/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[\w.-]+/"
            r"providers/Microsoft\.ApiManagement/service/[\w-]+",
            resource,
        ) or not re.fullmatch(r"[\w-]+", self.settings.apim_product_id):
            raise ApimError()
        return (
            f"https://management.azure.com{resource}/subscriptions/{UUID(subscription_id)}"
            f"{action}?api-version={API_VERSION}"
        )

    def _request(self, method: str, sid: str, action: str = "", body: dict | None = None) -> dict:
        url = self._url(sid, action)
        response = self._send(method, url, body, "*")
        if response.status_code == 202 or response.headers.get("Azure-AsyncOperation"):
            if method in {"PUT", "PATCH"} and not action:
                operation = response.headers.get("Azure-AsyncOperation") or response.headers.get("Location")
                try:
                    self._validate_subscription_operation(sid, operation)
                except ApimError:
                    operation = "unknown"
                raise ApimError(202, pending_operation=operation)
            raise ApimError(202)
        if response.status_code == 204:
            return {}
        return self._json(response)

    def _validate_subscription_operation(self, sid: str, operation: str | None) -> None:
        if not isinstance(operation, str) or len(operation) > 2048:
            raise ApimError()
        expected = urlsplit(self._url(sid))
        actual = urlsplit(operation)
        service = expected.path.rsplit("/subscriptions/", 1)[0]
        if ((actual.scheme, actual.netloc) != (expected.scheme, expected.netloc)
                or actual.fragment or actual.username or actual.password
                or not re.fullmatch(re.escape(service) + r"/(?:tenant/operationResults|entityOperationResults)/[A-Za-z0-9-]+", actual.path)):
            raise ApimError()

    def resolve_subscription_operation(self, sid: str, operation: str) -> None:
        """One bounded GET per retry, never a worker or permission expansion.

        Only a validated service operation's terminal status releases the
        barrier. 403/404/timeout/unknown stay failed for operator review; a
        resource's current active/suspended state cannot prove a late PUT ended.
        """
        self._validate_subscription_operation(sid, operation)
        response = self._send("GET", operation)
        if response.status_code != 200:
            raise ApimError(response.status_code)
        status = self._json(response).get("status")
        if status not in {"Succeeded", "Failed", "Canceled", "Cancelled"}:
            raise ApimError(202 if status in {"InProgress", "Running", "Accepted"} else 409)

    def _send(
        self, method: str, url: str, body: dict | None = None, etag: str | None = None,
    ) -> httpx.Response:
        if self._credential is None:
            self._credential = DefaultAzureCredential()
        try:
            token = self._credential.get_token("https://management.azure.com/.default").token
        except AzureError as exc:
            raise ApimError(reason="authentication_error") from exc
        try:
            response = httpx.request(
                method,
                url,
                json=body,
                timeout=30,
                headers={"Authorization": f"Bearer {token}"} | ({"If-Match": etag} if etag else {}),
            )
        except httpx.HTTPError as exc:
            # Credential failures above occur before sending and are retryable;
            # transport failures after sending a PUT have an unknown outcome.
            raise ApimError(pending_operation="unknown" if method == "PUT" else None,
                            reason="transport_error") from exc
        if response.status_code not in (200, 201, 202, 204):
            raise ApimError(response.status_code, pending_operation="unknown"
                            if method == "PUT" and (response.status_code >= 500 or response.status_code == 408) else None,
                            reason="http_error", diagnostics={"response_status": response.status_code})
        return response

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        try:
            result = response.json()
        except ValueError as exc:
            raise ApimError(response.status_code, reason="invalid_json",
                            diagnostics={"response_status": response.status_code}) from exc
        if not isinstance(result, dict):
            raise ApimError(response.status_code, reason="invalid_json",
                            diagnostics={"response_status": response.status_code})
        return result

    def _fragment_url(self, scope: str) -> str:
        if scope not in self.settings.gateway_settings_scopes:
            raise ApimError()
        # Reuse resource-ID validation, never accept an ARM URL from an API caller.
        self._url("00000000-0000-0000-0000-000000000000")
        fragment = f"aiflux-{scope}-settings"
        if self.settings.gateway_controls_poc_enabled:
            if scope != "dev-unified" or self.settings.gateway_controls_v2_enabled:
                raise ApimError()
            fragment = "aiflux-dev-unified-poc-settings"
        return (
            f"https://management.azure.com{self.settings.apim_resource_id.rstrip('/')}"
            f"/policyFragments/{fragment}?api-version={API_VERSION}"
        )

    def get_settings_fragment(self, scope: str) -> tuple[str, str]:
        with _fragment_diagnostics("fragment_get") as diagnostic:
            response = self._send("GET", self._fragment_url(scope) + "&format=xml")
            diagnostic.update(response_status=response.status_code, etag_present=bool(response.headers.get("ETag")))
            properties = self._json(response).get("properties")
            value = properties.get("value") if isinstance(properties, dict) else None
            etag = response.headers.get("ETag")
            if not isinstance(value, str) or not value or len(value) > 65536 or not etag or len(etag) > 200:
                raise ApimError(response.status_code, reason="invalid_fragment")
            return value, etag

    def put_settings_fragment(self, scope: str, value: str, etag: str) -> None:
        with _fragment_diagnostics("conditional_put", etag_present=bool(etag)):
            self._put_settings_fragment(scope, value, etag)

    def _put_settings_fragment(self, scope: str, value: str, etag: str) -> None:
        if not etag or etag == "*" or len(value.encode("utf-8")) > 65536:
            raise ApimError(reason="invalid_input")
        response = self._send(
            "PUT", self._fragment_url(scope),
            {"properties": {
                "description": (
                    "Runtime-owned bounded settings; invariant inspection and routing remain Terraform-owned."
                ),
                # Renderers return well-formed XML with escaped attributes.
                # rawxml is APIM's non-XML-encoded editor representation and
                # would treat &quot;/&lt; as C# tokens instead of XML entities.
                "format": "xml", "value": value,
            }}, etag,
        )
        operation = response.headers.get("Azure-AsyncOperation")
        location = response.headers.get("Location")
        expected = urlsplit(self._fragment_url(scope))
        service_path = expected.path.rsplit("/policyFragments/", 1)[0]
        with _fragment_diagnostics(
            "header_validation", response_status=response.status_code,
            operation_present=operation is not None, location_present=location is not None,
            operation_path="absent", location_path="absent",
        ) as diagnostic:
            for header, target in (("operation", operation), ("location", location)):
                if target is None:
                    continue
                diagnostic[header + "_path"] = "invalid"
                try:
                    actual = urlsplit(target)
                except ValueError as exc:
                    raise ApimError(reason="invalid_header") from exc
                resource_path = actual.path == expected.path
                service_operation = header == "operation" and re.fullmatch(
                    re.escape(service_path) + r"/(?:tenant/operationResults|entityOperationResults)/[A-Za-z0-9-]+", actual.path,
                ) is not None
                if ((actual.scheme, actual.netloc) != (expected.scheme, expected.netloc)
                        or actual.fragment or not (resource_path or service_operation)):
                    raise ApimError(reason="invalid_header")
                diagnostic[header + "_path"] = "exact_resource" if resource_path else "service_operation"
        # APIM's documented operationResults endpoint is outside the identity's
        # exact-fragment grant. Do not follow it or request broader permissions.
        # Resource readiness is sufficient only with Succeeded + exact canonical
        # desired XML + ETag. The caller still performs its independent readback.
        if (response.status_code == 202 or location is not None or
                (operation is not None and urlsplit(operation).path != expected.path)):
            with _fragment_diagnostics("resource_readiness", **{
                key: item for key, item in diagnostic.items() if key not in ("substage", "response_status")
            }):
                self._wait_settings_fragment(scope, value)
            return
        if operation is None:
            return
        with _fragment_diagnostics("operation_poll", **{
            key: item for key, item in diagnostic.items() if key not in ("substage", "response_status")
        }) as poll:
            deadline = time.monotonic() + 60
            poll["poll_count"] = 0
            for _ in range(12):
                if time.monotonic() >= deadline:
                    break
                poll["poll_count"] += 1
                for key in ("state", "state_present", "response_status"):
                    poll.pop(key, None)
                response = self._send("GET", operation)
                poll["response_status"] = response.status_code
                result = self._json(response)
                state = result.get("status")
                poll.update(_state_diagnostics(state, "status" in result))
                if state == "Succeeded":
                    return
                if state not in ("InProgress", "Running", "Accepted"):
                    raise ApimError(409, reason=_state_failure(state))
                time.sleep(2)
            raise ApimError(504, reason="operation_timeout")

    def _wait_settings_fragment(self, scope: str, desired: str) -> None:
        with _fragment_diagnostics("resource_readiness", poll_count=0) as diagnostic:
            self._wait_settings_fragment_ready(scope, desired, diagnostic)

    def _wait_settings_fragment_ready(self, scope: str, desired: str, diagnostic: dict) -> None:
        try:
            canonical = ET.canonicalize(desired, strip_text=True)
        except ET.ParseError as exc:
            raise ApimError(reason="malformed_xml") from exc
        deadline = time.monotonic() + 60
        for _ in range(12):
            if time.monotonic() >= deadline:
                break
            diagnostic["poll_count"] += 1
            # A later 202/invalid response must not inherit an earlier poll's state/match.
            for key in ("state", "state_present", "canonical_match", "response_status", "etag_present"):
                diagnostic.pop(key, None)
            response = self._send("GET", self._fragment_url(scope) + "&format=xml")
            diagnostic.update(response_status=response.status_code, etag_present=bool(response.headers.get("ETag")))
            if response.status_code == 202:
                time.sleep(2)
                continue
            properties = self._json(response).get("properties")
            if not isinstance(properties, dict):
                raise ApimError(response.status_code, reason="invalid_properties")
            state = properties.get("provisioningState")
            diagnostic.update(_state_diagnostics(state, "provisioningState" in properties))
            if state in ("Failed", "Canceled", "Cancelled"):
                raise ApimError(409, reason="terminal_failure")
            value, etag = properties.get("value"), response.headers.get("ETag")
            if (not isinstance(value, str) or not value or len(value.encode("utf-8")) > 65536
                    or not etag or etag == "*" or len(etag) > 200):
                raise ApimError(response.status_code, reason="invalid_fragment")
            try:
                equal = ET.canonicalize(value, strip_text=True) == canonical
            except ET.ParseError as exc:
                raise ApimError(response.status_code, reason="malformed_xml") from exc
            diagnostic["canonical_match"] = equal
            if state == "Succeeded" and equal:
                return
            if state not in ("Succeeded", "InProgress", "Running", "Accepted", "Updating"):
                raise ApimError(409, reason=_state_failure(state))
            time.sleep(2)
        raise ApimError(504, reason="readiness_timeout")

    def ensure(self, sid: str, display_name: str, state: str) -> None:
        if self._is_local_sandbox():
            self._local_states[sid] = state
            return
        self._request(
            "PUT",
            sid,
            body={
                "properties": {
                    "displayName": display_name,
                    "scope": f"{self.settings.apim_resource_id}/products/{self.settings.apim_product_id}",
                    "state": state,
                    "allowTracing": False,
                }
            },
        )

    def subscription_inventory(self) -> list[dict]:
        """Complete bounded service inventory, GET only, never listSecrets.

        Management responses can contain keys: allowlist metadata before it
        leaves this method. Validate every continuation before sending a token.
        """
        self._url("00000000-0000-0000-0000-000000000000")
        base = f"https://management.azure.com{self.settings.apim_resource_id.rstrip('/')}/subscriptions"
        url = f"{base}?api-version={API_VERSION}"
        seen, rows, ids = set(), [], set()
        while url:
            parsed = urlsplit(url)
            expected = urlsplit(base)
            if (parsed.scheme != expected.scheme or parsed.netloc != expected.netloc
                    or parsed.path != expected.path or parsed.fragment or url in seen or len(seen) >= 100):
                raise ApimError()
            seen.add(url)
            page = self._json(self._send("GET", url))
            if not isinstance(page.get("value"), list):
                raise ApimError()
            for item in page["value"]:
                props = item.get("properties", {})
                sid = item.get("name")
                if not isinstance(sid, str) or sid in ids or not isinstance(props, dict):
                    raise ApimError()
                ids.add(sid)
                rows.append({"id": item.get("id"), "name": sid,
                             "scope": props.get("scope"), "state": props.get("state"),
                             "owner_id": props.get("ownerId")})
                if len(rows) > 2000:
                    raise ApimError()
            url = page.get("nextLink")
            if url is not None and not isinstance(url, str):
                raise ApimError()
        return sorted(rows, key=lambda row: row["name"])

    def subscription_state(self, sid: str) -> str | None:
        """Exact UUID readback; return None only on the exact resource's 404.

        No keys/owner metadata escape. Reject master, all-APIs and other products.
        Never creates a missing subscription or follows an inventory inference.
        """
        if UUID(sid).int == 0:
            raise ApimError()
        if self._is_local_sandbox():
            return self._local_states.get(sid)
        try:
            data = self._request("GET", sid)
        except ApimError as exc:
            if exc.status_code == 404:
                return None
            raise
        props = data.get("properties")
        expected = f"{self.settings.apim_resource_id.rstrip('/')}/products/{self.settings.apim_product_id}"
        if (not isinstance(props, dict) or not isinstance(props.get("scope"), str)
                or props["scope"].rstrip("/").casefold() != expected.casefold()
            or props.get("provisioningState") not in {None, "Succeeded"}
                or props.get("state") not in {"active", "suspended", "submitted", "rejected", "cancelled", "expired"}):
            raise ApimError()
        return props["state"]

    def set_state(self, sid: str, state: str) -> None:
        if self._is_local_sandbox():
            self._local_states[sid] = state
            return
        self._request("PATCH", sid, body={"properties": {"state": state}})

    def reveal(self, sid: str, key: Literal["primary", "secondary"]) -> str:
        if self._is_local_sandbox():
            import secrets

            k = (sid, key)
            if k not in self._local_keys:
                self._local_keys[k] = f"ts-{key}-{sid[:8]}-{secrets.token_hex(8)}"
            return self._local_keys[k]
        result = self._request("POST", sid, "/listSecrets")
        value = result.get(f"{key}Key")
        if not isinstance(value, str) or not value:
            raise ApimError()
        return value

    def rotate(self, sid: str, key: Literal["primary", "secondary"]) -> None:
        if self._is_local_sandbox():
            import secrets

            self._local_keys[(sid, key)] = f"ts-{key}-{sid[:8]}-{secrets.token_hex(8)}"
            return
        action = "/regeneratePrimaryKey" if key == "primary" else "/regenerateSecondaryKey"
        self._request("POST", sid, action)
