import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DeletionDialog } from "../components/DeletionDialog";
import { VendorLogo } from "../components/VendorLogo";
import { ApiError } from "../client";
import { DeploymentStatus } from "../components/DeploymentStatus";
import { CustomerMonthlyBudgetCard } from "../components/MonthlyBudget";
import { DisplayPriceDetails, estimateMoney, EstimateCoverage } from "../components/DisplayPrice";
import { useSession } from "../session";
import { customerModelPresentation, isCatalogDeployed } from "../modelPresentation";
import type {
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

  return (
    <>
      <PageHeader
        title="Model catalog & pricing"
        subtitle="Accepted chat routes through the development gateway. Redacted external input leaves Azure; redaction is best-effort, not anonymization. Decision-1 is routing-only. Sourced public prices are estimates, not invoices."
      />
      <AsyncView
        state={state}
        isEmpty={(d) => d.items.length === 0}
        emptyTitle="No models in catalog"
        emptyHint="Contact your platform administrator to publish model endpoints."
      >
        {(d) => {
          const vendors = Array.from(new Set(d.items.map((m) => m.vendor)));
          const deployedCount = d.items.filter(isCatalogDeployed).length;
          const onboardingCount = d.items.length - deployedCount;
          const byStatus = d.items.filter((m) => {
            if (statusTab === "deployed") return isCatalogDeployed(m);
            if (statusTab === "onboarding") return !isCatalogDeployed(m);
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
                {visible.map((m) => {
                  const scoring = m.model_kind === "scoring";
                  const inputOnly = m.display_price?.billing_dimensions?.length === 1 && m.display_price.billing_dimensions[0] === "input";
                  return (
                  <li className="card" key={m.id}>
                    <div className="card-head">
                      <div className="vendor-header">
                        <div className="vendor-mark">
                          <VendorLogo vendor={m.vendor} size={22} />
                        </div>
                        <div>
                          <h2>{customerModelPresentation(m).displayName}</h2>
                          <p className="muted">
                            <code>{m.id}</code> · {m.vendor} · {m.region}
                          </p>
                        </div>
                      </div>
                      {scoring ? (
                        <Badge tone={m.scoring_available === true ? "ok" : m.scoring_available === false ? "warn" : "neutral"}>
                          {m.scoring_available === true ? "Scoring available" : m.scoring_available === false ? "Scoring unavailable" : "Scoring availability unverified"}
                        </Badge>
                      ) : m.coming_soon ? (
                        <Badge tone="warn">{m.capabilities.includes("routing-only") ? "Routing-only · integration unavailable" : "Coming soon"}</Badge>
                      ) : m.id === "auto" ? (
                        <Badge tone="info">Auto Router</Badge>
                      ) : (
                        <Badge tone="ok">Active</Badge>
                      )}
                    </div>
                    <p>{customerModelPresentation(m).description}</p>
                    <dl className="pricing-strip">
                      <div className="pricing-cell">
                        <dt>Input / 1M tokens</dt>
                        <dd>
                          {m.display_price ? `USD ${m.display_price.input}${m.display_price.status === "tbc" ? " · TBC" : ""}` : "Unknown — not free"}
                        </dd>
                      </div>
                      <div className="pricing-cell">
                        <dt>Output / 1M tokens</dt>
                        <dd>
                          {inputOnly ? "N/A" : m.display_price?.output != null ? `USD ${m.display_price.output}${m.display_price.status === "tbc" ? " · TBC" : ""}` : "Unknown — not free"}
                        </dd>
                      </div>
                      <div className="pricing-cell">
                        <dt>Cached input / 1M</dt>
                        <dd>
                          {inputOnly ? "N/A" : m.display_price?.cached != null ? `USD ${m.display_price.cached}` : "Unknown"}
                        </dd>
                      </div>
                    </dl>
                    <DisplayPriceDetails price={m.display_price} />
                    <div className="card-meta-row">
                      <span>{scoring ? "Published model context (not deployment verification)" : "Context / Max output"}</span>
                      <strong>
                        {scoring ? (m.context_window != null ? fmtInt(m.context_window) : /^(microsoft-)?decision-1$/i.test(m.id) ? fmtInt(32768) : "Unverified") : <>Unverified / {fmtInt(m.max_completion_tokens)}</>}
                      </strong>
                    </div>
                    <div className="badges">
                      {scoring && <Badge tone="info">Scoring-only · Used by Auto</Badge>}
                      {m.content_safety_enabled && (
                        <Badge tone="ok">Foundry Content Safety</Badge>
                      )}
                      {m.capabilities.map((cap) => (
                        <Badge key={cap} tone="info">
                          {cap}
                        </Badge>
                      ))}
                    </div>
                    {!scoring && !m.coming_soon && m.enabled && m.capabilities.includes("chat") && (
                      <div className="actions" style={{ marginTop: "auto", paddingTop: "0.4rem" }}>
                        <Link className="btn primary" style={{ width: "100%" }} to={`/playground?model=${encodeURIComponent(m.id)}`}>
                          Try in Playground →
                        </Link>
                      </div>
                    )}
                  </li>
                  );
                })}
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
    <div className="customer-overview-page">
      <PageHeader
        title="Overview & external estimated costs"
        subtitle="Measured requests and tokens with external price estimates by model, subscription and channel. Estimates are not invoices; missing prices are unknown, not free."
        actions={
          <div className="actions">
            <Link className="btn" to="/keys">Manage API Keys</Link>
            <Link className="btn primary" to="/playground">Open Playground →</Link>
          </div>
        }
      />
      <CustomerMonthlyBudgetCard overview />
      <div className="overview-usage-toolbar">
        <div><h2>Usage activity</h2><p className="muted">Selected reporting window · separate from the UTC month budget</p></div>
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
          const donutColors = ["#4D6BFE", "#D97757", "#10a37f", "#8b5cf6"];
          let cumulativePct = 0;

          return (
            <>
              <Badge tone="info">{summary.organization_name}</Badge>
              <dl className="overview-usage-kpis" aria-label="Usage summary">
                <div className="bento-card">
                  <dt className="bento-label">External estimated cost ({days}d)</dt>
                  <dd className="bento-value">{estimateMoney(summary.estimated_cost_usd)}</dd>
                  <dd className="bento-sub">External prices · not an invoice</dd>
                </div>
                <div className="bento-card">
                  <dt className="bento-label">Requests ({days}d)</dt>
                  <dd className="bento-value">{fmtInt(summary.total_requests)}</dd>
                  <dd className="bento-sub">Measured requests</dd>
                </div>
                <div className="bento-card">
                  <div className="bento-top">
                    <dt className="bento-label">Tokens ({days}d)</dt>
                  </div>
                  <dd className="bento-value" style={{ margin: 0 }}>
                    {fmtInt(summary.total_tokens)}
                  </dd>
                  <dd className="bento-sub">Measured input + output tokens</dd>
                </div>
              </dl>
              <details className="overview-disclosure overview-usage-coverage">
                <summary>Selected-window estimate coverage · {summary.unestimated_requests ?? "Unknown"} unestimated request(s)</summary>
                <p>Measured usage estimated at your organization's effective external prices. Not a credit balance or invoice.</p>
                <EstimateCoverage estimate={summary} />
              </details>

              <div className="visual-analytics-grid" aria-label="Visual token consumption charts">
                <section className="chart-card" aria-labelledby="donut-share-heading">
                  <div className="chart-card-head">
                    <div>
                      <h2 id="donut-share-heading">Token share by model</h2>
                      <p>Measured tokens in the selected {days}-day reporting window; independent of the current UTC month budget above.</p>
                    </div>
                  </div>
                  {summary.by_model.length === 0 ? <p className="muted">No model token share recorded in this window yet.</p> : <div className="donut-layout">
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
                          <span className="overview-model-share">{m.share_pct}%<small>{fmtInt(m.total_tokens)} tokens</small></span>
                        </li>
                      ))}
                    </ul>
                  </div>}
                </section>
              </div>

              <section className="panel" aria-labelledby="by-model-heading">
                <h2 id="by-model-heading">Usage breakdown by model</h2>
                {summary.by_model.length === 0 ? (
                  <p className="muted">No model usage recorded in this window yet.</p>
                ) : (
                  <Table
                    caption="Tokens and external estimates by model"
                    head={[
                      "Model",
                      "Vendor",
                      "Requests",
                      "Input tokens",
                      "Output tokens",
                      "Total tokens",
                      "External estimated cost (USD)",
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
                        <td>{estimateMoney(m.estimated_cost_usd)}<small className="block">{m.unestimated_requests ?? "Unknown"} unestimated</small></td>
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
                      "External estimated cost (USD)",
                      "Share",
                    ]}
                  >
                    {summary.by_product.map((p) => (
                      <tr key={p.subscription_id}>
                        <td><strong>{p.product_name}</strong></td>
                        <td>{p.team}</td>
                        <td>{fmtInt(p.requests)}</td>
                        <td>{fmtInt(p.total_tokens)}</td>
                        <td>{estimateMoney(p.estimated_cost_usd)}<small className="block">{p.unestimated_requests ?? "Unknown"} unestimated</small></td>
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
                    head={["Channel", "Requests", "Total tokens", "External estimated cost (USD)", "Share"]}
                  >
                    {summary.by_channel.map((c) => (
                      <tr key={c.channel}>
                        <td><Badge tone="info">{c.channel}</Badge></td>
                        <td>{fmtInt(c.requests)}</td>
                        <td>{fmtInt(c.total_tokens)}</td>
                        <td>{estimateMoney(c.estimated_cost_usd)}<small className="block">{c.unestimated_requests ?? "Unknown"} unestimated</small></td>
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
    </div>
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

// Keep the existing route/export without retaining the legacy enforcement editor.
export { MonthlyBudgetsPage as AdminBudgetsAndFinOpsPage } from "./MonthlyBudgetsPage";

const STRATEGY_PROFILES: Record<
  RouterStrategy,
  {
    title: string;
    badge: string;
    tone: "info" | "ok" | "warn" | "neutral";
    summary: string;
    sla: string;
    matrix: {
      category: string;
      description: string;
      preferred_model: string;
      fallback_model: string;
      target_metric: string;
    }[];
  }
> = {
  "microsoft-decision-1": {
    title: "Microsoft Decision-1 (Balanced Intent)",
    badge: "Default · SystemOne",
    tone: "info",
    summary:
      "Classifies prompt domain and complexity via /providers/microsoft/v1/systemone and dispatches each workload to its best-fit specialist model.",
    sla: "Avg Savings: ~42% · Avg TTFT: ~190ms",
    matrix: [
      {
        category: "coding_and_math",
        description: "Code generation, debugging, SQL, algorithms, and quantitative math problems",
        preferred_model: "DeepSeek-V3.2-Speciale",
        fallback_model: "gpt-5.4",
        target_metric: "$0.27 / $1.10 per 1M · High reasoning accuracy",
      },
      {
        category: "long_context_and_writing",
        description: "Executive memos, policy drafting, contract review, and long-document synthesis",
        preferred_model: "claude-sonnet-4-5",
        fallback_model: "gpt-5.4",
        target_metric: "200K context · Nuanced enterprise prose",
      },
      {
        category: "complex_architecture",
        description: "Multi-step system architecture, strategic planning, and deep reasoning",
        preferred_model: "gpt-5.4",
        fallback_model: "claude-sonnet-4-5",
        target_metric: "256K context · Frontier multi-step synthesis",
      },
      {
        category: "fast_general_qa",
        description: "High-speed Q&A, classification, extraction, and conversational queries",
        preferred_model: "gpt-5.4-mini",
        fallback_model: "claude-haiku-4-5",
        target_metric: "~85ms TTFT · $0.30 / $1.20 per 1M",
      },
    ],
  },
  "cost-optimized": {
    title: "Cost-Optimized (Minimum Token Spend)",
    badge: "Up to 85% Cost Reduction",
    tone: "ok",
    summary:
      "Enforces a strict cost floor by routing every intent category to the lowest-price model capable of passing quality guardrails, avoiding $10–$15/1M flagship models.",
    sla: "Target Spend: <$0.45 / 1M blended · Zero reasoning-token waste on simple Q&A",
    matrix: [
      {
        category: "cost_optimized_coding",
        description: "Coding, SQL, regex, Dockerfile, and quantitative logic",
        preferred_model: "DeepSeek-V3.2-Speciale",
        fallback_model: "gpt-5.4-mini",
        target_metric: "$0.27 in / $1.10 out (Saves 89% vs GPT-5.4 Flagship)",
      },
      {
        category: "cost_optimized_writing",
        description: "Document summarization, drafting, policy review, and long context",
        preferred_model: "claude-haiku-4-5",
        fallback_model: "gpt-5.4-mini",
        target_metric: "$0.80 in / $4.00 out (Saves 73% vs Claude Sonnet 4.5)",
      },
      {
        category: "cost_optimized_general",
        description: "General Q&A, classification, extraction, and standard chat",
        preferred_model: "gpt-5.4-mini",
        fallback_model: "DeepSeek-V3.2-Speciale",
        target_metric: "$0.30 in / $1.20 out (Zero  <think> token overhead)",
      },
    ],
  },
  "latency-optimized": {
    title: "Latency-Optimized (Sub-300ms Real-Time TTFT)",
    badge: "Lowest TTFT & E2E",
    tone: "warn",
    summary:
      "Prioritizes ultra-low Time-To-First-Token (TTFT) and high streaming throughput (>140 tok/s) for voice agents, live chat, and inline autocomplete — bypassing multi-second  <think> reasoning chains.",
    sla: "Target TTFT: 80–110ms · Target E2E: <320ms",
    matrix: [
      {
        category: "latency_optimized_ttft",
        description: "Interactive chat, tool calling, code completion, and real-time copilot turns",
        preferred_model: "gpt-5.4-mini",
        fallback_model: "claude-haiku-4-5",
        target_metric: "~85ms TTFT · ~260ms E2E (Bypasses DeepSeek  <think> delay)",
      },
      {
        category: "latency_optimized_stream",
        description: "High-speed document summarization, translation, and multi-turn drafting",
        preferred_model: "claude-haiku-4-5",
        fallback_model: "gpt-5.4-mini",
        target_metric: "~95ms TTFT · >140 tokens/sec streaming",
      },
    ],
  },
  "quality-first": {
    title: "Quality-First (Frontier Flagship Maximization)",
    badge: "Max Accuracy",
    tone: "neutral",
    summary:
      "Routes every prompt to the highest-benchmark frontier flagship model for that domain regardless of token cost or latency.",
    sla: "Target Models: GPT-5.4 Flagship & Claude Sonnet 4.5",
    matrix: [
      {
        category: "quality_first_reasoning",
        description: "Complex architecture, code synthesis, and multi-step reasoning",
        preferred_model: "gpt-5.4",
        fallback_model: "claude-sonnet-4-5",
        target_metric: "$2.50 in / $10.00 out · Maximum reasoning benchmark",
      },
      {
        category: "quality_first_writing",
        description: "Executive contracts, compliance analysis, and long-horizon writing",
        preferred_model: "claude-sonnet-4-5",
        fallback_model: "gpt-5.4",
        target_metric: "$3.00 in / $15.00 out · Highest prose & nuance score",
      },
    ],
  },
};

export { AdminAutoRouterPage as AdminModelRouterPage } from "./AdminAutoRouterPage";

// Retained only as explicitly named legacy metadata/simulator UI; not the live admin route.
export function LegacyModelRouterMetadataPage() {
  const { api } = useSession();
  const [version, setVersion] = useState(0);
  const routerState = useAsync(() => api.adminModelRouter(), [api, version]);
  const gardenState = useAsync(() => api.adminModelGarden(), [api, version]);
  const policyState = useAsync(() => api.turnstilePolicyPreview(), [api, version]);
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<string>();
  const [endpointInput, setEndpointInput] = useState<Record<string, string>>({});
  const [simPrompt, setSimPrompt] = useState(
    "Write a Python SQL migration script and Dockerfile for our token ledger.",
  );
  const [simResults, setSimResults] = useState<Record<string, RouterDecision> | null>(null);
  const [simBusy, setSimBusy] = useState(false);

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
      setNotice(`Saved router configuration '${nextStrategy}'. This does not deploy APIM routes or verify Decision-1 inference.`);
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not update model router.");
    }
  }

  async function compareAllStrategies(e: FormEvent) {
    e.preventDefault();
    if (!simPrompt.trim()) return;
    setSimBusy(true);
    setError(undefined);
    try {
      const strategies: RouterStrategy[] = [
        "microsoft-decision-1",
        "cost-optimized",
        "latency-optimized",
        "quality-first",
      ];
      const entries = await Promise.all(
        strategies.map(async (s) => [s, await api.decideModelRoute(simPrompt.trim(), s)] as const),
      );
      setSimResults(Object.fromEntries(entries));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not run strategy comparison.");
    } finally {
      setSimBusy(false);
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
        `${updated.display_name} (${updated.id}) metadata saved. This does not publish gateway routes.`,
      );
      setVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not update model endpoint.");
    }
  }

  return (
    <>
      <PageHeader
        title="Model router (Decision-1) & Model Catalog endpoints"
        subtitle="Manage model metadata. Database edits do not publish APIM routes; the keyword simulator is not Decision-1 inference."
      />
      <DeploymentStatus />
      {error && <ErrorState message={error} />}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <AsyncView state={routerState}>
        {(cfg) => {
          const activeProfile = STRATEGY_PROFILES[cfg.strategy] ?? STRATEGY_PROFILES["microsoft-decision-1"];
          return (
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
                      <option value="microsoft-decision-1">microsoft-decision-1 (Balanced Intent)</option>
                      <option value="cost-optimized">cost-optimized (Min Spend)</option>
                      <option value="latency-optimized">latency-optimized (Sub-300ms TTFT)</option>
                      <option value="quality-first">quality-first (Frontier Flagship)</option>
                    </select>
                  </dd>
                </div>
              </dl>

              <div className="bento-grid" aria-label="Decision-1 routing strategy profiles">
                {(Object.keys(STRATEGY_PROFILES) as RouterStrategy[]).map((sKey) => {
                  const prof = STRATEGY_PROFILES[sKey];
                  const isCurrent = cfg.strategy === sKey;
                  return (
                    <div
                      key={sKey}
                      className="bento-card"
                      style={{
                        cursor: "pointer",
                        borderColor: isCurrent ? "var(--teal-500)" : undefined,
                        background: isCurrent ? "var(--brand-soft)" : undefined,
                      }}
                      onClick={() => void changeStrategy(sKey)}
                    >
                      <div className="bento-top">
                        <span className="bento-label">{sKey}</span>
                        <Badge tone={isCurrent ? "info" : prof.tone}>
                          {isCurrent ? "Configured strategy · not verified inference" : "Not verified"}
                        </Badge>
                      </div>
                      <strong style={{ fontSize: "0.92rem" }}>{prof.title}</strong>
                      <p className="muted" style={{ margin: 0, fontSize: "0.78rem" }}>
                        Strategy configuration only. Actual Decision-1 inference, price optimization and latency targets have not been verified.
                      </p>
                      <span className="bento-sub" style={{ marginTop: "auto", paddingTop: "0.35rem", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                        No verified price, latency or savings guarantee.
                      </span>
                    </div>
                  );
                })}
              </div>

              <h2 style={{ marginTop: "0.5rem" }}>
                Active routing behavior: {activeProfile.title}
              </h2>
              <Table
                caption="Decision-1 routing policy matrix"
                head={[
                  "Route Category",
                  "Workload & Prompt Signals",
                  "Primary Target Model",
                  "Fallback Model",
                  "Cost / Latency Profile",
                ]}
              >
                {activeProfile.matrix.map((r) => (
                  <tr key={r.category}>
                    <td><code>{r.category}</code></td>
                    <td>{r.description}</td>
                    <td><Badge tone="ok">{r.preferred_model}</Badge></td>
                    <td><code>{r.fallback_model}</code></td>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem" }}>{r.target_metric}</td>
                  </tr>
                ))}
              </Table>

              <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--line)" }}>
                <h2>Compare all 4 routing strategies side-by-side</h2>
                <form onSubmit={(e) => void compareAllStrategies(e)} className="form-row">
                  <Field label="Test prompt across all 4 strategies">
                    {(id) => (
                      <input
                        id={id}
                        value={simPrompt}
                        onChange={(e) => setSimPrompt(e.target.value)}
                        required
                      />
                    )}
                  </Field>
                  <button className="btn primary" type="submit" disabled={simBusy}>
                    {simBusy ? "Comparing…" : "Compare 4 Strategies"}
                  </button>
                </form>
                {simResults && (
                  <Table
                    caption="Side-by-side strategy comparison"
                    head={["Strategy", "Selected Model", "Vendor", "Category", "Est. Input / Output ($/1M)", "Decision-1 Rationale"]}
                  >
                    {(["microsoft-decision-1", "cost-optimized", "latency-optimized", "quality-first"] as RouterStrategy[]).map((sKey) => {
                      const d = simResults[sKey];
                      if (!d) return null;
                      return (
                        <tr key={sKey}>
                          <td><code>{sKey}</code></td>
                          <td><Badge tone="ok">{d.selected_model}</Badge></td>
                          <td>{d.vendor}</td>
                          <td><code>{d.category}</code></td>
                          <td style={{ fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
                            ${d.estimated_input_per_million} / ${d.estimated_output_per_million}
                          </td>
                          <td className="muted">{d.reason}</td>
                        </tr>
                      );
                    })}
                  </Table>
                )}
              </div>
            </section>
          );
        }}
      </AsyncView>

      <AsyncView state={gardenState}>
        {(garden) => (
          <section className="panel" aria-labelledby="garden-endpoints-heading">
            <h2 id="garden-endpoints-heading">
              Model Catalog provider endpoints (OpenAI, Claude, DeepSeek, Singtel RE:AI, Gemini)
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
                    Unknown — not free
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
                      <Badge tone="warn">{m.capabilities.includes("routing-only") ? "Routing-only · integration unavailable" : "Coming soon"}</Badge>
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
                      disabled={m.capabilities.includes("routing-only") || m.id === "auto"}
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
              Illustrative policy preview — not the deployed APIM policy
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
  const [params] = useSearchParams();
  const [filter, setFilter] = useState(params.get("organization_id") ?? "");
  const [deleting, setDeleting] = useState<string>();
  const usersState = useAsync(() => api.localUsers(filter || undefined), [api, version, filter]);
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
                    {orgs.items.filter(o => o.enabled).map((o) => (
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
      <Field label="Filter local users by organization">{id => <select id={id} value={filter} onChange={e => setFilter(e.target.value)}>
        <option value="">All organizations</option>
        {orgsState.data?.items.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>}</Field>
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
                  <button className="btn" type="button" disabled={!!deleting} onClick={() => void toggleUser(u)}>
                    {u.enabled ? "Disable" : "Enable"}
                  </button>{" "}
                  <button className="btn danger" type="button" disabled={!!deleting} onClick={() => setDeleting(u.id)}>Delete</button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </AsyncView>
      {deleting && <DeletionDialog key={deleting} collection="local-users" entityId={deleting} onClose={() => setDeleting(undefined)}
        onChanged={r => { setNotice(r.message); setVersion(v => v + 1); }} />}
    </>
  );
}
