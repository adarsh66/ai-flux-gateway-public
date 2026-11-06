import { useEffect, useRef, useState } from "react";
import { ApiError } from "../client";
import { useSession } from "../session";
import type { ExternalRateInput, RateCard, RateInput, RateOrigin, RateRow, PricingHistoryDetail, PricingHistoryPage, PricingHistoryPoint } from "../types";
import { isDecimal } from "../validation";
import { AsyncView, Badge, Table, fmtDate, useAsync } from "../components/ui";
import { PricingRevisionViewer } from "./PricingRevisionViewer";

type Draft = { input: string; output: string; cached: string; write: string };
type Drafts = Record<string, Draft>;

function AutoPricingStatus({ card }: { card: RateCard }) {
  const { api } = useSession();
  const [status, setStatus] = useState(card.auto_pricing);
  useEffect(() => {
    setStatus(card.auto_pricing);
    if (!card.auto_pricing?.enabled) return;
    let active = true;
    let inFlight = false;
    const timer = setInterval(() => {
      if (inFlight) return;
      inFlight = true;
      void api.rateCard().then((next) => {
        if (active) setStatus(next.auto_pricing);
      }).catch(() => { /* Keep last known status; never erase unsaved drafts. */ })
        .finally(() => { inFlight = false; });
    }, 15000);
    return () => { active = false; clearInterval(timer); };
  }, [api, card.auto_pricing]);
  if (!status?.enabled) return null;
  const pending = status.state === "pending" || status.stale === true;
  const applied = status.applied_revision ?? (status.source === "last-good-or-packaged-default"
    ? "Last-good prices or packaged defaults (revision unavailable)" : "Packaged defaults");
  return <p className={`notice ${status.state === "applied" && !pending ? "ok" : "warn"}`} role="status" aria-label="Auto pricing sync status">
    Auto pricing · Saved: {status.desired_revision ?? card.revision} · Applied: {applied}
    {pending ? " · Automatic sync pending" : status.state === "applied" ? " · In sync" : " · Using packaged defaults"}
    {(status.stale || (pending && status.source === "rate-card")) && " · Last-good prices remain active"}
    {status.source === "packaged-default" && " · Estimated defaults remain active"}
    {status.error && <> · {status.error}</>}
    {status.applied_at && <> · Applied at: {fmtDate(status.applied_at)}</>}
    {pending && <> · Sync retries automatically{status.next_attempt_at && <>; next attempt: {fmtDate(status.next_attempt_at)}</>}.</>}
    {" · Pricing sync does not block saving rates, subscriptions, the Playground or API calls. Missing rates are not free."}
  </p>;
}

const ORIGIN: Record<RateOrigin, { label: string; tone: "ok" | "warn" | "neutral" | "info" }> = {
  configured: { label: "Configured", tone: "ok" },
  platform_default: { label: "Estimated default", tone: "warn" },
  public_list: { label: "Public list rate", tone: "info" },
  sourced_proxy: { label: "Proxy rate", tone: "warn" },
  tbc: { label: "Unconfirmed", tone: "warn" },
  unknown: { label: "No rate yet", tone: "neutral" },
};

const draftOf = (r: RateRow): Draft => ({ input: r.input ?? "", output: r.output ?? "", cached: r.cached ?? "", write: r.write ?? "" });
const defaultOf = (r: RateRow): Draft => ({ input: r.default_input ?? "", output: r.default_output ?? "", cached: r.default_cached ?? "", write: r.default_write ?? "" });
const same = (a: Draft, b: Draft) => (Object.keys(a) as (keyof Draft)[]).every((k) => a[k].trim() === b[k].trim());
const validRate = (value: string) => isDecimal(value) && Number(value.trim()) <= 100000;

