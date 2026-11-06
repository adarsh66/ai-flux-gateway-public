"""Offline advisory budget contracts; no cloud, providers, email or production DDL.

These tests are authored for the main agent's run, not an execution receipt.
"""
import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aiflux import external_pricing, monthly_budgets as budgets
from aiflux.auth import Principal
from aiflux.customer_pricing import customer_safe
from aiflux.models import (
    AuditEvent, Base, BudgetHardStopRemediation, CreditBudget, ExternalPriceCard,
    ExternalPriceCardRevision, Organization, OrganizationMonthlyBudgetPolicy,
    OrganizationMonthlyBudgetRevision, TeamSubscription, UsageRecord,
)
from aiflux.schemas import MonthlyBudgetSummary, MonthlyBudgetUpdate, CreditBudgetUpdate
from aiflux.turnstile_exchange import _budget_output, _enforcement_used_credits_for, _used_credits_for
from test_turnstile_exchange import deployed_garden  # existing synthetic-only fixture

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services/control-plane/migrations"
TARGET = "0006_monthly_advisory_budgets"


@pytest.fixture
def monthly(tmp_path, monkeypatch):
    clock = SimpleNamespace(now=NOW)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now

    monkeypatch.setattr(budgets, "datetime", Clock)
    engine = create_engine("sqlite:///" + (tmp_path / "monthly.db").as_posix())

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org, other = str(uuid4()), str(uuid4())
        db.add_all([Organization(id=org, name="Customer", tenant_id=str(uuid4())),
                    Organization(id=other, name="Other", tenant_id=str(uuid4()))])
        db.flush()
        subs = [str(uuid4()) for _ in range(3)]
        for index, sid in enumerate(subs):
            db.add(TeamSubscription(id=sid, organization_id=org if index < 2 else other,
                   name=sid, team="Test", state="active", idempotency_key=str(uuid4())))
        db.commit()
        principal = Principal(org, "Customer", str(uuid4()), str(uuid4()), "ids_admin")
        yield SimpleNamespace(db=db, engine=engine, org=org, other=other, subs=subs,
                              principal=principal, clock=clock)
    engine.dispose()


def configure_prices(p, entries=None, *, owner="default", version=1, effective=None):
    at = effective or datetime(2026, 10, 1, tzinfo=UTC)
    entries = entries if entries is not None else [dict(model="chat", provider="Test", region="test",
        operation="set", input="1", output="2", cached="0.2", valid_from=at.isoformat())]
    head = p.db.get(ExternalPriceCard, owner)
    if head is None:
        p.db.add(ExternalPriceCard(owner=owner, organization_id=None if owner == "default" else owner[4:], version=version))
    else:
        head.version = version
    p.db.flush()
    p.db.add(ExternalPriceCardRevision(owner=owner, version=version, effective_at=at,
           delta=json.dumps({"entries": entries}), reason="synthetic external tariff",
           object_id=p.principal.object_id))
    p.db.commit()


def usage(p, *, at=NOW - timedelta(minutes=1), sid=None, model="chat", inputs=1_000_000,
          outputs=1_000_000, completeness="price_missing", cost="9999", cached=0, write=0):
    sid = sid or p.subs[0]
    row = UsageRecord(id=str(uuid4()), organization_id=p.org if sid != p.subs[2] else p.other,
          subscription_id=sid, model=model, provider="Test", region="test", occurred_at=at,
          input_tokens=inputs, output_tokens=outputs, cached_input_tokens=cached, cache_write_tokens=write,
          status_code=200, completeness=completeness, cost=Decimal(cost), currency="USD")
    p.db.add(row)
    p.db.commit()
    return row


def allocate(p, amount="10", version=0, threshold=80, reason="Approved recurring advisory allocation"):
    return budgets.save(p.db, p.principal, p.org, MonthlyBudgetUpdate(allocated_usd=amount,
                        expected_version=version, advisory_threshold_pct=threshold, reason=reason))


