"""DBA-only PostgreSQL bootstrap. No ARM writes, password seeding, or runtime DDL grants.

Validate the immutable release offline first. Network changes are a separate,
reviewed Terraform operation. Live writes require both a mode and --execute.
"""

import argparse
import ast
import base64
import hashlib
import importlib
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from azure.identity import AzureCliCredential
from sqlalchemy import URL, create_engine, event, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
RELEASE = "local-20261023t074801z-939ccecd80d1"
INGESTION = {
    "team_subscriptions": ("SELECT",),
    "model_prices": ("SELECT",),
    "usage_records": ("SELECT", "INSERT", "UPDATE"),
    "ingestion_state": ("SELECT", "INSERT", "UPDATE"),
    "safety_events": ("SELECT", "INSERT"),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load_release(directory):
    directory = Path(directory).resolve()
    context = directory / "context"
    manifest = json.loads((directory / "source-manifest.json").read_text())
    require(manifest["tag"] == RELEASE, "Only the reviewed release is supported")
    paths = set()
    for entry in manifest["entries"]:
        relative = entry["path"]
        source = (context / relative).resolve()
        require(source.is_relative_to(context), "Unsafe manifest path")
        require(relative not in paths, "Duplicate manifest path")
        paths.add(relative)
        data = source.read_bytes()
        require(hashlib.sha256(data).hexdigest() == entry["sha256"], "Packaged source hash mismatch")
        if source.suffix == ".py":
            ast.parse(data, filename=relative)
    root = context / "services/control-plane"
    # Reject injected/unmanifested modules, especially the legacy duplicate 0003.
    for folder in (root / "src", root / "migrations"):
        for source in folder.rglob("*.py"):
            require(source.relative_to(context).as_posix() in paths, "Unmanifested Python source")
    source_root = root / "src"
    for name, module in list(sys.modules.items()):
        if name == "aiflux" or name.startswith("aiflux."):
            location = getattr(module, "__file__", None)
            require(location and Path(location).resolve().is_relative_to(source_root),
                    "Start a fresh process; aiflux was imported outside the reviewed release")
    sys.path.insert(0, str(source_root))
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("prepend_sys_path", str(source_root))
    graph = ScriptDirectory.from_config(config)
    revisions = list(graph.walk_revisions())
    require(graph.get_heads() == ["0003"] and
            sorted(item.revision for item in revisions) == ["0001", "0002", "0003"],
            "Unexpected packaged migration graph")
    models = importlib.import_module("aiflux.models")
    return config, models.Base.metadata, len(paths)


def migrate(config, connection):
    # Explicit settings bypass .env / local-auth validation, NOT identity checks on
    # live connections. There is deliberately no bootstrap/seeding import here.
    settings_module = importlib.import_module("aiflux.config")
    original = settings_module.get_settings
    settings_module.get_settings = lambda: settings_module.Settings(
        _env_file=None, environment="testing", database_url="postgresql://schema-only",
        local_auth_enabled=False,
    )
    config.attributes["connection"] = connection
    try:
        command.upgrade(config, "0003")
    finally:
        config.attributes.pop("connection", None)
        settings_module.get_settings = original


def validate_offline(config, metadata):
    # PostgreSQL compilation complements (but does not pretend to replace) a
    # PostgreSQL integration run. Legacy create_all migrations need a live bind.
    dialect = postgresql.dialect()
    for table in metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=dialect))
        for index in table.indexes:
            str(CreateIndex(index).compile(dialect=dialect))
    with tempfile.TemporaryDirectory(prefix="aiflux-pg-bootstrap-") as temp:
        engine = create_engine(URL.create("sqlite", database=str(Path(temp) / "schema.db")))
        try:
            with engine.begin() as connection:
                migrate(config, connection)
                migrate(config, connection)
                verify_schema(connection, metadata)
        finally:
            engine.dispose()


