import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { buildChatCompletionBody, chatCompletion, chatCompletionUrl, textChatRequest, type ChatMessage, type ChatRequest, type ChatResult } from "../chat";
import { useSession } from "../session";
import { routingLabels, routingProfiles, type RoutingProfile } from "../autoRouting";
import type { KeyName } from "../types";
import { buildToolChoice, supportsStructured, supportsTools, validateResponseFormat, validateTools, type ToolChoiceMode } from "../validation";
import { AsyncView, Badge, EmptyState, Field, PageHeader, useAsync } from "../components/ui";

interface Turn {
  role: "user" | "assistant";
  content: string;
  result?: ChatResult;
}

const SAMPLE_PROMPT = "Say hello in one sentence.";
const SAMPLE_TOOLS = '[{"type":"function","function":{"name":"get_weather","description":"Get the current weather for a city","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}]';
const SAMPLE_SCHEMA = '{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false}';

export function outcomeView(r: ChatResult): { tone: "ok" | "warn" | "bad" | "info"; label: string; text: string } | null {
  switch (r.outcome) {
    case "streaming": return null;
    case "completed": return { tone: "ok", label: "Completed", text: r.toolCalls.length ? "The model proposed tool calls (not executed)." : "The model finished normally." };
    case "length": return { tone: "warn", label: "Length limit", text: "The model stopped because it reached an output length limit." };
    case "content_filter": return { tone: "warn", label: "Content filter stop", text: "The server reported finish_reason “content_filter”. The response was stopped by a content filter." };
    case "provider_error": return { tone: "bad", label: "Provider error", text: r.errorMessage ?? "The server reported an error." };
    case "http_error": return { tone: "bad", label: `HTTP ${r.httpStatus ?? ""}`.trim(), text: `${r.errorMessage ?? "Request rejected."}${r.retryAfter ? ` Retry after ${r.retryAfter}${/^\d+$/.test(r.retryAfter) ? " seconds" : ""}.` : ""}` };
    case "abnormal": return { tone: "bad", label: "Stream ended abnormally", text: r.errorMessage ?? "The stream ended abnormally." };
    case "cancelled": return { tone: "info", label: "Cancelled by you", text: "You cancelled the request. Any text shown is partial." };
    case "network_error": return { tone: "bad", label: "Network error", text: r.errorMessage ?? "Network error." };
  }
}

