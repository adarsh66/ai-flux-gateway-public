/** OFFLINE PROPOSAL ONLY. No I/O, clock, authorization, executor or publication API.
 * Inputs are retained XML-export UTF-8 bytes, not ARM response/envelope bytes.
 * The only configurable scope is an explicit <=30 minute UTC fixture interval.
 */
import { createHash } from "node:crypto";

export const SCOPE = Object.freeze({
  apiIds: Object.freeze(["aiflux-dev-unified", "aiflux-dev-unified;rev=2"]),
  revision: "2", product: "aiflux",
  subscription: "e9f2abb0-930b-598a-b210-0ab0b279127f", ip: "167.103.66.248",
  paths: Object.freeze(["/dev/llm/v1/chat/completions", "/dev/llm/v1;rev=2/chat/completions"]),
});
export const ORIGINAL_GLOBAL_SHA256 = "936a862488c18ea2f11d27bfbe99f653b26edead85546eda171cdb7229600d31";
export const ORIGINAL_DIAGNOSTIC_SHA256 = "1897a95092b04282ae75b30194a5c7f0915230235d35114fa03dd3c1464df930";
export const sha256 = value => createHash("sha256").update(value).digest("hex");
const require = (value, message) => { if (!value) throw new Error(message); };

function exactKeys(value, keys) {
  require(value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).sort().join("|") === [...keys].sort().join("|"), "finite input keys");
}
function utc(value) {
  require(typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value), "literal UTC seconds required");
  const ms = Date.parse(value);
  require(Number.isFinite(ms) && new Date(ms).toISOString() === value.replace("Z", ".000Z"), "valid UTC date");
  return ms;
}
function interval(window) {
  exactKeys(window, ["start", "end"]);
  const start = utc(window.start), end = utc(window.end);
  require(end > start && end - start <= 30 * 60 * 1000, "bounded single interval");
  return { start, end };
}
function text(bytes, expected) {
  require(Buffer.isBuffer(bytes) && sha256(bytes) === expected, "exact retained predecessor hash");
  const value = bytes.toString("utf8");
  require(Buffer.from(value, "utf8").equals(bytes), "exact UTF-8");
  return value;
}
function encode(value, exported) {
  // The retained global XML export has ONE additional observed entity layer.
  // Do not normalize/serialize the surrounding document or guess rawxml syntax.
  let encoded = value.replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  if (exported) encoded = encoded.replaceAll("&amp;", "&amp;amp;")
    .replaceAll("&lt;", "&amp;lt;").replaceAll("&gt;", "&amp;gt;");
  return encoded;
}

/** Fixed trusted APIM context only: never request headers, query, effective URL,
 * prefix matching, case folding, regex, forwarded IP or caller-selected IDs.
 */
export function admissionExpression(window) {
  const { start, end } = interval(window);
  const ticks = ms => (BigInt(ms) * 10000n + 621355968000000000n).toString() + "L";
  return 'context.Api != null && (context.Api.Id == "' + SCOPE.apiIds[0]
    + '" || context.Api.Id == "' + SCOPE.apiIds[1] + '") && context.Api.Revision == "2"'
    + ' && context.Subscription != null && context.Product != null'
    + ' && context.Product.Id == "aiflux" && context.Subscription.Id == "' + SCOPE.subscription + '"'
    + ' && context.Request.Method == "POST" && context.Request.IpAddress == "167.103.66.248"'
    + ' && (context.Request.OriginalUrl.Path == "' + SCOPE.paths[0]
    + '" || context.Request.OriginalUrl.Path == "' + SCOPE.paths[1] + '")'
    + ' && DateTime.UtcNow.Ticks >= ' + ticks(start)
    + ' && DateTime.UtcNow.Ticks < ' + ticks(end);
}

