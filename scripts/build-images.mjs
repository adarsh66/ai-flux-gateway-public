// Build/publish only. All ARM actions run through the isolated Terraform root.
// No shell interpolation of credentials; SAS responses stay in process memory.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import https from 'node:https';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tfRoot = path.join(root, 'infra/image-build');
const tf = 'C:/Program Files/Terraform/terraform.exe';
const az = 'C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd';
const env = { ...process.env, TF_CLI_CONFIG_FILE: path.join(root, '.deployment/terraform.rc'), TF_IN_AUTOMATION: '1' };
// Azure CLI log streams contain Unicode (Vite/Functions); piped Windows output
// otherwise uses cp1252 and can abort successful remote build verification.
env.PYTHONIOENCODING = 'utf-8';
env.PYTHONUTF8 = '1';
delete env.TF_LOG;
delete env.TF_LOG_PATH;
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const redact = text => text.replace(/https:\/\/[^\s"<>]*\?[^\s"<>]*/g, '[redacted signed URL]');
let evidence;
function execute(exe, args, { json = false, log, quiet = false } = {}) {
  // cmd files require cmd.exe on Windows; arguments here are controlled strings.
  const result = spawnSync(exe.endsWith('.cmd') ? `"${exe}"` : exe, args, { cwd: root, env, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
    shell: exe.endsWith('.cmd'), windowsHide: true });
  const text = redact((result.stdout || '') + (result.stderr || ''));
  if (log) fs.writeFileSync(path.join(evidence, log), text);
  if (result.error || result.status !== 0) throw new Error(`${path.basename(exe)} ${args[0]} failed: ${redact(result.error?.message || text)}`);
  if (json) return JSON.parse(result.stdout);
  if (!quiet) console.log(text.trim());
  return result.stdout;
}
const terraform = (args, options) => execute(tf, [`-chdir=${tfRoot}`, ...args], options);
// az.cmd uses Python -I, which ignores PYTHONIOENCODING/PYTHONUTF8. Invoke the
// same installed CLI runtime with explicit UTF-8 (and no shell) for log streams.
const cli = (args, options) => execute(path.resolve(path.dirname(az),'../python.exe'),
  ['-X','utf8','-IBm','azure.cli',...args,'--only-show-errors'], options);
