"""Rate-card projection only: durable latest-desired reconciliation, no inference.

The dev-unified settings head is the shared publisher mutex. Its revision JSON
owns publication metadata; rate-card revisions remain the only editable rates.
No financial rows, routing pool, identity or API policy are written here.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import re
from typing import Any, Literal, NotRequired, TypedDict, cast
import xml.etree.ElementTree as ET

from sqlalchemy import update
from sqlalchemy.orm import Session

from aiflux import auto_snapshot, rate_card
from aiflux.apim import ApimClient, ApimError
from aiflux.config import Settings
from aiflux.models import GatewaySettings, GatewaySettingsRevision

log = logging.getLogger(__name__)
SCOPE = "dev-unified"
FIELD = "auto_pricing"
VARIABLE = "aiflux-auto-price-projection"
MODE = "aiflux-auto-price-only"
MAX_PROJECTION_BYTES = 24576


class ProjectedPrice(TypedDict):
    input: str
    output: str
    cached: NotRequired[str]
    write: NotRequired[str]
    status: str
    revision: str
    source_url: str
    source_model: str
    currency: Literal["USD"]
    unit: Literal["per_million_tokens"]


class PriceProjection(TypedDict):
    schema: Literal[1]
    pool_version: str
    rate_card_version: int
    revision: str
    source: Literal["rate-card", "packaged-default"]
    prices: dict[str, ProjectedPrice | None]
    sha256: str


def enabled(settings: Settings) -> bool:
    return (settings.auto_pricing_sync_enabled and settings.auto_routing_enabled
            and settings.gateway_controls_poc_enabled
            and not settings.gateway_controls_v2_enabled
            and settings.gateway_settings_scopes == [SCOPE])


def compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def validate_projection(value: Any) -> PriceProjection:
    """Closed gateway-partner contract; no arbitrary XML/expression fields.

    Hash covers compact sorted ASCII JSON WITHOUT sha256. Null means unknown,
    omitted cache dimensions mean unpriced, and decimal strings preserve zero.
    The gateway additionally compares pool_version and its exact six alias IDs.
    """
    keys = {"schema", "pool_version", "rate_card_version", "revision", "source", "prices", "sha256"}
    if (not isinstance(value, dict) or set(value) != keys
            or type(value["schema"]) is not int or value["schema"] != 1
            or type(value["rate_card_version"]) is not int or value["rate_card_version"] < 0
            or value["source"] != ("rate-card" if value["rate_card_version"] else "packaged-default")
            or not isinstance(value["pool_version"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["pool_version"])
            or not isinstance(value["prices"], dict) or len(value["prices"]) != 6):
        raise ValueError("Invalid Auto pricing envelope")
    for alias, price in value["prices"].items():
        if (not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", alias)
                or alias in {"auto", "Decision-1"}):
            raise ValueError("Invalid Auto pricing alias")
        if price is None:
            continue
        required = {"input", "output", "status", "revision", "source_url", "source_model", "currency", "unit"}
        if (not isinstance(price, dict) or not required <= set(price)
                or set(price) - required - {"cached", "write"}
                or price["currency"] != "USD" or price["unit"] != "per_million_tokens"
                or price["status"] not in {"configured", "public_list", "sourced_proxy", "tbc", "platform_default"}):
            raise ValueError("Invalid Auto projected price")
        for field in rate_card.FIELDS:
            if field in price:
                if not isinstance(price[field], str):
                    raise ValueError("Auto rates must be decimal strings")
                rate_card.parse_rate(price[field])
        for field in ("revision", "source_url", "source_model"):
            if not isinstance(price[field], str) or len(price[field]) > 2048:
                raise ValueError("Invalid Auto price provenance")
    if not isinstance(value["revision"], str) or not 1 <= len(value["revision"]) <= 2048:
        raise ValueError("Invalid Auto pricing revision")
    unhashed = {k: v for k, v in value.items() if k != "sha256"}
    if value["sha256"] != hashlib.sha256(compact(unhashed).encode()).hexdigest():
        raise ValueError("Invalid Auto pricing hash")
    if len(compact(value).encode()) > MAX_PROJECTION_BYTES:
        raise ValueError("Auto pricing projection exceeds supported capacity")
    return cast(PriceProjection, value)


def projection(settings: Settings, version: int, entries: list[dict[str, Any]]) -> PriceProjection:
    """Use EXACT catalog accepted scope and display_price, including zero/null."""
    snapshot = auto_snapshot.defaults(settings)
    scopes = dict(rate_card.accepted_scopes(settings))
    prices = {}
    for candidate in snapshot["candidates"]:
        alias = candidate["id"]
        price = rate_card.display_price(version, entries, scopes.get(alias))
        prices[alias] = None if price is None else {
            **{f: rate_card.fmt(rate_card.parse_rate(price[f]))
               for f in rate_card.FIELDS if price.get(f) is not None},
            "status": price["status"], "revision": price["revision"],
            "source_url": price.get("source_url", ""),
            "source_model": price.get("source_model", ""),
            "currency": "USD", "unit": "per_million_tokens",
        }
    value = {"schema": 1, "pool_version": snapshot["version"],
             "rate_card_version": version, "revision": rate_card.revision_label(version),
             "source": "rate-card" if version else "packaged-default",
             "prices": prices}
    value["sha256"] = hashlib.sha256(compact(value).encode()).hexdigest()
    return validate_projection(value)


def envelope(controls: str, price: PriceProjection | None) -> str:
    """Price-only inclusion never executes the formerly detached quota/safety."""
    from aiflux.settings_envelope import parse, render
    plain, _, access = parse(controls)
    if price is not None:
        validate_projection(price)
    return render(plain, price, access)


def _legacy_envelope(controls: str, price: PriceProjection | None) -> str:
    original = ET.fromstring(controls)
    if original.tag != "fragment":
        raise ValueError("Expected settings fragment")
    if price is None:
        return controls
    validate_projection(price)
    root = ET.Element("fragment")
    choose = ET.SubElement(root, "choose")
    when = ET.SubElement(choose, "when", condition=(
        '@(context.Variables.GetValueOrDefault<bool>("' + MODE + '", false))'))
    encoded = compact(price).replace('"', '""')
    # Verbatim C# string: @(@"...") after XML escaping.
    ET.SubElement(when, "set-variable", name=VARIABLE, value='@(@"' + encoded + '")')
    otherwise = ET.SubElement(choose, "otherwise")
    for child in original:
        otherwise.append(deepcopy(child))
    result = ET.tostring(root, encoding="unicode")
    if len(result.encode()) > 65536:
        raise ValueError("Shared settings fragment exceeds 64KiB")
    return result


def controls_only(value: str) -> str:
    from aiflux.settings_envelope import parse
    return parse(value)[0]


def _legacy_controls_only(value: str) -> str:
    root = ET.fromstring(value)
    if root.tag != "fragment":
        raise ValueError("Expected settings fragment")
    if len(root) == 1 and root[0].tag == "choose":
        choose = root[0]
        if (len(choose) == 2 and choose[0].tag == "when" and choose[1].tag == "otherwise"
                and len(choose[0]) == 1 and choose[0][0].get("name") == VARIABLE):
            expected = '@(context.Variables.GetValueOrDefault<bool>("' + MODE + '", false))'
            if (root.attrib or choose.attrib or choose[1].attrib
                or choose[0].attrib != {"condition": expected}
                or choose[0][0].tag != "set-variable"
                or set(choose[0][0].attrib) != {"name", "value"}
                or len(choose[0][0])):
                raise ValueError("Unknown shared fragment envelope")
            out = ET.Element("fragment")
            for child in choose[1]:
                out.append(deepcopy(child))
            return ET.tostring(out, encoding="unicode")
    return value


def metadata(row: GatewaySettingsRevision | None) -> dict[str, Any]:
    return json.loads(row.configuration).get(FIELD, {}) if row else {}


def store(row: GatewaySettingsRevision, state: dict[str, Any]) -> None:
    value = json.loads(row.configuration)
    value[FIELD] = state
    row.configuration = compact(value)


def status(db: Session, settings: Settings) -> dict[str, Any]:
    from aiflux.gateway_settings import revision_at
    head = db.get(GatewaySettings, SCOPE)
    row = revision_at(db, SCOPE, head.version) if head and head.version else None
    state = metadata(row)
    applied = state.get("applied")
    rate_head = db.get(GatewaySettings, rate_card.SCOPE)
    saved_version = rate_head.version if rate_head else 0
    pending = applied is None or applied.get("rate_card_version") != saved_version or state.get("state") == "pending"
    return {"enabled": enabled(settings), "desired_revision": rate_card.revision_label(saved_version),
            "applied_revision": applied.get("revision") if applied else None,
            "applied_sha256": applied.get("sha256") if applied else None,
            "source": applied.get("source") if applied else "packaged-default",
            "state": "pending" if pending and (state or saved_version) else state.get("state", "default"), "error": state.get("error"),
            "stale": applied is not None and pending,
            "applied_at": state.get("applied_at"),
            "next_attempt_at": state.get("next_attempt_at"),
            "access_gated": False}


def reconcile(db: Session, settings: Settings, apim: ApimClient, *,
              immediate: bool = False, _prepared: bool = False) -> bool:
    """One attempt; next attempt durable and bounded, including ambiguous PUT.

    Hold rate-card then shared-head locks through PUT+readback. Rate saves cannot
    overtake this snapshot, and all POC publishers lock the same shared head.
    Failures never change applied projection or gateway admission.
    """
    if not enabled(settings):
        return False
    from aiflux.gateway_settings import fingerprint, locked_head, render_revision, revision_at
    rate_head = locked_head(db, rate_card.SCOPE)
    if rate_head is None:
        # No persisted prices: the gateway uses its validated packaged fallback.
        # A missing row cannot be locked across replicas; do NOT publish a stale
        # default projection that could overtake the first committed price Save.
        db.rollback()
        return False
    acquired = db.execute(update(GatewaySettings).where(
        GatewaySettings.scope == rate_card.SCOPE, GatewaySettings.version == rate_head.version,
    ).values(version=rate_head.version))
    if acquired.rowcount != 1:
        db.rollback()
        return False
    version, entries = rate_card.load_state(db)
    if version != (rate_head.version if rate_head else 0):
        db.rollback()
        return False  # Never publish defaults over an unreadable saved rate card.
    head = locked_head(db, SCOPE)
    if head is None or not head.version:
        db.rollback()
        return False  # Live release requires an existing owned controls head.
    acquired = db.execute(update(GatewaySettings).where(
        GatewaySettings.scope == SCOPE, GatewaySettings.version == head.version,
    ).values(version=head.version))
    if acquired.rowcount != 1:
        db.rollback()
        return False
    row = revision_at(db, SCOPE, head.version)
    state = deepcopy(metadata(row))
    now = datetime.now(UTC)
    try:
        desired = projection(settings, version, entries)
        changed = state.get("desired", {}).get("sha256") != desired["sha256"]
        if (not immediate and not changed and state.get("next_attempt_at")
                and datetime.fromisoformat(state["next_attempt_at"]) > now):
            db.rollback()
            return False
        state["desired"] = desired
        if changed:
            state["attempts"] = 0
        current, etag = apim.get_settings_fragment(SCOPE)
        # Current known applied OR a crash-completed latest attempt is accepted.
        expected = render_revision(SCOPE, row)
        attempted = state.get("attempted_hash")
        current_hash = fingerprint(current)
        allowed = {fingerprint(expected), attempted, state.get("attempt_predecessor_hash")}
        if row.state != "published":
            allowed.add(row.base_hash)
        if current_hash not in allowed:
            raise ApimError(412)
        target = envelope(current, desired)
        target_hash = fingerprint(target)
        # Persist intent BEFORE the remote effect; release row lock only after
        # commit, then reacquire and recompute latest state on next invocation.
        if current_hash != target_hash and attempted != target_hash:
            state.update(attempted_hash=target_hash, attempt_predecessor_hash=current_hash,
                         state="pending", error=None)
            store(row, state)
            db.commit()
            if _prepared:
                return False  # Hot writers cannot create an unbounded save loop.
            return reconcile(db, settings, apim, immediate=True, _prepared=True)
        if current_hash != target_hash:
            try:
                apim.put_settings_fragment(SCOPE, target, etag)
            except ApimError:
                # Transport/202 ambiguity: only exact readback proves success.
                readback, _ = apim.get_settings_fragment(SCOPE)
                if fingerprint(readback) != target_hash:
                    raise
        readback, read_etag = apim.get_settings_fragment(SCOPE)
        if fingerprint(readback) != target_hash:
            raise ApimError(409)
        state.update(applied=desired, state="applied", error=None, attempts=0,
                     next_attempt_at=None, attempted_hash=None, attempt_predecessor_hash=None,
                     applied_at=now.isoformat())
        store(row, state)
        # Preserve a pending controls revision while rebasing ONLY its pricing
        # envelope predecessor so it cannot overwrite the newly applied prices.
        if row.state != "published":
            row.base_hash, row.base_etag = target_hash, read_etag
        db.commit()
        return True
    except (ApimError, ValueError, ET.ParseError) as exc:
        attempts = min(int(state.get("attempts", 0)) + 1, 10)
        state.update(state="pending", error="Automatic pricing sync pending; last good prices remain active.",
                     attempts=attempts,
                     next_attempt_at=(now + timedelta(seconds=min(300, 5 * 2 ** attempts))).isoformat())
        store(row, state)
        db.commit()
        log.warning("Auto pricing sync pending type=%s status=%s", type(exc).__name__,
                    exc.status_code if isinstance(exc, ApimError) else None)
        return False


def after_save(db: Session, settings: Settings, apim: ApimClient) -> dict[str, Any]:
    """Called only AFTER rate_card.save_rate_card committed its transaction.

    Any optional sync/status failure is informational, never a failed price Save.
    The worker derives latest desired from the committed rate-card on each tick,
    including failures before the shared JSON intent could be committed.
    """
    try:
        reconcile(db, settings, apim, immediate=True)
        return status(db, settings)
    except Exception as exc:
        db.rollback()
        log.warning("Saved rate card; automatic pricing retry pending type=%s", type(exc).__name__)
        return {"enabled": enabled(settings), "state": "pending", "access_gated": False,
                "source": "last-good-or-packaged-default",
                "error": "Rate card saved. Automatic pricing sync will retry."}