@pytest.mark.parametrize("at,start,end", [
    (datetime(2026, 12, 31, 23, 59, tzinfo=UTC), "2026-12-01", "2027-01-01"),
    (datetime(2027, 1, 1, tzinfo=UTC), "2027-01-01", "2027-02-01"),
    (datetime(2028, 2, 29, 23, 59, tzinfo=UTC), "2028-02-01", "2028-03-01"),
    (datetime(2027, 2, 28, tzinfo=UTC), "2027-02-01", "2027-03-01"),
    (datetime(2026, 11, 1, 7, tzinfo=timezone(timedelta(hours=8))), "2026-10-01", "2026-11-01"),
])
def test_utc_calendar_boundaries(at, start, end):
    first, next_start = budgets.month_window(at)
    assert budgets.iso(first) == start + "T00:00:00Z"
    assert budgets.iso(next_start) == end + "T00:00:00Z"


def test_get_unconfigured_no_financial_seed_or_mutation(monthly):
    p = monthly
    writes = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")):
            writes.append(statement)

    event.listen(p.engine, "before_cursor_execute", capture)
    try:
        result = budgets.summary(p.db, p.org)
        assert result.status == "unconfigured" and result.allocated_usd is None and result.version == 0
        assert result.estimated_used_usd == "0.000000000000"
        assert result.estimated_remaining_usd is None and not result.hard_stop_enabled
        assert budgets.history(p.db, p.org) == {"items": [], "total": 0}
        page = budgets.list_summaries(p.db, offset=1, limit=1)
        assert page["total"] == 2 and len(page["items"]) == 1
        assert not writes
    finally:
        event.remove(p.engine, "before_cursor_execute", capture)
    for table in (OrganizationMonthlyBudgetPolicy, OrganizationMonthlyBudgetRevision, CreditBudget, AuditEvent):
        assert p.db.scalar(select(func.count()).select_from(table)) == 0


def test_month_all_subscriptions_exact_asof_late_ingestion_external_only(monthly, monkeypatch):
    p = monthly
    configure_prices(p)
    first, end = budgets.month_window(NOW)
    usage(p, at=first - timedelta(microseconds=1), inputs=50_000_000)
    usage(p, at=first, sid=p.subs[0])
    usage(p, at=NOW, sid=p.subs[1])
    usage(p, at=NOW + timedelta(microseconds=1))
    usage(p, at=end)
    usage(p, sid=p.subs[2])
    from aiflux import rate_card
    monkeypatch.setattr(rate_card, "estimate_args", lambda *_: pytest.fail("internal fallback"))
    result = allocate(p)
    assert Decimal(result.estimated_used_usd) == 6  # all owned subs, not internal 9999
    assert result.estimated_requests == 2 and result.unestimated_requests == 0
    assert result.latest_usage_at == budgets.iso(NOW)
    assert result.estimated_utilization_pct == 60
    assert not result.estimate_complete and result.status == "unknown"  # unobserved scoring stage
    assert result.estimated_remaining_usd is None
    assert _used_credits_for(p.db, p.org, p.subs[0]) == Decimal("3.0000")
    assert _enforcement_used_credits_for(p.db, p.org) == Decimal("6.0000")
    # Late ingestion uses occurred_at, not the insertion date; no month reset.
    usage(p, at=first + timedelta(hours=1))
    assert Decimal(budgets.summary(p.db, p.org).estimated_used_usd) == 9
    assert p.db.scalar(select(func.count()).select_from(UsageRecord)) == 7


