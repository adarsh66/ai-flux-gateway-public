"""Offline successor adapter guards; never run Azure or Terraform."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / ".deployment/customer-send-plan-once.py"
spec = importlib.util.spec_from_file_location("customer_send_plan_once", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_original_build_source_binding_offline():
    assert m.build_binding(remote=False)["run_id"] == "cm38"


@pytest.mark.parametrize("key", ["baseline", "supplemental", "state_owner", "revisions", "current_api_sha256", "storage_sha256"])
def test_any_protected_drift_fails(key):
    before = {k: "same" for k in ("baseline", "supplemental", "state_owner", "revisions", "current_api_sha256", "storage_sha256")}
    before["remote_head"] = {k: "same" for k in ("etag", "content_length", "last_modified", "lease_status", "lease_state")}
    after = deepcopy(before)
    m.unchanged(before, after)
    after[key] = "changed"
    with pytest.raises(RuntimeError):
        m.unchanged(before, after)


@pytest.mark.parametrize("key", ["etag", "content_length", "last_modified", "lease_status", "lease_state"])
def test_remote_state_drift_fails(key):
    before = {k: "same" for k in ("baseline", "supplemental", "state_owner", "revisions", "current_api_sha256", "storage_sha256")}
    before["remote_head"] = {k: "same" for k in ("etag", "content_length", "last_modified", "lease_status", "lease_state")}
    after = deepcopy(before)
    after["remote_head"][key] = "changed"
    with pytest.raises(RuntimeError):
        m.unchanged(before, after)


@pytest.mark.parametrize("command", [("apply",), ("destroy",), ("import",), ("state", "rm"), ("workspace", "new")])
def test_no_mutating_command(command, monkeypatch):
    c = m.Controller(m.r.rt.HOME / "customer-send-plan-20261029TTEST")
    monkeypatch.setattr(m.subprocess, "run", lambda *_a, **_k: pytest.fail("command escaped guard"))
    with pytest.raises(RuntimeError):
        c.tf(*command)


def test_existing_package_fails_before_build_or_cloud(monkeypatch, tmp_path):
    monkeypatch.setattr(m.r.rt, "HOME", tmp_path)
    home = tmp_path / "customer-send-plan-20261029TTEST"
    home.mkdir()
    monkeypatch.setattr(m, "build_binding", lambda: pytest.fail("replay"))
    with pytest.raises(RuntimeError, match="never_replay"):
        m.Controller(home).run()


@pytest.mark.parametrize("field,unknown", [
    ("app_settings", {"unseen_setting": True}),
    ("identity", [{"identity_ids": [True]}]),
    ("site_config", [{"application_stack": [{"docker_image_name": True}]}]),
    ("site_config", [{"application_stack": [{"docker_registry_password": True}]}]),
    ("https_only", True),
    ("public_network_access_enabled", True),
    ("auth_settings_v2", [{"auth_enabled": True}]),
    ("virtual_network_subnet_id", True),
])
def test_nested_writable_unknowns_cannot_escape_image_guard(field, unknown):
    original_spec = importlib.util.spec_from_file_location("original_send_tests", PATH.parents[1] / "tests/unit/test_customer_send_release.py")
    original = importlib.util.module_from_spec(original_spec)
    original_spec.loader.exec_module(original)
    plan, before = original.plan_fixture()
    plan["resource_changes"][0]["change"]["after_unknown"] = {field: unknown}
    with pytest.raises(RuntimeError, match="unknown_writable"):
        m.r.guard(plan, original.IMAGE, before, {"complete": "preserved"})


@pytest.mark.parametrize("mutation", ["variables", "configuration", "customer_change", "failed_check", "unknown_check", "deferred"])
def test_companion_cannot_launder_different_inputs_or_customer_change(mutation):
    target = {"configuration": {"root": "same"}, "variables": {"image": "same"},
        "checks": [{"address": {"name": "required"}, "status": "unknown"}],
        "resource_changes": [{"address": m.r.ADDRESS, "change": {"actions": ["update"], "after": {"exact": True}}}]}
    full = deepcopy(target)
    full["checks"][0]["status"] = "pass"
    assert m.r.login.resolve(target, full, {m.r.ADDRESS})["checks"][0]["status"] == "pass"
    if mutation == "variables":
        full["variables"] = {"image": "different"}
    if mutation == "configuration":
        full["configuration"] = {"root": "different"}
    if mutation == "customer_change":
        full["resource_changes"][0]["change"]["after"] = {"exact": False}
    if mutation in {"failed_check", "unknown_check"}:
        full["checks"][0]["status"] = "fail" if mutation == "failed_check" else "unknown"
    if mutation == "deferred":
        full["deferred_changes"] = [{"not": "safe"}]
    with pytest.raises(RuntimeError):
        m.r.login.resolve(target, full, {m.r.ADDRESS})