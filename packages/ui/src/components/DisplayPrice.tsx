import type { DisplayEstimate, DisplayPrice } from "../types";

/** Preserve tiny nonzero USD amounts; never round measured POC spend to zero. */
export function estimateMoney(value: string | null | undefined): string {
  if (value == null || value.trim() === "") return "Unknown";
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return "Unknown";
  if (amount > 0 && amount < 0.00000001) return "USD <0.00000001";
  return `USD ${amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 8 })}`;
}

export function EstimateCoverage({ estimate, admin = false }: { estimate: DisplayEstimate; admin?: boolean }) {
  return <small className="muted block">{estimate.unestimated_requests ?? "Unknown"} unestimated request(s); {estimate.approximate_requests ?? "Unknown"} standard-input approximation(s) where cache detail is unavailable. {admin ? "Internal cost estimates" : "External price estimates"}, not invoices. Missing prices are unknown, not free. {admin && "Recorded costs and budget enforcement unchanged."}</small>;
}

export function DisplayPriceDetails({ price, admin = false }: { price?: DisplayPrice | null; admin?: boolean }) {
  if (!price) return <p title="Unknown does not mean free">Price: unknown</p>;
  const inputOnly = price.billing_dimensions?.length === 1 && price.billing_dimensions[0] === "input";
  return <div>
    <small className="muted">{admin ? "Internal estimated costs" : "External estimated prices"} · not an invoice</small>
    <p>Estimated USD / 1M tokens: input {price.input ?? "Unknown — not free"} · output {inputOnly ? "N/A" : price.output ?? "Unknown — not free"}{inputOnly ? <> · cached input N/A · cache write N/A</> : <>{price.cached != null && <> · cached input {price.cached}</>}{price.write != null && <> · cache write {price.write}</>}</>}{price.status === "tbc" && <strong> · TBC</strong>}{price.status === "platform_default" && <strong> · Estimated default</strong>}{price.status === "configured" && <strong> · Set by administrator</strong>}</p>
    <details><summary>Price source and assumptions</summary>
      <p>{price.source_url ? <><a href={price.source_url} target="_blank" rel="noreferrer">Public pricing source</a> · checked {price.checked_at}</> : <>Effective {price.checked_at}</>}</p>
      <p>{price.source_model} · {price.sku} · version {price.model_version} · {price.status}</p>
      <p>{price.assumption} {price.assumptions} {price.basis}</p>
      {price.provenance && <pre aria-label="Pricing provenance">{JSON.stringify(price.provenance, null, 2)}</pre>}
      <small>{price.revision}</small>
    </details>
  </div>;
}