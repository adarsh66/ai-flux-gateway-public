import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { SCOPE, ORIGINAL_GLOBAL_SHA256, ORIGINAL_DIAGNOSTIC_SHA256, sha256,
  renderProposal, assertExactProposal, assessGlobalCleanup, admissionExpression, mockAdmission,
} from "../scripts/proposals/auto_global_path_exception.mjs";

const root = new URL("../", import.meta.url);
const home = ".deployment/auto-offline-revision-20261029T060302997824Z/";
const read = path => readFileSync(new URL(path, root));
// Read only the known policy string from retained local JSON. Never print it.
const capture = JSON.parse(read(home + "scoring-diagnostic01/prepare-capture.json"));
const globalOriginal = Buffer.from(capture.inheritance["/policies/policy?format=xml"].body.properties.value);
const diagnosticOriginal = read(home + "scoring-diagnostic06/diagnostic.xml");
// Explicit EXPIRED historical fixture; no fresh activation interval is selected.
const window = Object.freeze({ start: "2026-10-29T10:16:50Z", end: "2026-10-29T10:46:50Z" });
const now = "2026-10-29T10:20:00Z";
const input = () => ({ globalOriginal, diagnosticOriginal, window });
const context = () => ({ api: { id: SCOPE.apiIds[1], revision: "2" },
  subscription: { id: SCOPE.subscription }, product: { id: "aiflux" },
  request: { method: "POST", ip: SCOPE.ip, originalPath: SCOPE.paths[1] } });
