from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json

import pytest

from scripts.deployment import inventory_recovery_oct29 as r


@pytest.fixture
def evidence():
    old = r.load(r.BASE / r.FOUNDRY)
    live = {"account": {"id": old["account_resource_id"], "properties": {"provisioningState": "Succeeded"}},
            "project": {"id": old["project_resource_id"], "properties": {"provisioningState": "Succeeded"}},
            "connections": {"value": []}, "deployments": {"value": []}}
    for d in old["deployments"]:
        live["deployments"]["value"].append({"id": d["id"], "name": d["name"],
            "properties": {"model": {"format": d["model_format"], "name": d["model_name"], "version": d["model_version"]},
                           "provisioningState": "Succeeded", "deploymentState": d.get("deployment_state"),
                           "capabilities": {"chatCompletion": str(d["chat_completion"]).lower()}},
            "sku": {"name": d.get("sku", "GlobalStandard"), "capacity": d["capacity"]}})
    return old, live


def test_renewal_changes_only_verified_timestamp(evidence):
    old, live = evidence
    before = deepcopy(old)
    stamp = datetime.now(UTC).isoformat()
    result = r.renew_foundry(old, live, stamp)
    assert result == {**old, "verified_at": stamp} and old == before
    assert len(result["routes"]) == 12


@pytest.mark.parametrize("mutation", [
    lambda d: d["account"].update(id="wrong"),
    lambda d: d["project"].update(id="wrong"),
    lambda d: d["account"]["properties"].update(provisioningState="Updating"),
    lambda d: d["connections"]["value"].append({"id": "new-connection"}),
    lambda d: d["connections"].update(nextLink="more"),
    lambda d: d["deployments"].update(nextLink="more"),
    lambda d: d["deployments"]["value"].pop(),
    lambda d: d["deployments"]["value"].append(deepcopy(d["deployments"]["value"][0])),
    lambda d: d["deployments"]["value"][0].update(id="wrong"),
    lambda d: d["deployments"]["value"][0]["properties"]["model"].update(version="changed"),
    lambda d: d["deployments"]["value"][0]["properties"].update(provisioningState="Failed"),
    lambda d: d["deployments"]["value"][0]["sku"].update(capacity=0),
    lambda d: d["deployments"]["value"][1]["properties"]["capabilities"].update(chatCompletion="false"),
])
def test_renewal_rejects_mismatched_or_partial_live_reads(evidence, mutation):
    old, live = evidence
    mutation(live)
    with pytest.raises(RuntimeError):
        r.renew_foundry(old, live, datetime.now(UTC).isoformat())


@pytest.mark.parametrize("offset", [timedelta(days=-1), timedelta(minutes=5)])
def test_expired_or_future_observation_rejected(evidence, offset):
    with pytest.raises(RuntimeError):
        r.renew_foundry(*evidence, (datetime.now(UTC) + offset).isoformat())


def test_missing_runtime_role_is_not_authority_to_refresh():
    proof = r.role_coverage([], "api-identity", "/subscriptions/example/resourceGroups/example")
    assert not proof["all_required_direct_actions_covered"]
    assert not proof["automatic_refresh_authorized"]


def test_retained_source_binding_excludes_unshipped_auto():
    manifest, built = r.retained_sources()
    assert manifest["sha256"] == built["source_sha256"]
    assert built["image"] == r.IMAGE


def test_external_renewal_preserves_historical_smoke():
    old = r.load(r.BASE / r.EXTERNAL)
    backend = {"id": "unchanged"}
    policy = "unchanged policy"
    old["routes"][0]["metadata_renewal"].update(policy_sha256=r.sha(policy), backend_sha256=r.sha(json.dumps(backend, sort_keys=True)))
    from scripts.deployment.glm_apim_secret import RESOURCE_ID
    ref = {"resource_id": RESOURCE_ID, "display_name": r.NAME, "secret": True, "key_vault": False, "checked_at": datetime.now(UTC).isoformat()}
    stamp = datetime.now(UTC).isoformat()
    renewed = r.renew_external(old, policy, backend, ref, stamp)
    result = deepcopy(renewed)
    result["routes"][0]["metadata_renewal"] = old["routes"][0]["metadata_renewal"]
    assert result == old
    assert not renewed["routes"][0]["metadata_renewal"]["smoke_repeated"]
    with pytest.raises(RuntimeError):
        r.renew_external(old, policy + " changed", backend, ref, stamp)
    with pytest.raises(RuntimeError):
        r.renew_external(old, policy, {"id": "changed"}, ref, stamp)


def test_prepared_recovery_package_has_only_authorized_metadata_deltas():
    folder = r.rt.HOME / "inventory-recovery-20261029-024900Z"
    if not (folder / "package-manifest.json").exists():
        pytest.skip("local exclusive evidence is not checked into source control")
    package = r.load(folder / "package-manifest.json")
    assert {e["path"] for e in package["entries"]} == {
        r.FOUNDRY, r.EXTERNAL, "InventoryRecovery.Dockerfile"}
    for entry in package["entries"]:
        assert r.sha((folder / "context" / entry["path"]).read_bytes()) == entry["sha256"]
    old_foundry = r.load(r.BASE / r.FOUNDRY)
    new_foundry = r.load(folder / "context" / r.FOUNDRY)
    assert new_foundry == {**old_foundry, "verified_at": package["observed_at_utc"]}
    old_external = r.load(r.BASE / r.EXTERNAL)
    new_external = r.load(folder / "context" / r.EXTERNAL)
    old_renewal = old_external["routes"][0]["metadata_renewal"]
    new_external["routes"][0]["metadata_renewal"]["observed_at"] = old_renewal["observed_at"]
    new_external["routes"][0]["metadata_renewal"]["reference_metadata_sha256"] = old_renewal["reference_metadata_sha256"]
    assert new_external == old_external
    docker = (folder / "context/InventoryRecovery.Dockerfile").read_text()
    assert docker.splitlines()[0] == "FROM " + r.IMAGE
    assert len(docker.splitlines()) == 3 and "RUN " not in docker and "ENV " not in docker


def test_no_push_null_representation_is_not_a_published_image():
    from scripts.deployment.customer_catalog_validate import no_published_images
    assert no_published_images([None])
    assert no_published_images([])
    assert no_published_images(None)
    assert not no_published_images([{"digest": "sha256:unexpected"}])