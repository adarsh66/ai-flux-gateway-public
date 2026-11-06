"""Offline external price contract, sharing one small database/clock fixture."""
import importlib.util
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aiflux import external_pricing as ep, rate_card
from aiflux.auth import Principal
from aiflux.display_pricing import detail_estimates
from aiflux.models import (
    Base, ExternalPriceCard, ExternalPriceCardRevision, GatewaySettings, GatewaySettingsRevision,
    Organization, TeamSubscription, UsageRecord,
)

START = datetime(2026, 10, 1, tzinfo=UTC)
NOW = datetime(2026, 11, 2, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services/control-plane/migrations"


@pytest.fixture
def pricing(monkeypatch):
    clock = SimpleNamespace(now=NOW)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now

    monkeypatch.setattr(ep, "datetime", Clock)
    chat = dict(model="chat", provider="Test", region="test", model_version="v1", sku="test",
                input="1", output="2", cached="0.2", status="public_list", source="supplier",
                source_url="https://supplier.invalid", applicable_from=START.isoformat())
    scorer = dict(model="Decision-1", provider="Microsoft", region="global", model_version="v1", sku="test",
                  model_kind="scoring", billing_dimensions=["input"], input="5", status="public_list",
                  applicable_from=START.isoformat())
    bases = {rate_card.key_of(row): row for row in (chat, scorer)}
    scopes = [(row["model"], row) for row in (chat, scorer)]
    monkeypatch.setattr(rate_card, "base_scopes", lambda: bases)
    monkeypatch.setattr(rate_card, "listed_scopes", lambda settings: scopes)
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        orgs = [str(uuid4()), str(uuid4())]
        db.add_all([Organization(id=o, name=o, tenant_id=str(uuid4())) for o in orgs])
        db.commit()
        principal = Principal(orgs[0], "Test", str(uuid4()), str(uuid4()), "ids_admin")
        yield SimpleNamespace(db=db, engine=engine, settings=SimpleNamespace(), principal=principal,
                              org=orgs[0], other=orgs[1], clock=clock, chat=chat, scorer=scorer,
                              bases=bases, scopes=scopes)
    engine.dispose()


def save(p, *, org=None, version=0, model="chat", operation="set", **rates):
    return ep.save_external_card(p.db, p.settings, p.principal, ep.ExternalCardUpdate(
        expected_version=version, rates=[ep.ExternalRateUpdate(model=model, operation=operation, **rates)]), org)


def baseline(p):
    return ep.initialize_external_baseline(p.db, p.settings, p.principal)


def item(output, model="chat"):
    return next(row for row in output.items if row.model == model)


def price(p, org=None, at=None):
    return ep.snapshot(p.db, org, at).display_price(p.chat)


def test_missing_store_get_is_read_only_unknown(pricing):
    p = pricing
    card = ep.get_external_card(p.db, p.settings)
    assert card.version == 0 and item(card).input is None
    assert ep.estimate_args(p.db) == {"periods": [], "revision": "external:default:v0", "inventory": None}
    assert ep.display_price(p.db, None, p.chat) is None
    assert ep.snapshot(p.db).scoring_estimate(100, NOW)["estimated_cost_usd"] is None
    assert p.db.scalar(select(func.count()).select_from(ExternalPriceCard)) == 0
    assert p.db.scalar(select(func.count()).select_from(ExternalPriceCardRevision)) == 0


def test_baseline_idempotent_detached_and_supplier_free(pricing, monkeypatch):
    p = pricing
    first = baseline(p)
    context = ep.snapshot(p.db)
    assert first.version == 1 and first.changed
    assert baseline(p).version == 1 and not baseline(p).changed
    assert price(p)["input"] == "1"
    assert "supplier" not in json.dumps(price(p))
    assert "https://" not in json.dumps(price(p))
    assert ep.snapshot(p.db).scoring_estimate(1_000_000, NOW)["estimated_cost_usd"] == Decimal("5")
    p.bases.clear()
    monkeypatch.setattr(rate_card, "load_state", lambda *_: pytest.fail("internal pricing read"))
    monkeypatch.setattr(rate_card, "base_scopes", lambda: pytest.fail("internal defaults read"))
    assert price(p)["input"] == "1"
    assert context.display_price(p.chat) == price(p)
    assert ep.estimate_args(p.db)["periods"] == context.estimate_args()["periods"]
    assert baseline(p).version == 1


def test_full_vector_zero_null_unknown_reset_history_isolation(pricing):
    p = pricing
    baseline(p)
    p.clock.now += timedelta(days=1)
    t1 = p.clock.now
    out = save(p, org=p.org, input="0", output="0", cached=None)
    assert out.changed and out.version == 1 and item(out).input == "0"
    assert item(out).cached is None  # full replacement, not inherited 0.2
    assert price(p, p.other)["input"] == "1"
    assert price(p)["input"] == "1"
    assert price(p, p.org, t1 - timedelta(microseconds=1))["input"] == "1"
    assert price(p, p.org, t1)["input"] == "0"
    p.clock.now += timedelta(days=1)
    t2 = p.clock.now
    save(p, org=p.org, version=1, operation="unknown")
    assert price(p, p.org) is None
    p.clock.now += timedelta(days=1)
    save(p, version=1, input="8", output="9")
    assert price(p, p.org) is None  # terminal unknown masks changed default
    p.clock.now += timedelta(days=1)
    reset = p.clock.now
    save(p, org=p.org, version=2, operation="inherit")
    assert price(p, p.org)["input"] == "8"
    p.clock.now += timedelta(days=1)
    save(p, version=2, input="10", output="11")
    assert price(p, p.org)["input"] == "10"
    assert price(p, p.org, reset)["input"] == "8"
    assert price(p, p.org, t2) is None
    assert price(p, p.org, t1)["input"] == "0"
    assert ep.get_external_card(p.db, p.settings, p.other).version == 0


def test_history_export_estimator_and_unknown_masks(pricing):
    p = pricing
    baseline(p)
    p.db.add(TeamSubscription(id="sub", organization_id=p.org, name="t", team="t", state="active",
                              desired_state="active", idempotency_key=str(uuid4())))
    p.db.flush()

    def usage(id, at):
        p.db.add(UsageRecord(id=id, organization_id=p.org, subscription_id="sub", model="chat",
                            provider="Test", region="test", occurred_at=at, input_tokens=1_000_000,
                            output_tokens=1_000_000, cached_input_tokens=0, cache_write_tokens=0,
                            status_code=200, completeness="price_missing"))

    # Existing estimator's independent global applicability begins Oct 27.
    before = NOW - timedelta(days=1)
    usage("before", before)
    save(p, org=p.org, input="0", output="0")
    usage("zero", p.clock.now)
    p.clock.now += timedelta(days=1)
    save(p, org=p.org, version=1, operation="unknown")
    usage("unknown", p.clock.now)
    p.db.flush()
    result = detail_estimates(p.db, ["before", "zero", "unknown"], **ep.estimate_args(p.db, p.org))
    assert Decimal(result["before"]["estimated_cost_usd"]) == 3
    assert Decimal(result["zero"]["estimated_cost_usd"]) == 0
    assert result["unknown"]["estimated_cost_usd"] is None
    assert set(ep.estimate_args(p.db, p.org)) == set(rate_card.estimate_args(p.db))


def test_baseline_captures_pruned_historic_revisions_and_current(pricing):
    p = pricing
    p.db.add(GatewaySettings(scope="rate-card", version=2))
    p.db.flush()
    old_at, latest_at = START + timedelta(days=2), START + timedelta(days=4)
    for version, at, amount in [(1, old_at, "3"), (2, latest_at, "9")]:
        entry = dict(model="chat", provider="Test", region="test", origin="configured",
                     valid_from=at.isoformat(), input=amount, output=amount)
        p.db.add(GatewaySettingsRevision(scope="rate-card", version=version,
                                        configuration=json.dumps({"entries": [entry]}), reason="test",
                                        object_id=p.principal.object_id, state="published", base_hash="", base_etag=""))
    p.db.commit()
    baseline(p)
    assert price(p, at=START)["input"] == "1"
    assert price(p, at=old_at)["input"] == "3"
    assert price(p, at=latest_at)["input"] == "9"
    # Mutating/removing internal history after initialization cannot affect external snapshots.
    for row in p.db.scalars(select(GatewaySettingsRevision)):
        row.configuration = '{"entries": []}'
    p.db.commit()
    assert price(p, at=old_at)["input"] == "3"
    assert price(p)["input"] == "9"


def test_scoring_input_only_historical_unknown_and_real_zero(pricing):
    p = pricing
    baseline(p)
    context = ep.snapshot(p.db)
    assert context.scoring_estimate(0, NOW)["estimated_cost_usd"] == 0
    for invalid in [None, -1, True, 1.1]:
        assert context.scoring_estimate(invalid, NOW)["estimated_cost_usd"] is None
    assert context.scoring_estimate(100, START - timedelta(seconds=1))["estimated_cost_usd"] is None
    with pytest.raises(ValueError):
        context.scoring_estimate(100, NOW.replace(tzinfo=None))
    with pytest.raises(HTTPException) as error:
        save(p, version=1, model="Decision-1", input="1", output="0")
    assert error.value.status_code == 422
    p.clock.now += timedelta(days=1)
    t1 = p.clock.now
    save(p, version=1, model="Decision-1", input="0")
    assert ep.snapshot(p.db).scoring_estimate(1_000_000, t1)["estimated_cost_usd"] == 0
    assert ep.snapshot(p.db).scoring_estimate(1_000_000, NOW)["estimated_cost_usd"] == 5
    assert all(r.get("model_kind") != "scoring" for r in ep.estimate_args(p.db)["periods"])
    p.clock.now += timedelta(days=1)
    save(p, version=2, model="Decision-1", operation="unknown")
    assert ep.snapshot(p.db).scoring_estimate(100, p.clock.now)["estimated_cost_usd"] is None


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "100001", "0.000000001", "", "bad"])
def test_validation_reuses_decimal_precision(value):
    with pytest.raises(ValidationError):
        ep.ExternalRateUpdate(model="chat", input=value, output="1")


