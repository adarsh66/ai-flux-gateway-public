"""Synthetic SQLite/API and SQL compilation only; no external DB or cloud access."""
import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aiflux.finops import (
    TOKEN_BUCKET_INTERVALS,
    bucket_count,
    bucket_origin,
    model_token_query,
    model_token_response,
    token_bucket_interval,
    usage_series_query,
    usage_series_response,
)
from aiflux.models import TeamSubscription, UsageRecord
from sqlalchemy.dialects import mssql, postgresql, sqlite
from sqlalchemy.orm import Session
from test_control_plane import create_key
from test_usage_series import add_usage

SGT = "Asia/Singapore"
USAGE = "/api/usage/timeseries"
TOKENS = "/api/usage/model-tokens"


def params(start, end, granularity="day", time_zone=SGT):
    return {"start": start.isoformat(), "end": end.isoformat(),
            "granularity": granularity, "time_zone": time_zone, "days": 366}


@pytest.mark.parametrize("boundary", [
    datetime(2026, 9, 30, 16, tzinfo=UTC),  # October midnight SGT
    datetime(2025, 12, 31, 16, tzinfo=UTC),  # January/year midnight SGT
])
def test_sgt_calendar_boundaries_shared_with_model_tokens_and_exact_clipping(env, boundary):
    sub = create_key(env)["id"]
    start, end = boundary - timedelta(minutes=3, seconds=17), boundary + timedelta(minutes=2)
    with Session(env.db_engine) as db:
        for when in (start - timedelta(microseconds=1), start,
                     boundary - timedelta(microseconds=1), boundary,
                     end - timedelta(microseconds=1), end):
            add_usage(db, env.orgs["customer"], sub, when)
        db.commit()
    query = params(start, end)
    usage = env.client.get(USAGE, params=query, headers=env.customer)
    tokens = env.client.get(TOKENS, params=query, headers=env.customer)
    assert usage.status_code == tokens.status_code == 200
    series, models = usage.json(), tokens.json()
    assert series["bucket_origin"] == models["bucket_origin"] == "1999-12-31T16:00:00Z"
    assert series["time_zone"] == models["time_zone"] == SGT
    assert series["interval_seconds"] == models["interval_seconds"] == 86400
    assert [row["requests"] for row in series["items"]] == [2, 2]
    for row, model, left, right in zip(series["items"], models["items"],
                                       (start, boundary), (boundary, end), strict=True):
        assert row["minute"] == model["start"] == left.isoformat().replace("+00:00", "Z")
        assert row["end"] == model["end"] == right.isoformat().replace("+00:00", "Z")
        assert row["partial_bucket"] is model["partial_bucket"] is True
        assert row["total_tokens"] == model["total_tokens"] == 30
    utc = env.client.get(USAGE, params=params(start, end, time_zone="UTC"), headers=env.customer).json()
    assert utc["bucket_origin"] == "2000-01-01T00:00:00Z"
    assert len(utc["items"]) == 1 and utc["items"][0]["requests"] == 4


@pytest.mark.parametrize("granularity,seconds", [("minute", 60), ("hour", 3600), ("day", 86400)])
def test_raw_weighted_latency_and_nullable_token_semantics(env, granularity, seconds):
    sub = create_key(env)["id"]
    boundary = datetime(2026, 10, 1, 16, tzinfo=UTC)
    start, end = boundary, boundary + timedelta(seconds=seconds)
    with Session(env.db_engine) as db:
        for _ in range(10):
            add_usage(db, env.orgs["customer"], sub, start, latency=1000)
        add_usage(db, env.orgs["customer"], sub, end - timedelta(seconds=1), latency=11000)
        add_usage(db, env.orgs["customer"], sub, start, inputs=None, outputs=7, latency=None)
        add_usage(db, env.orgs["customer"], sub, start, inputs=0, outputs=0, latency=None)
        db.commit()
    result = env.client.get(USAGE, params=params(start, end, granularity), headers=env.customer)
    assert result.status_code == 200, result.text
    row, = result.json()["items"]
    assert row["avg_e2e_seconds"] == pytest.approx(21 / 11)
    assert row["latency_samples"] == 11 and row["requests"] == 13
    assert row["input_tokens"] == 110 and row["output_tokens"] == 62
    assert row["total_tokens"] == 165 and row["missing_token_requests"] == 1
    assert row["partial_bucket"] is False


