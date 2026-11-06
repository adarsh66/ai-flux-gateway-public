"""Computed identity reconciliation must never admit unknown writable inputs."""
from copy import deepcopy

import pytest

from scripts.deployment import auto_revision_offline_reconcile as r
from tests.unit.test_auto_revision_offline_correct import example


def fixture():
    plan, selection = example()
    plan["configuration"] = {"root_module": {"resources": [{
        "address": r.c.ADDRESS.split("[")[0], "expressions": {
            "body": {"constant_value": {"properties": {"isOnline": False}}},
            "resource_id": {"references": ["local.apim", "var.auto_staging_revision"]}}}]}}
    plan["resource_changes"][0]["change"]["after_unknown"].update(name=True, parent_id=True)
    attrs = {k: {"computed": True, "optional": True, "type": "string"} for k in r.DERIVED}
    return plan, selection, attrs


def test_observed_computed_identity_only_and_no_input_mutation():
    plan, selection, attrs = fixture()
    prior = deepcopy(plan)
    assert r.guard(plan, selection, attrs)["api_creates"] == 0
    assert plan == prior
    with pytest.raises(RuntimeError, match="unknown_patch_input"):
        r.c.guard(plan, selection)


@pytest.mark.parametrize("key", ["resource_id", "type", "body", "sensitive_body", "update_headers",
    "update_query_parameters", "retry", "read_override", "locks", "arbitrary_writable"])
def test_all_writable_unknowns_remain_rejected(key):
    plan, selection, attrs = fixture()
    plan["resource_changes"][0]["change"]["after_unknown"][key] = True
    with pytest.raises(RuntimeError, match="unknown_patch_input"):
        r.guard(plan, selection, attrs)


@pytest.mark.parametrize("key", ["name", "parent_id"])
def test_configured_identity_unknown_is_not_derived(key):
    plan, selection, attrs = fixture()
    plan["configuration"]["root_module"]["resources"][0]["expressions"][key] = {"references": ["var.input"]}
    with pytest.raises(RuntimeError, match="unconfigured"):
        r.guard(plan, selection, attrs)


@pytest.mark.parametrize("key", ["name", "parent_id"])
def test_noncomputed_schema_rejected(key):
    plan, selection, attrs = fixture()
    attrs[key]["computed"] = False
    with pytest.raises(RuntimeError, match="computed_identity"):
        r.guard(plan, selection, attrs)


@pytest.mark.parametrize("value", [{"nested": True}, [True], 1, "true", None])
def test_only_boolean_computed_unknown_shape(value):
    plan, selection, attrs = fixture()
    plan["resource_changes"][0]["change"]["after_unknown"]["name"] = value
    with pytest.raises(RuntimeError, match="unknown_shape"):
        r.guard(plan, selection, attrs)


def test_nested_writable_body_unknown_rejected():
    plan, selection, attrs = fixture()
    plan["resource_changes"][0]["change"]["after_unknown"]["body"] = {"properties": {"isOnline": True}}
    with pytest.raises(RuntimeError, match="unknown_patch_input"):
        r.guard(plan, selection, attrs)


def test_exact_resource_id_still_locked():
    plan, selection, attrs = fixture()
    plan["resource_changes"][0]["change"]["after"]["resource_id"] = r.p.APIM + "/apis/" + r.p.API + ";rev=1"
    with pytest.raises(RuntimeError, match="exact_offline_patch_body"):
        r.guard(plan, selection, attrs)


def test_embedded_constant_cannot_disagree():
    plan, selection, attrs = fixture()
    plan["configuration"]["root_module"]["resources"][0]["expressions"]["body"]["constant_value"]["properties"]["isOnline"] = True
    with pytest.raises(RuntimeError, match="body_constant_locked"):
        r.guard(plan, selection, attrs)


@pytest.mark.parametrize("body", [{"properties": {"isOnline": True}}, {"properties": {"isOnline": 0}},
    {"properties": {"isOnline": False, "isCurrent": False}}])
def test_body_known_false_only(body):
    plan, selection, attrs = fixture()
    plan["resource_changes"][0]["change"]["after"]["body"] = body
    with pytest.raises(RuntimeError, match="exact_offline_patch_body"):
        r.guard(plan, selection, attrs)