"""Customer-only presentation boundary; never changes accounting or routing."""
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select

from aiflux import display_pricing
from aiflux.models import UsageRecord
from aiflux.schemas import RouterDecisionOutput

INTERNAL_FIELDS = frozenset({
    "cost", "cost_usd", "known_cost", "recorded_cost_usd", "used_credits",
    "remaining_credits", "utilization_pct", "low_credit_alert", "cost_complete",
    "unpriced_requests", "auto_pricing", "source_url", "source_model", "provenance",
    "assumption", "assumptions", "cny_per_usd_assumption",
    "estimated_input_per_million", "estimated_output_per_million",
})


def customer_routing_decision(value: Any) -> dict:
    """Allowlisted routing metadata; internal free-text reasons are not public."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    fields = (
        "requested_model", "selected_model", "display_name", "provider", "vendor",
        "category", "strategy", "decision_endpoint", "confidence",
    )
    return {**{key: customer_safe(value[key]) for key in fields if key in value},
            "reason": "Selected an available model under the configured routing policy."}


def customer_safe(value: Any) -> Any:
    """Strip internal monetary values at every depth, including nested DTOs."""
    if isinstance(value, RouterDecisionOutput):
        return customer_routing_decision(value)
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: (customer_routing_decision(item) if key == "routing_decision" and item is not None
                      else customer_safe(item)) for key, item in value.items()
                if key not in INTERNAL_FIELDS and not key.startswith("default_")}
    if isinstance(value, (list, tuple)):
        return [customer_safe(item) for item in value]
    return value


def estimate_summary(db, conditions, *groups, pricing_context=None):
    if pricing_context is None:
        from aiflux.rate_card import estimate_args
        return display_pricing.estimate_summary(db, conditions, *groups, **estimate_args(db))
    pricing = pricing_context.estimate_args()
    if any(p.get("status") != "unknown" for p in pricing["periods"]):
        return display_pricing.estimate_summary(db, conditions, *groups, **pricing)
    # Empty/all-unknown external timelines must not trigger manifest fallback or
    # generate an invalid empty SQL CASE. Preserve grouping and coverage counts.
    query = select(*groups, func.count()).select_from(UsageRecord).where(*conditions)
    if groups:
        query = query.group_by(*groups)
    return [{"group": tuple(row[:-1]), "estimated_cost_usd": None,
             "estimated_requests": 0, "unestimated_requests": row[-1],
             "approximate_requests": 0, "pricing_revision": pricing_context.revision}
            for row in db.execute(query)]


def detail_estimates(db, ids, *, pricing_context=None):
    if pricing_context is None:
        from aiflux.rate_card import estimate_args
        return display_pricing.detail_estimates(db, ids, **estimate_args(db))
    pricing = pricing_context.estimate_args()
    if any(p.get("status") != "unknown" for p in pricing["periods"]):
        return display_pricing.detail_estimates(db, ids, **pricing)
    return {key: {"estimated_cost_usd": None, "estimate_basis": "unestimated",
                  "pricing_revision": pricing_context.revision} for key in ids}