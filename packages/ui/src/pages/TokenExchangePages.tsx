import { useState, type FormEvent } from "react";
import { ApiError } from "../client";
import { useSession } from "../session";
import type {
  CreditBudget,
  KeyName,
  ModelGardenItem,
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

export function ModelGardenPage() {
  const { api } = useSession();
  const state = useAsync(() => api.modelGarden(), [api]);
  const [vendorFilter, setVendorFilter] = useState("");
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
        title="Model garden & pricing cards"
        subtitle="Curated frontier models from OpenAI, Anthropic Claude, and DeepSeek with Microsoft Decision-1 auto-routing and Azure AI Content Safety guardrails."
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
        emptyTitle="No models in garden"
        emptyHint="Contact your platform administrator to publish model endpoints."
      >
        {(d) => {
          const vendors = Array.from(new Set(d.items.map((m) => m.vendor)));
          const visible = vendorFilter
            ? d.items.filter((m) => m.vendor === vendorFilter)
            : d.items;
          return (
            <>
              <div className="filters">
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
                      <div>
                        <h2>{m.display_name}</h2>
                        <p className="muted">
                          <code>{m.id}</code> · {m.vendor} · {m.region}
                        </p>
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
                    <dl className="stats">
                      <div>
                        <dt>Input / 1M tokens</dt>
                        <dd>
                          {m.currency} {m.input_per_million}
                        </dd>
                      </div>
                      <div>
                        <dt>Output / 1M tokens</dt>
                        <dd>
                          {m.currency} {m.output_per_million}
                        </dd>
                      </div>
                      <div>
                        <dt>Cached input / 1M</dt>
                        <dd>
                          {m.cached_input_per_million
                            ? `${m.currency} ${m.cached_input_per_million}`
                            : "N/A"}
                        </dd>
                      </div>
                      <div>
                        <dt>Context / Max output</dt>
                        <dd>
                          {fmtInt(m.context_window)} / {fmtInt(m.max_completion_tokens)}
                        </dd>
                      </div>
                    </dl>
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
        title="Credits & Hitakari FinOps report"
        subtitle="Real-time token credit balance, low-credit threshold alerts, and usage breakdown by model, product subscription, and channel."
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
        {(summary) => (
          <>
            {summary.low_credit_alert && (
              <p role="alert" className="notice bad">
                Low credit alert: Your organization has consumed {summary.utilization_pct}% of its
                allocated {summary.currency} {summary.total_credits} budget (alert threshold:{" "}
                {summary.alert_threshold_pct}%).
              </p>
            )}
            <dl className="stats" aria-label="Credit balance summary">
              <div>
                <dt>Total credit allocation</dt>
                <dd>
                  {summary.currency} {summary.total_credits}
                </dd>
              </div>
              <div>
                <dt>Credits used ({days}d)</dt>
                <dd>
                  {summary.currency} {summary.used_credits}
                </dd>
              </div>
              <div>
                <dt>Remaining credits</dt>
                <dd>
                  {summary.currency} {summary.remaining_credits}
                </dd>
              </div>
              <div>
                <dt>Utilization</dt>
                <dd>
                  {summary.utilization_pct}%{" "}
                  <Badge tone={summary.low_credit_alert ? "bad" : "ok"}>
                    {summary.low_credit_alert ? "Low credit warning" : "Healthy"}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt>Total requests / tokens</dt>
                <dd>
                  {fmtInt(summary.total_requests)} reqs · {fmtInt(summary.total_tokens)} tokens
                </dd>
              </div>
            </dl>

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
                      <td><code>{m.model}</code></td>
                      <td>{m.vendor}</td>
                      <td>{fmtInt(m.requests)}</td>
                      <td>{fmtInt(m.input_tokens)}</td>
                      <td>{fmtInt(m.output_tokens)}</td>
                      <td>{fmtInt(m.total_tokens)}</td>
                      <td>{summary.currency} {m.cost_usd}</td>
                      <td>{m.share_pct}%</td>
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
                      <td>{p.product_name}</td>
                      <td>{p.team}</td>
                      <td>{fmtInt(p.requests)}</td>
                      <td>{fmtInt(p.total_tokens)}</td>
                      <td>{summary.currency} {p.cost_usd}</td>
                      <td>{p.share_pct}%</td>
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
                      <td>{c.share_pct}%</td>
                    </tr>
                  ))}
                </Table>
              )}
            </section>
          </>
        )}
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
          <ul className="cards" aria-label="Customer subscription keys">
            {d.items.map((sub) => {
              const revealed = keys[sub.id] ?? {};
              return (
                <li className="card" key={sub.id}>
                  <div className="card-head">
                    <div>
                      <h2>{sub.name}</h2>
                      <p className="muted">
                        Team {sub.team} · created {fmtDate(sub.created_at)}
                      </p>
                    </div>
                    <StateBadge state={sub.state} />
                  </div>
                  <div className="keys">
                    {(["primary", "secondary"] as KeyName[]).map((k) => {
                      const val = revealed[k];
                      return (
                        <div key={k} className="key-row">
                          <span className="key-label">{k} key</span>
                          {val ? (
                            <>
                              <code aria-label={`${k} key value`}>{val}</code>
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
                              className="btn"
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
                  <td><code>{m.id}</code></td>
                  <td>{m.display_name}</td>
                  <td>{m.vendor}</td>
                  <td>${m.input_per_million} / ${m.output_per_million}</td>
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
                      className="btn"
                      type="button"
                      onClick={() => void toggleModelEndpoint(m)}
                    >
                      {m.coming_soon || !m.enabled ? `Activate ${m.id}` : `Disable ${m.id}`}
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
