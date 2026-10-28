"""Render the actual Terraform candidate; these are NOT Azure acceptance tests."""

import json
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from scripts.deployment.apim_route_repair import (
    ACCOUNT, APIM, OPENAI_ENDPOINT, ORIGINS, PROJECT, SUBSCRIBER,
    RepairBlocked, guard_candidate_plan,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def rendered():
    executable = shutil.which("terraform")
    if not executable:
        pytest.skip("Terraform is needed for actual template rendering")
    env = os.environ.copy()
    config = ROOT / ".deployment/terraform.rc"
    if config.is_file():
        env.setdefault("TF_CLI_CONFIG_FILE", str(config))
    proc = subprocess.run(
        [executable, "-chdir=" + str(ROOT / "infra/project-route"), "console", "-no-color"],
        input="jsonencode({policy=local.policy, global=local.global_policy, children=local.children, project=local.project})\n",
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    value = proc.stdout[proc.stdout.find('"'):].strip()
    return json.loads(json.loads(value))


def test_actual_render_is_exact_project_not_superseded_account(rendered):
    assert rendered["project"] == PROJECT
    assert rendered["children"]["backend"]["body"]["properties"]["url"] == OPENAI_ENDPOINT + "openai/v1"
    assert "IDS-AI-Token" not in rendered["policy"]
    assert "gpt-5-mini" not in rendered["policy"]
    lists = []
    for node in ET.fromstring(rendered["policy"]).findall(".//set-body"):
        try:
            body = json.loads(node.text or "")
        except ValueError:
            continue
        if body.get("object") == "list":
            lists.append([item["id"] for item in body["data"]])
    assert lists == [["gpt-5.6-luna"]]


def test_actual_render_keeps_cors_before_base_and_exact_subscription(rendered):
    root = ET.fromstring(rendered["policy"])
    assert root.find("inbound")[0].tag == "cors"
    assert [n.text for n in root.findall("./inbound/cors/allowed-origins/origin")] == ORIGINS
    condition = root.find("./inbound/choose/when").get("condition")
    assert SUBSCRIBER in condition and 'context.Product.Id != "aiflux"' in condition
    assert 'context.Subscription == null' in condition


def test_actual_render_has_one_forward_zero_retries_and_bounded_token_quota(rendered):
    root = ET.fromstring(rendered["policy"])
    assert not root.findall(".//retry")
    assert [node.tag for node in root.find("backend")] == ["forward-request"]
    assert root.find(".//rate-limit-by-key").get("calls") == "1"
    limit = root.find(".//llm-token-limit")
    assert (limit.get("tokens-per-minute"), limit.get("token-quota"), limit.get("token-quota-period")) == ("1000", "10000", "Daily")
    assert limit.get("estimate-prompt-tokens") == "true"
    assert "max_completion_tokens up to 32" in rendered["policy"]


def test_actual_render_preserves_original_redacted_output_safety_and_pii(rendered):
    root = ET.fromstring(rendered["policy"])
    inbound = root.findall("./inbound/choose/when/llm-content-safety")
    outbound = root.findall("./outbound/choose/when/llm-content-safety")
    assert len(inbound) == 2 and len(outbound) == 1
    assert all(item.get("shield-prompt") == "true" for item in inbound)
    assert all(cat.get("threshold") == "1" for cat in root.findall(".//category"))
    assert len(root.findall(".//send-request")) == 5
    assert all(node.get("ignore-error") == "false" for node in root.findall(".//send-request"))
    assert "pii_inspection_unavailable" in rendered["policy"]
    for url in root.findall(".//send-request/set-url"):
        assert url.text.startswith("https://poc-ids-token-ex-foundry.cognitiveservices.azure.com/")
    assert ACCOUNT.endswith("/poc-ids-token-ex-foundry")


def test_explicit_operations_do_not_depend_on_missing_imported_schema(rendered):
    root = ET.fromstring(rendered["policy"])
    assert not root.findall(".//validate-content")
    policy = rendered["policy"]
    assert "System.Text.Encoding.UTF8.GetByteCount(raw) > 16384" in policy
    assert "JObject.Parse(raw);" in policy
    assert "catch { return true; }" in policy
    assert policy.index("JObject.Parse(raw);") < policy.index('name="aiflux-request-json"')
    assert "unsupported_request_shape" in policy
    assert 'messages.Count > 25' in policy
    assert "totalCharacters > 8000" in policy
    # The expose-header allowlist may name it, but ordinary non-demo policies
    # must not emit the bounded candidate/demo diagnostic itself.
    assert not root.findall(".//set-header[@name='x-aiflux-failure-stage']")


def test_actual_global_render_opens_only_adapter_and_legacy_remains_false(rendered):
    root = ET.fromstring(rendered["global"])
    gate = root.find("./inbound/choose/when").get("condition")
    assert '(false)' in gate and '(true)' in gate
    assert '/dev/llm/v1/chat/completions' in gate
    # The legacy paths are still behind the literal false expression.
    assert gate.index('(false)') < gate.index('/dev/v1/models') < gate.index('(true)')


def test_runtime_defaults_pin_correct_project():
    from aiflux.config import Settings
    settings = Settings()
    assert settings.foundry_project_resource_id == PROJECT
    assert settings.foundry_project_endpoint.endswith('/api/projects/poc-ids-token-ex-foundry-project')


@pytest.fixture(scope="module")
def candidate_rendered():
    env = os.environ.copy()
    env["TF_CLI_CONFIG_FILE"] = str(ROOT / ".deployment/terraform.rc")
    p = subprocess.run(
        ["terraform", "-chdir=" + str(ROOT / "infra/project-route"), "console", "-no-color", "-var=candidate_validation=true"],
        input="jsonencode({policy=local.policy,global=local.global_policy,children=local.children})\n",
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(json.loads(p.stdout[p.stdout.find('"'):].strip()))


def test_candidate_keeps_final_closed_and_has_no_double_slashes(candidate_rendered):
    value = candidate_rendered
    assert value["children"]["api"]["name"] == "aiflux-project-validation"
    assert value["children"]["api"]["body"]["properties"]["path"] == "dev/llm/validate/v1"
    gate = ET.fromstring(value["global"]).find("./inbound/choose/when").get("condition")
    assert "/dev/llm/validate/v1/chat/completions" in gate
    assert "/dev/llm/v1/" not in gate and "//dev/" not in gate
    assert "(false)" in gate and "(true)" in gate
    root = ET.fromstring(value["policy"])
    quota = root.find(".//quota-by-key")
    assert quota.get("calls") == "8" and quota.get("renewal-period") == "86400"
    assert SUBSCRIBER in value["policy"]
    assert len(root.findall(".//llm-content-safety")) == 3
    assert all(c.get("threshold") == "1" for c in root.findall(".//category"))


@pytest.mark.parametrize("fixture", ["rendered", "candidate_rendered"])
def test_backend_single_policy_preserves_typed_attempt_for_outbound(request, fixture):
    policy = request.getfixturevalue(fixture)["policy"]
    root = ET.fromstring(policy)
    assert [node.tag for node in root.find("backend")] == ["forward-request"]
    assert not root.findall(".//retry")
    attempts = root.findall(".//set-variable[@name='aiflux-backend-attempt']")
    assert len(attempts) == 1
    assert root.find("inbound")[-1] is attempts[0]
    assert attempts[0].get("value") == "@(1)"
    assert '(int)context.Variables["aiflux-backend-attempt"]' in policy


def candidate_plan(value):
    api = APIM + "/apis/aiflux-project-validation"
    objects = {}
    for key, item in value["children"].items():
        objects[f'azapi_resource.project_child["{key}"]'] = deepcopy(item)
    for name, method, path in (("models", "GET", "/models"), ("chat", "POST", "/chat/completions")):
        objects[f'azapi_resource.project_operation["{name}"]'] = dict(
            type="Microsoft.ApiManagement/service/apis/operations@2024-05-01", parent_id=api,
            name=name, body={"properties": {"displayName": name, "method": method, "urlTemplate": path}})
    objects["azurerm_api_management_product_api.project_binding[0]"] = dict(
        api_management_name="poc-ids-token-ex-apim", resource_group_name="IDS-TOKEN-EXCHANGE-POC",
        product_id="aiflux", api_name="aiflux-project-validation")
    objects["azapi_resource.project_policy[0]"] = dict(
        type="Microsoft.ApiManagement/service/apis/policies@2024-05-01", parent_id=api,
        name="policy", body={"properties": {"format": "rawxml", "value": value["policy"]}})
    global_obj = dict(type="Microsoft.ApiManagement/service/policies@2024-05-01", parent_id=APIM,
                      name="policy", body={"properties": {"format": "rawxml", "value": value["global"]}})
    baseline = value["global"].replace("(true)", "(false)").replace("/dev/llm/validate/v1/", "/dev/llm/v1/")
    before = deepcopy(global_obj)
    before["body"]["properties"]["value"] = baseline
    objects["azapi_resource.project_global_gate[0]"] = global_obj
    plan = {"applyable": True, "resource_changes": [
        {"address": address, "type": "azurerm_api_management_product_api" if address.startswith("azurerm_") else "azapi_resource", "change": {
            "actions": ["update"] if address.endswith("global_gate[0]") else ["create"],
            "before": before if address.endswith("global_gate[0]") else None,
            "after": obj, "after_unknown": {"id": True, "output": True}}}
        for address, obj in objects.items()]}
    from datetime import UTC, datetime
    ready = {"checked_at": datetime.now(UTC).isoformat(), "phase": "restricted_candidate",
             "ready_for_scoped_planning": True, "configuration_authorized": True, "blockers": []}
    return plan, baseline, ready


def test_candidate_exact_saved_plan_guard(candidate_rendered):
    plan, baseline, ready = candidate_plan(candidate_rendered)
    guard_candidate_plan(plan, candidate_rendered, baseline, ready)


@pytest.mark.parametrize("mutation", ["missing", "delete", "foreign", "unknown", "final", "legacy", "baseline", "duplicate", "unready"])
def test_candidate_guard_rejects_unrelated_or_incomplete_changes(candidate_rendered, mutation):
    plan, baseline, ready = candidate_plan(candidate_rendered)
    value = deepcopy(candidate_rendered)
    item = plan["resource_changes"][0]
    if mutation == "missing": plan["resource_changes"].pop()
    if mutation == "delete": item["change"]["actions"] = ["delete"]
    if mutation == "foreign": item["change"]["after"]["parent_id"] = ACCOUNT
    if mutation == "unknown": item["change"]["after_unknown"]["body"] = True
    if mutation == "final": value["global"] = value["global"].replace("/dev/llm/validate/v1/", "/dev/llm/v1/")
    if mutation == "legacy": value["global"] = value["global"].replace("(false)", "(true)")
    if mutation == "baseline": baseline = baseline.replace("(false)", "(true)", 1)
    if mutation == "duplicate": plan["resource_changes"].append(deepcopy(item))
    if mutation == "unready": ready["configuration_authorized"] = False
    with pytest.raises(RepairBlocked):
        guard_candidate_plan(plan, value, baseline, ready)


def render_with_variables(variables):
    env = os.environ.copy()
    env["TF_CLI_CONFIG_FILE"] = str(ROOT / ".deployment/terraform.rc")
    return subprocess.run(
        ["terraform", "-chdir=" + str(ROOT / "infra/project-route"), "console", "-no-color",
         *[f"-var={key}={json.dumps(value)}" for key, value in variables.items()]],
        input="jsonencode({policy=local.policy,enabled=var.enabled,acceptance=var.acceptance_verified,retries=var.backend_retries})\n",
        capture_output=True, text=True, env=env, timeout=120,
    )


def test_custom_limits_render_consistently_without_counter_reset(rendered):
    proc = render_with_variables({"rpm_limit": 2, "tpm_limit": 500, "daily_token_quota": 2000,
                                  "completion_token_limit": 16})
    assert proc.returncode == 0, proc.stderr
    value = json.loads(json.loads(proc.stdout[proc.stdout.find('"'):].strip()))
    assert value["enabled"] is False and value["acceptance"] is False
    root = ET.fromstring(value["policy"])
    original = ET.fromstring(rendered["policy"])
    rate = root.find(".//rate-limit-by-key")
    assert (rate.get("calls"), rate.get("renewal-period")) == ("2", "60")
    token = root.find(".//llm-token-limit")
    assert (token.get("tokens-per-minute"), token.get("token-quota"), token.get("token-quota-period")) == ("500", "2000", "Daily")
    for tag in ("rate-limit-by-key", "llm-token-limit"):
        assert root.find(f".//{tag}").get("counter-key") == original.find(f".//{tag}").get("counter-key")
    assert "modelMaximum = 16;" in value["policy"]
    assert "max_completion_tokens up to 16" in value["policy"]
    assert not root.findall(".//retry")
    assert len(root.findall(".//llm-content-safety")) == 3


@pytest.mark.parametrize("variables", [
    {"rpm_limit": 0}, {"rpm_limit": -1}, {"rpm_limit": 1.5},
    {"rate_limit_window_seconds": 0}, {"rate_limit_window_seconds": 61},
    {"rate_limit_window_seconds": 301},
    {"tpm_limit": 0}, {"tpm_limit": 31}, {"tpm_limit": 1000.5},
    {"daily_token_quota": 0}, {"daily_token_quota": 999}, {"daily_token_quota": 10000.5},
    {"completion_token_limit": 0}, {"completion_token_limit": 33}, {"completion_token_limit": 2.5},
    {"safety_threshold": 8},
])
def test_invalid_configuration_fails_closed(variables):
    # Retry validation is exercised by the real mock plan in defaults.tftest.hcl.
    # Terraform console may return exit0 with a validation diagnostic for an
    # input not used by local.policy; it is not a deployment-readiness command.
    proc = render_with_variables(variables)
    assert proc.returncode != 0
    assert "Invalid value for variable" in proc.stderr


def test_rate_limit_is_inbound_before_safety_without_deferred_increment(rendered, candidate_rendered):
    for value in (rendered, candidate_rendered):
        root = ET.fromstring(value["policy"])
        rate = root.find(".//rate-limit-by-key")
        assert "increment-condition" not in rate.attrib
        assert "increment-count" not in rate.attrib
        assert rate.get("remaining-calls-header-name") == "x-aiflux-rpm-remaining"
        assert value["policy"].index("<rate-limit-by-key") < value["policy"].index("<llm-content-safety")
        # GET returns before counters; CORS is first and no OPTIONS operation
        # reaches inference. Malformed/unsupported POSTs are rejected first.
        assert value["policy"].index('context.Request.Method == "GET"') < value["policy"].index("<rate-limit-by-key")
        assert value["policy"].index("unsupported_request_shape") < value["policy"].index("<rate-limit-by-key")
    for tag in ("rate-limit-by-key", "llm-token-limit"):
        a = ET.fromstring(rendered["policy"]).find(f".//{tag}")
        b = ET.fromstring(candidate_rendered["policy"]).find(f".//{tag}")
        assert a.get("counter-key") == b.get("counter-key")


@pytest.mark.parametrize("old,new", [
    ('calls="1" renewal-period="60"', 'calls="2" renewal-period="60"'),
    ('renewal-period="60"', 'renewal-period="61"'),
    ('tokens-per-minute="1000"', 'tokens-per-minute="1001"'),
    ('token-quota="10000"', 'token-quota="10001"'),
    ('token-quota-period="Daily"', 'token-quota-period="Monthly"'),
    ('estimate-prompt-tokens="true"', 'estimate-prompt-tokens="false"'),
    ('threshold="1"', 'threshold="7"'),
    ('shield-prompt="true"', 'shield-prompt="false"'),
    ('ignore-error="false"', 'ignore-error="true"'),
    ('<rate-limit-by-key ', '<rate-limit-by-key increment-condition="@(true)" '),
    ('"rpm:"', '"rpm:release-id:"'),
    ('project-validation:', 'project-validation:new-release:'),
])
def test_even_matching_saved_plan_cannot_expand_or_reset_candidate_limits(candidate_rendered, old, new):
    value = deepcopy(candidate_rendered)
    assert old in value["policy"]
    value["policy"] = value["policy"].replace(old, new)
    plan, baseline, ready = candidate_plan(value)
    with pytest.raises(RepairBlocked):
        guard_candidate_plan(plan, value, baseline, ready)