@pytest.mark.parametrize("allocation,status,pct,overrun", [
    ("3.7975", "unknown", Decimal(3) / Decimal("3.7975") * 100, "0"),
    ("3.75", "threshold_reached", Decimal(80), "0"),
    ("3", "threshold_reached", Decimal(100), "0"),
    ("2.4", "over_budget", Decimal(125), "0.6"),
])
def test_advisory_status_over100_with_incomplete_stage_coverage(monthly, allocation, status, pct, overrun):
    p = monthly
    configure_prices(p)
    usage(p)
    result = allocate(p, allocation)
    assert result.status == status
    assert result.estimated_utilization_pct == pytest.approx(float(pct))
    assert Decimal(result.estimated_overrun_usd) == Decimal(overrun)
    assert not result.hard_stop_enabled and not result.estimate_complete


def test_empty_known_month_below_threshold_and_recurring_no_rollover(monthly):
    p = monthly
    configure_prices(p)
    out = allocate(p, "2.4")
    assert out.status == "below_threshold" and out.estimate_complete
    assert Decimal(out.estimated_remaining_usd) == Decimal("2.4")
    usage(p)
    assert budgets.summary(p.db, p.org).status == "over_budget"
    p.clock.now = datetime(2026, 12, 1, tzinfo=UTC)
    out = budgets.summary(p.db, p.org)
    assert out.version == 1 and out.allocated_usd == "2.4000"
    assert out.status == "below_threshold" and Decimal(out.estimated_used_usd) == 0
    assert p.db.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetRevision)) == 1
    assert p.db.scalar(select(func.count()).select_from(UsageRecord)) == 1


def test_external_tariff_boundary_org_override_inherit_and_unknown(monthly):
    p = monthly
    configure_prices(p)
    boundary = NOW - timedelta(hours=1)
    configure_prices(p, [dict(model="chat", provider="Test", region="test", operation="set",
        input="4", output="6", valid_from=boundary.isoformat())], owner="org:" + p.org, effective=boundary)
    usage(p, at=boundary - timedelta(microseconds=1))
    usage(p, at=boundary)
    usage(p, at=boundary, sid=p.subs[2])
    result = allocate(p, "10")
    assert Decimal(result.estimated_used_usd) == 13
    assert result.pricing_revision.endswith("+org:" + p.org + ":v1")
    assert Decimal(budgets.summary(p.db, p.other).estimated_used_usd) == 3
    reset = NOW - timedelta(minutes=30)
    configure_prices(p, [dict(model="chat", provider="Test", region="test", operation="inherit",
        valid_from=reset.isoformat())], owner="org:" + p.org, version=2, effective=reset)
    usage(p, at=reset)
    assert Decimal(budgets.summary(p.db, p.org).estimated_used_usd) == 16
    configure_prices(p, [dict(model="chat", provider="Test", region="test", operation="unknown",
        valid_from=NOW.isoformat())], owner="org:" + p.org, version=3, effective=NOW)
    usage(p, at=NOW)
    result = budgets.summary(p.db, p.org)
    assert Decimal(result.estimated_used_usd) == 16 and result.unestimated_requests == 1


def test_unknown_prices_missing_tokens_and_approximation_not_complete(monthly):
    p = monthly
    usage(p)
    out = allocate(p)
    assert out.estimated_used_usd is None and out.status == "unknown"
    assert out.estimated_requests == 0 and out.unestimated_requests == 1
    configure_prices(p)
    usage(p, inputs=None)
    usage(p, cached=None, write=None)
    out = budgets.summary(p.db, p.org)
    assert out.estimated_requests == 2 and out.unestimated_requests == 1
    assert Decimal(out.estimated_used_usd) == 6 and not out.estimate_complete


def test_unavailable_external_store_no_internal_fallback(monthly, monkeypatch):
    p = monthly
    usage(p)
    monkeypatch.setattr(external_pricing, "snapshot", lambda db, org, at: external_pricing.PricingContext(
        org, 0, "external:unavailable", at, ()))
    out = allocate(p)
    assert out.pricing_revision == "external:unavailable" and out.estimated_used_usd is None
    assert not out.estimate_complete and out.status == "unknown"


