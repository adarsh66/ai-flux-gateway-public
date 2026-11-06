"""Synthetic release receipts and offline source contracts; never live proof."""
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux import auto_snapshot, decision_router
from aiflux.config import Settings
from aiflux.models import ModelRouterConfig

ROOT = Path(__file__).resolve().parents[2]


def configured():
    return Settings(_env_file=None, environment="testing", local_auth_enabled=True,
        foundry_inventory_path=ROOT / "gateway/catalog/foundry-inventory-20261026.json")


def receipt(settings, tmp_path):
    snapshot = auto_snapshot.defaults(settings)
    settings.auto_routing_publication_path = tmp_path / "synthetic-receipt.json"
    settings.auto_routing_published_policy_sha256 = "a" * 64
    value = {"schema": 1, "snapshot_version": snapshot["version"], "policy_sha256": "a" * 64,
        "gateway_runtime_evidence_sha256": "b" * 64, "authorization_evidence_sha256": "c" * 64,
        "endpoint": auto_snapshot.ENDPOINT, "deployment": "Decision-1",
        "gateway_principal": auto_snapshot.GATEWAY_PRINCIPAL, "gateway_client": auto_snapshot.GATEWAY_CLIENT,
        "response_contract": "systemone-choice-probabilities-v1", "runtime_verified": True}
    settings.auto_routing_publication_path.write_text(json.dumps(value), encoding="utf-8")
    return snapshot, value


def test_three_shared_defaults_deterministic_no_db_or_subscription_ids():
    settings = configured()
    first = auto_snapshot.defaults(settings)
    assert first == auto_snapshot.defaults(settings)
    assert set(first["profiles"]) == {"balanced", "cost", "quality"}
    for profile in first["profiles"].values():
        assert 2 <= len(profile["candidate_models"]) <= 10
        assert profile["fallback_model"] in profile["candidate_models"]
    assert set(c["id"] for c in first["candidates"]) == set(decision_router.STARTERS)
    assert "subscription" not in json.dumps(first)
    assert "benchmark quality" in first["profiles"]["quality"]["instructions"]


def test_omitted_profile_balanced_and_no_legacy_api_required(tmp_path):
    settings = configured()
    settings.entra_audience = "local://not-an-entra-resource"
    settings.auto_gateway_principal_id = settings.auto_gateway_client_id = ""
    snapshot, _ = receipt(settings, tmp_path)
    settings.auto_routing_enabled = True
    assert decision_router.availability(None, settings) == {"ready": True, "profiles": list(decision_router.PROFILES),
        "config_version": snapshot["version"], "architecture": "gateway-direct", "max_completion_tokens": 1024}
    assert decision_router.ResolveRequest(subscription_id="new", messages=[{"role": "user", "content": "Hi"}],
        max_completion_tokens=20).routing_profile == "balanced"


def test_flags_alone_never_expose_auto():
    settings = configured()
    settings.auto_routing_enabled = settings.auto_routing_gateway_ready = settings.auto_routing_contract_verified = True
    assert decision_router.availability(None, settings) == {"ready": False, "profiles": []}


@pytest.mark.parametrize("field,value", [("snapshot_version", "x" * 64), ("policy_sha256", "d" * 64),
    ("gateway_runtime_evidence_sha256", ""), ("authorization_evidence_sha256", "fixture"),
    ("runtime_verified", False), ("runtime_verified", "true"), ("gateway_principal", "wrong"),
    ("gateway_client", "wrong"), ("endpoint", "https://evil.invalid"), ("deployment", "other"),
    ("response_contract", "unproven"), ("schema", 2)])
def test_mismatched_release_receipt_fails_closed(tmp_path, field, value):
    settings = configured()
    _, data = receipt(settings, tmp_path)
    data[field] = value
    settings.auto_routing_publication_path.write_text(json.dumps(data), encoding="utf-8")
    settings.auto_routing_enabled = True
    assert decision_router.availability(None, settings)["ready"] is False


def test_elapsed_metadata_does_not_retire_platform_defaults(tmp_path):
    settings = configured()
    snapshot, data = receipt(settings, tmp_path)
    data.update(verified_at="2000-01-01T00:00:00Z", expires_at="2000-01-02T00:00:00Z")
    settings.auto_routing_publication_path.write_text(json.dumps(data), encoding="utf-8")
    assert auto_snapshot.publication(settings, snapshot) is not None


def test_unknown_prices_excluded_from_cost_not_other_profiles(monkeypatch):
    original = auto_snapshot.accepted_catalog_price
    monkeypatch.setattr(auto_snapshot, "accepted_catalog_price", lambda inv, alias, backend, url:
        None if alias == "gpt-6.1-sol" else original(inv, alias, backend, url))
    snapshot = auto_snapshot.defaults(configured())
    for name in ("balanced", "quality"):
        assert "gpt-6.1-sol" in snapshot["profiles"][name]["candidate_models"]
    assert "gpt-6.1-sol" not in snapshot["profiles"]["cost"]["candidate_models"]
    monkeypatch.setattr(auto_snapshot, "accepted_catalog_price", lambda *a: None)
    with pytest.raises(ValueError, match="default pool"):
        auto_snapshot.defaults(configured())


