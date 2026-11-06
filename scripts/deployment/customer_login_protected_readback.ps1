param([ValidateSet('baseline','verify')][string]$Phase)
$env:PYTHONPATH='C:/LocalWorkspace/ai-flux-gateway-public;C:/LocalWorkspace/ai-flux-gateway-public/services/control-plane/src;C:/LocalWorkspace/ai-flux-gateway-public/.venv/Lib/site-packages'
$code=@'
import json, sys
from pathlib import Path
from scripts.deployment import customer_login_release as s
phase=sys.argv[1]
r=s.Release('customer-login-20261028T124500Z')
s.account()
if phase=='baseline':
    s.rt.require(not (r.home/'apply-intent.json').exists(), 'supplement_before_apply_required')
account=s.rt.RG+'/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry'
policies=s.rt.cli(['rest','--method','get','--url','https://management.azure.com'+account+'/raiPolicies?api-version=2025-06-01'])
s.rt.require(not policies.get('nextLink'), 'rai_policy_pagination')
deployments=s.rt.cli(['rest','--method','get','--url','https://management.azure.com'+account+'/deployments?api-version=2025-06-01'])
s.rt.require(not deployments.get('nextLink'), 'deployment_pagination')
bindings={d['name']:d['properties'].get('raiPolicyName') for d in deployments['value']}
protected={'rai_policies_sha256':s.fs.sha(policies),'rai_bindings_sha256':s.fs.sha(bindings)}
roles=s.load(r.home/'baseline.json')['runtime']['roleAssignments']
definitions={}
for rid in sorted({a[2] for a in roles}):
    definitions[rid]=s.rt.cli(['rest','--method','get','--url','https://management.azure.com'+rid+'?api-version=2022-04-01'])
protected['role_definitions_sha256']=s.fs.sha(definitions)
for kind in ('vnet','nsg','private-endpoint','route-table'):
    value=s.rt.cli(['network',kind,'list','--subscription',s.rt.SUB,'--resource-group','IDS-TOKEN-EXCHANGE-POC'])
    protected[kind+'_sha256']=s.fs.sha(value)
protected['tool_sha256']=s.sha((s.rt.ROOT/'scripts/deployment/customer_login_protected_readback.ps1').read_bytes())
proof={'at':s.fs.stamp(),'phase':phase,'protected':protected,'rai_policy_count':len(policies['value']),
       'rai_binding_count':len(bindings),'role_definition_count':len(definitions),'configuration_writes':0}
if phase=='verify':
    prior=s.load(r.home/'supplemental-baseline.json')
    proof['passed']=prior['protected']==protected
    r.write('supplemental-verified.json',proof)
    s.rt.require(proof['passed'], 'supplemental_readback_failed_no_reapply')
else:
    r.write('supplemental-baseline.json',proof)
print(json.dumps(proof),flush=True)
'@
$code | & 'C:/Program Files/Python313/python.exe' -X utf8 -u - $Phase
exit $LASTEXITCODE