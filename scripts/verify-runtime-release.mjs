// Read-only Azure evidence and immutable Terraform input generation. No resource writes.
import fs from 'node:fs';
import path from 'node:path';
import dns from 'node:dns/promises';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tag = process.argv[2];
if (!/^local-[0-9]{8}t[0-9]{6}z-[a-f0-9]{12}$/.test(tag || '')) throw new Error('Verified release tag required');
const dir = path.join(root,'.deployment/image-build',tag);
const release = JSON.parse(fs.readFileSync(path.join(dir,'results.json'),'utf8'));
const subscription = 'aa28274d-fea0-46d4-b9c8-30f3ef0a0e52';
const rg = `/subscriptions/${subscription}/resourceGroups/IDS-TOKEN-EXCHANGE-POC`;
const cliPython = 'C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe';
function cli(args, allowFailure = false) {
  const result = spawnSync(cliPython,['-X','utf8','-IBm','azure.cli',...args,'--only-show-errors','-o','json'],
    {cwd:root,env:process.env,encoding:'utf8',maxBuffer:16*1024*1024,windowsHide:true});
  if (result.status !== 0) {
    if (allowFailure) return {success:false,forbiddenByRbac:/ForbiddenByRbac/.test(result.stderr || ''),exitCode:result.status};
    throw new Error(`Read-only Azure operation failed: ${args.slice(0,2).join(' ')}`);
  }
  return JSON.parse(result.stdout);
}
const account = cli(['account','show']);
if (account.id !== subscription || account.tenantId !== 'beb276ac-6e9f-498e-8e31-019ee666decd' ||
    account.user.name.toLowerCase() !== 'xv.puneet.devadiga@singtel.com') throw new Error('Wrong Azure context');
const results = release.results;
for (const name of ['api','admin','customer','ingestion','control-plane-function']) {
  if (results[name]?.status !== 'Succeeded' || !/^pocidstokenexacr\.azurecr\.io\/aiflux-[a-z-]+@sha256:[a-f0-9]{64}$/.test(results[name]?.image || '')) throw new Error('Incomplete verified image release');
}
const pins = {
  apps:Object.fromEntries(['api','admin','customer'].map(name => [name,{
    image:results[name].image.split('/').slice(1).join('/'),registry_url:'https://pocidstokenexacr.azurecr.io',
    port:name === 'api' ? 8000 : 8080,health_path:name === 'api' ? '/health' : '/healthz',
  }])),
  ingestion_container_image:results.ingestion.image,
  control_plane_container_image:results['control-plane-function'].image,
  ingestion_enabled:false,ingestion_timer_enabled:false,control_plane_worker_enabled:false,
  retain_legacy_mssql:true,
};

