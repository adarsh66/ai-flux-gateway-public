"""Exclusive customer-only release; never invokes historical build/plan/apply."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import difflib
import json
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
from urllib.request import urlopen

from scripts.deployment import customer_catalog_validate as native
from scripts.deployment import portal_fix as portals
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.poc_fragment_bootstrap import Bootstrap, ID, FRAGMENT, DEFAULTS
from scripts.deployment.poc_fragment_readback import compare
from scripts.deployment.project_route_product_access import sha

HOME = rt.HOME / 'customer-catalog-release-20261028'
ROOT = HOME / 'infra/terraform'
PLAN = HOME / 'customer-only.tfplan'
VALIDATED = rt.HOME / 'customer-catalog-copy-20261028T042834246153Z'
PREDECESSOR = portals.HOME / 'local-20261027t113934z-7296b4dd49fc'
ADDRESS = 'azurerm_linux_web_app.main["customer"]'
PINS = {
    'api': 'dd8b048b8a189061d870ca9011c3d8e0152ff63712ee6d61fe3f2a37af3b0a33',
    'ingestion': 'fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90',
    'admin': '8950baf1fa8c5e8b0762c3b1069251706fe043dbca9c060b31c77092ba9f6ca0',
    'customer': '072fe85e23168d20081894357ac87aa036e14363eb031e796e68686f4d357594',
}


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def exclusive(name, value):
    with (HOME / name).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)


def account():
    ssl.create_default_context(cafile=rt.CA)
    rt.require(rt.ENV.get('AZURE_CLI_DISABLE_CONNECTION_VERIFICATION', '').lower()
               not in ('1', 'true', 'yes'), 'tls_verification_required')
    a = rt.cli(['account', 'show'])
    rt.require(a['id'] == rt.SUB and a['tenantId'] == rt.TENANT and a['state'] == 'Enabled'
               and a['user']['name'].lower() == 'xv.puneet.devadiga@singtel.com', 'account_scope')


def validated_sources(remote=False):
    m, proof = load(VALIDATED / 'sources.json'), load(VALIDATED / 'verification.json')
    entries = m['entries']
    rt.require(m['source_sha256'] == proof['source_sha256'] == sha(json.dumps(entries, sort_keys=True))
               and proof['passed'] and proof['run_id'] == 'cm2f' and proof['no_published_images_verified']
               and proof['tests_passed'] == 116 and proof['test_files_passed'] == 15, 'native_proof_required')
    expected = {p.relative_to(rt.ROOT).as_posix() for p in portals.source_files()} | {native.DOCKERFILE}
    rt.require(expected == {e['path'] for e in entries}, 'source_inventory_drift')
    for e in entries:
        path = Path(e['path'])
        rt.require(not path.is_absolute() and '..' not in path.parts, 'source_path')
        rt.require(all(sha((base / path).read_bytes()) == e['sha256']
                       for base in (rt.ROOT, VALIDATED / 'context')), 'validated_source_changed:' + e['path'])
    # The existing validator hashes decoded universal-newline text, not Windows
    # CRLF bytes. Match that original contract without rewriting the evidence.
    rt.require(sha((VALIDATED / 'validation.log').read_text(encoding='utf-8')) == proof['validation_log_sha256'], 'native_log_changed')
    if remote:
        run = rt.cli(['acr', 'task', 'show-run', '-r', portals.REGISTRY, '--run-id', 'cm2f', '--subscription', rt.SUB])
        rt.require(run['status'] == 'Succeeded' and run['finishTime'] == proof['finishTime']
                   and native.no_published_images(run.get('outputImages')), 'native_remote_changed')
    return m


def baseline():
    run = Bootstrap()
    result = run.protected_complete()
    fragment = run.exact()
    raw = run.arm('/policyFragments/' + FRAGMENT + '?format=rawxml')
    rt.require(fragment and fragment['id'].lower() == ID.lower()
               and raw['id'].lower() == ID.lower() and compare(DEFAULTS.read_text(),
               raw['properties']['value'], fragment['properties']['value'])['semantic_equal'], 'existing_fragment_required')
    result['existing_fragment_sha256'] = fs.sha(fragment)
    return result


def require_pins(value):
    for kind, pin in PINS.items():
        rt.require(value['runtime']['sites'][kind]['image'] == 'DOCKER|' + portals.HOST
                   + '/aiflux-' + kind + '@sha256:' + pin, 'predecessor_changed_reconcile:' + kind)


def tools():
    paths = [Path(__file__), rt.ROOT / 'scripts/deployment/customer_catalog_release_validation.py',
             rt.ROOT / 'tests/unit/test_customer_catalog_release.py',
             *[rt.ROOT / ('scripts/deployment/' + n + '.py') for n in
               ('portal_fix', 'runtime_rollout', 'finops_function_stage', 'poc_fragment_bootstrap',
                'poc_fragment_readback', 'project_route_product_access', 'customer_catalog_validate', 'deploy_portals')],
             rt.ROOT / 'tests/unit/test_portal_fix.py',
             * (rt.ROOT / 'infra/terraform').glob('*.tf'),
             * (rt.ROOT / 'infra/terraform').glob('*.tf.json'),
             rt.ROOT / 'infra/terraform/.terraform.lock.hcl', rt.ROOT / 'infra/terraform/backend.hcl',
             rt.HOME / 'rebuild-platform.tfvars.json', rt.HOME / 'jwt-runtime.tfvars.json']
    return {p.relative_to(rt.ROOT).as_posix(): sha(p.read_bytes()) for p in paths}


def preflight():
    account()
    m = validated_sources(remote=True)
    rt.require(not HOME.exists(), 'release_exists_reconcile_do_not_replay')
    before = baseline()
    require_pins(before)
    registry = rt.cli(['acr', 'show', '-n', portals.REGISTRY, '--subscription', rt.SUB])
    rt.require(registry['id'].lower() == (rt.RG + '/providers/Microsoft.ContainerRegistry/registries/'
               + portals.REGISTRY).lower() and registry['loginServer'] == portals.HOST
               and registry['adminUserEnabled'] is False, 'registry_security')
    old = {e['path']: e['sha256'] for e in load(PREDECESSOR / 'source-manifest.json')['entries']}
    rt.require(load(PREDECESSOR / 'approved-images.json')['pins']['customer'] == 'sha256:' + PINS['customer'], 'predecessor_provenance')
    delta = [e['path'] for e in m['entries'] if old.get(e['path']) != e['sha256']]
    rt.require(all(n.startswith('packages/ui/') or n == native.DOCKERFILE for n in delta), 'unexpected_bundle_delta')
    fs.protect(HOME)
    exclusive('release-intent.json', {'at': fs.stamp(), 'scope': ['customer'], 'max_builds': 1,
              'max_applies': 1, 'source_sha256': m['source_sha256'], 'predecessor': PINS['customer']})
    rt.save(HOME / 'preflight-baseline.json', before)
    rt.save(HOME / 'sources.json', m)
    rt.save(HOME / 'tooling.json', tools())
    diffs = []
    for name in delta:
        current = (rt.ROOT / name).read_text(encoding='utf-8').splitlines(keepends=True)
        previous = PREDECESSOR / 'context' / name
        diffs.extend(difflib.unified_diff(previous.read_text(encoding='utf-8').splitlines(keepends=True)
                     if previous.exists() else [], current, fromfile='live-predecessor/' + name, tofile='validated/' + name))
    (HOME / 'bundle-scope.diff').write_text(''.join(diffs), encoding='utf-8')
    rt.save(HOME / 'scope-review.json', {'at': fs.stamp(), 'changed_or_added_sources': delta,
        'lockfile_unchanged_vs_live': old['package-lock.json'] == next(e['sha256'] for e in m['entries'] if e['path'] == 'package-lock.json'),
        'warnings': 'Existing npm audit 1 moderate, 1 high, 2 critical; not a clean vulnerability scan. No severity gate in reviewed POC policy/pipeline.',
        'customer_routes_unchanged': True, 'admin_controls_not_customer_routes': True,
        'optional_controls_off_verified': True, 'fragment_preserved': True})
    print(json.dumps({'preflight': 'passed', 'source_sha256': m['source_sha256'], 'bundle_delta': delta,
                      'baseline_sha256': fs.sha(before), 'cloud_writes': 0}), flush=True)


def source_check():
    rt.require(load(HOME / 'sources.json') == validated_sources() and load(HOME / 'tooling.json') == tools(), 'source_or_tooling_drift')


def build():
    account()
    source_check()
    rt.require(not (HOME / 'build-intent.json').exists(), 'build_attempted_never_replay')
    before = baseline()
    rt.require(before == load(HOME / 'preflight-baseline.json'), 'prebuild_baseline_drift')
    context = HOME / 'context'
    for e in load(HOME / 'sources.json')['entries']:
        p = rt.ROOT / e['path']
        rt.require(not p.is_symlink(), 'source_symlink')
        target = context / e['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    tag = 'customer-copy-' + datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')
    args = ['acr', 'build', '--registry', portals.REGISTRY, '--subscription', rt.SUB,
            '--platform', 'linux/amd64', '--timeout', '1800', '--file', 'apps/customer-portal/Dockerfile',
            '--image', 'aiflux-customer:' + tag, '--build-arg', 'VITE_AUTH_MODE=local',
            '--build-arg', 'VITE_CONTROL_API_URL=/api', '--build-arg',
            'VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1', '.']
    exclusive('build-intent.json', {'at': fs.stamp(), 'args': args, 'tag': tag, 'source_sha256': load(HOME / 'sources.json')['source_sha256']})
    p = subprocess.run(rt.CLI + args, cwd=context, env=rt.ENV, capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=2100)
    text = native.redact(p.stdout + p.stderr)
    (HOME / 'customer-build.log').write_text(text, encoding='utf-8')
    ids = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
    rt.require(p.returncode == 0 and ids, 'customer_build_failed_reconcile_no_replay')
    run = rt.cli(['acr', 'task', 'show-run', '-r', portals.REGISTRY, '--run-id', ids[-1], '--subscription', rt.SUB])
    meta = rt.cli(['acr', 'repository', 'show', '-n', portals.REGISTRY, '--image', 'aiflux-customer:' + tag, '--subscription', rt.SUB])
    rt.require(run['status'] == 'Succeeded' and re.fullmatch(r'sha256:[a-f0-9]{64}', meta['digest'])
               and run['outputImages'] == [{'digest': meta['digest'], 'registry': portals.HOST, 'repository': 'aiflux-customer', 'tag': tag}], 'exact_customer_build_output')
    rt.require('syntax is ok' in text and 'test is successful' in text, 'nginx_validation_required')
    source_check()
    result = {'at': fs.stamp(), 'tag': tag, 'run_id': ids[-1], 'finish_time': run['finishTime'],
              'digest': meta['digest'], 'image': portals.HOST + '/aiflux-customer@' + meta['digest'],
              'source_sha256': load(HOME / 'sources.json')['source_sha256'], 'log_sha256': sha((HOME / 'customer-build.log').read_bytes())}
    rt.save(HOME / 'build.json', result)
    print(json.dumps(result), flush=True)


def built(remote=True):
    source_check()
    result = load(HOME / 'build.json')
    rt.require(re.fullmatch(re.escape(portals.HOST) + r'/aiflux-customer@sha256:[a-f0-9]{64}', result['image'])
               and result['image'].endswith('@' + result['digest']) and result['source_sha256'] == load(HOME / 'sources.json')['source_sha256']
               and result['log_sha256'] == sha((HOME / 'customer-build.log').read_bytes()), 'build_binding')
    if remote:
        run = rt.cli(['acr', 'task', 'show-run', '-r', portals.REGISTRY, '--run-id', result['run_id'], '--subscription', rt.SUB])
        meta = rt.cli(['acr', 'repository', 'show', '-n', portals.REGISTRY, '--image', 'aiflux-customer:' + result['tag'], '--subscription', rt.SUB])
        rt.require(run['status'] == 'Succeeded' and run['finishTime'] == result['finish_time']
                   and meta['digest'] == result['digest'], 'remote_build_drift')
    return result


def guard(plan, image):
    rt.require(plan.get('applyable') is True and not plan.get('errored') and not plan.get('deferred_changes'), 'resolved_plan_required')
    rt.require(re.fullmatch(re.escape(portals.HOST) + r'/aiflux-customer@sha256:[a-f0-9]{64}', image), 'immutable_customer_image')
    portals.guard(plan, {'portals': ['customer'], 'results': {'customer': {'image': image}}})
    item = next(r for r in plan['resource_changes'] if r['address'] == ADDRESS)
    rt.require(item['change']['before']['site_config'][0]['application_stack'][0]['docker_image_name']
               == 'aiflux-customer@sha256:' + PINS['customer'], 'saved_predecessor_mismatch')
    rt.require(all(c.get('status') == 'pass' for c in plan.get('checks', [])), 'all_plan_preconditions_must_pass')


def plan():
    account()
    image = built()['image']
    rt.require(not (HOME / 'plan-intent.json').exists() and not (HOME / 'apply-intent.json').exists(), 'never_replan_or_replay')
    before = baseline()
    rt.require(before == load(HOME / 'preflight-baseline.json'), 'preplan_baseline_drift')
    settings = fs.current_settings()
    ROOT.mkdir(parents=True, exist_ok=False)
    for p in (rt.ROOT / 'infra/terraform').iterdir():
        if p.is_file() and (p.name.endswith(('.tf', '.tf.json')) or p.name == '.terraform.lock.hcl'):
            shutil.copyfile(p, ROOT / p.name)
    for name in ('infra/models', 'gateway/catalog', 'gateway/policies'):
        shutil.copytree(rt.ROOT / name, HOME / name, ignore=shutil.ignore_patterns('.terraform', '*.tfstate*', '*.tfplan', '__pycache__'))
    for p in (rt.ROOT / 'gateway').glob('*.json'):
        shutil.copyfile(p, HOME / 'gateway' / p.name)
    runtime = before['runtime']
    variables = portals.runtime_variables({'portals': ['customer'], 'results': {'customer': {'image': image}}}, runtime)
    variables.update(ingestion_container_image=runtime['sites']['ingestion']['image'].removeprefix('DOCKER|'),
                     ingestion_enabled=True, ingestion_timer_enabled=True,
                     ingestion_start_at=before['cutoff'], ingestion_catalog_accepted=True)
    rt.save(HOME / 'runtime.tfvars.json', variables)
    rt.save(ROOT / 'customer_preserved.tf.json', {'locals': {'customer_release_settings': fs.literal(fs.preserved_web_settings(settings))}})
    rt.save(ROOT / 'zzzz_customer_override.tf.json', {'resource': {'azurerm_linux_web_app': {'main': {
        'app_settings': '${local.customer_release_settings[each.key]}'}}}})
    fs.terraform(ROOT, 'init', '-input=false', '-lockfile=readonly', '-no-color', '-backend-config=' + str(rt.ROOT / 'infra/terraform/backend.hcl'))
    fs.terraform(ROOT, 'validate', '-no-color')
    rt.require(fs.terraform(ROOT, 'workspace', 'show').strip() == 'default', 'workspace')
    exclusive('plan-intent.json', {'at': fs.stamp(), 'target': ADDRESS, 'apply_only': str(PLAN)})
    fs.terraform(ROOT, 'plan', '-input=false', '-no-color', '-lock-timeout=60s',
        '-var-file=' + str(rt.HOME / 'rebuild-platform.tfvars.json'), '-var-file=' + str(HOME / 'runtime.tfvars.json'),
        '-var-file=' + str(rt.HOME / 'jwt-runtime.tfvars.json'), '-target=' + ADDRESS, '-out=' + str(PLAN))
    parsed = json.loads(fs.terraform(ROOT, 'show', '-json', str(PLAN)))
    guard(parsed, image)
    artifacts = [*ROOT.glob('*.tf'), *ROOT.glob('*.tf.json'), ROOT / '.terraform.lock.hcl', HOME / 'runtime.tfvars.json']
    review = {'at': fs.stamp(), 'plan_sha256': sha(PLAN.read_bytes()), 'image': image,
              'source_sha256': load(HOME / 'sources.json')['source_sha256'], 'tooling': tools(), 'baseline': before,
              'artifacts': {p.relative_to(HOME).as_posix(): sha(p.read_bytes()) for p in artifacts},
              'guard': 'exact_one_customer_image_only'}
    rt.save(HOME / 'review.json', review)
    print(json.dumps({k: review[k] for k in ('at', 'plan_sha256', 'image', 'guard')}), flush=True)


def check(live=True):
    review = load(HOME / 'review.json')
    rt.require(review['tooling'] == tools() and review['plan_sha256'] == sha(PLAN.read_bytes()), 'review_drift')
    rt.require(all(sha((HOME / p).read_bytes()) == h for p, h in review['artifacts'].items()), 'archived_input_drift')
    rt.require(built(remote=live)['image'] == review['image'], 'image_drift')
    guard(json.loads(fs.terraform(ROOT, 'show', '-json', str(PLAN))), review['image'])
    if live:
        account()
        rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review['at']) < timedelta(hours=2), 'plan_expired')
        rt.require(baseline() == review['baseline'], 'full_live_baseline_drift')
    return review


def apply():
    rt.require(not (HOME / 'apply-intent.json').exists(), 'apply_attempted_never_replay')
    review = check()
    proof = load(HOME / 'validation.json')
    status = load(rt.ROOT / '.azure/validate-status.json')
    doc = (rt.ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
    rt.require(proof['checks_passed'] is True and proof['plan_sha256'] == review['plan_sha256']
               and proof['tooling'] == tools() and status['completedStep'] == 'UpdateStatus'
               and 'Customer catalog release status: Validated.' in doc and proof['at'] in doc
               and review['plan_sha256'] in doc, 'independent_exact_validation_required')
    exclusive('apply-intent.json', {'at': fs.stamp(), 'plan_sha256': review['plan_sha256']})
    output = fs.terraform(ROOT, 'apply', '-input=false', '-no-color', str(PLAN))
    rt.save(HOME / 'applied.json', {'at': fs.stamp(), 'plan_sha256': review['plan_sha256'],
            'summary': re.findall(r'Apply complete! Resources: [^\r\n]+', output)})
    print(json.dumps(load(HOME / 'applied.json')), flush=True)


def verify():
    review = check(live=False)
    rt.require(load(HOME / 'applied.json')['plan_sha256'] == review['plan_sha256'], 'matching_apply_required')
    expected = deepcopy(review['baseline'])
    expected['runtime']['sites']['customer']['image'] = 'DOCKER|' + review['image']
    current = baseline()
    proof = {'at': fs.stamp(), 'plan_sha256': review['plan_sha256'], 'image': review['image'],
             'protected_equal_except_customer_image': current == expected,
             'all_four_settings_hashes_equal': current['settings_hashes'] == expected['settings_hashes'],
             'existing_fragment_unchanged': current['existing_fragment_sha256'] == expected['existing_fragment_sha256'],
             'unchanged_images': {k: current['runtime']['sites'][k]['image'] for k in ('api', 'admin', 'ingestion')},
             'http': [], 'inference_requests': 0, 'cloud_configuration_writes': 'one customer image update only'}
    for path in ('/healthz', '/models'):
        with urlopen('https://poc-ids-token-ex-customer.azurewebsites.net' + path,
                     context=ssl.create_default_context(cafile=rt.CA), timeout=90) as response:
            proof['http'].append({'path': path, 'status': response.status})
    rt.save(HOME / 'independently-verified.json', proof)
    print(json.dumps(proof), flush=True)
    rt.require(current == expected and all(p['status'] == 200 for p in proof['http']), 'live_readback_failed_no_reapply')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'build', 'plan', 'check', 'apply', 'verify'))
    action = parser.parse_args().action
    if action == 'check':
        print(json.dumps({'checked': check()['plan_sha256']}), flush=True)
    else:
        globals()[action]()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'customer_release_failed_sensitive_detail_suppressed'}), flush=True)
        sys.exit(1)