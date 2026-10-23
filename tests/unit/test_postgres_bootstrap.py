import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("pg_bootstrap", ROOT / "infra/sql/bootstrap-postgres.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)

TENANT = "beb276ac-6e9f-498e-8e31-019ee666decd"
OID = "dd928302-055b-4516-9b8e-b06ae823057b"
API = "00000000-0000-0000-0000-000000000001"
INGESTION = "00000000-0000-0000-0000-000000000002"


def mapping(name="api", oid=API, kind="service", admin=0, tenant=TENANT):
    return {"rolename": name, "objectid": oid, "principaltype": kind,
            "tenantid": tenant, "isadmin": admin}


def test_existing_mapping_is_idempotent():
    bootstrap.check_mapping([mapping()], "api", API.upper(), TENANT)


@pytest.mark.parametrize("role_column", ["rolname", "rolename"])
def test_live_principal_columns_normalized_before_admin_verification(role_column):
    connection = Mock()
    raw = {role_column: "Puneet Devadiga", "principalType": "user", "objectId": OID,
           "tenantId": TENANT, "isMfa": 0, "isAdmin": 1}
    connection.execute.return_value.mappings.return_value = [raw]
    rows = bootstrap.principals(connection)
    assert rows[0]["rolename"] == "Puneet Devadiga"
    assert "rolname" not in rows[0]
    bootstrap.check_mapping(rows, "Puneet Devadiga", OID, TENANT, admin=True)


def test_principal_column_normalization_preserves_identity_rejection():
    connection = Mock()
    connection.execute.return_value.mappings.return_value = [{
        "rolname": "api", "principaltype": "service", "objectid": INGESTION,
        "tenantid": TENANT, "isadmin": 0, "ismfa": 0,
    }]
    with pytest.raises(RuntimeError, match="refusing takeover"):
        bootstrap.check_mapping(bootstrap.principals(connection), "api", API, TENANT)


@pytest.mark.parametrize("raw", [
    {"rolname": "api"},
    {**mapping(), "rolname": "different"},
])
def test_missing_or_conflicting_principal_columns_fail_closed(raw):
    connection = Mock()
    connection.execute.return_value.mappings.return_value = [raw]
    with pytest.raises(RuntimeError, match="columns"):
        bootstrap.principals(connection)


@pytest.mark.parametrize("overrides", [
    {"oid": INGESTION}, {"kind": "user"}, {"kind": "group"}, {"admin": 1},
    {"tenant": API},
])
def test_existing_mapping_refuses_takeover(overrides):
    with pytest.raises(RuntimeError, match="refusing takeover"):
        bootstrap.check_mapping([mapping(**overrides)], "api", API, TENANT)


def test_missing_or_duplicate_mapping_fails():
    for rows in ([], [mapping(), mapping()]):
        with pytest.raises(RuntimeError, match="ambiguous"):
            bootstrap.check_mapping(rows, "api", API, TENANT)


def test_token_identity_never_falls_back_to_other_identity():
    def token(oid):
        payload = base64.urlsafe_b64encode(json.dumps({"oid": oid, "tid": TENANT}).encode()).decode()
        return "header." + payload.rstrip("=") + ".signature"
    bootstrap.check_token_identity(token(OID), OID, TENANT)
    with pytest.raises(RuntimeError, match="Token identity"):
        bootstrap.check_token_identity(token(API), OID, TENANT)


def test_admin_connection_uses_explicit_credential_and_refreshes():
    payload = base64.urlsafe_b64encode(json.dumps({"oid": OID, "tid": TENANT}).encode()).decode()
    credential = Mock()
    credential.get_token.return_value = SimpleNamespace(token=f"head.{payload}.sig")
    audit = {"admin_login": "Puneet Devadiga", "fqdn": "server.postgres.database.azure.com",
             "admin_object_id": OID, "tenant": TENANT}
    engine = bootstrap.admin_engine(audit, "turnstile", credential)
    try:
        assert engine.url.username == "Puneet Devadiga"
        assert engine.url.password is None
        assert engine.url.query["sslmode"] == "require"
        for _ in range(2):
            parameters = {}
            for hook in engine.dialect.dispatch.do_connect:
                hook(engine.dialect, None, [], parameters)
            assert parameters["password"] == credential.get_token.return_value.token
        assert credential.get_token.call_count == 2
        credential.get_token.assert_called_with(bootstrap.SCOPE)
    finally:
        engine.dispose()


def test_unmapped_existing_postgres_role_is_never_adopted():
    connection = Mock()
    connection.execute.return_value.first.return_value = (False,) * 5 + (True,)
    with pytest.raises(RuntimeError, match="Missing/ambiguous"):
        bootstrap.check_runtime_role(connection, [], "api", API, TENANT)
    assert connection.execute.call_count == 1


@pytest.mark.parametrize("flags", [
    (True, False, False, False, False, True),
    (False, True, False, False, False, True),
    (False, False, True, False, False, True),
    (False, False, False, True, False, True),
    (False, False, False, False, True, True),
    (False,) * 6,
])
def test_elevated_or_nologin_runtime_role_rejected(flags):
    connection = Mock()
    connection.execute.return_value.first.return_value = flags
    with pytest.raises(RuntimeError, match="unsafe attributes"):
        bootstrap.check_runtime_role(connection, [mapping()], "api", API, TENANT)


def test_membership_or_ownership_requires_manual_review():
    for results in ([(False,) * 5 + (True,), (1,)],
                    [(False,) * 5 + (True,), None, (1,)]):
        connection = Mock()
        connection.execute.return_value.first.side_effect = results
        with pytest.raises(RuntimeError, match="manual privilege review"):
            bootstrap.check_runtime_role(connection, [mapping()], "api", API, TENANT)


def grant_connection():
    statements = []
    connection = Mock()
    connection.dialect = postgresql.dialect()
    def execute(statement, params=None):
        statements.append((str(statement), params))
        result = Mock()
        result.scalar_one.return_value = "turnstile" if "current_database()" in str(statement) and not params else False
        return result
    connection.execute.side_effect = execute
    return connection, statements


def test_grants_are_explicit_no_runtime_ddl_or_control_plane(monkeypatch):
    connection, statements = grant_connection()
    monkeypatch.setattr(bootstrap, "verify_schema", Mock())
    monkeypatch.setattr(bootstrap, "principals", Mock(return_value=[]))
    monkeypatch.setattr(bootstrap, "check_runtime_role", Mock(return_value=True))
    tables = set(bootstrap.INGESTION) | {"local_users", "organizations", "members"}
    bootstrap.grant_runtime(connection, SimpleNamespace(tables=tables), TENANT,
                            {"api": ("api", API), "ingestion": ("ingestion", INGESTION)},
                            identity_connection=connection)
    grants = [sql for sql, _ in statements if sql.startswith("GRANT")]
    assert 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public."local_users" TO "api"' in grants
    assert 'GRANT SELECT, INSERT, UPDATE ON TABLE public."usage_records" TO "ingestion"' in grants
    assert 'GRANT SELECT, INSERT ON TABLE public."safety_events" TO "ingestion"' in grants
    assert 'GRANT SELECT ON TABLE public."model_prices" TO "ingestion"' in grants
    assert not any("local_users" in sql and 'TO "ingestion"' in sql for sql in grants)
    assert not any("DELETE" in sql and 'TO "ingestion"' in sql for sql in grants)
    assert not any("alembic_version" in sql for sql in grants)
    assert not any(any(term in sql for term in ("CREATE", "ALL ", "SEQUENCE", "DEFAULT", "control-plane"))
                   for sql in grants)
    assert 'REVOKE CREATE, TEMPORARY ON DATABASE "turnstile" FROM PUBLIC' in [s for s, _ in statements]


def test_both_identities_audited_before_any_write(monkeypatch):
    connection, statements = grant_connection()
    monkeypatch.setattr(bootstrap, "verify_schema", Mock())
    monkeypatch.setattr(bootstrap, "principals", Mock(return_value=[]))
    monkeypatch.setattr(bootstrap, "check_runtime_role", Mock(side_effect=[False, RuntimeError("conflict")]))
    with pytest.raises(RuntimeError, match="conflict"):
        bootstrap.grant_runtime(connection, SimpleNamespace(tables=set()), TENANT,
                                {"api": ("api", API), "ingestion": ("ingestion", INGESTION)},
                                identity_connection=connection)
    assert statements == []


def test_new_principal_uses_oid_service_not_admin(monkeypatch):
    connection, statements = grant_connection()
    monkeypatch.setattr(bootstrap, "verify_schema", Mock())
    monkeypatch.setattr(bootstrap, "principals", Mock(return_value=[]))
    monkeypatch.setattr(bootstrap, "check_runtime_role", Mock(
        side_effect=[False, False, True, True, True, True]))
    monkeypatch.setattr(bootstrap, "create_runtime_principal", Mock())
    bootstrap.grant_runtime(connection, SimpleNamespace(tables=set()), TENANT,
                            {"api": ('api"quoted', API), "ingestion": ("ingestion", INGESTION)},
                            identity_connection=connection)
    assert bootstrap.create_runtime_principal.call_count == 2
    bootstrap.create_runtime_principal.assert_any_call(connection, 'api"quoted', API, TENANT)
    connection.commit.assert_called_once()
    assert any('TO "api""quoted"' in sql for sql, _ in statements)


def test_control_plane_and_duplicate_identities_rejected():
    for roles in ({"api": ("same", API), "ingestion": ("same", INGESTION)},
                  {"api": ("api", API), "ingestion": ("ingestion", API)},
                  {"api": ("api", API), "control-plane": ("cp", INGESTION)}):
        with pytest.raises(RuntimeError):
            bootstrap.grant_runtime(Mock(), SimpleNamespace(tables=set()), TENANT, roles,
                                    identity_connection=Mock())


def test_unexpected_schema_or_revision_rejected():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num TEXT)")
            connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('0002')")
            with pytest.raises(RuntimeError, match="revision"):
                bootstrap.verify_schema(connection, SimpleNamespace(tables=set()))
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='0003'")
            connection.exec_driver_sql("CREATE TABLE unrelated (id TEXT)")
            with pytest.raises(RuntimeError, match="application tables"):
                bootstrap.verify_schema(connection, SimpleNamespace(tables=set()))
    finally:
        engine.dispose()


