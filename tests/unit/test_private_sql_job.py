"""Local-only checks: synthetic tokens, mocked SQL catalog, real SQLite Alembic."""

import base64
import json
import logging
import os
import subprocess
import sys
import warnings
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from aiflux.config import get_settings
from aiflux.models import PortalUser
from aiflux.portal_auth import hash_password
from scripts.deployment import private_sql_job as job

TENANT = "11111111-1111-4111-8111-111111111111"
OPERATOR = "22222222-2222-4222-8222-222222222222"
CLIENT = "12345678-1234-4321-8765-123456789abc"
HOST = "reviewed-sql.database.windows.net"
URL = (f"mssql+pyodbc://@{HOST}:1433/aiflux?driver=ODBC+Driver+18+for+SQL+Server"
       "&Encrypt=yes&TrustServerCertificate=no")
NOW = 1_800_000_000
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def config():
    return job.JobConfig("migrate", HOST, "aiflux", TENANT, OPERATOR, CLIENT, "10.240.3.0/24")


@pytest.fixture
def token_env(monkeypatch):
    monkeypatch.setattr(job.time, "time", lambda: NOW)

    def install(changes=None, *, expiry=NOW + 3600):
        claims = {"tid": TENANT, "oid": OPERATOR, "aud": "https://database.windows.net/",
                  "exp": NOW + 3600}
        for key, value in (changes or {}).items():
            if value is None:
                claims.pop(key, None)
            else:
                claims[key] = value
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        # Not signed, never a real access token; SQL, not this parser, enforces trust.
        monkeypatch.setenv("AIFLUX_SQL_OPERATOR_TOKEN", "e30." + payload + ".synthetic")
        monkeypatch.setenv("AIFLUX_SQL_OPERATOR_TOKEN_EXPIRES_AT", str(expiry))

    install()
    return install


def test_configuration_and_url(config):
    config.validate()
    url = job.validate_url(URL, config)
    assert url.host == HOST and url.password is None
    assert UUID(CLIENT).bytes_le.hex() == "78563412341221438765123456789abc"


@pytest.mark.parametrize("change", [
    {"mode": "probe", "seed": True}, {"sql_host": "other.invalid"},
    {"sql_database": "aiflux;UID=unsafe"}, {"sql_host": HOST + ";Server=unsafe"},
    {"tenant_id": "not-a-uuid"}, {"api_client_id": "00000000-0000-0000-0000-000000000000"},
    {"private_cidr": "0.0.0.0/0"}, {"private_cidr": "127.0.0.0/8"},
    {"private_cidr": "169.254.0.0/16"}, {"private_cidr": "10.240.3.1/24"},
])
def test_unsafe_configuration_rejected(config, change):
    candidate = job.JobConfig(**(vars(config) | change))
    with pytest.raises((job.JobError, ValueError)):
        candidate.validate()


@pytest.mark.parametrize("change", [
    lambda value: value.replace(HOST, "other.database.windows.net"),
    lambda value: value.replace("/aiflux?", "/master?"),
    lambda value: value.replace(":1433", ":1444"),
    lambda value: value.replace("mssql+pyodbc", "mssql+pymssql"),
    lambda value: value.replace("//@", "//user:synthetic%40password@"),
    lambda value: value.replace("//@", "//user@"),
    lambda value: value.replace("//@", "//:synthetic@"),
    lambda value: value.replace("Encrypt=yes", "Encrypt=no"),
    lambda value: value.replace("TrustServerCertificate=no", "TrustServerCertificate=yes"),
    lambda value: value.replace("Driver+18", "Driver+17"),
    lambda value: value + "&Authentication=ActiveDirectoryMsi",
    lambda value: value + "&Trusted_Connection=Yes",
    lambda value: value + "&odbc_connect=Server%3Dother",
    lambda value: value + "&Server=other",
    lambda value: value + "&driver=ODBC+Driver+18+for+SQL+Server",
    lambda value: value.replace("Encrypt=yes", "encrypt=yes"),
    lambda value: value.replace("Encrypt=yes", "Encrypt=yes%3BUID%3Dunsafe"),
    lambda value: value.replace("/aiflux?", "/aiflux%3BServer%3Dunsafe?"),
])
def test_url_fails_closed(config, change):
    with pytest.raises(job.JobError):
        job.validate_url(change(URL), config)


