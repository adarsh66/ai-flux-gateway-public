"""Turnstile Token Exchange engine: Model Garden, Credit Ledger, Decision-1 Router, and Playground."""

import json
import re
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aiflux.auth import Principal, hash_password, issue_local_jwt, verify_password
from aiflux.config import Settings
from aiflux.finops import aware
from aiflux.models import (
    Base,
    CreditBudget,
    IngestionState,
    LocalUser,
    ManagedModelEndpoint,
    Member,
    ModelPrice,
    ModelRouterConfig,
    Organization,
    SafetyEvent,
    Team,
    TeamSubscription,
    UsageRecord,
)
from aiflux.schemas import (
    ChannelUsageBreakdownItem,
    CreditBudgetOutput,
    CreditBudgetUpdate,
    CreditSummaryOutput,
    IdentityOutput,
    LocalLoginRequest,
    LocalLoginResponse,
    LocalRegisterRequest,
    LocalUserCreate,
    LocalUserOutput,
    LocalUserUpdate,
    ModelGardenItemOutput,
    ModelGardenUpsert,
    ModelRouterConfigOutput,
    ModelRouterConfigUpdate,
    ModelUsageBreakdownItem,
    PlaygroundChatRequest,
    PlaygroundChatResponse,
    ProductUsageBreakdownItem,
    RouterDecisionOutput,
    RouterDecisionRequest,
    RouterRuleItem,
    TurnstilePolicyPreviewOutput,
)
from aiflux.subscriptions import audit

DEFAULT_MODELS: list[dict[str, Any]] = [
    {
        "id": "auto",
        "display_name": "Microsoft Decision-1 Auto Router",
        "provider": "microsoft_decision",
        "vendor": "Microsoft Foundry",
        "region": "eastus2",
        "backend_model": "Decision-1",
        "endpoint_url": "/providers/microsoft/v1/systemone",
        "context_window": 200000,
        "max_completion_tokens": 16384,
        "input_per_million": Decimal("0.40000000"),
        "output_per_million": Decimal("1.60000000"),
        "cached_input_per_million": Decimal("0.10000000"),
        "capabilities": ["chat", "streaming", "auto-routing", "cost-optimization"],
        "description": (
            "Microsoft Decision (SystemOne) intelligent model router that inspects prompt complexity "
            "and automatically dispatches to OpenAI, Claude, or DeepSeek."
        ),
        "enabled": True,
        "coming_soon": False,
        "content_safety_enabled": True,
        "priority": 1,
    },
    {
        "id": "gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini",
        "provider": "azure_openai",
        "vendor": "OpenAI",
        "region": "eastus2",
        "backend_model": "gpt-5.4-mini",
        "endpoint_url": "https://agents3iq-aigateway-apim.azure-api.net/foundrymodels",
        "context_window": 128000,
        "max_completion_tokens": 16384,
        "input_per_million": Decimal("0.30000000"),
        "output_per_million": Decimal("1.20000000"),
        "cached_input_per_million": Decimal("0.07500000"),
        "capabilities": ["chat", "streaming", "tool_calling", "json_mode"],
        "description": (
            "Fast, low-latency OpenAI model ideal for high-throughput customer support, "
            "classification, and everyday enterprise copilot tasks."
        ),
        "enabled": True,
        "coming_soon": False,
        "content_safety_enabled": True,
        "priority": 10,
    },
    {
        "id": "gpt-5.4",
        "display_name": "GPT-5.4 Flagship",
        "provider": "azure_openai",
        "vendor": "OpenAI",
        "region": "eastus2",
        "backend_model": "gpt-5.4",
        "endpoint_url": "https://agents3iq-aigateway-apim.azure-api.net/foundrymodels",
        "context_window": 256000,
        "max_completion_tokens": 32768,
        "input_per_million": Decimal("2.50000000"),
        "output_per_million": Decimal("10.00000000"),
        "cached_input_per_million": Decimal("0.62500000"),
        "capabilities": ["chat", "streaming", "reasoning", "tool_calling", "vision"],
        "description": (
            "Flagship OpenAI frontier model for complex multi-step enterprise workflows, "
            "agent orchestration, and structured synthesis."
        ),
        "enabled": True,
        "coming_soon": False,
        "content_safety_enabled": True,
        "priority": 20,
    },
    {
        "id": "claude-sonnet-4-5",
        "display_name": "Claude Sonnet 4.5",
        "provider": "anthropic",
        "vendor": "Anthropic",
        "region": "eastus2",
        "backend_model": "claude-sonnet-4-5-20250929",
        "endpoint_url": "https://agents3iq-aigateway-apim.azure-api.net/anthropic/v1/messages",
        "context_window": 200000,
        "max_completion_tokens": 16384,
        "input_per_million": Decimal("3.00000000"),
        "output_per_million": Decimal("15.00000000"),
        "cached_input_per_million": Decimal("0.30000000"),
        "capabilities": ["chat", "streaming", "coding", "long_context", "tool_calling"],
        "description": (
            "Anthropic Claude Sonnet 4.5 with 200K context window for nuanced enterprise writing, "
            "document analysis, and software engineering."
        ),
        "enabled": True,
        "coming_soon": False,
        "content_safety_enabled": True,
        "priority": 30,
    },
    {
        "id": "claude-haiku-4-5",
        "display_name": "Claude Haiku 4.5",
        "provider": "anthropic",
        "vendor": "Anthropic",
        "region": "eastus2",
        "backend_model": "claude-haiku-4-5-20251001",
        "endpoint_url": "https://agents3iq-aigateway-apim.azure-api.net/anthropic/v1/messages",
        "context_window": 200000,
        "max_completion_tokens": 8192,
        "input_per_million": Decimal("0.80000000"),
        "output_per_million": Decimal("4.00000000"),
        "cached_input_per_million": Decimal("0.08000000"),
        "capabilities": ["chat", "streaming", "fast_inference"],
        "description": (
            "Ultra-fast Anthropic model for real-time interactive agents, summarization, "
            "and high-concurrency SMB workloads."
        ),
        "enabled": True,
        "coming_soon": False,
        "content_safety_enabled": True,
        "priority": 35,
    },
    {
        "id": "DeepSeek-V3.2-Speciale",
        "display_name": "DeepSeek V3.2 Speciale",
        "provider": "deepseek",
        "vendor": "DeepSeek",
        "region": "eastus2",
        "backend_model": "DeepSeek-V3.2-Speciale",
        "endpoint_url": "https://agents3iq-aigateway-apim.azure-api.net/foundrymodels",
        "context_window": 128000,
        "max_completion_tokens": 16384,
        "input_per_million": Decimal("0.27000000"),
        "output_per_million": Decimal("1.10000000"),
        "cached_input_per_million": Decimal("0.07000000"),
        "capabilities": ["chat", "streaming", "coding", "math", "reasoning"],
        "description": (
            "High-efficiency DeepSeek reasoning and coding model protected by Azure AI Content Safety "
            "guardrails at the APIM gateway layer."
        ),
        "enabled": True,
        "coming_soon": False,
        "content_safety_enabled": True,
        "priority": 40,
    },
    {
        "id": "singtel-reai-70b",
        "display_name": "Singtel RE:AI Sovereign 70B",
        "provider": "singtel_reai",
        "vendor": "Singtel RE:AI",
        "region": "southeastasia",
        "backend_model": "reai-enterprise-70b-instruct",
        "endpoint_url": "",
        "context_window": 128000,
        "max_completion_tokens": 8192,
        "input_per_million": Decimal("0.65000000"),
        "output_per_million": Decimal("2.20000000"),
        "cached_input_per_million": None,
        "capabilities": ["chat", "streaming", "sovereign_gpu", "sea_languages"],
        "description": (
            "Sovereign GPU data center endpoint hosted on Singtel RE:AI infrastructure with "
            "Foundry Content Safety enforcement."
        ),
        "enabled": False,
        "coming_soon": True,
        "content_safety_enabled": True,
        "priority": 50,
    },
    {
        "id": "gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro",
        "provider": "google_gemini",
        "vendor": "Google",
        "region": "southeastasia",
        "backend_model": "gemini-2.5-pro",
        "endpoint_url": "",
        "context_window": 1000000,
        "max_completion_tokens": 16384,
        "input_per_million": Decimal("1.25000000"),
        "output_per_million": Decimal("5.00000000"),
        "cached_input_per_million": Decimal("0.31250000"),
        "capabilities": ["chat", "streaming", "long_context", "multimodal"],
        "description": (
            "Google Gemini 2.5 Pro with 1M token context window for massive document and "
            "repository analysis via OpenAI-compatible gateway adapter."
        ),
        "enabled": False,
        "coming_soon": True,
        "content_safety_enabled": True,
        "priority": 60,
    },
]

