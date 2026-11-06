"""Fresh parameterized customer-only release; historical entrypoints are never run."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import argparse
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
from urllib.request import urlopen

from scripts.deployment import runtime_rollout as rt, portal_fix as portals
from scripts.deployment import finops_function_stage as fs, customer_catalog_validate as ui
from scripts.deployment.poc_activation_release import snapshot, resolve, parsed, any_unknown
from scripts.deployment.project_route_product_access import sha

UI = rt.HOME / 'admin-showback-native-20261028T121721699258Z'
UI_HASH = '91443fba5fe909624fde27f1b0e6a54783fe74a8536acf0698c02231604921c4'
ADDRESS = 'azurerm_linux_web_app.main["customer"]'
PINS = {'api': 'b489df53815f0d0242eda4c28b2c471bca2ce53344abc6733220c67c87bc0e09',
        'admin': '2846f1ff04244f20cb6612cca62c348b6a79a2fff7245dfc609347564becbfe5',
        'customer': 'd9d8b4b21283801feb2aff3ad12707155f5c38c59b6fc09091a4c22c35e71ea3',
        'ingestion': 'fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def account():
    ssl.create_default_context(cafile=rt.CA)
    rt.require(rt.ENV.get('AZURE_CLI_DISABLE_CONNECTION_VERIFICATION', '').lower() not in ('true', '1', 'yes'), 'strict_tls')
    a = rt.cli(['account', 'show'])
    rt.require(a['id'] == rt.SUB and a['tenantId'] == rt.TENANT and a['state'] == 'Enabled'
               and a['user']['name'].lower() == 'xv.puneet.devadiga@singtel.com', 'account_scope')


def retained(remote=False):
    m, p = load(UI / 'sources.json'), load(UI / 'completion.json')
    rt.require(m['source_sha256'] == p['source_sha256'] == UI_HASH and p['passed'] and p['run_id'] == 'cm2x'
               and p['no_push'] and p['tests_passed'] == 124 and p['test_files_passed'] == 16
               and p['source_count'] == len(m['entries']) == 74, 'retained_native_proof')
    paths = {f.relative_to(rt.ROOT).as_posix() for f in portals.source_files()} | {ui.DOCKERFILE}
    rt.require(paths == {e['path'] for e in m['entries']}, 'source_inventory')
    for e in m['entries']:
        path = Path(e['path'])
        rt.require(not path.is_absolute() and '..' not in path.parts, 'unsafe_path')
        for base in (rt.ROOT, UI / 'context'):
            f = base / path
            rt.require(not any(x.is_symlink() for x in (f, *f.parents)) and sha(f.read_bytes()) == e['sha256'], 'source_context_hash:' + e['path'])
            rt.require(not re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}', f.read_bytes()), 'source_secret')
    rt.require(sha((UI / 'result.json').read_bytes()) == p['original_result_sha256']
               and sha((UI / 'validation.log').read_bytes()) == p['validation_log_sha256'], 'retained_artifacts')
    if remote:
        run = rt.cli(['acr', 'task', 'show-run', '-r', portals.REGISTRY, '--run-id', 'cm2x', '--subscription', rt.SUB])
        rt.require(run['status'] == 'Succeeded' and run['finishTime'] == p['finish_time_utc']
                   and ui.no_published_images(run.get('outputImages')), 'remote_no_push_proof')
    return m


def tooling():
    paths = set((rt.ROOT / 'scripts/deployment').glob('*.py'))
    paths |= set((rt.ROOT / 'infra/terraform').glob('*.tf')) | set((rt.ROOT / 'infra/terraform').glob('*.tf.json'))
    paths |= {rt.ROOT / 'tests/unit/test_customer_login_release.py', rt.ROOT / 'infra/terraform/.terraform.lock.hcl',
              rt.ROOT / 'infra/terraform/backend.hcl', rt.HOME / 'rebuild-platform.tfvars.json', rt.HOME / 'jwt-runtime.tfvars.json'}
    return {str(p): sha(p.read_bytes()) for p in sorted(paths)}


def workers():
    # Native metadata only; no optional psutil dependency or process secrets.
    code = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|terraform)\\.exe$' } | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress"
    output = rt.run(['C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-Command', code]).strip()
    rows = json.loads(output) if output else []
    if isinstance(rows, dict):
        rows = [rows]
    return [p for p in rows if p['ProcessId'] != os.getpid()]


def guard(plan, image, before):
    rt.require(plan.get('applyable') is True and not plan.get('errored') and not plan.get('deferred_changes'), 'applyable_plan')
    rt.require(re.fullmatch(re.escape(portals.HOST + '/aiflux-customer@sha256:') + '[a-f0-9]{64}', image), 'immutable_customer_image')
    writes = []
    for item in plan.get('resource_changes', []):
        c = item['change']
        if c['actions'] == ['no-op'] or (c['actions'] == ['read'] and item.get('mode') == 'data'):
            continue
        rt.require(item['address'] == ADDRESS and item.get('mode') == 'managed' and c['actions'] == ['update'], 'customer_only_update')
        writes.append(item)
        old, new = deepcopy(c['before']), deepcopy(c['after'])
        unknown = c.get('after_unknown') or {}
        rt.require(not any(any_unknown(v) for k, v in unknown.items() if k not in fs.COMPUTED), 'unknown_writable')
        for k in fs.COMPUTED:
            if any_unknown(unknown.get(k)):
                new[k] = old.get(k)
        rt.require(len(old['site_config']) == len(new['site_config']) == 1, 'site_shape')
        a, b = old['site_config'][0]['application_stack'], new['site_config'][0]['application_stack']
        rt.require(len(a) == len(b) == 1 and 'DOCKER|' + portals.HOST + '/' + a[0]['docker_image_name']
                   == before['runtime']['sites']['customer']['image'] and b[0]['docker_image_name'] == image.split('/', 1)[1]
                   and b[0]['docker_registry_url'] == 'https://' + portals.HOST, 'exact_predecessor_target')
        b[0]['docker_image_name'] = a[0]['docker_image_name']
        rt.require(old == new and c['before'] != c['after'], 'nonimage_delta')
    rt.require(len(writes) == 1 and plan.get('checks') and all(c['status'] == 'pass' for c in plan['checks']), 'one_update_all_checks')


class Release:
    def __init__(self, name):
        rt.require(re.fullmatch(r'customer-login-20261028T[0-9]{6}Z', name), 'fresh_release_name')
        self.home = rt.HOME / name
        self.root = self.home / 'infra/terraform'
        self.planfile = self.home / 'customer-only.tfplan'
        self.full = self.home / 'validation-only-NEVER-APPLY.tfplan'

    def write(self, name, value):
        with (self.home / name).open('x', encoding='utf-8') as f:
            json.dump(value, f, indent=2)

    def status(self):
        markers = []
        for folder in rt.HOME.iterdir():
            if folder.is_dir() and any(s in folder.name for s in ('customer', 'showback', 'poc-')):
                for p in folder.rglob('*intent.json'):
                    markers.append({'path': p.relative_to(rt.ROOT).as_posix(), 'applied': (p.parent / 'applied.json').exists(),
                                    'verified': any((p.parent / n).exists() for n in ('verified.json', 'independently-verified.json'))})
        result = {'at': fs.stamp(), 'workers': workers(), 'fresh_release_exists': self.home.exists(), 'intents': markers}
        print(json.dumps(result), flush=True)
        rt.require(not result['workers'], 'active_worker_reconcile_no_replay')
        return result

    def prepare(self):
        status = self.status()
        rt.require(not self.home.exists(), 'existing_release_reconcile_only')
        account()
        m = retained(remote=True)
        before = snapshot()
        for k, pin in PINS.items():
            rt.require(before['runtime']['sites'][k]['image'] == 'DOCKER|' + portals.HOST + '/aiflux-' + k + '@sha256:' + pin, 'fresh_pin:' + k)
        fs.protect(self.home)
        self.write('worker-reconciliation.json', status)
        self.write('baseline.json', before)
        self.write('sources.json', m)
        self.write('tooling.json', tooling())
        prior = load(rt.HOME / 'customer-catalog-copy-20261028T042834246153Z/sources.json')
        old = {e['path']: e['sha256'] for e in prior['entries']}
        delta = [e['path'] for e in m['entries'] if old.get(e['path']) != e['sha256']]
        self.write('scope-review.json', {'at': fs.stamp(), 'changed_sources_vs_deployed_customer': delta,
                   'backend_packaged': False, 'api_admin_ingestion_unchanged': True,
                   'warnings': 'Existing npm audit 1 moderate, 1 high, 2 critical and Vite chunk warnings; no dependency changes or clean CVE claim.',
                   'disclosure': 'Current validated shared UI includes prior Showback/client edits; this is not asserted to be a CTA-only byte delta.'})
        diffs = []
        for name in delta:
            previous = rt.HOME / 'customer-catalog-copy-20261028T042834246153Z/context' / name
            diffs.extend(difflib.unified_diff(previous.read_text(encoding='utf-8').splitlines(keepends=True) if previous.exists() else [],
                         (rt.ROOT / name).read_text(encoding='utf-8').splitlines(keepends=True), fromfile='customer-predecessor/' + name, tofile='validated/' + name))
        (self.home / 'bundle-scope.diff').write_text(''.join(diffs), encoding='utf-8')
        self.write('release-intent.json', {'at': fs.stamp(), 'scope': ['customer'], 'max_builds': 1, 'max_applies': 1,
                   'source_sha256': UI_HASH, 'fragment_preserve_current_not_historical_defaults': True})
        print(json.dumps({'stage': 'prepared', 'baseline_sha256': fs.sha(before), 'source_sha256': UI_HASH}), flush=True)

    def sources(self):
        rt.require(load(self.home / 'sources.json') == retained() and load(self.home / 'tooling.json') == tooling(), 'bound_tooling_source_drift')

    def build(self):
        account()
        self.sources()
        rt.require(snapshot() == load(self.home / 'baseline.json'), 'prebuild_baseline')
        folder = self.home / 'context'
        for e in retained()['entries']:
            dest = folder / e['path']
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as f:
                f.write((rt.ROOT / e['path']).read_bytes())
        tag = self.home.name.lower() + '-' + UI_HASH[:12]
        args = ['acr', 'build', '--registry', portals.REGISTRY, '--subscription', rt.SUB, '--platform', 'linux/amd64',
                '--timeout', '1800', '--file', 'apps/customer-portal/Dockerfile', '--image', 'aiflux-customer:' + tag,
                '--build-arg', 'VITE_AUTH_MODE=local', '--build-arg', 'VITE_CONTROL_API_URL=/api', '--build-arg',
                'VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1', '.']
        self.write('build-intent.json', {'at': fs.stamp(), 'tag': tag, 'source_sha256': UI_HASH, 'args': args})
        p = subprocess.run(rt.CLI + args, cwd=folder, env=rt.ENV, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=2100)
        text = ui.redact(p.stdout + p.stderr)
        (self.home / 'customer-build.log').write_text(text, encoding='utf-8')
        ids = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
        rt.require(p.returncode == 0 and ids, 'build_failed_reconcile_never_replay')
        run = rt.cli(['acr', 'task', 'show-run', '-r', portals.REGISTRY, '--run-id', ids[-1], '--subscription', rt.SUB])
        outputs = run.get('outputImages')
        rt.require(run['status'] == 'Succeeded' and len(outputs or []) == 1, 'exact_build_output')
        digest = outputs[0]['digest']
        rt.require(outputs == [{'digest': digest, 'registry': portals.HOST, 'repository': 'aiflux-customer', 'tag': tag}]
                   and 'syntax is ok' in text and 'test is successful' in text, 'production_nginx_proof')
        self.sources()
        self.write('build.json', {'at': fs.stamp(), 'run_id': ids[-1], 'finish_time': run['finishTime'], 'tag': tag,
                   'digest': digest, 'image': portals.HOST + '/aiflux-customer@' + digest, 'source_sha256': UI_HASH,
                   'log_sha256': sha((self.home / 'customer-build.log').read_bytes())})
        print(json.dumps(load(self.home / 'build.json')), flush=True)

    def built(self, remote=True):
        self.sources()
        b = load(self.home / 'build.json')
        rt.require(b['source_sha256'] == UI_HASH and b['image'] == portals.HOST + '/aiflux-customer@' + b['digest']
                   and re.fullmatch(r'sha256:[a-f0-9]{64}', b['digest'])
                   and b['log_sha256'] == sha((self.home / 'customer-build.log').read_bytes()), 'build_binding')
        if remote:
            run = rt.cli(['acr', 'task', 'show-run', '-r', portals.REGISTRY, '--run-id', b['run_id'], '--subscription', rt.SUB])
            meta = rt.cli(['acr', 'manifest', 'show-metadata', '--registry', portals.REGISTRY, '--name', 'aiflux-customer:' + b['tag'], '--subscription', rt.SUB])
            rt.require(run['status'] == 'Succeeded' and run['finishTime'] == b['finish_time'] and meta['digest'] == b['digest']
                       and run['outputImages'] == [{'digest': b['digest'], 'registry': portals.HOST, 'repository': 'aiflux-customer', 'tag': b['tag']}], 'remote_image_binding')
        return b

    def data(self):
        target = parsed(self.root, self.planfile)
        return resolve(target, parsed(self.root, self.full), {ADDRESS}) if self.full.exists() else target

    def plan(self):
        account()
        image = self.built()['image']
        before = snapshot()
        rt.require(before == load(self.home / 'baseline.json') and not self.root.exists(), 'fresh_plan_baseline')
        self.root.mkdir(parents=True)
        for p in (rt.ROOT / 'infra/terraform').iterdir():
            if p.is_file() and (p.name.endswith(('.tf', '.tf.json')) or p.name == '.terraform.lock.hcl'):
                shutil.copyfile(p, self.root / p.name)
        for path in ('infra/models', 'gateway/catalog', 'gateway/policies'):
            shutil.copytree(rt.ROOT / path, self.home / path, ignore=shutil.ignore_patterns('.terraform', '*.tfstate*', '*.tfplan', '__pycache__'))
        for p in (rt.ROOT / 'gateway').glob('*.json'):
            shutil.copyfile(p, self.home / 'gateway' / p.name)
        variables = portals.runtime_variables({'portals': ['customer'], 'results': {'customer': {'image': image}}}, before['runtime'])
        variables.update(ingestion_container_image=before['runtime']['sites']['ingestion']['image'].removeprefix('DOCKER|'),
                         ingestion_enabled=True, ingestion_timer_enabled=True, ingestion_start_at=before['cutoff'], ingestion_catalog_accepted=True)
        rt.save(self.home / 'inputs.tfvars.json', variables)
        settings = fs.current_settings()
        rt.require({k: fs.sha(v) for k, v in settings.items()} == before['settings_hashes'], 'all_settings_preserved')
        rt.save(self.root / 'login_preserved.tf.json', {'locals': {'login_settings': fs.literal(fs.preserved_web_settings(settings))}})
        rt.save(self.root / 'zzzz_login_override.tf.json', {'resource': {'azurerm_linux_web_app': {'main': {'app_settings': '${local.login_settings[each.key]}'}}}})
        args = ['-var-file=' + str(p) for p in (rt.HOME / 'rebuild-platform.tfvars.json', self.home / 'inputs.tfvars.json', rt.HOME / 'jwt-runtime.tfvars.json')]
        fs.terraform(self.root, 'init', '-input=false', '-lockfile=readonly', '-no-color', '-backend-config=' + str(rt.ROOT / 'infra/terraform/backend.hcl'))
        fs.terraform(self.root, 'validate', '-no-color')
        rt.require(fs.terraform(self.root, 'workspace', 'show').strip() == 'default', 'workspace')
        self.write('plan-intent.json', {'at': fs.stamp(), 'target': ADDRESS, 'max_applies': 1})
        fs.terraform(self.root, 'plan', '-input=false', '-no-color', '-lock-timeout=60s', *args, '-target=' + ADDRESS, '-out=' + str(self.planfile))
        if any(c['status'] != 'pass' for c in parsed(self.root, self.planfile).get('checks', [])):
            self.write('companion-intent.json', {'at': fs.stamp(), 'never_apply': True, 'target_sha256': sha(self.planfile.read_bytes())})
            fs.terraform(self.root, 'plan', '-input=false', '-no-color', '-lock-timeout=60s', *args, '-out=' + str(self.full))
        guard(self.data(), image, before)
        artifacts = [self.planfile, self.home / 'inputs.tfvars.json', *self.root.glob('*.tf'), *self.root.glob('*.tf.json'), self.root / '.terraform.lock.hcl']
        if self.full.exists():
            artifacts.append(self.full)
        self.write('review.json', {'at': fs.stamp(), 'plan_sha256': sha(self.planfile.read_bytes()), 'image': image,
                   'source_sha256': UI_HASH, 'tooling': tooling(), 'baseline': before,
                   'artifacts': {str(p): sha(p.read_bytes()) for p in artifacts}, 'companion_never_apply': True,
                   'companion_unapproved_writes': [{'address': c['address'], 'actions': c['change']['actions']}
                       for c in (parsed(self.root, self.full).get('resource_changes', []) if self.full.exists() else [])
                       if c['change']['actions'] not in (['no-op'], ['read']) and c['address'] != ADDRESS]})
        print(json.dumps({'stage': 'guarded_not_validated', 'plan_sha256': sha(self.planfile.read_bytes()), 'image': image}), flush=True)

    def check(self, live=True):
        v = load(self.home / 'review.json')
        rt.require(v['tooling'] == tooling() and all(sha(Path(p).read_bytes()) == h for p, h in v['artifacts'].items())
                   and v['plan_sha256'] == sha(self.planfile.read_bytes()) and v['source_sha256'] == UI_HASH
                   and v['image'] == self.built(remote=live)['image'], 'exact_plan_input_binding')
        guard(self.data(), v['image'], v['baseline'])
        if live:
            account()
            rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(v['at']) < timedelta(hours=2), 'stale_plan')
            rt.require(snapshot() == v['baseline'], 'complete_baseline_drift')
        return v

    def apply(self):
        rt.require(not (self.home / 'apply-intent.json').exists(), 'attempted_apply_reconcile_never_retry')
        v = self.check()
        p = load(self.home / 'validation.json')
        doc = (rt.ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
        rt.require(p['checks_passed'] and p['plan_sha256'] == v['plan_sha256'] and p['tooling'] == tooling()
                   and p['process_id'] != os.getpid() and p['at'] in doc and v['plan_sha256'] in doc
                   and 'Customer login release status: Validated.' in doc
                   and load(rt.ROOT / '.azure/validate-status.json')['completedStep'] == 'UpdateStatus', 'independent_section7_workflow_required')
        self.write('apply-intent.json', {'at': fs.stamp(), 'plan_sha256': v['plan_sha256']})
        output = fs.terraform(self.root, 'apply', '-input=false', '-no-color', '-parallelism=1', str(self.planfile))
        self.write('applied.json', {'at': fs.stamp(), 'plan_sha256': v['plan_sha256'], 'summary': re.findall(r'Apply complete! Resources: [^\r\n]+', output)})
        print(json.dumps(load(self.home / 'applied.json')), flush=True)

    def verify(self):
        v = self.check(live=False)
        rt.require(load(self.home / 'applied.json')['plan_sha256'] == v['plan_sha256'], 'matching_apply')
        current, expected = snapshot(), deepcopy(v['baseline'])
        expected['runtime']['sites']['customer']['image'] = 'DOCKER|' + v['image']
        proof = {'at': fs.stamp(), 'process_id': os.getpid(), 'plan_sha256': v['plan_sha256'], 'image': v['image'],
                 'passed': current == expected, 'baseline': current, 'all_four_settings_hashes_equal': current['settings_hashes'] == expected['settings_hashes']}
        self.write('verified.json', proof)
        rt.require(proof['passed'], 'readback_failed_never_reapply')
        base = 'https://poc-ids-token-ex-customer.azurewebsites.net'
        def get(path):
            with urlopen(base + path, context=ssl.create_default_context(cafile=rt.CA), timeout=90) as response:
                rt.require(response.status == 200, 'http_200_required')
                return response.read()
        get('/healthz')
        html = get('/').decode('utf-8')
        bundles = re.findall(r'<script[^>]+src="(/assets/[^"?]+\.js)"', html)
        rt.require(len(bundles) == 1, 'exact_bundle')
        data = get(bundles[0])
        http = {'at': fs.stamp(), 'http_status': 200, 'health_status': 200, 'bundle': bundles[0], 'bundle_sha256': sha(data),
                'login_present': b'Sign in' in data and b'/auth/login' in data,
                'cta_absent': b'Create a new OpCo account' not in data, 'backend_register_unchanged': True,
                'browser_acceptance': 'parent isolated signed-out verification pending; no shared browser changed'}
        self.write('http.json', http)
        rt.require(http['login_present'] and http['cta_absent'], 'bundle_acceptance_failed_no_reapply')
        print(json.dumps({k: v for k, v in proof.items() if k != 'baseline'} | {'http': http}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'prepare', 'build', 'plan', 'apply', 'verify'))
    parser.add_argument('--release', required=True)
    args = parser.parse_args()
    getattr(Release(args.release), args.action)()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error) if isinstance(error, RuntimeError) else 'sensitive_detail_suppressed'}), flush=True)
        raise SystemExit(1)