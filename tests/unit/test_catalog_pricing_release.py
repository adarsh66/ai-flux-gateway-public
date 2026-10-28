from copy import deepcopy
import json

import pytest
from scripts.deployment import catalog_pricing_release as release

IMAGE = release.prior.portals.HOST + "/aiflux-api@sha256:" + "a" * 64


def plan():
    before = {"app_settings": {"protected": "same"}, "site_config": [{"always_on": True,
              "application_stack": [{"docker_image_name": "aiflux-api@sha256:" + "b" * 64,
                                      "docker_registry_url": "https://" + release.prior.portals.HOST}]}]}
    after = deepcopy(before)
    after["site_config"][0]["application_stack"][0]["docker_image_name"] = IMAGE.split("/", 1)[1]
    return {"applyable": True, "resource_changes": [{"mode": "managed",
            "address": 'azurerm_linux_web_app.main["api"]',
            "change": {"actions": ["update"], "before": before, "after": after, "after_unknown": {}}}]}


def test_exact_api_only():
    release.guard(plan(), IMAGE)


@pytest.mark.parametrize("bad", ["admin", "customer", "ingestion", "settings", "always_on", "registry", "unknown", "extra", "delete", "none"])
def test_guard_rejects_every_non_api_image_change(bad):
    data = plan()
    resource = data["resource_changes"][0]
    change = resource["change"]
    if bad in ("admin", "customer", "ingestion"):
        resource["address"] = 'azurerm_linux_web_app.main["' + bad + '"]'
    elif bad == "settings":
        change["after"]["app_settings"]["protected"] = "changed"
    elif bad == "always_on":
        change["after"]["site_config"][0]["always_on"] = False
    elif bad == "registry":
        change["after"]["site_config"][0]["application_stack"][0]["docker_registry_url"] = "https://wrong.test"
    elif bad == "unknown":
        change["after_unknown"] = {"app_settings": True}
    elif bad == "extra":
        data["resource_changes"].append(deepcopy(resource))
    elif bad == "delete":
        change["actions"] = ["delete", "create"]
    else:
        data["resource_changes"] = []
    with pytest.raises(RuntimeError):
        release.guard(data, IMAGE)


@pytest.mark.parametrize("action,marker", [("build", "build-intent.json"), ("plan", "plan-intent.json"),
                                         ("plan", "apply-intent.json"), ("apply", "apply-intent.json")])
def test_no_replay_before_cloud(tmp_path, monkeypatch, action, marker):
    monkeypatch.setattr(release, "HOME", tmp_path)
    (tmp_path / marker).write_text(json.dumps({"attempted": True}))
    monkeypatch.setattr(release, "release", lambda: pytest.fail("must not access cloud"))
    monkeypatch.setattr(release, "check", lambda: pytest.fail("must not access cloud"))
    monkeypatch.setattr(release, "unchanged_portals", lambda: pytest.fail("must not access cloud"))
    with pytest.raises(RuntimeError, match="already_attempted"):
        getattr(release, action)()