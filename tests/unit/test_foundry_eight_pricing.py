"""Additive Foundry pricing contracts; no cloud, tariff fetches or ledger writes."""
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.resources import files
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import mssql, postgresql, sqlite
from sqlalchemy.orm import Session

from aiflux.display_pricing import (
    _merge_manifests, accepted_scope, catalog_price, detail_estimates,
    estimate_expressions, estimate_summary, manifest,
)
from aiflux.external_inventory import AcceptedInventory
from aiflux.models import Base, UsageRecord
from aiflux.rate_card import base_scopes, defaults, periods

ROOT = files("aiflux").joinpath("pricing")
CUTOFF = datetime(2026, 10, 27, 6, 6, 2, 45288, tzinfo=UTC)
SAVE = datetime(2026, 10, 30, 12, tzinfo=UTC)
# Alias case, prices, provider, version and conservative estimation cap are exact.
EXPECTED = {
    "claude-sonnet-5-5": ("2", "10", "0.10", "2.50", "Anthropic", "2", 128000),
    "claude-opus-5-5": ("4", "20", "0.20", "5", "Anthropic", "2", 128000),
    "claude-opus-5-5-fast": ("8", "40", "0.40", "10", "Anthropic", "2", 128000),
    "claude-haiku-5-5": ("0.10", "0.50", "0.01", "0.125", "Anthropic", "2", 100000),
    "gpt-6.1-terra": ("1", "5", "0.05", "1.25", "OpenAI", "2026-10-26", 128000),
    "gpt-6-luna": ("0.10", "0.50", "0.01", "0.125", "OpenAI", "2026-09-22", 128000),
    "claude-opus-4-8": ("5", "25", "0.50", "6.25", "Anthropic", "2", 128000),
    "Mistral-Large-3": ("0.50", "1.50", None, None, "Mistral AI", "1", 128000),
}
LEGACY_RATES = {
    "FW-GLM-5.3": (None, None, None, None),
    "FW-MiniMax-M3": (None, None, None, None),
    "gpt-5.6-luna": ("0.20", "1.20", "0.02", "0.25"),
    "gpt-6.1-sol": ("2", "10", "0.10", "2.50"),
    "gpt-5.4-mini": ("0.75", "4.50", "0.08", None),
    "gpt-4o": ("2.50", "10", "1.25", None),
    "DeepSeek-V4-Flash": ("0.19", "0.51", "0.028", None),
    "DeepSeek-V4-Pro": ("1.74", "3.48", "0.145", None),
    "Kimi-K2.7-Code": ("0.95", "4", "0.19", None),
    "grok-4.3": ("1.25", "2.50", None, None),
    "grok-4-20-reasoning": ("1.25", "2.50", None, None),
    "grok-4-1-fast-reasoning": ("0.20", "0.50", None, None),
    "glm-5.3": ("1.14285714", "4", "0.28571429", None),
}


def sources():
    return (ROOT.joinpath("rates-20261027.json").read_bytes(),
            ROOT.joinpath("rates-foundry-eight-20261030.json").read_bytes())


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_usage(db, identifier="r", alias="claude-sonnet-5-5", **changes):
    provider = EXPECTED[alias][4] if alias in EXPECTED else "OpenAI"
    values = dict(
        id=identifier, organization_id="org", subscription_id="sub", model=alias,
        provider=provider, region="eastus", occurred_at=CUTOFF,
        input_tokens=100, output_tokens=20, cached_input_tokens=0, cache_write_tokens=0,
        cost=None, currency=None, status_code=200, completeness="price_missing",
    )
    row = UsageRecord(**(values | changes))
    db.add(row)
    db.flush()
    return row


