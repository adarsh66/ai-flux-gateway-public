import type { ReactNode } from "react";
import { customerModelPresentation } from "../modelPresentation";
import type { ModelGardenItem, RateRow } from "../types";
import { Badge, fmtInt } from "./ui";

/** Explicit audience: never infer a price source from the current user's role. */
export function ModelCatalogCard({ model, logo, pricingAudience, rate, pricingState }: {
  model: ModelGardenItem;
  logo: ReactNode;
  pricingAudience: "external-default";
  rate?: RateRow;
  pricingState: "loading" | "unavailable" | "ready";
}) {
  const scoring = model.model_kind === "scoring";
  const copy = customerModelPresentation(model);
  function amount(dimension: "input" | "output" | "cached" | "write") {
    if (scoring && dimension !== "input") return "N/A";
    if (pricingState === "loading") return "Loading…";
    if (pricingState === "unavailable" || !rate) return "Unavailable — not free";
    if (rate.origin === "unknown" || rate[dimension] == null) return "Unknown — not free";
    return `USD ${rate[dimension]}`;
  }
  return <li className="card model-catalog-card" data-pricing-audience={pricingAudience}>
    <div className="card-head">
      <div className="vendor-header">
        <div className="vendor-mark">{logo}</div>
        <div><h2>{copy.displayName || model.id}</h2><p className="muted"><code>{model.id}</code> · {model.vendor || model.provider} · {model.region || "Region unverified"}</p></div>
      </div>
      <Badge tone={scoring ? model.scoring_available === true ? "info" : "warn" : model.coming_soon ? "warn" : "info"}>
        {scoring ? model.scoring_available === true ? "Scoring configured as available" : model.scoring_available === false ? "Scoring unavailable" : "Scoring availability unknown" : model.coming_soon ? "Availability unverified" : "Chat eligible"}
      </Badge>
    </div>
    <p>{copy.description}</p>
    <small className="muted">External default prices · USD per 1M tokens · estimates, not invoice amounts</small>
    <dl className="pricing-strip" aria-label="External default token prices">
      {([["input", "Input"], ["output", "Output"], ["cached", "Cached input"], ["write", "Cache write"]] as const).map(([dimension, label]) => <div className="pricing-cell" key={dimension}><dt>{label} / 1M tokens</dt><dd>{amount(dimension)}</dd></div>)}
    </dl>
    {pricingState === "ready" && rate && <details><summary>External default price basis</summary>
      <p>{rate.provider} · {rate.region} · version {rate.model_version} · {rate.sku}</p>
      <p>{rate.origin === "unknown" ? "Unknown — not free" : rate.origin} · {rate.note}</p>
      <p>Effective {rate.configured_from ?? "date unavailable"}. This is the external default, without organization overrides or internal costs.</p>
    </details>}
    <div className="card-meta-row"><span>{scoring ? "Published model context" : "Context / Max output"}</span><strong>{model.context_window != null ? fmtInt(model.context_window) : "Unverified"}{!scoring && <> / {model.max_completion_tokens > 0 ? fmtInt(model.max_completion_tokens) : "Unverified"}</>}</strong></div>
    <div className="badges">{scoring && <Badge tone="info">Scoring service · not chat</Badge>}{model.capabilities.map(capability => <Badge key={capability} tone="info">{capability}</Badge>)}</div>
    <p className="muted">{scoring ? "Used for routing decisions, not a completion endpoint. Availability is independent of chat eligibility and is not proof of a successful invocation. See Usage for separate scoring telemetry." : "Catalog eligibility is not runtime execution proof. Capabilities are declared metadata, not verified support for every request."}</p>
  </li>;
}