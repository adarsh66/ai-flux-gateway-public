"""Read-only, request-scoped Decision-1 trace showback; never completion usage."""

import csv
import hashlib
import io
import json
import math
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux.config import Settings
from aiflux.models import TeamSubscription
from aiflux.rate_card import load_state, scoring_effective_estimate
from aiflux.external_pricing import PricingContext
from aiflux.customer_pricing import customer_safe

RETENTION_NOTICE = "Log Analytics retention applies; trace availability is not an ingestion or billing guarantee."
MAX_ROWS = 10000
MAX_BUCKETS = 10000
INTERVALS = {"minute": 60, "hour": 3600, "day": 86400}
ITEM_FIELDS = (
    "id", "parent_request_id", "subscription_id", "organization_id", "occurred_at",
    "routing_profile", "selected_model", "config_version", "input_tokens", "output_tokens",
    "total_tokens", "latency_ms", "recorded_cost_usd", "estimated_cost_usd", "estimate_basis",
    "pricing_revision", "parent_status_code", "usage_kind",
)


def authorized_subscriptions(db: Session, organization_id: str | None, subscription_id: str | None) -> dict[str, str]:
    """APIM uses TeamSubscription.id; never accept ownership claimed by a trace."""
    query = select(TeamSubscription.id, TeamSubscription.organization_id)
    if organization_id is not None:
        query = query.where(TeamSubscription.organization_id == organization_id)
    if subscription_id is not None:
        query = query.where(TeamSubscription.id == subscription_id)
    return {sid: org for sid, org in db.execute(query)}


def render_query(settings: Settings, start: datetime, end: datetime, owners: dict[str, str], row_limit: int) -> str:
    """Adapt the frozen query only in memory. Fail closed if its insertion point changes."""
    source = Path(__file__).with_name("queries").joinpath("decision-overhead.kql").read_text(encoding="utf-8")
    anchor = "              gateway_region=Region, trace_records=TraceRecords;"
    if source.count(anchor) != 1 or source.count("| take {row_limit}") != 1 or not owners:
        raise ValueError("Unsupported Decision-1 query contract")
    source = source.replace(anchor, anchor[:-1] + "\n    | where subscription_id in (" +
                            ", ".join(json.dumps(sid) for sid in sorted(owners)) + ");", 1)
    return source.format(start=start.isoformat(), end=end.isoformat(),
                         resource=json.dumps(settings.apim_resource_id),
                         product=json.dumps(settings.apim_product_id), row_limit=row_limit + 1)


def _query(client: Any, settings: Settings, query: str, start: datetime, end: datetime, row_limit: int) -> list[dict]:
    response = client.query_workspace(settings.log_workspace_id, query, timespan=(start, end),
                                      server_timeout=15, connection_timeout=5, read_timeout=20, retry_total=0)
    if response.status != "Success":
        raise ValueError("Partial Decision-1 query")
    rows = []
    for table in response.tables:
        columns = [c if isinstance(c, str) else c.name for c in table.columns]
        if len(set(columns)) != len(columns):
            raise ValueError("Duplicate query columns")
        for values in table.rows:
            if len(rows) >= row_limit:
                raise ValueError("Decision-1 row limit exceeded")
            rows.append(dict(zip(columns, values, strict=True)))
    return rows


def query_rows(client: Any, settings: Settings, query: str, start: datetime, end: datetime, row_limit: int) -> list[dict]:
    if client is not None:
        return _query(client, settings, query, start, end, row_limit)
    # No credential construction at import, startup, missing configuration or empty scope.
    from azure.identity import DefaultAzureCredential
    from azure.monitor.query import LogsQueryClient

    with DefaultAzureCredential(exclude_interactive_browser_credential=True, process_timeout=5,
                                retry_total=0, connection_timeout=5, read_timeout=20) as credential:
        with LogsQueryClient(credential, retry_total=0, connection_timeout=5, read_timeout=20) as logs:
            return _query(logs, settings, query, start, end, row_limit)


def _number(value: Any, maximum: int, *, integer: bool = False) -> int | float | None:
    if value is None:
        return None
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or not 0 <= value <= maximum or (integer and int(value) != value)):
        raise ValueError("Invalid Decision-1 numeric field")
    return int(value) if integer else float(value)


