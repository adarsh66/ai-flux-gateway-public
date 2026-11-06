"""Offline-only mutation negatives; no Azure access or historical release calls."""
from copy import deepcopy

import pytest

from scripts.deployment import auto_revision_prepare as stage


def fixture():
    value = stage.reservation("2", "a" * 32, "b" * 64)
    inputs = {"auto_staging_revision": value, "auto_routing_enabled": False,
              "poc_controls_enabled": False, "allow_product_subscriptions": True}
    c = {"actions": ["create"], "before": None, "after": {
        "type": "Microsoft.ApiManagement/service/apis@2024-05-01",
        "parent_id": stage.APIM, "name": stage.API + ";rev=2",
        "body": stage.expected_body(value)}, "after_unknown": {"output": True, "id": True}}
    plan = {"applyable": True, "errored": False,
            "variables": {k: {"value": v} for k, v in inputs.items()},
            "configuration": {"root_module": {"resources": []}},
            "checks": [{"address": {"to_display": stage.ADDRESS}, "status": "pass"}],
            "resource_changes": [{"address": stage.ADDRESS, "mode": "managed", "change": c}]}
    return inputs, plan, deepcopy(plan)


def test_only_new_offline_revision_is_admitted():
    inputs, plan, full = fixture()
    assert stage.guard_target(plan, full, inputs) == {
        "address": stage.ADDRESS, "actions": ["create"], "is_current": False,
        "is_online": False, "companion_never_apply": True, "scoring_budget": 0,
        "completion_budget": 0}


@pytest.mark.parametrize("revision", ["1", "0", "02", "2/other", "2;rev=3", "1000000", "-2", ""])
def test_noncurrent_revision_name_is_bounded(revision):
    with pytest.raises(RuntimeError, match="exact_noncurrent_revision"):
        stage.reservation(revision, "a" * 32, "b" * 64)


@pytest.mark.parametrize("field,value", [("owner_nonce", "a" * 31), ("owner_nonce", "A" * 32),
                                        ("baseline_sha256", "x" * 64), ("baseline_sha256", "b" * 63)])
def test_ownership_and_complete_baseline_binding_required(field, value):
    args = {"revision": "2", "nonce": "a" * 32, "baseline_sha256": "b" * 64}
    args["nonce" if field == "owner_nonce" else field] = value
    with pytest.raises(RuntimeError, match="exact_"):
        stage.reservation(**args)


@pytest.mark.parametrize("field,value", [("isCurrent", True), ("isOnline", True),
    ("isOnline", None), ("sourceApiId", stage.APIM + "/apis/aiflux-native-validation-pending"),
    ("path", "v1"), ("apiRevision", "1"), ("apiRevisionDescription", "foreign owner")])
def test_revision_cannot_be_online_current_foreign_or_unowned(field, value):
    inputs, plan, full = fixture()
    plan["resource_changes"][0]["change"]["after"]["body"]["properties"][field] = value
    full["resource_changes"] = deepcopy(plan["resource_changes"])
    with pytest.raises(RuntimeError, match="exact_offline_body"):
        stage.guard_target(plan, full, inputs)


@pytest.mark.parametrize("actions", [["update"], ["delete"], ["delete", "create"]])
def test_no_update_delete_or_adoption(actions):
    inputs, plan, full = fixture()
    plan["resource_changes"][0]["change"]["actions"] = actions
    with pytest.raises(RuntimeError, match="new_owned_revision_only"):
        stage.guard_target(plan, full, inputs)


@pytest.mark.parametrize("address", [stage.POLICY, "azapi_resource.poc_settings[0]",
    'azurerm_linux_web_app.main["api"]', 'azurerm_role_assignment.gateway',
    'azapi_resource.project_child["api"]'])
def test_any_extra_write_is_rejected(address):
    inputs, plan, full = fixture()
    extra = deepcopy(plan["resource_changes"][0])
    extra["address"] = address
    plan["resource_changes"].append(extra)
    with pytest.raises(RuntimeError, match="offline_revision_only"):
        stage.guard_target(plan, full, inputs)


def test_unknown_writable_body_is_rejected():
    inputs, plan, full = fixture()
    plan["resource_changes"][0]["change"]["after_unknown"]["body"] = True
    with pytest.raises(RuntimeError, match="unknown_writable_input"):
        stage.guard_target(plan, full, inputs)


def test_unresolved_companion_cannot_validate_target():
    inputs, plan, full = fixture()
    full["checks"][0]["status"] = "unknown"
    with pytest.raises(RuntimeError, match="full_checks_required"):
        stage.guard_target(plan, full, inputs)


def test_different_companion_variables_rejected():
    inputs, plan, full = fixture()
    full["variables"]["auto_staging_revision"]["value"]["revision"] = "3"
    with pytest.raises(RuntimeError, match="identical_full_companion"):
        stage.guard_target(plan, full, inputs)


def test_targeted_unknown_check_requires_actual_passing_full_check():
    inputs, plan, full = fixture()
    plan["checks"][0]["status"] = "unknown"
    assert stage.guard_target(plan, full, inputs)["is_online"] is False


def test_collision_or_missing_current_revision_is_never_permission_to_adopt():
    with pytest.raises(RuntimeError, match="revision_collision"):
        stage.require_absent_revision([{"revision": "2", "is_current": True}], "2")
    with pytest.raises(RuntimeError, match="one_actual_current_revision"):
        stage.require_absent_revision([{"revision": "1", "is_current": False}], "2")
    stage.require_absent_revision([{"revision": "1", "is_current": True}], "2")


def test_companion_rejects_all_unrelated_writes():
    _, plan, _ = fixture()
    extra = deepcopy(plan["resource_changes"][0])
    extra["address"] = "azapi_resource.foreign"
    plan["resource_changes"].append(extra)
    with pytest.raises(RuntimeError, match="companion_unapproved_write"):
        stage.guard_companion(plan, "<policies />")


def test_no_apply_invocation_or_probe_entrypoint_in_preparation():
    import inspect
    source = inspect.getsource(stage.main)
    assert 'tf("apply"' not in source
    assert 'tf("destroy"' not in source
    assert "get-access-token" not in source
    assert "--no-push" not in source  # no UI validation/build replay either