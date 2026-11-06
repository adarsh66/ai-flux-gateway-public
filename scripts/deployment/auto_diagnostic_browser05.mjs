// Parent-owned normal keyboard submit ONLY. No click/force/focus bypass, HTTP
// client, authentication inspection, response bodies, or retry implementation.
import { createHash } from "node:crypto";
import { existsSync, readFileSync, openSync, writeSync, fsyncSync, closeSync } from "node:fs";
import { dirname, resolve, relative, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";
import { TEXT, NORMAL, REVISION, validBody } from "./auto_diagnostic_browser.mjs";

export { TEXT, NORMAL, REVISION };
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const PACKAGE = resolve(ROOT, ".deployment/auto-offline-revision-20261029T060302997824Z/scoring-diagnostic05");
const STAGES = ["policy-put", "online", "reserve-browser", "offline"];
const IP = "167.103.66.248";
const hash = data => createHash("sha256").update(data).digest("hex");
const read = name => JSON.parse(readFileSync(resolve(PACKAGE, name), "utf8"));
const digest = name => hash(readFileSync(resolve(PACKAGE, name)));
function requireGuard(value) { if (!value) throw new Error("diagnostic05 binding rejected; no retry"); }

function exclusive(name, value) {
  const fd = openSync(resolve(PACKAGE, name), "wx", 0o600);
  try { writeSync(fd, JSON.stringify(value)); fsyncSync(fd); } finally { closeSync(fd); }
}

export function boundReservation(intent, sha, end) {
  requireGuard(/^[a-f0-9]{64}$/.test(sha) && Number.isFinite(Date.parse(end))
    && intent?.manifest_sha256 === sha && intent.end === end && intent.IP === IP
    && intent.attempt_budget === 1 && intent.scoring_budget === 1 && intent.completion_budget === 0
    && intent.retry_budget === 0 && intent.fixed_text === TEXT && intent.model === "gpt-5.4-mini"
    && intent.path === "/dev/llm/v1;rev=2/chat/completions");
}

function actualBinding() {
  const manifest = read("manifest.json"), sha = digest("manifest.json"), reservation = read("reserve-browser-intent.json");
  const review = read("parent-review.json"), activation = read("activate-result.json");
  boundReservation(reservation, sha, manifest.end);
  requireGuard(review.approved === true && review.independent_native_review === true
    && review.manifest_sha256 === sha && JSON.stringify(review.stages) === JSON.stringify(STAGES)
    && reservation.review_sha256 === digest("parent-review.json")
    && activation.status === "ONLINE_READY" && activation.manifest_sha256 === sha
    && activation.reservation_sha256 === digest("reserve-browser-intent.json")
    && manifest.IP === IP && manifest.scoring_budget === 1 && manifest.completion_budget === 0
    && manifest.retry_budget === 0 && manifest.historical_scoring_request_count === null
    && manifest.budget_scope === "NEW_USER_AUTHORIZED_DIAGNOSTIC05_SINGLE_ATTEMPT"
    && manifest.sources[relative(ROOT, fileURLToPath(import.meta.url)).replaceAll("\\", "/")] === hash(readFileSync(fileURLToPath(import.meta.url)))
    && !existsSync(resolve(PACKAGE, "offline-intent.json")));
  const transcript = resolve(PACKAGE, review.transcript), rel = relative(PACKAGE, transcript);
  requireGuard(!rel.startsWith("..") && !isAbsolute(rel) && hash(readFileSync(transcript)) === review.transcript_sha256
    && Date.parse(manifest.at_utc) <= Date.parse(review.at_utc) && Date.parse(review.at_utc) <= Date.now()
    && Date.now() - Date.parse(review.at_utc) < 30 * 60000
    && Date.parse(manifest.start) <= Date.now() && Date.now() < Date.parse(manifest.end) - 90000);
  return { reservation, sha, end: manifest.end };
}

// Testable browser orchestration. Production entrypoint below always supplies
// actual on-disk binding + synchronous exclusive fsync journal, never a fixture.
export async function keyboardAttempt(page, binding, journal) {
  boundReservation(binding.reservation, binding.sha, binding.end);
  requireGuard(Date.now() < Date.parse(binding.end) - 90000);
  // Durable ownership BEFORE route installation, fill, or press. A crash or
  // timeout permanently consumes this new scope even if no POST was observed.
  journal.intent({ at_utc: new Date().toISOString(), manifest_sha256: binding.sha,
    attempt_budget: 1, retry_budget: 0, completion_budget: 0, input: "FIXED_REVIEWED_TEXT",
    method: "Message.press(Control+Enter)", new_scope_consumed: true });
  let consumed = false, forwarded = false, forwardAttempted = false, closed = false;
  let installed = false, keyboardInvocations = 0, observedPosts = 0, abortedPosts = 0, httpStatus = null;
  let finished = false, resolveResponse;
  const responseSeen = new Promise(resolve => { resolveResponse = resolve; });
  const match = url => url.origin === "https://poc-ids-token-ex-apim.azure-api.net"
    && /\/chat\/completions$/.test(url.pathname);
  const handler = async route => {
    const request = route.request();
    if (request.method() === "OPTIONS" && !closed) return route.continue();
    if (request.method() !== "POST") return route.abort("blockedbyclient");
    observedPosts++;
    if (closed || consumed) { abortedPosts++; return route.abort("blockedbyclient"); }
    consumed = true; // BEFORE parsing/validation/continue, including exceptions.
    let body;
    try { body = request.postDataJSON(); } catch { abortedPosts++; return route.abort("blockedbyclient"); }
    if (request.url() !== NORMAL || Date.now() >= Date.parse(binding.end) - 90000 || !validBody(body)) {
      abortedPosts++; return route.abort("blockedbyclient");
    }
    forwardAttempted = true; // Continue failure is ambiguous, NOT proof of zero.
    try { await route.continue({ url: REVISION }); forwarded = true; }
    catch { closed = true; resolveResponse(false); }
  };
  const response = value => {
    if (!closed && (value.url() === NORMAL || value.url() === REVISION) && value.request().method() === "POST") {
      httpStatus = value.status(); resolveResponse(true); // No headers/body.
    }
  };
  let timer;
  try {
    await page.route(match, handler); installed = true;
    page.on("response", response);
    const message = page.getByRole("textbox", { name: "Message", exact: true });
    requireGuard(await message.isEnabled({ timeout: 5000 }));
    requireGuard(await page.getByRole("button", { name: "Send", exact: true }).isEnabled({ timeout: 5000 }));
    await message.fill(TEXT, { timeout: 5000 });
    requireGuard(await message.inputValue({ timeout: 5000 }) === TEXT);
    // Existing UI handler is e.ctrlKey/metaKey + Enter. Locator.press does not
    // wait for Send-button animation/stability or demand bringing tab to front.
    keyboardInvocations++;
    await message.press("Control+Enter", { timeout: 5000 });
    finished = await Promise.race([responseSeen, new Promise(resolve => { timer = setTimeout(() => resolve(false), 15000); })]);
  } catch {
    // Never echo exception.message, raw requests, tokens, body or response text.
  } finally {
    closed = true;
    clearTimeout(timer);
    try { page.off("response", response); }
    finally {
      // Keep the installed handler CLOSED until verified offline cleanup.
      // Removing it on timeout could let a delayed/repeated POST escape.
      journal.result({ at_utc: new Date().toISOString(), manifest_sha256: binding.sha,
        new_scope_consumed: true, consumed, forwarded, forwarding_attempted: forwardAttempted,
        wire_outcome: forwardAttempted ? "UNKNOWN_SCORER_COUNT_NOT_TELEMETRY" : "NO_FORWARD_ATTEMPT_OBSERVED_BY_HELPER",
        keyboard_invocations: keyboardInvocations, observed_posts: observedPosts, aborted_posts: abortedPosts,
        http_status: httpStatus, response_received: httpStatus !== null,
        status: finished ? "HTTP_METADATA_ONLY_NOT_SCORER_SCHEMA_PROOF" : "FAILED_OR_TIMEOUT_NO_RETRY",
        guard_retained_closed: installed, retry_authorized: false, raw_body_logged: false, auth_inspected: false });
    }
  }
  return { consumed: () => consumed, forwarded: () => forwarded,
    // Parent may remove blocker ONLY after actual bound offline verification.
    disposeAfterOffline: async () => {
      const verified = read("offline-verification.json"), intent = read("offline-intent.json");
      requireGuard(verified.manifest_sha256 === binding.sha && intent.manifest_sha256 === binding.sha
        && verified.intent_sha256 === digest("offline-intent.json") && verified.revision2_online === false
        && verified.revision2_current === false && verified.all13_supplemental_exact === true
        && verified.exact_both_formats === true);
      await page.unroute(match, handler);
    } };
}

// Parent calls this ONCE only AFTER actual native review + ONLINE_READY.
// No top-level browser execution; importing this file cannot Send.
export async function submitOnce(page) {
  return keyboardAttempt(page, actualBinding(), {
    intent: value => exclusive("browser-send-intent.json", value),
    result: value => exclusive("browser-send-result.json", value),
  });
}