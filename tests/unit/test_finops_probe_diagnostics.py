"""Finite diagnostics and dependency-shape regressions; no live I/O."""
import base64
import builtins
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
import azure.identity
import psycopg

from tests.unit.test_finops_private_probe import Database, NOW, ROLE, probe, token
from tests.unit.test_finops_runner_preparation import entrypoint


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("11"), Decimal("1e30"), 0, 107])
def test_aggregate_conversion_is_lossless(value):
    assert type(probe.aggregate_integer(value)) is int
    assert probe.aggregate_integer(value) == value


@pytest.mark.parametrize("value", [Decimal("0.1"), Decimal("NaN"), Decimal("Infinity"),
    Decimal("-1"), Decimal("1e101"), True, False, None, "11", 11.0])
def test_bad_aggregates_fail_closed_without_rounding(value):
    with pytest.raises(probe.ProbeBlocked, match="aggregate_integer_required"):
        probe.aggregate_integer(value)


@pytest.mark.parametrize("value", [None, "", "opaque", "x.y", "x.!!!!.z",
    "x." + base64.urlsafe_b64encode(b"[]").decode().rstrip("=") + ".z",
    token(aud=[]), token(exp="123"), token(exp=True), token(exp=float("inf")),
    token(exp=float("nan")), token(exp=10**1000)])
def test_bad_jwt_shapes_fail_closed_with_fixed_labels(value):
    with pytest.raises(probe.ProbeBlocked):
        probe.verify_token(value, "expected-object")


@pytest.mark.parametrize("stage", sorted(probe.STAGES))
def test_every_stage_survives_two_sanitizers_without_exception_messages(stage):
    supervisor = entrypoint()
    assert probe.STAGES == supervisor.STAGES
    assert probe.EXCEPTION_TYPES == supervisor.EXCEPTION_TYPES
    assert probe.GUARD_REASONS == supervisor.GUARD_REASONS
    value = probe.failure_report(TypeError("SECRET-DSN-TOKEN-HOST-USER-SQL"), stage)
    assert value["stage"] == stage and value["exception_type"] == "TypeError"
    assert "SECRET" not in json.dumps(value)
    assert supervisor.sanitize(json.dumps(value), 2) == value
    assert supervisor.sanitize(json.dumps(supervisor.sanitize(json.dumps(value), 2)), 0) == value


@pytest.mark.parametrize("field,value", [("reason", "SECRET"), ("stage", "SECRET"),
    ("exception_type", "SECRET"), ("sqlstate", "SECRT"), ("database_writes", False),
    ("database_writes", 1), ("replay_authorized", True), ("raw_message", "SECRET")])
def test_failure_sanitizer_rejects_non_allowlisted_fields(field, value):
    report = probe.failure_report(TypeError("SECRET"), "identity_token")
    report[field] = value
    result = entrypoint().sanitize(json.dumps(report), 2)
    assert result["reason"] == "unverified_runtime_failure"
    assert "SECRET" not in json.dumps(result) and "SECRT" not in json.dumps(result)


def test_unknown_exception_name_and_state_cannot_be_exfiltration_channels():
    custom = type("SECRET", (Exception,), {"sqlstate": "SECRT"})
    report = probe.failure_report(custom("SECRET"), "database_connect")
    assert report["exception_type"] == "unknown" and report["sqlstate"] is None
    assert "SECRET" not in json.dumps(report)
    report = probe.failure_report(psycopg.errors.InsufficientPrivilege("SECRET"), "database_privileges")
    assert report["exception_type"] == "InsufficientPrivilege" and report["sqlstate"] == "42501"


@pytest.mark.parametrize("index,stage", [(0, "database_session"), (1, "database_role"),
    (2, "database_privileges"), (3, "database_privileges"), (8, "usage_all_time"),
    (9, "usage_window"), (10, "ingestion_checkpoint"), (11, "subscription_bindings"),
    (12, "usage_ownership"), (13, "price_coverage")])