def test_validation_scope_org_role_and_noop(pricing):
    p = pricing
    baseline(p)
    for operation in ("unknown", "inherit"):
        with pytest.raises(ValidationError):
            ep.ExternalRateUpdate(model="chat", operation=operation, input="0")
    with pytest.raises(HTTPException) as error:
        save(p, version=1, input="1")
    assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error:
        save(p, version=1, model="new-unlisted", input="1", output="2")
    assert error.value.status_code == 422
    for org, code in [("short", 422), (str(uuid4()), 404)]:
        with pytest.raises(HTTPException) as error:
            save(p, org=org, input="1", output="2")
        assert error.value.status_code == code
    payload = ep.ExternalCardUpdate(expected_version=1, rates=[
        ep.ExternalRateUpdate(model="chat", input="1", output="2")]*2)
    with pytest.raises(HTTPException) as error:
        ep.save_external_card(p.db, p.settings, p.principal, payload)
    assert error.value.status_code == 422
    customer = Principal(p.org, "Test", "tenant", "user", "customer")
    with pytest.raises(HTTPException) as error:
        ep.initialize_external_baseline(p.db, p.settings, customer)
    assert error.value.status_code == 403
    save(p, version=1, input="1.00000000", output="2", cached="0.2")
    p.clock.now += timedelta(seconds=1)
    assert not save(p, version=1, input="1", output="2", cached="0.2").changed
    assert p.db.scalar(select(func.count()).select_from(ExternalPriceCardRevision)) == 1


