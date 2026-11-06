// Parent-owned normal UI action; URL-only request continuation. No key/header,
// storage, DOM credential inspection, timers, Node globals or direct fetch.
export async function successorAttempt(page, binding, normalUiAction) {
  const normal = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions";
  const revision = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1;rev=2/chat/completions";
  const text = "Please greet me in one short sentence.";
  const require = x => { if (!x) throw new Error("CLOSED_NO_RETRY"); };
  const exact = (x, keys) => x !== null && typeof x === "object" && !Array.isArray(x)
    && Object.keys(x).sort().join() === [...keys].sort().join();
  const hex = x => typeof x === "string" && /^[a-f0-9]{64}$/.test(x);
  let closed = false, consumed = false, installed = false, attempted = false;
  let posts = 0, aborted = 0, actions = 0, status = null, summary = null;
  const handler = async route => {
    const request = route.request();
    if (request.method() === "OPTIONS" && !closed) return route.continue();
    if (request.method() !== "POST") return route.abort("blockedbyclient");
    posts++;
    if (closed || consumed) { aborted++; return route.abort("blockedbyclient"); }
    consumed = true;
    try {
      const body = request.postDataJSON();
      require(request.url() === normal && Date.now() < Date.parse(binding.end) - 300000
        && exact(body, ["model", "messages", "stream", "max_completion_tokens"])
        && body.model === "gpt-5.4-mini" && body.stream === false
        && Number.isInteger(body.max_completion_tokens) && body.max_completion_tokens > 0 && body.max_completion_tokens <= 1024
        && Array.isArray(body.messages) && body.messages.length === 1
        && exact(body.messages[0], ["role", "content"])
        && body.messages[0].role === "user" && body.messages[0].content === text);
      attempted = true;
      return await route.continue({ url: revision });
    } catch { aborted++; return route.abort("blockedbyclient"); }
  };
  try {
    require(binding?.scope === "AUTO_PATH_SUCCESSOR_ONE_ATTEMPT"
      && binding.parent_disk_verified === true && binding.supervisor_live === true
      && binding.exact_online_readback === true && typeof normalUiAction === "function"
      && [binding.manifest_sha256, binding.reservation_sha256, binding.browser_source_sha256].every(hex)
      && binding.scoring_budget === 1 && binding.completion_budget === 0 && binding.retry_budget === 0
      && binding.IP === "167.103.66.248" && binding.subscription === "e9f2abb0-930b-598a-b210-0ab0b279127f"
      && Date.now() < Date.parse(binding.end) - 300000
      && Date.now() >= Date.parse(binding.verified_at_utc)
      && Date.now() - Date.parse(binding.verified_at_utc) < 30000);
    await page.route(/^https:\/\/poc-ids-token-ex-apim\.azure-api\.net\/.*chat\/completions(?:\?.*)?$/, handler);
    installed = true;
    const pending = page.waitForResponse(r => attempted && consumed && !closed
      && [normal, revision].includes(r.url()) && r.request().method() === "POST", { timeout: 20000 })
      .then(value => value, () => null);
    actions++;
    await normalUiAction(); // Actual parent normal UI action, NEVER direct POST.
    const response = await pending;
    if (response) {
      status = response.status();
      const raw = await response.text();
      require(raw.length <= 8192);
      const value = JSON.parse(raw);
      require(exact(value, ["scoring_status", "schema_valid", "body_within_bound", "key_types", "probabilities", "usage"])
        && (value.scoring_status === null || (Number.isInteger(value.scoring_status) && value.scoring_status >= 100 && value.scoring_status <= 599))
        && typeof value.schema_valid === "boolean" && typeof value.body_within_bound === "boolean"
        && exact(value.usage, ["input_tokens", "output_tokens", "total_tokens"]));
      require(value.key_types !== null && typeof value.key_types === "object" && !Array.isArray(value.key_types));
      for (const [key, type] of Object.entries(value.key_types)) require(["answers", "usage", "model", "id", "error"].includes(key)
        && ["Object", "Array", "Integer", "Float", "String", "Boolean", "Null", "Undefined", "Date", "Bytes", "Guid", "Uri", "TimeSpan", "Raw", "Constructor", "Property", "Comment", "None"].includes(type));
      for (const n of Object.values(value.usage)) require(n === null || (Number.isInteger(n) && n >= 0 && n <= 2147483647));
      require(value.probabilities === null || (exact(value.probabilities, ["greeting", "arithmetic"])
        && Object.values(value.probabilities).every(n => Number.isFinite(n) && n >= 0 && n <= 1)
        && Math.abs(value.probabilities.greeting + value.probabilities.arithmetic - 1) <= 0.02));
      require(!value.schema_valid || (value.scoring_status === 200 && value.body_within_bound && value.probabilities !== null));
      summary = value;
    }
  } catch { /* No raw errors/bodies/credentials in evidence. UNKNOWN consumes. */ }
  finally { closed = true; } // Retain abort-only route until verified cleanup.
  return { scope: "AUTO_PATH_SUCCESSOR_ONE_ATTEMPT", actions, observed_posts: posts,
    aborted_posts: aborted, consumed, forwarding_attempted: attempted,
    http_status: status, summary, guard_retained_closed: installed && closed,
    scorer_schema_proven: status === 200 && summary?.scoring_status === 200
      && summary?.schema_valid === true && summary?.body_within_bound === true,
    scoring_request_count: null, completion_request_count: null, retry_authorized: false,
    auth_inspected: false, raw_body_logged: false };
}