export function validateRates(card: RateCard, drafts: Drafts): { ok: true; rates: RateInput[] } | { ok: false; error: string } {
  const rates: RateInput[] = [];
  for (const row of card.items) {
    const d = drafts[row.model];
    if (!d || same(d, draftOf(row))) continue;
    if (row.model_kind === "scoring") {
      if (!validRate(d.input)) return { ok: false, error: `${row.model}: input rate must be a non-negative decimal up to 100000 with at most 8 decimal places (e.g. 0.042).` };
      if ([d.output, d.cached, d.write].some((value) => value.trim())) {
        return { ok: false, error: `${row.model}: scoring supports input only; output and cache rates must be blank (N/A).` };
      }
      rates.push({ model: row.model, input: d.input.trim(), output: null, cached: null, write: null });
      continue;
    }
    if (!validRate(d.input) || !validRate(d.output)) return { ok: false, error: `${row.model}: input and output rates must be non-negative decimals up to 100000 with at most 8 decimal places (e.g. 2.50).` };
    for (const k of ["cached", "write"] as const) {
      if (d[k].trim() && !validRate(d[k])) return { ok: false, error: `${row.model}: cache rates must be blank or non-negative decimals up to 100000 with at most 8 decimal places.` };
    }
    rates.push({ model: row.model, input: d.input.trim(), output: d.output.trim(), cached: d.cached.trim() || null, write: d.write.trim() || null });
  }
  return { ok: true, rates };
}

export function validateExternalRates(card: RateCard, drafts: Drafts, operations: Record<string, ExternalRateInput["operation"]>, organization: boolean): { ok: true; rates: ExternalRateInput[] } | { ok: false; error: string } {
  const rates: ExternalRateInput[] = [];
  for (const row of card.items) {
    const operation = operations[row.model];
    if (!operation) continue;
    if (operation === "inherit" && !organization) return { ok: false, error: "The external default cannot inherit another card." };
    if (operation !== "set") { rates.push({ model: row.model, operation }); continue; }
    // Validate explicit sets even when their numeric values equal inherited values.
    const result = validateRates({ ...card, items: [{ ...row, input: null, output: null, cached: null, write: null }] }, drafts);
    if (!result.ok) return result;
    if (result.rates.length === 0) return { ok: false, error: `${row.model}: enter a rate or mark it unknown explicitly.` };
    rates.push({ ...result.rates[0]!, operation: "set" });
  }
  return { ok: true, rates };
}

export function historicalDraft(card: RateCard, detail: PricingHistoryDetail, external: boolean) {
  const drafts: Drafts = Object.fromEntries(card.items.map((r) => [r.model, draftOf(r)]));
  const operations: Record<string, ExternalRateInput["operation"]> = {};
  const skipped = [...detail.skipped];
  let loaded = 0;
  for (const row of card.items) {
    const old = detail.items.find((r) => r.model === row.model);
    const compatible = old && old.state !== "unavailable" && old.provider === row.provider && old.region === row.region
      && old.model_version === row.model_version && old.sku === row.sku
      && old.model_kind === (row.model_kind ?? "chat")
      && JSON.stringify(old.billing_dimensions) === JSON.stringify(row.billing_dimensions ?? ["input", "output"]);
    if (!compatible || (!external && old.state === "unknown")) {
      skipped.push(`${row.model}: ${old?.note ?? "historical identity/vector unavailable"}; current value unchanged`);
      continue;
    }
    drafts[row.model] = { input: old.input ?? "", output: old.output ?? "", cached: old.cached ?? "", write: old.write ?? "" };
    if (external) operations[row.model] = old.state === "unknown" ? "unknown" : "set";
    loaded++;
  }
  for (const old of detail.items) if (!card.items.some((r) => r.model === old.model)) skipped.push(`${old.model}: retired row skipped`);
  return { drafts, operations, skipped, loaded };
}

function sourceLabel(point: PricingHistoryPoint) {
  return point.internal_version != null ? `internal v${point.internal_version}`
    : `default v${point.default_version ?? 0} / organization v${point.organization_version ?? 0}`;
}

