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


@lru_cache(maxsize=1)
def manifest() -> dict[str, Any]:
    raw = files("aiflux").joinpath("pricing/rates-20261027.json").read_bytes()
    data = json.loads(raw)
    seen = set()
    for rate in data["rates"]:
        key = (rate["model"], rate["provider"], rate["region"])
        if key in seen or rate["source"] not in data["sources"]:
            raise ValueError("Invalid display rate scope")
        seen.add(key)
        if rate.get("status") == "unknown":
            if any(field in rate for field in ("input", "output", "cached", "write")):
                raise ValueError("Unknown tariff must not carry invented rates")
        elif not all(field in rate for field in ("input", "output")):
            raise ValueError("Priced tariff requires input and output rates")
        for field in ("input", "output", "cached", "write"):
            if field in rate and (not Decimal(rate[field]).is_finite() or Decimal(rate[field]) < 0):
                raise ValueError("Invalid display rate")
    data["sha256"] = hashlib.sha256(raw).hexdigest()
    return data


def catalog_price(model: str, provider: str, region: str) -> dict[str, Any] | None:
    data = manifest()
    for rate in data["rates"]:
        if (rate["model"], rate["provider"], rate["region"]) == (model, provider, region):
            if rate.get("status") == "unknown":
                return None  # Existing UI explicitly renders unknown, not free.
            return {
                **rate, "revision": data["revision"], "manifest_sha256": data["sha256"],
                "currency": "USD", "unit": data["unit"], "checked_at": data["checked_at"],
                "source_url": data["sources"][rate["source"]], "basis": data["basis"],
                "assumptions": data["assumptions"], "applicable_from": data["applicable_from"],
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
        if (route.model_name != rate.get("deployment_model", rate["model"]) or route.model_version != rate["model_version"]
                or (deployment.sku is not None and deployment.sku != rate["sku"])):
            return None
    return catalog_price(model, provider, rate["region"])


def estimate_expressions():
    """Reviewed manifest CASE, bounded query size; no per-record rate queries."""
    data = manifest()
    valid = and_(
        U.occurred_at >= datetime.fromisoformat(data["applicable_from"].replace("Z", "+00:00")),
        U.input_tokens >= 0, U.output_tokens >= 0,
        U.status_code >= 200, U.status_code < 300, U.completeness.in_(ELIGIBLE),
        or_(U.cached_input_tokens.is_(None), U.cached_input_tokens >= 0),
        or_(U.cache_write_tokens.is_(None), U.cache_write_tokens >= 0),
        func.coalesce(cast(U.cached_input_tokens, BigInteger), 0)
        + func.coalesce(cast(U.cache_write_tokens, BigInteger), 0) <= cast(U.input_tokens, BigInteger),
    )
    amounts, approximations = [], []
    for rate in data["rates"]:
        if rate.get("status") == "unknown":
            continue  # Measured tokens remain reportable, cost remains unknown.
        scope = and_(valid, U.model == rate["model"], U.provider == rate["provider"], U.region == rate["region"])
        if "max_input_tokens" in rate:
            scope = and_(scope, U.input_tokens <= rate["max_input_tokens"])
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
            (inp - U.cached_input_tokens - U.cache_write_tokens) * Decimal(rate["input"])
            + out * Decimal(rate["output"])
            + U.cached_input_tokens * Decimal(rate.get("cached", "0"))
            + U.cache_write_tokens * Decimal(rate.get("write", "0"))
        )
        amounts.append((scope, cast(case((cache_known, detailed), else_=standard) / Decimal(1_000_000), MONEY)))
        approximations.append((scope, case((cache_known, 0), else_=1)))
    return case(*amounts, else_=None), case(*approximations, else_=0)


def estimate_summary(db: Session, conditions: list, *groups) -> list[dict[str, Any]]:
    amount, approximate = estimate_expressions()
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
            "approximate_requests": approx or 0, "pricing_revision": manifest()["revision"],
        })
    return results


def detail_estimates(db: Session, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    amount, approximate = estimate_expressions()
    return {
        row.id: {"estimated_cost_usd": format(cost, ".12f") if cost is not None else None,
                 "estimate_basis": "standard_input_approximation" if approx else (
                     "measured_cache_detail" if cost is not None else "unestimated"),
                 "pricing_revision": manifest()["revision"]}
        for row, cost, approx in db.execute(select(U, amount, approximate).where(U.id.in_(ids)))
    }