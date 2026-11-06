"""Offline customer pricing boundary: trusted ownership, estimates, no ledger writes."""
import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from test_catalog_pricing_correction import accepted  # noqa: F401
from test_decision_telemetry import decision_env, native  # noqa: F401
from test_turnstile_exchange import deployed_garden  # noqa: F401

from aiflux import external_pricing as external, rate_card
from aiflux.auth import Principal
from aiflux.customer_pricing import INTERNAL_FIELDS, customer_safe
from aiflux.models import (
    CreditBudget, ExternalPriceCardRevision, GatewaySettingsRevision, ModelPrice,
    TeamSubscription, UsageRecord,
)
from conftest import ADMIN_USER, HOME

ALIAS = "gpt-5.4-mini"
DEFAULT_PATH = "/api/admin/external-rate-card"


def org_path(org):
    return f"/api/admin/organizations/{org}/external-rate-card"


def initialize(env):
    with Session(env.db_engine) as db:
        result = external.initialize_external_baseline(db, env.settings, Principal(
            env.orgs["admin"], "IDS", HOME, ADMIN_USER, "ids_admin"))
        assert result.version == 1


@pytest.fixture
def pricing_env(accepted):
    env, _ = accepted
    initialize(env)
    return env


def put(env, *, org=None, version=None, model=ALIAS, operation="set", **rates):
    if version is None:
        version = 0 if org else 1
    return env.client.put(org_path(org) if org else DEFAULT_PATH, headers=env.admin, json={
        "expected_version": version, "rates": [{"model": model, "operation": operation, **rates}]})


def row(body, model=ALIAS):
    return next(item for item in body["items"] if item["model"] == model)


def no_internal(value):
    if isinstance(value, dict):
        assert not INTERNAL_FIELDS.intersection(value)
        assert not any(key.startswith("default_") for key in value)
        for item in value.values():
            no_internal(item)
    elif isinstance(value, list):
        for item in value:
            no_internal(item)


def no_supplier_values(value):
    """Check parsed values, never substrings in request/org UUIDs or metadata."""
    no_internal(value)
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"reason", "reply", "content"} and isinstance(item, str):
                assert "$" not in item and "Internal $999 supplier rate" not in item
            if any(word in key for word in ("cost", "price", "million", "credits")) and isinstance(item, (str, int, float, Decimal)):
                try:
                    amount = Decimal(str(item))
                except ArithmeticError:
                    pass  # Non-numeric price labels/revision metadata are not amounts.
                else:
                    assert amount != Decimal("999")
            no_supplier_values(item)
    elif isinstance(value, list):
        for item in value:
            no_supplier_values(item)


def scoring_csv_rows(text):
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["metadata", "value"]
    separator = rows.index([])
    metadata = dict(rows[1:separator])
    summary = {key.removeprefix("summary."): value for key, value in metadata.items()
               if key.startswith("summary.")}
    no_supplier_values(summary)
    fields = rows[separator + 1]
    assert len(fields) == len(set(fields))
    no_internal(dict.fromkeys(fields))
    records = []
    for values in rows[separator + 2:]:
        assert len(values) == len(fields)
        record = dict(zip(fields, values, strict=True))
        no_internal(record)
        # IDs, timestamps, hashes and revision provenance are not money values.
        money = {key: value for key, value in record.items()
                 if any(word in key for word in ("cost", "price", "million", "credits"))}
        no_supplier_values(money)
        records.append(record)
    return summary, records


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(at=datetime.now(UTC) - timedelta(hours=2))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return state.at

    monkeypatch.setattr(external, "datetime", Clock)
    return state