function Editor({ card: initialCard, saved, setSaved, onSaved, external, organizationId, onDirty }: { card: RateCard; saved?: string; setSaved: (s?: string) => void; onSaved: (c: RateCard) => void; external: boolean; organizationId: string; onDirty: (dirty: boolean) => void }) {
  const { api } = useSession();
  const [card, setCard] = useState(initialCard);
  const [drafts, setDrafts] = useState<Drafts>(() => Object.fromEntries(card.items.map((r) => [r.model, draftOf(r)])));
  const [operations, setOperations] = useState<Record<string, ExternalRateInput["operation"]>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [confirmReload, setConfirmReload] = useState(false);
  const [history, setHistory] = useState<PricingHistoryPage>();
  const [historyError, setHistoryError] = useState<string>();
  const [historyBusy, setHistoryBusy] = useState(false);
  const [selection, setSelection] = useState("");
  const [source, setSource] = useState<PricingHistoryPoint>();
  const [summary, setSummary] = useState<string[]>([]);
  const [confirmHistory, setConfirmHistory] = useState(false);
  const [staged, setStaged] = useState<{ card: RateCard; detail: PricingHistoryDetail; draft: ReturnType<typeof historicalDraft> }>();
  const request = useRef(0);
  const lock = useRef(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  async function loadHistory(offset = 0) {
    if (lock.current) return;
    lock.current = true;
    setHistoryBusy(true);
    setHistoryError(undefined);
    try {
      const next = await api.pricingHistory(external, organizationId || undefined, offset);
      if (active.current) setHistory((previous) => ({ ...next, items: offset ? [...(previous?.items ?? []), ...next.items.filter((p) => !previous?.items.some((q) => p.id === q.id))] : next.items }));
    } catch (err) {
      if (active.current) setHistoryError(err instanceof ApiError ? err.detail : "Could not load pricing history.");
    } finally { lock.current = false; if (active.current) setHistoryBusy(false); }
  }
  useEffect(() => { void loadHistory(); }, [api, external, organizationId]);
  const result = external ? validateExternalRates(card, drafts, operations, !!organizationId) : validateRates(card, drafts);
  const pending = external ? Object.keys(operations).length : result.ok ? result.rates.length : card.items.filter((r) => !same(drafts[r.model] ?? draftOf(r), draftOf(r))).length;
  useEffect(() => { if (active.current) onDirty(pending > 0 || busy || historyBusy); }, [pending, busy, historyBusy, onDirty]);
  function installHistory(next: { card: RateCard; detail: PricingHistoryDetail; draft: ReturnType<typeof historicalDraft> }) {
    setCard(next.card); // Latest head is the CAS baseline; never the historical version.
    setDrafts(next.draft.drafts);
    setOperations(next.draft.operations);
    setSource(next.detail.source);
    setSummary(next.draft.skipped);
    setStaged(undefined);
    setSaved(undefined);
  }
  async function loadRevision() {
    setConfirmHistory(false);
    if (!selection || lock.current || busy) return;
    const generation = ++request.current;
    lock.current = true;
    setHistoryBusy(true);
    setHistoryError(undefined);
    try {
      const detail = await api.pricingHistoryDetail(external, selection, organizationId || undefined);
      const latest = external ? await api.externalRateCard(organizationId || undefined) : await api.rateCard();
      if (!active.current || request.current !== generation) return;
      const draft = historicalDraft(latest, detail, external);
      if (!draft.loaded) throw new Error("No reconstructible compatible historical rows; editor unchanged.");
      const next = { card: latest, detail, draft };
      if (detail.requires_acknowledgement || draft.skipped.length) setStaged(next);
      else installHistory(next);
    } catch (err) {
      if (active.current && request.current === generation) setHistoryError(err instanceof ApiError ? err.detail : err instanceof Error ? err.message : "Could not load the historical draft; editor unchanged.");
    } finally { lock.current = false; if (active.current) setHistoryBusy(false); }
  }
  const edit = (row: RateRow, k: keyof Draft, value: string) => {
    setSaved(undefined);
    if (external) setOperations((ops) => ({ ...ops, [row.model]: "set" }));
    setDrafts((d) => ({ ...d, [row.model]: { ...(d[row.model] ?? draftOf(row)), [k]: value } }));
  };
  const externalOperation = (r: RateRow, operation: "unknown" | "inherit") => {
    setSaved(undefined);
    setOperations((ops) => ({ ...ops, [r.model]: operation }));
    setDrafts((d) => ({ ...d, [r.model]: operation === "inherit" ? defaultOf(r) : { input: "", output: "", cached: "", write: "" } }));
  };
  const resetRow = (r: RateRow) => {
    setSaved(undefined);
    setDrafts((d) => ({ ...d, [r.model]: defaultOf(r) }));
  };
  const resetAll = () => {
    setSaved(undefined);
    setDrafts(Object.fromEntries(card.items.map((r) => [r.model, defaultOf(r)])));
  };

  async function reloadLatest() {
    if (lock.current) return;
    lock.current = true;
    setConfirmReload(false);
    setBusy(true);
    setError(undefined);
    try {
      const next = external ? await api.externalRateCard(organizationId || undefined) : await api.rateCard();
      if (!active.current) return;
      setDrafts(Object.fromEntries(next.items.map((r) => [r.model, draftOf(r)])));
      setOperations({});
      setCard(next);
      setSource(undefined);
      setSelection("");
      setSummary([]);
      setSaved(undefined);
      onDirty(false);
      onSaved(next);
    } catch (err) {
      if (active.current) setError(err instanceof ApiError ? err.detail : "Could not reload the rates. Your edits are preserved.");
    } finally {
      lock.current = false;
      if (active.current) setBusy(false);
    }
  }

  async function save() {
    if (lock.current || busy) return;
    if (!result.ok) return setError(result.error);
    lock.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const next = external
        ? await api.saveExternalRateCard({ expected_version: card.version, rates: (result as { ok: true; rates: ExternalRateInput[] }).rates, reason: source ? `Restore prices from ${sourceLabel(source)} (${source.effective_at}); saved as a new effective-now revision`.slice(0, 500) : "External price update from the admin portal" }, organizationId || undefined)
        : await api.saveRateCard(card.version, (result as { ok: true; rates: RateInput[] }).rates, source ? `Restore prices from ${sourceLabel(source)} (${source.effective_at}); saved as a new effective-now revision`.slice(0, 500) : "Rate card update from the admin portal");
      if (!active.current) return;
      setDrafts(Object.fromEntries(next.items.map((r) => [r.model, draftOf(r)])));
      setOperations({});
      setCard(next);
      setSource(undefined);
      setSelection("");
      setSummary([]);
      onDirty(false);
      onSaved(next);
      setSaved(next.changed ? `Saved ${result.rates.length} rate change(s).` : "No changes to save.");
    } catch (err) {
      if (active.current) setError(err instanceof ApiError ? err.detail : "Could not save the rates.");
    } finally {
      lock.current = false;
      if (active.current) setBusy(false);
    }
  }

  return (
    <>
      <div className="actions" aria-label="Pricing history">
        <label>Historical revision <select aria-label="Historical revision" value={selection} disabled={busy || historyBusy || !!staged}
          onChange={(e) => { request.current++; setSelection(e.target.value); setConfirmHistory(false); }}>
          <option value="">Current / latest (select a historical draft)</option>
          {history?.items.map((point) => <option key={point.id} value={point.id}>{fmtDate(point.effective_at)} · {sourceLabel(point)} · {point.source}{point.simultaneous ? " · explicit simultaneous bound" : ""}{point.reason ? ` · ${point.reason}` : ""}</option>)}
        </select></label>
        <button type="button" className="btn" disabled={!selection || busy || historyBusy || !!staged} onClick={() => pending ? setConfirmHistory(true) : void loadRevision()}>Load into editor</button>
        {history?.next_offset != null && <button className="btn" disabled={busy || historyBusy} onClick={() => void loadHistory(history.next_offset!)}>Load more revisions</button>}
        {historyBusy && <span role="status">Loading history…</span>}
        {history && !history.items.length && <span>No retained historical revisions.</span>}
      </div>
      {historyError && <p className="notice bad" role="alert">{historyError} <button className="btn" disabled={busy || historyBusy} onClick={() => void loadHistory()}>Retry history</button></p>}
      {confirmHistory && <div role="dialog" aria-modal="true" aria-label="Replace unsaved pricing draft?">
        <p>Loading replaces unsaved edits only after both historical data and the latest head load successfully. It does not save prices.</p>
        <button className="btn" onClick={() => setConfirmHistory(false)}>Cancel</button>
        <button className="btn" onClick={() => void loadRevision()}>Replace draft</button>
      </div>}
      {staged && <div role="dialog" aria-modal="true" aria-label="Acknowledge skipped historical rows">
        <p>Some historical defaults or identities cannot be reconstructed. These current rows stay unchanged; no amounts are guessed.</p>
        <ul>{staged.draft.skipped.map((s, i) => <li key={i}>{s}</li>)}</ul>
        <button className="btn" onClick={() => setStaged(undefined)}>Cancel</button>
        <button className="btn" onClick={() => installHistory(staged)}>Acknowledge skipped rows and load draft</button>
      </div>}
      {source && <p role="status" className="notice warn">Draft copied from {sourceLabel(source)} at {fmtDate(source.effective_at)}. Nothing has been saved. Save appends a new effective-now revision using current version {card.version}.{external && " Historical effective numbers become explicit SET overrides, not inheritance; this freezes these amounts against future default updates. Historical unknown remains explicitly unknown, never zero."}</p>}
      {summary.length > 0 && <details><summary>Historical rows left unchanged or skipped ({summary.length})</summary><ul>{summary.map((s, i) => <li key={i}>{s}</li>)}</ul></details>}
      <div className="actions">
        <button className="btn primary" disabled={busy || historyBusy || !!staged || pending === 0} onClick={() => void save()}>
          {busy ? "Saving…" : pending ? `Save ${pending} change${pending === 1 ? "" : "s"}` : "Save changes"}
        </button>
        {!external && <button className="btn" disabled={busy} onClick={resetAll}>Restore all defaults</button>}
        <button type="button" className="btn" disabled={busy} onClick={() => pending > 0 ? setConfirmReload(true) : void reloadLatest()}>Reload latest</button>
        <span className="muted">Version {card.version} · {card.revision}</span>
      </div>
      {confirmReload && <div role="dialog" aria-modal="true" aria-label="Reload latest rates?">
        <p>Reloading discards unsaved changes after the latest rates load successfully.</p>
        <button type="button" className="btn" onClick={() => setConfirmReload(false)}>Cancel</button>
        <button type="button" className="btn" onClick={() => void reloadLatest()}>Discard changes and reload</button>
      </div>}
      {error && <p role="alert" className="notice bad">{error}</p>}
      {saved && <p role="status" className="notice ok">{saved}</p>}
      <Table caption="Model rates (USD per 1M tokens)" head={["Model", "Provider / region", "Basis", "Input", "Output", "Cached in (optional)", "Cache write (optional)", "Action"]}>
        {card.items.map((r) => {
          const d = drafts[r.model] ?? draftOf(r);
          const origin = ORIGIN[r.origin] ?? ORIGIN.unknown;
          const changed = external ? !!operations[r.model] : !same(d, draftOf(r));
          const atDefault = same(d, defaultOf(r));
          return (
            <tr key={r.model}>
              <th scope="row">{r.model}{changed && <> <Badge tone="info">edited</Badge></>}</th>
              <td>{r.provider} · {r.region}</td>
              <td>
                <Badge tone={origin.tone}>{external ? operations[r.model] === "unknown" ? "Unknown" : operations[r.model] === "inherit" ? "Inherited" : operations[r.model] === "set" ? "Override" : organizationId && /inherit/i.test(r.note ?? "") ? "Inherited" : r.input == null ? "Unknown" : organizationId ? "Override" : "External default" : origin.label}</Badge>
                {external && (operations[r.model] === "inherit" ? !d.input : !operations[r.model] && r.input == null) && <small className="block">Unknown — not free</small>}
                {external && r.note && <div className="muted">{r.note}</div>}
                {r.configured_from && <div className="muted">from {fmtDate(r.configured_from)}</div>}
              </td>
              {(["input", "output", "cached", "write"] as const).map((k) => (
                <td key={k}>
                  <input
                    className="num" inputMode="decimal"
                    disabled={busy || historyBusy || !!staged || (r.model_kind === "scoring" && k !== "input")}
                    value={r.model_kind === "scoring" && k !== "input" ? "N/A" : d[k]}
                    placeholder={k === "cached" || k === "write" ? "not priced" : "0.00"}
                    aria-label={`${r.model} ${k === "write" ? "cache write" : k === "cached" ? "cached input" : k} rate`}
                    onChange={(e) => edit(r, k, e.target.value)}
                  />
                </td>
              ))}
              <td>{external ? <>
                {organizationId && <button className="btn" disabled={busy} onClick={() => externalOperation(r, "inherit")} aria-label={`${r.model} return to default`}>Return to default</button>}
                <button className="btn" disabled={busy} onClick={() => externalOperation(r, "unknown")} aria-label={`${r.model} mark unknown`}>Mark unknown</button>
              </> : <button className="btn" disabled={atDefault || busy} onClick={() => resetRow(r)}>Reset</button>}</td>
            </tr>
          );
        })}
      </Table>
      {!external && <AutoPricingStatus card={card} />}
    </>
  );
}

