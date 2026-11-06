"""Input-only scoring rates share rate-card revisions, never chat economics."""
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_catalog_pricing_correction import accepted  # noqa: F401

from aiflux import rate_card
from aiflux.external_inventory import AcceptedInventory
from aiflux.models import AuditEvent, GatewaySettingsRevision, ModelPrice, UsageRecord
from aiflux.scoring_catalog import scoring_descriptor

BASELINE = datetime(2026, 10, 1, tzinfo=UTC)
CHANGED = datetime(2026, 10, 31, 12, tzinfo=UTC)


def entry(value, when=CHANGED, origin="configured"):
    scope = scoring_descriptor()
    return {**{k: scope[k] for k in ("model", "provider", "region")},
            "input": value, "valid_from": when, "origin": origin}


def put(env, version, **rates):
    return env.client.put("/api/admin/rate-card", headers=env.admin, json={
        "expected_version": version, "rates": [{"model": "Decision-1", **rates}],
    })


def test_rate_input_requires_chat_output_but_forbids_scoring_output_cache_and_write():
    assert rate_card.RateInput(model="Decision-1", input="0").output is None
    with pytest.raises(ValidationError):
        rate_card.RateInput(model="gpt-5.4-mini", input="1")
    for field in ("output", "cached", "write"):
        for value in ("0", "", "0.042"):
            with pytest.raises(ValidationError):
                rate_card.RateInput(model="Decision-1", input="0.042", **{field: value})


@pytest.mark.parametrize("tokens,when,expected", [
    (None, BASELINE, None), (0, BASELINE, Decimal("0")),
    (1_000_000, BASELINE, Decimal("0.042")), (1, BASELINE, Decimal("0.000000042")),
    (1_000_000, BASELINE - timedelta(microseconds=1), None),
    (-1, CHANGED, None), (True, CHANGED, None), (1, CHANGED.replace(tzinfo=None), None),
])
def test_effective_estimate_missing_zero_baseline_and_exact_decimal(tokens, when, expected):
    result = rate_card.scoring_effective_estimate(0, [], tokens, when)
    assert result["estimated_cost_usd"] == expected
    expected_basis = "unestimated" if expected is None else "measured_scoring_input_tokens"
    assert result["estimate_basis"] == expected_basis
    assert result["pricing_revision"] == "decision1-scoring-20261031-v1+rate-card-v0"


def test_date_effective_history_and_reset_are_half_open_and_order_independent():
    reset = CHANGED + timedelta(days=1)
    history = [entry("0.042", reset, "public_list"), entry("2")]
    for when, expected in ((CHANGED - timedelta(microseconds=1), "0.042"),
                           (CHANGED, "2"), (reset - timedelta(microseconds=1), "2"), (reset, "0.042")):
        result = rate_card.scoring_effective_estimate(2, history, 1_000_000, when)
        assert result["estimated_cost_usd"] == Decimal(expected)
    assert rate_card.scoring_effective_estimate(2, history, None, reset)["estimated_cost_usd"] is None
    scoring_periods = rate_card.periods(history, model_kind="scoring")
    assert len(scoring_periods) == 3
    assert scoring_periods[0]["valid_to"] == CHANGED
    assert scoring_periods[1]["valid_to"] == reset
    assert scoring_periods[2]["valid_to"] is None
    assert all("output" not in p and p["billing_dimensions"] == ["input"] for p in scoring_periods)
    assert not any(p["model"] == "Decision-1" for p in rate_card.periods(history))


def test_listed_scoring_scope_never_enters_accepted_chat_scopes(accepted):
    env, inventory = accepted
    assert "Decision-1" not in dict(rate_card.accepted_scopes(env.settings))
    response = env.client.get("/api/admin/rate-card", headers=env.admin)
    assert response.status_code == 200
    items = {i["model"]: i for i in response.json()["items"]}
    assert set(items) == inventory.accepted_aliases(env.settings) | {"Decision-1"}
    item = items["Decision-1"]
    assert item["model_kind"] == "scoring" and item["billing_dimensions"] == ["input"]
    assert item["input"] == item["default_input"] == "0.042"
    assert item["output"] is None and item["default_output"] is None
    assert item["cached"] is None and item["write"] is None
    assert all(i["billing_dimensions"] == ["input", "output"] for m, i in items.items() if m != "Decision-1")


