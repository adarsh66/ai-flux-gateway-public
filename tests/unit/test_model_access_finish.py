"""Additional offline reconciliation proofs; no live schema or resource writes."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text

from aiflux import model_access as ma
from aiflux.models import ModelAccessPublication
from fastapi import HTTPException
from tests.unit.test_model_access import access, save


def test_empty_catalog_saves_and_publishes_zero_choices(access):
    access.models.clear()
    assert save(access)["version"] == 1
    assert ma.compile_projection(access.db, [])["catalog"] == []


def test_reason_cannot_be_whitespace():
    with pytest.raises(ValidationError):
        ma.AccessUpdate(expected_version=0, denied_models=[], reason="   ")


def test_future_alias_waits_for_publication_and_corruption_fails_closed(access):
    save(access)
    job = access.db.get(ModelAccessPublication, "default")
    job.applied_json = ma.compact(ma.compile_projection(access.db, ["a", "b"]))
    access.db.commit()
    assert ma.filter_items(access.db, access.oid, [{"id": "future"}, {"id": "b"}]) == [{"id": "b"}]
    with pytest.raises(HTTPException) as exc:
        ma.require_model(access.db, access.oid, "future")
    assert exc.value.status_code == 403
    job.applied_json = job.applied_json.replace('"generation":0', '"generation":1')
    access.db.commit()
    with pytest.raises(HTTPException) as exc:
        ma.filter_items(access.db, access.oid, [{"id": "b"}])
    assert exc.value.status_code == 503


def test_catalog_capacity_is_not_truncated(access):
    with pytest.raises(ValueError):
        ma.compile_projection(access.db, [f"m{x}" for x in range(201)])


@pytest.mark.parametrize("applied,denied,ready", [([], [], False), (["a"], ["a"], False), (["a"], [], True)])
def test_auto_availability_requires_applied_allowed_candidate(env, monkeypatch, applied, denied, ready):
    from aiflux import auto_snapshot, decision_router
    env.settings.model_access_enabled = True
    monkeypatch.setattr(decision_router, "availability", lambda *_: {"ready": True})
    monkeypatch.setattr(auto_snapshot, "defaults", lambda *_: {"candidates": [{"id": "a"}]})
    monkeypatch.setattr(ma, "effective", lambda *_: {"bootstrap_pending": False, "auto_enabled": True,
        "denied_models": denied, "applied_catalog": applied})
    response = env.client.get("/api/auto-routing/availability", headers=env.customer)
    assert response.status_code == 200
    assert response.json()["ready"] is ready


def test_catalog_price_badges_are_metadata_not_entitlements(monkeypatch):
    from aiflux import turnstile_exchange, external_pricing
    model = SimpleNamespace(id="a", display_name="A", vendor="provider", enabled=True,
                            coming_soon=False, capabilities=["chat"], display_price=None)
    monkeypatch.setattr(turnstile_exchange, "list_model_garden", lambda *a, **k: [model])
    monkeypatch.setattr(external_pricing, "snapshot", lambda *a, **k: None)
    row = ma.catalog(None, None, "org")[0]
    assert row["model_kind"] == "chat" and row["globally_enabled"]
    assert not row["internal_price_available"] and not row["external_price_available"]


def test_frozen_additive_migration_executes_without_financial_changes():
    path = Path(__file__).resolve().parents[2] / "services/control-plane/migrations/versions/0005_organization_model_access.py"
    spec = importlib.util.spec_from_file_location("feature2_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE financial_sentinel (balance INTEGER NOT NULL)"))
        conn.execute(text("INSERT INTO financial_sentinel VALUES (42)"))
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
        assert set(inspect(conn).get_table_names()) == {"organizations", "financial_sentinel",
            "organization_model_access", "organization_model_access_revisions", "model_access_publication"}
        assert conn.scalar(text("SELECT balance FROM financial_sentinel")) == 42
        assert inspect(conn).get_foreign_keys("organization_model_access")[0]["referred_table"] == "organizations"
    engine.dispose()