"""Display estimates must not mutate canonical costs or financial controls."""
import csv
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import mssql, postgresql, sqlite
from sqlalchemy.orm import Session

from aiflux.display_pricing import catalog_price, detail_estimates, estimate_expressions, estimate_summary, manifest
from aiflux.finops import calculate_cost, usage_csv, usage_response
from aiflux.models import Base, UsageRecord

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def usage(db, id="r", **kwargs):
    values = dict(id=id, organization_id="org", subscription_id="sub", model="glm-5.3",
                  provider="ModelArts", region="ap-southeast-1", occurred_at=NOW,
                  input_tokens=100, output_tokens=20, cached_input_tokens=None, cache_write_tokens=None,
                  cost=None, currency=None, status_code=200, completeness="price_missing")
    db.add(UsageRecord(**(values | kwargs)))
    db.flush()


def test_manifest_exact_current_eleven_and_sources():
    accepted = json.loads(Path("services/usage-ingestion/ingestion-approved.json").read_text())
    tuples = {(r["id"], r["provider"], r["region"]) for r in accepted["models"] if r["enabled"]}
    priced = {(r["model"], r["provider"], r["region"])
              for r in manifest()["rates"] if r["status"] != "unknown"}
    unknown = {(r["model"], r["provider"], r["region"])
               for r in manifest()["rates"] if r["status"] == "unknown"}
    assert priced | unknown == tuples and not priced & unknown
    assert unknown == {("FW-GLM-5.3", "Fireworks", "eastus"), ("FW-MiniMax-M3", "Fireworks", "eastus")}
    assert len(tuples) == 13
    for model, provider, region in unknown:
        assert catalog_price(model, provider, region) is None
    for model, provider, region in priced:
        price = catalog_price(model, provider, region)
        assert price["source_url"].startswith("https://")
        assert price["checked_at"] == "2026-10-27"
        assert price["unit"] == "per_million_tokens"
        assert len(price["manifest_sha256"]) == 64
    glm = catalog_price("glm-5.3", "ModelArts", "ap-southeast-1")
    assert glm["status"] == "tbc" and glm["cny_per_usd_assumption"] == "7"
    assert "NOT ModelArts" in glm["assumption"]
    assert catalog_price("glm-5.3", "ModelArts", "eastus") is None


def test_glm_in_total_details_and_no_recorded_write(db):
    usage(db)
    usage(db, "luna", model="gpt-5.6-luna", provider="OpenAI", region="eastus")
    summary = estimate_summary(db, [])[0]
    details = detail_estimates(db, ["r", "luna"])
    assert summary["estimated_requests"] == 2
    assert summary["approximate_requests"] == 2
    assert Decimal(summary["estimated_cost_usd"]) == sum(Decimal(d["estimated_cost_usd"]) for d in details.values())
    assert Decimal(details["r"]["estimated_cost_usd"]) == Decimal("0.000194285714")
    for row in db.scalars(select(UsageRecord)):
        assert row.cost is None and row.currency is None and row.completeness == "price_missing"
        assert calculate_cost(row, None) == (None, "price_missing")
    assert not db.dirty


@pytest.mark.parametrize("override", [
    {"input_tokens": None}, {"output_tokens": None}, {"input_tokens": -1},
    {"cached_input_tokens": 101}, {"cache_write_tokens": -1},
    {"cached_input_tokens": 60, "cache_write_tokens": 60},
    {"completeness": "retry_usage_unknown"}, {"completeness": "backend_attribution_missing"},
    {"completeness": "status_missing"}, {"completeness": "usage_missing"},
    {"status_code": 429}, {"status_code": 500}, {"provider": "OpenAI"}, {"region": "eastus"},
    {"occurred_at": datetime(2026, 10, 27, 6, tzinfo=UTC)},
])
def test_unsafe_usage_stays_unestimated(db, override):
    usage(db, **override)
    result = estimate_summary(db, [])[0]
    assert result["estimated_cost_usd"] is None
    assert result["unestimated_requests"] == 1


