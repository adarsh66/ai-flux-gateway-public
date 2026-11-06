"""Platform showback rate card: one rate source for every estimate shown in the portals.

Display and estimates only. It never reads or writes ModelPrice, UsageRecord.cost,
budgets or enforcement, and nothing here is consulted when a subscription is
created or a request is routed, so pricing can never gate access. When no admin
rate exists the bundled public/proxy rates (or labelled platform planning
estimates) apply automatically. The store is the existing versioned
``gateway_settings`` JSON tables under their own scope: no schema change.
"""
import hashlib
import json
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib.resources import files
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from aiflux.auth import Principal
from aiflux.config import Settings
from aiflux.display_pricing import accepted_scope, catalog_price, manifest
from aiflux.external_inventory import AcceptedInventory
from aiflux.models import GatewaySettings, GatewaySettingsRevision
from aiflux.scoring_catalog import is_scoring_model, scoring_descriptor, scoring_manifest, scoring_scope

log = logging.getLogger(__name__)

SCOPE = "rate-card"
MAX_REVISIONS_PER_MODEL = 12
MAX_RATE = Decimal("100000")
FIELDS = ("input", "output", "cached", "write")
CONFIGURED_SOURCE = "Administrator-configured rate"


class RateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=100)
    input: str = Field(max_length=40)
    output: str | None = Field(default=None, max_length=40)
    cached: str | None = Field(default=None, max_length=40)
    write: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def billing_dimensions(self) -> "RateInput":
        if is_scoring_model(self.model):
            if any(getattr(self, f) is not None for f in ("output", "cached", "write")):
                raise ValueError("Scoring rates support input tokens only")
        elif self.output is None:
            raise ValueError("Chat rates require output")
        return self


class RateCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=500)
    rates: list[RateInput] = Field(min_length=1, max_length=200)


