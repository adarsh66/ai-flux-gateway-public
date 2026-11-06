import { useEffect, useRef, useState } from "react";
import { useSession } from "../session";
import { formatSgt } from "../time";
import type { DecisionScoringQuery, DecisionScoringTelemetry } from "../types";
import { estimateMoney } from "./DisplayPrice";
import { AsyncView, Badge, EmptyState, ErrorState, Field, Pager, Table, downloadBlob, fmtMs, useAsync } from "./ui";

const PAGE_SIZE = 50;
const AGGREGATE_PAGE_SIZE = 25;
const count = (value: number | null | undefined) => value == null ? "Unknown" : value.toLocaleString("en-US");

/** The parent keys this component by scope, viewport, granularity and refresh. */
export function DecisionScoringUsage({ admin = false, query }: { admin?: boolean; query: DecisionScoringQuery }) {
  const { api } = useSession();
  const [offset, setOffset] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string>();
  const pageQuery = { ...query, offset, limit: PAGE_SIZE };
  const key = JSON.stringify([admin, pageQuery]);
  const current = useRef<string | null>(key);
  current.current = key;
  useEffect(() => {
    current.current = key;
    setExporting(false);
    setExportError(undefined);
    return () => { current.current = null; };
  }, [key]);
  const state = useAsync(async () => ({ key, data: await (admin ? api.adminDecisionScoring(pageQuery) : api.decisionScoring(pageQuery)) }), [api, key]);
  const data = state.data?.key === key ? state.data.data : undefined;

  async function exportPage() {
    const exportKey = key;
    setExporting(true);
    setExportError(undefined);
    try {
      const blob = await api.exportDecisionScoringCsv(admin, pageQuery);
      if (current.current === exportKey) downloadBlob(blob, `aiflux-decision-scoring-page-${offset / PAGE_SIZE + 1}.csv`);
    } catch (error) {
      if (current.current === exportKey) setExportError(error instanceof Error ? error.message : "Scoring export failed.");
    } finally {
      if (current.current === exportKey) setExporting(false);
    }
  }

  return <section aria-label="Decision-1 scoring usage" className="usage-chart-section">
    <div className="usage-chart-head"><h2>Decision-1 scoring overhead</h2>
      <button className="btn" disabled={exporting || state.loading || !data} onClick={() => void exportPage()}>{exporting ? "Preparing scoring CSV…" : "Export scoring page CSV"}</button>
    </div>
    <p className="muted">Separate scoring invocations, not customer completion requests. Never added to completion totals. Estimates are not recorded charges or invoices; budget enforcement is unchanged.</p>
    <p className="notice">Log Analytics retention applies. Source completeness is unknown, even when the query is available or returns no traces. Catalog availability and parent HTTP status do not prove successful scorer or completion execution.</p>
    {exportError && <ErrorState message={exportError} />}
    <AsyncView state={{ ...state, data }}>
      {(telemetry) => <>
        <p role="status"><Badge tone={telemetry.status === "available" ? "info" : "warn"}>Telemetry {telemetry.status}</Badge> {telemetry.notice}</p>
        <p className="muted">{telemetry.retention_notice}</p>
        {telemetry.status === "unavailable" ? <EmptyState title="Scoring telemetry unavailable" hint="Counts, tokens, latency and cost are unknown, not zero. Retry or narrow the shared viewport." /> : <>
          <ScoringBody data={telemetry} admin={admin} />
          <Pager offset={offset} limit={PAGE_SIZE} total={telemetry.total ?? 0} onChange={(next) => { setOffset(next); setExportError(undefined); }} />
        </>}
        <small className="muted">CSV contains page metadata and scoring rows for these filters and this offset, not all pages. Paging and export each re-query the source; newly arriving traces may change totals or repeat or shift rows between pages. These are independent observations, not a frozen billing snapshot.</small>
      </>}
    </AsyncView>
  </section>;
}