def dns_rows(addresses):
    return [(2, 1, 6, "", (address, 1433)) for address in addresses]


@pytest.mark.parametrize("addresses,accepted", [
    (["10.240.3.4", "10.240.3.5"], True), ([], False),
    (["20.1.2.3"], False), (["10.241.3.4"], False),
    (["10.240.3.4", "20.1.2.3"], False),
    (["10.240.3.4", "10.240.4.4"], False), (["::1"], False),
])
def test_exact_private_dns(config, monkeypatch, addresses, accepted):
    monkeypatch.setattr(job.socket, "getaddrinfo", lambda *a, **k: dns_rows(addresses))
    if accepted:
        job.validate_dns(config)
    else:
        with pytest.raises(job.JobError, match="private_dns_rejected"):
            job.validate_dns(config)


@pytest.mark.parametrize("claims,expiry", [
    ({"exp": NOW - 1}, NOW - 1), ({"exp": None}, NOW + 3600),
    ({"exp": str(NOW + 3600)}, NOW + 3600), ({"exp": True}, NOW + 3600),
    ({"tid": OPERATOR}, NOW + 3600), ({"oid": TENANT}, NOW + 3600),
    ({"aud": "https://management.azure.com/"}, NOW + 3600),
    ({"aud": ["https://database.windows.net/"]}, NOW + 3600),
    ({"nbf": NOW + 10}, NOW + 3600), ({}, NOW + 3601),
    ({}, "NaN"), ({}, "1.8e9"), ({}, NOW + 299),
])
def test_operator_token_guards(config, token_env, claims, expiry):
    token_env(claims, expiry=expiry)
    with pytest.raises(job.JobError):
        job.OperatorCredential.from_environment(config)


def test_static_credential_rechecks_ttl_and_scope(config, token_env, monkeypatch):
    credential = job.OperatorCredential.from_environment(config)
    assert credential.get_token(job.SQL_SCOPE).expires_on == NOW + 3600
    assert "synthetic" not in repr(credential)
    with pytest.raises(job.JobError, match="operator_scope_rejected"):
        credential.get_token("https://management.azure.com/.default")
    monkeypatch.setattr(job.time, "time", lambda: NOW + 3541)
    with pytest.raises(job.JobError, match="operator_token_expiring"):
        credential.get_token(job.SQL_SCOPE)


def test_duplicate_token_claim_rejected(config, token_env, monkeypatch):
    payload = base64.urlsafe_b64encode(b'{"tid":"one","tid":"two"}').decode().rstrip("=")
    monkeypatch.setenv("AIFLUX_SQL_OPERATOR_TOKEN", "e30." + payload + ".synthetic")
    with pytest.raises(job.JobError, match="operator_token_rejected"):
        job.OperatorCredential.from_environment(config)


def test_operator_engine_uses_only_static_token(config, token_env, monkeypatch):
    monkeypatch.setattr(job, "validate_dns", lambda config: None)
    credential = job.OperatorCredential.from_environment(config)
    engine = job.operator_engine(job.validate_url(URL, config), credential, config)
    args = ["Server=reviewed;Trusted_Connection=Yes"]
    params = {}
    for listener in engine.dialect.dispatch.do_connect:
        listener(None, None, args, params)
    assert engine.hide_parameters is True and engine.echo is False
    assert "Trusted_Connection" not in args[0]
    assert set(params["attrs_before"]) == {1256}
    monkeypatch.setattr(job.time, "time", lambda: NOW + 3599)
    with pytest.raises(job.JobError):
        for listener in engine.dialect.dispatch.do_connect:
            listener(None, None, args, {})
    engine.dispose()


class Result:
    def __init__(self, rows=()):
        self.rows = rows

    def all(self):
        return list(self.rows)

    def one(self):
        return self.rows[0]

    def scalar_one(self):
        return self.rows[0][0]

    def scalars(self):
        return Result([row[0] for row in self.rows])


