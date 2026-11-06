"""Synthetic local accounting regression; no production DB or runtime proof."""
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux.catalog import Catalog
from aiflux.ingestion import extract_usage, ingest_rows
from aiflux.models import UsageRecord
from test_control_plane import create_key
from test_finops_ingestion import price, usage_trace


def decision_trace(tokens):
    return [{"source": "aiflux", "metadata": {
        "category": "decision-overhead",
        "payload": json.dumps({
            "schema": "decision-overhead-v1", "request_id": "decision-accounting-test",
            "routing_profile": "balanced", "selected_model": "test-alias", "config_version": "f" * 64,
            "latency_ms": 17.5, "usage": {"input_tokens": tokens, "output_tokens": tokens}, "cost_usd": None,
        }),
    }}]


@pytest.mark.parametrize("tokens", [None, 2147483647])
def test_decision_overhead_does_not_add_usage_rows_tokens_or_cost(env, tokens):
    key = create_key(env)
    now = datetime.now(UTC)
    provider = usage_trace()
    traces = decision_trace(tokens) + provider
    assert extract_usage(traces) == extract_usage(provider)
    assert extract_usage(decision_trace(tokens)) is None
    source = {
        "subscription_id": key["id"], "correlation_id": "decision-accounting-test",
        "resource_id": env.settings.apim_resource_id, "occurred_at": now,
        "status_code": 200, "trace_records": traces,
    }
    with Session(env.db_engine) as db:
        db.add(price(model="test-alias", provider="test", region="test-region", effective_from=now, currency="USD"))
        db.commit()
        # Replay/late native enrichment still means ONE parent provider completion.
        for _ in range(2):
            assert ingest_rows(db, [source], Catalog.load(env.settings.catalog_path)) == 1
            db.commit()
            source.update(model="test-alias", input_tokens=99999, output_tokens=99999)
        rows = list(db.scalars(select(UsageRecord)))
        assert len(rows) == 1
        row = rows[0]
        assert row.model == "test-alias" and row.input_tokens == 100 and row.output_tokens == 20
        assert row.cached_input_tokens == 40 and row.cache_write_tokens == 10
        assert row.cost == Decimal("0.00025") and row.completeness == "complete"


def test_decision_tokens_never_fill_missing_provider_usage(env):
    key = create_key(env)
    source = {
        "subscription_id": key["id"], "correlation_id": "missing-provider",
        "resource_id": env.settings.apim_resource_id, "occurred_at": datetime.now(UTC),
        "status_code": 200, "model": "test-model", "trace_records": decision_trace(2147483647),
    }
    with Session(env.db_engine) as db:
        ingest_rows(db, [source], Catalog.load(env.settings.catalog_path))
        db.commit()
        rows = list(db.scalars(select(UsageRecord)))
        assert len(rows) == 1
        assert rows[0].input_tokens is None and rows[0].output_tokens is None and rows[0].cost is None