def test_query_failure_stage_is_exact_and_always_rolls_back(index, stage):
    class Failed(Database):
        def execute(self, query, parameters=None):
            if len(self.statements) - 1 == index:
                raise psycopg.OperationalError("SECRET")
            super().execute(query, parameters)
    db = Failed()
    progress = {}
    with pytest.raises(psycopg.OperationalError):
        probe.inspect_database(db, ROLE, now=NOW, progress=progress)
    assert progress["stage"] == stage and db.rolled_back


def test_rollback_error_has_its_own_stage():
    class Failed(Database):
        def rollback(self):
            raise psycopg.OperationalError("SECRET")
    progress = {}
    with pytest.raises(psycopg.OperationalError):
        probe.inspect_database(Failed(), ROLE, now=NOW, progress=progress)
    assert progress["stage"] == "database_rollback"


@pytest.fixture
def offline_main(monkeypatch, tmp_path):
    client = "e1d25c87-9df1-4225-9744-ce22121cf462"
    oid = "edbfc3e2-a8e5-4652-9bb0-311233756d42"
    monkeypatch.setattr(sys, "argv", ["probe", "--role", ROLE, "--client-id", client, "--object-id", oid])
    monkeypatch.setenv("AZURE_CLIENT_ID", client)
    monkeypatch.setenv("AIFLUX_DATABASE_URL", f"postgresql://{ROLE}@{probe.HOST}/turnstile")
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic path only; no TLS attempted")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    monkeypatch.setattr(probe.socket, "getaddrinfo", lambda *_a, **_kw:
        [(None, None, None, None, ("10.240.3.12", 5432))])
    class Credential:
        def __init__(self, *, client_id): assert client_id == client
        def __enter__(self): return self
        def __exit__(self, *_a): pass
        def get_token(self, scope):
            assert scope == "https://ossrdbms-aad.database.windows.net/.default"
            return SimpleNamespace(token=token(oid=oid))
    monkeypatch.setattr(azure.identity, "ManagedIdentityCredential", Credential)
    def no_connection(**_kwargs):
        raise psycopg.OperationalError("SECRET")
    monkeypatch.setattr(psycopg, "connect", no_connection)
    return Credential


@pytest.mark.parametrize("stage", ["dependency_import", "dns_resolution", "identity_initialization",
    "identity_token", "token_validation", "database_connect"])
