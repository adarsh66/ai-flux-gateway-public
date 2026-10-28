"""Synthetic SQLite/API regressions: no production connections or telemetry writes."""
import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux.finops import ingestion_health, model_token_response
from aiflux.models import CreditBudget, IngestionState, TeamSubscription, UsageRecord
from aiflux.turnstile_exchange import credit_summary_response, _budget_output, _used_credits_for, _enforcement_used_credits_for
from scripts.deployment.finops_diagnose import destination
from test_control_plane import create_key
from test_model_tokens import record


@pytest.mark.parametrize("granularity,seconds", [("hour", 3600), ("day", 86400)])
def test_utc_complete_totals_known_components_and_end_exclusion(env, granularity, seconds):
    sub = create_key(env)["id"]
    start = (datetime.now(UTC) - timedelta(days=1)).replace(hour=23, minute=17, second=0, microsecond=0)
    if start >= datetime.now(UTC) - timedelta(hours=2):
        start -= timedelta(days=1)
    end = start + timedelta(hours=2)
    with Session(env.db_engine) as db:
        record(db, env.orgs["customer"], sub, start, "glm-5.3", 11, 7)
        record(db, env.orgs["customer"], sub, start, "glm-5.3", None, 100)
        record(db, env.orgs["customer"], sub, end, "outside", 500, 500)
        db.commit()
        result = model_token_response(db, env.orgs["customer"], sub, start, end, granularity=granularity)
        assert result["interval_seconds"] == seconds
        assert sum(r["total_tokens"] or 0 for r in result["items"]) == 18
        assert sum(r["input_tokens"] or 0 for r in result["items"]) == 11
        assert sum(r["output_tokens"] or 0 for r in result["items"]) == 107
        assert sum(r["measured_requests"] for r in result["items"]) == 1
        assert result["items"][0]["partial_bucket"]
        assert result["health"]["status"] == "unverified"


def test_admin_all_org_selected_org_and_customer_denial(env):
    sub = create_key(env)["id"]
    other = str(uuid4())
    now = datetime.now(UTC) - timedelta(minutes=10)
    with Session(env.db_engine) as db:
        db.add(TeamSubscription(id=other, organization_id=env.orgs["admin"], name="Other", team="Other", idempotency_key=str(uuid4()), state="active"))
        db.flush()
        record(db, env.orgs["customer"], sub, now, inputs=11, outputs=7)
        record(db, env.orgs["admin"], other, now, inputs=10, outputs=20)
        db.commit()
    path = "/api/admin/usage/model-tokens"
    assert env.client.get(path, headers=env.customer).status_code == 403
    all_orgs = env.client.get(path, params={"granularity": "hour"}, headers=env.admin)
    assert all_orgs.status_code == 200, all_orgs.text
    assert sum(r["total_tokens"] for r in all_orgs.json()["items"]) == 48
    scoped = env.client.get(path, params={"organization_id": env.orgs["customer"], "granularity": "day"}, headers=env.admin)
    assert sum(r["total_tokens"] for r in scoped.json()["items"]) == 18
    assert env.client.get(path, params={"organization_id": env.orgs["customer"], "subscription_id": other}, headers=env.admin).status_code == 404
    customer = env.client.get("/api/usage/model-tokens", params={"organization_id": env.orgs["admin"]}, headers=env.customer)
    assert sum(r["total_tokens"] for r in customer.json()["items"]) == 18


def test_explicit_hour_limit_returns_422_not_silent_downsampling(env):
    response = env.client.get("/api/usage/model-tokens", params={"days": 90, "granularity": "hour"}, headers=env.customer)
    assert response.status_code == 422 and "744" in response.json()["detail"]
    assert env.client.get("/api/usage/model-tokens", params={"granularity": "minute"}, headers=env.customer).status_code == 422


def test_same_window_summary_chart_and_csv(env):
    sub = create_key(env)["id"]
    end = datetime.now(UTC) - timedelta(minutes=5)
    start = end - timedelta(hours=2)
    with Session(env.db_engine) as db:
        record(db, env.orgs["customer"], sub, start, inputs=11, outputs=7)
        record(db, env.orgs["customer"], sub, end, inputs=100, outputs=100)
        db.commit()
    query = {"start": start.isoformat(), "end": end.isoformat(), "days": 1}
    summary = env.client.get("/api/usage", params=query, headers=env.customer).json()["summary"]
    chart = env.client.get("/api/usage/model-tokens", params={**query, "granularity": "hour"}, headers=env.customer).json()
    exported = env.client.get("/api/usage/export", params=query, headers=env.customer)
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert summary["requests"] == len(rows) == 1
    assert sum(r["total_tokens"] for r in chart["items"]) == summary["input_tokens"] + summary["output_tokens"] == 18