const principal = {
  'control-plane':'967370eb-a5b0-4531-bc2b-b15a83ac3efd',
  ingestion:'edbfc3e2-a8e5-4652-9bb0-311233756d42',
  api:'4e7b70ed-9868-47ba-9b61-304f1e1fdd89',gateway:'bcf69911-f34e-4f33-acd8-a36f164db811',
};
const assignments = cli(['role','assignment','list','--all','--include-inherited']);
const suffix = {
  acr:'/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr',
  insights:'/providers/Microsoft.Insights/components/poc-ids-token-ex-insights',
  storage:'/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc',
  vault:'/providers/Microsoft.KeyVault/vaults/pocidstokenexkv',
  events:'/providers/Microsoft.EventHub/namespaces/poc-ids-token-ex-eh/eventhubs/token-usage',
};
const requests = [
  ['control-plane','AcrPull','acr'],['control-plane','Monitoring Metrics Publisher','insights'],
  ...['Storage Blob Data Owner','Storage Queue Data Contributor','Storage Table Data Contributor'].map(role => ['control-plane',role,'storage']),
  ['ingestion','AcrPull','acr'],['api','Key Vault Secrets User','vault'],
  ['api','Storage Table Data Contributor','storage'],['gateway','Storage Table Data Contributor','storage'],
  ['gateway','Azure Event Hubs Data Sender','events'],['ingestion','Azure Event Hubs Data Receiver','events'],
];
const grants = requests.map(([identity,role,resource]) => {
  const scope = rg + suffix[resource];
  return {identity,principalId:principal[identity],role,scope,visible:assignments.some(item =>
    item.principalId?.toLowerCase() === principal[identity] && item.roleDefinitionName === role &&
    (scope.toLowerCase() === item.scope.toLowerCase() || scope.toLowerCase().startsWith(item.scope.toLowerCase() + '/')))};
});
// Runtime attestation follows actual central-team evidence, never a hardcoded
// false that erases a completed handoff, nor a true set merely to bypass gates.
pins.manual_rbac_verified = grants.length === 11 && grants.every(item => item.visible);
const pinsPath = path.join(dir,'runtime-images.tfvars.json');
const existingPins = fs.existsSync(pinsPath) ? JSON.parse(fs.readFileSync(pinsPath,'utf8')) : {};
fs.writeFileSync(pinsPath,JSON.stringify({...existingPins,...pins},null,2));
const resources = cli(['resource','list','-g','IDS-TOKEN-EXCHANGE-POC']);
const runners = resources.filter(item => ['Microsoft.Compute/virtualMachines','Microsoft.App/jobs','Microsoft.ContainerInstance/containerGroups'].includes(item.type)).map(({name,type,id}) => ({name,type,id}));
const postgres = cli(['postgres','flexible-server','show','-g','IDS-TOKEN-EXCHANGE-POC','-n','poc-ids-token-ex-pg']);
const addresses = await dns.lookup(postgres.fullyQualifiedDomainName,{all:true});
const privateOnly = addresses.length > 0 && addresses.every(({address}) => /^10\.|^192\.168\.|^172\.(1[6-9]|2[0-9]|3[01])\./.test(address));
const vaultMetadata = cli(['keyvault','secret','list','--vault-name','pocidstokenexkv','--maxresults','1','--query','[].id'],true);
const sites = [];
for (const name of ['api','admin','customer']) {
  const site = cli(['webapp','show','-g','IDS-TOKEN-EXCHANGE-POC','-n',`poc-ids-token-ex-${name}`]);
  const config = cli(['webapp','config','show','-g','IDS-TOKEN-EXCHANGE-POC','-n',`poc-ids-token-ex-${name}`]);
  sites.push({name,state:site.state,publicNetworkAccess:site.publicNetworkAccess,
    image:config.linuxFxVersion,defaultAction:config.ipSecurityRestrictionsDefaultAction,
    scmDefaultAction:config.scmIpSecurityRestrictionsDefaultAction,scmUsesMain:config.scmIpSecurityRestrictionsUseMain,
    allows:config.ipSecurityRestrictions.filter(rule => rule.action === 'Allow').map(rule => ({name:rule.name,ip:rule.ipAddress})),
    scmAllows:config.scmIpSecurityRestrictions.filter(rule => rule.action === 'Allow').map(rule => ({name:rule.name,ip:rule.ipAddress}))});
}
const report = {checkedAt:new Date().toISOString(),tag,grants,missingVisibleGrants:grants.filter(item => !item.visible).length,
  vaultMetadata:{success:Array.isArray(vaultMetadata),forbiddenByRbac:vaultMetadata.forbiddenByRbac || false},
  postgres:{state:postgres.state,publicNetworkAccess:postgres.network.publicNetworkAccess,addresses,privateOnly},
  existingPrivateRunnerCandidates:runners,sites,runtimeApplied:false,
  limitations:['No live database login/bootstrap or managed-identity DML check performed.',
    'No central grants, secrets, application settings or network restrictions changed.',
    'Publication worker requires separate fragment-scoped central authorization and is disabled under Terraform-only writes.',
    'Release/provisioning workers and Event Hub ingestion adapters are not implemented by the current runtime.']};
fs.writeFileSync(path.join(dir,'runtime-readiness.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));