def _cost(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Invalid recorded cost")
    try:
        cost = Decimal(str(value))
        if not cost.is_finite() or not 0 <= cost <= Decimal("1000000000000"):
            raise ValueError("Invalid recorded cost")
        return format(cost, "f")
    except InvalidOperation as exc:
        raise ValueError("Invalid recorded cost") from exc


def validate_rows(rows: list[dict], settings: Settings, owners: dict[str, str], start: datetime,
                  end: datetime, version: int, entries: list[dict], *,
                  pricing_context: PricingContext | None = None) -> list[dict]:
    items, seen = [], set()
    for row in rows:
        resource, correlation, sid = (row.get(k) for k in ("resource_id", "correlation_id", "subscription_id"))
        if (not isinstance(resource, str) or resource.lower() != settings.apim_resource_id.lower()
                or not isinstance(correlation, str) or row.get("request_id") != correlation
                or not isinstance(sid, str) or sid not in owners):
            raise ValueError("Untrusted Decision-1 attribution")
        if str(UUID(correlation)) != correlation or UUID(correlation).int == 0:
            raise ValueError("Invalid Decision-1 request ID")
        key = (resource.lower(), correlation)
        if key in seen or type(row.get("decision_trace_count")) is not int or row["decision_trace_count"] != 1:
            raise ValueError("Duplicate Decision-1 event")
        seen.add(key)
        if (row.get("decision_schema") != "decision-overhead-v1"
                or row.get("routing_profile") not in ("balanced", "cost", "quality")
                or not isinstance(row.get("config_version"), str)
                or re.fullmatch(r"[0-9a-f]{64}", row["config_version"]) is None
                or not isinstance(row.get("selected_model"), str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}", row["selected_model"]) is None):
            raise ValueError("Invalid Decision-1 configuration")
        occurred = row.get("occurred_at")
        if isinstance(occurred, str):
            occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
        if not isinstance(occurred, datetime) or occurred.tzinfo is None or occurred.utcoffset() is None:
            raise ValueError("Invalid Decision-1 timestamp")
        occurred = occurred.astimezone(UTC)
        if occurred.timestamp() < 0 or not start <= occurred < end:
            raise ValueError("Decision-1 timestamp outside viewport")
        input_tokens = _number(row.get("decision_input_tokens"), 2147483647, integer=True)
        output_tokens = _number(row.get("decision_output_tokens"), 2147483647, integer=True)
        latency = _number(row.get("decision_latency_ms"), 120000)
        status = _number(row.get("parent_status_code"), 599, integer=True)
        if status is not None and status < 100:
            raise ValueError("Invalid parent HTTP status")
        estimate = (pricing_context.scoring_estimate(input_tokens, occurred) if pricing_context is not None
                else scoring_effective_estimate(version, entries, input_tokens, occurred))
        recorded = _cost(row.get("decision_cost_usd"))
        items.append({
            "id": hashlib.sha256(f"{resource.lower()}:{correlation}".encode()).hexdigest(),
            "parent_request_id": correlation, "subscription_id": sid, "organization_id": owners[sid],
            "occurred_at": occurred.isoformat(), "routing_profile": row["routing_profile"],
            "selected_model": row["selected_model"], "config_version": row["config_version"],
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None,
            "latency_ms": latency, "recorded_cost_usd": (
                recorded if pricing_context is None else None),
            "estimated_cost_usd": _cost(estimate["estimated_cost_usd"]),
            "estimate_basis": estimate["estimate_basis"], "pricing_revision": estimate["pricing_revision"],
            "parent_status_code": status, "usage_kind": "decision_scoring",
        })
    return sorted(items, key=lambda item: (item["occurred_at"], item["id"]), reverse=True)


def _sum(items: list[dict], field: str, *, money: bool = False) -> Any:
    values = [item[field] for item in items]
    if any(v is None for v in values):
        return None
    if money:
        return format(sum((Decimal(v) for v in values), Decimal(0)), "f") if values else None
    return sum(values)


def _aggregate(items: list[dict]) -> dict:
    latencies = [item["latency_ms"] for item in items if item["latency_ms"] is not None]
    return {"invocations": len(items), **{field: _sum(items, field) for field in
            ("input_tokens", "output_tokens", "total_tokens")},
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else None}


def _bucket_bounds(start: datetime, end: datetime, granularity: str, time_zone: str) -> tuple[datetime, timedelta]:
    if granularity not in INTERVALS or time_zone not in ("UTC", "Asia/Singapore"):
        raise ValueError("Unsupported Decision-1 bucket settings")
    interval = timedelta(seconds=INTERVALS[granularity])
    origin = datetime(1970, 1, 1, tzinfo=UTC) - timedelta(hours=8 if time_zone == "Asia/Singapore" else 0)
    first = origin + ((start - origin) // interval) * interval
    if math.ceil((end - first) / interval) > MAX_BUCKETS:
        raise ValueError("Decision-1 viewport exceeds 10000 buckets; choose a coarser granularity")
    return first, interval


def decision_scoring(db: Session, settings: Settings, organization_id: str | None, subscription_id: str | None,
                     start: datetime, end: datetime, offset: int = 0, limit: int = 50,
                     granularity: str = "hour", time_zone: str = "UTC", client: Any = None, *,
                     pricing_context: PricingContext | None = None) -> dict:
    first, interval = _bucket_bounds(start, end, granularity, time_zone)
    owners = authorized_subscriptions(db, organization_id, subscription_id)
    version, entries = load_state(db) if pricing_context is None else (0, [])
    revision = (pricing_context.revision if pricing_context is not None else
                scoring_effective_estimate(version, entries, None, start)["pricing_revision"])
    response = {
        "model": "Decision-1", "source": "log_analytics", "status": "unavailable", "notice": None,
        "start": start.isoformat(), "end": end.isoformat(), "retention_notice": RETENTION_NOTICE,
        "summary": {"invocations": None, "input_tokens": None, "output_tokens": None, "total_tokens": None,
                    "measured_invocations": 0, "missing_token_invocations": 0, "estimated_cost_usd": None,
                    "estimated_invocations": 0, "unestimated_invocations": 0, "avg_latency_ms": None,
                    "recorded_cost_usd": None, "pricing_revision": revision},
        "items": [], "total": None, "series": [], "breakdown": [],
        "granularity": granularity, "time_zone": time_zone, "offset": offset, "limit": limit,
    }
    if not settings.log_workspace_id.strip() or not settings.apim_resource_id.strip() or not settings.apim_product_id.strip():
        result = {**response, "notice": "Decision-1 monitoring is not configured."}
        return customer_safe(result) if pricing_context is not None else result
    if not owners:
        result = {**response, "notice": "No authorized APIM subscriptions are available for this scope."}
        return customer_safe(result) if pricing_context is not None else result
    try:
        row_limit = min(MAX_ROWS, settings.ingestion_max_rows)
        if row_limit < 1:
            raise ValueError("Invalid query row limit")
        query = render_query(settings, start, end, owners, row_limit)
        rows = query_rows(client, settings, query, start, end, row_limit)
        items = validate_rows(rows, settings, owners, start, end, version, entries,
                      pricing_context=pricing_context)
    except Exception:
        # Never echo SDK errors, untrusted rows or partial cross-tenant results.
        result = {**response, "notice": "Decision-1 telemetry could not be verified completely; narrow the viewport or retry later."}
        return customer_safe(result) if pricing_context is not None else result
    measured = sum(item["total_tokens"] is not None for item in items)
    estimated = sum(item["estimated_cost_usd"] is not None for item in items)
    summary = {**_aggregate(items), "measured_invocations": measured,
               "missing_token_invocations": len(items) - measured,
               "estimated_cost_usd": _sum(items, "estimated_cost_usd", money=True),
               "recorded_cost_usd": _sum(items, "recorded_cost_usd", money=True),
               "estimated_invocations": estimated, "unestimated_invocations": len(items) - estimated,
               "pricing_revision": revision}
    buckets: dict[datetime, list[dict]] = {}
    groups: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        occurred = datetime.fromisoformat(item["occurred_at"])
        bucket = first + ((occurred - first) // interval) * interval
        buckets.setdefault(bucket, []).append(item)
        groups.setdefault((item["organization_id"], item["subscription_id"]), []).append(item)
    series = []
    bucket = first
    while bucket < end:
        series.append({"start": max(start, bucket).isoformat(), "end": min(end, bucket + interval).isoformat(),
                       **_aggregate(buckets.get(bucket, [])),
                       "partial_bucket": bucket < start or bucket + interval > end})
        bucket += interval
    breakdown = [{"organization_id": org, "subscription_id": sid,
                  **{k: v for k, v in _aggregate(group).items() if k != "avg_latency_ms"},
                  "estimated_cost_usd": _sum(group, "estimated_cost_usd", money=True)}
                 for (org, sid), group in sorted(groups.items())]
    partial = measured < len(items) or estimated < len(items) or any(item["latency_ms"] is None for item in items)
    result = {**response, "status": "partial" if partial else "available",
            "notice": "Some scoring tokens, latencies or date-effective estimates are missing; unknown totals remain null." if partial else None,
            "summary": summary, "items": items[offset:offset + limit], "total": len(items),
            "series": series, "breakdown": breakdown}
    return customer_safe(result) if pricing_context is not None else result


def decision_csv(response: dict) -> str:
    """A paginated snapshot with status/coverage metadata, never a fabricated zero row."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)

    def safe(value: Any) -> str:
        value = "" if value is None else str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) or value.startswith(("\t", "\r", "\n")) else value

    metadata = ("model", "source", "status", "notice", "start", "end", "retention_notice", "total",
                "granularity", "time_zone", "offset", "limit")
    writer.writerow(["metadata", "value"])
    for field in metadata:
        writer.writerow([field, safe(response[field])])
    for field, value in response["summary"].items():
        writer.writerow(["summary." + field, safe(value)])
    writer.writerow([])
    fields = tuple(field for field in ITEM_FIELDS
                   if field != "recorded_cost_usd" or field in response["summary"])
    writer.writerow(fields)
    for item in response["items"]:
        writer.writerow([safe(item[field]) for field in fields])
    return stream.getvalue()