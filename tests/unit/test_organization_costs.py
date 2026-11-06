from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event

from aiflux import external_pricing as ep, rate_card
from aiflux.models import Organization, TeamSubscription, UsageRecord
from aiflux.organization_costs import organization_costs
from test_external_pricing import pricing, baseline, save, NOW


def add(p, org, ident, at, model="chat", tokens=1_000_000, **extra):
    sub = "sub-" + org
    if p.db.get(TeamSubscription, sub) is None:
        p.db.add(TeamSubscription(id=sub, organization_id=org, name="t", team="t", idempotency_key=str(uuid4())))
        p.db.flush()
    p.db.add(UsageRecord(id=ident, organization_id=org, subscription_id=sub, model=model,
        provider="Test", region="test", occurred_at=at, input_tokens=tokens,
        output_tokens=tokens, cached_input_tokens=0, cache_write_tokens=0,
        status_code=extra.pop("status_code", 200), completeness="price_missing", **extra))
    p.db.flush()


def test_historical_dual_rates_unknown_zero_inherit_and_scoring_exclusion(pricing):
    p = pricing
    baseline(p)
    add(p, p.org, "before", NOW)
    p.clock.now += timedelta(hours=1)
    save(p, org=p.org, input="0", output="0")
    add(p, p.org, "zero", p.clock.now, status_code=500)
    p.clock.now += timedelta(hours=1)
    save(p, org=p.org, version=1, operation="unknown")
    add(p, p.org, "unknown", p.clock.now)
    p.clock.now += timedelta(hours=1)
    save(p, version=1, input="8", output="9")
    p.clock.now += timedelta(hours=1)
    save(p, org=p.org, version=2, operation="inherit")
    add(p, p.org, "inherit", p.clock.now)
    add(p, p.other, "other", p.clock.now)
    add(p, p.org, "scoring", p.clock.now, model="Decision-1")
    result = organization_costs(p.db, NOW, p.clock.now + timedelta(seconds=1), None, 0, 10)
    a = next(r for r in result["items"] if r["id"] == p.org)
    b = next(r for r in result["items"] if r["id"] == p.other)
    assert a["requests"] == 4
    assert Decimal(a["internal"]["estimated_cost_usd"]) == 9  # failed usage remains unestimated
    assert Decimal(a["external"]["estimated_cost_usd"]) == 20
    assert a["external"]["estimated_requests"] == 2
    assert a["external"]["unestimated_requests"] == 2
    assert Decimal(b["external"]["estimated_cost_usd"]) == 17


def test_batch_snapshot_same_as_single_and_no_owner_leak(pricing):
    p = pricing
    baseline(p)
    save(p, org=p.org, input="99", output="99")
    queries = []
    def capture(conn, cursor, statement, params, context, many):
        if statement.startswith("SELECT"):
            queries.append(statement)
    event.listen(p.engine, "before_cursor_execute", capture)
    try:
        contexts = ep.snapshots_for_organizations(p.db, [p.org, p.other, None])
    finally:
        event.remove(p.engine, "before_cursor_execute", capture)
    assert len(queries) == 1
    for org, context in contexts.items():
        assert context == ep.snapshot(p.db, org)
        assert all(e["owner"] in {"default", "org:" + org} if org else e["owner"] == "default" for e in context._events)
    assert contexts[p.other].display_price(p.chat)["input"] == "1"


def test_page_more_than_ten_stable_order_query_bound_unknown_not_zero(pricing):
    p = pricing
    orgs = sorted([p.org, p.other] + [str(uuid4()) for _ in range(10)])
    for org in orgs:
        if p.db.get(Organization, org) is None:
            p.db.add(Organization(id=org, name="Same", tenant_id=str(uuid4())))
            p.db.flush()
        add(p, org, org, NOW, tokens=0)
    queries = []
    def capture(conn, cursor, statement, params, context, many):
        if statement.startswith("SELECT"):
            queries.append(statement)
    event.listen(p.engine, "before_cursor_execute", capture)
    try:
        result = organization_costs(p.db, NOW, NOW + timedelta(seconds=1), None, 0, 10)
    finally:
        event.remove(p.engine, "before_cursor_execute", capture)
    assert result["total"] == 12 and [r["id"] for r in result["items"]] == orgs[:10]
    assert len(queries) <= 16  # two page + internal load/aggregate + batch + <=10
    assert all(r["external"]["estimated_cost_usd"] is None for r in result["items"])
    assert all(r["external"]["unestimated_requests"] == 1 for r in result["items"])
    assert [r["id"] for r in organization_costs(p.db, NOW, NOW + timedelta(seconds=1), None, 10, 10)["items"]] == orgs[10:]


def test_zero_tiny_unknown_completion_alias_and_missing_attribution(pricing):
    p = pricing
    baseline(p)
    save(p, org=p.org, input="0", output="0")
    add(p, p.org, "zero", NOW, tokens=1)
    add(p, p.other, "tiny", NOW, tokens=1)
    add(p, p.other, "legacy", NOW, model="retired-completion", tokens=1)
    result = organization_costs(p.db, NOW, NOW + timedelta(seconds=1), None, 0, 10)
    a = next(r for r in result["items"] if r["id"] == p.org)
    b = next(r for r in result["items"] if r["id"] == p.other)
    assert Decimal(a["external"]["estimated_cost_usd"]) == 0
    assert Decimal(b["external"]["estimated_cost_usd"]) == Decimal("0.000003")
    assert b["requests"] == 2 and b["external"]["unestimated_requests"] == 1


@pytest.mark.parametrize("params", [{"limit": 11}, {"offset": -1}, {"limit": 0}, {"start": "2026-11-01T00:00:00Z"}])
def test_endpoint_validation(env, params):
    assert env.client.get("/api/admin/usage/organization-costs", params=params, headers=env.admin).status_code == 422


def test_endpoint_admin_only_and_empty(env):
    path = "/api/admin/usage/organization-costs"
    assert env.client.get(path).status_code == 401
    assert env.client.get(path, headers=env.customer).status_code == 403
    response = env.client.get(path, headers=env.admin)
    assert response.status_code == 200 and response.json()["items"] == []