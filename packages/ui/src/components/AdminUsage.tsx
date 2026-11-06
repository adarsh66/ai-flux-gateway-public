import { useState } from "react";
import { useSession } from "../session";
import type { AdminSubscription, UsageRankingQuery } from "../types";
import { AsyncView, EmptyState, Field, Pager, Table, fmtInt, useAsync } from "./ui";

/** Load every safe metadata page, not just the first 100 subscriptions. */
export function AdminUsageSubscriptions({ organizationId, value, onChange }: {
  organizationId: string; value: string; onChange: (id: string) => void;
}) {
  const { api } = useSession();
  const [search, setSearch] = useState("");
  const state = useAsync(async () => {
    const items: AdminSubscription[] = [];
    let total = 0;
    do {
      const page = await api.adminSubscriptions(items.length, 100, organizationId || undefined);
      total = page.total;
      if (!page.items.length && items.length < total) throw new Error("Incomplete subscription metadata");
      items.push(...page.items);
    } while (items.length < total);
    return { organizationId, items };
  }, [api, organizationId]);
  const items = !state.loading && state.data?.organizationId === organizationId ? state.data.items : [];
  const matches = items.filter(s => s.id === value || `${s.name} ${s.organization_name} ${s.id}`.toLowerCase().includes(search.toLowerCase()));
  return <div>
    <Field label="Search subscriptions">{id => <input id={id} type="search" value={search} onChange={e => setSearch(e.target.value)} />}</Field>
    <Field label="Subscription">{id => <select id={id} value={value} disabled={state.loading || !!state.error} onChange={e => onChange(e.target.value)}>
      <option value="">All subscriptions</option>
      {matches.map(s => <option key={s.id} value={s.id}>{s.name} — {s.organization_name} ({s.id})</option>)}
      {value && !items.some(s => s.id === value) && <option value={value}>{value}</option>}
    </select>}</Field>
    {state.loading && <p role="status">Loading subscriptions…</p>}
    {state.error && <div role="alert">Could not load subscriptions. <button className="btn" onClick={state.reload}>Retry subscriptions</button></div>}
    {!state.loading && !state.error && search && !matches.length && <p role="status">No matching subscriptions.</p>}
  </div>;
}

export function UsageRankingTable({ query, title, onSelect }: {
  query: Omit<UsageRankingQuery, "offset" | "limit">;
  title: string; onSelect: (id: string) => void;
}) {
  const { api } = useSession();
  const [offset, setOffset] = useState(0);
  const key = JSON.stringify([query, offset]);
  const state = useAsync(async () => ({ key, data: await api.adminUsageRankings({ ...query, offset, limit: 10 }) }), [api, key]);
  return <section aria-label={title}>
    <h2>{title}</h2>
    <p className="muted">{query.dimension === "organizations"
      ? "Global: all organizations, independent of the detail organization and subscription filters."
      : "Compare all subscriptions in this organization, independent of the detail subscription filter."}
      {" "}Selected SGT-displayed viewport and model; descending measured input + output tokens, ID breaks ties.
      {" "}Totals require both measurements; known components include partial requests. Cache tokens are not added again.</p>
    <AsyncView state={{ ...state, data: !state.loading && state.data?.key === key ? state.data.data : undefined }}>
      {data => <>
        <p>Scope total: {fmtInt(data.totals?.total_tokens)} measured tokens; {fmtInt(data.totals?.requests)} requests across {fmtInt(data.total)} groups.
          {" "}{fmtInt(data.totals?.missing_token_requests)} missing token measurement(s); {fmtInt(data.totals?.incomplete_requests)} incomplete request(s).</p>
        {!data.items.length ? <EmptyState title="No usage in this ranking scope" /> : <Table caption={`${title} ranking table`} head={["Rank", "Name / ID", "Requests", "Known input", "Known output", "Measured total", "Share of scope tokens", "Completeness"]}>
          {data.items.map((row, i) => <tr key={row.id}>
            <td>{offset + i + 1}</td>
            <td><button className="btn" onClick={() => onSelect(row.id)}>{row.name}</button><small className="block muted">{row.id}</small></td>
            <td>{fmtInt(row.requests)}</td><td>{fmtInt(row.input_tokens)}</td><td>{fmtInt(row.output_tokens)}</td><td>{fmtInt(row.total_tokens)}</td>
            <td>{row.share === null ? "Unknown" : `${(row.share * 100).toFixed(1)}%`}</td>
            <td>{row.missing_token_requests} missing tokens; {row.incomplete_requests} incomplete usage/pricing/attribution</td>
          </tr>)}
        </Table>}
        <Pager offset={offset} limit={10} total={data.total} onChange={setOffset} />
      </>}
    </AsyncView>
  </section>;
}