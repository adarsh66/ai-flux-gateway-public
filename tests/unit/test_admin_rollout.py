"""Admin release scope and private-state safety: no Azure access."""
import json
from unittest.mock import Mock

import pytest

from scripts.deployment import admin_rollout as d
from scripts.deployment import deploy_portals as p
from scripts.deployment import run_private_sql as r


def test_deploy_requires_admin_specific_validation(tmp_path, monkeypatch):
    (tmp_path / ".azure").mkdir()
    (tmp_path / ".azure/deployment-plan.md").write_text("Status: Validated")
    (tmp_path / ".azure/validate-status.json").write_text('{"completedStep":"UpdateStatus"}')
    monkeypatch.setattr(p, "ROOT", tmp_path)
    arm = Mock()
    with pytest.raises(r.RunnerError, match="admin_validation_incomplete"):
        d.deploy(arm, r.Redactor())
    arm.assert_not_called()
    arm.request.assert_not_called()


def test_deploy_only_admin_image_and_restart(tmp_path, monkeypatch):
    (tmp_path / ".azure").mkdir()
    (tmp_path / ".azure/deployment-plan.md").write_text("Admin ingress status: Validated")
    (tmp_path / ".azure/validate-status.json").write_text('{"completedStep":"UpdateStatus"}')
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}")
    monkeypatch.setattr(d, "BASELINE", baseline)
    monkeypatch.setattr(p, "ROOT", tmp_path)
    monkeypatch.setattr(d, "validate", Mock(return_value={}))
    monkeypatch.setattr(d, "preserve_others", Mock())
    arm = Mock()
    arm.get.side_effect = lambda path, version: {"properties": (
        {"virtualNetworkSubnetId": p.INTEGRATION} if path == p.site("admin") else
        {"linuxFxVersion": d.IMAGE, **d.ingress.restriction_properties([])})}
    assert d.deploy(arm, r.Redactor())["status"] == "deployed_private_pending_smoke"
    calls = arm.request.call_args_list
    assert len(calls) == 2
    assert calls[0].args[:2] == ("PATCH", p.site("admin") + "/config/web")
    assert calls[1].args[:2] == ("POST", p.site("admin") + "/restart")
    assert set(calls[0].args[3]["properties"]) == {
        "linuxFxVersion", "acrUseManagedIdentityCreds", "acrUserManagedIdentityID", "alwaysOn", "healthCheckPath"}


def test_deploy_write_failure_closes_public(tmp_path, monkeypatch):
    (tmp_path / ".azure").mkdir()
    (tmp_path / ".azure/deployment-plan.md").write_text("Admin ingress status: Validated")
    (tmp_path / ".azure/validate-status.json").write_text('{"completedStep":"UpdateStatus"}')
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}")
    monkeypatch.setattr(d, "BASELINE", baseline)
    monkeypatch.setattr(p, "ROOT", tmp_path)
    monkeypatch.setattr(d, "validate", Mock(return_value={}))
    close = Mock()
    monkeypatch.setattr(d.ingress, "set_public", close)
    arm = Mock()
    arm.get.side_effect = lambda path, version: {"properties": (
        {"virtualNetworkSubnetId": p.INTEGRATION} if path == p.site("admin") else d.ingress.restriction_properties([]))}
    arm.request.side_effect = TimeoutError
    with pytest.raises(TimeoutError):
        d.deploy(arm, r.Redactor())
    close.assert_called_once_with(arm, p.site("admin"), "Disabled")


def test_other_sites_change_is_rejected(monkeypatch):
    baseline = {"api": {"image": "old"}, "customer": {}, "sql_public": "Disabled"}
    current = json.loads(json.dumps(baseline))
    current["api"]["image"] = "new"
    monkeypatch.setattr(d, "snapshot", lambda arm: current)
    with pytest.raises(r.RunnerError, match="out_of_scope_state_changed"):
        d.preserve_others(Mock(), baseline)


def test_private_probe_tests_same_origin_admin_authorization():
    assert "login=call(admin,'/api/auth/login'" in p.PRIVATE_PROBE
    assert "token=login['token'];call(admin,'/api/me'" in p.PRIVATE_PROBE
    assert "call(admin,path,200 if user['role']=='ids_admin' else 403" in p.PRIVATE_PROBE
    assert "call(admin,'/api/auth/login',401" in p.PRIVATE_PROBE
    compile(p.PRIVATE_PROBE, "private-probe", "exec")