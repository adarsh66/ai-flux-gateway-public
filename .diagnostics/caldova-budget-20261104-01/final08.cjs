// Offline evidence analysis only: no network, imports of project code, or file writes.
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const path = require('node:path');
const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const read = p => fs.readFileSync(path.resolve(__dirname, p));
const json = p => JSON.parse(read(p));
function csv(text) {
  const rows = []; let row = [], value = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') { if (quoted && text[i + 1] === '"') { value += '"'; i++; } else quoted = !quoted; }
    else if (!quoted && (c === ',' || c === '\n')) {
      row.push(value.replace(/\r$/, '')); value = '';
      if (c === '\n') { rows.push(row); row = []; }
    } else value += c;
  }
  assert(!quoted);
  if (value || row.length) { row.push(value.replace(/\r$/, '')); rows.push(row); }
  const header = rows.shift(); header[0] = header[0].replace(/^\uFEFF/, '');
  return rows.filter(r => r.length > 1).map(r => { assert.equal(r.length, header.length); return Object.fromEntries(header.map((h,i) => [h,r[i]])); });
}
const table = p => { const t = json(p).tables[0]; return t.rows.map(r => Object.fromEntries(t.columns.map((c,i) => [c.name,r[i]]))); };
const group = (xs, f) => xs.reduce((a,x) => (a[f(x)] = (a[f(x)] || 0) + 1, a), {});
const fixed = v => { assert(/^\d+(\.\d{1,12})?$/.test(v)); const [a,b=''] = v.split('.'); return BigInt(a)*10n**12n + BigInt(b.padEnd(12,'0')); };
const money = v => `${v/10n**12n}.${String(v%10n**12n).padStart(12,'0')}`;
// Compare UTC fractions textually, retaining microseconds; JavaScript Date would lose them.
const timestamp = s => { const m = s.match(/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(?:Z|\+00:00)$/); assert(m, s); return m[1]+'.'+(m[2]||'').padEnd(7,'0').slice(0,6); };
const csvPath = 'C:/Users/p4032099/Downloads/aiflux-completion-usage-org-30d.csv';
const raw = fs.readFileSync(csvPath), all = csv(raw.toString('utf8'));
assert.equal(all.length,201); assert.equal(new Set(all.map(r=>r.id)).size,201);
const month = all.filter(r=>r.occurred_at >= '2026-11-01' && r.occurred_at < '2026-12-01');
const estimated = month.filter(r=>r.estimated_cost_usd !== '');
const unknown = month.filter(r=>r.estimated_cost_usd === '');
assert.equal(month.length,112); assert.equal(estimated.length,89); assert.equal(unknown.length,23);
assert(unknown.every(r=>r.completeness==='backend_attribution_missing' && !r.provider && !r.region));
const browser = json('browser06.json');
assert.equal(new Set(all.map(r=>r.subscription_id)).size,1);
assert(all.every(r=>r.subscription_id===browser.usage_read.subscription_id));
const completion = table('demo-completion-metadata05-result.json');
const scoring = table('demo-scoring-metadata05-result.json');
assert.equal(completion.length, month.length);
for (const r of month) {
  const ts = completion.filter(t=>sha(`${t.resource_id.toLowerCase()}:${t.correlation_id}`)===r.id);
  assert.equal(ts.length,1); const t=ts[0];
  assert.equal(t.subscription_id,r.subscription_id);
  assert.equal(t.parent_status_code,Number(r.status_code));
  assert.equal(timestamp(t.occurred_at),timestamp(r.occurred_at));
}
assert.equal(new Set(scoring.map(t=>`${t.resource_id}:${t.correlation_id}`)).size,scoring.length);
assert(scoring.every(t=>t.subscription_id===browser.usage_read.subscription_id && month.some(r=>r.id===sha(`${t.resource_id.toLowerCase()}:${t.correlation_id}`))));
const correlated = unknown.map(r => {
  const matches = completion.filter(t=>sha(`${t.resource_id.toLowerCase()}:${t.correlation_id}`)===r.id);
  assert.equal(matches.length,1,r.id); const t=matches[0];
  assert.equal(t.subscription_id,r.subscription_id); assert.equal(t.parent_status_code,Number(r.status_code));
  assert.equal(timestamp(t.occurred_at),timestamp(r.occurred_at));
  const b = browser.unestimated_rows.find(b=>b[0]===r.id); assert(b);
  return {csv:r, telemetry:t, timestamp_microseconds_equal:true};
});
const good = correlated.filter(r=>r.csv.status_code==='200');
for (const {csv:r,telemetry:t} of good) {
  assert.equal(t.backend_id,'aiflux-project-foundry-eight-anthropic');
  assert.equal(t.usage_trace_count,1); assert.equal(t.backend_request_count_capped,1);
  for (const [field,key] of [['input_tokens','input_values'],['output_tokens','output_values'],['cached_input_tokens','cached_values'],['cache_write_tokens','write_values']]) {
    assert.deepEqual(JSON.parse(t[key]),[Number(r[field])]);
  }
  assert.deepEqual(JSON.parse(t.attempts_values),[1]);
  assert.deepEqual(JSON.parse(t.models),['claude-opus-5-5-fast']);
  assert.deepEqual(JSON.parse(t.llm_deployments),['claude-opus-5-5-fast']);
}
const input = good.reduce((s,r)=>s+Number(r.csv.input_tokens),0), output=good.reduce((s,r)=>s+Number(r.csv.output_tokens),0);
const total=estimated.reduce((s,r)=>s+fixed(r.estimated_cost_usd),0n);
assert.equal(money(total),browser.budget.estimated_used_usd);
const observation=browser.live_catalog_observation;
assert.equal(observation.model,'claude-opus-5-5-fast');
const illustrative = BigInt(input)*fixed(observation.input_usd_per_million)/1000000n + BigInt(output)*fixed(observation.output_usd_per_million)/1000000n;
if (process.argv.includes('--verify-reports')) {
  const report=json('FINAL.json');
  assert.equal(report.input.csv_sha256,sha(raw));
  assert.equal(report.before.estimated_used_usd,money(total));
  assert.equal(report.after_if_all_four_individually_proven_and_eligible.illustrative_sum_delta_at_observed_fast_rates_usd,money(illustrative));
  assert.equal(report.after_if_all_four_individually_proven_and_eligible.illustrative_new_estimated_used_usd,money(total+illustrative));
  assert.equal(report.after_if_all_four_individually_proven_and_eligible.validated_sum_delta_usd,null);
  assert.equal(report.four_candidates.length,good.length);
  for (const c of report.four_candidates) {
    const r=good.find(g=>g.csv.id===c.id); assert(r);
    assert.equal(c.correlation_id,r.telemetry.correlation_id);
    assert.equal(c.input_tokens,Number(r.csv.input_tokens));
    assert.equal(c.output_tokens,Number(r.csv.output_tokens));
    const amount=(BigInt(c.input_tokens)*fixed(observation.input_usd_per_million)+BigInt(c.output_tokens)*fixed(observation.output_usd_per_million))/1000000n;
    assert.equal(c.illustrative_cost_usd,money(amount));
  }
  const errors=correlated.filter(r=>r.csv.status_code!=='200');
  assert.equal(errors.length,19);
  assert(errors.filter(r=>r.csv.status_code!=='503').every(({telemetry:t})=>!t.backend_id && t.usage_trace_count===null && t.backend_request_count_capped===0));
  for (const p of ['FINAL.md','ONEOFF-PROPOSAL.md']) {
    for (const match of read(p).toString().matchAll(/\]\(([^)#]+)(?:#[^)]*)?\)/g)) {
      assert(fs.existsSync(path.resolve(__dirname,match[1])),`Broken report link: ${match[1]}`);
    }
  }
  console.log('PASS: CSV hash, all 112 completion joins, all 23 unestimated joins, four measured-usage/attempt checks, scoring parent joins, exact final arithmetic, candidate IDs, error evidence and report links. No network or production writes.');
  process.exit(0);
}
console.log(JSON.stringify({offline:true,new_cloud_reads:0,production_writes:0,
  evidence_hashes:Object.fromEntries([['CSV',raw],...['browser06.json','demo-completion-metadata05-result.json','demo-scoring-metadata05-result.json','telemetry05-scope.json','demo-completion-metadata05-body.json','demo-scoring-metadata05-body.json'].map(p=>[p,read(p)])].map(([p,b])=>[p,sha(b)])),
  csv:{total:all.length,unique_ids:new Set(all.map(r=>r.id)).size,november:month.length,estimated:estimated.length,unestimated:unknown.length,estimated_sum_usd:money(total),basis:group(estimated,r=>r.estimate_basis),estimated_completeness:group(estimated,r=>r.completeness),unknown_status:group(unknown,r=>r.status_code),models:group(unknown,r=>r.model||'(empty)'),revision:[...new Set(month.map(r=>r.pricing_revision))],subscription:[...new Set(all.map(r=>r.subscription_id))]},
  telemetry:{completion_rows:completion.length,completion_statuses:group(completion,r=>r.parent_status_code),scoring_invocations:scoring.length,scoring_input_tokens:scoring.reduce((s,r)=>s+r.input_tokens,0),scoring_output_tokens:scoring.reduce((s,r)=>s+r.output_tokens,0),scoring_statuses:group(scoring,r=>r.parent_status_code),scoring_schemas:group(scoring,r=>r.schema),all_112_unique_hash_and_microsecond_joins:true,all_23_unique_hash_and_microsecond_joins:true,four_success_usage_cache_attempts_verified:true,scoring_unique_and_parent_join_verified:true},
  successes:{count:good.length,input,output,current_config_only_rates:observation,illustrative_delta_usd:money(illustrative),illustrative_total_usd:money(total+illustrative),validated_delta_usd:null,historical_rate_proven:false,historical_route_proven:false},
  correlated_unestimated_rows:correlated.map(({csv:r,telemetry:t})=>({id:r.id,occurred_at:r.occurred_at,correlation_id:t.correlation_id,status:Number(r.status_code),input:Number(r.input_tokens),output:Number(r.output_tokens),backend:t.backend_id,usage_traces:t.usage_trace_count,llm_model:t.llm_models,llm_deployment:t.llm_deployments,backend_requests_capped:t.backend_request_count_capped}))},null,2));