class Catalog:
    def __init__(self, *, principals=None, roles=(), ownership=(), permissions=(),
                 operator=("aiflux", "dbo", 1), effective=(), elevated=()):
        self.principals = ([(7, "aiflux-api", UUID(CLIENT).bytes_le, "E", "EXTERNAL")]
                           if principals is None else principals)
        self.roles = roles
        self.ownership = ownership
        self.permissions = permissions
        self.operator = operator
        self.effective = effective
        self.elevated = elevated
        self.statements = []

    def execute(self, statement, params):
        sql = str(statement)
        self.statements.append(sql)
        if "WHERE name =" in sql:
            return Result(self.principals)
        if "database_role_members" in sql:
            return Result(self.roles)
        if "sys.schemas" in sql:
            return Result(self.ownership)
        if "database_permissions" in sql:
            return Result(self.permissions)
        raise AssertionError("Unexpected catalog statement")

    def exec_driver_sql(self, sql):
        self.statements.append(sql)
        if sql.startswith("SELECT DB_NAME()"):
            return Result([self.operator])
        if "SCHEMA_ID" in sql:
            return Result([(1,)])
        if "SELECT HAS_PERMS" in sql:
            return Result([(1, 1, 1, 1)])
        if "SELECT p.permission_name" in sql:
            return Result(self.elevated)
        if "fn_my_permissions" in sql:
            return Result([(permission,) for permission in self.effective])
        return Result()


@pytest.mark.parametrize("operator", [("master", "dbo", 1), ("aiflux", "aiflux-api", 1),
                                      ("aiflux", "dbo", 0), ("aiflux", "dbo", None)])
def test_actual_database_and_privileges(config, operator):
    with pytest.raises(job.JobError):
        job.verify_operator(Catalog(operator=operator), config)


@pytest.mark.parametrize("changes", [
    {"principals": [(7, "aiflux-api", b"wrong", "E", "EXTERNAL")]},
    {"principals": [(7, "alias", UUID(CLIENT).bytes_le, "E", "EXTERNAL")]},
    {"principals": [(7, "aiflux-api", UUID(CLIENT).bytes_le, "S", "INSTANCE")]},
    {"principals": [(7, "aiflux-api", UUID(CLIENT).bytes_le, "E", "EXTERNAL"),
                    (8, "alias", UUID(CLIENT).bytes_le, "E", "EXTERNAL")]},
    {"roles": [(1,)]}, {"roles": [(16384,)]}, {"roles": [(16390,)]},
    {"ownership": [(7,)]}, {"permissions": [(0, 0, 0, "CONTROL", "G")]},
    {"permissions": [(3, 1, 0, "SELECT", "W")]},
    {"permissions": [(1, 123, 0, "ALTER", "G")]},
])
def test_runtime_audit_rejects_ambiguous_or_privileged_mapping(changes):
    catalog = Catalog(**changes)
    with pytest.raises(job.JobError):
        job.provision_runtime(catalog, CLIENT)
    assert not any(sql.startswith(("CREATE USER", "GRANT", "DENY")) for sql in catalog.statements)


def test_runtime_safe_provision_and_no_silent_replacement():
    catalog = Catalog(permissions=[(3, 1, 0, "SELECT", "G")], effective=["CONNECT"])
    job.provision_runtime(catalog, CLIENT)
    assert not any(sql.startswith("CREATE USER") for sql in catalog.statements)
    assert any(sql.startswith("DENY CREATE TABLE") for sql in catalog.statements)
    database_deny = next(sql for sql in catalog.statements if sql.startswith("DENY CREATE TABLE"))
    assert "CREATE SEQUENCE" not in database_deny
    assert "CREATE TYPE" in database_deny
    assert "DENY CREATE SEQUENCE ON SCHEMA::dbo TO [aiflux-api]" in catalog.statements
    assert "DENY ALTER ON SCHEMA::dbo TO [aiflux-api]" in catalog.statements
    assert not any("DROP USER" in sql or "ALTER ROLE" in sql for sql in catalog.statements)
    assert catalog.statements[-1] == "REVERT"


