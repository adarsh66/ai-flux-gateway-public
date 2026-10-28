"""Synthetic ownership/plan/probe guards; no Azure writes or production DB tests."""
from copy import deepcopy
import hashlib

import pytest

from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_preflight as preflight

NONCE = "012345abcdef"
IDS = g.owned_ids(NONCE)


def resources():
    result = {key: {"id": rid, "location": "southeastasia", "tags": {"finops-owner": NONCE}, "properties": {}}
              for key, rid in IDS.items()}
    result["subnet"] = {"id": IDS["subnet"], "properties": {
        "addressPrefix": g.CIDR, "defaultOutboundAccess": False,
        "delegations": [{"properties": {"serviceName": g.DELEGATION}}],
        "natGateway": {"id": IDS["nat"]}, "networkSecurityGroup": {"id": IDS["nsg"]}}}
    return result


def journal():
    return {"owner_nonce": NONCE, "baseline_absent": {k: True for k in IDS}, "write_intents": list(IDS)}


def test_cleanup_owned_dependency_order_and_independent_gets():
    live = {r["id"]: r for r in resources().values()}
    deleted, gets = [], []
    def get(rid):
        gets.append(rid)
        return live.get(rid)
    def delete(rid):
        deleted.append(rid)
        del live[rid]
    assert g.cleanup_owned(nonce=NONCE, journal=journal(), get_resource=get, delete_resource=delete) == list(IDS.values())
    assert deleted == list(IDS.values()) and not live
    assert all(gets.count(rid) >= 4 for rid in IDS.values())


@pytest.mark.parametrize("mutation", ["tag", "journal", "cidr", "nat", "foreign_id", "association"])
def test_foreign_or_changed_resource_prevents_every_delete(mutation):
    current, j = resources(), journal()
    if mutation == "tag": current["pip"]["tags"]["finops-owner"] = "foreign"
    if mutation == "journal": j["baseline_absent"]["pip"] = False
    if mutation == "cidr": current["subnet"]["properties"]["addressPrefix"] = "10.240.3.0/24"
    if mutation == "nat": current["subnet"]["properties"]["natGateway"]["id"] = "/foreign"
    if mutation == "foreign_id": current["api"]["id"] = g.VNET
    if mutation == "association": current["nsg"]["properties"]["subnets"] = [{"id": g.VNET + "/subnets/existing"}]
    live = {IDS[k]: r for k, r in current.items()}
    with pytest.raises(g.GuardBlocked):
        g.cleanup_owned(nonce=NONCE, journal=j, get_resource=live.get,
                        delete_resource=lambda _: pytest.fail("must reject before first delete"))


def test_cleanup_does_not_treat_authorization_error_as_absent():
    def get(_): raise PermissionError("synthetic denial")
    with pytest.raises(PermissionError):
        g.cleanup_owned(nonce=NONCE, journal=journal(), get_resource=get,
                        delete_resource=lambda _: pytest.fail("no delete"))


def test_cleanup_failure_does_not_claim_verified_absence():
    live = resources()["ingestion"]
    def get(rid): return live if rid == IDS["ingestion"] else None
    with pytest.raises(g.GuardBlocked, match="cleanup_not_absent"):
        g.cleanup_owned(nonce=NONCE, journal=journal(), get_resource=get, delete_resource=lambda _: None)


def test_exact_network_plan_creates_only_four_owned_objects():
    plan = {"status": "Succeeded", "changes": [{"resourceId": IDS[k], "changeType": "Create"}
            for k in ("subnet", "nsg", "nat", "pip")]}
    assert g.guard_what_if(plan, NONCE, "network")
    for change in [{"resourceId": g.VNET, "changeType": "Modify"},
                   {"resourceId": g.RG + "/providers/Microsoft.Authorization/roleAssignments/foreign", "changeType": "Create"},
                   {"resourceId": IDS["pip"], "changeType": "Modify"}]:
        bad = deepcopy(plan)
        bad["changes"].append(change)
        with pytest.raises(g.GuardBlocked): g.guard_what_if(bad, NONCE, "network")
    with pytest.raises(g.GuardBlocked): g.guard_what_if({"status": "Succeeded", "changes": []}, NONCE, "network")


def group():
    image = "pocidstokenexacr.azurecr.io/aiflux-finops-probe@sha256:" + "a" * 64
    source = hashlib.sha256(b"reviewed probe").hexdigest()
    return {"id": IDS["ingestion"], "location": "southeastasia", "identity": {
        "type": "UserAssigned", "userAssignedIdentities": {g.IDENTITIES["ingestion"]: {}}}, "properties": {
        "osType": "Linux", "restartPolicy": "Never", "subnetIds": [{"id": IDS["subnet"]}],
        "dnsConfig": {"nameServers": ["168.63.129.16"]},
        "imageRegistryCredentials": [{"server": "pocidstokenexacr.azurecr.io", "identity": g.IDENTITIES["ingestion"]}],
        "containers": [{"name": "probe", "properties": {"image": image,
            "command": ["python", "-I", "/probe/entrypoint.py", "--probe-sha256", source, "--identity", "ingestion"],
            "resources": {"requests": {"cpu": 1, "memoryInGB": 1.5}, "limits": {"cpu": 1, "memoryInGB": 1.5}}}}]}}, image, source


