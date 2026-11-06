import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { SOURCE } from "../scripts/deployment/auto_diagnostic_browser05b.mjs";

const NORMAL = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions";
const REVISION = NORMAL.replace("/v1/", "/v1;rev=2/");
const TEXT = "Please greet me in one short sentence.";
const SHA = "a".repeat(64);
function binding() {
  const end = new Date(Date.now() + 1800000).toISOString();
  return { scope: "DIAGNOSTIC05_05B_ONE_USER_ATTEMPT", parent_disk_verified: true,
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
  const calls = [], handlers = [], listeners = new Map();
  let text = "", savedResponse;
  async function post(data = body(), url = NORMAL, method = "POST") {
    const request = { method: () => method, url: () => url, postDataJSON: () => {
      if (options.parseError) throw Error("SECRET_BODY"); return data;
    } };
    const route = { request: () => request, abort: async () => { calls.push("abort"); },
      continue: async change => {
        calls.push(change?.url ?? "options");
        if (options.continueError) throw Error("SECRET_AUTH");
        if (method === "OPTIONS") return;
        savedResponse = { request: () => request, url: () => REVISION, status: () => options.http ?? 200,
          text: async () => { if (options.textError) throw Error("SECRET_RESPONSE");
            return options.raw ?? JSON.stringify(options.summary ?? summary()); } };
        for (const listener of listeners.get("response") ?? []) void listener(savedResponse);
      } };
    await handlers[0](route);
  }
  const message = { isEnabled: async () => true, fill: async value => { calls.push("fill"); text = value; },
    inputValue: async () => text, press: async key => {
      calls.push(key); if (options.pressError) throw Error("SECRET_PRESS");
      await post(options.body ?? body(), options.url ?? NORMAL);
      if (options.duplicate) await post();
    } };
  const page = { route: async (match, handler) => {
    assert.equal(match({ origin: "https://poc-ids-token-ex-apim.azure-api.net", pathname: "/dev/llm/v1/chat/completions" }), true);
    calls.push("route"); handlers.push(handler);
  }, on: (event, fn) => { listeners.set(event, [...(listeners.get(event) ?? []), fn]); },
  off: (event, fn) => { listeners.set(event, (listeners.get(event) ?? []).filter(f => f !== fn));
    if (options.offError) throw Error("SECRET_OFF"); },
  getByRole: (role, spec) => {
    assert.equal(spec.exact, true);
    return role === "textbox" ? message : { isEnabled: async () => !options.disabled };
  } };
  return { page, calls, post, handlers };
}

async function run(f, b = binding()) {
  // Actual browser constraint reproduction: no process, Buffer, require, URL,
  // node imports, workspace helpers or filesystem; SOURCE alone must execute.
  const context = vm.createContext({ page: f.page, binding: b,
    setTimeout: fn => setTimeout(fn, 5), clearTimeout });
  return JSON.parse(JSON.stringify(await vm.runInContext(`(${SOURCE})(page, binding)`, context)));
}

test("exact SOURCE executes without node/fs/workspace/URL globals, returns real schema", async () => {
  const f = fixture(); const r = await run(f);
  assert.equal(r.status, "SCORER_SCHEMA_PROVEN"); assert.equal(r.scorer_schema_proven, true);
  assert.deepEqual(r.diagnostic, summary()); assert.equal(r.guard_retained_closed, true);
  assert.equal(r.keyboard_invocations, 1); assert.equal(r.scoring_request_count, null);
  assert.deepEqual(f.calls, ["route", "fill", "Control+Enter", REVISION]);
  assert.doesNotMatch(SOURCE, /\bimport\b|\brequire\(|node:|readFile|writeFile|\.click\(|force:|\.evaluate\(|fetch\(/);
});

for (const [field, value] of [["parent_disk_verified", false], ["parent_intent_sha256", "bad"],
  ["shared_owner_sha256", null], ["scope", "NEW_ATTEMPT"], ["verified_at_utc", "2020-01-01"],
  ["end", "invalid"]]) {
  test(`binding ${field} fails before page interaction`, async () => {
    const b = binding(); b[field] = value; const f = fixture(); const r = await run(f, b);
    assert.equal(r.keyboard_invocations, 0); assert.deepEqual(f.calls, []); assert.equal(r.retry_authorized, false);
  });
}
for (const [field, value] of [["IP", "167.103.63.12"], ["scoring_budget", 2], ["completion_budget", 1],
  ["retry_budget", 1], ["fixed_text", "different"], ["browser_source_sha256", "b".repeat(64)]]) {
  test(`reservation ${field} rejected`, async () => {
    const b = binding(); b.reservation[field] = value; const f = fixture();
    assert.equal((await run(f, b)).keyboard_invocations, 0); assert.deepEqual(f.calls, []);
  });
}
for (const options of [{ pressError: true }, { continueError: true }, { parseError: true },
  { disabled: true }, { textError: true }, { offError: true }]) {
  test(`sanitized result evenerror ${Object.keys(options)[0]}; retained closed`, async () => {
    const f = fixture(options), r = await run(f);
    assert.equal(r.guard_retained_closed, true); assert.equal(r.retry_authorized, false);
    assert.doesNotMatch(JSON.stringify(r), /SECRET/);
    const before = f.calls.filter(v => v === REVISION).length;
    await f.post(); assert.equal(f.calls.at(-1), "abort");
    assert.equal(f.calls.filter(v => v === REVISION).length, before);
    if (options.continueError) assert.equal(r.forwarding_attempted, true);
  });
}
test("duplicate and delayed POST remain blocked without cleanup or unroute", async () => {
  const f = fixture({ duplicate: true }); const r = await run(f);
  assert.equal(r.aborted_posts, 1); await f.post();
  assert.equal(f.calls.filter(v => v === REVISION).length, 1); assert.equal(f.calls.at(-1), "abort");
});
for (const mutate of [s => { s.secret = "SECRET"; }, s => { s.key_types.authorization = "String"; },
  s => { s.key_types.model = "SECRET"; }, s => { s.probabilities.greeting = 4; },
  s => { s.probabilities.arithmetic = "SECRET"; }, s => { s.usage.input_tokens = -1; },
  s => { s.usage.total_tokens = 2147483648; }, s => { s.body_within_bound = false; },
  s => { s.scoring_status = 403; }, s => { s.probabilities = null; }]) {
  test(`malformed/secret summary rejected ${mutate.toString()}`, async () => {
    const s = summary(); mutate(s); const r = await run(fixture({ summary: s }));
    assert.equal(r.scorer_schema_proven, false); assert.equal(r.diagnostic, null);
    assert.doesNotMatch(JSON.stringify(r), /SECRET/);
  });
}
for (const raw of ["SECRET", "x".repeat(8193), JSON.stringify({ choices: [{ content: "SECRET" }] })]) {
  test(`raw/oversize/non-summary body not persisted (${raw.length})`, async () => {
    const r = await run(fixture({ raw })); assert.equal(r.diagnostic, null);
    assert.equal(r.scorer_schema_proven, false); assert.doesNotMatch(JSON.stringify(r), /SECRET|choices/);
  });
}
test("valid failure summary is retained, never scoring acceptance", async () => {
  const s = summary(); s.scoring_status = 403; s.schema_valid = false; s.probabilities = null;
  const r = await run(fixture({ summary: s })); assert.deepEqual(r.diagnostic, s);
  assert.equal(r.scorer_schema_proven, false);
});
for (const change of [b => { b.model = "other"; }, b => { b.messages[0].content = "other"; },
  b => { b.stream = true; }, b => { b.max_completion_tokens = 1025; }, b => { b.extra = true; }]) {
  test(`exact original request validation ${change.toString()}`, async () => {
    const data = body(); change(data); const f = fixture({ body: data }); const r = await run(f);
    assert.equal(r.forwarding_attempted, false); assert.equal(r.consumed, true);
    assert.equal(f.calls.includes(REVISION), false);
  });
}