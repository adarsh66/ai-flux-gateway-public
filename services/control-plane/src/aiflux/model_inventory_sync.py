"""Explicit audited reconciliation. Never run as startup seeding or gateway publish."""
import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from aiflux.auth import Principal
from aiflux.config import Settings
from aiflux.external_inventory import AcceptedInventory
from aiflux.models import ManagedModelEndpoint, ModelRouterConfig
from aiflux.turnstile_exchange import audit


def sync_verified_models(db: Session, settings: Settings, principal: Principal) -> dict:
    inventory = AcceptedInventory.load(settings)
    aliases = inventory.accepted_aliases(settings)
    if not aliases:
        raise HTTPException(409, "No gateway-verified routes to synchronize")
    changed = []
    for alias in sorted(aliases):
        route = inventory.route(alias)
        assert route is not None
        provider = inventory.provider(alias)
        row = db.get(ManagedModelEndpoint, alias)
        new = row is None
        if row is None:
            row = ManagedModelEndpoint(id=alias, display_name=alias, provider=provider,
                vendor=provider, region="unknown", enabled=True, coming_soon=False,
                context_window=1024, description="Verified chat route. Context limit and pricing not verified.")
            db.add(row)
        # Routing metadata only: retain existing operator prices, display names,
        # priority, enable/disable decisions, safety settings and unrelated rows.
        values = {"backend_model": route.backend_model, "endpoint_url": route.endpoint_url,
                  "max_completion_tokens": route.max_completion_tokens,
                  "capabilities_json": json.dumps(route.capabilities)}
        if new or any(getattr(row, field) != value for field, value in values.items()):
            for field, value in values.items():
                setattr(row, field, value)
            row.updated_at = datetime.now(UTC)
            audit(db, principal, "model_inventory.synchronized", alias)
            changed.append(alias)
    router = db.get(ModelRouterConfig, "default")
    if router is not None:
        candidates = json.dumps(sorted(aliases))
        default = router.default_model if router.default_model in aliases else (
            "gpt-5.6-luna" if "gpt-5.6-luna" in aliases else sorted(aliases)[0])
        if router.enabled or router.candidate_models_json != candidates or router.default_model != default:
            router.enabled = False  # Deployment of Decision-1 is not integration evidence.
            router.candidate_models_json = candidates
            router.default_model = default
            router.updated_at = datetime.now(UTC)
            audit(db, principal, "model_inventory.router_reconciled", router.id)
            changed.append("router:default")
    db.commit()
    return {"changed": changed, "accepted_models": sorted(aliases), "auto_enabled": False,
            "gateway_published": False, "prices_changed": False}