def test_new_model_unknown_not_future_internal_fallback(pricing):
    p = pricing
    baseline(p)
    new = {**p.chat, "model": "new", "input": "999", "output": "999"}
    p.scopes.append(("new", new))
    p.bases[rate_card.key_of(new)] = new
    assert ep.snapshot(p.db).display_price(new) is None
    assert item(ep.get_external_card(p.db, p.settings), "new").input is None
    assert all(r["model"] != "new" for r in ep.estimate_args(p.db)["periods"])


def test_same_clock_writes_are_visible_and_history_revision_is_external(pricing):
    p = pricing
    baseline(p)
    saved = save(p, version=1, input="7", output="8")
    assert saved.version == 2 and item(saved).input == "7"
    saved = save(p, version=2, input="9", output="10")
    assert saved.version == 3 and item(saved).input == "9"
    historical = ep.snapshot(p.db, at=START)
    assert historical.revision == "external:default:v1"
    assert historical.display_price(p.chat)["input"] == "1"


def test_default_unknown_inheritance_and_default_reset_never_internal(pricing):
    p = pricing
    baseline(p)
    save(p, version=1, operation="unknown")
    assert price(p) is None and price(p, p.org) is None
    save(p, org=p.org, input="0", output="0")
    assert price(p, p.org)["input"] == "0"
    save(p, org=p.org, version=1, operation="inherit")
    assert price(p, p.org) is None
    with pytest.raises(HTTPException) as error:
        save(p, version=2, operation="inherit")
    assert error.value.status_code == 422
    assert price(p) is None


