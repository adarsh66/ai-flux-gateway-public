import type { DisplayEstimate, DisplayPrice } from "../types";

/** Preserve tiny nonzero USD amounts; never round measured POC spend to zero. */
export function estimateMoney(value: string | null | undefined): string {
  if (value == null) return "Unknown";
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return "Unknown";
  if (amount > 0 && amount < 0.00000001) return "USD <0.00000001";
  return `USD ${amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 8 })}`;
}

export function EstimateCoverage({ estimate }: { estimate: DisplayEstimate }) {
  return <small className="muted block">{estimate.unestimated_requests ?? 0} unestimated request(s); {estimate.approximate_requests ?? 0} standard-input approximation(s) where cache detail is unavailable. Public list estimates, not invoices. Recorded costs and budget enforcement unchanged.</small>;
}

export function DisplayPriceDetails({ price }: { price?: DisplayPrice | null }) {
  if (!price) return <p title="Unknown does not mean free">Price: unknown</p>;
  return <div>
    <p>Estimated USD / 1M tokens: input {price.input} · output {price.output}{price.cached !== undefined && <> · cached input {price.cached}</>}{price.write !== undefined && <> · cache write {price.write}</>}{price.status === "tbc" && <strong> · TBC</strong>}</p>
    <details><summary>Price source and assumptions</summary>
      <p><a href={price.source_url} target="_blank" rel="noreferrer">Public pricing source</a> · checked {price.checked_at}</p>
      <p>{price.source_model} · {price.sku} · version {price.model_version} · {price.status}</p>
      <p>{price.assumption} {price.assumptions} {price.basis}</p>
      <small>{price.revision}</small>
    </details>
  </div>;
}