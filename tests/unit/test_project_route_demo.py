"""Real Terraform render and independent demo guard; no live acceptance claims."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts.deployment.apim_route_repair import RepairBlocked
from scripts.deployment.project_route_demo import guard_demo_plan, guard_policy_update, policy_structure
from test_apim_project_route import candidate_plan


@pytest.fixture(scope="module")
def demo():
    expiry = (datetime.now(UTC) + timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%SZ")
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "TF_CLI_CONFIG_FILE": str(root / ".deployment/terraform.rc")}
    proc = subprocess.run(["terraform", "-chdir=" + str(root / "infra/project-route"), "console", "-no-color",
                           "-var=demo_authorized=true", "-var=rpm_limit=60", "-var=demo_expires_at=" + expiry],
                          input="jsonencode({policy=local.policy,global=local.global_policy,children=local.children})\n",
                          text=True, capture_output=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    value = json.loads(json.loads(proc.stdout[proc.stdout.find('"'):].strip()))
    plan, baseline, _ = candidate_plan(value)
    # Helper constructs operation/binding target names for a candidate.
    for item in plan["resource_changes"]:
        after = item["change"]["after"]
        if "parent_id" in after:
            after["parent_id"] = after["parent_id"].replace("aiflux-project-validation", "aiflux-dev-unified")
        if "api_name" in after:
            after["api_name"] = "aiflux-dev-unified"
    plan["variables"] = {k: {"value": v} for k, v in {
        "demo_authorized": True, "acceptance_verified": False, "candidate_validation": False,
        "demo_expires_at": expiry, "rpm_limit": 60}.items()}
    return plan, value, baseline


def test_demo_guard_accepts_only_explicit_bounded_demo(demo):
    guard_demo_plan(*demo)
    assert '"project-demo:"' in demo[1]["policy"]
    assert "demo_expired" in demo[1]["policy"]
    assert "<retry" not in demo[1]["policy"]
    assert 'calls="60" renewal-period="60"' in demo[1]["policy"]


@pytest.mark.parametrize("mutation", ["acceptance", "candidate", "unauthorized", "expired", "long_expiry",
                                         "missing_expiry", "quota", "rpm", "pii", "global", "foreign", "delete"])
def test_demo_guard_rejects_expansion_and_forged_acceptance(demo, mutation):
    plan, value, baseline = deepcopy(demo)
    if mutation == "acceptance": plan["variables"]["acceptance_verified"]["value"] = True
    if mutation == "candidate": plan["variables"]["candidate_validation"]["value"] = True
    if mutation == "unauthorized": plan["variables"]["demo_authorized"]["value"] = False
    if mutation == "expired": plan["variables"]["demo_expires_at"]["value"] = "2020-01-01T00:00:00Z"
    if mutation == "long_expiry": plan["variables"]["demo_expires_at"]["value"] = "2099-01-01T00:00:00Z"
    if mutation == "missing_expiry": value["policy"] = value["policy"].replace("demo_expired", "removed")
    if mutation == "quota": value["policy"] = value["policy"].replace('calls="8"', 'calls="80"')
    if mutation == "rpm": value["policy"] = value["policy"].replace('calls="60"', 'calls="100"')
    if mutation == "pii": value["policy"] = value["policy"].replace('ignore-error="false"', 'ignore-error="true"')
    if mutation == "global": value["global"] = value["global"].replace('(false)', '(true)')
    if mutation == "foreign": plan["resource_changes"][0]["change"]["after"]["parent_id"] = "unrelated"
    if mutation == "delete": plan["resource_changes"][0]["change"]["actions"] = ["delete"]
    with pytest.raises(RepairBlocked):
        guard_demo_plan(plan, value, baseline)


def test_error_cors_is_exact_and_quota_mapping_does_not_reset_counter(demo):
    from xml.etree import ElementTree as ET
    root = ET.fromstring(demo[1]["policy"])
    errors = root.find("on-error")
    origins = errors.findall(".//set-header[@name='Access-Control-Allow-Origin']")
    assert len(origins) >= 6
    condition = origins[0].find("value").text
    assert '== "https://poc-ids-token-ex-customer.azurewebsites.net"' in condition
    assert '== "https://poc-ids-token-ex-admin.azurewebsites.net"' in condition
    assert "*" not in condition
    assert "bounded_call_quota_exceeded" in demo[1]["policy"]
    assert root.find(".//quota-by-key").get("calls") == "8"
    for response in errors.findall(".//return-response"):
        assert response[0].tag == "set-status"
        assert response.find("set-header[@name='Access-Control-Allow-Origin']") is not None
        assert response.find("set-header[@name='x-aiflux-failure-stage']") is not None


def test_policy_only_guard_accepts_owned_update_and_rejects_other_writes(demo):
    previous, rendered, baseline = deepcopy(demo)
    after = next(x["change"]["after"] for x in previous["resource_changes"] if x["address"] == "azapi_resource.project_policy[0]")
    update = {"applyable": True, "resource_changes": [{"address": "azapi_resource.project_policy[0]",
              "change": {"actions": ["update"], "before": deepcopy(after), "after": deepcopy(after)}}]}
    guard_policy_update(update, rendered, previous, baseline)
    for field in ("type", "parent_id", "name"):
        bad = deepcopy(update)
        bad["resource_changes"][0]["change"]["after"][field] = "unrelated"
        with pytest.raises(RepairBlocked):
            guard_policy_update(bad, rendered, previous, baseline)
    bad = deepcopy(update)
    bad["resource_changes"].append({"address": "unrelated", "change": {"actions": ["delete"]}})
    with pytest.raises(RepairBlocked):
        guard_policy_update(bad, rendered, previous, baseline)


def test_arm_serialization_comparison_does_not_ignore_changed_expression():
    assert policy_structure('<policies>\n <when condition="@(true)" />\n</policies>') == policy_structure('<policies><when condition="@(true)" /></policies>')
    assert policy_structure('<when condition="@(true)" />') != policy_structure('<when condition="@(false)" />')


def quota_case(demo):
    previous, rendered, baseline = deepcopy(demo)
    before = next(x["change"]["after"] for x in previous["resource_changes"]
                  if x["address"] == "azapi_resource.project_policy[0]")
    rendered["policy"] = rendered["policy"].replace('<quota-by-key calls="8"', '<quota-by-key calls="1000"')
    after = deepcopy(before)
    after["body"]["properties"]["value"] = rendered["policy"]
    plan = {"applyable": True, "variables": {**deepcopy(previous["variables"]), "daily_call_allowance": {"value": 1000}},
            "resource_changes": [{"address": "azapi_resource.project_policy[0]",
                                  "change": {"actions": ["update"], "before": before, "after": after}}]}
    return plan, rendered, previous, baseline


def test_authorized_quota_only_update_preserves_all_counter_attributes(demo):
    from xml.etree import ElementTree as ET
    from scripts.deployment.project_route_quota import guard_quota_update
    plan, rendered, previous, baseline = quota_case(demo)
    guard_quota_update(plan, rendered, previous, baseline)
    before = ET.fromstring(plan["resource_changes"][0]["change"]["before"]["body"]["properties"]["value"])
    after = ET.fromstring(rendered["policy"])
    for tag in ("rate-limit-by-key", "llm-token-limit", "quota-by-key"):
        old = dict(before.find(".//" + tag).attrib)
        new = dict(after.find(".//" + tag).attrib)
        if tag == "quota-by-key":
            assert old.pop("calls") == "8"
            assert new.pop("calls") == "1000"
        assert old == new
    assert "first-period-start" not in after.find(".//quota-by-key").attrib


@pytest.mark.parametrize("old,new", [
    ('project-demo:', 'project-demo-new:'),
    ('renewal-period="86400"', 'renewal-period="86401"'),
    ('calls="1000"', 'calls="0"'),
    ('calls="1000"', 'calls="1001"'),
    ('calls="60"', 'calls="61"'),
    ('token-quota="10000"', 'token-quota="10001"'),
    ('tokens-per-minute="1000"', 'tokens-per-minute="2000"'),
    ('threshold="1"', 'threshold="2"'),
    ('ignore-error="false"', 'ignore-error="true"'),
    ('"rpm:"', '"rpm-reset:"'),
    ('"tpm:"', '"tpm-reset:"'),
    ('renewal-period="86400"', 'renewal-period="86400" first-period-start="2026-10-26T00:00:00Z"'),
    ('https://poc-ids-token-ex-customer.azurewebsites.net', 'https://untrusted.invalid'),
])
def test_quota_update_rejects_other_policy_changes_even_when_render_matches(demo, old, new):
    from scripts.deployment.project_route_quota import guard_quota_update
    plan, rendered, previous, baseline = quota_case(demo)
    assert old in rendered["policy"]
    rendered["policy"] = rendered["policy"].replace(old, new)
    plan["resource_changes"][0]["change"]["after"]["body"]["properties"]["value"] = rendered["policy"]
    with pytest.raises(RepairBlocked):
        guard_quota_update(plan, rendered, previous, baseline)


@pytest.mark.parametrize("mutation", ["expiry", "acceptance", "global_write", "delete", "drift", "unknown"])
def test_quota_update_rejects_input_or_plan_expansion(demo, mutation):
    from scripts.deployment.project_route_quota import guard_quota_update
    plan, rendered, previous, baseline = quota_case(demo)
    change = plan["resource_changes"][0]["change"]
    if mutation == "expiry": plan["variables"]["demo_expires_at"]["value"] = "2099-01-01T00:00:00Z"
    if mutation == "acceptance": plan["variables"]["acceptance_verified"]["value"] = True
    if mutation == "global_write": plan["resource_changes"].append({"address": "azapi_resource.project_global_gate[0]", "change": {"actions": ["update"]}})
    if mutation == "delete": change["actions"] = ["delete", "create"]
    if mutation == "drift": change["before"]["body"]["properties"]["value"] = change["before"]["body"]["properties"]["value"].replace('calls="8"', 'calls="9"')
    if mutation == "unknown": change["after_unknown"] = {"body": True}
    with pytest.raises(RepairBlocked):
        guard_quota_update(plan, rendered, previous, baseline)


def test_quota_executor_cannot_invoke_destructive_workflow():
    import inspect
    from scripts.deployment.project_route_quota import QuotaRun
    source = inspect.getsource(QuotaRun.update)
    assert "self.cleanup(" not in source
    assert "self.run(" not in source
    assert 'self.tf("apply", "-no-color", "-input=false", str(saved))' in source