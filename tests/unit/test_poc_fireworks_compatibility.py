"""Real Terraform renders and security mutation checks, without ARM or state writes."""
import json
import subprocess
import xml.etree.ElementTree as ET

import pytest

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.poc_controls_guards import guard_policy

MODELS = {"gpt-5.6-luna", "gpt-6.1-sol", "gpt-5.4-mini", "gpt-4o", "DeepSeek-V4-Flash",
          "DeepSeek-V4-Pro", "Kimi-K2.7-Code", "grok-4.3", "grok-4-20-reasoning",
          "grok-4-1-fast-reasoning", "FW-GLM-5.3", "FW-MiniMax-M3", "glm-5.3"}


def render(**overrides):
    values = {"poc_controls_enabled": True, "poc_publisher_permissions_verified": True,
              "poc_settings_bootstrap_enabled": True, **overrides}
    args = [rt.TF, "-chdir=" + str(rt.ROOT / "infra/project-route"), "console", "-no-color",
            "-var-file=" + str(rt.HOME / "poc-fragment-bootstrap-20261028/inputs.tfvars.json")]
    args += ["-var=" + key + "=" + (json.dumps(value) if not isinstance(value, str) else value)
             for key, value in values.items()]
    result = subprocess.run(args, input="jsonencode({compatible=local.fireworks_profile_compatible,policy=local.policy,backends=local.route_backends,aliases=local.all_aliases})\n",
                            capture_output=True, text=True, env=rt.ENV, timeout=120)
    if result.returncode:
        return None
    return json.loads(json.loads(result.stdout[result.stdout.find('"'):].strip()))


def test_actual_thirteen_model_activation_is_only_reviewed_policy_delta():
    old, new = render(poc_controls_enabled=False), render()
    assert old is not None and new is not None
    assert old["compatible"] and new["compatible"]
    assert set(new["aliases"]) == MODELS
    assert new["backends"] == old["backends"]
    assert {k for k, v in new["backends"].items() if v == "aiflux-project-fireworks"} == {"FW-GLM-5.3", "FW-MiniMax-M3"}
    guard_policy(old["policy"], new["policy"])
    tree = ET.fromstring(new["policy"])
    assert len(tree.findall(".//include-fragment")) == 1
    assert len(tree.findall(".//forward-request")) == 1
    assert len(tree.findall(".//llm-content-safety")) == 3
    assert not tree.findall(".//retry")
    assert "subscription_controls_unpublished" not in new["policy"]
    assert 'context.Subscription == null || context.Product == null || context.Product.Id != "aiflux"' in new["policy"]
    assert 'Bearer {{aiflux-glm-5-3-api-key}}' in new["policy"]
    assert 'first-period-start' not in new["policy"]


@pytest.mark.parametrize("overrides", [
    {"poc_publisher_permissions_verified": False}, {"poc_settings_bootstrap_enabled": False},
    {"persistent_poc_authorized": False}, {"allow_product_subscriptions": False},
    {"glm_enabled": False}, {"candidate_validation": True}, {"acceptance_verified": True},
    {"daily_call_allowance": 1001}, {"backend_retries": 1}, {"safety_threshold": 0},
])
def test_unsafe_profiles_never_satisfy_compatibility(overrides):
    value = render(**overrides)
    assert value is None or value["compatible"] is False


@pytest.mark.parametrize("defect", ["partial", "provider", "version", "upstream"])
def test_route_contract_mutation_is_rejected(tmp_path, defect):
    data = json.loads((rt.ROOT / "gateway/catalog/fireworks-candidate-routes.json").read_text())
    if defect == "partial":
        data["routes"].pop("gpt-4o")
    else:
        data["routes"]["FW-GLM-5.3"][{"provider": "provider", "version": "version", "upstream": "upstream_url"}[defect]] = "foreign"
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(data))
    value = render(route_manifest_path=path.as_posix())
    assert value is None or value["compatible"] is False