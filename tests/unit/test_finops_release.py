"""Offline source manifest and exact four-image plan rejection tests."""
from copy import deepcopy

import pytest

from scripts.deployment import finops_release as release


def fixture():
    images = {k: release.REGISTRY + "/aiflux-" + k + "@sha256:" + "a" * 64 for k in release.COMPONENTS}
    changes = []
    for address, kind in release.ADDRESSES.items():
        stack = {"docker_registry_url": "https://" + release.REGISTRY,
                 "docker_image_name": "aiflux-" + kind + "@sha256:" + "b" * 64}
        if kind == "ingestion":
            stack = {"docker": [{"registry_url": "https://" + release.REGISTRY,
                                  "image_name": "aiflux-ingestion@sha256", "image_tag": "b" * 64}]}
        old = {"enabled": False, "public_network_access_enabled": False,
               "app_settings": {"AzureWebJobs.ingest_usage.Disabled": "true", "cutoff": "preserved"},
               "identity": [{"type": "UserAssigned", "identity_ids": ["preserved"]}],
               "site_config": [{"minimum_tls_version": "1.2", "application_stack": [stack]}]}
        new = deepcopy(old)
        target = new["site_config"][0]["application_stack"][0]
        if kind == "ingestion":
            target["docker"][0]["image_tag"] = "a" * 64
        else:
            target["docker_image_name"] = images[kind].split("/", 1)[1]
        changes.append({"address": address, "mode": "managed", "change": {
            "actions": ["update"], "before": old, "after": new, "after_unknown": {}}})
    return {"applyable": True, "resource_changes": changes}, images


def test_four_image_guard_is_structural_only_and_does_not_mutate_plan():
    plan, images = fixture()
    saved = deepcopy(plan)
    assert release.guard_image_plan(plan, images) == {
        "structural_guard": "passed", "release_authorized": False, "apply_executed": False}
    assert plan == saved


@pytest.mark.parametrize("mutation", ["timer", "cutoff", "enabled", "network", "identity", "tls", "rbac",
                                     "delete", "missing", "duplicate", "unknown", "deferred", "native",
                                     "registry", "pin", "tag", "extra_pin", "not_applyable", "errored"])
def test_all_non_image_or_unbound_changes_are_rejected(mutation):
    plan, images = fixture()
    change = plan["resource_changes"][-1]["change"]
    after = change["after"]
    if mutation == "timer":
        after["app_settings"]["AzureWebJobs.ingest_usage.Disabled"] = "false"
    elif mutation == "cutoff":
        after["app_settings"]["cutoff"] = "invented"
    elif mutation == "enabled":
        after["enabled"] = True
    elif mutation == "network":
        after["public_network_access_enabled"] = True
    elif mutation == "identity":
        after["identity"][0]["identity_ids"] = ["other"]
    elif mutation == "tls":
        after["site_config"][0]["minimum_tls_version"] = "1.0"
    elif mutation == "rbac":
        item = deepcopy(plan["resource_changes"][-1])
        item["address"] = "azurerm_role_assignment.extra"
        plan["resource_changes"].append(item)
    elif mutation == "delete":
        change["actions"] = ["delete", "create"]
    elif mutation == "missing":
        plan["resource_changes"].pop()
    elif mutation == "duplicate":
        plan["resource_changes"].append(deepcopy(plan["resource_changes"][-1]))
    elif mutation == "unknown":
        change["after_unknown"] = {"app_settings": {"hidden": True}}
    elif mutation == "deferred":
        plan["deferred_changes"] = [{"reason": "unknown"}]
    elif mutation == "native":
        change["before"]["site_config"][0]["application_stack"] = [{"python_version": "3.11"}]
    elif mutation == "registry":
        after["site_config"][0]["application_stack"][0]["docker"][0]["registry_url"] = "https://unapproved.invalid"
    elif mutation == "pin":
        after["site_config"][0]["application_stack"][0]["docker"][0]["image_tag"] = "c" * 64
    elif mutation == "tag":
        images["ingestion"] = release.REGISTRY + "/aiflux-ingestion:latest"
    elif mutation == "extra_pin":
        images["worker"] = images["ingestion"]
    elif mutation == "not_applyable":
        plan["applyable"] = False
    else:
        plan["errored"] = True
    with pytest.raises(ValueError):
        release.guard_image_plan(plan, images)


def test_real_source_manifest_includes_all_four_packaged_components_and_ingester_dockerfile():
    manifest = release.source_manifest()
    assert manifest["required_changed_components"] == list(release.COMPONENTS)
    assert not manifest["release_authorized"]
    for kind in ("api", "ingestion"):
        names = {e["path"] for e in manifest["components"][kind]["entries"]}
        assert "services/control-plane/src/aiflux/finops.py" in names
        assert "services/control-plane/src/aiflux/ingestion.py" in names
        assert "services/control-plane/migrations/versions/0003_portal_users.py" not in names
        assert "services/control-plane/migrations/versions/0003_stable_teams.py" in names
    names = {e["path"] for e in manifest["components"]["ingestion"]["entries"]}
    assert "services/usage-ingestion/Dockerfile" in names and "Dockerfile.aca" not in names
    for kind in ("admin", "customer"):
        names = {e["path"] for e in manifest["components"][kind]["entries"]}
        assert "packages/ui/src/pages/UsagePage.tsx" in names
        assert f"apps/{kind}-portal/Dockerfile" in names


def test_shared_backend_change_invalidates_api_and_ingestion_not_ui(tmp_path):
    before = release.source_manifest()
    # Copy only the allowlisted public manifest inputs into the synthetic root.
    for component in before["components"].values():
        for entry in component["entries"]:
            name = entry["path"]
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((release.ROOT / name).read_bytes())
    same = release.source_manifest(tmp_path)
    assert same == before
    changed = tmp_path / "services/control-plane/src/aiflux/finops.py"
    changed.write_bytes(changed.read_bytes() + b"\n# synthetic change\n")
    after = release.source_manifest(tmp_path)
    for kind in release.COMPONENTS:
        assert (after["components"][kind]["source_sha256"] != before["components"][kind]["source_sha256"]) is (kind in {"api", "ingestion"})