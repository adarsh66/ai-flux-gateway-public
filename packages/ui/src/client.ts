import type {
  PricingHistoryPage, PricingHistoryDetail,
  DeletionCollection, DeletionPreview, DeletionRequest, DeletionResult,
  MonthlyBudgetSummary, MonthlyBudgetUpdate, MonthlyBudgetRevision, AdminMonthlyBudgetDashboard,
  AdminSubscription, CustomerCreditSummary, ExternalCardUpdate, ExternalRateCard,
  UsageRankings, UsageRankingQuery, OrganizationCosts, OrganizationCostsQuery,
  CatalogModel, CreditBudget, CreditBudgetUpdateInput, CreditSummary, GatewayConfigurationUnion, GatewayRevision, GatewayScope, GatewaySettings, GatewayTarget, LocalUserCreateInput, LocalUserItem, ModelGardenItem, ModelRouterConfig, PlaygroundChatInput, PlaygroundChatResult, RouterDecision, RouterStrategy, SafetyConfiguration,
  KeyName, Me, Member, ModelTokenSeries, Organization, Paged, Price, PriceInput, RateCard, RateInput, SafetyEvent,
  Subscription, SubscriptionState, TurnstilePolicyPreview, UsageFilters, UsagePage, UsageQuery, UsageSeries, UsageSeriesQuery,
} from "./types";

import type { AutoConfiguration, AutoProfileConfig, AutoRoutingAvailability, RoutingProfile } from "./autoRouting";

export class ApiError extends Error {
  constructor(public status: number, public detail: string, public body?: unknown) {
    super(detail);
    this.name = "ApiError";
  }
}

