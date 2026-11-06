"""Offline Decision-1 API/security contracts. Never contacts Monitor or inference."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from aiflux import decision_telemetry as telemetry
from aiflux.auth import Principal
from aiflux.external_pricing import initialize_external_baseline
from aiflux.models import TeamSubscription, UsageRecord
from conftest import ADMIN_USER, HOME

CUSTOMER_PATH = "/api/usage/decision-scoring"
ADMIN_PATH = "/api/admin/usage/decision-scoring"


class FakeLogs:
    def __init__(self):
        self.rows = []
        self.calls = []
        self.status = "Success"
        self.error = None

    def query_workspace(self, workspace, query, **kwargs):
        self.calls.append((workspace, query, kwargs))
        if self.error:
            raise self.error
        columns = list(self.rows[0]) if self.rows else []
        return SimpleNamespace(status=self.status, tables=[SimpleNamespace(
            columns=columns, rows=[[row.get(key) for key in columns] for row in self.rows],
        )])


@pytest.fixture
def decision_env(env):
    ids = {"customer": str(uuid4()), "admin": str(uuid4())}
    with Session(env.db_engine) as db:
        for owner, sid in ids.items():
            db.add(TeamSubscription(id=sid, organization_id=env.orgs[owner], name="Telemetry",
                                    team="Offline", state="active", desired_state="active",
                                    idempotency_key=str(uuid4())))
        db.commit()
        initialize_external_baseline(db, env.settings, Principal(
            env.orgs["admin"], "IDS", HOME, ADMIN_USER, "ids_admin",
        ))
    logs = FakeLogs()
    env.app.state.decision_telemetry_client = logs
    # Relative timestamps remain inside the app's validated viewport on any test date.
    end = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
    start = end - timedelta(hours=2)
    env.decision_ids = ids
    env.logs = logs
    env.decision_start = start
    env.decision_end = end
    env.decision_params = {"days": 1, "start": start.isoformat(), "end": end.isoformat()}
    return env


def native(env, owner="customer", **changes):
    correlation = str(uuid4())
    return {
        "resource_id": env.settings.apim_resource_id.lower(), "correlation_id": correlation,
        "request_id": correlation, "subscription_id": env.decision_ids[owner],
        "occurred_at": env.decision_start + timedelta(minutes=1),
        "parent_status_code": 502, "decision_schema": "decision-overhead-v1",
        "routing_profile": "balanced", "selected_model": "test-alias", "config_version": "f" * 64,
        "decision_latency_ms": 17.5, "decision_input_tokens": 100, "decision_output_tokens": 20,
        "decision_cost_usd": None, "decision_trace_count": 1,
    } | changes


def get(env, path=CUSTOMER_PATH, headers=None, **params):
    return env.client.get(path, headers=headers or env.customer, params=env.decision_params | params)


def test_full_aggregate_before_page_failed_parent_retained_and_no_writes(decision_env):
    env = decision_env
    env.logs.rows = [native(env), native(env, decision_input_tokens=200, decision_output_tokens=40)]
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(env.db_engine, "before_cursor_execute", capture)
    try:
        response = get(env, offset=1, limit=1)
    finally:
        event.remove(env.db_engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "available" and data["source"] == "log_analytics"
    assert data["model"] == "Decision-1" and data["total"] == 2 and len(data["items"]) == 1
    assert data["summary"]["invocations"] == 2
    assert data["summary"]["input_tokens"] == 300 and data["summary"]["output_tokens"] == 60
    assert data["summary"]["total_tokens"] == 360 and data["summary"]["measured_invocations"] == 2
    assert "recorded_cost_usd" not in data["summary"]
    assert all("recorded_cost_usd" not in item for item in data["items"])
    assert Decimal(data["summary"]["estimated_cost_usd"]) > 0
    assert data["items"][0]["parent_status_code"] == 502
    assert data["items"][0]["usage_kind"] == "decision_scoring"
    assert data["breakdown"][0]["invocations"] == 2
    assert sum(bucket["invocations"] for bucket in data["series"]) == 2
    assert all(not sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER"))
               for sql in statements)
    with Session(env.db_engine) as db:
        assert list(db.scalars(select(UsageRecord))) == []
    _, query, kwargs = env.logs.calls[0]
    trusted_filter = "| where subscription_id in (" + json.dumps(env.decision_ids["customer"]) + ");"
    assert trusted_filter in query
    assert query.index(trusted_filter) < query.index("let decisions") < query.index("| take 10001")
    assert env.decision_ids["admin"] not in query
    assert kwargs["retry_total"] == 0 and kwargs["server_timeout"] == 15
    assert kwargs["connection_timeout"] == 5 and kwargs["read_timeout"] == 20


def test_customer_cannot_select_organization_and_admin_is_enforced(decision_env):
    env = decision_env
    env.logs.rows = [native(env)]
    response = get(env, organization_id=env.orgs["admin"])
    assert response.status_code == 200
    assert response.json()["items"][0]["organization_id"] == env.orgs["customer"]
    assert env.decision_ids["admin"] not in env.logs.calls[-1][1]
    before = len(env.logs.calls)
    assert get(env, subscription_id=env.decision_ids["admin"]).status_code == 404
    assert get(env, path=ADMIN_PATH).status_code == 403
    assert get(env, path=ADMIN_PATH + "/export.csv").status_code == 403
    assert len(env.logs.calls) == before
    env.logs.rows = [native(env, "admin")]
    data = get(env, path=ADMIN_PATH, headers=env.admin, organization_id=env.orgs["admin"]).json()
    assert data["items"][0]["organization_id"] == env.orgs["admin"]
    assert env.decision_ids["customer"] not in env.logs.calls[-1][1]


def test_admin_all_organizations_are_trusted_but_unknown_sid_not_queried(decision_env):
    env = decision_env
    env.logs.rows = [native(env), native(env, "admin")]
    data = get(env, path=ADMIN_PATH, headers=env.admin).json()
    assert data["total"] == 2 and len(data["breakdown"]) == 2
    calls = len(env.logs.calls)
    data = get(env, path=ADMIN_PATH, headers=env.admin, subscription_id=str(uuid4())).json()
    assert data["status"] == "unavailable" and data["total"] is None
    assert len(env.logs.calls) == calls


@pytest.mark.parametrize("field,value", [
    ("decision_input_tokens", -1), ("decision_output_tokens", True), ("decision_input_tokens", 1.5),
    ("decision_input_tokens", 2147483648), ("decision_output_tokens", float("inf")),
    ("decision_latency_ms", float("nan")), ("decision_latency_ms", 120001),
    ("decision_latency_ms", -1),
    ("decision_cost_usd", "NaN"), ("decision_cost_usd", "-0.1"),
    ("routing_profile", "caller-profile"), ("config_version", "x" * 64),
    ("selected_model", "=formula"), ("selected_model", "x" * 101),
    ("decision_schema", "finops-v1"), ("decision_trace_count", 2),
    ("decision_trace_count", True), ("parent_status_code", 600),
    ("resource_id", "/untrusted/resource"), ("subscription_id", "unknown-secret-subscription"),
    ("request_id", str(uuid4())), ("correlation_id", "not-a-request-id"),
    ("occurred_at", "not-a-timestamp"), ("occurred_at", datetime(2026, 1, 1)),
])
def test_invalid_or_untrusted_rows_fail_closed_without_leak(decision_env, field, value):
    env = decision_env
    env.logs.rows = [native(env), native(env, **{field: value})]
    data = get(env).json()
    assert data["status"] == "unavailable" and data["total"] is None
    assert data["items"] == [] and data["series"] == [] and data["breakdown"] == []
    assert data["summary"]["invocations"] is None
    assert "unknown-secret-subscription" not in json.dumps(data)


@pytest.mark.parametrize("at_end", [False, True])
def test_half_open_viewport_rejects_outside_rows(decision_env, at_end):
    env = decision_env
    occurred = env.decision_end if at_end else env.decision_start - timedelta(microseconds=1)
    env.logs.rows = [native(env, occurred_at=occurred)]
    assert get(env).json()["status"] == "unavailable"


def test_duplicate_resource_correlation_rejected(decision_env):
    env = decision_env
    row = native(env)
    env.logs.rows = [row, row | {"resource_id": env.settings.apim_resource_id.upper()}]
    assert get(env).json()["status"] == "unavailable"


def test_input_only_estimation_and_nullable_token_coverage(decision_env):
    env = decision_env
    env.logs.rows = [native(env, decision_output_tokens=None)]
    data = get(env).json()
    assert data["status"] == "partial"
    assert data["summary"]["input_tokens"] == 100
    assert data["summary"]["output_tokens"] is None and data["summary"]["total_tokens"] is None
    assert data["summary"]["measured_invocations"] == 0 and data["summary"]["missing_token_invocations"] == 1
    assert data["summary"]["estimated_invocations"] == 1 and data["summary"]["unestimated_invocations"] == 0
    assert Decimal(data["summary"]["estimated_cost_usd"]) > 0
    env.logs.rows = [native(env, decision_input_tokens=None, decision_output_tokens=None)]
    data = get(env).json()
    assert data["summary"]["estimated_cost_usd"] is None and data["summary"]["unestimated_invocations"] == 1
    assert "recorded_cost_usd" not in data["summary"]
    env.logs.rows = [native(env, decision_input_tokens=0, decision_output_tokens=0)]
    data = get(env).json()
    assert data["status"] == "available" and data["summary"]["total_tokens"] == 0
    assert data["summary"]["measured_invocations"] == 1
    assert data["summary"]["missing_token_invocations"] == 0
    assert Decimal(data["summary"]["estimated_cost_usd"]) == 0


def test_date_effective_helper_receives_loaded_state(decision_env, monkeypatch):
    env = decision_env
    sentinel = [{"valid_from": env.decision_start}]
    calls = []
    monkeypatch.setattr(telemetry, "load_state", lambda db: (7, sentinel))

    def estimate(version, entries, tokens, occurred):
        assert version == 7 and entries is sentinel
        calls.append((tokens, occurred))
        amount = Decimal("0.25") if tokens is not None else None
        return {"estimated_cost_usd": amount, "estimate_basis": "date-effective-test",
                "pricing_revision": "test-rate-card-v7"}

    monkeypatch.setattr(telemetry, "scoring_effective_estimate", estimate)
    env.logs.rows = [native(env, "admin", decision_output_tokens=None)]
    data = get(env, path=ADMIN_PATH, headers=env.admin).json()
    assert data["items"][0]["estimated_cost_usd"] == "0.25"
    assert data["summary"]["pricing_revision"] == "test-rate-card-v7"
    assert calls[-1] == (100, env.decision_start + timedelta(minutes=1))


@pytest.mark.parametrize("mode", ["partial", "exception", "overflow"])
def test_incomplete_query_never_returns_truncated_or_false_zero(decision_env, mode):
    env = decision_env
    env.logs.rows = [native(env), native(env)]
    if mode == "partial":
        env.logs.status = "PartialError"
    elif mode == "exception":
        env.logs.error = RuntimeError("credential-secret-must-not-leak")
    else:
        env.settings.ingestion_max_rows = 1
    response = get(env)
    data = response.json()
    assert data["status"] == "unavailable" and data["summary"]["invocations"] is None
    assert data["total"] is None and data["items"] == []
    assert "credential-secret" not in response.text
    if mode == "overflow":
        assert "| take 2" in env.logs.calls[-1][1]


@pytest.mark.parametrize("missing", ["log_workspace_id", "apim_resource_id", "apim_product_id", "scope"])
def test_no_credentials_or_logs_when_configuration_or_scope_missing(decision_env, monkeypatch, missing):
    env = decision_env
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Credential/query path must not be reached")

    monkeypatch.setattr(telemetry, "query_rows", forbidden)
    if missing == "scope":
        with Session(env.db_engine) as db:
            for row in db.scalars(select(TeamSubscription)):
                db.delete(row)
            db.commit()
    else:
        setattr(env.settings, missing, "")
    data = get(env).json()
    assert data["status"] == "unavailable" and data["notice"]
    assert data["summary"]["invocations"] is None and env.logs.calls == [] and attempts == []


def test_empty_success_is_distinct_from_unavailable(decision_env):
    data = get(decision_env).json()
    assert data["status"] == "available" and data["total"] == 0
    assert data["summary"]["invocations"] == 0
    assert data["summary"]["estimated_cost_usd"] is None
    assert "recorded_cost_usd" not in data["summary"]


def test_singapore_day_boundaries_clip_to_actual_viewport(decision_env):
    env = decision_env
    midnight_utc = env.decision_end.replace(hour=0, minute=0)
    start, end = midnight_utc - timedelta(hours=10, minutes=30), midnight_utc - timedelta(hours=6)
    env.logs.rows = [native(env, occurred_at=midnight_utc - timedelta(hours=8))]
    data = get(env, start=start.isoformat(), end=end.isoformat(), granularity="day",
               time_zone="Asia/Singapore").json()
    assert len(data["series"]) == 2
    first, second = data["series"]
    boundary = (midnight_utc - timedelta(hours=8)).isoformat()
    assert first["start"] == start.isoformat() and first["end"] == boundary
    assert second["start"] == boundary and second["end"] == end.isoformat()
    assert first["invocations"] == 0 and second["invocations"] == 1
    assert first["partial_bucket"] and second["partial_bucket"]


@pytest.mark.parametrize("params", [
    {"granularity": "month"}, {"time_zone": "Europe/London"}, {"offset": -1}, {"limit": 101},
    {"days": 0}, {"start": "2026-10-30T00:00:00"}, {"subscription_id": "invalid"},
])
def test_parameter_validation_never_queries(decision_env, params):
    env = decision_env
    assert get(env, **params).status_code == 422
    assert env.logs.calls == []


def test_bucket_count_is_bounded_before_query(decision_env):
    env = decision_env
    response = get(env, days=30, start=(env.decision_end - timedelta(days=30)).isoformat(), granularity="minute")
    assert response.status_code == 422 and env.logs.calls == []


def test_csv_scope_metadata_nulls_pagination_and_formula_escape(decision_env):
    env = decision_env
    env.logs.rows = [native(env, decision_output_tokens=None)]
    response = get(env, path=CUSTOMER_PATH + "/export.csv", limit=1)
    assert response.status_code == 200 and "text/csv" in response.headers["content-type"]
    assert response.headers["x-decision-telemetry-status"] == "partial"
    rows = list(csv.reader(io.StringIO(response.text)))
    assert ["status", "partial"] in rows
    assert "recorded_cost_usd" not in response.text
    fields = [field for field in telemetry.ITEM_FIELDS if field != "recorded_cost_usd"]
    header = rows.index(fields)
    assert rows[header + 1][fields.index("output_tokens")] == ""
    assert rows[header + 1][fields.index("organization_id")] == env.orgs["customer"]
    data = get(env).json()
    data["items"][0]["selected_model"] = " =HYPERLINK(1)"
    data["notice"] = "\t@formula"
    escaped = list(csv.reader(io.StringIO(telemetry.decision_csv(data))))
    assert ["notice", "'\t@formula"] in escaped
    assert any("' =HYPERLINK(1)" in row for row in escaped)
    admin = get(env, path=ADMIN_PATH + "/export.csv", headers=env.admin)
    assert admin.status_code == 200
    admin_rows = list(csv.reader(io.StringIO(admin.text)))
    assert list(telemetry.ITEM_FIELDS) in admin_rows
    assert ["summary.recorded_cost_usd", ""] in admin_rows


def test_route_registration_unique_and_frozen_query_not_mutated(decision_env):
    env = decision_env
    paths = [route.path for route in env.app.routes]
    for path in (CUSTOMER_PATH, ADMIN_PATH, CUSTOMER_PATH + "/export.csv", ADMIN_PATH + "/export.csv"):
        assert paths.count(path) == 1
    assert "/api/usage" in paths and "/api/admin/usage" in paths
    path = Path(telemetry.__file__).with_name("queries") / "decision-overhead.kql"
    before = path.read_bytes()
    get(env)
    assert path.read_bytes() == before


@pytest.mark.parametrize("fail", [False, True])
def test_owned_sdk_resources_close_and_retry_timeouts_are_bounded(decision_env, monkeypatch, fail):
    import azure.identity
    import azure.monitor.query

    env = decision_env
    lifecycle = []

    class Credential:
        def __init__(self, **kwargs):
            assert kwargs["retry_total"] == 0 and kwargs["process_timeout"] == 5
            assert kwargs["exclude_interactive_browser_credential"] is True

        def __enter__(self):
            lifecycle.append("credential.open")
            return self

        def __exit__(self, *args):
            lifecycle.append("credential.close")

    class Logs(FakeLogs):
        def __init__(self, credential, **kwargs):
            super().__init__()
            assert isinstance(credential, Credential) and kwargs["retry_total"] == 0
            if fail:
                self.error = RuntimeError("mock-timeout")

        def __enter__(self):
            lifecycle.append("logs.open")
            return self

        def __exit__(self, *args):
            lifecycle.append("logs.close")

    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", Credential)
    monkeypatch.setattr(azure.monitor.query, "LogsQueryClient", Logs)
    env.app.state.decision_telemetry_client = None
    data = get(env).json()
    assert data["status"] == ("unavailable" if fail else "available")
    assert lifecycle == ["credential.open", "logs.open", "logs.close", "credential.close"]


def test_query_insertion_contract_fails_closed_on_source_drift(decision_env, monkeypatch):
    env = decision_env
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: "gateway | take {row_limit}")
    with pytest.raises(ValueError, match="query contract"):
        telemetry.render_query(env.settings, env.decision_start, env.decision_end,
                               {env.decision_ids["customer"]: env.orgs["customer"]}, 10)