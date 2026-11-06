from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, insert
from sqlalchemy.dialects import mssql, postgresql
from sqlalchemy.orm import Session

from aiflux.finops import usage_rankings
from aiflux.models import Organization, TeamSubscription, UsageRecord
from test_usage_filters import row, MODEL


@pytest.fixture
def ranked(env):
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    start = end - timedelta(days=1)
    orgs = [str(uuid4()) for _ in range(3)]
    subs = sorted(str(uuid4()) for _ in range(14))
    with Session(env.db_engine) as db:
        db.add_all(Organization(id=o, name="Duplicate org", tenant_id=str(uuid4())) for o in orgs)
        db.flush()
        db.add_all(TeamSubscription(id=s, organization_id=orgs[0] if i < 12 else orgs[i - 11],
                                   name="Duplicate sub", team="Shared", idempotency_key=str(uuid4()))
                   for i, s in enumerate(subs))
        db.flush()
        db.execute(insert(UsageRecord), [
            *(row(orgs[0], s, occurred_at=start, input_tokens=10, output_tokens=5,
                  cached_input_tokens=8, cache_write_tokens=2) for s in subs[:12]),
            row(orgs[1], subs[12], occurred_at=start, input_tokens=180, output_tokens=0, status_code=429),
            row(orgs[2], subs[13], occurred_at=start, input_tokens=None, output_tokens=7,
                completeness="usage_missing", status_code=500),
            row(orgs[0], subs[0], occurred_at=start + timedelta(seconds=1), input_tokens=9,
                output_tokens=None, completeness="usage_missing"),
            row(orgs[0], subs[0], "excluded", occurred_at=start, input_tokens=999),
            row(orgs[0], subs[0], occurred_at=end, input_tokens=999),
            row(orgs[0], subs[0], occurred_at=start - timedelta(microseconds=1), input_tokens=999),
        ])
        db.commit()
    return orgs, subs, {"start": start.isoformat(), "end": end.isoformat(), "days": 1, "model": MODEL}


def get(env, params, **extra):
    response = env.client.get("/api/admin/usage/rankings", params={**params, **extra}, headers=env.admin)
    assert response.status_code == 200, response.text
    return response.json()


def test_global_grouping_ties_full_scope_shares_and_partial_observations(env, ranked):
    orgs, subs, params = ranked
    first = get(env, params, limit=1, organization_id=orgs[2], subscription_id=subs[13])
    second = get(env, params, limit=1, offset=1)
    assert first["total"] == 3
    assert first["organization_id"] is None
    assert [first["items"][0]["id"], second["items"][0]["id"]] == sorted(orgs[:2])
    assert first["totals"] == {"requests": 15, "input_tokens": 309, "output_tokens": 67,
                               "total_tokens": 360, "missing_token_requests": 2, "incomplete_requests": 2}
    assert first["items"][0]["share"] == 0.5
    partial = get(env, params, offset=2)["items"][0]
    assert partial["id"] == orgs[2] and partial["total_tokens"] is None
    assert partial["input_tokens"] is None and partial["output_tokens"] == 7
    assert partial["share"] is None and partial["missing_token_requests"] == 1
    empty_page = get(env, params, offset=500)
    assert empty_page["items"] == [] and empty_page["totals"] == first["totals"]


def test_subscription_ranking_counts_all_groups_not_page_and_matches_details(env, ranked):
    orgs, subs, params = ranked
    result = get(env, params, dimension="subscriptions", organization_id=orgs[0], limit=5,
                 subscription_id=subs[0])  # Detail selection must not restrict comparisons.
    assert result["total"] == 12
    assert [r["id"] for r in result["items"]] == subs[:5]
    assert result["totals"]["total_tokens"] == 180
    assert all(r["share"] == pytest.approx(1 / 12) for r in result["items"])
    assert result["items"][0]["input_tokens"] == 19
    assert result["items"][0]["total_tokens"] == 15
    assert get(env, params, dimension="subscriptions", organization_id=orgs[0], offset=10)["items"][-1]["id"] == subs[11]
    detail = env.client.get("/api/admin/usage", params={**params, "organization_id": orgs[0]}, headers=env.admin).json()
    assert detail["summary"]["total_tokens"] == result["totals"]["total_tokens"]
    assert detail["summary"]["requests"] == result["totals"]["requests"]
    models = env.client.get("/api/admin/usage/models", params={**params, "organization_id": orgs[0]}, headers=env.admin)
    assert models.status_code == 200
    assert set(models.json()["items"]) == {MODEL, "excluded", "test-alias"}