export function RateCardEditor() {
  const [audience, setAudience] = useState<"internal" | "external">("internal");
  const [viewingRevisions, setViewingRevisions] = useState(false);
  const [organizationId, setOrganizationId] = useState("");
  const [dirty, setDirty] = useState(false);
  const [switchTo, setSwitchTo] = useState<{ audience: "internal" | "external"; organizationId: string }>();
  function switchCard(next: { audience: "internal" | "external"; organizationId: string }) {
    if (next.audience === audience && next.organizationId === organizationId) return;
    if (dirty) { setSwitchTo(next); return; }
    setAudience(next.audience);
    setOrganizationId(next.organizationId);
    setDirty(false);
    setSwitchTo(undefined);
  }
  return <section className="panel">
    <h2>Model rates</h2>
    <div role="tablist" aria-label="Pricing audience">
      <button role="tab" aria-selected={!viewingRevisions && audience === "internal"} onClick={() => { setViewingRevisions(false); switchCard({ audience: "internal", organizationId: "" }); }}>Internal costs</button>
      <button role="tab" aria-selected={!viewingRevisions && audience === "external"} onClick={() => { setViewingRevisions(false); switchCard({ audience: "external", organizationId }); }}>External prices</button>
      <button role="tab" aria-selected={viewingRevisions} onClick={() => setViewingRevisions(true)}>View revisions</button>
    </div>
    <div hidden={viewingRevisions}>
    {switchTo && <div role="dialog" aria-modal="true" aria-label="Discard unsaved rate changes?">
      <p>Switching cards discards unsaved changes. An in-flight save may still finish for its original card.</p>
      <button className="btn" onClick={() => setSwitchTo(undefined)}>Cancel</button>
      <button className="btn" onClick={() => { setAudience(switchTo.audience); setOrganizationId(switchTo.organizationId); setDirty(false); setSwitchTo(undefined); }}>Discard changes</button>
    </div>}
    <CardScope key={`${audience}:${organizationId}`} external={audience === "external"} organizationId={organizationId} onDirty={setDirty} onOrganization={(id) => switchCard({ audience: "external", organizationId: id })} />
    </div>
    {viewingRevisions && <PricingRevisionViewer />}
  </section>;
}

