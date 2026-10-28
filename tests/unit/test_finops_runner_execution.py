"""Offline exact execution/reaper guards, not live DB acceptance."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from scripts.deployment import finops_runner_execute as ex
from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_prepare as prep

NONCE = "012345abcdef"


def session():
    start = datetime.now(UTC)
    return {"owner_nonce": NONCE, "ids": g.owned_ids(NONCE), "started_at_utc": start.isoformat(),
        "deadline_utc": (start + timedelta(minutes=60)).isoformat(), "baseline_absent": {k: True for k in g.owned_ids(NONCE)},
        "write_intents": list(g.owned_ids(NONCE)), "image": "pocidstokenexacr.azurecr.io/aiflux-finops-probe@sha256:" + "a" * 64,
        "probe_hash": "b" * 64}


def objects(s):
    result = {}
    for key in ("pip", "nsg", "nat", "subnet"):
        kind = {"pip": "/publicIPAddresses", "nsg": "/networkSecurityGroups", "nat": "/natGateways", "subnet": "/subnets"}[key]
        value = next(x for x in prep.network_template(NONCE)["resources"] if x["type"].endswith(kind))
        result[s["ids"][key]] = {**value, "id": s["ids"][key]}
    for phase in g.IDENTITIES:
        result[s["ids"][phase]] = prep.group_resource(NONCE, phase, s["image"], s["probe_hash"])
    return result


class FakeArm:
    def __init__(self, values): self.values, self.deleted = values, []
    def get(self, rid): return self.values.get(rid)
    def delete(self, rid):
        self.deleted.append(rid)
        del self.values[rid]


def test_cleanup_exact_dependency_order_independent_six_gets(tmp_path):
    s = session()
    arm = FakeArm(objects(s))
    value = ex.cleanup(s, tmp_path, arm)
    assert value["exit_code"] == 0
    assert value["deleted_resource_ids"] == [s["ids"][key] for key in ("ingestion", "api", "subnet", "nsg", "nat", "pip")]
    assert len(value["absence"]) == 6 and all(x["http_status"] == 404 for x in value["absence"])


@pytest.mark.parametrize("key", ["ingestion", "api", "nsg", "nat", "pip"])
def test_wrong_nonce_never_deletes_foreign_object(key, tmp_path):
    s = session()
    values = objects(s)
    values[s["ids"][key]]["tags"]["finops-owner"] = "foreign"
    arm = FakeArm(values)
    value = ex.cleanup(s, tmp_path, arm)
    assert value["exit_code"] == 2 and s["ids"][key] not in arm.deleted


@pytest.mark.parametrize("mutation", ["rule", "nat", "subnet", "both_mis", "entrypoint"])
def test_changed_object_refused_even_with_owner_tag(mutation):
    s = session()
    values = objects(s)
    key = {"rule": "nsg", "nat": "nat", "subnet": "subnet", "both_mis": "ingestion", "entrypoint": "api"}[mutation]
    value = deepcopy(values[s["ids"][key]])
    if mutation == "rule": value["properties"]["securityRules"][0]["properties"]["sourceAddressPrefix"] = "*"
    if mutation == "nat": value["properties"]["publicIpAddresses"] = [{"id": "foreign"}]
    if mutation == "subnet": value["properties"]["addressPrefix"] = "10.240.3.0/24"
    if mutation == "both_mis": value["identity"]["userAssignedIdentities"][g.IDENTITIES["api"]] = {}
    if mutation == "entrypoint": value["properties"]["containers"][0]["properties"]["command"] = ["uvicorn"]
    with pytest.raises(g.GuardBlocked): ex.verify_owned(value, key, s)


def test_bound_session_rejects_hash_ids_and_longer_deadline(tmp_path):
    s = session()
    path = tmp_path / "session.json"
    ex.write(path, s)
    assert ex.bound_session(path, prep.digest(path)) == s
    with pytest.raises(g.GuardBlocked): ex.bound_session(path, "a" * 64)
    s["deadline_utc"] = (datetime.fromisoformat(s["deadline_utc"]) + timedelta(seconds=1)).isoformat()
    ex.write(path, s)
    with pytest.raises(g.GuardBlocked): ex.bound_session(path, prep.digest(path))


def test_cleanup_started_blocks_any_later_resource_creation(tmp_path):
    s = session()
    ex.write(tmp_path / "cleanup-started.json", {})
    class NoCalls:
        def get(self, *args): pytest.fail("must block before ARM")
    with pytest.raises(g.GuardBlocked): ex.live_put(NoCalls(), s, tmp_path, "pip", {})


def test_foreign_arm_id_or_action_refused_before_token():
    arm = ex.Arm(session())
    with pytest.raises(g.GuardBlocked): arm.request("DELETE", g.VNET)
    with pytest.raises(g.GuardBlocked): arm.request("GET", g.owned_ids(NONCE)["api"], action="/exec")


def test_arm_case_normalization_preserves_exact_single_identity_and_subnet():
    s = session()
    group = objects(s)[s["ids"]["api"]]
    group["identity"]["userAssignedIdentities"] = {g.IDENTITIES["api"].lower(): {"clientId": "provider-metadata"}}
    group["properties"]["subnetIds"] = [{"id": s["ids"]["subnet"].lower(), "name": "provider-metadata"}]
    group["properties"]["imageRegistryCredentials"][0]["identity"] = g.IDENTITIES["api"].lower()
    ex.verify_owned(group, "api", s)


def test_probe_deployment_failed_and_deadline_have_finite_labels(monkeypatch):
    class Failed:
        def get(self, *args): return {"properties": {"provisioningState": "Failed"}}
    with pytest.raises(g.GuardBlocked, match="resource_provisioning_failed"): ex.wait_resource(Failed(), "owned", 0)
    class Waiting:
        def get(self, *args): return {"properties": {"provisioningState": "Creating"}}
    with pytest.raises(g.GuardBlocked, match="resource_deployment_deadline"): ex.wait_resource(Waiting(), "owned", 0)


@pytest.mark.parametrize("metadata", [None, {"type": "Private", "ports": []},
    {"type": "Private", "ports": None, "ip": "10.240.5.4"},
    {"type": "Private", "ip": "10.240.5.5"}, {"type": "Private", "ip": None}])
def test_arm_private_metadata_keeps_full_ownership_cleanup(metadata, tmp_path):
    s = session()
    values = objects(s)
    values[s["ids"]["ingestion"]]["properties"]["ipAddress"] = metadata
    arm = FakeArm(values)
    assert ex.cleanup(s, tmp_path, arm)["exit_code"] == 0
    assert len(arm.deleted) == 6


@pytest.mark.parametrize("metadata", [{"type": "Public"}, {"type": "Private", "ports": [{"port": 80}]},
    {"type": "Private", "ip": "8.8.8.8"}, {"type": "Private", "ip": "10.240.4.4"},
    {"type": "Private", "ip": "::1"}, {"type": "Private", "ip": "invalid"},
    {"type": "Private", "ip": 123}, {"type": "Private", "fqdn": "foreign"}, {}])
def test_private_metadata_never_allows_public_foreign_or_invalid(metadata, tmp_path):
    s = session()
    values = objects(s)
    values[s["ids"]["ingestion"]]["properties"]["ipAddress"] = metadata
    arm = FakeArm(values)
    assert ex.cleanup(s, tmp_path, arm)["exit_code"] == 2
    assert arm.deleted == []


def test_cleanup_reconciliation_preserves_nonempty_first_delete_evidence(tmp_path, monkeypatch):
    s = session()
    path = tmp_path / "session.json"
    ex.write(path, s)
    digest = prep.digest(path)
    original = tmp_path / "original.json"
    ex.write(original, {"ids": s["ids"], "owner_nonce": NONCE,
        "independent_watchdog_ready": {"session_sha256": digest},
        "created_resource_ids": list(s["ids"].values()), "watchdog_pid": 123,
        "inbound": "approved-exact-scope"})
    (tmp_path / "gateway/validation").mkdir(parents=True)
    arm = FakeArm(objects(s))
    arm.events = []
    monkeypatch.setattr(ex, "OUT", original)
    monkeypatch.setattr(ex.p, "ROOT", tmp_path)
    monkeypatch.setattr(ex, "Arm", lambda _: arm)
    monkeypatch.setattr(prep, "preservation_readback", lambda: {"preservation_verified": True})
    assert ex.reconcile_cleanup(path, digest) == 0
    output = tmp_path / "gateway/validation/finops-owned-cleanup-20261027.json"
    first = output.read_bytes()
    assert len(ex.load(output)["cleanup"]["deleted_resource_ids"]) == 6
    assert ex.reconcile_cleanup(path, digest) == 0
    assert output.read_bytes() == first
    checks = list(output.parent.glob("finops-owned-cleanup-verification-*.json"))
    assert len(checks) == 1
    assert ex.load(checks[0])["cleanup"]["deleted_resource_ids"] == []
    assert all(x["http_status"] == 404 for x in ex.load(checks[0])["final_exact_id_readbacks"])