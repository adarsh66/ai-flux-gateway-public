async function successor11Browser(page, request) {
  // Standalone native Playwright, NOT page JS: response.headerValue is permitted
  // regardless of Access-Control-Expose-Headers. Never change production CORS.
  const ORIGIN = 'https://poc-ids-token-ex-customer.azurewebsites.net';
  const NORMAL = 'https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions';
  const OWNED = NORMAL.replace('/v1/', '/v1;rev=2/');
  const TEXT = 'Please greet me in one short sentence.';
  const pattern = /\/chat\/completions(?:\?.*)?$/;
  const check = (v, why) => { if (!v) throw new Error(why); };
  const object = v => v && typeof v === 'object' && !Array.isArray(v);
  const exact = (v, keys) => object(v) && Object.keys(v).sort().join(',') === keys.sort().join(',');
  const integration = request.scope === 'READ_ONLY_INTEGRATION_NOT_PACKAGE_PREFLIGHT';
  check(request.schema === 11 && ['observe', 'inspect', 'score', 'close'].includes(request.phase)
    && /^[a-f0-9]{64}$/.test(request.challenge) && /^[a-f0-9]{64}$/.test(request.manifest_sha256)
    && /^[a-f0-9]{32}$/.test(request.nonce)
    && (request.scope === 'ONE_SCORE_ZERO_COMPLETION_NO_RETRY' || (integration && request.phase !== 'score'))
    && page.url() === ORIGIN + '/playground' && Date.now() >= Date.parse(request.issued_at)
    && Date.now() < Date.parse(request.expires_at), 'REQUEST_BINDING');
  if (!integration && request.phase !== 'close') {
    check(/^[a-f0-9]{64}$/.test(request.checkpoint_sha256)
      && Date.now() >= Date.parse(request.full_started_at)
      && Date.now() - Date.parse(request.full_started_at) <= 90000, 'FULL_CHECKPOINT_MAX90');
  }
  const send = page.getByRole('button', { name: 'Send', exact: true });
  const message = page.getByRole('textbox', { name: 'Message', exact: true });
  const system = page.getByRole('textbox', { name: 'System prompt (optional)', exact: true });
  const model = page.getByRole('combobox', { name: 'Model', exact: true });
  const log = page.getByRole('log');
  const dom = async () => ({ model: await model.inputValue(), system_empty: await system.inputValue() === '',
    turns: await log.locator('.turn').count(), draft_matches: await message.inputValue() === TEXT,
    send_disabled: !(await send.isEnabled()) });
  if (request.phase === 'close') {
    await page.route(pattern, route => route.abort('blockedbyclient'));
    await send.evaluate(button => { button.disabled = true; });
    return { binding: request, closed: true };
  }
  if (request.phase === 'observe') {
    await page.route(pattern, route => route.abort('blockedbyclient'));
    await send.evaluate(button => { button.disabled = true; });
    check(await system.inputValue() === '' && await log.locator('.turn').count() === 0
      && (await log.innerText()).includes('Start a conversation')
      && await message.inputValue() === '', 'EMPTY_SYSTEM_HISTORY_DRAFT');
    await model.selectOption('gpt-5.4-mini', { timeout: 5000 });
    await message.fill(TEXT, { timeout: 5000 });
    await message.press('End', { timeout: 5000 });
    await send.evaluate(button => { button.disabled = true; });
  }
  const before = await dom();
  check(before.model === 'gpt-5.4-mini' && before.system_empty && before.turns === 0
    && before.draft_matches && before.send_disabled, 'INDEPENDENT_DOM_DRIFT');
  if (request.phase !== 'score') return { binding: request, dom: before, auth_inspected: false,
    integration_only: integration, manifest_accepted_preflight: false };
  const fresh = () => Date.now() < Date.parse(request.expires_at)
    && Date.now() >= Date.parse(request.inspection_issued_at)
    && Date.now() - Date.parse(request.inspection_issued_at) < 30000
    && Date.now() - Date.parse(request.full_started_at) <= 90000
    && Date.now() <= Date.parse(request.window_end) - 22 * 60000;
  check(request.activation_manifest_sha256 === request.manifest_sha256
    && /^[a-f0-9]{64}$/.test(request.reservation_sha256) && fresh(), 'AUDITED_ACTIVATION_RESERVE');
  let closed = false, consumed = false, forwarded = false, posts = 0, aborted = 0;
  let requestStarted = null;
  const valid = body => exact(body, ['model', 'stream', 'messages', 'max_completion_tokens'])
    && body.model === 'gpt-5.4-mini' && body.stream === false
    && Number.isInteger(body.max_completion_tokens) && body.max_completion_tokens > 0
    && body.max_completion_tokens <= 1024 && Array.isArray(body.messages) && body.messages.length === 1
    && exact(body.messages[0], ['role', 'content']) && body.messages[0].role === 'user'
    && body.messages[0].content === TEXT;
  await page.route(pattern, async route => {
    const r = route.request();
    if (r.method() === 'OPTIONS' && !closed && [NORMAL, OWNED].includes(r.url())) return route.continue();
    if (r.method() === 'POST') posts++;
    if (closed || consumed || r.method() !== 'POST') { aborted++; return route.abort('blockedbyclient'); }
    consumed = true;
    let body;
    try { body = r.postDataJSON(); } catch { aborted++; return route.abort('blockedbyclient'); }
    if (r.url() !== NORMAL || !valid(body) || !fresh()) { aborted++; return route.abort('blockedbyclient'); }
    requestStarted = new Date().toISOString();
    forwarded = true;
    return route.continue({ url: OWNED });
  });
  let response = null, received = null;
  try {
    const pending = page.waitForResponse(r => forwarded && [NORMAL, OWNED].includes(r.url())
      && r.request().method() === 'POST', { timeout: 20000 }).then(v => v, () => null);
    check(fresh(), 'FRESH_BEFORE_SEND');
    await send.evaluate(button => { button.disabled = false; });
    await message.press('Control+Enter', { timeout: 5000 });
    response = await pending;
    received = new Date().toISOString();
  } finally {
    closed = true;
    await send.evaluate(button => { button.disabled = true; });
  }
  check(response && posts === 1 && forwarded, 'ONE_POST_RESPONSE_REQUIRED_NO_RETRY');
  const correlation = await response.headerValue('apim-request-id');
  check(/^[A-Za-z0-9-]{1,128}$/.test(correlation || ''), 'SERVER_CORRELATION_REQUIRED');
  const raw = await response.text();
  check(raw.length <= 8192, 'BOUNDED_DIAGNOSTIC');
  const value = JSON.parse(raw);
  // EXACT retained owned XML auto-diagnostic-summary contract. Usage is three
  // nullable int32 counters; key_types is a bounded partial JToken type map.
  const typeNames = ['answers', 'usage', 'model', 'id', 'error'];
  const tokenTypes = ['Object', 'Array', 'Integer', 'Float', 'String', 'Boolean', 'Null', 'Date', 'Bytes', 'Undefined', 'Raw', 'Guid', 'Uri', 'TimeSpan', 'Constructor', 'Property', 'Comment', 'None'];
  check(exact(value, ['scoring_status', 'schema_valid', 'body_within_bound', 'key_types', 'probabilities', 'usage'])
    && response.status() === 200 && value.scoring_status === 200 && value.schema_valid === true
    && value.body_within_bound === true && object(value.key_types)
    && Object.entries(value.key_types).every(([k, v]) => typeNames.includes(k) && tokenTypes.includes(v))
    && value.key_types.answers === 'Object'
    && exact(value.usage, ['input_tokens', 'output_tokens', 'total_tokens'])
    && Object.values(value.usage).every(n => n === null || (Number.isInteger(n) && n >= 0 && n <= 2147483647))
    && exact(value.probabilities, ['greeting', 'arithmetic'])
    && Object.values(value.probabilities).every(n => Number.isFinite(n) && n >= 0 && n <= 1)
    && Math.abs(value.probabilities.greeting + value.probabilities.arithmetic - 1) <= .02,
  'ACTUAL_SERVER_DIAGNOSTIC_REQUIRED');
  return { binding: request, server_correlation: correlation, http_status: response.status(),
    probabilities: value.probabilities, diagnostic_schema_valid: true, forwarded,
    observed_posts: posts, aborted_posts: aborted, guard_retained_closed: closed,
    auth_inspected: false, raw_body_logged: false,
    request_started_at: requestStarted, response_received_at: received };
}