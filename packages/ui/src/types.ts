export type Role = "customer" | "ids_admin";
export type SubscriptionState = "pending" | "active" | "suspended" | "failed";
export type KeyName = "primary" | "secondary";

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
}

export interface AdminSubscription extends Subscription {
  organization_id: string;
  organization_name: string;
  team_id: string | null;
  gateway_access: "ready" | "pending" | "not_managed";
  gateway_message: string | null;
}

export interface UsageSummary {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  known_cost: string | null;
  currency: string | null;
  incomplete_requests: number;
  failed_requests: number;
  throttled_requests: number;
  e2e_p95_ms: number | null;
  ttft_supported: boolean;
  cache_tokens_supported: boolean;
  last_ingested_at: string | null;
}

export interface UsageItem {
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
  cost: string | null;
  currency: string | null;
  status_code: number;
  e2e_ms: number | null;
  ttft_ms: number | null;
  completeness: string;
}

export interface UsagePage extends Paged<UsageItem> {
  summary: UsageSummary;
}

export interface UsageMinute {
  minute: string;
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
  interval_seconds: 60;
}

export interface ModelTokenBucket {
  start: string;
  end: string;
  model: string;
  requests: number;
  total_tokens: number | null;
  missing_token_requests: number;
}

export interface ModelTokenSeries {
  items: ModelTokenBucket[];
  start: string;
  end: string;
  interval_seconds: number;
}

export interface UsageFilters {
  days: number;
  subscription_id?: string;
  organization_id?: string;
  model?: string;
}

export interface UsageQuery extends UsageFilters {
  offset: number;
  limit: number;
}

export interface UsageSeriesQuery extends UsageFilters {
  start?: string;
  end?: string;
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
export type GatewayConfigurationUnion = GatewayConfiguration | ManagedGatewayConfiguration;
export interface GatewayCapabilities {
  managed_controls_enabled: boolean;
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
  capabilities?: GatewayCapabilities;
}

export interface ModelGardenItem {
  id: string;
  display_name: string;
  provider: string;
  vendor: string;
  region: string;
  backend_model: string;
  endpoint_url: string;
  context_window: number;
  max_completion_tokens: number;
  input_per_million: string;
  output_per_million: string;
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
  remaining_credits: string;
  utilization_pct: number;
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

export interface ModelUsageBreakdownItem {
  model: string;
  provider: string;
  vendor: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: string;
  share_pct: number;
}

export interface ProductUsageBreakdownItem {
  subscription_id: string;
  subscription_name: string;
  team: string;
  product_name: string;
  requests: number;
  total_tokens: number;
  cost_usd: string;
  share_pct: number;
}

export interface ChannelUsageBreakdownItem {
  channel: string;
  requests: number;
  total_tokens: number;
  cost_usd: string;
  share_pct: number;
}

export interface CreditSummary {
  organization_id: string;
  organization_name: string;
  currency: string;
  total_credits: string;
  used_credits: string;
  remaining_credits: string;
  utilization_pct: number;
  alert_threshold_pct: number;
  low_credit_alert: boolean;
  hard_stop_enabled: boolean;
  total_requests: number;
  total_tokens: number;
  by_model: ModelUsageBreakdownItem[];
  by_product: ProductUsageBreakdownItem[];
  by_channel: ChannelUsageBreakdownItem[];
}

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
  estimated_cost_usd: string;
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
