import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, type ControlApi } from "../client";
import { routingLabels, routingProfiles, type AutoCandidate, type AutoConfiguration, type AutoProfileConfig, type AutoRoutingAvailability, type RoutingProfile } from "../autoRouting";
import { useSession } from "../session";
import { AsyncView, Badge, ErrorState, Field, PageHeader, useAsync } from "../components/ui";

type RouterView = { kind: "editor"; config: AutoConfiguration } | { kind: "availability"; availability: AutoRoutingAvailability };

async function loadRouter(api: ControlApi): Promise<RouterView> {
  try {
    return { kind: "editor", config: await api.adminAutoRouting() };
  } catch (error) {
    // The optional editor is absent in availability-only deployments. Do not
    // conceal authentication, throttling, server or transport failures.
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
    return { kind: "availability", availability: await api.autoRoutingAvailability() };
  }
}

function RouterAvailability({ availability }: { availability: AutoRoutingAvailability }) {
  return <section className="panel" aria-label="Auto routing availability">
    <h2>Platform routing status</h2>
    <Badge tone={availability.ready ? "ok" : "warn"}>
      {availability.ready ? "Auto routing advertised available" : "Auto routing currently unavailable"}
    </Badge>
    <p>This deployment exposes read-only routing availability. Profile editing is not supported here; the missing optional editor does not determine whether Auto is available.</p>
    <p>Availability is reported by the control plane, not an independent inference or gateway publication check. Explicit model access is unchanged.</p>
    {availability.architecture && <p>Architecture: {availability.architecture}</p>}
    <p>Configuration version: {availability.config_version ?? "not provided"}</p>
    <h3>Reported routing profiles</h3>
    {availability.profiles.length ? <ul>{availability.profiles.map((profile) => <li key={profile}>{routingLabels[profile]}</li>)}</ul>
      : <p>No routing profiles reported.</p>}
    <p>Candidate pools and prices are not included in this availability response. View model details and pricing separately.</p>
    <div className="actions"><Link to="/models">Model catalog</Link><Link to="/prices">Rate card &amp; pricing</Link></div>
  </section>;
}

export function AdminAutoRouterPage() {
  const { api } = useSession();
  const [revision, setRevision] = useState(0);
  const state = useAsync(() => loadRouter(api), [api, revision]);
  const [profile, setProfile] = useState<RoutingProfile>("balanced");
  return <>
    <PageHeader title="Decision-1 Auto routing" subtitle="Shared platform defaults; no tenant initialization or approval. Optional audited customization is desired configuration until released. Explicit model access is unchanged." />
    <AsyncView state={state}>{(view) => {
      if (view.kind === "availability") return <RouterAvailability availability={view.availability} />;
      const { config } = view;
      return <>
      <section className="panel">
        <Badge tone={config.feature_enabled && config.publication_verified ? "ok" : "warn"}>
          {config.feature_enabled && config.publication_verified ? "Published platform snapshot verified" : "Not live — release gates are off or unverified"}
        </Badge>
        <p>Every normally provisioned active product subscription uses the same published defaults immediately. No seed POST, subscriber whitelist or per-organization publication is required.</p>
        <p>Published version: {config.published_version ?? "not verified"}. Saving an optional override does not change gateway routing or disable defaults.</p>
        <p>Saving a pool does not deploy gateway policies or prove inference access. Decision overhead is separate; unavailable usage and prices remain unknown, not zero.</p>
        <p className="muted">Descriptors: {config.descriptor_version} · Pricing: {config.pricing_revision}. Published and provisional display rates are planning inputs, not invoices or quality rankings.</p>
      </section>
      <Field label="Routing profile">{(id) => <select id={id} value={profile} onChange={(e) => setProfile(e.target.value as RoutingProfile)}>
        {routingProfiles.map((p) => <option value={p} key={p}>{routingLabels[p]}</option>)}
      </select>}</Field>
      {config.items.find((p) => p.profile === profile) ?
        <ProfileEditor key={`${profile}:${config.items.find((p) => p.profile === profile)!.version}`} config={config.items.find((p) => p.profile === profile)!} candidates={config.candidates}
          saved={() => setRevision((n) => n + 1)} /> :
        <section className="panel"><p>Platform snapshot unavailable. GET requests never seed configuration. Existing explicit models remain available.</p></section>}
    </>;
    }}</AsyncView>
  </>;
}

function ProfileEditor({ config, candidates, saved }: { config: AutoProfileConfig; candidates: AutoCandidate[]; saved: () => void }) {
  const { api } = useSession();
  const [selected, setSelected] = useState(config.candidate_models);
  const [fallback, setFallback] = useState(config.fallback_model);
  const [enabled, setEnabled] = useState(config.enabled);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const eligible = candidates.filter((c) => config.profile !== "cost" || (c.price !== null && c.price_status !== "unknown"));
  const valid = selected.length >= 2 && selected.length <= 10 && selected.includes(fallback)
    && selected.every((id) => eligible.some((c) => c.id === id));
  async function save() {
    setBusy(true); setError(undefined);
    try {
      await api.saveAutoProfile(config.profile, { enabled, candidate_models: selected, fallback_model: fallback, expected_version: config.version });
      saved();
    } catch (e) { setError(e instanceof ApiError ? e.detail : "Save failed. Reload before trying again."); }
    finally { setBusy(false); }
  }
  return <section className="panel" aria-label={`${config.profile} candidate pool`}>
    <h2>{routingLabels[config.profile]}</h2>
    <p className="muted">Version {config.version} · Last updated {config.updated_at}</p>
    <p>{config.source === "desired-override" ? "Desired override — not published; gateway continues using platform defaults." : "Platform default — no database profile row required."}</p>
    {error && <ErrorState message={error} />}
    <fieldset disabled={busy}><legend>Eligible text models</legend>
      {candidates.map((c) => <div key={c.id}>
        <label className="check"><input type="checkbox" checked={selected.includes(c.id)} disabled={!eligible.includes(c)}
          onChange={(e) => setSelected(e.target.checked ? [...selected, c.id] : selected.filter((id) => id !== c.id))} />{c.id}</label>
        <small>{c.provider} · {c.model_name} {c.model_version} · {c.capabilities.join(", ")} · output ≤{c.max_completion_tokens}</small>
        <p>{c.price && c.price_status !== "unknown" ? <>USD / 1M input {c.price.input}, output {c.price.output} · {c.price_status} · <a href={c.price.source_url} target="_blank" rel="noreferrer">Price source</a></> : "Price unknown — not free; excluded from Cost"}</p>
      </div>)}
      <Field label="Fallback model" hint="Desired configuration only. Gateway-direct currently fails closed on every scoring error; no fallback is activated.">{(id) =>
        <select id={id} value={fallback} onChange={(e) => setFallback(e.target.value)}>
          <option value="">Select eligible fallback</option>{eligible.filter((c) => selected.includes(c.id)).map((c) => <option key={c.id}>{c.id}</option>)}
        </select>}</Field>
      <label className="check"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />Enable this profile in desired override (does not disable platform defaults)</label>
    </fieldset>
    {!valid && <p role="alert">Choose 2–10 current eligible models and a fallback in that pool.</p>}
    <button className="btn primary" disabled={busy || !valid} onClick={() => void save()}>Save audited profile</button>
  </section>;
}