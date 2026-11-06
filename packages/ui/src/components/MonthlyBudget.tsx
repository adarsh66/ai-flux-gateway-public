import type { ReactNode } from "react";
import { useSession } from "../session";
import type { MonthlyBudgetSummary } from "../types";
import { estimateMoney } from "./DisplayPrice";
import { AsyncView, Badge, fmtInt, useAsync } from "./ui";

const STATUS = {
  unconfigured: "No monthly budget configured",
  below_threshold: "Below advisory threshold",
  threshold_reached: "On-screen advisory threshold reached",
  over_budget: "Over monthly budget — advisory only",
  unknown: "Budget utilization unknown",
} as const;

/** Budget periods deliberately use UTC, not the portal's SGT reporting buckets. */
function utc(value: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toISOString().replace("T", " ").replace(".000Z", " UTC").replace("Z", " UTC");
}

export function MonthlyBudgetDetails({ budget, showProgress = true }: { budget: MonthlyBudgetSummary; showProgress?: boolean }) {
  const pct = budget.estimated_utilization_pct;
  const knownPct = pct != null && Number.isFinite(pct);
  const percentText = knownPct ? `${pct.toLocaleString("en-US", { maximumFractionDigits: 2 })}%` : "Unknown";
  return <section className="panel" aria-label="Monthly advisory budget">
    <div className="card-head">
      <h2>Monthly advisory budget</h2>
      {budget.status !== "unknown" && <Badge tone={budget.status === "over_budget" || budget.status === "threshold_reached" ? "warn" : "info"}>{!showProgress && !budget.estimate_complete && budget.status === "below_threshold" ? "Incomplete estimate — advisory status not confirmed" : STATUS[budget.status]}</Badge>}
    </div>
    <p>Organization-wide · all subscriptions · current UTC calendar month. Recurs monthly, with no rollover.</p>
    <p>This budget never blocks traffic or changes model access. The {budget.advisory_threshold_pct}% threshold is an on-screen advisory only. Email notifications are not enabled.</p>
    <dl className="pricing-strip">
      <div className="pricing-cell"><dt>Monthly allocation</dt><dd>{budget.allocated_usd == null ? "Not configured" : estimateMoney(budget.allocated_usd)}</dd></div>
      <div className="pricing-cell"><dt>Known estimated usage</dt><dd>{estimateMoney(budget.estimated_used_usd)}</dd></div>
      <div className="pricing-cell"><dt>Estimated remaining</dt><dd>{estimateMoney(budget.estimated_remaining_usd)}</dd></div>
      <div className="pricing-cell"><dt>Estimated overrun</dt><dd>{estimateMoney(budget.estimated_overrun_usd)}</dd></div>
      <div className="pricing-cell"><dt>Estimated utilization</dt><dd>{percentText}{!showProgress && !budget.estimate_complete ? " known estimate (incomplete coverage)" : ""}</dd></div>
    </dl>
    {showProgress && knownPct && <div role="progressbar" aria-label="Monthly budget utilization" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={Math.max(0, Math.min(100, pct))} aria-valuetext={`${percentText} estimated utilization; advisory only`}
      className="share-bar-track">
      <div className="share-bar-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>}
    <dl>
      <div><dt>UTC period (end exclusive)</dt><dd>{utc(budget.period_start)} – {utc(budget.period_end)}</dd></div>
      <div><dt>As of</dt><dd>{utc(budget.as_of)}</dd></div>
      <div><dt>Latest observed usage</dt><dd>{utc(budget.latest_usage_at)}</dd></div>
      <div><dt>Pricing coverage</dt><dd>{fmtInt(budget.estimated_requests)} estimated request(s); {fmtInt(budget.unestimated_requests)} unestimated request(s). {budget.estimate_complete ? "Reported estimate coverage complete." : "Incomplete estimate coverage; known amounts are not a complete total."}</dd></div>
      <div><dt>External pricing revision</dt><dd>{budget.pricing_revision}</dd></div>
    </dl>
    <p className="muted">External customer prices effective at usage time; estimates, not invoices. Missing prices are unknown, not free. Ingestion may be delayed. Decision-1 scoring telemetry is not fully represented in the usage ledger: zero unestimated requests does not prove complete scoring coverage.</p>
  </section>;
}

/** Independently scoped to the current principal, never the usage page's detail filters. */
export function CustomerMonthlyBudgetCard({ refresh = 0, overview = false }: { refresh?: number; overview?: boolean }) {
  const { api, me } = useSession();
  return <PrincipalBudget key={`${me.tenant_id}:${me.organization_id}:${me.object_id}`} refresh={refresh} api={api} overview={overview} />;
}

/** No client-side budget arithmetic: percentages, remaining and overrun come from the API. */
export function MonthlyBudgetGauge({ budget, compact = false }: { budget: MonthlyBudgetSummary; compact?: boolean }) {
  const allocation = budget.allocated_usd;
  const configured = allocation != null && allocation.trim() !== "" && Number.isFinite(Number(allocation)) && Number(allocation) > 0;
  const used = budget.estimated_used_usd;
  const knownUsage = used != null && used.trim() !== "" && Number.isFinite(Number(used)) && Number(used) >= 0;
  const pct = budget.estimated_utilization_pct;
  const known = configured && knownUsage && pct != null && Number.isFinite(pct) && pct >= 0;
  const fill = known ? Math.min(100, pct) : 0;
  const percent = known ? `${pct.toLocaleString("en-US", { maximumFractionDigits: 2 })}%` : allocation == null ? "Not configured" : "Unknown";
  const threshold = budget.advisory_threshold_pct;
  const validThreshold = Number.isFinite(threshold) && threshold >= 1 && threshold <= 100;
  const incomplete = !budget.estimate_complete;
  const status = !configured ? (allocation == null ? STATUS.unconfigured : STATUS.unknown) : !known ? STATUS.unknown
    : incomplete && budget.status === "below_threshold" ? "Incomplete estimate — advisory status not confirmed" : STATUS[budget.status];
  return <section className={compact ? "monthly-budget-gauge overview-budget-gauge" : "chart-card monthly-budget-gauge"} aria-label="Current UTC month budget consumption">
    {!compact && <div className="chart-card-head"><div><h2>Monthly budget utilization</h2><p>Current UTC calendar month · all organization subscriptions</p></div></div>}
    <div className="monthly-gauge-layout">
      <div className={`monthly-gauge-track${known ? "" : " is-unknown"}`} role="progressbar" aria-label="Monthly budget utilization"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={known ? fill : undefined}
        aria-valuetext={`${percent}${known ? ` known estimated utilization${incomplete ? " (incomplete coverage)" : ""}` : ""}; advisory only`}
        aria-orientation="vertical">
        <div className="monthly-gauge-fill" style={{ height: `${fill}%` }} />
        <span className="monthly-gauge-limit" aria-hidden="true">100% allocation</span>
        {validThreshold && <span className="monthly-gauge-threshold" style={{ bottom: `${threshold}%` }} aria-hidden="true"><span>{threshold}% advisory</span></span>}
      </div>
      <div className="monthly-gauge-copy">
        <p className="bento-value">{percent}</p>
        <p>Known estimated consumption{incomplete ? " (incomplete coverage)" : ""}</p>
        {!compact && <p><strong>{knownUsage ? estimateMoney(used) : "Unknown"}</strong> used / {configured ? estimateMoney(allocation) : allocation == null ? "Not configured" : "Unknown"} allocated</p>}
        {status !== STATUS.unknown && <Badge tone={budget.status === "over_budget" || budget.status === "threshold_reached" ? "warn" : "info"}>{status}</Badge>}
        {!compact && <>
          <p>Estimated remaining: {estimateMoney(budget.estimated_remaining_usd)} · Estimated overrun: {estimateMoney(budget.estimated_overrun_usd)}</p>
          {validThreshold && <p>{threshold}% on-screen advisory threshold · 100% allocation marker</p>}
          <p className="muted">Advisory only — never blocks traffic, including above 100%. Estimates are not invoices.</p>
        </>}
      </div>
    </div>
  </section>;
}

/** Pure opt-in presentation. Customers pass external budget data only. */
export function BudgetDashboard({ budget, reload, extraMetric, extraDetails, refreshDisabled = false }: {
  budget: MonthlyBudgetSummary; reload: () => void; extraMetric?: ReactNode; extraDetails?: ReactNode; refreshDisabled?: boolean;
}) {
  const allocation = budget.allocated_usd;
  const configured = allocation != null && allocation.trim() !== "" && Number.isFinite(Number(allocation)) && Number(allocation) > 0;
  const start = new Date(budget.period_start);
  const month = Number.isNaN(start.getTime()) ? "Current UTC calendar month" : `${start.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" })} · UTC`;
  const asOf = new Date(budget.as_of);
  return <section className="panel overview-budget-dashboard" aria-label="Monthly advisory budget">
    <header className="overview-budget-heading">
      <div><h2>Monthly advisory budget</h2><p>{budget.organization_name} · {month}</p></div>
      <div className="overview-budget-refresh"><p className="muted">As of {Number.isNaN(asOf.getTime()) ? "Not available" : <time dateTime={budget.as_of}>{asOf.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })} · {asOf.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC</time>}</p><button className="btn" disabled={refreshDisabled} onClick={reload}>Refresh monthly budget</button></div>
    </header>
    <div className="overview-budget-body">
      <MonthlyBudgetGauge budget={budget} compact />
      <dl className="overview-budget-metrics">
        <div aria-label="Current monthly allocation"><dt>Monthly allocation (USD)</dt><dd>{allocation == null ? "Not configured" : configured ? estimateMoney(allocation) : "Unknown"}</dd></div>
        <div><dt>Known estimated usage</dt><dd>{estimateMoney(budget.estimated_used_usd)}</dd></div>
        <div><dt>Estimated remaining</dt><dd>{estimateMoney(budget.estimated_remaining_usd)}</dd></div>
        <div><dt>Estimated overrun</dt><dd>{estimateMoney(budget.estimated_overrun_usd)}</dd></div>
        {extraMetric}
      </dl>
    </div>
    <p className="overview-budget-notice">Month-to-date external price estimate · {budget.estimate_complete ? "Reported estimate coverage complete." : "Incomplete coverage — known amounts are not a complete total."}</p>
    <p className="muted">Advisory only — never blocks traffic, including above 100%. Estimates are not invoices.</p>
    <details className="overview-disclosure">
      <summary>Budget details &amp; calculation basis</summary>
      <p>Organization-wide · all subscriptions · current UTC calendar month. Recurs monthly, with no rollover.</p>
      <p>This budget never blocks traffic or changes model access. The {budget.advisory_threshold_pct}% threshold is an on-screen advisory only. Email notifications are not enabled.</p>
      <dl className="overview-budget-metadata">
        <div><dt>UTC period (end exclusive)</dt><dd>{utc(budget.period_start)} – {utc(budget.period_end)}</dd></div>
        <div><dt>As of</dt><dd>{utc(budget.as_of)}</dd></div>
        <div><dt>Latest observed usage</dt><dd>{utc(budget.latest_usage_at)}</dd></div>
        <div><dt>Pricing coverage</dt><dd>{fmtInt(budget.estimated_requests)} estimated request(s); {fmtInt(budget.unestimated_requests)} unestimated request(s). {budget.estimate_complete ? "Reported estimate coverage complete." : "Incomplete estimate coverage; known amounts are not a complete total."}</dd></div>
        <div><dt>External pricing revision</dt><dd>{budget.pricing_revision}</dd></div>
      </dl>
      {extraDetails}
      <p className="muted">External customer prices effective at usage time; estimates, not invoices. Missing prices are unknown, not free. Ingestion may be delayed. Decision-1 scoring telemetry is not fully represented in the usage ledger: zero unestimated requests does not prove complete scoring coverage.</p>
    </details>
  </section>;
}

function PrincipalBudget({ api, refresh, overview }: { api: ReturnType<typeof useSession>["api"]; refresh: number; overview: boolean }) {
  const state = useAsync(() => api.monthlyBudget(), [api, refresh]);
  return <div>
    {!overview && <div className="actions"><button className="btn" disabled={state.loading} onClick={state.reload}>Refresh monthly budget</button></div>}
    <AsyncView state={{ ...state, data: state.loading ? undefined : state.data }}>
      {(budget) => overview ? <BudgetDashboard budget={budget} reload={state.reload} /> : <MonthlyBudgetDetails budget={budget} />}
    </AsyncView>
  </div>;
}