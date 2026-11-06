import logging
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aiflux.apim import ApimClient, ApimError
from aiflux.auth import Principal
from aiflux.models import AuditEvent, Organization, Team, TeamSubscription
from aiflux.schemas import SubscriptionCreate

log = logging.getLogger(__name__)


def team_identity(organization_id: str, name: str) -> str:
    # Exact label bytes avoid SQL collation accidentally merging differently named teams.
    return str(uuid5(NAMESPACE_URL, f"aiflux:team:{organization_id}:{name}"))


def audit(
    db: Session, principal: Principal, action: str, target: str, organization_id: str | None = None,
    reason: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=organization_id or principal.organization_id,
            object_id=principal.object_id,
            action=action,
            target_id=target,
            reason=reason,
        )
    )


def subscription_dict(row: TeamSubscription) -> dict[str, Any]:
    from aiflux.finops import aware

    return {field: getattr(row, field) for field in ("id", "name", "team", "state")} | {
        "created_at": aware(row.created_at).isoformat(),
        "deleted_at": aware(row.deleted_at).isoformat() if row.deleted_at else None,
        "deletion_status": row.deletion_status,
    }


def lock_organization(db: Session, organization_id: str, *, allow_disabled: bool = False) -> Organization:
    org = db.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
        .with_hint(
            Organization,
            "WITH (UPDLOCK, HOLDLOCK)",
            dialect_name="mssql",
        )
        .execution_options(populate_existing=True)
    )
    if org is None or org.deleted_at is not None or (not allow_disabled and not org.enabled):
        raise HTTPException(403, "Organization is disabled")
    return org


def require_live_subscription(row: TeamSubscription) -> None:
    try:
        if UUID(row.id).int == 0 or str(UUID(row.id)) != row.id:
            raise ValueError
    except ValueError:
        raise HTTPException(409, "Only DB-linked managed UUID subscriptions support lifecycle actions") from None
    if row.deleted_at is not None or row.deletion_requested_at is not None:
        raise HTTPException(409, "Subscription is archived or deletion is pending; only deletion retry is allowed")


def mark_subscription_ready(db: Session, sid: str) -> int:
    """Publication finalization CAS: a stale snapshot cannot undo tombstones.

    No APIM action, commit, queue or feature activation. Unlike an ORM read then
    write, the lifecycle predicates are evaluated atomically by PostgreSQL.
    """
    result = db.execute(update(TeamSubscription).where(
        TeamSubscription.id == sid, TeamSubscription.state == "pending",
        TeamSubscription.desired_state == "active", TeamSubscription.deleted_at.is_(None),
        TeamSubscription.deletion_requested_at.is_(None), TeamSubscription.apim_pending_operation.is_(None),
    ).values(state="active"))
    return result.rowcount


def owned(db: Session, sid: UUID, principal: Principal) -> TeamSubscription:
    lock_organization(db, principal.organization_id)
    row = db.scalar(
        select(TeamSubscription)
        .where(
            TeamSubscription.id == str(sid),
            TeamSubscription.organization_id == principal.organization_id,
        )
        .with_hint(TeamSubscription, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .with_for_update().execution_options(populate_existing=True)
    )
    if row is None:
        raise HTTPException(404, "Subscription not found")
    require_live_subscription(row)
    return row


def admin_owned(db: Session, sid: UUID) -> TeamSubscription:
    organization_id = db.scalar(
        select(TeamSubscription.organization_id).where(TeamSubscription.id == str(sid)),
    )
    if organization_id is None:
        raise HTTPException(404, "Subscription not found")
    lock_organization(db, organization_id)
    row = db.scalar(
        select(TeamSubscription).where(TeamSubscription.id == str(sid))
        .with_hint(TeamSubscription, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .with_for_update().execution_options(populate_existing=True)
    )
    if row is None:
        raise HTTPException(404, "Subscription not found")
    require_live_subscription(row)
    return row


def reconcile(db: Session, row: TeamSubscription, apim: ApimClient, principal: Principal) -> None:
    lock_organization(db, row.organization_id)
    db.refresh(row)
    require_live_subscription(row)
    try:
        if row.apim_pending_operation:
            apim.resolve_subscription_operation(row.id, row.apim_pending_operation)
            row.apim_pending_operation = None
        # PUT is idempotent; ownership is durable before any key becomes usable.
        apim.ensure(row.id, row.name, row.desired_state)
    except ApimError as exc:
        if exc.pending_operation:
            row.apim_pending_operation = exc.pending_operation
        row.state = "failed"
        audit(db, principal, "subscription.provision.failed", row.id, row.organization_id)
        db.commit()
        log.warning("APIM reconciliation failed subscription=%s status=%s", row.id, exc.status_code)
        raise HTTPException(502, "APIM operation failed; subscription reconciliation is required") from exc
    row.state = row.desired_state
    if getattr(getattr(apim, "settings", None), "model_access_enabled", False):
        from aiflux.model_access import queue
        queue(db)
        if row.desired_state == "active":
            # APIM may already be active, but portal keys are not ready until
            # the trusted binding snapshot is applied and read back.
            row.state = "pending"
    audit(db, principal, "subscription.reconciled", row.id, row.organization_id)
    db.commit()


def create_subscription(
    db: Session,
    principal: Principal,
    payload: SubscriptionCreate,
    idempotency_key: UUID,
    apim: ApimClient,
    organization_id: str | None = None,
) -> TeamSubscription:
    organization_id = organization_id or principal.organization_id
    lock_organization(db, organization_id)
    sid = str(uuid5(NAMESPACE_URL, f"aiflux:{organization_id}:{idempotency_key}"))
    row = db.get(TeamSubscription, sid, populate_existing=True)
    if row is not None:
        require_live_subscription(row)
        if row.name != payload.name or row.team != payload.team:
            raise HTTPException(409, "Idempotency key already used with a different request")
        if row.state in ("pending", "failed"):
            reconcile(db, row, apim, principal)
        return row
    team_id = team_identity(organization_id, payload.team)
    if db.get(Team, team_id) is None:
        db.add(Team(id=team_id, organization_id=organization_id, name=payload.team))
        db.flush()
    row = TeamSubscription(
        id=sid,
        organization_id=organization_id,
        name=payload.name,
        team=payload.team,
        team_id=team_id,
        idempotency_key=str(idempotency_key),
        state="pending",
        desired_state="active",
    )
    db.add(row)
    audit(db, principal, "subscription.requested", row.id, organization_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(TeamSubscription, sid, populate_existing=True)
        if existing is None:
            raise
        if existing.name != payload.name or existing.team != payload.team:
            raise HTTPException(409, "Idempotency key already used with a different request") from None
        row = existing
        require_live_subscription(row)
    reconcile(db, row, apim, principal)
    return row
