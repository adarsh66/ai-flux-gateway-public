"""Resolver service authentication, deliberately separate from user/local auth."""
from uuid import UUID
from datetime import UTC, datetime
import re

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
import jwt

from aiflux.auth import bearer


def gateway_configuration_ready(settings) -> bool:
    """Shape gate only, never proof the resource exists or MI can obtain a token."""
    try:
        for value in (settings.auto_gateway_principal_id, settings.auto_gateway_client_id, settings.home_tenant_id):
            UUID(value)
        audience = settings.entra_audience
        if audience.startswith("api://"):
            return bool(re.fullmatch(r"api://[A-Za-z0-9][A-Za-z0-9._/-]*", audience))
        UUID(audience)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def require_gateway(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    settings = request.app.state.settings
    if not credentials:
        raise HTTPException(401, "Gateway managed identity required")
    if not gateway_configuration_ready(settings):
        raise HTTPException(503, "Gateway service authentication is not configured")
    try:
        # Never dispatch by unverified issuer/tenant or trust X-* caller headers.
        expected_oid = str(UUID(settings.auto_gateway_principal_id))
        expected_app = str(UUID(settings.auto_gateway_client_id))
        tenant = str(UUID(settings.home_tenant_id))
    except ValueError as exc:
        raise HTTPException(503, "Gateway service authentication is not configured") from exc
    try:
        claims = request.app.state.token_verifier.verify(credentials.credentials, tenant)
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(503, "Gateway signing keys unavailable") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid gateway identity token") from exc
    now = datetime.now(UTC).timestamp()
    if (claims.get("iss") != f"https://login.microsoftonline.com/{tenant}/v2.0"
            or claims.get("aud") != settings.entra_audience
            or type(claims.get("exp")) not in (int, float) or claims["exp"] <= now
            or type(claims.get("nbf")) not in (int, float) or claims["nbf"] > now
            or claims.get("tid") != tenant or claims.get("oid") != expected_oid
            or claims.get("azp", claims.get("appid")) != expected_app
            or claims.get("scp") or claims.get("idtyp", "app") != "app"):
        raise HTTPException(403, "Only the configured gateway managed identity may resolve routes")