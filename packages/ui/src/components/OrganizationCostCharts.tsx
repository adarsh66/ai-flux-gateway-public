import { useState } from "react";
import { useSession } from "../session";
import type { OrganizationCostEstimate, OrganizationCosts, OrganizationCostsQuery } from "../types";
import { estimateMoney } from "./DisplayPrice";
import { AsyncView, EmptyState, Pager, Table, fmtInt, useAsync } from "./ui";

function Coverage({ value }: { value: OrganizationCostEstimate }) {
  return <small className="block muted">{value.estimated_requests} estimated; {value.unestimated_requests} unestimated; {value.approximate_requests} approximate request(s){value.unestimated_requests > 0 && value.estimated_requests > 0 ? " · Partial estimate" : ""}</small>;
}

export function OrganizationCostComparison({ data, onSelect }: { data: OrganizationCosts; onSelect: (id: string) => void }) {
  const maximum = Math.max(0, ...data.items.flatMap(row => [row.external, row.internal].map(value => {
    const number = Number(value.estimated_cost_usd);
    return value.estimated_cost_usd !== null && Number.isFinite(number) && number >= 0 ? number : 0;
  })));
  return <>
    <p className="muted">Shared USD page scale: 0 – {estimateMoney(String(maximum))}. Both charts use the same organization order, descending measured input + output tokens, then ID. Scale changes with the page.</p>
    <div className="organization-cost-grid">
      {(["external", "internal"] as const).map(kind => <section key={kind} aria-label={`${kind} organization cost chart`}>
        <h3>{kind === "external" ? "External customer token estimate by organization" : "Internal token cost estimate by organization"}</h3>
        <p className="muted">{kind === "external" ? "External customer" : "Internal"} rate-card estimates · USD · not invoices or recorded ledger costs</p>
        <ol className={`organization-cost-bars ${kind}`}>
          {data.items.map(row => {
            const value = row[kind];
            const known = value.estimated_cost_usd !== null;
            const amount = Number(value.estimated_cost_usd);
            return <li key={row.id}>
              <button className="btn" onClick={() => onSelect(row.id)}>{row.name}</button>
              <span className="organization-cost-track" aria-hidden="true">{known && <span className="organization-cost-fill" style={{ width: `${maximum > 0 ? amount / maximum * 100 : 0}%`, minWidth: amount > 0 ? "2px" : 0 }} />}</span>
              <strong>{estimateMoney(value.estimated_cost_usd)}</strong>{!known && <small> · Unknown, not free</small>}
              <Coverage value={value} />
            </li>;
          })}
        </ol>
      </section>)}
    </div>
    <Table caption="Organization internal and external estimate comparison — accessible chart data" head={["Organization / ID", "Requests / measured tokens", "External customer estimate (USD)", "Internal cost estimate (USD)"]}>
      {data.items.map(row => <tr key={row.id}>
        <td><button className="btn" onClick={() => onSelect(row.id)}>{row.name}</button><small className="block muted">{row.id}</small></td>
        <td>{fmtInt(row.requests)} / {fmtInt(row.total_tokens)}</td>
        <td>{estimateMoney(row.external.estimated_cost_usd)}<Coverage value={row.external} /></td>
        <td>{estimateMoney(row.internal.estimated_cost_usd)}<Coverage value={row.internal} /></td>
      </tr>)}
    </Table>
  </>;
}

export function OrganizationCostCharts({ query, onSelect }: { query: Omit<OrganizationCostsQuery, "offset" | "limit">; onSelect: (id: string) => void }) {
  const { api } = useSession();
  const [offset, setOffset] = useState(0);
  const key = JSON.stringify([query, offset]);
  const state = useAsync(async () => ({ key, data: await api.adminOrganizationCosts({ ...query, offset, limit: 10 }) }), [api, key]);
  return <section aria-label="Organization rate-card cost comparison">
    <h2>Organization rate-card cost comparison</h2>
    <p className="notice">Global comparison: selected date/window and model; independent of detail organization and subscription filters. Completion tokens only; Decision-1 scoring is separate. Historical time-effective rates applied to measured usage, not current unit rates. Missing prices are unknown, not zero. Partial estimates exclude unestimated requests; approximate estimates may lack cache detail.</p>
    <AsyncView state={{ ...state, data: !state.loading && state.data?.key === key ? state.data.data : undefined }}>
      {data => <>
        <p>{data.total ? `Showing ${Math.min(offset + 1, data.total)}–${Math.min(offset + data.items.length, data.total)} of ${data.total} organizations` : "0 organizations"}</p>
        {data.items.length ? <OrganizationCostComparison data={data} onSelect={onSelect} /> : <EmptyState title="No completion usage in this comparison window" />}
        <Pager offset={offset} limit={10} total={data.total} onChange={setOffset} />
      </>}
    </AsyncView>
  </section>;
}