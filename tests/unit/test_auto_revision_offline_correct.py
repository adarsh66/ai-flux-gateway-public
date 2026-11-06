"""Pure negative coverage for a successor PATCH; never invokes Azure/Terraform."""
from copy import deepcopy

import pytest

from scripts.deployment import auto_revision_offline_correct as c


def example():
    selection = {"revision": "2", "owner_nonce": "a" * 32, "baseline_sha256": "b" * 64}
    plan = {"applyable": True, "variables": {k: {"value": value} for k, value in {
        "auto_staging_take_offline": True, "auto_staging_revision": selection,
        "auto_routing_enabled": False, "poc_controls_enabled": False,
        "admin_settings_enabled": False}.items()}, "resource_changes": [{
        "address": c.ADDRESS, "mode": "managed", "change": {"actions": ["create"], "before": None,
            "after": {"type": "Microsoft.ApiManagement/service/apis@2024-05-01",
                      "resource_id": c.p.APIM + "/apis/" + c.p.API + ";rev=2",
                      "body": {"properties": {"isOnline": False}}}, "after_unknown": {"id": True, "output": True}}}]}
    return plan, selection


def test_exact_existing_revision_offline_only_patch():
    plan, selection = example()
    result = c.guard(plan, selection)
    assert result["api_creates"] == result["current_changes"] == result["scoring_requests"] == 0


@pytest.mark.parametrize("body", [{"properties": {"isOnline": True}}, {"properties": {}},
    {"properties": {"isOnline": 0}},
    {"properties": {"isOnline": "false"}}, {"properties": {"isOnline": False, "isCurrent": False}},
    {"properties": {"isOnline": False, "path": "dev/llm/v1"}}])
def test_no_online_missing_string_or_extra_writable_properties(body):
    plan, selection = example()
    plan["resource_changes"][0]["change"]["after"]["body"] = body
    with pytest.raises(RuntimeError, match="exact_offline_patch_body"):
        c.guard(plan, selection)


@pytest.mark.parametrize("suffix", ["", ";rev=1", ";rev=3"])
def test_cannot_patch_current_or_other_revision(suffix):
    plan, selection = example()
    plan["resource_changes"][0]["change"]["after"]["resource_id"] = c.p.APIM + "/apis/" + c.p.API + suffix
    with pytest.raises(RuntimeError, match="exact_offline_patch_body"):
        c.guard(plan, selection)


def test_no_companion_or_other_write():
    plan, selection = example()
    plan["resource_changes"].append(deepcopy(plan["resource_changes"][0]))
    with pytest.raises(RuntimeError, match="offline_patch_ONLY"):
        c.guard(plan, selection)


@pytest.mark.parametrize("flag", ["auto_routing_enabled", "poc_controls_enabled", "admin_settings_enabled"])
def test_no_activation_flags(flag):
    plan, selection = example()
    plan["variables"][flag]["value"] = True
    with pytest.raises(RuntimeError, match="exact_offline_inputs"):
        c.guard(plan, selection)


def test_unknown_patch_body_rejected():
    plan, selection = example()
    plan["resource_changes"][0]["change"]["after_unknown"]["body"] = {"properties": {"isOnline": True}}
    with pytest.raises(RuntimeError, match="unknown_patch_input"):
        c.guard(plan, selection)


def test_original_create_is_not_successor_patch():
    plan, selection = example()
    plan["resource_changes"][0]["address"] = c.p.ADDRESS
    with pytest.raises(RuntimeError, match="offline_patch_ONLY"):
        c.guard(plan, selection)