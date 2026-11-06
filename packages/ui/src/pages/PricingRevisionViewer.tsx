import { useEffect, useRef, useState } from "react";
import { ApiError } from "../client";
import { Table, useAsync } from "../components/ui";
import { useSession } from "../session";
import type { HistoricalRateRow, PricingHistoryDetail, PricingHistoryPage, PricingHistoryPoint } from "../types";

type Scope = "internal" | "external-default" | "organization-external";
const message = (error: unknown, fallback: string) => error instanceof ApiError ? error.detail : fallback;

function versionLabel(point: PricingHistoryPoint) {
  return point.internal_version != null ? `Internal v${point.internal_version}`
    : `External default v${point.default_version ?? 0} / organization v${point.organization_version ?? 0}`;
}

function historicalAmount(row: HistoricalRateRow, dimension: "input" | "output" | "cached" | "write") {
  if (row.model_kind === "scoring" && dimension !== "input") return "N/A";
  // Chat DTOs declare input/output dimensions even when cache sub-rates exist.
  // Only an explicitly non-billing primary dimension is N/A; nullable cache rates are unknown.
  if ((dimension === "input" || dimension === "output") && !row.billing_dimensions.includes(dimension)) return "N/A";
  if (row.state === "unavailable") return "Unavailable";
  if (row.state === "unknown" || row[dimension] == null) return "Unknown — not free";
  // Render the API decimal string verbatim: never round through Number or coerce null to zero.
  return row[dimension];
}

/** Read-only history. Deliberately independent of the editor's historical draft/restore workflow. */
export function PricingRevisionViewer() {
  const { api } = useSession();
  const [scope, setScope] = useState<Scope>("internal");
  const [organizationId, setOrganizationId] = useState("");
  const organizations = useAsync(() => scope === "organization-external" ? api.organizations() : Promise.resolve({ items: [], total: 0 }), [api, scope]);
  return <section aria-label="Read-only pricing revisions">
    <h3>View revisions</h3>
    <p className="muted">Read-only historical prices · USD per 1M tokens. Viewing never loads an editing draft or changes prices. Unknown and unavailable rates are not free; current rates are never substituted for historical gaps.</p>
    <div className="actions">
      <label>Revision scope <select aria-label="Revision scope" value={scope} onChange={(event) => { setScope(event.target.value as Scope); setOrganizationId(""); }}>
        <option value="internal">Internal costs</option>
        <option value="external-default">External default</option>
        <option value="organization-external">Organization external prices</option>
      </select></label>
      {scope === "organization-external" && <label>Revision organization <select aria-label="Revision organization" value={organizationId} disabled={organizations.loading || !!organizations.error} onChange={(event) => setOrganizationId(event.target.value)}>
        <option value="">Select an organization</option>
        {!organizations.loading && !organizations.error && organizations.data?.items.map((org) => <option key={org.id} value={org.id}>{org.name} · {org.id}</option>)}
      </select></label>}
    </div>
    {scope === "organization-external" && <>
      {organizations.loading && <p role="status">Loading revision organizations…</p>}
      {organizations.error && <p role="alert" className="notice bad">Could not load organizations. {organizations.error} <button className="btn" onClick={organizations.reload}>Retry organizations</button></p>}
      {!organizations.loading && !organizations.error && !organizations.data?.items.length && <p>No organizations available.</p>}
      {!organizationId && <p>Select an organization to view its external price history.</p>}
    </>}
    {(scope !== "organization-external" || organizationId) && <RevisionList key={`${scope}:${organizationId}`} external={scope !== "internal"} organizationId={scope === "organization-external" ? organizationId : undefined} />}
  </section>;
}

