"""Actual Terraform render and synthetic mutation guards, never gateway traffic."""
from copy import deepcopy
import json
import subprocess

import pytest

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.finops_function_stage import sha
from scripts.deployment.poc_controls_guards import guard_policy, guard_protected, require_publisher
from scripts.deployment.poc_controls_preflight import ACTIONS, allowed_actions, selected_publisher


@pytest.fixture(scope="module")
def policies():
    args = [rt.TF, "-chdir=" + str(rt.ROOT / "infra/project-route"), "console", "-no-color",
            "-var=demo_authorized=true", "-var=persistent_poc_authorized=true",
            "-var=rpm_limit=60", "-var=tpm_limit=2048", "-var=completion_token_limit=1024",
            "-var=daily_call_allowance=1000", "-var=glm_enabled=true",
            "-var=allow_product_subscriptions=true", "-var=poc_publisher_permissions_verified=true",
            "-var=route_manifest_path=" + (rt.ROOT / "gateway/catalog/project-routes.json").as_posix()]
    result = []
    for enabled in (False, True):
        p = subprocess.run(args + ["-var=poc_controls_enabled=" + str(enabled).lower()],
                           input="jsonencode(local.policy)\n", env=rt.ENV, capture_output=True,
                           text=True, timeout=90)
        assert p.returncode == 0, "offline Terraform rendering failed"
        result.append(json.loads(json.loads(p.stdout[p.stdout.find('"'): ])))
    return result


def test_real_eleven_model_terraform_policy_exact_delta(policies):
    guard_policy(*policies)


@pytest.mark.parametrize("old,new", [
    ('context.Subscription == null', 'false'), ('context.Product == null', 'false'),
    ('context.Product.Id != "aiflux"', 'false'), ('"rpm:"', '"reset:"'),
    ('"tpm:"', '"reset:"'), ('renewal-period="60"', 'renewal-period="300"'),
    ('token-quota-period="Daily"', 'token-quota-period="Monthly"'),
    ('shield-prompt="true"', 'shield-prompt="false"'),
    ('pii_inspection_unavailable', 'pii_optional'), ('glm-5.3', 'unknown'),
    ('gpt-4o', 'unapproved-model'), ('modelMaximum = 1024;', 'modelMaximum = 9999;'),
    ('Bearer {{aiflux-glm-5-3-api-key}}', 'Bearer {{other-key}}'),
    ('timeout="45"', 'timeout="46"'),
    ('https://poc-ids-token-ex-customer.azurewebsites.net', 'https://untrusted.invalid'),
])
def test_unrelated_policy_mutation_is_rejected(policies, old, new):
    assert old in policies[1]
    with pytest.raises(RuntimeError, match="unapproved_policy_delta"):
        guard_policy(policies[0], policies[1].replace(old, new))


def test_publisher_is_selected_identity_not_any_attached_identity():
    identity = {"principalId": "system", "userAssignedIdentities": {
        "a": {"clientId": "client-a", "principalId": "principal-a"}}}
    assert selected_publisher(identity, "client-a") == "principal-a"
    assert selected_publisher(identity, None) == "system"
    with pytest.raises(RuntimeError):
        selected_publisher(identity, "not-attached")


def test_permission_wildcards_and_exclusions():
    assert all(allowed_actions([{"actions": ["Microsoft.ApiManagement/service/*"]}]).values())
    assert not all(allowed_actions([{"actions": ["*"], "notActions": [ACTIONS[1]]}]).values())
    assert not any(allowed_actions([{"actions": ["Microsoft.ApiManagement/service/subscriptions/*"]}]).values())


def test_preflight_false_or_other_principal_cannot_unlock_release():
    with pytest.raises(RuntimeError):
        require_publisher({"publisher_fragment_permission_verified": False})
    with pytest.raises(RuntimeError):
        require_publisher({"publisher_fragment_permission_verified": True,
                           "selected_publisher_principal_id": "selected",
                           "publisher_permissions": [{"principal_id": "other", "fragment_actions":
                                                       {a: True for a in ACTIONS}}]})


@pytest.fixture
def protected_release():
    settings = {name: {"keep": "synthetic", "jwt": "synthetic-reference"} for name in
                ("api", "admin", "customer", "ingestion")}
    baseline = {"runtime": {"sites": {name: {"image": "old", "protected": {"alwaysOn": True}}
                                       for name in settings}},
                "settings_hashes": {name: sha(value) for name, value in settings.items()},
                "state_network": {"defaultAction": "Deny"}, "apim": {"global": "unchanged"}}
    after = deepcopy(baseline)
    images = {name: "pocidstokenexacr.azurecr.io/aiflux-" + name + "@sha256:" + "a" * 64
              for name in ("api", "admin")}
    for name in images:
        after["runtime"]["sites"][name]["image"] = "DOCKER|" + images[name]
    changed = deepcopy(settings)
    changed["api"].update({"AIFLUX_GATEWAY_CONTROLS_POC_ENABLED": "true",
                          "AIFLUX_GATEWAY_CONTROLS_V2_ENABLED": "false",
                          "AIFLUX_GATEWAY_SETTINGS_SCOPES": '["dev-unified"]'})
    after["settings_hashes"] = {name: sha(value) for name, value in changed.items()}
    return baseline, after, settings, changed, images


def test_exact_image_and_flags_delta_only(protected_release):
    guard_protected(*protected_release)


@pytest.mark.parametrize("mutation", ["customer", "ingestion", "alwaysOn", "network", "global",
                                     "jwt", "timer", "extra_flag"])
def test_complete_protected_baseline_has_no_mutation_exemptions(protected_release, mutation):
    before, after, settings, changed, images = deepcopy(protected_release)
    if mutation in ("customer", "ingestion"):
        after["runtime"]["sites"][mutation]["image"] = "new"
    elif mutation == "alwaysOn":
        after["runtime"]["sites"]["api"]["protected"]["alwaysOn"] = False
    elif mutation == "network":
        after["state_network"]["defaultAction"] = "Allow"
    elif mutation == "global":
        after["apim"]["global"] = "changed"
    else:
        changed["ingestion" if mutation == "timer" else "api"][mutation] = "changed"
        after["settings_hashes"] = {name: sha(value) for name, value in changed.items()}
    with pytest.raises(RuntimeError):
        guard_protected(before, after, settings, changed, images)