import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { keyboardAttempt, boundReservation, TEXT, NORMAL, REVISION } from "../scripts/deployment/auto_diagnostic_browser05.mjs";

const body = () => ({ model: "gpt-5.4-mini", messages: [{ role: "user", content: TEXT }], stream: false, max_completion_tokens: 1024 });
const binding = () => {
  const sha = "a".repeat(64), end = new Date(Date.now() + 180000).toISOString();
  return { sha, end, reservation: { manifest_sha256: sha, end, IP: "167.103.66.248", attempt_budget: 1,
    scoring_budget: 1, completion_budget: 0, retry_budget: 0, fixed_text: TEXT, model: "gpt-5.4-mini",
    path: "/dev/llm/v1;rev=2/chat/completions" } };
};
function fixture({ pressFails = false, fillFails = false, continueFails = false, malformed = false,
    repeat = false, emit = true, intentFails = false, badUrl = false, enabled = true } = {}) {
  let handler, observer, value = "", intents = 0, result, pressCount = 0, continueCount = 0, abortCount = 0;
  const events = [];
  const route = { request: () => ({ method: () => "POST", url: () => badUrl ? REVISION : NORMAL,
    postDataJSON: () => malformed ? { ...body(), stream: true } : body() }),
    continue: async options => { events.push("continue"); continueCount++; assert.deepEqual(options, { url: REVISION });
      if (continueFails) throw new Error("secret-bearing message must not escape"); },
    abort: async () => { abortCount++; } };
  const page = { route: async (_, h) => { events.push("route"); handler = h; },
    on: (_, h) => { observer = h; }, off: () => { events.push("off"); },
    unroute: async () => { throw new Error("must remain closed until offline verified"); },
    getByRole: (role, options) => {
      assert.equal(options.exact, true);
      if (role === "button") { assert.equal(options.name, "Send"); return { isEnabled: async () => enabled }; }
      assert.equal(role, "textbox"); assert.equal(options.name, "Message");
      return { isEnabled: async () => enabled, fill: async text => { events.push("fill"); value = text;
        if (fillFails) throw new Error("sensitive fill error"); }, inputValue: async () => value,
        press: async key => { assert.equal(key, "Control+Enter"); events.push("press"); pressCount++;
          await handler(route); if (repeat) await handler(route);
          if (emit) observer({ url: () => REVISION, request: () => ({ method: () => "POST" }), status: () => 403 });
          if (pressFails) throw new Error("sensitive timeout"); } };
    } };
  const journal = { intent: v => { events.push("intent"); if (intentFails || intents++) throw new Error("consumed");
      assert.equal(v.new_scope_consumed, true); }, result: v => { assert.equal(result, undefined); result = v; events.push("result"); } };
  return { page, journal, route, events, handler: () => handler,
    stats: () => ({ result, pressCount, continueCount, abortCount, intents }) };
}

test("normal existing keyboard submits once with durable intent before any interaction and safe403", async () => {
  const f = fixture({ repeat: true });
  await keyboardAttempt(f.page, binding(), f.journal);
  assert.deepEqual(f.events.slice(0, 4), ["intent", "route", "fill", "press"]);
  const { result, pressCount, continueCount, abortCount } = f.stats();
  assert.equal(pressCount, 1); assert.equal(continueCount, 1); assert.equal(abortCount, 1);
  assert.equal(result.consumed, true); assert.equal(result.forwarded, true); assert.equal(result.http_status, 403);
  assert.equal(result.new_scope_consumed, true); assert.equal(result.guard_retained_closed, true);
  assert.equal(result.retry_authorized, false); assert.equal(result.auth_inspected, false);
  await f.handler()(f.route);
  assert.equal(f.stats().continueCount, 1); assert.equal(f.stats().abortCount, 2);
});

test("press exception AFTER forwarding still journals consumed/forwarded in finally without raw error", async () => {
  const f = fixture({ pressFails: true });
  await keyboardAttempt(f.page, binding(), f.journal);
  const { result } = f.stats();
  assert.equal(result.consumed, true); assert.equal(result.forwarded, true);
  assert.equal(result.status, "FAILED_OR_TIMEOUT_NO_RETRY");
  assert.equal(JSON.stringify(result).includes("sensitive"), false);
  assert.equal(JSON.stringify(result).includes(TEXT), false);
});

