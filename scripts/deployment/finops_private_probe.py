"""Read-only PostgreSQL readiness on an EXISTING approved private host.

No deployment/remote execution, CLI credentials, secrets retrieval, DDL/DML,
cutoff inference or replay. The host must already expose the application's
database URL and its attached managed identity. Output is aggregate-only.
"""
from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import re
import socket
import ssl
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

HOST = "poc-ids-token-ex-pg.postgres.database.azure.com"
TENANT = "beb276ac-6e9f-498e-8e31-019ee666decd"
NETWORK = ipaddress.ip_network("10.240.3.0/24")
TABLES = ("usage_records", "safety_events", "ingestion_state", "team_subscriptions", "model_prices")
# Match the existing reviewed PostgreSQL bootstrap and actual ingest_rows/run_once
# operations. The worker never DELETEs; SafetyEvent is insert-only.
WRITABLE = {"usage_records": ("insert", "update"),
            "safety_events": ("insert",), "ingestion_state": ("insert", "update")}
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


class ProbeBlocked(ValueError):
    """Only fixed guard labels, never settings or driver messages."""


def require(value, label):
    if not value:
        raise ProbeBlocked(label)


def private_addresses(addresses):
    """Only the existing endpoint subnet, not arbitrary private/link-local DNS."""
    return bool(addresses) and all(ipaddress.ip_address(a) in NETWORK for a in addresses)


def connection_options(value, expected_role):
    """Validate settings in memory; never export the URL or arbitrary query options."""
    from sqlalchemy.engine import make_url

    url = make_url(value)
    require(url.get_backend_name() == "postgresql" and url.host == HOST and
            url.database == "turnstile" and (url.port or 5432) == 5432, "database_destination")
    require(url.username == expected_role and not url.password, "managed_identity_role_required")
    require(set(url.query) <= {"sslmode", "sslrootcert"}, "unreviewed_database_options")
    require(url.query.get("sslmode", "verify-full") in {"require", "verify-ca", "verify-full"}, "tls_verification_required")
    # Strengthen the existing require-only DSN locally; never rewrite app settings.
    ca = url.query.get("sslrootcert") or os.environ.get("SSL_CERT_FILE") or ssl.get_default_verify_paths().cafile
    require(isinstance(ca, str) and os.path.isfile(ca), "trusted_ca_required")
    return {"host": HOST, "port": 5432, "dbname": "turnstile", "user": expected_role,
            "sslmode": "verify-full", "sslrootcert": ca, "connect_timeout": 8,
            "options": "-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000 -c search_path=public,pg_catalog"}


def verify_token(token, object_id):
    """Check selected MI claims in memory; PostgreSQL performs actual token validation."""
    require(isinstance(token, str) and len(token) <= 65536, "identity_token_format")
    parts = token.split(".")
    require(len(parts) == 3 and all(parts), "identity_token_format")
    part = parts[1]
    require(re.fullmatch(r"[A-Za-z0-9_-]+", part) is not None, "identity_token_format")
    try:
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (ValueError, UnicodeError):
        raise ProbeBlocked("identity_token_format") from None
    require(isinstance(claims, dict) and isinstance(claims.get("aud"), str) and
            type(claims.get("exp")) in (int, float), "identity_token_format")
    require(claims.get("tid") == TENANT and claims.get("oid") == object_id and
            claims.get("aud", "").rstrip("/") == "https://ossrdbms-aad.database.windows.net", "managed_identity_claims")
    import math
    require(0 < claims["exp"] < 2**63 and math.isfinite(claims["exp"]) and
            claims["exp"] > datetime.now(UTC).timestamp(), "expired_identity_token")


def aggregate_integer(value):
    """psycopg loads PostgreSQL SUM(bigint) / numeric as Decimal, not int."""
    require(type(value) is int or (type(value) is Decimal and value.is_finite() and
            value == value.to_integral_value()), "aggregate_integer_required")
    require(0 <= value <= 10**100, "aggregate_integer_required")
    return int(value)


