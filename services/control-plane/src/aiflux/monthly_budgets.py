"""Recurring UTC advisory budgets. Reads never seed or mutate financial data.

No publisher, inference, email or Monitor dependencies. Usage is estimated only
against a detached external pricing snapshot. Decision-1's production telemetry
is NOT in UsageRecord: absent stage coverage is reported as incomplete, never
silently converted into zero/free scoring. Persisted scoring rows, if supplied
by a future separately approved ingestion path, use external input-only prices.
"""
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import Numeric, and_, case, cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aiflux import customer_pricing, external_pricing
from aiflux.auth import Principal
from aiflux.display_pricing import ELIGIBLE
from aiflux.models import (
    Organization, OrganizationMonthlyBudgetPolicy, OrganizationMonthlyBudgetRevision, UsageRecord,
)
from aiflux.schemas import (AdminMonthlyBudgetDashboard, AdminMonthlyBudgetListItem,
                           MonthlyBudgetRevisionOutput, MonthlyBudgetSummary, MonthlyBudgetUpdate)
from aiflux.subscriptions import audit

SCORING_MODELS = ("decision-1", "microsoft-decision-1")


def utc(value: datetime) -> datetime:
    # SQLite restores UTC storage timestamps without timezone information.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def iso(value: datetime) -> str:
    return utc(value).isoformat().replace("+00:00", "Z")


def month_window(at: datetime) -> tuple[datetime, datetime]:
    at = utc(at)
    start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def monthly_estimate(db: Session, organization_id: str, *, at: datetime | None = None,
                     subscription_id: str | None = None) -> dict:
    at = utc(at or datetime.now(UTC))
    start, end = month_window(at)
    conditions = [UsageRecord.organization_id == organization_id,
                  UsageRecord.occurred_at >= start, UsageRecord.occurred_at < end,
                  UsageRecord.occurred_at <= at]
    if subscription_id is not None:
        conditions.append(UsageRecord.subscription_id == subscription_id)
    context = external_pricing.snapshot(db, organization_id, at)
    scoring = func.lower(UsageRecord.model).in_(SCORING_MODELS)
    estimate = customer_pricing.estimate_summary(db, [*conditions, ~scoring], pricing_context=context)[0]
    completion_count = estimate["estimated_requests"] + estimate["unestimated_requests"]
    # Build a SQL input-only CASE from the SAME external snapshot. Never read
    # internal tariffs and never issue price queries per usage row.
    scoring_keys = {(e["model"], e["provider"], e["region"]) for e in context._events
                    if e.get("model_kind") == "scoring"}
    # scoring_estimate deliberately refuses ambiguous scopes. A price alone
    # must not supply missing or conflicting usage attribution.
    scoring_key = next(iter(scoring_keys)) if len(scoring_keys) == 1 else None
    times = sorted({e["at"] for e in context._events if scoring_key is not None
                    and (e["model"], e["provider"], e["region"]) == scoring_key})
    branches = []
    for index, valid_from in enumerate(times):
        if scoring_key[0].lower() not in SCORING_MODELS:
            continue
        price = context.scoring_estimate(1_000_000, valid_from)["estimated_cost_usd"]
        if price is None:
            continue
        valid = [UsageRecord.occurred_at >= valid_from, UsageRecord.input_tokens >= 0,
                 UsageRecord.status_code >= 200, UsageRecord.status_code < 300,
                 UsageRecord.completeness.in_(ELIGIBLE),
                 UsageRecord.provider == scoring_key[1], UsageRecord.region == scoring_key[2]]
        if index + 1 < len(times):
            valid.append(UsageRecord.occurred_at < times[index + 1])
        branches.append((and_(*valid), cast(UsageRecord.input_tokens, Numeric(38, 12))
                         * Decimal(price) / Decimal(1_000_000)))
    amount = case(*branches, else_=None) if branches else cast(None, Numeric(38, 12))
    count, estimated, scoring_cost = db.execute(select(func.count(), func.count(amount), func.sum(amount))
        .select_from(UsageRecord).where(*conditions, scoring)).one()
    values = [Decimal(value) for value in (estimate["estimated_cost_usd"], scoring_cost) if value is not None]
    estimated_count = estimate["estimated_requests"] + estimated
    unestimated_count = estimate["unestimated_requests"] + count - estimated
    # Empty observed usage is a zero estimate, but unavailable pricing is still
    # unknown. This is observed coverage, not an assertion of timely ingestion.
    used = sum(values, Decimal(0)) if values else (
        Decimal(0) if completion_count + count == 0 and context.revision != "external:unavailable" else None)
    latest = db.scalar(select(func.max(UsageRecord.occurred_at)).where(*conditions))
    # Production scoring remains in Log Analytics. Even apparently fully priced
    # completion rows do not establish complete billable-stage coverage. Counts
    # above are observed rows only; do not invent missing invocation counts.
    complete = (unestimated_count == 0 and not estimate["approximate_requests"]
                and context.revision != "external:unavailable" and completion_count == 0)
    return dict(used=used, estimated_requests=estimated_count, unestimated_requests=unestimated_count,
                estimate_complete=complete, pricing_revision=context.revision,
                latest_usage_at=iso(latest) if latest else None, period_start=iso(start),
                period_end=iso(end), as_of=iso(at))


def _organization(db: Session, organization_id: str) -> Organization:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    return org