def test_scoring_external_input_only_if_priced_no_inference_queries(monthly):
    p = monthly
    start = datetime(2026, 10, 1, tzinfo=UTC)
    configure_prices(p, [dict(model="Decision-1", provider="Test", region="test", operation="set",
        model_kind="scoring", billing_dimensions=["input"], input="0.042", valid_from=start.isoformat())])
    usage(p, model="Decision-1", outputs=None)
    result = allocate(p, "0.01")
    assert Decimal(result.estimated_used_usd) == Decimal("0.042")
    assert result.estimated_requests == 1 and result.unestimated_requests == 0
    assert result.estimate_complete and result.status == "over_budget"
    p.clock.now += timedelta(hours=1)
    configure_prices(p, [dict(model="Decision-1", provider="Test", region="test", operation="unknown",
        model_kind="scoring", billing_dimensions=["input"], valid_from=p.clock.now.isoformat())],
        version=2, effective=p.clock.now)
    usage(p, model="Microsoft-Decision-1", at=p.clock.now)
    result = budgets.summary(p.db, p.org)
    assert Decimal(result.estimated_used_usd) == Decimal("0.042") and result.unestimated_requests == 1
    assert not result.estimate_complete


def test_decimal_tiny_amount_and_precision(monthly):
    p = monthly
    configure_prices(p)
    usage(p, inputs=1, outputs=0)
    out = allocate(p, "0.0001")
    assert Decimal(out.estimated_used_usd) == Decimal("0.000001")
    assert out.estimated_utilization_pct == 1


def test_scoring_conflicting_attribution_and_ineligible_rows_are_unknown(monthly):
    p = monthly
    start = datetime(2026, 10, 1, tzinfo=UTC)
    configure_prices(p, [dict(model="Decision-1", provider="Test", region="test", operation="set",
        model_kind="scoring", billing_dimensions=["input"], input="0.042", valid_from=start.isoformat())])
    wrong_provider = usage(p, model="Decision-1", outputs=None)
    wrong_provider.provider = "Other"
    wrong_region = usage(p, model="Decision-1", outputs=None)
    wrong_region.region = "other"
    usage(p, model="Decision-1", outputs=None, completeness="backend_attribution_missing")
    p.db.commit()
    result = allocate(p)
    assert result.estimated_used_usd is None
    assert result.estimated_requests == 0 and result.unestimated_requests == 3
    assert not result.estimate_complete and result.status == "unknown"


@pytest.mark.parametrize("amount", [0, 1.2, True, None, "0", "-1", "NaN", "Infinity", "1e2",
    ".1", "01", "1.00001", "1000000000.0001", "1000000001", "1,000"])
def test_invalid_positive_bounded_currency(amount):
    with pytest.raises(ValidationError):
        MonthlyBudgetUpdate(allocated_usd=amount, expected_version=0, reason="audit")


@pytest.mark.parametrize("extra", [dict(advisory_threshold_pct=0), dict(advisory_threshold_pct=101),
    dict(advisory_threshold_pct=True), dict(advisory_threshold_pct=80.5), dict(expected_version=-1),
    dict(expected_version=True), dict(expected_version=1.0), dict(reason=" "), dict(reason="x" * 501),
    dict(hard_stop_enabled=True), dict(allowed_models=["chat"]), dict(organization_id=str(uuid4())),
    dict(email_enabled=True), dict(reset=True)])
def test_strict_input_and_no_enforcement_controls(extra):
    with pytest.raises(ValidationError):
        MonthlyBudgetUpdate(**(dict(allocated_usd="10", expected_version=0, reason="audit") | extra))