def test_changed_catalog_binding_does_not_silently_publish(tmp_path):
    settings = configured()
    copy = tmp_path / "catalog.json"
    copy.write_bytes(settings.foundry_inventory_path.read_bytes() + b" ")
    settings.foundry_inventory_path = copy
    with pytest.raises(ValueError, match="inputs changed"):
        auto_snapshot.defaults(settings)


def test_missing_configured_catalog_fails_readiness_closed(tmp_path):
    settings = configured()
    receipt(settings, tmp_path)
    settings.auto_routing_enabled = True
    settings.catalog_configured = True
    settings.catalog_path = tmp_path / "missing-catalog.json"
    assert decision_router.availability(None, settings) == {"ready": False, "profiles": []}


def test_production_catalog_eligibility_not_local_auth_bypass(tmp_path):
    settings = configured()
    inventory = auto_snapshot.AcceptedInventory.load(settings)
    catalog = {"models": [{"id": alias, "provider": inventory.provider(alias),
        "backend_model": inventory.foundry.route(alias).backend_model,
        "capabilities": ["chat"], "enabled": True, "max_completion_tokens": 1024}
        for alias in decision_router.STARTERS]}
    settings.environment = "production"
    settings.local_auth_enabled = False
    settings.catalog_configured = True
    settings.catalog_path = tmp_path / "synthetic-production-catalog.json"
    settings.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    snapshot, _ = receipt(settings, tmp_path)
    settings.auto_routing_enabled = True
    assert set(c["id"] for c in snapshot["candidates"]) == set(decision_router.STARTERS)
    assert decision_router.availability(None, settings)["ready"] is True
    # A release receipt cannot authorize a removed/disabled catalog candidate.
    next(m for m in catalog["models"] if m["id"] == "gpt-5.4-mini")["enabled"] = False
    settings.catalog_path = tmp_path / "disabled-catalog.json"
    settings.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    assert decision_router.availability(None, settings) == {"ready": False, "profiles": []}


def test_all_missing_db_profiles_use_defaults_no_get_writes(env):
    env.settings.foundry_inventory_path = configured().foundry_inventory_path
    env.settings.local_auth_enabled = True
    env.settings.catalog_configured = False
    before = env.client.get("/api/admin/auto-routing", headers=env.admin)
    assert before.status_code == 200, before.text
    assert len(before.json()["items"]) == 3
    assert all(p["source"] == "platform-default" and p["enabled"] for p in before.json()["items"])
    with Session(env.db_engine) as db:
        assert not list(db.scalars(select(ModelRouterConfig).where(ModelRouterConfig.id.like("auto-%"))))


def test_optional_first_save_creates_desired_override_without_seed(env, tmp_path):
    env.settings.foundry_inventory_path = configured().foundry_inventory_path
    env.settings.local_auth_enabled = True
    env.settings.catalog_configured = False
    snapshot, _ = receipt(env.settings, tmp_path)
    env.settings.auto_routing_enabled = True
    # Catalog DB rows are optional administrative metadata, not request-time
    # authorization. Use the reviewed platform descriptors in this unit fixture.
    from unittest.mock import patch
    with patch.object(decision_router, "candidates", return_value=snapshot["candidates"]):
        desired = env.client.put("/api/admin/auto-routing/cost", headers=env.admin, json={
            "enabled": False, "candidate_models": snapshot["profiles"]["cost"]["candidate_models"],
            "fallback_model": "gpt-5.4-mini", "expected_version": snapshot["version"]})
    assert desired.status_code == 200, desired.text
    assert desired.json()["publication_status"] == "desired-not-published"
    # A disabled desired Cost override cannot block Balanced or other defaults.
    assert decision_router.availability(None, env.settings)["profiles"] == list(decision_router.PROFILES)


def test_disabled_legacy_api_does_not_create_scoring_client(env):
    result = env.client.post("/internal/auto-routing/resolve", headers=env.admin, json={
        "subscription_id": "new", "messages": [{"role": "user", "content": "hello"}], "max_completion_tokens": 20})
    assert result.status_code in (401, 403, 503)
    assert env.app.state.auto_decision_client is None


def test_gateway_auth_authority_remains_product_not_static_tenant_list():
    source = (ROOT / "gateway/policies/dev-openai.xml.tftpl").read_text()
    assert 'context.Subscription == null || context.Product == null || context.Product.Id !=' in source
    auto = (ROOT / "gateway/policies/auto-resolve.xml.tftpl").read_text()
    assert "TeamSubscription" not in auto and "subscription_id" not in auto and "azurewebsites.net" not in auto
    app = (ROOT / "services/control-plane/src/aiflux/app.py").read_text()
    assert 'apim.ensure(row.id, row.name, "suspended")' in app
    assert "Portal access disabled; key suspension incomplete. Retry disable." in app
    # This proves the source contract only, not atomic DB/APIM organization disable.


def test_protected_inventory_modules_untouched():
    for name, digest in {"foundry_inventory.py": "712dc96d153cdce26aa41daf4d2f2dd2d93628565fd756c16920cf2f551595b9",
                         "external_inventory.py": "c6a7443a670f072e046093d83f794d8d9f42d7146d3c24b774dfa489d4fd2e4c"}.items():
        assert hashlib.sha256((ROOT / "services/control-plane/src/aiflux" / name).read_bytes()).hexdigest() == digest