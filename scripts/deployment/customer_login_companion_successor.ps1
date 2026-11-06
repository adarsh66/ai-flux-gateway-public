$env:PYTHONPATH='C:/LocalWorkspace/ai-flux-gateway-public;C:/LocalWorkspace/ai-flux-gateway-public/services/control-plane/src;C:/LocalWorkspace/ai-flux-gateway-public/.venv/Lib/site-packages'
$code=@'
import json, shutil
from pathlib import Path
from scripts.deployment import customer_login_release as s
old=s.Release('customer-login-20261028T124500Z')
new=s.Release('customer-login-20261028T125500Z')
s.rt.require(not s.workers() and not new.home.exists() and not (old.home/'apply-intent.json').exists(), 'fresh_exclusive_successor_required')
s.account()
old.sources()
image=old.built()['image']
before=s.snapshot()
s.rt.require(before==s.load(old.home/'baseline.json'), 'complete_baseline_before_successor')
target=s.parsed(old.root,old.planfile)
failed=s.parsed(old.root,old.full)
intent=s.load(old.home/'companion-intent.json')
s.rt.require(s.sha(old.planfile.read_bytes())==intent['target_sha256'], 'original_target_changed')
s.rt.require(target.get('applyable') and not target.get('errored') and failed.get('errored'), 'original_target_and_failed_companion_classification')
s.fs.protect(new.home)
new.write('successor-intent.json',{'at':s.fs.stamp(),'predecessor':str(old.home),'target_sha256':s.sha(old.planfile.read_bytes()),
    'failed_companion_sha256':s.sha(old.full.read_bytes()),'rebuilds':0,'target_replans':0,'applies':0,
    'original_artifacts_preserved':True,'companion_parallelism':1,
    'tool_sha256':s.sha((s.rt.ROOT/'scripts/deployment/customer_login_companion_successor.ps1').read_bytes())})
for name in ('baseline.json','sources.json','tooling.json','build.json','customer-build.log','scope-review.json','bundle-scope.diff','inputs.tfvars.json','supplemental-baseline.json'):
    shutil.copyfile(old.home/name,new.home/name)
new.root.mkdir(parents=True)
for p in old.root.iterdir():
    if p.is_file() and (p.name.endswith(('.tf','.tf.json')) or p.name=='.terraform.lock.hcl'):
        shutil.copyfile(p,new.root/p.name)
for path in ('infra/models','gateway/catalog','gateway/policies'):
    shutil.copytree(old.home/path,new.home/path,ignore=shutil.ignore_patterns('.terraform','*.tfstate*','*.tfplan','__pycache__'))
for p in (old.home/'gateway').glob('*.json'):
    shutil.copyfile(p,new.home/'gateway'/p.name)
shutil.copyfile(old.planfile,new.planfile)
s.fs.terraform(new.root,'init','-input=false','-lockfile=readonly','-no-color','-backend-config='+str(s.rt.ROOT/'infra/terraform/backend.hcl'))
s.rt.require(s.fs.terraform(new.root,'workspace','show').strip()=='default','workspace')
s.fs.terraform(new.root,'validate','-no-color')
new.write('companion-intent.json',{'at':s.fs.stamp(),'never_apply':True,'target_sha256':s.sha(new.planfile.read_bytes()),'original_target_not_replanned':True})
args=['-var-file='+str(p) for p in (s.rt.HOME/'rebuild-platform.tfvars.json',new.home/'inputs.tfvars.json',s.rt.HOME/'jwt-runtime.tfvars.json')]
s.fs.terraform(new.root,'plan','-input=false','-no-color','-lock-timeout=60s','-parallelism=1',*args,'-out='+str(new.full))
s.guard(new.data(),image,before)
artifacts=[new.planfile,new.full,new.home/'inputs.tfvars.json',*new.root.glob('*.tf'),*new.root.glob('*.tf.json'),new.root/'.terraform.lock.hcl']
review={'at':s.fs.stamp(),'plan_sha256':s.sha(new.planfile.read_bytes()),'image':image,'source_sha256':s.UI_HASH,
    'tooling':s.tooling(),'baseline':before,'artifacts':{str(p):s.sha(p.read_bytes()) for p in artifacts},'companion_never_apply':True,
    'original_target_byte_identical':new.planfile.read_bytes()==old.planfile.read_bytes(),
    'companion_unapproved_writes':[{'address':c['address'],'actions':c['change']['actions']} for c in s.parsed(new.root,new.full).get('resource_changes',[])
        if c['change']['actions'] not in (['no-op'],['read']) and c['address']!=s.ADDRESS]}
new.write('review.json',review)
print(json.dumps({k:v for k,v in review.items() if k not in ('tooling','baseline','artifacts')}),flush=True)
'@
$code | & 'C:/Program Files/Python313/python.exe' -X utf8 -u -
exit $LASTEXITCODE