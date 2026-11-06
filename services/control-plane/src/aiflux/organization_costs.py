"""Admin-only completion cost comparison. No ledger, writes or per-record pricing.

Two group-page reads, one internal pricing load + grouped aggregate, one batch
external snapshot statement, and at most ten external aggregate statements.
SQL savepoint commands are additional; query count never grows with usage rows.
"""
from datetime import datetime

from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.orm import Session

from aiflux import customer_pricing, display_pricing, external_pricing, rate_card
from aiflux.models import Organization, UsageRecord as U


def internal_completion_estimate(db: Session, organization_id: str,
                                 start: datetime, end: datetime, as_of: datetime) -> dict:
    """Existing internal historical rate-card estimator, bounded to one snapshot.

    Retained subscription usage is included by organization ownership on the
    ledger; no active-subscription join or recorded-cost substitution.
    """
    conditions = [U.organization_id == organization_id, U.occurred_at >= start,
                  U.occurred_at < end, U.occurred_at <= as_of,
                  func.lower(U.model).notin_(["decision-1", "microsoft-decision-1"])]
    result = display_pricing.estimate_summary(db, conditions, **rate_card.estimate_args(db))[0]
    return {key: value for key, value in result.items() if key != "group"}


def organization_costs(db: Session, start: datetime, end: datetime,
                       model: str | None, offset: int, limit: int) -> dict:
    if not 1 <= limit <= 10 or offset < 0:
        raise ValueError("Invalid organization cost page")
    # Explicit scoring exclusion, not the current selectable-completion catalog:
    # historical completion aliases remain discoverable (unknown prices allowed).
    conditions = [U.occurred_at >= start, U.occurred_at < end,
                  func.lower(U.model).notin_(["decision-1", "microsoft-decision-1"])]
    if model is not None:
        conditions.append(U.model == model)
    grouped = select(
        U.organization_id.label("id"), Organization.name.label("name"),
        func.count().label("requests"),
        func.sum(cast(U.input_tokens, BigInteger) + cast(U.output_tokens, BigInteger)).label("total_tokens"),
    ).join(Organization, Organization.id == U.organization_id).where(*conditions).group_by(
        U.organization_id, Organization.name).subquery()
    total = db.scalar(select(func.count()).select_from(grouped)) or 0
    rows = db.execute(select(grouped).order_by(
        func.coalesce(grouped.c.total_tokens, -1).desc(), grouped.c.id,
    ).offset(offset).limit(limit)).mappings().all()
    result = {"items": [], "total": total, "start": start, "end": end,
              "currency": "USD", "order": "measured_tokens_desc_id_asc"}
    if not rows:
        return result
    ids = [row["id"] for row in rows]
    page_conditions = [*conditions, U.organization_id.in_(ids)]
    internal = {row["group"][0]: row for row in display_pricing.estimate_summary(
        db, page_conditions, U.organization_id, **rate_card.estimate_args(db))}
    contexts = external_pricing.snapshots_for_organizations(db, ids)
    for row in rows:
        external = customer_pricing.estimate_summary(
            db, [*conditions, U.organization_id == row["id"]], pricing_context=contexts[row["id"]])[0]
        result["items"].append({**dict(row),
            "internal": {k: v for k, v in internal[row["id"]].items() if k != "group"},
            "external": {k: v for k, v in external.items() if k != "group"}})
    return result