def test_generalized_null_empty_and_legacy_rows_unchanged(env):
    sub = create_key(env)["id"]
    start = datetime(2026, 10, 1, 16, 0, 17, tzinfo=UTC)
    end = start + timedelta(seconds=20)
    with Session(env.db_engine) as db:
        add_usage(db, env.orgs["customer"], sub, start, inputs=None, outputs=None, latency=None)
        db.commit()
    explicit = env.client.get(USAGE, params=params(start, end, "minute"), headers=env.customer).json()
    row, = explicit["items"]
    assert row["minute"] == start.isoformat().replace("+00:00", "Z")
    assert row["end"] == end.isoformat().replace("+00:00", "Z") and row["partial_bucket"]
    assert row["input_tokens"] is row["output_tokens"] is row["total_tokens"] is row["avg_e2e_seconds"] is None
    assert row["latency_samples"] == 0
    legacy_params = {"start": start.isoformat(), "end": end.isoformat()}
    legacy = env.client.get(USAGE, params=legacy_params, headers=env.customer).json()
    old, = legacy["items"]
    assert old["minute"] == "2026-10-01T16:00:00Z"
    assert "end" not in old and "partial_bucket" not in old
    assert legacy["time_zone"] == "UTC" and legacy["interval_seconds"] == 60
    for path in (USAGE, TOKENS):
        empty = env.client.get(path, params={**params(start, end, "hour"), "model": "absent"},
                               headers=env.customer).json()
        assert empty["items"] == [] and empty["bucket_origin"] == explicit["bucket_origin"]


@pytest.mark.parametrize("granularity,interval,limit", [
    ("minute", 60, 10080), ("hour", 3600, 744), ("day", 86400, 744),
])
def test_explicit_limits_count_both_partial_edges_and_legacy_has_no_new_guard(env, granularity, interval, limit):
    start = bucket_origin(SGT) + timedelta(days=9500)
    end = start + timedelta(seconds=interval * limit)
    with Session(env.db_engine) as db:
        result = usage_series_response(db, None, None, start, end, granularity=granularity, time_zone=SGT)
        assert result["items"] == [] and result["interval_seconds"] == interval
        with pytest.raises(ValueError, match=str(limit)):
            usage_series_response(db, None, None, start + timedelta(microseconds=1),
                                  end + timedelta(microseconds=1), granularity=granularity, time_zone=SGT)
        if granularity in ("hour", "day"):
            assert model_token_response(db, None, None, start, end, granularity=granularity,
                                        time_zone=SGT)["items"] == []
            with pytest.raises(ValueError, match="744"):
                model_token_response(db, None, None, start + timedelta(microseconds=1),
                                     end + timedelta(microseconds=1), granularity=granularity, time_zone=SGT)
        legacy = usage_series_response(db, None, None, start, end)
        assert legacy["interval_seconds"] == 60


@pytest.mark.parametrize("path", [USAGE, "/api/admin/usage/timeseries", TOKENS, "/api/admin/usage/model-tokens"])
def test_api_invalid_timezone_granularity_and_helpful_limits(env, path):
    headers = env.admin if "/admin/" in path else env.customer
    for query in ({"time_zone": "Europe/London"}, {"time_zone": "+08:00"}, {"granularity": "week"}):
        response = env.client.get(path, params=query, headers=headers)
        assert response.status_code == 422 and response.json()["detail"]
    query = {"days": 90, "granularity": "hour", "time_zone": SGT}
    response = env.client.get(path, params=query, headers=headers)
    assert response.status_code == 422 and "744" in response.json()["detail"]
    assert "viewport" in response.json()["detail"]
    if path.endswith("timeseries"):
        response = env.client.get(path, params={"days": 30, "granularity": "minute"}, headers=headers)
        assert response.status_code == 422 and "10080" in response.json()["detail"]
        assert env.client.get(path, params={"days": 30}, headers=headers).status_code == 200


