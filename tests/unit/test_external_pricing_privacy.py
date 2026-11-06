"""Offline customer privacy and missing external-baseline regression contracts."""

import csv
import io
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from test_decision_telemetry import ADMIN_PATH, CUSTOMER_PATH, decision_env, get, native  # noqa: F401

from aiflux import decision_telemetry as telemetry
from aiflux.customer_pricing import INTERNAL_FIELDS, customer_safe
from aiflux.models import ExternalPriceCard, ExternalPriceCardRevision


def assert_private(value):
    if isinstance(value, dict):
        assert not INTERNAL_FIELDS.intersection(value)
        assert not any(key.startswith("default_") for key in value)
        for child in value.values():
            assert_private(child)
    elif isinstance(value, list):
        for child in value:
            assert_private(child)


def test_customer_projection_strips_nested_internal_fields_without_mutating_admin_data():
    hidden = dict.fromkeys(INTERNAL_FIELDS, "supplier-secret")
    original = {"nested": [{**hidden, "default_future_rate": "supplier-secret",
                            "estimated_cost_usd": "2", "total_tokens": 0}]}
    projected = customer_safe(original)
    assert_private(projected)
    assert projected == {"nested": [{"estimated_cost_usd": "2", "total_tokens": 0}]}
    assert original["nested"][0]["recorded_cost_usd"] == "supplier-secret"


def test_customer_decision_json_csv_hide_recorded_cost_admin_preserves_it(decision_env):
    env = decision_env
    env.logs.rows = [native(env, decision_cost_usd="987.12345678")]
    response = get(env)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "available"
    assert Decimal(body["summary"]["estimated_cost_usd"]) > 0
    assert_private(body)
    assert "987.12345678" not in response.text
    exported = get(env, path=CUSTOMER_PATH + "/export.csv")
    assert exported.status_code == 200, exported.text
    assert "recorded_cost_usd" not in exported.text
    assert "987.12345678" not in exported.text
    admin = get(env, path=ADMIN_PATH, headers=env.admin)
    assert admin.status_code == 200, admin.text
    assert admin.json()["summary"]["recorded_cost_usd"] == "987.12345678"
    assert admin.json()["items"][0]["recorded_cost_usd"] == "987.12345678"
    admin_csv = get(env, path=ADMIN_PATH + "/export.csv", headers=env.admin)
    assert admin_csv.status_code == 200, admin_csv.text
    records = list(csv.reader(io.StringIO(admin_csv.text)))
    assert list(telemetry.ITEM_FIELDS) in records
    assert ["summary.recorded_cost_usd", "987.12345678"] in records


@pytest.mark.parametrize("tokens,measured", [(100, 1), (0, 1), (None, 0)])
def test_missing_baseline_decision_is_unknown_partial_and_zero_tokens_are_measured(
    decision_env, monkeypatch, tokens, measured,
):
    env = decision_env
    with Session(env.db_engine) as db:
        for model in (ExternalPriceCardRevision, ExternalPriceCard):
            for row in db.scalars(select(model)):
                db.delete(row)
            db.flush()
        db.commit()

    def forbidden(*args, **kwargs):
        pytest.fail("Customer read fell back to internal scoring pricing")

    monkeypatch.setattr(telemetry, "load_state", forbidden)
    monkeypatch.setattr(telemetry, "scoring_effective_estimate", forbidden)
    env.logs.rows = [native(env, decision_input_tokens=tokens,
                            decision_output_tokens=0 if tokens is not None else None,
                            decision_cost_usd="987.12345678")]
    statements = []

    def capture(conn, cursor, statement, params, context, many):
        statements.append(statement)

    event.listen(env.db_engine, "before_cursor_execute", capture)
    try:
        response = get(env)
        exported = get(env, path=CUSTOMER_PATH + "/export.csv")
    finally:
        event.remove(env.db_engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "partial" and body["total"] == 1
    assert body["summary"]["input_tokens"] == tokens
    assert body["summary"]["total_tokens"] == tokens
    assert body["summary"]["measured_invocations"] == measured
    assert body["summary"]["missing_token_invocations"] == 1 - measured
    assert body["summary"]["estimated_cost_usd"] is None
    assert body["summary"]["estimated_invocations"] == 0
    assert body["summary"]["unestimated_invocations"] == 1
    assert body["items"][0]["estimated_cost_usd"] is None
    assert body["items"][0]["estimate_basis"] == "unestimated"
    assert_private(body)
    assert exported.status_code == 200, exported.text
    assert exported.headers["x-decision-telemetry-status"] == "partial"
    assert "recorded_cost_usd" not in exported.text
    assert "987.12345678" not in exported.text
    assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                   for sql in statements)


def test_missing_baseline_does_not_gate_router_or_playground(env, monkeypatch):
    import aiflux.app as app_module
    from aiflux.schemas import PlaygroundChatResponse, RouterDecisionOutput

    with Session(env.db_engine) as db:
        assert list(db.scalars(select(ExternalPriceCardRevision))) == []
    calls = []
    route = RouterDecisionOutput(
        selected_model="test", display_name="Test", provider="Test", vendor="Test",
        category="general", strategy="test", decision_endpoint="test", confidence=1,
        reason="Test", estimated_input_per_million="987.12345678",
        estimated_output_per_million="987.12345678",
    )

    def decide(*args):
        calls.append("router")
        return route

    def chat(*args):
        calls.append("playground")
        return PlaygroundChatResponse(
            id="test", requested_model="auto", selected_model="test", provider="Test", vendor="Test",
            reply="OK", routing_decision=route, safety_status="passed", safety_categories={},
            input_tokens=0, output_tokens=0, total_tokens=0,
            estimated_cost_usd="987.12345678", latency_ms=3,
        )

    monkeypatch.setattr(app_module, "decide_model_route", decide)
    monkeypatch.setattr(app_module, "run_playground_chat", chat)
    routed = env.client.post("/api/model-router/decide", headers=env.customer, json={"prompt": "Hello"})
    chatted = env.client.post("/api/playground/chat", headers=env.customer,
                              json={"messages": [{"role": "user", "content": "Hello"}]})
    assert routed.status_code == 200, routed.text
    assert chatted.status_code == 200, chatted.text
    assert calls == ["router", "playground"]
    assert chatted.json()["total_tokens"] == 0
    assert chatted.json()["safety_status"] == "passed"
    assert "estimated_cost_usd" not in chatted.json()
    for response in (routed, chatted):
        assert_private(response.json())
        assert "987.12345678" not in response.text