def test_empty_unknown_and_measured_zero_are_distinct(env, ranked):
    orgs, subs, params = ranked
    empty = get(env, params, model="no-data")
    assert empty["total"] == 0 and empty["totals"]["total_tokens"] is None
    assert empty["totals"]["requests"] == 0
    with Session(env.db_engine) as db:
        db.execute(insert(UsageRecord), [row(orgs[0], subs[0], "zero", occurred_at=datetime.fromisoformat(params["start"]), input_tokens=0, output_tokens=0)])
        db.commit()
    zero = get(env, params, model="zero")
    assert zero["items"][0]["total_tokens"] == 0 and zero["items"][0]["share"] is None


@pytest.mark.parametrize("params,status", [
    ({"dimension": "subscriptions"}, 422),
    ({"dimension": "subscriptions", "organization_id": str(uuid4())}, 404),
    ({"dimension": "invalid"}, 422), ({"limit": 101}, 422), ({"offset": -1}, 422),
    ({"start": "2026-10-28T00:00:00Z"}, 422),
    ({"start": "2026-10-28T00:00:00", "end": "2026-10-28T01:00:00"}, 422),
])
def test_ranking_validation(env, params, status):
    assert env.client.get("/api/admin/usage/rankings", params=params, headers=env.admin).status_code == status


def test_rankings_require_admin(env):
    assert env.client.get("/api/admin/usage/rankings").status_code == 401
    assert env.client.get("/api/admin/usage/rankings", headers=env.customer).status_code == 403


def test_admin_model_options_share_exact_viewport_and_subscription_ownership(env, ranked):
    orgs, subs, params = ranked
    start, end = datetime.fromisoformat(params["start"]), datetime.fromisoformat(params["end"])
    with Session(env.db_engine) as db:
        db.execute(insert(UsageRecord), [
            row(orgs[0], subs[0], "before-only", occurred_at=start - timedelta(microseconds=1)),
            row(orgs[0], subs[0], "end-only", occurred_at=end),
            row(orgs[0], subs[1], "other-sub-only", occurred_at=start),
        ])
        db.commit()
    query = {**params, "organization_id": orgs[0], "subscription_id": subs[0]}
    response = env.client.get("/api/admin/usage/models", params=query, headers=env.admin)
    assert response.status_code == 200
    assert set(response.json()["items"]) == {MODEL, "excluded", "test-alias"}
    for suffix in ("", "/models", "/timeseries", "/model-tokens", "/export"):
        wrong_scope = env.client.get("/api/admin/usage" + suffix,
                                     params={**query, "organization_id": orgs[1]}, headers=env.admin)
        assert wrong_scope.status_code == 404


def test_large_dataset_two_sql_queries_bound_parameters_and_portable_sql(env, ranked):
    orgs, subs, params = ranked
    with Session(env.db_engine) as db:
        db.execute(insert(UsageRecord), [row(orgs[0], subs[0], occurred_at=datetime.fromisoformat(params["start"])) for _ in range(3000)])
        db.commit()
        queries = []
        def capture(conn, clause, multiparams, parameters, execution_options):
            queries.append(clause)
        event.listen(env.db_engine, "before_execute", capture)
        try:
            result = usage_rankings(db, "organizations", None, datetime.fromisoformat(params["start"]),
                                    datetime.fromisoformat(params["end"]), MODEL, 0, 1)
        finally:
            event.remove(env.db_engine, "before_execute", capture)
    assert len(queries) == 2
    assert result["total"] == 3 and result["totals"]["requests"] == 3015
    for dialect in (mssql.dialect(), postgresql.dialect()):
        for query in queries:
            compiled = query.compile(dialect=dialect)
            assert MODEL in compiled.params.values() and MODEL not in str(compiled)
            assert "GROUP BY" in str(compiled)