// Actual native browser contract; no credential/storage/header inspection.
// Reuse the reviewed r5 one-POST bridge, not an HTTP scoring substitute.
import { SOURCE as nativeSource } from './auto_path_oct30_r5_bridge.mjs';
import { createHash } from 'node:crypto';
const ORIGIN = 'https://poc-ids-token-ex-customer.azurewebsites.net';
const TEXT = 'Please greet me in one short sentence.';
const leases = new WeakMap();

function channel(page, binding, phase) {
  const c = binding.channel;
  if (!c || c.phase !== phase || !/^[a-f0-9]{64}$/.test(c.capability)
      || !/^[a-f0-9]{64}$/.test(c.request_id) || c.origin !== ORIGIN
      || c.page_url !== ORIGIN + '/playground' || page.url() !== c.page_url
      || c.page_id !== binding.page_id || c.manifest_sha256 !== binding.manifest_sha256
      || c.browser_source_sha256 !== binding.browser_source_sha256
      || !(Date.now() >= Date.parse(c.issued_at) && Date.now() - Date.parse(c.issued_at) < 30000)) {
    throw new Error('AUTHENTICATED_PARENT_CHANNEL_REQUIRED');
  }
  return c;
}

export async function observe(page, binding) {
  const c = channel(page, binding, 'observe');
  if (leases.has(page)) throw new Error('PREFLIGHT_NO_REPLAY');
  const lease = { capability: c.capability, used: false, blocker: route => route.abort('blockedbyclient') };
  leases.set(page, lease);
  if (!/^[a-f0-9]{64}$/.test(binding.manifest_sha256) || binding.IP !== '167.103.66.248'
      || binding.browser_source_sha256 !== sourceHash) throw new Error('BROWSER_BINDING');
  const system = page.getByRole('textbox', { name: 'System prompt (optional)', exact: true });
  const log = page.getByRole('log');
  const message = page.getByRole('textbox', { name: 'Message', exact: true });
  // Observe real mounted DOM and safe keyboard/input events without Send.
  if (await system.inputValue({ timeout: 5000 }) !== ''
      || !(await log.innerText({ timeout: 5000 })).includes('Start a conversation')
      || await log.locator('.turn').count() !== 0
      || await page.getByRole('combobox', { name: 'Model', exact: true }).inputValue() !== 'gpt-5.4-mini'
      || await message.inputValue() !== '') {
    throw new Error('EMPTY_HISTORY_SYSTEM_MODEL_REQUIRED');
  }
  await page.route(/\/chat\/completions(?:\?.*)?$/, lease.blocker);
  await page.getByRole('button', { name: 'Send', exact: true }).evaluate(button => { button.disabled = true; });
  await message.fill('Please greet me in one short sentence.', { timeout: 5000 });
  await message.press('End', { timeout: 5000 });
  if (await message.inputValue() !== TEXT
      || await page.getByRole('button', { name: 'Send', exact: true }).isEnabled()) throw new Error('SAFE_EVENT');
  return { manifest_sha256: binding.manifest_sha256, browser_source_sha256: sourceHash,
    issued_at: new Date().toISOString(), page_url: page.url(), page_id: binding.page_id,
    IP: binding.IP, system_empty: true, history_empty: true, safe_event: 'fill+End',
    fixture: false, send_invoked: false, auth_inspected: false, channel: c,
    dom: { selected_model: 'gpt-5.4-mini', system: '', turns: 0, draft: TEXT, send_disabled_until_route: true } };
}

export async function score(page, binding) {
  const c = channel(page, binding, 'score');
  const lease = leases.get(page);
  if (!lease || lease.used || c.capability === lease.capability) throw new Error('SCORE_NO_REPLAY');
  lease.used = true;
  const message = page.getByRole('textbox', { name: 'Message', exact: true });
  if (await message.inputValue() !== TEXT
      || await page.getByRole('textbox', { name: 'System prompt (optional)', exact: true }).inputValue() !== ''
      || await page.getByRole('log').locator('.turn').count() !== 0
      || await page.getByRole('combobox', { name: 'Model', exact: true }).inputValue() !== 'gpt-5.4-mini'
      || await page.getByRole('button', { name: 'Send', exact: true }).isEnabled()) throw new Error('DOM_DRIFT');
  // Native source is frozen and hash-bound in the package/review. It installs
  // the catch-all chat route and retains its closed guard until parent cleanup.
  const attempt = (0, eval)('(' + nativeSource + ')');
  let correlation = null;
  const proxy = new Proxy(page, { get(target, key) {
    if (key === 'route') return async (match, handler) => {
      await target.route(match, handler);
      await target.unroute(/\/chat\/completions(?:\?.*)?$/, lease.blocker);
      await target.getByRole('button', { name: 'Send', exact: true }).evaluate(button => { button.disabled = false; });
    };
    if (key === 'waitForResponse') return async (...args) => {
      const response = await target.waitForResponse(...args);
      correlation = await response.headerValue('apim-request-id');
      if (!/^[a-zA-Z0-9-]{1,128}$/.test(correlation || '')) throw new Error('SERVER_CORRELATION_REQUIRED');
      return response;
    };
    const value = target[key];
    return typeof value === 'function' ? value.bind(target) : value;
  } });
  const result = await attempt(proxy, binding);
  return { ...result, channel: c, server_correlation: correlation,
    dom: { selected_model: 'gpt-5.4-mini', system: '', turns: 0, draft: TEXT, send_disabled_until_route: true } };
}

export const SOURCE = JSON.stringify({ channel: channel.toString(), observe: observe.toString(),
  score: score.toString(), nativeSource, ORIGIN, TEXT });
export const sourceHash = createHash('sha256').update(SOURCE).digest('hex');

if (process.argv[1]?.replaceAll('\\', '/').endsWith('/auto_resume06_browser.mjs')
    && process.argv[2] === '--source') process.stdout.write(SOURCE);