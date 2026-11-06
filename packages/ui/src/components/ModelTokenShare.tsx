import { useId, useMemo, type CSSProperties } from "react";
import type { ModelTokenSeries } from "../types";
import { formatSgt } from "../time";

const COLORS = ["--teal-500", "--info", "--ok", "--warn", "--bad", "--ink-dim"];
const integer = new Intl.NumberFormat("en-SG");
const label = (model: string) => model.trim() || "Unknown model";

// Model identity, not current filter/order, determines its theme colour and pattern.
function appearance(model: string) {
  let hash = 0;
  for (const char of model) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return { color: `var(${COLORS[hash % COLORS.length]})`, pattern: Math.floor(hash / COLORS.length) % 4 };
}

export function tokenShares(series: ModelTokenSeries) {
  const models = new Map<string, { tokens: bigint; known: boolean; partial: boolean }>();
  for (const item of series.items) {
    const row = models.get(item.model) ?? { tokens: 0n, known: false, partial: false };
    // Paired totals only: never substitute component subtotals for missing totals.
    if (item.total_tokens !== null && Number.isSafeInteger(item.total_tokens) && item.total_tokens >= 0) {
      row.tokens += BigInt(item.total_tokens);
      row.known = true;
    } else row.partial = true;
    row.partial ||= item.missing_token_requests > 0;
    models.set(item.model, row);
  }
  const rows = [...models].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([model, row]) => ({ model, ...row }));
  const total = rows.reduce((sum, row) => sum + row.tokens, 0n);
  return { total, rows, partial: rows.some(row => row.partial) };
}

export function shareLabel(tokens: bigint, total: bigint): string {
  if (!total) return "Not applicable";
  if (!tokens) return "0.0%";
  if (tokens * 1000n < total) return "<0.1%";
  return `${(Number(tokens) / Number(total) * 100).toFixed(1)}%`;
}

export function ModelTokenShare({ series }: { series: ModelTokenSeries }) {
  const id = useId().replace(/:/g, "");
  const { rows, total, partial } = useMemo(() => tokenShares(series), [series]);
  const known = rows.some(row => row.known);
  let accumulated = 0n;
  return <section className="chart-panel model-token-share" aria-labelledby={`${id}-title`}>
    <h2 id={`${id}-title`}>Token share by model</h2>
    <p id={`${id}-caption`} className="muted">All token buckets in the selected filters and viewport: {formatSgt(Date.parse(series.start))} – {formatSgt(Date.parse(series.end))}. Independent of transaction pagination. Shares use known measured paired input + output totals only, not provider-billed tokens.</p>
    {partial && <p className="notice" role="status">Partial token measurements: unknown totals are excluded from the share denominator, not treated as zero. Known portions remain included.</p>}
    {series.health?.status !== "healthy" && <p className="notice" role="status">Telemetry {series.health?.status ?? "unverified"}: these shares describe available measurements, not confirmed complete traffic.</p>}
    <div className="token-share-layout">
      <div className="token-share-figure">
        {total > 0n ? <svg viewBox="0 0 200 200" role="img" aria-labelledby={`${id}-title`} aria-describedby={`${id}-caption ${id}-rounding`}>
          <title>Exact proportional model shares; each model and measured count is listed in the adjacent table.</title>
          <defs>{rows.map((row, index) => {
            const style = appearance(row.model);
            return <pattern key={row.model} id={`${id}-${index}`} width="8" height="8" patternUnits="userSpaceOnUse">
              <rect width="8" height="8" fill={style.color} />
              {style.pattern === 1 && <path d="M0 8L8 0" className="token-share-pattern" />}
              {style.pattern === 2 && <circle cx="4" cy="4" r="1.5" className="token-share-pattern" />}
              {style.pattern === 3 && <path d="M0 4H8M4 0V8" className="token-share-pattern" />}
            </pattern>;
          })}</defs>
          {rows.map((row, index) => {
            const offset = Number(accumulated) / Number(total) * 100;
            accumulated += row.tokens;
            if (!row.tokens) return null;
            const percent = Number(row.tokens) / Number(total) * 100;
            return <circle key={row.model} data-share-model={row.model} data-tokens={String(row.tokens)}
              cx="100" cy="100" r="76" pathLength="100" fill="none" stroke={`url(#${id}-${index})`}
              strokeWidth="30" strokeDasharray={`${percent} ${100 - percent}`} strokeDashoffset={-offset}
              transform="rotate(-90 100 100)">
              <title>{label(row.model)}: {integer.format(row.tokens)} tokens; {shareLabel(row.tokens, total)}</title>
            </circle>;
          })}
        </svg> : <p className="muted">{known ? "Known measured token total is zero; no positive shares to plot." : "No measured token total available; no shares to plot."}</p>}
        <div className={total > 0n ? "token-share-center" : "token-share-total"}>
          <strong>{known ? integer.format(total) : "Unknown"}</strong><span>Known measured tokens</span>
        </div>
      </div>
      <div className="table-wrap">
        <table className="token-share-legend">
          <caption>Exact model token shares — known measured denominator {known ? integer.format(total) : "unknown"}</caption>
          <thead><tr><th scope="col">Model</th><th scope="col">Measured tokens</th><th scope="col">Share</th><th scope="col">Coverage</th></tr></thead>
          <tbody>{rows.map(row => {
            const style = appearance(row.model);
            return <tr key={row.model} tabIndex={0} style={{ "--share-color": style.color } as CSSProperties}>
              <th scope="row"><span className={`token-share-swatch pattern-${style.pattern}`} aria-hidden="true" />{label(row.model)}</th>
              <td className="num">{row.known ? integer.format(row.tokens) : "Unknown"}</td>
              <td className="num">{row.known ? shareLabel(row.tokens, total) : "Unknown"}</td>
              <td>{row.partial ? row.known ? "Partial; known portion" : "Unknown measurements" : "Measured"}</td>
            </tr>;
          })}</tbody>
        </table>
        {!rows.length && <p className="muted">No model measurements returned for this viewport. No traffic or billing conclusion is implied.</p>}
      </div>
    </div>
    <p id={`${id}-rounding`} className="muted">Percentages are rounded independently to one decimal and may not sum to 100%. Positive shares below 0.1% are labelled &lt;0.1%; slices use actual proportions, with no minimum angle or grouped “Other”. Tab through model rows for exact counts and coverage.</p>
  </section>;
}