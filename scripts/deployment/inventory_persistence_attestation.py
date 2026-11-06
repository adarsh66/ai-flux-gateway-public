"""Native exact-image attestation. No Azure credentials or inference."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(mode):
    import aiflux
    from aiflux.config import Settings
    from aiflux.external_inventory import AcceptedInventory, ExternalRoute, historical_acceptance_sha256
    from fastapi import HTTPException
    manifest = json.loads(Path("/tmp/attestation.json").read_text())
    prefix = "services/control-plane/src/aiflux/"
    expected = {e["path"][len(prefix):]: e["sha256"] for e in manifest["retained"]["entries"] if e["path"].startswith(prefix)}
    if mode == "after":
        expected.update(manifest["changed"])
    installed = Path(aiflux.__file__).parent
    assert {p.relative_to(installed).as_posix() for p in installed.rglob("*.py")} == {n for n in expected if n.endswith(".py")}
    for name, value in expected.items():
        assert digest(Path("/app") / prefix / name) == value, "packaged code changed:" + name
        if name.endswith(".py"):
            assert digest(installed / name) == value, "installed code changed:" + name
    assert not any(n.startswith("decision_") for n in expected)
    by_path = {e["path"]: e["sha256"] for e in manifest["retained"]["entries"]}
    settings = Settings(_env_file=None, local_auth_enabled=True)
    for path in (settings.foundry_inventory_path, settings.external_inventory_path, settings.catalog_path):
        assert digest(path) == by_path[path.resolve().relative_to("/app").as_posix()], "metadata must not be restamped"
    if mode == "before":
        try:
            AcceptedInventory.load(settings)
        except HTTPException as error:
            assert error.status_code == 503
        else:
            raise AssertionError("old immutable image must reproduce inventory503")
    else:
        baseline = AcceptedInventory.load(settings)
        aliases = baseline.accepted_aliases(settings)
        assert len(aliases) == 13 and not {"auto", "Decision-1"} & aliases
        assert all(r.expires_at is None for r in baseline.foundry.routes)
        original = json.loads(settings.foundry_inventory_path.read_text())
        ext = json.loads(settings.external_inventory_path.read_text())
        with tempfile.TemporaryDirectory() as folder:
            settings.foundry_inventory_path = Path(folder) / "foundry.json"
            settings.external_inventory_path = Path(folder) / "external.json"
            old = (datetime.now(UTC) - timedelta(days=100)).isoformat()
            original["verified_at"] = old
            for route in original["routes"]:
                route["expires_at"] = old
            ext["routes"][0]["verified_at"] = old
            renewal = ext["routes"][0]["metadata_renewal"]
            renewal["observed_at"] = old
            without = deepcopy(ext["routes"][0])
            without.pop("metadata_renewal")
            renewal["historical_acceptance_sha256"] = historical_acceptance_sha256(ExternalRoute.model_validate(without))
            settings.foundry_inventory_path.write_text(json.dumps(original))
            settings.external_inventory_path.write_text(json.dumps(ext))
            stale = AcceptedInventory.load(settings)
            assert stale.accepted_aliases(settings) == aliases
            assert all(stale.route(a) for a in aliases)
            for field, value in (("verified_at", (datetime.now(UTC) + timedelta(days=1)).isoformat()),
                                 ("verified_at", "bad"), ("verified_at", "2020-01-01T00:00:00"),
                                 ("account_resource_id", original["account_resource_id"] + "-wrong")):
                bad = deepcopy(original)
                bad[field] = value
                settings.foundry_inventory_path.write_text(json.dumps(bad))
                try:
                    AcceptedInventory.load(settings)
                except HTTPException as error:
                    assert error.status_code == 503
                else:
                    raise AssertionError("invalid provenance/parent accepted")
            bad = deepcopy(original)
            bad["routes"][0]["model_version"] = "tampered"
            settings.foundry_inventory_path.write_text(json.dumps(bad))
            assert AcceptedInventory.load(settings).route(bad["routes"][0]["alias"]) is None
            settings.foundry_inventory_path.write_text(json.dumps(original))
            ext["routes"][0]["metadata_renewal"]["observed_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
            settings.external_inventory_path.write_text(json.dumps(ext))
            assert AcceptedInventory.load(settings).route("glm-5.3") is None
    print(json.dumps({"persistence_attestation": mode, "exact_code_delta_verified": True,
                      "unchanged_inventory_catalog": True, "all13_100days": mode == "after"}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])