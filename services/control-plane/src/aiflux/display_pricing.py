"""Immutable public-rate showback. No DML, price seeding or enforcement imports.

Both SQL aggregates and bounded details use the same expression. Existing stored
cost/currency and financial completeness are deliberately never substituted.
"""
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from importlib.resources import files
from typing import Any

from sqlalchemy import BigInteger, Numeric, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from aiflux.models import UsageRecord as U
from aiflux.external_inventory import AcceptedInventory, ExternalRoute

ELIGIBLE = ("complete", "price_missing", "cache_usage_missing", "cache_write_usage_missing")
MONEY = Numeric(38, 12)


def _merge_manifests(raw: bytes, additive_raw: bytes | None = None) -> dict[str, Any]:
    """Merge byte-bound additive scopes without rewriting historical rate metadata.

    Omitting the additive source reproduces the original manifest and digest.
    A present but invalid source is an error, never a silent partial-price load.
    """
    data = json.loads(raw)
    source_hashes = {"rates-20261027.json": hashlib.sha256(raw).hexdigest()}
    if additive_raw is not None:
        extra = json.loads(additive_raw)
        if any(extra[key] != data[key] for key in ("currency", "unit", "applicable_from")):
            raise ValueError("Incompatible additive display rates")
        if data["sources"].keys() & extra["sources"].keys():
            raise ValueError("Duplicate display rate source")
        for rate in extra["rates"]:
            if (not all(isinstance(rate.get(key), str) and rate[key].strip() for key in (
                    "model", "provider", "region", "model_version", "deployment_model", "sku", "source_model"))
                    or rate.get("source") not in extra["sources"]
                    or type(rate.get("input_includes_cached")) is not bool
                    or rate.get("usage_input_includes_cached") is not True
                    or type(rate.get("max_input_tokens")) is not int or rate["max_input_tokens"] <= 0
                    or rate.get("status") not in ("public_list", "sourced_proxy", "platform_default")
                    or not rate.get("context_applicability")):
                raise ValueError("Invalid additive display rate scope")
            if not rate["input_includes_cached"] and rate.get("cache_write_ttl_verified") is not False:
                raise ValueError("Native cache-write TTL must remain explicitly unverified")
            for key in ("basis", "assumptions", "checked_at"):
                rate.setdefault(key, extra[key])
        data["rates"] = [*data["rates"], *extra["rates"]]
        data["sources"] = {**data["sources"], **extra["sources"]}
        data["revision"] += "+" + extra["revision"]
        source_hashes["rates-foundry-eight-20261030.json"] = hashlib.sha256(additive_raw).hexdigest()
    seen = set()
    seen_models = set()
    for rate in data["rates"]:
        key = (rate["model"], rate["provider"], rate["region"])
        if key in seen or rate["model"] in seen_models or rate["source"] not in data["sources"]:
            raise ValueError("Invalid display rate scope")
        seen.add(key)
        seen_models.add(rate["model"])
        if rate.get("status") == "unknown":
            if any(field in rate for field in ("input", "output", "cached", "write")):
                raise ValueError("Unknown tariff must not carry invented rates")
        elif not all(field in rate for field in ("input", "output")):
            raise ValueError("Priced tariff requires input and output rates")
        for field in ("input", "output", "cached", "write"):
            if field in rate and (not Decimal(rate[field]).is_finite() or Decimal(rate[field]) < 0):
                raise ValueError("Invalid display rate")
    data["sha256"] = (hashlib.sha256(raw).hexdigest() if additive_raw is None else hashlib.sha256(
        json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest())
    data["source_sha256"] = source_hashes
    return data


@lru_cache(maxsize=4)
def manifest(include_foundry_eight: bool = True, include_successor22: bool | None = None) -> dict[str, Any]:
    root = files("aiflux").joinpath("pricing")
    raw = root.joinpath("rates-20261027.json").read_bytes()
    additive_raw = None
    if include_foundry_eight:
        try:
            additive_raw = root.joinpath("rates-foundry-eight-20261030.json").read_bytes()
        except FileNotFoundError:
            pass  # Historical packages containing only the original source still work.
    current = _merge_manifests(raw, additive_raw)
    # No activation marker is shipped by source preparation. Future clean
    # accepted22 packaging must opt in explicitly AFTER genuine probe proof.
    # Historical manifest(False) remains byte/digest exact for frozen readers.
    if include_successor22 is None and include_foundry_eight:
        try:
            activation = json.loads(root.joinpath('successor22-activation.json').read_bytes())
        except FileNotFoundError:
            activation = None
        if activation is not None:
            if (activation.get('profile') != 'foundry-successor22-accepted'
                    or not isinstance(activation.get('proof_sha256'), str)
                    or len(activation['proof_sha256']) != 64
                    or any(c not in '0123456789abcdef' for c in activation['proof_sha256'])):
                raise ValueError('Invalid explicit successor22 pricing activation')
            include_successor22 = True
    if include_successor22:
        if not include_foundry_eight or additive_raw is None:
            raise ValueError('Successor22 requires the unchanged existing21 rates')
        ninth_raw = root.joinpath('rates-successor22-20261031.json').read_bytes()
        merged_raw = json.dumps({k: v for k, v in current.items() if k not in ('sha256', 'source_sha256')}).encode()
        merged = _merge_manifests(merged_raw, ninth_raw)
        merged['source_sha256'] = {**current['source_sha256'],
            'rates-successor22-20261031.json': hashlib.sha256(ninth_raw).hexdigest()}
        merged['sha256'] = hashlib.sha256(json.dumps(merged['source_sha256'], sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        return merged
    return current


def catalog_price(model: str, provider: str, region: str) -> dict[str, Any] | None:
    data = manifest()
    for rate in data["rates"]:
        if (rate["model"], rate["provider"], rate["region"]) == (model, provider, region):
            if rate.get("status") == "unknown":
                return None  # Existing UI explicitly renders unknown, not free.
            return {
                **rate, "revision": data["revision"], "manifest_sha256": data["sha256"],
                "currency": "USD", "unit": data["unit"], "checked_at": rate.get("checked_at", data["checked_at"]),
                "source_url": data["sources"][rate["source"]], "basis": rate.get("basis", data["basis"]),
                "assumptions": rate.get("assumptions", data["assumptions"]),
                "applicable_from": data["applicable_from"],
            }
    return None


def accepted_catalog_price(
    inventory: AcceptedInventory, model: str, backend_model: str, endpoint_url: str,
) -> dict[str, Any] | None:
    """Display scope from accepted route provenance, never legacy SQL metadata.

    Inventory has no Foundry region field. A single immutable manifest scope is
    usable only after joining the accepted alias, exact binding, deployment model,
    version and provider. Ambiguous scopes fail closed. Usage estimation retains
    its independent exact provider/region predicates below.
    """
    rate = accepted_scope(inventory, model, backend_model, endpoint_url)
    return catalog_price(model, rate["provider"], rate["region"]) if rate else None


def accepted_scope(
    inventory: AcceptedInventory, model: str, backend_model: str, endpoint_url: str,
) -> dict[str, Any] | None:
    """Manifest scope (priced or unknown) joined to the accepted route, else None."""
    if model not in inventory.accepted_aliases(inventory.settings):
        return None
    route = inventory.route(model)
    if route is None or not inventory.matches(model, backend_model, [endpoint_url]):
        return None
    provider = inventory.provider(model)
    candidates = [r for r in manifest()["rates"] if r["model"] == model and r["provider"] == provider]
    if len(candidates) != 1:
        return None
    rate = candidates[0]
    if isinstance(route, ExternalRoute):
        # ExternalRoute validates the fixed ModelArts upstream and gateway; its
        # region is in that upstream hostname, not persisted garden metadata.
        if (rate["model_version"] != route.backend_model
                or not route.upstream_url.startswith("https://api-" + rate["region"] + ".modelarts-maas.com/")):
            return None
    else:
        deployment = next(d for d in inventory.foundry.deployments
                          if d.id.lower() == route.deployment_id.lower())
        # New scopes have retained ARM SKU evidence; do not treat absent SKU as
        # an exact new binding. Preserve the original13 optional-SKU behavior.
        if "input_includes_cached" in rate and deployment.sku != rate["sku"]:
            return None
        if (route.model_name != rate.get("deployment_model", rate["model"]) or route.model_version != rate["model_version"]
                or (deployment.sku is not None and deployment.sku != rate["sku"])):
            return None
    return rate


def usage_scope(rate: dict[str, Any], inventory: AcceptedInventory | None = None):
    """Read-only attribution: exact stored scope or verified accepted provenance.

    Never replace a known conflicting field, normalize aliases, or infer a scope
    from a tariff alone. Cache validity and history predicates remain independent.
    """
    provider, region = U.provider == rate["provider"], U.region == rate["region"]
    if inventory is not None:
        route = inventory.route(rate["model"])
        accepted = accepted_scope(inventory, rate["model"], route.backend_model, route.endpoint_url) if route else None
        if accepted and (accepted["provider"], accepted["region"]) == (rate["provider"], rate["region"]):
            provider = or_(provider, U.provider.is_(None), U.provider == "unknown", U.provider == "")
            region = or_(region, U.region.is_(None), U.region == "unknown", U.region == "")
    return and_(U.model == rate["model"], provider, region)


def estimate_expressions(periods: list[dict[str, Any]] | None = None, inventory: AcceptedInventory | None = None):
    """Reviewed rate CASE, bounded query size; no per-record rate queries.

    ``periods`` are manifest-shaped rates with optional ``valid_from``/``valid_to``
    (aware datetimes, half-open). Default is the immutable manifest.
    """
    data = manifest()
    if periods is None:
        periods = data["rates"]
    valid = and_(
        U.occurred_at >= datetime.fromisoformat(data["applicable_from"].replace("Z", "+00:00")),
        U.input_tokens >= 0, U.output_tokens >= 0,
        U.status_code >= 200, U.status_code < 300,
        or_(U.cached_input_tokens.is_(None), U.cached_input_tokens >= 0),
        or_(U.cache_write_tokens.is_(None), U.cache_write_tokens >= 0),
    )
    # Configured periods intentionally contain prices only. Recover immutable
    # accounting/applicability for NEW scopes without changing any old13 period.
    additive_scopes = {
        (r["model"], r["provider"], r["region"]): r
        for r in data["rates"] if "input_includes_cached" in r
    }
    amounts, approximations = [], []
    for rate in periods:
        if rate.get("status") == "unknown":
            continue  # Measured tokens remain reportable, cost remains unknown.
        identity = (rate["model"], rate["provider"], rate["region"])
        metadata = additive_scopes.get(identity, rate)
        # Provider-native accounting is provenance, not the persisted usage
        # contract: APIM finops-v1 normalizes Anthropic input to inclusive prompt
        # totals and ingestion stores them verbatim. Never add cache twice.
        native_exclusive = not metadata.get("input_includes_cached", True)
        inclusive = metadata.get("usage_input_includes_cached", metadata.get("input_includes_cached", True))
        attribution_only = literal(False)
        if inventory is not None and identity in additive_scopes:
            route = inventory.route(rate["model"])
            accepted = accepted_scope(inventory, rate["model"], route.backend_model, route.endpoint_url) if route else None
            if accepted and (accepted["provider"], accepted["region"]) == identity[1:]:
                # This completeness reason is NOT generally eligible. Recover
                # only this accepted additive scope, with no known attribution
                # or cache conflict; other completeness reasons remain excluded.
                attribution_only = and_(
                    U.completeness == "backend_attribution_missing",
                    or_(U.provider.is_(None), U.provider.in_(("", "unknown"))),
                    or_(U.region.is_(None), U.region.in_(("", "unknown"))),
                    U.cached_input_tokens.is_not(None), U.cache_write_tokens.is_not(None),
                    literal("cached" in rate) | (U.cached_input_tokens == 0),
                    literal("write" in rate) | (U.cache_write_tokens == 0),
                )
        scope = and_(valid, usage_scope(rate, inventory), or_(U.completeness.in_(ELIGIBLE), attribution_only))
        if rate.get("valid_from") is not None:
            scope = and_(scope, U.occurred_at >= rate["valid_from"])
        if rate.get("valid_to") is not None:
            scope = and_(scope, U.occurred_at < rate["valid_to"])
        cache_total = (func.coalesce(cast(U.cached_input_tokens, BigInteger), 0)
                       + func.coalesce(cast(U.cache_write_tokens, BigInteger), 0))
        context_tokens = cast(U.input_tokens, BigInteger)
        if inclusive:
            scope = and_(scope, cache_total <= context_tokens)
        else:
            context_tokens = context_tokens + cache_total
        if native_exclusive:
            # Normalization requires both native counters. Preserve unknowns
            # and refuse a precise write estimate until its TTL is verified.
            scope = and_(scope, U.cached_input_tokens.is_not(None), U.cache_write_tokens.is_not(None))
            if not metadata.get("cache_write_ttl_verified", True):
                scope = and_(scope, U.cache_write_tokens == 0)
        if "max_input_tokens" in metadata:
            scope = and_(scope, context_tokens <= metadata["max_input_tokens"])
        # Null cache detail never becomes fabricated measured zero. Instead use
        # the explicitly disclosed standard-input approximation for that row.
        cache_known = and_(
            U.cached_input_tokens.is_not(None), U.cache_write_tokens.is_not(None),
            literal("cached" in rate) | (U.cached_input_tokens == 0),
            literal("write" in rate) | (U.cache_write_tokens == 0),
        )
        inp, out = cast(U.input_tokens, MONEY), cast(U.output_tokens, MONEY)
        standard = inp * Decimal(rate["input"]) + out * Decimal(rate["output"])
        detailed = (
            (inp - U.cached_input_tokens - U.cache_write_tokens if inclusive else inp) * Decimal(rate["input"])
            + out * Decimal(rate["output"])
            + U.cached_input_tokens * Decimal(rate.get("cached", "0"))
            + U.cache_write_tokens * Decimal(rate.get("write", "0"))
        )
        if native_exclusive or not inclusive:
            scope = and_(scope, cache_known)
        amounts.append((scope, cast(case((cache_known, detailed), else_=standard) / Decimal(1_000_000), MONEY)))
        approximations.append((scope, case((cache_known, 0), else_=1)))
    return case(*amounts, else_=None), case(*approximations, else_=0)


def estimate_summary(
    db: Session, conditions: list, *groups, periods: list[dict[str, Any]] | None = None,
    revision: str | None = None,
    inventory: AcceptedInventory | None = None,
) -> list[dict[str, Any]]:
    amount, approximate = estimate_expressions(periods, inventory)
    query = select(*groups, func.count(), func.count(amount), func.sum(amount), func.sum(approximate)).where(*conditions)
    if groups:
        query = query.group_by(*groups)
    results = []
    for row in db.execute(query):
        total, estimated, cost, approx = row[-4:]
        results.append({
            "group": tuple(row[:-4]),
            "estimated_cost_usd": format(cost, ".12f") if cost is not None else None,
            "estimated_requests": estimated, "unestimated_requests": total - estimated,
            "approximate_requests": approx or 0, "pricing_revision": revision or manifest()["revision"],
        })
    return results


def detail_estimates(
    db: Session, ids: list[str], periods: list[dict[str, Any]] | None = None,
    revision: str | None = None,
    inventory: AcceptedInventory | None = None,
) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    amount, approximate = estimate_expressions(periods, inventory)
    return {
        row.id: {"estimated_cost_usd": format(cost, ".12f") if cost is not None else None,
                 "estimate_basis": "standard_input_approximation" if approx else (
                     "measured_cache_detail" if cost is not None else "unestimated"),
                 "pricing_revision": revision or manifest()["revision"]}
        for row, cost, approx in db.execute(select(U, amount, approximate).where(U.id.in_(ids)))
    }