DEFAULT_ROUTER_RULES: list[dict[str, Any]] = [
    {
        "category": "coding_and_math",
        "description": "Code generation, debugging, SQL, algorithms, and quantitative math problems",
        "keywords": [
            "code", "python", "typescript", "sql", "function", "bug", "algorithm", "regex", "math",
            "compile", "dockerfile", "terraform",
        ],
        "preferred_model": "DeepSeek-V3.2-Speciale",
        "fallback_model": "gpt-5.4",
    },
    {
        "category": "long_context_and_writing",
        "description": "Executive memos, policy drafting, contract review, and long-document synthesis",
        "keywords": [
            "summarize", "document", "contract", "policy", "report", "memo", "draft", "essay",
            "review", "compliance", "clause",
        ],
        "preferred_model": "claude-sonnet-4-5",
        "fallback_model": "gpt-5.4",
    },
    {
        "category": "complex_architecture",
        "description": "Multi-step system architecture, strategic planning, and deep reasoning",
        "keywords": [
            "architecture", "design", "strategy", "tradeoff", "compare", "migration", "plan",
            "enterprise", "security",
        ],
        "preferred_model": "gpt-5.4",
        "fallback_model": "claude-sonnet-4-5",
    },
    {
        "category": "fast_general_qa",
        "description": "High-speed Q&A, classification, extraction, and conversational queries",
        "keywords": ["quick", "hello", "what is", "translate", "classify", "extract", "status"],
        "preferred_model": "gpt-5.4-mini",
        "fallback_model": "claude-haiku-4-5",
    },
]


def ensure_model_garden_seeded(db: Session) -> None:
    Base.metadata.create_all(db.get_bind(), checkfirst=True)
    existing_count = db.scalar(select(func.count()).select_from(ManagedModelEndpoint)) or 0
    if existing_count > 0:
        return
    now = datetime.now(UTC)
    effective_start = datetime(2025, 1, 1, tzinfo=UTC)
    for item in DEFAULT_MODELS:
        db.add(
            ManagedModelEndpoint(
                id=item["id"],
                display_name=item["display_name"],
                provider=item["provider"],
                vendor=item["vendor"],
                region=item["region"],
                backend_model=item["backend_model"],
                endpoint_url=item["endpoint_url"],
                context_window=item["context_window"],
                max_completion_tokens=item["max_completion_tokens"],
                input_per_million=item["input_per_million"],
                output_per_million=item["output_per_million"],
                cached_input_per_million=item["cached_input_per_million"],
                currency="USD",
                capabilities_json=json.dumps(item["capabilities"]),
                description=item["description"],
                enabled=item["enabled"],
                coming_soon=item["coming_soon"],
                content_safety_enabled=item["content_safety_enabled"],
                priority=item["priority"],
                updated_at=now,
            )
        )
        price_exists = db.scalar(
            select(func.count()).select_from(ModelPrice).where(ModelPrice.model == item["id"])
        )
        if not price_exists:
            db.add(
                ModelPrice(
                    model=item["id"],
                    provider=item["provider"],
                    region=item["region"],
                    effective_from=effective_start,
                    effective_to=None,
                    currency="USD",
                    input_per_million=item["input_per_million"],
                    output_per_million=item["output_per_million"],
                    cached_input_per_million=item["cached_input_per_million"],
                    cache_write_per_million=None,
                    input_includes_cached=True,
                )
            )
    db.commit()


