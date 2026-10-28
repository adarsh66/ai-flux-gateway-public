import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from aiflux.external_inventory import AcceptedInventory, ExternalInventory, ExternalRoute, GATEWAY
from aiflux.models import ManagedModelEndpoint
from pydantic import ValidationError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]


def external(env, tmp_path, accepted=False):
    data = json.loads((ROOT / "gateway/catalog/external-inventory.json").read_text())
    data["routes"][0].pop("metadata_renewal", None)
    # Release evidence may now be accepted. Fixtures must explicitly construct
    # their pending state rather than depend on mutable live release status.
    data["routes"][0].update(gateway_validated=False, credential_healthy=False,
        probe_status=None, probe_prompt_tokens=None, probe_completion_tokens=None,
        probe_total_tokens=None, assistant_nonempty=False, verified_at=None)
    if accepted:
        data["routes"][0].update(gateway_validated=True, credential_healthy=True, probe_status=200,
            probe_prompt_tokens=5, probe_completion_tokens=10, probe_total_tokens=15,
            assistant_nonempty=True, verified_at=datetime.now(UTC).isoformat())
    path = tmp_path / "external.json"
    path.write_text(json.dumps(data))
    env.settings.external_inventory_path = path
    return data


def allow_catalog(env):
    data = json.loads(env.settings.catalog_path.read_text())
    data["models"].append({"id": "glm-5.3", "provider": "ModelArts", "backend_model": "glm-5.3",
        "enabled": True, "capabilities": ["chat"], "max_completion_tokens": 1024})
    env.settings.catalog_path.write_text(json.dumps(data))


def test_pending_external_is_discovery_only_and_foundry_unchanged(env, tmp_path):
    external(env, tmp_path)
    inventory = AcceptedInventory.load(env.settings)
    assert inventory.route("test-alias") is not None
    assert inventory.route("glm-5.3") is None
    row = next(r for r in inventory.discovery() if r["id"] == "glm-5.3")
    assert not row["chat_selectable"] and not row["credential_healthy"]
    assert row["status"] == "pending-verification"
    assert "vault" not in json.dumps(row).lower()
    assert "glm-5.3" not in inventory.accepted_aliases(env.settings)


@pytest.mark.parametrize("field,value", [
    ("upstream_url", "https://evil.invalid/v1"), ("upstream_url", "http://api-ap-southeast-1.modelarts-maas.com/v1"),
    ("endpoint_url", "https://api-ap-southeast-1.modelarts-maas.com/v1"), ("alias", "test-alias"),
    ("backend_model", "another-model"), ("capabilities", ["chat", "stream"]),
    ("capabilities", ["chat", "chat"]), ("max_completion_tokens", 1025),
    ("api_key", "synthetic-placeholder-not-a-real-key"), ("key_vault_secret_id", "not-permitted"),
    ("upstream_token_parameter", "max_tokens"), ("gateway_validated", True),
])
def test_invalid_external_fails_glm_only(env, tmp_path, field, value):
    data = external(env, tmp_path)
    data["routes"][0][field] = value
    with pytest.raises(ValidationError):
        ExternalInventory.model_validate(data)
    env.settings.external_inventory_path.write_text(json.dumps(data))
    inventory = AcceptedInventory.load(env.settings)
    assert inventory.route("glm-5.3") is None
    assert inventory.route("test-alias") is not None


def test_accepted_sync_idempotent_gateway_only_unknown_prices_and_no_fake_deployment(env, tmp_path):
    external(env, tmp_path, True)
    allow_catalog(env)
    first = env.client.post("/api/admin/model-deployments/sync", headers=env.admin)
    assert first.status_code == 200, first.text
    assert "glm-5.3" in first.json()["accepted_models"]
    assert env.client.post("/api/admin/model-deployments/sync", headers=env.admin).json()["changed"] == []
    models = env.client.get("/api/models", headers=env.customer).json()["items"]
    assert next(m for m in models if m["id"] == "glm-5.3")["capabilities"] == ["chat"]
    garden = env.client.get("/api/model-garden", headers=env.customer).json()["items"]
    glm = next(m for m in garden if m["id"] == "glm-5.3")
    assert glm["input_per_million"] is None and glm["output_per_million"] is None
    assert glm["context_window"] is None and glm["endpoint_url"] == GATEWAY
    with Session(env.db_engine) as db:
        row = db.get(ManagedModelEndpoint, "glm-5.3")
        row.enabled, row.priority, row.display_name = False, 9, "Operator GLM"
        db.commit()
    env.client.post("/api/admin/model-deployments/sync", headers=env.admin)
    with Session(env.db_engine) as db:
        row = db.get(ManagedModelEndpoint, "glm-5.3")
        assert not row.enabled and row.priority == 9 and row.display_name == "Operator GLM"


@pytest.mark.parametrize("delta", [timedelta(days=-2), timedelta(minutes=5)])
def test_stale_or_future_external_evidence_does_not_hide_foundry(env, tmp_path, delta):
    data = external(env, tmp_path, True)
    data["routes"][0]["verified_at"] = (datetime.now(UTC) + delta).isoformat()
    env.settings.external_inventory_path.write_text(json.dumps(data))
    inventory = AcceptedInventory.load(env.settings)
    assert inventory.route("glm-5.3") is None and inventory.route("test-alias") is not None


def test_duplicate_external_and_cross_provider_aliases_rejected(env, tmp_path):
    data = external(env, tmp_path, True)
    with pytest.raises(ValidationError):
        ExternalInventory.model_validate({**data, "routes": data["routes"] * 2})
    foundry = json.loads(env.settings.foundry_inventory_path.read_text())
    foundry["routes"][0]["alias"] = "glm-5.3"
    env.settings.foundry_inventory_path.write_text(json.dumps(foundry))
    inventory = AcceptedInventory.load(env.settings)
    assert inventory.external.routes == []
    assert inventory.route("glm-5.3").deployment_id  # Still Foundry, not a shadow external route.


def test_missing_external_file_preserves_foundry(env, tmp_path):
    env.settings.external_inventory_path = tmp_path / "missing.json"
    assert AcceptedInventory.load(env.settings).route("test-alias") is not None


@pytest.mark.parametrize("field,value", [("probe_status", None), ("probe_total_tokens", 1),
    ("credential_healthy", False), ("assistant_nonempty", False), ("probe_completion_tokens", 201)])
def test_acceptance_requires_real_bounded_metered_evidence(env, tmp_path, field, value):
    data = external(env, tmp_path, True)
    data["routes"][0][field] = value
    with pytest.raises(ValidationError):
        ExternalRoute.model_validate(data["routes"][0])