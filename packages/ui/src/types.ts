export type Role = "customer" | "ids_admin";
export type SubscriptionState = "pending" | "active" | "suspended" | "failed";
export type KeyName = "primary" | "secondary";

export type DeletionCollection = "organizations" | "subscriptions" | "local-users" | "members";
export interface DeletionPreview {
  entity_type: "organization" | "subscription" | "local_user" | "member";
  entity_id: string;
  label: string;
  can_delete: boolean;
  blockers: string[];
  dependencies: { subscriptions: number; users: number; members: number };
  effect: string;
}
export interface DeletionRequest { confirmation: string; reason: string }
export interface DeletionResult {
  entity_id: string;
  status: "archived" | "pending" | "failed";
  message: string;
}

export interface OrganizationModelAccess {
  organization_id: string;
  organization_enabled: boolean;
  version: number;
  denied_models: string[];
  auto_enabled: boolean;
  applied_version: number | null;
  applied_sha256: string | null;
  state: "pending" | "applied" | "error";
  error: string | null;
  attempts?: number;
  applied_at?: string | null;
  next_attempt_at?: string | null;
  items: { id: string; display_name: string; provider: string; globally_enabled: boolean; model_kind: "chat" | "informational"; internal_price_available?: boolean; external_price_available?: boolean }[];
}

export interface Me {
  organization_id: string;
  organization_name: string;
  tenant_id: string;
  object_id: string;
  role: Role;
}

export interface Paged<T> {
  items: T[];
  total: number;
}

/** Advisory only. USD values are server-calculated decimal strings, never credit balances. */
export interface MonthlyBudgetSummary {
  organization_id: string;
  organization_name: string;
  allocated_usd: string | null;
  estimated_used_usd: string | null;
  estimated_remaining_usd: string | null;
  estimated_overrun_usd: string | null;
  estimated_utilization_pct: number | null;
  advisory_threshold_pct: number;
  status: "unconfigured" | "below_threshold" | "threshold_reached" | "over_budget" | "unknown";
  period_start: string;
  period_end: string;
  as_of: string;
  latest_usage_at: string | null;
  estimated_requests: number;
  unestimated_requests: number;
  pricing_revision: string;
  version: number;
  estimate_complete: boolean;
  basis: "external_customer_prices";
  hard_stop_enabled: false;
}

/** Admin-only projection; never added to customer payloads. */
export interface AdminMonthlyBudgetDashboard {
  budget: MonthlyBudgetSummary;
  internal: OrganizationCostEstimate;
  internal_basis: "internal_price_estimate";
  internal_scope: "completion_usage";
  archived_at: string | null;
  read_only: boolean;
  as_of: string;
}

export interface MonthlyBudgetUpdate {
  allocated_usd: string;
  advisory_threshold_pct: number;
  expected_version: number;
  reason: string;
}

export interface MonthlyBudgetRevision {
  version: number;
  allocated_usd: string;
  advisory_threshold_pct: number;
  reason: string;
  changed_by: string;
  changed_at: string;
}

export interface CatalogModel {
  id: string;
  provider: string;
  capabilities: string[];
  enabled: boolean;
  placeholder?: boolean;
  max_completion_tokens?: number | null;
}

export interface Subscription {
  id: string;
  name: string;
  team: string;
  state: SubscriptionState;
  created_at: string;
  deleted_at?: string | null;
  deletion_status?: "pending" | "failed" | null;
}

export interface AdminSubscription extends Subscription {
  organization_id: string;
  organization_name: string;
  team_id: string | null;
  gateway_access: "ready" | "pending" | "not_managed";
  gateway_message: string | null;
}

export interface DisplayEstimate {
  estimated_cost_usd?: string | null;
  estimated_requests?: number;
  unestimated_requests?: number;
  approximate_requests?: number;
  pricing_revision?: string | null;
}

export interface DisplayPrice {
  input: string;
  output?: string | null;
  cached?: string | null;
  write?: string | null;
  model_kind?: "chat" | "scoring";
  billing_dimensions?: string[];
  provenance?: Record<string, unknown>;
  currency: string;
  status: string;
  source_url: string;
  checked_at: string;
  revision: string;
  model_version: string;
  sku: string;
  source_model: string;
  assumption?: string;
  assumptions: string;
  basis: string;
}

export type RateOrigin = "configured" | "platform_default" | "public_list" | "sourced_proxy" | "tbc" | "unknown";