def test_sql_cas_history_and_first_create_conflicts(monthly):
    p = monthly
    out = allocate(p)
    assert out.version == 1 and out.advisory_threshold_pct == 80
    with Session(p.engine) as second:
        payload = MonthlyBudgetUpdate(allocated_usd="20", expected_version=1, reason="second session")
        assert budgets.save(second, p.principal, p.org, payload).version == 2
    with pytest.raises(HTTPException) as conflict:
        allocate(p, "30", version=1)
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as conflict:
        allocate(p, "40", version=0)
    assert conflict.value.status_code == 409
    hist = budgets.history(p.db, p.org)
    assert hist["total"] == 2 and [r.version for r in hist["items"]] == [2, 1]
    assert [r.allocated_usd for r in hist["items"]] == ["20.0000", "10.0000"]
    assert all(r.changed_by == p.principal.object_id and r.changed_at.endswith("Z") for r in hist["items"])
    assert budgets.history(p.db, p.org, offset=1, limit=1)["items"][0].version == 1
    assert budgets.history(p.db, p.other)["items"] == []
    assert p.db.scalar(select(func.count()).select_from(AuditEvent)) == 2
    assert p.db.scalar(select(func.count()).select_from(CreditBudget)) == 0


def test_create_integrity_race_translates409_and_rolls_back(monthly, monkeypatch):
    p = monthly
    original_flush = p.db.flush
    def race(*args, **kwargs):
        if any(isinstance(row, OrganizationMonthlyBudgetPolicy) for row in p.db.new):
            raise IntegrityError("synthetic competing insert", {}, Exception("unique constraint"))
        return original_flush(*args, **kwargs)
    monkeypatch.setattr(p.db, "flush", race)
    with pytest.raises(HTTPException) as conflict:
        allocate(p)
    assert conflict.value.status_code == 409
    assert not p.db.new and not p.db.dirty


def test_revision_insert_failure_rolls_back_cas_and_audit(monthly, monkeypatch):
    p = monthly
    allocate(p)
    original_flush = p.db.flush

    def fail_revision(*args, **kwargs):
        if any(isinstance(row, OrganizationMonthlyBudgetRevision) for row in p.db.new):
            raise IntegrityError("synthetic revision failure", {}, Exception("constraint"))
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(p.db, "flush", fail_revision)
    with pytest.raises(HTTPException) as conflict:
        allocate(p, "20", version=1)
    assert conflict.value.status_code == 409
    monkeypatch.setattr(p.db, "flush", original_flush)
    assert p.db.scalar(select(OrganizationMonthlyBudgetPolicy.version)) == 1
    assert p.db.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetRevision)) == 1
    assert p.db.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_legacy_defaults_outputs_and_monthly_estimate_ignore_internal_cost(monthly):
    p = monthly
    configure_prices(p)
    usage(p, at=NOW - timedelta(days=40))
    usage(p)
    row = CreditBudget(organization_id=p.org, hard_stop_enabled=True)
    p.db.add(row)
    p.db.commit()
    out = _budget_output(p.db, row)
    assert not out.hard_stop_enabled and out.used_credits == "3.0000"
    assert row.hard_stop_enabled is True  # GET does not secretly remediate live rows
    defaults = CreditBudgetUpdate(monthly_budget_usd="10", credit_allocation="10")
    assert defaults.hard_stop_enabled is False
    with pytest.raises(ValidationError):
        CreditBudgetUpdate(monthly_budget_usd="10", credit_allocation="10", hard_stop_enabled=True)