@pytest.mark.parametrize("mutation", [None, "both_mis", "previous_alive", "mutable_image", "application_entrypoint", "env", "ports"])
def test_probe_mi_image_hash_and_no_application_entrypoint_binding(mutation):
    value, image, source = group()
    if mutation == "both_mis": value["identity"]["userAssignedIdentities"][g.IDENTITIES["api"]] = {}
    if mutation == "mutable_image": image = image.split("@")[0] + ":latest"
    if mutation == "application_entrypoint": value["properties"]["containers"][0]["properties"]["command"] = ["uvicorn", "aiflux.app:app"]
    if mutation == "env": value["properties"]["containers"][0]["properties"]["environmentVariables"] = [{"name": "SECRET", "value": "never"}]
    if mutation == "ports": value["properties"]["ipAddress"] = {"type": "Public", "ports": [{"port": 19390}]}
    kwargs = dict(nonce=NONCE, phase="ingestion", image=image, source_hash=source, prior_group_absent=mutation != "previous_alive")
    if mutation:
        with pytest.raises(g.GuardBlocked): g.guard_probe_group(value, **kwargs)
    else:
        assert g.guard_probe_group(value, **kwargs)
        g.verify_source(b"reviewed probe", source)
        with pytest.raises(g.GuardBlocked): g.verify_source(b"changed probe", source)


def test_platform_conflict_is_a_gate_not_permission_to_open_ports():
    with pytest.raises(g.GuardBlocked, match="aci_platform_19390"):
        g.platform_gate(all_inbound_denied=True, documented_management_port_required=True,
                requirement_applies_to_subnet_nsg=True)


@pytest.mark.parametrize("mutation", [None, "extra_claim", "raw_error", "writes", "sqlstate"])
def test_probe_output_never_exports_claims_raw_driver_messages_or_writes(mutation):
    value = {"status": "blocked", "reason": "unverified_runtime_failure", "sqlstate": None,
             "database_writes": 0, "replay_authorized": False}
    if mutation == "extra_claim": value["oid"] = "secret-claim"
    if mutation == "raw_error": value["reason"] = "SECRET-DSN-AND-TOKEN"
    if mutation == "writes": value["database_writes"] = 1
    if mutation == "sqlstate": value["sqlstate"] = "SECRET-DRIVER-ERROR"
    if mutation:
        with pytest.raises(g.GuardBlocked): g.safe_probe_failure(value)
    else:
        assert g.safe_probe_failure(value) == value


def test_network_capacity_and_collision_checks():
    vnet = {"id": g.VNET, "location": "southeastasia", "properties": {
        "addressSpace": {"addressPrefixes": ["10.240.0.0/16"]}, "subnets": [
            {"id": g.VNET + "/subnets/existing", "properties": {"addressPrefixes": ["10.240.3.0/24"]}}]}}
    assert g.network_capacity(vnet)["usable_addresses_after_azure_reservation"] == 251
    vnet["properties"]["subnets"][0]["properties"]["addressPrefixes"] = [g.CIDR]
    with pytest.raises(g.GuardBlocked, match="collision"): g.network_capacity(vnet)


@pytest.mark.parametrize("args", [["container", "create"], ["network", "vnet", "subnet", "create"],
                                 ["rest", "--method", "put"], ["rest", "--method", "delete"],
                                 ["deployment", "group", "create"], ["acr", "build"]])
def test_preflight_has_no_cloud_write_command_path(args, monkeypatch):
    monkeypatch.setattr(preflight.subprocess, "run", lambda *_a, **_kw: pytest.fail("must reject before subprocess"))
    with pytest.raises(g.GuardBlocked, match="read_only_command_required"):
        preflight.cli(args)


def test_nat_price_selection_rejects_government_region_and_other_skus():
    value = {"productName": "NAT Gateway", "skuName": "Standard", "meterName": "Standard Gateway",
             "unitOfMeasure": "1 Hour", "armRegionName": "Global", "currencyCode": "USD",
             "type": "Consumption", "retailPrice": 0.045, "meterId": "synthetic", "effectiveStartDate": "synthetic"}
    kwargs = dict(product="NAT Gateway", name="Standard Gateway", unit="1 Hour", region="Global")
    assert preflight.meter([value], **kwargs)["retailPrice"] == 0.045
    for fields in ({"armRegionName": "US Gov"}, {"skuName": "StandardV2"}, {"currencyCode": "SGD"},
                   {"type": "Reservation"}, {"unitOfMeasure": "1 GB"}):
        with pytest.raises(g.GuardBlocked): preflight.meter([{**value, **fields}], **kwargs)
    with pytest.raises(g.GuardBlocked): preflight.meter([value, value], **kwargs)