def test_organization_scoring_event_time_inherit_and_snapshot_detachment(pricing):
    p = pricing
    baseline(p)
    detached = ep.snapshot(p.db, p.org)
    save(p, org=p.org, model="Decision-1", input="1")
    t1 = p.clock.now
    p.clock.now += timedelta(days=1)
    save(p, version=1, model="Decision-1", input="9")
    t2 = p.clock.now
    p.clock.now += timedelta(days=1)
    save(p, org=p.org, version=1, model="Decision-1", operation="inherit")
    current = ep.snapshot(p.db, p.org)
    assert current.scoring_estimate(1_000_000, t1)["estimated_cost_usd"] == 1
    assert current.scoring_estimate(1_000_000, t2)["estimated_cost_usd"] == 1
    assert current.scoring_estimate(1_000_000, p.clock.now)["estimated_cost_usd"] == 9
    assert detached.scoring_estimate(1_000_000, t1)["estimated_cost_usd"] == 5


def test_cas_stale_and_interleaved_update_and_create_races(pricing, monkeypatch):
    p = pricing
    baseline(p)
    with pytest.raises(HTTPException) as error:
        save(p, input="3", output="4")
    assert error.value.status_code == 409
    # Force head to advance between snapshot validation and conditional UPDATE.
    original = ep._append

    def race(db, owner, expected, *args, **kwargs):
        head = db.get(ExternalPriceCard, owner)
        head.version += 1
        db.commit()
        return original(db, owner, expected, *args, **kwargs)

    monkeypatch.setattr(ep, "_append", race)
    p.clock.now += timedelta(seconds=1)
    with pytest.raises(HTTPException) as error:
        save(p, version=1, input="3", output="4")
    assert error.value.status_code == 409
    monkeypatch.setattr(ep, "_append", original)
    # A competing create wins the unique owner before this writer flushes.
    p.db.add(ExternalPriceCard(owner="org:" + p.org, organization_id=p.org, version=1))
    p.db.commit()
    with pytest.raises(HTTPException) as error:
        save(p, org=p.org, input="3", output="4")
    assert error.value.status_code == 409
    assert p.db.scalar(select(func.count()).select_from(ExternalPriceCardRevision)) == 1


def test_baseline_invalid_history_fails_without_partial_seed(pricing):
    p = pricing
    p.db.add(GatewaySettings(scope="rate-card", version=1))
    p.db.commit()
    with pytest.raises(ValueError, match="Missing current"):
        baseline(p)
    assert p.db.scalar(select(func.count()).select_from(ExternalPriceCard)) == 0


