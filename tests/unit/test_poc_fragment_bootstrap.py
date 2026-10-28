"""Offline mutation tests; no Azure requests or persistent deployment writes."""
from copy import deepcopy
import json

import pytest

from scripts.deployment import poc_fragment_bootstrap as b


@pytest.fixture
def plan(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "HOME", tmp_path)
    inputs = tmp_path / "inputs.json"
    monkeypatch.setattr(b, "INPUT", inputs)
    inputs.write_text("{}")
    (tmp_path / "state-before-summary.json").write_text(json.dumps({"managed_addresses": ["azapi_resource.project_policy[0]"]}))
    from scripts.deployment.project_route_persistent import APPROVED
    values = {**APPROVED, "enabled": True, "poc_settings_bootstrap_enabled": True,
              "poc_controls_enabled": False, "poc_publisher_permissions_verified": False,
              "allow_product_subscriptions": True, "glm_enabled": True, "excluded_routes": []}
    models = ["FW-GLM-5.3", "FW-MiniMax-M3", "glm-5.3"] + ["old-" + str(n) for n in range(10)]
    policy = '<policies><inbound><set-body>' + json.dumps({"data": [{"id": m} for m in models]}) + '</set-body></inbound></policies>'
    return {"applyable": True, "errored": False, "checks": [{"status": "pass"}],
            "variables": {k: {"value": v} for k, v in values.items()}, "resource_changes": [
                {"address": b.ADDRESS, "change": {"actions": ["create"], "before": None,
                 "after": {"name": b.FRAGMENT, "parent_id": b.APIM,
                 "type": "Microsoft.ApiManagement/service/policyFragments@2024-05-01",
                 "body": {"properties": {"description": "Runtime-owned bounded POC variables and literal-call quota; stable counter identity and envelope.",
                 "format": "rawxml", "value": b.DEFAULTS.read_text()}}}, "after_unknown": {"id": True, "output": True}}},
                {"address": "azapi_resource.project_policy[0]", "change": {"actions": ["no-op"],
                 "after": {"body": {"properties": {"value": policy}}}}}]}


def test_exact_create_accepts_missing_runtime_publisher_permission(plan):
    assert b.guard(plan)["actions"] == ["create"]


@pytest.mark.parametrize("actions", [["update"], ["delete", "create"], ["delete"], ["no-op"]])
def test_no_overwrite_replacement_or_delete(plan, actions):
    plan["resource_changes"][0]["change"]["actions"] = actions
    with pytest.raises(RuntimeError):
        b.guard(plan)


@pytest.mark.parametrize("address", ["azapi_resource.project_policy[0]", "azurerm_role_assignment.publisher", "azurerm_linux_web_app.api"])
def test_any_extra_write_refused(plan, address):
    plan["resource_changes"].append({"address": address, "change": {"actions": ["update"]}})
    with pytest.raises(RuntimeError):
        b.guard(plan)


@pytest.mark.parametrize("field,value", [("poc_controls_enabled", True), ("poc_settings_bootstrap_enabled", False), ("poc_publisher_permissions_verified", True)])
def test_activation_or_fake_publisher_proof_refused(plan, field, value):
    plan["variables"][field]["value"] = value
    with pytest.raises(RuntimeError):
        b.guard(plan)


@pytest.mark.parametrize("field,value", [("name", "other"), ("parent_id", "/other"), ("type", "Microsoft.ApiManagement/service/apis/policies@2024-05-01")])
def test_wrong_target_refused(plan, field, value):
    plan["resource_changes"][0]["change"]["after"][field] = value
    with pytest.raises(RuntimeError):
        b.guard(plan)


def test_changed_safe_defaults_refused(plan):
    plan["resource_changes"][0]["change"]["after"]["body"]["properties"]["value"] = "<fragment />"
    with pytest.raises(RuntimeError):
        b.guard(plan)


def test_unresolved_checks_refused(plan):
    plan["checks"][0]["status"] = "unknown"
    with pytest.raises(RuntimeError):
        b.guard(plan)


def test_unknown_writable_value_refused(plan):
    plan["resource_changes"][0]["change"]["after_unknown"]["body"] = True
    with pytest.raises(RuntimeError):
        b.guard(plan)


def test_checkpoint_atomic_and_preserves_history(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "HOME", tmp_path)
    b.checkpoint("one", cloud_writes=0)
    b.checkpoint("two")
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["stage"] == "two" and result["cloud_writes"] == 0
    assert [v["stage"] for v in result["history"]] == ["one", "two"]


def test_fragment_collection_subtracts_only_exact_created_row_and_count():
    old = {"name": "existing", "id": "/existing", "properties": {"value": "unchanged"}}
    response = {"count": 2, "value": [old, {"name": b.FRAGMENT, "id": b.ID}]}
    assert b.without_created_fragment(response) == {"count": 1, "value": [old]}
    assert response["count"] == 2
    assert b.without_created_fragment({"count": 0, "value": []}) == {"count": 0, "value": []}


@pytest.mark.parametrize("response", [
    {"count": 3, "value": []},
    {"count": 1, "value": [{"name": b.FRAGMENT, "id": "/wrong"}]},
    {"count": 0, "value": [], "nextLink": "unexpected"},
    {"count": 2, "value": [{"name": b.FRAGMENT, "id": b.ID}, {"name": b.FRAGMENT, "id": b.ID}]},
])
def test_fragment_collection_rejects_bad_count_identity_pagination_or_duplicate(response):
    with pytest.raises(RuntimeError):
        b.without_created_fragment(response)


