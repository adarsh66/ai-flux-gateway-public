from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SubscriptionCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    team: str = Field(min_length=1, max_length=100)


class AdminSubscriptionCreate(SubscriptionCreate):
    organization_id: UUID


class KeyRequest(Input):
    key: Literal["primary", "secondary"] = "primary"


class StateRequest(Input):
    state: Literal["active", "suspended"]


class OrganizationCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    tenant_id: UUID


class EnabledRequest(Input):
    enabled: bool


class MemberCreate(Input):
    organization_id: UUID
    object_id: UUID
    role: Literal["customer", "ids_admin"] = "customer"


class PriceCreate(Input):
    model: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=60)
    region: str = Field(min_length=1, max_length=60)
    effective_from: datetime
    effective_to: datetime | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    input_per_million: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    output_per_million: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    cached_input_per_million: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=8)
    cache_write_per_million: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=8)
    input_includes_cached: bool = True

    @field_validator("effective_from", "effective_to")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Price effective dates require an explicit timezone")
        return value

    @model_validator(mode="after")
    def valid_period(self) -> "PriceCreate":
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be later than effective_from")
        return self


class PriceEnd(Input):
    effective_to: datetime

    @field_validator("effective_to")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Price effective dates require an explicit timezone")
        return value


GatewayScope = Literal["dev-openai", "dev-unified"]
QuotaPeriod = Literal["Hourly", "Daily", "Weekly", "Monthly", "Yearly"]


class GatewayConfiguration(Input):
    safety_threshold: int = Field(strict=True, ge=0, le=7)
    rpm: int = Field(strict=True, ge=1, le=2)
    tpm: int = Field(strict=True, ge=1, le=20000)
    token_quota: int = Field(strict=True, ge=1, le=2147483647)
    quota_period: QuotaPeriod


