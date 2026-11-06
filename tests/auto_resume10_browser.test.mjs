import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../scripts/deployment/auto_resume10_browser.js', import.meta.url), 'utf8');
const NORMAL = 'https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions';
const OWNED = NORMAL.replace('/v1/', '/v1;rev=2/');
const TEXT = 'Please greet me in one short sentence.';
function fixture() {
  const state = { draft: '', disabled: false, model: 'gpt-5.6-luna', turns: 0, events: [], routes: [], continued: [], aborted: 0 };
  const body = { model: 'gpt-5.4-mini', stream: false, max_completion_tokens: 512, messages: [{ role: 'user', content: TEXT }] };
  const response = { url: () => OWNED, request: () => ({ method: () => 'POST' }), status: () => 200,
    headerValue: async name => { assert.equal(name, 'apim-request-id'); return 'SERVER-123'; },
    text: async () => JSON.stringify({ scoring_status: 200, schema_valid: true, body_within_bound: true,
      key_types: {}, probabilities: { greeting: .8, arithmetic: .2 }, usage: {} }) };
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
    waitForResponse: fn => { state.events.push('wait'); predicate = fn; return new Promise(resolve => { resolveResponse = resolve; }); },
    getByRole: (role, options = {}) => {
      if (role === 'textbox' && options.name === 'Message') return message;
      if (role === 'textbox') return { inputValue: async () => '' };
      if (role === 'button') return button;
      if (role === 'combobox') return { inputValue: async () => state.model,
        selectOption: async model => { assert.ok(state.disabled); state.model = model; } };
      if (role === 'log') return { innerText: async () => 'Start a conversation', locator: () => ({ count: async () => state.turns }) };
      throw Error('Unsupported API');
    } };
  const request = phase => ({ schema: 10, phase, scope: 'ONE_SCORE_ZERO_COMPLETION_NO_RETRY',
    challenge: 'a'.repeat(64), manifest_sha256: 'b'.repeat(64), nonce: 'c'.repeat(32),
    issued_at: new Date(Date.now() - 100).toISOString(), expires_at: new Date(Date.now() + 30000).toISOString(),
    activation_manifest_sha256: 'b'.repeat(64), reservation_sha256: 'd'.repeat(64),
    window_end: new Date(Date.now() + 30 * 60000).toISOString() });
  // Every phase executes in a NEW empty VM, like separate native tool calls.
  const invoke = async phase => vm.runInNewContext('(' + source + ')(page, request)', { page, request: request(phase) });
  return { state, page, request, invoke };
}

test('standalone observe blocks route and disables Send BEFORE fill+End; new-context inspect', async () => {
  const f = fixture();
  const observed = await f.invoke('observe');
  assert.equal(observed.dom.model, 'gpt-5.4-mini');
  assert.deepEqual(f.state.events.slice(0, 4), ['route', 'disable', 'fill', 'End']);
  assert.equal((await f.invoke('inspect')).dom.send_disabled, true);
  assert.equal(f.state.continued.length, 0);
});

test('one POST URL-only rewrite, waiter first, no credentials, all later requests abort', async () => {
  const f = fixture(); await f.invoke('observe'); await f.invoke('inspect');
  const result = await f.invoke('score');
  assert.equal(result.server_correlation, 'SERVER-123');
  assert.equal(result.observed_posts, 1);
  assert.equal(result.guard_retained_closed, true);
  assert.equal(f.state.continued.length, 1);
  assert.equal(JSON.stringify(f.state.continued[0]), JSON.stringify({ url: OWNED }));
  assert.ok(f.state.events.indexOf('wait') < f.state.events.indexOf('Control+Enter'));
  await f.state.routePost();
  assert.equal(f.state.continued.length, 1);
  assert.equal(f.state.aborted, 1);
  assert.equal('scoring_request_count' in result, false);
});

test('invalid first body consumes allowance, never forwarded, never retried', async () => {
  const f = fixture(); await f.invoke('observe'); f.state.badBody = true;
  await assert.rejects(f.invoke('score'), /ONE_POST_RESPONSE/);
  await f.state.routePost();
  assert.equal(f.state.continued.length, 0);
  assert.equal(f.state.aborted, 2);
  assert.equal(f.state.disabled, true);
});

test('wrong activation/window prevents Send; unsupported globals absent', async () => {
  const f = fixture(); await f.invoke('observe');
  const request = { ...f.request('score'), activation_manifest_sha256: '0'.repeat(64) };
  await assert.rejects(vm.runInNewContext('(' + source + ')(page, request)', { page: f.page, request }), /ACTIVATION/);
  assert.equal(f.state.events.includes('Control+Enter'), false);
  assert.doesNotMatch(source, /\brequire\s*\(|setTimeout|setInterval|localStorage|sessionStorage|\.headers\(/);
});