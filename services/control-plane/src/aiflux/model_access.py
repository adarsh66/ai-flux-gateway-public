"""Organization model entitlements, independent of financial and historical data.

No row means current/future models allowed. Only explicit denies are stored.
All writes are admin CAS transactions; reads never seed. Publication is separate.
"""
from datetime import UTC, datetime
import hashlib
import json
import re
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from aiflux.auth import Principal
from aiflux.models import (Organization, OrganizationModelAccess, OrganizationModelAccessRevision,
                           ModelAccessPublication, TeamSubscription, CreditBudget)

MAX_SUBSCRIPTIONS = 200
VARIABLE = "aiflux-model-access-projection"
MODE = "aiflux-model-access-only"


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class AccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0, strict=True)
    denied_models: list[str] = Field(max_length=200)
    auto_enabled: StrictBool = True
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError("An audit reason is required")
        return value.strip()


def organization(db, oid):
    try:
        canonical = str(UUID(oid))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "Canonical organization UUID required") from exc
    if oid != canonical:
        raise HTTPException(422, "Canonical organization UUID required")
    org = db.get(Organization, oid)
    if org is None:
        raise HTTPException(404, "Organization not found")
    return org


def admin(principal):
    if principal.role != "ids_admin":
        raise HTTPException(403, "Administrator access required")


def revision(db, oid):
    head = db.get(OrganizationModelAccess, oid, populate_existing=True)
    if head is None:
        return None
    row = db.scalar(select(OrganizationModelAccessRevision).where(
        OrganizationModelAccessRevision.organization_id == oid,
        OrganizationModelAccessRevision.version == head.version))
    if row is None:
        raise HTTPException(503, "Model access revision is unavailable")
    return row


def preference(db, oid):
    row = revision(db, oid)
    return {"version": row.version if row else 0,
            "denied_models": json.loads(row.denied_models_json) if row else [],
            "auto_enabled": row.auto_enabled if row else True}


def catalog(db, settings, oid=None):
    from aiflux.turnstile_exchange import list_model_garden
    from aiflux.external_pricing import snapshot
    external = {m.id: m.display_price for m in list_model_garden(
        db, settings, include_disabled=True, pricing_context=snapshot(db, oid))}
    return [{"id": m.id, "display_name": m.display_name, "provider": m.vendor,
             "globally_enabled": m.enabled and not m.coming_soon,
             "internal_price_available": bool(m.display_price),
             "external_price_available": bool(external.get(m.id)),
             "model_kind": "chat" if "chat" in m.capabilities and m.id not in {"auto", "Decision-1"} else "informational"}
            for m in list_model_garden(db, settings, include_disabled=True)]


def status(db, oid):
    desired = preference(db, oid)
    out = db.get(ModelAccessPublication, "default", populate_existing=True)
    applied = json.loads(out.applied_json)["organizations"].get(oid) if out and out.applied_json else None
    applied_version = applied["version"] if applied else None
    state = "applied" if applied_version == desired["version"] and out and out.state == "applied" else (
        "error" if out and out.state == "error" else "pending")
    return {**desired, "organization_id": oid, "applied_version": applied_version,
            "state": state, "error": out.error if out else None,
            "applied_sha256": json.loads(out.applied_json)["sha256"] if out and out.applied_json else None,
            "attempts": out.attempts if out else 0,
            "applied_at": out.applied_at if out else None, "next_attempt_at": out.next_attempt_at if out else None}


def get_access(db, settings, principal, oid):
    admin(principal)
    org = organization(db, oid)
    return {**status(db, oid), "organization_enabled": org.enabled, "items": catalog(db, settings, oid)}


def queue(db):
    """Caller holds org transaction. Atomic generation, never a lost JSON update."""
    changed = db.execute(update(ModelAccessPublication).where(ModelAccessPublication.id == "default").values(
        generation=ModelAccessPublication.generation + 1, state="pending", next_attempt_at=None, error=None))
    if changed.rowcount == 0:
        # Two first writers may both observe absence. Isolate that insert race
        # so the losing writer keeps its preference/audit transaction and still
        # increments the winner's durable job rather than rolling it all back.
        try:
            with db.begin_nested():
                db.add(ModelAccessPublication(id="default", generation=1, applied_generation=0, state="pending", attempts=0))
                db.flush()
        except IntegrityError:
            changed = db.execute(update(ModelAccessPublication).where(ModelAccessPublication.id == "default").values(
                generation=ModelAccessPublication.generation + 1, state="pending", next_attempt_at=None, error=None))
            if changed.rowcount != 1:
                raise


