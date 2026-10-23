import { useState, type FormEvent } from "react";
import { ApiError } from "../client";
import { AsyncView, Badge, ErrorState, Field, PageHeader, useAsync } from "../components/ui";
import {
  SAFETY_CATEGORIES, SAFETY_TOGGLES, STANDARD_SAFETY, applyFloor, currentSafety, isFloorToggle, isManaged, isRelaxation, presetFor, safetyLabel, validateSafety,
} from "../managed";
import { useSession } from "../session";
import type { GatewayConfigurationUnion, GatewaySettings, SafetyConfiguration } from "../types";
import { RevisionHistory } from "./RevisionHistory";

const FOUNDRY_RISK_META: Record<
  (typeof SAFETY_CATEGORIES)[number],
  { title: string; subtitle: string }
> = {
  hate: {
    title: "Hate and fairness",
    subtitle: "Discriminatory, derogatory, or identity-targeted language",
  },
  sexual: {
    title: "Sexual",
    subtitle: "Explicit or non-consensual sexual content",
  },
  violence: {
    title: "Violence",
    subtitle: "Physical harm, weapons, or violent instructions",
  },
  self_harm: {
    title: "Self-harm",
    subtitle: "Suicide, self-injury, or encouragement of self-harm",
  },
};

const FOUNDRY_TOGGLE_META: Record<
  (typeof SAFETY_TOGGLES)[number],
  { stage: "Input" | "Output" | "Both"; desc: string; apiPath: string }
> = {
  prompt_attack: {
    stage: "Input",
    desc: "User prompts (Jailbreak) & Document attack (Indirect prompt injection) via Prompt Shields.",
    apiPath: "/contentsafety/text:shieldPrompt",
  },
  protected_material: {
    stage: "Output",
    desc: "Detects known copyrighted text and protected material in model completions.",
    apiPath: "/contentsafety/text:detectProtectedMaterial",
  },
  input_filtering: {
    stage: "Input",
    desc: "Scans inbound user and system messages before forwarding to upstream LLMs.",
    apiPath: "APIM Inbound <llm-content-safety>",
  },
  output_filtering: {
    stage: "Output",
    desc: "Scans outbound model completions before returning responses to the caller.",
    apiPath: "APIM Outbound <llm-content-safety>",
  },
};

function thresholdDescription(val: number): string {
  if (val <= 2) {
    return "Blocks most potentially harmful content, including low-severity and ambiguous cases.";
  }
  if (val <= 4) {
    return "Moderately filters content, catching clear and moderately severe instances.";
  }
  return "Blocks only the most severe content, allowing borderline or contextually sensitive material.";
}

