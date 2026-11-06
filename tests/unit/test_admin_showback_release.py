from copy import deepcopy
import pytest
from scripts.deployment import admin_showback_release as s


def fixture():
    images = {k: s.r.portals.HOST + "/aiflux-" + k + "@sha256:" + "b" * 64 for k in s.KINDS}
    baseline = {"runtime": {"sites": {}}}
    changes = []
    for address, kind in s.ADDRESSES.items():
        baseline["runtime"]["sites"][kind] = {"image": "DOCKER|" + s.r.portals.HOST + "/aiflux-" + kind + "@sha256:" + "a" * 64}
        before = {"app_settings": {"protected": "same"}, "identity": {"type": "UserAssigned"},
            "site_config": [{"always_on": True, "application_stack": [{"docker_image_name": "aiflux-" + kind + "@sha256:" + "a" * 64,
                "docker_registry_url": "https://" + s.r.portals.HOST}]}]}
        after = deepcopy(before)
        after["site_config"][0]["application_stack"][0]["docker_image_name"] = images[kind].split("/", 1)[1]
        changes.append({"address": address, "mode": "managed", "change": {"actions": ["update"], "before": before, "after": after, "after_unknown": {}}})
    return {"applyable": True, "checks": [{"status": "pass"}], "resource_changes": changes}, images, baseline


def test_exact_two_images():
    p, images, before = fixture()
    original = deepcopy(p)
    s.guard(p, images, before)
    assert p == original


@pytest.mark.parametrize("mutation", ["settings", "identity", "always_on", "registry", "unknown", "extra", "delete", "missing", "predecessor", "check", "tag", "managed_read"])
def test_rejects_protected_mutations(mutation):
    p, images, before = fixture()
    c = p["resource_changes"][0]["change"]
    if mutation == "settings": c["after"]["app_settings"]["flag"] = "new"
    elif mutation == "identity": c["after"]["identity"] = {}
    elif mutation == "always_on": c["after"]["site_config"][0]["always_on"] = False
    elif mutation == "registry": c["after"]["site_config"][0]["application_stack"][0]["docker_registry_url"] = "https://other"
    elif mutation == "unknown": c["after_unknown"] = {"app_settings": True}
    elif mutation == "extra": p["resource_changes"].append({"address": "policy", "mode": "managed", "change": deepcopy(c)})
    elif mutation == "delete": c["actions"] = ["delete", "create"]
    elif mutation == "missing": p["resource_changes"].pop()
    elif mutation == "predecessor": before["runtime"]["sites"]["api"]["image"] = "old"
    elif mutation == "check": p["checks"][0]["status"] = "unknown"
    elif mutation == "tag": images["api"] = "latest"
    elif mutation == "managed_read": p["resource_changes"].append({"address": "other", "mode": "managed", "change": {"actions": ["read"]}})
    with pytest.raises(RuntimeError): s.guard(p, images, before)


def test_computed_output_only():
    p, images, before = fixture()
    c = p["resource_changes"][0]["change"]
    c["before"]["outbound_ip_addresses"] = "same"
    c["after"]["outbound_ip_addresses"] = None
    c["after_unknown"] = {"outbound_ip_addresses": True}
    s.guard(p, images, before)


def test_no_apply_companion_path():
    import inspect
    text = inspect.getsource(s.apply)
    assert 'str(PLAN)' in text and 'str(FULL)' not in text
    assert 'apply-intent.json' in text and 'parallelism=1' in text