export interface RateRow {
  model: string;
  /** Omitted by legacy responses: chat, with input and output billing. */
  model_kind?: "chat" | "scoring";
  billing_dimensions?: string[];
  provider: string;
  region: string;
  model_version: string;
  sku: string;
  origin: RateOrigin;
  note: string | null;
  source_url: string | null;
  input: string | null;
  output: string | null;
  cached: string | null;
  write: string | null;
  default_input: string | null;
  default_output: string | null;
  default_cached: string | null;
  default_write: string | null;
  configured_from: string | null;
}

/** Optional RateCardOutput metadata from auto_pricing.status / after_save.
 * The fallback after_save response deliberately omits revisions and timestamps.
 * Informational only: never an admission or Save permission signal.
 */
export interface RateCardAutoPricingStatus {
  enabled: boolean;
  desired_revision?: string | null;
  applied_revision?: string | null;
  applied_sha256?: string | null;
  source: "rate-card" | "packaged-default" | "last-good-or-packaged-default";
  state: "default" | "pending" | "applied";
  stale?: boolean;
  error?: string | null;
  applied_at?: string | null;
  next_attempt_at?: string | null;
  access_gated: false;
}

export interface RateCard {
  version: number;
  revision: string;
  currency: string;
  unit: string;
  items: RateRow[];
  total: number;
  changed: boolean;
  auto_pricing?: RateCardAutoPricingStatus | null;
}

export interface RateInput {
  model: string;
  input: string;
  output?: string | null;
  cached?: string | null;
  write?: string | null;
}

export interface PricingHistoryPoint {
  id: string;
  source: string;
  effective_at: string;
  reason: string | null;
  internal_version: number | null;
  default_version: number | null;
  organization_version: number | null;
  simultaneous: boolean;
}
export interface PricingHistoryPage {
  items: PricingHistoryPoint[];
  total: number;
  next_offset: number | null;
}
export interface HistoricalRateRow {
  model: string;
  canonical_model: string;
  provider: string;
  region: string;
  model_version: string | null;
  sku: string | null;
  model_kind: "chat" | "scoring";
  billing_dimensions: string[];
  state: "known" | "unknown" | "unavailable";
  input: string | null;
  output: string | null;
  cached: string | null;
  write: string | null;
  note: string | null;
}
export interface PricingHistoryDetail {
  source: PricingHistoryPoint;
  items: HistoricalRateRow[];
  skipped: string[];
  current_version: number;
  requires_acknowledgement: boolean;
}

/** External cards never participate in internal Auto pricing synchronization. */
export type ExternalRateCard = Omit<RateCard, "auto_pricing">;
export type ExternalRateInput = { model: string } & (
  | { operation: "set"; input: string; output?: string | null; cached?: string | null; write?: string | null }
  | { operation: "unknown" | "inherit" }
);
export interface ExternalCardUpdate {
  expected_version: number;
  reason: string;
  rates: ExternalRateInput[];
}

export interface UsageSummary extends DisplayEstimate {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens?: number | null;
  measured_requests?: number;
  missing_token_requests?: number;
  health?: ModelTokenSeries["health"];
  known_cost?: string | null;
  currency: string | null;
  incomplete_requests: number;
  failed_requests: number;
  throttled_requests: number;
  e2e_p95_ms: number | null;
  ttft_supported: boolean;
  cache_tokens_supported: boolean;
  last_ingested_at: string | null;
}

export interface UsageItem extends DisplayEstimate {
  estimate_basis?: string;
  id: string;
  subscription_id: string;
  model: string;
  provider: string;
  region: string;
  occurred_at: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
  cache_write_tokens: number | null;
  cost?: string | null;
  currency: string | null;
  status_code: number;
  e2e_ms: number | null;
  ttft_ms: number | null;
  completeness: string;
}

export interface UsagePage extends Paged<UsageItem> {
  summary: UsageSummary;
}

export interface UsageRankingTotals {
  requests: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  missing_token_requests: number;
  incomplete_requests: number;
}

export interface UsageRankingItem extends UsageRankingTotals {
  id: string;
  name: string;
  share: number | null;
}

export interface UsageRankings extends Paged<UsageRankingItem> {
  dimension: "organizations" | "subscriptions";
  organization_id: string | null;
  start: string;
  end: string;
  totals: UsageRankingTotals;
}

export type UsageRankingQuery = Pick<UsageFilters, "days" | "model" | "start" | "end" | "organization_id"> & {
  dimension: "organizations" | "subscriptions";
  offset: number;
  limit: number;
};