def test_schema_constraints_and_revision_uuid(pricing):
    p = pricing
    baseline(p)
    from uuid import UUID
    assert UUID(p.db.scalar(select(ExternalPriceCardRevision.id)))
    p.db.add(ExternalPriceCard(owner="org:" + p.org, organization_id=p.other, version=1))
    with pytest.raises(IntegrityError):
        p.db.flush()
    p.db.rollback()


def test_migration_independent_heads_idempotent_and_empty(pricing):
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    scripts = ScriptDirectory.from_config(config)
    assert set(scripts.get_heads()) == {"0005_org_model_access", "0006_monthly_advisory_budgets"}
    assert set(scripts.get_revision("0004_external_pricing").down_revision) == {"0003", "0003_portal_users"}
    spec = importlib.util.spec_from_file_location("external_migration", MIGRATIONS / "versions/0004_external_pricing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
            module.upgrade()
            assert connection.scalar(select(func.count()).select_from(ExternalPriceCard)) == 0
            names = inspect(connection).get_table_names()
            assert "external_price_card_revisions" in names
            module.downgrade()
            assert "external_price_cards" not in inspect(connection).get_table_names()
    engine.dispose()


def test_full_alembic_upgrade_from_empty_database(tmp_path):
    config = Config(str(MIGRATIONS.parent / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", "sqlite:///" + (tmp_path / "migration.db").as_posix())
    # env.py uses settings unless an explicit connection is supplied.
    engine = create_engine("sqlite:///" + (tmp_path / "migration.db").as_posix())
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0004_external_pricing")
        assert MigrationContext.configure(connection).get_current_heads() == ("0004_external_pricing",)
        assert connection.scalar(select(func.count()).select_from(ExternalPriceCard)) == 0
        assert "portal_users" in inspect(connection).get_table_names()
    engine.dispose()


def test_real_bundled_baseline_freezes_every_scope_without_supplier_metadata(monkeypatch):
    # Do not mock base_scopes: prove the actual shipped manifests can be frozen.
    monkeypatch.setattr(rate_card, "listed_scopes", lambda _: [])
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        principal = Principal(str(uuid4()), "Operator", str(uuid4()), str(uuid4()), "ids_admin")
        ep.initialize_external_baseline(db, SimpleNamespace(), principal)
        context = ep.snapshot(db)
        assert len(context._events) == len(rate_card.base_scopes())
        for key, base in rate_card.base_scopes().items():
            display = context.display_price(base)
            if base.get("status") == "unknown":
                assert display is None
            else:
                assert display["input"] == rate_card.fmt(rate_card.parse_rate(base["input"]))
                assert display["source_url"] == ""
        assert all("source" not in row and "provenance" not in row for row in context._events)
        assert ep.initialize_external_baseline(db, SimpleNamespace(), principal).version == 1
    engine.dispose()


def test_baseline_provenance_lock_refresh_and_published_only(pricing, monkeypatch):
    from sqlalchemy.dialects import mssql, postgresql

    p = pricing
    head = GatewaySettings(scope=rate_card.SCOPE, version=0)
    p.db.add(head)
    p.db.commit()
    with p.engine.begin() as conn:
        conn.execute(GatewaySettings.__table__.update().values(version=1))
    configuration = json.dumps({"entries": [{**p.chat, "origin": "public_list",
                                            "valid_from": START.isoformat()}]}, indent=2)
    for version, state in [(1, "published"), (2, "pending"), (3, "failed")]:
        p.db.add(GatewaySettingsRevision(scope=rate_card.SCOPE, version=version,
                                        configuration=configuration if version == 1 else "bad json",
                                        state=state, object_id=p.principal.object_id,
                                        reason="test", base_hash="", base_etag=""))
    p.db.commit()
    # Keep a stale identity-map value to prove populate_existing matters.
    p.db.refresh(head)
    p.db.expire_on_commit = False
    with p.engine.begin() as conn:
        conn.execute(GatewaySettings.__table__.update().values(version=0))
    p.db.refresh(head)
    with p.engine.begin() as conn:
        conn.execute(GatewaySettings.__table__.update().values(version=1))
    statements = []

    @event.listens_for(p.db, "do_orm_execute")
    def observe(state):
        if state.is_select and state.statement.column_descriptions[0].get("entity") is GatewaySettings:
            statements.append(state.statement)

    baseline(p)
    statement = statements[0]
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))
    assert "WITH (UPDLOCK, HOLDLOCK)" in str(statement.compile(dialect=mssql.dialect()))
    assert statement.get_execution_options()["populate_existing"]
    data = json.loads(p.db.scalar(select(ExternalPriceCardRevision.delta)))
    proof = data["provenance"]
    assert proof["internal_head_version"] == 1
    assert proof["raw_configuration_sha256"] == hashlib.sha256(configuration.encode()).hexdigest()
    assert proof["internal_revisions"] == [{"version": 1, "raw_configuration_sha256":
                                           proof["raw_configuration_sha256"]}]
    assert proof["frozen_base_sha256"] == hashlib.sha256(json.dumps(
        [p.bases[key] for key in sorted(p.bases)], sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    assert "provenance" not in json.dumps(ep.get_external_card(p.db, p.settings).model_dump(mode="json"))
    assert "sha256" not in json.dumps(price(p))


def test_initialization_required_for_writes_not_reads_and_empty_inherit_noop(pricing):
    p = pricing
    for org in (None, p.org):
        with pytest.raises(HTTPException) as error:
            save(p, org=org, input="4", output="5")
        assert error.value.status_code == 409 and "not initialized" in error.value.detail
    assert not save(p, org=p.org, operation="inherit").changed
    assert p.db.scalar(select(func.count()).select_from(ExternalPriceCard)) == 0
    assert price(p, p.org) is None
    for org, code in [(str(uuid4()), 404), ("bad", 422)]:
        with pytest.raises(HTTPException) as error:
            ep.get_external_card(p.db, p.settings, org)
        assert error.value.status_code == code


def test_organization_notes(pricing):
    p = pricing
    baseline(p)
    assert item(ep.get_external_card(p.db, p.settings, p.org)).note == "Inherited external default"
    assert item(save(p, org=p.org, input="3", output="4")).note == "Organization override"
    assert item(save(p, org=p.org, version=1, operation="unknown")).note == "Unknown external price"
    assert item(save(p, org=p.org, version=2, operation="inherit")).note == "Inherited external default"


def test_missing_table_unknown_preserves_caller_transaction_and_corruption_raises(pricing, caplog):
    p = pricing
    ExternalPriceCardRevision.__table__.drop(p.engine)
    p.db.get(Organization, p.org).name = "pending usage work"
    context = ep.snapshot(p.db, p.org)
    assert context.revision == "external:unavailable"
    assert context.estimate_args()["periods"] == [] and context.display_price(p.chat) is None
    assert "prices are unknown" in caplog.text
    p.db.commit()
    assert p.db.get(Organization, p.org).name == "pending usage work"
    ExternalPriceCardRevision.__table__.create(p.engine)
    baseline(p)
    row = p.db.scalar(select(ExternalPriceCardRevision))
    row.delta = "corrupt"
    p.db.commit()
    with pytest.raises(json.JSONDecodeError):
        ep.snapshot(p.db)


def test_history_unknown_gap_and_public_default_resets_freeze_vectors(pricing):
    p = pricing
    unknown_at, reset_at = START + timedelta(days=1), START + timedelta(days=2)
    p.db.add(GatewaySettings(scope=rate_card.SCOPE, version=1))
    p.db.flush()
    entries = [dict(model="chat", provider="Test", region="test", origin="unknown",
                    valid_from=unknown_at.isoformat()),
               dict(model="chat", provider="Test", region="test", origin="platform_default",
                    valid_from=reset_at.isoformat(), input="7", output="8")]
    p.db.add(GatewaySettingsRevision(scope=rate_card.SCOPE, version=1,
                                    configuration=json.dumps({"entries": entries}), state="published",
                                    object_id=p.principal.object_id, reason="test", base_hash="", base_etag=""))
    p.db.commit()
    baseline(p)
    context = ep.snapshot(p.db)
    periods = [r for r in context.estimate_args()["periods"] if r["model"] == "chat"]
    assert [(r["valid_from"], r["valid_to"]) for r in periods] == [
        (START, unknown_at), (unknown_at, reset_at), (reset_at, None)]
    assert periods[1]["status"] == "unknown" and "input" not in periods[1]
    assert price(p, at=unknown_at) is None
    assert price(p, at=reset_at)["input"] == "7"  # Stored reset vector, not today's base.
    assert context.display_price(p.chat)["output"] == "8"


def test_first_organization_save_concurrent_unique_winner(pricing, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    p = pricing
    engine = create_engine("sqlite:///" + (tmp_path / "race.db").as_posix(),
                           connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Organization(id=p.org, name="race", tenant_id=str(uuid4())))
        db.commit()
        ep.initialize_external_baseline(db, p.settings, p.principal)
    barrier = Barrier(2)
    append = ep._append

    def interleave(*args, **kwargs):
        barrier.wait(timeout=10)
        return append(*args, **kwargs)

    monkeypatch.setattr(ep, "_append", interleave)

    def writer(amount):
        with Session(engine) as db:
            try:
                result = ep.save_external_card(db, p.settings, p.principal, ep.ExternalCardUpdate(
                    expected_version=0, rates=[ep.ExternalRateUpdate(model="chat", input=amount, output=amount)]),
                    p.org)
                return result.version
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(writer, ["3", "4"])) == [1, 409]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ExternalPriceCardRevision).where(
            ExternalPriceCardRevision.owner == "org:" + p.org)) == 1
    engine.dispose()


@pytest.mark.parametrize("stamp", ["0003", "0003_portal_users", "ambiguous_portal_0003"])
def test_actual_alembic_upgrade_branch_stamps_repairs_teams(tmp_path, stamp):
    config = Config(str(MIGRATIONS.parent / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS))
    engine = create_engine("sqlite:///" + (tmp_path / "branch.db").as_posix())
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002")
        if stamp == "ambiguous_portal_0003":
            command.upgrade(config, "0003_portal_users")
            # Reproduce the original portal-users-only schema stamped 0003.
            with Operations.context(MigrationContext.configure(connection)):
                with Operations(MigrationContext.configure(connection)).batch_alter_table("team_subscriptions") as batch:
                    batch.drop_index("ix_team_subscriptions_team_id")
                    batch.drop_column("team_id")
            for name in ("teams", "local_users", "credit_budgets", "managed_model_endpoints", "model_router_configs"):
                Base.metadata.tables[name].drop(connection)
            command.stamp(config, "0003", purge=True)
        else:
            command.upgrade(config, stamp)
        command.upgrade(config, "0004_external_pricing")
        command.upgrade(config, "0004_external_pricing")
        assert MigrationContext.configure(connection).get_current_heads() == ("0004_external_pricing",)
        names = inspect(connection).get_table_names()
        assert {"portal_users", "teams", "external_price_cards", "local_users"} <= set(names)
        assert "team_id" in {c["name"] for c in inspect(connection).get_columns("team_subscriptions")}
        assert connection.scalar(select(func.count()).select_from(ExternalPriceCardRevision)) == 0
    engine.dispose()


def test_operator_cli_explicit_and_idempotent(pricing, monkeypatch, capsys):
    from aiflux import external_pricing_migration as cli

    p = pricing
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(database_url="sqlite://"))
    monkeypatch.setattr(cli, "engine_for", lambda _: p.engine)
    for args in ([], ["--actor-object-id", p.principal.object_id],
                 ["--init-baseline", "--actor-object-id", "invalid"]):
        with pytest.raises(SystemExit) as error:
            cli.main(args)
        assert error.value.code == 2
    args = ["--init-baseline", "--actor-object-id", p.principal.object_id]
    cli.main(args)
    cli.main(args)
    assert "changed=True" in capsys.readouterr().out
    row = p.db.scalar(select(ExternalPriceCardRevision))
    assert row.object_id == p.principal.object_id
    assert p.db.scalar(select(func.count()).select_from(ExternalPriceCardRevision)) == 1