function CardScope({ external, organizationId, onDirty, onOrganization }: { external: boolean; organizationId: string; onDirty: (dirty: boolean) => void; onOrganization: (id: string) => void }) {
  const { api } = useSession();
  const state = useAsync(() => external ? api.externalRateCard(organizationId || undefined) : api.rateCard(), [api, external, organizationId]);
  const orgs = useAsync(() => external ? api.organizations() : Promise.resolve({ items: [], total: 0 }), [api, external]);
  const [override, setOverride] = useState<RateCard>();
  const [saved, setSaved] = useState<string>();
  const card = override ?? state.data;
  return (
    <>
      {external && <label>External price scope <select aria-label="External price scope" value={organizationId} onChange={(e) => onOrganization(e.target.value)}>
        <option value="">External default</option>
        {orgs.data?.items.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}
      </select></label>}
      {external && orgs.error && <p role="alert">Could not load organizations. {orgs.error} <button className="btn" onClick={orgs.reload}>Retry organizations</button></p>}
      <p className="muted">
        {external ? "External prices are customer estimates, not internal costs or invoices. Organizations automatically inherit the external default for rows without overrides, including future organizations; no initialization or approval is needed. Unknown is not free. Returning to default removes an organization override; it does not copy rates."
          : "Internal costs are used for administrator showback and Auto pricing only. Restore defaults remains internal-only. Rates and missing rates never block subscriptions, the Playground or API calls."}
      </p>
      <AsyncView state={{ ...state, data: card }} isEmpty={(c) => c.items.length === 0} emptyTitle="No models available" emptyHint="Rates appear here once models are accepted in the catalog.">
        {(c) => <Editor key={`${external ? "external" : "internal"}:${organizationId}:${c.version}`} card={c} external={external} organizationId={organizationId} onDirty={onDirty} saved={saved} setSaved={setSaved} onSaved={setOverride} />}
      </AsyncView>
    </>
  );
}