export type OrganizationCostsQuery = Pick<UsageFilters, "days" | "model" | "start" | "end"> & { offset: number; limit: number };
export interface OrganizationCostEstimate {
  estimated_cost_usd: string | null;
  estimated_requests: number;
  unestimated_requests: number;
  approximate_requests: number;
  pricing_revision: string;
}
export interface OrganizationCostItem {
  id: string; name: string; requests: number; total_tokens: number | null;
  internal: OrganizationCostEstimate; external: OrganizationCostEstimate;
}
export interface OrganizationCosts extends Paged<OrganizationCostItem> {
  start: string; end: string; currency: "USD"; order: "measured_tokens_desc_id_asc";
}

export interface UsageMinute {
  minute: string;
  end?: string;
  partial_bucket?: boolean;
  requests: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  avg_e2e_seconds: number | null;
  missing_token_requests: number;
  latency_samples: number;
}

export interface UsageSeries {
  items: UsageMinute[];
  start: string;
  end: string;
  interval_seconds: number;
  time_zone?: string;
  bucket_origin?: string;
}

export interface ModelTokenBucket {
  start: string;
  end: string;
  model: string;
  requests: number;
  total_tokens: number | null;
  missing_token_requests: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  measured_requests?: number;
  partial_bucket?: boolean;
}

export interface ModelTokenSeries {
  items: ModelTokenBucket[];
  start: string;
  end: string;
  interval_seconds: number;
  time_zone?: string;
  bucket_origin?: string;
  granularity?: "auto" | "hour" | "day";
  health?: {
    status: "healthy" | "stale" | "unverified" | "disabled" | "error";
    last_query_success_at: string | null;
    last_row_ingested_at: string | null;
    watermark: string | null;
    lag_seconds: number | null;
    expected_delay_seconds: number;
  } | null;
}

export interface UsageFilters {
  days: number;
  subscription_id?: string;
  organization_id?: string;
  model?: string;
  start?: string;
  end?: string;
}

export interface UsageQuery extends UsageFilters {
  offset: number;
  limit: number;
}

export interface UsageSeriesQuery extends UsageFilters {
  start?: string;
  end?: string;
  granularity?: "minute" | "hour" | "day";
  time_zone?: "UTC" | "Asia/Singapore";
}

export interface Organization {
  id: string;
  name: string;
  tenant_id: string;
  enabled: boolean;
}

export interface Member {
  id: string;
  organization_id: string;
  object_id: string;
  role: Role;
  enabled: boolean;
}

export interface SafetyEvent {
  id: string;
  organization_id: string;
  subscription_id: string;
  occurred_at: string;
  category: string;
  action: string;
  correlation_id: string;
}

export interface Price {
  id: string;
  model: string;
  provider: string;
  region: string;
  effective_from: string;
  effective_to: string | null;
  currency: string;
  input_per_million: string;
  output_per_million: string;
  cached_input_per_million: string | null;
  cache_write_per_million: string | null;
  input_includes_cached: boolean;
}

export type PriceInput = Omit<Price, "id">;
export type GatewayScope = "dev-openai" | "dev-unified";
export type QuotaPeriod = "Hourly" | "Daily" | "Weekly" | "Monthly" | "Yearly";
export interface GatewayConfiguration {
  safety_threshold: number;
  rpm: number;
  tpm: number;
  token_quota: number;
  quota_period: QuotaPeriod;
}
export type Concurrency = 1 | 2 | 4 | 8 | 16;
export type RequestQuotaPeriod = "Daily" | "Monthly";
export interface GatewayLimits {
  rpm: number;
  tpm: number;
  token_quota: number;
  quota_period: QuotaPeriod;
  concurrency: Concurrency;
  request_quota: number | null;
  request_quota_period: RequestQuotaPeriod;
}
export interface TeamGatewayLimits { organization_id: string; team_id: string; limits: GatewayLimits }
export interface SubscriptionGatewayLimits { organization_id: string; subscription_id: string; limits: GatewayLimits }
export type SafetyProfile = "Standard" | "Strict" | "Custom";
export interface SafetyConfiguration {
  profile: SafetyProfile;
  hate: number;
  violence: number;
  sexual: number;
  self_harm: number;
  prompt_attack: boolean;
  protected_material: boolean;
  input_filtering: boolean;
  output_filtering: boolean;
}
export interface ManagedGatewayConfiguration {
  schema_version: 2;
  defaults: GatewayLimits;
  teams: TeamGatewayLimits[];
  subscriptions: SubscriptionGatewayLimits[];
  safety: SafetyConfiguration;
}
export interface PocLimits { rpm: number; tpm: number; token_quota: number; request_quota: number }
export interface PocOverride { organization_id: string; subscription_id: string | null; limits: PocLimits | null; safety: SafetyConfiguration | null }
export interface PocGatewayConfiguration { schema_version: 3; defaults: PocLimits; safety: SafetyConfiguration; overrides: PocOverride[] }
export type GatewayConfigurationUnion = GatewayConfiguration | ManagedGatewayConfiguration | PocGatewayConfiguration;
export interface GatewayCapabilities {
  managed_controls_enabled: boolean;
  poc_controls_enabled?: boolean;
  concurrency_tiers: number[];
  protected_material_available: boolean;
  safety_relaxation_allowed: boolean;
  monthly_request_quota_available: boolean;
  enforcement_enabled: boolean;
  initial_safety_threshold?: number;
}
export interface GatewayTarget {
  organization_id: string;
  organization_name: string;
  team_id: string;
  team: string;
  subscription_id: string;
  name: string;
  state: SubscriptionState;
}export interface GatewayRevision {
  version: number;
  configuration: GatewayConfigurationUnion;
  reason: string;
  object_id: string;
  occurred_at: string;
  state: "pending" | "published" | "failed";
  error: string | null;
}
export interface GatewaySettings {
  scope: GatewayScope;
  max_rpm: number;
  max_tpm: number;
  version: number;
  published_version: number | null;
  desired: GatewayRevision | null;
  effective_defaults?: PocGatewayConfiguration | null;
  published?: GatewayRevision | null;
  capabilities?: GatewayCapabilities;
}