def cli_read(args, cli_python=None):
    if cli_python:
        executable = Path(cli_python).resolve()
        prefix = [str(executable), "-X", "utf8", "-IBm", "azure.cli"]
        # AzureCliCredential itself discovers az.cmd via PATH. Process-local only.
        os.environ["PATH"] = str(executable.parent / "wbin") + os.pathsep + os.environ.get("PATH", "")
    else:
        executable = shutil.which("az")
        require(executable, "Azure CLI not found")
        prefix = [executable]
    result = subprocess.run(prefix + args + ["--only-show-errors", "-o", "json"],
                            capture_output=True, text=True, encoding="utf-8", check=False)
    require(result.returncode == 0, "Azure CLI read failed; inspect identity/network outside this script")
    return json.loads(result.stdout)


def audit_admin(args):
    account = cli_read(["account", "show"], args.cli_python)
    require(account["id"].lower() == args.subscription.lower() and
            account["tenantId"].lower() == args.tenant.lower() and
            account["user"]["type"].lower() == "user", "Unexpected CLI account/tenant/subscription")
    user = cli_read(["ad", "signed-in-user", "show"], args.cli_python)
    require(user["id"].lower() == args.admin_object_id.lower(), "Signed-in user is not the approved DBA")
    resource = (f"https://management.azure.com/subscriptions/{args.subscription}"
                f"/resourceGroups/{args.resource_group}/providers/Microsoft.DBforPostgreSQL"
                f"/flexibleServers/{args.server}")
    server = cli_read(["rest", "--method", "get", "--url", resource + "?api-version=2024-08-01"],
                      args.cli_python)
    admins = cli_read(["rest", "--method", "get", "--url",
                       resource + "/administrators?api-version=2024-08-01"], args.cli_python)
    matches = [item["properties"] for item in admins["value"]
               if item["properties"]["objectId"].lower() == args.admin_object_id.lower()]
    require(len(matches) == 1, "Approved DBA is not a configured PostgreSQL administrator")
    admin = matches[0]
    require(admin["tenantId"].lower() == args.tenant.lower() and
            admin["principalType"].lower() == "user", "PostgreSQL DBA tenant/type mismatch")
    properties = server["properties"]
    require(properties["authConfig"]["activeDirectoryAuth"] == "Enabled" and
            properties["authConfig"]["passwordAuth"] == "Disabled", "Expected Entra-only PostgreSQL")
    audit = {"admin_object_id": admin["objectId"], "admin_login": admin["principalName"],
             "tenant": admin["tenantId"], "subscription": account["id"],
             "fqdn": properties["fullyQualifiedDomainName"],
             "public_access": properties["network"]["publicNetworkAccess"]}
    firewall = cli_read(["rest", "--method", "get", "--url",
                         resource + "/firewallRules?api-version=2024-08-01"], args.cli_python)
    audit["firewall_rules"] = [
        {"name": item["name"], "start": item["properties"]["startIpAddress"],
         "end": item["properties"]["endIpAddress"]} for item in firewall["value"]
    ]
    print(json.dumps({"admin_audit": audit}), flush=True)
    return audit


def verify_network(audit, approved_ip):
    if audit["public_access"] == "Disabled":
        return  # Private path still needs to be reachable; this makes no network change.
    require(audit["public_access"] == "Enabled" and approved_ip,
            "Public PostgreSQL requires an explicit approved bootstrap IPv4")
    address = ipaddress.IPv4Address(approved_ip)
    require(address.is_global, "Bootstrap IPv4 must be a public unicast address")
    rules = audit["firewall_rules"]
    require(len(rules) == 1 and rules[0]["start"] == str(address) == rules[0]["end"],
            "Public firewall is not exclusively the approved single IPv4; no database writes allowed")


def check_token_identity(token, object_id, tenant):
    # The token comes directly from AzureCliCredential, not from user input.
    # Decode only to fail closed on an unintended CLI identity. Never log it.
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    require(claims.get("oid", "").lower() == object_id.lower() and
            claims.get("tid", "").lower() == tenant.lower(), "Token identity differs from audited DBA")


def admin_engine(audit, database, credential):
    url = URL.create("postgresql+psycopg", username=audit["admin_login"], host=audit["fqdn"],
                     port=5432, database=database, query={"sslmode": "require", "connect_timeout": "15"})
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True)

    @event.listens_for(engine, "do_connect")
    def token_for_connection(dialect, record, positional, parameters):
        token = credential.get_token(SCOPE).token
        check_token_identity(token, audit["admin_object_id"], audit["tenant"])
        parameters["password"] = token

    return engine