class GatewayLimits(Input):
    rpm: int = Field(strict=True, ge=1, le=100000)
    tpm: int = Field(strict=True, ge=1, le=20000)
    token_quota: int = Field(strict=True, ge=1, le=2147483647)
    quota_period: QuotaPeriod
    concurrency: Literal[1, 2, 4, 8, 16]
    request_quota: int | None = Field(default=None, strict=True, ge=1, le=2147483647)
    request_quota_period: Literal["Daily", "Monthly"] = "Daily"

    @field_validator("concurrency", mode="before")
    @classmethod
    def integer_concurrency(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Concurrency requires an approved integer tier")
        return value


class SafetyConfiguration(Input):
    profile: Literal["Standard", "Strict", "Custom"]
    hate: int = Field(strict=True, ge=0, le=7)
    violence: int = Field(strict=True, ge=0, le=7)
    sexual: int = Field(strict=True, ge=0, le=7)
    self_harm: int = Field(strict=True, ge=0, le=7)
    prompt_attack: bool = Field(strict=True)
    protected_material: bool = Field(strict=True)
    input_filtering: bool = Field(strict=True)
    output_filtering: bool = Field(strict=True)

    @model_validator(mode="after")
    def consistent_profile(self) -> "SafetyConfiguration":
        if self.protected_material and not self.output_filtering:
            raise ValueError("Protected-material detection requires output scanning")
        if self.prompt_attack and not self.input_filtering:
            raise ValueError("Prompt protection requires input scanning")
        if self.profile != "Custom":
            threshold = 4 if self.profile == "Standard" else 1
            if (
                any(value != threshold for value in (self.hate, self.violence, self.sexual, self.self_harm))
                or not all((
                    self.prompt_attack, self.protected_material, self.input_filtering, self.output_filtering,
                ))
            ):
                raise ValueError("Preset values must match the selected safety profile")
        return self


class TeamGatewayLimits(Input):
    organization_id: UUID
    team_id: UUID
    limits: GatewayLimits


class SubscriptionGatewayLimits(Input):
    organization_id: UUID
    subscription_id: UUID
    limits: GatewayLimits


class ManagedGatewayConfiguration(Input):
    schema_version: Literal[2]
    defaults: GatewayLimits
    teams: list[TeamGatewayLimits] = Field(default_factory=list, max_length=100)
    subscriptions: list[SubscriptionGatewayLimits] = Field(default_factory=list, max_length=200)
    safety: SafetyConfiguration

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema version must be the integer 2")
        return value


class SafetySettingsUpdate(Input):
    expected_version: int = Field(strict=True, ge=1)
    configuration: SafetyConfiguration
    reason: str = Field(min_length=1, max_length=500)
    acknowledge_relaxation: bool = Field(default=False, strict=True)


class GatewaySettingsUpdate(Input):
    expected_version: int = Field(strict=True, ge=0)
    configuration: GatewayConfiguration | ManagedGatewayConfiguration
    reason: str = Field(min_length=1, max_length=500)


class GatewaySettingsRetry(Input):
    expected_version: int = Field(strict=True, ge=1)


class GatewayRevisionOutput(BaseModel):
    version: int
    configuration: GatewayConfiguration | ManagedGatewayConfiguration
    reason: str
    object_id: str
    occurred_at: datetime
    state: Literal["pending", "published", "failed"]
    error: str | None


class GatewayCapabilities(BaseModel):
    managed_controls_enabled: bool = False
    concurrency_tiers: list[int] = [1, 2, 4, 8, 16]
    protected_material_available: bool = False
    safety_relaxation_allowed: bool = False
    monthly_request_quota_available: bool = False
    enforcement_enabled: bool = False
    initial_safety_threshold: int = 1


class GatewaySettingsOutput(BaseModel):
    scope: GatewayScope
    max_rpm: int = 2
    max_tpm: int
    version: int
    published_version: int | None
    desired: GatewayRevisionOutput | None
    capabilities: GatewayCapabilities = Field(default_factory=GatewayCapabilities)


class GatewayTarget(BaseModel):
    organization_id: str
    organization_name: str
    team_id: str
    team: str
    subscription_id: str
    name: str
    state: str


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int


class IdentityOutput(BaseModel):
    organization_id: str
    organization_name: str
    tenant_id: str
    object_id: str
    role: Literal["customer", "ids_admin"]


class CatalogOutput(BaseModel):
    id: str
    provider: str
    capabilities: list[str]
    enabled: bool
    placeholder: bool = False
    max_completion_tokens: int | None = None


class SubscriptionOutput(BaseModel):
    id: str
    name: str
    team: str
    state: Literal["pending", "active", "suspended", "failed"]
    created_at: datetime


class AdminSubscriptionOutput(SubscriptionOutput):
    organization_id: str
    organization_name: str
    team_id: str | None
    gateway_access: Literal["ready", "pending", "not_managed"]
    gateway_message: str | None = None


class OrganizationOutput(BaseModel):
    id: str
    name: str
    tenant_id: str
    enabled: bool


class MemberOutput(BaseModel):
    id: str
    organization_id: str
    object_id: str
    role: Literal["customer", "ids_admin"]
    enabled: bool


class PriceOutput(PriceCreate):
    id: str


class UsageOutput(BaseModel):
    id: str
    subscription_id: str
    model: str
    provider: str
    region: str
    occurred_at: datetime
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    cache_write_tokens: int | None
    cost: str | None
    currency: str | None
    status_code: int
    e2e_ms: int | None
    ttft_ms: int | None
    completeness: str


class UsageSummary(BaseModel):
    requests: int
    input_tokens: int
    output_tokens: int
    known_cost: str | None
    currency: str | None
    incomplete_requests: int
    failed_requests: int
    throttled_requests: int
    e2e_p95_ms: int | None
    ttft_supported: bool
    cache_tokens_supported: bool
    last_ingested_at: datetime | None


class UsagePage(Page[UsageOutput]):
    summary: UsageSummary


class UsageMinute(BaseModel):
    minute: datetime
    requests: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    avg_e2e_seconds: float | None
    missing_token_requests: int
    latency_samples: int


class UsageSeries(BaseModel):
    items: list[UsageMinute]
    start: datetime
    end: datetime
    interval_seconds: int = 60


class ModelTokenBucket(BaseModel):
    start: datetime
    end: datetime
    model: str
    requests: int
    total_tokens: int | None
    missing_token_requests: int


class ModelTokenSeries(BaseModel):
    items: list[ModelTokenBucket]
    start: datetime
    end: datetime
    interval_seconds: int


class SafetyOutput(BaseModel):
    id: str
    organization_id: str
    subscription_id: str
    occurred_at: datetime
    category: str
    action: str
    correlation_id: str


class ModelGardenItemOutput(BaseModel):
    id: str
    display_name: str
    provider: str
    vendor: str
    region: str
    backend_model: str
    endpoint_url: str
    context_window: int
    max_completion_tokens: int
    input_per_million: str
    output_per_million: str
    cached_input_per_million: str | None = None
    currency: str = "USD"
    capabilities: list[str]
    description: str
    enabled: bool
    coming_soon: bool = False
    content_safety_enabled: bool = True
    priority: int = 100


class ModelGardenUpsert(Input):
    id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=60)
    vendor: str = Field(min_length=1, max_length=60)
    region: str = Field(default="eastus2", min_length=1, max_length=60)
    backend_model: str = Field(min_length=1, max_length=100)
    endpoint_url: str = Field(default="", max_length=500)
    context_window: int = Field(default=128000, ge=1024, le=10000000)
    max_completion_tokens: int = Field(default=16384, ge=1, le=200000)
    input_per_million: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=8)
    output_per_million: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=8)
    cached_input_per_million: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=8)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    capabilities: list[str] = Field(default_factory=lambda: ["chat", "streaming"])
    description: str = Field(default="", max_length=500)
    enabled: bool = True
    coming_soon: bool = False
    content_safety_enabled: bool = True
    priority: int = Field(default=100, ge=1, le=1000)