test("continue failure is ambiguous not zero and permanently closes handler", async () => {
  const f = fixture({ continueFails: true, emit: false });
  await keyboardAttempt(f.page, binding(), f.journal);
  const { result } = f.stats();
  assert.equal(result.consumed, true); assert.equal(result.forwarding_attempted, true); assert.equal(result.forwarded, false);
  assert.equal(result.wire_outcome, "UNKNOWN_SCORER_COUNT_NOT_TELEMETRY");
  await f.handler()(f.route); assert.equal(f.stats().continueCount, 1);
});

test("fill exception still consumes new scope with zero press and no forwarding observed", async () => {
  const f = fixture({ fillFails: true });
  await keyboardAttempt(f.page, binding(), f.journal);
  assert.equal(f.stats().result.new_scope_consumed, true); assert.equal(f.stats().pressCount, 0);
  assert.equal(f.stats().result.consumed, false); assert.equal(f.stats().result.forwarded, false);
  assert.equal(f.stats().result.guard_retained_closed, true);
});

test("disabled control consumes scope without trying keyboard or click", async () => {
  const f = fixture({ enabled: false });
  await keyboardAttempt(f.page, binding(), f.journal);
  assert.equal(f.stats().pressCount, 0); assert.equal(f.stats().result.new_scope_consumed, true);
});

test("durable intent failure rejects before installing or interacting", async () => {
  const f = fixture({ intentFails: true });
  await assert.rejects(keyboardAttempt(f.page, binding(), f.journal));
  assert.deepEqual(f.events, ["intent"]); assert.equal(f.stats().result, undefined);
});

test("same journal cannot submit twice", async () => {
  const f = fixture();
  const b = binding();
  await keyboardAttempt(f.page, b, f.journal);
  await assert.rejects(keyboardAttempt(f.page, b, f.journal));
  assert.equal(f.stats().pressCount, 1);
});

for (const options of [{ malformed: true }, { badUrl: true }]) test("malformed or unexpected URL consumes then aborts", async () => {
  const f = fixture({ ...options, pressFails: true, emit: false });
  await keyboardAttempt(f.page, binding(), f.journal);
  assert.equal(f.stats().result.consumed, true); assert.equal(f.stats().continueCount, 0);
  assert.equal(f.stats().abortCount, 1);
});

for (const [field, value] of [["IP", "167.103.63.12"], ["scoring_budget", 2], ["completion_budget", 1],
  ["retry_budget", 1], ["model", "auto"], ["manifest_sha256", "bad"], ["fixed_text", "other"]]) {
  test(`bad reservation ${field} rejects before interaction`, async () => {
    const b = binding(), f = fixture(); b.reservation[field] = value;
    assert.throws(() => boundReservation(b.reservation, b.sha, b.end));
    await assert.rejects(keyboardAttempt(f.page, b, f.journal)); assert.deepEqual(f.events, []);
  });
}

test("expired window rejects before durable intent", async () => {
  const b = binding(), f = fixture(); b.end = b.reservation.end = new Date(Date.now() - 1).toISOString();
  await assert.rejects(keyboardAttempt(f.page, b, f.journal)); assert.deepEqual(f.events, []);
});

test("actual response timeout remains CLOSED, records finally, and does not retry", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const f = fixture({ emit: false }), promise = keyboardAttempt(f.page, binding(), f.journal);
  // Drain bounded microtasks to reach the timeout, never a real/browser sleep.
  for (let i = 0; i < 30; i++) await Promise.resolve();
  t.mock.timers.tick(15000);
  await promise;
  assert.equal(f.stats().pressCount, 1); assert.equal(f.stats().result.status, "FAILED_OR_TIMEOUT_NO_RETRY");
  assert.equal(f.stats().result.guard_retained_closed, true);
  await f.handler()(f.route); assert.equal(f.stats().continueCount, 1);
});

test("source has no forceclick/HTTP/auth/body inspection and imports do not submit", () => {
  const source = readFileSync(new URL("../scripts/deployment/auto_diagnostic_browser05.mjs", import.meta.url), "utf8");
  for (const token of [".click(", ".fetch(", ".headers(", ".storageState(", ".evaluate(", ".json(", ".text(", "force: true"]) {
    assert.equal(source.includes(token), false, token);
  }
  assert.equal(source.includes('openSync(resolve(PACKAGE, name), "wx"'), true);
  assert.equal(source.includes("fsyncSync(fd)"), true);
});