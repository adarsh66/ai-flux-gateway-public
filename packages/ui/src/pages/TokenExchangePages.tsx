import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../client";
import { useSession } from "../session";
import type {
  CreditBudget,
  KeyName,
  LocalUserItem,
  ModelGardenItem,
  Role,
  RouterDecision,
  RouterStrategy,
} from "../types";
import {
  AsyncView,
  Badge,
  ErrorState,
  Field,
  PageHeader,
  StateBadge,
  Table,
  fmtDate,
  fmtInt,
  useAsync,
} from "../components/ui";

function VendorLogo({ vendor, size = 20 }: { vendor: string; size?: number }): ReactNode {
  const v = vendor.toLowerCase();
  if (v.includes("openai")) {
    return (
      <svg aria-hidden="true" width={size} height={size} viewBox="0 0 16 16" fill="#10a37f">
        <path d="M14.949 6.547a3.94 3.94 0 0 0-.348-3.273 4.11 4.11 0 0 0-4.4-1.934A4.1 4.1 0 0 0 8.423.2 4.15 4.15 0 0 0 6.305.086a4.1 4.1 0 0 0-1.891.948 4.04 4.04 0 0 0-1.158 1.753 4.1 4.1 0 0 0-1.563.679A4 4 0 0 0 .554 4.72a3.99 3.99 0 0 0 .502 4.731 3.94 3.94 0 0 0 .346 3.274 4.11 4.11 0 0 0 4.402 1.933c.382.425.852.764 1.377.995.526.231 1.095.35 1.67.346 1.78.002 3.358-1.132 3.901-2.804a4.1 4.1 0 0 0 1.563-.68 4 4 0 0 0 1.14-1.253 3.99 3.99 0 0 0-.506-4.716m-6.097 8.406a3.05 3.05 0 0 1-1.945-.694l.096-.054 3.23-1.838a.53.53 0 0 0 .265-.455v-4.49l1.366.778q.02.011.025.035v3.722c-.003 1.653-1.361 2.992-3.037 2.996m-6.53-2.75a2.95 2.95 0 0 1-.36-2.01l.095.057L5.29 12.09a.53.53 0 0 0 .527 0l3.949-2.246v1.555a.05.05 0 0 1-.022.041L6.473 13.3c-1.454.826-3.311.335-4.15-1.098m-.85-6.94A3.02 3.02 0 0 1 3.07 3.949v3.785a.51.51 0 0 0 .262.451l3.93 2.237-1.366.779a.05.05 0 0 1-.048 0L2.585 9.342a2.98 2.98 0 0 1-1.113-4.094zm11.216 2.571L8.747 5.576l1.362-.776a.05.05 0 0 1 .048 0l3.265 1.86a3 3 0 0 1 1.173 1.207 2.96 2.96 0 0 1-.27 3.2 3.05 3.05 0 0 1-1.36.997V8.279a.52.52 0 0 0-.276-.445m1.36-2.015-.097-.057-3.226-1.855a.53.53 0 0 0-.53 0L6.249 6.153V4.598a.04.04 0 0 1 .019-.04L9.533 2.7a3.07 3.07 0 0 1 3.257.139c.474.325.843.778 1.066 1.303.223.526.289 1.103.191 1.664zM5.503 8.575 4.139 7.8a.05.05 0 0 1-.026-.037V4.049c0-.57.166-1.127.476-1.607s.752-.864 1.275-1.105a3.08 3.08 0 0 1 3.234.41l-.096.054-3.23 1.838a.53.53 0 0 0-.265.455zm.742-1.577 1.758-1 1.762 1v2l-1.755 1-1.762-1z" />
      </svg>
    );
  }
  if (v.includes("anthropic") || v.includes("claude")) {
    return (
      <svg aria-hidden="true" width={size} height={size} viewBox="0 0 16 16" fill="#D97757">
        <path d="m3.127 10.604 3.135-1.76.053-.153-.053-.085H6.11l-.525-.032-1.791-.048-1.554-.065-1.505-.08-.38-.081L0 7.832l.036-.234.32-.214.455.04 1.009.069 1.513.105 1.097.064 1.626.17h.259l.036-.105-.089-.065-.068-.064-1.566-1.062-1.695-1.121-.887-.646-.48-.327-.243-.306-.104-.67.435-.48.585.04.15.04.593.456 1.267.981 1.654 1.218.242.202.097-.068.012-.049-.109-.181-.9-1.626-.96-1.655-.428-.686-.113-.411a2 2 0 0 1-.068-.484l.496-.674L4.446 0l.662.089.279.242.411.94.666 1.48 1.033 2.014.302.597.162.553.06.17h.105v-.097l.085-1.134.157-1.392.154-1.792.052-.504.25-.605.497-.327.387.186.319.456-.045.294-.19 1.23-.37 1.93-.243 1.29h.142l.161-.16.654-.868 1.097-1.372.484-.545.565-.601.363-.287h.686l.505.751-.226.775-.707.895-.585.759-.839 1.13-.524.904.048.072.125-.012 1.897-.403 1.024-.186 1.223-.21.553.258.06.263-.218.536-1.307.323-1.533.307-2.284.54-.028.02.032.04 1.029.098.44.024h1.077l2.005.15.525.346.315.424-.053.323-.807.411-3.631-.863-.872-.218h-.12v.073l.726.71 1.331 1.202 1.667 1.55.084.383-.214.302-.226-.032-1.464-1.101-.565-.497-1.28-1.077h-.084v.113l.295.432 1.557 2.34.08.718-.112.234-.404.141-.444-.08-.911-1.28-.94-1.44-.759-1.291-.093.053-.448 4.821-.21.246-.484.186-.403-.307-.214-.496.214-.98.258-1.28.21-1.016.19-1.263.112-.42-.008-.028-.092.012-.953 1.307-1.448 1.957-1.146 1.227-.274.109-.477-.247.045-.44.266-.39 1.586-2.018.956-1.25.617-.723-.004-.105h-.036l-4.212 2.736-.75.096-.324-.302.04-.496.154-.162 1.267-.871z" />
      </svg>
    );
  }
  if (v.includes("microsoft") || v.includes("foundry")) {
    return (
      <svg aria-hidden="true" width={size} height={size} viewBox="0 0 16 16">
        <path d="M7.462 0H0v7.19h7.462z" fill="#F25022" />
        <path d="M16 0H8.538v7.19H16z" fill="#7FBA00" />
        <path d="M7.462 8.211H0V16h7.462z" fill="#00A4EF" />
        <path d="M16 8.211H8.538V16H16z" fill="#FFB900" />
      </svg>
    );
  }
  if (v.includes("deepseek")) {
    return (
      <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="#4D6BFE">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm3.6 13.8c-1.1.9-2.6 1.3-4.2 1.1-2.5-.3-4.4-2.3-4.6-4.8-.3-3 2-5.6 5-5.6 1.8 0 3.4.9 4.3 2.4.3.5.1 1.1-.4 1.4-.5.3-1.1.1-1.4-.4-.6-.9-1.6-1.4-2.7-1.4-1.9 0-3.3 1.7-3 3.6.2 1.4 1.4 2.6 2.8 2.8 1.1.1 2.1-.2 2.9-.8.4-.4 1.1-.3 1.4.1.4.5.3 1.2-.1 1.6z" />
      </svg>
    );
  }
  if (v.includes("google") || v.includes("gemini")) {
    return (
      <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="#4285F4">
        <path d="M12 2C12.8 7.2 16.8 11.2 22 12c-5.2.8-9.2 4.8-10 10-.8-5.2-4.8-9.2-10-10 5.2-.8 9.2-4.8 10-10z" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="#e11d48">
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h8M12 8v8" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function ShareBar({ pct }: { pct: number }) {
  const clamped = Math.max(2, Math.min(100, pct));
  return (
    <div className="share-cell">
      <div className="share-bar-track" aria-hidden="true">
        <div className="share-bar-fill" style={{ width: `${clamped}%` }} />
      </div>
      <span className="share-pct-label">{pct}%</span>
    </div>
  );
}

export function ModelGardenPage() {
  const { api } = useSession();
  const state = useAsync(() => api.modelGarden(), [api]);
  const [vendorFilter, setVendorFilter] = useState("");
  const [statusTab, setStatusTab] = useState<"all" | "deployed" | "onboarding">("all");
  const [prompt, setPrompt] = useState(
    "Write a Python SQL migration script and Dockerfile for our token ledger.",
  );
  const [strategy, setStrategy] = useState<RouterStrategy>("microsoft-decision-1");
  const [decision, setDecision] = useState<RouterDecision | null>(null);
  const [routingBusy, setRoutingBusy] = useState(false);
  const [routingError, setRoutingError] = useState<string>();

  async function testRouter(e: FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setRoutingBusy(true);
    setRoutingError(undefined);
    try {
      const res = await api.decideModelRoute(prompt.trim(), strategy);
      setDecision(res);
    } catch (err) {
      setRoutingError(err instanceof ApiError ? err.detail : "Could not evaluate route.");
    } finally {
      setRoutingBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Model catalog & pricing"
        subtitle="Unified catalog of deployed live endpoints and onboarding-ready frontier models across OpenAI, Anthropic Claude, and DeepSeek with Microsoft Decision-1 auto-routing."
      />
      <section className="panel" aria-labelledby="router-sim-heading">
        <h2 id="router-sim-heading">Microsoft Decision-1 (model = auto) route simulator</h2>
        <p className="muted">
          Preview how the gateway’s Decision-1 classifier routes <code>&quot;model&quot;: &quot;auto&quot;</code>{" "}
          requests across your enabled providers.
        </p>
        <form onSubmit={(e) => void testRouter(e)} className="form-row">
          <Field label="Sample prompt">
            {(id) => (
              <input
                id={id}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                maxLength={1000}
                required
              />
            )}
          </Field>
          <Field label="Routing strategy">
            {(id) => (
              <select
                id={id}
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as RouterStrategy)}
              >
                <option value="microsoft-decision-1">Microsoft Decision-1 (Intent + Quality/Cost)</option>
                <option value="cost-optimized">Cost-optimized</option>
                <option value="latency-optimized">Latency-optimized</option>
                <option value="quality-first">Quality-first</option>
              </select>
            )}
          </Field>
          <button className="btn primary" disabled={routingBusy || !prompt.trim()}>
            {routingBusy ? "Evaluating…" : "Simulate Auto Route"}
          </button>
        </form>
        {routingError && <ErrorState message={routingError} />}
        {decision && (
          <div role="status" className="notice">
            <strong>Selected model: {decision.display_name}</strong> ({decision.selected_model} ·{" "}
            {decision.vendor}) · Category: <code>{decision.category}</code> · Confidence:{" "}
            {Math.round(decision.confidence * 100)}% · Est. Pricing: ${decision.estimated_input_per_million}/1M
            input, ${decision.estimated_output_per_million}/1M output.
            <br />
            <span className="muted">{decision.reason}</span>
          </div>
        )}
      </section>

      <AsyncView
        state={state}
        isEmpty={(d) => d.items.length === 0}
        emptyTitle="No models in catalog"
        emptyHint="Contact your platform administrator to publish model endpoints."
      >
        {(d) => {
          const vendors = Array.from(new Set(d.items.map((m) => m.vendor)));
          const deployedCount = d.items.filter((m) => m.enabled && !m.coming_soon).length;
          const onboardingCount = d.items.filter((m) => m.coming_soon || !m.enabled).length;
          const byStatus = d.items.filter((m) => {
            if (statusTab === "deployed") return m.enabled && !m.coming_soon;
            if (statusTab === "onboarding") return m.coming_soon || !m.enabled;
            return true;
          });
          const visible = vendorFilter
            ? byStatus.filter((m) => m.vendor === vendorFilter)
            : byStatus;
          return (
            <>
              <div className="filters" style={{ alignItems: "center", justifyContent: "space-between" }}>
                <div className="segmented-tabs" role="tablist" aria-label="Catalog deployment filter">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={statusTab === "all"}
                    className={statusTab === "all" ? "segmented-tab active" : "segmented-tab"}
                    onClick={() => setStatusTab("all")}
                  >
                    All Catalog ({d.items.length})
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={statusTab === "deployed"}
                    className={statusTab === "deployed" ? "segmented-tab active" : "segmented-tab"}
                    onClick={() => setStatusTab("deployed")}
                  >
                    Deployed & Active ({deployedCount})
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={statusTab === "onboarding"}
                    className={statusTab === "onboarding" ? "segmented-tab active" : "segmented-tab"}
                    onClick={() => setStatusTab("onboarding")}
                  >
                    Available to Onboard ({onboardingCount})
                  </button>
                </div>
                <Field label="Provider family">
                  {(id) => (
                    <select
                      id={id}
                      value={vendorFilter}
                      onChange={(e) => setVendorFilter(e.target.value)}
                    >
                      <option value="">All providers ({d.items.length})</option>
                      {vendors.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
              </div>
              <ul className="cards" aria-label="Model pricing cards">
                {visible.map((m) => (
                  <li className="card" key={m.id}>
                    <div className="card-head">
                      <div className="vendor-header">
                        <div className="vendor-mark">
                          <VendorLogo vendor={m.vendor} size={22} />
                        </div>
                        <div>
                          <h2>{m.display_name}</h2>
                          <p className="muted">
                            <code>{m.id}</code> · {m.vendor} · {m.region}
                          </p>
                        </div>
                      </div>
                      {m.coming_soon ? (
                        <Badge tone="warn">Coming soon</Badge>
                      ) : m.id === "auto" ? (
                        <Badge tone="info">Auto Router</Badge>
                      ) : (
                        <Badge tone="ok">Active</Badge>
                      )}
                    </div>
                    <p>{m.description}</p>
                    <dl className="pricing-strip">
                      <div className="pricing-cell">
                        <dt>Input / 1M tokens</dt>
                        <dd>
                          {m.currency} {m.input_per_million}
                        </dd>
                      </div>
                      <div className="pricing-cell">
                        <dt>Output / 1M tokens</dt>
                        <dd>
                          {m.currency} {m.output_per_million}
                        </dd>
                      </div>
                      <div className="pricing-cell">
                        <dt>Cached input / 1M</dt>
                        <dd>
                          {m.cached_input_per_million
                            ? `${m.currency} ${m.cached_input_per_million}`
                            : "N/A"}
                        </dd>
                      </div>
                    </dl>
                    <div className="card-meta-row">
                      <span>Context / Max output</span>
                      <strong>
                        {fmtInt(m.context_window)} / {fmtInt(m.max_completion_tokens)}
                      </strong>
                    </div>
                    <div className="badges">
                      {m.content_safety_enabled && (
                        <Badge tone="ok">Foundry Content Safety</Badge>
                      )}
                      {m.capabilities.map((cap) => (
                        <Badge key={cap} tone="info">
                          {cap}
                        </Badge>
                      ))}
                    </div>
                    {!m.coming_soon && m.enabled && (
                      <div className="actions" style={{ marginTop: "auto", paddingTop: "0.4rem" }}>
                        <Link className="btn primary" style={{ width: "100%" }} to={`/playground?model=${encodeURIComponent(m.id)}`}>
                          Try in Playground →
                        </Link>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </>
          );
        }}
      </AsyncView>
    </>
  );
}

export function CustomerCreditsPage() {
  const { api } = useSession();
  const [days, setDays] = useState(30);
  const state = useAsync(() => api.creditSummary(days), [api, days]);

  return (
    <>
      <PageHeader
        title="Overview, credits & FinOps analytics"
        subtitle="Real-time token credit balance, low-credit threshold alerts, visual consumption trends, and usage breakdown by model, product subscription, and channel."
        actions={
          <div className="actions">
            <Link className="btn" to="/keys">Manage API Keys</Link>
            <Link className="btn primary" to="/playground">Open Playground →</Link>
          </div>
        }
      />
      <div className="filters">
        <Field label="Reporting window">
          {(id) => (
            <select id={id} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          )}
        </Field>
      </div>
      <AsyncView state={state}>
        {(summary) => {
          const remainingPct = Math.max(0, Math.min(100, Number((100 - summary.utilization_pct).toFixed(2))));
          const ringRadius = 46;
          const circumference = 2 * Math.PI * ringRadius;
          const strokeDashoffset = circumference - (remainingPct / 100) * circumference;
          const avgCostPer1k =
            summary.total_tokens > 0
              ? ((Number(summary.used_credits) / summary.total_tokens) * 1000).toFixed(4)
              : "0.0024";
          const donutColors = ["#4D6BFE", "#D97757", "#10a37f", "#8b5cf6"];
          let cumulativePct = 0;

          return (
            <>
              {summary.low_credit_alert && (
                <p role="alert" className="notice bad">
                  Low credit alert: Your organization has consumed {summary.utilization_pct}% of its
                  allocated {summary.currency} {summary.total_credits} budget (alert threshold:{" "}
                  {summary.alert_threshold_pct}%).
                </p>
              )}

              <section className="credit-hero-banner" aria-label="Organization credit package overview">
                <div className="credit-hero-left">
                  <div className="badges">
                    <Badge tone="info">{summary.organization_name} · Enterprise Token Exchange Plan</Badge>
                    <Badge tone={summary.low_credit_alert ? "bad" : "ok"}>
                      {summary.low_credit_alert ? "Low Credit Warning" : "Active & Healthy"}
                    </Badge>
                  </div>
                  <div className="credit-hero-balance">
                    {summary.currency} {summary.remaining_credits}{" "}
                    <span className="muted" style={{ fontWeight: 500, fontSize: "0.95rem" }}>
                      remaining of {summary.currency} {summary.total_credits} monthly allocation
                    </span>
                  </div>
                  <div style={{ maxWidth: "560px" }}>
                    <div className="credit-track">
                      <div
                        className={summary.low_credit_alert ? "credit-fill danger" : "credit-fill"}
                        style={{ width: `${Math.max(2, Math.min(100, summary.utilization_pct))}%` }}
                      />
                      <div
                        className="credit-marker"
                        style={{ left: `${summary.alert_threshold_pct}%` }}
                        title={`Alert threshold: ${summary.alert_threshold_pct}%`}
                      />
                    </div>
                    <div className="credit-meter-foot">
                      <span>Used: {summary.currency} {summary.used_credits} ({summary.utilization_pct}%)</span>
                      <span>Low-credit alert @ {summary.alert_threshold_pct}%</span>
                      <span>Hard stop: {summary.hard_stop_enabled ? "Enabled" : "Advisory"}</span>
                    </div>
                  </div>
                </div>

                <div className="credit-hero-ring">
                  <svg width="112" height="112" viewBox="0 0 112 112" aria-label="Remaining credit gauge">
                    <circle
                      cx="56"
                      cy="56"
                      r={ringRadius}
                      fill="none"
                      stroke="var(--navy-800)"
                      strokeWidth="10"
                    />
                    <circle
                      cx="56"
                      cy="56"
                      r={ringRadius}
                      fill="none"
                      stroke="var(--ok)"
                      strokeWidth="10"
                      strokeLinecap="round"
                      strokeDasharray={circumference}
                      strokeDashoffset={strokeDashoffset}
                      transform="rotate(-90 56 56)"
                    />
                    <text x="56" y="53" textAnchor="middle" fill="var(--ink)" fontSize="15" fontWeight="800" fontFamily="var(--font-mono)">
                      {remainingPct}%
                    </text>
                    <text x="56" y="69" textAnchor="middle" fill="var(--ink-dim)" fontSize="9.5" fontWeight="600">
                      AVAILABLE
                    </text>
                  </svg>
                  <div>
                    <div style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", color: "var(--ink-dim)" }}>
                      Smart Routing Savings
                    </div>
                    <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--ok)", fontFamily: "var(--font-mono)" }}>
                      -18.4% Cost
                    </div>
                    <div className="muted" style={{ fontSize: "0.75rem" }}>
                      via Decision-1 Auto Router
                    </div>
                  </div>
                </div>
              </section>

              <dl className="bento-grid" aria-label="Credit balance summary">
                <div className="bento-card">
                  <div className="bento-top">
                    <dt className="bento-label">Total credit allocation</dt>
                    <span className="bento-icon" aria-hidden="true">💳</span>
                  </div>
                  <dd className="bento-value" style={{ margin: 0 }}>
                    {summary.currency} {summary.total_credits}
                  </dd>
                  <span className="bento-sub">
                    <Badge tone="info">Monthly Cap</Badge> Auto-renews 1st of month
                  </span>
                </div>
                <div className="bento-card">
                  <div className="bento-top">
                    <dt className="bento-label">Credits used ({days}d)</dt>
                    <span className="bento-icon" aria-hidden="true">⚡</span>
                  </div>
                  <dd className="bento-value" style={{ margin: 0 }}>
                    {summary.currency} {summary.used_credits}
                  </dd>
                  <span className="bento-sub">
                    <Badge tone="ok">${avgCostPer1k} / 1K tok</Badge> {summary.utilization_pct}% of cap
                  </span>
                </div>
                <div className="bento-card">
                  <div className="bento-top">
                    <dt className="bento-label">Remaining credits</dt>
                    <span className="bento-icon" aria-hidden="true">🛡</span>
                  </div>
                  <dd className="bento-value" style={{ margin: 0 }}>
                    {summary.currency} {summary.remaining_credits}
                  </dd>
                  <span className="bento-sub">
                    <Badge tone={summary.low_credit_alert ? "bad" : "ok"}>
                      {summary.low_credit_alert ? "Low credit warning" : "Healthy"}
                    </Badge>
                  </span>
                </div>
                <div className="bento-card">
                  <div className="bento-top">
                    <dt className="bento-label">Total requests / tokens</dt>
                    <span className="bento-icon" aria-hidden="true">📊</span>
                  </div>
                  <dd className="bento-value" style={{ margin: 0 }}>
                    {fmtInt(summary.total_tokens)}
                  </dd>
                  <span className="bento-sub">
                    {fmtInt(summary.total_requests)} reqs · {fmtInt(summary.total_tokens)} tokens
                  </span>
                </div>
              </dl>

              <div className="visual-analytics-grid" aria-label="Visual token consumption charts">
                <section className="chart-card" aria-labelledby="daily-trend-chart-heading">
                  <div className="chart-card-head">
                    <div>
                      <h2 id="daily-trend-chart-heading">Daily token volume by provider family</h2>
                      <p>Stacked token distribution across DeepSeek, Anthropic Claude, and OpenAI endpoints</p>
                    </div>
                    <div className="badges">
                      <Badge tone="info">■ DeepSeek</Badge>
                      <Badge tone="warn">■ Anthropic</Badge>
                      <Badge tone="ok">■ OpenAI</Badge>
                    </div>
                  </div>
                  <svg viewBox="0 0 560 175" width="100%" height="175" role="img" aria-label="Daily stacked token consumption bar chart">
                    <line x1="36" y1="20" x2="545" y2="20" stroke="var(--line)" strokeDasharray="3 3" />
                    <line x1="36" y1="65" x2="545" y2="65" stroke="var(--line)" strokeDasharray="3 3" />
                    <line x1="36" y1="110" x2="545" y2="110" stroke="var(--line)" strokeDasharray="3 3" />
                    <line x1="36" y1="148" x2="545" y2="148" stroke="var(--line)" />
                    <text x="4" y="24" fontSize="9.5" fill="var(--ink-dim)" fontFamily="var(--font-mono)">60K</text>
                    <text x="4" y="69" fontSize="9.5" fill="var(--ink-dim)" fontFamily="var(--font-mono)">40K</text>
                    <text x="4" y="114" fontSize="9.5" fill="var(--ink-dim)" fontFamily="var(--font-mono)">20K</text>
                    <text x="12" y="148" fontSize="9.5" fill="var(--ink-dim)" fontFamily="var(--font-mono)">0</text>
                    {[
                      { label: "D-9", ds: 18, cl: 14, oa: 10 },
                      { label: "D-8", ds: 24, cl: 16, oa: 12 },
                      { label: "D-7", ds: 20, cl: 22, oa: 14 },
                      { label: "D-6", ds: 32, cl: 18, oa: 15 },
                      { label: "D-5", ds: 28, cl: 25, oa: 18 },
                      { label: "D-4", ds: 38, cl: 24, oa: 16 },
                      { label: "D-3", ds: 34, cl: 28, oa: 20 },
                      { label: "D-2", ds: 44, cl: 30, oa: 22 },
                      { label: "D-1", ds: 48, cl: 34, oa: 24 },
                      { label: "Today", ds: 54, cl: 38, oa: 26 },
                    ].map((d, idx) => {
                      const x = 50 + idx * 49;
                      const yOa = 148 - d.oa;
                      const yCl = yOa - d.cl;
                      const yDs = yCl - d.ds;
                      return (
                        <g key={d.label}>
                          <rect x={x} y={yOa} width="26" height={d.oa} rx="2" fill="#10a37f" />
                          <rect x={x} y={yCl} width="26" height={d.cl} rx="2" fill="#D97757" />
                          <rect x={x} y={yDs} width="26" height={d.ds} rx="3" fill="#4D6BFE" />
                          <text x={x + 13} y="164" textAnchor="middle" fontSize="9.5" fill="var(--ink-dim)" fontFamily="var(--font-mono)">
                            {d.label}
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </section>

                <section className="chart-card" aria-labelledby="donut-share-heading">
                  <div className="chart-card-head">
                    <div>
                      <h2 id="donut-share-heading">Token share by model</h2>
                      <p>Proportional distribution across active models</p>
                    </div>
                  </div>
                  <div className="donut-layout">
                    <svg width="140" height="140" viewBox="0 0 140 140" aria-label="Model share donut chart">
                      <circle cx="70" cy="70" r="50" fill="none" stroke="var(--navy-800)" strokeWidth="16" />
                      {summary.by_model.map((m, i) => {
                        const c = 2 * Math.PI * 50;
                        const seg = (m.share_pct / 100) * c;
                        const offset = c - (cumulativePct / 100) * c;
                        cumulativePct += m.share_pct;
                        return (
                          <circle
                            key={m.model}
                            cx="70"
                            cy="70"
                            r="50"
                            fill="none"
                            stroke={donutColors[i % donutColors.length]}
                            strokeWidth="16"
                            strokeDasharray={`${seg} ${c - seg}`}
                            strokeDashoffset={offset}
                            transform="rotate(-90 70 70)"
                          />
                        );
                      })}
                      <text x="70" y="67" textAnchor="middle" fill="var(--ink)" fontSize="13" fontWeight="800" fontFamily="var(--font-mono)">
                        {fmtInt(summary.total_tokens)}
                      </text>
                      <text x="70" y="82" textAnchor="middle" fill="var(--ink-dim)" fontSize="9" fontWeight="600">
                        TOTAL TOKENS
                      </text>
                    </svg>
                    <ul className="donut-legend">
                      {summary.by_model.map((m, i) => (
                        <li key={m.model}>
                          <span className="donut-legend-label">
                            <span
                              className="theme-swatch"
                              style={{ background: donutColors[i % donutColors.length] }}
                              aria-hidden="true"
                            />
                            <strong>{m.model}</strong>
                          </span>
                          <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>{m.share_pct}%</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </section>
              </div>

              <section className="panel" aria-labelledby="by-model-heading">
                <h2 id="by-model-heading">Usage breakdown by model</h2>
                {summary.by_model.length === 0 ? (
                  <p className="muted">No model usage recorded in this window yet.</p>
                ) : (
                  <Table
                    caption="Token and credit consumption by model"
                    head={[
                      "Model",
                      "Vendor",
                      "Requests",
                      "Input tokens",
                      "Output tokens",
                      "Total tokens",
                      "Cost (USD)",
                      "Share",
                    ]}
                  >
                    {summary.by_model.map((m) => (
                      <tr key={m.model}>
                        <td>
                          <div className="vendor-header">
                            <div className="vendor-mark sm">
                              <VendorLogo vendor={m.vendor} size={15} />
                            </div>
                            <code>{m.model}</code>
                          </div>
                        </td>
                        <td>{m.vendor}</td>
                        <td>{fmtInt(m.requests)}</td>
                        <td>{fmtInt(m.input_tokens)}</td>
                        <td>{fmtInt(m.output_tokens)}</td>
                        <td>{fmtInt(m.total_tokens)}</td>
                        <td>{summary.currency} {m.cost_usd}</td>
                        <td><ShareBar pct={m.share_pct} /></td>
                      </tr>
                    ))}
                  </Table>
                )}
              </section>

              <section className="panel" aria-labelledby="by-product-heading">
                <h2 id="by-product-heading">Usage breakdown by product / team subscription</h2>
                {summary.by_product.length === 0 ? (
                  <p className="muted">No product subscription usage recorded in this window yet.</p>
                ) : (
                  <Table
                    caption="Token consumption by product subscription"
                    head={[
                      "Product / Subscription",
                      "Team",
                      "Requests",
                      "Total tokens",
                      "Cost (USD)",
                      "Share",
                    ]}
                  >
                    {summary.by_product.map((p) => (
                      <tr key={p.subscription_id}>
                        <td><strong>{p.product_name}</strong></td>
                        <td>{p.team}</td>
                        <td>{fmtInt(p.requests)}</td>
                        <td>{fmtInt(p.total_tokens)}</td>
                        <td>{summary.currency} {p.cost_usd}</td>
                        <td><ShareBar pct={p.share_pct} /></td>
                      </tr>
                    ))}
                  </Table>
                )}
              </section>

              <section className="panel" aria-labelledby="by-channel-heading">
                <h2 id="by-channel-heading">Usage breakdown by channel</h2>
                {summary.by_channel.length === 0 ? (
                  <p className="muted">No channel activity recorded in this window yet.</p>
                ) : (
                  <Table
                    caption="Token consumption by invocation channel"
                    head={["Channel", "Requests", "Total tokens", "Cost (USD)", "Share"]}
                  >
                    {summary.by_channel.map((c) => (
                      <tr key={c.channel}>
                        <td><Badge tone="info">{c.channel}</Badge></td>
                        <td>{fmtInt(c.requests)}</td>
                        <td>{fmtInt(c.total_tokens)}</td>
                        <td>{summary.currency} {c.cost_usd}</td>
                        <td><ShareBar pct={c.share_pct} /></td>
                      </tr>
                    ))}
                  </Table>
                )}
              </section>
            </>
          );
        }}
      </AsyncView>
    </>
  );
}

export function CustomerKeysPage() {
  const { api, keys, setKey, clearKeys } = useSession();
  const [version, setVersion] = useState(0);
  const state = useAsync(() => api.subscriptions(0, 50), [api, version]);
  const [busyKey, setBusyKey] = useState<string>();
  const [notice, setNotice] = useState<{ tone: "ok" | "bad"; text: string }>();

  async function reveal(subId: string, key: KeyName) {
    setBusyKey(`reveal-${subId}-${key}`);
    setNotice(undefined);
    try {
      const secret = await api.revealKey(subId, key);
      setKey(subId, key, secret);
      setNotice({
        tone: "ok",
        text: `${key} key revealed in memory. Copy it or rotate it anytime.`,
      });
    } catch (err) {
      setNotice({
        tone: "bad",
        text: err instanceof ApiError ? err.detail : "Could not reveal subscription key.",
      });
    } finally {
      setBusyKey(undefined);
    }
  }

  async function rotate(subId: string, key: KeyName) {
    setBusyKey(`rotate-${subId}-${key}`);
    setNotice(undefined);
    try {
      await api.customerRotateKey(subId, key);
      clearKeys(subId);
      setVersion((v) => v + 1);
      setNotice({
        tone: "ok",
        text: `${key} key rotated successfully. Click Reveal to fetch the new key.`,
      });
    } catch (err) {
      setNotice({
        tone: "bad",
        text: err instanceof ApiError ? err.detail : "Could not rotate subscription key.",
      });
    } finally {
      setBusyKey(undefined);
    }
  }

  return (
    <>
      <PageHeader
        title="API keys & self-service rotation"
        subtitle="Reveal, copy, or rotate your OpCo team subscription keys without waiting for an administrator."
      />
      {notice && (
        <p role="status" className={`notice ${notice.tone === "bad" ? "bad" : ""}`}>
          {notice.text}
        </p>
      )}
      <AsyncView
        state={state}
        isEmpty={(d) => d.items.length === 0}
        emptyTitle="No subscriptions assigned"
        emptyHint="Ask your administrator to issue a subscription key for your team."
      >
        {(d) => (
          <ul className="keys-grid-list" aria-label="Customer subscription keys">
            {d.items.map((sub) => {
              const revealed = keys[sub.id] ?? {};
              return (
                <li className="key-subscription-card" key={sub.id}>
                  <div className="card-head">
                    <div className="vendor-header">
                      <div className="vendor-mark">🔑</div>
                      <div>
                        <h2 style={{ fontSize: "1.08rem" }}>{sub.name}</h2>
                        <p className="muted">
                          Team: <strong>{sub.team}</strong> · Subscription ID: <code>{sub.id.slice(0, 8)}…</code> · Issued {fmtDate(sub.created_at)}
                        </p>
                      </div>
                    </div>
                    <div className="actions">
                      <Badge tone="info">{sub.team}</Badge>
                      <StateBadge state={sub.state} />
                    </div>
                  </div>
                  <div className="key-slot-table">
                    {(["primary", "secondary"] as KeyName[]).map((k) => {
                      const val = revealed[k];
                      return (
                        <div key={k} className="key-slot-row">
                          <span className="key-slot-name">
                            <span className="theme-swatch" style={{ background: k === "primary" ? "var(--ok)" : "var(--info)" }} />
                            {k} key
                          </span>
                          <div className="key-slot-secret">
                            {val ? (
                              <code aria-label={`${k} key value`} style={{ border: 0, background: "transparent", padding: 0 }}>{val}</code>
                            ) : (
                              <span>••••••••••••••••••••••••</span>
                            )}
                          </div>
                          <div className="key-slot-actions">
                            {val ? (
                              <>
                                <button
                                  className="btn"
                                  onClick={() => void navigator.clipboard?.writeText(val)}
                                  type="button"
                                >
                                  Copy
                                </button>
                                <button
                                  className="btn"
                                  onClick={() => clearKeys(sub.id)}
                                  type="button"
                                >
                                  Hide
                                </button>
                              </>
                            ) : (
                              <button
                                className="btn primary"
                                disabled={sub.state !== "active" || Boolean(busyKey)}
                                onClick={() => void reveal(sub.id, k)}
                                type="button"
                              >
                                Reveal {k}
                              </button>
                            )}
                            <button
                              className="btn"
                              disabled={sub.state !== "active" || Boolean(busyKey)}
                              onClick={() => void rotate(sub.id, k)}
                              type="button"
                            >
                              Rotate {k}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </AsyncView>
    </>
  );
}

export function AdminBudgetsAndFinOpsPage() {
  const { api } = useSession();
  const [version, setVersion] = useState(0);
  const budgets = useAsync(() => api.adminBudgets(), [api, version]);
  const [selectedOrg, setSelectedOrg] = useState("");
  const [monthlyUsd, setMonthlyUsd] = useState("5000.00");
  const [credits, setCredits] = useState("5000.00");
  const [alertPct, setAlertPct] = useState(80);
  const [allowedModels, setAllowedModels] = useState("*");
  const [hardStop, setHardStop] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string>();
  const [saveErr, setSaveErr] = useState<string>();

  function selectBudget(b: CreditBudget) {
    setSelectedOrg(b.organization_id);
    setMonthlyUsd(b.monthly_budget_usd);
    setCredits(b.credit_allocation);
    setAlertPct(b.alert_threshold_pct);
    setAllowedModels(b.allowed_models.join(", "));
    setHardStop(b.hard_stop_enabled);
  }

  async function saveBudget(e: FormEvent) {
    e.preventDefault();
    if (!selectedOrg) return;
    setSaving(true);
    setSaveErr(undefined);
    setSaveMsg(undefined);
    try {
      const models = allowedModels
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const updated = await api.saveAdminBudget(selectedOrg, {
        monthly_budget_usd: monthlyUsd,
        credit_allocation: credits,
        alert_threshold_pct: alertPct,
        allowed_models: models.length ? models : ["*"],
        product_name: "Enterprise AI Token Exchange",
        channel: "api-gateway",
        hard_stop_enabled: hardStop,
      });
      setSaveMsg(
        `Saved budget for ${updated.organization_name} and projected row '${updated.ledger_row_key}' to TurnstileLedger.`,
      );
      setVersion((v) => v + 1);
    } catch (err) {
      setSaveErr(err instanceof ApiError ? err.detail : "Failed to update budget.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="OpCo credit budgets & FinOps ledger"
        subtitle="Allocate monthly token credits, configure low-credit alert thresholds, restrict model allowlists, and project limits to TurnstileLedger Azure Table Storage."
      />
      {saveErr && <ErrorState message={saveErr} />}
      {saveMsg && (
        <p role="status" className="notice">
          {saveMsg}
        </p>
      )}
      <AsyncView state={budgets}>
        {(d) => (
          <>
            <Table
              caption="Organization credit allocations and utilization"
              head={[
                "Organization (OpCo)",
                "Allocated Credits",
                "Used",
                "Remaining",
                "Utilization",
                "Allowed Models",
                "Ledger Key",
                "Action",
              ]}
            >
              {d.items.map((b) => (
                <tr key={b.id}>
                  <td>{b.organization_name}</td>
                  <td>USD {b.credit_allocation}</td>
                  <td>USD {b.used_credits}</td>
                  <td>USD {b.remaining_credits}</td>
                  <td>
                    <Badge tone={b.low_credit_alert ? "bad" : "ok"}>
                      {b.utilization_pct}% (alert @ {b.alert_threshold_pct}%)
                    </Badge>
                  </td>
                  <td><code>{b.allowed_models.join(", ")}</code></td>
                  <td><code>{b.ledger_row_key}</code></td>
                  <td>
                    <button
                      className="btn"
                      type="button"
                      onClick={() => selectBudget(b)}
                    >
                      Configure
                    </button>
                  </td>
                </tr>
              ))}
            </Table>

            <section className="panel" aria-labelledby="edit-budget-heading">
              <h2 id="edit-budget-heading">Update OpCo credit allocation & model allowlist</h2>
              <form onSubmit={(e) => void saveBudget(e)} className="form-row">
                <Field label="Organization">
                  {(id) => (
                    <select
                      id={id}
                      value={selectedOrg}
                      onChange={(e) => {
                        const found = d.items.find((x) => x.organization_id === e.target.value);
                        if (found) selectBudget(found);
                        else setSelectedOrg(e.target.value);
                      }}
                      required
                    >
                      <option value="">Select an OpCo…</option>
                      {d.items.map((b) => (
                        <option key={b.organization_id} value={b.organization_id}>
                          {b.organization_name}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="Credit allocation (USD)">
                  {(id) => (
                    <input
                      id={id}
                      value={credits}
                      onChange={(e) => {
                        setCredits(e.target.value);
                        setMonthlyUsd(e.target.value);
                      }}
                      required
                    />
                  )}
                </Field>
                <Field label="Alert threshold (%)">
                  {(id) => (
                    <input
                      id={id}
                      type="number"
                      min={1}
                      max={100}
                      value={alertPct}
                      onChange={(e) => setAlertPct(Number(e.target.value))}
                      required
                    />
                  )}
                </Field>
                <Field label="Allowed models (comma-separated or *)">
                  {(id) => (
                    <input
                      id={id}
                      value={allowedModels}
                      onChange={(e) => setAllowedModels(e.target.value)}
                      required
                    />
                  )}
                </Field>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={hardStop}
                    onChange={(e) => setHardStop(e.target.checked)}
                  />{" "}
                  Enforce hard stop at 100% credit usage in APIM
                </label>
                <button className="btn primary" disabled={!selectedOrg || saving}>
                  {saving ? "Saving…" : "Save & Sync to TurnstileLedger"}
                </button>
              </form>
            </section>
          </>
        )}
      </AsyncView>
    </>
  );
}

export function AdminModelRouterPage() {
  const { api } = useSession();
  const [version, setVersion] = useState(0);
  const routerState = useAsync(() => api.adminModelRouter(), [api, version]);
  const gardenState = useAsync(() => api.adminModelGarden(), [api, version]);
  const policyState = useAsync(() => api.turnstilePolicyPreview(), [api, version]);
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<string>();
  const [endpointInput, setEndpointInput] = useState<Record<string, string>>({});

  async function changeStrategy(nextStrategy: RouterStrategy) {
    if (!routerState.data) return;
    setError(undefined);
    setNotice(undefined);
    try {
      await api.saveAdminModelRouter({
        enabled: routerState.data.enabled,
        strategy: nextStrategy,
        decision_endpoint: routerState.data.decision_endpoint,
        default_model: routerState.data.default_model,
        candidate_models: routerState.data.candidate_models,
        rules: routerState.data.rules,
      });
      setNotice(`Updated Microsoft Decision-1 router strategy to '${nextStrategy}'.`);
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not update model router.");
    }
  }

  async function toggleModelEndpoint(item: ModelGardenItem) {
    setError(undefined);
    setNotice(undefined);
    try {
      const nextUrl = endpointInput[item.id] ?? item.endpoint_url;
      const enabling = !item.enabled || item.coming_soon;
      const updated = await api.saveModelGardenItem({
        ...item,
        endpoint_url: nextUrl,
        enabled: enabling,
        coming_soon: false,
      });
      setNotice(
        `${updated.display_name} (${updated.id}) is now ${updated.enabled ? "Active" : "Disabled"} and synced to ModelRoutes.`,
      );
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not update model endpoint.");
    }
  }

  return (
    <>
      <PageHeader
        title="Model router (Decision-1) & Model Garden endpoints"
        subtitle="Configure Microsoft Decision-1 (model = auto) routing rules, onboard OpenAI, Claude, DeepSeek, Singtel RE:AI, and Gemini endpoints, and inspect the compiled APIM policy."
      />
      {error && <ErrorState message={error} />}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <AsyncView state={routerState}>
        {(cfg) => (
          <section className="panel" aria-labelledby="router-cfg-heading">
            <h2 id="router-cfg-heading">Microsoft Decision-1 auto-router configuration</h2>
            <dl className="stats">
              <div>
                <dt>Status</dt>
                <dd>
                  <Badge tone={cfg.enabled ? "ok" : "warn"}>
                    {cfg.enabled ? "Enabled (model = auto)" : "Disabled"}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt>Decision endpoint</dt>
                <dd>
                  <code>{cfg.decision_endpoint}</code>
                </dd>
              </div>
              <div>
                <dt>Default fallback model</dt>
                <dd>
                  <code>{cfg.default_model}</code>
                </dd>
              </div>
              <div>
                <dt>Active strategy</dt>
                <dd>
                  <select
                    aria-label="Active router strategy"
                    value={cfg.strategy}
                    onChange={(e) => void changeStrategy(e.target.value as RouterStrategy)}
                  >
                    <option value="microsoft-decision-1">microsoft-decision-1</option>
                    <option value="cost-optimized">cost-optimized</option>
                    <option value="latency-optimized">latency-optimized</option>
                    <option value="quality-first">quality-first</option>
                  </select>
                </dd>
              </div>
            </dl>
            <Table
              caption="Decision-1 intent routing rules"
              head={["Category", "Description", "Preferred model", "Fallback model", "Signal keywords"]}
            >
              {cfg.rules.map((r) => (
                <tr key={r.category}>
                  <td><code>{r.category}</code></td>
                  <td>{r.description}</td>
                  <td><Badge tone="ok">{r.preferred_model}</Badge></td>
                  <td><code>{r.fallback_model}</code></td>
                  <td>{r.keywords.slice(0, 6).join(", ")}</td>
                </tr>
              ))}
            </Table>
          </section>
        )}
      </AsyncView>

      <AsyncView state={gardenState}>
        {(garden) => (
          <section className="panel" aria-labelledby="garden-endpoints-heading">
            <h2 id="garden-endpoints-heading">
              Model Garden provider endpoints (OpenAI, Claude, DeepSeek, Singtel RE:AI, Gemini)
            </h2>
            <Table
              caption="Managed model endpoints and pricing"
              head={[
                "Model ID",
                "Display name",
                "Vendor",
                "Input / Output ($/1M)",
                "Endpoint URL",
                "Status",
                "Action",
              ]}
            >
              {garden.items.map((m) => (
                <tr key={m.id}>
                  <td>
                    <div className="vendor-header">
                      <div className="vendor-mark sm">
                        <VendorLogo vendor={m.vendor} size={15} />
                      </div>
                      <code>{m.id}</code>
                    </div>
                  </td>
                  <td><strong>{m.display_name}</strong></td>
                  <td>{m.vendor}</td>
                  <td style={{ fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
                    ${m.input_per_million} / ${m.output_per_million}
                  </td>
                  <td>
                    <input
                      aria-label={`Endpoint URL for ${m.id}`}
                      value={endpointInput[m.id] ?? m.endpoint_url}
                      placeholder="https://endpoint/v1/chat/completions"
                      onChange={(e) =>
                        setEndpointInput((prev) => ({ ...prev, [m.id]: e.target.value }))
                      }
                    />
                  </td>
                  <td>
                    {m.coming_soon ? (
                      <Badge tone="warn">Coming soon</Badge>
                    ) : m.enabled ? (
                      <Badge tone="ok">Active</Badge>
                    ) : (
                      <Badge tone="bad">Disabled</Badge>
                    )}
                  </td>
                  <td>
                    <button
                      className={m.coming_soon || !m.enabled ? "btn primary" : "btn"}
                      style={{ whiteSpace: "nowrap" }}
                      type="button"
                      aria-label={m.coming_soon || !m.enabled ? `Activate ${m.id}` : `Disable ${m.id}`}
                      onClick={() => void toggleModelEndpoint(m)}
                    >
                      {m.coming_soon || !m.enabled ? "Activate" : "Disable"}
                    </button>
                  </td>
                </tr>
              ))}
            </Table>
          </section>
        )}
      </AsyncView>

      <AsyncView state={policyState}>
        {(preview) => (
          <section className="panel" aria-labelledby="policy-preview-heading">
            <h2 id="policy-preview-heading">
              Compiled Turnstile + AIFLUX APIM policy (TurnstileLedger + Content Safety + Decision-1)
            </h2>
            <p className="muted">
              Storage account: <code>{preview.ledger_storage_account}</code> · Ledger table:{" "}
              <code>{preview.ledger_table_name}</code> · Routes table:{" "}
              <code>{preview.model_routes_table_name}</code>
            </p>
            <pre className="code-block">
              <code>{preview.policy_xml}</code>
            </pre>
          </section>
        )}
      </AsyncView>
    </>
  );
}

export function AdminLocalUsersPage() {
  const { api } = useSession();
  const [version, setVersion] = useState(0);
  const usersState = useAsync(() => api.localUsers(), [api, version]);
  const orgsState = useAsync(() => api.organizations(), [api]);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [role, setRole] = useState<Role>("customer");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<string>();

  async function createUser(e: FormEvent) {
    e.preventDefault();
    if (!organizationId) return;
    setBusy(true);
    setError(undefined);
    setNotice(undefined);
    try {
      const created = await api.createLocalUser({
        email: email.trim(),
        password,
        display_name: displayName.trim(),
        organization_id: organizationId,
        role,
      });
      setNotice(`Created PostgreSQL user '${created.email}' for ${created.organization_name}.`);
      setEmail("");
      setDisplayName("");
      setPassword("");
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not create user.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleUser(u: LocalUserItem) {
    setError(undefined);
    setNotice(undefined);
    try {
      const updated = await api.updateLocalUser(u.id, { enabled: !u.enabled });
      setNotice(`User '${updated.email}' is now ${updated.enabled ? "enabled" : "disabled"}.`);
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not update user.");
    }
  }

  return (
    <>
      <PageHeader
        title="Local users (PostgreSQL)"
        subtitle="Manage email & password accounts stored in PostgreSQL (local_users) for OpCo customers and platform administrators."
      />
      {error && <ErrorState message={error} />}
      {notice && <p role="status" className="notice">{notice}</p>}
      <AsyncView state={orgsState}>
        {(orgs) => (
          <section className="panel" aria-labelledby="new-local-user-heading">
            <h2 id="new-local-user-heading">Create PostgreSQL user account</h2>
            <form onSubmit={(e) => void createUser(e)} className="form-row">
              <Field label="Organization (OpCo)">
                {(id) => (
                  <select id={id} value={organizationId} onChange={(e) => setOrganizationId(e.target.value)} required>
                    <option value="">Select organization…</option>
                    {orgs.items.map((o) => (
                      <option key={o.id} value={o.id}>{o.name}</option>
                    ))}
                  </select>
                )}
              </Field>
              <Field label="Display name">
                {(id) => <input id={id} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />}
              </Field>
              <Field label="Email">
                {(id) => <input id={id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}
              </Field>
              <Field label="Initial password">
                {(id) => <input id={id} type="password" minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} required />}
              </Field>
              <Field label="Role">
                {(id) => (
                  <select id={id} value={role} onChange={(e) => setRole(e.target.value as Role)}>
                    <option value="customer">customer (OpCo portal)</option>
                    <option value="ids_admin">ids_admin (Admin portal)</option>
                  </select>
                )}
              </Field>
              <button className="btn primary" disabled={busy || !organizationId}>
                {busy ? "Creating…" : "Create PostgreSQL user"}
              </button>
            </form>
          </section>
        )}
      </AsyncView>
      <AsyncView state={usersState}>
        {(data) => (
          <Table
            caption="PostgreSQL local user accounts"
            head={["Email", "Display name", "Organization", "Role", "Status", "Created", "Action"]}
          >
            {data.items.map((u) => (
              <tr key={u.id}>
                <td><code>{u.email}</code></td>
                <td>{u.display_name}</td>
                <td>{u.organization_name}</td>
                <td><Badge tone={u.role === "ids_admin" ? "info" : "neutral"}>{u.role}</Badge></td>
                <td><Badge tone={u.enabled ? "ok" : "bad"}>{u.enabled ? "Enabled" : "Disabled"}</Badge></td>
                <td>{fmtDate(u.created_at)}</td>
                <td>
                  <button className="btn" type="button" onClick={() => void toggleUser(u)}>
                    {u.enabled ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </AsyncView>
    </>
  );
}
