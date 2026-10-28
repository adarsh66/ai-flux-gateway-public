"""Offline exact-saved-plan guard for the optional GLM extension. No apply entry.

RBAC/identity/network changes are intentionally not allowlisted. Internal APIM
secrets are out-of-band and must never be owned, imported or read by Terraform.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import re
import xml.etree.ElementTree as ET

from scripts.deployment.apim_route_repair import APIM, RepairBlocked
from scripts.deployment.project_route_demo import policy_structure
from scripts.deployment.project_route_models import POLICY
from scripts.deployment.project_route_persistent import APPROVED
from scripts.deployment.glm_apim_secret import internal_ready

NAMED_VALUE = "azapi_resource.glm_named_value[0]"
BACKEND = "azapi_resource.glm_backend[0]"


def guard_external_update(plan, baseline, rendered, previous_variables, secret_identifier, *, storage_mode="apim-internal", internal_metadata=None):
    """Inputs are non-secret artifacts; never accepts a provider key."""
    if plan.get("errored") or plan.get("applyable") is not True or plan.get("deferred_changes"):
        raise RepairBlocked("Resolved applyable saved plan required")
    values = {k: v["value"] for k, v in plan.get("variables", {}).items()}
    if storage_mode not in ("key-vault", "apim-internal"):
        raise RepairBlocked("Explicit reviewed credential storage required")
    internal = storage_mode == "apim-internal"
    if internal:
        if secret_identifier != "" or not internal_ready(internal_metadata):
            raise RepairBlocked("Existing internal secret metadata required; no vault reference allowed")
        if set(internal_metadata) != {"resource_id", "display_name", "secret", "key_vault", "checked_at"}:
            raise RepairBlocked("Only non-secret metadata evidence is accepted")
        try:
            checked = datetime.fromisoformat(internal_metadata["checked_at"])
            now = datetime.now(UTC)
            fresh = checked.tzinfo is not None and now - timedelta(minutes=5) <= checked <= now
        except (TypeError, ValueError):
            fresh = False
        if not fresh:
            raise RepairBlocked("Fresh metadata check required immediately before plan review/apply")
        def owns_named_value(resource):
            if resource.get("address") == NAMED_VALUE:
                return True
            change = resource.get("change", {})
            return any("/namedValues@" in (obj or {}).get("type", "")
                       for obj in (change.get("before"), change.get("after")))
        if any(owns_named_value(r) for r in plan.get("resource_changes", [])):
            raise RepairBlocked("Terraform must not own/import/read the internal secret")
    expected = {**previous_variables, **APPROVED, "glm_enabled": True,
                "glm_credential_storage": storage_mode, "glm_internal_secret_verified": internal,
                "glm_resolver_verified": not internal, "glm_secret_identifier": secret_identifier}
    if values != expected:
        raise RepairBlocked("Only GLM opt-in inputs may change; quotas/routes/epochs must be preserved")
    writes = {r["address"]: r["change"] for r in plan.get("resource_changes", [])
              if r["change"]["actions"] not in (["read"], ["no-op"])}
    allowed = {POLICY, BACKEND} if internal else {POLICY, NAMED_VALUE, BACKEND}
    if set(writes) != allowed:
        raise RepairBlocked("Only reviewed GLM backend/policy and optional vault-reference creation allowed")
    def unknown(value):
        if isinstance(value, dict):
            return any(unknown(v) for v in value.values())
        if isinstance(value, list):
            return any(unknown(v) for v in value)
        return value is True
    for address, change in writes.items():
        if change["actions"] != (["update"] if address == POLICY else ["create"]):
            raise RepairBlocked("No replacements/deletions or unrelated resource updates allowed")
        if unknown(change.get("after_unknown", {}).get("body")):
            raise RepairBlocked("Unknown resource body")
    expected_bodies = {
        NAMED_VALUE: ("Microsoft.ApiManagement/service/namedValues@2024-05-01", "aiflux-glm-5-3-api-key",
            {"properties": {"displayName": "aiflux-glm-5-3-api-key", "secret": True,
                            "keyVault": {"secretIdentifier": secret_identifier}}}),
        BACKEND: ("Microsoft.ApiManagement/service/backends@2024-05-01", "aiflux-external-glm-5-3",
            {"properties": {"protocol": "http", "url": "https://api-ap-southeast-1.modelarts-maas.com/v1",
                            "tls": {"validateCertificateChain": True, "validateCertificateName": True}}}),
    }
    if internal:
        del expected_bodies[NAMED_VALUE]
    for address, (kind, name, body) in expected_bodies.items():
        after = writes[address]["after"]
        if any(after.get(k) != v for k, v in {"type": kind, "name": name, "parent_id": APIM, "body": body}.items()):
            raise RepairBlocked("Exact credential-reference/TLS backend contract required")
    change = writes[POLICY]
    for obj in (change["before"], change["after"]):
        if (obj.get("parent_id") != APIM + "/apis/aiflux-dev-unified" or obj.get("name") != "policy"
                or obj.get("type") != "Microsoft.ApiManagement/service/apis/policies@2024-05-01"):
            raise RepairBlocked("Wrong existing dev API")
    if policy_structure(change["before"]["body"]["properties"]["value"]) != policy_structure(baseline):
        raise RepairBlocked("Live baseline changed")
    if change["after"]["body"] != {"properties": {"format": "rawxml", "value": rendered}}:
        raise RepairBlocked("Saved plan/render mismatch")
    tree, prior = ET.fromstring(rendered), ET.fromstring(baseline)
    for tag in ("cors", "quota-by-key", "rate-limit-by-key", "llm-token-limit", "llm-content-safety", "send-request", "authentication-managed-identity", "forward-request"):
        def structures(t):
            return [policy_structure(ET.tostring(n, encoding="unicode")) for n in t.findall(".//" + tag)]
        if structures(tree) != structures(prior):
            raise RepairBlocked("Protected guardrail changed: " + tag)
    if (tree.findall(".//retry") or len(list(tree.find("backend"))) != 1
            or "context.NamedValues" in rendered or "demo_expired" in rendered
            or rendered.count("Bearer {{aiflux-glm-5-3-api-key}}") != 1):
        raise RepairBlocked("One forward/no retry and exact server-side credential reference required")
    before_dispatch = {n.get("condition"): policy_structure(ET.tostring(n, encoding="unicode"))
                       for n in prior.findall(".//when") if n.find("set-backend-service") is not None}
    after_dispatch = {n.get("condition"): policy_structure(ET.tostring(n, encoding="unicode"))
                      for n in tree.findall(".//when") if n.find("set-backend-service") is not None}
    if any(after_dispatch.get(k) != v for k, v in before_dispatch.items()) or len(after_dispatch) != len(before_dispatch) + 1:
        raise RepairBlocked("Existing Foundry dispatch changed")
    if (rendered.index("Bearer {{") < rendered.rindex("</send-request>")
            or rendered.index("Bearer {{") < rendered.index('name="Ocp-Apim-Subscription-Key" exists-action="delete"')):
        raise RepairBlocked("Credential injection must follow safety/PII and incoming auth cleanup")
    # Recover the predecessor by removing only the explicit GLM extension. This
    # catches changes to validation, PII parsing, on-error and unrelated headers,
    # not merely selected security tags. Never trust a changed request cap.
    recovered = deepcopy(tree)
    extra_headers = {"x-api-key", "apikey", "x-goog-api-key", "x-auth-token", "Proxy-Authorization",
        "Cookie", "Ocp-Apim-Trace", "Ocp-Apim-Trace-Location", "Apim-Debug-Authorization",
        "x-ms-client-request-id", "anthropic-version"}
    for parent in list(recovered.iter()):
        for child in list(parent):
            text = ET.tostring(child, encoding="unicode")
            if child.tag == "choose" and child.find("when/set-body[@id='aiflux-external-response']") is not None:
                parent.remove(child)
            elif (child.tag == "choose" and parent.tag == "outbound"
                  and child.find("when/return-response/set-status[@code='200']") is not None
                  and 'glm-5.3' in child.find("when").get("condition", "")):
                parent.remove(child)
            elif child.tag == "choose" and child.find("when/set-header[@name='Authorization']/value") is not None:
                if "Bearer {{aiflux-glm-5-3-api-key}}" not in text:
                    raise RepairBlocked("Wrong external auth branch")
                identity = child.find("otherwise/authentication-managed-identity")
                if identity is None or child.find("when/authentication-managed-identity") is not None:
                    raise RepairBlocked("External branch may not acquire a Foundry token")
                parent.insert(list(parent).index(child), deepcopy(identity))
                parent.remove(child)
            elif child.tag == "set-header" and child.get("name") in extra_headers and parent.tag == "when":
                parent.remove(child)
    for node in recovered.iter():
        for key, value in node.attrib.items():
            value = value.replace(' || (string)model == "glm-5.3"', '')
            value = value.replace(' if ((string)model == "glm-5.3") { modelMaximum = 1024; }', '')
            node.set(key, value)
        if node.tag == "set-body" and (node.text or "").startswith('{"data":'):
            data = json.loads(node.text)
            data["data"] = [m for m in data["data"] if m["id"] != "glm-5.3"]
            node.text = json.dumps(data, separators=(",", ":"), sort_keys=True)
    # Whitespace between interpolated model-limit statements isn't semantic;
    # do not normalize other expression content or guards.
    def comparable(value):
        return policy_structure(re.sub(r"(?<=}) +(?=if \(\(string\)model)", " ", value))
    if comparable(ET.tostring(recovered, encoding="unicode")) != comparable(baseline):
        raise RepairBlocked("Unapproved predecessor policy change outside the GLM extension")