def compile_projection(db, aliases, generation=0, override=None):
    """TeamSubscription.id is exactly the APIM resource name in ApimClient.ensure.

    No header, DB row position, inferred org, key value or tenant fallback.
    Bootstrap must separately attest a complete actual APIM inventory.
    """
    aliases = sorted(set(aliases))
    if len(aliases) > 200 or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", a) or a in {"auto", "Decision-1"} for a in aliases):
        raise ValueError("Invalid chat catalog")
    bindings = {}
    rows = db.scalars(select(TeamSubscription).where(
        TeamSubscription.desired_state == "active", TeamSubscription.state.in_(["active", "pending"]),
        TeamSubscription.deleted_at.is_(None), TeamSubscription.deletion_requested_at.is_(None))).all()
    if len(rows) > MAX_SUBSCRIPTIONS:
        raise HTTPException(422, "Model access exceeds 200 subscriptions")
    # Preferences without subscriptions still need a verifiable applied version.
    organizations = db.scalars(select(Organization).where(Organization.deleted_at.is_(None)).order_by(Organization.id)).all()
    if len(organizations) > 200:
        raise HTTPException(422, "Model access exceeds 200 organizations")
    orgs = {org.id: {**(override[1] if override and override[0] == org.id else preference(db, org.id)),
                     "enabled": org.enabled} for org in organizations}
    for sub in rows:
        try:
            sid = str(UUID(sub.id))
        except ValueError as exc:
            raise HTTPException(422, "Unverified APIM subscription binding") from exc
        if sid != sub.id or sid in bindings:
            raise HTTPException(422, "Ambiguous APIM subscription binding")
        org = organization(db, sub.organization_id)
        pref = (override[1] if override and override[0] == org.id else preference(db, org.id))
        bindings[sid] = org.id
        orgs[org.id] = {**pref, "enabled": org.enabled}
    value = {"schema": 1, "generation": generation, "catalog": aliases,
             "catalog_sha256": hashlib.sha256(compact(aliases).encode()).hexdigest(),
             "bindings": bindings, "organizations": orgs}
    value["sha256"] = hashlib.sha256(compact(value).encode()).hexdigest()
    return value


def save_access(db, settings, principal, oid, payload):
    admin(principal)
    organization(db, oid)
    previous = preference(db, oid)
    models = catalog(db, settings)
    aliases = {m["id"] for m in models if m["model_kind"] == "chat"}
    denies = payload.denied_models
    if (len(denies) != len(set(denies)) or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", a) for a in denies)
            or set(denies) - aliases - set(previous["denied_models"])):
        raise HTTPException(422, "Unknown, duplicate or invalid model deny")
    if payload.expected_version != previous["version"]:
        raise HTTPException(409, "Model access changed; reload without discarding your draft")
    next_pref = {"version": previous["version"] + 1, "denied_models": sorted(denies), "auto_enabled": payload.auto_enabled}
    # Whole fragment bound is checked with the actual retained siblings, before any write.
    from aiflux.model_access_publisher import preflight
    callable_aliases = {m["id"] for m in models if m["model_kind"] == "chat" and m["globally_enabled"]}
    preflight(db, compile_projection(db, callable_aliases, override=(oid, next_pref)))
    try:
        if previous["version"]:
            acquired = db.execute(update(OrganizationModelAccess).where(
                OrganizationModelAccess.organization_id == oid,
                OrganizationModelAccess.version == payload.expected_version).values(version=next_pref["version"]))
            if acquired.rowcount != 1:
                raise HTTPException(409, "Model access changed")
        else:
            db.add(OrganizationModelAccess(organization_id=oid, version=1))
            db.flush()
        db.add(OrganizationModelAccessRevision(organization_id=oid, version=next_pref["version"],
            denied_models_json=compact(sorted(denies)), auto_enabled=payload.auto_enabled,
            object_id=principal.object_id, reason=payload.reason))
        queue(db)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Model access changed") from exc
    return get_access(db, settings, principal, oid)


def effective(db, oid):
    """Conservative portal view: pending grants are NOT advertised as usable."""
    org = organization(db, oid)
    if not org.enabled:
        raise HTTPException(403, "Organization is disabled")
    desired = preference(db, oid)
    out = db.get(ModelAccessPublication, "default")
    projection = None
    try:
        if out and out.applied_json:
            projection = json.loads(out.applied_json)
            unsigned = {k: v for k, v in projection.items() if k != "sha256"}
            if (projection["schema"] != 1 or projection["sha256"] != hashlib.sha256(compact(unsigned).encode()).hexdigest()
                    or projection["catalog_sha256"] != hashlib.sha256(compact(projection["catalog"]).encode()).hexdigest()):
                raise ValueError("Invalid applied projection")
        applied = projection["organizations"].get(oid) if projection else None
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(503, "Trusted model access publication is unavailable") from exc
    # No bootstrap means no new grant can honestly be advertised as applied.
    if applied is None:
        return {"denied_models": desired["denied_models"], "auto_enabled": desired["auto_enabled"], "bootstrap_pending": True}
    if not applied["enabled"]:
        # A pending re-enable must not advertise access before publication.
        return {"denied_models": desired["denied_models"], "auto_enabled": False, "bootstrap_pending": True}
    return {"denied_models": sorted(set(desired["denied_models"]) | set(applied["denied_models"])),
            "auto_enabled": desired["auto_enabled"] and applied["auto_enabled"], "bootstrap_pending": False,
            "applied_catalog": projection["catalog"]}


