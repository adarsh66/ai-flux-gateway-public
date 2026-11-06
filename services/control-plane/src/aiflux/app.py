import logging
import asyncio
from contextlib import asynccontextmanager
import os
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import ValidationError
from sqlalchemy import func, literal, select, text, true
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from aiflux.apim import ApimClient, ApimError
from aiflux.auth import Principal, TokenVerifier, get_admin, get_principal
from aiflux.catalog import Catalog
from aiflux.config import Settings, get_settings
from aiflux import decision_router
from aiflux.decision_auth import require_gateway
from aiflux.decision_client import DecisionClient
from aiflux.decision_telemetry import decision_csv, decision_scoring
from aiflux.db import engine_for, get_db
from aiflux.external_inventory import AcceptedInventory
from aiflux.finops import (
    aware,
    create_price,
    ingestion_health,
    model_token_response,
    usage_csv,
    usage_models,
    usage_rankings,
    usage_response,
    usage_series_response,
)
from aiflux.gateway_settings import (
    bootstrap_fragment,
    canonical_scope,
    publish_settings,
    refresh_subscription_bindings,
    require_scope,
    revision_output,
    save_safety,
    save_settings,
    settings_output,
    subscription_access,
)
from aiflux.models import (
    Base,
    GatewaySettingsRevision,
    Member,
    ModelPrice,
    Organization,
    SafetyEvent,
    Team,
    TeamSubscription,
)
from aiflux.schemas import (
    AdminSubscriptionCreate,
    AdminSubscriptionOutput,
    CatalogOutput,
    CreditBudgetOutput,
    CreditBudgetUpdate,
    CreditSummaryOutput,
    EnabledRequest,
    GatewayRevisionOutput,
    GatewayScope,
    GatewaySettingsOutput,
    GatewaySettingsRetry,
    GatewaySettingsUpdate,
    GatewayTarget,
    IdentityOutput,
    IngestionHealth,
    KeyRequest,
    LocalLoginRequest,
    LocalLoginResponse,
    LocalRegisterRequest,
    LocalUserCreate,
    LocalUserOutput,
    LocalUserUpdate,
    MemberCreate,
    MemberOutput,
    ModelGardenItemOutput,
    ModelGardenUpsert,
    ModelRouterConfigOutput,
    ModelRouterConfigUpdate,
    ModelTokenSeries,
    OrganizationCreate,
    OrganizationOutput,
    Page,
    PlaygroundChatRequest,
    PlaygroundMessage,
    PriceCreate,
    PriceEnd,
    PriceOutput,
    RouterDecisionRequest,
    SafetyOutput,
    SafetySettingsUpdate,
    StateRequest,
    SubscriptionCreate,
    SubscriptionOutput,
    TurnstilePolicyPreviewOutput,
    UsagePage,
    UsageRankings,
    UsageSeries,
)
from aiflux.rate_card import RateCardOutput, RateCardUpdate, get_rate_card, save_rate_card
from aiflux.pricing_history import HistoryDetail, HistoryPage, history as pricing_history
from aiflux.external_pricing import ExternalCardUpdate, PricingContext, get_external_card, save_external_card, snapshot
from aiflux.customer_pricing import customer_routing_decision, customer_safe
from aiflux import monthly_budgets
from aiflux import archival
from aiflux.schemas import DeletionPreview, DeletionRequest, DeletionResult
from aiflux.schemas import (AdminMonthlyBudgetDashboard, AdminMonthlyBudgetListItem,
                           MonthlyBudgetSummary, MonthlyBudgetUpdate, MonthlyBudgetRevisionOutput)
from aiflux.subscriptions import (
    admin_owned,
    audit,
    create_subscription,
    lock_organization,
    owned,
    reconcile,
    subscription_dict,
)
from aiflux.turnstile_exchange import (
    authenticate_local_user,
    create_local_user,
    credit_summary_response,
    decide_model_route,
    get_router_config_output,
    list_budgets,
    list_local_users,
    list_model_garden,
    register_local_user,
    render_turnstile_exchange_policy,
    run_playground_chat,
    update_local_user,
    update_router_config,
    upsert_budget,
    upsert_model_garden_item,
)

Db = Annotated[Session, Depends(get_db)]
User = Annotated[Principal, Depends(get_principal)]
Admin = Annotated[Principal, Depends(get_admin)]
log = logging.getLogger(__name__)


def apim_client(request: Request) -> ApimClient:
    return request.app.state.apim


Apim = Annotated[ApimClient, Depends(apim_client)]