@pytest.mark.parametrize("path", [USAGE, TOKENS])
def test_sgt_generalized_scope_auth_org_subscription_model_filters(env, path):
    sub, other = create_key(env)["id"], create_key(env, "Other")["id"]
    foreign = str(uuid4())
    now = datetime.now(UTC) - timedelta(minutes=10)
    with Session(env.db_engine) as db:
        db.add(TeamSubscription(id=foreign, organization_id=env.orgs["admin"], name="Foreign", team="IDS",
                                idempotency_key=str(uuid4()), state="active"))
        db.flush()
        for org, sid in ((env.orgs["customer"], sub), (env.orgs["customer"], other), (env.orgs["admin"], foreign)):
            add_usage(db, org, sid, now)
        db.commit()
    query = {"granularity": "day", "time_zone": SGT}
    assert env.client.get(path, params=query).status_code == 401
    assert env.client.get("/api/admin" + path[4:], params=query, headers=env.customer).status_code == 403
    for sid in (foreign, str(uuid4())):
        assert env.client.get(path, params={**query, "subscription_id": sid}, headers=env.customer).status_code == 404
    scoped = env.client.get(path, params={**query, "subscription_id": sub, "model": "test-alias",
                                          "organization_id": env.orgs["admin"]}, headers=env.customer).json()
    assert sum(row["requests"] for row in scoped["items"]) == 1
    admin_path = "/api/admin" + path[4:]
    all_orgs = env.client.get(admin_path, params=query, headers=env.admin).json()
    assert sum(row["requests"] for row in all_orgs["items"]) == 3
    organization = env.client.get(admin_path, params={**query, "organization_id": env.orgs["customer"]},
                                   headers=env.admin).json()
    assert sum(row["requests"] for row in organization["items"]) == 2
    assert env.client.get(admin_path, params={**query, "organization_id": env.orgs["customer"],
                                              "subscription_id": foreign}, headers=env.admin).status_code == 404


@pytest.mark.parametrize("dialect", [mssql.dialect(), postgresql.dialect(), sqlite.dialect()],
                         ids=["mssql", "postgresql", "sqlite"])
@pytest.mark.parametrize("granularity,interval", [("minute", 60), ("hour", 3600), ("day", 86400)])
def test_generalized_cross_dialect_safe_raw_aggregates_and_same_origin(dialect, granularity, interval):
    start = datetime(2026, 10, 1, tzinfo=UTC)
    query = usage_series_query(dialect.name, "org", "sub", start, start + timedelta(days=1),
                               "alias", granularity, SGT)
    token = model_token_query(dialect.name, "org", "sub", start, start + timedelta(days=1), interval, "alias", SGT)
    sql = str(query.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    token_sql = str(token.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    assert "GROUP BY floor(" in sql and "GROUP BY floor(" in token_sql
    assert "avg(CAST(usage_records.e2e_ms AS FLOAT))" in sql
    assert "count(usage_records.e2e_ms)" in sql
    assert "usage_records.organization_id = 'org'" in sql
    assert "usage_records.subscription_id = 'sub'" in sql and "usage_records.model = 'alias'" in sql
    assert "CAST(usage_records.input_tokens AS BIGINT)" in sql and "CAST(usage_records.output_tokens AS BIGINT)" in sql
    if dialect.name == "mssql":
        assert "dateadd(hour, -8, CONVERT(datetime2, '20000101', 112))" in sql
        positional = str(query.compile(dialect=mssql.dialect(paramstyle="qmark")))
        assert "?" not in positional.split(" GROUP BY ")[1]
    else:
        assert "946656000" in sql and "946656000" in token_sql


@pytest.mark.parametrize("days", [1, 7, 30, 90, 366])
def test_auto_intervals_are_origin_aware_and_keep_existing_choices(days):
    start = datetime(2026, 1, 1, 16, 17, tzinfo=UTC)
    end = start + timedelta(days=days, seconds=17)
    interval = token_bucket_interval(start, end, SGT)
    assert interval in TOKEN_BUCKET_INTERVALS
    assert bucket_count(start, end, interval, bucket_origin(SGT)) <= 120
    first, last = (start - bucket_origin(SGT)).total_seconds(), (end - bucket_origin(SGT)).total_seconds()
    expected = next(value for value in TOKEN_BUCKET_INTERVALS
                    if math.ceil(last / value) - math.floor(first / value) <= 120)
    assert interval == expected


def test_invalid_internal_contract_values_fail_before_query(env):
    start = datetime(2026, 10, 1, tzinfo=UTC)
    with Session(env.db_engine) as db:
        with pytest.raises(ValueError, match="Time zone"):
            usage_series_response(db, None, None, start, start + timedelta(hours=1), time_zone="bad")
        with pytest.raises(ValueError, match="granularity"):
            usage_series_response(db, None, None, start, start + timedelta(hours=1), granularity="bad")
        with pytest.raises(ValueError, match="end must be after start"):
            usage_series_response(db, None, None, start, start)
        with pytest.raises(ValueError, match="Time zone"):
            model_token_response(db, None, None, start, start + timedelta(hours=1), time_zone="bad")