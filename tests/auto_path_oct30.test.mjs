import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { renderProposal, admissionExpression, sha256 } from "../scripts/proposals/auto_global_path_exception.mjs";
import { IP, OLD_IP, renderOct30, expression } from "../scripts/proposals/auto_path_oct30.mjs";
import { SOURCE } from "../scripts/deployment/auto_path_oct30_browser.mjs";
import { SOURCE as historical } from "../scripts/deployment/auto_path_diagnostic_browser.mjs";

const root = new URL("../", import.meta.url);
const read = name => readFileSync(new URL(name, root));
const home = ".deployment/auto-offline-revision-20261029T060302997824Z/";
const capture = JSON.parse(read(home + "scoring-diagnostic01/prepare-capture.json"));
const window = { start: "2026-10-30T01:00:00Z", end: "2026-10-30T01:30:00Z" }; // fixture, never a frozen live window
const input = { globalOriginal: Buffer.from(capture.inheritance["/policies/policy?format=xml"].body.properties.value),
  diagnosticOriginal: read(home + "scoring-diagnostic06/diagnostic.xml"), window };

test("Oct30 native renderer proves one finite IP substitution each, all other bytes exact", () => {
  const old = renderProposal(input), fresh = renderOct30(input);
  assert.equal(expression(window).replace(IP, OLD_IP), admissionExpression(window));
  for (const name of ["global", "diagnostic"]) {
    assert.equal(fresh[name].toString().split(IP).length - 1, 1);
    assert.equal(fresh[name].includes(Buffer.from(OLD_IP)), false);
    assert.equal(fresh[name].toString().replace(IP, OLD_IP), old[name].toString());
    assert.equal(fresh.diffs[name].before, old.diffs[name].before);
    assert.equal(fresh.diffs[name].offset, old.diffs[name].offset);
    assert.equal(fresh.diffs[name].after_sha256, sha256(Buffer.from(fresh.diffs[name].after)));
    assert.equal(fresh.candidateHashes[name], sha256(fresh[name]));
  }
  assert.deepEqual(fresh.originalHashes, old.originalHashes);
});

function admitted({ ip = IP, id = "aiflux-dev-unified;rev=2", path = "/dev/llm/v1;rev=2/chat/completions",
  method = "POST", revision = "2", at = "2026-10-30T01:01:00Z" } = {}) {
  const predicate = expression(window).replaceAll("DateTime.UtcNow.Ticks", "nowTicks")
    .replaceAll(" == ", " === ").replace(/\b(\d+)L\b/g, "$1n");
  return vm.runInNewContext(predicate, { context: { Api: { Id: id, Revision: revision },
    Product: { Id: "aiflux" }, Subscription: { Id: "e9f2abb0-930b-598a-b210-0ab0b279127f" },
    Request: { Method: method, IpAddress: ip, OriginalUrl: { Path: path },
      Headers: { "X-Forwarded-For": IP }, Url: { Path: "/dev/llm/v1;rev=2/chat/completions" } } },
    nowTicks: BigInt(Date.parse(at)) * 10000n + 621355968000000000n }, { timeout: 100 });
}
for (const id of ["aiflux-dev-unified", "aiflux-dev-unified;rev=2"]) {
  for (const path of ["/dev/llm/v1/chat/completions", "/dev/llm/v1;rev=2/chat/completions"]) {
    test("Oct30 predicate permits only newIP for fixed representation " + id + " " + path, () => {
      assert.equal(admitted({ id, path }), true);
      assert.equal(admitted({ id, path, ip: OLD_IP }), false);
    });
  }
}
for (const change of [{ ip: "192.0.2.1" }, { ip: IP + "/32" }, { ip: "::ffff:" + IP },
  { method: "GET" }, { revision: "1" }, { id: "aiflux-dev-unified;rev=2-evil" },
  { path: "/dev/llm/v1;rev=2/chat/completions?x=1" }, { path: "/dev/llm/v1;rev=2/chat/completions/" },
  { at: window.end }, { at: "2026-10-30T00:59:59Z" }]) {
  test("Oct30 context-only predicate remains closed " + JSON.stringify(change), () => {
    assert.equal(admitted(change), false);
  });
}