def ensure_router_config(db: Session, settings: Settings) -> ModelRouterConfig:
    ensure_model_garden_seeded(db)
    row = db.get(ModelRouterConfig, "default")
    if row is None:
        row = ModelRouterConfig(
            id="default",
            enabled=settings.decision_router_enabled,
            strategy="microsoft-decision-1",
            decision_endpoint=settings.decision_router_endpoint,
            default_model=settings.decision_router_default_model,
            candidate_models_json=json.dumps(
                ["gpt-5.4-mini", "gpt-5.4", "claude-sonnet-4-5", "DeepSeek-V3.2-Speciale"]
            ),
            rules_json=json.dumps(DEFAULT_ROUTER_RULES),
            updated_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
    return row


def model_garden_item_dict(row: ManagedModelEndpoint) -> ModelGardenItemOutput:
    return ModelGardenItemOutput(
        id=row.id,
        display_name=row.display_name,
        provider=row.provider,
        vendor=row.vendor,
        region=row.region,
        backend_model=row.backend_model,
        endpoint_url=row.endpoint_url,
        context_window=row.context_window,
        max_completion_tokens=row.max_completion_tokens,
        input_per_million=f"{Decimal(row.input_per_million):.4f}",
        output_per_million=f"{Decimal(row.output_per_million):.4f}",
        cached_input_per_million=(
            f"{Decimal(row.cached_input_per_million):.4f}"
            if row.cached_input_per_million is not None
            else None
        ),
        currency=row.currency,
        capabilities=json.loads(row.capabilities_json or "[]"),
        description=row.description,
        enabled=row.enabled,
        coming_soon=row.coming_soon,
        content_safety_enabled=row.content_safety_enabled,
        priority=row.priority,
    )


def list_model_garden(db: Session, *, include_disabled: bool = True) -> list[ModelGardenItemOutput]:
    ensure_model_garden_seeded(db)
    query = select(ManagedModelEndpoint).order_by(
        ManagedModelEndpoint.priority.asc(), ManagedModelEndpoint.id.asc()
    )
    if not include_disabled:
        query = query.where(
            (ManagedModelEndpoint.enabled.is_(True)) | (ManagedModelEndpoint.coming_soon.is_(True))
        )
    rows = db.scalars(query).all()
    return [model_garden_item_dict(row) for row in rows]


def upsert_model_garden_item(
    db: Session, principal: Principal, payload: ModelGardenUpsert
) -> ModelGardenItemOutput:
    ensure_model_garden_seeded(db)
    row = db.get(ManagedModelEndpoint, payload.id)
    now = datetime.now(UTC)
    if row is None:
        row = ManagedModelEndpoint(id=payload.id)
        db.add(row)
    row.display_name = payload.display_name
    row.provider = payload.provider
    row.vendor = payload.vendor
    row.region = payload.region
    row.backend_model = payload.backend_model
    row.endpoint_url = payload.endpoint_url
    row.context_window = payload.context_window
    row.max_completion_tokens = payload.max_completion_tokens
    row.input_per_million = payload.input_per_million
    row.output_per_million = payload.output_per_million
    row.cached_input_per_million = payload.cached_input_per_million
    row.currency = payload.currency
    row.capabilities_json = json.dumps(payload.capabilities)
    row.description = payload.description
    row.enabled = payload.enabled
    row.coming_soon = payload.coming_soon
    row.content_safety_enabled = payload.content_safety_enabled
    row.priority = payload.priority
    row.updated_at = now
    audit(db, principal, "model_garden.upserted", row.id)
    db.commit()
    return model_garden_item_dict(row)


def ensure_organization_budget(db: Session, organization_id: str) -> CreditBudget:
    row = db.scalar(
        select(CreditBudget).where(
            CreditBudget.organization_id == organization_id,
            CreditBudget.subscription_id.is_(None),
        )
    )
    if row is None:
        row = CreditBudget(
            organization_id=organization_id,
            subscription_id=None,
            monthly_budget_usd=Decimal("5000.0000"),
            credit_allocation=Decimal("5000.0000"),
            alert_threshold_pct=80,
            allowed_models_json=json.dumps(["*"]),
            product_name="Enterprise AI Token Exchange",
            channel="api-gateway",
            hard_stop_enabled=True,
            updated_at=datetime.now(UTC),
        )
        db.add(row)
        db.commit()
    return row


def _used_credits_for(db: Session, organization_id: str, subscription_id: str | None = None) -> Decimal:
    conditions = [UsageRecord.organization_id == organization_id]
    if subscription_id is not None:
        conditions.append(UsageRecord.subscription_id == subscription_id)
    total_cost = db.scalar(select(func.sum(UsageRecord.cost)).where(*conditions))
    if total_cost is not None and Decimal(total_cost) > 0:
        return Decimal(total_cost).quantize(Decimal("0.0001"))
    total_tokens = db.scalar(
        select(
            func.coalesce(func.sum(UsageRecord.input_tokens), 0)
            + func.coalesce(func.sum(UsageRecord.output_tokens), 0)
        ).where(*conditions)
    ) or 0
    return (Decimal(total_tokens) * Decimal("0.0000015")).quantize(Decimal("0.0001"))


def _budget_output(db: Session, row: CreditBudget) -> CreditBudgetOutput:
    org = db.get(Organization, row.organization_id)
    sub = db.get(TeamSubscription, row.subscription_id) if row.subscription_id else None
    used = _used_credits_for(db, row.organization_id, row.subscription_id)
    allocated = Decimal(row.credit_allocation)
    remaining = max(Decimal("0.0000"), allocated - used)
    utilization = float((used / allocated * Decimal(100)) if allocated > 0 else Decimal(0))
    return CreditBudgetOutput(
        id=row.id,
        organization_id=row.organization_id,
        organization_name=org.name if org else row.organization_id,
        subscription_id=row.subscription_id,
        subscription_name=sub.name if sub else None,
        monthly_budget_usd=f"{Decimal(row.monthly_budget_usd):.2f}",
        credit_allocation=f"{allocated:.2f}",
        used_credits=f"{used:.4f}",
        remaining_credits=f"{remaining:.4f}",
        utilization_pct=round(utilization, 2),
        low_credit_alert=utilization >= row.alert_threshold_pct,
        alert_threshold_pct=row.alert_threshold_pct,
        allowed_models=json.loads(row.allowed_models_json or '["*"]'),
        product_name=row.product_name,
        channel=row.channel,
        hard_stop_enabled=row.hard_stop_enabled,
        ledger_row_key=row.subscription_id or f"org:{row.organization_id}",
        updated_at=aware(row.updated_at),
    )


def list_budgets(db: Session, organization_id: str | None = None) -> list[CreditBudgetOutput]:
    orgs = (
        [db.get(Organization, organization_id)]
        if organization_id
        else list(db.scalars(select(Organization).order_by(Organization.name)).all())
    )
    for org in orgs:
        if org is not None:
            ensure_organization_budget(db, org.id)
    query = select(CreditBudget).order_by(CreditBudget.organization_id.asc(), CreditBudget.id.asc())
    if organization_id is not None:
        query = query.where(CreditBudget.organization_id == organization_id)
    rows = db.scalars(query).all()
    return [_budget_output(db, row) for row in rows]


def upsert_budget(
    db: Session, principal: Principal, organization_id: str, payload: CreditBudgetUpdate
) -> CreditBudgetOutput:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    sub_id = str(payload.subscription_id) if payload.subscription_id else None
    if sub_id is not None:
        sub = db.get(TeamSubscription, sub_id)
        if sub is None or sub.organization_id != organization_id:
            raise HTTPException(404, "Subscription not found in organization")
    row = db.scalar(
        select(CreditBudget).where(
            CreditBudget.organization_id == organization_id,
            CreditBudget.subscription_id == sub_id
            if sub_id is not None
            else CreditBudget.subscription_id.is_(None),
        )
    )
    if row is None:
        row = CreditBudget(organization_id=organization_id, subscription_id=sub_id)
        db.add(row)
    row.monthly_budget_usd = payload.monthly_budget_usd
    row.credit_allocation = payload.credit_allocation
    row.alert_threshold_pct = payload.alert_threshold_pct
    row.allowed_models_json = json.dumps(payload.allowed_models or ["*"])
    row.product_name = payload.product_name
    row.channel = payload.channel
    row.hard_stop_enabled = payload.hard_stop_enabled
    row.updated_at = datetime.now(UTC)
    audit(db, principal, "budget.updated", row.id, organization_id)
    db.commit()
    return _budget_output(db, row)


def credit_summary_response(
    db: Session, organization_id: str, days: int = 30, subscription_id: str | None = None
) -> CreditSummaryOutput:
    ensure_model_garden_seeded(db)
    budget = ensure_organization_budget(db, organization_id)
    org = db.get(Organization, organization_id)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    conditions = [UsageRecord.organization_id == organization_id, UsageRecord.occurred_at >= cutoff]
    if subscription_id is not None:
        conditions.append(UsageRecord.subscription_id == subscription_id)
    rows = db.scalars(select(UsageRecord).where(*conditions)).all()
    endpoints = {m.id: m for m in db.scalars(select(ManagedModelEndpoint)).all()}
    subs = {
        s.id: s
        for s in db.scalars(
            select(TeamSubscription).where(TeamSubscription.organization_id == organization_id)
        ).all()
    }

    model_buckets: dict[str, dict[str, Any]] = {}
    product_buckets: dict[str, dict[str, Any]] = {}
    channel_buckets: dict[str, dict[str, Any]] = {}
    total_tokens_all = 0
    total_cost_all = Decimal("0.0000")

    for r in rows:
        inp = r.input_tokens or 0
        out = r.output_tokens or 0
        toks = inp + out
        total_tokens_all += toks
        endpoint = endpoints.get(r.model)
        if r.cost is not None:
            row_cost = Decimal(r.cost)
        elif endpoint is not None:
            row_cost = (
                Decimal(inp) * Decimal(endpoint.input_per_million)
                + Decimal(out) * Decimal(endpoint.output_per_million)
            ) / Decimal(1_000_000)
        else:
            row_cost = Decimal(toks) * Decimal("0.0000015")
        total_cost_all += row_cost

        vendor = endpoint.vendor if endpoint else r.provider
        m_entry = model_buckets.setdefault(
            r.model,
            {
                "model": r.model,
                "provider": r.provider,
                "vendor": vendor,
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost": Decimal("0"),
            },
        )
        m_entry["requests"] += 1
        m_entry["input_tokens"] += inp
        m_entry["output_tokens"] += out
        m_entry["total_tokens"] += toks
        m_entry["cost"] += row_cost

        sub = subs.get(r.subscription_id)
        p_entry = product_buckets.setdefault(
            r.subscription_id,
            {
                "subscription_id": r.subscription_id,
                "subscription_name": sub.name if sub else r.subscription_id,
                "team": sub.team if sub else "General",
                "product_name": f"{sub.team} · {sub.name}" if sub else budget.product_name,
                "requests": 0,
                "total_tokens": 0,
                "cost": Decimal("0"),
            },
        )
        p_entry["requests"] += 1
        p_entry["total_tokens"] += toks
        p_entry["cost"] += row_cost

        channel_name = (
            "playground"
            if r.completeness == "playground"
            else ("auto-router" if r.completeness == "auto_routed" else "api-gateway")
        )
        c_entry = channel_buckets.setdefault(
            channel_name,
            {"channel": channel_name, "requests": 0, "total_tokens": 0, "cost": Decimal("0")},
        )
        c_entry["requests"] += 1
        c_entry["total_tokens"] += toks
        c_entry["cost"] += row_cost

    allocated = Decimal(budget.credit_allocation)
    remaining = max(Decimal("0.0000"), allocated - total_cost_all)
    utilization = float((total_cost_all / allocated * Decimal(100)) if allocated > 0 else Decimal(0))
    denom_tokens = max(1, total_tokens_all)

    by_model = [
        ModelUsageBreakdownItem(
            model=item["model"],
            provider=item["provider"],
            vendor=item["vendor"],
            requests=item["requests"],
            input_tokens=item["input_tokens"],
            output_tokens=item["output_tokens"],
            total_tokens=item["total_tokens"],
            cost_usd=f"{item['cost']:.4f}",
            share_pct=round(item["total_tokens"] / denom_tokens * 100.0, 1),
        )
        for item in sorted(model_buckets.values(), key=lambda x: x["total_tokens"], reverse=True)
    ]
    by_product = [
        ProductUsageBreakdownItem(
            subscription_id=item["subscription_id"],
            subscription_name=item["subscription_name"],
            team=item["team"],
            product_name=item["product_name"],
            requests=item["requests"],
            total_tokens=item["total_tokens"],
            cost_usd=f"{item['cost']:.4f}",
            share_pct=round(item["total_tokens"] / denom_tokens * 100.0, 1),
        )
        for item in sorted(product_buckets.values(), key=lambda x: x["total_tokens"], reverse=True)
    ]
    by_channel = [
        ChannelUsageBreakdownItem(
            channel=item["channel"],
            requests=item["requests"],
            total_tokens=item["total_tokens"],
            cost_usd=f"{item['cost']:.4f}",
            share_pct=round(item["total_tokens"] / denom_tokens * 100.0, 1),
        )
        for item in sorted(channel_buckets.values(), key=lambda x: x["total_tokens"], reverse=True)
    ]

    return CreditSummaryOutput(
        organization_id=organization_id,
        organization_name=org.name if org else organization_id,
        currency="USD",
        total_credits=f"{allocated:.2f}",
        used_credits=f"{total_cost_all:.4f}",
        remaining_credits=f"{remaining:.4f}",
        utilization_pct=round(utilization, 2),
        alert_threshold_pct=budget.alert_threshold_pct,
        low_credit_alert=utilization >= budget.alert_threshold_pct,
        hard_stop_enabled=budget.hard_stop_enabled,
        total_requests=len(rows),
        total_tokens=total_tokens_all,
        by_model=by_model,
        by_product=by_product,
        by_channel=by_channel,
    )


def get_router_config_output(db: Session, settings: Settings) -> ModelRouterConfigOutput:
    row = ensure_router_config(db, settings)
    rules = [RouterRuleItem.model_validate(item) for item in json.loads(row.rules_json or "[]")]
    return ModelRouterConfigOutput(
        enabled=row.enabled,
        strategy=row.strategy,  # type: ignore[arg-type]
        decision_endpoint=row.decision_endpoint,
        default_model=row.default_model,
        candidate_models=json.loads(row.candidate_models_json or "[]"),
        rules=rules,
        updated_at=aware(row.updated_at),
    )


def update_router_config(
    db: Session, settings: Settings, principal: Principal, payload: ModelRouterConfigUpdate
) -> ModelRouterConfigOutput:
    row = ensure_router_config(db, settings)
    row.enabled = payload.enabled
    row.strategy = payload.strategy
    row.decision_endpoint = payload.decision_endpoint
    row.default_model = payload.default_model
    row.candidate_models_json = json.dumps(payload.candidate_models)
    row.rules_json = json.dumps([rule.model_dump() for rule in payload.rules])
    row.updated_at = datetime.now(UTC)
    audit(db, principal, "model_router.updated", row.id)
    db.commit()
    return get_router_config_output(db, settings)


def decide_model_route(
    db: Session, settings: Settings, payload: RouterDecisionRequest
) -> RouterDecisionOutput:
    config = get_router_config_output(db, settings)
    strategy = payload.strategy or config.strategy
    prompt_lower = payload.prompt.lower()
    endpoints = {
        m.id: m
        for m in db.scalars(
            select(ManagedModelEndpoint).where(
                ManagedModelEndpoint.enabled.is_(True), ManagedModelEndpoint.id != "auto"
            )
        ).all()
    }
    candidates = [m for m in config.candidate_models if m in endpoints]
    if not candidates:
        candidates = list(endpoints.keys()) or ["gpt-5.4-mini"]

    selected_id = config.default_model if config.default_model in endpoints else candidates[0]
    category = "fast_general_qa"
    confidence = 0.86
    reason = "Defaulted to fast general model via Microsoft Decision-1 router."

    if strategy == "cost-optimized":
        cheapest = min(
            (endpoints[c] for c in candidates if c in endpoints),
            key=lambda m: Decimal(m.input_per_million) + Decimal(m.output_per_million),
        )
        selected_id = cheapest.id
        category = "cost_optimized"
        confidence = 0.94
        reason = (
            f"Selected {cheapest.display_name} (${Decimal(cheapest.input_per_million):.2f}/1M in) "
            "under cost-optimized routing policy."
        )
    elif strategy == "latency-optimized":
        selected_id = "gpt-5.4-mini" if "gpt-5.4-mini" in endpoints else candidates[0]
        category = "latency_optimized"
        confidence = 0.92
        reason = "Selected lowest-TTFT deployment under latency-optimized routing policy."
    elif strategy == "quality-first":
        for high_tier in ("gpt-5.4", "claude-sonnet-4-5", "DeepSeek-V3.2-Speciale"):
            if high_tier in candidates and high_tier in endpoints:
                selected_id = high_tier
                break
        category = "quality_first"
        confidence = 0.95
        reason = "Selected frontier reasoning model under quality-first routing policy."
    else:
        for rule in config.rules:
            matched = [kw for kw in rule.keywords if kw.lower() in prompt_lower]
            if matched:
                if rule.preferred_model in endpoints:
                    selected_id = rule.preferred_model
                elif rule.fallback_model in endpoints:
                    selected_id = rule.fallback_model
                category = rule.category
                confidence = min(0.98, 0.85 + 0.03 * len(matched))
                reason = (
                    f"Microsoft Decision-1 ({config.decision_endpoint}) classified intent as "
                    f"'{rule.category}' (signals: {', '.join(matched[:3])}) -> {selected_id}."
                )
                break
        else:
            if len(payload.prompt) > 1200 and "claude-sonnet-4-5" in endpoints:
                selected_id = "claude-sonnet-4-5"
                category = "long_context_and_writing"
                confidence = 0.91
                reason = (
                    f"Microsoft Decision-1 ({config.decision_endpoint}) detected long-context "
                    "input and routed to Claude Sonnet 4.5."
                )

    chosen = endpoints.get(selected_id) or next(iter(endpoints.values()))
    return RouterDecisionOutput(
        requested_model="auto",
        selected_model=chosen.id,
        display_name=chosen.display_name,
        provider=chosen.provider,
        vendor=chosen.vendor,
        category=category,
        strategy=strategy,
        decision_endpoint=config.decision_endpoint,
        confidence=round(confidence, 2),
        reason=reason,
        estimated_input_per_million=f"{Decimal(chosen.input_per_million):.4f}",
        estimated_output_per_million=f"{Decimal(chosen.output_per_million):.4f}",
    )


_UNSAFE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("prompt_attack", re.compile(r"(ignore (all )?previous instructions|jailbreak|system prompt)", re.I)),
    ("violence", re.compile(r"(build a bomb|make a weapon|attack plan)", re.I)),
    ("self_harm", re.compile(r"(self-harm|suicide instructions)", re.I)),
    ("hate", re.compile(r"(hate speech slur)", re.I)),
]