def add_usage(env, at, *, id="priced", organization=None, sid=None):
    organization = organization or env.orgs["customer"]
    sid = sid or str(uuid4())
    with Session(env.db_engine) as db:
        if db.get(TeamSubscription, sid) is None:
            db.add(TeamSubscription(id=sid, organization_id=organization, name="Pricing", team="Offline",
                                    state="active", desired_state="active", idempotency_key=str(uuid4())))
            db.flush()
        db.add(UsageRecord(id=id, organization_id=organization, subscription_id=sid, model=ALIAS,
                           provider="OpenAI", region="eastus", occurred_at=at, input_tokens=1_000_000,
                           output_tokens=1_000_000, cached_input_tokens=0, cache_write_tokens=0,
                           cost=Decimal("987.12345678"), currency="USD", status_code=200,
                           completeness="complete", e2e_ms=321))
        db.commit()
    return sid


def test_admin_crud_authorization_versions_and_no_internal_hook(pricing_env, monkeypatch):
    env = pricing_env
    from aiflux import auto_pricing
    env.settings.auto_pricing_sync_enabled = True
    monkeypatch.setattr(auto_pricing, "after_save", lambda *a: pytest.fail("external save called internal hook"))
    for path in (DEFAULT_PATH, org_path(env.orgs["customer"])):
        assert env.client.get(path, headers=env.customer).status_code == 403
        assert env.client.put(path, headers=env.customer, json={
            "expected_version": 0, "rates": [{"model": ALIAS, "input": "1", "output": "2"}]
        }).status_code == 403
    saved = put(env, input="8", output="12")
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 2 and row(saved.json())["input"] == "8"
    assert put(env, input="1", output="2").status_code == 409
    assert put(env, org=env.orgs["customer"], input="2", output="3").status_code == 200
    assert env.client.get(org_path(env.orgs["customer"]), headers=env.admin).json()["version"] == 1
    assert env.client.get(org_path(str(uuid4())), headers=env.admin).status_code == 404
    assert put(env, org=str(uuid4()), input="1", output="1").status_code == 404
    with Session(env.db_engine) as db:
        assert db.scalar(select(func.count()).select_from(GatewaySettingsRevision)) == 0
    assert env.apim.calls == []


def test_gets_never_initialize_and_customer_card_cannot_spoof_org(accepted):
    env, _ = accepted
    statements = []
    def capture(conn, cursor, statement, params, context, many):
        statements.append(statement)
    event.listen(env.db_engine, "before_cursor_execute", capture)
    try:
        for path, headers in ((DEFAULT_PATH, env.admin), ("/api/rate-card", env.customer),
                              ("/api/model-garden", env.customer), ("/api/credits/summary", env.customer)):
            response = env.client.get(path, headers=headers)
            assert response.status_code == 200, response.text
            if headers is env.customer:
                no_internal(response.json())
    finally:
        event.remove(env.db_engine, "before_cursor_execute", capture)
    assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements)
    # Reads never migrate, and writes must not silently initialize either.
    assert put(env, version=0, input="8", output="12").status_code == 409
    assert put(env, org=env.orgs["customer"], input="2", output="3").status_code == 409
    initialize(env)
    assert put(env, input="8", output="12").status_code == 200
    assert put(env, org=env.orgs["customer"], input="0", output="0").status_code == 200
    assert put(env, org=env.orgs["admin"], input="99", output="99").status_code == 200
    spoofed = env.token(organization_id=env.orgs["admin"], role="ids_admin")
    response = env.client.get("/api/rate-card", headers=spoofed,
                              params={"organization_id": env.orgs["admin"]})
    assert response.status_code == 200
    assert row(response.json())["input"] == "0"
    no_internal(response.json())
    assert put(env, org=env.orgs["customer"], version=1, operation="unknown").status_code == 200
    assert row(env.client.get("/api/rate-card", headers=env.customer).json())["input"] is None
    assert put(env, org=env.orgs["customer"], version=2, operation="inherit").status_code == 200
    assert row(env.client.get("/api/rate-card", headers=env.customer).json())["input"] == "8"


