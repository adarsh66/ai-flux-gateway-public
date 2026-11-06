import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';

const source = readFileSync(new URL('../scripts/deployment/auto_resume09_probe.js', import.meta.url), 'utf8');
const url = 'https://poc-ids-token-ex-customer.azurewebsites.net/playground';
function fixture() {
  const calls = [];
  const binding = { schema: 9, phase: 'mounted-observe',
    page_id: '73973940-4718-42f8-8f59-4c5623ba1926', page_url: url,
    request_id: 'a'.repeat(64), manifest_sha256: 'b'.repeat(64), sources_sha256: 'c'.repeat(64),
    issued_at: new Date(Date.now() - 1000).toISOString(), expires_at: new Date(Date.now() + 60000).toISOString() };
  function locator(label) {
    return new Proxy({}, { get(_, method) {
      if (['locator', 'getByText'].includes(method)) return arg => locator(label + ':' + arg);
      if (method === 'allTextContents') return async () => ['MOCK_NAMES_ONLY_NOT_LIVE'];
      if (method === 'innerText') return async () => label.startsWith('Model') ? 'gpt-5.6-luna' : 'Caldova-AI';
      if (method === 'inputValue') return async () => '';
      if (method === 'count') return async () => label.includes('.turn') ? 0 : 1;
      if (method === 'isEnabled') return async () => true;
      throw new Error('UNEXPECTED_LOCATOR_ACTION:' + String(method));
    } });
  }
  const page = new Proxy({}, { get(_, method) {
    if (method === 'url') return () => url;
    if (method === 'getByRole') return (role, options) => {
      calls.push([role, options?.name]);
      return locator(options?.name || role);
    };
    if (method === 'getByText') return text => locator(text);
    throw new Error('UNEXPECTED_PAGE_ACTION:' + String(method));
  } });
  // Test compilation of the exact standalone source the actual browser receives.
  return { probe: vm.runInNewContext('(' + source + ')'), page, binding, calls };
}
test('standalone source runs without module closure, only allowlisted read operations', async () => {
  const f = fixture();
  const result = await f.probe(f.page, f.binding);
  assert.equal(result.dom.draft_empty, true);
  assert.equal(result.dom.turns, 0);
  assert.deepEqual(result.binding, f.binding);
  assert.ok(!f.calls.some(c => /key/i.test(c[1] || '')));
});
test('every page/phase/hash/time guard rejects before DOM reads', async () => {
  for (const [field, value] of [['phase', 'score'], ['page_id', 'foreign'], ['page_url', 'https://evil.invalid'],
    ['request_id', ''], ['sources_sha256', 'x'], ['manifest_sha256', 'x'],
    ['expires_at', '2000-01-01T00:00:00Z'], ['issued_at', '2099-01-01T00:00:00Z']]) {
    const f = fixture(); f.binding[field] = value;
    await assert.rejects(() => f.probe(f.page, f.binding), /BINDING/);
    assert.equal(f.calls.length, 0);
  }
});
test('second external inspection executes without prior module memory', async () => {
  const f = fixture(); f.binding.phase = 'mounted-inspect';
  assert.equal((await f.probe(f.page, f.binding)).binding.phase, 'mounted-inspect');
});