class CreditBudgetUpdate(Input):
    subscription_id: UUID | None = None
    monthly_budget_usd: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    credit_allocation: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    alert_threshold_pct: int = Field(default=80, ge=1, le=100)
    rpm_limit: int = Field(default=60, ge=1, le=100000)
    tpm_limit: int = Field(default=120000, ge=100, le=100000000)
    allowed_models: list[str] = Field(default_factory=lambda: ["*"])
    product_name: str = Field(default="Enterprise AI Gateway", min_length=1, max_length=100)
    channel: str = Field(default="api-gateway", min_length=1, max_length=60)
    hard_stop_enabled: bool = True


class CreditBudgetOutput(BaseModel):
    id: str
    organization_id: str
    organization_name: str
    subscription_id: str | None
    subscription_name: str | None = None
    monthly_budget_usd: str
    credit_allocation: str
    used_credits: str
    remaining_credits: str
    utilization_pct: float
    low_credit_alert: bool
    alert_threshold_pct: int
    rpm_limit: int = 60
    tpm_limit: int = 120000
    allowed_models: list[str]
    product_name: str
    channel: str
    hard_stop_enabled: bool
    ledger_row_key: str
    updated_at: datetime


class ModelUsageBreakdownItem(BaseModel):
    model: str
    provider: str
    vendor: str
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: str
    share_pct: float


class ProductUsageBreakdownItem(BaseModel):
    subscription_id: str
    subscription_name: str
    team: str
    product_name: str
    requests: int
    total_tokens: int
    cost_usd: str
    share_pct: float


class ChannelUsageBreakdownItem(BaseModel):
    channel: str
    requests: int
    total_tokens: int
    cost_usd: str
    share_pct: float


