"""Single bounded attempt against the existing fragment; never an API policy.

Lock shared settings head before outbox. Intent committed before remote effect;
reacquisition recompiles latest state. ETag/readback reconcile ambiguous success.
"""
from datetime import UTC, datetime, timedelta
import json

from fastapi import HTTPException
from sqlalchemy import select, update

from aiflux.apim import ApimError
from aiflux.models import GatewaySettings, ModelAccessPublication, Organization, TeamSubscription
from aiflux import model_access as access
from aiflux.settings_envelope import parse, render

SCOPE = "dev-unified"


def preflight(db, projection):
    from aiflux.gateway_settings import revision_at
    from aiflux.poc_controls import render as controls
    from aiflux.schemas import PocGatewayConfiguration
    head = db.get(GatewaySettings, SCOPE)
    row = revision_at(db, SCOPE, head.version) if head and head.version else None
    stored = json.loads(row.configuration) if row else {}
    try:
        render(controls(PocGatewayConfiguration.model_validate(stored.get("configuration", {})), stored.get("bindings", [])),
               stored.get("auto_pricing", {}).get("applied"), projection)
    except ValueError as exc:
        raise HTTPException(422, "Shared model access fragment exceeds supported capacity") from exc


def reconcile(db, settings, apim, *, immediate=False, prepared=False, bootstrap=False):
    if not getattr(settings, "model_access_enabled", False) and not bootstrap:
        return False
    # Lifecycle lock order precedes shared fragment/outbox locks. Home row first
    # matches identity mutation order. Hold through readback and finalization;
    # a deletion intent committed before reacquisition is compiled out below.
    db.scalars(select(Organization).order_by(
        (Organization.tenant_id == settings.home_tenant_id).desc(), Organization.id,
    ).with_for_update().execution_options(populate_existing=True)).all()
    from aiflux.gateway_settings import locked_head, revision_at, fingerprint, render_revision
    head = locked_head(db, SCOPE)
    if head is None or not head.version:
        db.rollback()
        return False
    db.execute(update(GatewaySettings).where(GatewaySettings.scope == SCOPE).values(version=head.version))
    job = db.scalar(select(ModelAccessPublication).where(ModelAccessPublication.id == "default")
                    .with_for_update().execution_options(populate_existing=True))
    if job is None:
        db.rollback()
        return False
    now = datetime.now(UTC)
    next_at = job.next_attempt_at
    if next_at and next_at.tzinfo is None:
        next_at = next_at.replace(tzinfo=UTC)
    if not immediate and next_at and next_at > now:
        db.rollback()
        return False
    row = revision_at(db, SCOPE, head.version)
    try:
        aliases = [m["id"] for m in access.catalog(db, settings) if m["model_kind"] == "chat" and m["globally_enabled"]]
        desired = access.compile_projection(db, aliases, job.generation)
        # Worker-only comparison, including already-applied jobs. Every catalog
        # mutation/inventory refresh is observed without GET writes or inference
        # fetches. The shared mutex precedes the outbox lock; concurrent queue()
        # increments cannot be overwritten by this publication transaction.
        if job.state == "applied":
            if job.applied_json and json.loads(job.applied_json) == desired:
                db.rollback()
                return False
            access.queue(db)
            db.refresh(job)
            desired = access.compile_projection(db, aliases, job.generation)
        current, etag = apim.get_settings_fragment(SCOPE)
        current_hash = fingerprint(current)
        if current_hash not in {fingerprint(render_revision(SCOPE, row)), job.attempted_hash, job.predecessor_hash}:
            raise ApimError(412)
        controls, price, _ = parse(current)
        target = render(controls, price, desired)
        target_hash = fingerprint(target)
        if current_hash != target_hash and job.attempted_hash != target_hash:
            job.attempted_hash, job.predecessor_hash = target_hash, current_hash
            db.commit()
            return False if prepared else reconcile(db, settings, apim, immediate=True, prepared=True, bootstrap=bootstrap)
        if current_hash != target_hash:
            try:
                apim.put_settings_fragment(SCOPE, target, etag)
            except ApimError:
                if fingerprint(apim.get_settings_fragment(SCOPE)[0]) != target_hash:
                    raise
        readback, _ = apim.get_settings_fragment(SCOPE)
        if fingerprint(readback) != target_hash:
            raise ApimError(409)
        # Defensive CAS as well as row locks: never mark a newer queued job as
        # applied if an adapter releases its lock or a callback queues more work.
        applied_generation = desired["generation"]
        completed = db.execute(update(ModelAccessPublication).where(
            ModelAccessPublication.id == "default",
            ModelAccessPublication.generation == applied_generation).values(
                applied_json=access.compact(desired), applied_generation=applied_generation,
                state="applied", error=None, attempts=0, applied_at=now,
                next_attempt_at=None, attempted_hash=None, predecessor_hash=None))
        if completed.rowcount != 1:
            db.rollback()
            return False
        stored = json.loads(row.configuration)
        stored["model_access"] = {"applied": desired}
        row.configuration = access.compact(stored)
        from aiflux.subscriptions import mark_subscription_ready
        for sid in desired["bindings"]:
            mark_subscription_ready(db, sid)
        db.commit()
        return True
    except (ApimError, ValueError, HTTPException) as exc:
        job.state = "error"
        job.error = "publication_conflict" if isinstance(exc, ApimError) and exc.status_code == 412 else "publication_unavailable"
        job.attempts += 1
        job.next_attempt_at = now + timedelta(seconds=min(300, 5 * 2 ** min(job.attempts, 6)))
        db.commit()
        return False