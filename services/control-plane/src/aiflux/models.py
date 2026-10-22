from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    tenant_id: Mapped[str] = mapped_column(String(36), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("organization_id", "object_id"),
        CheckConstraint("role IN ('customer', 'ids_admin')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    object_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class TeamSubscription(Base):
    __tablename__ = "team_subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key"),
        CheckConstraint("state IN ('pending', 'active', 'suspended', 'failed')"),
        CheckConstraint("desired_state IN ('active', 'suspended')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    team: Mapped[str] = mapped_column(String(100))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    desired_state: Mapped[str] = mapped_column(String(20), default="active")
    idempotency_key: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    object_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelPrice(Base):
    __tablename__ = "model_prices"
    __table_args__ = (
        Index("ix_price_lookup", "model", "provider", "region", "effective_from"),
        CheckConstraint("input_per_million >= 0 AND output_per_million >= 0"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(60))
    region: Mapped[str] = mapped_column(String(60))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    cached_input_per_million: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    cache_write_per_million: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    input_includes_cached: Mapped[bool] = mapped_column(Boolean, default=True)


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_org_time", "organization_id", "occurred_at"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    subscription_id: Mapped[str] = mapped_column(ForeignKey("team_subscriptions.id"), index=True)
    model: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(60))
    region: Mapped[str] = mapped_column(String(60))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer)
    e2e_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completeness: Mapped[str] = mapped_column(String(100))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SafetyEvent(Base):
    __tablename__ = "safety_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    subscription_id: Mapped[str] = mapped_column(ForeignKey("team_subscriptions.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    category: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60))
    correlation_id: Mapped[str] = mapped_column(String(100))


class IngestionState(Base):
    __tablename__ = "ingestion_state"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    watermark: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GatewaySettings(Base):
    __tablename__ = "gateway_settings"
    scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    published_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class GatewaySettingsRevision(Base):
    __tablename__ = "gateway_settings_revisions"
    __table_args__ = (
        UniqueConstraint("scope", "version"),
        CheckConstraint("state IN ('pending', 'published', 'failed')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(ForeignKey("gateway_settings.scope"))
    version: Mapped[int] = mapped_column(Integer)
    configuration: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(500))
    object_id: Mapped[str] = mapped_column(String(36))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    state: Mapped[Literal["pending", "published", "failed"]] = mapped_column(String(16), default="pending")
    base_hash: Mapped[str] = mapped_column(String(64))
    base_etag: Mapped[str] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)


class CreditBudget(Base):
    __tablename__ = "credit_budgets"
    __table_args__ = (UniqueConstraint("organization_id", "subscription_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    subscription_id: Mapped[str | None] = mapped_column(
        ForeignKey("team_subscriptions.id"), nullable=True, index=True,
    )
    monthly_budget_usd: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("5000.0000"))
    credit_allocation: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("5000.0000"))
    alert_threshold_pct: Mapped[int] = mapped_column(Integer, default=80)
    allowed_models_json: Mapped[str] = mapped_column(Text, default='["*"]')
    product_name: Mapped[str] = mapped_column(String(100), default="Enterprise AI Gateway")
    channel: Mapped[str] = mapped_column(String(60), default="api-gateway")
    hard_stop_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ManagedModelEndpoint(Base):
    __tablename__ = "managed_model_endpoints"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(60))
    vendor: Mapped[str] = mapped_column(String(60))
    region: Mapped[str] = mapped_column(String(60), default="eastus2")
    backend_model: Mapped[str] = mapped_column(String(100))
    endpoint_url: Mapped[str] = mapped_column(String(500), default="")
    context_window: Mapped[int] = mapped_column(Integer, default=128000)
    max_completion_tokens: Mapped[int] = mapped_column(Integer, default=16384)
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    cached_input_per_million: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    capabilities_json: Mapped[str] = mapped_column(Text, default='["chat", "streaming"]')
    description: Mapped[str] = mapped_column(String(500), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    coming_soon: Mapped[bool] = mapped_column(Boolean, default=False)
    content_safety_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelRouterConfig(Base):
    __tablename__ = "model_router_configs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    strategy: Mapped[str] = mapped_column(String(40), default="microsoft-decision-1")
    decision_endpoint: Mapped[str] = mapped_column(
        String(500), default="/providers/microsoft/v1/systemone",
    )
    default_model: Mapped[str] = mapped_column(String(100), default="gpt-5.4-mini")
    candidate_models_json: Mapped[str] = mapped_column(
        Text, default='["gpt-5.4-mini", "gpt-5.4", "claude-sonnet-4-5", "DeepSeek-V3.2-Speciale"]',
    )
    rules_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