function walk(dir, accept) {
  return fs.readdirSync(path.join(root, dir), { withFileTypes: true }).sort((a,b) => a.name.localeCompare(b.name)).flatMap(entry => {
    const name = `${dir}/${entry.name}`;
    if (entry.isSymbolicLink()) throw new Error(`Symlink rejected: ${name}`);
    if (entry.isDirectory()) return entry.name.startsWith('.') || ['node_modules','dist','build','__pycache__'].includes(entry.name) ? [] : walk(name, accept);
    return accept(name) ? [name] : [];
  });
}
function packageSource() {
  const exact = ['package.json','package-lock.json','tsconfig.base.json','pyproject.toml',
    'services/control-plane/Dockerfile','services/control-plane/alembic.ini',
    'services/control-plane/functions.Dockerfile',
    'services/usage-ingestion/Dockerfile',
    'gateway/policies/settings-unconfigured.xml'];
  const files = [...exact,
    ...walk('services/control-plane/functions', n => /\.(py|json)$/.test(n)),
    ...walk('services/usage-ingestion', n => /\.(py|json|txt)$/.test(n)),
    ...walk('services/control-plane/src', n => /\.(py|kql)$/.test(n)),
    ...walk('services/control-plane/migrations', n => n.endsWith('.py') && !n.endsWith('/0003_portal_users.py')),
    ...walk('gateway/catalog', n => n.endsWith('.json')),
    ...['apps/admin-portal','apps/customer-portal','packages/ui'].flatMap(dir => walk(dir, n =>
      /\/(src|public)\//.test(n) ? /\.(tsx?|css|svg|png|ico|woff2?|json)$/.test(n) :
        /\/(package\.json|tsconfig\.json|vite\.config\.ts|index\.html|Dockerfile|nginx\.conf\.template)$/.test(n))),
  ].sort();
  const revisions = files.filter(n => /migrations\/versions\/.*\.py$/.test(n)).map(n => {
    const text = fs.readFileSync(path.join(root,n),'utf8');
    return { path:n, revision:text.match(/^revision\s*=\s*['"]([^'"]+)/m)?.[1], parent:text.match(/^down_revision\s*=\s*['"]([^'"]+)/m)?.[1] ?? null };
  });
  if (new Set(revisions.map(r => r.revision)).size !== revisions.length || revisions.some(r => !r.revision || (r.parent && !revisions.some(p => p.revision === r.parent)))) throw new Error('Invalid packaged migration graph');
  const entries = files.map(name => {
    if (/(^|\/)(\.|node_modules|state|credentials)|\.(tfvars|pem|pfx|key|db|sqlite)/i.test(name)) throw new Error(`Disallowed source: ${name}`);
    const bytes = fs.readFileSync(path.join(root,name));
    if (/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}|[?&]sig=[A-Za-z0-9%+/]{30}/.test(bytes.toString('utf8'))) throw new Error(`Potential secret in ${name}`);
    return { path:name, sha256:hash(bytes), size:bytes.length };
  });
  const sourceHash = hash(JSON.stringify(entries));
  const tag = `local-${new Date().toISOString().replace(/[-:]/g,'').slice(0,15).toLowerCase()}z-${sourceHash.slice(0,12)}`;
  evidence = path.join(root, '.deployment/image-build', tag);
  fs.mkdirSync(evidence,{recursive:true});
  const stage = path.join(evidence,'context');
  for (const entry of entries) {
    const dest = path.join(stage,entry.path);
    fs.mkdirSync(path.dirname(dest),{recursive:true});
    fs.copyFileSync(path.join(root,entry.path),dest);
    if (hash(fs.readFileSync(dest)) !== entry.sha256) throw new Error('Source changed during packaging');
  }
  const archive = path.join(evidence,'source.tar.gz');
  execute('C:/Windows/System32/tar.exe',['-czf',archive,'-C',stage,'.'],{quiet:true});
  fs.writeFileSync(path.join(evidence,'source-manifest.json'),JSON.stringify({tag,sourceHash,archiveSha256:hash(fs.readFileSync(archive)),entries,revisions,
    exclusions:['legacy untracked 0003_portal_users.py: PortalUser model no longer exists; active auth uses LocalUser/0003_stable_teams.py'],
  },null,2));
  return {tag,archive,sourceHash};
}
function checkedPlan(tag, enabled, name) {
  const plan = path.join(evidence,`${name}.tfplan`);
  terraform(['plan','-input=false','-no-color',`-var=release_tag=${tag}`,`-var=build_enabled=${enabled}`,`-out=${plan}`],{log:`${name}-plan.log`,quiet:true});
  const parsed = terraform(['show','-json',plan],{json:true,quiet:true});
  if (parsed.errored || parsed.applyable === false) throw new Error('Build plan is not applyable');
  for (const resource of parsed.resource_changes || []) {
    if (resource.change.actions.every(a => a === 'no-op')) continue;
    if (resource.type !== 'azapi_resource_action' || !['source_upload','build'].includes(resource.name) || resource.change.actions.some(a => a !== 'create')) throw new Error(`Out-of-scope plan: ${resource.address}`);
    const after = resource.change.after;
    if (!['listBuildSourceUploadUrl','scheduleRun'].includes(after.action) || after.resource_id !== registryId) throw new Error('Out-of-scope ARM action');
  }
  terraform(['apply','-input=false','-no-color','-parallelism=1',plan],{log:`${name}-apply.log`,quiet:true});
}
const registryId = '/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr';
async function putArchive(url, archive) {
  if (!/^https:\/\/[^/]+\.blob\.core\.windows\.net\//.test(url)) throw new Error('Unexpected upload endpoint');
  await new Promise((resolve,reject) => {
    const request = https.request(url,{method:'PUT',headers:{'x-ms-blob-type':'BlockBlob','Content-Type':'application/octet-stream','Content-Length':fs.statSync(archive).size}}, response => {
      response.resume();
      response.on('end',() => response.statusCode === 201 ? resolve() : reject(new Error(`Artifact upload HTTP ${response.statusCode}`)));
    });
    request.on('error',error => reject(new Error(`Artifact transfer failed: ${error.code}`)));
    fs.createReadStream(archive).pipe(request);
  });
}
async function main() {
  const account = cli(['account','show','-o','json'],{json:true,quiet:true});
  if (account.id !== 'aa28274d-fea0-46d4-b9c8-30f3ef0a0e52' || account.tenantId !== 'beb276ac-6e9f-498e-8e31-019ee666decd' || account.user.name.toLowerCase() !== 'xv.puneet.devadiga@singtel.com') throw new Error('Wrong Azure account');
  const resumeTag = process.argv[2] === '--verify-release' ? process.argv[3] : null;
  if (resumeTag && !/^local-[0-9]{8}t[0-9]{6}z-[a-f0-9]{12}$/.test(resumeTag)) throw new Error('Invalid release tag');
  if (resumeTag) evidence = path.join(root,'.deployment/image-build',resumeTag);
  const release = resumeTag ? JSON.parse(fs.readFileSync(path.join(evidence,'source-manifest.json'),'utf8')) : packageSource();
  console.log(`Build-only release ${release.tag}; evidence ${path.relative(root,evidence)}`);
  const registry = cli(['acr','show','-n','pocidstokenexacr','-o','json'],{json:true,quiet:true});
  if (registry.id.toLowerCase() !== registryId.toLowerCase() || registry.adminUserEnabled || registry.loginServer !== 'pocidstokenexacr.azurecr.io') throw new Error('Registry target/security mismatch');
  fs.writeFileSync(path.join(evidence,'registry-before.json'),JSON.stringify(registry,null,2));
  if (!resumeTag) {
  terraform(['init','-input=false','-no-color','-reconfigure','-backend-config=../terraform/backend.hcl',`-backend-config=key=poc-ids-token-ex/image-build/${release.tag}.tfstate`],{log:'init.log',quiet:true});
  terraform(['validate','-no-color'],{log:'validate.log'});
  checkedPlan(release.tag,false,'upload');
  const upload = terraform(['output','-json','source_upload'],{json:true,quiet:true});
  await putArchive(upload.uploadUrl,release.archive);
  console.log('Allowlisted local source artifact uploaded; signed URL not logged.');
  checkedPlan(release.tag,true,'build');
  const scheduled = terraform(['output','-json','build_runs'],{json:true,quiet:true});
  fs.writeFileSync(path.join(evidence,'build-runs.json'),JSON.stringify(scheduled,null,2));
  }
  const runs = JSON.parse(fs.readFileSync(path.join(evidence,'build-runs.json'),'utf8'));
  const results = {};
  for (const [name,run] of Object.entries(runs)) {
    console.log(`${name}: ACR run ${run.runId}`);
    cli(['acr','task','logs','-r','pocidstokenexacr','--run-id',run.runId,'--no-format'],{log:`${name}-build.log`,quiet:true});
    const status = cli(['acr','task','show-run','-r','pocidstokenexacr','--run-id',run.runId,'-o','json'],{json:true,quiet:true});
    fs.writeFileSync(path.join(evidence,`${name}-run.json`),JSON.stringify(status,null,2));
    if (status.status !== 'Succeeded') { results[name]={runId:run.runId,status:status.status}; continue; }
    const manifest = cli(['acr','repository','show','-n','pocidstokenexacr','--image',`aiflux-${name}:${release.tag}`,'-o','json'],{json:true,quiet:true});
    if (!/^sha256:[a-f0-9]{64}$/.test(manifest.digest)) throw new Error('Invalid registry manifest digest');
    fs.writeFileSync(path.join(evidence,`${name}-manifest.json`),JSON.stringify(manifest,null,2));
    results[name]={runId:run.runId,status:status.status,tag:release.tag,digest:manifest.digest,image:`pocidstokenexacr.azurecr.io/aiflux-${name}@${manifest.digest}`};
    console.log(`${name}: Succeeded ${results[name].image}`);
  }
  fs.writeFileSync(path.join(evidence,'results.json'),JSON.stringify({tag:release.tag,sourceHash:release.sourceHash,results},null,2));
  const expected = ['api','admin','customer','ingestion','control-plane-function'];
  if (expected.some(name => results[name]?.status !== 'Succeeded') || Object.keys(results).length !== expected.length) throw new Error('One or more required images did not build/publish');
}
main().catch(error => { console.error(redact(error.message)); process.exitCode=1; });