def test_api_authorization_scope_contract_privacy_and_no_side_effects(env):
    org = env.orgs["customer"]
    admin_path = "/api/admin/monthly-budgets"
    assert env.client.get(admin_path).status_code == 401
    assert env.client.get(admin_path, headers=env.customer).status_code == 403
    body = {"allocated_usd": "10.25", "expected_version": 0, "reason": "Monthly advisory"}
    assert env.client.put(admin_path + "/" + org, headers=env.customer, json=body).status_code == 403
    assert env.client.get(admin_path + "/" + org + "/history", headers=env.customer).status_code == 403
    calls = list(env.apim.calls)
    saved = env.client.put(admin_path + "/" + org, headers=env.admin, json=body)
    assert saved.status_code == 200, saved.text
    own = env.client.get("/api/budget/monthly", headers=env.customer,
                         params={"organization_id": env.orgs["admin"]})
    assert own.status_code == 200 and own.json()["organization_id"] == org
    assert {k: v for k, v in own.json().items() if k != "as_of"} == {
        k: v for k, v in saved.json().items() if k != "as_of"}
    assert set(own.json()) == set(MonthlyBudgetSummary.model_fields)
    assert "external:" in own.json()["pricing_revision"] and own.json()["basis"] == "external_customer_prices"
    assert not own.json()["hard_stop_enabled"]
    assert customer_safe({"nested": own.json(), "used_credits": "secret", "cost": "secret"}) == {"nested": own.json()}
    listed = env.client.get(admin_path, headers=env.admin, params={"offset": 0, "limit": 1})
    assert listed.status_code == 200 and listed.json()["total"] == 2 and len(listed.json()["items"]) == 1
    history = env.client.get(admin_path + "/" + org + "/history", headers=env.admin)
    assert history.status_code == 200 and history.json()["items"][0]["allocated_usd"] == "10.2500"
    assert env.client.put(admin_path + "/" + org, headers=env.admin, json=body).status_code == 409
    assert env.client.put(admin_path + "/" + org, headers=env.admin, json=body | {"hard_stop_enabled": True}).status_code == 422
    assert env.client.put(admin_path + "/" + str(uuid4()), headers=env.admin, json=body).status_code == 404
    assert env.client.get(admin_path + "/" + str(uuid4()) + "/history", headers=env.admin).status_code == 404
    assert env.client.get(admin_path, headers=env.admin, params={"limit": 101}).status_code == 422
    assert env.client.delete(admin_path + "/" + org, headers=env.admin).status_code == 405
    assert env.apim.calls == calls
    with Session(env.db_engine) as db:
        assert db.scalar(select(func.count()).select_from(CreditBudget)) == 0
        assert db.scalar(select(func.count()).select_from(ExternalPriceCard)) == 0


@pytest.mark.parametrize("persisted_stop", [False, True])
@pytest.mark.parametrize("requested_model", ["gpt-5.4-mini", "auto"])
def test_legacy_chat_never_budget402_preserves_model_allowlist(env, deployed_garden, monkeypatch,
                                                             persisted_stop, requested_model):
    from aiflux import turnstile_exchange as legacy
    from test_control_plane import create_key
    sub = create_key(env)["id"]
    with Session(env.db_engine) as db:
        db.add(CreditBudget(organization_id=env.orgs["customer"], credit_allocation=Decimal(0),
                           hard_stop_enabled=persisted_stop, allowed_models_json='["*"]'))
        db.commit()
    monkeypatch.setattr(legacy, "_enforcement_used_credits_for", lambda *_: pytest.fail("budget admission calculation"))
    monkeypatch.setattr(legacy.httpx, "post", lambda *a, **k: pytest.fail("paid inference"))
    request = {"model": requested_model, "subscription_id": sub,
               "messages": [{"role": "user", "content": "Synthetic greeting"}], "max_completion_tokens": 16}
    result = env.client.post("/api/playground/chat", headers=env.customer, json=request)
    assert result.status_code == 200, result.text
    with Session(env.db_engine) as db:
        row = db.scalar(select(CreditBudget).where(CreditBudget.organization_id == env.orgs["customer"]))
        row.allowed_models_json = "[]"
        db.commit()
    assert env.client.post("/api/playground/chat", headers=env.customer, json=request).status_code == 403
    assert env.client.post("/api/playground/chat", json=request).status_code == 401


