import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../scripts/deployment/auto_resume11_browser.js', import.meta.url), 'utf8');
const evidence = JSON.parse(readFileSync(new URL('../.deployment/auto-resume11/diagnostic-contract.json', import.meta.url)));
const NORMAL = 'https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions';
const OWNED = NORMAL.replace('/v1/', '/v1;rev=2/');
const TEXT = 'Please greet me in one short sentence.';
function fixture() {
  const state = { draft: '', disabled: false, model: 'gpt-5.6-luna', turns: 0, events: [], routes: [], continued: [], aborted: 0,
    diagnostic: structuredClone(evidence.contract_success_fixture) };
  const body = { model: 'gpt-5.4-mini', stream: false, max_completion_tokens: 512, messages: [{ role: 'user', content: TEXT }] };
  const response = { url: () => OWNED, request: () => ({ method: () => 'POST' }), status: () => 200,
    headerValue: async name => { assert.equal(name, 'apim-request-id'); return 'SERVER-123'; },
    text: async () => JSON.stringify(state.diagnostic) };
  let resolveResponse, predicate;
  state.routePost = async (value = body, url = NORMAL) => {
    const r = { method: () => 'POST', url: () => url, postDataJSON: () => value,
      headers: () => { throw Error('NO_HEADERS'); } };
    await state.routes.at(-1)({ request: () => r, abort: async () => { state.aborted++; },
      continue: async options => { state.continued.push(options); if (predicate(response)) resolveResponse(response); } });
  };
  const message = { inputValue: async () => state.draft,
    fill: async text => { assert.ok(state.disabled && state.routes.length); state.events.push('fill'); state.draft = text; },
    press: async key => {
      state.events.push(key);
      if (key === 'Control+Enter') {
        assert.ok(predicate, 'waiter before event');
        await state.routePost(state.badBody ? { ...body, model: 'BAD' } : body);
        if (state.badBody) resolveResponse(null);
      }
    } };
  const button = { isEnabled: async () => !state.disabled,
    evaluate: async fn => { const b = { disabled: state.disabled }; fn(b); state.disabled = b.disabled;
      state.events.push(b.disabled ? 'disable' : 'enable'); } };
  const page = { url: () => 'https://poc-ids-token-ex-customer.azurewebsites.net/playground',
    route: async (_, handler) => { state.events.push('route'); state.routes.push(handler); },
    waitForResponse: fn => { predicate = fn; state.events.push('wait'); return new Promise(resolve => { resolveResponse = resolve; }); },
    getByRole: (role, options = {}) => {
      if (role === 'textbox' && options.name === 'Message') return message;
      if (role === 'textbox') return { inputValue: async () => '' };
      if (role === 'button') return button;
      if (role === 'combobox') return { inputValue: async () => state.model,
        selectOption: async model => { assert.ok(state.disabled); state.model = model; } };
      if (role === 'log') return { innerText: async () => 'Start a conversation', locator: () => ({ count: async () => state.turns }) };
      throw Error('Unsupported API');
    } };
  const request = phase => ({ schema: 11, phase, scope: 'ONE_SCORE_ZERO_COMPLETION_NO_RETRY',
    challenge: 'a'.repeat(64), manifest_sha256: 'b'.repeat(64), nonce: 'c'.repeat(32),
    checkpoint_sha256: 'e'.repeat(64), full_started_at: new Date(Date.now() - 1000).toISOString(),
    inspection_issued_at: new Date(Date.now() - 100).toISOString(),
    issued_at: new Date(Date.now() - 100).toISOString(), expires_at: new Date(Date.now() + 30000).toISOString(),
    activation_manifest_sha256: 'b'.repeat(64), reservation_sha256: 'd'.repeat(64),
    window_end: new Date(Date.now() + 30 * 60000).toISOString() });
  const invoke = async phase => vm.runInNewContext('(' + source + ')(page, request)', { page, request: request(phase) });
  return { state, page, request, invoke };
}

test('fixture is explicitly derived from exact retained XML, NOT claimed actual server output', () => {
  assert.equal(evidence.provenance, 'RETAINED_XML_CONTRACT_DERIVED_NOT_SERVER_RESPONSE');
  assert.match(evidence.summary_expression, /summary\["usage"\]\[name\] = \(long\)number/);
  assert.match(evidence.summary_expression, /2147483647/);
  assert.equal(evidence.trace_metadata.some(x => ['nonce', 'manifest_sha256'].includes(x.name)), false);
  assert.equal(evidence.single_terminal_score, true);
});

test('standalone exact helper blocks before draft; independent empty VM inspect', async () => {
  const f = fixture(); await f.invoke('observe');
  assert.deepEqual(f.state.events.slice(0, 4), ['route', 'disable', 'fill', 'End']);
  assert.equal((await f.invoke('inspect')).dom.send_disabled, true);
  assert.equal(f.state.continued.length, 0);
});

test('actual XML contract success fixture accepted by standaloneJS and later requests blocked', async () => {
  const f = fixture(); await f.invoke('observe'); await f.invoke('inspect');
  const result = await f.invoke('score');
  assert.equal(result.diagnostic_schema_valid, true);
  assert.equal(result.server_correlation, 'SERVER-123');
  assert.equal(result.observed_posts, 1);
  assert.equal(result.guard_retained_closed, true);
  assert.equal(JSON.stringify(f.state.continued), JSON.stringify([{ url: OWNED }]));
  await f.state.routePost(); assert.equal(f.state.continued.length, 1);
  assert.equal(f.state.aborted, 1);
});

test('real XML nullable counters accepted; invalid counter and unknown key type rejected', async () => {
  for (const [field, value] of [['usage', {}], ['usage', { input_tokens: -1, output_tokens: null, total_tokens: null }],
    ['key_types', { answers: 'Object', secret: 'String' }]]) {
    const f = fixture(); await f.invoke('observe'); f.state.diagnostic[field] = value;
    await assert.rejects(f.invoke('score'), /SERVER_DIAGNOSTIC/);
    assert.equal(f.state.disabled, true);
  }
});

test('invalid first POST consumes allowance permanently', async () => {
  const f = fixture(); await f.invoke('observe'); f.state.badBody = true;
  await assert.rejects(f.invoke('score'), /ONE_POST_RESPONSE/);
  await f.state.routePost(); assert.equal(f.state.continued.length, 0); assert.equal(f.state.aborted, 2);
});

test('stale DOM30, checkpoint90 and integration score all fail closed', async () => {
  for (const change of [{ inspection_issued_at: new Date(Date.now() - 30001).toISOString() },
    { full_started_at: new Date(Date.now() - 90001).toISOString() },
    { scope: 'READ_ONLY_INTEGRATION_NOT_PACKAGE_PREFLIGHT' }]) {
    const f = fixture(); await f.invoke('observe');
    await assert.rejects(vm.runInNewContext('(' + source + ')(page, request)',
      { page: f.page, request: { ...f.request('score'), ...change } }));
    assert.equal(f.state.continued.length, 0);
  }
});