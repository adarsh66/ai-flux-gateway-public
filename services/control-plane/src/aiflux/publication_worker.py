"""Retry existing gateway intents; never synthesize releases or provisioning jobs.

Disabled by default. Activation requires an approved runtime publication policy;
the Terraform-only deployment must leave this worker disabled.
"""

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux.apim import ApimClient
from aiflux.auth import Principal
from aiflux.config import Settings
from aiflux.gateway_settings import canonical_scope, publish_settings
from aiflux.models import GatewaySettings, GatewaySettingsRevision, Organization

log = logging.getLogger(__name__)


def reconcile_pending(db: Session, settings: Settings, apim: ApimClient) -> int:
    """Replay only the current persisted intent through the existing CAS publisher.

    Conflicts fail the invocation rather than reporting successful reconciliation.
    Each publisher retains its own transaction/ETag/readback protections.
    """
    org = db.scalar(select(Organization).where(Organization.tenant_id == settings.home_tenant_id))
    if org is None:
        raise RuntimeError("Publication requires the bootstrapped home organization")
    count = 0
    failures = 0
    scopes = sorted({canonical_scope(settings, scope) for scope in settings.gateway_settings_scopes})
    for scope in scopes:
        head = db.get(GatewaySettings, scope)
        if head is None or not head.version:
            continue
        revision = db.scalar(select(GatewaySettingsRevision).where(
            GatewaySettingsRevision.scope == scope,
            GatewaySettingsRevision.version == head.version,
        ))
        if revision is None:
            raise RuntimeError("Current gateway revision is missing; operator review required")
        if revision.state == "published":
            continue
        # Attribute retries to the original request; do not invent an admin identity.
        principal = Principal(org.id, org.name, org.tenant_id, revision.object_id, "admin")
        try:
            publish_settings(db, settings, apim, principal, scope, head.version)
            count += 1
        except HTTPException as exc:
            db.rollback()
            failures += 1
            log.warning("Publication retry failed scope=%s status=%s", scope, exc.status_code)
    if failures:
        raise RuntimeError(f"Gateway publication incomplete for {failures} scope(s)")
    return count