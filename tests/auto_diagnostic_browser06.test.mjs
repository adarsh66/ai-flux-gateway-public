import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { createHash } from "node:crypto";
import { SOURCE } from "../scripts/deployment/auto_diagnostic_browser06.mjs";

const NORMAL = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions";
const REVISION = NORMAL.replace("/v1/", "/v1;rev=2/");
const TEXT = "Please greet me in one short sentence.";
const SHA = "a".repeat(64);
function binding() {
  const end = new Date(Date.now() + 1800000).toISOString();
  return { scope: "DIAGNOSTIC06_CORRECTION_ONE_USER_ATTEMPT", correction_of: "DIAGNOSTIC05B_TIMER_GLOBAL_FAILURE",
    parent_disk_verified: true, parent_claim_durable: true, cleanup_complete: true,
    manifest_sha256: SHA, parent_intent_sha256: SHA, shared_owner_sha256: SHA,
    reservation_sha256: SHA, browser_source_sha256: SHA, end, verified_at_utc: new Date().toISOString(),
    reservation: { manifest_sha256: SHA, end, IP: "167.103.66.248", attempt_budget: 1,
      scoring_budget: 1, completion_budget: 0, retry_budget: 0, fixed_text: TEXT,
      model: "gpt-5.4-mini", path: "/dev/llm/v1;rev=2/chat/completions", browser_source_sha256: SHA } };
}
const body = () => ({ model: "gpt-5.4-mini", stream: false, max_completion_tokens: 32,
  messages: [{ role: "user", content: TEXT }] });
const summary = () => ({ scoring_status: 200, schema_valid: true, body_within_bound: true,
  key_types: { answers: "Object", usage: "Object", model: "String" },
  probabilities: { greeting: 0.9, arithmetic: 0.1 }, usage: { input_tokens: 12, output_tokens: 4, total_tokens: 16 } });

function fixture(options = {}) {
  const calls = [], handlers = [];
  let text = "", predicate, resolveWait, rejectWait, pressReturned = false, responseReads = 0;
  const pending = new Promise((resolve, reject) => { resolveWait = resolve; rejectWait = reject; });
  const response = (url = REVISION, method = "POST") => ({ url: () => url,
    // Deliberately NEW wrapper each time, never original request identity.
    request: () => ({ method: () => method }), status: () => options.http ?? 200,
    text: async () => { responseReads++; if (options.textError) throw Error("SECRET_RESPONSE");
      return options.raw ?? JSON.stringify(options.summary ?? summary()); } });
  function emit(value) { if (predicate?.(value)) resolveWait(value); }
  async function post(data = body(), url = NORMAL, method = "POST") {
    const request = { method: () => method, url: () => url, postDataJSON: () => {
      if (options.parseError) throw Error("SECRET_BODY"); return data;
    } };
    await handlers[0]({ request: () => request, abort: async () => { calls.push("abort"); },
      continue: async change => {
        calls.push(change?.url ?? "options");
        if (options.continueError) throw Error("SECRET_CONTINUE");
        if (method === "OPTIONS" || options.noResponse) return;
        emit(response(options.responseUrl ?? REVISION, options.responseMethod ?? "POST"));
      } });
  }
  const message = { isEnabled: async () => true, fill: async value => { calls.push("fill"); text = value; },
    inputValue: async () => text, press: async key => {
      calls.push(key); if (options.pressError) { rejectWait(Error("SECRET_WAIT")); throw Error("SECRET_PRESS"); }
      // An unrelated exact-URL POST before consumption/forwarding must not match.
      assert.equal(predicate(response()), false);
      if (options.waitTimeout) { rejectWait(Error("SECRET_TIMEOUT")); return; }
      const send = async () => {
        if (options.delayed) { assert.equal(pressReturned, true); calls.push("delayed-post"); }
        await post(options.body ?? body(), options.url ?? NORMAL);
        if (options.duplicate) await post();
        // Mock the waiter's own timeout, not a helper timer/global.
        rejectWait(Error("SECRET_TIMEOUT"));
      };
      if (options.delayed) { pressReturned = true; queueMicrotask(() => { void send(); }); }
      else await send();
    } };
  const page = { route: async (match, handler) => {
    assert.equal(match({ origin: "https://poc-ids-token-ex-apim.azure-api.net", pathname: "/dev/llm/v1/chat/completions" }), true);
    assert.equal(match({ origin: "https://wrong.invalid", pathname: "/dev/llm/v1/chat/completions" }), false);
    calls.push("route"); handlers.push(handler);
  }, waitForResponse: (fn, config) => {
    assert.equal(config.timeout, 20000); calls.push("wait"); predicate = fn; return pending;
  }, getByRole: (role, spec) => {
    assert.equal(spec.exact, true);
    return role === "textbox" ? message : { isEnabled: async () => !options.disabled };
  } };
  return { page, calls, post, emit, response, handlers, reads: () => responseReads };
}