def verify_database_session(row, expected_role):
    """Strict session proof with finite reasons, never returned metadata.

    PostgreSQL string GUCs retain input spelling; psycopg text loading does not
    insert comma whitespace. Accept only the startup spelling and the previous
    test spelling, not arbitrary schemas, quoted identifiers or reordered paths.
    current_setting('transaction_read_only') returns text, not a Python bool.
    """
    require(type(row) is tuple and len(row) == 6, "database_session_shape")
    database, session, user, schema, search_path, read_only = row
    for actual, expected, reason in (
        (database, "turnstile", "database_session_database"),
        (session, expected_role, "database_session_session_user"),
        (user, expected_role, "database_session_current_user"),
        (schema, "public", "database_session_schema"),
    ):
        require(type(actual) is str and actual == expected, reason)
    require(type(search_path) is str and search_path in ("public,pg_catalog", "public, pg_catalog"),
            "database_session_search_path")
    require(type(read_only) is str and read_only == "on", "database_session_read_only")


def failure_report(exc, stage):
    """Finite labels only. Never stringify an untrusted exception or SQLSTATE."""
    kind = type(exc).__name__
    reason = str(exc) if type(exc) is ProbeBlocked and str(exc) in GUARD_REASONS else "runtime_stage_failed"
    state = getattr(exc, "sqlstate", None)
    # Actual PostgreSQL codes only, not any arbitrary five-character string.
    states = {"08001", "08006", "28P01", "28000", "42501", "42P01", "42703", "57014", "25006", "3D000", "3F000"}
    return {"status": "blocked", "stage": stage if stage in STAGES else "configuration",
            "exception_type": kind if kind in EXCEPTION_TYPES else "unknown", "reason": reason,
            "sqlstate": state if isinstance(state, str) and state in states else None,
            "database_writes": 0, "replay_authorized": False}


