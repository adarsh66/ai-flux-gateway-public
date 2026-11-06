"""Pure plan mutation tests; no cloud requests, builds or applies."""
from copy import deepcopy

import pytest

from scripts.deployment import poc_reliability_release as release


IMAGE = "pocidstokenexacr.azurecr.io/aiflux-api@sha256:" + "b" * 64
OLD = "aiflux-api@sha256:" + "a" * 64


def plan():
    before = {"app_settings": {"flag": "preserved"}, "identity": {"type": "UserAssigned"},
              "site_config": [{"always_on": True, "application_stack": [{"docker_image_name": OLD,
                  "docker_registry_url": "https://pocidstokenexacr.azurecr.io"}]}]}
    after = deepcopy(before)
    after["site_config"][0]["application_stack"][0]["docker_image_name"] = IMAGE.split("/", 1)[1]
    return {"applyable": True, "errored": False, "checks": [{"status": "pass"}], "resource_changes": [
        {"address": release.ADDRESS, "mode": "managed", "change": {"actions": ["update"], "before": before, "after": after, "after_unknown": {}}}]}


def baseline():
    return {"runtime": {"sites": {"api": {"image": "DOCKER|pocidstokenexacr.azurecr.io/" + OLD}}}}


def test_exact_api_image_only_with_current_predecessor():
    release.strict(plan(), IMAGE, baseline())


@pytest.mark.parametrize("defect", ["settings", "identity", "always_on", "registry", "admin", "fragment", "create", "unknown", "check", "predecessor", "errored"])
def test_rejects_every_nonimage_delta_or_unvalidated_plan(defect):
    data = plan()
    change = data["resource_changes"][0]["change"]
    if defect == "settings":
        change["after"]["app_settings"]["flag"] = "different"
    elif defect == "identity":
        change["after"]["identity"] = {}
    elif defect == "always_on":
        change["after"]["site_config"][0]["always_on"] = False
    elif defect == "registry":
        change["after"]["site_config"][0]["application_stack"][0]["docker_registry_url"] = "https://foreign.invalid"
    elif defect in ("admin", "fragment"):
        data["resource_changes"].append({"mode": "managed", "address": defect, "change": {"actions": ["update"]}})
    elif defect == "create":
        change["actions"] = ["create"]
    elif defect == "unknown":
        change["after_unknown"] = {"app_settings": True}
    elif defect == "check":
        data["checks"][0]["status"] = "unknown"
    elif defect == "predecessor":
        change["before"]["site_config"][0]["application_stack"][0]["docker_image_name"] = "foreign"
    else:
        data["errored"] = True
    with pytest.raises(RuntimeError):
        release.strict(data, IMAGE, baseline())


def test_existing_apply_intent_blocks_before_any_live_read(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "HOME", tmp_path)
    (tmp_path / "apply-intent.json").write_text("preserved")
    monkeypatch.setattr(release, "check", lambda: pytest.fail("live check after existing apply intent"))
    with pytest.raises(RuntimeError, match="reconcile_only"):
        release.apply()
    assert (tmp_path / "apply-intent.json").read_text() == "preserved"