def principals(connection):
    rows = connection.execute(text("SELECT * FROM pg_catalog.pgaadauth_list_principals(false)"))
    normalized = []
    for row in rows.mappings():
        item = {key.lower(): value for key, value in row.items()}
        # Live Azure servers return rolname; documentation uses rolename.
        # Normalize only the field label, never the identity values.
        if "rolname" in item:
            require("rolename" not in item or item["rolename"] == item["rolname"],
                    "Conflicting Entra role-name columns")
            item["rolename"] = item.pop("rolname")
        require({"rolename", "objectid", "principaltype", "tenantid", "isadmin"} <= item.keys(),
                "Unexpected Entra principal-list columns")
        normalized.append(item)
    return normalized


def check_mapping(rows, name, object_id, tenant, admin=False):
    matches = [row for row in rows if row["rolename"] == name]
    require(len(matches) == 1, "Missing/ambiguous Entra role mapping")
    row = matches[0]
    require(row["objectid"].lower() == object_id.lower() and
            row["principaltype"].lower() == ("user" if admin else "service") and
            row["tenantid"].lower() == tenant.lower() and bool(row["isadmin"]) == admin,
            "Existing Entra role OID/type/tenant/admin mismatch; refusing takeover")


def verify_session_admin(connection, audit):
    identity = connection.execute(text("SELECT session_user, current_user")).one()
    require(identity[0] == audit["admin_login"] and identity[1] == audit["admin_login"],
            "Database session is not the audited DBA")


def verify_connected_admin(connection, audit):
    verify_session_admin(connection, audit)
    check_mapping(principals(connection), audit["admin_login"], audit["admin_object_id"],
                  audit["tenant"], admin=True)


def verify_schema(connection, metadata):
    schema = "public" if connection.dialect.name == "postgresql" else None
    actual = set(inspect(connection).get_table_names(schema=schema))
    require(actual == set(metadata.tables) | {"alembic_version"},
            "Unexpected/missing application tables; review schema before grants")
    require(connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == ["0003"],
            "Database must be at reviewed revision 0003")
    if schema:
        require(not inspect(connection).get_sequence_names(schema=schema),
                "Unexpected sequences require an explicit privilege review")


def check_runtime_role(connection, rows, name, object_id, tenant):
    flags = connection.execute(text(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolcanlogin "
        "FROM pg_catalog.pg_roles WHERE rolname = :name"), {"name": name}).first()
    if flags is None:
        require(not any(row["rolename"] == name for row in rows), "Inconsistent Entra mapping")
        return False
    check_mapping(rows, name, object_id, tenant)
    require(not any(flags[:5]) and flags[5], "Existing runtime role has unsafe attributes")
    require(not connection.execute(text(
        "SELECT 1 FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r "
        "ON r.oid = m.member WHERE r.rolname = :name"), {"name": name}).first(),
        "Runtime role has inherited memberships; manual privilege review required")
    require(not connection.execute(text(
        "SELECT 1 FROM pg_catalog.pg_shdepend d JOIN pg_catalog.pg_roles r "
        "ON d.refobjid = r.oid WHERE r.rolname = :name AND d.deptype = 'o'"),
        {"name": name}).first(), "Runtime role owns objects; manual privilege review required")
    return True


def create_runtime_principal(connection, name, oid, tenant):
    # Azure versions expose either the documented five-argument form or a
    # seven-argument form. Never rely on optional defaults or skip validation.
    seven, five = connection.execute(text(
        "SELECT to_regprocedure('pg_catalog.pgaadauth_create_principal_with_oid"
        "(text,text,text,boolean,boolean,text,boolean)') IS NOT NULL, "
        "to_regprocedure('pg_catalog.pgaadauth_create_principal_with_oid"
        "(text,text,text,boolean,boolean)') IS NOT NULL")).one()
    require(seven or five, "Unsupported Entra principal-creation function signature in postgres")
    arguments = "CAST(:name AS text), CAST(:oid AS text), 'service', false, false"
    parameters = {"name": name, "oid": oid}
    if seven:
        arguments += ", CAST(:tenant AS text), false"
        parameters["tenant"] = tenant
    connection.execute(text(
        f"SELECT pg_catalog.pgaadauth_create_principal_with_oid({arguments})"), parameters)