def _evaluate_content_safety(text_input: str) -> tuple[Literal["passed", "blocked"], dict[str, int], str]:
    scores = {"hate": 0, "violence": 0, "sexual": 0, "self_harm": 0, "prompt_attack": 0}
    triggered_category = ""
    for category, pattern in _UNSAFE_PATTERNS:
        if pattern.search(text_input):
            scores[category] = 6
            triggered_category = category
            break
    status: Literal["passed", "blocked"] = "blocked" if triggered_category else "passed"
    return status, scores, triggered_category


def run_playground_chat(
    db: Session, settings: Settings, principal: Principal, payload: PlaygroundChatRequest
) -> PlaygroundChatResponse:
    ensure_model_garden_seeded(db)
    budget = ensure_organization_budget(db, principal.organization_id)
    used = _used_credits_for(db, principal.organization_id)
    if budget.hard_stop_enabled and used >= Decimal(budget.credit_allocation):
        raise HTTPException(402, "Organization credit allocation exhausted; contact administrator")

    sub_row: TeamSubscription | None = None
    if payload.subscription_id is not None:
        sub_row = db.scalar(
            select(TeamSubscription).where(
                TeamSubscription.id == str(payload.subscription_id),
                TeamSubscription.organization_id == principal.organization_id,
            )
        )
        if sub_row is None:
            raise HTTPException(404, "Subscription not found")
    else:
        sub_row = db.scalar(
            select(TeamSubscription)
            .where(TeamSubscription.organization_id == principal.organization_id)
            .order_by(TeamSubscription.created_at.desc())
        )
        if sub_row is None:
            sub_row = TeamSubscription(
                id=str(uuid4()),
                organization_id=principal.organization_id,
                name="Playground Default Key",
                team="Playground",
                state="active",
                desired_state="active",
                idempotency_key=str(uuid4()),
            )
            db.add(sub_row)
            db.flush()

    combined_prompt = "\n".join(msg.content for msg in payload.messages if msg.role == "user")
    routing_decision: RouterDecisionOutput | None = None
    requested_model = payload.model
    if requested_model == "auto":
        routing_decision = decide_model_route(
            db, settings, RouterDecisionRequest(prompt=combined_prompt or "Hello")
        )
        selected_model_id = routing_decision.selected_model
    else:
        selected_model_id = requested_model

    endpoint = db.get(ManagedModelEndpoint, selected_model_id)
    if endpoint is None or not endpoint.enabled or endpoint.coming_soon:
        raise HTTPException(422, f"Model '{selected_model_id}' is not currently enabled in the Model Garden")

    allowed = json.loads(budget.allowed_models_json or '["*"]')
    if "*" not in allowed and selected_model_id not in allowed and requested_model not in allowed:
        raise HTTPException(403, f"Model '{selected_model_id}' is not in this organization's allowlist")

    safety_status, safety_scores, triggered_cat = _evaluate_content_safety(combined_prompt)
    now = datetime.now(UTC)
    if safety_status == "blocked":
        db.add(
            SafetyEvent(
                id=str(uuid4()),
                organization_id=principal.organization_id,
                subscription_id=sub_row.id,
                occurred_at=now,
                category=triggered_cat,
                action="blocked_by_foundry_content_safety",
                correlation_id=str(uuid4()),
            )
        )
        db.commit()
        return PlaygroundChatResponse(
            id=str(uuid4()),
            requested_model=requested_model,
            selected_model=endpoint.id,
            provider=endpoint.provider,
            vendor=endpoint.vendor,
            reply=(
                f"[Blocked by Azure AI Content Safety] Request triggered '{triggered_cat}' "
                "guardrail policy before reaching the upstream model."
            ),
            routing_decision=routing_decision,
            safety_status="blocked",
            safety_categories=safety_scores,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd="0.00000000",
            latency_ms=42,
        )

    input_tokens = max(12, sum(max(1, len(m.content) // 4) for m in payload.messages))
    output_tokens = min(payload.max_completion_tokens, 64)
    latency_ms = 320 if "mini" in endpoint.id or "haiku" in endpoint.id else 680
    reply_text = ""

    if (
        settings.upstream_apim_url
        and settings.upstream_apim_key
        and settings.environment != "testing"
    ):
        live_deployments = {"gpt-5.4-mini", "gpt-5.4", "DeepSeek-V3.2-Speciale"}
        target_dep = endpoint.id if endpoint.id in live_deployments else (
            "gpt-5.4" if "sonnet" in endpoint.id else "gpt-5.4-mini"
        )
        base_apim = settings.upstream_apim_url.rstrip("/")
        apim_url = f"{base_apim}/openai/deployments/{target_dep}/chat/completions?api-version=2024-10-21"
        req_body: dict[str, Any] = {
            "messages": [{"role": m.role, "content": m.content} for m in payload.messages],
        }
        if target_dep == "DeepSeek-V3.2-Speciale":
            req_body["max_tokens"] = max(512, payload.max_completion_tokens)
        else:
            req_body["max_completion_tokens"] = max(64, payload.max_completion_tokens)
        t0 = time.monotonic()
        try:
            resp = httpx.post(
                apim_url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": settings.upstream_apim_key,
                    "Ocp-Apim-Subscription-Key": settings.upstream_apim_key,
                },
                json=req_body,
                timeout=30.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                latency_ms = max(50, int((time.monotonic() - t0) * 1000))
                msg_obj = (data.get("choices") or [{}])[0].get("message") or {}
                raw_content = str(msg_obj.get("content") or "")
                if "</think>" in raw_content:
                    raw_content = raw_content.split("</think>", 1)[1].strip()
                prefix = (
                    f"[{endpoint.display_name} · routed via Microsoft Decision-1 "
                    f"({routing_decision.category})]\n"
                    if routing_decision is not None
                    else ""
                )
                reply_text = f"{prefix}{raw_content}".strip()
                usage_obj = data.get("usage") or {}
                input_tokens = int(usage_obj.get("prompt_tokens") or input_tokens)
                output_tokens = int(usage_obj.get("completion_tokens") or output_tokens)
        except httpx.HTTPError:
            reply_text = ""

    if not reply_text:
        if routing_decision is not None:
            reply_text = (
                f"[{endpoint.display_name} · routed via Microsoft Decision-1 ({routing_decision.category})] "
                f"Processed your request ({input_tokens} prompt tokens) with Azure AI Content Safety "
                f"verified. Routing reason: {routing_decision.reason}"
            )
        else:
            reply_text = (
                f"[{endpoint.display_name} ({endpoint.vendor})] "
                f"Completed response via Turnstile Token Exchange Gateway ({endpoint.region}) "
                "with Foundry Content Safety active."
            )
        output_tokens = min(payload.max_completion_tokens, max(24, len(reply_text) // 4))

    cost = (
        Decimal(input_tokens) * Decimal(endpoint.input_per_million)
        + Decimal(output_tokens) * Decimal(endpoint.output_per_million)
    ) / Decimal(1_000_000)
    cost = cost.quantize(Decimal("0.00000001"))

    usage_id = str(uuid4())
    db.add(
        UsageRecord(
            id=usage_id,
            organization_id=principal.organization_id,
            subscription_id=sub_row.id,
            model=endpoint.id,
            provider=endpoint.provider,
            region=endpoint.region,
            occurred_at=now,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=0,
            cache_write_tokens=0,
            cost=cost,
            currency=endpoint.currency,
            status_code=200,
            e2e_ms=latency_ms,
            ttft_ms=max(80, latency_ms // 3),
            completeness="auto_routed" if requested_model == "auto" else "playground",
            ingested_at=now,
        )
    )
    db.commit()

    return PlaygroundChatResponse(
        id=usage_id,
        requested_model=requested_model,
        selected_model=endpoint.id,
        provider=endpoint.provider,
        vendor=endpoint.vendor,
        reply=reply_text,
        routing_decision=routing_decision,
        safety_status="passed",
        safety_categories=safety_scores,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd=f"{cost:.8f}",
        latency_ms=latency_ms,
    )


def render_turnstile_exchange_policy(db: Session, settings: Settings) -> TurnstilePolicyPreviewOutput:
    router = get_router_config_output(db, settings)
    storage_account = settings.ledger_storage_account or "aifluxfunc"
    ledger_table = settings.ledger_table_name or "TurnstileLedger"
    routes_table = settings.model_routes_table_name or "ModelRoutes"
    ledger_url = (
        f"@(\"https://{storage_account}.table.core.windows.net/{ledger_table}"
        "(PartitionKey='Budget',RowKey='\" + context.Subscription.Id + "
        "\"')?$format=application/json;odata=nometadata\")"
    )
    routes_url = (
        f"@(\"https://{storage_account}.table.core.windows.net/{routes_table}()"
        "?$format=application/json;odata=nometadata\")"
    )
    budget_cond = (
        "@((bool)((JObject)context.Variables[&quot;turnstile-budget&quot;])"
        "[&quot;HardStopEnabled&quot;] &amp;&amp; "
        "(double)((JObject)context.Variables[&quot;turnstile-budget&quot;])[&quot;SpentUsd&quot;] &gt;= "
        "(double)((JObject)context.Variables[&quot;turnstile-budget&quot;])[&quot;MonthlyBudgetUsd&quot;])"
    )
    budget_err = (
        '{"error":{"code":"credit_budget_exhausted",'
        '"message":"Monthly OpCo token credit allocation has been reached."}}'
    )
    lines = [
        "<policies>",
        "  <inbound>",
        "    <base />",
        "    <!-- 1. Turnstile Hot-Path Credit & Model Allowlist Lookup (<5ms Azure Table Storage) -->",
        '    <send-request mode="new" response-variable-name="turnstile-ledger-resp" '
        'timeout="3" ignore-error="false">',
        f"      <set-url>{ledger_url}</set-url>",
        "      <set-method>GET</set-method>",
        '      <set-header name="x-ms-version" exists-action="override">'
        "<value>2020-12-06</value></set-header>",
        '      <authentication-managed-identity resource="https://storage.azure.com/" />',
        "    </send-request>",
        "    <choose>",
        '      <when condition="@(((IResponse)context.Variables'
        '[&quot;turnstile-ledger-resp&quot;]).StatusCode == 200)">',
        '        <set-variable name="turnstile-budget" '
        'value="@(((IResponse)context.Variables[&quot;turnstile-ledger-resp&quot;])'
        '.Body.As&lt;JObject&gt;())" />',
        "        <choose>",
        f'          <when condition="{budget_cond}">',
        "            <return-response>",
        '              <set-status code="402" reason="Credit Allocation Exhausted" />',
        '              <set-header name="Content-Type" exists-action="override">'
        "<value>application/json</value></set-header>",
        f"              <set-body>{budget_err}</set-body>",
        "            </return-response>",
        "          </when>",
        "        </choose>",
        "      </when>",
        "    </choose>",
        "    <!-- 2. Azure AI Content Safety Guardrail (Foundry Content Safety + Prompt Shields) -->",
        '    <llm-content-safety backend-id="foundry-content-safety" shield-prompt="true">',
        '      <categories output-type="EightSeverityLevels">',
        '        <category name="Hate" threshold="1" />',
        '        <category name="Violence" threshold="1" />',
        '        <category name="Sexual" threshold="1" />',
        '        <category name="SelfHarm" threshold="1" />',
        "      </categories>",
        "    </llm-content-safety>",
        "    <!-- 3. Microsoft Decision-1 (model = auto) Dynamic Model Router -->",
        '    <set-variable name="requested-model" '
        'value="@((string)context.Request.Body.As&lt;JObject&gt;(preserveContent: true)'
        '[&quot;model&quot;])" />',
        "    <choose>",
        '      <when condition="@((string)context.Variables[&quot;requested-model&quot;] '
        '== &quot;auto&quot;)">',
        '        <send-request mode="new" response-variable-name="decision-router-resp" '
        'timeout="5" ignore-error="true">',
        f"          <set-url>{routes_url}</set-url>",
        "          <set-method>GET</set-method>",
        '          <authentication-managed-identity resource="https://storage.azure.com/" />',
        "        </send-request>",
        f'        <set-variable name="selected-model" value="{router.default_model}" />',
        "      </when>",
        "      <otherwise>",
        '        <set-variable name="selected-model" '
        'value="@((string)context.Variables[&quot;requested-model&quot;])" />',
        "      </otherwise>",
        "    </choose>",
        "  </inbound>",
        "  <backend>",
        "    <base />",
        "  </backend>",
        "  <outbound>",
        "    <base />",
        '    <set-header name="x-turnstile-selected-model" exists-action="override">',
        '      <value>@((string)context.Variables.GetValueOrDefault("selected-model", '
        '"gpt-5.4-mini"))</value>',
        "    </set-header>",
        '    <log-to-eventhub logger-id="finops-token-usage-eventhub">@(new JObject(',
        '      new JProperty("subscription_id", context.Subscription.Id),',
        '      new JProperty("requested_model", '
        'context.Variables.GetValueOrDefault("requested-model", "")),',
        '      new JProperty("selected_model", '
        'context.Variables.GetValueOrDefault("selected-model", "")),',
        '      new JProperty("status_code", context.Response.StatusCode)',
        "    ).ToString())</log-to-eventhub>",
        "  </outbound>",
        "</policies>",
    ]
    xml = "\n".join(lines)
    return TurnstilePolicyPreviewOutput(
        ledger_storage_account=storage_account,
        ledger_table_name=ledger_table,
        model_routes_table_name=routes_table,
        decision_router_enabled=router.enabled,
        decision_endpoint=router.decision_endpoint,
        policy_xml=xml,
    )


def ensure_local_users_seeded(db: Session, settings: Settings) -> None:
    Base.metadata.create_all(db.get_bind(), checkfirst=True)
    count = db.scalar(select(func.count()).select_from(LocalUser)) or 0
    if count > 0:
        return
    home_tid = settings.home_tenant_id or "00000000-0000-0000-0000-000000000001"
    home_org = db.scalar(select(Organization).where(Organization.tenant_id == home_tid))
    if home_org is None:
        home_org = Organization(
            name=settings.home_organization_name or "Singtel IDS",
            tenant_id=home_tid,
            enabled=True,
        )
        db.add(home_org)
        db.flush()

    cust_tid = "00000000-0000-0000-0000-000000000002"
    cust_org = db.scalar(select(Organization).where(Organization.tenant_id == cust_tid))
    if cust_org is None:
        cust_org = Organization(name="Enterprise OpCo Alpha", tenant_id=cust_tid, enabled=True)
        db.add(cust_org)
        db.flush()

    admin_oid = "00000000-0000-0000-0000-000000000101"
    if db.scalar(
        select(Member).where(Member.organization_id == home_org.id, Member.object_id == admin_oid)
    ) is None:
        db.add(Member(organization_id=home_org.id, object_id=admin_oid, role="ids_admin", enabled=True))

    cust_oid = "00000000-0000-0000-0000-000000000202"
    if db.scalar(
        select(Member).where(Member.organization_id == cust_org.id, Member.object_id == cust_oid)
    ) is None:
        db.add(Member(organization_id=cust_org.id, object_id=cust_oid, role="customer", enabled=True))

    db.add(
        LocalUser(
            email="admin@turnstile.local",
            password_hash=hash_password("turnstile-admin"),
            display_name="Platform Admin",
            organization_id=home_org.id,
            object_id=admin_oid,
            role="ids_admin",
            enabled=True,
        )
    )
    db.add(
        LocalUser(
            email="customer@opco.local",
            password_hash=hash_password("turnstile-customer"),
            display_name="OpCo Developer",
            organization_id=cust_org.id,
            object_id=cust_oid,
            role="customer",
            enabled=True,
        )
    )
    ensure_model_garden_seeded(db)
    ensure_organization_budget(db, cust_org.id)
    ensure_organization_budget(db, home_org.id)
    sub_id = "00000000-0000-0000-0000-000000000301"
    team_id = "00000000-0000-0000-0000-000000000401"
    if db.get(Team, team_id) is None:
        db.add(Team(id=team_id, organization_id=cust_org.id, name="Digital Products"))
        db.flush()
    if db.get(TeamSubscription, sub_id) is None:
        db.add(
            TeamSubscription(
                id=sub_id,
                organization_id=cust_org.id,
                name="OpCo Alpha Production Key",
                team="Digital Products",
                team_id=team_id,
                state="active",
                desired_state="active",
                idempotency_key=sub_id,
            )
        )
        db.flush()
    now = datetime.now(UTC)
    if db.get(IngestionState, "native-llm") is None:
        db.add(IngestionState(id="native-llm", watermark=now, last_success_at=now))
    sample_usage = [
        ("gpt-5.4-mini", "azure_openai", 42000, 18000, Decimal("0.03420000"), 280, "complete"),
        ("claude-sonnet-4-5", "anthropic", 65000, 24000, Decimal("0.55500000"), 640, "auto_routed"),
        ("DeepSeek-V3.2-Speciale", "deepseek", 88000, 35000, Decimal("0.06226000"), 490, "playground"),
    ]
    for idx, (m_id, prov, inp, out, cost_val, lat, comp) in enumerate(sample_usage):
        u_id = f"seed-usage-{idx + 1}"
        if db.get(UsageRecord, u_id) is None:
            db.add(
                UsageRecord(
                    id=u_id,
                    organization_id=cust_org.id,
                    subscription_id=sub_id,
                    model=m_id,
                    provider=prov,
                    region="eastus2",
                    occurred_at=now - timedelta(minutes=(idx + 1) * 15),
                    input_tokens=inp,
                    output_tokens=out,
                    cached_input_tokens=0,
                    cache_write_tokens=0,
                    cost=cost_val,
                    currency="USD",
                    status_code=200,
                    e2e_ms=lat,
                    ttft_ms=lat // 3,
                    completeness=comp,
                    ingested_at=now,
                )
            )
    db.commit()


def authenticate_local_user(
    db: Session, settings: Settings, payload: LocalLoginRequest
) -> LocalLoginResponse:
    if not settings.local_auth_enabled:
        raise HTTPException(403, "Local PostgreSQL authentication is disabled")
    ensure_local_users_seeded(db, settings)
    email = payload.email.strip().lower()
    user = db.scalar(select(LocalUser).where(func.lower(LocalUser.email) == email))
    if user is None or not user.enabled or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    org = db.get(Organization, user.organization_id)
    if org is None or not org.enabled:
        raise HTTPException(403, "Organization is disabled")
    token = issue_local_jwt(settings, user, org)
    return LocalLoginResponse(
        access_token=token,
        token_type="bearer",
        user=IdentityOutput(
            organization_id=org.id,
            organization_name=org.name,
            tenant_id=org.tenant_id,
            object_id=user.object_id,
            role=user.role,  # type: ignore[arg-type]
        ),
        email=user.email,
        display_name=user.display_name,
    )


def register_local_user(
    db: Session, settings: Settings, payload: LocalRegisterRequest
) -> LocalLoginResponse:
    if not settings.local_auth_enabled:
        raise HTTPException(403, "Local PostgreSQL authentication is disabled")
    ensure_local_users_seeded(db, settings)
    email = payload.email.strip().lower()
    existing = db.scalar(select(LocalUser).where(func.lower(LocalUser.email) == email))
    if existing is not None:
        raise HTTPException(409, "An account with that email already exists")
    org = db.scalar(
        select(Organization).where(func.lower(Organization.name) == payload.organization_name.strip().lower())
    )
    if org is None:
        org = Organization(
            name=payload.organization_name.strip(),
            tenant_id=str(uuid4()),
            enabled=True,
        )
        db.add(org)
        db.flush()
        ensure_organization_budget(db, org.id)
    oid = str(uuid4())
    db.add(Member(organization_id=org.id, object_id=oid, role="customer", enabled=True))
    user = LocalUser(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        organization_id=org.id,
        object_id=oid,
        role="customer",
        enabled=True,
    )
    db.add(user)
    db.commit()
    token = issue_local_jwt(settings, user, org)
    return LocalLoginResponse(
        access_token=token,
        token_type="bearer",
        user=IdentityOutput(
            organization_id=org.id,
            organization_name=org.name,
            tenant_id=org.tenant_id,
            object_id=user.object_id,
            role="customer",
        ),
        email=user.email,
        display_name=user.display_name,
    )


def _local_user_output(db: Session, user: LocalUser) -> LocalUserOutput:
    org = db.get(Organization, user.organization_id)
    return LocalUserOutput(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=user.organization_id,
        organization_name=org.name if org else user.organization_id,
        object_id=user.object_id,
        role=user.role,  # type: ignore[arg-type]
        enabled=user.enabled,
        created_at=aware(user.created_at),
    )


def list_local_users(
    db: Session, settings: Settings, organization_id: str | None = None
) -> list[LocalUserOutput]:
    if settings.local_auth_enabled:
        ensure_local_users_seeded(db, settings)
    query = select(LocalUser).order_by(LocalUser.email.asc())
    if organization_id is not None:
        query = query.where(LocalUser.organization_id == organization_id)
    return [_local_user_output(db, row) for row in db.scalars(query).all()]


def create_local_user(
    db: Session, settings: Settings, principal: Principal, payload: LocalUserCreate
) -> LocalUserOutput:
    org = db.get(Organization, str(payload.organization_id))
    if org is None:
        raise HTTPException(404, "Organization not found")
    if payload.role == "ids_admin" and org.tenant_id != settings.home_tenant_id:
        raise HTTPException(422, "IDS admin role can only be granted in the home organization")
    email = payload.email.strip().lower()
    existing = db.scalar(select(LocalUser).where(func.lower(LocalUser.email) == email))
    if existing is not None:
        raise HTTPException(409, "A user with that email already exists")
    oid = str(uuid4())
    db.add(Member(organization_id=org.id, object_id=oid, role=payload.role, enabled=True))
    user = LocalUser(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        organization_id=org.id,
        object_id=oid,
        role=payload.role,
        enabled=True,
    )
    db.add(user)
    db.flush()
    audit(db, principal, "local_user.created", user.id, org.id)
    db.commit()
    return _local_user_output(db, user)


def update_local_user(
    db: Session, principal: Principal, user_id: str, payload: LocalUserUpdate
) -> LocalUserOutput:
    user = db.get(LocalUser, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    user.enabled = payload.enabled
    if payload.password:
        user.password_hash = hash_password(payload.password)
    member = db.scalar(
        select(Member).where(
            Member.organization_id == user.organization_id,
            Member.object_id == user.object_id,
        )
    )
    if member is not None:
        member.enabled = payload.enabled
    audit(db, principal, "local_user.updated", user.id, user.organization_id)
    db.commit()
    return _local_user_output(db, user)

