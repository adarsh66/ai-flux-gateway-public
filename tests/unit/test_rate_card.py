"""One rate card feeds the catalog and every estimate; display only, never a gate."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_catalog_pricing_correction import accepted  # noqa: F401

from aiflux import rate_card
from aiflux.display_pricing import detail_estimates, estimate_summary
from aiflux.models import GatewaySettings, GatewaySettingsRevision, ModelPrice, UsageRecord
from aiflux.turnstile_exchange import list_model_garden

ALIAS = "gpt-5.4-mini"
SAVED_AT = datetime(2026, 10, 28, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return SAVED_AT

    monkeypatch.setattr(rate_card, "datetime", Frozen)


def rows(client, headers):
    response = client.get("/api/admin/rate-card", headers=headers)
    assert response.status_code == 200, response.text
    return response.json(), {i["model"]: i for i in response.json()["items"]}


def put(client, headers, version, **rates):
    body = {"expected_version": version, "rates": [{"model": m, **r} for m, r in rates.items()]}
    return client.put("/api/admin/rate-card", headers=headers, json=body)


def usage(db, **kwargs):
    values = dict(id="u1", organization_id="org", subscription_id="sub", model=ALIAS,
                  provider="OpenAI", region="eastus", occurred_at=datetime(2026, 10, 27, 12, tzinfo=UTC),
                  input_tokens=1_000_000, output_tokens=1_000_000, cached_input_tokens=None,
                  cache_write_tokens=None, cost=None, currency=None, status_code=200,
                  completeness="price_missing")
    db.add(UsageRecord(**(values | kwargs)))
    db.flush()


def test_admin_only_and_every_accepted_model_listed(accepted):
    env, inventory = accepted
    assert env.client.get("/api/admin/rate-card", headers=env.customer).status_code == 403
    assert env.client.put("/api/admin/rate-card", headers=env.customer, json={
        "expected_version": 0, "rates": [{"model": ALIAS, "input": "1", "output": "1"}]}).status_code == 403
    page, items = rows(env.client, env.admin)
    expected = inventory.accepted_aliases(env.settings)
    assert len(expected) == 13  # Historical fixture; additive pricing is not route acceptance.
    assert set(items) == expected | {"Decision-1"}
    assert items["Decision-1"]["model_kind"] == "scoring"
    assert items["Decision-1"]["billing_dimensions"] == ["input"]
    assert page["version"] == 0 and page["total"] == len(items) == len(expected) + 1
    assert items[ALIAS]["origin"] != "configured" and items[ALIAS]["input"] is not None


def test_change_updates_catalog_and_estimates_without_touching_prices_or_costs(accepted):
    env, _ = accepted
    page, items = rows(env.client, env.admin)
    default_input = items[ALIAS]["input"]
    with Session(env.db_engine) as db:
        usage(db)
        db.commit()
        prices = list(db.execute(select(ModelPrice.id, ModelPrice.input_per_million, ModelPrice.effective_to)))
        before = estimate_summary(db, [], **rate_card.estimate_args(db))[0]
    response = put(env.client, env.admin, 0, **{ALIAS: {"input": "10", "output": "20", "cached": "1"}})
    assert response.status_code == 200, response.text
    body = response.json()
    row = {i["model"]: i for i in body["items"]}[ALIAS]
    assert body["version"] == 1 and body["changed"] and row["origin"] == "configured"
    assert (row["input"], row["output"], row["cached"]) == ("10", "20", "1")
    assert row["default_input"] == default_input
    with Session(env.db_engine) as db:
        price = next(i for i in list_model_garden(db, env.settings) if i.id == ALIAS).display_price
        assert price["status"] == "configured" and price["input"] == "10" and price["output"] == "20"
        assert "+rate-card-v1" in price["revision"]
        after = estimate_summary(db, [], **rate_card.estimate_args(db))[0]
        # Existing usage predates the new rate and keeps its estimate; new usage uses it.
        assert after["estimated_cost_usd"] == before["estimated_cost_usd"] == "5.250000000000"
        usage(db, id="u2", occurred_at=SAVED_AT + timedelta(days=1))
        detail = detail_estimates(db, ["u2"], **rate_card.estimate_args(db))
        assert Decimal(detail["u2"]["estimated_cost_usd"]) == Decimal("30")
        assert prices and prices == list(db.execute(select(
            ModelPrice.id, ModelPrice.input_per_million, ModelPrice.effective_to)))
        assert all(r.cost is None and r.completeness == "price_missing" for r in db.scalars(select(UsageRecord)))


def test_stale_version_invalid_unknown_and_noop(accepted):
    env, _ = accepted
    assert put(env.client, env.admin, 0, **{ALIAS: {"input": "2", "output": "3"}}).status_code == 200
    assert put(env.client, env.admin, 0, **{ALIAS: {"input": "4", "output": "5"}}).status_code == 409
    for bad in ({"input": "-1", "output": "1"}, {"input": "abc", "output": "1"},
                {"input": "1", "output": "1e9"}, {"input": "1", "output": "0.000000001"}):
        assert put(env.client, env.admin, 1, **{ALIAS: bad}).status_code == 422
    assert put(env.client, env.admin, 1, **{"not-a-model": {"input": "1", "output": "1"}}).status_code == 422
    same = put(env.client, env.admin, 1, **{ALIAS: {"input": "2", "output": "3"}})
    assert same.status_code == 200 and same.json()["version"] == 1 and not same.json()["changed"]
    with Session(env.db_engine) as db:
        assert db.scalar(select(func.count()).select_from(GatewaySettingsRevision)
                         .where(GatewaySettingsRevision.scope == "rate-card")) == 1


def test_reset_to_default_restores_bundled_rate_and_keeps_history(accepted):
    env, _ = accepted
    _, items = rows(env.client, env.admin)
    default = items[ALIAS]
    rates = {k: default["default_" + k] for k in ("input", "output", "cached", "write")
             if default["default_" + k] is not None}
    assert put(env.client, env.admin, 0, **{ALIAS: {"input": "9", "output": "9"}}).status_code == 200
    reset = put(env.client, env.admin, 1, **{ALIAS: rates})
    assert reset.status_code == 200 and reset.json()["version"] == 2
    row = {i["model"]: i for i in reset.json()["items"]}[ALIAS]
    assert row["origin"] != "configured" and row["input"] == default["default_input"]
    with Session(env.db_engine) as db:
        assert db.get(GatewaySettings, "rate-card").version == 2
        assert db.scalar(select(func.count()).select_from(GatewaySettingsRevision)
                         .where(GatewaySettingsRevision.scope == "rate-card")) == 2
        price = next(i for i in list_model_garden(db, env.settings) if i.id == ALIAS).display_price
        assert price["status"] != "configured" and price["input"] == default["default_input"]


def test_unpriced_fireworks_models_get_labelled_estimate_and_can_be_configured(accepted):
    env, _ = accepted
    _, items = rows(env.client, env.admin)
    for alias in [a for a, i in items.items() if i["provider"] == "Fireworks"]:
        assert items[alias]["origin"] == "platform_default" and items[alias]["input"] is not None
        with Session(env.db_engine) as db:
            price = next(i for i in list_model_garden(db, env.settings) if i.id == alias).display_price
            assert price["status"] == "platform_default" and price["assumption"]


def test_unreadable_store_falls_back_to_bundled_rates(accepted):
    env, _ = accepted
    assert put(env.client, env.admin, 0, **{ALIAS: {"input": "7", "output": "8"}}).status_code == 200
    with Session(env.db_engine) as db:
        db.get(GatewaySettingsRevision, db.scalar(select(GatewaySettingsRevision.id))).configuration = "{broken"
        db.commit()
        assert rate_card.load_state(db) == (0, [])
        price = next(i for i in list_model_garden(db, env.settings) if i.id == ALIAS).display_price
        assert price["status"] != "configured"


def test_optional_auto_sync_exception_after_commit_returns_saved_pending(accepted, monkeypatch):
    from aiflux import auto_pricing
    env, _ = accepted
    env.settings.auto_pricing_sync_enabled = True
    def broken(*args, **kwargs):
        raise RuntimeError("not safe for response")
    monkeypatch.setattr(auto_pricing, "reconcile", broken)
    saved = put(env.client, env.admin, 0, **{ALIAS: {"input": "7", "output": "8"}})
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1 and saved.json()["changed"]
    assert saved.json()["auto_pricing"]["state"] == "pending"
    assert saved.json()["auto_pricing"]["access_gated"] is False
    assert "not safe for response" not in saved.text
    with Session(env.db_engine) as db:
        assert db.get(GatewaySettings, "rate-card").version == 1
        assert rate_card.load_state(db)[1][-1]["input"] == "7"
