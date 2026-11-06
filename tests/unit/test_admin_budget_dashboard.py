"""Admin-only budget snapshot and archive read/write boundaries; synthetic DB only."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aiflux import monthly_budgets as budgets, rate_card
from aiflux.models import AuditEvent, Organization, OrganizationMonthlyBudgetPolicy, OrganizationMonthlyBudgetRevision
from aiflux.schemas import MonthlyBudgetSummary
from test_monthly_budgets import monthly, configure_prices, usage, allocate, NOW


def test_archive_filter_before_count_and_pagination_disabled_included(monthly):
    p = monthly
    rows = [Organization(id=str(uuid4()), name=f"Interleaved {i:03d}", tenant_id=str(uuid4()),
                         enabled=i % 3 != 0, deleted_at=NOW if i % 2 else None) for i in range(206)]
    p.db.add_all(rows)
    p.db.commit()
    for state, expected in [("current", 105), ("archived", 103)]:
        first = budgets.list_summaries(p.db, limit=100, archive_state=state)
        tail = budgets.list_summaries(p.db, offset=100, limit=100, archive_state=state)
        items = first["items"] + tail["items"]
        assert first["total"] == tail["total"] == expected == len(items)
        assert len({r.organization_id for r in items}) == expected
        assert all((r.archived_at is not None) == (state == "archived") for r in items)
        assert [(r.organization_name, r.organization_id) for r in items] == sorted((r.organization_name, r.organization_id) for r in items)
    assert budgets.list_summaries(p.db, offset=1000, archive_state="archived")["items"] == []
    with pytest.raises(HTTPException) as error:
        budgets.list_summaries(p.db, archive_state="all")
    assert error.value.status_code == 422


def test_admin_same_snapshot_internal_historical_basis_not_external_or_ledger(monthly, monkeypatch):
    p = monthly
    configure_prices(p)
    # Actual SQL estimator with independent historical internal periods.
    start, end = budgets.month_window(NOW)
    boundary = NOW - timedelta(hours=1)
    monkeypatch.setattr(rate_card, "estimate_args", lambda db: {
        "periods": [{"model": "chat", "provider": "Test", "region": "test", "input": "4", "output": "6",
                     "valid_from": start, "valid_to": boundary},
                    {"model": "chat", "provider": "Test", "region": "test", "input": "8", "output": "12",
                     "valid_from": boundary, "valid_to": None}], "revision": "internal-test-v2"})
    usage(p, at=start - timedelta(microseconds=1))
    usage(p, at=start)
    usage(p, at=boundary, sid=p.subs[1])
    usage(p, at=NOW)
    usage(p, at=NOW + timedelta(microseconds=1))
    usage(p, at=end)
    usage(p, model="Decision-1")
    usage(p, sid=p.subs[2])
    # Archived subscriptions still own retained usage.
    from aiflux.models import TeamSubscription
    p.db.get(TeamSubscription, p.subs[1]).deleted_at = NOW
    p.db.commit()
    snapshot = budgets.admin_dashboard(p.db, p.org, at=NOW)
    assert snapshot.as_of == snapshot.budget.as_of == budgets.iso(NOW)
    assert snapshot.budget.period_start == budgets.iso(start)
    assert snapshot.internal_basis == "internal_price_estimate" and snapshot.internal_scope == "completion_usage"
    assert snapshot.internal.estimated_requests == 3
    assert Decimal(snapshot.internal.estimated_cost_usd) == 50
    assert Decimal(snapshot.budget.estimated_used_usd) == 9
    assert snapshot.internal.pricing_revision == "internal-test-v2"
    assert not snapshot.read_only and snapshot.archived_at is None
    assert set(snapshot.budget.model_dump()) == set(MonthlyBudgetSummary.model_fields)


def test_archived_save_rejected_before_cas_history_audit_and_disabled_valid(monthly):
    p = monthly
    p.db.get(Organization, p.org).enabled = False
    p.db.commit()
    allocate(p)
    p.db.get(Organization, p.org).deleted_at = NOW
    p.db.commit()
    for expected in [0, 1, 99]:
        with pytest.raises(HTTPException) as error:
            allocate(p, version=expected)
        assert error.value.status_code == 409 and "archived" in error.value.detail
    assert p.db.scalar(select(OrganizationMonthlyBudgetPolicy.version)) == 1
    for model in [AuditEvent, OrganizationMonthlyBudgetRevision]:
        assert p.db.scalar(select(func.count()).select_from(model)) == 1
    assert budgets.history(p.db, p.org)["total"] == 1
    out = budgets.admin_dashboard(p.db, p.org, at=NOW)
    assert out.read_only and out.archived_at == budgets.iso(NOW)


def test_admin_route_privacy_current_archived_and_history(env):
    org = env.orgs["customer"]
    path = "/api/admin/monthly-budgets/" + org
    for target in [path, path + "/history", "/api/admin/monthly-budgets?archive_state=archived"]:
        assert env.client.get(target).status_code == 401
        assert env.client.get(target, headers=env.customer).status_code == 403
    assert env.client.get(path, headers=env.admin).status_code == 200
    with Session(env.db_engine) as db:
        db.get(Organization, org).deleted_at = NOW
        db.commit()
    out = env.client.get(path, headers=env.admin)
    assert out.status_code == 200 and out.json()["read_only"]
    assert out.json()["archived_at"]
    current = env.client.get("/api/admin/monthly-budgets", headers=env.admin).json()
    archived = env.client.get("/api/admin/monthly-budgets?archive_state=archived", headers=env.admin).json()
    assert all(r["organization_id"] != org for r in current["items"])
    assert [r["organization_id"] for r in archived["items"]] == [org]
    assert env.client.put(path, headers=env.admin, json={"allocated_usd": "10", "expected_version": 0, "reason": "blocked synthetic"}).status_code == 409
    assert env.client.get(path + "/history", headers=env.admin).status_code == 200
    assert env.client.get("/api/admin/monthly-budgets?archive_state=all", headers=env.admin).status_code == 422


@pytest.mark.parametrize("known", [False, True])
def test_internal_unknown_partial_cache_and_non_usd_ledger_not_substituted(monthly, monkeypatch, known):
    p = monthly
    configure_prices(p)
    monkeypatch.setattr(rate_card, "estimate_args", lambda db: {
        "periods": [{"model": "chat", "provider": "Test", "region": "test", "input": "4", "output": "6"}],
        "revision": "internal-partial"})
    usage(p, model="unpriced-completion")
    if known:
        row = usage(p, cached=500_000)
        row.currency = "EUR"
        row.cost = Decimal("987654")
        p.db.commit()
    snapshot = budgets.admin_dashboard(p.db, p.org, at=NOW)
    assert snapshot.internal.unestimated_requests == 1
    assert snapshot.internal.estimated_requests == int(known)
    # No cached rate: retain the existing approximate uncached-price subtotal.
    assert snapshot.internal.approximate_requests == int(known)
    assert (Decimal(snapshot.internal.estimated_cost_usd) == 10) if known else snapshot.internal.estimated_cost_usd is None
    assert snapshot.internal.pricing_revision == "internal-partial"
    assert not snapshot.budget.estimate_complete


def test_customer_budget_payload_never_evaluates_or_exposes_internal_estimate(env, monkeypatch):
    from aiflux import organization_costs
    from aiflux.schemas import MonthlyBudgetSummary

    def forbidden(*args, **kwargs):
        pytest.fail("Customer read evaluated internal pricing")

    monkeypatch.setattr(organization_costs, "internal_completion_estimate", forbidden)
    response = env.client.get("/api/budget/monthly", headers=env.customer)
    assert response.status_code == 200
    assert set(response.json()) == set(MonthlyBudgetSummary.model_fields)
    assert "internal" not in response.text
    for path in ("/api/admin/monthly-budgets/"+env.orgs["admin"],
                 "/api/admin/monthly-budgets/"+env.orgs["customer"]):
        assert env.client.get(path, headers=env.customer).status_code == 403