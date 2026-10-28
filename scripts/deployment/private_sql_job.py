"""Operator-token-only private SQL job; never provisions resources or changes Entra admins.

Run in the private runner image, with an approved private route already available.
Required environment: AIFLUX_DATABASE_URL, AIFLUX_SQL_OPERATOR_TOKEN,
AIFLUX_SQL_OPERATOR_TOKEN_EXPIRES_AT (integer Unix seconds). --seed additionally
requires AIFLUX_PORTAL_SEED_USERS: exactly customer1/2/3 (customer) and admin
(ids_admin), with independently supplied strong passwords. No .env file is read.

Token claims are UNVERIFIED routing hints. Azure SQL validates the token. Requiring
the authenticated database user dbo and CONTROL rejects ordinary contained users;
this does not attest the ARM Entra admin assignment or assume an oid-to-SID mapping
(group administrators and dbo have different mapping semantics).

Migration, identity provisioning and seeding commit separately. A failed job may
have committed earlier phases; review its fixed check labels before retrying.
No CLI credential discovery, Graph lookups, password fallback or global patches.
Optional --verify-api-mi uses only the explicitly selected API managed identity
for rollback-only DML and denied DDL probes, never for migrations/provisioning.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import logging
import os
import re
import socket
import struct
import sys
import time
import warnings
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Never
from uuid import UUID, uuid4, uuid5

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from azure.core.credentials import AccessToken, TokenCredential
from sqlalchemy import Connection, Engine, create_engine, event, inspect, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from aiflux.config import Settings
from aiflux.models import Base, PortalUser
from aiflux.portal_auth import account_organization, parse_seed_users, seed_portal_users, verify_password

ROOT = Path(__file__).resolve().parents[2]
SQL_SCOPE = "https://database.windows.net/.default"
DRIVER = "ODBC Driver 18 for SQL Server"
EXPECTED_ACCOUNTS = {"customer1": "customer", "customer2": "customer", "customer3": "customer",
                     "admin": "ids_admin"}
PRIVATE_RANGES = tuple(ipaddress.ip_network(value) for value in
                       ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))
ERROR_CODES = frozenset({
    "arguments_rejected", "configuration_rejected", "private_cidr_rejected", "sql_url_rejected",
    "private_dns_rejected", "operator_token_rejected", "operator_token_expiring",
    "operator_scope_rejected", "database_mismatch", "operator_privilege_rejected",
    "migration_head_mismatch", "schema_mismatch", "runtime_identity_rejected",
    "runtime_roles_rejected", "runtime_ownership_rejected", "runtime_permissions_rejected",
    "runtime_effective_permissions_rejected", "seed_configuration_rejected",
    "seed_verification_rejected", "odbc18_unavailable",
    "runtime_mi_identity_rejected", "runtime_mi_dml_rejected", "runtime_mi_ddl_not_denied",
})
SQL_STAGES = frozenset({
    "operator_identity", "runtime_principal", "runtime_roles", "runtime_ownership",
    "runtime_permissions", "dbo_schema_id", "runtime_xact_abort", "runtime_create_user",
    "runtime_grant_dml", "runtime_deny_database_ddl", "runtime_deny_schema_alter",
    "runtime_execute_as", "runtime_effective_dml", "runtime_effective_database",
    "runtime_effective_objects", "runtime_revert", "migration_statement",
    "schema_statement", "seed_statement", "unclassified_statement",
    "runtime_deny_schema_sequence", "runtime_mi_identity", "runtime_mi_insert",
    "runtime_mi_select", "runtime_mi_update", "runtime_mi_delete", "runtime_mi_rollback",
    "runtime_mi_create_table", "runtime_mi_create_sequence", "runtime_mi_create_type",
})
SQL_STAGE: ContextVar[str] = ContextVar("private_sql_stage", default="unclassified_statement")


def sql(connection: Connection, stage: str, statement: str, parameters: dict | None = None):
    """Fixed source labels only; never derive diagnostics from SQL or its arguments."""
    require(stage in SQL_STAGES, "configuration_rejected")
    SQL_STAGE.set(stage)
    try:
        if parameters is not None:
            return connection.execute(text(statement), parameters)
        return connection.exec_driver_sql(statement)
    except Exception as error:
        error.aiflux_sql_stage = stage
        raise


class JobError(Exception):
    """Only fixed, non-sensitive codes may cross the entrypoint boundary."""


def require(condition: object, code: str) -> None:
    if not condition:
        raise JobError(code)


@dataclass(frozen=True, repr=False)
class JobConfig:
    mode: str
    sql_host: str
    sql_database: str
    tenant_id: str
    operator_object_id: str
    api_client_id: str
    private_cidr: str
    seed: bool = False
    verify_api_mi: bool = False

    def validate(self) -> None:
        require(self.mode in {"probe", "migrate"} and (not self.seed or self.mode == "migrate")
            and (not self.verify_api_mi or self.mode == "migrate"),
                "configuration_rejected")
        require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}\.database\.windows\.net", self.sql_host),
                "configuration_rejected")
        require(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.sql_database), "configuration_rejected")
        for value in (self.tenant_id, self.operator_object_id, self.api_client_id):
            require(str(UUID(value)) == value.lower() and UUID(value).int != 0, "configuration_rejected")
        network = ipaddress.ip_network(self.private_cidr, strict=True)
        require(any(
            (isinstance(network, ipaddress.IPv4Network) and isinstance(private, ipaddress.IPv4Network)
             and network.subnet_of(private))
            or (isinstance(network, ipaddress.IPv6Network) and isinstance(private, ipaddress.IPv6Network)
                and network.subnet_of(private))
            for private in PRIVATE_RANGES
        ), "private_cidr_rejected")


def validate_url(raw: str, config: JobConfig) -> URL:
    url = make_url(raw)
    require(url.drivername == "mssql+pyodbc" and not url.username and url.password is None,
            "sql_url_rejected")
    require(url.host == config.sql_host and url.database == config.sql_database
            and url.port in (None, 1433), "sql_url_rejected")
    # Whitelist, not blacklist: no Authentication, UID/PWD, odbc_connect,
    # Trusted_Connection, alternate server, certificate override or ODBC injection.
    require(set(url.query) == {"driver", "Encrypt", "TrustServerCertificate"}, "sql_url_rejected")
    require(url.query["driver"] == DRIVER and url.query["Encrypt"] in ("yes", "mandatory", "strict")
            and url.query["TrustServerCertificate"] == "no", "sql_url_rejected")
    return url


def validate_dns(config: JobConfig) -> None:
    network = ipaddress.ip_network(config.private_cidr)
    addresses = {row[4][0] for row in socket.getaddrinfo(
        config.sql_host, 1433, type=socket.SOCK_STREAM)}
    require(addresses and all(ipaddress.ip_address(address) in network for address in addresses),
            "private_dns_rejected")


def _unique_object(pairs: list[tuple]) -> dict:
    result: dict = {}
    for key, value in pairs:
        require(key not in result, "operator_token_rejected")
        result[key] = value
    return result


@dataclass(repr=False)
class OperatorCredential:
    token: str = field(repr=False)
    expires_at: int

    @classmethod
    def from_environment(cls, config: JobConfig) -> OperatorCredential:
        token = os.environ.get("AIFLUX_SQL_OPERATOR_TOKEN", "")
        expiry = os.environ.get("AIFLUX_SQL_OPERATOR_TOKEN_EXPIRES_AT", "")
        require(expiry.isascii() and expiry.isdigit(), "operator_token_rejected")
        require(0 < len(token) <= 32768 and len(token.split(".")) == 3, "operator_token_rejected")
        payload = token.split(".")[1]
        claims = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4),
                                             altchars=b"-_", validate=True),
                            object_pairs_hook=_unique_object)
        require(isinstance(claims, dict), "operator_token_rejected")
        require(claims.get("tid") == config.tenant_id and claims.get("oid") == config.operator_object_id,
                "operator_token_rejected")
        require(claims.get("aud") in ("https://database.windows.net/", "https://database.windows.net"),
                "operator_token_rejected")
        exp = claims.get("exp")
        require(type(exp) is int and 0 < int(expiry) <= exp, "operator_token_rejected")
        if "nbf" in claims:
            require(type(claims["nbf"]) is int and claims["nbf"] <= time.time(), "operator_token_rejected")
        credential = cls(token, int(expiry))
        credential.check_ttl(300)
        return credential

    def check_ttl(self, minimum: int = 60) -> None:
        require(self.expires_at - time.time() >= minimum, "operator_token_expiring")

    def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        require(scopes == (SQL_SCOPE,) and not kwargs.get("claims")
                and kwargs.get("tenant_id") is None, "operator_scope_rejected")
        self.check_ttl()
        return AccessToken(self.token, self.expires_at)


def operator_engine(url: URL, credential: TokenCredential, config: JobConfig) -> Engine:
    """Same ODBC access-token protocol as db.engine_for, without its shared cache.

    Set hide_parameters at construction, before any engine logging can occur.
    NullPool prevents pooled privileged sessions surviving a phase or failed REVERT.
    """
    engine = create_engine(url, hide_parameters=True, echo=False, poolclass=NullPool,
                           connect_args={"timeout": 30})

    @event.listens_for(engine, "before_cursor_execute")
    def label_statement(conn, cursor, statement, parameters, context, executemany):
        # Covers Alembic, reflection and ORM statements as well as explicit SQL.
        # Arguments deliberately never inspected, formatted or logged.
        context.aiflux_sql_stage = SQL_STAGE.get()
        print(json.dumps({"sql_stage": context.aiflux_sql_stage}), flush=True)

    @event.listens_for(engine, "handle_error")
    def label_error(context):
        stage = getattr(context.execution_context, "aiflux_sql_stage", SQL_STAGE.get())
        if context.sqlalchemy_exception is not None and stage in SQL_STAGES:
            context.sqlalchemy_exception.aiflux_sql_stage = stage

    @event.listens_for(engine, "do_connect")
    def provide_token(dialect: object, conn_rec: object, cargs: list, cparams: dict) -> None:
        validate_dns(config)
        token = credential.get_token(SQL_SCOPE).token.encode("utf-16-le")
        cargs[0] = cargs[0].replace(";Trusted_Connection=Yes", "")
        cparams["attrs_before"] = {1256: struct.pack(f"<I{len(token)}s", len(token), token)}

    return engine


def verify_operator(connection: Connection, config: JobConfig) -> None:
    row = sql(connection, "operator_identity",
        "SELECT DB_NAME(), USER_NAME(), HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CONTROL')"
    ).one()
    require(row[0] == config.sql_database, "database_mismatch")
    require(row[1] == "dbo" and row[2] == 1, "operator_privilege_rejected")


def migration_config() -> Config:
    config = Config(str(ROOT / "services/control-plane/alembic.ini"))
    # The existing env.py accepts this connection; no engine_for monkeypatch.
    return config


def apply_migrations(engine: Engine, credential: OperatorCredential) -> None:
    credential.check_ttl(300)
    SQL_STAGE.set("migration_statement")
    config = migration_config()
    # Alembic owns its transaction. Do not wrap all phases in one giant transaction.
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def verify_schema(connection: Connection) -> None:
    SQL_STAGE.set("schema_statement")
    heads = set(ScriptDirectory.from_config(migration_config()).get_heads())
    require(heads and set(MigrationContext.configure(connection).get_current_heads()) == heads,
            "migration_head_mismatch")
    schema = inspect(connection)
    for table in Base.metadata.sorted_tables:
        require(schema.has_table(table.name), "schema_mismatch")
        actual = {column["name"] for column in schema.get_columns(table.name)}
        require(set(table.columns.keys()) <= actual, "schema_mismatch")
    require(any(fk["constrained_columns"] == ["organization_id"]
                and fk["referred_table"] == "organizations"
                for fk in schema.get_foreign_keys("portal_users")), "schema_mismatch")


def audit_runtime(connection: Connection, client_id: str) -> bool:
    # Match bootstrap-identities.sql CONVERT(binary(16), CONVERT(uniqueidentifier,...)).
    sid = UUID(client_id).bytes_le
    rows = sql(connection, "runtime_principal",
        "SELECT principal_id, name, sid, type, authentication_type_desc "
        "FROM sys.database_principals WHERE name = :name OR sid = :sid"
    , {"name": "aiflux-api", "sid": sid}).all()
    if not rows:
        return False
    require(len(rows) == 1 and rows[0][1] == "aiflux-api" and bytes(rows[0][2]) == sid
            and rows[0][3] == "E" and rows[0][4] == "EXTERNAL", "runtime_identity_rejected")
    principal = rows[0][0]
    # Reject ALL explicit roles, including nested/custom paths to db_owner/ddladmin.
    roles = sql(connection, "runtime_roles",
        "SELECT role_principal_id FROM sys.database_role_members WHERE member_principal_id=:id"
    , {"id": principal}).all()
    require(not roles, "runtime_roles_rejected")
    ownership = sql(connection, "runtime_ownership",
        "SELECT principal_id FROM sys.schemas WHERE principal_id=:id UNION ALL "
        "SELECT principal_id FROM sys.objects WHERE principal_id=:id UNION ALL "
        "SELECT owning_principal_id FROM sys.database_principals WHERE owning_principal_id=:id"
    , {"id": principal}).all()
    require(not ownership, "runtime_ownership_rejected")
    permissions = sql(connection, "runtime_permissions",
        "SELECT class, major_id, minor_id, permission_name, state "
        "FROM sys.database_permissions WHERE grantee_principal_id=:id"
    , {"id": principal}).all()
    dbo = sql(connection, "dbo_schema_id", "SELECT SCHEMA_ID('dbo')").scalar_one()
    for kind, major, minor, permission, state in permissions:
        # DENYs cannot elevate; existing GRANT WITH GRANT OPTION is never accepted.
        allowed = state == "D" or (state == "G" and minor == 0 and (
            (kind == 3 and major == dbo and permission in {"SELECT", "INSERT", "UPDATE", "DELETE"})
            or (kind == 0 and major == 0 and permission == "CONNECT")))
        require(allowed, "runtime_permissions_rejected")
    return True


def provision_runtime(connection: Connection, client_id: str) -> None:
    sql(connection, "runtime_xact_abort", "SET XACT_ABORT ON")
    if not audit_runtime(connection, client_id):
        # Only a UUID-derived hex literal is interpolated. The identifier is fixed.
        sid = UUID(client_id).bytes_le.hex()
        sql(connection, "runtime_create_user", f"CREATE USER [aiflux-api] WITH SID = 0x{sid}, TYPE = E")
    sql(connection, "runtime_grant_dml", "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO [aiflux-api]")
    sql(connection, "runtime_deny_database_ddl",
        "DENY CREATE TABLE, CREATE VIEW, CREATE PROCEDURE, CREATE FUNCTION, CREATE SCHEMA, "
        "CREATE TYPE, CREATE SYNONYM, ALTER ANY USER, ALTER ANY ROLE, "
        "TAKE OWNERSHIP TO [aiflux-api]"
    )
    # CREATE SEQUENCE is a SCHEMA permission, unlike database CREATE TYPE.
    # https://learn.microsoft.com/sql/t-sql/statements/create-sequence-transact-sql#permissions
    sql(connection, "runtime_deny_schema_sequence",
        "DENY CREATE SEQUENCE ON SCHEMA::dbo TO [aiflux-api]")
    sql(connection, "runtime_deny_schema_alter", "DENY ALTER ON SCHEMA::dbo TO [aiflux-api]")
    audit_runtime(connection, client_id)
    # Check effective permissions too (e.g. an unexpectedly privileged public role).
    try:
        sql(connection, "runtime_execute_as", "EXECUTE AS USER = 'aiflux-api'")
        verify_effective_permissions(connection)
    finally:
        sql(connection, "runtime_revert", "REVERT")


def verify_effective_permissions(connection: Connection) -> None:
    dml = sql(connection, "runtime_effective_dml",
        "SELECT HAS_PERMS_BY_NAME('dbo','SCHEMA','SELECT'), "
        "HAS_PERMS_BY_NAME('dbo','SCHEMA','INSERT'), "
        "HAS_PERMS_BY_NAME('dbo','SCHEMA','UPDATE'), "
        "HAS_PERMS_BY_NAME('dbo','SCHEMA','DELETE')"
    ).one()
    require(all(value == 1 for value in dml), "runtime_effective_permissions_rejected")
    permissions = sql(connection, "runtime_effective_database",
        "SELECT permission_name FROM sys.fn_my_permissions(NULL, 'DATABASE')"
    ).scalars().all()
    require(set(permissions) <= {"CONNECT", "SELECT", "INSERT", "UPDATE", "DELETE",
                                "VIEW ANY COLUMN ENCRYPTION KEY DEFINITION",
                                "VIEW ANY COLUMN MASTER KEY DEFINITION"},
            "runtime_effective_permissions_rejected")
    # Database-level checks alone miss public/custom object-level grants.
    # Ignore system schemas/objects, whose metadata visibility SQL controls.
    elevated = sql(connection, "runtime_effective_objects",
        "SELECT p.permission_name FROM sys.schemas s CROSS APPLY "
        "sys.fn_my_permissions(QUOTENAME(s.name), 'SCHEMA') p "
        "WHERE s.name NOT IN ('sys','INFORMATION_SCHEMA') "
        "AND p.permission_name NOT IN ('SELECT','INSERT','UPDATE','DELETE') "
        "UNION ALL SELECT p.permission_name FROM sys.objects o CROSS APPLY "
        "sys.fn_my_permissions(QUOTENAME(SCHEMA_NAME(o.schema_id)) + '.' + "
        "QUOTENAME(o.name), 'OBJECT') p WHERE o.is_ms_shipped=0 "
        "AND p.permission_name NOT IN ('SELECT','INSERT','UPDATE','DELETE')"
    ).all()
    require(not elevated, "runtime_effective_permissions_rejected")


def driver_codes(error: Exception) -> tuple[str | None, list[int]]:
    """Extract codes only, never return SQL/parameters or arbitrary driver text."""
    # Explicit causes preserve driver evidence when a fail-closed JobError wraps
    # an unexpected result. Never traverse implicit contexts containing seed data.
    for _ in range(4):
        if isinstance(error, JobError) and error.__cause__ is not None:
            error = error.__cause__
        else:
            break
    original = getattr(error, "orig", error)
    args = getattr(original, "args", ())
    state = (args[0] if args and type(args[0]) is str
             and re.fullmatch(r"[0-9A-Z]{5}", args[0]) else None)
    numbers = sorted({int(number) for arg in args if type(arg) is str
                      for number in re.findall(r"\((\d{1,6})\)", arg)})
    return state, numbers


def verify_runtime_mi(url: URL, config: JobConfig, checks: list[str]) -> None:
    """Real MI authentication and rollback-only CRUD, with real permission denials."""
    from azure.identity import ManagedIdentityCredential

    credential = ManagedIdentityCredential(client_id=config.api_client_id)
    engine = operator_engine(url, credential, config)
    probe_id = str(uuid4())
    try:
        with engine.connect() as connection:
            row = sql(connection, "runtime_mi_identity",
                      "SELECT DB_NAME(), USER_NAME(), "
                      "HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CONTROL'), SCHEMA_ID('dbo')").one()
            require(row[0] == config.sql_database and row[1] == "aiflux-api"
                    and row[2] == 0 and row[3] is not None, "runtime_mi_identity_rejected")
            verify_effective_permissions(connection)
        checks.append("api_managed_identity_authenticated")
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                params = {"id": probe_id, "name": "private-runner-rollback-probe", "tenant": probe_id}
                sql(connection, "runtime_mi_insert",
                    "INSERT INTO dbo.organizations (id,name,tenant_id,enabled) "
                    "VALUES (:id,:name,:tenant,1)", params)
                require(sql(connection, "runtime_mi_select",
                            "SELECT COUNT(*) FROM dbo.organizations WHERE id=:id",
                            {"id": probe_id}).scalar_one() == 1, "runtime_mi_dml_rejected")
                require(sql(connection, "runtime_mi_update",
                            "UPDATE dbo.organizations SET name=:name WHERE id=:id",
                            {"id": probe_id, "name": "private-runner-updated"}).rowcount == 1,
                        "runtime_mi_dml_rejected")
                require(sql(connection, "runtime_mi_delete",
                            "DELETE FROM dbo.organizations WHERE id=:id",
                            {"id": probe_id}).rowcount == 1, "runtime_mi_dml_rejected")
            finally:
                transaction.rollback()
        with engine.connect() as connection:
            require(sql(connection, "runtime_mi_rollback",
                        "SELECT COUNT(*) FROM dbo.organizations WHERE id=:id",
                        {"id": probe_id}).scalar_one() == 0, "runtime_mi_dml_rejected")
        checks.append("api_managed_identity_dml_verified")
        # Separate rollback-only transactions; even an unexpected success cannot
        # persist a new object. Syntax error 102 is NEVER accepted as SQL_DENY_DDL.
        suffix = uuid4().hex
        for operation, statement in (
            ("create_table", f"CREATE TABLE dbo.[aiflux_probe_{suffix}] (id int)"),
            ("create_sequence", f"CREATE SEQUENCE dbo.[aiflux_probe_{suffix}] AS bigint START WITH 1"),
            ("create_type", f"CREATE TYPE dbo.[aiflux_probe_{suffix}] FROM int"),
        ):
            denied = False
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    sql(connection, "runtime_mi_" + operation, statement)
                except Exception as error:
                    state, numbers = driver_codes(error)
                    if not (state == "42000" and bool(numbers)
                            and set(numbers) <= {229, 262, 2760, 15247}):
                        failure = JobError("runtime_mi_ddl_not_denied")
                        failure.aiflux_sql_stage = "runtime_mi_" + operation
                        raise failure from error
                    denied = True
                    print(json.dumps({"runtime_probe": "SQL_DENY_DDL", "operation": operation,
                                      "sqlstate": state, "native_codes": numbers}), flush=True)
                finally:
                    transaction.rollback()
            require(denied, "runtime_mi_ddl_not_denied")
        checks.append("api_managed_identity_ddl_denied")
    finally:
        engine.dispose()
        credential.close()


def seed_settings(config: JobConfig) -> Settings:
    raw = os.environ.get("AIFLUX_PORTAL_SEED_USERS", "")
    users = parse_seed_users(raw)
    require({user.username: user.role for user in users} == EXPECTED_ACCOUNTS and len(users) == 4,
            "seed_configuration_rejected")
    # Use Settings and the established parser/seeder, without reading .env or
    # requiring a signing key for this one-shot offline password-hashing task.
    return Settings(_env_file=None, home_tenant_id=config.tenant_id, portal_seed_users=raw)


def seed_accounts(engine: Engine, settings: Settings) -> None:
    SQL_STAGE.set("seed_statement")
    # seed_portal_users calls Session.commit(). Bind it to an external transaction
    # without propagating commit, so verification failure rolls back the seed phase.
    with engine.begin() as connection:
        with Session(bind=connection, join_transaction_mode="rollback_only") as session:
            seed_portal_users(session, settings)
            for seed in parse_seed_users(settings.portal_seed_users):
                users = session.scalars(select(PortalUser).where(
                    PortalUser.username == seed.username)).all()
                require(len(users) == 1, "seed_verification_rejected")
                user = users[0]
                org = account_organization(session, user, settings)
                tenant = (settings.home_tenant_id if seed.role == "ids_admin" else
                          str(uuid5(UUID(settings.home_tenant_id), "sql-portal:" + seed.username)))
                require(org is not None and user.role == seed.role and user.tenant_id == tenant
                        and user.organization_name == org.name
                        and verify_password(seed.password, user.password_hash), "seed_verification_rejected")


def run_job(config: JobConfig, checks: list[str]) -> None:
    config.validate()
    url = validate_url(os.environ.get("AIFLUX_DATABASE_URL", ""), config)
    credential = OperatorCredential.from_environment(config)
    settings = seed_settings(config) if config.seed else None
    checks.append("configuration_validated")
    validate_dns(config)
    checks.append("private_dns_validated")
    import pyodbc

    require(DRIVER in pyodbc.drivers(), "odbc18_unavailable")
    checks.append("odbc18_available")
    engine = operator_engine(url, credential, config)
    try:
        with engine.connect() as connection:
            verify_operator(connection, config)
            # Detect identity ambiguity/elevation BEFORE migrations, even on probe.
            audit_runtime(connection, config.api_client_id)
        checks.append("operator_database_verified")
        if config.mode == "probe":
            return
        apply_migrations(engine, credential)
        with engine.connect() as connection:
            verify_schema(connection)
        checks.append("migration_head_schema_verified")
        credential.check_ttl()
        with engine.begin() as connection:
            verify_operator(connection, config)
            provision_runtime(connection, config.api_client_id)
        checks.append("runtime_dml_identity_verified")
        if settings is not None:
            credential.check_ttl(300)
            seed_accounts(engine, settings)
            checks.append("four_portal_accounts_verified")
        if config.verify_api_mi:
            verify_runtime_mi(url, config, checks)
    finally:
        engine.dispose()


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise JobError("arguments_rejected")


def main(argv: list[str] | None = None) -> int:
    # Alembic/SQL/Azure diagnostics can include SQL parameters, URLs or tokens.
    # This dedicated process deliberately emits only the fixed status document.
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    checks: list[str] = []
    stage = "arguments_rejected"
    try:
        parser = SafeParser(description=__doc__, allow_abbrev=False)
        parser.add_argument("mode", choices=("probe", "migrate"))
        for name in ("sql-host", "sql-database", "tenant-id", "operator-object-id",
                     "api-client-id", "private-cidr"):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--seed", action="store_true")
        parser.add_argument("--verify-api-mi", action="store_true")
        config = JobConfig(**vars(parser.parse_args(argv)))
        stage = "job_failed"
        run_job(config, checks)
    except Exception as error:
        # Never stringify exceptions (including parser/Pydantic/ODBC/SQLAlchemy).
        # Check labels identify the last completed phase, not exception contents.
        if (isinstance(error, JobError) and len(error.args) == 1
                and type(error.args[0]) is str and error.args[0] in ERROR_CODES):
            stage = error.args[0]
        print(json.dumps({"status": "failed", "code": stage, "checks": checks}))
        return 1
    print(json.dumps({"status": "ok", "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())