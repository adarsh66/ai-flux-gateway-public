"""Offline PostgreSQL session contract; real loaders, NOT server observations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex

import pytest
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.bool import BoolLoader
from psycopg.types.string import TextLoader

from tests.unit.test_finops_private_probe import Database, NOW, ROLE, probe
from tests.unit.test_finops_probe_diagnostics import offline_main
from tests.unit.test_finops_runner_preparation import entrypoint


def documented_session(tmp_path, monkeypatch):
    """Feed documented wire values to installed psycopg; no connection made.

    search_path is a string GUC, not a normalized identifier array. Its startup
    setting is public,pg_catalog. current_setting returns text (OID 25), even
    for boolean GUCs; current_database/user/schema return name (OID 19).
    https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SET
    https://www.postgresql.org/docs/16/runtime-config-client.html#GUC-SEARCH-PATH
    """
    def forbidden(*_args, **_kwargs):
        pytest.fail("offline session tests must not connect or resolve DNS")
    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(probe.socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(probe.socket.socket, "connect", forbidden)
    monkeypatch.setattr(probe.socket.socket, "connect_ex", forbidden)
    ca = tmp_path / "synthetic-ca.pem"
    ca.write_text("path only; no TLS attempted")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    options = probe.connection_options(f"postgresql://{ROLE}@{probe.HOST}/turnstile", ROLE)
    startup = conninfo_to_dict(make_conninfo(**options))["options"]
    path = next(x.removeprefix("search_path=") for x in shlex.split(startup)
                if x.startswith("search_path="))
    assert path == "public,pg_catalog"
    name = TextLoader(19).load
    text = TextLoader(25).load
    row = (name(b"turnstile"), name(ROLE.encode()), name(ROLE.encode()),
           name(b"public"), text(path.encode()), text(b"on"))
    assert all(type(x) is str for x in row)
    assert BoolLoader(16).load(b"t") is True  # Not the GUC's text type.
    assert text(b"repeatable read") == "repeatable read"  # Not repeatable_read.
    return row


def test_startup_search_path_with_real_text_loader_is_not_a_session_failure(tmp_path, monkeypatch):
    db = Database()
    db.answers[0] = documented_session(tmp_path, monkeypatch)
    report = probe.inspect_database(db, ROLE, now=NOW)
    assert report["status"] == "verified_read_only_snapshot" and db.rolled_back
    supervisor = entrypoint()
    first = supervisor.sanitize(json.dumps(report, default=str), 0)
    assert first["status"] == "verified_read_only_snapshot"
    assert supervisor.sanitize(json.dumps(first), 0) == first


@pytest.mark.parametrize("index,value,reason", [
    (0, "SECRET-DB", "database_session_database"),
    (1, "SECRET-LOGIN", "database_session_session_user"),
    (2, "SECRET-ROLE", "database_session_current_user"),
    (3, None, "database_session_schema"),
    (3, "pg_catalog", "database_session_schema"),
    (4, '"$user", public', "database_session_search_path"),
    (4, "pg_catalog,public", "database_session_search_path"),
    (4, "public,SECRET", "database_session_search_path"),
    (4, "public,pg_catalog,pg_temp", "database_session_search_path"),
    (4, '"public,pg_catalog"', "database_session_search_path"),
    (4, "public,pg_catalog ", "database_session_search_path"),
    (5, True, "database_session_read_only"),
    (5, "off", "database_session_read_only"),
])
def test_session_invariant_has_precise_finite_reason_through_both_sanitizers(index, value, reason):
    db = Database()
    row = list(db.answers[0])
    row[index] = value
    db.answers[0] = tuple(row)
    progress = {}
    with pytest.raises(probe.ProbeBlocked) as caught:
        probe.inspect_database(db, ROLE, now=NOW, progress=progress)
    assert str(caught.value) == reason
    report = probe.failure_report(caught.value, progress["stage"])
    assert report["reason"] == reason and report["stage"] == "database_session"
    assert report["sqlstate"] is None and report["database_writes"] == 0
    assert "SECRET" not in json.dumps(report) and ROLE not in json.dumps(report)
    supervisor = entrypoint()
    assert supervisor.sanitize(json.dumps(report), 2) == report
    assert supervisor.sanitize(json.dumps(supervisor.sanitize(json.dumps(report), 2)), 0) == report
    assert db.rolled_back and len(db.statements) == 2  # No roles/grants/usage reads.


@pytest.mark.parametrize("row", [None, (), ("SECRET",), (True,) * 7])
def test_malformed_session_row_has_finite_shape_diagnostic(row):
    db = Database()
    db.answers[0] = row
    with pytest.raises(probe.ProbeBlocked, match="^database_session_shape$"):
        probe.inspect_database(db, ROLE, now=NOW)
    assert db.rolled_back


@pytest.mark.parametrize("index,value,reason", [
    (0, "SECRET-DB", "database_session_database"),
    (1, "SECRET-LOGIN", "database_session_session_user"),
    (2, "SECRET-ROLE", "database_session_current_user"),
    (3, "pg_catalog", "database_session_schema"),
    (4, "SECRET-PATH", "database_session_search_path"),
    (5, "off", "database_session_read_only"),
])
def test_actual_main_emits_nonempty_precise_session_code(index, value, reason,
        offline_main, monkeypatch, capsys):
    db = Database()
    row = list(db.answers[0])
    row[index] = value
    db.answers[0] = tuple(row)
    monkeypatch.setattr(psycopg, "connect", lambda **_kwargs: db)
    assert probe.main() == 2
    captured = capsys.readouterr()
    assert captured.out and not captured.err
    report = json.loads(captured.out)
    assert report == {"status": "blocked", "stage": "database_session",
        "exception_type": "ProbeBlocked", "reason": reason, "sqlstate": None,
        "database_writes": 0, "replay_authorized": False}
    assert "SECRET" not in captured.out and ROLE not in captured.out and probe.HOST not in captured.out
    supervisor = entrypoint()
    assert supervisor.sanitize(json.dumps(supervisor.sanitize(captured.out, 2)), 0) == report
    assert db.rolled_back and len(db.statements) == 2


def test_corrected_image_false_predicate_reproduces_189_bytes_but_not_actual_field(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "gateway/validation/finops-corrected-image-05a9ff859f48.json").read_text())
    outcome = json.loads((root / "gateway/validation/finops-corrected-outcome-05a9ff859f48.json").read_text())
    context = root / ".deployment/finops-runner/05a9ff859f48/image-context"
    modules = []
    for filename in ("finops_private_probe.py", "entrypoint.py"):
        path = context / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["context_files_sha256"][filename]
        spec = importlib.util.spec_from_file_location("corrected_old_" + filename[:-3], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    old_probe, old_supervisor = modules
    row = documented_session(tmp_path, monkeypatch)
    # Distinct causes give identical retained output: no recovery of actual row.
    for session in (row, ("wrong_db", *row[1:4], "public, pg_catalog", "on")):
        db = Database()
        db.answers[0] = session
        progress = {}
        with pytest.raises(old_probe.ProbeBlocked) as caught:
            old_probe.inspect_database(db, ROLE, now=NOW, progress=progress)
        report = old_probe.failure_report(caught.value, progress["stage"])
        assert db.rolled_back and len(db.statements) == 2
        assert old_supervisor.sanitize(json.dumps(report), 2) == report
        wire = (json.dumps(report) + "\n").encode()
        assert len(wire) == 189
        assert hashlib.sha256(wire).hexdigest() == "e371609eebb403db74832defdafdf8d90bfd0595e093f7fdb000860f878ef6e8"
        assert all(actual["sanitized_result"] == report for actual in outcome["probes"].values())