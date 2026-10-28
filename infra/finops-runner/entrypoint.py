"""Fixed one-shot supervisor. No server, CLI credential, app import or raw errors.

Internal probe exit is in sanitized JSON. OS exit is zero even on a blocked
snapshot: current ACI guidance warns nonzero exits can restart even with Never.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys

IDENTITIES = {
    "ingestion": ("e1d25c87-9df1-4225-9744-ce22121cf462", "edbfc3e2-a8e5-4652-9bb0-311233756d42"),
    "api": ("f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1", "4e7b70ed-9868-47ba-9b61-304f1e1fdd89"),
}
SUCCESS_FIELDS = {"status", "collected_at", "database", "schema", "identity_role_matches",
    "runtime_ddl_or_ownership", "table_privileges", "all_time", "window", "checkpoint",
    "ownership", "prices", "approved_activation_cutoff", "replay_authorized", "database_writes"}
STAGES = frozenset({"configuration", "dependency_import", "dns_resolution",
    "identity_initialization", "identity_token", "token_validation", "database_connect",
    "database_session", "database_role", "database_privileges", "usage_all_time",
    "usage_window", "ingestion_checkpoint", "subscription_bindings", "usage_ownership",
    "price_coverage", "aggregate_validation", "database_rollback", "database_cleanup",
    "identity_cleanup", "report_serialization"})
EXCEPTION_TYPES = frozenset({"ProbeBlocked", "ImportError", "ModuleNotFoundError",
    "AttributeError", "TypeError", "ValueError", "IndexError", "KeyError", "OverflowError",
    "OSError", "FileNotFoundError", "PermissionError", "TimeoutError", "gaierror",
    "SSLError", "SSLCertVerificationError", "ClientAuthenticationError",
    "CredentialUnavailableError", "ServiceRequestError", "ServiceResponseError",
    "HttpResponseError", "OperationalError", "InterfaceError", "ProgrammingError",
    "DataError", "UndefinedTable", "UndefinedColumn", "InsufficientPrivilege",
    "InvalidPassword", "QueryCanceled", "InvalidTextRepresentation", "unknown"})
GUARD_REASONS = frozenset({"database_destination", "managed_identity_role_required",
    "unreviewed_database_options", "tls_verification_required", "trusted_ca_required",
    "managed_identity_claims", "expired_identity_token", "identity_token_format",
    "explicit_utc_required", "database_session_proof", "runtime_role_elevated",
    "runtime_ddl_or_ownership", "runtime_select_missing", "ingester_dml_missing",
    "attached_client_id_required", "approved_private_endpoint_required",
    "aggregate_integer_required", "database_session_shape", "database_session_database",
    "database_session_session_user", "database_session_current_user",
    "database_session_schema", "database_session_search_path", "database_session_read_only"})
SQLSTATES = frozenset({"08001", "08006", "28P01", "28000", "42501", "42P01",
    "42703", "57014", "25006", "3D000", "3F000"})
FAILURE_FIELDS = {"status", "stage", "exception_type", "reason", "sqlstate",
    "database_writes", "replay_authorized"}


def failure(reason, sqlstate=None, *, stage=None, exception_type="unknown"):
    value = {"status": "blocked", "reason": reason, "sqlstate": sqlstate,
            "database_writes": 0, "replay_authorized": False}
    if stage is not None:
        value.update(stage=stage, exception_type=exception_type)
    return value


def verified_aggregate(value):
    """Reject arbitrary nested strings/keys even if the top-level schema matches."""
    def fields(item, counts=(), dates=(), flags=()):
        if not isinstance(item, dict) or set(item) != set(counts) | set(dates) | set(flags):
            return False
        for key in counts:
            if type(item[key]) is not int or item[key] < 0:
                return False
        for key in flags:
            if type(item[key]) is not bool:
                return False
        for key in dates:
            if item[key] is not None:
                if not isinstance(item[key], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d{1,6})?\+00:00", item[key]):
                    return False
                datetime.fromisoformat(item[key])
        return True
    tables = {"usage_records", "safety_events", "ingestion_state", "team_subscriptions", "model_prices"}
    return (value["database"] == "turnstile" and value["schema"] == "public"
        and value["identity_role_matches"] is True and value["runtime_ddl_or_ownership"] is False
        and fields({"collected_at": value["collected_at"]}, dates=("collected_at",)) and value["collected_at"] is not None
        and isinstance(value["table_privileges"], dict) and set(value["table_privileges"]) == tables
        and all(fields(x, flags=("select", "insert", "update", "delete")) for x in value["table_privileges"].values())
        and fields(value["all_time"], ("requests",), ("first_request_at", "latest_request_at", "last_ingested_at"))
        and fields(value["window"], ("default_lookback_days", "requests", "known_input_tokens", "known_output_tokens", "fully_measured_total_tokens", "missing_token_requests", "unpriced_or_non_usd_requests"), ("start", "end_exclusive"), ("source_retention_verified",))
        and value["window"]["source_retention_verified"] is False and value["window"]["default_lookback_days"] == 30
        and (value["checkpoint"] is None or fields(value["checkpoint"], dates=("watermark", "last_success_at")))
        and fields(value["ownership"], ("subscription_bindings", "active_bindings", "orphaned_or_misattributed_usage_rows"), ("earliest_binding_created_at", "latest_binding_created_at"), ("source_subscription_match_verified",))
        and value["ownership"]["source_subscription_match_verified"] is False
        and fields(value["prices"], ("rows", "usd_rows", "effective_rows")))


def sanitize(content, exit_code):
    try:
        if not isinstance(content, str) or len(content) > 32768 or type(exit_code) is not int or exit_code not in (0, 2):
            return failure("unverified_runtime_failure")
        value = json.loads(content)
        if not isinstance(value, dict):
            return failure("unverified_runtime_failure")
        if (set(value) == FAILURE_FIELDS and value["status"] == "blocked"
                and type(value["database_writes"]) is int and value["database_writes"] == 0
                and value["replay_authorized"] is False and value["stage"] in STAGES
                and value["exception_type"] in EXCEPTION_TYPES
                and value["reason"] in GUARD_REASONS | {"runtime_stage_failed"}
                and (value["sqlstate"] is None or value["sqlstate"] in SQLSTATES)):
            # The controller sanitizes the supervisor's OS-exit-0 JSON again.
            # Preserve only this exact finite schema across BOTH boundaries.
            return dict(value)
        if exit_code == 0 and set(value) == SUCCESS_FIELDS and value["status"] == "verified_read_only_snapshot" and value["database_writes"] == 0 and value["replay_authorized"] is False and value["approved_activation_cutoff"] is None:
            if verified_aggregate(value):
                return value
            return failure("unverified_runtime_failure")
        state = value.get("sqlstate")
        state = state if isinstance(state, str) and state in SQLSTATES else None
        return failure("unverified_runtime_failure", state)
    except Exception:
        return failure("unverified_runtime_failure")


def worker(phase, probe):
    # SDK warnings/errors must not escape through stderr or unauthorized logs.
    logging.disable(logging.CRITICAL)
    client, oid = IDENTITIES[phase]
    role = "poc-ids-token-ex-" + phase + "-identity"
    # Construct the approved password-free destination locally, never ARM env.
    os.environ["AZURE_CLIENT_ID"] = client
    os.environ["AIFLUX_DATABASE_URL"] = "postgresql://" + role + "@poc-ids-token-ex-pg.postgres.database.azure.com/turnstile?sslmode=verify-full"
    try:
        spec = importlib.util.spec_from_file_location("reviewed_probe", probe)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        kind = type(exc).__name__
        print(json.dumps(failure("runtime_stage_failed", stage="dependency_import",
            exception_type=kind if kind in EXCEPTION_TYPES else "unknown")), flush=True)
        return 2
    sys.argv = [str(probe), "--role", role, "--client-id", client, "--object-id", oid]
    return module.main()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-sha256", required=True)
    parser.add_argument("--identity", choices=IDENTITIES, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    probe = Path(__file__).with_name("finops_private_probe.py")
    try:
        source_matches = re.fullmatch(r"[0-9a-f]{64}", args.probe_sha256) and hashlib.sha256(probe.read_bytes()).hexdigest() == args.probe_sha256
    except OSError:
        source_matches = False
    if not source_matches:
        print(json.dumps(failure("probe_source_changed")), flush=True)
        return 0
    if args.worker:
        return worker(args.identity, probe)
    try:
        # Refuse to re-run the DB snapshot if this filesystem survives a restart.
        fd = os.open("/scratch/probe-started", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        child = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()),
            "--probe-sha256", args.probe_sha256, "--identity", args.identity, "--worker"],
            capture_output=True, text=True, timeout=590, check=False)
        result = sanitize(child.stdout, child.returncode)
    except subprocess.TimeoutExpired:
        result = failure("deadline_exceeded")
    except Exception:
        result = failure("unverified_runtime_failure")
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())