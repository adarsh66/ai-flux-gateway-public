"""Synthetic fixtures only; no fixture attests live permissions or acceptance."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from scripts.deployment.apim_route_repair import (
    ACCOUNT, APIM, OPENAI_ENDPOINT, PROJECT, PROJECT_ENDPOINT, SUBSCRIBER,
    RepairBlocked, conservative_defaults, guard_plan, prepare,
)

NOW = datetime(2026, 10, 26, 4, 10, tzinfo=UTC)


def evidence():
    return {
        "checked_at": NOW.isoformat(), "project_id": PROJECT, "project_endpoint": PROJECT_ENDPOINT,
        "complete": True, "connection_ids": [],
        "openai_endpoint": OPENAI_ENDPOINT,
        "subscription": {"state": "active", "scope": APIM + "/products/aiflux"},
        "gateway_inference_role_verified": True, "safety_pii_verified": True,
        "budget_quota_verified": True, "legacy_policy_baseline_verified": True,
        "fragment_hashes": {"aiflux-test-budget": "a" * 64},
        "deployments": [{"name": "gpt-5-mini", "id": ACCOUNT + "/deployments/gpt-5-mini",
                         "model_name": "gpt-5-mini", "version": "2025-08-07", "format": "OpenAI",
                         "state": "Succeeded", "capacity": 5000, "chat": True}],
    }


def approval():
    return {
        "approved_at": NOW.isoformat(), "deployment_name": "gpt-5-mini", "model_name": "gpt-5-mini",
        "model_version": "2025-08-07", "model_cost_terms_approved": True, "safety_threshold": 1,
        "safety_approved": True, "subscription_id": SUBSCRIBER,
        "budget_fragment_id": "aiflux-test-budget", "budget_fragment_sha256": "a" * 64,
        "subscription_budget_quota_approved": True,
    }


def test_no_implicit_approval_or_inference_activation():
    result = prepare(evidence(), now=NOW)
    assert result["ready_for_scoped_planning"] is False
    assert result["apply_authorized"] is False
    assert "explicit_IDS_approved_safety_threshold_required" in result["blockers"]
    assert "model_cost_and_terms_approval_required" in result["blockers"]
    assert result["proposal"]["backend_model"] is None


def test_project_specific_proposal_preserves_existing_subscription_scope():
    result = prepare(evidence(), approval(), now=NOW)
    assert result["blockers"] == []
    assert result["ready_for_scoped_planning"] is True
    assert result["apply_authorized"] is False
    proposed = result["proposal"]
    assert proposed["product_id"] == "aiflux"
    assert proposed["backend_model"] == "gpt-5-mini"
    assert proposed["backend_base"] == OPENAI_ENDPOINT + "openai/v1"
    assert proposed["backend_retries"] == 0
    assert proposed["smoke_max_completion_tokens"] == 32
    assert not proposed["legacy_dev_v1_enabled"] and not proposed["production_v1_enabled"]
    assert set(proposed["operations"]) == {"models", "chat"}
    assert all(origin.endswith(".azurewebsites.net") for origin in proposed["cors_origins"])


@pytest.mark.parametrize("field,value", [
    ("complete", False), ("connection_ids", ["unapproved"]),
    ("project_id", ACCOUNT + "/projects/another"), ("project_endpoint", "https://foreign.invalid"),
    ("openai_endpoint", PROJECT_ENDPOINT), ("gateway_inference_role_verified", False),
    ("safety_pii_verified", False), ("budget_quota_verified", False),
    ("legacy_policy_baseline_verified", False), ("fragment_hashes", {}),
    ("checked_at", (NOW - timedelta(hours=2)).isoformat()),
    ("checked_at", (NOW + timedelta(seconds=1)).isoformat()), ("checked_at", "2026-10-26T04:10:00"),
])
def test_incomplete_wrong_scoped_or_stale_evidence_blocks(field, value):
    snapshot = evidence()
    snapshot[field] = value
    assert prepare(snapshot, approval(), now=NOW)["blockers"]


@pytest.mark.parametrize("field,value", [
    ("safety_threshold", None), ("safety_threshold", True), ("safety_threshold", 8),
    ("safety_approved", False), ("model_cost_terms_approved", False),
    ("subscription_budget_quota_approved", False), ("subscription_id", "another"),
    ("budget_fragment_sha256", "b" * 64), ("budget_fragment_id", "aiflux-../../bad"),
    ("deployment_name", "auto"), ("deployment_name", "gpt-5.6-luna"),
    ("model_version", "unverified"), ("approved_at", "not-a-date"),
])
def test_approval_cannot_invent_acceptance(field, value):
    approved = approval()
    approved[field] = value
    assert prepare(evidence(), approved, now=NOW)["blockers"]


@pytest.mark.parametrize("field,value", [
    ("id", ACCOUNT + "-Backup/deployments/gpt-5-mini"), ("state", "Failed"),
    ("capacity", 0), ("capacity", True), ("chat", False), ("format", "DeepSeek"),
])
def test_deployment_existence_is_not_route_readiness(field, value):
    snapshot = evidence()
    snapshot["deployments"][0][field] = value
    assert prepare(snapshot, approval(), now=NOW)["blockers"]


def saved_plan():
    after = {"name": "aiflux-project-gpt-5-mini", "parent_id": APIM,
             "type": "Microsoft.ApiManagement/service/backends@2024-05-01",
             "body": {"properties": {"url": OPENAI_ENDPOINT + "openai/v1",
                                      "tls": {"validateCertificateChain": True, "validateCertificateName": True}}}}
    change = {"actions": ["create"], "before": None, "after": after, "after_unknown": {"id": True}}
    address = "azapi_resource.project_backend"
    plan = {"applyable": True, "errored": False, "resource_changes": [
        {"address": address, "type": "azapi_resource", "change": deepcopy(change)}]}
    manifest = {"changes": {address: {**deepcopy(change), "arm_id": APIM + "/backends/" + after["name"]}}}
    return plan, manifest


def test_accepts_only_exact_reviewed_gateway_child():
    plan, manifest = saved_plan()
    guard_plan(plan, manifest, prepare(evidence(), approval(), now=NOW), now=NOW)


@pytest.mark.parametrize("mutation", ["delete", "replace", "unknown", "settings", "missing", "deferred", "wrong_target", "wrong_type", "duplicate", "unapproved"])
def test_exact_plan_guard_rejects_unrelated_or_changed_writes(mutation):
    plan, manifest = saved_plan()
    resource = plan["resource_changes"][0]
    if mutation == "delete": resource["change"]["actions"] = ["delete"]
    if mutation == "replace": resource["change"]["actions"] = ["delete", "create"]
    if mutation == "unknown": resource["change"]["after_unknown"]["body"] = {"properties": {"url": True}}
    if mutation == "settings": resource["change"]["after"]["body"]["properties"]["url"] = "https://foreign.invalid"
    if mutation == "missing": plan["resource_changes"] = []
    if mutation == "deferred": plan["deferred_changes"] = [{"deferred": True}]
    if mutation == "wrong_target":
        resource["change"]["after"]["parent_id"] = ACCOUNT
        manifest["changes"][resource["address"]]["after"]["parent_id"] = ACCOUNT
    if mutation == "wrong_type": resource["type"] = "azurerm_role_assignment"
    if mutation == "duplicate": plan["resource_changes"].append(deepcopy(resource))
    if mutation == "unapproved": manifest["changes"] = {}
    with pytest.raises(RepairBlocked):
        guard_plan(plan, manifest, prepare(evidence(), approval(), now=NOW), now=NOW)


def test_guard_requires_fresh_ready_evidence_not_merely_approval():
    plan, manifest = saved_plan()
    with pytest.raises(RepairBlocked): guard_plan(plan, manifest, prepare(evidence(), now=NOW), now=NOW)
    ready = prepare(evidence(), approval(), now=NOW)
    with pytest.raises(RepairBlocked): guard_plan(plan, manifest, ready, now=NOW + timedelta(hours=2))


def test_superseded_project_and_endpoint_cannot_pass_even_with_old_grant():
    snapshot = evidence()
    snapshot["project_id"] = ACCOUNT.replace("poc-ids-token-ex-foundry", "IDS-AI-Token") + "/projects/proj-poc-token-exchange"
    snapshot["project_endpoint"] = "https://ids-ai-token.services.ai.azure.com/api/projects/proj-poc-token-exchange"
    snapshot["openai_endpoint"] = "https://ids-ai-token.openai.azure.com/"
    result = prepare(snapshot, approval(), now=NOW)
    assert "exact_project_scope_required" in result["blockers"]
    assert "arm_advertised_openai_endpoint_required" in result["blockers"]


def test_conservative_defaults_are_not_legal_or_runtime_acceptance():
    snapshot = evidence()
    snapshot["deployments"][0].update(name="gpt-5.6-luna", id=ACCOUNT + "/deployments/gpt-5.6-luna",
                                      model_name="gpt-5.6-luna", version="2026-07-09")
    defaults = conservative_defaults(snapshot, now=NOW)
    assert defaults["project_id"] == PROJECT
    assert defaults["deployment_name"] == "gpt-5.6-luna"
    assert (defaults["rpm"], defaults["tpm"], defaults["daily_token_quota"]) == (1, 1000, 10000)
    assert defaults["max_completion_tokens"] == 32 and defaults["backend_retries"] == 0
    assert defaults["safety_threshold"] == 1
    for field in ("model_terms_accepted", "safety_tests_passed", "gateway_inference_verified", "cheapest_model_verified"):
        assert defaults[field] is False
    assert prepare(snapshot, defaults, now=NOW)["ready_for_scoped_planning"] is False
    result = prepare(snapshot, configuration=defaults, now=NOW)
    assert result["configuration_authorized"] is True
    assert result["legal_terms_attested"] is False
    assert "model_cost_and_terms_approval_required" not in result["blockers"]
    assert "explicit_IDS_approved_safety_threshold_required" not in result["blockers"]
    assert "reviewed_live_subscription_budget_and_quota_fragment_required" not in result["blockers"]
    assert "real_gateway_managed_identity_inference_proof_required" in result["blockers"]


@pytest.mark.parametrize("mutation", ["foreign", "failed", "disabled", "capacity", "third_party"])
def test_default_candidate_cannot_use_foreign_inactive_or_untranslated_models(mutation):
    snapshot = evidence()
    model = snapshot["deployments"][0]
    model.update(name="gpt-5.6-luna", id=ACCOUNT + "/deployments/gpt-5.6-luna")
    if mutation == "foreign": model["id"] = model["id"].replace("poc-ids-token-ex-foundry", "IDS-AI-Token")
    if mutation == "failed": model["state"] = "Failed"
    if mutation == "disabled": model["deployment_state"] = "Disabled"
    if mutation == "capacity": model["capacity"] = 0
    if mutation == "third_party": model["format"] = "DeepSeek"
    assert conservative_defaults(snapshot, now=NOW)["deployment_name"] is None


def test_most_restrictive_valid_threshold_does_not_attest_usable_chat():
    approved = approval()
    approved["safety_threshold"] = 0
    result = prepare(evidence(), approved, now=NOW)
    assert "threshold_zero_blocks_benign_severity_zero_cannot_accept_chat" in result["blockers"]
    plan, manifest = saved_plan()
    with pytest.raises(RepairBlocked):
        guard_plan(plan, manifest, result, now=NOW)


def test_restricted_candidate_does_not_require_circular_live_acceptance():
    snapshot = evidence()
    snapshot["deployments"][0].update(name="gpt-5.6-luna", id=ACCOUNT + "/deployments/gpt-5.6-luna",
                                      model_name="gpt-5.6-luna", version="2026-07-09")
    snapshot["safety_pii_verified"] = False
    config = conservative_defaults(snapshot, now=NOW)
    result = prepare(snapshot, configuration=config, candidate_validation=True, now=NOW)
    assert result["ready_for_scoped_planning"] is True
    assert result["phase"] == "restricted_candidate"
    assert result["apply_authorized"] is False and not result["legal_terms_attested"]
    plan, manifest = saved_plan()
    with pytest.raises(RepairBlocked, match="Candidate evidence"):
        guard_plan(plan, manifest, result, now=NOW)
    assert prepare(snapshot, configuration=config, now=NOW)["blockers"]
    snapshot["gateway_inference_role_verified"] = False
    assert prepare(snapshot, configuration=config, candidate_validation=True, now=NOW)["blockers"]


@pytest.mark.parametrize("url", ["https://ids-ai-token.openai.azure.com/openai/v1",
                                 PROJECT_ENDPOINT, "https://foreign.invalid/openai/v1"])
def test_even_reviewed_manifest_cannot_route_to_old_or_foreign_project(url):
    plan, manifest = saved_plan()
    item = plan["resource_changes"][0]
    item["change"]["after"]["body"]["properties"]["url"] = url
    manifest["changes"][item["address"]]["after"] = deepcopy(item["change"]["after"])
    with pytest.raises(RepairBlocked, match="corrected project"):
        guard_plan(plan, manifest, prepare(evidence(), approval(), now=NOW), now=NOW)


@pytest.mark.parametrize("change_legacy", [False, True])
def test_global_saved_plan_protects_legacy_even_if_manifest_was_reviewed(change_legacy):
    from pathlib import Path
    template = (Path(__file__).resolve().parents[2] / "gateway/policies/global-dev-gate.xml.tftpl").read_text()
    before = template.replace("${enabled}", "false").replace("${unified_enabled}", "false")
    after = template.replace("${enabled}", "true" if change_legacy else "false").replace("${unified_enabled}", "true")
    obj = {"name": "policy", "parent_id": APIM, "type": "Microsoft.ApiManagement/service/policies@2024-05-01",
           "body": {"properties": {"format": "rawxml", "value": before}}}
    updated = deepcopy(obj)
    updated["body"]["properties"]["value"] = after
    change = {"actions": ["update"], "before": obj, "after": updated, "after_unknown": {}}
    address = "azapi_resource.project_global_gate[0]"
    plan = {"applyable": True, "resource_changes": [{"address": address, "type": "azapi_resource", "change": change}]}
    manifest = {"changes": {address: {**deepcopy(change), "arm_id": APIM + "/policies/policy"}}}
    if change_legacy:
        with pytest.raises(RepairBlocked, match="adapter branch"):
            guard_plan(plan, manifest, prepare(evidence(), approval(), now=NOW), now=NOW)
    else:
        guard_plan(plan, manifest, prepare(evidence(), approval(), now=NOW), now=NOW)