"""Offline rejection tests for the GLM-only immutable application rollout."""
from copy import deepcopy

import pytest

from scripts.deployment.glm_runtime_release import KINDS, guard


def fixture():
    resources, results = [], {}
    for kind in KINDS:
        image = f"pocidstokenexacr.azurecr.io/aiflux-{kind}@sha256:" + "a" * 64
        results[kind] = {"image": image}
        old = {"app_settings": {"preserved": "unchanged"}, "identity": {"type": "UserAssigned"},
               "site_config": [{"always_on": True, "application_stack": [{
                   "docker_registry_url": "https://pocidstokenexacr.azurecr.io",
                   "docker_image_name": f"aiflux-{kind}@sha256:" + "b" * 64}]}]}
        new = deepcopy(old)
        new["site_config"][0]["application_stack"][0]["docker_image_name"] = image.split("/", 1)[1]
        resources.append({"address": f'azurerm_linux_web_app.main["{kind}"]', "mode": "managed",
                          "change": {"actions": ["update"], "before": old, "after": new, "after_unknown": {}}})
    return {"applyable": True, "resource_changes": resources}, {"results": results}


def test_exact_three_images_pass():
    plan, built = fixture()
    guard(plan, built)


@pytest.mark.parametrize("mutation", ["settings", "identity", "network", "site", "registry", "pin",
                                     "unknown", "delete", "extra", "missing", "read", "deferred"])
def test_non_image_or_incomplete_plan_rejected(mutation):
    plan, built = fixture()
    resource = plan["resource_changes"][0]
    change = resource["change"]
    after = change["after"]
    if mutation == "settings":
        after["app_settings"]["worker"] = "true"
    elif mutation == "identity":
        after["identity"]["type"] = "SystemAssigned"
    elif mutation == "network":
        after["public_network_access_enabled"] = True
    elif mutation == "site":
        after["site_config"][0]["always_on"] = False
    elif mutation == "registry":
        after["site_config"][0]["application_stack"][0]["docker_registry_url"] = "https://other.example"
    elif mutation == "pin":
        after["site_config"][0]["application_stack"][0]["docker_image_name"] = "unapproved:latest"
    elif mutation == "unknown":
        change["after_unknown"] = {"app_settings": True}
    elif mutation == "delete":
        change["actions"] = ["delete", "create"]
    elif mutation == "extra":
        extra = deepcopy(resource)
        extra["address"] = "azurerm_role_assignment.extra"
        plan["resource_changes"].append(extra)
    elif mutation == "missing":
        plan["resource_changes"].pop()
    elif mutation == "read":
        resource["mode"] = "data"
        change["actions"] = ["read"]
    elif mutation == "deferred":
        plan["deferred_changes"] = [{"reason": "unknown"}]
    with pytest.raises(RuntimeError):
        guard(plan, built)


def test_only_computed_network_outputs_can_be_unknown():
    plan, built = fixture()
    change = plan["resource_changes"][0]["change"]
    change["before"]["outbound_ip_addresses"] = "192.0.2.1"
    change["after"]["outbound_ip_addresses"] = None
    change["after_unknown"]["outbound_ip_addresses"] = True
    guard(plan, built)


def apply_chain():
    from scripts.deployment.glm_resume import applied_baseline
    baseline = {"sites": {k: {"image": "old", "protected": {"private": True}} for k in KINDS},
                "jwt": {"resolved": True}}
    images = {k: "registry/" + k + "@sha256:" + "a" * 64 for k in KINDS}
    review = {"images": images, "plan_sha256": "original", "baseline": baseline}
    applied = {"images": images, "plan_sha256": "original", "image_only_readback_verified": True}
    before = deepcopy(baseline)
    for kind in KINDS:
        before["sites"][kind]["image"] = "DOCKER|" + images[kind]
    release = {"tag": "latest", "results": {k: {"image": "registry/" + k + "@sha256:" + "b" * 64}
                                               for k in ("admin", "customer")}}
    correction = {"applied": True, "guard": "passed", "tag": "latest", "portals": ["admin", "customer"],
                  "changes": [{"address": f'azurerm_linux_web_app.main["{k}"]', "actions": ["update"],
                               "changedFields": ["site_config"]} for k in ("admin", "customer")]}
    return applied_baseline, review, applied, before, release, correction


def test_live_baseline_accepts_exact_applied_portal_successor():
    helper, review, applied, before, release, correction = apply_chain()
    expected = helper(review, applied, before, release, correction)
    assert expected["sites"]["api"] == before["sites"]["api"]
    assert expected["sites"]["admin"]["image"] == "DOCKER|" + release["results"]["admin"]["image"]
    assert expected["jwt"] == before["jwt"]


@pytest.mark.parametrize("mutation", ["predecessor", "plan", "image", "unapplied", "scope", "tag"])
def test_live_baseline_rejects_unbound_successor(mutation):
    helper, review, applied, before, release, correction = apply_chain()
    if mutation == "predecessor":
        before["sites"]["api"]["protected"]["private"] = False
    elif mutation == "plan":
        applied["plan_sha256"] = "other"
    elif mutation == "image":
        applied["images"] = {**applied["images"], "api": "unapproved"}
    elif mutation == "unapplied":
        correction["applied"] = False
    elif mutation == "scope":
        correction["changes"][0]["actions"] = ["delete"]
    else:
        correction["tag"] = "other"
    with pytest.raises(RuntimeError):
        helper(review, applied, before, release, correction)