def test_legacy_preview_has_no_financial_stop(env, deployed_garden):
    from aiflux.turnstile_exchange import render_turnstile_exchange_policy
    with Session(env.db_engine) as db:
        xml = render_turnstile_exchange_policy(db, env.settings).policy_xml
        assert 'code="402"' not in xml and "HardStopEnabled" not in xml
        assert "llm-content-safety" in xml and "TurnstileLedger" in xml


def test_independent_migration_audited_off_no_feature2_and_safe_downgrade(tmp_path):
    cfg = Config(str(MIGRATIONS.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(MIGRATIONS))
    scripts = ScriptDirectory.from_config(cfg)
    # Archive metadata now succeeds the budget branch; explicit budget target
    # behavior and its independent relationship to paused Feature2 are intact.
    assert set(scripts.get_heads()) == {"0005_org_model_access", "0007_admin_archival"}
    assert scripts.get_revision("0007_admin_archival").down_revision == TARGET
    node = scripts.get_revision(TARGET)
    assert node.down_revision == "0004_external_pricing"
    assert node.dependencies is None and "monthly_advisory_budgets" in node.branch_labels
    engine = create_engine("sqlite:///" + (tmp_path / "migration.db").as_posix())
    with engine.begin() as conn:
        # Start at actual deployed prerequisite, not historical dynamic 0001.
        # Sorted metadata emits organizations before subscription/budget FKs.
        for table in Base.metadata.sorted_tables:
            if table.name in {"organizations", "teams", "team_subscriptions", "credit_budgets"}:
                table.create(conn)
        org = str(uuid4())
        conn.execute(Organization.__table__.insert().values(id=org, name="Test", tenant_id=str(uuid4())))
        for bid, flag in [("true-budget", True), ("false-budget", False)]:
            conn.execute(CreditBudget.__table__.insert().values(id=bid, organization_id=org,
                hard_stop_enabled=flag, monthly_budget_usd=Decimal("25"), credit_allocation=Decimal("50")))
        cfg.attributes["connection"] = conn
        command.stamp(cfg, "0004_external_pricing")
        command.upgrade(cfg, TARGET)
        assert MigrationContext.configure(conn).get_current_heads() == (TARGET,)
        names = set(inspect(conn).get_table_names())
        assert "organization_model_access" not in names and "model_access_publication" not in names
        rows = conn.execute(select(CreditBudget.__table__)).mappings().all()
        assert all(not r["hard_stop_enabled"] and r["credit_allocation"] == 50 and r["monthly_budget_usd"] == 25 for r in rows)
        receipt = conn.execute(select(BudgetHardStopRemediation.__table__)).mappings().one()
        assert receipt["budget_id"] == "true-budget" and receipt["previous_hard_stop_enabled"] is True
        assert receipt["reason"] and receipt["remediated_at"]
        assert conn.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetPolicy)) == 0
        assert conn.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetRevision)) == 0
        # Server default is OFF even when ORM defaults are not involved.
        conn.execute(text("INSERT INTO credit_budgets (id,organization_id,monthly_budget_usd,credit_allocation,alert_threshold_pct,allowed_models_json,product_name,channel,updated_at) VALUES ('raw-default',:org,1,1,80,'[]','test','test',CURRENT_TIMESTAMP)"), {"org": org})
        assert conn.scalar(select(CreditBudget.hard_stop_enabled).where(CreditBudget.id == "raw-default")) is False
        command.downgrade(cfg, "0004_external_pricing")
        assert "organization_monthly_budget_policies" not in inspect(conn).get_table_names()
        assert conn.scalar(select(BudgetHardStopRemediation.previous_hard_stop_enabled)) is True
        assert conn.scalar(select(CreditBudget.hard_stop_enabled).where(CreditBudget.id == "true-budget")) is False
        command.upgrade(cfg, TARGET)
        assert conn.scalar(select(func.count()).select_from(BudgetHardStopRemediation)) == 1
        assert conn.execute(select(BudgetHardStopRemediation.__table__)).mappings().one() == receipt
    engine.dispose()