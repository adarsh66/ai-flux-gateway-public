import { useState, type FormEvent } from "react";
import { ApiError } from "../client";
import { ErrorState, Field, Pager, useAsync } from "../components/ui";
import { isRelaxation, migrateLegacySafety, SAFETY_CATEGORIES, safetyLabel } from "../managed";
import { useSession } from "../session";
import type { GatewayConfigurationUnion, GatewaySettings, PocGatewayConfiguration, PocLimits, SafetyConfiguration } from "../types";
import { RevisionHistory } from "./RevisionHistory";

export const POC_DEFAULTS: PocGatewayConfiguration = { schema_version: 3,
  defaults: { rpm: 60, tpm: 2048, token_quota: 10000, request_quota: 1000 },
  safety: migrateLegacySafety(1), overrides: [] };
export const isPoc = (c: GatewayConfigurationUnion | null | undefined): c is PocGatewayConfiguration => !!c && "schema_version" in c && c.schema_version === 3;
export function pocEffective(c: PocGatewayConfiguration, org: string, sub: string) {
  let limits = c.defaults, safety = c.safety, limitsSource = "POC defaults", safetySource = "POC defaults";
  for (const sid of [null, ...(sub ? [sub] : [])]) {
    const o = c.overrides.find((x) => x.organization_id === org && x.subscription_id === sid);
    if (o?.limits) { limits = o.limits; limitsSource = sid ? "subscription override" : "organization override"; }
    if (o?.safety) { safety = o.safety; safetySource = sid ? "subscription override" : "organization override"; }
  }
  return { limits, safety, limitsSource, safetySource };
}
const labels: Record<keyof PocLimits, string> = { rpm: "Requests per minute per model", tpm: "Tokens per minute per model", token_quota: "Daily tokens per model", request_quota: "Calls per subscription / 86400 seconds" };