function oneCondition(value, offset) {
  const pattern = /condition=(['"])(.*?)\1/gs;
  pattern.lastIndex = offset;
  const match = pattern.exec(value);
  require(match !== null, "one known condition required");
  return { offset: match.index, before: match[0], expression: match[2], quote: match[1] };
}
function edit(original, span, expression, exported) {
  const after = "condition=" + span.quote + encode(expression, exported) + span.quote;
  const candidate = original.slice(0, span.offset) + after + original.slice(span.offset + span.before.length);
  const beforeBytes = Buffer.from(span.before), afterBytes = Buffer.from(after);
  const offset = Buffer.byteLength(original.slice(0, span.offset));
  return { bytes: Buffer.from(candidate), diff: Object.freeze({ offset,
    before: span.before, after, before_sha256: sha256(beforeBytes), after_sha256: sha256(afterBytes) }) };
}
function decodeKnownExport(value) {
  return value.replaceAll("&quot;", '"').replaceAll("&amp;amp;", "&amp;")
    .replaceAll("&amp;lt;", "&lt;").replaceAll("&amp;gt;", "&gt;")
    .replaceAll("&amp;", "&").replaceAll("&lt;", "<").replaceAll("&gt;", ">");
}

/** Produces in-memory proposal bytes and exactly two finite condition spans.
 * No new window is frozen: callers/tests provide dates; no current-time default.
 * Existing diagnostic06 is an immutable fixture, NEVER a successor to execute.
 */
export function renderProposal(input) {
  exactKeys(input, ["globalOriginal", "diagnosticOriginal", "window"]);
  const global = text(input.globalOriginal, ORIGINAL_GLOBAL_SHA256);
  const diagnostic = text(input.diagnosticOriginal, ORIGINAL_DIAGNOSTIC_SHA256);
  const expression = admissionExpression(input.window);
  const globalSpan = oneCondition(global, global.indexOf("<inbound>"));
  const old = decodeKnownExport(globalSpan.expression);
  require(old.startsWith("@(!(") && old.endsWith(")"), "known denial predicate");
  const g = edit(global, globalSpan, "@((" + old.slice(2, -1) + ") && !(" + expression + "))", true);
  const scopeMarker = diagnostic.indexOf("diagnostic_scope_closed");
  require(scopeMarker > 0, "known diagnostic guard");
  const previous = diagnostic.lastIndexOf("<when ", scopeMarker);
  const diagnosticSpan = oneCondition(diagnostic, previous);
  require(diagnosticSpan.offset < scopeMarker && diagnosticSpan.expression.startsWith("@(context.Subscription == null"), "exact old scope predicate");
  const d = edit(diagnostic, diagnosticSpan, "@(!(" + expression + "))", false);
  return {
    status: "PROPOSAL_PENDING_EXPLICIT_NARROW_AUTHORIZATION_NOT_VALIDATED",
    window: Object.freeze({ ...input.window }), expression,
    global: g.bytes, diagnostic: d.bytes,
    diffs: Object.freeze({ global: g.diff, diagnostic: d.diff }),
    originalHashes: Object.freeze({ global: ORIGINAL_GLOBAL_SHA256, diagnostic: ORIGINAL_DIAGNOSTIC_SHA256 }),
    candidateHashes: Object.freeze({ global: sha256(g.bytes), diagnostic: sha256(d.bytes) }),
    // Not a wire request, saved plan, receipt, cleanup intent or permission.
    cleanupRequirement: "Exact original bytes/hash; fresh candidate hash and opaque ETag; conditional If-Match, never wildcard; conflict stops; expiry never prevents cleanup.",
  };
}

/** Rejects *any* candidate drift, including bytes outside the finite spans. */
export function assertExactProposal(input, candidates) {
  exactKeys(candidates, ["global", "diagnostic"]);
  const expected = renderProposal(input);
  for (const name of ["global", "diagnostic"]) {
    require(Buffer.isBuffer(candidates[name]) && candidates[name].equals(expected[name]), "unallowlisted " + name + " delta");
  }
  return true;
}

/** Pure cleanup precondition assessment, NOT a transport or authorization gate.
 * Both values model post-install/fresh-read evidence, not a stale preinstall ETag.
 * No expiry check: expired proposals must still be removable. An actual future
 * executor must enforce the same If-Match at ARM, preserve exact rawxml bytes,
 * verify both formats and restore the whole protected baseline independently.
 */
export function assessGlobalCleanup(input, evidence) {
  exactKeys(evidence, ["observedGlobal", "installedEtag", "observedEtag"]);
  const proposal = renderProposal(input);
  require(Buffer.isBuffer(evidence.observedGlobal) && evidence.observedGlobal.equals(proposal.global), "cleanup candidate drift: stop, never clobber");
  const valid = value => typeof value === "string" && /^(?:W\/)?"[\x21\x23-\x7e]+"$/.test(value) && value.length <= 1024;
  require(valid(evidence.installedEtag) && valid(evidence.observedEtag)
    && evidence.installedEtag === evidence.observedEtag, "fresh exact candidate ETag required; never wildcard");
  return Object.freeze({ status: "MOCK_CLEANUP_PRECONDITIONS_ONLY_NOT_AUTHORIZATION",
    originalExportSha256: ORIGINAL_GLOBAL_SHA256, candidateExportSha256: proposal.candidateHashes.global,
    requiredIfMatch: evidence.observedEtag, restoreExport: Buffer.from(input.globalOriginal),
    retryBudget: 0, conflictAction: "STOP_RECONCILE_NO_OVERWRITE", expiryBlocksCleanup: false });
}

/** OFFLINE semantic model, not an APIM interpreter, auth proof or scoring proof.
 * Existing active-subscription/product association checks stay external mandatory
 * preflight gates; APIM policy context does not expose a subscription State field.
 */
export function mockAdmission(context, window, nowUtc) {
  const { start, end } = interval(window), now = utc(nowUtc);
  return context?.api != null && SCOPE.apiIds.includes(context.api.id) && context.api.revision === "2"
    && context.subscription?.id === SCOPE.subscription && context.product?.id === SCOPE.product
    && context.request?.method === "POST" && context.request?.ip === SCOPE.ip
    && SCOPE.paths.includes(context.request?.originalPath) && start <= now && now < end;
}