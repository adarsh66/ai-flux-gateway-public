"""Deployment safety regressions; no Azure calls or real credentials."""
import json
from unittest.mock import Mock

import pytest

from scripts.deployment import deploy_portals as d
from scripts.deployment import run_private_sql as r


def private_config():
    return {"ipSecurityRestrictionsDefaultAction": "Deny", "ipSecurityRestrictions": [],
            "scmIpSecurityRestrictionsDefaultAction": "Deny", "scmIpSecurityRestrictions": []}


@pytest.mark.parametrize("kind", ["api", "admin"])
def test_private_without_endpoint_never_bypassed(kind):
    arm = Mock()
    arm.get.return_value = None
    app = {"properties": {"publicNetworkAccess": "Disabled"}}
    with pytest.raises(r.RunnerError, match="private_endpoint_missing"):
        d.network_proof(arm, kind, app, private_config())


@pytest.mark.parametrize("kind", ["api", "admin"])
def test_private_public_enabled_rejected(kind):
    with pytest.raises(r.RunnerError, match="private_site_exposed"):
        d.network_proof(Mock(), kind, {"properties": {"publicNetworkAccess": "Enabled"}}, private_config())


def test_scm_allow_rejected():
    config = private_config()
    config["scmIpSecurityRestrictions"] = [{"action": "Allow", "ipAddress": "Any"}]
    with pytest.raises(r.RunnerError, match="scm_allow_rule"):
        d.network_proof(Mock(), "api", {"properties": {}}, config)


def test_customer_scm_cannot_inherit_public_rules():
    config = private_config()
    config.update(ipSecurityRestrictionsDefaultAction="Allow", scmIpSecurityRestrictionsUseMain=True)
    with pytest.raises(r.RunnerError, match="customer_ingress_mismatch"):
        d.network_proof(Mock(), "customer", {"properties": {"publicNetworkAccess": "Enabled"}}, config)


def test_customer_exact_integration_required():
    config = private_config()
    config.update(ipSecurityRestrictionsDefaultAction="Allow", scmIpSecurityRestrictionsUseMain=False)
    with pytest.raises(r.RunnerError, match="customer_integration_mismatch"):
        d.network_proof(Mock(), "customer", {"properties": {"publicNetworkAccess": "Enabled",
                        "virtualNetworkSubnetId": "/some-other-subnet"}}, config)


def test_fixed_images_are_digest_pinned():
    for kind in d.CLIENTS:
        assert "@sha256:" in d.image(kind)
        assert d.image(kind).endswith(d.DIGESTS[kind])
        assert "latest" not in d.image(kind)


def test_workflow_cannot_skip_steps(tmp_path, monkeypatch):
    (tmp_path / ".azure").mkdir()
    monkeypatch.setattr(d, "ROOT", tmp_path)
    d.workflow("None")
    with pytest.raises(r.RunnerError, match="workflow_step_skipped"):
        d.workflow("UpdateStatus")
    for step in d.WORKFLOW_STEPS[1:]:
        d.workflow(step)
    assert json.loads((tmp_path / ".azure/validate-status.json").read_text())["completedStep"] == "UpdateStatus"


def test_deploy_requires_validated_plan(tmp_path, monkeypatch):
    (tmp_path / ".azure").mkdir()
    (tmp_path / ".azure/deployment-plan.md").write_text("Status: Ready for Validation")
    (tmp_path / ".azure/validate-status.json").write_text('{"completedStep":"UpdateStatus"}')
    monkeypatch.setattr(d, "ROOT", tmp_path)
    arm = Mock()
    with pytest.raises(r.RunnerError, match="validation_workflow_incomplete"):
        d.deploy(arm, r.Redactor())
    arm.request.assert_not_called()


def test_private_probe_no_sql_migration_or_secrets_in_program():
    assert "PORTAL_SMOKE_USERS" in d.PRIVATE_PROBE
    assert "EXPECTED_SOURCE_HASHES" in d.PRIVATE_PROBE
    assert "print(json.dumps({'status'" in d.PRIVATE_PROBE
    assert "alembic" not in d.PRIVATE_PROBE
    assert "seed_portal_users" not in d.PRIVATE_PROBE


def test_snapshot_never_contains_values(monkeypatch):
    arm = Mock()
    arm.get.side_effect = lambda resource, version: ({"properties": {"linuxFxVersion": "", "publicNetworkAccess": "Disabled"}})
    monkeypatch.setattr(d, "read_settings", lambda arm, kind: {"SECRET": "do-not-output"})
    result = d.snapshot(arm)
    assert "do-not-output" not in json.dumps(result)
    assert result["api"]["setting_names"] == ["SECRET"]


def test_deploy_only_patches_images_then_restarts(tmp_path, monkeypatch):
    (tmp_path / ".azure").mkdir()
    (tmp_path / ".azure/deployment-plan.md").write_text("Status: Validated")
    (tmp_path / ".azure/validate-status.json").write_text('{"completedStep":"UpdateStatus"}')
    monkeypatch.setattr(d, "ROOT", tmp_path)
    validation = Mock(return_value={"passed": True})
    monkeypatch.setattr(d, "validate", validation)
    arm = Mock()
    d.deploy(arm, r.Redactor())
    calls = arm.request.call_args_list
    assert len(calls) == 6
    assert [c.args[0] for c in calls] == ["PATCH"] * 3 + ["POST"] * 3
    for kind, call in zip(d.CLIENTS, calls[:3]):
        props = call.args[3]["properties"]
        assert props["linuxFxVersion"] == "DOCKER|" + d.image(kind)
        assert props["acrUseManagedIdentityCreds"] is True
        assert "publicNetworkAccess" not in props
        assert "ipSecurityRestrictions" not in props
    assert validation.call_count == 2