function RevisionList({ external, organizationId }: { external: boolean; organizationId?: string }) {
  const { api } = useSession();
  const [history, setHistory] = useState<PricingHistoryPage>();
  const [selection, setSelection] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [failedOffset, setFailedOffset] = useState(0);
  const generation = useRef(0);
  const lock = useRef(false);
  async function load(offset = 0) {
    if (lock.current) return;
    lock.current = true;
    const request = ++generation.current;
    setLoading(true);
    setError(undefined);
    try {
      const next = await api.pricingHistory(external, organizationId, offset);
      if (request !== generation.current) return;
      setHistory((previous) => ({ ...next, items: offset ? [...(previous?.items ?? []), ...next.items.filter((point) => !previous?.items.some((old) => old.id === point.id))] : next.items }));
      if (offset === 0) setSelection(next.items[0]?.id ?? "");
    } catch (reason) {
      if (request !== generation.current) return;
      setFailedOffset(offset);
      setError(message(reason, "Could not load pricing revisions."));
    } finally {
      if (request === generation.current) { lock.current = false; setLoading(false); }
    }
  }
  useEffect(() => {
    void load();
    return () => { generation.current++; lock.current = false; };
  }, [api, external, organizationId]);
  return <>
    <div className="actions">
      <label>Revision to view <select aria-label="Revision to view" disabled={loading || !history?.items.length} value={selection} onChange={(event) => setSelection(event.target.value)}>
        {!history?.items.length && <option value="">Select a revision</option>}
        {history?.items.map((point) => <option key={point.id} value={point.id}>{versionLabel(point)} · {point.effective_at} · {point.source} · {point.reason ?? "No reason recorded"}{point.simultaneous ? " · simultaneous version bound" : ""}</option>)}
      </select></label>
      {history?.next_offset != null && <button className="btn" disabled={loading} onClick={() => void load(history.next_offset!)}>Load more revisions</button>}
      {history && <span className="muted">{history.items.length} of {history.total} revisions loaded</span>}
    </div>
    {loading && <p role="status">Loading revisions…</p>}
    {error && <p role="alert" className="notice bad">{error} <button className="btn" disabled={loading} onClick={() => void load(failedOffset)}>Retry revisions</button></p>}
    {!loading && !error && history && !history.items.length && <p>No retained historical revisions.</p>}
    {selection && <RevisionDetail key={selection} external={external} organizationId={organizationId} revision={selection} />}
  </>;
}

function RevisionDetail({ external, organizationId, revision }: { external: boolean; organizationId?: string; revision: string }) {
  const { api } = useSession();
  const state = useAsync(() => api.pricingHistoryDetail(external, revision, organizationId), [api, external, revision, organizationId]);
  if (state.loading) return <p role="status">Loading historical rates…</p>;
  if (state.error) return <p role="alert" className="notice bad">{state.error} <button className="btn" onClick={state.reload}>Retry historical rates</button></p>;
  return state.data ? <HistoricalTable detail={state.data} /> : null;
}

function HistoricalTable({ detail }: { detail: PricingHistoryDetail }) {
  return <>
    <dl aria-label="Historical revision metadata">
      <dt>Source versions</dt><dd>{versionLabel(detail.source)}</dd>
      <dt>Revision identifier</dt><dd>{detail.source.id}</dd>
      <dt>Source</dt><dd>{detail.source.source}</dd>
      <dt>Effective at (UTC)</dt><dd><time dateTime={detail.source.effective_at}>{detail.source.effective_at}</time></dd>
      <dt>Reason</dt><dd>{detail.source.reason ?? "No reason recorded"}</dd>
      <dt>Current scope version (reference only)</dt><dd>{detail.current_version}</dd>
    </dl>
    {detail.source.simultaneous && <p className="notice warn">Simultaneous changes: this revision uses the explicit default / organization version bound shown above.</p>}
    {(detail.requires_acknowledgement || detail.skipped.length > 0) && <div className="notice warn" role="status">
      <p>Incomplete historical reconstruction. Some rows or historical defaults could not be reconstructed; no current prices have been substituted. Viewing requires no editing acknowledgement.</p>
      {detail.skipped.length > 0 && <><p>Skipped or unverifiable rows ({detail.skipped.length}):</p><ul>{detail.skipped.map((note, index) => <li key={index}>{note}</li>)}</ul></>}
    </div>}
    {!detail.items.length ? <p>No historical rate rows available for this revision.</p> : <Table caption="Historical model rates (USD per 1M tokens)" head={["Model / canonical identity", "Provider / region", "Model version / SKU", "Billing dimensions", "Historical state / notes", "Input", "Output", "Cached input", "Cache write"]}>
      {detail.items.map((row, index) => <tr key={`${row.model}:${row.provider}:${row.region}:${index}`}>
        <th scope="row">{row.model}<small className="block">Canonical: {row.canonical_model}</small></th>
        <td>{row.provider} · {row.region}</td>
        <td>{row.model_version ?? "Unavailable"} · {row.sku ?? "Unavailable"}</td>
        <td>{row.model_kind} · {row.billing_dimensions.join(", ") || "Unavailable"}</td>
        <td>{row.state === "known" ? "Known" : row.state === "unknown" ? "Unknown — not free" : "Unavailable — not free"}{row.note && <small className="block">{row.note}</small>}</td>
        {(["input", "output", "cached", "write"] as const).map((dimension) => <td key={dimension}>{historicalAmount(row, dimension)}</td>)}
      </tr>)}
    </Table>}
    <p className="muted">Historical rows include retired models when retained in this revision. N/A denotes a non-billing dimension, not a free rate.</p>
  </>;
}