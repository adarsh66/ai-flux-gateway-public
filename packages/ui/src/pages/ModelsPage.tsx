import { useSession } from "../session";
import { AsyncView, Badge, PageHeader, useAsync } from "../components/ui";
import { DeploymentStatus } from "../components/DeploymentStatus";
import { DisplayPriceDetails } from "../components/DisplayPrice";
import { ModelCatalogCard } from "../components/ModelCatalogCard";
import { VendorLogo } from "../components/VendorLogo";
import type { CatalogModel, ModelGardenItem, RateRow } from "../types";

// Current rate-card output.model is the accepted public alias, not backend_model.
// An ambiguous alias is unavailable: never pick an arbitrary provider/region row.
function externalRate(rows: RateRow[] | undefined, id: string, scoring: boolean) {
  const matches = rows?.filter(row => row.model === id && (row.model_kind === "scoring") === scoring) ?? [];
  return matches.length === 1 ? matches[0] : undefined;
}

function catalogPresentation(model: CatalogModel, garden?: ModelGardenItem): ModelGardenItem {
  return {
    id: model.id, display_name: garden?.display_name || model.id, provider: model.provider,
    vendor: garden?.vendor || model.provider, region: garden?.region || "", backend_model: "", endpoint_url: "",
    context_window: garden?.context_window ?? null, max_completion_tokens: model.max_completion_tokens ?? garden?.max_completion_tokens ?? 0,
    input_per_million: null, output_per_million: null, cached_input_per_million: null, currency: "USD",
    capabilities: model.capabilities, description: garden?.description ?? "", enabled: model.enabled, coming_soon: garden?.coming_soon ?? false,
    content_safety_enabled: false, priority: 0,
  };
}

function AdminCatalog() {
  const { api } = useSession();
  const state = useAsync(async () => {
    const [models, garden] = await Promise.all([api.models(), api.adminModelGarden()]);
    const scoring = garden.items.filter(m => m.model_kind === "scoring");
    const scoringIds = new Set(scoring.map(m => m.id));
    return { scoring, chat: models.items.filter(m => m.id !== "Decision-1" && !scoringIds.has(m.id) && m.enabled && !m.placeholder && m.capabilities.includes("chat"))
      .map(m => catalogPresentation(m, garden.items.find(g => g.id === m.id))) };
  }, [api]);
  // Independent request: a failed default card must never hide the model catalog
  // or expose the internal display_price fields returned by adminModelGarden.
  const prices = useAsync(() => api.externalRateCard(), [api]);
  const pricingState = prices.loading ? "loading" : prices.error ? "unavailable" : "ready";
  return <div className="admin-model-catalog">
    <PageHeader title="Model catalog" subtitle="Chat-eligible models and separate scoring services. External default prices only, without organization overrides or internal costs. Estimates, not invoice amounts. This catalog is read-only." />
    {prices.loading && <p role="status">Loading external default prices…</p>}
    {prices.error && <p className="notice warn" role="alert">External default prices unavailable. Missing prices are not free; no internal or organization prices substituted. <button className="btn" onClick={prices.reload}>Retry external default prices</button></p>}
    <AsyncView state={state} isEmpty={d => d.chat.length === 0 && d.scoring.length === 0} emptyTitle="No models are enabled" emptyHint="IDS has not published any enabled models yet. Contact your IDS representative.">
      {d => <ul className="cards" aria-label="Model availability">
        {[...d.chat, ...d.scoring].map(model => <ModelCatalogCard key={model.id} model={model} logo={<VendorLogo vendor={model.vendor || model.provider} size={22} />} pricingAudience="external-default" pricingState={pricingState} rate={externalRate(prices.loading || prices.error ? undefined : prices.data?.items, model.id, model.model_kind === "scoring")} />)}
      </ul>}
    </AsyncView>
    <DeploymentStatus />
  </div>;
}

export function ModelsPage({ admin = false }: { admin?: boolean }) {
  return admin ? <AdminCatalog /> : <CustomerCatalog />;
}

function CustomerCatalog() {
  const admin = false;
  const { api } = useSession();
  const state = useAsync(async () => {
    const [models, garden] = await Promise.all([api.models(), admin ? api.adminModelGarden() : api.modelGarden()]);
    const scoring = garden.items.filter(m => m.model_kind === "scoring");
    const scoringIds = new Set(scoring.map(m => m.id));
    const chat = models.items.filter(m => m.id !== "Decision-1" && !scoringIds.has(m.id) && m.enabled && !m.placeholder && m.capabilities.includes("chat"))
      .map(m => ({ ...m, display_price: garden.items.find(g => g.id === m.id)?.display_price }));
    return { chat, scoring };
  }, [api, admin]);
  return (
    <>
      <PageHeader title="Model catalog" subtitle="Chat-eligible models and separate scoring services. Catalog availability is not runtime execution proof. This catalog is read-only; no router configurator changes." />
      <AsyncView state={state} isEmpty={(d) => d.chat.length === 0 && d.scoring.length === 0} emptyTitle="No models are enabled" emptyHint="IDS has not published any enabled models yet. Contact your IDS representative.">
        {(d) => (
          <ul className="cards" aria-label="Model availability">
            {d.chat.map((m) => (
              <li className="card" key={m.id}>
                <h2>{m.id}</h2>
                <p>{m.provider}</p>
                <DisplayPriceDetails price={m.display_price} admin={admin} />
                  <span className="badges">
                    {m.placeholder ? <Badge tone="warn">Preview only - not callable</Badge> : m.capabilities.length === 0 ? <span className="muted">None declared</span> : m.capabilities.map((c) => <Badge key={c} tone="info">{c}</Badge>)}
                  </span>
              </li>
            ))}
            {d.scoring.map((m) => <li className="card" key={m.id}>
              <h2>{m.display_name || m.id}</h2>
              <p>{m.id} · {m.provider}</p>
              <p>{m.description}</p>
              <DisplayPriceDetails price={m.display_price} admin={admin} />
              <span className="badges"><Badge tone="info">Scoring service · not chat</Badge><Badge tone={m.scoring_available === true ? "info" : "warn"}>{m.scoring_available === true ? "Scoring configured as available" : m.scoring_available === false ? "Scoring unavailable" : "Scoring availability unknown"}</Badge></span>
              <p className="muted">Used for routing decisions, not a completion endpoint. Availability is independent of chat eligibility and is not proof of a successful invocation. See Usage for separate scoring telemetry.</p>
            </li>)}
          </ul>
        )}
      </AsyncView>
      <DeploymentStatus />
    </>
  );
}