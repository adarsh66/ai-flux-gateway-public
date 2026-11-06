"""Runs inside the immutable base/candidate, without credentials or network calls."""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(manifest_path, mode):
    manifest = json.loads(Path(manifest_path).read_text())
    entries = manifest["entries"]
    import aiflux
    installed = Path(aiflux.__file__).parent
    prefix = "services/control-plane/src/aiflux/"
    expected = {e["path"][len(prefix):]: e["sha256"] for e in entries if e["path"].startswith(prefix)}
    assert {p.relative_to(installed).as_posix() for p in installed.rglob("*.py")} == {p for p in expected if p.endswith(".py")}
    for name, value in expected.items():
        assert digest(Path("/app") / prefix / name) == value, "packaged source mismatch"
        if name.endswith(".py"):
            assert digest(installed / name) == value, "installed module mismatch"
    assert not any(name.startswith("decision_") for name in expected), "unshipped Auto is forbidden"
    assert os.environ["AIFLUX_FOUNDRY_INVENTORY_MAX_AGE_SECONDS"] == "86400"
    from aiflux.config import Settings
    from aiflux.external_inventory import AcceptedInventory
    from fastapi import HTTPException
    settings = Settings(_env_file=None, local_auth_enabled=True)
    foundry_path = settings.foundry_inventory_path
    external_path = settings.external_inventory_path
    assert str(foundry_path) == "/app/gateway/catalog/foundry-inventory-20261026.json"
    assert str(external_path) == "/app/gateway/catalog/external-inventory.json"
    foundry = json.loads(foundry_path.read_text())
    if mode == "before":
        by_path = {e["path"]: e["sha256"] for e in entries}
        for path in (foundry_path, external_path):
            assert digest(path) == by_path[path.relative_to("/app").as_posix()]
        try:
            AcceptedInventory.load(settings)
        except HTTPException as error:
            assert error.status_code == 503 and "inventory" in error.detail
        else:
            raise AssertionError("expired base must reproduce HTTP503")
    else:
        inventory = AcceptedInventory.load(settings)
        aliases = inventory.accepted_aliases(settings)
        expected_aliases = {r["alias"] for r in foundry["routes"]} | {"glm-5.3"}
        assert len(aliases) == 13 and aliases == expected_aliases
        assert "Decision-1" not in aliases and "auto" not in aliases
        assert all(inventory.route(alias) is not None for alias in aliases)
    print(json.dumps({"image_attestation": mode, "installed_and_packaged_api_sources_unchanged": True,
        "unshipped_auto_excluded": True, "ttl_seconds": settings.foundry_inventory_max_age_seconds,
        "foundry_sha256": digest(foundry_path), "external_sha256": digest(external_path),
        "verified_at": foundry["verified_at"], "at_utc": datetime.now(UTC).isoformat()}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])