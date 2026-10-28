"""Azure Functions v1 adapter for the existing versioned gateway publisher."""

import os

import azure.functions as func
from sqlalchemy.orm import Session

from aiflux.apim import ApimClient
from aiflux.config import get_settings
from aiflux.db import engine_for
from aiflux.publication_worker import reconcile_pending


def gateway_publication(timer: func.TimerRequest) -> None:
    if os.environ.get("GATEWAY_PUBLICATION_WORKER_ENABLED", "false").lower() != "true":
        raise RuntimeError("Gateway publication is not approved for activation")
    settings = get_settings()
    if not settings.database_url or not settings.apim_resource_id or not settings.gateway_settings_scopes:
        raise RuntimeError("Configure database, APIM and gateway scopes before activation")
    with Session(engine_for(settings.database_url)) as db:
        reconcile_pending(db, settings, ApimClient(settings))