def test_original_sources_rates_and_metadata_survive_merge_byte_for_byte():
    raw, extra = sources()
    defaults_before = ROOT.joinpath("default-estimates-20261030.json").read_bytes()
    original = json.loads(raw)
    historical = _merge_manifests(raw)
    merged = _merge_manifests(raw, extra)
    assert len(original["rates"]) == 13
    assert merged["rates"][:13] == original["rates"] == historical["rates"]
    assert {r["model"]: tuple(r.get(f) for f in ("input", "output", "cached", "write"))
            for r in original["rates"]} == LEGACY_RATES
    for key in ("applicable_from", "checked_at", "basis", "assumptions", "unit", "currency"):
        assert merged[key] == historical[key] == original[key]
    assert historical["sources"] == original["sources"]
    assert all(merged["sources"][k] == v for k, v in original["sources"].items())
    assert historical["sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest(False) == historical
    assert sources() == (raw, extra)
    assert ROOT.joinpath("default-estimates-20261030.json").read_bytes() == defaults_before
    assert defaults()["rates"] == json.loads(defaults_before)["rates"]


def test_merged_digest_binds_both_actual_byte_sources_not_just_parsed_json():
    raw, extra = sources()
    merged = _merge_manifests(raw, extra)
    hashes = {"rates-20261027.json": hashlib.sha256(raw).hexdigest(),
              "rates-foundry-eight-20261030.json": hashlib.sha256(extra).hexdigest()}
    assert merged["source_sha256"] == hashes
    assert merged["sha256"] == hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert _merge_manifests(raw + b"\n", extra)["sha256"] != merged["sha256"]
    assert _merge_manifests(raw, extra + b"\n")["sha256"] != merged["sha256"]


def test_optional_additive_absence_preserves_historical_package_but_corruption_is_not_ignored(monkeypatch):
    raw, _ = sources()
    package, pricing, original, additive = Mock(), Mock(), Mock(), Mock()
    package.joinpath.return_value = pricing
    pricing.joinpath.side_effect = lambda name: original if name == "rates-20261027.json" else additive
    original.read_bytes.return_value = raw
    additive.read_bytes.side_effect = FileNotFoundError
    monkeypatch.setattr("aiflux.display_pricing.files", lambda name: package)
    assert manifest.__wrapped__() == _merge_manifests(raw)
    additive.read_bytes.side_effect = None
    additive.read_bytes.return_value = b"not json"
    with pytest.raises(ValueError):
        manifest.__wrapped__()


def test_exact_eight_rates_sources_and_twenty_one_unique_scopes():
    raw, extra_raw = sources()
    extra = json.loads(extra_raw)
    merged = _merge_manifests(raw, extra_raw)
    assert {r["model"] for r in extra["rates"]} == set(EXPECTED)
    assert len(merged["rates"]) == 21
    assert len({(r["model"], r["provider"], r["region"]) for r in merged["rates"]}) == 21
    assert "mistral-medium-3-5" not in {r["model"] for r in merged["rates"]}
    assert "Decision-1" not in {r["model"] for r in merged["rates"]}
    for alias, (inp, out, cached, write, provider, version, cap) in EXPECTED.items():
        rate = catalog_price(alias, provider, "eastus")
        assert rate is not None
        assert tuple(rate.get(f) for f in ("input", "output", "cached", "write")) == (inp, out, cached, write)
        assert rate["deployment_model"] == alias  # Actual retained ARM name, including fast.
        assert rate["model_version"] == version and rate["sku"] == "GlobalStandard"
        assert rate["max_input_tokens"] == cap and rate["context_applicability"]
        assert rate["checked_at"] == "2026-10-30"
        assert rate["source_model"] and rate["source_url"].startswith("https://")
        assert rate["applicable_from"] == "2026-10-27T06:06:02.045288Z"
        assert rate["input_includes_cached"] is (provider != "Anthropic")
        assert rate["usage_input_includes_cached"] is True
        if provider == "Anthropic":
            assert "Foundry" in rate["source_model"] and "CCU" in rate["assumption"]
            assert rate["cache_write_ttl_seconds"] == 300 and not rate["cache_write_ttl_verified"]
        assert catalog_price(alias, provider, "westus") is None
        assert catalog_price(alias, "wrong-provider", "eastus") is None
    assert catalog_price("Mistral-Large-3", "Mistral AI", "eastus")["status"] == "sourced_proxy"
    assert catalog_price("mistral-large-3", "Mistral AI", "eastus") is None
    assert catalog_price("claude-opus-5-5-fast", "Anthropic", "eastus")["required_usage_speed"] == "fast"


@pytest.mark.parametrize("problem", [
    "duplicate_scope", "duplicate_alias_other_provider", "source_collision", "unknown_source",
    "cutoff", "currency", "unit", "missing_model_version", "missing_deployment_model",
    "negative", "nonfinite", "missing_output", "invalid_accounting", "invalid_cap", "unverified_ttl",
    "missing_usage_input_includes_cached", "normalized_exclusive",
])
def test_invalid_additive_scopes_and_collisions_are_rejected(problem):
    raw, extra_raw = sources()
    extra = json.loads(extra_raw)
    rate = extra["rates"][0]
    if problem.startswith("duplicate_"):
        duplicate = copy.deepcopy(rate)
        if problem == "duplicate_alias_other_provider":
            duplicate["provider"] = "Other"
        extra["rates"].append(duplicate)
    elif problem == "source_collision":
        extra["sources"]["openai"] = "https://example.invalid/"
    elif problem == "unknown_source":
        rate["source"] = "not-declared"
    elif problem in ("cutoff", "currency", "unit"):
        extra[{"cutoff": "applicable_from"}.get(problem, problem)] = "different"
    elif problem.startswith("missing_"):
        del rate[problem.removeprefix("missing_")]
    elif problem in ("negative", "nonfinite"):
        rate["input"] = "-1" if problem == "negative" else "NaN"
    elif problem == "invalid_accounting":
        rate["input_includes_cached"] = "false"
    elif problem == "invalid_cap":
        rate["max_input_tokens"] = True
    elif problem == "normalized_exclusive":
        rate["usage_input_includes_cached"] = False
    else:
        rate["cache_write_ttl_verified"] = True
    with pytest.raises(ValueError):
        _merge_manifests(raw, json.dumps(extra).encode("utf-8"))


def test_collision_with_historical_alias_cannot_shadow_original():
    raw, extra_raw = sources()
    extra = json.loads(extra_raw)
    extra["rates"][0]["model"] = "gpt-6.1-sol"
    with pytest.raises(ValueError, match="scope"):
        _merge_manifests(raw, json.dumps(extra).encode("utf-8"))


@pytest.mark.parametrize("alias", EXPECTED)
def test_all_eight_available_at_original_cutoff_and_not_before(db, alias):
    add_usage(db, alias=alias)
    add_usage(db, "before", alias=alias, occurred_at=CUTOFF - timedelta(microseconds=1))
    details = detail_estimates(db, ["r", "before"])
    assert details["r"]["estimated_cost_usd"] is not None
    assert details["before"]["estimated_cost_usd"] is None
    assert details["r"]["estimate_basis"] == "measured_cache_detail"


def test_normalized_anthropic_and_openai_inclusive_cache_math(db):
    add_usage(db, input_tokens=600, cached_input_tokens=500)
    add_usage(db, "openai", alias="gpt-6.1-terra", input_tokens=1000,
              output_tokens=100, cached_input_tokens=500, cache_write_tokens=100)
    details = detail_estimates(db, ["r", "openai"])
    # Native 100 + read 500 becomes inclusive 600 at APIM. Do NOT charge
    # 600*2 + 20*10 + 500*.1 (0.00145), or add cache again for context.
    assert Decimal(details["r"]["estimated_cost_usd"]) == Decimal("0.000450000000")
    # OpenAI includes both cache components: 400*1 + 100*5 + 500*.05 + 100*1.25.
    assert Decimal(details["openai"]["estimated_cost_usd"]) == Decimal("0.001050000000")
    result = estimate_summary(db, [])[0]
    assert Decimal(result["estimated_cost_usd"]) == Decimal("0.001500000000")
    assert result["estimated_requests"] == 2 and result["approximate_requests"] == 0


@pytest.mark.parametrize("change", [
    {"cached_input_tokens": None}, {"cache_write_tokens": None}, {"cache_write_tokens": 1},
    {"cached_input_tokens": -1}, {"cache_write_tokens": -1}, {"input_tokens": None},
    {"output_tokens": None}, {"input_tokens": -1}, {"status_code": 429},
    {"completeness": "retry_usage_unknown"}, {"provider": "OpenAI"}, {"region": "westus"},
    {"cached_input_tokens": 101},
])
def test_native_missing_cache_unknown_write_ttl_and_invalid_usage_stay_unknown(db, change):
    row = add_usage(db, **change)
    before = (row.input_tokens, row.cached_input_tokens, row.cache_write_tokens, row.completeness)
    result = detail_estimates(db, ["r"])["r"]
    assert result["estimated_cost_usd"] is None and result["estimate_basis"] == "unestimated"
    assert (row.input_tokens, row.cached_input_tokens, row.cache_write_tokens, row.completeness) == before
    assert row.cost is None and row.currency is None and not db.dirty


@pytest.mark.parametrize("alias", EXPECTED)
def test_context_boundary_and_cache_inclusive_native_context(db, alias):
    cap = EXPECTED[alias][-1]
    native = EXPECTED[alias][4] == "Anthropic"
    add_usage(db, alias=alias, input_tokens=cap,
              cached_input_tokens=10 if native else 0)
    add_usage(db, "over", alias=alias, input_tokens=cap + 1,
              cached_input_tokens=10 if native else 0)
    details = detail_estimates(db, ["r", "over"])
    assert details["r"]["estimated_cost_usd"] is not None
    assert details["over"]["estimated_cost_usd"] is None


def test_openai_missing_cache_is_still_disclosed_approximation_and_overflow_rejected(db):
    row = add_usage(db, alias="gpt-6-luna", cached_input_tokens=None, cache_write_tokens=None)
    add_usage(db, "bad", alias="gpt-6-luna", cached_input_tokens=101)
    result = detail_estimates(db, ["r", "bad"])
    assert result["r"]["estimate_basis"] == "standard_input_approximation"
    assert Decimal(result["r"]["estimated_cost_usd"]) == Decimal("0.000020000000")
    assert result["bad"]["estimated_cost_usd"] is None
    assert row.cached_input_tokens is None and row.cache_write_tokens is None


def test_configured_new_periods_retain_native_accounting_and_caps_without_history_mutation(db):
    entries = [{"model": "claude-haiku-5-5", "provider": "Anthropic", "region": "eastus",
                "origin": "configured", "valid_from": SAVE,
                "input": "1", "output": "2", "cached": "0.1", "write": "1.25"}]
    original = copy.deepcopy(entries)
    resolved = periods(entries)
    add_usage(db, alias="claude-haiku-5-5", input_tokens=600,
              cached_input_tokens=500, occurred_at=SAVE - timedelta(microseconds=1))
    add_usage(db, "saved", alias="claude-haiku-5-5", input_tokens=600,
              cached_input_tokens=500, occurred_at=SAVE)
    add_usage(db, "over", alias="claude-haiku-5-5", input_tokens=100001,
              cached_input_tokens=2, occurred_at=SAVE)
    add_usage(db, "ttl", alias="claude-haiku-5-5", cache_write_tokens=1, occurred_at=SAVE)
    details = detail_estimates(db, ["r", "saved", "over", "ttl"], periods=resolved)
    assert Decimal(details["r"]["estimated_cost_usd"]) == Decimal("0.000025000000")
    assert Decimal(details["saved"]["estimated_cost_usd"]) == Decimal("0.000190000000")
    assert details["over"]["estimated_cost_usd"] is None and details["ttl"]["estimated_cost_usd"] is None
    assert entries == original and len(base_scopes()) == 21
    for group in (UsageRecord.model, UsageRecord.subscription_id, UsageRecord.organization_id):
        grouped = estimate_summary(db, [], group, periods=resolved)
        assert Decimal(grouped[0]["estimated_cost_usd"]) == Decimal("0.000215000000")
    assert all(row.cost is None for row in db.scalars(select(UsageRecord))) and not db.dirty


def test_normalized_finops_trace_is_stored_verbatim_and_estimated_once(env):
    from aiflux.catalog import Catalog
    from aiflux.ingestion import extract_usage, ingest_rows, record_id
    from aiflux.models import TeamSubscription

    payload = {"schema": "finops-v1", "model": "claude-sonnet-5-5", "attempts": 1,
               "input_tokens": 600, "output_tokens": 20,
               "cached_input_tokens": 500, "cache_write_tokens": 0}
    trace = [{"source": "aiflux", "metadata": {
        "category": "usage", "payload": json.dumps(payload)}}]
    assert extract_usage(trace) == payload
    catalog = Catalog.model_validate({"models": [{
        "id": "claude-sonnet-5-5", "provider": "Anthropic", "region": "eastus",
        "backend_model": "claude-sonnet-5-5", "enabled": True, "capabilities": ["chat"]}]})
    source = {"subscription_id": "normalized-sub", "correlation_id": "normalized-cache",
              "resource_id": env.settings.apim_resource_id, "occurred_at": CUTOFF,
              "status_code": 200, "trace_records": trace}
    with Session(env.db_engine) as session:
        session.add(TeamSubscription(id="normalized-sub", organization_id=env.orgs["customer"],
                                    name="Cache test", team="test", state="active",
                                    desired_state="active", idempotency_key="normalized-cache"))
        session.commit()
        for _ in range(2):
            assert ingest_rows(session, [source], catalog) == 1
            session.commit()
        rows = list(session.scalars(select(UsageRecord)))
        assert len(rows) == 1
        row = rows[0]
        assert (row.input_tokens, row.cached_input_tokens, row.cache_write_tokens) == (600, 500, 0)
        identifier = record_id(source["resource_id"], source["correlation_id"])
        result = detail_estimates(session, [identifier])[identifier]
        assert result["estimated_cost_usd"] == "0.000450000000"
        assert row.cost is None and row.currency is None and not session.dirty


def test_old_thirteen_sql_amounts_and_cache_approximations_unchanged(db):
    old_rates = json.loads(sources()[0])["rates"]
    ids = []
    for index, rate in enumerate(old_rates):
        for suffix, cached, write in (("known", 500, 0), ("missing", None, None), ("overflow", 1001, 0)):
            identifier = f"old-{index}-{suffix}"
            ids.append(identifier)
            add_usage(db, identifier, alias=rate["model"], provider=rate["provider"], region=rate["region"],
                      input_tokens=1000, output_tokens=100, cached_input_tokens=cached, cache_write_tokens=write)
    details = detail_estimates(db, ids)
    assert details == detail_estimates(db, ids, periods=old_rates)
    assert estimate_summary(db, []) == estimate_summary(db, [], periods=old_rates)
    # Independent reference to the original inclusive math, not just two calls
    # through the changed estimator. These counts avoid half-ulp rounding ties.
    for index, rate in enumerate(old_rates):
        for suffix in ("known", "missing", "overflow"):
            result = details[f"old-{index}-{suffix}"]
            if rate["status"] == "unknown" or suffix == "overflow":
                assert result["estimated_cost_usd"] is None
                continue
            measured_cache = suffix == "known" and "cached" in rate
            tokens = Decimal(500 if measured_cache else 1000)
            expected = tokens * Decimal(rate["input"]) + Decimal(100) * Decimal(rate["output"])
            if measured_cache:
                expected += Decimal(500) * Decimal(rate["cached"])
            assert Decimal(result["estimated_cost_usd"]) == expected / Decimal(1_000_000)
            assert result["estimate_basis"] == (
                "measured_cache_detail" if measured_cache else "standard_input_approximation")


@pytest.mark.parametrize("alias", EXPECTED)
def test_accepted_scope_requires_exact_provider_version_sku_and_actual_model_name(alias):
    rate = next(r for r in manifest()["rates"] if r["model"] == alias)
    route = SimpleNamespace(deployment_id="deployment", model_name=rate["deployment_model"],
                            model_version=rate["model_version"])
    deployment = SimpleNamespace(id="deployment", sku="GlobalStandard")
    inventory = Mock(spec=AcceptedInventory)
    inventory.settings = object()
    inventory.accepted_aliases.return_value = {alias}
    inventory.route.return_value = route
    inventory.matches.return_value = True
    inventory.provider.return_value = rate["provider"]
    inventory.foundry = SimpleNamespace(deployments=[deployment])
    assert accepted_scope(inventory, alias, alias, "https://gateway.invalid/") == rate
    for field in ("model_name", "model_version"):
        previous = getattr(route, field)
        setattr(route, field, "wrong")
        assert accepted_scope(inventory, alias, alias, "https://gateway.invalid/") is None
        setattr(route, field, previous)
    for sku in ("DataZoneStandard", None):
        deployment.sku = sku
        assert accepted_scope(inventory, alias, alias, "https://gateway.invalid/") is None
    deployment.sku = "GlobalStandard"
    inventory.provider.return_value = "wrong"
    assert accepted_scope(inventory, alias, alias, "https://gateway.invalid/") is None
    inventory.provider.return_value = rate["provider"]
    inventory.matches.return_value = False
    assert accepted_scope(inventory, alias, alias, "https://gateway.invalid/") is None
    inventory.matches.return_value = True
    inventory.accepted_aliases.return_value = set()
    assert accepted_scope(inventory, alias, alias, "https://gateway.invalid/") is None


@pytest.mark.parametrize("dialect", [postgresql.dialect(), sqlite.dialect(), mssql.dialect()])
def test_new_native_and_inclusive_sql_remain_portable_read_only(dialect):
    amount, approximation = estimate_expressions()
    statement = str(select(UsageRecord.id, amount, approximation).compile(dialect=dialect)).upper()
    assert "SELECT" in statement and "CASE" in statement and "BIGINT" in statement
    assert not any(word in statement for word in ("INSERT ", "UPDATE ", "DELETE "))