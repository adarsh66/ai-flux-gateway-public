import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { successorAttempt } from "../scripts/proposals/auto_path_browser.mjs";
const normal = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions";
const revision = normal.replace("v1/", "v1;rev=2/");
const body = () => ({ model: "gpt-5.4-mini", stream: false, max_completion_tokens: 1024,
  messages: [{ role: "user", content: "Please greet me in one short sentence." }] });
const binding = () => ({ scope: "AUTO_PATH_SUCCESSOR_ONE_ATTEMPT", parent_disk_verified: true,
  supervisor_live: true, exact_online_readback: true, manifest_sha256: "a".repeat(64),
  reservation_sha256: "b".repeat(64), browser_source_sha256: "c".repeat(64),
  scoring_budget: 1, completion_budget: 0, retry_budget: 0, IP: "167.103.66.248",
  subscription: "e9f2abb0-930b-598a-b210-0ab0b279127f",
  end: new Date(Date.now() + 1800000).toISOString(), verified_at_utc: new Date().toISOString() });
const summary = () => ({ scoring_status: 200, schema_valid: true, body_within_bound: true,
  key_types: { answers: "Object" }, probabilities: { greeting: 0.9, arithmetic: 0.1 },
  usage: { input_tokens: null, output_tokens: null, total_tokens: null } });
function fixture(value = body(), url = normal, result = summary()) {
  let handler, continued = [], aborts = 0;
  const req = { method: () => "POST", url: () => url, postDataJSON: () => value };
  const route = { request: () => req, continue: async x => { continued.push(x); }, abort: async () => { aborts++; } };
  const page = { route: async (_, fn) => { handler = fn; },
    waitForResponse: async predicate => {
      // Microtask scheduling only: no timers injected into sandbox.
      await Promise.resolve(); await Promise.resolve();
      const response = { url: () => revision, request: () => req, status: () => 200,
        text: async () => JSON.stringify(result) };
      return predicate(response) ? response : null;
    } };
  return { page, action: () => handler(route), duplicate: () => handler(route), continued, aborts: () => aborts };
}
test("URL-only forwarding once; retained guard aborts duplicates", async () => {
  const f = fixture(); const r = await successorAttempt(f.page, binding(), f.action);
  assert.equal(r.forwarding_attempted, true);
  assert.deepEqual(f.continued, [{ url: revision }]);
  await f.duplicate(); assert.equal(f.aborts(), 1);
  assert.equal(r.guard_retained_closed, true);
  assert.equal(r.scorer_schema_proven, true);
});
for (const [name, change] of [
  ["wrong model", b => { b.model = "auto"; }], ["stream", b => { b.stream = true; }],
  ["extra body", b => { b.routing_profile = "quality"; }], ["output", b => { b.max_completion_tokens = 1025; }],
  ["prompt", b => { b.messages[0].content = "other"; }], ["extra message", b => { b.messages.push(b.messages[0]); }],
]) test(name + " consumes and aborts first POST", async () => {
  const b = body(); change(b); const f = fixture(b);
  const r = await successorAttempt(f.page, binding(), f.action);
  assert.equal(r.consumed, true); assert.equal(f.continued.length, 0); assert.equal(f.aborts(), 1);
});
for (const key of ["parent_disk_verified", "supervisor_live", "exact_online_readback"]) test("requires " + key, async () => {
  const f = fixture(), b = binding(); b[key] = false;
  const r = await successorAttempt(f.page, b, f.action); assert.equal(r.actions, 0);
});
test("expired interval cannot invoke parent action", async () => {
  const f = fixture(), b = binding(); b.end = "2000-01-01T00:00:00Z";
  assert.equal((await successorAttempt(f.page, b, f.action)).actions, 0);
});
test("other gateway path cannot forward", async () => {
  const f = fixture(body(), revision); const r = await successorAttempt(f.page, binding(), f.action);
  assert.equal(r.consumed, true); assert.equal(r.forwarding_attempted, false);
});
test("sandbox uses no timers/Node injection or credential APIs", async () => {
  const helper = vm.runInNewContext("(" + successorAttempt.toString() + ")", {});
  const f = fixture(); await helper(f.page, binding(), f.action);
  assert.equal(f.continued.length, 1);
  const text = readFileSync(new URL("../scripts/proposals/auto_path_browser.mjs", import.meta.url), "utf8");
  assert.doesNotMatch(text, /setTimeout|setInterval|request\.headers|localStorage|sessionStorage|fetch\(/);
});
for (const [name, change] of [
  ["extra summary", v => { v.secret = "synthetic-not-real"; }],
  ["scorer401", v => { v.scoring_status = 401; }],
  ["invalid probabilities", v => { v.probabilities.greeting = 2; }],
  ["negative usage", v => { v.usage.input_tokens = -1; }],
  ["unknown key type", v => { v.key_types.authorization = "String"; }],
]) test("no acceptance for " + name, async () => {
  const value = summary(); change(value); const f = fixture(body(), normal, value);
  const r = await successorAttempt(f.page, binding(), f.action);
  assert.equal(r.scorer_schema_proven, false); assert.equal(r.summary, null);
});