for (const key of ["ip", "paths", "headers", "body", "subscription", "product", "authorized"]) {
  test("Oct30 renderer rejects extra scope " + key, () => assert.throws(() => renderOct30({ ...input, [key]: IP })));
}
for (const key of ["globalOriginal", "diagnosticOriginal"]) {
  test("Oct30 renderer rejects predecessor drift " + key, () => assert.throws(() => renderOct30({ ...input,
    [key]: Buffer.concat([input[key], Buffer.from(" ")]) })));
}
test("all173 consumed source hashes remain exact, rather than adopting diagnostic06's older source baseline", () => {
  const manifestBytes = read(".deployment/auto-path-diagnostic-20261029T1410225944396Z/manifest.json");
  assert.equal(sha256(manifestBytes), "04c09dfb6c64b50a87f5a1e0ffebeeec01e1ec7232e2bcd82ba27318cc6eef91");
  const manifest = JSON.parse(manifestBytes);
  assert.equal(Object.keys(manifest.sources).length, 173);
  assert.deepEqual(Object.entries(manifest.sources).filter(([name, hash]) => sha256(read(name)) !== hash), []);
});
test("independent native whole-account proof binds actual authorized storage addition and no other drift", () => {
  const home = ".deployment/storage-firewall-167-103-67-80-20261030/";
  const bytes = read(home + "final-offline-audit.json");
  assert.equal(sha256(bytes), "92f2b40369ce793e6f6b3f490e6bf244b1c2415f90f36d332fc16bfc22d777d8");
  const audit = JSON.parse(bytes), load = name => JSON.parse(read(home + name));
  for (const [name, digest] of Object.entries(audit.evidence_sha256)) {
    assert.equal(name.includes("/"), false);
    assert.equal(sha256(read(home + name)), digest);
  }
  const authorization = load("authorization.json"), before = load("before.json").account;
  assert.equal(authorization.source, "explicit_current_user_message");
  assert.equal(authorization.ip, IP);
  assert.equal(authorization.scope, "one_IP_addition_only_not_Auto_or_deployment");
  const expected = structuredClone(before);
  assert.equal(expected.properties.networkAcls.ipRules.some(rule => rule.value === IP), false);
  expected.properties.networkAcls.ipRules.push({ value: IP, action: "Allow" });
  for (const name of ["independent-after.json", "final-account.json"]) {
    assert.deepEqual(load(name).account, expected);
  }
  assert.equal(audit.actual_wire_mutations, 1);
  assert.equal(load("wire-response.json").http_status, 200);
  assert.equal(load("blob-head.json").method, "HEAD");
  assert.equal(load("blob-head.json").http_status, 200);
  assert.equal(load("result.json").success, true);
});
test("standalone browser source differs only at exact reservation IP guard", () => {
  assert.equal(SOURCE.replace('r.IP === "' + IP + '"', 'r.IP === "' + OLD_IP + '"'), historical);
  assert.equal(SOURCE.split(IP).length - 1, 1);
  assert.doesNotMatch(SOURCE, /setTimeout|clearTimeout|node:|process\.|fetch\(|\.click\(/);
});

const SHA = "a".repeat(64), nonce = "b".repeat(32);
function binding() {
  const end = new Date(Date.now() + 1800000).toISOString();
  return { scope: "AUTO_PATH_DIAGNOSTIC_ONE_NEW_ATTEMPT", correction_of: "GLOBAL_ORIGINAL_PATH_CONJUNCTION",
    parent_disk_verified: true, parent_claim_durable: true, prerequisite_offline_verified: true,
    manifest_sha256: SHA, parent_intent_sha256: SHA, shared_owner_sha256: SHA, reservation_sha256: SHA,
    browser_source_sha256: SHA, review_sha256: SHA, claim_sha256: SHA, nonce, end,
    verified_at_utc: new Date().toISOString(), reservation: { manifest_sha256: SHA, IP, end,
      attempt_budget: 1, scoring_budget: 1, completion_budget: 0, retry_budget: 0,
      fixed_text: "Please greet me in one short sentence.", model: "gpt-5.4-mini",
      path: "/dev/llm/v1;rev=2/chat/completions", browser_source_sha256: SHA, review_sha256: SHA, nonce } };
}
function fixture() {
  const calls = [];
  const message = { isEnabled: async () => true, fill: async text => { calls.push("fill"); message.text = text; },
    inputValue: async () => message.text, press: async key => calls.push(key) };
  const page = { route: async (_, handler) => { calls.push("route"); page.handler = handler; },
    getByRole: role => role === "textbox" ? message : { isEnabled: async () => true },
    waitForResponse: (_, options) => { assert.equal(options.timeout, 20000); calls.push("wait"); return Promise.reject(Error("TEST_ONLY")); } };
  return { page, calls };
}
async function run(b, f) {
  const ctx = vm.createContext({ page: f.page, binding: b });
  assert.equal(vm.runInContext("typeof setTimeout", ctx), "undefined");
  return JSON.parse(JSON.stringify(await vm.runInContext(`(${SOURCE})(page,binding)`, ctx)));
}
test("newIP browser fixture remains one-shot and route-closed, not live proof", async () => {
  const f = fixture(), value = await run(binding(), f);
  assert.deepEqual(f.calls, ["route", "fill", "wait", "Control+Enter"]);
  assert.equal(value.keyboard_invocations, 1);
  assert.equal(value.guard_retained_closed, true);
  assert.equal(value.scorer_schema_proven, false);
  const route = { request: () => ({ method: () => "POST" }), abort: async () => f.calls.push("abort") };
  await f.page.handler(route);
  assert.equal(f.calls.at(-1), "abort");
});
for (const ip of [OLD_IP, "167.103.63.12", IP + "/32", "::ffff:" + IP, "0.0.0.0", null, undefined]) {
  test("newIP browser rejects other representation " + ip, async () => {
    const b = binding(), f = fixture(); b.reservation.IP = ip;
    assert.equal((await run(b, f)).keyboard_invocations, 0);
    assert.deepEqual(f.calls, []);
  });
}
for (const [field, value] of [["nonce", "bad"], ["review_sha256", "bad"], ["claim_sha256", "bad"],
  ["prerequisite_offline_verified", false], ["parent_disk_verified", false], ["parent_claim_durable", false],
  ["scope", "old"], ["verified_at_utc", "2020-01-01"]]) {
  test("newIP browser retains binding gate " + field, async () => {
    const b = binding(), f = fixture(); b[field] = value;
    assert.equal((await run(b, f)).keyboard_invocations, 0);
    assert.deepEqual(f.calls, []);
  });
}
for (const [field, value] of [["attempt_budget", 2], ["scoring_budget", 2], ["completion_budget", 1],
  ["retry_budget", 1], ["nonce", "c".repeat(32)], ["model", "other"], ["path", "/dev/llm/v1/chat/completions"]]) {
  test("newIP browser retains reservation gate " + field, async () => {
    const b = binding(), f = fixture(); b.reservation[field] = value;
    assert.equal((await run(b, f)).keyboard_invocations, 0);
    assert.deepEqual(f.calls, []);
  });
}