def test_catalog_external_rates_and_no_supplier_provenance(pricing_env, clock):
    env = pricing_env
    assert put(env, input="7", output="11", cached="1").status_code == 200
    garden = env.client.get("/api/model-garden", headers=env.customer)
    assert garden.status_code == 200, garden.text
    item = next(item for item in garden.json()["items"] if item["id"] == ALIAS)
    assert (item["input_per_million"], item["output_per_million"],
            item["cached_input_per_million"]) == ("7", "11", "1")
    assert item["display_price"]["input"] == "7"
    no_internal(garden.json())
    assert "public_list" not in garden.text and "https://openai.com" not in garden.text
    assert put(env, org=env.orgs["customer"], operation="unknown").status_code == 200
    item = next(item for item in env.client.get("/api/model-garden", headers=env.customer).json()["items"]
                if item["id"] == ALIAS)
    assert item["input_per_million"] is None and item["display_price"] is None
    admin = env.client.get("/api/admin/model-garden", headers=env.admin).json()
    assert next(item for item in admin["items"] if item["id"] == ALIAS)["display_price"]["input"] != "7"


def test_usage_summary_csv_showback_external_and_financial_rows_unchanged(pricing_env, clock):
    env = pricing_env
    assert put(env, input="2", output="3").status_code == 200
    sid = add_usage(env, clock.at + timedelta(minutes=1))
    other_sid = add_usage(env, clock.at + timedelta(minutes=1), id="other", organization=env.orgs["admin"])
    with Session(env.db_engine) as db:
        before = list(db.execute(select(ModelPrice.id, ModelPrice.input_per_million)))
        budget_count = db.scalar(select(func.count()).select_from(CreditBudget))
    response = env.client.get("/api/usage", headers=env.customer,
                              params={"organization_id": env.orgs["admin"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1 and body["items"][0]["subscription_id"] == sid
    assert Decimal(body["items"][0]["estimated_cost_usd"]) == 5
    assert Decimal(body["summary"]["estimated_cost_usd"]) == 5
    assert body["items"][0]["e2e_ms"] == 321
    no_internal(body)
    assert "987.123" not in response.text
    for path in ("/api/usage", "/api/usage/export", "/api/credits/summary", "/api/usage/timeseries",
                 "/api/usage/model-tokens"):
        assert env.client.get(path, headers=env.customer,
                              params={"subscription_id": other_sid}).status_code == 404
    showback = env.client.get("/api/credits/summary", headers=env.customer)
    assert showback.status_code == 200, showback.text
    assert Decimal(showback.json()["estimated_cost_usd"]) == 5
    assert Decimal(showback.json()["by_model"][0]["estimated_cost_usd"]) == 5
    assert showback.json()["by_model"][0]["share_pct"] == 100  # token share, not cost
    no_internal(showback.json())
    export = env.client.get("/api/usage/export", headers=env.customer)
    assert export.status_code == 200, export.text
    records = list(csv.DictReader(io.StringIO(export.text)))
    assert "cost" not in records[0] and Decimal(records[0]["estimated_cost_usd"]) == 5
    assert "987.123" not in export.text
    admin = env.client.get("/api/admin/usage", headers=env.admin).json()
    assert admin["items"][0]["cost"] == "987.12345678"
    with Session(env.db_engine) as db:
        assert before == list(db.execute(select(ModelPrice.id, ModelPrice.input_per_million)))
        assert budget_count == db.scalar(select(func.count()).select_from(CreditBudget))
        assert db.get(UsageRecord, "priced").cost == Decimal("987.12345678")


def test_usage_date_effective_unknown_zero_and_empty_external_never_internal_fallback(pricing_env, clock, monkeypatch):
    env = pricing_env
    clock.at -= timedelta(minutes=2)
    assert put(env, operation="unknown").status_code == 200
    clock.at += timedelta(minutes=2)
    add_usage(env, clock.at - timedelta(minutes=1), id="before")
    assert put(env, version=2, input="2", output="3").status_code == 200
    add_usage(env, clock.at + timedelta(minutes=1), id="default")
    clock.at += timedelta(minutes=2)
    assert put(env, org=env.orgs["customer"], input="0", output="0").status_code == 200
    add_usage(env, clock.at + timedelta(minutes=1), id="zero")
    clock.at += timedelta(minutes=2)
    assert put(env, org=env.orgs["customer"], version=1, operation="unknown").status_code == 200
    add_usage(env, clock.at + timedelta(minutes=1), id="unknown")
    monkeypatch.setattr(rate_card, "estimate_args", lambda *a: pytest.fail("internal pricing fallback"))
    data = env.client.get("/api/usage", headers=env.customer).json()
    details = {item["id"]: item for item in data["items"]}
    assert details["before"]["estimated_cost_usd"] is None
    assert details["unknown"]["estimated_cost_usd"] is None
    assert Decimal(details["zero"]["estimated_cost_usd"]) == 0
    assert Decimal(details["default"]["estimated_cost_usd"]) == 5
    assert data["summary"]["unestimated_requests"] == 2
    with Session(env.db_engine) as db:
        for revision in db.scalars(select(ExternalPriceCardRevision)):
            db.delete(revision)
        db.commit()
    data = env.client.get("/api/usage", headers=env.customer).json()
    assert data["summary"]["estimated_cost_usd"] is None
    assert data["summary"]["unestimated_requests"] == 4
    assert all(item["estimated_cost_usd"] is None for item in data["items"])


def test_scoring_snapshot_injected_for_rows_summary_csv_and_cross_org(decision_env, monkeypatch):
    env = decision_env
    # Match the initialized scope, rather than inventing a second scoring key
    # which must correctly fail closed as ambiguous.
    scorer = next(scope for scope in rate_card.base_scopes().values()
                  if scope.get("model_kind") == "scoring")
    monkeypatch.setattr(rate_card, "listed_scopes", lambda settings: [("Decision-1", scorer)])
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return env.decision_start
    monkeypatch.setattr(external, "datetime", Clock)
    assert put(env, model="Decision-1", input="20").status_code == 200
    env.logs.rows = [native(env, decision_input_tokens=1_000_000, decision_cost_usd="999")]
    data = env.client.get("/api/usage/decision-scoring", headers=env.customer, params=env.decision_params)
    assert data.status_code == 200, data.text
    assert Decimal(data.json()["items"][0]["estimated_cost_usd"]) == 20
    assert Decimal(data.json()["summary"]["estimated_cost_usd"]) == 20
    no_internal(data.json())
    exported = env.client.get("/api/usage/decision-scoring/export.csv", headers=env.customer,
                              params=env.decision_params)
    assert exported.status_code == 200
    summary, records = scoring_csv_rows(exported.text)
    assert len(records) == 1
    assert Decimal(summary["estimated_cost_usd"]) == 20
    assert Decimal(records[0]["estimated_cost_usd"]) == 20
    env.logs.rows = [native(env, "admin", decision_cost_usd="999")]
    rejected = env.client.get("/api/usage/decision-scoring", headers=env.customer, params=env.decision_params)
    assert rejected.json()["status"] == "unavailable"
    admin = env.client.get("/api/admin/usage/decision-scoring", headers=env.admin, params=env.decision_params)
    assert admin.json()["items"][0]["recorded_cost_usd"] == "999"


def test_legacy_router_playground_and_session_never_leak_money(env, monkeypatch):
    import aiflux.app as app_module
    from aiflux.schemas import PlaygroundChatResponse, RouterDecisionOutput
    route = RouterDecisionOutput(selected_model="test", display_name="Test", provider="Test", vendor="Test",
                                 category="general", strategy="test", decision_endpoint="test", confidence=1,
                                 reason="Internal $999 supplier rate", estimated_input_per_million="999",
                                 estimated_output_per_million="999")
    monkeypatch.setattr(app_module, "decide_model_route", lambda *a: route)
    monkeypatch.setattr(app_module, "run_playground_chat", lambda *a: PlaygroundChatResponse(
        id="test", requested_model="auto", selected_model="test", provider="Test", vendor="Test", reply="OK",
        routing_decision=route, safety_status="passed", safety_categories={}, input_tokens=1, output_tokens=2,
        total_tokens=3, estimated_cost_usd="999", latency_ms=3))
    response = env.client.post("/api/model-router/decide", headers=env.customer, json={"prompt": "Hello"})
    assert response.status_code == 200
    no_supplier_values(response.json())
    response = env.client.post("/api/playground/chat", headers=env.customer,
                               json={"messages": [{"role": "user", "content": "Hello"}]})
    assert response.status_code == 200
    assert "estimated_cost_usd" not in response.json()
    assert response.json()["total_tokens"] == 3 and response.json()["safety_status"] == "passed"
    no_supplier_values(response.json())
    env.settings.local_auth_enabled = True
    response = env.client.post("/v1/chat/completions", headers={"Ocp-Apim-Subscription-Key": "test"},
                               json={"messages": [{"role": "user", "content": "Hello"}]})
    assert response.status_code == 200, response.text
    no_supplier_values(response.json())
    assert route.reason == "Internal $999 supplier rate"  # Admin/internal DTO is not mutated.
    identity = env.client.get("/api/me", headers=env.customer).json()
    assert set(identity) == {"organization_id", "organization_name", "tenant_id", "object_id", "role"}


def test_recursive_projection_handles_future_nested_financial_fields():
    payload = {"nested": [{"cost": "secret", "default_input": "secret", "totals": {
        "remaining_credits": "secret", "estimated_cost_usd": "2", "requests": 7}}]}
    safe = customer_safe(payload)
    no_internal(safe)
    assert safe["nested"][0]["totals"] == {"estimated_cost_usd": "2", "requests": 7}


def test_routing_projection_is_allowlisted_without_suppressing_application_error_reasons():
    payload = {"reason": "Application error explanation", "routing_decision": {
        "selected_model": "test", "reason": "Internal $999 supplier rate",
        "future_supplier_details": "Internal $999 supplier rate"}}
    safe = customer_safe(payload)
    assert safe["reason"] == payload["reason"]
    assert safe["routing_decision"]["selected_model"] == "test"
    assert "future_supplier_details" not in safe["routing_decision"]
    no_supplier_values(safe)
    assert payload["routing_decision"]["reason"] == "Internal $999 supplier rate"


@pytest.mark.parametrize("path", ["/api/model-router/decide", "/api/playground/chat", "/v1/chat/completions"])
def test_actual_routing_and_testing_reply_are_price_free(env, deployed_garden, monkeypatch, path):
    import aiflux.app as app_module
    from aiflux import turnstile_exchange as exchange
    from aiflux.schemas import RouterDecisionRequest

    with Session(env.db_engine) as db:
        route = exchange.decide_model_route(db, env.settings, RouterDecisionRequest(
            prompt="Hello", strategy="cost-optimized"))
    assert "$" in route.reason  # Real legacy policy still retains its internal explanation.
    route = route.model_copy(update={"reason": "Internal $999 supplier rate"})
    monkeypatch.setattr(exchange, "decide_model_route", lambda *a: route)
    monkeypatch.setattr(app_module, "decide_model_route", lambda *a: route)
    # Do not replace run_playground_chat: exercise the actual testing fallback.
    headers = env.customer if path != "/v1/chat/completions" else {"Ocp-Apim-Subscription-Key": "test"}
    payload = {"prompt": "Hello"} if path == "/api/model-router/decide" else {
        "model": "auto", "messages": [{"role": "user", "content": "Hello"}]}
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    no_supplier_values(body)
    routing = body if path == "/api/model-router/decide" else body["routing_decision"]
    assert routing["selected_model"] == route.selected_model
    assert routing["reason"] == "Selected an available model under the configured routing policy."
    if path == "/api/playground/chat":
        assert "Selected an available model" in body["reply"]
        assert "estimated_cost_usd" not in body
        assert body["total_tokens"] > 0 and body["safety_status"] == "passed"
    elif path == "/v1/chat/completions":
        assert "Selected an available model" in body["choices"][0]["message"]["content"]
        assert body["usage"]["total_tokens"] > 0
    assert route.reason == "Internal $999 supplier rate"