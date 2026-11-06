import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { ApiError } from "../client";
import { useSession } from "../session";
import type { DeletionCollection, DeletionPreview, DeletionResult } from "../types";
import { Field } from "./ui";

/** Terminal archive, deliberately separate from reversible Disable/Suspend. */
export function DeletionDialog({ collection, entityId, onClose, onChanged, onAttempt, onUncertain }: {
  collection: DeletionCollection;
  entityId: string;
  onClose: () => void;
  onChanged: (result: DeletionResult) => void;
  onAttempt?: () => void;
  onUncertain?: () => void;
}) {
  const { api } = useSession();
  const title = useId(), description = useId();
  const modal = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const latch = useRef(false), alive = useRef(true);
  const [preview, setPreview] = useState<DeletionPreview>();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<DeletionResult>();

  async function load() {
    setLoading(true);
    try {
      const data = await api.deletionPreview(collection, entityId);
      if (alive.current) { setPreview(data); setError(undefined); }
    } catch (e) {
      if (alive.current) setError(e instanceof ApiError ? e.detail : "Could not load the deletion preview.");
    } finally { if (alive.current) setLoading(false); }
  }
  useEffect(() => {
    alive.current = true;
    void load();
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const siblings = Array.from(document.body.children).filter(e => e !== modal.current?.parentElement);
    const prior = siblings.map(e => e.getAttribute("inert"));
    siblings.forEach(e => e.setAttribute("inert", ""));
    cancel.current?.focus();
    return () => {
      alive.current = false;
      siblings.forEach((e, i) => prior[i] === null ? e.removeAttribute("inert") : e.setAttribute("inert", prior[i]!));
      if (previous?.isConnected) previous.focus();
      else document.querySelector<HTMLElement>("h1")?.focus();
    };
    // This component is keyed by target. Ignore async results after unmount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, collection, entityId]);

  const valid = !loading && preview?.can_delete && confirmation === preview.label && !!reason.trim() && !busy;
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid || latch.current) return;
    latch.current = true;
    setBusy(true); setError(undefined);
    onAttempt?.();
    try {
      const response = await api.deleteEntity(collection, entityId, { confirmation, reason: reason.trim() });
      if (!alive.current) return;
      setResult(response);
      onChanged(response);
      if (response.status === "archived") onClose();
    } catch (e) {
      if (!alive.current) return;
      onUncertain?.();
      // Dependency counts and protection may change after the original preview.
      await load();
      if (alive.current) setError(e instanceof ApiError ? e.detail : "Deletion outcome is unknown. Reload the preview and retry the same record; do not assume access was revoked.");
    } finally {
      latch.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return createPortal(<div className="deletion-backdrop">
    <div ref={modal} tabIndex={-1} className="panel deletion-dialog" role="dialog" aria-modal="true" aria-labelledby={title} aria-describedby={description}
      onKeyDown={e => {
        if (e.key === "Escape") { e.preventDefault(); if (!latch.current) onClose(); }
        if (e.key === "Tab") {
          const controls = Array.from(modal.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]') ?? []);
          const first = controls[0], last = controls[controls.length - 1];
          if (!first) { e.preventDefault(); modal.current?.focus(); return; }
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
        }
      }}>
      <h2 id={title}>Delete — archive and revoke access</h2>
      <p id={description}>This is permanent, not Disable or Suspend. Historical usage, pricing, budgets and audit records are retained. No financial history or Entra directory account is deleted.</p>
      {loading && <p role="status">Loading current dependencies…</p>}
      {preview && <>
        <p><strong>{preview.label}</strong></p><p>{preview.effect}</p>
        {collection === "organizations" && <>
          <ul aria-label="Dependencies">
            <li>Subscriptions: {preview.dependencies.subscriptions}</li>
            <li>Local users: {preview.dependencies.users}</li>
            <li>Memberships: {preview.dependencies.members}</li>
          </ul>
          <p>Disabled and pending children still block deletion. Archive linked local users first; archive independent memberships under Members.</p>
          {!busy && <nav aria-label="Manage dependencies">
            <Link to={`/subscriptions?organization_id=${encodeURIComponent(entityId)}`} onClick={onClose}>Manage subscriptions</Link>{" · "}
            <Link to={`/local-users?organization_id=${encodeURIComponent(entityId)}`} onClick={onClose}>Manage local users</Link>{" · "}
            <Link to={`/members?organization_id=${encodeURIComponent(entityId)}`} onClick={onClose}>Manage members</Link>
          </nav>}
        </>}
        {!!preview.blockers.length && <ul role="alert">{preview.blockers.map(b => <li key={b}>{b}</li>)}</ul>}
      </>}
      {result && <p role={result.status === "failed" ? "alert" : "status"} className={`notice ${result.status === "failed" ? "bad" : ""}`}>{result.status}: {result.message}</p>}
      {error && <p role="alert" className="notice bad">{error}</p>}
      <form onSubmit={e => void submit(e)} aria-busy={busy}>
        <Field label="Type the exact record label" hint={preview ? `Type exactly: ${preview.label}` : "Wait for the current preview."}>{(id, d) =>
          <input id={id} aria-describedby={d} autoComplete="off" value={confirmation} disabled={busy || loading} maxLength={255} onChange={e => setConfirmation(e.target.value)} />}</Field>
        <Field label="Audit reason">{id => <textarea id={id} value={reason} maxLength={500} disabled={busy} required onChange={e => setReason(e.target.value)} />}</Field>
        <div className="actions">
          <button ref={cancel} className="btn" type="button" disabled={busy} onClick={onClose}>Cancel</button>
          <button className="btn" type="button" disabled={busy || loading} onClick={() => void load()}>Reload preview</button>
          <button className="btn danger" type="submit" disabled={!valid}>{busy ? "Revoking…" : result ? "Retry deletion" : "Confirm deletion"}</button>
        </div>
      </form>
    </div>
  </div>, document.body);
}