export function PocControlsForm({ row, refresh, safetyPage = false }: { row: GatewaySettings; refresh: () => void; safetyPage?: boolean }) {
  const { api } = useSession();
  const initial = isPoc(row.desired?.configuration) ? row.desired.configuration : row.effective_defaults ?? POC_DEFAULTS;
  const [config, setConfig] = useState(initial);
  const [version, setVersion] = useState(row.version);
  const [org, setOrg] = useState("");
  const [sub, setSub] = useState("");
  const [offset, setOffset] = useState(0);
  const [reason, setReason] = useState("");
  const [approved, setApproved] = useState(false);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const orgs = useAsync(() => api.organizations(), [api]);
  const targets = useAsync(() => org ? api.gatewayTargets(offset, 100, org) : Promise.resolve(undefined), [api, org, offset]);
  const current = pocEffective(config, org, sub);
  const original = pocEffective(initial, org, sub);
  const target = config.overrides.find((o) => o.organization_id === org && o.subscription_id === (sub || null));
  const override = safetyPage ? target?.safety : target?.limits;
  const pending = !!row.desired && row.desired.state !== "published";
  const conflict = version !== row.version;
  const relaxing = isRelaxation(current.safety, original.safety);
  const valid = safetyPage ? SAFETY_CATEGORIES.every((k) => Number.isInteger(current.safety[k]) && current.safety[k] >= 0 && current.safety[k] <= 7) :
    (Object.keys(labels) as (keyof PocLimits)[]).every((k) => Number.isInteger(current.limits[k]) && current.limits[k] >= 1 && current.limits[k] <= POC_DEFAULTS.defaults[k]);

  function edit(value: PocLimits | SafetyConfiguration | null) {
    const key = safetyPage ? "safety" : "limits";
    if (!org) setConfig((c) => ({ ...c, [safetyPage ? "safety" : "defaults"]: value } as PocGatewayConfiguration));
    else setConfig((c) => {
      const old = c.overrides.find((o) => o.organization_id === org && o.subscription_id === (sub || null));
      const next = { organization_id: org, subscription_id: sub || null, limits: null, safety: null, ...old, [key]: value };
      return { ...c, overrides: [...c.overrides.filter((o) => o !== old), ...(next.limits || next.safety ? [next] : [])] };
    });
    setApproved(false); setAck(false);
  }
  function load(c?: GatewayConfigurationUnion) {
    setConfig(isPoc(c) ? c : initial); setVersion(row.version); setApproved(false); setAck(false); setError(undefined);
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!valid || busy || pending || conflict || !approved || !reason.trim() || (safetyPage && relaxing && !ack)) return;
    setBusy(true); setError(undefined);
    try {
      const next = safetyPage ? await api.saveContentSafetySettings(row.scope, version, current.safety, reason.trim(), ack,
        { organization_id: org || null, subscription_id: sub || null, inherit: !!org && !override }) :
        await api.saveGatewaySettings(row.scope, version, config, reason.trim());
      if (isPoc(next.desired?.configuration)) setConfig(next.desired.configuration);
      setVersion(next.version); setReason(""); setApproved(false); setAck(false);
    } catch (e) { setError(e instanceof ApiError ? e.detail : "Publication failed. Edits retained."); }
    finally { setBusy(false); refresh(); }
  }
  async function reconcile() {
    setBusy(true);
    try { await api.reconcileGatewaySettings(row.scope, row.version); }
    catch (e) { setError(e instanceof ApiError ? e.detail : "Reconciliation failed."); }
    finally { setBusy(false); refresh(); }
  }
  return <section className="panel" aria-label="Optional POC controls">
    <h2>{safetyPage ? "Organization and subscription safety" : "Organization and subscription limits"}</h2>
    <p>New active aiflux product subscriptions are usable immediately with defaults. Overrides are optional, not access approvals. API and playground share /dev/llm/v1.</p>
    <p role="status">Revision {row.version}; published {row.published_version ?? "none"}; {row.desired?.state ?? "defaults"}. Published means management-plane readback, not traffic proven.</p>
    {(error || row.desired?.error) && <ErrorState message={error ?? row.desired?.error ?? ""} />}
    {conflict && <p role="alert">Server revision changed. Edits retained; reload before publishing.</p>}
    {pending && <button className="btn" disabled={busy} onClick={() => void reconcile()}>Retry publication</button>}
    <form onSubmit={(e) => void save(e)} className="gateway-form">
      <Field label="Organization">{(id) => <select id={id} value={org} onChange={(e) => { setOrg(e.target.value); setSub(""); setOffset(0); setApproved(false); setAck(false); }}><option value="">POC defaults</option>{orgs.data?.items.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>}</Field>
      <Field label="Subscription (optional)">{(id) => <select id={id} disabled={!org} value={sub} onChange={(e) => { setSub(e.target.value); setApproved(false); setAck(false); }}><option value="">Organization / all subscriptions</option>{targets.data?.items.map((t) => <option key={t.subscription_id} value={t.subscription_id}>{t.name} ({t.state})</option>)}</select>}</Field>
      {targets.data && <Pager offset={offset} limit={100} total={targets.data.total} onChange={setOffset} />}
      {(orgs.error || targets.error) && <ErrorState message={orgs.error ?? targets.error ?? ""} />}
      <p role="status">Effective source: {safetyPage ? current.safetySource : current.limitsSource}. Subscription overrides organization; organization overrides defaults.</p>
      {org && !override && <button type="button" className="btn" onClick={() => edit(safetyPage ? { ...current.safety } : { ...current.limits })}>Add optional {sub ? "subscription" : "organization"} override</button>}
      {org && override && <button type="button" className="btn" onClick={() => edit(null)}>Remove override (inherit)</button>}
      <fieldset disabled={!!org && !override}>
        {safetyPage ? <>
          {SAFETY_CATEGORIES.map((k) => <Field key={k} label={`${safetyLabel[k]} threshold (0–7)`}>{(id) => <input id={id} type="number" min={0} max={7} step={1} value={Number.isNaN(current.safety[k]) ? "" : current.safety[k]} onChange={(e) => edit({ ...current.safety, profile: "Custom", [k]: e.target.value === "" ? NaN : Number(e.target.value) })} />}</Field>)}
          <p>Lower is stricter. Zero is not Off. The same thresholds apply to original input, redacted input and output.</p>
          <label><input type="checkbox" checked disabled />Prompt shield, input/output scanning and PII (mandatory)</label>
          <label><input type="checkbox" checked={false} disabled />Protected material detection (unavailable)</label>
        </> : (Object.keys(labels) as (keyof PocLimits)[]).map((k) => <Field key={k} label={labels[k]} hint={`Operator ceiling ${POC_DEFAULTS.defaults[k]}`}>{(id, d) => <input id={id} aria-describedby={d} type="number" min={1} max={POC_DEFAULTS.defaults[k]} step={1} value={Number.isNaN(current.limits[k]) ? "" : current.limits[k]} onChange={(e) => edit({ ...current.limits, [k]: e.target.value === "" ? NaN : Number(e.target.value) })} />}</Field>)}
      </fieldset>
      {!safetyPage && <p>Read-only: 60-second RPM window, daily token period, existing 86400-second call counter, output1024, retries0. Concurrency and monthly quotas unavailable. Counter keys and reset semantics are unchanged.</p>}
      {safetyPage && <p>Foundry shared baseline is independent of APIM overrides; it is never relaxed by this form. Deployment bindings require operator metadata verification. GLM ModelArts: Foundry RAI not applicable; APIM safety applies.</p>}
      {safetyPage && relaxing && <label><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />I acknowledge this relaxes APIM safety, not the shared Foundry baseline.</label>}
      <Field label="Reason for this revision">{(id) => <input id={id} required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
      <label><input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} />I approve these optional settings.</label>
      <button className="btn primary" disabled={!valid || busy || pending || conflict || !approved || !reason.trim() || (safetyPage && relaxing && !ack)}>Publish {safetyPage ? "safety" : "gateway"} settings</button>
    </form>
    <details><summary>Revision history and recovery</summary>
      <button className="btn" disabled={busy} onClick={() => load(row.desired?.configuration)}>Reload desired settings</button>
      <button className="btn" disabled={busy || !row.version} onClick={() => void reconcile()}>Check APIM / reconcile</button>
      <RevisionHistory load={(o) => api.gatewaySettingsHistory(row.scope, o)} deps={[api, row.scope, row.version, row.desired?.state]} disabled={busy || pending} onUse={load} />
    </details>
  </section>;
}