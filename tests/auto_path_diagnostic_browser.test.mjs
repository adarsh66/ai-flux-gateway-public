import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { SOURCE } from "../scripts/deployment/auto_path_diagnostic_browser.mjs";

const SHA = "a".repeat(64), nonce = "b".repeat(32);
function binding() {
  return { scope: "AUTO_PATH_DIAGNOSTIC_ONE_NEW_ATTEMPT", correction_of: "GLOBAL_ORIGINAL_PATH_CONJUNCTION",
    parent_disk_verified: true, parent_claim_durable: true, prerequisite_offline_verified: true,
    manifest_sha256: SHA, parent_intent_sha256: SHA, shared_owner_sha256: SHA,
    reservation_sha256: SHA, browser_source_sha256: SHA, review_sha256: SHA, claim_sha256: SHA, nonce,
    end: new Date(Date.now() + 1800000).toISOString(), verified_at_utc: new Date().toISOString(),
    reservation: { manifest_sha256: SHA, IP: "167.103.66.248", attempt_budget: 1, scoring_budget: 1,
      completion_budget: 0, retry_budget: 0, fixed_text: "Please greet me in one short sentence.",
      model: "gpt-5.4-mini", path: "/dev/llm/v1;rev=2/chat/completions", browser_source_sha256: SHA,
      review_sha256: SHA, nonce } };
}
function fixture() {
  const calls = [];
  const message = { isEnabled: async () => true, fill: async text => { calls.push("fill"); message.text = text; },
    inputValue: async () => message.text, press: async key => { calls.push(key); } };
  const page = { route: async (_, handler) => { calls.push("route"); page.handler = handler; },
    getByRole: role => role === "textbox" ? message : { isEnabled: async () => true },
    waitForResponse: (_, options) => { assert.equal(options.timeout, 20000); calls.push("wait"); return Promise.reject(Error("fixture timeout")); } };
  return { page, calls };
}
async function run(b, f) {
  b.reservation.end ??= b.end;
  const ctx = vm.createContext({ page: f.page, binding: b });
  assert.equal(vm.runInContext("typeof setTimeout", ctx), "undefined");
  return JSON.parse(JSON.stringify(await vm.runInContext(`(${SOURCE})(page,binding)`, ctx)));
}
test("standalone successor runs without timers or Node and keeps guard closed", async () => {
  const f = fixture(), result = await run(binding(), f);
  assert.deepEqual(f.calls, ["route", "fill", "wait", "Control+Enter"]);
  assert.equal(result.guard_retained_closed, true);
  assert.equal(result.keyboard_invocations, 1);
  assert.equal(result.scorer_schema_proven, false); // mock is NOT live proof
  const route = { request: () => ({ method: () => "POST" }), abort: async () => f.calls.push("abort") };
  await f.page.handler(route);
  assert.equal(f.calls.at(-1), "abort");
  assert.doesNotMatch(SOURCE, /setTimeout|clearTimeout|node:|process\.|fetch\(|\.click\(/);
});
for (const [field, value] of [["nonce", "bad"], ["review_sha256", "bad"], ["claim_sha256", "bad"],
  ["scope", "DIAGNOSTIC06_CORRECTION_ONE_USER_ATTEMPT"], ["correction_of", "old"],
  ["prerequisite_offline_verified", false], ["parent_disk_verified", false], ["parent_claim_durable", false],
  ["verified_at_utc", "2020-01-01"], ["browser_source_sha256", "b".repeat(64)]]) {
  test(`successor binding rejects ${field} before interaction`, async () => {
    const b = binding(), f = fixture(); b[field] = value;
    const result = await run(b, f);
    assert.deepEqual(f.calls, []); assert.equal(result.keyboard_invocations, 0);
  });
}
for (const [field, value] of [["nonce", "c".repeat(32)], ["review_sha256", "c".repeat(64)],
  ["IP", "167.103.63.12"], ["attempt_budget", 2], ["completion_budget", 1], ["retry_budget", 1]]) {
  test(`successor reservation rejects ${field}`, async () => {
    const b = binding(), f = fixture(); b.reservation[field] = value;
    assert.equal((await run(b, f)).keyboard_invocations, 0); assert.deepEqual(f.calls, []);
  });
}