def test_source_retains_lifecycle_and_default_off():
    source = (b.TFROOT / "poc-controls.tf").read_text()
    assert 'variable "poc_settings_bootstrap_enabled"' in source
    assert "var.enabled && (var.poc_settings_bootstrap_enabled || var.poc_controls_enabled)" in source
    assert "prevent_destroy = true" in source
    assert "ignore_changes = [body.properties.value]" in source
    assert "&& var.poc_publisher_permissions_verified" in source
    assert 'default     = false' in source.split('variable "poc_settings_bootstrap_enabled"', 1)[1].split('variable "poc_controls_enabled"', 1)[0]


@pytest.mark.parametrize("mutation", [None, "meaningful_policy_change", "extra_write", "stored_policy_drift"])
def test_representation_companion_is_not_a_drift_waiver(mutation):
    from scripts.deployment.poc_fragment_bootstrap_exact import companion_guard
    before = {"format": "xml", "value": "<policies><inbound /></policies>"}
    after = {"format": "rawxml", "value": "<policies><inbound /></policies>"}
    old = {"body": {"properties": deepcopy(before)}, "output": {}}
    new = {"body": {"properties": deepcopy(after)}, "output": None}
    original = {"applyable": True, "checks": [{"status": "pass"}], "resource_changes": [
        {"address": b.ADDRESS, "change": {"actions": ["create"]}},
        {"address": "azapi_resource.project_policy[0]", "change": {"actions": ["update"], "before": old, "after": new}}]}
    state = {"values": {"root_module": {"resources": [{"address": "azapi_resource.project_policy[0]", "values": deepcopy(new)}]}}}
    if mutation == "meaningful_policy_change":
        new["body"]["properties"]["value"] = "<policies><inbound><base /></inbound></policies>"
    if mutation == "extra_write":
        original["resource_changes"].append({"address": "other", "change": {"actions": ["update"]}})
    if mutation == "stored_policy_drift":
        state["values"]["root_module"]["resources"][0]["values"]["body"] = {}

    class Run:
        def terraform(self, *args):
            return json.dumps(original if len(args) == 3 else state)

        def policy(self):
            return before["value"]

    if mutation:
        with pytest.raises(RuntimeError):
            companion_guard(Run())
    else:
        assert companion_guard(Run()) is not None


@pytest.mark.parametrize("mutation", [None, "policy_write", "extra_write", "wrong_inputs", "wrong_xml", "failed_check"])
def test_targeted_release_requires_identical_full_companion_and_no_policy_write(plan, mutation):
    from scripts.deployment.poc_fragment_bootstrap_targeted import targeted_guard
    plan["checks"][0]["address"] = "var.example"
    full = deepcopy(plan)
    full["resource_changes"][1]["change"]["actions"] = ["update"]
    target = deepcopy(plan)
    target["resource_changes"] = target["resource_changes"][:1]
    if mutation == "policy_write":
        target["resource_changes"].append(deepcopy(full["resource_changes"][1]))
    if mutation == "extra_write":
        target["resource_changes"].append({"address": "other", "change": {"actions": ["update"]}})
    if mutation == "wrong_inputs":
        target["variables"]["poc_controls_enabled"]["value"] = True
    if mutation == "wrong_xml":
        target["resource_changes"][0]["change"]["after"]["body"]["properties"]["value"] = "<fragment />"
    if mutation == "failed_check":
        full["checks"][0]["status"] = "fail"
    if mutation:
        with pytest.raises(RuntimeError):
            targeted_guard(target, full)
    else:
        assert targeted_guard(target, full)["policy_writes_in_release"] == 0


@pytest.mark.parametrize("mutation", [None, "semantic_change", "stored_change", "nonbody_change", "extra_write"])
def test_fresh_companion_is_exact_export_diagnosis_only(plan, mutation):
    from scripts.deployment.poc_fragment_bootstrap_targeted import companion_guard
    c = plan["resource_changes"][1]["change"]
    c["after"]["body"]["properties"]["format"] = "rawxml"
    c["after"]["output"] = None
    c["before"] = deepcopy(c["after"])
    c["before"]["body"]["properties"]["format"] = "xml"
    c["before"]["output"] = {}
    c["actions"] = ["update"]
    stored = deepcopy(c["after"])
    live = c["before"]["body"]["properties"]["value"]
    if mutation == "semantic_change":
        c["after"]["body"]["properties"]["value"] = "<policies />"
    if mutation == "stored_change":
        stored["body"] = {}
    if mutation == "nonbody_change":
        c["after"]["name"] = "other"
    if mutation == "extra_write":
        plan["resource_changes"].append({"address": "other", "change": {"actions": ["update"]}})
    if mutation:
        with pytest.raises(RuntimeError):
            companion_guard(plan, stored, live)
    else:
        assert companion_guard(plan, stored, live)["companion_never_apply"] is True


@pytest.mark.parametrize("address,status,companion_status,accept", [
    ("var.excluded_routes", "unknown", "pass", True),
    ("var.excluded_routes", "unknown", "fail", False),
    ("var.excluded_routes", "fail", "pass", False),
    ("azapi_resource.poc_settings", "unknown", "pass", False),
    ("var.unexpected", "unknown", "pass", False),
])
def test_target_excluded_check_requires_exact_enumeration_and_full_pass(plan, address, status, companion_status, accept):
    from scripts.deployment.poc_fragment_bootstrap_targeted import targeted_guard
    full = deepcopy(plan)
    full["checks"] = [{"address": {"to_display": address}, "status": companion_status}]
    full["resource_changes"][1]["change"]["actions"] = ["update"]
    target = deepcopy(plan)
    target["checks"] = [{"address": {"to_display": address}, "status": status}]
    target["resource_changes"] = target["resource_changes"][:1]
    if accept:
        assert targeted_guard(target, full)["companion_resolved_excluded_checks"] == [address]
    else:
        with pytest.raises(RuntimeError):
            targeted_guard(target, full)