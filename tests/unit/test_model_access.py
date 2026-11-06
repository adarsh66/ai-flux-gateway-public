"""Focused source-only SQLite contracts. Never contacts Azure or providers."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from aiflux import model_access as ma
from aiflux.auth import Principal
from aiflux.models import (Base, Organization, TeamSubscription, OrganizationModelAccessRevision,
                           ModelAccessPublication, CreditBudget)
from aiflux.settings_envelope import render, parse


@pytest.fixture
def access(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        oid, other, sid = (str(uuid4()) for _ in range(3))
        db.add_all([Organization(id=o, name=o, tenant_id=str(uuid4())) for o in (oid, other)])
        db.flush()
        db.add(TeamSubscription(id=sid, organization_id=oid, name="t", team="t", state="active",
                                desired_state="active", idempotency_key=str(uuid4())))
        db.commit()
        models = [{"id": a, "display_name": a, "provider": "test", "globally_enabled": True, "model_kind": "chat"}
                  for a in ("a", "b")]
        monkeypatch.setattr(ma, "catalog", lambda *_: models)
        yield SimpleNamespace(db=db, oid=oid, other=other, sid=sid, models=models,
            settings=SimpleNamespace(), admin=Principal(oid, "t", str(uuid4()), str(uuid4()), "ids_admin"))
    engine.dispose()


def save(p, denies=(), version=0, auto=True):
    return ma.save_access(p.db, p.settings, p.admin, p.oid,
                         ma.AccessUpdate(expected_version=version, denied_models=list(denies), auto_enabled=auto, reason="test"))


def test_default_future_read_only_and_financial_unchanged(access):
    p = access
    assert ma.get_access(p.db, p.settings, p.admin, p.oid)["denied_models"] == []
    assert p.db.scalar(select(func.count()).select_from(OrganizationModelAccessRevision)) == 0
    assert p.db.scalar(select(func.count()).select_from(CreditBudget)) == 0
    save(p, ["a"])
    job = p.db.get(ModelAccessPublication, "default")
    job.applied_json = ma.compact(ma.compile_projection(p.db, ["a", "b", "future"]))
    p.db.commit()
    assert ma.filter_items(p.db, p.oid, [{"id": "a"}, {"id": "b"}, {"id": "future"}]) == [{"id": "b"}, {"id": "future"}]
    assert ma.preference(p.db, p.other)["denied_models"] == []
    assert p.db.scalar(select(func.count()).select_from(CreditBudget)) == 0


@pytest.mark.parametrize("denies", [["*"], ["unknown"], ["a", "a"], ["auto"], ["Decision-1"]])
def test_invalid_denies_atomic(access, denies):
    with pytest.raises(HTTPException) as exc:
        save(access, denies)
    assert exc.value.status_code == 422
    assert ma.preference(access.db, access.oid)["version"] == 0


def test_cas_retired_denies_and_auto_independent(access):
    p = access
    assert save(p, ["a"], auto=False)["state"] == "pending"
    with pytest.raises(HTTPException) as exc:
        save(p, [], version=0)
    assert exc.value.status_code == 409
    p.models.pop(0)
    save(p, ["a"], version=1)
    assert ma.preference(p.db, p.oid)["denied_models"] == ["a"]
    with pytest.raises(HTTPException):
        ma.require_model(p.db, p.oid, "a", requested="auto")
    assert ma.filter_items(p.db, p.oid, [{"id": "b"}]) == []


def test_legacy_empty_and_wildcard_import_idempotent_no_financial_writes(access):
    p = access
    budget = CreditBudget(organization_id=p.oid, subscription_id=None, allowed_models_json="[]")
    p.db.add(budget)
    p.db.commit()
    original = budget.monthly_budget_usd
    preview = ma.review_legacy(p.db, p.oid, ["a", "b"])
    assert preview["denied_models"] == ["a", "b"] and not preview["auto_enabled"]
    for _ in range(2):
        ma.import_legacy(p.db, p.settings, p.admin, p.oid, expected_version=0,
                         reviewed_sha256=preview["review_sha256"], reason="Reviewed empty restriction")
    assert ma.preference(p.db, p.oid)["version"] == 1
    assert budget.allowed_models_json == "[]" and budget.monthly_budget_usd == original
    budget.allowed_models_json = '["*"]'
    p.db.commit()
    assert ma.review_legacy(p.db, p.oid, ["a", "b"])["denied_models"] == []
    with pytest.raises(HTTPException):
        ma.import_legacy(p.db, p.settings, p.admin, p.oid, expected_version=1,
                         reviewed_sha256=preview["review_sha256"], reason="Stale")


def test_auth_uuid_disabled_and_spoof(access):
    p = access
    customer = Principal(p.oid, "t", str(uuid4()), str(uuid4()), "customer")
    with pytest.raises(HTTPException) as exc:
        ma.get_access(p.db, p.settings, customer, p.other)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        ma.organization(p.db, "not-a-uuid")
    p.db.get(Organization, p.oid).enabled = False
    p.db.commit()
    with pytest.raises(HTTPException) as exc:
        ma.filter_items(p.db, p.oid, [{"id": "a"}])
    assert exc.value.status_code == 403


def test_projection_mapping_deny_global_and_integrity(access):
    p = access
    save(p, ["a"])
    value = ma.compile_projection(p.db, ["a", "b"])
    assert value["bindings"] == {p.sid: p.oid}
    assert ma.authorize_projection(value, p.sid, "b")
    for selected in ("a", "globally-disabled"):
        with pytest.raises(HTTPException) as exc:
            ma.authorize_projection(value, p.sid, selected)
        assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        ma.authorize_projection(value, str(uuid4()), "b")
    assert exc.value.status_code == 503
    value["organizations"][p.oid]["denied_models"] = []
    with pytest.raises(HTTPException) as exc:
        ma.authorize_projection(value, p.sid, "a")
    assert exc.value.status_code == 503


def test_pending_grant_conservative(access):
    p = access
    save(p, ["a"], auto=False)
    job = p.db.get(ModelAccessPublication, "default")
    job.applied_json = ma.compact(ma.compile_projection(p.db, ["a", "b"]))
    job.state = "applied"
    p.db.commit()
    save(p, [], version=1)
    assert ma.effective(p.db, p.oid)["denied_models"] == ["a"]
    assert ma.effective(p.db, p.oid)["auto_enabled"] is False


@pytest.mark.parametrize("price,entitlement", [(None, None), ({"x": "price"}, None), (None, {"x": "access"}), ({"x": "price"}, {"x": "access"})])
def test_envelope_modes_roundtrip_siblings(price, entitlement):
    controls = '<fragment><quota-by-key calls="50000" renewal-period="86400" counter-key="original" /></fragment>'
    value = render(controls, price, entitlement)
    plain, got_price, got_access = parse(value)
    assert got_price == price and got_access == entitlement
    assert "50000" in plain
    assert parse(render(plain, {"new": 1}, got_access))[2] == entitlement
    assert len(value.encode()) <= 65536


def test_envelope_oversize_and_malformed_reject():
    with pytest.raises(ValueError):
        render("<fragment />", None, {"large": "x" * 65536})
    with pytest.raises(ValueError):
        parse(render("<fragment />", {}, {}).replace('value="2"', 'value="3"'))


def test_alembic_only_new_additive_head():
    root = Path(__file__).resolve().parents[2]
    cfg = Config()
    cfg.set_main_option("script_location", str(root / "services/control-plane/migrations"))
    scripts = ScriptDirectory.from_config(cfg)
    # Monthly advisory budgets are an independent sibling; this does not
    # execute or enable the paused model-access branch.
    assert set(scripts.get_heads()) == {"0005_org_model_access", "0007_admin_archival"}
    assert scripts.get_revision("0007_admin_archival").down_revision == "0006_monthly_advisory_budgets"
    assert scripts.get_revision("0005_org_model_access").down_revision == "0004_external_pricing"