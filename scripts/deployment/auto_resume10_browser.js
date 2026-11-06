async function successor10Browser(page, request) {
  // Standalone native-tool body: no imports, Node globals, timers, or free closures.
  const ORIGIN = 'https://poc-ids-token-ex-customer.azurewebsites.net';
  const NORMAL = 'https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions';
  const OWNED = 'https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1;rev=2/chat/completions';
  const TEXT = 'Please greet me in one short sentence.';
  const pattern = /\/chat\/completions(?:\?.*)?$/;
  const check = (v, why) => { if (!v) throw new Error(why); };
  const exact = (v, keys) => v && typeof v === 'object' && !Array.isArray(v)
    && Object.keys(v).sort().join(',') === keys.sort().join(',');
  check(request.schema === 10 && ['observe', 'inspect', 'score', 'close'].includes(request.phase)
    && /^[a-f0-9]{64}$/.test(request.challenge) && /^[a-f0-9]{64}$/.test(request.manifest_sha256)
    && /^[a-f0-9]{32}$/.test(request.nonce) && request.scope === 'ONE_SCORE_ZERO_COMPLETION_NO_RETRY'
    && page.url() === ORIGIN + '/playground' && Date.now() >= Date.parse(request.issued_at)
    && Date.now() < Date.parse(request.expires_at), 'REQUEST_BINDING');
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
    // Install fail-closed routing and disable Send BEFORE any draft event.
    await page.route(pattern, route => route.abort('blockedbyclient'));
    await send.evaluate(button => { button.disabled = true; });
    check(await system.inputValue() === '' && await log.locator('.turn').count() === 0
      && (await log.innerText()).includes('Start a conversation')
      && await message.inputValue() === '', 'EMPTY_SYSTEM_HISTORY_DRAFT');
    await model.selectOption('gpt-5.4-mini', { timeout: 5000 });
    await message.fill(TEXT, { timeout: 5000 });
    await message.press('End', { timeout: 5000 });
    // React may have rerendered after fill. The route has remained blocked.
    await send.evaluate(button => { button.disabled = true; });
  }
  const before = await dom();
  check(before.model === 'gpt-5.4-mini' && before.system_empty && before.turns === 0
    && before.draft_matches && before.send_disabled, 'INDEPENDENT_DOM_DRIFT');
  if (request.phase !== 'score') return { binding: request, dom: before, auth_inspected: false };
  check(request.activation_manifest_sha256 === request.manifest_sha256
    && /^[a-f0-9]{64}$/.test(request.reservation_sha256)
    && Date.now() <= Date.parse(request.window_end) - 22 * 60000, 'AUDITED_ACTIVATION_RESERVE');
  let closed = false, consumed = false, forwarded = false, posts = 0, aborted = 0;
  const valid = body => exact(body, ['model', 'stream', 'messages', 'max_completion_tokens'])
    && body.model === 'gpt-5.4-mini' && body.stream === false
    && Number.isInteger(body.max_completion_tokens) && body.max_completion_tokens > 0
    && body.max_completion_tokens <= 1024 && Array.isArray(body.messages) && body.messages.length === 1
    && exact(body.messages[0], ['role', 'content']) && body.messages[0].role === 'user'
    && body.messages[0].content === TEXT;
  // Newest matching Playwright route wins; never unroute the preflight blocker.
  await page.route(pattern, async route => {
    const r = route.request();
    if (r.method() === 'OPTIONS' && !closed && [NORMAL, OWNED].includes(r.url())) return route.continue();
    if (r.method() === 'POST') posts++;
    if (closed || consumed || r.method() !== 'POST') { aborted++; return route.abort('blockedbyclient'); }
    consumed = true; // First POST consumes allowance even when its body is wrong.
    let body;
    try { body = r.postDataJSON(); } catch { aborted++; return route.abort('blockedbyclient'); }
    if (r.url() !== NORMAL || !valid(body) || Date.now() > Date.parse(request.window_end) - 22 * 60000) {
      aborted++; return route.abort('blockedbyclient');
    }
    forwarded = true;
    return route.continue({ url: OWNED }); // URL only: never inspect/copy/log credentials.
  });
  let response = null;
  try {
    // Waiter registered BEFORE the only event. Rejection observed immediately.
    const pending = page.waitForResponse(r => forwarded && [NORMAL, OWNED].includes(r.url())
      && r.request().method() === 'POST', { timeout: 20000 }).then(v => v, () => null);
    await send.evaluate(button => { button.disabled = false; });
    await message.press('Control+Enter', { timeout: 5000 });
    response = await pending;
  } finally {
    closed = true; // Handler stays installed, aborting ALL later chat requests.
    await send.evaluate(button => { button.disabled = true; });
  }
  check(response && posts === 1 && forwarded, 'ONE_POST_RESPONSE_REQUIRED_NO_RETRY');
  const correlation = await response.headerValue('apim-request-id');
  check(/^[A-Za-z0-9-]{1,128}$/.test(correlation || ''), 'SERVER_CORRELATION_REQUIRED');
  const raw = await response.text();
  check(raw.length <= 8192, 'BOUNDED_DIAGNOSTIC');
  const value = JSON.parse(raw);
  check(exact(value, ['scoring_status', 'schema_valid', 'body_within_bound', 'key_types', 'probabilities', 'usage'])
    && response.status() === 200 && value.scoring_status === 200
    && value.schema_valid === true && value.body_within_bound === true
    && exact(value.probabilities, ['greeting', 'arithmetic'])
    && Object.values(value.probabilities).every(n => Number.isFinite(n) && n >= 0 && n <= 1)
    && Math.abs(value.probabilities.greeting + value.probabilities.arithmetic - 1) <= .02,
  'ACTUAL_SERVER_DIAGNOSTIC_REQUIRED');
  // Do not report invented server invocation counters. Parent corroborates trace.
  return { binding: request, server_correlation: correlation, http_status: response.status(),
    probabilities: value.probabilities, diagnostic_schema_valid: true, forwarded,
    observed_posts: posts, aborted_posts: aborted, guard_retained_closed: closed,
    auth_inspected: false, raw_body_logged: false };
}