def test_runtime_sql_failure_has_exact_fixed_stage_without_statement():
    class Broken(Catalog):
        def exec_driver_sql(self, statement):
            if statement.startswith("DENY CREATE TABLE"):
                raise RuntimeError("synthetic-sensitive-driver-text")
            return super().exec_driver_sql(statement)

    with pytest.raises(RuntimeError) as caught:
        job.provision_runtime(Broken(), CLIENT)
    assert caught.value.aiflux_sql_stage == "runtime_deny_database_ddl"


def test_diagnostic_does_not_emit_driver_text_or_unknown_stage(monkeypatch, capsys):
    from scripts.deployment import private_sql_diagnostic as diagnostic

    def failure(config, checks):
        error = RuntimeError("42000", "synthetic-secret SQL text (102)")
        error.aiflux_sql_stage = "synthetic-secret"
        raise error

    monkeypatch.setattr(sys, "argv", ["diagnostic", *cli_args()])
    monkeypatch.setattr(job, "run_job", failure)
    old_disable = logging.root.manager.disable
    try:
        with warnings.catch_warnings():
            assert diagnostic.main() == 1
    finally:
        logging.disable(old_disable)
    captured = capsys.readouterr()
    assert "synthetic-secret" not in captured.out + captured.err
    result = json.loads(captured.out.splitlines()[-1])
    assert result["sqlstate"] == "42000" and result["native_codes"] == [102]
    assert result["stage"] is None


def test_new_runtime_sid_is_client_id_convention():
    catalog = Catalog(principals=[])
    job.provision_runtime(catalog, CLIENT)
    assert any("SID = 0x78563412341221438765123456789abc, TYPE = E" in sql
               for sql in catalog.statements)


def test_effective_elevation_rejected_and_reverted():
    catalog = Catalog(effective=["CONTROL"])
    with pytest.raises(job.JobError, match="runtime_effective_permissions_rejected"):
        job.provision_runtime(catalog, CLIENT)
    assert catalog.statements[-1] == "REVERT"


def test_effective_public_object_permissions_rejected():
    catalog = Catalog(elevated=[("EXECUTE",)])
    with pytest.raises(job.JobError, match="runtime_effective_permissions_rejected"):
        job.provision_runtime(catalog, CLIENT)
    assert catalog.statements[-1] == "REVERT"


@pytest.mark.parametrize("permission", ["CREATE SEQUENCE", "ALTER", "CONTROL", "TAKE OWNERSHIP"])
def test_schema_sequence_or_other_elevation_still_rejected(permission):
    with pytest.raises(job.JobError, match="runtime_effective_permissions_rejected"):
        job.verify_effective_permissions(Catalog(elevated=[(permission,)]))


@pytest.mark.parametrize("native,accepted", [
    (262, True), (2760, True), (15247, True), (102, False), (99999, False), (None, False)])
def test_real_mi_probe_is_rollback_only_and_never_accepts_syntax_or_success(
        config, monkeypatch, capsys, native, accepted):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import azure.identity

    rollbacks, closed, statements = [], [], []
    credential = SimpleNamespace(close=lambda: closed.append("credential"))

    def managed_identity(**kwargs):
        assert kwargs == {"client_id": CLIENT}
        return credential

    monkeypatch.setattr(azure.identity, "ManagedIdentityCredential", managed_identity)

    class RuntimeConnection(Catalog):
        def begin(self):
            return SimpleNamespace(rollback=lambda: rollbacks.append(True))

        def execute(self, statement, params):
            statements.append(str(statement))
            if str(statement).startswith("SELECT COUNT"):
                return Result([(0 if job.SQL_STAGE.get() == "runtime_mi_rollback" else 1,)])
            return SimpleNamespace(rowcount=1)

        def exec_driver_sql(self, statement):
            statements.append(statement)
            if statement.startswith("SELECT DB_NAME()"):
                return Result([("aiflux", "aiflux-api", 0, 1)])
            if statement.startswith("CREATE ") and native is not None:
                raise RuntimeError("42000", f"synthetic-secret-driver-text ({native})")
            return super().exec_driver_sql(statement)

    connection = RuntimeConnection(effective=["CONNECT"])
    engine = SimpleNamespace(connect=lambda: nullcontext(connection),
                             dispose=lambda: closed.append("engine"))

    def make_engine(url, supplied, supplied_config):
        assert supplied is credential and supplied_config is config
        return engine

    monkeypatch.setattr(job, "operator_engine", make_engine)
    checks = []
    if accepted:
        job.verify_runtime_mi(job.validate_url(URL, config), config, checks)
        assert checks == ["api_managed_identity_authenticated", "api_managed_identity_dml_verified",
                          "api_managed_identity_ddl_denied"]
        assert len(rollbacks) == 4
    else:
        with pytest.raises(job.JobError, match="runtime_mi_ddl_not_denied") as caught:
            job.verify_runtime_mi(job.validate_url(URL, config), config, checks)
        if native is not None:
            assert job.driver_codes(caught.value) == ("42000", [native])
            assert caught.value.aiflux_sql_stage == "runtime_mi_create_table"
        assert "api_managed_identity_ddl_denied" not in checks
        assert len(rollbacks) == 2
    assert closed == ["engine", "credential"]
    assert not any(sql.startswith(("GRANT", "DENY", "EXECUTE AS")) for sql in statements)
    assert "synthetic-secret-driver-text" not in capsys.readouterr().out