def test_internal_first_save_wins_absent_head_initialization_race(pricing, tmp_path, monkeypatch):
    p = pricing
    # This fixture's synthetic scorer has no supplier-source mapping; only chat
    # is needed to exercise the real internal first-save transaction.
    monkeypatch.setattr(rate_card, "listed_scopes", lambda _: [("chat", p.chat)])
    engine = create_engine("sqlite:///" + (tmp_path / "internal-race.db").as_posix())
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Organization(id=p.org, name="race", tenant_id=str(uuid4())))
        db.commit()
    with Session(engine) as initializer:
        scalar = initializer.scalar
        competed = False

        def race(statement, *args, **kwargs):
            nonlocal competed
            result = scalar(statement, *args, **kwargs)
            if not competed and statement.get_execution_options().get("populate_existing"):
                competed = True
                assert result is None
                with Session(engine) as writer:
                    result_save = rate_card.save_rate_card(writer, p.settings, p.principal,
                        rate_card.RateCardUpdate(expected_version=0, rates=[
                            rate_card.RateInput(model="chat", input="6", output="7")]))
                    assert result_save.changed
                return None  # The initializer already observed the missing head.
            return result

        monkeypatch.setattr(initializer, "scalar", race)
        with pytest.raises(HTTPException) as error:
            ep.initialize_external_baseline(initializer, p.settings, p.principal)
        assert error.value.status_code == 409
        assert initializer.scalar(select(func.count()).select_from(ExternalPriceCard)) == 0
        assert initializer.scalar(select(GatewaySettingsRevision.state)) == "published"
        ep.initialize_external_baseline(initializer, p.settings, p.principal)
        # Internal save uses its real clock; external fixtures freeze Nov 2.
        context = ep.snapshot(initializer, at=datetime(2100, 1, 1, tzinfo=UTC))
        assert context.display_price(p.chat)["input"] == "6"
        proof = json.loads(initializer.scalar(select(ExternalPriceCardRevision.delta)))["provenance"]
        assert proof["internal_head_version"] == 1
    engine.dispose()


