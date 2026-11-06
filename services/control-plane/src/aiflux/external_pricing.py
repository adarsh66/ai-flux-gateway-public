"""Independent customer prices. Only initialize_external_baseline reads internal rates.

Writes commit the caller's session (as rate_card does); use a dedicated unit of
work. Revisions are deltas, never rewritten. An inherit event is a reset, not a
copy of today's default: usage always inherits the default at its event time.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from aiflux import rate_card
from aiflux.auth import Principal
from aiflux.config import Settings
from aiflux.models import (
    ExternalPriceCard, ExternalPriceCardRevision, GatewaySettings, GatewaySettingsRevision, Organization,
)

FIELDS = rate_card.FIELDS
Key = tuple[str, str, str]
log = logging.getLogger(__name__)


class ExternalRateUpdate(BaseModel):
    """One full vector; null cache prices mean unknown, never zero or inheritance."""
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=100)
    operation: Literal["set", "unknown", "inherit"] = "set"
    input: str | None = Field(default=None, max_length=40)
    output: str | None = Field(default=None, max_length=40)
    cached: str | None = Field(default=None, max_length=40)
    write: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def vector(self) -> "ExternalRateUpdate":
        if self.operation != "set" and any(getattr(self, f) is not None for f in FIELDS):
            raise ValueError("unknown/inherit must not contain rates")
        if self.operation == "set":
            if self.input is None:
                raise ValueError("set requires input")
            for f in FIELDS:
                if getattr(self, f) is not None:
                    rate_card.parse_rate(getattr(self, f))
        return self


class ExternalCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=500)
    rates: list[ExternalRateUpdate] = Field(min_length=1, max_length=200)


# Explicit alias for integrations naming the envelope after the resource.
ExternalPriceCardUpdate = ExternalCardUpdate


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware UTC-compatible datetime is required")
    return value.astimezone(UTC)


def _stored_time(value: datetime) -> datetime:
    # SQLite drops offsets; persisted timestamps are always UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else _utc(value)


def _owner(organization_id: str | None) -> str:
    if organization_id is None:
        return "default"
    try:
        canonical = str(UUID(organization_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "organization_id must be a full UUID") from exc
    if organization_id != canonical:
        raise HTTPException(422, "organization_id must be a canonical full UUID")
    return "org:" + canonical


def _key(row: dict[str, Any]) -> Key:
    return row["model"], row["provider"], row["region"]


def _metadata(scope: dict[str, Any]) -> dict[str, Any]:
    # Deliberately omit supplier sources, prices, defaults, provenance and URLs.
    allowed = ("model", "provider", "region", "model_version", "sku", "model_kind",
               "billing_dimensions", "input_includes_cached", "usage_input_includes_cached",
               "cache_write_ttl_verified", "max_input_tokens", "applicable_from")
    return {f: deepcopy(scope[f]) for f in allowed if f in scope}


@dataclass(frozen=True)
class PricingContext:
    """Detached read snapshot. Methods never query internal pricing or the DB."""
    organization_id: str | None
    version: int
    revision: str
    at: datetime
    _events: tuple[dict[str, Any], ...]

    def _resolve(self, key: Key, at: datetime, owner: str | None = None) -> dict[str, Any] | None:
        owner = owner or _owner(self.organization_id)
        candidates = [e for e in self._events if e["owner"] == owner
                      and _key(e) == key and e["at"] <= at]
        event = max(candidates, key=lambda e: (e["at"], e["version"], e["ordinal"])) if candidates else None
        if owner != "default" and (event is None or event["operation"] == "inherit"):
            return self._resolve(key, at, "default")
        return event if event and event["operation"] != "inherit" else None

    def estimate_args(self) -> dict[str, Any]:
        """Exact rate_card.estimate_args keyword shape; chat-only half-open periods."""
        periods = []
        for key in sorted({_key(e) for e in self._events}):
            times = sorted({e["at"] for e in self._events if _key(e) == key and e["at"] <= self.at})
            for index, start in enumerate(times):
                event = self._resolve(key, start)
                if event is None or event.get("model_kind") == "scoring":
                    continue
                periods.append({**_metadata(event),
                                **{f: event[f] for f in FIELDS if event.get(f) is not None},
                                "status": "unknown" if event["operation"] == "unknown" else "configured",
                                "valid_from": start,
                                "valid_to": times[index + 1] if index + 1 < len(times) else None})
        return {"periods": periods, "revision": self.revision, "inventory": None}

    def display_price(self, scope: dict[str, Any] | None) -> dict[str, Any] | None:
        if scope is None:
            return None
        event = self._resolve(_key(scope), self.at)
        if event is None or event["operation"] == "unknown":
            return None
        return {**_metadata(event), **{f: event[f] for f in FIELDS if event.get(f) is not None},
                "status": "configured", "revision": self.revision, "currency": "USD",
                "unit": "per_million_tokens", "checked_at": event["at"].date().isoformat(),
                "valid_from": event["at"].isoformat(), "source_url": "",
                "source_model": "Administrator-configured external price",
                "basis": "External customer estimate; not an invoice or an enforcement rate.",
                "assumptions": ""}

    def scoring_estimate(self, tokens: int | None, at: datetime) -> dict[str, Any]:
        at = _utc(at)
        result = {"estimated_cost_usd": None, "estimate_basis": "unestimated",
                  "pricing_revision": self.revision}
        if type(tokens) is not int or tokens < 0:
            return result
        keys = {_key(e) for e in self._events if e.get("model_kind") == "scoring"}
        if len(keys) != 1:
            return result
        event = self._resolve(next(iter(keys)), at)
        if event is None or event["operation"] != "set" or event.get("input") is None:
            return result
        return {**result, "estimated_cost_usd": Decimal(tokens) * Decimal(event["input"]) / 1_000_000,
                "estimate_basis": "measured_scoring_input_tokens"}


def snapshot(db: Session, organization_id: str | None = None, at: datetime | None = None,
             *, strict: bool = False) -> PricingContext:
    return snapshots_for_organizations(db, [organization_id], at, strict=strict)[organization_id]


def snapshots_for_organizations(
    db: Session, organization_ids: list[str | None], at: datetime | None = None,
    *, strict: bool = False,
) -> dict[str | None, PricingContext]:
    """One revision statement for default + requested owners; no cross-org events.

    Keep the single-snapshot savepoint and cutoff semantics. Context methods are
    detached; unavailable storage never falls back to internal prices.
    """
    owners = {_owner(org) for org in organization_ids} | {"default"}
    cutoff = _utc(at) if at is not None else datetime.now(UTC)
    try:
        with db.connection().begin_nested():
            revisions = db.scalars(select(ExternalPriceCardRevision).where(
                ExternalPriceCardRevision.owner.in_(owners),
            ).order_by(ExternalPriceCardRevision.owner, ExternalPriceCardRevision.version)
              .execution_options(autoflush=False)).all()
    except SQLAlchemyError:
        if strict:
            raise
        log.warning("External pricing store unavailable; prices are unknown (no internal fallback)")
        return {org: PricingContext(org, 0, "external:unavailable", cutoff, ()) for org in organization_ids}
    return {org: _context_from_revisions(revisions, org, cutoff) for org in organization_ids}


def _context_from_revisions(revisions, organization_id: str | None, cutoff: datetime) -> PricingContext:
    owner = _owner(organization_id)
    versions = {"default": 0, owner: 0}
    events = []
    for row in revisions:
        if row.owner not in {"default", owner}:
            continue
        data = json.loads(row.delta)
        if _stored_time(row.effective_at) <= cutoff:
            versions[row.owner] = row.version
        for ordinal, raw in enumerate(data["entries"]):
            event = {**raw, "owner": row.owner, "version": row.version,
                     "ordinal": ordinal, "at": rate_card._aware(raw["valid_from"])}
            if event["at"] <= cutoff:
                events.append(event)
    revision = f"external:default:v{versions['default']}"
    if owner != "default":
        revision += f"+{owner}:v{versions[owner]}"
    return PricingContext(organization_id, versions[owner], revision, cutoff, tuple(events))


def estimate_args(db: Session, organization_id: str | None = None) -> dict[str, Any]:
    return snapshot(db, organization_id).estimate_args()


def display_price(db: Session, organization_id: str | None, scope: dict[str, Any] | None) -> dict[str, Any] | None:
    return snapshot(db, organization_id).display_price(scope)


def _output(db: Session, settings: Settings, organization_id: str | None, changed: bool = False) -> rate_card.RateCardOutput:
    context = snapshot(db, organization_id)
    items = []
    for alias, scope in rate_card.listed_scopes(settings):
        event = context._resolve(_key(scope), context.at)
        default = context._resolve(_key(scope), context.at, "default")
        known = event is not None and event["operation"] == "set"
        items.append(rate_card.RateRow(
            model=alias, provider=scope["provider"], region=scope["region"],
            model_version=scope.get("model_version", ""), sku=scope.get("sku", ""),
            model_kind=scope.get("model_kind", "chat"),
            billing_dimensions=scope.get("billing_dimensions", ["input", "output"]),
            origin="configured" if known else "unknown", source_url=None,
            note=("Unknown external price" if not known else
                "Inherited external default" if organization_id is not None and event["owner"] == "default"
                else "Organization override" if organization_id is not None else None),
            configured_from=event["at"] if known else None,
            **{f: event.get(f) if known else None for f in FIELDS},
            **{"default_" + f: default.get(f) if default and default["operation"] == "set" else None
               for f in FIELDS},
        ))
    return rate_card.RateCardOutput(version=context.version, revision=context.revision,
                                   items=items, total=len(items), changed=changed)


def get_external_card(db: Session, settings: Settings, organization_id: str | None = None) -> rate_card.RateCardOutput:
    _owner(organization_id)
    if organization_id is not None and db.get(Organization, organization_id) is None:
        raise HTTPException(404, "Organization not found")
    return _output(db, settings, organization_id)


def _admin(principal: Principal) -> None:
    if principal.role != "ids_admin":
        raise HTTPException(403, "Administrator role required")


def _append(db: Session, owner: str, expected: int, principal: Principal,
            entries: list[dict[str, Any]], reason: str, at: datetime, *, baseline: bool = False,
            provenance: dict[str, Any] | None = None) -> None:
    try:
        if expected == 0:
            db.add(ExternalPriceCard(owner=owner, organization_id=None if owner == "default" else owner[4:], version=1))
            db.flush()
        else:
            result = db.execute(update(ExternalPriceCard).where(
                ExternalPriceCard.owner == owner, ExternalPriceCard.version == expected,
            ).values(version=expected + 1))
            if result.rowcount != 1:
                raise HTTPException(409, "External prices changed; refresh before saving")
        db.add(ExternalPriceCardRevision(
            owner=owner, version=expected + 1, effective_at=at, object_id=principal.object_id,
            delta=json.dumps({"schema": 1, "baseline": baseline, "entries": entries,
                              **({"provenance": provenance} if provenance is not None else {})}, sort_keys=True),
            reason=reason,
        ))
        db.commit()
    except (IntegrityError, HTTPException) as exc:
        db.rollback()
        raise HTTPException(409, "External prices changed; refresh before saving") from exc


def save_external_card(db: Session, settings: Settings, principal: Principal,
                       payload: ExternalCardUpdate, organization_id: str | None = None) -> rate_card.RateCardOutput:
    _admin(principal)
    owner = _owner(organization_id)
    if organization_id is not None and db.get(Organization, organization_id) is None:
        raise HTTPException(404, "Organization not found")
    scopes = dict(rate_card.listed_scopes(settings))
    context = snapshot(db, organization_id, strict=True)
    if context.version != payload.expected_version:
        raise HTTPException(409, "External prices changed; refresh before saving")
    now = datetime.now(UTC)
    # Nondecreasing owner time; version breaks ties for coarse/frozen clocks.
    # Do not publish future microsecond timestamps invisible to the response.
    previous = db.scalar(select(ExternalPriceCardRevision).where(
        ExternalPriceCardRevision.owner == owner,
    ).order_by(ExternalPriceCardRevision.version.desc()))
    if previous is not None:
        now = max(now, _stored_time(previous.effective_at))
    entries, seen = [], set()
    for item in payload.rates:
        if item.model not in scopes:
            raise HTTPException(422, "Rates can only be set for listed models")
        scope = scopes[item.model]
        if owner == "default" and item.operation == "inherit":
            raise HTTPException(422, "The default external card cannot inherit")
        key = _key(scope)
        if key in seen:
            raise HTTPException(422, "Each pricing scope may appear once")
        seen.add(key)
        scoring = scope.get("model_kind") == "scoring"
        if item.operation == "set":
            if scoring and any(getattr(item, f) is not None for f in ("output", "cached", "write")):
                raise HTTPException(422, "Scoring rates support input tokens only")
            if not scoring and item.output is None:
                raise HTTPException(422, "Chat rates require output")
        vector = {f: rate_card.fmt(rate_card.parse_rate(getattr(item, f)))
                  if getattr(item, f) is not None else None for f in FIELDS}
        old = [e for e in context._events if e["owner"] == owner and _key(e) == key]
        latest = max(old, key=lambda e: (e["at"], e["version"], e["ordinal"])) if old else None
        if item.operation == "inherit" and latest is None:
            continue  # An untouched organization already inherits; no empty head.
        if latest and latest["operation"] == item.operation and all(latest.get(f) == vector[f] for f in FIELDS):
            continue
        entries.append({**_metadata(scope), **vector, "operation": item.operation, "valid_from": now.isoformat()})
    if not entries:
        return _output(db, settings, organization_id)
    baseline_row = db.scalar(select(ExternalPriceCardRevision).where(
        ExternalPriceCardRevision.owner == "default", ExternalPriceCardRevision.version == 1,
    ))
    if baseline_row is None or not json.loads(baseline_row.delta).get("baseline"):
        raise HTTPException(409, "External baseline not initialized; run the explicit operator migration")
    _append(db, owner, payload.expected_version, principal, entries, payload.reason or "External price update", now)
    return _output(db, settings, organization_id, changed=True)


def initialize_external_baseline(db: Session, settings: Settings, principal: Principal) -> rate_card.RateCardOutput:
    """Freeze a coherent internal snapshot in one transaction with the external seed."""
    _admin(principal)
    try:
        return _initialize_external_baseline(db, settings, principal)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Pricing changed during initialization; retry the explicit migration") from exc
    except Exception:
        db.rollback()
        raise


def _initialize_external_baseline(db: Session, settings: Settings, principal: Principal) -> rate_card.RateCardOutput:
    """Explicit, idempotent operator write; freeze bundled AND every published historical rate.

    No supplier/source metadata is exported. Malformed internal history aborts
    the transaction rather than silently freezing today's fallback as history.
    """
    _admin(principal)
    existing = db.scalar(select(ExternalPriceCardRevision).where(
        ExternalPriceCardRevision.owner == "default", ExternalPriceCardRevision.version == 1,
    ))
    if existing is not None:
        if json.loads(existing.delta).get("baseline"):
            return _output(db, settings, None)
        raise HTTPException(409, "Default external card already exists; baseline not overwritten")
    bases = deepcopy(rate_card.base_scopes())
    history: dict[tuple[Key, datetime], dict[str, Any]] = {}
    # Match save_rate_card's lock, including SQL Server range locking and
    # refreshing an already-loaded identity-map object. Hold it through commit.
    head = db.scalar(select(GatewaySettings).where(GatewaySettings.scope == rate_card.SCOPE)
                     .with_for_update()
                     .with_hint(GatewaySettings, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
                     .execution_options(populate_existing=True))
    if head is None:
        # PostgreSQL cannot row-lock an absent head. Its unique key serializes
        # this seed against an internal first save (the losing insert conflicts).
        head = GatewaySettings(scope=rate_card.SCOPE, version=0)
        db.add(head)
        db.flush()
    rows = db.scalars(select(GatewaySettingsRevision).where(
        GatewaySettingsRevision.scope == rate_card.SCOPE,
        GatewaySettingsRevision.state == "published",
    ).order_by(GatewaySettingsRevision.version)).all()
    if head.version and not any(r.version == head.version for r in rows):
        raise ValueError("Missing current internal rate revision")
    if any(row.version > head.version for row in rows):
        raise ValueError("Published internal revision exceeds head")
    provenance = {
        "internal_head_version": head.version,
        "raw_configuration_sha256": next((hashlib.sha256(r.configuration.encode("utf-8")).hexdigest()
                                           for r in rows if r.version == head.version), None),
        "frozen_base_sha256": hashlib.sha256(json.dumps(
            [bases[key] for key in sorted(bases)], sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest(),
        "internal_revisions": [{"version": r.version, "raw_configuration_sha256":
                                hashlib.sha256(r.configuration.encode("utf-8")).hexdigest()} for r in rows],
    }
    for row in rows:
        for raw in json.loads(row.configuration)["entries"]:
            key = _key(raw)
            if key not in bases:
                raise ValueError("Historic rate scope has no frozen metadata")
            history[key, rate_card._aware(raw["valid_from"])] = raw
    entries = []
    for key, base in sorted(bases.items()):
        start = rate_card._aware(base.get("applicable_from", rate_card.manifest()["applicable_from"]))
        candidates = [(start, base), *sorted(
            [(at, raw) for (k, at), raw in history.items() if k == key], key=lambda pair: pair[0])]
        for at, raw in candidates:
            scoring = base.get("model_kind") == "scoring"
            unknown = raw.get("status", raw.get("origin")) == "unknown"
            if not unknown and (raw.get("input") is None or (not scoring and raw.get("output") is None)):
                raise ValueError("Incomplete historical rate vector")
            if scoring and any(raw.get(f) is not None for f in ("output", "cached", "write")):
                raise ValueError("Scoring rates support input tokens only")
            entries.append({**_metadata(base), "operation": "unknown" if unknown else "set",
                            "valid_from": at.isoformat(),
                            **{f: rate_card.fmt(rate_card.parse_rate(raw[f]))
                               if not unknown and raw.get(f) is not None else None for f in FIELDS}})
    baseline_at = min(rate_card._aware(e["valid_from"]) for e in entries) if entries else datetime.now(UTC)
    _append(db, "default", 0, principal, entries, "Explicit frozen external baseline", baseline_at,
            baseline=True, provenance=provenance)
    return _output(db, settings, None, changed=True)