"""Offline render and rejection tests; never infer live acceptance from fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts.deployment.apim_route_repair import RepairBlocked
from scripts.deployment.project_route_models import EXPIRY, POLICY, guard_model_update

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def model_update():
    def render(multi):
        args = ["terraform", "-chdir=" + str(ROOT / "infra/project-route"), "console", "-no-color",
                "-var=demo_authorized=true", "-var=rpm_limit=60", "-var=daily_call_allowance=1000",
                "-var=demo_expires_at=" + EXPIRY]
        if multi:
            args += ["-var=route_manifest_path=" + (ROOT / "gateway/catalog/project-routes.json").as_posix()]
        proc = subprocess.run(args, input="jsonencode({policy=local.policy})\n", capture_output=True,
            text=True, env={**os.environ, "TF_CLI_CONFIG_FILE": str(ROOT / ".deployment/terraform.rc")}, timeout=90)
        assert proc.returncode == 0, proc.stderr
        return json.loads(json.loads(proc.stdout[proc.stdout.find('"'):]))
    before, after = render(False), render(True)
    obj = {"type": "Microsoft.ApiManagement/service/apis/policies@2024-05-01",
           "parent_id": "/existing/apis/aiflux-dev-unified", "name": "policy",
           "body": {"properties": {"format": "rawxml", "value": before["policy"]}}}
    new = deepcopy(obj)
    new["body"]["properties"]["value"] = after["policy"]
    values = {"rpm_limit": 60, "tpm_limit": 1000, "daily_token_quota": 10000, "daily_call_allowance": 1000,
              "completion_token_limit": 32, "backend_retries": 0, "safety_threshold": 1,
              "demo_expires_at": EXPIRY, "demo_authorized": True, "candidate_validation": False, "acceptance_verified": False}
    plan = {"applyable": True, "variables": {k: {"value": v} for k, v in values.items()},
            "resource_changes": [{"address": POLICY, "change": {"actions": ["update"], "before": obj, "after": new}}]}
    return plan, after, before["policy"], json.loads((ROOT / "gateway/catalog/project-routes.json").read_text())


def test_exact_ten_model_render_preserves_security(model_update):
    guard_model_update(*model_update)
    policy = model_update[1]["policy"]
    assert policy.count("<forward-request") == 1
    assert "<retry" not in policy
    assert 'request["max_tokens"] = request["max_completion_tokens"]' in policy
    assert "Decision-1" not in policy


@pytest.mark.parametrize("mutation", ["foreign", "delete", "counter", "expiry", "unknown", "backend", "safety", "missing_luna"])
def test_guard_rejects_unapproved_changes(model_update, mutation):
    plan, rendered, before, manifest = deepcopy(model_update)
    change = plan["resource_changes"][0]["change"]
    if mutation == "foreign":
        plan["resource_changes"].append({"address": "foreign", "change": {"actions": ["update"]}})
    elif mutation == "delete":
        change["actions"] = ["delete"]
    elif mutation == "expiry":
        plan["variables"]["demo_expires_at"]["value"] = "2026-10-28T05:41:01Z"
    elif mutation == "unknown":
        change["after_unknown"] = {"body": {"properties": {"value": True}}}
    elif mutation == "missing_luna":
        del manifest["routes"]["gpt-5.6-luna"]
    else:
        pairs = {"counter": ('"tpm:"', '"new-counter:"'), "backend": ("aiflux-project-gpt-5-6-luna", "arbitrary-backend"),
                 "safety": ('threshold="1"', 'threshold="7"')}
        old, new = pairs[mutation]
        rendered["policy"] = rendered["policy"].replace(old, new)
        change["after"]["body"]["properties"]["value"] = rendered["policy"]
    with pytest.raises(RepairBlocked):
        guard_model_update(plan, rendered, before, manifest)