export interface ModelGardenItem {
  display_price?: DisplayPrice | null;
  /** Omitted by legacy responses: chat. Scoring availability is independent of chat eligibility. */
  model_kind?: "chat" | "scoring";
  scoring_available?: boolean | null;
  id: string;
  display_name: string;
  provider: string;
  vendor: string;
  region: string;
  backend_model: string;
  endpoint_url: string;
  context_window: number | null;
  max_completion_tokens: number;
  input_per_million: string | null;
  output_per_million: string | null;
  cached_input_per_million: string | null;
  currency: string;
  capabilities: string[];
  description: string;
  enabled: boolean;
  coming_soon: boolean;
  content_safety_enabled: boolean;
  priority: number;
}

export interface CreditBudget {
  id: string;
  organization_id: string;
  organization_name: string;
  subscription_id: string | null;
  subscription_name: string | null;
  monthly_budget_usd: string;
  credit_allocation: string;
  used_credits: string;
  remaining_credits: string | null;
  utilization_pct: number | null;
  unpriced_requests?: number;
  cost_complete?: boolean;
  low_credit_alert: boolean;
  alert_threshold_pct: number;
  allowed_models: string[];
  product_name: string;
  channel: string;
  hard_stop_enabled: boolean;
  ledger_row_key: string;
  updated_at: string;
}

export interface CreditBudgetUpdateInput {
  subscription_id?: string | null;
  monthly_budget_usd: string;
  credit_allocation: string;
  alert_threshold_pct: number;
  allowed_models: string[];
  product_name: string;
  channel: string;
  hard_stop_enabled: boolean;
}

export interface ModelUsageBreakdownItem extends DisplayEstimate {
  model: string;
  provider: string;
  vendor: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd?: string | null;
  unpriced_requests?: number;
  share_pct: number;
}

export interface ProductUsageBreakdownItem extends DisplayEstimate {
  subscription_id: string;
  subscription_name: string;
  team: string;
  product_name: string;
  requests: number;
  total_tokens: number;
  cost_usd?: string | null;
  unpriced_requests?: number;
  share_pct: number;
}

export interface ChannelUsageBreakdownItem extends DisplayEstimate {
  channel: string;
  requests: number;
  total_tokens: number;
  cost_usd?: string | null;
  unpriced_requests?: number;
  share_pct: number;
}

export interface CreditSummary extends DisplayEstimate {
  organization_id: string;
  organization_name: string;
  currency: string;
  total_credits: string;
  used_credits: string;
  remaining_credits: string | null;
  utilization_pct: number | null;
  unpriced_requests?: number;
  cost_complete?: boolean;
  alert_threshold_pct: number;
  low_credit_alert: boolean;
  hard_stop_enabled: boolean;
  total_requests: number;
  total_tokens: number;
  by_model: ModelUsageBreakdownItem[];
  by_product: ProductUsageBreakdownItem[];
  by_channel: ChannelUsageBreakdownItem[];
}

