"""Real offline Terraform render and adversarial exact-delta release contracts."""
from copy import deepcopy
import json
import subprocess
import xml.etree.ElementTree as ET

import pytest

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.apim_route_repair import APIM, RepairBlocked, SUBSCRIBER
from scripts.deployment.project_route_product_access import (
    CONTOSO, POLICY, PRODUCT_GATE, expected_policy, guard_product_update,
)
from scripts.deployment.project_route_persistent import APPROVED


@pytest.fixture(scope="module")
def product_plan():
    def render(optin):
        args = [rt.TF, "-chdir=" + str(rt.ROOT / "infra/project-route"), "console", "-no-color",
                "-var=demo_authorized=true", "-var=persistent_poc_authorized=true",
                "-var=rpm_limit=60", "-var=tpm_limit=2048", "-var=completion_token_limit=1024",
                "-var=daily_call_allowance=1000", "-var=glm_enabled=true",
                "-var=route_manifest_path=" + (rt.ROOT / "gateway/catalog/project-routes.json").as_posix(),
                "-var=allow_product_subscriptions=" + str(optin).lower()]
        p = subprocess.run(args, input="jsonencode(local.policy)\n", env=rt.ENV,
                           capture_output=True, text=True, timeout=90)
        assert p.returncode == 0, p.stderr
        return json.loads(json.loads(p.stdout[p.stdout.find('"'):]))
    before, after = render(False), render(True)
    previous = {**APPROVED, "glm_enabled": True, "glm_credential_storage": "apim-internal",
                "excluded_routes": [], "allow_product_subscriptions": False}
    obj = {"type": "Microsoft.ApiManagement/service/apis/policies@2024-05-01",
           "parent_id": APIM + "/apis/aiflux-dev-unified", "name": "policy", "output": {},
           "body": {"properties": {"format": "rawxml", "value": before}}}
    new = deepcopy(obj)
    new["body"]["properties"]["value"] = after
    plan = {"applyable": True, "variables": {k: {"value": v} for k, v in
            {**previous, "allow_product_subscriptions": True}.items()},
            "resource_changes": [{"address": POLICY, "change": {
                "actions": ["update"], "before": obj, "after": new}}]}
    return plan, before, previous


def test_real_glm_inclusive_render_changes_only_eligibility(product_plan):
    policy = guard_product_update(*product_plan)
    tree = ET.fromstring(policy)
    assert tree.find("./inbound/choose/when").get("condition") == PRODUCT_GATE
    assert "context.Subscription.Id !=" not in policy
    assert "Bearer {{aiflux-glm-5-3-api-key}}" in policy


@pytest.mark.parametrize("sid", [SUBSCRIBER, CONTOSO, "future-admin-created-product-subscription"])
def test_product_expression_accepts_any_authenticated_product_subscription(product_plan, sid):
    # Evaluate the actual emitted C# eligibility expression with synthetic APIM
    # contexts. APIM performs key/state authentication BEFORE policy execution.
    tree = ET.fromstring(guard_product_update(*product_plan))
    expression = tree.find("./inbound/choose/when").get("condition")
    expression = expression[2:-1].replace("context.Subscription == null", str(sid is None))
    expression = expression.replace("context.Product == null", "False")
    expression = expression.replace('context.Product.Id != "aiflux"', "False").replace("||", "or")
    assert eval(expression, {"__builtins__": {}}, {}) is False


@pytest.mark.parametrize("has_key,state,product", [
    (False, "active", "aiflux"), (True, "suspended", "aiflux"),
    (True, "cancelled", "aiflux"), (True, "submitted", "aiflux"),
    (True, "active", None), (True, "active", "other"),
])
def test_missing_invalid_or_ineligible_context_fails_closed(product_plan, has_key, state, product):
    tree = ET.fromstring(guard_product_update(*product_plan))
    expression = tree.find("./inbound/choose/when").get("condition")
    # Suspended/revoked/invalid keys have no authenticated APIM subscription;
    # this synthetic contract is not represented as a live suspension test.
    authenticated = has_key and state == "active"
    expression = expression[2:-1].replace("context.Subscription == null", str(not authenticated))
    expression = expression.replace("context.Product == null", str(product is None))
    expression = expression.replace('context.Product.Id != "aiflux"', str(product != "aiflux")).replace("||", "or")
    assert eval(expression, {"__builtins__": {}}, {}) is True


@pytest.mark.parametrize("old,new", [
    ('context.Subscription == null', 'false'), ('context.Product == null', 'false'),
    ('context.Product.Id != "aiflux"', 'false'), ('calls="60"', 'calls="600"'),
    ('calls="1000"', 'calls="10000"'), ('renewal-period="86400"', 'renewal-period="1"'),
    ('tokens-per-minute="2048"', 'tokens-per-minute="2049"'),
    ('token-quota="10000"', 'token-quota="10001"'), ('"tpm:"', '"reset:"'),
    ('"rpm:"', '"reset:"'), ('"project-demo:"', '"new-epoch:"'),
    ('threshold="1"', 'threshold="7"'), ('shield-prompt="true"', 'shield-prompt="false"'),
    ('ignore-error="false"', 'ignore-error="true"'), ('pii_inspection_unavailable', 'pii_optional'),
    ('gpt-4o', 'unapproved-model'), ('glm-5.3', 'glm-unknown'),
    ('modelMaximum = 1024;', 'modelMaximum = 99999;'),
    ('https://poc-ids-token-ex-customer.azurewebsites.net', 'https://untrusted.invalid'),
    ('Bearer {{aiflux-glm-5-3-api-key}}', 'Bearer {{other-key}}'),
    ('timeout="45"', 'timeout="46"'),
])
def test_every_other_policy_change_is_rejected(product_plan, old, new):
    plan, before, prior = deepcopy(product_plan)
    body = plan["resource_changes"][0]["change"]["after"]["body"]["properties"]
    assert old in body["value"]
    body["value"] = body["value"].replace(old, new)
    with pytest.raises(RepairBlocked):
        guard_product_update(plan, before, prior)


@pytest.mark.parametrize("mutation", ["global", "product", "backend", "network", "fragment", "namedvalue",
                                    "create", "delete", "replace", "unknown", "target", "attribute", "input"])
def test_no_other_resource_unknown_or_input_change(product_plan, mutation):
    plan, before, prior = deepcopy(product_plan)
    change = plan["resource_changes"][0]["change"]
    if mutation in {"global", "product", "backend", "network", "fragment"}:
        plan["resource_changes"].append({"address": mutation, "change": {"actions": ["update"]}})
    elif mutation == "namedvalue":
        plan["resource_changes"].append({"address": "data.secret", "change": {"actions": ["read"],
            "after": {"type": "Microsoft.ApiManagement/service/namedValues@2024-05-01"}}})
    elif mutation in {"create", "delete", "replace"}:
        change["actions"] = [mutation] if mutation != "replace" else ["delete", "create"]
    elif mutation == "unknown":
        change["after_unknown"] = {"body": True}
    elif mutation == "target":
        change["after"]["parent_id"] += "-other"
    elif mutation == "attribute":
        change["after"]["schema_validation_enabled"] = False
    else:
        plan["variables"]["candidate_validation"] = {"value": True}
    with pytest.raises(RepairBlocked):
        guard_product_update(plan, before, prior)


def test_predecessor_must_have_exact_original_gate(product_plan):
    before = product_plan[1]
    with pytest.raises(RepairBlocked):
        expected_policy(before.replace(SUBSCRIBER, CONTOSO))
    with pytest.raises(RepairBlocked):
        expected_policy(expected_policy(before))