def test_cache_measured_zero_discount_and_missing_not_zero(db):
    usage(db, input_tokens=1000, output_tokens=100, cached_input_tokens=500, cache_write_tokens=0)
    usage(db, "missing", input_tokens=1000, output_tokens=100)
    details = detail_estimates(db, ["r", "missing"])
    assert details["r"]["estimate_basis"] == "measured_cache_detail"
    assert details["missing"]["estimate_basis"] == "standard_input_approximation"
    assert Decimal(details["r"]["estimated_cost_usd"]) < Decimal(details["missing"]["estimated_cost_usd"])
    assert db.get(UsageRecord, "missing").cached_input_tokens is None


def test_scope_summary_model_subscription_csv_reconcile(db):
    usage(db)
    usage(db, "other", organization_id="other", subscription_id="other")
    usage(db, "tiny", input_tokens=1, output_tokens=0)
    start, end = NOW - timedelta(minutes=1), NOW + timedelta(minutes=1)
    response = usage_response(db, "org", 1, None, 0, 1, start=start, end=end)
    assert response["summary"]["requests"] == 2 and len(response["items"]) == 1
    records = list(csv.DictReader(io.StringIO(usage_csv(db, "org", 1, None, start=start, end=end))))
    amount = Decimal(response["summary"]["estimated_cost_usd"])
    assert amount == sum(Decimal(r["estimated_cost_usd"]) for r in records)
    for group in (UsageRecord.model, UsageRecord.subscription_id, UsageRecord.organization_id):
        grouped = estimate_summary(db, [UsageRecord.organization_id == "org"], group)
        assert amount == sum(Decimal(r["estimated_cost_usd"]) for r in grouped)
    assert all(r["cost"] == "" for r in records)
    assert Decimal(next(r for r in records if r["id"] == "tiny")["estimated_cost_usd"]) > 0


def test_half_open_window_and_no_data(db):
    usage(db)
    assert estimate_summary(db, [UsageRecord.occurred_at < NOW])[0]["estimated_cost_usd"] is None
    result = estimate_summary(db, [UsageRecord.occurred_at >= NOW])[0]
    assert result["estimated_requests"] == 1


def test_short_context_only(db):
    usage(db, model="gpt-6.1-sol", provider="OpenAI", region="eastus", input_tokens=128001)
    assert estimate_summary(db, [])[0]["estimated_cost_usd"] is None


def test_credit_breakdowns_match_usage_without_repricing_budget(env):
    from aiflux.turnstile_exchange import credit_summary_response

    response = env.client.post("/api/admin/subscriptions", headers=env.admin | {"Idempotency-Key": env.idempotency()},
                               json={"organization_id": env.orgs["customer"], "name": "Pricing POC", "team": "Test"})
    assert response.status_code in (200, 201), response.text
    sid = response.json()["id"]
    with Session(env.db_engine) as session:
        usage(session, organization_id=env.orgs["customer"], subscription_id=sid,
              occurred_at=datetime.now(UTC) - timedelta(seconds=1))
        session.commit()
        result = credit_summary_response(session, env.orgs["customer"])
        assert result.estimated_requests == 1
        assert result.estimated_cost_usd is not None
        assert result.used_credits == "0.0000"
        assert result.remaining_credits is None and not result.cost_complete
        for breakdown in (result.by_model, result.by_product, result.by_channel):
            assert result.estimated_cost_usd == breakdown[0].estimated_cost_usd
            assert breakdown[0].cost_usd is None
        assert session.get(UsageRecord, "r").cost is None


@pytest.mark.parametrize("dialect", [postgresql.dialect(), sqlite.dialect(), mssql.dialect()])
def test_sql_is_portable_and_read_only(dialect):
    amount, approximation = estimate_expressions()
    sql = str(select(UsageRecord.id, amount, approximation).compile(dialect=dialect)).upper()
    assert "SELECT" in sql and "CASE" in sql
    assert not any(word in sql for word in ("INSERT ", "UPDATE ", "DELETE "))