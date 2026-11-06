"""Synthetic local source acceptance; no Feature2, cloud, DB migration or inference."""
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aiflux import auto_pricing, auto_snapshot, completion_limits, default_limits
from aiflux.config import Settings
from aiflux.external_inventory import AcceptedInventory

ROOT = Path(__file__).resolve().parents[2]


def install(settings, tmp_path, aliases, allowance=4096, provider_limit=8192):
    path = tmp_path / "synthetic-completion-limits.json"
    value = {"schema": 1, "allowance": allowance,
             "provider_limits": {alias: provider_limit for alias in aliases}}
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    settings.gateway_completion_limits_path = path
    settings.gateway_max_completion_tokens = allowance
    return value


@pytest.mark.parametrize("allowance", [1, 1024, 1025, 4096])
def test_allowance_boundaries_and_provider_min(tmp_path, allowance):
    settings = Settings(_env_file=None)
    install(settings, tmp_path, {"a", "b"}, allowance)
    limits = completion_limits.load(settings, {"a", "b"})
    assert completion_limits.effective(settings, "a", 1024, limits) == allowance
    value = json.loads(settings.gateway_completion_limits_path.read_text())
    value["provider_limits"]["a"] = 512
    settings.gateway_completion_limits_path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    assert completion_limits.effective(settings, "a", 1024,
        completion_limits.load(settings, {"a", "b"})) == min(allowance, 512)


@pytest.mark.parametrize("bad", [4097, 0, -1, True, 4096.0, "4096", None])
def test_invalid_allowance_never_coerced(tmp_path, bad):
    settings = Settings(_env_file=None)
    value = install(settings, tmp_path, {"a"})
    value["allowance"] = bad
    settings.gateway_completion_limits_path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    with pytest.raises((ValueError, ValidationError)):
        completion_limits.load(settings, {"a"})


@pytest.mark.parametrize("bad", [True, 1.5, "4096", 0, -1, 1000001, None])
def test_invalid_provider_limits(tmp_path, bad):
    settings = Settings(_env_file=None)
    value = install(settings, tmp_path, {"a"})
    value["provider_limits"]["a"] = bad
    settings.gateway_completion_limits_path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    with pytest.raises(ValueError):
        completion_limits.load(settings, {"a"})


def test_contract_missing_extra_duplicate_oversize_and_mismatch_fail_closed(tmp_path):
    settings = Settings(_env_file=None)
    install(settings, tmp_path, {"a"})
    for aliases in ({"a", "b"}, set()):
        with pytest.raises(ValueError, match="exact accepted"):
            completion_limits.load(settings, aliases)
    settings.gateway_max_completion_tokens = 1024
    with pytest.raises(ValueError, match="disagree"):
        completion_limits.load(settings, {"a"})
    for raw in ('{"schema":1,"schema":1}', ' ' * 16384):
        settings.gateway_completion_limits_path.write_text(raw)
        with pytest.raises(ValueError):
            completion_limits.load(settings, {"a"})


def test_historical_fallback_and_live_verification_not_fabricated():
    settings = Settings(_env_file=None, gateway_max_completion_tokens=4096)
    assert completion_limits.effective(settings, "a", 1024) == 1024
    assert completion_limits.snapshot_version("original", None) == "original"
    status = default_limits.global_defaults_status(None, 0, None)
    assert status["completion_allowance"] == 1024
    assert status["completion_4096_verified"] is False


def test_auto_snapshot_and_price_republication_cannot_reset_cap(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, environment="testing", local_auth_enabled=True,
        foundry_inventory_path=ROOT / "gateway/catalog/foundry-inventory-20261026.json")
    inventory = AcceptedInventory.load(settings)
    aliases = inventory.accepted_aliases(settings)
    before = auto_snapshot.defaults(settings)
    frozen = settings.foundry_inventory_path.read_bytes()
    install(settings, tmp_path, aliases)
    after = auto_snapshot.defaults(settings)
    assert after["profiles"] == before["profiles"]
    assert len(after["candidates"]) == 6 and len(after["profiles"]) == 3
    assert {c["max_completion_tokens"] for c in after["candidates"]} == {4096}
    assert after["version"] != before["version"]
    original = hashlib.sha256(auto_snapshot.files("aiflux").joinpath(
        "pricing/auto-routing-defaults.json").read_bytes()).hexdigest()
    digest = hashlib.sha256(settings.gateway_completion_limits_path.read_bytes()).hexdigest()
    assert after["version"] == hashlib.sha256(f"{original}:{digest}".encode()).hexdigest()
    monkeypatch.setattr(auto_pricing.rate_card, "accepted_scopes", lambda _: [(a, {}) for a in aliases])
    monkeypatch.setattr(auto_pricing.rate_card, "display_price", lambda *a: None)
    for version in (0, 1, 2):
        projection = auto_pricing.projection(settings, version, [])
        assert projection["pool_version"] == after["version"]
        assert len(projection["prices"]) == 6
        assert {c["max_completion_tokens"] for c in auto_snapshot.defaults(settings)["candidates"]} == {4096}
    assert settings.foundry_inventory_path.read_bytes() == frozen