export function PlaygroundPage() {
  const { api, config, keys, setKey, me } = useSession();
  const models = useAsync(() => api.models(), [api, me.organization_id]);
  const subs = useAsync(() => api.subscriptions(0, 100), [api, me.organization_id]);
  const auto = useAsync(() => api.autoRoutingAvailability(), [api, me.organization_id]);
  useEffect(() => {
    const refresh = () => { models.reload(); auto.reload(); subs.reload(); };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [models.reload, auto.reload, subs.reload]);

  return (
    <>
      <PageHeader title="Playground" subtitle="Send live requests directly to the gateway using one of your subscription keys. External ModelArts models process redacted input outside Azure; PII redaction is best-effort, not anonymization. Conversation history stays in this browser tab only." />
      <AsyncView state={models}>
        {(m) => (
          <AsyncView state={subs}>
            {(s) => {
              const enabled = m.items.filter((x) => x.id !== "auto" && x.enabled && !x.placeholder && x.capabilities.includes("chat"));
              const active = s.items.filter((x) => x.state === "active");
              const choices = auto.data?.ready === true ? [...enabled, { id: "auto", capabilities: ["chat"], max_completion_tokens: auto.data.max_completion_tokens }] : enabled;
              return <>
                {!enabled.length && <p role="status">No enabled models. Conversation history is retained; no request can be sent.</p>}
                {!active.length && <p role="status">No active subscription. Contact your administrator.</p>}
                {auto.data?.ready === false && <p role="status">Auto routing is unavailable: {auto.data.reason ?? "not ready"}.</p>}
                <Chat key={me.organization_id} models={choices} subs={active} gatewayUrl={config.gatewayUrl} keys={keys} setKey={setKey} reveal={api.revealKey} />
              </>;
            }}
          </AsyncView>
        )}
      </AsyncView>
    </>
  );
}

interface ChatProps {
  models: { id: string; capabilities: string[]; max_completion_tokens?: number | null }[];
  subs: { id: string; name: string }[];
  gatewayUrl: string;
  keys: Record<string, Partial<Record<KeyName, string>>>;
  setKey: (id: string, name: KeyName, value: string) => void;
  reveal: (id: string, key: KeyName, signal?: AbortSignal) => Promise<string>;
}

function Chat({ models, subs, gatewayUrl, keys, setKey, reveal }: ChatProps) {
  const [searchParams] = useSearchParams();
  const initialModelId = models.find((m) => m.id === searchParams.get("model"))?.id ?? models[0]?.id ?? "";
  const [modelId, setModelId] = useState(initialModelId);
  const [routingProfile, setRoutingProfile] = useState<RoutingProfile>("balanced");
  const [subId, setSubId] = useState(subs[0]?.id ?? "");
  const [pasted, setPasted] = useState("");
  const [system, setSystem] = useState("");
  const [input, setInput] = useState("");
  const [stream, setStream] = useState(models[0]?.capabilities.includes("stream") ?? false);
  const [useTools, setUseTools] = useState(false);
  const [toolsText, setToolsText] = useState(SAMPLE_TOOLS);
  const [choiceMode, setChoiceMode] = useState<ToolChoiceMode>("auto");
  const [choiceFn, setChoiceFn] = useState("");
  const [fmt, setFmt] = useState<"text" | "json_object" | "json_schema">("text");
  const [schemaName, setSchemaName] = useState("response");
  const [schemaText, setSchemaText] = useState(SAMPLE_SCHEMA);
  const [examplesOpen, setExamplesOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [live, setLive] = useState<ChatResult | null>(null);
  const [formError, setFormError] = useState<string>();
  const [revealMsg, setRevealMsg] = useState<string>();
  const abort = useRef<AbortController | null>(null);
  const [phase, setPhase] = useState<"revealing" | "sending" | null>(null);
  const codeButton = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const busy = phase !== null;

  // Invalidate ownership before aborting: even a transport ignoring abort cannot
  // cache a late credential, update this conversation, or send to the gateway.
  useEffect(() => () => {
    const ctrl = abort.current;
    abort.current = null;
    ctrl?.abort();
  }, [subId, gatewayUrl]);

  const model = models.find((m) => m.id === modelId) ?? { id: "", capabilities: [] };
  const available = !!model.id && subs.some(s => s.id === subId);
  useEffect(() => {
    if (modelId && !models.some((m) => m.id === modelId)) {
      setModelId("");
      setFormError("The selected model is no longer available. Conversation history is retained; choose an available model before sending.");
      cancel(false);
    }
  }, [models, modelId]);
  useEffect(() => {
    if (subId && !subs.some(s => s.id === subId)) { setSubId(""); setPasted(""); cancel(false); }
  }, [subs, subId]);
  useEffect(() => {
    setStream(model.capabilities.includes("stream"));
    setUseTools(false);
    setFmt("text");
  }, [model.id]);
  const toolsOk = supportsTools(model.capabilities);
  const schemaOk = supportsStructured(model.capabilities);
  const streamOk = model.capabilities.includes("stream");
  const toolsCheck = useMemo(() => useTools && toolsOk ? validateTools(toolsText) : null, [useTools, toolsOk, toolsText]);
  const toolNames = toolsCheck?.ok ? toolsCheck.value.map((t) => (t as { function: { name: string } }).function.name) : [];
  const fmtCheck = useMemo(() => fmt !== "text" && schemaOk ? validateResponseFormat(fmt, schemaName, schemaText) : null, [fmt, schemaOk, schemaName, schemaText]);
  const revealed = keys[subId]?.primary ?? keys[subId]?.secondary;
  const key = revealed ?? pasted.trim();

  const exampleMessages: ChatMessage[] = [
    ...(system.trim() ? [{ role: "system", content: system.trim() } as ChatMessage] : []),
    { role: "user", content: input.trim() || SAMPLE_PROMPT },
  ];
  function requestFor(messages: ChatMessage[]): ChatRequest {
    const request = textChatRequest(modelId, messages, model.max_completion_tokens);
    if (modelId === "auto") request.routing_profile = routingProfile;
    if (useTools && toolsOk && toolsCheck?.ok) {
      request.tools = toolsCheck.value;
      const choice = buildToolChoice(choiceMode, choiceFn, toolsCheck.value);
      if (choice.ok) request.tool_choice = choice.value;
    }
    if (fmt !== "text" && schemaOk && fmtCheck?.ok) request.response_format = fmtCheck.value;
    return request;
  }
  const requestBody = buildChatCompletionBody(requestFor(exampleMessages), stream && streamOk);
  const endpoint = chatCompletionUrl(gatewayUrl);
  const curlExample = [
    `curl --fail-with-body --request POST ${shellQuote(endpoint)} \\`,
    `  --header 'Content-Type: application/json' \\`,
    `  --header "Ocp-Apim-Subscription-Key: \${AIFLUX_SUBSCRIPTION_KEY}" \\`,
    `  --data-raw ${shellQuote(JSON.stringify(requestBody))}`,
  ].join("\n");
  const pythonExample = [
    "import json",
    "import os",
    "from openai import OpenAI",
    "",
    "client = OpenAI(",
    `    base_url=${JSON.stringify(gatewayUrl.replace(/\/+$/, ""))},`,
    '    api_key="unused",',
    '    default_headers={"Ocp-Apim-Subscription-Key": os.environ["AIFLUX_SUBSCRIPTION_KEY"]},',
    "    max_retries=0,",
    ")",
    "",
    `request = json.loads(${JSON.stringify(JSON.stringify(requestBody))})`,
    ...(modelId === "auto" ? ['request["extra_body"] = {"routing_profile": request.pop("routing_profile")}'] : []),
    "response = client.chat.completions.create(**request)",
    ...(stream && streamOk ? ["for chunk in response:", "    if chunk.choices:", '        print(chunk.choices[0].delta.content or "", end="")'] : ["print(response.choices[0].message.content)"]),
  ].join("\n");

  useEffect(() => {
    if (!examplesOpen) return;
    dialog.current?.focus();
    return () => { codeButton.current?.focus(); };
  }, [examplesOpen]);

  function closeExamples() {
    setExamplesOpen(false);
    setCopyStatus("");
  }

  async function copyExample(text: string) {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard access is unavailable.");
      await navigator.clipboard.writeText(text);
      setCopyStatus("Example copied to clipboard.");
    } catch {
      setCopyStatus("Could not copy the example. Check browser clipboard permissions and try again.");
    }
  }

  function begin() {
    if (abort.current) return null;
    const ctrl = new AbortController();
    abort.current = ctrl;
    setPhase("revealing");
    return ctrl;
  }

  function owns(ctrl: AbortController) {
    return abort.current === ctrl;
  }

  function finish(ctrl: AbortController) {
    if (!owns(ctrl)) return;
    abort.current = null;
    setPhase(null);
    setLive(null);
  }

  async function retrieveKey(ctrl: AbortController): Promise<string> {
    // Bound the await as well as fetch, including token acquisition and custom
    // reveal implementations which do not honor AbortSignal.
    let timer: ReturnType<typeof setTimeout> | undefined;
    let onAbort = () => {};
    try {
      const stopped = new Promise<never>((_, reject) => {
        onAbort = () => reject(new Error("Credential retrieval stopped."));
        ctrl.signal.addEventListener("abort", onAbort, { once: true });
        timer = setTimeout(() => ctrl.abort("credential-timeout"), 15_000);
      });
      ctrl.signal.throwIfAborted();
      return await Promise.race([reveal(subId, "primary", ctrl.signal), stopped]);
    } finally {
      clearTimeout(timer);
      ctrl.signal.removeEventListener("abort", onAbort);
    }
  }

  function revealError(ctrl: AbortController) {
    return ctrl.signal.reason === "credential-timeout"
      ? "Key retrieval timed out. No gateway request was sent."
      : "Could not reveal the key. Reveal one or paste it below.";
  }

  async function doReveal() {
    if (!subs.some(s => s.id === subId)) return;
    const ctrl = begin();
    if (!ctrl) return;
    setRevealMsg(undefined);
    try {
      const fetched = await retrieveKey(ctrl);
      if (!owns(ctrl) || ctrl.signal.aborted) return;
      if (!fetched) throw new Error("Missing credential.");
      setKey(subId, "primary", fetched);
      setRevealMsg("Primary key revealed and held in memory.");
    } catch {
      if (owns(ctrl)) setRevealMsg(revealError(ctrl));
    } finally {
      finish(ctrl);
    }
  }

  async function send() {
    if (abort.current) return;
    if (!available) return setFormError("Choose an available model and active subscription before sending.");
    setFormError(undefined);
    const text = input.trim();
    if (!text) return setFormError("Enter a message.");
    if (useTools && toolsOk) {
      if (!toolsCheck?.ok) return setFormError(toolsCheck?.error ?? "Tools are invalid.");
      const choice = buildToolChoice(choiceMode, choiceFn, toolsCheck.value);
      if (!choice.ok) return setFormError(choice.error);
    }
    if (fmt !== "text" && schemaOk && !fmtCheck?.ok) return setFormError(fmtCheck?.error ?? "Response format is invalid.");
    const history: ChatMessage[] = turns.filter((t) => t.role === "user" || (t.result && t.result.outcome === "completed" && t.result.toolCalls.length === 0))
      .map((t) => ({ role: t.role, content: t.content }) as ChatMessage);
    const messages: ChatMessage[] = [...(system.trim() ? [{ role: "system", content: system.trim() } as ChatMessage] : []), ...history, { role: "user", content: text }];
    const ctrl = begin();
    if (!ctrl) return;
    let sending = false;
    try {
      let activeKey = key;
      if (!activeKey) {
        activeKey = await retrieveKey(ctrl);
        if (!owns(ctrl) || ctrl.signal.aborted) return;
        if (!activeKey) throw new Error("Missing credential.");
        setKey(subId, "primary", activeKey);
      }
      if (!owns(ctrl) || ctrl.signal.aborted) return;
      sending = true;
      setPhase("sending");
      setInput("");
      setTurns((t) => [...t, { role: "user", content: text }]);
      setLive({ outcome: "streaming", content: "", toolCalls: [], finishReason: null, usage: null, sawDone: false });
      const result = await chatCompletion({
        gatewayUrl,
        key: activeKey,
        stream: stream && streamOk,
        signal: ctrl.signal,
        request: requestFor(messages),
        onUpdate: (update) => { if (owns(ctrl) && !ctrl.signal.aborted) setLive(update); },
      });
      if (!owns(ctrl) || ctrl.signal.aborted) return;
      setTurns((t) => [...t, { role: "assistant", content: result.content, result }]);
      // The public error parser intentionally exposes message, not raw code.
      // Treat any forbidden request conservatively; never silently resend it.
      if (result.httpStatus === 403) {
        setModelId("");
        setFormError("Model access was denied. History is retained; choose an available model. The request was not retried.");
      }
    } catch {
      if (owns(ctrl)) setFormError(sending ? "The request could not be completed. It was not retried." : revealError(ctrl));
    } finally {
      finish(ctrl);
    }
  }

  function cancel(showOutcome = true) {
    const ctrl = abort.current;
    abort.current = null;
    ctrl?.abort();
    setPhase(null);
    if (showOutcome && ctrl) {
      if (live) setTurns((t) => [...t, { role: "assistant", content: live.content, result: { ...live, outcome: "cancelled" } }]);
      else setRevealMsg("Key retrieval cancelled. No gateway request was sent.");
    }
    setLive(null);
  }

  function reset() {
    cancel(false);
    setTurns([]);
    setLive(null);
    setFormError(undefined);
    setRevealMsg(undefined);
  }

  return (
    <div className="playground">
      <section className="panel config" aria-label="Request settings">
        <Field label="Model">{(id) => <select id={id} value={modelId} onChange={(e) => setModelId(e.target.value)} disabled={busy}><option value="">Select an available model</option>{models.map((m) => <option key={m.id}>{m.id}</option>)}</select>}</Field>
        {modelId === "auto" && <Field label="Routing profile" hint="Decision-1 scores eligible options; completion usage is separate from Decision overhead.">{(id) => <select id={id} value={routingProfile} disabled={busy} onChange={(e) => setRoutingProfile(e.target.value as RoutingProfile)}>{routingProfiles.map((p) => <option key={p} value={p}>{routingLabels[p]}</option>)}</select>}</Field>}
        <div className="endpoint-details">
          <p><strong>Gateway base URI</strong><code>{gatewayUrl}</code></p>
          <p><strong>REST endpoint</strong><code>{endpoint}</code></p>
          <button ref={codeButton} type="button" className="btn" onClick={() => setExamplesOpen(true)}>Code</button>
        </div>
        <Field label="Subscription">{(id) => <select id={id} value={subId} onChange={(e) => { reset(); setPasted(""); setSubId(e.target.value); }} disabled={busy}><option value="">Select an active subscription</option>{subs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>}</Field>
        {revealed ? (
          <p className="notice" role="status">Using the revealed key (memory only).</p>
        ) : (
          <>
            <button className="btn" disabled={busy} onClick={() => void doReveal()}>Reveal primary key</button>
            <Field label="Or paste a key" hint="Held in memory only; never stored.">{(id, d) => <input id={id} aria-describedby={d} type="password" autoComplete="off" disabled={busy} value={pasted} onChange={(e) => setPasted(e.target.value)} />}</Field>
          </>
        )}
        {revealMsg && <p role="status" className="muted">{revealMsg}</p>}
        {phase === "revealing" && <p role="status">Preparing request: retrieving subscription key…</p>}
        <Field label="System prompt (optional)">{(id) => <textarea id={id} rows={2} value={system} onChange={(e) => setSystem(e.target.value)} disabled={busy} />}</Field>
        <label className="check"><input type="checkbox" checked={stream && streamOk} onChange={(e) => setStream(e.target.checked)} disabled={busy || !streamOk} /> Stream response (SSE)</label>
        {!streamOk && !toolsOk && !schemaOk && <p className="muted">Guarded text-only requests; streaming, tools, and structured output are not sent.</p>}
        {model.max_completion_tokens != null && <p className="muted">Development output limit: {model.max_completion_tokens} tokens.</p>}
        <fieldset disabled={busy}>
          <legend>Tools</legend>
          {!toolsOk ? <p className="muted">This model does not advertise tool support.</p> : <>
            <label className="check"><input type="checkbox" checked={useTools} onChange={(e) => setUseTools(e.target.checked)} /> Send tool definitions</label>
            {useTools && <>
              <Field label="Tools JSON" error={toolsCheck && !toolsCheck.ok ? toolsCheck.error : undefined} hint="Proposed calls are displayed only. They are never executed.">{(id, d) => <textarea id={id} aria-describedby={d} rows={8} spellCheck={false} value={toolsText} onChange={(e) => setToolsText(e.target.value)} />}</Field>
              <Field label="Tool choice">{(id) => <select id={id} value={choiceMode} onChange={(e) => setChoiceMode(e.target.value as ToolChoiceMode)}><option value="auto">auto</option><option value="none">none</option><option value="required">required</option><option value="function">specific function</option></select>}</Field>
              {choiceMode === "function" && <Field label="Function">{(id) => <select id={id} value={choiceFn} onChange={(e) => setChoiceFn(e.target.value)}><option value="">Select...</option>{toolNames.map((n) => <option key={n}>{n}</option>)}</select>}</Field>}
            </>}
          </>}
        </fieldset>
        <fieldset disabled={busy}>
          <legend>Response format</legend>
          {!schemaOk ? <p className="muted">This model does not advertise structured output support.</p> : <>
            <Field label="Format">{(id) => <select id={id} value={fmt} onChange={(e) => setFmt(e.target.value as typeof fmt)}><option value="text">Text (default)</option><option value="json_object">JSON object</option><option value="json_schema">JSON schema</option></select>}</Field>
            {fmt === "json_schema" && <>
              <Field label="Schema name">{(id) => <input id={id} value={schemaName} onChange={(e) => setSchemaName(e.target.value)} />}</Field>
              <Field label="JSON schema" error={fmtCheck && !fmtCheck.ok ? fmtCheck.error : undefined}>{(id, d) => <textarea id={id} aria-describedby={d} rows={7} spellCheck={false} value={schemaText} onChange={(e) => setSchemaText(e.target.value)} />}</Field>
            </>}
          </>}
        </fieldset>
      </section>

      <section className="panel convo" aria-label="Conversation">
        <div className="log" role="log" aria-live="polite" aria-relevant="additions text">
          {turns.length === 0 && !live && <EmptyState title="Start a conversation" hint="Messages are sent straight to the gateway. History is kept in memory and cleared when you reload or sign out." />}
          {turns.map((t, i) => <TurnView key={i} turn={t} />)}
          {live && <TurnView turn={{ role: "assistant", content: live.content, result: live }} />}
        </div>
        {formError && <p role="alert" className="notice bad">{formError}</p>}
        <form onSubmit={(e) => { e.preventDefault(); if (!busy) void send(); }} className="composer">
          <Field label="Message">{(id) => <textarea id={id} rows={3} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !busy) { e.preventDefault(); void send(); } }} />}</Field>
          <div className="actions">
            {busy ? <button type="button" className="btn danger" onClick={() => cancel()}>Cancel</button> : <button className="btn primary" disabled={!available}>Send</button>}
            <button type="button" className="btn" onClick={reset}>Clear conversation</button>
            <small className="muted">Ctrl+Enter to send</small>
          </div>
        </form>
      </section>
      {examplesOpen && (
        <div className="dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) closeExamples(); }}>
          <div
            ref={dialog}
            className="code-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="code-dialog-title"
            tabIndex={-1}
            onKeyDown={(e) => {
              if (e.key === "Escape") { e.preventDefault(); closeExamples(); }
              if (e.key === "Tab") {
                const items = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], [tabindex]:not([tabindex='-1'])"));
                const first = items[0];
                const last = items.at(-1);
                if (e.shiftKey && (document.activeElement === first || document.activeElement === e.currentTarget)) { e.preventDefault(); last?.focus(); }
                else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
              }
            }}
          >
            <div className="code-dialog-head">
              <div><h2 id="code-dialog-title">Gateway request examples</h2><p className="muted">REST chat completions for <code>{modelId}</code></p></div>
              <button type="button" className="btn" onClick={closeExamples} aria-label="Close code examples">Close</button>
            </div>
            <p className="endpoint-uri"><strong>Gateway base URI:</strong> <code>{gatewayUrl}</code><br /><strong>REST endpoint URI:</strong> <code>{endpoint}</code></p>
            <p className="muted">Set <code>AIFLUX_SUBSCRIPTION_KEY</code> in your environment. The example never includes the key currently held by this page.</p>
            <section aria-labelledby="curl-example-title">
              <div className="code-title"><h3 id="curl-example-title">cURL REST</h3><button type="button" className="btn" onClick={() => void copyExample(curlExample)}>Copy cURL</button></div>
              <pre className="code-example" tabIndex={0}><code>{curlExample}</code></pre>
            </section>
            <section aria-labelledby="python-example-title">
              <div className="code-title"><h3 id="python-example-title">OpenAI Python SDK</h3><button type="button" className="btn" onClick={() => void copyExample(pythonExample)}>Copy Python</button></div>
              <pre className="code-example" tabIndex={0}><code>{pythonExample}</code></pre>
            </section>
            <p className="muted">Examples use the selected model, current system prompt and message, its advertised output limit, and only supported request settings.</p>
            {copyStatus && <p className="notice" role="status" aria-live="polite">{copyStatus}</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, "'\\''")}'`;
}

