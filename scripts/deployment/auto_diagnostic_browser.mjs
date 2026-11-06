// Parent imports this reviewed helper AFTER durable reserve-browser intent.
// Installs interception only; never clicks Send, reads headers/keys/storage, or
// issues a request. Parent uses normal Playground controls exactly once.
export const TEXT = "Please greet me in one short sentence.";
export const NORMAL = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions";
export const REVISION = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1;rev=2/chat/completions";

export function validBody(body) {
  return !!body && Object.keys(body).sort().join(",") === "max_completion_tokens,messages,model,stream"
    && body.model === "gpt-5.4-mini" && body.stream === false
    && Number.isInteger(body.max_completion_tokens) && body.max_completion_tokens > 0 && body.max_completion_tokens <= 1024
    && Array.isArray(body.messages) && body.messages.length === 1
    && !!body.messages[0] && typeof body.messages[0] === "object"
    && Object.keys(body.messages[0]).sort().join(",") === "content,role"
    && body.messages[0].role === "user" && body.messages[0].content === TEXT;
}

export async function install(page, intent, manifestSha256, end) {
  if (!Number.isFinite(Date.parse(end)) || !intent || intent.manifest_sha256 !== manifestSha256 || intent.end !== end
      || intent.attempt_budget !== 1 || intent.scoring_budget !== 1 || intent.completion_budget !== 0
      || intent.retry_budget !== 0 || intent.fixed_text !== TEXT || intent.model !== "gpt-5.4-mini"
      || intent.path !== "/dev/llm/v1;rev=2/chat/completions") throw new Error("bound durable browser intent required");
  let consumed = false;
  const handler = async route => {
    const request = route.request();
    if (request.method() === "OPTIONS") return route.continue();
    // Consume on FIRST POST, even malformed/expired/failed: NO retry.
    if (request.method() !== "POST" || consumed) return route.abort("blockedbyclient");
    consumed = true;
    let body;
    try { body = request.postDataJSON(); } catch { return route.abort("blockedbyclient"); }
    if (request.url() !== NORMAL || Date.now() >= Date.parse(end) - 30000 || !validBody(body))
      return route.abort("blockedbyclient");
    // URL ONLY. Existing authentication/body/method untouched. No route.fetch
    // (which would add a separate request/retry implementation).
    return route.continue({ url: REVISION });
  };
  const match = url => url.origin === "https://poc-ids-token-ex-apim.azure-api.net"
    && /\/chat\/completions$/.test(url.pathname);
  await page.route(match, handler);
  return { consumed: () => consumed, dispose: () => page.unroute(match, handler) };
}