class RateRow(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model: str
    model_kind: Literal["chat", "scoring"] = "chat"
    billing_dimensions: list[str] = Field(default_factory=lambda: ["input", "output"])
    provider: str
    region: str
    model_version: str
    sku: str
    origin: str
    note: str | None = None
    source_url: str | None = None
    input: str | None = None
    output: str | None = None
    cached: str | None = None
    write: str | None = None
    default_input: str | None = None
    default_output: str | None = None
    default_cached: str | None = None
    default_write: str | None = None
    configured_from: datetime | None = None


class RateCardOutput(BaseModel):
    version: int
    revision: str
    currency: str = "USD"
    unit: str = "per_million_tokens"
    items: list[RateRow]
    total: int
    changed: bool = False
    auto_pricing: dict[str, Any] | None = None


@lru_cache(maxsize=1)
def defaults() -> dict[str, Any]:
    data = json.loads(files("aiflux").joinpath("pricing/default-estimates-20261030.json").read_bytes())
    for rate in data["rates"]:
        for field in FIELDS:
            if field in rate:
                parse_rate(rate[field])
    return data


def parse_rate(value: Any) -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Rates must be decimal numbers") from exc
    if not number.is_finite() or number < 0 or number > MAX_RATE:
        raise ValueError("Rates must be between 0 and 100000 USD per million tokens")
    if number.as_tuple().exponent < -8:  # type: ignore[operator]
        raise ValueError("Rates support at most 8 decimal places")
    return number


def fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def key_of(rate: dict[str, Any]) -> tuple[str, str, str]:
    return rate["model"], rate["provider"], rate["region"]


@lru_cache(maxsize=1)
def base_scopes() -> dict[tuple[str, str, str], dict[str, Any]]:
    """Manifest scopes; unknown tariffs receive a labelled platform estimate if one is bundled."""
    estimates = {key_of(r): r for r in defaults()["rates"]}
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rate in manifest()["rates"]:
        key = key_of(rate)
        if rate.get("status") == "unknown" and key in estimates:
            estimate = estimates[key]
            rate = {
                **rate, "status": "platform_default", "source_model": "Platform planning estimate",
                "assumption": defaults()["assumption"],
                **{f: estimate[f] for f in FIELDS if f in estimate},
            }
        out[key] = rate
    scorer = scoring_descriptor()
    out[key_of(scorer)] = scorer
    return out


def rates_of(rate: dict[str, Any]) -> dict[str, Decimal]:
    return {f: parse_rate(rate[f]) for f in FIELDS if rate.get(f) is not None}


def revision_label(version: int) -> str:
    base = f"{manifest()['revision']}+{defaults()['revision']}"
    return f"{base}+rate-card-v{version}" if version else base


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def load_state(db: Session) -> tuple[int, list[dict[str, Any]]]:
    """Current version and ordered rate entries. Never raises: failure means bundled rates."""
    try:
        head = db.scalar(select(GatewaySettings).where(GatewaySettings.scope == SCOPE))
        if head is None or not head.version:
            return 0, []
        row = db.scalars(select(GatewaySettingsRevision).where(
            GatewaySettingsRevision.scope == SCOPE, GatewaySettingsRevision.version == head.version,
        )).one()
        entries = []
        for raw in json.loads(row.configuration)["entries"]:
            entry = {"model": raw["model"], "provider": raw["provider"], "region": raw["region"],
                     "origin": raw["origin"], "valid_from": _aware(raw["valid_from"])}
            for f in FIELDS:
                if raw.get(f) is not None:
                    parse_rate(raw[f])
                    entry[f] = raw[f]
            scoring = key_of(entry) == key_of(scoring_descriptor())
            if scoring and any(f in entry for f in ("output", "cached", "write")):
                raise ValueError("Scoring rates support input tokens only")
            if "input" not in entry or (not scoring and "output" not in entry):
                raise ValueError("Incomplete rate")
            entries.append(entry)
        entries.sort(key=lambda e: e["valid_from"])
        return head.version, entries
    except (SQLAlchemyError, ValueError, KeyError, TypeError, InvalidOperation):
        log.warning("Rate card unavailable; falling back to bundled rates")
        return 0, []


def periods(
    entries: list[dict[str, Any]], *, model_kind: Literal["chat", "scoring"] = "chat",
) -> list[dict[str, Any]]:
    """Half-open history, separated by billing kind; old SQL callers stay chat-only."""
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for entry in entries:
        by_key.setdefault(key_of(entry), []).append(entry)
    out = []
    for key, base in base_scopes().items():
        if base.get("model_kind", "chat") != model_kind:
            continue
        history = sorted(by_key.get(key, []), key=lambda e: e["valid_from"])
        out.append({**base,
                    **({"valid_from": _aware(base["applicable_from"])} if model_kind == "scoring" else {}),
                    "valid_to": history[0]["valid_from"] if history else None})
        for index, entry in enumerate(history):
            out.append({
                "model": key[0], "provider": key[1], "region": key[2], "status": entry["origin"],
                **({"model_kind": "scoring", "billing_dimensions": ["input"],
                    "applicable_from": base["applicable_from"]} if base.get("model_kind") == "scoring" else {}),
                **{f: entry[f] for f in FIELDS if f in entry}, "valid_from": entry["valid_from"],
                "valid_to": history[index + 1]["valid_from"] if index + 1 < len(history) else None,
            })
    return out


def estimate_args(db: Session, settings: Settings | None = None) -> dict[str, Any]:
    """Read-only estimate inputs using request-bound accepted inventory."""
    version, entries = load_state(db)
    settings = settings if settings is not None else db.info.get("settings")
    # The existing SQL estimator requires chat output counters/rates. Scoring
    # estimates have their own input-only helper, never fabricated output=0.
    return {"periods": periods(entries),
            "revision": revision_label(version),
            "inventory": AcceptedInventory.load(settings) if settings is not None else None}


def effective(entries: list[dict[str, Any]], key: tuple[str, str, str]) -> dict[str, Any] | None:
    """Latest administrator entry for the scope, else None (bundled rate applies)."""
    history = [e for e in entries if key_of(e) == key]
    return max(history, key=lambda e: e["valid_from"]) if history else None


def scoring_effective_estimate(
    version: int, entries: list[dict[str, Any]], input_tokens: int | None, occurred_at: datetime,
) -> dict[str, Any]:
    """Pure Decimal scoring showback using half-open, date-effective rate history.

    Returns estimated_cost_usd (Decimal or None), estimate_basis, and
    pricing_revision. Missing/invalid counters or pre-baseline dates remain
    unestimated; measured zero is valid. No DB reads, writes or chat economics.
    """
    data = scoring_manifest()
    result: dict[str, Any] = {
        "estimated_cost_usd": None, "estimate_basis": "unestimated",
        "pricing_revision": f"{data['revision']}+rate-card-v{version}",
    }
    if (type(input_tokens) is not int or input_tokens < 0
            or occurred_at.tzinfo is None or occurred_at.utcoffset() is None
            or occurred_at < _aware(data["applicable_from"])):
        return result
    key = key_of(scoring_descriptor())
    history = [e for e in entries if key_of(e) == key and e["valid_from"] <= occurred_at]
    rate = max(history, key=lambda e: e["valid_from"]) if history else scoring_descriptor()
    if rate.get("input") is None or any(rate.get(f) is not None for f in ("output", "cached", "write")):
        return result
    try:
        amount = Decimal(input_tokens) * parse_rate(rate["input"]) / Decimal(1_000_000)
    except ValueError:
        return result
    return {**result, "estimated_cost_usd": amount, "estimate_basis": "measured_scoring_input_tokens"}


def display_price(version: int, entries: list[dict[str, Any]], scope: dict[str, Any] | None) -> dict[str, Any] | None:
    """Catalog price for an accepted scope; None only if no rate or estimate exists at all."""
    if scope is None:
        return None
    key = key_of(scope)
    base = base_scopes()[key]
    entry = effective(entries, key)
    if base.get("model_kind") == "scoring":
        data = scoring_manifest()
        configured = entry is not None and entry["origin"] == "configured"
        current = entry if entry is not None else base
        return {
            **base, "input": current["input"], "status": "configured" if configured else base["status"],
            "revision": f"{data['revision']}+rate-card-v{version}",
            "manifest_sha256": data["sha256"], "currency": data["currency"], "unit": data["unit"],
            "checked_at": entry["valid_from"].date().isoformat() if configured else data["checked_at"],
            "source_url": "" if configured else data["sources"][base["source"]],
            "source_model": CONFIGURED_SOURCE if configured else base["source_model"],
            "basis": "Administrator-configured scoring input-token showback rate; not an invoice or "
                     "an access/enforcement rate." if configured else data["basis"],
            "assumptions": data["assumptions"],
            "provenance": deepcopy(data["provenance"]),
            **({"valid_from": entry["valid_from"].isoformat()} if entry is not None else {}),
        }
    if entry is not None and entry["origin"] == "configured":
        data = manifest()
        return {
            "model": key[0], "provider": key[1], "region": key[2], "model_version": base["model_version"],
            "sku": base["sku"], "status": "configured", "source_model": CONFIGURED_SOURCE,
            **{f: entry[f] for f in FIELDS if f in entry},
            "revision": revision_label(version), "currency": "USD", "unit": data["unit"],
            "checked_at": entry["valid_from"].date().isoformat(), "source_url": "",
            "basis": "Showback rate configured by the platform administrator (USD per 1M tokens). "
                     "Estimates only; not an invoice and never used for access or budget enforcement.",
            "assumptions": "", "assumption": "Applies to usage from " + entry["valid_from"].isoformat() + " onward.",
            "valid_from": entry["valid_from"].isoformat(),
        }
    if base.get("status") == "unknown":
        return None
    if base["status"] == "platform_default":
        data, extra = manifest(), defaults()
        return {
            **{k: base[k] for k in ("model", "provider", "region", "model_version", "sku", "source_model")},
            **{f: base[f] for f in FIELDS if f in base}, "status": "platform_default",
            "revision": revision_label(version), "currency": "USD", "unit": data["unit"],
            "checked_at": extra["checked_at"], "source_url": data["sources"][base["source"]],
            "basis": data["basis"], "assumptions": data["assumptions"], "assumption": base["assumption"],
        }
    return catalog_price(*key)


def accepted_scopes(
    settings: Settings, *, inventory: AcceptedInventory | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    inventory = inventory if inventory is not None else AcceptedInventory.load(settings)
    found = []
    for alias in sorted(inventory.accepted_aliases(settings), key=str.lower):
        route = inventory.route(alias)
        if route is None:
            continue
        scope = accepted_scope(inventory, alias, route.backend_model, route.endpoint_url)
        if scope is not None:
            found.append((alias, scope))
    return found


def listed_scopes(settings: Settings) -> list[tuple[str, dict[str, Any]]]:
    """Editable/displayed tariffs; scoring never enters accepted chat scopes."""
    inventory = AcceptedInventory.load(settings)
    found = accepted_scopes(settings, inventory=inventory)
    scope = scoring_scope(settings, inventory)
    if scope is not None:
        found.append((scope["model"], scope))
    return found


def output(settings: Settings, version: int, entries: list[dict[str, Any]], changed: bool = False) -> RateCardOutput:
    items = []
    for alias, scope in listed_scopes(settings):
        key = key_of(scope)
        base = base_scopes()[key]
        entry = effective(entries, key)
        current = entry if entry is not None else base
        unknown = current.get("status") == "unknown"
        configured = entry is not None and entry["origin"] == "configured"
        note = None
        if configured:
            note = "Configured by administrator"
        elif base["status"] == "platform_default":
            note = "Platform planning estimate"
        elif base["status"] in ("sourced_proxy", "tbc"):
            note = "Proxy or unconfirmed public rate"
        items.append(RateRow(
            model=alias, provider=key[1], region=key[2], model_version=scope["model_version"], sku=scope["sku"],
            model_kind=base.get("model_kind", "chat"),
            billing_dimensions=base.get("billing_dimensions", ["input", "output"]),
            origin="configured" if configured else base["status"], note=note,
            source_url=None if configured else (
                scoring_manifest()["sources"][scope["source"]] if base.get("model_kind") == "scoring"
                else manifest()["sources"].get(scope.get("source"))),
            **({} if unknown else {f: current.get(f) for f in FIELDS}),
            **{"default_" + f: base.get(f) for f in FIELDS},
            configured_from=entry["valid_from"] if configured else None,
        ))
    return RateCardOutput(version=version, revision=revision_label(version), items=items, total=len(items), changed=changed)


def get_rate_card(db: Session, settings: Settings) -> RateCardOutput:
    version, entries = load_state(db)
    result = output(settings, version, entries)
    if settings.auto_pricing_sync_enabled:
        from aiflux.auto_pricing import status
        result.auto_pricing = status(db, settings)
    return result


def save_rate_card(
    db: Session, settings: Settings, principal: Principal, payload: RateCardUpdate,
) -> RateCardOutput:
    from aiflux.subscriptions import audit

    scopes = dict(listed_scopes(settings))
    seen: set[str] = set()
    requested: dict[tuple[str, str, str], dict[str, Decimal]] = {}
    for item in payload.rates:
        if item.model not in scopes:
            raise HTTPException(422, "Rates can only be set for listed models")
        if item.model in seen:
            raise HTTPException(422, "Each model may appear once")
        seen.add(item.model)
        try:
            scoring = scopes[item.model].get("model_kind") == "scoring"
            if scoring and any(getattr(item, f) is not None for f in ("output", "cached", "write")):
                raise ValueError("Scoring rates support input tokens only; omit output, cached and write")
            if not scoring and item.output is None:
                raise ValueError("Chat rates require output")
            rates = {"input": parse_rate(item.input)}
            if not scoring:
                rates["output"] = parse_rate(item.output)
            for optional in ("cached", "write"):
                value = getattr(item, optional)
                if value is not None and value.strip() != "":
                    rates[optional] = parse_rate(value)
        except ValueError as error:
            raise HTTPException(422, f"{item.model}: {error}") from error
        requested[key_of(scopes[item.model])] = rates

    head = db.scalar(
        select(GatewaySettings).where(GatewaySettings.scope == SCOPE)
        .with_for_update()
        .with_hint(GatewaySettings, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .execution_options(populate_existing=True)
    )
    current_version = head.version if head else 0
    if current_version != payload.expected_version:
        raise HTTPException(409, "Rates changed; refresh before saving")
    version, entries = load_state(db)
    if version != current_version:
        raise HTTPException(409, "Rate card could not be read; refresh before saving")

    now = datetime.now(UTC)
    added = []
    for key, rates in requested.items():
        base = base_scopes()[key]
        entry = effective(entries, key)
        current = rates_of(entry if entry is not None else base) if (
            entry is not None or base.get("status") != "unknown") else None
        if current == rates:
            continue
        history = [e for e in entries if key_of(e) == key]
        if len(history) + 1 > MAX_REVISIONS_PER_MODEL:
            raise HTTPException(422, f"{key[0]}: revision history limit reached")
        floor = history[-1]["valid_from"] + timedelta(milliseconds=1) if history else now
        base_rates = rates_of(base) if base.get("status") != "unknown" else None
        added.append({
            "model": key[0], "provider": key[1], "region": key[2],
            "origin": base["status"] if base_rates == rates else "configured",
            "valid_from": max(now, floor), **{f: fmt(v) for f, v in rates.items()},
        })
    if not added:
        return output(settings, version, entries)

    all_entries = sorted([*entries, *added], key=lambda e: e["valid_from"])
    new_version = current_version + 1
    stored = json.dumps({"schema": 1, "entries": [
        {**e, "valid_from": e["valid_from"].astimezone(UTC).isoformat()} for e in all_entries]}, sort_keys=True)
    previous = hashlib.sha256(json.dumps(
        [e["valid_from"].isoformat() for e in entries]).encode()).hexdigest()
    try:
        if head is None:
            db.add(GatewaySettings(scope=SCOPE, version=new_version))
            db.flush()
        else:
            result = db.execute(update(GatewaySettings).where(
                GatewaySettings.scope == SCOPE, GatewaySettings.version == current_version,
            ).values(version=new_version))
            if result.rowcount != 1:
                raise HTTPException(409, "Rates changed; refresh before saving")
        db.add(GatewaySettingsRevision(
            scope=SCOPE, version=new_version, configuration=stored,
            reason=(payload.reason or "Rate card update")[:500], object_id=principal.object_id,
            state="published", base_hash=previous, base_etag="rate-card",
        ))
        audit(db, principal, "rate_card.updated", f"{SCOPE}:{new_version}")
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Rates changed; refresh before saving") from error
    return output(settings, new_version, all_entries, changed=True)