def entity_dict(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(row, field) for field in fields}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    from aiflux import model_access as model_access_service
    @asynccontextmanager
    async def lifespan(application):
        from aiflux.auto_pricing_worker import run_worker
        stop = asyncio.Event()
        task = asyncio.create_task(run_worker(settings, application.state.apim, stop)) if (
            settings.auto_pricing_sync_enabled or settings.model_access_enabled) else None
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                await task

    app = FastAPI(title="AIFLUX control plane", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.token_verifier = TokenVerifier(settings)
    app.state.apim = ApimClient(settings)
    # Lazy credential construction; startup/GET never performs inference or DB seeding.
    app.state.auto_decision_client = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Ocp-Apim-Subscription-Key"],
    )

    @app.middleware("http")
    async def secure_responses(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(IntegrityError)
    async def integrity_failure(request: Request, exc: IntegrityError) -> Response:
        from fastapi.responses import JSONResponse

        log.warning("Database constraint conflict path=%s", request.url.path)
        return JSONResponse({"detail": "Conflicting record; refresh and retry"}, status_code=409)

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(request: Request, exc: SQLAlchemyError) -> Response:
        from fastapi.responses import JSONResponse

        log.error("Database operation failed type=%s", type(exc).__name__)
        return JSONResponse({"detail": "Database temporarily unavailable"}, status_code=503)

    @app.exception_handler(ApimError)
    async def management_failure(request: Request, exc: ApimError) -> Response:
        from fastapi.responses import JSONResponse

        log.warning("APIM management failure status=%s", exc.status_code)
        return JSONResponse({"detail": "APIM management operation failed"}, status_code=502)

    @app.get("/health")
    def health() -> dict:
        return {"status": "alive"}

    @app.get("/.well-known/acme-challenge/{token}", response_class=PlainTextResponse)
    def acme_challenge(token: str) -> PlainTextResponse:
        if not settings.acme_challenge_enabled or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", token):
            raise HTTPException(404, "Not found")
        path = settings.acme_challenge_directory / token
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 300:
            raise HTTPException(404, "Not found")
        value = path.read_text(encoding="ascii")
        if not re.fullmatch(re.escape(token) + r"\.[A-Za-z0-9_-]{43}", value):
            raise HTTPException(404, "Not found")
        return PlainTextResponse(value)

    @app.api_route(
        "/_edge-denied/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    )
    def edge_denied(path: str) -> PlainTextResponse:
        return PlainTextResponse("Public application routes are not released", status_code=403)

    @app.get("/ready")
    def ready() -> dict:
        if settings.identity_errors():
            raise HTTPException(503, "Required identity/database configuration is incomplete")
        if settings.gateway_settings_scopes:
            bootstrap_fragment()
        with engine_for(settings.database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
            for table in Base.metadata.sorted_tables:
                connection.execute(select(literal(1)).select_from(table).limit(1))
        return {"status": "ready"}

    @app.get("/api/me", response_model=IdentityOutput)
    def me(principal: User) -> dict:
        return asdict(principal)

    @app.get("/api/admin/gateway-targets", response_model=Page[GatewayTarget])
    def gateway_targets(
        principal: Admin, db: Db, organization_id: UUID | None = None,
        offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
    ) -> dict:
        query = (
            select(TeamSubscription, Team, Organization)
            .join(Team, TeamSubscription.team_id == Team.id)
            .join(Organization, TeamSubscription.organization_id == Organization.id)
                 .where(Team.organization_id == Organization.id, Organization.enabled == true(),
                     Organization.deleted_at.is_(None), TeamSubscription.deleted_at.is_(None),
                     TeamSubscription.deletion_requested_at.is_(None))
        )
        if organization_id is not None:
            query = query.where(Organization.id == str(organization_id))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.execute(
            query.order_by(Organization.id, Team.id, TeamSubscription.id).offset(offset).limit(limit),
        )
        return {"items": [{
            "organization_id": org.id, "organization_name": org.name,
            "team_id": team.id, "team": team.name, "subscription_id": subscription.id,
            "name": subscription.name, "state": subscription.state,
        } for subscription, team, org in rows], "total": total}

    @app.get("/api/admin/content-safety-settings", response_model=Page[GatewaySettingsOutput])
    @app.get("/api/admin/gateway-settings", response_model=Page[GatewaySettingsOutput])
    def gateway_settings(principal: Admin, db: Db) -> dict:
        items = [
            settings_output(db, scope, settings) for scope in dict.fromkeys(settings.gateway_settings_scopes)
        ]
        return {"items": items, "total": len(items)}

    @app.put("/api/admin/gateway-settings/{scope}", response_model=GatewaySettingsOutput)
    def gateway_settings_update(
        scope: GatewayScope, payload: GatewaySettingsUpdate, principal: Admin, db: Db, apim: Apim,
    ) -> GatewaySettingsOutput:
        return save_settings(db, settings, apim, principal, scope, payload)

    @app.put("/api/admin/content-safety-settings/{scope}", response_model=GatewaySettingsOutput)
    def safety_settings_update(
        scope: GatewayScope, payload: SafetySettingsUpdate, principal: Admin, db: Db, apim: Apim,
    ) -> GatewaySettingsOutput:
        return save_safety(db, settings, apim, principal, scope, payload)

    @app.post("/api/admin/content-safety-settings/{scope}/reconcile", response_model=GatewaySettingsOutput)
    @app.post("/api/admin/gateway-settings/{scope}/reconcile", response_model=GatewaySettingsOutput)
    def gateway_settings_reconcile(
        scope: GatewayScope, payload: GatewaySettingsRetry, principal: Admin, db: Db, apim: Apim,
    ) -> GatewaySettingsOutput:
        return publish_settings(db, settings, apim, principal, scope, payload.expected_version)

    @app.get("/api/admin/content-safety-settings/{scope}/history", response_model=Page[GatewayRevisionOutput])
    @app.get("/api/admin/gateway-settings/{scope}/history", response_model=Page[GatewayRevisionOutput])
    def gateway_settings_history(
        scope: GatewayScope, principal: Admin, db: Db,
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    ) -> dict:
        require_scope(settings, scope)
        query = select(GatewaySettingsRevision).where(
            GatewaySettingsRevision.scope == canonical_scope(settings, scope),
        )
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(
            query.order_by(GatewaySettingsRevision.version.desc()).offset(offset).limit(limit),
        )
        return {"items": [revision_output(row) for row in rows], "total": total}

    @app.get("/api/model-deployments")
    def model_deployments(principal: User, db: Db) -> dict:
        inventory = AcceptedInventory.load(settings)
        items = inventory.discovery()
        if settings.model_access_enabled and principal.role != "ids_admin":
            items = model_access_service.filter_items(db, principal.organization_id, items)
        return {"items": items, "total": len(items), "verified_at": inventory.verified_at.isoformat(),
                "auto_enabled": False, "pricing_note": "Unknown prices are not free; no monetary-ledger guarantee."}

    @app.post("/api/admin/model-deployments/sync")
    def sync_model_deployments(principal: Admin, db: Db, reconcile_router: bool = True) -> dict:
        from aiflux.model_inventory_sync import sync_verified_models
        return sync_verified_models(db, settings, principal, reconcile_router=reconcile_router)

    @app.get("/api/models", response_model=Page[CatalogOutput])
    def models(principal: User, db: Db) -> dict:
        inventory = AcceptedInventory.load(settings)
        if not settings.catalog_configured:
            if settings.local_auth_enabled:
                garden = list_model_garden(db, settings, include_disabled=False)
                items = [
                    {
                        "id": m.id,
                        "provider": m.vendor,
                        "capabilities": m.capabilities,
                        "enabled": m.enabled and not m.coming_soon,
                        "placeholder": m.coming_soon,
                        "max_completion_tokens": m.max_completion_tokens,
                    }
                    for m in garden
                ]
                if settings.model_access_enabled and principal.role != "ids_admin":
                    items = model_access_service.filter_items(db, principal.organization_id, items)
                return {"items": items, "total": len(items)}
            raise HTTPException(503, "Model catalog has not passed gateway capability validation")
        try:
            catalog = Catalog.load(settings.catalog_path)
        except (OSError, ValueError, ValidationError) as exc:
            log.error("Catalog configuration invalid type=%s", type(exc).__name__)
            raise HTTPException(503, "Model catalog is unavailable") from exc
        from aiflux import completion_limits
        accepted = inventory.accepted_aliases(settings)
        try:
            limits = completion_limits.load(settings, accepted)
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(503, "Completion limit configuration is unavailable") from exc
        for model in catalog.models:
            route = inventory.route(model.id)
            if route is not None:
                model.capabilities = [cap for cap in model.capabilities if cap in route.capabilities]
                model.max_completion_tokens = completion_limits.effective(
                    settings, model.id, min(model.max_completion_tokens or route.max_completion_tokens,
                                            route.max_completion_tokens),
                    limits if model.id in accepted else None)
        if settings.gateway_max_completion_tokens is not None:
            for model in catalog.models:
                if model.max_completion_tokens is not None:
                    model.max_completion_tokens = min(
                        model.max_completion_tokens, settings.gateway_max_completion_tokens
                    )
        items = [
            model.model_dump(
                include={"id", "provider", "capabilities", "enabled", "placeholder", "max_completion_tokens"}
            )
            for model in catalog.models
            if model.enabled and not model.placeholder and "chat" in model.capabilities
            and inventory.matches_catalog_model(model)
            and (model.id != "auto" or get_router_config_output(db, settings).enabled)
        ]
        if settings.model_access_enabled and principal.role != "ids_admin":
            items = model_access_service.filter_items(db, principal.organization_id, items)
        return {"items": items, "total": len(items)}

    @app.get("/api/subscriptions", response_model=Page[SubscriptionOutput])
    def subscriptions(
        principal: User,
        db: Db,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ) -> dict:
        condition = ((TeamSubscription.organization_id == principal.organization_id)
                 & TeamSubscription.deleted_at.is_(None)
                 & TeamSubscription.deletion_requested_at.is_(None))
        items = db.scalars(
            select(TeamSubscription)
            .where(condition)
            .order_by(
                TeamSubscription.created_at.desc(),
                TeamSubscription.id,
            )
            .offset(offset)
            .limit(limit)
        ).all()
        return {
            "items": [subscription_dict(row) for row in items],
            "total": db.scalar(select(func.count()).select_from(TeamSubscription).where(condition)),
        }

    @app.post("/api/subscriptions", status_code=201, response_model=SubscriptionOutput)
    def new_subscription(
        payload: SubscriptionCreate,
        principal: Admin,
        db: Db,
        apim: Apim,
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict:
        row = create_subscription(db, principal, payload, idempotency_key, apim)
        return refresh_access(db, row, apim, principal)

    @app.post("/api/subscriptions/{sid}/reveal")
    def reveal(sid: UUID, payload: KeyRequest, principal: User, db: Db, apim: Apim) -> dict:
        lock_organization(db, principal.organization_id)
        row = owned(db, sid, principal)
        if row.state != "active":
            raise HTTPException(409, "Only active subscriptions can reveal keys")
        audit(db, principal, f"subscription.reveal.{payload.key}", row.id)
        db.flush()
        secret = apim.reveal(row.id, payload.key)
        db.commit()
        return {"key": secret}

    @app.post("/api/subscriptions/{sid}/rotate")
    @app.post("/api/admin/subscriptions/{sid}/rotate")
    def rotate(sid: UUID, payload: KeyRequest, principal: Admin, db: Db, apim: Apim) -> dict:
        row = admin_owned(db, sid)
        if row.state not in ("active", "suspended"):
            raise HTTPException(409, "Reconcile the subscription before rotating")
        audit(db, principal, f"subscription.rotate.{payload.key}", row.id, row.organization_id)
        db.flush()
        apim.rotate(row.id, payload.key)
        db.commit()
        return {"state": row.state}

    @app.put("/api/subscriptions/{sid}/state", response_model=SubscriptionOutput)
    @app.put("/api/admin/subscriptions/{sid}/state", response_model=AdminSubscriptionOutput)
    def subscription_state(sid: UUID, payload: StateRequest, principal: Admin, db: Db, apim: Apim) -> dict:
        row = admin_owned(db, sid)
        row.desired_state = payload.state
        row.state = "pending"
        audit(db, principal, "subscription.state.requested", row.id, row.organization_id)
        db.commit()
        reconcile(db, row, apim, principal)
        return admin_subscription_output(db, row)

    @app.post("/api/subscriptions/{sid}/reconcile", response_model=SubscriptionOutput)
    @app.post("/api/admin/subscriptions/{sid}/reconcile", response_model=AdminSubscriptionOutput)
    def subscription_reconcile(sid: UUID, principal: Admin, db: Db, apim: Apim) -> dict:
        row = admin_owned(db, sid)
        reconcile(db, row, apim, principal)
        return refresh_access(db, row, apim, principal)

    def admin_subscription_output(db: Session, row: TeamSubscription) -> dict:
        org = db.get(Organization, row.organization_id)
        access, message = subscription_access(db, settings, row.id)
        if row.deleted_at or row.deletion_requested_at:
            access, message = "pending", "Deletion requested; access revoked locally. Only deletion retry is allowed."
        return subscription_dict(row) | {
            "organization_id": row.organization_id,
            "organization_name": org.name if org else row.organization_id,
            "team_id": row.team_id, "gateway_access": access, "gateway_message": message,
        }

    def refresh_access(db: Session, row: TeamSubscription, apim: ApimClient, principal: Principal) -> dict:
        message = None
        try:
            refresh_subscription_bindings(db, settings, apim, principal, row.id)
        except (HTTPException, ApimError) as exc:
            db.rollback()
            db.refresh(row)
            if row.deleted_at or row.deletion_requested_at:
                raise HTTPException(409, "Subscription is archived or deletion is pending") from exc
            message = (str(exc.detail) if isinstance(exc, HTTPException)
                       else "APIM gateway publication failed; reconcile to retry.")
            log.warning("Subscription gateway access pending subscription=%s reason=%s", row.id, message)
        result = admin_subscription_output(db, row)
        if message:
            result.update(
                gateway_access="ready" if settings.gateway_controls_poc_enabled and not settings.model_access_enabled else "pending",
                gateway_message=("Default product access available; optional overrides pending. " + message)
                if settings.gateway_controls_poc_enabled else message,
            )
        return result

    @app.get("/api/admin/subscriptions", response_model=Page[AdminSubscriptionOutput])
    def admin_subscriptions(
        principal: Admin, db: Db, organization_id: UUID | None = None,
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    ) -> dict:
        query = select(TeamSubscription).where(TeamSubscription.deleted_at.is_(None))
        if organization_id is not None:
            query = query.where(TeamSubscription.organization_id == str(organization_id))
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        rows = db.scalars(query.order_by(
            TeamSubscription.created_at.desc(), TeamSubscription.id,
        ).offset(offset).limit(limit)).all()
        return {"items": [admin_subscription_output(db, row) for row in rows], "total": total}

    @app.post("/api/admin/subscriptions", status_code=201, response_model=AdminSubscriptionOutput)
    def admin_new_subscription(
        payload: AdminSubscriptionCreate, principal: Admin, db: Db, apim: Apim,
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
    ) -> dict:
        row = create_subscription(
            db, principal, SubscriptionCreate(name=payload.name, team=payload.team), idempotency_key,
            apim, str(payload.organization_id),
        )
        return refresh_access(db, row, apim, principal)

    @app.post("/api/admin/subscriptions/{sid}/reveal")
    def admin_reveal(sid: UUID, payload: KeyRequest, principal: Admin, db: Db, apim: Apim) -> dict:
        row = admin_owned(db, sid)
        if row.state != "active":
            raise HTTPException(409, "Only active subscriptions can reveal keys")
        audit(db, principal, f"subscription.reveal.{payload.key}", row.id, row.organization_id)
        db.flush()
        secret = apim.reveal(row.id, payload.key)
        db.commit()
        return {"key": secret}

    def check_usage_subscription(
        db: Session,
        organization_id: str | None,
        subscription_id: UUID | None,
    ) -> None:
        if subscription_id is not None and organization_id is not None:
            row = db.get(TeamSubscription, str(subscription_id))
            if row is None or row.organization_id != organization_id:
                raise HTTPException(404, "Subscription not found")

    def usage(
        db: Session,
        organization_id: str | None,
        days: int,
        subscription_id: UUID | None,
        offset: int,
        limit: int,
        model: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        *, pricing_context: PricingContext | None = None,
    ) -> dict:
        check_usage_subscription(db, organization_id, subscription_id)
        start, end = usage_viewport(days, start, end)
        return usage_response(
            db, organization_id, days, str(subscription_id) if subscription_id else None, offset, limit, model, start, end,
            pricing_context=pricing_context,
        )

    @app.get("/api/usage", response_model=None)
    def customer_usage(
        principal: User,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        subscription_id: UUID | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        model: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        return usage(db, principal.organization_id, days, subscription_id, offset, limit, model, start, end,
                 pricing_context=snapshot(db, principal.organization_id))

    @app.get("/api/usage/health", response_model=IngestionHealth)
    def customer_usage_health(principal: User, db: Db, subscription_id: UUID | None = None) -> dict:
        check_usage_subscription(db, principal.organization_id, subscription_id)
        return ingestion_health(db, principal.organization_id, str(subscription_id) if subscription_id else None)

    @app.get("/api/admin/usage/health", response_model=IngestionHealth)
    def admin_usage_health(principal: Admin, db: Db, organization_id: UUID | None = None,
                           subscription_id: UUID | None = None) -> dict:
        org = str(organization_id) if organization_id else None
        check_usage_subscription(db, org, subscription_id)
        return ingestion_health(db, org, str(subscription_id) if subscription_id else None)

    @app.get("/api/usage/models", response_model=Page[str])
    def customer_usage_models(
        principal: User,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        subscription_id: UUID | None = None,
    ) -> dict:
        check_usage_subscription(db, principal.organization_id, subscription_id)
        return usage_models(
            db, principal.organization_id, days, str(subscription_id) if subscription_id else None,
            current_models=[m['id'] for m in models(principal, db)['items'] if m['id'] not in ('auto', 'Decision-1')],
        )

    @app.get("/api/admin/usage/models", response_model=Page[str])
    def admin_usage_models(
        principal: Admin,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        organization_id: UUID | None = None,
        subscription_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        org = str(organization_id) if organization_id else None
        check_usage_subscription(db, org, subscription_id)
        start, end = usage_viewport(days, start, end)
        return usage_models(db, org, days, str(subscription_id) if subscription_id else None, start, end,
                            current_models=[m['id'] for m in models(principal, db)['items'] if m['id'] not in ('auto', 'Decision-1')])

    @app.get("/api/admin/usage/rankings", response_model=UsageRankings)
    def admin_usage_rankings(
        principal: Admin, db: Db,
        dimension: str = Query("organizations", pattern="^(organizations|subscriptions)$"),
        organization_id: UUID | None = None,
        days: int = Query(30, ge=1, le=366),
        start: datetime | None = None, end: datetime | None = None,
        model: str | None = None,
        offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100),
    ) -> dict:
        org = str(organization_id) if organization_id else None
        if dimension == "subscriptions":
            if org is None:
                raise HTTPException(422, "Select an organization for subscription rankings")
            if db.get(Organization, org) is None:
                raise HTTPException(404, "Organization not found")
        start, end = usage_viewport(days, start, end)
        return usage_rankings(db, dimension, org, start, end, model, offset, limit)

    @app.get("/api/admin/usage/organization-costs")
    def admin_organization_costs(
        principal: Admin, db: Db,
        days: int = Query(30, ge=1, le=366),
        start: datetime | None = None, end: datetime | None = None,
        model: str | None = Query(None, max_length=100),
        offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=10),
    ):
        from aiflux.organization_costs import organization_costs
        from aiflux.schemas import OrganizationCosts
        start, end = usage_viewport(days, start, end)
        return OrganizationCosts.model_validate(organization_costs(db, start, end, model, offset, limit))

    def usage_viewport(
        days: int, start: datetime | None, end: datetime | None,
    ) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        period_end = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        if (start is None) != (end is None):
            raise HTTPException(422, "Specify both start and end for a chart viewport")
        if start is not None and end is not None:
            if start.tzinfo is None or end.tzinfo is None:
                raise HTTPException(422, "Chart timestamps must include a timezone")
            start, end = aware(start), aware(end)
            if not (now - timedelta(days=366) <= start < end <= period_end
                    and end - start <= timedelta(days=days)):
                raise HTTPException(422, "Chart viewport must be inside the selected period")
        else:
            start, end = now - timedelta(days=days), now
        return start, end

    def usage_series(
        db: Session,
        organization_id: str | None,
        days: int,
        subscription_id: UUID | None,
        start: datetime | None,
        end: datetime | None,
        model: str | None = None,
        granularity: str | None = None,
        time_zone: str = "UTC",
    ) -> dict:
        check_usage_subscription(db, organization_id, subscription_id)
        start, end = usage_viewport(days, start, end)
        try:
            return usage_series_response(
                db, organization_id, str(subscription_id) if subscription_id else None, start, end, model,
                granularity, time_zone,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/usage/timeseries", response_model=UsageSeries, response_model_exclude_unset=True)
    def customer_usage_series(
        principal: User,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        subscription_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        model: str | None = None,
        granularity: str | None = Query(None, pattern="^(minute|hour|day)$"),
        time_zone: str = Query("UTC", pattern="^(UTC|Asia/Singapore)$"),
    ) -> dict:
        return usage_series(db, principal.organization_id, days, subscription_id, start, end, model,
                            granularity, time_zone)

    @app.get("/api/usage/model-tokens", response_model=ModelTokenSeries)
    def customer_model_tokens(
        principal: User,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        subscription_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        model: str | None = None,
        granularity: str = Query("auto", pattern="^(auto|hour|day)$"),
        time_zone: str = Query("UTC", pattern="^(UTC|Asia/Singapore)$"),
    ) -> dict:
        check_usage_subscription(db, principal.organization_id, subscription_id)
        start, end = usage_viewport(days, start, end)
        try:
            return model_token_response(
                db, principal.organization_id, str(subscription_id) if subscription_id else None,
                start, end, model, granularity, time_zone,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/admin/usage/model-tokens", response_model=ModelTokenSeries)
    def admin_model_tokens(
        principal: Admin,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        organization_id: UUID | None = None,
        subscription_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        model: str | None = None,
        granularity: str = Query("auto", pattern="^(auto|hour|day)$"),
        time_zone: str = Query("UTC", pattern="^(UTC|Asia/Singapore)$"),
    ) -> dict:
        org = str(organization_id) if organization_id else None
        check_usage_subscription(db, org, subscription_id)
        start, end = usage_viewport(days, start, end)
        try:
            return model_token_response(db, org, str(subscription_id) if subscription_id else None,
                                        start, end, model, granularity, time_zone)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/admin/usage/timeseries", response_model=UsageSeries, response_model_exclude_unset=True)
    def admin_usage_series(
        principal: Admin,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        organization_id: UUID | None = None,
        subscription_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        model: str | None = None,
        granularity: str | None = Query(None, pattern="^(minute|hour|day)$"),
        time_zone: str = Query("UTC", pattern="^(UTC|Asia/Singapore)$"),
    ) -> dict:
        return usage_series(
            db, str(organization_id) if organization_id else None, days, subscription_id, start, end, model,
            granularity, time_zone,
        )

    def export(
        db: Session, org: str | None, days: int, subscription_id: UUID | None, model: str | None,
        start: datetime | None = None, end: datetime | None = None,
        *, pricing_context: PricingContext | None = None,
    ) -> Response:
        check_usage_subscription(db, org, subscription_id)
        start, end = usage_viewport(days, start, end)
        try:
            content = usage_csv(db, org, days, str(subscription_id) if subscription_id else None, model, start, end,
                                pricing_context=pricing_context)
        except ValueError as exc:
            raise HTTPException(413, str(exc)) from exc
        return Response(
            content,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="aiflux-usage.csv"',
            },
        )

    @app.get("/api/usage/export")
    def customer_export(
        principal: User,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        subscription_id: UUID | None = None,
        model: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Response:
        return export(db, principal.organization_id, days, subscription_id, model, start, end,
                  pricing_context=snapshot(db, principal.organization_id))

    @app.get("/api/admin/usage", response_model=UsagePage)
    def admin_usage(
        principal: Admin,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        organization_id: UUID | None = None,
        subscription_id: UUID | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        model: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        return usage(
            db, str(organization_id) if organization_id else None, days, subscription_id, offset, limit, model, start, end
        )

    @app.get("/api/admin/usage/export")
    def admin_export(
        principal: Admin,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        organization_id: UUID | None = None,
        subscription_id: UUID | None = None,
        model: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> Response:
        return export(db, str(organization_id) if organization_id else None, days, subscription_id, model, start, end)

    def decision_scoring_view(
        request: Request, db: Session, org: str | None, days: int, subscription_id: UUID | None,
        start: datetime | None, end: datetime | None, offset: int, limit: int,
        granularity: str, time_zone: str,
        *, pricing_context: PricingContext | None = None,
    ) -> dict:
        check_usage_subscription(db, org, subscription_id)
        start, end = usage_viewport(days, start, end)
        try:
            return decision_scoring(
                db, settings, org, str(subscription_id) if subscription_id else None,
                start, end, offset, limit, granularity, time_zone,
                getattr(request.app.state, "decision_telemetry_client", None),
                pricing_context=pricing_context,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/usage/decision-scoring")
    def customer_decision_scoring(
        request: Request, principal: User, db: Db,
        days: int = Query(30, ge=1, le=366), subscription_id: UUID | None = None,
        start: datetime | None = None, end: datetime | None = None,
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
        granularity: str = Query("hour", pattern="^(minute|hour|day)$"),
        time_zone: str = Query("UTC", pattern="^(UTC|Asia/Singapore)$"),
    ) -> dict:
        return decision_scoring_view(request, db, principal.organization_id, days, subscription_id,
                                     start, end, offset, limit, granularity, time_zone,
                                     pricing_context=snapshot(db, principal.organization_id))

    @app.get("/api/admin/usage/decision-scoring")
    def admin_decision_scoring(
        request: Request, principal: Admin, db: Db,
        days: int = Query(30, ge=1, le=366), organization_id: UUID | None = None,
        subscription_id: UUID | None = None, start: datetime | None = None, end: datetime | None = None,
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
        granularity: str = Query("hour", pattern="^(minute|hour|day)$"),
        time_zone: str = Query("UTC", pattern="^(UTC|Asia/Singapore)$"),
    ) -> dict:
        return decision_scoring_view(request, db, str(organization_id) if organization_id else None,
                                     days, subscription_id, start, end, offset, limit, granularity, time_zone)

    def decision_export_response(data: dict, offset: int, limit: int) -> Response:
        return Response(
            decision_csv(data), media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="aiflux-decision-scoring.csv"',
                     "X-Decision-Telemetry-Status": data["status"],
                     "X-Decision-Telemetry-Offset": str(offset), "X-Decision-Telemetry-Limit": str(limit)},
        )

    @app.get("/api/usage/decision-scoring/export.csv")
    def customer_decision_scoring_export(
        request: Request, principal: User, db: Db,
        days: int = Query(30, ge=1, le=366), subscription_id: UUID | None = None,
        start: datetime | None = None, end: datetime | None = None,
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
        granularity: str = Query("hour", pattern="^(minute|hour|day)$"),
        time_zone: str = Query("UTC", pattern="^(UTC|Asia/Singapore)$"),
    ) -> Response:
        data = decision_scoring_view(request, db, principal.organization_id, days, subscription_id,
                                     start, end, offset, limit, granularity, time_zone,
                                     pricing_context=snapshot(db, principal.organization_id))
        return decision_export_response(data, offset, limit)

    @app.get("/api/admin/usage/decision-scoring/export.csv")
    def admin_decision_scoring_export(
        request: Request, principal: Admin, db: Db,
        days: int = Query(30, ge=1, le=366), organization_id: UUID | None = None,
        subscription_id: UUID | None = None, start: datetime | None = None, end: datetime | None = None,
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
        granularity: str = Query("hour", pattern="^(minute|hour|day)$"),
        time_zone: str = Query("UTC", pattern="^(UTC|Asia/Singapore)$"),
    ) -> Response:
        data = decision_scoring_view(request, db, str(organization_id) if organization_id else None,
                                     days, subscription_id, start, end, offset, limit, granularity, time_zone)
        return decision_export_response(data, offset, limit)

    @app.get("/api/admin/organizations", response_model=Page[OrganizationOutput])
    def organizations(principal: Admin, db: Db) -> dict:
        rows = db.scalars(select(Organization).where(Organization.deleted_at.is_(None)).order_by(Organization.name)).all()
        return {
            "items": [entity_dict(row, ("id", "name", "tenant_id", "enabled")) for row in rows],
            "total": len(rows),
        }

    @app.post("/api/admin/organizations", status_code=201, response_model=OrganizationOutput)
    def add_organization(payload: OrganizationCreate, principal: Admin, db: Db) -> dict:
        archival.lock_identity(db, principal)
        org = Organization(name=payload.name, tenant_id=str(payload.tenant_id))
        db.add(org)
        db.flush()
        audit(db, principal, "organization.created", org.id)
        db.commit()
        return entity_dict(org, ("id", "name", "tenant_id", "enabled"))

    @app.put("/api/admin/organizations/{oid}", response_model=OrganizationOutput)
    def enable_organization(oid: UUID, payload: EnabledRequest, principal: Admin, db: Db, apim: Apim) -> dict:
        archival.lock_identity(db, principal)
        org = db.scalar(
            select(Organization)
            .where(Organization.id == str(oid))
            .with_for_update().execution_options(populate_existing=True)
            .with_hint(
                Organization,
                "WITH (UPDLOCK, HOLDLOCK)",
                dialect_name="mssql",
            )
        )
        if org is None:
            raise HTTPException(404, "Organization not found")
        archival.require_unarchived(org)
        if org.id == principal.organization_id and not payload.enabled:
            raise HTTPException(409, "Cannot disable your own IDS organization")
        org.enabled = payload.enabled
        if settings.model_access_enabled:
            model_access_service.queue(db)
        audit(db, principal, "organization.enabled" if payload.enabled else "organization.disabled", org.id)
        if not payload.enabled:
            rows = db.scalars(
                select(TeamSubscription).where(TeamSubscription.organization_id == org.id,
                                              TeamSubscription.deleted_at.is_(None),
                                              TeamSubscription.deletion_requested_at.is_(None))
            ).all()
            for row in rows:
                row.desired_state = "suspended"
                row.state = "pending"
            db.commit()
            for row in rows:
                current_org = db.scalar(
                    select(Organization)
                    .where(Organization.id == org.id)
                    .with_for_update()
                    .with_hint(Organization, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
                    .execution_options(populate_existing=True)
                )
                if current_org is None or current_org.enabled or current_org.deleted_at:
                    raise HTTPException(409, "Organization state changed during key suspension")
                db.refresh(row)
                if row.deleted_at or row.deletion_requested_at:
                    continue
                try:
                    if row.apim_pending_operation:
                        apim.resolve_subscription_operation(row.id, row.apim_pending_operation)
                        row.apim_pending_operation = None
                    apim.ensure(row.id, row.name, "suspended")
                except ApimError as exc:
                    if exc.pending_operation:
                        row.apim_pending_operation = exc.pending_operation
                    row.state = "failed"
                    db.commit()
                    log.warning("Organization suspension incomplete organization=%s", org.id)
                    raise HTTPException(
                        502,
                        "Portal access disabled; key suspension incomplete. Retry disable.",
                    ) from exc
                row.state = "suspended"
                db.commit()
        else:
            db.commit()
        return entity_dict(org, ("id", "name", "tenant_id", "enabled"))

    @app.get("/api/admin/members", response_model=Page[MemberOutput])
    def members(organization_id: UUID, principal: Admin, db: Db) -> dict:
        rows = db.scalars(select(Member).where(Member.organization_id == str(organization_id),
                                              Member.deleted_at.is_(None))).all()
        return {
            "items": [
                entity_dict(row, ("id", "organization_id", "object_id", "role", "enabled")) for row in rows
            ],
            "total": len(rows),
        }

    @app.post("/api/admin/members", status_code=201, response_model=MemberOutput)
    def add_member(payload: MemberCreate, principal: Admin, db: Db) -> dict:
        archival.lock_identity(db, principal)
        org = lock_organization(db, str(payload.organization_id))
        if payload.role == "ids_admin" and org.tenant_id != settings.home_tenant_id:
            raise HTTPException(422, "IDS roles can only be granted within the home tenant")
        member = Member(organization_id=org.id, object_id=str(payload.object_id), role=payload.role)
        db.add(member)
        db.flush()
        audit(db, principal, "member.approved", member.id)
        db.commit()
        return entity_dict(member, ("id", "organization_id", "object_id", "role", "enabled"))

    @app.put("/api/admin/members/{mid}", response_model=MemberOutput)
    def enable_member(mid: UUID, payload: EnabledRequest, principal: Admin, db: Db) -> dict:
        archival.lock_identity(db, principal)
        member = db.get(Member, str(mid), populate_existing=True)
        if member is None:
            raise HTTPException(404, "Member not found")
        lock_organization(db, member.organization_id, allow_disabled=True)
        archival.require_unarchived(member)
        if not payload.enabled:
            blockers = archival.member_blockers(db, principal, member)
            if blockers:
                raise HTTPException(409, blockers)
        from aiflux.models import LocalUser
        if db.scalar(select(LocalUser.id).where(
            LocalUser.organization_id == member.organization_id, LocalUser.object_id == member.object_id,
            LocalUser.deleted_at.is_not(None),
        )):
            raise HTTPException(409, "Archived linked identity cannot be restored")
        member.enabled = payload.enabled
        audit(db, principal, "member.enabled" if payload.enabled else "member.disabled", member.id)
        db.commit()
        return entity_dict(member, ("id", "organization_id", "object_id", "role", "enabled"))

    @app.get("/api/admin/organizations/{entity_id}/deletion-preview", response_model=DeletionPreview)
    def organization_deletion_preview(entity_id: UUID, principal: Admin, db: Db):
        return archival.preview(db, settings, principal, "organization", str(entity_id))

    @app.get("/api/admin/subscriptions/{entity_id}/deletion-preview", response_model=DeletionPreview)
    def subscription_deletion_preview(entity_id: UUID, principal: Admin, db: Db):
        return archival.preview(db, settings, principal, "subscription", str(entity_id))

    @app.get("/api/admin/local-users/{entity_id}/deletion-preview", response_model=DeletionPreview)
    def local_user_deletion_preview(entity_id: UUID, principal: Admin, db: Db):
        return archival.preview(db, settings, principal, "local_user", str(entity_id))

    @app.get("/api/admin/members/{entity_id}/deletion-preview", response_model=DeletionPreview)
    def member_deletion_preview(entity_id: UUID, principal: Admin, db: Db):
        return archival.preview(db, settings, principal, "member", str(entity_id))

    def delete_entity(kind, entity_id, payload, principal, db, apim):
        from fastapi.responses import JSONResponse
        result = archival.archive(db, settings, principal, kind, str(entity_id), payload, apim)
        if result.status == "failed":
            return JSONResponse(result.model_dump(), status_code=502)
        return result

    @app.delete("/api/admin/organizations/{entity_id}", response_model=DeletionResult)
    def delete_organization(entity_id: UUID, payload: DeletionRequest, principal: Admin, db: Db, apim: Apim):
        return delete_entity("organization", entity_id, payload, principal, db, apim)

    @app.delete("/api/admin/subscriptions/{entity_id}", response_model=DeletionResult)
    def delete_subscription(entity_id: UUID, payload: DeletionRequest, principal: Admin, db: Db, apim: Apim):
        return delete_entity("subscription", entity_id, payload, principal, db, apim)

    @app.delete("/api/admin/local-users/{entity_id}", response_model=DeletionResult)
    def delete_local_user(entity_id: UUID, payload: DeletionRequest, principal: Admin, db: Db, apim: Apim):
        return delete_entity("local_user", entity_id, payload, principal, db, apim)

    @app.delete("/api/admin/members/{entity_id}", response_model=DeletionResult)
    def delete_member(entity_id: UUID, payload: DeletionRequest, principal: Admin, db: Db, apim: Apim):
        return delete_entity("member", entity_id, payload, principal, db, apim)

    @app.get("/api/admin/safety", response_model=Page[SafetyOutput])
    def safety(
        principal: Admin,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        organization_id: UUID | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ) -> dict:
        conditions = [SafetyEvent.occurred_at >= datetime.now(UTC) - timedelta(days=days)]
        if organization_id is not None:
            conditions.append(SafetyEvent.organization_id == str(organization_id))
        rows = db.scalars(
            select(SafetyEvent)
            .where(*conditions)
            .order_by(
                SafetyEvent.occurred_at.desc(),
                SafetyEvent.id,
            )
            .offset(offset)
            .limit(limit)
        ).all()
        return {
            "items": [
                entity_dict(
                    row, ("id", "organization_id", "subscription_id", "category", "action", "correlation_id")
                )
                | {"occurred_at": aware(row.occurred_at).isoformat()}
                for row in rows
            ],
            "total": db.scalar(select(func.count()).select_from(SafetyEvent).where(*conditions)),
        }

    @app.get("/api/admin/prices", response_model=Page[PriceOutput])
    def prices(principal: Admin, db: Db) -> dict:
        rows = db.scalars(select(ModelPrice).order_by(ModelPrice.effective_from.desc())).all()
        return {"items": [price_dict(row) for row in rows], "total": len(rows)}

    @app.post("/api/admin/prices", status_code=201, response_model=PriceOutput)
    def add_price(payload: PriceCreate, principal: Admin, db: Db) -> dict:
        try:
            row, _ = create_price(db, payload)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        audit(db, principal, "price.created", row.id)
        db.commit()
        return price_dict(row)

    @app.put("/api/admin/prices/{pid}/end", response_model=PriceOutput)
    def end_price(pid: UUID, payload: PriceEnd, principal: Admin, db: Db) -> dict:
        row = db.scalar(
            select(ModelPrice)
            .where(ModelPrice.id == str(pid))
            .with_hint(ModelPrice, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        )
        if row is None:
            raise HTTPException(404, "Price not found")
        if row.effective_to is not None or payload.effective_to <= aware(row.effective_from):
            raise HTTPException(409, "Only an open period can be closed after its effective start")
        row.effective_to = payload.effective_to
        audit(db, principal, "price.period.closed", row.id)
        db.commit()
        return price_dict(row)

    @app.get("/api/admin/rate-card/history", response_model=HistoryPage)
    def admin_internal_price_history(principal: Admin, db: Db, offset: int = Query(0, ge=0),
                                     limit: int = Query(25, ge=1, le=100)):
        return pricing_history(db, settings, principal, offset=offset, limit=limit)

    @app.get("/api/admin/rate-card/history/detail", response_model=HistoryDetail)
    def admin_internal_price_revision(principal: Admin, db: Db, revision: str = Query(max_length=200)):
        return pricing_history(db, settings, principal, revision=revision)

    @app.get("/api/admin/external-rate-card/history", response_model=HistoryPage)
    def admin_external_price_history(principal: Admin, db: Db, offset: int = Query(0, ge=0),
                                     limit: int = Query(25, ge=1, le=100)):
        return pricing_history(db, settings, principal, external_card=True, offset=offset, limit=limit)

    @app.get("/api/admin/external-rate-card/history/detail", response_model=HistoryDetail)
    def admin_external_price_revision(principal: Admin, db: Db, revision: str = Query(max_length=200)):
        return pricing_history(db, settings, principal, external_card=True, revision=revision)

    @app.get("/api/admin/organizations/{organization_id}/external-rate-card/history", response_model=HistoryPage)
    def admin_org_price_history(organization_id: UUID, principal: Admin, db: Db,
                               offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
        return pricing_history(db, settings, principal, external_card=True,
                               organization_id=str(organization_id), offset=offset, limit=limit)

    @app.get("/api/admin/organizations/{organization_id}/external-rate-card/history/detail", response_model=HistoryDetail)
    def admin_org_price_revision(organization_id: UUID, principal: Admin, db: Db,
                                revision: str = Query(max_length=200)):
        return pricing_history(db, settings, principal, external_card=True,
                               organization_id=str(organization_id), revision=revision)

    @app.get("/api/admin/rate-card", response_model=RateCardOutput)
    def admin_rate_card(principal: Admin, db: Db) -> RateCardOutput:
        return get_rate_card(db, settings)

    @app.put("/api/admin/rate-card", response_model=RateCardOutput)
    def admin_save_rate_card(payload: RateCardUpdate, principal: Admin, db: Db, apim: Apim) -> RateCardOutput:
        saved = save_rate_card(db, settings, principal, payload)
        if settings.auto_pricing_sync_enabled:
            from aiflux.auto_pricing import after_save
            saved.auto_pricing = after_save(db, settings, apim)
        return saved

    @app.get("/api/admin/external-rate-card", response_model=RateCardOutput)
    def admin_external_rate_card(principal: Admin, db: Db) -> RateCardOutput:
        return get_external_card(db, settings)

    @app.put("/api/admin/external-rate-card", response_model=RateCardOutput)
    def admin_save_external_rate_card(payload: ExternalCardUpdate, principal: Admin, db: Db) -> RateCardOutput:
        return save_external_card(db, settings, principal, payload)

    @app.get("/api/admin/organizations/{organization_id}/external-rate-card", response_model=RateCardOutput)
    def admin_org_external_rate_card(organization_id: UUID, principal: Admin, db: Db) -> RateCardOutput:
        if db.get(Organization, str(organization_id)) is None:
            raise HTTPException(404, "Organization not found")
        return get_external_card(db, settings, str(organization_id))

    @app.put("/api/admin/organizations/{organization_id}/external-rate-card", response_model=RateCardOutput)
    def admin_save_org_external_rate_card(organization_id: UUID, payload: ExternalCardUpdate,
                                         principal: Admin, db: Db) -> RateCardOutput:
        return save_external_card(db, settings, principal, payload, str(organization_id))

    @app.get("/api/rate-card", response_model=None)
    def customer_rate_card(principal: User, db: Db) -> dict:
        result = customer_safe(get_external_card(db, settings, principal.organization_id))
        if settings.model_access_enabled:
            result["items"] = model_access_service.filter_items(db, principal.organization_id, result["items"])
            result["total"] = len(result["items"])
        return result

    @app.get("/api/model-garden", response_model=None)
    def customer_model_garden(principal: User, db: Db) -> dict:
        items = list_model_garden(db, settings, include_disabled=False,
                                  pricing_context=snapshot(db, principal.organization_id))
        if settings.model_access_enabled:
            items = model_access_service.filter_items(db, principal.organization_id, items)
        return customer_safe({"items": items, "total": len(items)})

    @app.get("/api/admin/organizations/{organization_id}/model-access")
    @app.get("/api/admin/organizations/{organization_id}/model-access/status")
    def admin_model_access(organization_id: UUID, principal: Admin, db: Db) -> dict:
        return model_access_service.get_access(db, settings, principal, str(organization_id))

    @app.put("/api/admin/organizations/{organization_id}/model-access", status_code=202)
    def admin_save_model_access(organization_id: UUID, payload: model_access_service.AccessUpdate,
                               principal: Admin, db: Db) -> dict:
        return model_access_service.save_access(db, settings, principal, str(organization_id), payload)

    @app.post("/api/admin/organizations/{organization_id}/model-access/retry", status_code=202)
    def admin_retry_model_access(organization_id: UUID, principal: Admin, db: Db) -> dict:
        model_access_service.get_access(db, settings, principal, str(organization_id))
        model_access_service.queue(db)
        db.commit()
        return model_access_service.get_access(db, settings, principal, str(organization_id))

    @app.get("/api/admin/model-garden", response_model=Page[ModelGardenItemOutput])
    def admin_model_garden(principal: Admin, db: Db) -> dict:
        items = list_model_garden(db, settings, include_disabled=True)
        return {"items": items, "total": len(items)}

    @app.post("/api/admin/model-garden", response_model=ModelGardenItemOutput)
    @app.put("/api/admin/model-garden/{model_id}", response_model=ModelGardenItemOutput)
    def save_model_garden_item(
        payload: ModelGardenUpsert, principal: Admin, db: Db, model_id: str | None = None
    ) -> ModelGardenItemOutput:
        if model_id is not None and payload.id != model_id:
            raise HTTPException(422, "Path model_id must match payload id")
        AcceptedInventory.load(settings)
        upsert_model_garden_item(db, principal, payload)
        return next(item for item in list_model_garden(db, settings) if item.id == payload.id)

    @app.get("/api/credits/summary", response_model=None)
    def customer_credits_summary(
        principal: User,
        db: Db,
        days: int = Query(30, ge=1, le=366),
        subscription_id: UUID | None = None,
    ) -> dict:
        check_usage_subscription(db, principal.organization_id, subscription_id)
        return customer_safe(credit_summary_response(
            db, principal.organization_id, days, str(subscription_id) if subscription_id else None,
            pricing_context=snapshot(db, principal.organization_id),
        ))

    @app.get("/api/admin/finops/summary", response_model=CreditSummaryOutput)
    def admin_finops_summary(
        principal: Admin,
        db: Db,
        organization_id: UUID | None = None,
        days: int = Query(30, ge=1, le=366),
        subscription_id: UUID | None = None,
    ) -> CreditSummaryOutput:
        target_org = str(organization_id) if organization_id else principal.organization_id
        check_usage_subscription(db, target_org, subscription_id)
        return credit_summary_response(
            db, target_org, days, str(subscription_id) if subscription_id else None
        )

    @app.get("/api/admin/monthly-budgets", response_model=Page[AdminMonthlyBudgetListItem])
    def admin_monthly_budgets(principal: Admin, db: Db,
                             offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                             archive_state: Literal["current", "archived"] = "current") -> dict:
        return monthly_budgets.list_summaries(db, offset=offset, limit=limit, archive_state=archive_state)

    @app.get("/api/admin/monthly-budgets/{organization_id}", response_model=AdminMonthlyBudgetDashboard)
    def admin_monthly_budget_dashboard(organization_id: UUID, principal: Admin, db: Db) -> AdminMonthlyBudgetDashboard:
        return monthly_budgets.admin_dashboard(db, str(organization_id))

    @app.put("/api/admin/monthly-budgets/{organization_id}", response_model=MonthlyBudgetSummary)
    def admin_save_monthly_budget(organization_id: UUID, payload: MonthlyBudgetUpdate,
                                  principal: Admin, db: Db) -> MonthlyBudgetSummary:
        return monthly_budgets.save(db, principal, str(organization_id), payload)

    @app.get("/api/admin/monthly-budgets/{organization_id}/history", response_model=Page[MonthlyBudgetRevisionOutput])
    def admin_monthly_budget_history(organization_id: UUID, principal: Admin, db: Db,
                                    offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)) -> dict:
        return monthly_budgets.history(db, str(organization_id), offset=offset, limit=limit)

    @app.get("/api/budget/monthly", response_model=MonthlyBudgetSummary)
    def customer_monthly_budget(principal: User, db: Db) -> dict:
        return customer_safe(monthly_budgets.summary(db, principal.organization_id))

    @app.get("/api/admin/budgets", response_model=Page[CreditBudgetOutput])
    def admin_budgets(
        principal: Admin, db: Db, organization_id: UUID | None = None
    ) -> dict:
        items = list_budgets(db, str(organization_id) if organization_id else None)
        return {"items": items, "total": len(items)}

    @app.put("/api/admin/budgets/{organization_id}", response_model=CreditBudgetOutput)
    def admin_update_budget(
        organization_id: UUID, payload: CreditBudgetUpdate, principal: Admin, db: Db
    ) -> CreditBudgetOutput:
        return upsert_budget(db, principal, str(organization_id), payload)

    @app.post("/api/subscriptions/{sid}/customer-rotate")
    def customer_rotate_key(
        sid: UUID, payload: KeyRequest, principal: User, db: Db, apim: Apim
    ) -> dict:
        lock_organization(db, principal.organization_id)
        row = owned(db, sid, principal)
        if row.state != "active":
            raise HTTPException(409, "Only active subscriptions can rotate keys")
        audit(db, principal, f"subscription.customer_rotate.{payload.key}", row.id)
        db.flush()
        apim.rotate(row.id, payload.key)
        db.commit()
        return {"state": row.state, "rotated_key": payload.key}

    @app.get("/api/model-router", response_model=ModelRouterConfigOutput)
    def customer_model_router_info(principal: User, db: Db) -> ModelRouterConfigOutput:
        return get_router_config_output(db, settings)

    @app.get("/api/auto-routing/availability")
    def auto_routing_availability(principal: User, db: Db) -> dict:
        result = decision_router.availability(db, settings)
        if settings.model_access_enabled and principal.role != "ids_admin":
            access = model_access_service.effective(db, principal.organization_id)
            from aiflux import auto_snapshot
            candidates = auto_snapshot.defaults(settings)["candidates"]
            if access["bootstrap_pending"] or not access["auto_enabled"] or not any(
                c["id"] in access["applied_catalog"] and c["id"] not in access["denied_models"] for c in candidates
            ):
                result = {**result, "ready": False, "reason": "organization_model_access"}
        return result

    @app.get("/api/admin/auto-routing")
    def admin_auto_configuration(principal: Admin, db: Db) -> dict:
        return decision_router.admin_configuration(db, settings)

    @app.post("/api/admin/auto-routing/initialize")
    def admin_initialize_auto(principal: Admin, db: Db) -> dict:
        return decision_router.seed_profiles(db, settings, principal)

    @app.put("/api/admin/auto-routing/{profile}")
    def admin_save_auto(profile: decision_router.Profile, payload: decision_router.ProfileUpdate,
                        principal: Admin, db: Db) -> dict:
        return decision_router.save_profile(db, settings, principal, profile, payload)

    @app.post("/internal/auto-routing/resolve", dependencies=[Depends(require_gateway)])
    def internal_auto_resolve(payload: decision_router.ResolveRequest, db: Db) -> dict:
        if not (settings.auto_routing_legacy_resolver_enabled and settings.auto_routing_enabled and settings.auto_routing_contract_verified
                and settings.auto_routing_gateway_ready):
            raise HTTPException(503, "Auto routing is not ready")
        if app.state.auto_decision_client is None:
            app.state.auto_decision_client = DecisionClient(client_id=os.environ.get("AZURE_CLIENT_ID"),
                timeout=settings.auto_decision_timeout_seconds)
        return decision_router.resolve(db, settings, payload, app.state.auto_decision_client)

    @app.get("/api/admin/model-router", response_model=ModelRouterConfigOutput)
    def admin_get_model_router(principal: Admin, db: Db) -> ModelRouterConfigOutput:
        return get_router_config_output(db, settings)

    @app.put("/api/admin/model-router", response_model=ModelRouterConfigOutput)
    def admin_update_model_router(
        payload: ModelRouterConfigUpdate, principal: Admin, db: Db
    ) -> ModelRouterConfigOutput:
        return update_router_config(db, settings, principal, payload)

    @app.post("/api/model-router/decide", response_model=None)
    def model_router_decide(
        payload: RouterDecisionRequest, principal: User, db: Db
    ) -> dict:
        return customer_routing_decision(decide_model_route(db, settings, payload))

    @app.post("/api/playground/chat", response_model=None)
    def playground_chat(
        payload: PlaygroundChatRequest, principal: User, db: Db
    ) -> dict:
        result = customer_safe(run_playground_chat(db, settings, principal, payload))
        # Legacy inference has no date-effective external context. Never label
        # its internal accounting result as a customer estimate.
        result.pop("estimated_cost_usd", None)
        return result

    @app.get("/api/admin/turnstile/policy-preview", response_model=TurnstilePolicyPreviewOutput)
    def admin_turnstile_policy_preview(principal: Admin, db: Db) -> TurnstilePolicyPreviewOutput:
        return render_turnstile_exchange_policy(db, settings)

    @app.post("/api/auth/login", response_model=LocalLoginResponse)
    def local_auth_login(payload: LocalLoginRequest, db: Db) -> LocalLoginResponse:
        return authenticate_local_user(db, settings, payload)

    @app.post("/api/auth/register", status_code=201, response_model=LocalLoginResponse)
    def local_auth_register(payload: LocalRegisterRequest, db: Db) -> LocalLoginResponse:
        return register_local_user(db, settings, payload)

    @app.get("/api/admin/local-users", response_model=Page[LocalUserOutput])
    def admin_get_local_users(
        principal: Admin, db: Db, organization_id: UUID | None = None
    ) -> dict:
        items = list_local_users(db, settings, str(organization_id) if organization_id else None)
        return {"items": items, "total": len(items)}

    @app.post("/api/admin/local-users", status_code=201, response_model=LocalUserOutput)
    def admin_add_local_user(
        payload: LocalUserCreate, principal: Admin, db: Db
    ) -> LocalUserOutput:
        return create_local_user(db, settings, principal, payload)

    @app.put("/api/admin/local-users/{user_id}", response_model=LocalUserOutput)
    def admin_modify_local_user(
        user_id: UUID, payload: LocalUserUpdate, principal: Admin, db: Db
    ) -> LocalUserOutput:
        return update_local_user(db, principal, str(user_id), payload)

    @app.post("/v1/chat/completions")
    def local_gateway_chat_completions(
        payload: dict[str, Any],
        db: Db,
        subscription_key: str | None = Header(default=None, alias="Ocp-Apim-Subscription-Key"),
    ) -> dict[str, Any]:
        if not settings.local_auth_enabled:
            raise HTTPException(404, "Not found")
        if not subscription_key or not subscription_key.strip():
            raise HTTPException(401, "Missing Ocp-Apim-Subscription-Key header")
        from aiflux.turnstile_exchange import ensure_local_users_seeded

        ensure_local_users_seeded(db, settings)
        cust_org = db.scalar(
            select(Organization).where(Organization.tenant_id == "00000000-0000-0000-0000-000000000002")
        ) or db.scalar(select(Organization))
        if cust_org is None:
            raise HTTPException(503, "No organization configured")
        principal = Principal(
            cust_org.id, cust_org.name, cust_org.tenant_id, "00000000-0000-0000-0000-000000000202", "customer"
        )
        raw_msgs = payload.get("messages") or [{"role": "user", "content": "Hello"}]
        req = PlaygroundChatRequest(
            model=str(payload.get("model", "auto")),
            messages=[
                PlaygroundMessage(role=m.get("role", "user"), content=str(m.get("content", "")))
                for m in raw_msgs
                if isinstance(m, dict) and m.get("content")
            ],
            max_completion_tokens=int(payload.get("max_completion_tokens") or 512),
        )
        res = run_playground_chat(db, settings, principal, req)
        return {
            "id": res.id,
            "object": "chat.completion",
            "model": res.selected_model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": res.reply},
                    "finish_reason": "content_filter" if res.safety_status == "blocked" else "stop",
                }
            ],
            "usage": {
                "prompt_tokens": res.input_tokens,
                "completion_tokens": res.output_tokens,
                "total_tokens": res.total_tokens,
            },
            "routing_decision": customer_routing_decision(res.routing_decision) if res.routing_decision else None,
        }

    portals_dir = os.environ.get("AIFLUX_SERVE_PORTALS_DIR", "").strip()
    if portals_dir and Path(portals_dir).is_dir():
        root_dir = Path(portals_dir).resolve()
        admin_dist = (root_dir / "admin").resolve()
        customer_dist = (root_dir / "customer").resolve()

        @app.get("/admin", include_in_schema=False)
        @app.get("/admin/{subpath:path}", include_in_schema=False)
        def serve_admin_spa(subpath: str = "") -> FileResponse:
            if subpath:
                candidate = (admin_dist / subpath).resolve()
                if candidate.is_relative_to(admin_dist) and candidate.is_file():
                    return FileResponse(candidate)
            return FileResponse(admin_dist / "index.html")

        @app.get("/", include_in_schema=False)
        @app.get("/{subpath:path}", include_in_schema=False)
        def serve_customer_spa(subpath: str = "") -> FileResponse:
            if subpath.startswith(("api/", "v1/", "health", "ready", ".well-known/", "_edge-denied/")):
                raise HTTPException(404, "Not found")
            if subpath:
                candidate = (customer_dist / subpath).resolve()
                if candidate.is_relative_to(customer_dist) and candidate.is_file():
                    return FileResponse(candidate)
            return FileResponse(customer_dist / "index.html")

    return app


def price_dict(row: ModelPrice) -> dict:
    values = entity_dict(row, ("id", "model", "provider", "region", "currency", "input_includes_cached"))
    for name in (
        "input_per_million",
        "output_per_million",
        "cached_input_per_million",
        "cache_write_per_million",
    ):
        value = getattr(row, name)
        values[name] = str(value) if value is not None else None
    values["effective_from"] = aware(row.effective_from).isoformat()
    values["effective_to"] = aware(row.effective_to).isoformat() if row.effective_to else None
    return values


app = create_app()
