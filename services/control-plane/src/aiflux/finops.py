import csv
import io
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, case, cast, func, literal_column, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement, Select

from aiflux.models import IngestionState, ModelPrice, UsageRecord
from aiflux.schemas import PriceCreate
from aiflux.display_pricing import detail_estimates, estimate_summary


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def create_price(db: Session, payload: PriceCreate, *, idempotent: bool = False) -> tuple[ModelPrice, bool]:
    rows = db.scalars(
        select(ModelPrice)
        .where(
            ModelPrice.model == payload.model,
            ModelPrice.provider == payload.provider,
            ModelPrice.region == payload.region,
        )
        .with_hint(ModelPrice, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
    ).all()
    values = payload.model_dump()
    for price in rows:
        existing = {key: getattr(price, key) for key in values}
        existing["effective_from"] = aware(price.effective_from)
        existing["effective_to"] = aware(price.effective_to) if price.effective_to else None
        if idempotent and existing == values:
            return price, False
        if (payload.effective_to is None or aware(price.effective_from) < payload.effective_to) and (
            price.effective_to is None or payload.effective_from < aware(price.effective_to)
        ):
            raise ValueError("Price periods must not overlap")
    row = ModelPrice(**values)
    db.add(row)
    db.flush()
    return row, True


def price_for(db: Session, row: UsageRecord) -> ModelPrice | None:
    return db.scalar(
        select(ModelPrice)
        .where(
            ModelPrice.model == row.model,
            ModelPrice.provider == row.provider,
            ModelPrice.region == row.region,
            ModelPrice.effective_from <= row.occurred_at,
            (ModelPrice.effective_to.is_(None)) | (ModelPrice.effective_to > row.occurred_at),
        )
        .order_by(ModelPrice.effective_from.desc())
    )


def calculate_cost(row: UsageRecord, price: ModelPrice | None) -> tuple[Decimal | None, str]:
    if row.input_tokens is None or row.output_tokens is None:
        return None, "usage_missing"
    if price is None:
        return None, "price_missing"
    cached = row.cached_input_tokens
    writes = row.cache_write_tokens
    if price.cached_input_per_million is not None and cached is None:
        return None, "cache_usage_missing"
    if price.cache_write_per_million is not None and writes is None:
        return None, "cache_write_usage_missing"
    regular = row.input_tokens
    if price.input_includes_cached:
        if cached is not None:
            regular -= cached
        if writes is not None:
            regular -= writes
    if regular < 0 or (cached and price.cached_input_per_million is None):
        return None, "cache_accounting_unknown"
    if writes and price.cache_write_per_million is None:
        return None, "cache_accounting_unknown"
    cost = (
        Decimal(regular) * price.input_per_million
        + Decimal(row.output_tokens) * price.output_per_million
        + Decimal(cached or 0) * (price.cached_input_per_million or Decimal(0))
        + Decimal(writes or 0) * (price.cache_write_per_million or Decimal(0))
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.00000001")), "complete"


def usage_dict(row: UsageRecord) -> dict[str, Any]:
    fields = (
        "id",
        "subscription_id",
        "model",
        "provider",
        "region",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "currency",
        "status_code",
        "e2e_ms",
        "ttft_ms",
        "completeness",
    )
    result = {field: getattr(row, field) for field in fields}
    result["occurred_at"] = aware(row.occurred_at).isoformat()
    result["cost"] = str(row.cost) if row.cost is not None else None
    return result


def usage_conditions(
    organization_id: str | None,
    subscription_id: str | None,
    model: str | None = None,
) -> list[ColumnElement[bool]]:
    conditions = []
    if organization_id is not None:
        conditions.append(UsageRecord.organization_id == organization_id)
    if subscription_id is not None:
        conditions.append(UsageRecord.subscription_id == subscription_id)
    if model is not None:
        conditions.append(UsageRecord.model == model)
    return conditions


def usage_models(
    db: Session, organization_id: str | None, days: int, subscription_id: str | None,
) -> dict[str, Any]:
    items = list(db.scalars(
        select(UsageRecord.model)
        .where(
            *usage_conditions(organization_id, subscription_id),
            UsageRecord.occurred_at >= datetime.now(UTC) - timedelta(days=days),
        )
        .distinct()
        .order_by(UsageRecord.model)
    ))
    return {"items": items, "total": len(items)}


def usage_response(
    db: Session,
    organization_id: str | None,
    days: int,
    subscription_id: str | None,
    offset: int,
    limit: int,
    model: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=days)
    conditions = [
        *usage_conditions(organization_id, subscription_id, model),
        UsageRecord.occurred_at >= start, UsageRecord.occurred_at < end,
    ]
    aggregates = db.execute(
        select(
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            func.sum(UsageRecord.cost),
            func.count(func.distinct(UsageRecord.currency)),
            func.min(UsageRecord.currency),
            func.sum(case((UsageRecord.completeness != "complete", 1), else_=0)),
            func.sum(case((UsageRecord.status_code >= 400, 1), else_=0)),
            func.sum(case((UsageRecord.status_code == 429, 1), else_=0)),
            func.sum(cast(UsageRecord.input_tokens, BigInteger) + cast(UsageRecord.output_tokens, BigInteger)),
            func.sum(case((UsageRecord.input_tokens.is_(None) | UsageRecord.output_tokens.is_(None), 1), else_=0)),
        ).where(*conditions)
    ).one()
    latency_conditions = [*conditions, UsageRecord.e2e_ms.is_not(None)]
    latency_count = db.scalar(select(func.count()).select_from(UsageRecord).where(*latency_conditions)) or 0
    p95 = (
        db.scalar(
            select(UsageRecord.e2e_ms)
            .where(*latency_conditions)
            .order_by(
                UsageRecord.e2e_ms,
            )
            .offset(max(0, math.ceil(latency_count * 0.95) - 1))
            .limit(1)
        )
        if latency_count
        else None
    )
    state = db.get(IngestionState, "native-llm")
    count, inputs, outputs, cost, currencies, currency, incomplete, failed, throttled, total_tokens, missing_tokens = aggregates
    rows = db.scalars(
        select(UsageRecord)
        .where(*conditions)
        .order_by(
            UsageRecord.occurred_at.desc(),
            UsageRecord.id,
        )
        .offset(offset)
        .limit(limit)
    ).all()
    estimates = detail_estimates(db, [row.id for row in rows])
    estimated_summary = estimate_summary(db, conditions)[0]
    estimated_summary.pop("group")
    return {
        "summary": {
            **estimated_summary,
            "requests": count,
            "input_tokens": inputs,
            "output_tokens": outputs,
            "total_tokens": total_tokens,
            "measured_requests": count - (missing_tokens or 0),
            "missing_token_requests": missing_tokens or 0,
            "known_cost": str(cost) if cost is not None and currencies == 1 else None,
            "currency": currency if currencies == 1 else None,
            "incomplete_requests": incomplete or 0,
            "failed_requests": failed or 0,
            "throttled_requests": throttled or 0,
            "e2e_p95_ms": p95,
            "ttft_supported": False,
            "cache_tokens_supported": bool(db.scalar(
                select(func.count()).select_from(UsageRecord).where(
                    *conditions, UsageRecord.cached_input_tokens.is_not(None),
                )
            )),
            "last_ingested_at": aware(state.last_success_at).isoformat() if state else None,
            "health": ingestion_health(db, organization_id, subscription_id),
        },
        "items": [usage_dict(row) | estimates[row.id] for row in rows],
        "total": count,
    }


def usage_csv(
    db: Session,
    organization_id: str | None,
    days: int,
    subscription_id: str | None,
    model: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> str:
    result = usage_response(db, organization_id, days, subscription_id, 0, 10001, model, start, end)
    if result["total"] > 10000:
        raise ValueError("Export exceeds 10000 records; narrow the time, subscription or model filter")
    output = io.StringIO(newline="")
    fields = [
        "id",
        "subscription_id",
        "model",
        "provider",
        "region",
        "occurred_at",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "cost",
        "currency",
        "status_code",
        "e2e_ms",
        "ttft_ms",
        "completeness",
        "estimated_cost_usd",
        "estimate_basis",
        "pricing_revision",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in result["items"]:
        safe_row = {
            key: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
            for key, value in row.items()
        }
        writer.writerow(safe_row)
    return output.getvalue()


def usage_series_query(
    dialect: str,
    organization_id: str | None,
    subscription_id: str | None,
    start: datetime,
    end: datetime,
    model: str | None = None,
) -> Select:
    timestamp = UsageRecord.occurred_at
    if dialect == "mssql":
        epoch = literal_column("CONVERT(datetime2, '20000101', 112)", type_=DateTime())
        minute = func.dateadd(
            literal_column("minute"), func.datediff(literal_column("minute"), epoch, timestamp), epoch,
        )
    elif dialect == "postgresql":
        minute = func.date_trunc("minute", timestamp)
    elif dialect == "sqlite":
        minute = func.strftime("%Y-%m-%dT%H:%M:00Z", timestamp)
    else:
        raise ValueError(f"Minute usage aggregation does not support database dialect {dialect!r}")
    conditions = [
        *usage_conditions(organization_id, subscription_id, model), timestamp >= start, timestamp < end,
    ]
    inputs = cast(UsageRecord.input_tokens, BigInteger)
    outputs = cast(UsageRecord.output_tokens, BigInteger)
    missing_tokens = UsageRecord.input_tokens.is_(None) | UsageRecord.output_tokens.is_(None)
    return (
        select(
            minute.label("minute"),
            func.count(UsageRecord.id).label("requests"),
            func.sum(inputs).label("input_tokens"),
            func.sum(outputs).label("output_tokens"),
            func.sum(inputs + outputs).label("total_tokens"),
            (func.avg(cast(UsageRecord.e2e_ms, Float)) / 1000.0).label("avg_e2e_seconds"),
            func.sum(cast(case((missing_tokens, 1), else_=0), BigInteger)).label("missing_token_requests"),
            func.count(UsageRecord.e2e_ms).label("latency_samples"),
        )
        .where(*conditions)
        .group_by(minute)
        .order_by(minute)
    )


def usage_series_response(
    db: Session,
    organization_id: str | None,
    subscription_id: str | None,
    start: datetime,
    end: datetime,
    model: str | None = None,
) -> dict[str, Any]:
    query = usage_series_query(
        db.get_bind().dialect.name, organization_id, subscription_id, start, end, model,
    )
    items = []
    for row in db.execute(query).mappings():
        item = dict(row)
        minute = item["minute"]
        item["minute"] = aware(datetime.fromisoformat(minute) if isinstance(minute, str) else minute)
        items.append(item)
    return {"items": items, "start": start, "end": end, "interval_seconds": 60}


TOKEN_BUCKET_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
TOKEN_BUCKET_INTERVALS = (60, 300, 900, 3600, 21600, 43200, 86400, 604800)


def token_bucket_interval(start: datetime, end: datetime) -> int:
    first = (start - TOKEN_BUCKET_EPOCH).total_seconds()
    last = (end - TOKEN_BUCKET_EPOCH).total_seconds()
    for seconds in TOKEN_BUCKET_INTERVALS:
        if math.ceil(last / seconds) - math.floor(first / seconds) <= 120:
            return seconds
    raise ValueError("Token chart viewport exceeds the supported range")


def model_token_query(
    dialect: str, organization_id: str | None, subscription_id: str | None,
    start: datetime, end: datetime, interval_seconds: int, model: str | None = None,
) -> Select:
    if interval_seconds not in TOKEN_BUCKET_INTERVALS:
        raise ValueError("Unsupported model token bucket interval")
    timestamp = UsageRecord.occurred_at
    if dialect == "mssql":
        epoch = literal_column("CONVERT(datetime2, '20000101', 112)", type_=DateTime())
        minutes = func.datediff(literal_column("minute"), epoch, timestamp)
        # Positional parameters in repeated GROUP BY expressions are distinct
        # to SQL Server. Only validated server-owned interval constants are inlined.
        bucket = func.floor(cast(minutes, Float) / literal_column(str(interval_seconds // 60)))
    elif dialect == "postgresql":
        epoch_seconds = int(TOKEN_BUCKET_EPOCH.timestamp())
        pg_seconds = cast(func.extract("epoch", timestamp), Float) - literal_column(str(epoch_seconds))
        bucket = func.floor(pg_seconds / literal_column(str(interval_seconds)))
    elif dialect == "sqlite":
        seconds = cast(func.strftime("%s", timestamp), BigInteger) - int(TOKEN_BUCKET_EPOCH.timestamp())
        bucket = func.floor(cast(seconds, Float) / interval_seconds)
    else:
        raise ValueError(f"Model token aggregation does not support database dialect {dialect!r}")
    missing = UsageRecord.input_tokens.is_(None) | UsageRecord.output_tokens.is_(None)
    return (
        select(
            bucket.label("bucket"),
            UsageRecord.model,
            func.count(UsageRecord.id).label("requests"),
            func.sum(
                cast(UsageRecord.input_tokens, BigInteger) + cast(UsageRecord.output_tokens, BigInteger),
            ).label("total_tokens"),
            func.sum(cast(UsageRecord.input_tokens, BigInteger)).label("input_tokens"),
            func.sum(cast(UsageRecord.output_tokens, BigInteger)).label("output_tokens"),
            func.sum(cast(case((missing, 1), else_=0), BigInteger)).label("missing_token_requests"),
        )
        .where(
            *usage_conditions(organization_id, subscription_id, model), timestamp >= start, timestamp < end,
        )
        .group_by(bucket, UsageRecord.model)
        .order_by(bucket, UsageRecord.model)
    )


def model_token_response(
    db: Session, organization_id: str | None, subscription_id: str | None,
    start: datetime, end: datetime, model: str | None = None, granularity: str = "auto",
) -> dict[str, Any]:
    start, end = aware(start), aware(end)
    if start >= end:
        raise ValueError("Usage window end must be after start")
    if granularity not in ("auto", "hour", "day"):
        raise ValueError("Granularity must be hour, day or auto")
    interval = token_bucket_interval(start, end) if granularity == "auto" else (
        3600 if granularity == "hour" else 86400)
    buckets = math.ceil((end - TOKEN_BUCKET_EPOCH).total_seconds() / interval) - math.floor(
        (start - TOKEN_BUCKET_EPOCH).total_seconds() / interval)
    if buckets > 744:
        raise ValueError("Requested granularity exceeds 744 buckets; narrow the viewport or select Daily")
    query = model_token_query(
        db.get_bind().dialect.name, organization_id, subscription_id, start, end, interval, model,
    )
    items = []
    for row in db.execute(query).mappings():
        bucket_start = TOKEN_BUCKET_EPOCH + timedelta(seconds=int(row["bucket"]) * interval)
        items.append({
            "start": max(start, bucket_start),
            "end": min(end, bucket_start + timedelta(seconds=interval)),
            "model": row["model"], "requests": row["requests"],
            "total_tokens": row["total_tokens"], "missing_token_requests": row["missing_token_requests"],
            "input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"],
            "measured_requests": row["requests"] - row["missing_token_requests"],
            "partial_bucket": bucket_start < start or bucket_start + timedelta(seconds=interval) > end,
        })
    return {"items": items, "start": start, "end": end, "interval_seconds": interval,
            "granularity": granularity, "health": ingestion_health(db, organization_id, subscription_id)}


def ingestion_health(db: Session, organization_id: str | None, subscription_id: str | None = None) -> dict:
    """Strictly read-only, scoped row timestamps; never seed budgets or expose raw failures.

    Absence of a checkpoint is unverified, not proof of disabled ingestion. The API
    process cannot infer another app's timer settings from its own environment.
    """
    state = db.get(IngestionState, "native-llm")
    latest = db.scalar(select(func.max(UsageRecord.ingested_at)).where(
        *usage_conditions(organization_id, subscription_id)))
    now = datetime.now(UTC)
    lag = max(0, int((now - aware(state.watermark)).total_seconds())) if state else None
    success_lag = max(0, int((now - aware(state.last_success_at)).total_seconds())) if state else None
    status = "unverified" if not state else "stale" if max(lag or 0, success_lag or 0) > 900 else "healthy"
    return {"status": status, "watermark": aware(state.watermark) if state else None,
            "last_query_success_at": aware(state.last_success_at) if state else None,
            "last_row_ingested_at": aware(latest) if latest else None,
            "lag_seconds": lag, "stale_after_seconds": 900, "expected_delay_seconds": 300}
