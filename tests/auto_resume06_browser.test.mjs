import test from 'node:test';
import assert from 'node:assert/strict';
import { observe, score, SOURCE, sourceHash } from '../scripts/deployment/auto_resume06_browser.mjs';
import { SOURCE as original } from '../scripts/deployment/auto_path_oct30_r5_bridge.mjs';

function fixture() {
  const events = [];
  let message = '';
  let disabled = false;
  const page = {
    url: () => 'https://poc-ids-token-ex-customer.azurewebsites.net/playground',
    route: async () => events.push('route-block'),
    getByRole(role, options) {
      const name = options?.name;
      if (role === 'log') return { innerText: async () => 'Start a conversation', locator: () => ({ count: async () => 0 }) };
      return { inputValue: async () => name === 'System prompt (optional)' ? '' : name === 'Model' ? 'gpt-5.4-mini' : message,
        isEnabled: async () => !disabled,
        evaluate: async fn => { const button = { disabled }; fn(button); disabled = button.disabled; },
        fill: async text => { message = text; events.push('fill'); },
        press: async key => events.push(key) };
    }
  };
  const binding = { manifest_sha256: 'a'.repeat(64), browser_source_sha256: sourceHash,
    IP: '167.103.66.248', page_id: 'p'.repeat(36) };
  binding.channel = { phase: 'observe', capability: 'c'.repeat(64), request_id: 'd'.repeat(64),
    page_id: binding.page_id, page_url: page.url(), origin: 'https://poc-ids-token-ex-customer.azurewebsites.net',
    manifest_sha256: binding.manifest_sha256, browser_source_sha256: sourceHash, issued_at: new Date().toISOString() };
  return { page, binding, events };
}
test('bridge source exactly original real r5 one-shot implementation', () => {
  assert.equal(JSON.parse(SOURCE).nativeSource, original);
  assert.match(original, /route\.continue\(\{ url: REVISION \}\)/);
  assert.match(original, /sanitize\(await value\.text\(\)\)/);
  assert.doesNotMatch(SOURCE, /localStorage|sessionStorage|request\.headers/);
});
test('preflight executes actual locator safe events without Send', async () => {
  const f = fixture(); const value = await observe(f.page, f.binding);
  assert.deepEqual(f.events, ['route-block', 'fill', 'End']);
  assert.equal(value.system_empty, true); assert.equal(value.history_empty, true);
  assert.equal(value.fixture, false); assert.equal(value.send_invoked, false);
  assert.equal(value.manifest_sha256, f.binding.manifest_sha256);
});
test('wrong manifest/source/IP rejected before page events', async () => {
  for (const change of [{manifest_sha256: 'bad'}, {browser_source_sha256: 'b'.repeat(64)}, {IP: 'old'}]) {
    const f = fixture(); await assert.rejects(observe(f.page, {...f.binding, ...change}));
    assert.deepEqual(f.events, []);
  }
});
test('nonempty system blocks native score before routing or keyboard', async () => {
  const f = fixture(); f.page.getByRole = () => ({inputValue: async () => 'not empty'});
  await assert.rejects(observe(f.page, f.binding)); assert.deepEqual(f.events, []);
});
test('noauth unknown origin wrong page request nonce and expired channel rejected', async () => {
  for (const change of [null, {origin: 'http://localhost'}, {page_url: 'https://evil.invalid/'},
    {request_id: ''}, {capability: ''}, {issued_at: '2020-01-01T00:00:00Z'}]) {
    const f = fixture();
    f.binding.channel = change === null ? null : {...f.binding.channel, ...change};
    await assert.rejects(observe(f.page, f.binding), /CHANNEL_REQUIRED/);
    assert.deepEqual(f.events, []);
  }
});
test('preflight replay and same nonce score cannot invoke keyboard', async () => {
  const f = fixture(); await observe(f.page, f.binding);
  await assert.rejects(observe(f.page, f.binding), /NO_REPLAY/);
  f.binding.channel.phase = 'score';
  await assert.rejects(score(f.page, f.binding), /NO_REPLAY/);
  assert.equal(f.events.includes('Control+Enter'), false);
});
test('single fresh score attempt consumes before route even if DOM drifts', async () => {
  const f = fixture(); await observe(f.page, f.binding);
  f.binding.channel = {...f.binding.channel, phase: 'score', capability: 'e'.repeat(64)};
  f.page.getByRole = () => ({inputValue: async () => 'FOREIGN'});
  await assert.rejects(score(f.page, f.binding), /DOM_DRIFT/);
  await assert.rejects(score(f.page, f.binding), /NO_REPLAY/);
  assert.equal(f.events.includes('Control+Enter'), false);
});