function ScoringBody({ data, admin }: { data: DecisionScoringTelemetry; admin: boolean }) {
  const summary = data.summary;
  const [sort, setSort] = useState<"total_tokens" | "invocations">("total_tokens");
  const [groupOffset, setGroupOffset] = useState(0);
  const [bucketOffset, setBucketOffset] = useState(0);
  const groups = [...data.breakdown].sort((a, b) => {
    const left = a[sort], right = b[sort];
    return (left == null ? (right == null ? 0 : 1) : right == null ? -1 : right - left)
      || a.organization_id.localeCompare(b.organization_id) || a.subscription_id.localeCompare(b.subscription_id);
  });
  const metrics = [
    ["Scoring invocations", count(summary.invocations)],
    ["Scoring input tokens", count(summary.input_tokens)],
    ["Scoring output tokens", count(summary.output_tokens)],
    ["Scoring total tokens", count(summary.total_tokens)],
    ["Average scoring latency", summary.avg_latency_ms == null ? "Unknown" : fmtMs(summary.avg_latency_ms)],
    [admin ? "Estimated scoring cost" : "External estimated scoring cost", estimateMoney(summary.estimated_cost_usd)],
    ...(admin ? [["Recorded scoring cost", estimateMoney(summary.recorded_cost_usd)]] : []),
  ];
  const maxTokens = data.series.reduce((max, row) => Math.max(max, row.total_tokens ?? 0), 1);
  return <>
    <dl className="stats">{metrics.map(([label, value]) => <div className="stat" key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <p className="muted">{count(summary.measured_invocations)} invocations with complete tokens; {count(summary.missing_token_invocations)} missing tokens. {count(summary.estimated_invocations)} estimated; {count(summary.unestimated_invocations)} unestimated. Null means unknown, never free. Pricing revision: {summary.pricing_revision ?? "Unknown"}.</p>
    <h3>Scoring tokens over time (SGT)</h3>
    <p className="muted">Shared {data.granularity} viewport; Singapore-midnight daily boundaries. Gaps are unknown; edge intervals may be partial. Tokens are scorer overhead only.</p>
    {data.series.length > 0 && <svg className="usage-chart" viewBox="0 0 920 160" role="img" aria-label="Decision-1 scoring token chart in SGT; exact values in scoring interval data">
      {data.series.map((row, index) => row.total_tokens == null ? null : <rect key={row.start} x={index * 920 / data.series.length} y={140 - row.total_tokens / maxTokens * 130} width={Math.max(0.1, 920 / data.series.length * 0.8)} height={row.total_tokens / maxTokens * 130} fill="currentColor"><title>{formatSgt(row.start)}: {count(row.total_tokens)} scoring tokens{row.partial_bucket ? " (partial interval)" : ""}</title></rect>)}
      <text x="0" y="157" fontSize="10">{formatSgt(data.start)}</text><text x="920" y="157" textAnchor="end" fontSize="10">{formatSgt(data.end)}</text>
    </svg>}
    <details><summary>Scoring interval data</summary>
      <Table caption="Scoring interval data" head={["SGT interval", "Invocations", "Input tokens", "Output tokens", "Total tokens", "Average scoring latency"]}>
        {data.series.slice(bucketOffset, bucketOffset + AGGREGATE_PAGE_SIZE).map(row => <tr key={row.start}><td>{formatSgt(row.start)} – {formatSgt(row.end)}{row.partial_bucket ? " (partial interval)" : ""}</td><td>{count(row.invocations)}</td><td>{count(row.input_tokens)}</td><td>{count(row.output_tokens)}</td><td>{count(row.total_tokens)}</td><td>{row.avg_latency_ms == null ? "Unknown" : fmtMs(row.avg_latency_ms)}</td></tr>)}
      </Table>
      <Pager offset={bucketOffset} limit={AGGREGATE_PAGE_SIZE} total={data.series.length} onChange={setBucketOffset} />
    </details>
    <h3>Scoring showback by organization / subscription</h3>
    <p className="muted">Ranked across the full returned aggregate dataset before local pagination, independent of the invocation page. Limited to verified traces within this scope and source query bounds; not a global completeness guarantee.</p>
    <Field label="Scoring ranking sort">{id => <select id={id} value={sort} onChange={event => { setSort(event.target.value as typeof sort); setGroupOffset(0); }}><option value="total_tokens">Total scoring tokens</option><option value="invocations">Scoring invocations</option></select>}</Field>
    <Table caption="Scoring organization and subscription showback" head={["Organization", "Subscription", "Invocations", "Input tokens", "Output tokens", "Total tokens", admin ? "Estimated USD" : "External estimated USD"]}>
      {groups.slice(groupOffset, groupOffset + AGGREGATE_PAGE_SIZE).map(row => <tr key={`${row.organization_id}/${row.subscription_id}`}><td>{row.organization_id}</td><td>{row.subscription_id}</td><td>{count(row.invocations)}</td><td>{count(row.input_tokens)}</td><td>{count(row.output_tokens)}</td><td>{count(row.total_tokens)}</td><td>{estimateMoney(row.estimated_cost_usd)}</td></tr>)}
    </Table>
    <Pager offset={groupOffset} limit={AGGREGATE_PAGE_SIZE} total={groups.length} onChange={setGroupOffset} />
    <h3>Scoring invocation details</h3>
    {data.items.length === 0 && <EmptyState title="No scoring traces on this page" hint="No observed traces is not proof of no scoring activity." />}
    <Table caption="Decision-1 scoring invocations" head={["SGT time", "Organization / subscription", "Profile", "Selected completion model", "Parent request ID", "Configuration version", "Input / output / total tokens", "Scoring latency", admin ? "Estimated cost" : "External estimated cost", ...(admin ? ["Recorded cost"] : []), "Estimate basis / revision", "Parent HTTP status (context only)"]}>
      {data.items.map(row => <tr key={row.id}><td>{formatSgt(row.occurred_at, true)}</td><td>{row.organization_id} / {row.subscription_id}</td><td>{row.routing_profile}</td><td>{row.selected_model}</td><td>{row.parent_request_id}</td><td>{row.config_version}</td><td>{count(row.input_tokens)} / {count(row.output_tokens)} / {count(row.total_tokens)}</td><td>{row.latency_ms == null ? "Unknown" : fmtMs(row.latency_ms)}</td><td>{estimateMoney(row.estimated_cost_usd)}</td>{admin && <td>{estimateMoney(row.recorded_cost_usd)}</td>}<td>{row.estimate_basis} / {row.pricing_revision ?? "Unknown"}</td><td>{row.parent_status_code ?? "Unknown"}</td></tr>)}
    </Table>
  </>;
}