async function run(f, b = binding()) {
  const context = vm.createContext({ page: f.page, binding: b });
  assert.equal(vm.runInContext("[typeof setTimeout, typeof clearTimeout, typeof process, typeof Buffer, typeof require, typeof URL].every(x => x === 'undefined')", context), true);
  return JSON.parse(JSON.stringify(await vm.runInContext(`(${SOURCE})(page, binding)`, context)));
}

test("source fingerprint matches actual abort-only browser-tool sandbox preflight", t => {
  // Windows module text uses CRLF; browser inline source uses LF. No other
  // whitespace, comments or code normalization is permitted for this check.
  const browserSource = SOURCE.replace(/\r\n/g, "\n");
  let fingerprint = 2166136261;
  for (const ch of browserSource) fingerprint = Math.imul(fingerprint ^ ch.charCodeAt(0), 16777619) >>> 0;
  assert.equal(browserSource.length, 8192);
  assert.equal(fingerprint.toString(16), "5ac396b8");
  t.diagnostic(`source_sha256=${createHash("sha256").update(SOURCE).digest("hex")}`);
});

test("exact SOURCE with no timer or Node globals handles delayed post and unstable request wrappers", async () => {
  const f = fixture({ delayed: true, duplicate: true }), r = await run(f);
  assert.equal(r.status, "SCORER_SCHEMA_PROVEN"); assert.equal(r.scorer_schema_proven, true);
  assert.deepEqual(r.diagnostic, summary()); assert.equal(r.guard_retained_closed, true);
  assert.equal(r.response_wait_started, true); assert.equal(r.keyboard_invocations, 1);
  assert.equal(r.observed_posts, 2); assert.equal(r.aborted_posts, 1);
  assert.deepEqual(f.calls, ["route", "fill", "wait", "Control+Enter", "delayed-post", REVISION, "abort"]);
  assert.doesNotMatch(SOURCE, /setTimeout|clearTimeout|Promise\.race|\bimport\b|\brequire\b|node:|\bprocess\b|\bBuffer\b|readFile|writeFile|\.on\(|\.off\(|\.click\(|\.evaluate\(|fetch\(/);
});

for (const [field, value] of [["parent_disk_verified", false], ["parent_claim_durable", false],
  ["cleanup_complete", false], ["scope", "DIAGNOSTIC05_05B_ONE_USER_ATTEMPT"],
  ["correction_of", "unconstrained_retry"], ["parent_intent_sha256", "bad"], ["shared_owner_sha256", null],
  ["verified_at_utc", "2020-01-01"], ["end", "invalid"]]) {
  test(`binding ${field} rejected before any interaction`, async () => {
    const b = binding(); b[field] = value; const f = fixture(), r = await run(f, b);
    assert.equal(r.keyboard_invocations, 0); assert.deepEqual(f.calls, []); assert.equal(r.retry_authorized, false);
  });
}
for (const [field, value] of [["IP", "167.103.63.12"], ["attempt_budget", 2], ["scoring_budget", 2],
  ["completion_budget", 1], ["retry_budget", 1], ["fixed_text", "different"], ["browser_source_sha256", "b".repeat(64)]]) {
  test(`reservation ${field} rejected`, async () => {
    const b = binding(); b.reservation[field] = value; const f = fixture();
    assert.equal((await run(f, b)).keyboard_invocations, 0); assert.deepEqual(f.calls, []);
  });
}
for (const options of [{ pressError: true }, { continueError: true }, { parseError: true },
  { disabled: true }, { textError: true }, { waitTimeout: true }, { noResponse: true }]) {
  test(`error ${Object.keys(options)[0]} returns every metric with retained closed route`, async () => {
    const f = fixture(options), r = await run(f);
    assert.equal(r.guard_retained_closed, true); assert.equal(r.retry_authorized, false);
    assert.equal(r.scorer_schema_proven, false); assert.equal(r.scoring_request_count, null);
    assert.equal(r.completion_request_count, null); assert.equal(r.auth_inspected, false);
    assert.doesNotMatch(JSON.stringify(r), /SECRET/);
    const snapshot = JSON.stringify(r), before = f.calls.filter(v => v === REVISION).length;
    await f.post(); assert.equal(f.calls.at(-1), "abort");
    f.emit(f.response()); assert.equal(JSON.stringify(r), snapshot);
    assert.equal(f.calls.filter(v => v === REVISION).length, before);
    if (options.waitTimeout) { assert.equal(r.consumed, false); assert.equal(r.forwarding_attempted, false); }
  });
}
for (const [url, method] of [[NORMAL, "POST"], [REVISION, "POST"], [REVISION + "?extra=1", "POST"],
  ["https://wrong.invalid/chat/completions", "POST"], [REVISION, "GET"]]) {
  test(`response requires exact URL and method: ${url} ${method}`, async () => {
    const f = fixture({ responseUrl: url, responseMethod: method }), r = await run(f);
    const accepted = [NORMAL, REVISION].includes(url) && method === "POST";
    assert.equal(r.scorer_schema_proven, accepted); assert.equal(f.reads(), accepted ? 1 : 0);
  });
}
for (const mutate of [s => { s.secret = "SECRET"; }, s => { s.key_types.authorization = "String"; },
  s => { s.key_types.model = "SECRET"; }, s => { s.probabilities.greeting = 4; },
  s => { s.probabilities.arithmetic = "SECRET"; }, s => { s.usage.input_tokens = -1; },
  s => { s.usage.total_tokens = 2147483648; }, s => { s.body_within_bound = false; },
  s => { s.scoring_status = 403; }, s => { s.probabilities = null; }]) {
  test(`invalid summary ${mutate.toString()}`, async () => {
    const s = summary(); mutate(s); const r = await run(fixture({ summary: s }));
    assert.equal(r.scorer_schema_proven, false); assert.equal(r.diagnostic, null);
    assert.doesNotMatch(JSON.stringify(r), /SECRET/);
  });
}
for (const raw of ["SECRET", "x".repeat(8193), JSON.stringify({ choices: [{ content: "SECRET" }] })]) {
  test(`raw/oversize/non-summary body rejected (${raw.length})`, async () => {
    const r = await run(fixture({ raw })); assert.equal(r.diagnostic, null);
    assert.equal(r.scorer_schema_proven, false); assert.doesNotMatch(JSON.stringify(r), /SECRET|choices/);
  });
}
test("valid sanitized failure is not schema acceptance", async () => {
  const s = summary(); s.scoring_status = 403; s.schema_valid = false; s.probabilities = null;
  const r = await run(fixture({ summary: s })); assert.deepEqual(r.diagnostic, s);
  assert.equal(r.scorer_schema_proven, false);
});
for (const change of [b => { b.model = "other"; }, b => { b.messages[0].content = "other"; },
  b => { b.stream = true; }, b => { b.max_completion_tokens = 1025; }, b => { b.extra = true; }]) {
  test(`first invalid POST consumed ${change.toString()}`, async () => {
    const data = body(); change(data); const f = fixture({ body: data, duplicate: true }), r = await run(f);
    assert.equal(r.forwarding_attempted, false); assert.equal(r.consumed, true);
    assert.equal(r.aborted_posts, 2); assert.equal(f.calls.includes(REVISION), false);
  });
}
test("GET aborted and OPTIONS only continues while open; all methods closed after return", async () => {
  const f = fixture(), r = await run(f);
  await f.post(null, NORMAL, "GET"); await f.post(null, NORMAL, "OPTIONS");
  assert.equal(r.forwarded, true); assert.deepEqual(f.calls.slice(-2), ["abort", "abort"]);
});