class CreditSummaryOutput(BaseModel):
    organization_id: str
    organization_name: str
    currency: str = "USD"
    total_credits: str
    used_credits: str
    remaining_credits: str
    utilization_pct: float
    alert_threshold_pct: int
    rpm_limit: int = 60
    tpm_limit: int = 120000
    allowed_models: list[str] = Field(default_factory=lambda: ["*"])
    low_credit_alert: bool
    hard_stop_enabled: bool
    total_requests: int
    total_tokens: int
    by_model: list[ModelUsageBreakdownItem]
    by_product: list[ProductUsageBreakdownItem]
    by_channel: list[ChannelUsageBreakdownItem]


class RouterRuleItem(Input):
    category: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=240)
    keywords: list[str] = Field(default_factory=list)
    preferred_model: str = Field(min_length=1, max_length=100)
    fallback_model: str = Field(min_length=1, max_length=100)


class ModelRouterConfigOutput(BaseModel):
    enabled: bool
    strategy: Literal["microsoft-decision-1", "cost-optimized", "latency-optimized", "quality-first"]
    decision_endpoint: str
    default_model: str
    candidate_models: list[str]
    rules: list[RouterRuleItem]
    updated_at: datetime


class ModelRouterConfigUpdate(Input):
    enabled: bool = True
    strategy: Literal[
        "microsoft-decision-1", "cost-optimized", "latency-optimized", "quality-first"
    ] = "microsoft-decision-1"
    decision_endpoint: str = Field(
        default="/providers/microsoft/v1/systemone", min_length=1, max_length=500,
    )
    default_model: str = Field(default="gpt-5.4-mini", min_length=1, max_length=100)
    candidate_models: list[str] = Field(min_length=1, max_length=20)
    rules: list[RouterRuleItem] = Field(default_factory=list, max_length=20)


class RouterDecisionRequest(Input):
    prompt: str = Field(min_length=1, max_length=8000)
    strategy: Literal[
        "microsoft-decision-1", "cost-optimized", "latency-optimized", "quality-first"
    ] | None = None


class RouterDecisionOutput(BaseModel):
    requested_model: str = "auto"
    selected_model: str
    display_name: str
    provider: str
    vendor: str
    category: str
    strategy: str
    decision_endpoint: str
    confidence: float
    reason: str
    estimated_input_per_million: str
    estimated_output_per_million: str


class PlaygroundMessage(Input):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class PlaygroundChatRequest(Input):
    model: str = Field(default="auto", min_length=1, max_length=100)
    messages: list[PlaygroundMessage] = Field(min_length=1, max_length=25)
    max_completion_tokens: int = Field(default=512, ge=1, le=16384)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    subscription_id: UUID | None = None


class PlaygroundChatResponse(BaseModel):
    id: str
    requested_model: str
    selected_model: str
    provider: str
    vendor: str
    reply: str
    routing_decision: RouterDecisionOutput | None = None
    safety_status: Literal["passed", "blocked"]
    safety_categories: dict[str, int]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: str
    latency_ms: int


class TurnstilePolicyPreviewOutput(BaseModel):
    ledger_storage_account: str
    ledger_table_name: str
    model_routes_table_name: str
    decision_router_enabled: bool
    decision_endpoint: str
    policy_xml: str


class LocalLoginRequest(Input):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=4, max_length=128)


class LocalRegisterRequest(Input):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    organization_name: str = Field(default="Enterprise OpCo Alpha", min_length=2, max_length=100)


class LocalLoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: IdentityOutput
    email: str
    display_name: str


class LocalUserCreate(Input):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    organization_id: UUID
    role: Literal["customer", "ids_admin"] = "customer"


class LocalUserUpdate(Input):
    enabled: bool = True
    password: str | None = Field(default=None, min_length=6, max_length=128)


class LocalUserOutput(BaseModel):
    id: str
    email: str
    display_name: str
    organization_id: str
    organization_name: str
    object_id: str
    role: Literal["customer", "ids_admin"]
    enabled: bool
    created_at: datetime


