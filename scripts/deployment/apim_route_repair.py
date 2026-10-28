"""Read-only readiness and exact-plan guard for the project-specific APIM repair.

There is deliberately no apply, key retrieval, inference, or RBAC-write command.
The legacy multi-region adapter must not be enabled for this different project.
An approved manifest must contain the complete before/after values from a reviewed
Terraform saved plan, including rendered policies, before guard_plan can accept it.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

SUBSCRIPTION = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
RG = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/IDS-TOKEN-EXCHANGE-POC"
APIM = RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"
ACCOUNT = RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
PROJECT = ACCOUNT + "/projects/poc-ids-token-ex-foundry-project"
PROJECT_ENDPOINT = "https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project"
OPENAI_ENDPOINT = "https://poc-ids-token-ex-foundry.openai.azure.com/"
SUBSCRIBER = "e9f2abb0-930b-598a-b210-0ab0b279127f"
ORIGINS = [f"https://poc-ids-token-ex-{app}.azurewebsites.net" for app in ("customer", "admin")]
GATEWAY_PRINCIPAL = "bcf69911-f34e-4f33-acd8-a36f164db811"
INFERENCE_ROLES = {"a97b65f3-24c7-4388-baec-2e87135dc908", "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"}


class RepairBlocked(ValueError):
    """No authorization/readiness can be inferred from incomplete evidence."""


def conservative_defaults(snapshot: dict, *, now: datetime | None = None) -> dict:
    """Configuration authorized by the correction, NEVER an acceptance record.

    Price ranking is deliberately unset without comparable approved prices. The
    existing OpenAI deployment is a bounded candidate, not a cheapest-model claim.
    No third-party deployment, model-router or invented auto alias is substituted.
    """
    candidates = [d for d in snapshot.get("deployments", []) if (
        d.get("id", "").lower() == (ACCOUNT + "/deployments/" + d.get("name", "")).lower()
        and d.get("format") == "OpenAI" and d.get("chat") is True
        and d.get("state") == "Succeeded" and d.get("deployment_state") in (None, "Active", "Succeeded")
        and type(d.get("capacity")) is int and d["capacity"] > 0
    )]
    # Explicit deterministic candidate preference, NOT a price ordering.
    model = next((d for d in candidates if d["name"] == "gpt-5.6-luna"), None)
    return {
        "configured_at": (now or datetime.now(UTC)).isoformat(),
        "authorization": "user-corrected-project-conservative-defaults-20261026",
        "project_id": PROJECT, "project_endpoint": PROJECT_ENDPOINT,
        "subscription_id": SUBSCRIBER,
        "deployment_name": model["name"] if model else None,
        "model_name": model["model_name"] if model else None,
        "model_version": model["version"] if model else None,
        "rpm": 1, "tpm": 1000, "daily_token_quota": 10000,
        "max_completion_tokens": 32, "backend_retries": 0,
        "safety_threshold": 1, "safety_output_type": "EightSeverityLevels",
        "prompt_shield": True, "input_safety": True, "output_safety": True,
        "pii_required": True, "fail_closed": True,
        "budget_mode": "bounded-token-quota-not-monetary-ledger",
        "cheapest_model_verified": False, "model_terms_accepted": False,
        "safety_tests_passed": False, "gateway_inference_verified": False,
        "reason": "Existing OpenAI bounded candidate only; threshold 1 is the user-authorized smallest usable default. No provider terms, prices, or passing runtime checks are invented.",
    }


def _fresh(value: Any, now: datetime) -> bool:
    try:
        stamp = datetime.fromisoformat(value)
        return stamp.tzinfo is not None and now - timedelta(hours=1) <= stamp <= now
    except (TypeError, ValueError):
        return False


def prepare(snapshot: dict, approval: dict | None = None, *, now: datetime | None = None,
            configuration: dict | None = None, candidate_validation: bool = False) -> dict:
    """Produce a non-applyable proposal; never turn existence into acceptance."""
    now = now or datetime.now(UTC)
    approval = approval or {}
    blockers: list[str] = []
    defaults = configuration is not None
    if candidate_validation and not defaults:
        blockers.append("candidate_requires_exact_authorized_defaults")
    if defaults:
        expected = conservative_defaults(snapshot, now=now)
        if any(configuration.get(k) != v for k, v in expected.items() if k != "configured_at"):
            blockers.append("exact_authorized_conservative_configuration_required")
        if not _fresh(configuration.get("configured_at"), now):
            blockers.append("fresh_default_configuration_required")
        approval = {**configuration, "approved_at": configuration.get("configured_at")}
    if not _fresh(snapshot.get("checked_at"), now):
        blockers.append("fresh_complete_live_snapshot_required")
    if snapshot.get("project_id", "").lower() != PROJECT.lower() or snapshot.get("project_endpoint") != PROJECT_ENDPOINT:
        blockers.append("exact_project_scope_required")
    if snapshot.get("complete") is not True or snapshot.get("connection_ids") != []:
        blockers.append("complete_reads_and_explicit_connection_scope_required")
    if snapshot.get("openai_endpoint") != OPENAI_ENDPOINT:
        blockers.append("arm_advertised_openai_endpoint_required")
    subscription = snapshot.get("subscription", {})
    if subscription.get("state") != "active" or subscription.get("scope", "").lower() != (APIM + "/products/aiflux").lower():
        blockers.append("active_caldova_existing_product_scope_required")
    if snapshot.get("gateway_inference_role_verified") is not True:
        blockers.append("gateway_identity_inference_permission_on_correct_parent_account_required")
    deployments = snapshot.get("deployments", [])
    selected = [d for d in deployments if d.get("name") == approval.get("deployment_name")]
    model = selected[0] if len(selected) == 1 else None
    if not model or not (
        model.get("id", "").lower() == (ACCOUNT + "/deployments/" + model.get("name", "")).lower()
        and model.get("state") == "Succeeded"
        and model.get("deployment_state") in (None, "Active", "Succeeded")
        and model.get("format") == "OpenAI"
        and model.get("chat") is True
        and type(model.get("capacity")) is int and model["capacity"] > 0
        and model.get("model_name") == approval.get("model_name")
        and model.get("version") == approval.get("model_version")
    ):
        blockers.append("explicit_approved_live_openai_deployment_and_version_required")
    if not defaults and approval.get("model_cost_terms_approved") is not True:
        blockers.append("model_cost_and_terms_approval_required")
    threshold = approval.get("safety_threshold")
    if (not defaults and approval.get("safety_approved") is not True) or type(threshold) is not int or not 0 <= threshold <= 7:
        blockers.append("explicit_IDS_approved_safety_threshold_required")
    if type(threshold) is int and threshold == 0:
        blockers.append("threshold_zero_blocks_benign_severity_zero_cannot_accept_chat")
    if not candidate_validation and snapshot.get("safety_pii_verified") is not True:
        blockers.append("live_gateway_identity_content_safety_and_PII_proof_required")
    fragment = approval.get("budget_fragment_id")
    digest = approval.get("budget_fragment_sha256")
    if defaults:
        if not candidate_validation and snapshot.get("token_controls_verified") is not True:
            blockers.append("rendered_and_live_subscription_token_controls_proof_required")
        if not candidate_validation and snapshot.get("gateway_inference_verified") is not True:
            blockers.append("real_gateway_managed_identity_inference_proof_required")
    elif not (
        isinstance(fragment, str) and re.fullmatch(r"aiflux-[a-z0-9-]+", fragment)
        and isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest)
        and snapshot.get("fragment_hashes", {}).get(fragment) == digest
        and approval.get("subscription_budget_quota_approved") is True
        and approval.get("subscription_id") == SUBSCRIBER
        and snapshot.get("budget_quota_verified") is True
    ):
        blockers.append("reviewed_live_subscription_budget_and_quota_fragment_required")
    if not _fresh(approval.get("approved_at"), now):
        blockers.append("fresh_route_specific_approval_required")
    if snapshot.get("legacy_policy_baseline_verified") is not True:
        blockers.append("protected_global_and_legacy_policy_baseline_required")
    return {
        "checked_at": now.isoformat(),
        "ready_for_scoped_planning": not blockers,
        "apply_authorized": False,
        "phase": "restricted_candidate" if candidate_validation else "final",
        "configuration_authorized": defaults and "exact_authorized_conservative_configuration_required" not in blockers,
        "legal_terms_attested": False if defaults else approval.get("model_cost_terms_approved") is True,
        "blockers": blockers,
        "proposal": {
            "api_id": "aiflux-dev-unified", "path": "dev/llm/v1",
            "operations": {"models": {"method": "GET", "path": "/models"},
                           "chat": {"method": "POST", "path": "/chat/completions"}},
            "subscription_required": True, "product_id": "aiflux",
            "approved_subscription_id": SUBSCRIBER, "cors_origins": ORIGINS,
            "project_id": PROJECT, "project_endpoint": PROJECT_ENDPOINT,
            "backend_base": OPENAI_ENDPOINT + "openai/v1",
            "backend_model": model["name"] if model else None,
            "auth": "existing gateway user-assigned managed identity only",
            "safety_threshold": threshold, "budget_fragment_id": fragment,
            "legacy_dev_v1_enabled": False, "production_v1_enabled": False,
            "smoke_max_completion_tokens": 32, "backend_retries": 0,
        },
        "baseline": snapshot.get("baseline", {}),
        "remaining_before_apply": [
            "Render reviewed guarded policy with approved subscription and budget/quota checks; retain PII and input/output safety.",
            "Create and test the project-specific Terraform mapping; do not enable the unrelated Luna/Sol/Haiku profile.",
            "Protect full rollback baseline outside logs; review every complete before/after saved-plan value.",
            "Complete current azure-validate and azure-deploy workflows against that exact saved plan.",
            "Recheck baseline immediately before apply; rollback only owned changes on failed acceptance.",
        ],
    }


def guard_candidate_plan(plan: dict, rendered: dict, baseline: str, readiness: dict,
                         *, now: datetime | None = None, authorized_rpm: int = 1) -> None:
    """Independently match EVERY write to the rendered bounded candidate contract.

    No self-approved manifest, invented live acceptance, import-over-existing
    object, final-route activation, or unrelated update is accepted here.
    """
    if (readiness.get("phase") != "restricted_candidate"
            or readiness.get("ready_for_scoped_planning") is not True
            or readiness.get("configuration_authorized") is not True
            or readiness.get("blockers")
            or not _fresh(readiness.get("checked_at"), now or datetime.now(UTC))):
        raise RepairBlocked("Fresh exact-project candidate prerequisites required")
    if plan.get("errored") or plan.get("applyable") is not True or plan.get("deferred_changes"):
        raise RepairBlocked("Resolved applyable candidate saved plan required")
    api = APIM + "/apis/aiflux-project-validation"
    expected = {}
    for key, item in rendered["children"].items():
        expected[f'azapi_resource.project_child["{key}"]'] = (item["type"], item["parent_id"], item["name"], item["body"])
    for name, method, path in (("models", "GET", "/models"), ("chat", "POST", "/chat/completions")):
        expected[f'azapi_resource.project_operation["{name}"]'] = (
            "Microsoft.ApiManagement/service/apis/operations@2024-05-01", api, name,
            {"properties": {"displayName": name, "method": method, "urlTemplate": path}})
    binding_address = "azurerm_api_management_product_api.project_binding[0]"
    expected[binding_address] = {
        "resource_group_name": "IDS-TOKEN-EXCHANGE-POC", "api_management_name": "poc-ids-token-ex-apim",
        "product_id": "aiflux", "api_name": "aiflux-project-validation",
    }
    expected["azapi_resource.project_policy[0]"] = (
        "Microsoft.ApiManagement/service/apis/policies@2024-05-01", api, "policy",
        {"properties": {"format": "rawxml", "value": rendered["policy"]}})
    closed = baseline.replace("\r\n", "\n").strip()
    flags = list(re.finditer(r"\(false\)", closed))
    if len(flags) != 2:
        raise RepairBlocked("Protected closed global baseline required")
    flag = flags[1]
    candidate_global = (closed[:flag.start()] + "(true)" + closed[flag.end():]).replace(
        "/dev/llm/v1/", "/dev/llm/validate/v1/")
    if rendered["global"].replace("\r\n", "\n").strip() != candidate_global:
        raise RepairBlocked("Candidate must leave legacy and final global routes closed")
    global_format = rendered.get("global_format", "rawxml")
    if global_format not in ("xml", "rawxml"):
        raise RepairBlocked("Exact protected export format required")
    expected["azapi_resource.project_global_gate[0]"] = (
        "Microsoft.ApiManagement/service/policies@2024-05-01", APIM, "policy",
        {"properties": {"format": global_format, "value": rendered["global"]}})
    policy = rendered["policy"]
    # Configurability is not authorization to expand the bounded live runner.
    # Parse real nodes so comments/diagnostic strings cannot satisfy the guard.
    try:
        root = ET.fromstring(policy)
        rates = root.findall(".//rate-limit-by-key")
        tokens = root.findall(".//llm-token-limit")
        quotas = root.findall(".//quota-by-key")
        inbound_safety = root.findall("./inbound/choose/when/llm-content-safety")
        outbound_safety = root.findall("./outbound/choose/when/llm-content-safety")
        pii = root.findall(".//send-request")
        if (len(inbound_safety) != 2 or len(outbound_safety) != 1
                or any(node.get("shield-prompt") != "true" for node in inbound_safety)
                or any(node.find("categories") is None
                       or node.find("categories").get("output-type") != "EightSeverityLevels"
                       or sorted((cat.get("name"), cat.get("threshold")) for cat in node.findall("./categories/category"))
                       != [(name, "1") for name in ("Hate", "SelfHarm", "Sexual", "Violence")]
                       for node in inbound_safety + outbound_safety)
                or len(pii) != 5 or any(node.get("ignore-error") != "false" for node in pii)
                or "pii_inspection_unavailable" not in policy):
            raise RepairBlocked("Candidate mandatory safety/PII contract changed")
        rate_key = '@("rpm:" + (string)context.Subscription.Id + ":" + (string)context.Variables["aiflux-model"])'
        token_key = rate_key.replace('"rpm:"', '"tpm:"')
        if (len(rates) != 1 or len(tokens) != 1 or len(quotas) != 1
                or any(rates[0].get(k) != v for k, v in {
                    "calls": str(authorized_rpm), "renewal-period": "60", "counter-key": rate_key}.items())
                or any(k in rates[0].attrib for k in ("increment-condition", "increment-count"))
                or any(tokens[0].get(k) != v for k, v in {
                    "tokens-per-minute": "1000", "token-quota": "10000", "token-quota-period": "Daily",
                    "estimate-prompt-tokens": "true", "counter-key": token_key}.items())
                or any(quotas[0].get(k) != v for k, v in {
                    "calls": "8", "renewal-period": "86400",
                    "counter-key": '@("project-validation:" + context.Subscription.Id)'}.items())
                or any(k in quotas[0].attrib for k in ("first-period-start", "increment-condition", "increment-count"))):
            raise RepairBlocked("Candidate rate/quota settings or stable counter identity changed; new scoped review required")
    except ET.ParseError as exc:
        raise RepairBlocked("Candidate policy must be valid XML") from exc
    if (rendered["children"]["api"]["name"] != "aiflux-project-validation"
            or rendered["children"]["api"]["body"]["properties"]["path"] != "dev/llm/validate/v1"
            or 'calls="8" renewal-period="86400"' not in policy
            or SUBSCRIBER not in policy
            or '<retry' in policy
            or policy.count('<llm-content-safety') != 3
            or 'threshold="0"' in policy
            or 'token-quota="10000"' not in policy):
        raise RepairBlocked("Bounded candidate security contract missing")
    seen = set()
    for item in plan.get("resource_changes", []):
        change = item.get("change", {})
        if change.get("actions") in (["no-op"], ["read"]):
            continue
        address = item.get("address")
        expected_type = "azurerm_api_management_product_api" if address == binding_address else "azapi_resource"
        if address in seen or address not in expected or item.get("type") != expected_type:
            raise RepairBlocked("Unexpected candidate write")
        is_global = address == "azapi_resource.project_global_gate[0]"
        if change.get("actions") != (["update"] if is_global else ["create"]):
            raise RepairBlocked("Candidate may only create absent children and update imported global")
        after = change.get("after") or {}
        wanted = expected[address]
        actual = {k: after.get(k) for k in wanted} if address == binding_address else tuple(after.get(k) for k in ("type", "parent_id", "name", "body"))
        if actual != wanted:
            raise RepairBlocked("Candidate write differs from independently rendered exact values")
        if any(_unknown(v) for k, v in (change.get("after_unknown") or {}).items() if k not in ("id", "output")):
            raise RepairBlocked("Unknown candidate writable value")
        if is_global:
            before = (change.get("before") or {}).get("body", {}).get("properties", {})
            # Compare like-for-like: ARM's default xml export is encoded
            # differently from rawxml. Do not unescape or silently reserialize.
            if before.get("format") != global_format or before.get("value", "").replace("\r\n", "\n").strip() != closed:
                raise RepairBlocked("Imported global differs from protected same-format baseline")
        seen.add(address)
    if seen != set(expected):
        raise RepairBlocked("Candidate plan omits required guarded resources")


def guard_candidate_rollback(plan: dict, candidate_plan: dict, baseline: dict) -> None:
    """Delete only candidate-owned objects; restore, never delete, the global."""
    if plan.get("errored") or plan.get("applyable") is not True or plan.get("deferred_changes"):
        raise RepairBlocked("Resolved rollback plan required")
    owned = {item["address"]: item["change"]["after"] for item in candidate_plan["resource_changes"]
             if item["change"]["actions"] == ["create"]}
    for item in plan.get("resource_changes", []):
        change = item.get("change", {})
        if change.get("actions") in (["read"], ["no-op"]):
            continue
        address = item.get("address")
        if address == "azapi_resource.project_global_gate[0]":
            after = change.get("after") or {}
            if (change.get("actions") != ["update"] or after.get("parent_id") != APIM
                    or after.get("name") != "policy" or after.get("body") != {"properties": baseline}):
                raise RepairBlocked("Rollback must restore exact global export, never delete it")
        else:
            before = change.get("before") or {}
            expected = owned.get(address)
            fields = ("api_management_name", "resource_group_name", "product_id", "api_name") if address == "azurerm_api_management_product_api.project_binding[0]" else ("type", "parent_id", "name")
            if not expected or change.get("actions") != ["delete"] or any(
                before.get(k) != expected.get(k) for k in fields
            ):
                raise RepairBlocked("Rollback may delete only exact candidate-owned children")


def _unknown(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(_unknown(item) for item in value)
    return value is True


def guard_plan(plan: dict, manifest: dict, readiness: dict, *, now: datetime | None = None) -> None:
    """Reject every change except fully reviewed existing-APIM child changes."""
    if readiness.get("phase") == "restricted_candidate":
        raise RepairBlocked("Candidate evidence cannot authorize a final-route saved plan")
    if readiness.get("ready_for_scoped_planning") is not True or readiness.get("blockers"):
        raise RepairBlocked("Readiness prerequisites have not passed")
    if not _fresh(readiness.get("checked_at"), now or datetime.now(UTC)):
        raise RepairBlocked("Readiness evidence expired")
    if plan.get("errored") or plan.get("applyable") is not True or plan.get("deferred_changes"):
        raise RepairBlocked("An applyable error-free resolved saved plan is required")
    expected = manifest.get("changes", {})
    if not expected:
        raise RepairBlocked("An exact reviewed change manifest is required")
    allowed_types = {"azurerm_api_management_api", "azurerm_api_management_api_operation",
                     "azurerm_api_management_product_api", "azapi_resource"}
    seen = set()
    for item in plan.get("resource_changes", []):
        change = item.get("change", {})
        actions = change.get("actions", [])
        if actions in (["no-op"], ["read"]):
            continue
        address = item.get("address")
        reviewed = expected.get(address)
        if item.get("type") not in allowed_types or actions not in (["create"], ["update"]) or not reviewed:
            raise RepairBlocked("Unexpected resource, deletion, or replacement")
        unknown = change.get("after_unknown") or {}
        if not isinstance(unknown, dict) or address in seen or any(
            _unknown(value) for key, value in unknown.items() if key not in ("id", "output")
        ):
            raise RepairBlocked("Duplicate or unresolved writable resource")
        if any(change.get(k) != reviewed.get(k) for k in ("actions", "before", "after")):
            raise RepairBlocked("Saved-plan change differs from complete reviewed values")
        target = reviewed.get("arm_id", "").lower()
        prefix = APIM.lower()
        allowed = (
            target == prefix + "/policies/policy"
            or target.startswith(prefix + "/backends/aiflux-project-")
            or target == prefix + "/apis/aiflux-dev-unified"
            or target.startswith(prefix + "/apis/aiflux-dev-unified/operations/")
            or target == prefix + "/apis/aiflux-dev-unified/policies/policy"
            or target == prefix + "/products/aiflux/apis/aiflux-dev-unified"
        )
        if not allowed:
            raise RepairBlocked("Only the reviewed adapter, binding, backends and global gate may change")
        after = change.get("after") or {}
        if item["type"] == "azapi_resource":
            arm_type = after.get("type", "").split("@", 1)[0]
            if arm_type not in (
                "Microsoft.ApiManagement/service/backends", "Microsoft.ApiManagement/service/apis",
                "Microsoft.ApiManagement/service/apis/operations", "Microsoft.ApiManagement/service/apis/policies",
                "Microsoft.ApiManagement/service/policies", "Microsoft.ApiManagement/service/products/apis",
            ):
                raise RepairBlocked("Unexpected ARM resource type")
            properties = after.get("body", {}).get("properties", {})
            if arm_type == "Microsoft.ApiManagement/service/backends":
                safety = target == prefix + "/backends/aiflux-project-safety"
                expected_url = (
                    "https://poc-ids-token-ex-safety.cognitiveservices.azure.com"
                    if safety else OPENAI_ENDPOINT + "openai/v1"
                )
                if properties.get("url", "").rstrip("/") != expected_url.rstrip("/"):
                    raise RepairBlocked("Backend is outside the corrected project account or exact safety service")
                if properties.get("tls") != {"validateCertificateChain": True, "validateCertificateName": True}:
                    raise RepairBlocked("Backend certificate verification must remain enabled")
            if arm_type == "Microsoft.ApiManagement/service/policies":
                before_value = (change.get("before") or {}).get("body", {}).get("properties", {}).get("value", "")
                before_value = before_value.replace("\r\n", "\n").strip()
                after_value = properties.get("value", "").replace("\r\n", "\n").strip()
                flags = list(re.finditer(r"\(false\)", before_value))
                if len(flags) != 2:
                    raise RepairBlocked("Exact closed global baseline required before branch-only update")
                flag = flags[1]
                expected_value = before_value[:flag.start()] + "(true)" + before_value[flag.end():]
                if after_value != expected_value:
                    raise RepairBlocked("Only the adapter branch may change; legacy and other global bytes are protected")
            actual = after.get("parent_id", "").rstrip("/") + "/" + arm_type.rsplit("/", 1)[-1] + "/" + after.get("name", "")
        elif item["type"] == "azurerm_api_management_product_api":
            actual = APIM + "/products/" + after.get("product_id", "") + "/apis/" + after.get("api_name", "")
        elif item["type"] == "azurerm_api_management_api_operation":
            actual = APIM + "/apis/" + after.get("api_name", "") + "/operations/" + after.get("operation_id", "")
        else:
            actual = APIM + "/apis/" + after.get("name", "")
        if actual.lower() != target:
            raise RepairBlocked("Reviewed ARM ID does not match actual writable target")
        if item["type"].startswith("azurerm_") and (
            after.get("api_management_name") != "poc-ids-token-ex-apim"
            or after.get("resource_group_name", "").lower() != "ids-token-exchange-poc"
        ):
            raise RepairBlocked("Wrong gateway or resource group")
        seen.add(address)
    if seen != set(expected):
        raise RepairBlocked("Saved plan omits reviewed changes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True, help="Sanitized fresh operator evidence; never keys")
    parser.add_argument("--approval", type=Path, help="Explicit reviewed approvals; omitted means blocked")
    parser.add_argument("--use-authorized-defaults", action="store_true",
                        help="Show user-authorized configuration separately; does not attest tests or terms")
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    approval = json.loads(args.approval.read_text(encoding="utf-8-sig")) if args.approval else None
    configuration = conservative_defaults(snapshot) if args.use_authorized_defaults else None
    report = prepare(snapshot, approval, configuration=configuration)
    if args.use_authorized_defaults:
        report["default_configuration"] = configuration
    print(json.dumps(report, indent=2))
    return 0 if report["ready_for_scoped_planning"] else 2


if __name__ == "__main__":
    raise SystemExit(main())