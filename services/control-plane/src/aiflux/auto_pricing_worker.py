"""Actual API lifespan reconciliation; durable state survives worker restarts.

Every replica uses the same database row mutex. Only pricing intents are
reconciled here; the disabled legacy controls worker is not activated.
"""
import asyncio
import logging

from sqlalchemy.orm import Session

from aiflux.auto_pricing import enabled, reconcile
from aiflux.apim import ApimClient
from aiflux.config import Settings
from aiflux.db import engine_for

log = logging.getLogger(__name__)


def reconcile_once(settings: Settings, apim: ApimClient) -> bool:
    if not enabled(settings) and not settings.model_access_enabled:
        return False
    with Session(engine_for(settings.database_url), expire_on_commit=False) as db:
        try:
            priced = reconcile(db, settings, apim) if enabled(settings) else False
            if settings.model_access_enabled:
                from aiflux.model_access_publisher import reconcile as reconcile_access
                return reconcile_access(db, settings, apim) or priced
            return priced
        except Exception as exc:
            db.rollback()
            # Fixed exception type only, never DSNs/XML/customer data.
            log.warning("Automatic pricing reconciliation failed type=%s", type(exc).__name__)
            return False


async def run_worker(settings: Settings, apim: ApimClient, stop: asyncio.Event) -> None:
    """One finite attempt per tick, bounded persisted retry backoff, clean stop."""
    while not stop.is_set():
        try:
            await asyncio.to_thread(reconcile_once, settings, apim)
        except Exception as exc:
            # A broken tick cannot permanently kill automatic retry on a replica.
            log.warning("Automatic pricing worker tick failed type=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.auto_pricing_reconcile_seconds)
        except asyncio.TimeoutError:
            pass