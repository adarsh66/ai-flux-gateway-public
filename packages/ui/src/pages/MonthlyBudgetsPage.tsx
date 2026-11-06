import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, type ControlApi } from "../client";
import { BudgetDashboard } from "../components/MonthlyBudget";
import { estimateMoney } from "../components/DisplayPrice";
import { AsyncView, ErrorState, Field, PageHeader, Pager, Table, fmtDate, useAsync } from "../components/ui";
import { useSession } from "../session";
import type { MonthlyBudgetSummary } from "../types";

/** Fetch every metadata page; do not silently omit organizations after the first 100. */
async function allBudgets(api: ControlApi, archiveState: "current" | "archived") {
  const items: MonthlyBudgetSummary[] = [];
  let total = 0;
  do {
    const page = await api.adminMonthlyBudgets(items.length, 100, archiveState);
    total = page.total;
    if (!page.items.length && items.length < total) throw new ApiError(0, "Organization list changed while loading. Refresh and try again.");
    items.push(...page.items);
  } while (items.length < total);
  return { items, total };
}

export function validMonthlyAllocation(value: string): boolean {
  if (!/^(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,4})?$/.test(value) || !/[1-9]/.test(value)) return false;
  const [whole = "", fraction = ""] = value.split(".");
  // String comparisons only: never round financial input through a JS float.
  return whole.length < 10 || (whole === "1000000000" && !/[1-9]/.test(fraction));
}

export function MonthlyBudgetsPage() {
  const { api } = useSession();
  const [archiveState, setArchiveState] = useState<"current" | "archived">("current");
  const [saving, setSaving] = useState(false);
  return <div className="admin-budget-page">
    <div className="actions" role="group" aria-label="Organization archive view">
      <button className="btn" disabled={saving} aria-pressed={archiveState === "current"} onClick={() => setArchiveState("current")}>Current organizations</button>
      <button className="btn" disabled={saving} aria-pressed={archiveState === "archived"} onClick={() => setArchiveState("archived")}>Archived organizations</button>
    </div>
    <BudgetView key={archiveState} api={api} archiveState={archiveState} onSaving={setSaving} />
  </div>;
}

function BudgetView({ api, archiveState, onSaving }: { api: ControlApi; archiveState: "current" | "archived"; onSaving: (busy: boolean) => void }) {
  const budgets = useAsync(() => allBudgets(api, archiveState), [api, archiveState]);
  const [organizationId, setOrganizationId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (!budgets.loading && budgets.data && !budgets.data.items.some((item) => item.organization_id === organizationId)) setOrganizationId("");
  }, [budgets.loading, budgets.data, organizationId]);
  return <>
    <PageHeader title="Monthly organization budgets" subtitle="Recurring USD allocations and current-month external price estimates. Advisory only — never a traffic limit."
      actions={<><Link className="btn" to="/usage">FinOps usage ledger</Link><button className="btn" disabled={busy || budgets.loading} onClick={() => { setMessage(""); budgets.reload(); }}>Refresh budgets</button></>} />
    <p className="muted">{archiveState === "archived" ? "Archived organizations · read-only current-month estimates from retained usage, not frozen archive-time balances. Budget change history is retained." : "Current organizations includes disabled organizations; archived organizations are available in the separate read-only view."}</p>
    {message && <p className="notice" role="status">{message}</p>}
    <AsyncView state={{ ...budgets, data: budgets.loading ? undefined : budgets.data }} isEmpty={(d) => d.items.length === 0}
      emptyTitle="No organizations" emptyHint="No monthly allocations have been created by viewing this page.">
      {(data) => {
        const selected = data.items.find((b) => b.organization_id === organizationId);
        return <>
          <Field label="Organization">
            {(id) => <select id={id} disabled={busy} value={organizationId} onChange={(e) => { setOrganizationId(e.target.value); setMessage(""); }}>
              <option value="">Select an organization…</option>
              {data.items.map((b) => <option key={b.organization_id} value={b.organization_id}>{b.organization_name} ({b.organization_id})</option>)}
            </select>}
          </Field>
          {selected ? <SelectedBudget key={`${archiveState}:${selected.organization_id}:${selected.version}:${selected.as_of}`} organizationId={selected.organization_id} archived={archiveState === "archived"} busy={busy} api={api} onBusy={(value) => { setBusy(value); onSaving(value); }}
            onSaved={() => { setMessage("Monthly advisory budget saved. No traffic controls or email changed."); budgets.reload(); }} onRefresh={budgets.reload} />
            : <p className="muted">Select an organization to view utilization, configure an allocation, and review budget change history. Unconfigured allocations remain blank.</p>}
        </>;
      }}
    </AsyncView>
    <p className="muted">Budget changes apply immediately to the current and future months. Existing FinOps usage records, filters and exports are unchanged.</p>
  </>;
}