function decode(value, exported = false) {
  if (exported) value = value.replaceAll("&amp;amp;", "&amp;").replaceAll("&amp;lt;", "&lt;").replaceAll("&amp;gt;", "&gt;");
  return value.replaceAll("&quot;", '"').replaceAll("&amp;", "&").replaceAll("&lt;", "<").replaceAll("&gt;", ">");
}
function expression(span, exported) {
  return decode(span.match(/^condition=(['"])(.*)\1$/s)[2], exported);
}
function evaluate(csharp, c, at = now) {
  // Restricted translation for *this* fixed scalar C# predicate only. This is
  // deliberately NOT runtime C# compilation, ARM validation or auth evidence.
  const js = csharp.slice(2, -1).replaceAll("DateTime.UtcNow.Ticks", "nowTicks")
    .replaceAll("DateTime.UtcNow", "now")
    .replaceAll(" == ", " === ")
    .replace(/\b(\d+)L\b/g, "$1n")
    .replace(/DateTime\.Parse\("([0-9TZ:-]+)"\)\.ToUniversalTime\(\)/g, (_, date) => String(Date.parse(date)));
  const ctx = { Api: c.api && { Id: c.api.id, Revision: c.api.revision },
    Subscription: c.subscription && { Id: c.subscription.id }, Product: c.product && { Id: c.product.id },
    Request: { Method: c.request?.method, IpAddress: c.request?.ip, OriginalUrl: { Path: c.request?.originalPath } } };
  return vm.runInNewContext(js, { context: ctx, now: Date.parse(at),
    nowTicks: BigInt(Date.parse(at)) * 10000n + 621355968000000000n }, { timeout: 100 });
}
const proposal = renderProposal(input());
const globalExpression = expression(proposal.diffs.global.after, true);
const diagnosticExpression = expression(proposal.diffs.diagnostic.after, false);
const oldGlobal = expression(proposal.diffs.global.before, true);
function restored(candidate, diff) {
  const after = Buffer.from(diff.after), before = Buffer.from(diff.before);
  assert.ok(candidate.subarray(diff.offset, diff.offset + after.length).equals(after));
  return Buffer.concat([candidate.subarray(0, diff.offset), before, candidate.subarray(diff.offset + after.length)]);
}

test("retained hashes match actual evidence; proposal is not approval", () => {
  assert.equal(sha256(globalOriginal), ORIGINAL_GLOBAL_SHA256);
  assert.equal(sha256(diagnosticOriginal), ORIGINAL_DIAGNOSTIC_SHA256);
  assert.match(proposal.status, /PENDING.*NOT_VALIDATED/);
  assert.equal(proposal.authorized, undefined);
});
test("exactly one condition per policy changes, every other byte restores identically", () => {
  assert.deepEqual(restored(proposal.global, proposal.diffs.global), globalOriginal);
  assert.deepEqual(restored(proposal.diagnostic, proposal.diffs.diagnostic), diagnosticOriginal);
  assert.equal(assertExactProposal(input(), { global: proposal.global, diagnostic: proposal.diagnostic }), true);
  assert.ok(proposal.diagnostic.includes(Buffer.from("<base")));
  assert.equal(proposal.global.toString().split("<choose>").length, globalOriginal.toString().split("<choose>").length);
});
test("original guards are disjoint for both original-path representations", () => {
  const oldDiagnostic = expression(proposal.diffs.diagnostic.before, false);
  for (const originalPath of SCOPE.paths) {
    const c = context(); c.request.originalPath = originalPath;
    assert.equal(!evaluate(oldGlobal, c) && !evaluate(oldDiagnostic, c), false);
  }
});
for (const id of SCOPE.apiIds) for (const path of SCOPE.paths) {
  test(`fixed owned API/revision2 permits representation ${id} ${path}`, () => {
    const c = context(); c.api.id = id; c.request.originalPath = path;
    assert.equal(mockAdmission(c, window, now), true);
    assert.equal(evaluate(globalExpression, c), false);
    assert.equal(evaluate(diagnosticExpression, c), false);
  });
}

const negatives = [
  ["null API", c => { c.api = null; }], ["other API", c => { c.api.id = "aiflux-dev"; }],
  ["validation API", c => { c.api.id = "aiflux-validation"; }],
  ["revision1 suffix", c => { c.api.id = "aiflux-dev-unified;rev=1"; }],
  ["API prefix", c => { c.api.id += "-evil"; }],
  ["API case", c => { c.api.id = c.api.id.toUpperCase(); }],
  ["revision1", c => { c.api.revision = "1"; }], ["revision3", c => { c.api.revision = "3"; }],
  ["numeric revision", c => { c.api.revision = 2; }], ["missing revision", c => { delete c.api.revision; }],
  ["null subscription", c => { c.subscription = null; }],
  ["other subscription", c => { c.subscription.id = "other"; }],
  ["null product", c => { c.product = null; }], ["other product", c => { c.product.id = "other"; }],
  ["GET", c => { c.request.method = "GET"; }], ["OPTIONS", c => { c.request.method = "OPTIONS"; }],
  ["lowercase POST", c => { c.request.method = "post"; }],
  ["wrong source", c => { c.request.ip = "167.103.63.12"; }],
  ["CIDR source", c => { c.request.ip += "/32"; }],
  ["mapped source", c => { c.request.ip = "::ffff:" + SCOPE.ip; }],
  ...["/dev/llm/v1/models", "/dev/v1/chat/completions", "/dev/llm/v1;rev=1/chat/completions",
    "/dev/llm/v1;rev=3/chat/completions", "/dev/llm/v1;rev=02/chat/completions",
    "/dev/llm/v1;rev=2/chat/completions/", "/dev/llm/v1;rev=2/chat/completions/evil",
    "/dev/llm/v1%3Brev=2/chat/completions", "/dev/llm/v1;REV=2/chat/completions",
    "/DEV/llm/v1;rev=2/chat/completions", "/dev/llm/v1;rev=2/chat/completions?x=1",
    "/dev/llm/v1;rev=2/../chat/completions", "/dev/llm/v1;rev=2//chat/completions",
  ].map(path => ["nonexact path " + path, c => { c.request.originalPath = path; }]),
];
for (const [label, change] of negatives) test("closed: " + label, () => {
  const c = context(); change(c);
  assert.equal(mockAdmission(c, window, now), false);
  assert.equal(evaluate(diagnosticExpression, c), true);
  assert.equal(evaluate(globalExpression, c), evaluate(oldGlobal, c));
});

for (const [at, allowed] of [["2026-10-29T10:16:49Z", false], [window.start, true],
  ["2026-10-29T10:46:49Z", true], [window.end, false], ["2026-10-30T00:00:00Z", false]]) {
  test("single shared boundary " + at, () => {
    const c = context(); assert.equal(mockAdmission(c, window, at), allowed);
    assert.equal(evaluate(globalExpression, c, at), !allowed);
    assert.equal(evaluate(diagnosticExpression, c, at), !allowed);
  });
}
test("headers/query/effective URL cannot spoof any context gate", () => {
  const c = context(); c.request.ip = "192.0.2.1"; c.api.revision = "1";
  c.request.headers = { "X-Forwarded-For": SCOPE.ip, "X-Api-Revision": "2", "X-Subscription-Id": SCOPE.subscription };
  c.request.url = SCOPE.paths[1]; c.request.query = { revision: "2" };
  assert.equal(mockAdmission(c, window, now), false);
  assert.equal(evaluate(diagnosticExpression, c), true);
  assert.doesNotMatch(proposal.expression, /Headers|Query|Forwarded|Request\.Url|StartsWith|Contains|Regex/);
});
test("normal-path decisions identical across methods, identities, IPs, time", () => {
  for (const path of ["/dev/v1/models", "/dev/v1/chat/completions", ...SCOPE.paths.slice(0, 1), "/dev/llm/v1/models", "/unknown"])
    for (const method of ["GET", "POST", "OPTIONS"]) for (const id of ["aiflux-dev-unified", "legacy"])
      for (const revision of ["1", "3"]) for (const ip of [SCOPE.ip, "192.0.2.1"])
        for (const at of [window.start, window.end]) {
          const c = context(); c.api = { id, revision }; c.request = { originalPath: path, method, ip };
          assert.equal(evaluate(globalExpression, c, at), evaluate(oldGlobal, c, at));
        }
});
for (const windowBad of [null, {}, { ...window, end: window.start }, { ...window, start: window.end },
  { ...window, end: "2026-10-29T10:46:51Z" }, { ...window, end: "2026-10-29T10:46:50+00:00" },
  { ...window, end: "2026-02-30T10:46:50Z" }, { ...window, end: '2026-10-29T10:46:50Z" || true' },
  { ...window, ip: "0.0.0.0/0" }]) test("reject invalid/broadened interval " + JSON.stringify(windowBad), () => {
  assert.throws(() => admissionExpression(windowBad));
});
test("no caller-controlled scope keys or predecessor adoption", () => {
  for (const key of ["ip", "paths", "apiIds", "subscription", "product", "authorized", "expiry"]) {
    assert.throws(() => renderProposal({ ...input(), [key]: "anything" }));
  }
  for (const key of ["globalOriginal", "diagnosticOriginal"]) {
    assert.throws(() => renderProposal({ ...input(), [key]: Buffer.concat([input()[key], Buffer.from(" ")]) }));
  }
});
test("any extra policy change fails finite allowlist, including base/safety/quotas", () => {
  for (const name of ["global", "diagnostic"]) {
    const candidates = { global: Buffer.from(proposal.global), diagnostic: Buffer.from(proposal.diagnostic) };
    candidates[name] = Buffer.concat([candidates[name], Buffer.from("\n")]);
    assert.throws(() => assertExactProposal(input(), candidates));
  }
  for (const needle of ["base", "llm-content-safety", "quota-by-key", "authentication-managed-identity"]) {
    assert.ok(proposal.diagnostic.includes(Buffer.from(needle)));
    assert.throws(() => assertExactProposal(input(), { global: proposal.global,
      diagnostic: Buffer.from(proposal.diagnostic.toString().replace(needle, "REMOVED")) }));
  }
});
test("renderer import/source has no mutation, network, CLI, FS or implicit clock", () => {
  const source = read("scripts/proposals/auto_global_path_exception.mjs").toString();
  assert.deepEqual([...source.matchAll(/from "([^"]+)"/g)].map(x => x[1]), ["node:crypto"]);
  assert.doesNotMatch(source, /fetch\(|https?:\/\/|node:fs|child_process|Date\.now\(|process\.|writeFile|setTimeout/);
  assert.deepEqual(globalOriginal, input().globalOriginal);
  assert.deepEqual(diagnosticOriginal, input().diagnosticOriginal);
});

test("expiry-unrestricted cleanup binds exact original hash and candidate If-Match", () => {
  const evidence = { observedGlobal: proposal.global, installedEtag: '"fixture-candidate"', observedEtag: '"fixture-candidate"' };
  const cleanup = assessGlobalCleanup(input(), evidence);
  assert.equal(sha256(cleanup.restoreExport), ORIGINAL_GLOBAL_SHA256);
  assert.deepEqual(cleanup.restoreExport, globalOriginal);
  assert.equal(cleanup.requiredIfMatch, evidence.observedEtag);
  assert.equal(cleanup.expiryBlocksCleanup, false);
  assert.equal(cleanup.retryBudget, 0);
  assert.equal(cleanup.authorized, undefined);
});
for (const etag of [undefined, null, "", "*", 'W/"*"\r\nInjected: true', "unquoted", '"x"\n']) {
  test("reject unsafe cleanup ETag " + JSON.stringify(etag), () => {
    assert.throws(() => assessGlobalCleanup(input(), { observedGlobal: proposal.global,
      installedEtag: etag, observedEtag: etag }));
  });
}
test("cleanup stops on ETag or byte drift and cannot adopt another predecessor", () => {
  const evidence = { observedGlobal: proposal.global, installedEtag: '"installed"', observedEtag: '"later"' };
  assert.throws(() => assessGlobalCleanup(input(), evidence));
  assert.throws(() => assessGlobalCleanup(input(), { ...evidence, observedEtag: evidence.installedEtag,
    observedGlobal: Buffer.concat([proposal.global, Buffer.from(" ")]) }));
  assert.throws(() => assessGlobalCleanup(input(), { ...evidence, observedGlobal: globalOriginal }));
  assert.throws(() => assessGlobalCleanup({ ...input(), globalOriginal: Buffer.from("replacement") }, evidence));
});

test("existing diagnostic06 source bindings and customer retained input bindings unchanged", () => {
  const manifest = JSON.parse(read(home + "scoring-diagnostic06/manifest.json"));
  const mismatches = Object.entries(manifest.sources)
    .filter(([name, hash]) => sha256(read(name)) !== hash).map(([name]) => name);
  assert.deepEqual(mismatches, [], "retained diagnostic06 source drift");
  const customer = JSON.parse(read(".deployment/customer-send-independent-reconcile-20261029T113000Z/preflight.json"));
  assert.ok(Object.keys(customer.input_hashes).length > 0);
  assert.deepEqual(Object.entries(customer.input_hashes)
    .filter(([name, hash]) => sha256(read(name)) !== hash).map(([name]) => name), [], "retained customer input drift");
});