@pytest.fixture
def sqlite_engine(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "migration.db").as_posix()
    monkeypatch.setenv("AIFLUX_DATABASE_URL", url)
    get_settings.cache_clear()
    engine = create_engine(url)
    yield engine
    engine.dispose()
    get_settings.cache_clear()


def test_real_alembic_supplied_connection_and_idempotent_head(sqlite_engine, monkeypatch):
    import aiflux.db

    def forbidden_fallback(*args, **kwargs):
        pytest.fail("Alembic must use the supplied operator connection")

    monkeypatch.setattr(aiflux.db, "engine_for", forbidden_fallback)
    credential = job.OperatorCredential("unused-synthetic", 4_000_000_000)
    job.apply_migrations(sqlite_engine, credential)
    job.apply_migrations(sqlite_engine, credential)
    with sqlite_engine.connect() as connection:
        job.verify_schema(connection)
    assert "portal_users" in inspect(sqlite_engine).get_table_names()


def test_real_schema_verification_detects_missing_table(sqlite_engine):
    job.apply_migrations(sqlite_engine, job.OperatorCredential("unused", 4_000_000_000))
    with sqlite_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE portal_users")
        with pytest.raises(job.JobError, match="schema_mismatch"):
            job.verify_schema(connection)


def install_seed(monkeypatch):
    # Synthetic local-test password only. Never printed or parametrized.
    records = [{"username": name, "role": role, "password": "Local-test!9-Zebra"}
               for name, role in job.EXPECTED_ACCOUNTS.items()]
    monkeypatch.setenv("AIFLUX_PORTAL_SEED_USERS", json.dumps(records))


def test_real_seed_four_accounts_and_repeat(sqlite_engine, config, monkeypatch):
    job.apply_migrations(sqlite_engine, job.OperatorCredential("unused", 4_000_000_000))
    install_seed(monkeypatch)
    settings = job.seed_settings(config)
    job.seed_accounts(sqlite_engine, settings)
    with Session(sqlite_engine) as session:
        before = {user.username: user.password_hash for user in session.scalars(select(PortalUser))}
    job.seed_accounts(sqlite_engine, settings)
    with Session(sqlite_engine) as session:
        after = {user.username: user.password_hash for user in session.scalars(select(PortalUser))}
    assert set(before) == set(job.EXPECTED_ACCOUNTS)
    assert before == after


def test_seed_mismatch_rolls_back_new_accounts(sqlite_engine, config, monkeypatch):
    job.apply_migrations(sqlite_engine, job.OperatorCredential("unused", 4_000_000_000))
    install_seed(monkeypatch)
    settings = job.seed_settings(config)
    job.seed_accounts(sqlite_engine, settings)
    with Session(sqlite_engine) as session:
        users = session.scalars(select(PortalUser)).all()
        for user in users:
            if user.username != "admin":
                session.delete(user)
            else:
                user.password_hash = hash_password("Different-test!8-Key")
        session.commit()
    with pytest.raises(job.JobError, match="seed_verification_rejected"):
        job.seed_accounts(sqlite_engine, settings)
    with Session(sqlite_engine) as session:
        assert session.scalars(select(PortalUser.username)).all() == ["admin"]