def grant_runtime(connection, metadata, tenant, roles, *, identity_connection):
    require(set(roles) == {"api", "ingestion"}, "Only API/ingestion roles may be bootstrapped")
    require(len({value[0] for value in roles.values()}) == 2 and
            len({value[1].lower() for value in roles.values()}) == 2, "Runtime identities must be distinct")
    verify_schema(connection, metadata)
    rows = principals(identity_connection)
    existing = {}
    # Audit BOTH mappings before any write. Never relabel, rename, drop or adopt a role.
    for kind, (name, oid) in roles.items():
        require(name and len(name.encode()) <= 63 and not name.lower().startswith(("pg_", "azure_")),
                "Invalid runtime role name")
        UUID(oid)
        existing[kind] = check_runtime_role(identity_connection, rows, name, oid, tenant)
    for kind, (name, oid) in roles.items():
        if not existing[kind]:
            create_runtime_principal(identity_connection, name, oid, tenant)
            check_runtime_role(identity_connection, principals(identity_connection), name, oid, tenant)
    # Roles are cluster-wide, but Azure's mapping functions exist only in
    # postgres. Commit there BEFORE the application database can grant to them.
    # This is deliberately not represented as a cross-database atomic operation:
    # if later grants fail, verified nonadmin roles may remain for a safe retry.
    identity_connection.commit()
    rows = principals(identity_connection)
    for name, oid in roles.values():
        require(check_runtime_role(connection, rows, name, oid, tenant),
                "Committed runtime role is not visible in the application database")
    quote = connection.dialect.identifier_preparer.quote_identifier
    database = quote(connection.execute(text("SELECT current_database()")).scalar_one())
    connection.execute(text(f"REVOKE CREATE, TEMPORARY ON DATABASE {database} FROM PUBLIC"))
    connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    for kind, (name, oid) in roles.items():
        role = quote(name)
        connection.execute(text(f"REVOKE ALL PRIVILEGES ON DATABASE {database} FROM {role}"))
        connection.execute(text(f"GRANT CONNECT ON DATABASE {database} TO {role}"))
        connection.execute(text(f"REVOKE ALL PRIVILEGES ON SCHEMA public FROM {role}"))
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        for table in sorted(set(metadata.tables) | {"alembic_version"}):
            target = f"public.{quote(table)}"
            connection.execute(text(f"REVOKE ALL PRIVILEGES ON TABLE {target} FROM PUBLIC"))
            connection.execute(text(f"REVOKE ALL PRIVILEGES ON TABLE {target} FROM {role}"))
            permissions = (("SELECT", "INSERT", "UPDATE", "DELETE") if kind == "api" and
                           table in metadata.tables else INGESTION.get(table, ()) if kind == "ingestion" else ())
            if permissions:
                connection.execute(text(f"GRANT {', '.join(permissions)} ON TABLE {target} TO {role}"))
        # PostgreSQL has no DENY: check effective privileges after PUBLIC and direct
        # grants are constrained. No ALL TABLES/default/future/sequence/DDL grants.
        require(not connection.execute(text(
            "SELECT has_schema_privilege(:role, 'public', 'CREATE') OR "
            "has_database_privilege(:role, current_database(), 'CREATE') OR "
            "has_database_privilege(:role, current_database(), 'TEMP')"), {"role": name}).scalar_one(),
            "Runtime role retains effective DDL privileges")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=["validate", "audit", "schema", "principals"])
    result.add_argument("--release-dir", required=True, type=Path)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--subscription")
    result.add_argument("--tenant")
    result.add_argument("--resource-group")
    result.add_argument("--server")
    result.add_argument("--database", default="turnstile")
    result.add_argument("--admin-object-id")
    result.add_argument("--approved-public-ip", help="Live writes fail if public firewall has any other rule")
    result.add_argument("--cli-python", type=Path)
    for kind in ("api", "ingestion"):
        result.add_argument(f"--{kind}-name")
        result.add_argument(f"--{kind}-object-id")
    return result


