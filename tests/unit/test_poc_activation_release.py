"""Synthetic mutation tests plus actual complete current thirteen-model render."""
from copy import deepcopy
import json
import subprocess
import xml.etree.ElementTree as ET

import pytest
from scripts.deployment import poc_activation_release as r


def test_curated_production_sources_include_declared_pricing_package_data():
    sources = set(r.prep.api_sources())
    pricing = set((r.rt.ROOT / "services/control-plane/src/aiflux/pricing").glob("*.json"))
    assert pricing and pricing <= sources
    assert r.rt.ROOT / "services/control-plane/migrations/versions/0003_portal_users.py" not in sources


@pytest.fixture
def runtime_plan():
    images = {k: r.portals.HOST + "/aiflux-" + k + "@sha256:" + "a" * 64 for k in ("api", "admin")}
    resources = []
    for address, kind in r.RUNTIME.items():
        before = {"app_settings": {"keep": "synthetic"}, "identity": [{"keep": True}], "enabled": True,
                  "site_config": [{"always_on": True, "application_stack": [{"docker_image_name": "aiflux-" + kind + "@sha256:" + r.PINS[kind],
                    "docker_registry_url": "https://" + r.portals.HOST}]}]}
        after = deepcopy(before)
        after["site_config"][0]["application_stack"][0]["docker_image_name"] = images[kind].split("/", 1)[1]
        if kind == "api":
            after["app_settings"].update(r.FLAGS)
        resources.append({"address": address, "mode": "managed", "change": {"actions": ["update"], "before": before, "after": after, "after_unknown": {}}})
    return {"applyable": True, "resource_changes": resources, "checks": [{"status": "pass"}]}, images


def test_exact_runtime_stage(runtime_plan):
    r.guard_runtime(*runtime_plan)


def test_runtime_variables_preserve_current_customer_and_separate_api_admin_pins():
    images = {k: r.portals.HOST + "/aiflux-" + k + "@sha256:" + "a" * 64 for k in ("api", "admin")}
    current = {"sites": {k: {"image": "DOCKER|" + r.portals.HOST + "/aiflux-" + k + "@sha256:" + v}
                          for k, v in r.PINS.items()}}
    variables = r.runtime_variables(images, current)
    for kind in ("api", "admin"):
        assert variables["apps"][kind]["image"] == images[kind].split("/", 1)[1]
    assert variables["apps"]["customer"]["image"] == current["sites"]["customer"]["image"].removeprefix("DOCKER|" + r.portals.HOST + "/")
    with pytest.raises(RuntimeError, match="exact_runtime_variable_images"):
        r.runtime_variables({"admin": images["admin"]}, current)


def test_failed_preplan_directory_is_not_reused():
    folder, _, _ = r.location("runtime")
    assert folder.name == "runtime-successor01"


def test_fragment_metadata_agrees_with_existing_runtime_publisher():
    # Local desired metadata follows the proven authorized MI publication,
    # avoiding a fragment metadata write during the policy-only activation.
    from aiflux.apim import ApimClient
    import inspect
    description = "Runtime-owned bounded settings; invariant inspection and routing remain Terraform-owned."
    assert description in inspect.getsource(ApimClient.put_settings_fragment)
    source = (r.rt.ROOT / "infra/project-route/poc-controls.tf").read_text(encoding="utf-8")
    assert 'description = "' + description + '"' in source
    assert "ignore_changes = [body.properties.value]" in source
    assert "prevent_destroy = true" in source


@pytest.mark.parametrize("mutation", ["extra_setting", "missing_flag", "v2", "customer", "recreate_fragment", "network", "always_on", "identity", "unknown", "delete", "wrong_predecessor", "wrong_image"])
def test_runtime_rejects_every_nonapproved_mutation(runtime_plan, mutation):
    plan, images = deepcopy(runtime_plan)
    change = plan["resource_changes"][0]["change"]
    if mutation == "extra_setting":
        change["after"]["app_settings"]["other"] = "changed"
    elif mutation == "missing_flag":
        del change["after"]["app_settings"]["AIFLUX_GATEWAY_CONTROLS_POC_ENABLED"]
    elif mutation == "v2":
        change["after"]["app_settings"]["AIFLUX_GATEWAY_CONTROLS_V2_ENABLED"] = "true"
    elif mutation in ("customer", "recreate_fragment"):
        plan["resource_changes"].append({"address": 'azurerm_linux_web_app.main["customer"]' if mutation == "customer" else "azapi_resource.poc_settings[0]",
            "mode": "managed", "change": {"actions": ["create"]}})
    elif mutation == "network":
        change["after"]["public_network_access_enabled"] = True
    elif mutation == "always_on":
        change["after"]["site_config"][0]["always_on"] = False
    elif mutation == "identity":
        change["after"]["identity"] = []
    elif mutation == "unknown":
        change["after_unknown"] = {"app_settings": True}
    elif mutation == "delete":
        change["actions"] = ["delete", "create"]
    elif mutation == "wrong_predecessor":
        change["before"]["site_config"][0]["application_stack"][0]["docker_image_name"] = "other"
    else:
        images["api"] = images["admin"]
    with pytest.raises(RuntimeError):
        r.guard_runtime(plan, images)


@pytest.fixture(scope="module")
def thirteen_policies():
    args = [r.rt.TF, "-chdir=" + str(r.rt.ROOT / "infra/project-route"), "console", "-no-color",
        "-var=demo_authorized=true", "-var=persistent_poc_authorized=true", "-var=allow_product_subscriptions=true",
        "-var=rpm_limit=60", "-var=tpm_limit=2048", "-var=completion_token_limit=1024", "-var=daily_call_allowance=1000",
        "-var=glm_enabled=true", "-var=poc_settings_bootstrap_enabled=true", "-var=poc_publisher_permissions_verified=true",
        "-var=route_manifest_path=" + (r.rt.ROOT / "gateway/catalog/fireworks-candidate-routes.json").as_posix()]
    values = []
    for flag in ("false", "true"):
        child = subprocess.run(args + ["-var=poc_controls_enabled=" + flag], input="jsonencode(local.policy)\n",
            env=r.rt.ENV, capture_output=True, text=True, timeout=90)
        assert child.returncode == 0
        values.append(json.loads(json.loads(child.stdout[child.stdout.find('"'): ])))
    return values


def test_actual_thirteen_model_transform_preserves_default_access_and_counters(thirteen_policies):
    before, after = thirteen_policies
    r.guard_policy(before, after)
    root = ET.fromstring(after)
    catalogs = [json.loads(n.text) for n in root.findall(".//set-body") if (n.text or "").startswith('{"data":')]
    assert {m["id"] for m in catalogs[0]["data"]} == r.MODELS
    assert "subscription_controls_unpublished" not in after and "aiflux:v2" not in after
    assert len(root.findall(".//include-fragment")) == 1
    assert len(root.findall(".//forward-request")) == 1 and not root.findall(".//retry")


@pytest.mark.parametrize("old,new", [('FW-GLM-5.3', 'other'), ('FW-MiniMax-M3', 'other'), ('"rpm:"', '"reset:"'),
    ('context.Product == null', 'false'), ('shield-prompt="true"', 'shield-prompt="false"')])
def test_thirteen_transform_rejects_route_safety_auth_counter_mutation(thirteen_policies, old, new):
    assert old in thirteen_policies[1]
    with pytest.raises(RuntimeError):
        r.guard_policy(thirteen_policies[0], thirteen_policies[1].replace(old, new))