def test_seed_requires_exact_accounts_and_strong_explicit_input(config, monkeypatch):
    monkeypatch.delenv("AIFLUX_PORTAL_SEED_USERS", raising=False)
    with pytest.raises(job.JobError):
        job.seed_settings(config)
    monkeypatch.setenv("AIFLUX_PORTAL_SEED_USERS", '[{"username":"admin","password":"weak"}]')
    with pytest.raises(ValueError):
        job.seed_settings(config)


def test_probe_never_calls_ddl_or_seeding(config, token_env, monkeypatch):
    config = job.JobConfig(**(vars(config) | {"mode": "probe"}))
    monkeypatch.setenv("AIFLUX_DATABASE_URL", URL)
    monkeypatch.setenv("AIFLUX_PORTAL_SEED_USERS", "not-json-ignored-without-seed")
    monkeypatch.setattr(job, "validate_dns", lambda config: None)
    import pyodbc
    monkeypatch.setattr(pyodbc, "drivers", lambda: [job.DRIVER])
    catalog = Catalog()

    class FakeEngine:
        disposed = False

        def connect(self):
            from contextlib import nullcontext
            return nullcontext(catalog)

        def dispose(self):
            self.disposed = True

    engine = FakeEngine()
    monkeypatch.setattr(job, "operator_engine", lambda *args: engine)
    monkeypatch.setattr(job, "apply_migrations", lambda *args: pytest.fail("probe attempted DDL"))
    monkeypatch.setattr(job, "seed_accounts", lambda *args: pytest.fail("probe attempted seed"))
    checks = []
    job.run_job(config, checks)
    assert engine.disposed
    assert checks[-1] == "operator_database_verified"
    assert all(sql.startswith("SELECT") for sql in catalog.statements)


def cli_args():
    return ["probe", "--sql-host", HOST, "--sql-database", "aiflux", "--tenant-id", TENANT,
            "--operator-object-id", OPERATOR, "--api-client-id", CLIENT,
            "--private-cidr", "10.240.3.0/24"]


def test_entrypoint_redacts_raw_exception_and_logs(monkeypatch, capsys):
    old_disable = logging.root.manager.disable

    def failure(config, checks):
        logging.getLogger("sqlalchemy.engine").critical("synthetic-sensitive-content")
        warnings.warn("synthetic-sensitive-content", stacklevel=1)
        raise RuntimeError("synthetic-sensitive-content")

    monkeypatch.setattr(job, "run_job", failure)
    try:
        with warnings.catch_warnings():
            assert job.main(cli_args()) == 1
    finally:
        logging.disable(old_disable)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "code": "job_failed", "checks": []}
    assert captured.err == ""


@pytest.mark.parametrize("code,expected", [("odbc18_unavailable", "odbc18_unavailable"),
                                          ("synthetic-sensitive-content", "job_failed")])
def test_entrypoint_only_emits_allowlisted_error_codes(monkeypatch, capsys, code, expected):
    old_disable = logging.root.manager.disable

    def failure(config, checks):
        raise job.JobError(code)

    monkeypatch.setattr(job, "run_job", failure)
    try:
        with warnings.catch_warnings():
            assert job.main(cli_args()) == 1
    finally:
        logging.disable(old_disable)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "code": expected, "checks": []}
    assert captured.err == ""


def test_real_entrypoint_rejects_cli_token_without_echo():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/deployment/private_sql_job.py"),
         *cli_args(), "--token", "synthetic-sensitive-content"],
        capture_output=True, text=True, env=os.environ.copy(), check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"status": "failed", "code": "arguments_rejected", "checks": []}
    assert result.stderr == ""


def test_container_definition_retains_nonroot_and_clears_api_command():
    dockerfile = (ROOT / "infra/sql/private-runner.Dockerfile").read_text()
    assert "ARG API_IMAGE\nFROM ${API_IMAGE}" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert 'ENTRYPOINT ["python", "/app/scripts/deployment/private_sql_job.py"]' in dockerfile
    assert "CMD []" in dockerfile