def require_model(db, oid, selected, *, requested=None, globally_enabled=True):
    access = effective(db, oid)
    if access["bootstrap_pending"]:
        raise HTTPException(503, {"code": "model_access_unavailable", "message": "Trusted model access publication is pending"})
    if (not globally_enabled or selected not in access["applied_catalog"] or selected in access["denied_models"]
            or (requested == "auto" and not access["auto_enabled"])):
        raise HTTPException(403, {"code": "model_not_allowed", "message": "Model is not allowed for this organization"})


def filter_items(db, oid, items):
    access = effective(db, oid)
    if access["bootstrap_pending"]:
        return []
    def available(item):
        alias = item.get("id", item.get("model")) if isinstance(item, dict) else getattr(item, "id", getattr(item, "model", None))
        return alias in access["applied_catalog"] and alias not in access["denied_models"]
    return [m for m in items if available(m)]


def authorize_projection(value, subscription_id, selected, *, requested=None):
    """Offline contract oracle; not a substitute for native gateway expressions."""
    try:
        unsigned = {k: v for k, v in value.items() if k != "sha256"}
        assert value["schema"] == 1
        assert value["sha256"] == hashlib.sha256(compact(unsigned).encode()).hexdigest()
        assert value["catalog_sha256"] == hashlib.sha256(compact(value["catalog"]).encode()).hexdigest()
        org = value["organizations"][value["bindings"][subscription_id]]
    except (KeyError, TypeError, AssertionError) as exc:
        raise HTTPException(503, "Model access projection unavailable") from exc
    if not org["enabled"] or (requested == "auto" and not org["auto_enabled"]) or selected not in value["catalog"] or selected in org["denied_models"]:
        raise HTTPException(403, "model_not_allowed")
    return True


def review_legacy(db, oid, aliases):
    """Explicit operator preview only: exact [] restricts all CURRENT aliases.

    Subscription restrictions are conservatively intersected organization-wide.
    Unknown aliases stop for operator review; this never edits financial rows.
    No startup/GET/customer route invokes this helper.
    """
    organization(db, oid)
    aliases = set(aliases)
    denied = set()
    auto_enabled = True
    rows = db.scalars(select(CreditBudget).where(CreditBudget.organization_id == oid)
                      .order_by(CreditBudget.id)).all()
    sources = []
    for row in rows:
        try:
            allowed = json.loads(row.allowed_models_json)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "Malformed legacy restrictions require operator review") from exc
        if not isinstance(allowed, list) or any(not isinstance(a, str) for a in allowed) or len(allowed) != len(set(allowed)):
            raise HTTPException(422, "Ambiguous legacy restrictions require operator review")
        if "*" in allowed:
            if allowed != ["*"]:
                raise HTTPException(422, "Mixed wildcard restrictions require operator review")
        else:
            if set(allowed) - aliases - {"auto"}:
                raise HTTPException(422, "Unknown legacy aliases require operator review")
            denied |= aliases - set(allowed)
            auto_enabled = auto_enabled and "auto" in allowed
        sources.append({"budget_id": row.id, "subscription_id": row.subscription_id, "allowed_models": allowed})
    result = {"organization_id": oid, "denied_models": sorted(denied), "auto_enabled": auto_enabled, "sources": sources}
    result["review_sha256"] = hashlib.sha256(compact(result).encode()).hexdigest()
    return result


def import_legacy(db, settings, principal, oid, *, expected_version, reviewed_sha256, reason):
    """Requires exact reviewed preview hash + CAS; replaying the same import is a no-op."""
    admin(principal)
    aliases = [m["id"] for m in catalog(db, settings) if m["model_kind"] == "chat"]
    preview = review_legacy(db, oid, aliases)
    if reviewed_sha256 != preview["review_sha256"]:
        raise HTTPException(409, "Legacy review changed; review again")
    receipt = f"legacy-import:{reviewed_sha256}"
    prior = db.scalar(select(OrganizationModelAccessRevision).where(
        OrganizationModelAccessRevision.organization_id == oid,
        OrganizationModelAccessRevision.reason == receipt))
    if prior:
        return get_access(db, settings, principal, oid)
    if not reason.strip():
        raise HTTPException(422, "Operator reason required")
    return save_access(db, settings, principal, oid, AccessUpdate(expected_version=expected_version,
        denied_models=preview["denied_models"], auto_enabled=preview["auto_enabled"], reason=receipt))