function SelectedBudget({ api, organizationId, archived, busy, onBusy, onSaved, onRefresh }: {
  api: ControlApi; organizationId: string; archived: boolean; busy: boolean; onBusy: (busy: boolean) => void; onSaved: () => void; onRefresh: () => void;
}) {
  const state = useAsync(() => api.adminMonthlyBudgetDashboard(organizationId), [api, organizationId]);
  return <AsyncView state={{ ...state, data: state.loading ? undefined : state.data }}>
    {(data) => {
      const internal = data.internal;
      const partial = internal.unestimated_requests > 0 || internal.approximate_requests > 0;
      const readOnly = archived || data.read_only || data.archived_at != null;
      return <>
        {readOnly && <p className="notice" role="status">Archived organization · read-only. Archived at {fmtDate(data.archived_at)}. These are current-month retained-usage estimates, not a frozen historical balance.</p>}
        <BudgetDashboard budget={data.budget} reload={onRefresh} refreshDisabled={busy}
          extraMetric={<div className="admin-internal-metric"><dt>Estimated internal cost (USD)</dt><dd>{estimateMoney(internal.estimated_cost_usd)}</dd><p>{internal.estimated_cost_usd == null ? "Unknown — no known priced subtotal" : partial ? "Partial completion usage estimate" : "Completion usage estimate"}</p><small>Internal rate-card basis · not budget consumption or an invoice</small></div>}
          extraDetails={<><h3>Internal estimate · completion usage</h3><dl className="overview-budget-metadata">
            <div><dt>Internal pricing revision</dt><dd>{internal.pricing_revision}</dd></div>
            <div><dt>Internal pricing coverage</dt><dd>{internal.estimated_requests} estimated request(s); {internal.unestimated_requests} unestimated; {internal.approximate_requests} approximate. {partial ? "Partial known subtotal, not a complete cost total." : "Reported completion pricing coverage complete; not proof of complete telemetry."}</dd></div>
          </dl><p className="muted">Existing time-effective internal rate-card estimates for this same UTC month and as-of. Completion usage only; excludes Decision-1 scoring and retries not represented in retained usage. Missing prices are unknown, not free. Not recorded ledger cost, supplier actual cost, or total actual cost.</p></>} />
        {!readOnly && <BudgetEditor key={`editor:${data.budget.organization_id}:${data.budget.version}`} budget={data.budget} api={api} onBusy={onBusy} onSaved={onSaved} />}
        <BudgetHistory key={`history:${organizationId}:${data.budget.version}`} api={api} organizationId={organizationId} />
      </>;
    }}
  </AsyncView>;
}

function BudgetEditor({ budget, api, onBusy, onSaved }: { budget: MonthlyBudgetSummary; api: ControlApi; onBusy: (busy: boolean) => void; onSaved: () => void }) {
  const [allocation, setAllocation] = useState(budget.allocated_usd ?? "");
  const [threshold, setThreshold] = useState(String(budget.advisory_threshold_pct));
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  const [conflict, setConflict] = useState(false);
  const valid = validMonthlyAllocation(allocation) && /^\d+$/.test(threshold) && Number(threshold) >= 1 && Number(threshold) <= 100 && reason.trim().length > 0 && reason.length <= 500;
  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving || conflict || !valid) return;
    setSaving(true); onBusy(true); setError(undefined);
    try {
      await api.saveMonthlyBudget(budget.organization_id, {
        allocated_usd: allocation, advisory_threshold_pct: Number(threshold), expected_version: budget.version, reason: reason.trim(),
      });
      onSaved();
    } catch (e) {
      const stale = e instanceof ApiError && e.status === 409;
      setConflict(stale);
      setError(stale ? "This budget changed since it was loaded. Your draft has not been saved. Refresh budgets to load the latest version and review before saving again." : e instanceof ApiError ? e.detail : "Could not save the monthly budget.");
    } finally { setSaving(false); onBusy(false); }
  }
  return <>
    <section className="panel" aria-label="Configure monthly advisory budget">
      <h2>Configure monthly allocation</h2>
      <p>Saved version {budget.version}. Threshold defaults to 80% for unconfigured budgets; on-screen only. No credit balance, model allowlist or enforcement is updated.</p>
      {error && <ErrorState message={error} />}
      <form className="form-row" onSubmit={(e) => void save(e)}>
        <fieldset disabled={saving}>
          <Field label="Monthly allocation (USD)" hint="Positive decimal, up to 1,000,000,000 USD and four decimal places. No default allocation.">
            {(id, desc) => <input id={id} aria-describedby={desc} inputMode="decimal" value={allocation} maxLength={32} required onChange={(e) => setAllocation(e.target.value)} />}
          </Field>
          <Field label="On-screen advisory threshold (%)" hint="Whole percentage from 1 to 100. Does not send email or stop requests.">
            {(id, desc) => <input id={id} aria-describedby={desc} type="number" min={1} max={100} step={1} value={threshold} required onChange={(e) => setThreshold(e.target.value)} />}
          </Field>
          <Field label="Reason for budget change">
            {(id) => <textarea id={id} value={reason} maxLength={500} required onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <button className="btn primary" disabled={!valid || conflict || saving}>{saving ? "Saving…" : "Save monthly budget"}</button>
        </fieldset>
      </form>
    </section>
  </>;
}

function BudgetHistory({ api, organizationId }: { api: ControlApi; organizationId: string }) {
  const [offset, setOffset] = useState(0);
  const state = useAsync(() => api.monthlyBudgetHistory(organizationId, offset, 20), [api, organizationId, offset]);
  return <section className="panel" aria-label="Monthly budget change history">
    <h2>Budget change history</h2>
    <AsyncView state={{ ...state, data: state.loading ? undefined : state.data }} isEmpty={(d) => !d.items.length}
      emptyTitle="No budget changes" emptyHint="Viewing an unconfigured budget does not create an allocation or revision.">
      {(data) => <><Table caption="Monthly budget revisions" head={["Version", "Allocation", "On-screen threshold", "Changed at", "Changed by", "Reason"]}>
        {data.items.map((r) => <tr key={r.version}><td>{r.version}</td><td>{estimateMoney(r.allocated_usd)}</td><td>{r.advisory_threshold_pct}%</td><td>{fmtDate(r.changed_at)}</td><td>{r.changed_by}</td><td>{r.reason}</td></tr>)}
      </Table><Pager offset={offset} limit={20} total={data.total} onChange={setOffset} /></>}
    </AsyncView>
  </section>;
}