export type TokenProvider = () => Promise<string>;
export type FetchLike = typeof fetch;

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && "message" in d && typeof d.message === "string") return d.message;
    if (Array.isArray(d)) {
      return d.map((e) => (e && typeof e === "object" && "msg" in e ? String((e as { msg: unknown }).msg) : "Invalid request")).join("; ");
    }
  }
  return fallback;
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export class ControlApi {
  constructor(
    private baseUrl: string,
    private getToken: TokenProvider,
    private fetchImpl: FetchLike = (...a) => fetch(...a),
  ) {}

  private async send(path: string, init: Omit<RequestInit, "headers"> & { json?: unknown; headers?: Record<string, string> } = {}): Promise<Response> {
    init.signal?.throwIfAborted();
    const token = await this.getToken();
    init.signal?.throwIfAborted();
    const headers: Record<string, string> = { Accept: "application/json", ...(init.headers ?? {}), Authorization: `Bearer ${token}` };
    let body = init.body;
    if (init.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(init.json);
    }
    let res: Response;
    try {
      res = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers, body, cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" });
    } catch {
      throw new ApiError(0, "Could not reach the control plane. Check your connection and try again.");
    }
    if (!res.ok) {
      let detail = `Request failed (${res.status}).`;
      let errorBody: unknown;
      try {
        errorBody = await res.json();
        detail = detailOf(errorBody, detail);
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(res.status, detail, errorBody);
    }
    return res;
  }

  private async json<T>(path: string, init?: Parameters<ControlApi["send"]>[1]): Promise<T> {
    const res = await this.send(path, init);
    return (await res.json()) as T;
  }

  me = () => this.json<Me>("/me");
  deletionPreview = (collection: DeletionCollection, id: string) =>
    this.json<DeletionPreview>(`/admin/${collection}/${encodeURIComponent(id)}/deletion-preview`);
  async deleteEntity(collection: DeletionCollection, id: string, input: DeletionRequest): Promise<DeletionResult> {
    try {
      return await this.json<DeletionResult>(`/admin/${collection}/${encodeURIComponent(id)}`, { method: "DELETE", json: input });
    } catch (error) {
      // A durable failed revocation is a result, not a generic hidden 502.
      if (error instanceof ApiError && error.status === 502 && error.body && typeof error.body === "object") {
        const result = error.body as Partial<DeletionResult>;
        if (result.entity_id === id && result.status === "failed" && typeof result.message === "string") return result as DeletionResult;
      }
      throw error;
    }
  }
  models = () => this.json<Paged<CatalogModel>>("/models");
  modelDeployments = () => this.json<{ items: { id: string; provider: string; model_name: string; model_version: string; role: string; status: string; chat_selectable: boolean; pricing_status: string; credential_healthy?: boolean; limitation?: string | null }[]; verified_at: string; auto_enabled: boolean }>("/model-deployments");
  subscriptions = (offset = 0, limit = 50) => this.json<Paged<Subscription>>(`/subscriptions${qs({ offset, limit })}`);
  adminSubscriptions = (offset = 0, limit = 50, organizationId?: string) =>
    this.json<Paged<AdminSubscription>>(`/admin/subscriptions${qs({ offset, limit, organization_id: organizationId })}`);
  adminCreateSubscription = (input: { organization_id: string; name: string; team: string }, idempotencyKey: string) =>
    this.json<AdminSubscription>("/admin/subscriptions", { method: "POST", json: input, headers: { "Idempotency-Key": idempotencyKey } });
  adminRevealKey = async (id: string, key: KeyName) =>
    (await this.json<{ key: string }>(`/admin/subscriptions/${encodeURIComponent(id)}/reveal`, { method: "POST", json: { key } })).key;
  createSubscription = (input: { name: string; team: string }, idempotencyKey: string) =>
    this.json<Subscription>("/subscriptions", { method: "POST", json: input, headers: { "Idempotency-Key": idempotencyKey } });
  revealKey = async (id: string, key: KeyName, signal?: AbortSignal) =>
    (await this.json<{ key: string }>(`/subscriptions/${encodeURIComponent(id)}/reveal`, { method: "POST", json: { key }, signal })).key;
  rotateKey = (id: string, key: KeyName) =>
    this.json<{ state: SubscriptionState }>(`/admin/subscriptions/${encodeURIComponent(id)}/rotate`, { method: "POST", json: { key } });
  setState = (id: string, state: "active" | "suspended") =>
    this.json<AdminSubscription>(`/admin/subscriptions/${encodeURIComponent(id)}/state`, { method: "PUT", json: { state } });
  reconcile = (id: string) => this.json<AdminSubscription>(`/admin/subscriptions/${encodeURIComponent(id)}/reconcile`, { method: "POST" });

  usage = (q: UsageQuery) => this.json<UsagePage>(`/usage${qs({ days: q.days, subscription_id: q.subscription_id, model: q.model, offset: q.offset, limit: q.limit, start: q.start, end: q.end })}`);
  adminUsage = (q: UsageQuery) =>
    this.json<UsagePage>(`/admin/usage${qs({ days: q.days, subscription_id: q.subscription_id, organization_id: q.organization_id, model: q.model, offset: q.offset, limit: q.limit, start: q.start, end: q.end })}`);
  usageModels = (q: Omit<UsageFilters, "model">) =>
    this.json<Paged<string>>(`/usage/models${qs({ days: q.days, subscription_id: q.subscription_id })}`);
  adminUsageModels = (q: Omit<UsageFilters, "model">) =>
    this.json<Paged<string>>(`/admin/usage/models${qs({ days: q.days, subscription_id: q.subscription_id, organization_id: q.organization_id, start: q.start, end: q.end })}`);
  adminUsageRankings = (q: UsageRankingQuery) =>
    this.json<UsageRankings>(`/admin/usage/rankings${qs({ ...q })}`);
  adminOrganizationCosts = (q: OrganizationCostsQuery) =>
    this.json<OrganizationCosts>(`/admin/usage/organization-costs${qs({ ...q })}`);
  usageSeries = (q: UsageSeriesQuery) =>
    this.json<UsageSeries>(`/usage/timeseries${qs({ days: q.days, subscription_id: q.subscription_id, model: q.model, start: q.start, end: q.end, granularity: q.granularity, time_zone: q.time_zone })}`);
  modelTokens = (q: Omit<UsageSeriesQuery, "granularity"> & { granularity?: "auto" | "hour" | "day" }) =>
    this.json<ModelTokenSeries>(`/usage/model-tokens${qs({ days: q.days, subscription_id: q.subscription_id, model: q.model, start: q.start, end: q.end, granularity: q.granularity, time_zone: q.time_zone })}`);
  adminModelTokens = (q: Omit<UsageSeriesQuery, "granularity"> & { granularity?: "auto" | "hour" | "day" }) =>
    this.json<ModelTokenSeries>(`/admin/usage/model-tokens${qs({ days: q.days, subscription_id: q.subscription_id, organization_id: q.organization_id, model: q.model, start: q.start, end: q.end, granularity: q.granularity, time_zone: q.time_zone })}`);
  adminUsageSeries = (q: UsageSeriesQuery) =>
    this.json<UsageSeries>(`/admin/usage/timeseries${qs({ days: q.days, subscription_id: q.subscription_id, organization_id: q.organization_id, model: q.model, start: q.start, end: q.end, granularity: q.granularity, time_zone: q.time_zone })}`);

  decisionScoring = (q: import("./types").DecisionScoringQuery) =>
    this.json<import("./types").DecisionScoringTelemetry>(`/usage/decision-scoring${qs({ ...q, organization_id: undefined })}`);
  adminDecisionScoring = (q: import("./types").DecisionScoringQuery) =>
    this.json<import("./types").DecisionScoringTelemetry>(`/admin/usage/decision-scoring${qs({ ...q })}`);
  async exportDecisionScoringCsv(admin: boolean, q: import("./types").DecisionScoringQuery): Promise<Blob> {
    const res = await this.send(`${admin ? "/admin" : ""}/usage/decision-scoring/export.csv${qs({ ...q, organization_id: admin ? q.organization_id : undefined })}`, { headers: { Accept: "text/csv" } });
    return res.blob();
  }

  /** Authenticated CSV export; the token travels only in the Authorization header. */
  async exportCsv(admin: boolean, q: UsageFilters): Promise<Blob> {
    const path = `${admin ? "/admin" : ""}/usage/export${qs({ days: q.days, subscription_id: q.subscription_id, organization_id: admin ? q.organization_id : undefined, model: q.model, start: q.start, end: q.end })}`;
    const res = await this.send(path, { headers: { Accept: "text/csv" } });
    return res.blob();
  }

  organizations = () => this.json<Paged<Organization>>("/admin/organizations");
  organizationModelAccess = (id: string) => this.json<import("./types").OrganizationModelAccess>(`/admin/organizations/${encodeURIComponent(id)}/model-access`);
  saveOrganizationModelAccess = (id: string, input: { expected_version: number; denied_models: string[]; auto_enabled: boolean; reason: string }) =>
    this.json<import("./types").OrganizationModelAccess>(`/admin/organizations/${encodeURIComponent(id)}/model-access`, { method: "PUT", json: input });
  retryOrganizationModelAccess = (id: string) => this.json<import("./types").OrganizationModelAccess>(`/admin/organizations/${encodeURIComponent(id)}/model-access/retry`, { method: "POST" });
  createOrganization = (input: { name: string; tenant_id: string }) => this.json<Organization>("/admin/organizations", { method: "POST", json: input });
  setOrganizationEnabled = (id: string, enabled: boolean) =>
    this.json<Organization>(`/admin/organizations/${encodeURIComponent(id)}`, { method: "PUT", json: { enabled } });

  members = (organizationId: string) => this.json<Paged<Member>>(`/admin/members${qs({ organization_id: organizationId })}`);
  createMember = (input: { organization_id: string; object_id: string; role: Member["role"] }) =>
    this.json<Member>("/admin/members", { method: "POST", json: input });
  setMemberEnabled = (id: string, enabled: boolean) =>
    this.json<Member>(`/admin/members/${encodeURIComponent(id)}`, { method: "PUT", json: { enabled } });

  safety = (days: number, organizationId: string | undefined, offset: number, limit: number) =>
    this.json<Paged<SafetyEvent>>(`/admin/safety${qs({ days, organization_id: organizationId, offset, limit })}`);

  prices = () => this.json<Paged<Price>>("/admin/prices");
  rateCard = () => this.json<RateCard>("/admin/rate-card");
  pricingHistory = (external: boolean, organizationId?: string, offset = 0) =>
    this.json<PricingHistoryPage>(`${external ? organizationId ? `/admin/organizations/${encodeURIComponent(organizationId)}/external-rate-card` : "/admin/external-rate-card" : "/admin/rate-card"}/history${qs({ offset })}`);
  pricingHistoryDetail = (external: boolean, revision: string, organizationId?: string) =>
    this.json<PricingHistoryDetail>(`${external ? organizationId ? `/admin/organizations/${encodeURIComponent(organizationId)}/external-rate-card` : "/admin/external-rate-card" : "/admin/rate-card"}/history/detail${qs({ revision })}`);
  saveRateCard = (expectedVersion: number, rates: RateInput[], reason?: string) =>
    this.json<RateCard>("/admin/rate-card", { method: "PUT", json: { expected_version: expectedVersion, rates, reason } });
  externalRateCard = (organizationId?: string) =>
    this.json<ExternalRateCard>(organizationId ? `/admin/organizations/${encodeURIComponent(organizationId)}/external-rate-card` : "/admin/external-rate-card");
  saveExternalRateCard = (input: ExternalCardUpdate, organizationId?: string) =>
    this.json<ExternalRateCard>(organizationId ? `/admin/organizations/${encodeURIComponent(organizationId)}/external-rate-card` : "/admin/external-rate-card", { method: "PUT", json: input });
  effectiveRateCard = () => this.json<ExternalRateCard>("/rate-card");
  gatewaySettings = () => this.json<Paged<GatewaySettings>>("/admin/gateway-settings");
  saveGatewaySettings = (scope: GatewayScope, expectedVersion: number, configuration: GatewayConfigurationUnion, reason: string) =>
    this.json<GatewaySettings>(`/admin/gateway-settings/${scope}`, { method: "PUT", json: { expected_version: expectedVersion, configuration, reason } });
  reconcileGatewaySettings = (scope: GatewayScope, expectedVersion: number) =>
    this.json<GatewaySettings>(`/admin/gateway-settings/${scope}/reconcile`, { method: "POST", json: { expected_version: expectedVersion } });
  gatewaySettingsHistory = (scope: GatewayScope, offset = 0, limit = 10) =>
    this.json<Paged<GatewayRevision>>(`/admin/gateway-settings/${scope}/history${qs({ offset, limit })}`);
  gatewayTargets = (offset = 0, limit = 100, organizationId?: string) =>
    this.json<Paged<GatewayTarget>>(`/admin/gateway-targets${qs({ offset, limit, organization_id: organizationId })}`);
  contentSafetySettings = () => this.json<Paged<GatewaySettings>>("/admin/content-safety-settings");
  saveContentSafetySettings = (scope: GatewayScope, expectedVersion: number, configuration: SafetyConfiguration, reason: string, acknowledgeRelaxation: boolean, target?: { organization_id: string | null; subscription_id: string | null; inherit: boolean }) =>
    this.json<GatewaySettings>(`/admin/content-safety-settings/${scope}`, { method: "PUT", json: { expected_version: expectedVersion, configuration, reason, acknowledge_relaxation: acknowledgeRelaxation, ...target } });
  reconcileContentSafetySettings = (scope: GatewayScope, expectedVersion: number) =>
    this.json<GatewaySettings>(`/admin/content-safety-settings/${scope}/reconcile`, { method: "POST", json: { expected_version: expectedVersion } });
  contentSafetySettingsHistory = (scope: GatewayScope, offset = 0, limit = 10) =>
    this.json<Paged<GatewayRevision>>(`/admin/content-safety-settings/${scope}/history${qs({ offset, limit })}`);
  endPrice = (id: string, effectiveTo: string) =>
    this.json<Price>(`/admin/prices/${encodeURIComponent(id)}/end`, { method: "PUT", json: { effective_to: effectiveTo } });
  createPrice = (input: PriceInput) => this.json<Price>("/admin/prices", { method: "POST", json: input });

  modelGarden = () => this.json<Paged<ModelGardenItem>>("/model-garden");
  adminModelGarden = () => this.json<Paged<ModelGardenItem>>("/admin/model-garden");
  saveModelGardenItem = (input: Omit<ModelGardenItem, "priority"> & { priority?: number }) =>
    this.json<ModelGardenItem>(`/admin/model-garden/${encodeURIComponent(input.id)}`, { method: "PUT", json: { priority: 100, ...input } });

  creditSummary = (days = 30, subscriptionId?: string) =>
    this.json<CustomerCreditSummary>(`/credits/summary${qs({ days, subscription_id: subscriptionId })}`);
  monthlyBudget = () => this.json<MonthlyBudgetSummary>("/budget/monthly");
  adminMonthlyBudgets = (offset = 0, limit = 100, archive_state: "current" | "archived" = "current") =>
    this.json<Paged<MonthlyBudgetSummary & { archived_at?: string | null }>>(`/admin/monthly-budgets${qs({ offset, limit, archive_state })}`);
  adminMonthlyBudgetDashboard = (organizationId: string) =>
    this.json<AdminMonthlyBudgetDashboard>(`/admin/monthly-budgets/${encodeURIComponent(organizationId)}`);
  saveMonthlyBudget = (organizationId: string, input: MonthlyBudgetUpdate) =>
    this.json<MonthlyBudgetSummary>(`/admin/monthly-budgets/${encodeURIComponent(organizationId)}`, { method: "PUT", json: input });
  monthlyBudgetHistory = (organizationId: string, offset = 0, limit = 20) =>
    this.json<Paged<MonthlyBudgetRevision>>(`/admin/monthly-budgets/${encodeURIComponent(organizationId)}/history${qs({ offset, limit })}`);
  adminFinopsSummary = (days = 30, organizationId?: string, subscriptionId?: string) =>
    this.json<CreditSummary>(`/admin/finops/summary${qs({ days, organization_id: organizationId, subscription_id: subscriptionId })}`);
  adminBudgets = (organizationId?: string) =>
    this.json<Paged<CreditBudget>>(`/admin/budgets${qs({ organization_id: organizationId })}`);
  saveAdminBudget = (organizationId: string, input: CreditBudgetUpdateInput) =>
    this.json<CreditBudget>(`/admin/budgets/${encodeURIComponent(organizationId)}`, { method: "PUT", json: input });

  customerRotateKey = (id: string, key: KeyName) =>
    this.json<{ state: SubscriptionState; rotated_key: KeyName }>(`/subscriptions/${encodeURIComponent(id)}/customer-rotate`, { method: "POST", json: { key } });

  modelRouter = () => this.json<ModelRouterConfig>("/model-router");
  autoRoutingAvailability = () => this.json<AutoRoutingAvailability>("/auto-routing/availability");
  adminAutoRouting = () => this.json<AutoConfiguration>("/admin/auto-routing");
  initializeAutoRouting = () => this.json<AutoConfiguration>("/admin/auto-routing/initialize", { method: "POST" });
  saveAutoProfile = (profile: RoutingProfile, input: { enabled: boolean; candidate_models: string[]; fallback_model: string; expected_version: string }) =>
    this.json<AutoProfileConfig>(`/admin/auto-routing/${profile}`, { method: "PUT", json: input });
  adminModelRouter = () => this.json<ModelRouterConfig>("/admin/model-router");
  saveAdminModelRouter = (input: Omit<ModelRouterConfig, "updated_at">) =>
    this.json<ModelRouterConfig>("/admin/model-router", { method: "PUT", json: input });
  decideModelRoute = (prompt: string, strategy?: RouterStrategy) =>
    this.json<RouterDecision>("/model-router/decide", { method: "POST", json: { prompt, strategy } });
  playgroundChat = (input: PlaygroundChatInput) =>
    this.json<PlaygroundChatResult>("/playground/chat", { method: "POST", json: input });
  turnstilePolicyPreview = () =>
    this.json<TurnstilePolicyPreview>("/admin/turnstile/policy-preview");

  localUsers = (organizationId?: string) =>
    this.json<Paged<LocalUserItem>>(`/admin/local-users${qs({ organization_id: organizationId })}`);
  createLocalUser = (input: LocalUserCreateInput) =>
    this.json<LocalUserItem>("/admin/local-users", { method: "POST", json: input });
  updateLocalUser = (id: string, input: { enabled: boolean; password?: string }) =>
    this.json<LocalUserItem>(`/admin/local-users/${encodeURIComponent(id)}`, { method: "PUT", json: input });
}