"""Availability provenance is not an authorization or credential lease."""
from datetime import UTC, datetime, timedelta
import json

import pytest

from aiflux.external_inventory import AcceptedInventory
from test_foundry_inventory import rewrite
from test_external_inventory import external, allow_catalog


@pytest.mark.parametrize("days", [2, 100, 3650])
@pytest.mark.parametrize("deadline", [None, "2020-01-01T00:00:00Z", "2099-01-01T00:00:00Z"])
def test_old_acceptance_survives_without_restamp_across_customer_paths(env, tmp_path, days, deadline):
    stamp = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    rewrite(env, lambda d: (d.update(verified_at=stamp), d["routes"][0].update(expires_at=deadline)))
    data = external(env, tmp_path, True)
    data["routes"][0]["verified_at"] = stamp
    env.settings.external_inventory_path.write_text(json.dumps(data))
    allow_catalog(env)
    env.settings.foundry_inventory_max_age_seconds = 1  # Compatibility setting is not a lease.
    inventory = AcceptedInventory.load(env.settings)
    assert inventory.verified_at.isoformat() == stamp
    assert inventory.route("test-alias") is not None
    assert inventory.route("glm-5.3") is not None
    for path in ("/api/models", "/api/model-garden", "/api/model-router"):
        assert env.client.get(path, headers=env.customer).status_code == 200
    # No provider traffic: request reaches existing model validation, not inventory503.
    chat = env.client.post("/api/playground/chat", headers=env.customer,
        json={"model": "not-accepted", "messages": [{"role": "user", "content": "Hello"}]})
    assert chat.status_code == 422
    assert not env.client.get("/api/models").is_success  # Authentication still required.
    assert all(not row["fresh_credential_health_verified"] for row in inventory.discovery() if row["id"] == "glm-5.3")


def test_naive_legacy_deadline_does_not_authorize_route(env):
    rewrite(env, lambda d: d["routes"][0].update(expires_at="2020-01-01T00:00:00"))
    assert AcceptedInventory.load(env.settings).route("test-alias") is None


@pytest.mark.parametrize("field,value", [("gateway_validated", False), ("backend_model", "tampered"), ("model_version", "tampered")])
def test_old_evidence_never_bypasses_disable_or_route_contract(env, field, value):
    rewrite(env, lambda d: (d.update(verified_at="2020-01-01T00:00:00Z"), d["routes"][0].update({field: value})))
    assert AcceptedInventory.load(env.settings).route("test-alias") is None