import { useEffect, useRef, useState } from "react";
import { ApiError } from "../client";
import { useSession } from "../session";
import type { OrganizationModelAccess } from "../types";
import { AsyncView, PageHeader, useAsync } from "../components/ui";

export function OrganizationModelAccessPage() {
  const { api } = useSession();
  const organizations = useAsync(() => api.organizations(), [api]);
  const [org, setOrg] = useState("");
  const [card, setCard] = useState<OrganizationModelAccess>();
  const [denies, setDenies] = useState<string[]>([]);
  const [auto, setAuto] = useState(true);
  const [search, setSearch] = useState("");
  const [vendor, setVendor] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const writing = useRef(false);
  const scope = useRef(0);
  const dirty = !!card && (auto !== card.auto_enabled || JSON.stringify([...denies].sort()) !== JSON.stringify([...card.denied_models].sort()));
  useEffect(() => {
    const generation = ++scope.current;
    setCard(undefined); setError("");
    if (!org) return;
    void api.organizationModelAccess(org).then(next => {
      if (scope.current !== generation) return;
      setCard(next); setDenies(next.denied_models); setAuto(next.auto_enabled);
    }).catch(e => { if (scope.current === generation) setError(String(e)); });
    return () => { ++scope.current; };
  }, [api, org]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    const leave = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (link && !event.defaultPrevented && !window.confirm("Discard unsaved model access changes?")) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    document.addEventListener("click", leave, true);
    return () => { window.removeEventListener("beforeunload", warn); document.removeEventListener("click", leave, true); };
  }, [dirty]);
  useEffect(() => {
    if (!org || !card || card.state === "applied") return;
    const generation = scope.current;
    let active = true;
    let pending = false;
    const timer = setInterval(() => {
      if (pending) return;
      pending = true;
      void api.organizationModelAccess(org).then(next => {
        // Status-only refresh must never replace a draft or its CAS base.
        if (active && scope.current === generation) setCard(old => old && ({ ...old,
          applied_version: next.applied_version, applied_sha256: next.applied_sha256,
          state: next.state, error: next.error, attempts: next.attempts,
          applied_at: next.applied_at, next_attempt_at: next.next_attempt_at }));
      }).catch(() => {}).finally(() => { pending = false; });
    }, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [api, org, card?.state]);
  async function save() {
    if (!card || writing.current) return;
    writing.current = true;
    const generation = scope.current;
    setBusy(true); setError("");
    try {
      const next = await api.saveOrganizationModelAccess(org, { expected_version: card.version,
        denied_models: denies, auto_enabled: auto, reason: "Organization model access editor" });
      if (scope.current === generation) { setCard(next); setDenies(next.denied_models); setAuto(next.auto_enabled); }
    } catch (e) {
      if (scope.current === generation) setError(e instanceof ApiError && e.status === 409
        ? "Conflict: another administrator saved. Your draft is retained. Reload to review the current version." : String(e));
    } finally { writing.current = false; if (scope.current === generation) setBusy(false); }
  }
  async function reload() {
    if (dirty && !window.confirm("Discard unsaved model access changes?")) return;
    const generation = scope.current;
    try {
      const next = await api.organizationModelAccess(org);
      if (scope.current === generation) { setCard(next); setDenies(next.denied_models); setAuto(next.auto_enabled); setError(""); }
    } catch (e) { if (scope.current === generation) setError(String(e)); }
  }
  const rows = card?.items.filter(m => (!vendor || m.provider === vendor) && `${m.display_name} ${m.id}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  return <>
    <PageHeader title="Organization model access" subtitle="Permissions apply to every subscription in the organization. All current and future models are enabled by default; only explicit denials are stored." />
    <AsyncView state={organizations}>{page => <label>Organization <select value={org} disabled={busy} onChange={event => {
      if (dirty && !window.confirm("Discard unsaved model access changes?")) return;
      setBusy(false); setOrg(event.target.value);
    }}><option value="">Select organization</option>{page.items.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>}</AsyncView>
    {error && <p role="alert" className="notice bad">{error}</p>}
    {card && <section className="card">
      <p role="status">Saved v{card.version} · Applied {card.applied_version === null ? "not yet" : `v${card.applied_version}`} · {card.state === "applied" ? "Applied" : card.state === "error" ? "Error" : "Applying"}{card.error && ` · ${card.error}`}</p>
      <p>Applied hash: {card.applied_sha256 ?? "not yet"} · Failed attempts: {card.attempts ?? 0} · Applied at: {card.applied_at ?? "not yet"} · Next attempt: {card.next_attempt_at ?? "not scheduled"}</p>
      <p>Old access may remain until gateway propagation completes. Applied means publication and readback verified, not instantaneous delivery to every edge. Pending grants are not advertised as usable.</p>
      <label><input type="checkbox" checked={auto} disabled={busy} onChange={e => setAuto(e.target.checked)} />Auto routing</label>
      <p>Microsoft Decision-1 is an informational internal scoring dependency, not a chat permission.</p>
      <label>Search models <input value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label>Provider <select value={vendor} onChange={e => setVendor(e.target.value)}><option value="">All providers</option>{[...new Set(card.items.map(m => m.provider))].map(p => <option key={p}>{p}</option>)}</select></label>
      <div><button disabled={busy} onClick={() => setDenies([])}>Enable all</button><button disabled={busy} onClick={() => setDenies([...new Set([...denies, ...card.items.filter(m => m.model_kind === "chat").map(m => m.id)])])}>Disable all current models</button></div>
      <p className="notice warn">Disable all denies current chat models only. Future models will still be enabled by default. Missing prices never deny access.</p>
      <table><thead><tr><th>Allowed preference</th><th>Model</th><th>Provider</th><th>Global status</th><th>Pricing availability</th></tr></thead><tbody>{rows.map(m => <tr key={m.id}>
        <td>{m.model_kind === "chat" ? <input aria-label={`Allow ${m.id}`} type="checkbox" disabled={busy} checked={!denies.includes(m.id)} onChange={e => setDenies(old => e.target.checked ? old.filter(a => a !== m.id) : [...old, m.id])} /> : "Informational"}</td>
        <td>{m.display_name} <small>{m.id}</small></td><td>{m.provider}</td><td>{m.globally_enabled ? "Available" : "Not usable globally; preference retained"}</td>
        <td>Internal: {m.internal_price_available ? "available" : "missing"} · External: {m.external_price_available ? "available" : "missing"}</td>
      </tr>)}</tbody></table>
      <button disabled={!dirty || busy} onClick={() => void save()}>{busy ? "Saving…" : "Save model access"}</button>
      <button disabled={busy} onClick={() => void reload()}>Reload / discard draft</button>
      <button disabled={busy || card.state === "applied"} onClick={() => {
        if (writing.current) return;
        writing.current = true; setBusy(true);
        const generation = scope.current;
        void api.retryOrganizationModelAccess(org).then(next => { if (scope.current === generation) setCard(old => old && ({ ...old, state: next.state, error: next.error })); })
          .catch(e => { if (scope.current === generation) setError(String(e)); })
          .finally(() => { writing.current = false; if (scope.current === generation) setBusy(false); });
      }}>Retry publication</button>
    </section>}
  </>;
}