/** Customer responses exclude all internal-cost-derived balance signals. */
export type CustomerCreditSummary = Omit<CreditSummary,
  "used_credits" | "remaining_credits" | "utilization_pct" | "low_credit_alert" | "cost_complete" | "unpriced_requests"
  | "by_model" | "by_product" | "by_channel"
> & {
  by_model: Omit<ModelUsageBreakdownItem, "cost_usd" | "unpriced_requests">[];
  by_product: Omit<ProductUsageBreakdownItem, "cost_usd" | "unpriced_requests">[];
  by_channel: Omit<ChannelUsageBreakdownItem, "cost_usd" | "unpriced_requests">[];
};

export type RouterStrategy = "microsoft-decision-1" | "cost-optimized" | "latency-optimized" | "quality-first";

export interface RouterRuleItem {
  category: string;
  description: string;
  keywords: string[];
  preferred_model: string;
  fallback_model: string;
}

export interface ModelRouterConfig {
  enabled: boolean;
  strategy: RouterStrategy;
  decision_endpoint: string;
  default_model: string;
  candidate_models: string[];
  rules: RouterRuleItem[];
  updated_at: string;
}

export interface RouterDecision {
  requested_model: string;
  selected_model: string;
  display_name: string;
  provider: string;
  vendor: string;
  category: string;
  strategy: string;
  decision_endpoint: string;
  confidence: number;
  reason: string;
  estimated_input_per_million: string;
  estimated_output_per_million: string;
}

export interface PlaygroundChatInput {
  model: string;
  messages: { role: "system" | "user" | "assistant"; content: string }[];
  max_completion_tokens?: number;
  temperature?: number;
  subscription_id?: string;
}

export interface PlaygroundChatResult {
  id: string;
  requested_model: string;
  selected_model: string;
  provider: string;
  vendor: string;
  reply: string;
  routing_decision: RouterDecision | null;
  safety_status: "passed" | "blocked";
  safety_categories: Record<string, number>;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: string | null;
  latency_ms: number;
}

export interface TurnstilePolicyPreview {
  ledger_storage_account: string;
  ledger_table_name: string;
  model_routes_table_name: string;
  decision_router_enabled: boolean;
  decision_endpoint: string;
  policy_xml: string;
}

export interface LocalUserItem {
  id: string;
  email: string;
  display_name: string;
  organization_id: string;
  organization_name: string;
  object_id: string;
  role: Role;
  enabled: boolean;
  created_at: string;
}

export interface LocalUserCreateInput {
  email: string;
  password: string;
  display_name: string;
  organization_id: string;
  role: Role;
}

/** Decision traces are separate from completion requests and billing records. */
export interface DecisionScoringQuery {
  days?: number;
  start?: string;
  end?: string;
  subscription_id?: string;
  organization_id?: string;
  offset?: number;
  limit?: number;
  granularity?: "minute" | "hour" | "day";
  time_zone?: "UTC" | "Asia/Singapore";
}

export interface DecisionScoringAggregate {
  invocations: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
}

export interface DecisionScoringTelemetry {
  model: "Decision-1";
  source: "log_analytics";
  status: "available" | "unavailable" | "partial";
  notice: string | null;
  start: string;
  end: string;
  retention_notice: string;
  granularity: "minute" | "hour" | "day";
  time_zone: "UTC" | "Asia/Singapore";
  offset: number;
  limit: number;
  total: number | null;
  summary: DecisionScoringAggregate & {
    measured_invocations: number;
    missing_token_invocations: number;
    estimated_cost_usd: string | null;
    recorded_cost_usd?: string | null;
    estimated_invocations: number;
    unestimated_invocations: number;
    avg_latency_ms: number | null;
    pricing_revision: string | null;
  };
  items: Array<{
    id: string;
    parent_request_id: string;
    subscription_id: string;
    organization_id: string;
    occurred_at: string;
    routing_profile: string;
    selected_model: string;
    config_version: string;
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    latency_ms: number | null;
    recorded_cost_usd?: string | null;
    estimated_cost_usd: string | null;
    estimate_basis: string;
    pricing_revision: string | null;
    parent_status_code: number | null;
    usage_kind: "decision_scoring";
  }>;
  series: Array<DecisionScoringAggregate & {
    start: string;
    end: string;
    partial_bucket: boolean;
    avg_latency_ms: number | null;
  }>;
  breakdown: Array<DecisionScoringAggregate & {
    organization_id: string;
    subscription_id: string;
    estimated_cost_usd: string | null;
  }>;
}

