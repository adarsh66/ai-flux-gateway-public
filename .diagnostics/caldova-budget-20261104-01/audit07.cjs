// Offline only. Reads allowlisted receipts/source, writes nothing, executes no imported code.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const here = __dirname;
const root = path.resolve(here, '../..');
const read = p => fs.readFileSync(path.resolve(root, p));
const json = p => JSON.parse(read(p));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const browser = JSON.parse(fs.readFileSync(path.join(here, 'browser06.json')));
const table = name => {
  const t = JSON.parse(fs.readFileSync(path.join(here, name))).tables[0];
  return t.rows.map(row => Object.fromEntries(t.columns.map((c, i) => [c.name, row[i]])));
};
const completion = table('demo-completion-metadata05-result.json');
const scoring = table('demo-scoring-metadata05-result.json');
const rows = browser.unestimated_rows.map(r => Object.fromEntries(browser.row_fields.map((k,i) => [k,r[i]])));
assert.equal(rows.length, 23);
assert.equal(new Set(rows.map(r => r.id)).size, 23);
assert(rows.every(r => r.completeness === 'backend_attribution_missing' && r.provider === '' && r.region === ''));
const correlated = rows.map(r => {
  const matches = completion.filter(t => sha(`${t.resource_id.toLowerCase()}:${t.correlation_id}`) === r.id);
  assert.equal(matches.length, 1, `Unique retained telemetry join required: ${r.id}`);
  const t = matches[0];
  assert.equal(t.parent_status_code, r.status_code);
  assert.equal(t.subscription_id, browser.usage_read.subscription_id);
  return {...r, telemetry: t};
});
const group = (xs, f) => xs.reduce((a,x) => (a[f(x)] = (a[f(x)] || 0)+1,a),{});
const dir = '.deployment/admin-archival-live-20261104-01/';
const monthly = '.deployment/monthly-budget-20261103-01/';
const old = json(monthly+'production04-api-verified.json');
const build = json(dir+'build23-api-intent.json');
assert.equal(sha(read(monthly+'api03/modules/monthly_budgets.py')), old.files['modules/monthly_budgets.py']);
assert.equal(old.pin.split('@')[1], 'sha256:440c63b274851a14e2c32416443a80df1e4c98202040b383250f1058bdc0168a');
const docker = read(dir+'contexts20/api/Production.Dockerfile').toString();
assert(docker.startsWith('FROM '+old.pin+' AS composed'));
assert.equal(sha(Buffer.from(docker)), build.files['Production.Dockerfile']);
assert(!Object.keys(build.files).some(p => /modules\/(monthly_budgets|external_pricing|customer_pricing|display_pricing)\.py$/.test(p)));
const current = json('.diagnostics/caldova-budget-20261104-01/api-image02.json').image;
const built = json(dir+'BUILD23.json').images.api;
assert.equal(current, 'DOCKER|'+built);
const monthlySource = read(monthly+'api03/modules/monthly_budgets.py').toString();
assert(monthlySource.includes('completion_count = estimate["estimated_requests"] + estimate["unestimated_requests"]'));
assert(monthlySource.includes('and completion_count == 0)'));
const successes = rows.filter(r=>r.status_code===200);
const input = successes.reduce((s,r)=>s+r.input_tokens,0);
const output = successes.reduce((s,r)=>s+r.output_tokens,0);
const microUsd = BigInt(input)*8n + BigInt(output)*40n;
const price = n => `${n/1000000n}.${String(n%1000000n).padStart(6,'0')}`;
console.log(JSON.stringify({offline:true,production_queries:0,source_chain:{
  live_pin:built,parent:old.pin,monthly_source_sha256:sha(read(monthly+'api03/modules/monthly_budgets.py')),
  inherited_without_overlay:true,compiled_sql_executed:false,runtime_source_reextracted:false},
  ledger_api:{unestimated:rows.length,statuses:group(rows,r=>r.status_code),reasons:group(rows,r=>r.completeness)},
  telemetry:{completion_rows:completion.length,statuses:group(completion,r=>r.parent_status_code),
    scoring_invocations:scoring.length,scoring_input:scoring.reduce((a,r)=>a+r.input_tokens,0),
    scoring_output:scoring.reduce((a,r)=>a+r.output_tokens,0),all_23_unique_hash_correlations:true},
  four_successes:{input,output,conditional_delta_at_catalog_rates:price(microUsd),
    limit:'Arithmetic only, not a validated historical pricing or SQL correction preview'},
  correlated_unestimated_rows:correlated},null,2));