def summary(db: Session, organization_id: str, *, at: datetime | None = None) -> MonthlyBudgetSummary:
    org = _organization(db, organization_id)
    at = utc(at or datetime.now(UTC))
    # Version/values come from one revision statement; no torn head+revision read.
    row = db.scalar(select(OrganizationMonthlyBudgetRevision).where(
        OrganizationMonthlyBudgetRevision.organization_id == organization_id,
        OrganizationMonthlyBudgetRevision.changed_at <= at,
    ).order_by(OrganizationMonthlyBudgetRevision.version.desc()).limit(1))
    estimate = monthly_estimate(db, organization_id, at=at)
    used = estimate.pop("used")
    allocated = Decimal(row.allocated_usd) if row else None
    threshold = row.advisory_threshold_pct if row else 80
    utilization = used / allocated * Decimal(100) if used is not None and allocated is not None else None
    status = "unconfigured" if row is None else "unknown"
    if utilization is not None and row is not None:
        if utilization > 100:
            status = "over_budget"
        elif utilization >= threshold:
            status = "threshold_reached"
        elif estimate["estimate_complete"]:
            status = "below_threshold"
    # Partial usage remains an explicitly incomplete estimate. Do not advertise
    # a remaining allocation when unknown stages could consume it.
    remaining = max(Decimal(0), allocated - used) if allocated is not None and used is not None and estimate["estimate_complete"] else None
    overrun = max(Decimal(0), used - allocated) if allocated is not None and used is not None else None
    return MonthlyBudgetSummary(
        organization_id=org.id, organization_name=org.name,
        allocated_usd=format(allocated, ".4f") if allocated is not None else None,
        estimated_used_usd=format(used, ".12f") if used is not None else None,
        estimated_remaining_usd=format(remaining, ".12f") if remaining is not None else None,
        estimated_overrun_usd=format(overrun, ".12f") if overrun is not None else None,
        estimated_utilization_pct=float(utilization) if utilization is not None else None,
        advisory_threshold_pct=threshold, version=row.version if row else 0, status=status, **estimate,
    )


def admin_dashboard(db: Session, organization_id: str, *, at: datetime | None = None) -> AdminMonthlyBudgetDashboard:
    from aiflux.organization_costs import internal_completion_estimate

    org = _organization(db, organization_id)
    at = utc(at or datetime.now(UTC))
    start, end = month_window(at)
    return AdminMonthlyBudgetDashboard(
        budget=summary(db, organization_id, at=at),
        internal=internal_completion_estimate(db, organization_id, start, end, at),
        archived_at=iso(org.deleted_at) if org.deleted_at else None,
        read_only=org.deleted_at is not None, as_of=iso(at))


def list_summaries(db: Session, *, offset: int = 0, limit: int = 20,
                   archive_state: str = "current") -> dict:
    if archive_state not in ("current", "archived"):
        raise HTTPException(422, "Invalid organization archive state")
    at = datetime.now(UTC)
    predicate = Organization.deleted_at.is_(None) if archive_state == "current" else Organization.deleted_at.is_not(None)
    total = db.scalar(select(func.count()).select_from(Organization).where(predicate)) or 0
    orgs = db.scalars(select(Organization).where(predicate).order_by(
        Organization.name, Organization.id).offset(offset).limit(limit))
    return {"items": [AdminMonthlyBudgetListItem(**summary(db, org.id, at=at).model_dump(),
                     archived_at=iso(org.deleted_at) if org.deleted_at else None) for org in orgs], "total": total}


def history(db: Session, organization_id: str, *, offset: int = 0, limit: int = 20) -> dict:
    _organization(db, organization_id)
    conditions = [OrganizationMonthlyBudgetRevision.organization_id == organization_id]
    total = db.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetRevision).where(*conditions)) or 0
    rows = db.scalars(select(OrganizationMonthlyBudgetRevision).where(*conditions)
                      .order_by(OrganizationMonthlyBudgetRevision.version.desc()).offset(offset).limit(limit))
    return {"items": [MonthlyBudgetRevisionOutput(version=row.version,
             allocated_usd=format(row.allocated_usd, ".4f"), advisory_threshold_pct=row.advisory_threshold_pct,
             reason=row.reason, changed_by=row.changed_by, changed_at=iso(row.changed_at)) for row in rows],
            "total": total}


def save(db: Session, principal: Principal, organization_id: str,
         payload: MonthlyBudgetUpdate) -> MonthlyBudgetSummary:
    version = payload.expected_version + 1
    try:
        # Same organization row mutex as archive/create. Refresh identity-map
        # state AFTER waiting; an archive winner must reject before any CAS,
        # revision or audit. Disabled but nonarchived organizations are valid.
        org = db.scalar(select(Organization).where(Organization.id == organization_id)
            .with_for_update().with_hint(Organization, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
            .execution_options(populate_existing=True))
        if org is None:
            raise HTTPException(404, "Organization not found")
        if org.deleted_at is not None:
            raise HTTPException(409, "Organization is archived; monthly budgets are read-only. Refresh budgets.")
        if payload.expected_version == 0:
            db.add(OrganizationMonthlyBudgetPolicy(organization_id=organization_id, version=version))
            db.flush()  # Unique PK races become a 409; never last-writer-wins.
        else:
            changed = db.execute(update(OrganizationMonthlyBudgetPolicy).where(
                OrganizationMonthlyBudgetPolicy.organization_id == organization_id,
                OrganizationMonthlyBudgetPolicy.version == payload.expected_version,
            ).values(version=version).execution_options(synchronize_session=False))
            if changed.rowcount != 1:
                raise HTTPException(409, "Monthly budget version conflict; reload before saving")
        at = datetime.now(UTC)
        db.add(OrganizationMonthlyBudgetRevision(organization_id=organization_id, version=version,
               allocated_usd=Decimal(payload.allocated_usd), advisory_threshold_pct=payload.advisory_threshold_pct,
               reason=payload.reason, changed_by=principal.object_id, changed_at=at))
        audit(db, principal, "monthly_budget.updated", organization_id, organization_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Monthly budget version conflict; reload before saving") from exc
    except Exception:
        db.rollback()
        raise
    return summary(db, organization_id)