"""Terminal archive-and-revoke. No hard deletes, inventory ownership, or workers.

Lock order: identity mutations lock the authenticating home organization first,
then target organization. Subscription operations use the target organization.
The latter lock is held THROUGH APIM I/O and final commit. A durable intent is
committed before revocation, then the common lock and fresh row are reacquired.
SQLite ignores FOR UPDATE; its tests cannot establish concurrent correctness.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aiflux.apim import ApimClient, ApimError
from aiflux.auth import Principal
from aiflux.config import Settings
from aiflux.models import LocalUser, Member, Organization, TeamSubscription, utcnow
from aiflux.schemas import DeletionPreview, DeletionRequest, DeletionResult
from aiflux.subscriptions import audit, lock_organization

MODELS = {"organization": Organization, "subscription": TeamSubscription, "local_user": LocalUser, "member": Member}


def lock_identity(db: Session, principal: Principal) -> None:
    """Existing home row provides a durable cross-auth-path administrator mutex."""
    lock_organization(db, principal.organization_id)
    actor = db.scalar(select(Member).where(
        Member.organization_id == principal.organization_id,
        Member.object_id == principal.object_id,
    ).execution_options(populate_existing=True))
    if actor is None or actor.deleted_at or not actor.enabled or actor.role != "ids_admin":
        raise HTTPException(403, "Administrator access is no longer available")


def require_unarchived(row) -> None:
    if row.deleted_at is not None:
        raise HTTPException(409, "Archived records cannot be changed or restored")


def member_blockers(db: Session, principal: Principal, member: Member | None) -> list[str]:
    if member is None:
        return []
    blockers = []
    if member.organization_id == principal.organization_id and member.object_id == principal.object_id:
        blockers.append("Cannot revoke your own account or administrator membership")
    if member.role == "ids_admin" and member.enabled and member.deleted_at is None:
        # Both local JWT and Entra authorize from Member, not LocalUser.role.
        # Archived linked users are explicitly rejected by both auth paths.
        viable = db.scalars(select(Member).join(Organization).where(
            Organization.tenant_id == principal.tenant_id,
            Organization.enabled.is_(True), Organization.deleted_at.is_(None),
            Member.enabled.is_(True), Member.deleted_at.is_(None), Member.role == "ids_admin",
            ~select(LocalUser.id).where(
                LocalUser.organization_id == Member.organization_id,
                LocalUser.object_id == Member.object_id, LocalUser.deleted_at.is_not(None),
            ).exists(),
        )).all()
        if not any(other.id != member.id for other in viable):
            blockers.append("Cannot revoke the last viable platform administrator")
    return blockers


def linked_member(db: Session, user: LocalUser) -> Member | None:
    return db.scalar(select(Member).where(
        Member.organization_id == user.organization_id, Member.object_id == user.object_id,
    ).execution_options(populate_existing=True))


def _row(db: Session, kind: str, entity_id: str):
    row = db.get(MODELS[kind], entity_id, populate_existing=True)
    if row is None:
        raise HTTPException(404, "Record not found")
    return row


def preview(db: Session, settings: Settings, principal: Principal, kind: str, entity_id: str) -> DeletionPreview:
    row = _row(db, kind, entity_id)
    dependencies = {"subscriptions": 0, "users": 0, "members": 0}
    blockers = []
    label = row.email if kind == "local_user" else row.object_id if kind == "member" else row.name
    effect = "Archive and revoke portal access; retain history. This cannot be undone."
    if kind == "organization":
        if row.id == principal.organization_id or row.tenant_id == settings.home_tenant_id:
            blockers.append("Cannot archive the IDS home organization")
        for key, model in (("subscriptions", TeamSubscription), ("users", LocalUser), ("members", Member)):
            dependencies[key] = db.scalar(select(func.count()).select_from(model).where(
                model.organization_id == row.id, model.deleted_at.is_(None),
            )) or 0
        if any(dependencies.values()):
            blockers.append("Archive all subscriptions, local users and memberships first, including disabled or pending records")
        effect = "Archive organization; retain teams, usage, budgets, pricing and audit history."
    elif kind == "member":
        blockers.extend(member_blockers(db, principal, row))
        dependencies["users"] = db.scalar(select(func.count()).select_from(LocalUser).where(
            LocalUser.organization_id == row.organization_id, LocalUser.object_id == row.object_id,
            LocalUser.deleted_at.is_(None),
        )) or 0
        if dependencies["users"]:
            blockers.append("Archive the linked local user first; its membership is archived atomically")
        effect = "Archive this independent membership and revoke portal access. Entra directory account and history are retained."
    elif kind == "local_user":
        blockers.extend(member_blockers(db, principal, linked_member(db, row)))
        # Protect the user even if its linked membership was damaged/missing.
        if row.organization_id == principal.organization_id and row.object_id == principal.object_id and not blockers:
            blockers.append("Cannot revoke your own account or administrator membership")
        effect = "Archive local user and its exact linked membership; revoke existing tokens. Entra account is not deleted."
    else:
        try:
            if str(UUID(row.id)) != row.id or UUID(row.id).int == 0:
                raise ValueError
        except ValueError:
            blockers.append("Only a DB-linked managed UUID subscription can be archived")
        effect = "Immediately block local key actions; suspend and verify the configured APIM subscription before terminal archive. Retain history."
    return DeletionPreview(entity_type=kind, entity_id=row.id, label=label,
                           can_delete=not blockers, blockers=blockers, dependencies=dependencies, effect=effect)


def _stamp(row, principal: Principal, reason: str) -> None:
    row.deleted_at = utcnow()
    row.deleted_by = principal.object_id
    row.deletion_reason = reason
    if hasattr(row, "enabled"):
        row.enabled = False


def archive(db: Session, settings: Settings, principal: Principal, kind: str,
            entity_id: str, payload: DeletionRequest, apim: ApimClient) -> DeletionResult:
    if kind != "subscription":
        lock_identity(db, principal)
    row = _row(db, kind, entity_id)
    oid = row.id if kind == "organization" else row.organization_id
    # Archive retries must also work on disabled orgs; never on archived parents
    # unless the target is already terminal (an idempotent, non-mutating reply).
    if row.deleted_at is None:
        lock_organization(db, oid, allow_disabled=True)
    row = _row(db, kind, entity_id)
    info = preview(db, settings, principal, kind, entity_id)
    if payload.confirmation != info.label:
        raise HTTPException(422, "Typed confirmation must exactly match the record label")
    if not payload.reason.strip():
        raise HTTPException(422, "An audit reason is required")
    if not info.can_delete:
        raise HTTPException(409, {"message": "Archive blocked", "blockers": info.blockers,
                                  "dependencies": info.dependencies.model_dump()})
    if row.deleted_at is not None:
        return DeletionResult(entity_id=row.id, status="archived", message="Already archived; history retained.")
    if kind == "subscription":
        return _revoke(db, principal, row, payload.reason, apim)
    if kind == "local_user":
        member = linked_member(db, row)
        if member is not None and member.deleted_at is None:
            _stamp(member, principal, payload.reason)
    _stamp(row, principal, payload.reason)
    audit(db, principal, f"{kind}.archived", row.id, oid, reason=payload.reason)
    db.commit()
    return DeletionResult(entity_id=row.id, status="archived", message="Archived; access revoked and history retained.")


def _revoke(db: Session, principal: Principal, row: TeamSubscription, reason: str,
            apim: ApimClient) -> DeletionResult:
    sid, oid = row.id, row.organization_id
    if row.deletion_requested_at is None:
        row.deletion_requested_at = utcnow()
        row.deleted_by = principal.object_id
        row.deletion_reason = reason
    row.deletion_status = "pending"
    row.desired_state = "suspended"
    row.state = "pending"
    audit(db, principal, "subscription.deletion.requested", sid, oid, reason=reason)
    db.commit()  # Durable local denial BEFORE external I/O. No network before re-lock.
    lock_organization(db, oid, allow_disabled=True)
    row = db.get(TeamSubscription, sid, populate_existing=True)
    if row.deleted_at is not None:
        return DeletionResult(entity_id=sid, status="archived", message="Already archived; history retained.")
    try:
        # A timed-out/202 activation from an earlier lock holder can finish
        # AFTER its HTTP request returns. Do not submit suspension or certify
        # revocation until that durable operation barrier has settled.
        if row.apim_pending_operation:
            apim.resolve_subscription_operation(sid, row.apim_pending_operation)
            row.apim_pending_operation = None
        # Readback validates exact configured product scope, never owner/inventory.
        current = apim.subscription_state(sid)
        if current is not None and current != "suspended":
            apim.set_state(sid, "suspended")
        verified = apim.subscription_state(sid)
        if verified not in (None, "suspended"):
            row.deletion_status = "pending"
            audit(db, principal, "subscription.deletion.pending", sid, oid, reason=reason)
            db.commit()
            return DeletionResult(entity_id=sid, status="pending",
                                  message="Local access revoked; APIM suspension is not yet verified. Retry deletion.")
    except ApimError as exc:
        if exc.pending_operation:
            row.apim_pending_operation = exc.pending_operation
        row.deletion_status = "failed"
        audit(db, principal, "subscription.deletion.failed", sid, oid, reason=reason)
        db.commit()
        return DeletionResult(entity_id=sid, status="failed",
                              message=("Local access revoked; a prior APIM write has an unknown outcome. Operator reconciliation is required before deletion can be verified."
                                       if row.apim_pending_operation == "unknown" else
                                       "Local access revoked; APIM revocation could not be verified. Retry deletion."))
    # An APIM-only success followed by DB failure remains safely retryable via GET.
    _stamp(row, principal, row.deletion_reason)
    row.state = "suspended"
    row.deletion_status = None
    audit(db, principal, "subscription.archived", sid, oid, reason=reason)
    db.commit()
    return DeletionResult(entity_id=sid, status="archived", message="APIM access revoked and verified; history retained.")