def test_baseline_period_economics_equal_internal_history_including_public_reset(pricing):
    p = pricing
    at1, at2 = START + timedelta(days=1), START + timedelta(days=2)
    raw = [dict(model="chat", provider="Test", region="test", origin=origin,
                valid_from=at.isoformat(), input=amount, output=amount)
           for at, amount, origin in [(at1, "9", "configured"), (at2, "1", "public_list")]]
    p.db.add(GatewaySettings(scope=rate_card.SCOPE, version=1))
    p.db.flush()
    p.db.add(GatewaySettingsRevision(scope=rate_card.SCOPE, version=1,
                                    configuration=json.dumps({"entries": raw}), state="published",
                                    object_id=p.principal.object_id, reason="test", base_hash="", base_etag=""))
    p.db.commit()
    _, entries = rate_card.load_state(p.db)
    old = rate_card.periods(entries)
    baseline(p)
    new = ep.estimate_args(p.db)["periods"]
    for previous, frozen in zip(old, new, strict=True):
        assert {f: previous.get(f) for f in ep.FIELDS} == {f: frozen.get(f) for f in ep.FIELDS}
        assert previous.get("valid_from", rate_card._aware(previous["applicable_from"]) if
                            "applicable_from" in previous else START) == frozen["valid_from"]
        assert previous["valid_to"] == frozen["valid_to"]