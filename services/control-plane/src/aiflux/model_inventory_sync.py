"""Explicit audited reconciliation. Never run as startup seeding or gateway publish."""
import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from aiflux.auth import Principal
from aiflux.catalog import Catalog
from aiflux.config import Settings
from aiflux.external_inventory import AcceptedInventory
from aiflux.models import ManagedModelEndpoint, ModelRouterConfig
from aiflux.turnstile_exchange import audit


def sync_verified_models(
    db: Session, settings: Settings, principal: Principal, *, reconcile_router: bool = True,
) -> dict:
    """Reconcile accepted model metadata only when explicitly invoked.

    Additive release callers can opt out of all router reads/reconciliation;
    existing callers retain historical router behavior. No subscription gates,
    startup hooks, permissions or gateway publication are introduced here.
    """
    inventory = AcceptedInventory.load(settings)
    aliases = inventory.accepted_aliases(settings)
    if not aliases:
        raise HTTPException(409, "No gateway-verified routes to synchronize")
    catalog = Catalog.load(settings.catalog_path) if not reconcile_router else None
    changed = []
    for alias in sorted(aliases):
        route = inventory.route(alias)
        assert route is not None
        provider = inventory.provider(alias)
        row = db.get(ManagedModelEndpoint, alias)
        if row is not None and not reconcile_router:
            continue  # Insert-only chat mode preserves EVERY existing operator column.
        new = row is None
        if row is None:
            region = "unknown"
            if catalog is not None:
                model = next((m for m in catalog.models if m.id == alias and m.enabled
                              and not m.placeholder and "chat" in m.capabilities
                              and inventory.matches_catalog_model(m)), None)
                if model is None or model.provider != provider or not model.region or model.region == "unknown":
                    db.rollback()
                    raise HTTPException(409, "Accepted catalog provider/region required for chat-only sync")
                region = model.region
            row = ManagedModelEndpoint(id=alias, display_name=alias, provider=provider,
                vendor=provider, region=region, enabled=True, coming_soon=False,
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
    router = db.get(ModelRouterConfig, "default") if reconcile_router else None
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
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    # Opt-out deliberately does not inspect router state; do not falsely report
    # that an existing enabled operator router was disabled by chat-only sync.
    return {"changed": changed, "accepted_models": sorted(aliases),
            "auto_enabled": False if reconcile_router else None,
            "gateway_published": False, "prices_changed": False}