def test_actual_main_classifies_immediate_failures_without_live_calls(stage, offline_main, monkeypatch, capsys):
    def fail(*_args, **_kwargs): raise TypeError("SECRET-DSN-TOKEN-HOST-USER-SQL")
    if stage == "dependency_import":
        original = builtins.__import__
        def fail_import(name, *args, **kwargs):
            if name == "azure.identity": raise ModuleNotFoundError("SECRET")
            return original(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", fail_import)
    elif stage == "dns_resolution": monkeypatch.setattr(probe.socket, "getaddrinfo", fail)
    elif stage == "identity_initialization": monkeypatch.setattr(azure.identity, "ManagedIdentityCredential", fail)
    elif stage == "identity_token": monkeypatch.setattr(offline_main, "get_token", fail)
    elif stage == "token_validation": monkeypatch.setattr(probe, "verify_token", fail)
    assert probe.main() == 2
    captured = capsys.readouterr()
    assert not captured.err and "SECRET" not in captured.out
    report = json.loads(captured.out)
    assert report["stage"] == stage
    assert entrypoint().sanitize(json.dumps(report), 2) == report


def test_worker_import_failure_never_exports_stderr(tmp_path, capsys, monkeypatch):
    source = tmp_path / "probe.py"
    source.write_text("raise ModuleNotFoundError('SECRET')")
    supervisor = entrypoint()
    monkeypatch.setenv("AZURE_CLIENT_ID", "synthetic-before-worker")
    monkeypatch.setenv("AIFLUX_DATABASE_URL", "synthetic-before-worker")
    disabled = []
    monkeypatch.setattr(supervisor.logging, "disable", disabled.append)
    assert supervisor.worker("ingestion", source) == 2
    assert disabled == [supervisor.logging.CRITICAL]
    captured = capsys.readouterr()
    assert not captured.err and "SECRET" not in captured.out
    value = json.loads(captured.out)
    assert value["stage"] == "dependency_import" and value["exception_type"] == "ModuleNotFoundError"


def test_psycopg_query_api_uses_positional_parameters_not_sqlalchemy_dicts():
    db = Database()
    probe.inspect_database(db, ROLE, now=NOW)
    for sql, params in db.statements:
        assert sql.startswith(("SELECT ", "SET TRANSACTION "))
        assert params is None or type(params) is tuple
        assert sql.count("%s") == (len(params) if params else 0)
    # These are the actual mapped schema columns, not invented dictionary mocks.
    from aiflux.models import ModelPrice, TeamSubscription, UsageRecord
    assert {"effective_from", "effective_to", "currency"} <= set(ModelPrice.__table__.columns.keys())
    assert {"created_at", "state", "organization_id"} <= set(TeamSubscription.__table__.columns.keys())
    assert {"occurred_at", "ingested_at", "input_tokens", "output_tokens", "cost", "currency"} <= set(UsageRecord.__table__.columns.keys())


def test_real_libpq_accepts_reviewed_ssl_and_readonly_options(tmp_path, monkeypatch):
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic path only; no connection")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    options = probe.connection_options(f"postgresql://{ROLE}@{probe.HOST}/turnstile", ROLE)
    options["hostaddr"] = "10.240.3.12"
    parsed = conninfo_to_dict(make_conninfo(**options, password="synthetic-token"))
    assert parsed["sslrootcert"] == str(ca) and parsed["sslmode"] == "verify-full"
    assert parsed["hostaddr"] == "10.240.3.12" and parsed["host"] == probe.HOST
    assert parsed["connect_timeout"] == "8"
    assert parsed["options"] == options["options"]


def test_missing_ca_blocks_before_dns_or_identity(offline_main, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "absent.pem"))
    monkeypatch.setattr(probe.socket, "getaddrinfo", lambda *_a, **_kw: pytest.fail("must block before DNS"))
    assert probe.main() == 2
    value = json.loads(capsys.readouterr().out)
    assert value["stage"] == "configuration" and value["reason"] == "trusted_ca_required"


def test_exact_historical_image_reproduces_the_recorded_generic_failure():
    """Historical files are read-only; do not overwrite image/session evidence."""
    root = Path(__file__).resolve().parents[2]
    context = root / ".deployment/finops-runner/2f75015b55d1/image-context"
    manifest = json.loads((root / "gateway/validation/finops-runner-image-20261027.json").read_text())
    import hashlib
    modules = []
    for filename in ("finops_private_probe.py", "entrypoint.py"):
        path = context / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["context_files_sha256"][filename]
        spec = importlib.util.spec_from_file_location("historical_" + filename[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    old_probe, old_supervisor = modules
    db = Database()
    db.answers[9] = (2, Decimal(11), Decimal(107), 1, 2, Decimal(18))
    success = old_probe.inspect_database(db, ROLE, now=NOW)
    rejected = old_supervisor.sanitize(json.dumps(success, default=str), 0)
    rendered = json.dumps(rejected) + "\n"
    execution = json.loads((root / "gateway/validation/finops-fresh-execution-9461fb0c1a35.json").read_text())
    for actual in execution["probes"].values():
        assert rejected == actual["sanitized_result"]
        assert len(rendered.encode()) == actual["arm_logs_bytes"] == 130
        assert hashlib.sha256(rendered.encode()).hexdigest() == actual["arm_logs_sha256"]
    # The SAME output also results from any swallowed failure: cause not recoverable.
    hidden = old_supervisor.sanitize(json.dumps({"status":"blocked", "exception_type":"TypeError",
        "reason":"unverified_runtime_failure", "sqlstate":None}), 2)
    assert hidden == rejected