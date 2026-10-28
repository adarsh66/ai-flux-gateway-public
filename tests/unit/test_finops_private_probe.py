"""Synthetic private-host proof tests. No Azure credentials or live DB access."""
import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts.deployment import finops_diagnose as diagnose
from scripts.deployment import finops_private_probe as probe

NOW = datetime(2026, 10, 27, 1, tzinfo=UTC)
ROLE = "poc-ids-token-ex-ingestion-identity"


class Database:
    def __init__(self):
        self.statements = []
        self.rolled_back = False
        self.answers = [
            ("turnstile", ROLE, ROLE, "public", "public, pg_catalog", "on"),
            (False,) * 4, (False,) * 3,
            *((True,) * 4 for _ in probe.TABLES),
            (2, NOW - timedelta(days=2), NOW - timedelta(days=1), NOW),
            (2, 11, 107, 1, 2, 18),
            (NOW - timedelta(minutes=10), NOW),
            (1, NOW - timedelta(days=3), NOW - timedelta(days=3), 1),
            (0,), (0, 0, 0),
        ]

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, parameters=None):
        assert query.startswith(("SELECT ", "SET TRANSACTION "))
        self.statements.append((query, parameters))

    def fetchone(self):
        return self.answers.pop(0)

    def rollback(self):
        self.rolled_back = True


def test_snapshot_is_rollback_only_scoped_and_never_approves_cutoff_or_source_ownership():
    db = Database()
    result = probe.inspect_database(db, ROLE, now=NOW)
    assert db.rolled_back and not db.answers
    assert db.statements[0][0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    window = result["window"]
    assert window["start"] == NOW - timedelta(days=30)
    assert window["end_exclusive"] == NOW - timedelta(minutes=5)
    assert window["fully_measured_total_tokens"] == 18
    assert window["known_output_tokens"] == 107 and window["missing_token_requests"] == 1
    assert window["source_retention_verified"] is False
    assert result["approved_activation_cutoff"] is None and not result["replay_authorized"]
    assert result["ownership"]["source_subscription_match_verified"] is False
    assert result["ownership"]["earliest_binding_created_at"] == NOW - timedelta(days=3)
    assert result["database_writes"] == 0
    assert ROLE not in json.dumps(result, default=str)
    assert "subscription_id" not in json.dumps(result, default=str)


def test_ingestion_least_privilege_contract_matches_existing_bootstrap_without_delete():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parents[2] / "infra/sql/bootstrap-postgres.py").read_text())
    bootstrap = next(ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "INGESTION" for t in node.targets))
    db = Database()
    for index, table in enumerate(probe.TABLES, 3):
        operations = bootstrap[table]
        db.answers[index] = tuple(op in operations for op in ("SELECT", "INSERT", "UPDATE", "DELETE"))
        assert "DELETE" not in operations
        assert probe.WRITABLE.get(table, ()) == tuple(op.lower() for op in operations if op != "SELECT")
    result = probe.inspect_database(db, ROLE, now=NOW)
    assert result["status"] == "verified_read_only_snapshot" and db.rolled_back
    assert all(not flags["delete"] for flags in result["table_privileges"].values())


@pytest.mark.parametrize("table,operation", [
    ("usage_records", "insert"), ("usage_records", "update"),
    ("safety_events", "insert"), ("ingestion_state", "insert"), ("ingestion_state", "update"),
])
def test_every_actual_ingestion_write_permission_remains_required(table, operation):
    db = Database()
    index = 3 + probe.TABLES.index(table)
    flags = list(db.answers[index])
    flags[("select", "insert", "update", "delete").index(operation)] = False
    db.answers[index] = tuple(flags)
    with pytest.raises(probe.ProbeBlocked, match="ingester_dml_missing"):
        probe.inspect_database(db, ROLE, now=NOW)
    assert db.rolled_back
    assert not any("min(occurred_at)" in sql for sql, _ in db.statements)


@pytest.mark.parametrize("index,answer", [
    (0, ("wrong_db", ROLE, ROLE, "public", "public, pg_catalog", "on")),
    (0, ("turnstile", ROLE, "operator", "public", "public, pg_catalog", "on")),
    (0, ("turnstile", ROLE, ROLE, "public", "public, pg_catalog", "off")),
    (1, (True, False, False, False)), (1, (False, False, False, True)),
    (2, (True, False, False)), (2, (False, True, False)), (2, (False, False, True)),
    (3, (True, False, True, True)), (6, (False, False, False, False)),
])
def test_bad_identity_elevation_owner_or_grants_fail_before_data_queries(index, answer):
    db = Database()
    db.answers[index] = answer
    with pytest.raises(ValueError):
        probe.inspect_database(db, ROLE, now=NOW)
    assert db.rolled_back
    assert not any("min(occurred_at)" in sql for sql, _ in db.statements)