def test_successor_cannot_reuse_old_publication_receipt(tmp_path):
    settings = Settings(_env_file=None, environment="testing", local_auth_enabled=True,
        foundry_inventory_path=ROOT / "gateway/catalog/foundry-inventory-20261026.json")
    before = auto_snapshot.defaults(settings)
    settings.auto_routing_published_policy_sha256 = "a" * 64
    receipt = {"schema": 1, "snapshot_version": before["version"], "policy_sha256": "a" * 64,
        "gateway_runtime_evidence_sha256": "b" * 64, "authorization_evidence_sha256": "c" * 64,
        "endpoint": auto_snapshot.ENDPOINT, "deployment": "Decision-1",
        "gateway_principal": auto_snapshot.GATEWAY_PRINCIPAL, "gateway_client": auto_snapshot.GATEWAY_CLIENT,
        "response_contract": "systemone-choice-probabilities-v1", "runtime_verified": True}
    settings.auto_routing_publication_json = json.dumps(receipt)
    assert auto_snapshot.publication(settings, before) is not None
    install(settings, tmp_path, AcceptedInventory.load(settings).accepted_aliases(settings))
    assert auto_snapshot.publication(settings, auto_snapshot.defaults(settings)) is None


def test_catalog_uses_shared_allowance_not_stale_1024_metadata(env, tmp_path):
    env.settings.gateway_max_completion_tokens = 4096
    install(env.settings, tmp_path, {"test-alias"})
    catalog = json.loads(env.settings.catalog_path.read_text())
    catalog["models"][0]["max_completion_tokens"] = 1024
    env.settings.catalog_path.write_text(json.dumps(catalog))
    response = env.client.get("/api/models", headers=env.customer)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["max_completion_tokens"] == 4096
    assert env.settings.model_access_enabled is False


def test_gateways_use_one_per_route_ceiling_and_preserve_reject_and_native_translation():
    tf = (ROOT / "infra/project-route/main.tf").read_text()
    auto = (ROOT / "infra/project-route/auto-routing.tf").read_text()
    policy = (ROOT / "gateway/policies/dev-openai.xml.tftpl").read_text()
    assert "modelMaximum = ${local.effective_completion_limits[alias]}" in tf
    assert "modelMaximum = ${local.effective_completion_limits[alias]}" in auto
    assert ": local.effective_completion_limits[alias]" in auto
    assert 'request[\\"max_tokens\\"] = request[\\"max_completion_tokens\\"]' in tf
    assert 'request.Remove(\\"max_completion_tokens\\")' in tf
    assert 'window-size="1000" window-overlap-size="100"' in policy
    assert 'buffer-response="true"' in policy
    assert 'body["max_completion_tokens"].Type != JTokenType.Integer' in policy
    assert '(int)body["max_completion_tokens"] > modelMaximum' in policy


@pytest.mark.parametrize("schema", [True, "1", 1.0, 2, None])
def test_schema_is_exact_integer_one(tmp_path, schema):
    settings = Settings(_env_file=None)
    value = install(settings, tmp_path, {"a"})
    value["schema"] = schema
    settings.gateway_completion_limits_path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    with pytest.raises(ValueError):
        completion_limits.load(settings, {"a"})


def test_unknown_fields_and_noncanonical_contract_fail_closed(tmp_path):
    settings = Settings(_env_file=None)
    value = install(settings, tmp_path, {"a"})
    path = settings.gateway_completion_limits_path
    path.write_text(json.dumps(value, indent=2))
    with pytest.raises(ValueError, match="canonical"):
        completion_limits.load(settings, {"a"})
    value["runtime_verified"] = True
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    with pytest.raises(ValueError):
        completion_limits.load(settings, {"a"})


def test_catalog_invalid_contract_is_503_not_stale_success(env, tmp_path):
    install(env.settings, tmp_path, {"wrong-alias"})
    response = env.client.get("/api/models", headers=env.customer)
    assert response.status_code == 503
    assert response.json()["detail"] == "Completion limit configuration is unavailable"


def test_garden_projects_single_contract_and_keeps_provider_ceiling(env, tmp_path, monkeypatch):
    from sqlalchemy.orm import Session
    from aiflux.models import ManagedModelEndpoint
    from aiflux.turnstile_exchange import list_model_garden
    install(env.settings, tmp_path, {"test-alias"}, provider_limit=2048)
    with Session(env.db_engine) as db:
        db.add(ManagedModelEndpoint(id="test-alias", display_name="Synthetic", provider="Test", vendor="Test",
            backend_model="test-model", endpoint_url="https://gateway.test/v1", enabled=True,
            capabilities_json='["chat"]', max_completion_tokens=1024))
        db.commit()
        calls = []
        original = completion_limits.load
        def capture(*args):
            calls.append(1)
            return original(*args)
        monkeypatch.setattr(completion_limits, "load", capture)
        items = list_model_garden(db, env.settings)
        assert len(calls) == 1
        chat = [item for item in items if item.id == "test-alias"]
        assert len(chat) == 1
        assert chat[0].max_completion_tokens == 2048
        assert {item.id for item in items} == {"test-alias", "Decision-1"}
        assert env.settings.model_access_enabled is False