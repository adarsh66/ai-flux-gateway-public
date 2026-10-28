"""Entire-policy rejection guard for the explicit no-deadline bounded POC."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts.deployment.apim_route_repair import APIM, RepairBlocked
from scripts.deployment.project_route_models import POLICY
from scripts.deployment.project_route_persistent import APPROVED, guard_persistent_update

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def persistent_update():
    def render(persistent):
        args = ["terraform", "-chdir=" + str(ROOT / "infra/project-route"), "console", "-no-color",
                "-var=demo_authorized=true", "-var=rpm_limit=60", "-var=daily_call_allowance=1000",
                "-var=route_manifest_path=" + (ROOT / "gateway/catalog/project-routes.json").as_posix()]
        args += (["-var=persistent_poc_authorized=true", "-var=completion_token_limit=1024", "-var=tpm_limit=2048"]
                 if persistent else ["-var=demo_expires_at=2026-10-27T05:41:01Z"])
        proc = subprocess.run(args, input="jsonencode({policy=local.policy})\n", capture_output=True, text=True,
            env={**os.environ, "TF_CLI_CONFIG_FILE": str(ROOT / ".deployment/terraform.rc")}, timeout=90)
        assert proc.returncode == 0, proc.stderr
        return json.loads(json.loads(proc.stdout[proc.stdout.find('"'):]))
    before, rendered = render(False), render(True)
    obj = {"type": "Microsoft.ApiManagement/service/apis/policies@2024-05-01",
           "parent_id": APIM + "/apis/aiflux-dev-unified", "name": "policy",
           "body": {"properties": {"format": "rawxml", "value": before["policy"]}}}
    new = deepcopy(obj)
    new["body"]["properties"]["value"] = rendered["policy"]
    previous = {**APPROVED, "persistent_poc_authorized": False, "completion_token_limit": 32,
                "tpm_limit": 1000, "demo_expires_at": "2026-10-27T05:41:01Z",
                "route_manifest_path": "preserved", "excluded_routes": []}
    plan = {"applyable": True, "variables": {k: {"value": v} for k, v in {**previous, **APPROVED}.items()},
            "resource_changes": [{"address": POLICY, "change": {"actions": ["update"], "before": obj, "after": new}}]}
    return plan, rendered, before["policy"], previous


def test_only_output_tpm_and_expiry_change(persistent_update):
    guard_persistent_update(*persistent_update)
    policy = persistent_update[1]["policy"]
    assert 'modelMaximum = 1024;' in policy
    assert 'tokens-per-minute="2048"' in policy
    assert 'demo_expired' not in policy and 'DateTime.Parse' not in policy
    assert 'first-period-start' not in policy
    assert all(alias in policy for alias in json.loads((ROOT / 'gateway/catalog/project-routes.json').read_text())['routes'])


@pytest.mark.parametrize("field,value", [("rpm_limit", 61), ("tpm_limit", 2049), ("daily_token_quota", 10001),
    ("daily_call_allowance", 1001), ("completion_token_limit", 1025), ("backend_retries", 1),
    ("safety_threshold", 2), ("acceptance_verified", True), ("candidate_validation", True),
    ("demo_expires_at", "2099-01-01T00:00:00Z"), ("persistent_poc_authorized", False), ("excluded_routes", ["gpt-4o"])])
def test_unapproved_inputs_rejected(persistent_update, field, value):
    plan, rendered, before, previous = deepcopy(persistent_update)
    plan["variables"][field]["value"] = value
    with pytest.raises(RepairBlocked):
        guard_persistent_update(plan, rendered, before, previous)


@pytest.mark.parametrize("old,new", [('"tpm:"', '"new-counter:"'), ('"project-demo:"', '"new-epoch:"'),
    ('calls="1000"', 'calls="1001"'), ('renewal-period="86400"', 'renewal-period="43200"'),
    ('token-quota="10000"', 'token-quota="10001"'), ('threshold="1"', 'threshold="7"'),
    ('shield-prompt="true"', 'shield-prompt="false"'), ('pii_inspection_unavailable', 'pii_optional'),
    ('gpt-6.1-sol', 'unapproved-model'), ('modelMaximum = 1024;', 'modelMaximum = 100000;')])
def test_any_other_policy_change_rejected(persistent_update, old, new):
    plan, rendered, before, previous = deepcopy(persistent_update)
    assert old in rendered["policy"]
    rendered["policy"] = rendered["policy"].replace(old, new)
    plan["resource_changes"][0]["change"]["after"]["body"]["properties"]["value"] = rendered["policy"]
    with pytest.raises(RepairBlocked):
        guard_persistent_update(plan, rendered, before, previous)


@pytest.mark.parametrize("mutation", ["foreign", "create", "delete", "unknown", "wrong_target"])
def test_scope_unknowns_and_replacements_rejected(persistent_update, mutation):
    plan, rendered, before, previous = deepcopy(persistent_update)
    change = plan["resource_changes"][0]["change"]
    if mutation == "foreign":
        plan["resource_changes"].append({"address": "foreign", "change": {"actions": ["update"]}})
    elif mutation == "unknown":
        change["after_unknown"] = {"body": {"properties": {"value": True}}}
    elif mutation == "wrong_target":
        change["after"]["parent_id"] += "-other"
    else:
        change["actions"] = [mutation]
    with pytest.raises(RepairBlocked):
        guard_persistent_update(plan, rendered, before, previous)