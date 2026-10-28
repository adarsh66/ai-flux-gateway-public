"""Bounded metadata-only recovery DRY RUN. Deliberately has no write/apply mode.

No live watermark rewinds, SQL writes, raw rows, prompts, subscription IDs or
correlation IDs are returned. Production recovery remains gated by verified
ownership, activation cutoff and private database readiness.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Callable

from aiflux.finops import aware
from aiflux.ingestion import extract_usage, nonnegative, record_id


def recovery_windows(start: datetime, end: datetime, cutoff: datetime, *,
                     now: datetime | None = None, minutes: int = 60) -> list[tuple[datetime, datetime]]:
    now = now or datetime.now(UTC)
    if any(value.tzinfo is None or value.utcoffset() is None for value in (start, end, cutoff, now)):
        raise ValueError("Recovery timestamps require explicit timezones")
    start, end, cutoff, now = map(aware, (start, end, cutoff, now))
    if not now - timedelta(days=30) <= start < end <= now - timedelta(minutes=5):
        raise ValueError("Recovery must stay within retained last 30 days and ingestion delay")
    if start < cutoff:
        raise ValueError("Recovery crosses activation cutoff; separate approval required")
    if not 1 <= minutes <= 60:
        raise ValueError("Recovery windows must be between 1 and 60 minutes")
    windows = []
    while start < end:
        boundary = min(end, start + timedelta(minutes=minutes))
        windows.append((start, boundary))
        start = boundary
    return windows


def dry_run(start: datetime, end: datetime, cutoff: datetime, query: Callable,
            *, now: datetime | None = None, owned: set[str] | None = None) -> dict:
    windows = recovery_windows(start, end, cutoff, now=now)
    seen: set[str] = set()
    report = {"dry_run_only": True, "writes": 0, "forward_watermark_changed": False,
              "ownership_verified": owned is not None, "requests": 0, "duplicate_source_rows": 0,
              "measured_requests": 0, "missing_token_requests": 0, "unresolved_owners": 0 if owned is not None else None,
              "known_input_tokens": 0, "known_output_tokens": 0, "complete_total_tokens": 0,
              "windows": []}

    def collect(left, right):
        try:
            rows = query(left, right)
        except RuntimeError as error:
            # Only overflow can subdivide. Partial queries and other errors abort.
            if "exceeds row limit" not in str(error) or right - left <= timedelta(seconds=1):
                raise
            middle = left + (right - left) / 2
            collect(left, middle)
            collect(middle, right)
            return
        counts = {"start": left.isoformat(), "end": right.isoformat(), "source_rows": len(rows)}
        for row in rows:
            occurred = row["occurred_at"]
            if isinstance(occurred, str):
                occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
            if not isinstance(occurred, datetime) or not left <= aware(occurred) < right:
                raise ValueError("Source row is outside the approved recovery window")
            resource, correlation = row.get("resource_id"), row.get("correlation_id")
            if not isinstance(resource, str) or not resource or not isinstance(correlation, str) or not correlation:
                raise ValueError("Recovery source identity is missing")
            identity = record_id(resource, correlation)
            if identity in seen:
                report["duplicate_source_rows"] += 1
                continue
            if len(seen) >= 100000:
                raise ValueError("Recovery exceeds bounded dry-run size; narrow the period")
            seen.add(identity)
            counters = extract_usage(row.get("trace_records")) or row
            inputs = nonnegative(counters.get("input_tokens"), "input_tokens")
            outputs = nonnegative(counters.get("output_tokens"), "output_tokens")
            report["requests"] += 1
            report["known_input_tokens"] += inputs if inputs is not None else 0
            report["known_output_tokens"] += outputs if outputs is not None else 0
            if inputs is not None and outputs is not None:
                report["measured_requests"] += 1
                report["complete_total_tokens"] += inputs + outputs
            else:
                report["missing_token_requests"] += 1
            if owned is not None and row.get("subscription_id") not in owned:
                report["unresolved_owners"] += 1
        report["windows"].append(counts)

    for left, right in windows:
        collect(left, right)
    report["write_authorized"] = False
    report["recovery_status"] = "dry_run_only_requires_private_database_ownership_and_cutoff_review"
    return report


def main() -> int:
    from scripts.deployment import runtime_rollout as rt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--end", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        account = rt.cli(["account", "show"])
        rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
        values = rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-ingestion/config/appsettings/list", "POST")["properties"]
        required = ("AIFLUX_INGESTION_START_AT", "AIFLUX_LOG_WORKSPACE_ID", "AIFLUX_APIM_RESOURCE_ID", "AIFLUX_APIM_PRODUCT_ID")
        if not all(values.get(key) for key in required):
            report = {"dry_run_only": True, "writes": 0, "status": "blocked",
                      "reason": "verified_ingestion_cutoff_and_source_configuration_required"}
        else:
            # Azure CLI token remains in memory. SDK response bodies are never exported.
            import os
            from azure.identity import AzureCliCredential
            from azure.monitor.query import LogsQueryClient
            from aiflux.config import Settings
            from aiflux.ingestion import query_rows

            os.environ["PATH"] = rt.ENV["PATH"]
            os.environ["REQUESTS_CA_BUNDLE"] = rt.CA
            settings = Settings(log_workspace_id=values["AIFLUX_LOG_WORKSPACE_ID"],
                                apim_resource_id=values["AIFLUX_APIM_RESOURCE_ID"],
                                apim_product_id=values["AIFLUX_APIM_PRODUCT_ID"])
            with AzureCliCredential(tenant_id=rt.TENANT) as credential, LogsQueryClient(credential) as client:
                report = dry_run(args.start, args.end, datetime.fromisoformat(values[required[0]].replace("Z", "+00:00")),
                                 lambda start, end: query_rows(client, settings, start, end))
        report["collected_at"] = datetime.now(UTC).isoformat()
        rt.save(rt.HOME / "finops" / "replay-dry-run.json", report)
        print(json.dumps(report), flush=True)
        return 2 if report.get("status") == "blocked" else 0
    except Exception as exc:
        # Exception messages may contain raw source identifiers; expose type only.
        print(json.dumps({"dry_run_only": True, "writes": 0, "status": "failed", "exception_type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())