def safe_failure(error):
    """Classify driver failures without emitting raw messages, SQL, URLs or tokens."""
    original = getattr(error, "orig", error)
    message = str(original).lower()
    categories = [
        ("timeout", ("timeout", "timed out")),
        ("network_unreachable", ("unreachable", "refused", "could not translate host", "getaddrinfo")),
        ("firewall_rejected", ("no pg_hba.conf entry", "not allowed to access")),
        ("token_audience", ("audience",)),
        ("authentication_rejected", ("authentication failed", "access token", "oauth", "principal")),
        ("tls_failure", ("certificate", "ssl", "tls")),
        ("permission_denied", ("permission denied",)),
    ]
    category = next((label for label, terms in categories if any(term in message for term in terms)),
                    "unclassified")
    state = getattr(original, "sqlstate", None)
    if state == "42883":
        category = "undefined_function"
    return {"category": category, "sqlstate": state if state and len(state) == 5 and state.isalnum() else None}


def main(argv=None):
    args = parser().parse_args(argv)
    config, metadata, hashed = load_release(args.release_dir)
    validate_offline(config, metadata)
    print(json.dumps({"release": RELEASE, "hashed_files": hashed, "head": "0003",
                      "sqlite_upgrade_and_repeat": "passed", "postgresql_ddl_compile": "passed",
                      "tables": sorted(metadata.tables), "seeding": "not_requested"}), flush=True)
    if args.mode == "validate":
        return
    require(all((args.subscription, args.tenant, args.resource_group, args.server, args.admin_object_id)),
            "Live audit requires explicit subscription, tenant, resource group, server and approved DBA OID")
    if args.mode in ("schema", "principals"):
        require(args.execute, "Live database writes require --execute")
    audit = audit_admin(args)
    if args.mode == "audit":
        return
    verify_network(audit, args.approved_public_ip)
    require(args.database != "postgres", "Application migrations must not target the identity database postgres")
    if args.mode == "principals":
        for kind in ("api", "ingestion"):
            name, oid = getattr(args, f"{kind}_name"), getattr(args, f"{kind}_object_id")
            require(name and oid and UUID(oid) != UUID(args.admin_object_id) and name != audit["admin_login"],
                    "Runtime identities must be explicitly provided and distinct from the DBA")
    with AzureCliCredential(tenant_id=args.tenant, process_timeout=60) as credential:
        engine = admin_engine(audit, args.database, credential)
        identity_engine = admin_engine(audit, "postgres", credential)
        try:
            with identity_engine.connect() as identity_connection, engine.begin() as connection:
                verify_connected_admin(identity_connection, audit)
                verify_session_admin(connection, audit)
                print(json.dumps({"database_admin_session_verified": True}), flush=True)
                connection.execute(text("SET LOCAL search_path TO public, pg_catalog"))
                connection.execute(text("SET LOCAL lock_timeout = '15s'"))
                connection.execute(text("SET LOCAL statement_timeout = '120s'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(184863, 5432)"))
                if args.mode == "schema":
                    migrate(config, connection)
                    migrate(config, connection)
                    verify_schema(connection, metadata)
                else:
                    grant_runtime(connection, metadata, args.tenant, {
                        kind: (getattr(args, f"{kind}_name"), getattr(args, f"{kind}_object_id"))
                        for kind in ("api", "ingestion")
                    }, identity_connection=identity_connection)
        finally:
            identity_engine.dispose()
            engine.dispose()
    print(json.dumps({"database_step": args.mode, "committed": True, "seeding": False,
                      "control_plane_grants": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Driver/CLI exceptions can carry credentials or SQL data. No raw exception,
        # traceback, connection URL, token, or local-login values in bootstrap logs.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "diagnostic": safe_failure(error),
                          "detail": str(error) if type(error) is RuntimeError else
                          "Step failed; inspect safely without logging credentials"}), file=sys.stderr)
        sys.exit(1)