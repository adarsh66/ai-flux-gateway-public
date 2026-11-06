async function mountedProbe(page, binding) {
  // This is the COMPLETE executable tool body, not stringified closures or a
  // Node module the VS Code browser would have to import. READ ONLY throughout.
  const url = 'https://poc-ids-token-ex-customer.azurewebsites.net/playground';
  if (binding.schema !== 9 || !['mounted-observe', 'mounted-inspect'].includes(binding.phase)
      || binding.page_id !== '73973940-4718-42f8-8f59-4c5623ba1926'
      || binding.page_url !== url || page.url() !== url
      || !/^[a-f0-9]{64}$/.test(binding.request_id)
      || !/^[a-f0-9]{64}$/.test(binding.manifest_sha256)
      || !/^[a-f0-9]{64}$/.test(binding.sources_sha256)
      || !(Date.now() >= Date.parse(binding.issued_at) && Date.now() < Date.parse(binding.expires_at))) {
    throw new Error('READONLY_REQUEST_BINDING');
  }
  const model = page.getByRole('combobox', { name: 'Model', exact: true });
  const subscription = page.getByRole('combobox', { name: 'Subscription', exact: true });
  const log = page.getByRole('log');
  // Inspect only public, non-secret controls. Never key fields, browser storage,
  // headers, response bodies, network events, route hooks, fills or keypresses.
  const dom = {
    model_names: await model.locator('option').allTextContents(),
    selected_model: await model.locator('option:checked').innerText({ timeout: 3000 }),
    subscription: await subscription.locator('option:checked').innerText({ timeout: 3000 }),
    system_empty: await page.getByRole('textbox', { name: 'System prompt (optional)', exact: true }).inputValue({ timeout: 3000 }) === '',
    draft_empty: await page.getByRole('textbox', { name: 'Message', exact: true }).inputValue({ timeout: 3000 }) === '',
    turns: await log.locator('.turn').count(),
    empty_conversation: await log.getByText('Start a conversation', { exact: true }).count() === 1,
    send_enabled: await page.getByRole('button', { name: 'Send', exact: true }).isEnabled({ timeout: 3000 }),
    customer: await page.getByText('Caldova', { exact: true }).count() === 1 ? 'Caldova' : 'NOT_MATCHED',
  };
  if (page.url() !== url || !(Date.now() < Date.parse(binding.expires_at))) throw new Error('READONLY_EXPIRED_OR_NAVIGATED');
  return { binding, observed_at: new Date().toISOString(), page_url: page.url(), dom };
}