def test_actual_reviewed_release_in_fresh_process_without_secrets():
    directory = ROOT / ".deployment/image-build" / bootstrap.RELEASE
    if not directory.exists():
        pytest.skip("Reviewed release is a local artifact, not committed")
    result = subprocess.run([sys.executable, str(ROOT / "infra/sql/bootstrap-postgres.py"),
                             "validate", "--release-dir", str(directory)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["hashed_files"] == 104
    assert output["head"] == "0003"
    assert output["seeding"] == "not_requested"


def test_manifest_tamper_rejected_before_import(tmp_path):
    context = tmp_path / "context"
    context.mkdir()
    (context / "bad.py").write_text("raise RuntimeError('must not execute')")
    (tmp_path / "source-manifest.json").write_text(json.dumps({
        "tag": bootstrap.RELEASE, "entries": [{"path": "bad.py", "sha256": "invalid"}],
    }))
    with pytest.raises(RuntimeError, match="hash mismatch"):
        bootstrap.load_release(tmp_path)


def test_live_audit_requires_matching_user_and_actual_arm_admin(monkeypatch):
    args = SimpleNamespace(subscription=API, tenant=TENANT, resource_group="rg", server="pg",
                           admin_object_id=OID, cli_python=None)
    server = {"properties": {"fullyQualifiedDomainName": "pg.postgres.database.azure.com",
              "authConfig": {"activeDirectoryAuth": "Enabled", "passwordAuth": "Disabled"},
              "network": {"publicNetworkAccess": "Disabled"}}}
    admins = {"value": [{"properties": {"objectId": OID, "tenantId": TENANT,
                                        "principalType": "User", "principalName": "Actual ARM Login"}}]}
    monkeypatch.setattr(bootstrap, "cli_read", Mock(side_effect=[
        {"id": API, "tenantId": TENANT, "user": {"type": "user"}}, {"id": OID}, server, admins,
        {"value": []},
    ]))
    assert bootstrap.audit_admin(args)["admin_login"] == "Actual ARM Login"
    monkeypatch.setattr(bootstrap, "cli_read", Mock(side_effect=[
        {"id": API, "tenantId": TENANT, "user": {"type": "user"}}, {"id": INGESTION},
    ]))
    with pytest.raises(RuntimeError, match="approved DBA"):
        bootstrap.audit_admin(args)


@pytest.mark.parametrize("rules", [
    [],
    [{"start": "0.0.0.0", "end": "0.0.0.0"}],
    [{"start": "167.103.66.114", "end": "167.103.66.115"}],
    [{"start": "167.103.66.114", "end": "167.103.66.114"},
     {"start": "0.0.0.0", "end": "0.0.0.0"}],
])
def test_public_schema_writes_blocked_unless_firewall_exclusively_one_ip(rules):
    with pytest.raises(RuntimeError, match="exclusively"):
        bootstrap.verify_network({"public_access": "Enabled", "firewall_rules": rules}, "167.103.66.114")


def test_private_or_single_public_ip_network_gate():
    bootstrap.verify_network({"public_access": "Disabled"}, None)
    bootstrap.verify_network({"public_access": "Enabled", "firewall_rules": [
        {"start": "167.103.66.114", "end": "167.103.66.114"},
    ]}, "167.103.66.114")


def test_safe_failure_never_emits_driver_message_or_credentials():
    error = RuntimeError("password=secret-token connection timeout host=private-name")
    assert bootstrap.safe_failure(error) == {"category": "timeout", "sqlstate": None}
    assert "secret-token" not in json.dumps(bootstrap.safe_failure(error))


def test_undefined_function_is_not_classified_as_authentication_failure():
    error = SimpleNamespace(orig=SimpleNamespace(sqlstate="42883"))
    assert bootstrap.safe_failure(error) == {"category": "undefined_function", "sqlstate": "42883"}


@pytest.mark.parametrize("seven,five", [(True, False), (True, True), (False, True)])
def test_principal_function_signature_keeps_validation_and_nonadmin(seven, five):
    connection = Mock()
    connection.execute.return_value.one.return_value = (seven, five)
    bootstrap.create_runtime_principal(connection, "api", API, TENANT)
    statement, parameters = connection.execute.call_args.args
    assert "'service', false, false" in str(statement)
    assert parameters["name"] == "api" and parameters["oid"] == API
    if seven:
        assert str(statement).endswith("CAST(:tenant AS text), false)")
        assert parameters["tenant"] == TENANT
    else:
        assert "tenant" not in parameters


def test_unknown_principal_signature_fails_before_creation():
    connection = Mock()
    connection.execute.return_value.one.return_value = (False, False)
    with pytest.raises(RuntimeError, match="Unsupported"):
        bootstrap.create_runtime_principal(connection, "api", API, TENANT)
    assert connection.execute.call_count == 1


def test_session_check_does_not_call_identity_functions():
    connection = Mock()
    connection.execute.return_value.one.return_value = ("Puneet Devadiga", "Puneet Devadiga")
    bootstrap.verify_session_admin(connection, {"admin_login": "Puneet Devadiga"})
    assert connection.execute.call_count == 1
    assert "pgaadauth" not in str(connection.execute.call_args.args[0])
    connection.execute.return_value.one.return_value = ("other", "Puneet Devadiga")
    with pytest.raises(RuntimeError, match="not the audited DBA"):
        bootstrap.verify_session_admin(connection, {"admin_login": "Puneet Devadiga"})


def test_identity_management_and_grants_use_separate_connections(monkeypatch):
    application, statements = grant_connection()
    identity = Mock()
    monkeypatch.setattr(bootstrap, "verify_schema", Mock())
    monkeypatch.setattr(bootstrap, "principals", Mock(return_value=[]))
    monkeypatch.setattr(bootstrap, "check_runtime_role", Mock(
        side_effect=[False, False, True, True, True, True]))
    creator = Mock()
    monkeypatch.setattr(bootstrap, "create_runtime_principal", creator)
    def committed_before_grants():
        assert statements == []
    identity.commit.side_effect = committed_before_grants
    bootstrap.grant_runtime(application, SimpleNamespace(tables=set()), TENANT,
                            {"api": ("api", API), "ingestion": ("ingestion", INGESTION)},
                            identity_connection=identity)
    identity.commit.assert_called_once()
    creator.assert_any_call(identity, "api", API, TENANT)
    assert all(call.args[0] is identity for call in bootstrap.principals.call_args_list)
    assert not any("pgaadauth" in sql for sql, _ in statements)
    assert any(sql.startswith("GRANT") for sql, _ in statements)


def test_schema_mode_routes_identity_audit_to_postgres_and_migrations_to_application(monkeypatch):
    monkeypatch.setattr(bootstrap, "load_release", Mock(return_value=(Mock(), Mock(tables={}), 104)))
    monkeypatch.setattr(bootstrap, "validate_offline", Mock())
    audit = {"admin_login": "Puneet Devadiga"}
    monkeypatch.setattr(bootstrap, "audit_admin", Mock(return_value=audit))
    monkeypatch.setattr(bootstrap, "verify_network", Mock())
    monkeypatch.setattr(bootstrap, "AzureCliCredential", MagicMock())
    application_engine, identity_engine = MagicMock(), MagicMock()
    application = application_engine.begin.return_value.__enter__.return_value
    identity = identity_engine.connect.return_value.__enter__.return_value
    factory = Mock(side_effect=[application_engine, identity_engine])
    monkeypatch.setattr(bootstrap, "admin_engine", factory)
    verify_identity, verify_session, migrate, verify_schema = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(bootstrap, "verify_connected_admin", verify_identity)
    monkeypatch.setattr(bootstrap, "verify_session_admin", verify_session)
    monkeypatch.setattr(bootstrap, "migrate", migrate)
    monkeypatch.setattr(bootstrap, "verify_schema", verify_schema)
    bootstrap.main(["schema", "--release-dir", ".", "--execute", "--subscription", API,
                    "--tenant", TENANT, "--resource-group", "rg", "--server", "pg",
                    "--admin-object-id", OID])
    assert [call.args[1] for call in factory.call_args_list] == ["turnstile", "postgres"]
    verify_identity.assert_called_once_with(identity, audit)
    verify_session.assert_called_once_with(application, audit)
    assert migrate.call_count == 2
    assert all(call.args[1] is application for call in migrate.call_args_list)
    assert not identity.execute.called
    application_engine.dispose.assert_called_once()
    identity_engine.dispose.assert_called_once()