def inspect_database(db, expected_role, *, now=None, progress=None):
    """One read-only repeatable snapshot, with rollback even on failed proof.

    Effective privileges are catalog queries, never write/DDL permission probes.
    Subscription creation dates are facts, NOT an approved activation cutoff.
    """
    def mark(stage):
        if progress is not None:
            progress["stage"] = stage

    now = now or datetime.now(UTC)
    require(now.tzinfo is not None and now.utcoffset() is not None, "explicit_utc_required")
    end = now.astimezone(UTC) - timedelta(minutes=5)
    start = now.astimezone(UTC) - timedelta(days=30)
    try:
        mark("database_session")
        with db.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SELECT current_database(), session_user, current_user, current_schema(), current_setting('search_path'), current_setting('transaction_read_only')")
            verify_database_session(cursor.fetchone(), expected_role)
            mark("database_role")
            cursor.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            role = cursor.fetchone()
            require(role is not None and not any(role), "runtime_role_elevated")
            mark("database_privileges")
            cursor.execute("SELECT has_database_privilege(current_user, current_database(), 'CREATE'), has_schema_privilege(current_user, 'public', 'CREATE'), EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND pg_has_role(current_user, c.relowner, 'USAGE'))")
            require(not any(cursor.fetchone()), "runtime_ddl_or_ownership")
            permissions = {}
            for table in TABLES:
                cursor.execute("SELECT has_table_privilege(current_user, %s, 'SELECT'), has_table_privilege(current_user, %s, 'INSERT'), has_table_privilege(current_user, %s, 'UPDATE'), has_table_privilege(current_user, %s, 'DELETE')",
                               ("public." + table,) * 4)
                flags = cursor.fetchone()
                permissions[table] = dict(zip(("select", "insert", "update", "delete"), flags, strict=True))
                require(flags[0], "runtime_select_missing")
                if expected_role.endswith("ingestion-identity") and table in WRITABLE:
                    require(all(permissions[table][operation] for operation in WRITABLE[table]), "ingester_dml_missing")
            mark("usage_all_time")
            cursor.execute("SELECT count(*), min(occurred_at), max(occurred_at), max(ingested_at) FROM public.usage_records")
            total, first, latest, ingested = cursor.fetchone()
            mark("usage_window")
            cursor.execute("SELECT count(*), coalesce(sum(input_tokens::bigint),0), coalesce(sum(output_tokens::bigint),0), count(*) FILTER (WHERE input_tokens IS NULL OR output_tokens IS NULL), count(*) FILTER (WHERE cost IS NULL OR currency IS DISTINCT FROM 'USD'), coalesce(sum(input_tokens::bigint + output_tokens::bigint) FILTER (WHERE input_tokens IS NOT NULL AND output_tokens IS NOT NULL),0) FROM public.usage_records WHERE occurred_at >= %s AND occurred_at < %s", (start, end))
            count, inputs, outputs, missing, unpriced, measured_total = cursor.fetchone()
            mark("aggregate_validation")
            inputs, outputs, measured_total = map(aggregate_integer, (inputs, outputs, measured_total))
            mark("ingestion_checkpoint")
            cursor.execute("SELECT watermark, last_success_at FROM public.ingestion_state WHERE id = 'native-llm'")
            checkpoint = cursor.fetchone()
            mark("subscription_bindings")
            cursor.execute("SELECT count(*), min(created_at), max(created_at), count(*) FILTER (WHERE state='active') FROM public.team_subscriptions")
            subscriptions, earliest_binding, latest_binding, active = cursor.fetchone()
            mark("usage_ownership")
            cursor.execute("SELECT count(*) FROM public.usage_records u LEFT JOIN public.team_subscriptions s ON s.id=u.subscription_id WHERE s.id IS NULL OR s.organization_id IS DISTINCT FROM u.organization_id")
            orphaned = cursor.fetchone()[0]
            mark("price_coverage")
            cursor.execute("SELECT count(*), count(*) FILTER (WHERE currency='USD'), count(*) FILTER (WHERE effective_from <= %s AND (effective_to IS NULL OR effective_to > %s)) FROM public.model_prices", (end, end))
            prices, usd_prices, effective_prices = cursor.fetchone()
            return {"status": "verified_read_only_snapshot", "collected_at": now.isoformat(),
                    "database": "turnstile", "schema": "public", "identity_role_matches": True,
                    "runtime_ddl_or_ownership": False, "table_privileges": permissions,
                    "all_time": {"requests": total, "first_request_at": first, "latest_request_at": latest, "last_ingested_at": ingested},
                    "window": {"start": start, "end_exclusive": end, "default_lookback_days": 30,
                               "source_retention_verified": False, "requests": count, "known_input_tokens": inputs,
                               "known_output_tokens": outputs, "fully_measured_total_tokens": measured_total,
                               "missing_token_requests": missing, "unpriced_or_non_usd_requests": unpriced},
                    "checkpoint": {"watermark": checkpoint[0], "last_success_at": checkpoint[1]} if checkpoint else None,
                    "ownership": {"subscription_bindings": subscriptions, "active_bindings": active,
                                  "earliest_binding_created_at": earliest_binding, "latest_binding_created_at": latest_binding,
                                  "orphaned_or_misattributed_usage_rows": orphaned, "source_subscription_match_verified": False},
                    "prices": {"rows": prices, "usd_rows": usd_prices, "effective_rows": effective_prices},
                    "approved_activation_cutoff": None, "replay_authorized": False, "database_writes": 0}
    finally:
        try:
            db.rollback()
        except Exception:
            mark("database_rollback")
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("poc-ids-token-ex-api-identity", "poc-ids-token-ex-ingestion-identity"), required=True)
    parser.add_argument("--client-id", type=UUID, required=True)
    parser.add_argument("--object-id", type=UUID, required=True)
    args = parser.parse_args()
    progress = {"stage": "configuration"}
    try:
        # No DefaultAzureCredential/CLI fallback: use only this already-attached MI.
        require(os.environ.get("AZURE_CLIENT_ID") == str(args.client_id), "attached_client_id_required")
        progress["stage"] = "dependency_import"
        from azure.identity import ManagedIdentityCredential
        import psycopg

        progress["stage"] = "configuration"
        options = connection_options(os.environ.get("AIFLUX_DATABASE_URL", ""), args.role)
        progress["stage"] = "dns_resolution"
        addresses = {a[4][0] for a in socket.getaddrinfo(HOST, 5432, type=socket.SOCK_STREAM)}
        require(private_addresses(addresses), "approved_private_endpoint_required")
        # Pin the validated private destination while retaining hostname TLS checks.
        options["hostaddr"] = sorted(addresses)[0]
        progress["stage"] = "identity_initialization"
        with ManagedIdentityCredential(client_id=str(args.client_id)) as credential:
            progress["stage"] = "identity_token"
            access = credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
            progress["stage"] = "token_validation"
            verify_token(access.token, str(args.object_id))
            progress["stage"] = "database_connect"
            with psycopg.connect(**options, password=access.token) as db:
                report = inspect_database(db, args.role, progress=progress)
                progress["stage"] = "database_cleanup"
            progress["stage"] = "identity_cleanup"
        progress["stage"] = "report_serialization"
        print(json.dumps(report, default=str), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps(failure_report(exc, progress["stage"])), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())