function SafetyForm({ row, refresh }: { row: GatewaySettings; refresh: () => void }) {
  const { api } = useSession();
  const caps = row.capabilities;
  const current = currentSafety(row.desired?.configuration, row.capabilities?.initial_safety_threshold);
  const ready = isManaged(row.desired?.configuration);
  const [draft, setDraft] = useState<SafetyConfiguration>(() => current ?? STANDARD_SAFETY);
  const [expectedVersion, setExpectedVersion] = useState(row.version);
  const [reason, setReason] = useState("");
  const [approved, setApproved] = useState(false);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [stageFilter, setStageFilter] = useState<"all" | "input" | "output">("all");
  const pending = row.desired != null && row.desired.state !== "published";
  const conflict = expectedVersion !== row.version;
  const relaxing = isRelaxation(draft, current);
  const invalid = validateSafety(draft, caps);
  const locked = !caps?.safety_relaxation_allowed;
  const blocked = !ready || !caps?.managed_controls_enabled;

  const edit = (next: SafetyConfiguration) => { setDraft(next); setApproved(false); setAck(false); };
  const setProfile = (profile: SafetyConfiguration["profile"]) => edit(applyFloor(presetFor(profile, draft), caps));
  const setCategory = (k: (typeof SAFETY_CATEGORIES)[number], v: string) => edit({ ...draft, profile: "Custom", [k]: v === "" ? Number.NaN : Number(v) });
  const setToggle = (k: (typeof SAFETY_TOGGLES)[number], v: boolean) => edit({ ...draft, profile: "Custom", [k]: v });

  async function save(e: FormEvent) {
    e.preventDefault();
    if (blocked || invalid || !reason.trim() || !approved || conflict || pending || (relaxing && !ack)) return;
    setBusy(true);
    setError(undefined);
    try {
      const next = await api.saveContentSafetySettings(row.scope, expectedVersion, draft, reason.trim(), relaxing && ack);
      setExpectedVersion(next.version);
      setReason("");
      setApproved(false);
      setAck(false);
    } catch (err) {
      setError(err instanceof ApiError
        ? err.status === 409 ? `${err.detail} Your edits are preserved; reload desired settings before publishing.` : err.detail
        : "Could not publish content safety settings.");
    } finally {
      setBusy(false);
      refresh();
    }
  }

  async function reconcile() {
    setBusy(true);
    setError(undefined);
    try {
      const next = await api.reconcileContentSafetySettings(row.scope, row.version);
      setExpectedVersion(next.version);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reconcile content safety settings.");
    } finally {
      setBusy(false);
      refresh();
    }
  }

  function load(config?: GatewayConfigurationUnion) {
    setDraft(currentSafety(config, row.capabilities?.initial_safety_threshold) ?? STANDARD_SAFETY);
    setExpectedVersion(row.version);
    setReason("");
    setApproved(false);
    setAck(false);
    setError(undefined);
  }

  return (
    <section className="panel" aria-label={`${row.scope} content safety`}>
      <div className="command-panel-head" style={{ marginBottom: "0.85rem" }}>
        <div>
          <h2>Microsoft Foundry Guardrails — Shared Safety Policy</h2>
          <p role="status" className="muted">
            {row.desired?.state ?? "Unconfigured"} - Revision {row.version} - Published {row.published_version ?? "none"} · Azure AI Content Safety (<code>agents-contentsafety.cognitiveservices.azure.com</code>)
          </p>
        </div>
        <div className="badges">
          <Badge tone="ok">● EightSeverityLevels (0–7)</Badge>
          <Badge tone={draft.prompt_attack ? "info" : "neutral"}>
            Prompt Shields: {draft.prompt_attack ? "Active" : "Off"}
          </Badge>
        </div>
      </div>

      {caps && !caps.managed_controls_enabled && <p role="alert">Managed controls are not enabled by the operator, so content safety cannot be changed here.</p>}
      {caps?.managed_controls_enabled && !ready && <p role="alert">Content safety needs an initialized managed gateway configuration. Publish managed gateway settings first.</p>}
      {caps && !caps.protected_material_available && <p role="alert">Protected material detection is unavailable in this environment. Configurations enabling it cannot be published.</p>}
      {row.desired?.error && <ErrorState message={row.desired.error} />}
      {error && <ErrorState message={error} />}
      {conflict && <p role="alert">The server revision changed. Your edits are preserved. Reload desired settings before publishing.</p>}
      {pending && <button className="btn" disabled={busy} onClick={() => void reconcile()}>Retry publication</button>}

      <form className="gateway-form" onSubmit={(e) => void save(e)}>
        <fieldset disabled={blocked} style={{ border: 0, padding: 0, margin: 0 }}>
          {/* Microsoft Foundry Filter & Preset Toolbar */}
          <div className="foundry-toolbar">
            <div className="foundry-filter-group" role="group" aria-label="Filter by intervention stage">
              <span className="foundry-filter-label">Filter by:</span>
              {(["all", "input", "output"] as const).map((st) => (
                <button
                  key={st}
                  type="button"
                  className={`foundry-pill ${stageFilter === st ? "active" : ""}`}
                  onClick={() => setStageFilter(st)}
                >
                  {st === "all" ? "All" : st === "input" ? "Input" : "Output"}
                </button>
              ))}
            </div>

            <div className="foundry-filter-group">
              <span className="foundry-filter-label">Apply preset:</span>
              {(["Standard", "Strict", "Custom"] as const).map((preset) => (
                <button
                  key={preset}
                  type="button"
                  className={`foundry-pill ${draft.profile === preset ? "active" : ""}`}
                  onClick={() => setProfile(preset)}
                >
                  {preset === "Standard" ? "Default (Standard)" : preset}
                </button>
              ))}
              <div style={{ minWidth: "150px", marginLeft: "0.35rem" }}>
                <Field label="Safety profile">
                  {(id) => (
                    <select
                      id={id}
                      value={draft.profile}
                      onChange={(e) => setProfile(e.target.value as SafetyConfiguration["profile"])}
                    >
                      <option value="Standard">Standard</option>
                      <option value="Strict">Strict</option>
                      <option value="Custom">Custom</option>
                    </select>
                  )}
                </Field>
              </div>
            </div>
          </div>

          {/* Section 1: AI Safety and Security Risk Thresholds (Foundry Style) */}
          <div className="foundry-section-header">
            <span>▾ AI safety and security</span>
            <Badge tone="info">{SAFETY_CATEGORIES.length} risks selected</Badge>
            <span className="muted" style={{ marginLeft: "auto", fontSize: "0.75rem", fontWeight: 500 }}>
              API: <code>/contentsafety/text:analyze?api-version=2024-09-01</code>
            </span>
          </div>
          <div className="foundry-table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col" style={{ width: "220px" }}>Risk</th>
                  <th scope="col" style={{ width: "160px" }}>Intervention Stage</th>
                  <th scope="col">Threshold</th>
                  <th scope="col" style={{ width: "100px" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {SAFETY_CATEGORIES.map((k) => {
                  const meta = FOUNDRY_RISK_META[k];
                  const val = Number.isNaN(draft[k]) ? 4 : draft[k];
                  const fillPct = val <= 2 ? 33 : val <= 4 ? 66 : 100;
                  const levelBand = val <= 2 ? "Low" : val <= 4 ? "Medium" : "High";
                  return (
                    <tr key={k}>
                      <td>
                        <div style={{ display: "flex", alignItems: "flex-start", gap: "0.55rem" }}>
                          <input type="checkbox" checked readOnly aria-hidden="true" style={{ marginTop: "0.2rem" }} />
                          <div>
                            <strong>{meta.title}</strong>
                            <div className="muted" style={{ fontSize: "0.74rem" }}>{meta.subtitle}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        {(stageFilter === "all" || stageFilter === "input") && draft.input_filtering && (
                          <span className="stage-pill">Input</span>
                        )}
                        {(stageFilter === "all" || stageFilter === "output") && draft.output_filtering && (
                          <span className="stage-pill">Output</span>
                        )}
                      </td>
                      <td>
                        <div className="foundry-threshold-cell">
                          <div className="foundry-slider-box">
                            <div className="foundry-slider-track">
                              <div className="foundry-slider-fill" style={{ width: `${fillPct}%` }} />
                            </div>
                            <div className="foundry-slider-stops">
                              {([
                                { label: "Low", score: "1" },
                                { label: "Medium", score: "4" },
                                { label: "High", score: "6" },
                              ] as const).map((stop) => (
                                <button
                                  key={stop.label}
                                  type="button"
                                  disabled={draft.profile !== "Custom"}
                                  className={`foundry-stop-btn ${levelBand === stop.label ? "active" : ""}`}
                                  onClick={() => setCategory(k, stop.score)}
                                >
                                  {stop.label}
                                </button>
                              ))}
                            </div>
                          </div>
                          <div>
                            <Field label={`${safetyLabel[k]} severity threshold (0-7)`}>
                              {(id) => (
                                <input
                                  id={id}
                                  type="number"
                                  min={0}
                                  max={7}
                                  step={1}
                                  disabled={draft.profile !== "Custom"}
                                  value={Number.isNaN(draft[k]) ? "" : draft[k]}
                                  onChange={(e) => setCategory(k, e.target.value)}
                                />
                              )}
                            </Field>
                          </div>
                          <span className="muted" style={{ fontSize: "0.78rem" }}>
                            {thresholdDescription(val)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <Badge tone="info">Block</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Section 2: Prompt Shields, Protected Material & Stage Gates */}
          <div className="foundry-section-header">
            <span>▾ Prompt shields, IP &amp; stage protections</span>
            <Badge tone="ok">Foundry Security Controls</Badge>
          </div>
          <div className="foundry-table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col" style={{ width: "260px" }}>Control</th>
                  <th scope="col" style={{ width: "150px" }}>Intervention Stage</th>
                  <th scope="col">Protection Scope &amp; Azure Service Binding</th>
                  <th scope="col" style={{ width: "110px" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {SAFETY_TOGGLES.filter((k) => {
                  const stage = FOUNDRY_TOGGLE_META[k].stage;
                  if (stageFilter === "input") return stage === "Input" || stage === "Both";
                  if (stageFilter === "output") return stage === "Output" || stage === "Both";
                  return true;
                }).map((k) => {
                  const meta = FOUNDRY_TOGGLE_META[k];
                  const isDisabled =
                    (isFloorToggle(k, caps) && draft[k]) ||
                    (k === "protected_material" && !caps?.protected_material_available && !draft[k]);
                  return (
                    <tr key={k}>
                      <td>
                        <label style={{ display: "flex", alignItems: "center", gap: "0.55rem", fontWeight: 600, cursor: isDisabled ? "not-allowed" : "pointer" }}>
                          <input
                            type="checkbox"
                            checked={draft[k]}
                            disabled={isDisabled}
                            onChange={(e) => setToggle(k, e.target.checked)}
                          />{" "}
                          {safetyLabel[k]}
                        </label>
                      </td>
                      <td>
                        <span className="stage-pill">{meta.stage}</span>
                      </td>
                      <td>
                        <div style={{ fontSize: "0.82rem" }}>{meta.desc}</div>
                        <div className="muted" style={{ fontSize: "0.73rem" }}>
                          Binding: <code>{meta.apiPath}</code>
                        </div>
                      </td>
                      <td>
                        <Badge tone={draft[k] ? "ok" : "neutral"}>
                          {draft[k] ? "Block" : "Disabled"}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {invalid && !blocked && <p role="alert" className="notice bad">{invalid}</p>}
          {relaxing && (
            <label className="checkbox">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I acknowledge this change relaxes content safety protection.
            </label>
          )}
          <div className="panel" style={{ marginBottom: 0, background: "var(--navy-950)" }}>
            <div className="form-row">
              <Field label="Reason for this revision">
                {(id) => <input id={id} required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Align Violence and Prompt Shield thresholds with enterprise policy" />}
              </Field>
              <label className="checkbox" style={{ paddingBottom: "0.55rem" }}>
                <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} /> I approve these content safety values.
              </label>
              <button
                className="btn primary"
                disabled={busy || blocked || !!invalid || !reason.trim() || !approved || pending || conflict || (relaxing && !ack)}
              >
                {busy ? "Publishing..." : "Publish safety settings"}
              </button>
            </div>
          </div>
        </fieldset>
      </form>
      <details className="gateway-advanced">
        <summary>Revision history and recovery</summary>
        <button className="btn" disabled={busy} onClick={() => load(row.desired?.configuration)}>Reload desired settings</button>
        {row.desired && <button className="btn" disabled={busy} onClick={() => void reconcile()}>Check APIM / reconcile</button>}
        <RevisionHistory load={(o) => api.contentSafetySettingsHistory(row.scope, o)} deps={[api, row.scope, row.version, row.desired?.state]} disabled={busy || pending} onUse={load} />
      </details>
      <details className="gateway-advanced">
        <summary>Important notes</summary>
        <ul>
          <li>Both interfaces share the same safety configuration and revision. Saving here updates both interfaces without changing request limits.</li>
          <li>Published confirms APIM readback, not immediate gateway propagation. Old settings may apply briefly.</li>
          {locked && caps?.managed_controls_enabled && <li>The operator floor requires prompt attack, input and output filtering to be on; they cannot be turned off. Protected material is not part of the floor.</li>}
          <li>Lower severity thresholds are stricter. A threshold of 0 blocks every severity; it does not disable filtering.</li>
          <li>Protected material detection covers known protected text, not code or a copyright guarantee. Input PII redaction remains mandatory.</li>
          <li>Do not put secrets, prompts or customer content in revision reasons.</li>
        </ul>
      </details>
    </section>
  );
}

export function ContentSafetySettingsPage() {
  const { api } = useSession();
  const [tick, setTick] = useState(0);
  const state = useAsync(() => api.contentSafetySettings(), [api, tick]);
  const refresh = () => setTick((t) => t + 1);
  return <>
    <PageHeader title="Content safety" subtitle="Profiles, thresholds and protections applied to guarded gateway traffic" actions={<button className="btn" onClick={refresh}>Refresh publication status</button>} />
    <AsyncView state={state} isEmpty={(d) => d.items.length === 0} emptyTitle="No content safety scopes">
      {(data) => {
        const shared = data.items.find((row) => row.scope === "dev-openai") ?? data.items[0];
        return <>
          <div className="gateway-interfaces" aria-label="Configured interfaces">
            {data.items.map((row) => <section className="panel" key={row.scope}>
              <h2>{row.scope === "dev-openai" ? "API interface (/dev/v1)" : "Chatbot interface (/dev/llm/v1)"}</h2>
            </section>)}
          </div>
          <p className="muted">Settings below apply to {data.items.length > 1 ? "both interfaces" : "this interface"}.</p>
          {shared && <SafetyForm key={shared.scope} row={shared} refresh={refresh} />}
        </>;
      }}
    </AsyncView>
  </>;
}