@pytest.mark.parametrize("addresses,allowed", [
    ({"10.240.3.4"}, True), ({"10.240.3.4", "10.240.3.5"}, True),
    (set(), False), ({"4.193.98.244"}, False), ({"127.0.0.1"}, False),
    ({"169.254.169.254"}, False), ({"10.240.4.4"}, False),
    ({"10.240.3.4", "4.193.98.244"}, False), ({"::1"}, False),
])
def test_dns_requires_exact_existing_endpoint_subnet(addresses, allowed):
    assert probe.private_addresses(addresses) is allowed


def test_existing_require_dsn_is_strengthened_without_settings_mutation(tmp_path, monkeypatch):
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic certificate path")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    value = f"postgresql://{ROLE}@{probe.HOST}/turnstile?sslmode=require"
    result = probe.connection_options(value, ROLE)
    assert result["sslmode"] == "verify-full" and "password" not in result
    assert "default_transaction_read_only=on" in result["options"]
    assert "statement_timeout=15000" in result["options"]
    assert "sslmode=require" in value


@pytest.mark.parametrize("value", [
    f"postgresql://{ROLE}:SECRET@{probe.HOST}/turnstile",
    f"postgresql://operator@{probe.HOST}/turnstile",
    f"postgresql://{ROLE}@other.invalid/turnstile",
    f"postgresql://{ROLE}@{probe.HOST}/other",
    f"postgresql://{ROLE}@{probe.HOST}/turnstile?options=-c+search_path=evil",
    f"postgresql://{ROLE}@{probe.HOST}/turnstile?sslmode=disable",
])
def test_unapproved_destination_password_identity_or_options_rejected(value):
    with pytest.raises(ValueError):
        probe.connection_options(value, ROLE)