function TurnView({ turn }: { turn: Turn }) {
  const r = turn.result;
  const outcome = r ? outcomeView(r) : null;
  return (
    <article className={`turn ${turn.role}`}>
      <h2 className="turn-role">{turn.role === "user" ? "You" : "Assistant"}{r?.outcome === "streaming" && <Badge tone="info">Streaming…</Badge>}</h2>
      {turn.content && <p className="turn-text">{turn.content}</p>}
      {r && r.toolCalls.length > 0 && (
        <div className="tool-calls">
          <strong>Proposed tool calls — not executed</strong>
          {r.toolCalls.map((tc) => (
            <pre key={tc.index} tabIndex={0}><code>{tc.name}({tc.arguments})</code>{tc.id ? `\nid: ${tc.id}` : ""}</pre>
          ))}
        </div>
      )}
      {outcome && <p className="notice" role={outcome.tone === "bad" ? "alert" : "status"}><Badge tone={outcome.tone}>{outcome.label}</Badge> {outcome.text}</p>}
      {r?.usage && <p className="muted usage-line">Usage reported by server: {JSON.stringify(r.usage)}</p>}
      {r?.routing && <p className="muted" aria-label="Actual Auto routing result">
        Completion model: {r.actualModel ?? "not reported"} · selected alias: {r.routing.selected_model} · profile: {r.routing.routing_profile} · fallback: {r.routing.fallback_used ? "yes" : "no"} · config: {r.routing.config_version}.
        Decision usage: {r.routing.decision_usage ? JSON.stringify(r.routing.decision_usage) : "unknown"}; Decision cost: {r.routing.decision_cost_usd ?? "unknown"} (separate from completion).
      </p>}
    </article>
  );
}