def test_absent_evidence_hides_rate_and_rejects_configuration(accepted, monkeypatch):
    env, inventory = accepted
    inventory.foundry.deployments = [d for d in inventory.foundry.deployments if d.name != "Decision-1"]
    monkeypatch.setattr(AcceptedInventory, "load", classmethod(lambda cls, settings: inventory))
    assert "Decision-1" not in dict(rate_card.listed_scopes(env.settings))
    assert put(env, 0, input="2").status_code == 422


def test_scoring_save_noop_stale_reset_history_and_chat_estimator_isolation(accepted, monkeypatch):
    env, _ = accepted

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return CHANGED

    monkeypatch.setattr(rate_card, "datetime", Frozen)
    with Session(env.db_engine) as db:
        price_query = select(ModelPrice.id, ModelPrice.input_per_million, ModelPrice.output_per_million)
        prices = list(db.execute(price_query))
        usage_count = db.scalar(select(func.count()).select_from(UsageRecord))
        original_chat_periods = rate_card.estimate_args(db)["periods"]
    first = put(env, 0, input="2")
    assert first.status_code == 200, first.text
    assert first.json()["changed"] and first.json()["version"] == 1
    assert put(env, 0, input="3").status_code == 409
    same = put(env, 1, input="2")
    assert same.status_code == 200 and same.json()["version"] == 1 and not same.json()["changed"]
    with Session(env.db_engine) as db:
        version, entries = rate_card.load_state(db)
        assert version == 1 and len(entries) == 1 and "output" not in entries[0]
        price = rate_card.display_price(version, entries, scoring_descriptor())
        assert price["input"] == "2" and price["status"] == "configured" and "output" not in price
        estimate = rate_card.scoring_effective_estimate(version, entries, 1_000_000, CHANGED)
        assert estimate["estimated_cost_usd"] == Decimal("2")
        assert original_chat_periods == rate_card.estimate_args(db)["periods"]
        first_revision = db.scalar(select(GatewaySettingsRevision).where(
            GatewaySettingsRevision.scope == "rate-card", GatewaySettingsRevision.version == 1))
        retained = first_revision.configuration
    reset = put(env, 1, input="0.042")
    assert reset.status_code == 200 and reset.json()["version"] == 2
    with Session(env.db_engine) as db:
        version, entries = rate_card.load_state(db)
        assert version == 2 and len(entries) == 2
        assert entries[1]["origin"] == "public_list"
        assert entries[1]["valid_from"] > entries[0]["valid_from"]
        assert rate_card.display_price(version, entries, scoring_descriptor())["input"] == "0.042"
        estimate = rate_card.scoring_effective_estimate(version, entries, 1_000_000, entries[1]["valid_from"])
        assert estimate["estimated_cost_usd"] == Decimal("0.042")
        assert retained == db.scalar(select(GatewaySettingsRevision.configuration).where(
            GatewaySettingsRevision.scope == "rate-card", GatewaySettingsRevision.version == 1))
        assert prices == list(db.execute(price_query))
        assert usage_count == db.scalar(select(func.count()).select_from(UsageRecord))
        audit_count = db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "rate_card.updated"))
        assert audit_count == 2


def test_scoring_and_chat_entries_coexist_in_the_same_stored_revision(accepted):
    env, _ = accepted
    response = env.client.put("/api/admin/rate-card", headers=env.admin, json={
        "expected_version": 0, "rates": [
            {"model": "Decision-1", "input": "0"},
            {"model": "gpt-5.4-mini", "input": "7", "output": "8"},
        ],
    })
    assert response.status_code == 200, response.text
    with Session(env.db_engine) as db:
        version, entries = rate_card.load_state(db)
        assert version == 1 and len(entries) == 2
        assert {e["model"] for e in entries} == {"Decision-1", "gpt-5.4-mini"}
        assert next(e for e in entries if e["model"] == "Decision-1")["input"] == "0"
        occurred_at = max(BASELINE, *(e["valid_from"] for e in entries))
        estimate = rate_card.scoring_effective_estimate(version, entries, 1_000_000, occurred_at)
        assert estimate["estimated_cost_usd"] == Decimal("0")
        stored = db.scalar(select(GatewaySettingsRevision.configuration).where(
            GatewaySettingsRevision.scope == "rate-card"))
        assert len(json.loads(stored)["entries"]) == 2