def token(**changes):
    claims = {"tid": probe.TENANT, "oid": "expected-object", "aud": "https://ossrdbms-aad.database.windows.net",
              "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(), **changes}
    return "header." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".signature"


def test_token_claims_check_selected_identity_not_operator_fallback():
    probe.verify_token(token(), "expected-object")
    for changes in ({"tid": "other"}, {"oid": "operator"}, {"aud": "https://management.azure.com/"}, {"exp": 0}):
        with pytest.raises(ValueError, match="identity"):
            probe.verify_token(token(**changes), "expected-object")


@pytest.mark.parametrize("value,verified", [
    ({"Output": "200\n", "ExitCode": 0}, True),
    ({"output": "200", "exitCode": 0}, True),
    ({"Output": "", "ExitCode": 0}, False),
    ({"Output": "200", "ExitCode": 1}, False),
    ({"Output": "200", "ExitCode": False}, False),
    ({"Output": "403", "ExitCode": 0}, False),
    ({"Output": "SECRET 200", "ExitCode": 0}, False),
    ({"Output": "200", "ExitCode": "0"}, False), ([], False),
])
def test_scm_transport_cannot_masquerade_as_health(value, verified):
    result = diagnose.scm_health_result(value)
    assert (result["status"] == "verified") is verified
    assert "SECRET" not in str(result)


def test_workstation_probe_never_requests_operator_database_token(monkeypatch):
    monkeypatch.setattr(diagnose.socket, "getaddrinfo", lambda *_args, **_kw: [(None, None, None, None, ("10.240.3.4", 5432))])
    class Socket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(diagnose.socket, "create_connection", lambda *_args, **_kw: Socket())
    monkeypatch.setattr(diagnose.rt, "cli", lambda *_: pytest.fail("operator token must not be requested"))
    result = diagnose.private_database_probe()
    assert result["status"] == "transport_only" and not result["database_authenticated"]


def test_state_probe_preserves_deny_and_exports_only_finite_failure_labels(monkeypatch):
    calls = []
    def cli(args):
        calls.append(args)
        if args[:3] == ["storage", "account", "show"]:
            return {"networkRuleSet": {"defaultAction": "Deny", "ipRules": [
                {"ipAddressOrRange": "167.103.66.248"}, {"ipAddressOrRange": "167.103.66.93"}]}}
        pytest.fail("unexpected Azure call")
    monkeypatch.setattr(diagnose.rt, "cli", cli)
    from types import SimpleNamespace
    def run(args, **kwargs):
        calls.append(args)
        assert "exists" in args and "login" in args and "create" not in args
        return SimpleNamespace(returncode=1, stdout="", stderr="AuthorizationFailure DO-NOT-EXPORT-RAW-STATE-OR-TOKEN")
    monkeypatch.setattr(diagnose.subprocess, "run", run)
    result = diagnose.state_storage_probe()
    assert result["default_action"] == "Deny" and result["other_ip_rule_count"] == 0
    assert result["container_metadata_access"]["status"] == "blocked"
    assert result["container_metadata_access"]["categories"] == ["authorization_failure"]
    assert "DO-NOT-EXPORT" not in str(result) and len(calls) == 2


@pytest.mark.parametrize("extra,other_count", [((), 0), (("203.0.113.9",), 1)])
def test_state_only_approved_ip_reconciliation_does_not_authorize_other_rules(monkeypatch, extra, other_count):
    approved = {"167.103.66.248", "167.103.66.93", "167.103.65.36"}
    assert diagnose.APPROVED_STATE_STORAGE_IPS == approved
    calls = []

    def cli(args):
        calls.append(args)
        assert args[:3] == ["storage", "account", "show"]
        return {"networkRuleSet": {"defaultAction": "Deny", "ipRules": [
            {"ipAddressOrRange": ip} for ip in sorted(approved | set(extra))]}}

    monkeypatch.setattr(diagnose.rt, "cli", cli)
    monkeypatch.setattr(diagnose, "container_metadata_probe", lambda: {"status": "verified"})
    result = diagnose.state_storage_probe()
    assert result["approved_ips_present"] == sorted(approved)
    assert result["default_action"] == "Deny" and result["other_ip_rule_count"] == other_count
    assert result["container_metadata_access"] == {"status": "verified"}
    assert len(calls) == 1  # Diagnostic reconciliation must never change any ACL.


def test_retention_and_assignments_are_metadata_not_effective_mi_proof(monkeypatch):
    def cli(args):
        if args[:2] == ["rest", "--method"]:
            assert args[2] == "get"
            if "/tables/" in args[4]:
                return {"properties": {"retentionInDays": 30, "totalRetentionInDays": 90, "plan": "Analytics"}}
            return {"properties": {"customerId": "workspace", "retentionInDays": 30}}
        assert args[:3] == ["role", "assignment", "list"]
        return [{"principalId": "ingester", "scope": diagnose.rt.RG,
                 "roleDefinitionName": "Log Analytics Reader"},
                {"principalId": "other", "scope": diagnose.rt.RG,
                 "roleDefinitionName": "Owner"},
                {"principalId": "ingester", "scope": "/unrelated", "roleDefinitionName": "Owner"}]
    monkeypatch.setattr(diagnose.rt, "cli", cli)
    monkeypatch.setattr(diagnose.rt, "arm", lambda *args: {"properties": {
        "AIFLUX_LOG_WORKSPACE_ID": "workspace", "secret": "NEVER-EXPORT"}})
    result = diagnose.retention_and_roles({"ingestion": {"attached_identities": [{"object_id": "ingester"}]}})
    assert result["api_workspace_matches"] is True
    assert result["managed_identity_data_plane_verified"] is False
    assert result["tables"]["ApiManagementGatewayLogs"]["retentionInDays"] == 30
    roles = result["roles"]["ingestion"]["monitor_workspace"]["known_builtin_role_names"]
    assert roles == ["Log Analytics Reader"]
    assert "Owner" not in str(result) and "NEVER-EXPORT" not in str(result)


def test_cli_blocks_missing_host_identity_before_network_or_credentials(monkeypatch, capsys):
    import sys
    monkeypatch.setattr(sys, "argv", ["probe", "--role", ROLE,
        "--client-id", "e1d25c87-9df1-4225-9744-ce22121cf462",
        "--object-id", "edbfc3e2-a8e5-4652-9bb0-311233756d42"])
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.setenv("AIFLUX_DATABASE_URL", "SECRET-DSN-DO-NOT-OUTPUT")
    monkeypatch.setattr(probe.socket, "getaddrinfo", lambda *_a, **_kw: pytest.fail("must fail before networking"))
    assert probe.main() == 2
    output = capsys.readouterr().out
    assert "SECRET" not in output
    result = json.loads(output)
    assert result["reason"] == "attached_client_id_required" and result["database_writes"] == 0