// Import-free SOURCE is the browser-tool implementation. All disk ownership is
// REAL PARENT responsibility, checked locally before this function is inlined.
export async function diagnostic05bAttempt(page, binding) {
  const TEXT = "Please greet me in one short sentence.";
  const NORMAL = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions";
  const REVISION = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1;rev=2/chat/completions";
  const hex = value => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
  const exact = (value, names) => value !== null && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).sort().join(",") === [...names].sort().join(",");
  const guard = value => { if (!value) throw new Error("BINDING_REJECTED_NO_RETRY"); };
  let closed = false, consumed = false, installed = false, keyboard = 0;
  let forwarding = false, forwarded = false, posts = 0, aborted = 0, http = null;
  let diagnostic = null, outcome = "FAILED_OR_TIMEOUT_NO_RETRY", timer;
  let done, forwardRequest;
  const responseSeen = new Promise(resolve => { done = resolve; });
  const result = () => ({ status: outcome, manifest_sha256: hex(binding?.manifest_sha256) ? binding.manifest_sha256 : null,
    parent_intent_sha256: hex(binding?.parent_intent_sha256) ? binding.parent_intent_sha256 : null,
    shared_owner_sha256: hex(binding?.shared_owner_sha256) ? binding.shared_owner_sha256 : null,
    new_scope_consumed: true, retry_authorized: false, keyboard_invocations: keyboard,
    observed_posts: posts, aborted_posts: aborted, consumed, forwarding_attempted: forwarding,
    forwarded, http_status: http, diagnostic, guard_retained_closed: installed && closed,
    scorer_schema_proven: http === 200 && diagnostic?.scoring_status === 200
      && diagnostic?.schema_valid === true && diagnostic?.body_within_bound === true,
    scoring_request_count: null, completion_request_count: null,
    raw_body_logged: false, auth_inspected: false });
  const validBody = body => exact(body, ["max_completion_tokens", "messages", "model", "stream"])
    && body.model === "gpt-5.4-mini" && body.stream === false
    && Number.isInteger(body.max_completion_tokens) && body.max_completion_tokens > 0 && body.max_completion_tokens <= 1024
    && Array.isArray(body.messages) && body.messages.length === 1
    && exact(body.messages[0], ["role", "content"])
    && body.messages[0].role === "user" && body.messages[0].content === TEXT;
  const sanitize = raw => {
    guard(typeof raw === "string" && raw.length <= 8192);
    const value = JSON.parse(raw);
    guard(exact(value, ["scoring_status", "schema_valid", "body_within_bound", "key_types", "probabilities", "usage"]));
    guard(value.scoring_status === null || (Number.isInteger(value.scoring_status) && value.scoring_status >= 100 && value.scoring_status <= 599));
    guard(typeof value.schema_valid === "boolean" && typeof value.body_within_bound === "boolean");
    guard(value.key_types !== null && typeof value.key_types === "object" && !Array.isArray(value.key_types));
    const keyTypes = {};
    for (const [key, type] of Object.entries(value.key_types)) {
      guard(["answers", "usage", "model", "id", "error"].includes(key)
        && ["Object", "Array", "Integer", "Float", "String", "Boolean", "Null", "Undefined", "Date", "Bytes", "Guid", "Uri", "TimeSpan", "Raw", "Constructor", "Property", "Comment", "None"].includes(type));
      keyTypes[key] = type;
    }
    let probabilities = null;
    if (value.probabilities !== null) {
      guard(exact(value.probabilities, ["greeting", "arithmetic"]));
      const { greeting, arithmetic } = value.probabilities;
      guard([greeting, arithmetic].every(n => typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 1)
        && Math.abs(greeting + arithmetic - 1) <= 0.02);
      probabilities = { greeting, arithmetic };
    }
    guard(exact(value.usage, ["input_tokens", "output_tokens", "total_tokens"]));
    const usage = {};
    for (const key of ["input_tokens", "output_tokens", "total_tokens"]) {
      const n = value.usage[key];
      guard(n === null || (Number.isInteger(n) && n >= 0 && n <= 2147483647));
      usage[key] = n;
    }
    guard(!value.schema_valid || (value.scoring_status === 200 && value.body_within_bound && probabilities !== null));
    return { scoring_status: value.scoring_status, schema_valid: value.schema_valid,
      body_within_bound: value.body_within_bound, key_types: keyTypes, probabilities, usage };
  };
  const match = url => url.origin === "https://poc-ids-token-ex-apim.azure-api.net"
    && /\/chat\/completions$/.test(url.pathname);
  const handler = async route => {
    try {
      const request = route.request();
      if (request.method() === "OPTIONS" && !closed) return await route.continue();
      if (request.method() !== "POST") return await route.abort("blockedbyclient");
      posts++;
      if (closed || consumed) { aborted++; return await route.abort("blockedbyclient"); }
      consumed = true; // Permanently consumed BEFORE parse/validation/continue.
      let body;
      try { body = request.postDataJSON(); } catch { aborted++; return await route.abort("blockedbyclient"); }
      if (request.url() !== NORMAL || Date.now() >= Date.parse(binding.end) - 90000 || !validBody(body)) {
        aborted++; return await route.abort("blockedbyclient");
      }
      forwardRequest = request;
      forwarding = true;
      await route.continue({ url: REVISION }); forwarded = true;
    } catch { closed = true; done(false); } // No exception text crosses boundary.
  };
  let responseClaimed = false;
  const response = async value => {
    try {
      if (closed || responseClaimed || !forwarding || ![NORMAL, REVISION].includes(value.url())
          || value.request() !== forwardRequest || value.request().method() !== "POST") return;
      responseClaimed = true;
      http = value.status();
      // This is the policy's bounded SANITIZED summary, never raw scorer data.
      // No response headers, request auth, storage, fetch, or extra network call.
      const summary = sanitize(await value.text());
      if (closed) return; // A late body may not mutate the already returned result.
      diagnostic = summary;
      outcome = http === 200 && summary.scoring_status === 200 && summary.schema_valid && summary.body_within_bound
        ? "SCORER_SCHEMA_PROVEN" : "DIAGNOSTIC_SUMMARY_NOT_SCHEMA_ACCEPTANCE";
      done(true);
    } catch { if (!closed) { outcome = "SUMMARY_INVALID_OR_UNAVAILABLE_NO_RETRY"; done(false); } }
  };
  try {
    const r = binding?.reservation;
    guard(binding?.parent_disk_verified === true && binding.scope === "DIAGNOSTIC05_05B_ONE_USER_ATTEMPT"
      && [binding.manifest_sha256, binding.parent_intent_sha256, binding.shared_owner_sha256,
        binding.reservation_sha256, binding.browser_source_sha256].every(hex)
      && r?.manifest_sha256 === binding.manifest_sha256 && r.end === binding.end
      && r.IP === "167.103.66.248" && r.attempt_budget === 1 && r.scoring_budget === 1
      && r.completion_budget === 0 && r.retry_budget === 0 && r.fixed_text === TEXT
      && r.model === "gpt-5.4-mini" && r.path === "/dev/llm/v1;rev=2/chat/completions"
      && r.browser_source_sha256 === binding.browser_source_sha256
      && Number.isFinite(Date.parse(binding.end)) && Date.now() < Date.parse(binding.end) - 90000
      && Number.isFinite(Date.parse(binding.verified_at_utc))
      && Date.now() >= Date.parse(binding.verified_at_utc) && Date.now() - Date.parse(binding.verified_at_utc) < 30000);
    await page.route(match, handler); installed = true;
    page.on("response", response);
    const message = page.getByRole("textbox", { name: "Message", exact: true });
    guard(await message.isEnabled({ timeout: 5000 }));
    guard(await page.getByRole("button", { name: "Send", exact: true }).isEnabled({ timeout: 5000 }));
    await message.fill(TEXT, { timeout: 5000 });
    guard(await message.inputValue({ timeout: 5000 }) === TEXT);
    guard(Date.now() < Date.parse(binding.end) - 90000);
    keyboard++;
    await message.press("Control+Enter", { timeout: 5000 });
    await Promise.race([responseSeen, new Promise(resolve => { timer = setTimeout(() => resolve(false), 20000); })]);
  } catch { /* Return sanitized failure EVEN for binding/locator/press errors. */ }
  finally {
    closed = true;
    clearTimeout(timer);
    try { page.off("response", response); } catch { /* Closed handler retained. */ }
  }
  // Handler closure is retained by page.route, NOT a returned nonserializable
  // handle. Never unroute until parent separately verifies actual offline state.
  return result();
}

export const SOURCE = diagnostic05bAttempt.toString();