def test_partial_token_summary_matches_chart_complete_totals_not_known_components(env):
    sub = create_key(env)["id"]
    now = datetime.now(UTC) - timedelta(minutes=10)
    with Session(env.db_engine) as db:
        record(db, env.orgs["customer"], sub, now, inputs=11, outputs=7)
        record(db, env.orgs["customer"], sub, now, inputs=None, outputs=100)
        db.commit()
    summary = env.client.get("/api/usage", headers=env.customer).json()["summary"]
    chart = env.client.get("/api/usage/model-tokens", params={"granularity": "hour"}, headers=env.customer).json()
    assert summary["total_tokens"] == sum(row["total_tokens"] for row in chart["items"]) == 18
    assert summary["output_tokens"] == 107 and summary["measured_requests"] == 1
    assert summary["missing_token_requests"] == 1


def test_health_routes_are_readonly_authorized_and_do_not_seed_budgets(env):
    assert env.client.get("/api/admin/usage/health", headers=env.customer).status_code == 403
    assert env.client.get("/api/usage/health", headers=env.customer).json()["status"] == "unverified"
    assert env.client.get("/api/admin/usage/health", headers=env.admin).json()["status"] == "unverified"
    with Session(env.db_engine) as db:
        assert list(db.scalars(select(CreditBudget))) == []


def test_freshness_is_readonly_no_traffic_not_disabled_and_scoped(env):
    with Session(env.db_engine) as db:
        assert ingestion_health(db, env.orgs["customer"])["status"] == "unverified"
        assert list(db.scalars(select(CreditBudget))) == []
        now = datetime.now(UTC)
        state = IngestionState(id="native-llm", watermark=now - timedelta(minutes=5), last_success_at=now)
        db.add(state)
        db.commit()
        assert ingestion_health(db, env.orgs["customer"])["status"] == "healthy"
        state.watermark = now - timedelta(minutes=16)
        db.commit()
        assert ingestion_health(db, env.orgs["customer"])["status"] == "stale"


def test_unknown_prices_are_not_endpoint_rates_or_free_and_enforcement_unchanged(env):
    sub = create_key(env)["id"]
    with Session(env.db_engine) as db:
        record(db, env.orgs["customer"], sub, datetime.now(UTC) - timedelta(minutes=5), "test-alias", 1000, 1000)
        db.commit()
        summary = credit_summary_response(db, env.orgs["customer"])
        assert summary.used_credits == "0.0000"  # known lower bound, not a fully priced total
        assert summary.cost_complete is False and summary.unpriced_requests == 1
        assert summary.remaining_credits is None and summary.utilization_pct is None
        assert summary.by_model[0].cost_usd is None
        assert summary.by_model[0].unpriced_requests == 1
        assert _used_credits_for(db, env.orgs["customer"]) == 0
        assert _enforcement_used_credits_for(db, env.orgs["customer"]) == Decimal("0.0030")
        budget = db.scalar(select(CreditBudget).where(CreditBudget.organization_id == env.orgs["customer"]))
        assert _budget_output(db, budget).remaining_credits is None


def test_database_destination_ignores_credentials_but_not_database():
    a = destination("postgresql://api:NEVER-OUTPUT@db.test/turnstile")
    b = destination("postgresql://ingester:OTHER-SECRET@db.test:5432/turnstile")
    assert a == b
    assert "NEVER-OUTPUT" not in str(a) and "api" not in str(a)
    assert destination(None) is None
    assert a != destination("postgresql://ingester@db.test/other")


def test_non_usd_cost_never_silently_converts_to_usd_credits(env):
    sub = create_key(env)["id"]
    with Session(env.db_engine) as db:
        record(db, env.orgs["customer"], sub, datetime.now(UTC) - timedelta(minutes=5))
        db.flush()
        row = db.scalar(select(UsageRecord))
        row.cost, row.currency = Decimal("10"), "EUR"
        db.commit()
        result = credit_summary_response(db, env.orgs["customer"])
        assert result.currency == "USD" and result.used_credits == "0.0000"
        assert result.cost_complete is False and result.remaining_credits is None
        assert result.by_model[0].cost_usd is None
        assert _used_credits_for(db, env.orgs["customer"]) == 0
        # Existing enforcement is deliberately not changed by display repair.
        assert _enforcement_used_credits_for(db, env.orgs["customer"]) == 10