"""One-shot API+ingestion image release; never applies the gateway or resets usage."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from xml.etree import ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import finops_release as manifest_builder
from scripts.deployment import portal_fix as portals
from scripts.deployment.project_route_product_access import ProductRun, sha

HOME = rt.HOME / 'fireworks-live-20261028'
ROOT = HOME / 'infra/terraform'
PLAN = HOME / 'runtime.tfplan'
KINDS = ('api', 'ingestion')
ADDRESSES = {'azurerm_linux_web_app.main["api"]': 'api', fs.FUNCTION: 'ingestion'}
TESTS = HOME / 'release-tests.xml'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sources():
    groups = manifest_builder.source_manifest()['components']
    paths = {rt.ROOT / e['path'] for kind in KINDS for e in groups[kind]['entries']}
    paths |= set((rt.ROOT / 'infra/terraform').glob('*.tf'))
    paths |= set((rt.ROOT / 'infra/terraform').glob('*.tf.json'))
    paths |= {rt.ROOT / 'infra/terraform/.terraform.lock.hcl', Path(__file__),
              rt.ROOT / 'scripts/deployment/fireworks_runtime_validation.py',
              rt.ROOT / 'scripts/deployment/fireworks_runtime_preserved.py',
              rt.ROOT / 'scripts/deployment/fireworks_acceptance.py'}
    paths |= set((rt.ROOT / 'tests/unit').glob('test_fireworks*.py'))
    paths |= {rt.ROOT / 'tests/unit/test_external_metadata_renewal.py',
              rt.ROOT / 'tests/unit/test_external_inventory.py'}
    paths |= set((rt.ROOT / 'tests/unit').glob('*.py'))
    paths |= set((rt.ROOT / 'gateway/tools').glob('*.py'))
    return [{'path': p.relative_to(rt.ROOT).as_posix(), 'sha256': sha(p.read_bytes())} for p in sorted(paths)]


def tests():
    suites = list(ET.parse(TESTS).getroot().iter('testsuite'))
    count = sum(int(s.get('tests', 0)) for s in suites)
    rt.require(count >= 200 and all(int(s.get(k, 0)) == 0 for s in suites
               for k in ('failures', 'errors', 'skipped')), 'actual_clean_release_tests_required')
    return {'tests': count, 'sha256': sha(TESTS.read_bytes())}


def baseline():
    run = ProductRun()
    return {'protected': run.protected(), 'policy_sha256': sha(run.policy())}


def guard(plan, images):
    rt.require(set(images) == set(KINDS) and plan.get('applyable') is True
               and not plan.get('errored') and not plan.get('deferred_changes'), 'resolved_exact_two_images_required')
    for kind, image in images.items():
        rt.require(re.fullmatch(re.escape(portals.HOST + '/aiflux-' + kind + '@sha256:') + '[a-f0-9]{64}', image),
                   'immutable_exact_repository_required')
    seen = set()
    for item in plan.get('resource_changes', []):
        change = item['change']
        if change['actions'] in (['no-op'], ['read']):
            rt.require(change['actions'] == ['no-op'] or item.get('mode') == 'data', 'managed_read_rejected')
            continue
        address = item['address']
        rt.require(item.get('mode') == 'managed' and address in ADDRESSES and address not in seen
                   and change['actions'] == ['update'], 'exact_api_ingestion_update_only')
        seen.add(address)
        before, after = deepcopy(change['before']), deepcopy(change['after'])
        unknown = change.get('after_unknown') or {}
        rt.require(not any(rt.any_true(v) for k, v in unknown.items() if k not in fs.COMPUTED),
                   'unknown_writable_input')
        for key in fs.COMPUTED:
            if rt.any_true(unknown.get(key)):
                after[key] = before.get(key)
        rt.require(len(before['site_config']) == len(after['site_config']) == 1, 'site_shape')
        old, new = before['site_config'][0]['application_stack'], after['site_config'][0]['application_stack']
        rt.require(len(old) == len(new) == 1, 'stack_shape')
        kind = ADDRESSES[address]
        if kind == 'api':
            rt.require(new[0]['docker_image_name'] == images[kind].split('/', 1)[1]
                       and new[0]['docker_registry_url'] == 'https://' + portals.HOST, 'exact_api_pin')
            new[0]['docker_image_name'] = old[0]['docker_image_name']
        else:
            rt.require(before['enabled'] is True and after['enabled'] is True, 'enabled_function_preserved')
            settings = before['app_settings']
            rt.require(settings['AzureWebJobs.ingest_usage.Disabled'] == 'false'
                       and settings['AIFLUX_CATALOG_CONFIGURED'] == 'true'
                       and settings['AIFLUX_INGESTION_START_AT'] == '2026-10-27T06:06:02.045288+00:00'
                       and before['site_config'][0]['always_on'] is True, 'healthy_finops_settings_required')
            rt.require(len(old[0]['docker']) == len(new[0]['docker']) == 1, 'existing_function_container')
            docker = new[0]['docker'][0]
            repo, pin = images[kind].split('@sha256:')
            rt.require(docker['image_name'] == repo.split('/', 1)[1] + '@sha256'
                       and docker['image_tag'] == pin and docker['registry_url'] == 'https://' + portals.HOST
                       and not docker.get('registry_username') and not docker.get('registry_password'), 'exact_function_pin')
            for key in ('image_name', 'image_tag'):
                docker[key] = old[0]['docker'][0][key]
        rt.require(change['before'] != change['after'] and before == after, 'non_image_change_rejected')
    rt.require(seen == set(ADDRESSES), 'exact_two_image_updates_required')
    rt.require(all(c.get('status') == 'pass' for c in resolved_checks(plan)), 'all_plan_checks_must_pass')


def resolve_checks(target, companion):
    """Resolve targeted unknowns from identical-input full planning, never apply it."""
    def normalized(value):
        if isinstance(value, dict):
            return {k: sorted(v) if k == 'references' and isinstance(v, list)
                    and all(isinstance(x, str) for x in v) else normalized(v)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [normalized(v) for v in value]
        return value
    rt.require(target.get('configuration') is not None
               and normalized(target['configuration']) == normalized(companion.get('configuration'))
               and target.get('variables') is not None
               and target['variables'] == companion.get('variables')
               and not companion.get('errored') and not companion.get('deferred_changes'),
               'companion_plan_input_drift')
    full = {c['address']: c for c in companion.get('resource_changes', [])}
    for item in target.get('resource_changes', []):
        if item['address'] in ADDRESSES:
            rt.require(item['address'] in full and item['change'] == full[item['address']]['change'],
                       'companion_target_change_drift')
    checks = companion.get('checks', [])
    rt.require(checks and all(c.get('status') == 'pass' for c in checks), 'companion_checks_not_passed')
    by_address = {json.dumps(c['address'], sort_keys=True): c for c in checks}
    result = []
    for check in target.get('checks', []):
        rt.require(check.get('status') in ('pass', 'unknown'), 'target_failed_check')
        key = json.dumps(check['address'], sort_keys=True)
        rt.require(key in by_address, 'companion_missing_check')
        result.append(by_address[key])
    return result


def resolved_checks(plan):
    if all(c.get('status') == 'pass' for c in plan.get('checks', [])):
        return plan.get('checks', [])
    companion = HOME / 'validation-only-refreshed-never-apply.tfplan'
    rt.require(companion.exists(), 'all_plan_checks_must_pass')
    full = json.loads(fs.terraform(ROOT, 'show', '-json', str(companion)))
    return resolve_checks(plan, full)


def acceptance():
    proof = load(HOME / 'acceptance.json')
    for filename, key in [('foundry-inventory-20261026.json', 'foundry_sha256'),
                           ('external-inventory.json', 'external_sha256')]:
        rt.require(sha((rt.ROOT / 'gateway/catalog' / filename).read_bytes()) == proof[key], 'accepted_source_drift')
    rt.require(len(proof['enabled_chat_models']) == 13 and proof['historical_external_smoke_unchanged']
               and not proof['fresh_external_credential_health_verified']
               and not proof['gateway_applied_again'], 'actual_acceptance_required')
    rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(proof['metadata_at_utc'])
               < timedelta(hours=12), 'metadata_must_remain_fresh_through_release')
    return proof


def context(folder, include_tests=False):
    groups = manifest_builder.source_manifest()['components']
    names = {e['path'] for kind in KINDS for e in groups[kind]['entries']}
    if include_tests:
        names |= {p.relative_to(rt.ROOT).as_posix() for p in (rt.ROOT / 'tests/unit').glob('*.py')}
        names |= {p.relative_to(rt.ROOT).as_posix() for p in (rt.ROOT / 'gateway/tools').glob('*.py')}
    for name in sorted(names):
        path = rt.ROOT / name
        raw = path.read_bytes()
        rt.require(not path.is_symlink() and not re.search(
            rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}', raw), 'source_secret_pattern')
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return folder


def remote_build(folder, file, kind=None, tag=None):
    args = rt.CLI + ['acr', 'build', '--registry', portals.REGISTRY, '--subscription', rt.SUB,
        '--platform', 'linux/amd64', '--timeout', '1800', '--file', file]
    args += ['--no-push'] if kind is None else ['--image', 'aiflux-' + kind + ':' + tag]
    child = subprocess.run(args + ['.'], cwd=folder, env=rt.ENV, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=2100)
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', child.stdout + child.stderr)
    log = folder.parent / ((kind or 'native-validation') + '-build.log')
    log.write_text(text, encoding='utf-8')
    ids = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
    rt.require(child.returncode == 0 and ids, 'remote_build_failed_no_resubmission:' + (kind or 'native'))
    run = rt.cli(['acr', 'task', 'show-run', '-r', portals.REGISTRY, '--run-id', ids[-1], '--subscription', rt.SUB])
    rt.require(run['status'] == 'Succeeded' and run['platform']['os'].lower() == 'linux', 'native_build_not_succeeded')
    result = {'run_id': ids[-1], 'status': run['status'], 'finished_at': run['finishTime'],
              'log_sha256': sha(log.read_bytes()), 'no_push': kind is None}
    if kind is not None:
        meta = rt.cli(['acr', 'manifest', 'show-metadata', '--registry', portals.REGISTRY,
                       '--name', 'aiflux-' + kind + ':' + tag, '--subscription', rt.SUB])
        rt.require(re.fullmatch('sha256:[a-f0-9]{64}', meta['digest']), 'immutable_digest_required')
        rt.require(run['outputImages'] == [{'digest': meta['digest'], 'registry': portals.HOST,
                   'repository': 'aiflux-' + kind, 'tag': tag}], 'exact_native_output_required')
        result.update(tag=tag, digest=meta['digest'], image=portals.HOST + '/aiflux-' + kind + '@' + meta['digest'])
    return result


def native(corrected=False, isolated=False):
    acceptance()
    tests()
    name = 'native-isolated' if isolated else ('native-corrected' if corrected else 'native')
    if corrected:
        rt.require((HOME / 'native-intent.json').exists() and not (HOME / 'native.json').exists(),
                   'failed_original_native_required')
    with (HOME / (name + '-intent.json')).open('x') as handle:
        json.dump({'at': datetime.now(UTC).isoformat(), 'sources': sources()}, handle)
    folder = context(HOME / name / 'context', include_tests=True)
    docker = (folder / 'services/control-plane/Dockerfile').read_text()
    docker += ('\nRUN python -m pip install --user --no-cache-dir pytest==8.4.0\n'
               'COPY tests/unit /app/tests/unit\n'
               'COPY gateway/tools /app/gateway/tools\n'
               'COPY services/usage-ingestion/ingestion-approved.json /app/services/usage-ingestion/ingestion-approved.json\n'
               'RUN python -m pytest -q tests/unit/test_external_metadata_renewal.py '
               'tests/unit/test_external_inventory.py tests/unit/test_foundry_inventory.py '
               'tests/unit/test_display_pricing.py --junitxml=/tmp/fireworks-native.xml\n')
    (folder / 'FireworksNative.Dockerfile').write_text(docker, encoding='utf-8')
    result = remote_build(folder, 'FireworksNative.Dockerfile')
    result['sources'] = sources()
    rt.save(HOME / 'native.json', result)
    print(json.dumps(result), flush=True)


def build():
    acceptance()
    tests()
    native_proof = load(HOME / 'native.json')
    rt.require(native_proof['sources'] == sources() and native_proof['status'] == 'Succeeded', 'native_source_binding')
    from scripts.deployment.finops_ingestion_image_repair import scan
    scanner = scan()
    rt.save(HOME / 'scanner.json', scanner)
    rt.require(scanner['exit_code'] == 0 and not scanner['failed_checks'], 'ingestion_security_scan_required')
    with (HOME / 'build-intent.json').open('x') as handle:
        json.dump({'at': datetime.now(UTC).isoformat(), 'sources': sources(), 'components': list(KINDS)}, handle)
    folder = context(HOME / 'build/context')
    rt.save(HOME / 'sources.json', sources())
    result = {}
    for kind in KINDS:
        rt.require(sources() == load(HOME / 'sources.json'), 'source_changed_before_submission')
        tag = 'fireworks-' + datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz') + '-' + sha(json.dumps(sources(), sort_keys=True))[:12]
        with (HOME / (kind + '-build-intent.json')).open('x') as handle:
            json.dump({'at': datetime.now(UTC).isoformat(), 'tag': tag, 'submissions': 1}, handle)
        file = 'services/control-plane/Dockerfile' if kind == 'api' else 'services/usage-ingestion/Dockerfile'
        result[kind] = remote_build(folder, file, kind, tag)
        rt.save(HOME / 'build.json', result)
        print(json.dumps({kind: result[kind]}), flush=True)


def corrected_ingestion():
    """Retain the successful API; repair only the observed missing COPY input."""
    acceptance()
    tests()
    original = load(HOME / 'sources.json')
    now = sources()
    old_map = {p['path']: p['sha256'] for p in original}
    new_map = {p['path']: p['sha256'] for p in now}
    changed = {p for p in old_map.keys() | new_map.keys() if old_map.get(p) != new_map.get(p)}
    rt.require(changed == {'services/usage-ingestion/Dockerfile',
                          'scripts/deployment/fireworks_runtime.py'}, 'exact_packaging_correction_only')
    native_proof = load(HOME / 'native.json')
    rt.require(native_proof['sources'] == original and native_proof['status'] == 'Succeeded',
               'original_native_proof_required')
    entries = manifest_builder.source_manifest()['components']['api']['entries']
    rt.require(all(old_map[e['path']] == e['sha256'] for e in entries), 'retained_api_inputs_changed')
    docker = rt.ROOT / 'services/usage-ingestion/Dockerfile'
    previous = HOME / 'build/context/services/usage-ingestion/Dockerfile'
    added = b'COPY gateway/catalog/fireworks-candidate-routes.json ./gateway/catalog/\n'
    rt.require(docker.read_bytes().replace(b'\r\n', b'\n') ==
               previous.read_bytes().replace(b'\r\n', b'\n').replace(
                   b'COPY services/usage-ingestion/approved_catalog.py',
                   added + b'COPY services/usage-ingestion/approved_catalog.py'), 'exact_missing_copy_only')
    result = load(HOME / 'build.json')
    rt.require(set(result) == {'api'}, 'successful_api_only_required')
    scan = __import__('scripts.deployment.finops_ingestion_image_repair', fromlist=['scan']).scan()
    rt.require(scan['exit_code'] == 0 and not scan['failed_checks'], 'corrected_ingestion_security_scan')
    rt.save(HOME / 'corrected-scanner.json', scan)
    with (HOME / 'ingestion-correction-intent.json').open('x') as handle:
        json.dump({'at': datetime.now(UTC).isoformat(), 'sources': now,
                   'original_sources_sha256': sha((HOME / 'sources.json').read_bytes()),
                   'changed_paths': sorted(changed), 'retained_api': result['api'],
                   'api_production_inputs_equal': True, 'original_native_run_id': native_proof['run_id']}, handle)
    folder = context(HOME / 'ingestion-correction/context')
    tag = 'fireworks-ingestion-' + datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')
    result['ingestion'] = remote_build(folder, 'services/usage-ingestion/Dockerfile', 'ingestion', tag)
    rt.save(HOME / 'corrected-build.json', result)
    print(json.dumps(result), flush=True)


def built():
    acceptance()
    correction = HOME / 'ingestion-correction-intent.json'
    if correction.exists():
        proof = load(correction)
        # Images contain production package inputs, not this release controller.
        # The current controller itself is bound by the subsequent plan/review.
        tooling = {
            Path(__file__).relative_to(rt.ROOT).as_posix(),
            'tests/unit/test_fireworks_runtime.py',
            'scripts/deployment/fireworks_runtime_validation.py',
            'scripts/deployment/fireworks_runtime_preserved.py',
        }
        rt.require([p for p in sources() if p['path'] not in tooling] ==
               [p for p in proof['sources'] if p['path'] not in tooling]
                   and proof['api_production_inputs_equal'] is True
                   and sha((HOME / 'sources.json').read_bytes()) == proof['original_sources_sha256'],
                   'corrected_build_source_changed')
        result = load(HOME / 'corrected-build.json')
        rt.require(result['api'] == proof['retained_api'] == load(HOME / 'build.json')['api'],
                   'retained_api_changed')
    else:
        rt.require(sources() == load(HOME / 'sources.json'), 'built_source_changed')
        result = load(HOME / 'build.json')
    rt.require(set(result) == set(KINDS), 'both_images_required')
    for kind, item in result.items():
        run = rt.cli(['acr', 'task', 'show-run', '-r', portals.REGISTRY, '--run-id', item['run_id'], '--subscription', rt.SUB])
        meta = rt.cli(['acr', 'manifest', 'show-metadata', '--registry', portals.REGISTRY,
                       '--name', 'aiflux-' + kind + ':' + item['tag'], '--subscription', rt.SUB])
        rt.require(run['status'] == 'Succeeded' and run['finishTime'] == item['finished_at']
                   and meta['digest'] == item['digest'], 'built_remote_pin_changed')
    return {k: v['image'] for k, v in result.items()}


def verify_external_metadata():
    """Fresh readback of exact release-bound metadata, never credential health."""
    from aiflux.external_inventory import ExternalRoute
    from scripts.deployment.glm_apim_secret import NAME, metadata, internal_ready
    route = ExternalRoute.model_validate(load(rt.ROOT / 'gateway/catalog/external-inventory.json')['routes'][0])
    renewal = route.metadata_renewal
    rt.require(renewal is not None, 'separate_metadata_renewal_required')
    age = (datetime.now(UTC) - renewal.observed_at).total_seconds()
    rt.require(0 <= age <= 86400, 'external_metadata_renewal_expired')
    run = ProductRun()
    policy = run.policy()
    backends = run.arm('/backends')
    external = [b for b in backends['value'] if 'glm' in b['name'].lower()]
    reference = metadata(run.arm('/namedValues/' + NAME))
    original_reference = load(HOME / 'readback.json')['external_internal_reference']
    # checked_at is collector time, not an ARM binding field. Authenticate the
    # original full attestation, then compare every actual reference field.
    binding = lambda value: {k: v for k, v in value.items() if k != 'checked_at'}
    rt.require(len(external) == 1 and internal_ready(reference)
               and sha(policy) == renewal.policy_sha256
               and sha(json.dumps(external[0], sort_keys=True)) == renewal.backend_sha256
               and sha(json.dumps(original_reference, sort_keys=True)) == renewal.reference_metadata_sha256
               and binding(reference) == binding(original_reference),
               'external_live_metadata_binding_changed')
    return {'metadata_binding_verified': True, 'historical_health_at': route.verified_at.isoformat(),
            'fresh_credential_health_verified': False, 'external_inference_requests': 0}


def plan():
    rt.require(not (HOME / 'plan-intent.json').exists() and not (HOME / 'apply-intent.json').exists(), 'never_replan_or_replay')
    images = built()
    verify_external_metadata()
    before = baseline()
    settings = fs.current_settings()
    api = settings['api']
    rt.require(api.get('AIFLUX_GATEWAY_CONTROLS_POC_ENABLED', 'false').lower() == 'false'
               and api.get('AIFLUX_GATEWAY_CONTROLS_V2_ENABLED', 'false').lower() == 'false'
               and json.loads(api.get('AIFLUX_GATEWAY_SETTINGS_SCOPES', '[]')) == [], 'optional_controls_off')
    fs.protect(HOME)
    ROOT.mkdir(parents=True)
    for path in (rt.ROOT / 'infra/terraform').iterdir():
        if path.is_file() and (path.name.endswith(('.tf', '.tf.json')) or path.name == '.terraform.lock.hcl'):
            shutil.copyfile(path, ROOT / path.name)
    for name in ('infra/models', 'gateway/catalog', 'gateway/policies'):
        shutil.copytree(rt.ROOT / name, HOME / name,
                        ignore=shutil.ignore_patterns('.terraform', '*.tfstate*', '__pycache__', '*.tfplan'))
    for path in (rt.ROOT / 'gateway').glob('*.json'):
        shutil.copyfile(path, HOME / 'gateway' / path.name)
    current = before['protected']['runtime']
    variables = portals.runtime_variables({'results': {k: {'image': current['sites'][k]['image'].removeprefix('DOCKER|')}
        for k in ('admin', 'customer')}}, current)
    variables['apps']['api']['image'] = images['api'].split('/', 1)[1]
    variables.update(ingestion_container_image=images['ingestion'], ingestion_enabled=True,
        ingestion_timer_enabled=True, ingestion_start_at=settings['ingestion']['AIFLUX_INGESTION_START_AT'],
        ingestion_catalog_accepted=True)
    rt.save(HOME / 'runtime.tfvars.json', variables)
    fs.terraform(ROOT, 'init', '-input=false', '-lockfile=readonly', '-no-color',
                 '-backend-config=' + str(rt.ROOT / 'infra/terraform/backend.hcl'))
    function = fs.preserved_function(ROOT, {k: v for k, v in settings['ingestion'].items()
        if k not in {'DOCKER_REGISTRY_SERVER_URL', 'DOCKER_REGISTRY_SERVER_USERNAME', 'DOCKER_REGISTRY_SERVER_PASSWORD'}},
        images['ingestion'], settings['ingestion']['AZURE_CLIENT_ID'])
    function['enabled'] = True
    # preserved_function's historical disabled-stage default is false. This
    # image-only release must retain the live approved Always On=true setting.
    function['site_config'][0]['always_on'] = True
    rt.save(ROOT / 'fireworks_preserved.tf.json', {'locals': {'fireworks_web_settings': fs.literal(fs.preserved_web_settings(settings))}})
    rt.save(ROOT / 'zzzz_fireworks_override.tf.json', {'resource': {
        'azurerm_linux_web_app': {'main': {'app_settings': '${local.fireworks_web_settings[each.key]}' }},
        'azurerm_linux_function_app': {'ingestion': function}}})
    fs.terraform(ROOT, 'validate', '-no-color')
    rt.require(fs.terraform(ROOT, 'workspace', 'show').strip() == 'default', 'workspace')
    with (HOME / 'plan-intent.json').open('x') as handle:
        json.dump({'at': datetime.now(UTC).isoformat()}, handle)
    fs.terraform(ROOT, 'plan', '-input=false', '-no-color', '-lock-timeout=60s',
        '-var-file=' + str(rt.HOME / 'rebuild-platform.tfvars.json'),
        '-var-file=' + str(HOME / 'runtime.tfvars.json'), '-var-file=' + str(rt.HOME / 'jwt-runtime.tfvars.json'),
        *['-target=' + a for a in ADDRESSES], '-out=' + str(PLAN))
    parsed = load_plan()
    guard(parsed, images)
    review = {'at': datetime.now(UTC).isoformat(), 'plan_sha256': sha(PLAN.read_bytes()),
              'sources': sources(), 'images': images, 'baseline': before, 'tests': tests(),
              'artifacts': {p.relative_to(HOME).as_posix(): sha(p.read_bytes()) for p in [
                  *ROOT.glob('*.tf'), *ROOT.glob('*.tf.json'), ROOT / '.terraform.lock.hcl', HOME / 'runtime.tfvars.json']},
              'guard': 'exact_api_and_ingestion_images_only'}
    rt.save(HOME / 'review.json', review)
    print(json.dumps({k: review[k] for k in ('at', 'plan_sha256', 'images', 'guard')}), flush=True)


def load_plan():
    return json.loads(fs.terraform(ROOT, 'show', '-json', str(PLAN)))


def check(live=True):
    review = load(HOME / 'review.json')
    rt.require(review['sources'] == sources() and review['tests'] == tests()
               and review['plan_sha256'] == sha(PLAN.read_bytes()), 'review_source_tests_or_plan_drift')
    rt.require(all(sha((HOME / p).read_bytes()) == digest for p, digest in review['artifacts'].items()), 'archived_input_drift')
    if live:
        rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review['at']) < timedelta(hours=2), 'plan_expired')
    rt.require(built() == review['images'], 'built_images_changed')
    guard(load_plan(), review['images'])
    if live:
        verify_external_metadata()
        rt.require(baseline() == review['baseline'], 'full_protected_baseline_drift')
    return review


def apply():
    rt.require(not (HOME / 'apply-intent.json').exists(), 'never_replay_apply')
    review = check()
    proof = load(HOME / 'validation.json')
    status = load(rt.ROOT / '.azure/validate-status.json')
    doc = (rt.ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
    rt.require(proof['checks_passed'] is True and proof['plan_sha256'] == review['plan_sha256']
               and proof['sources'] == sources() and status['completedStep'] == 'UpdateStatus'
               and 'Fireworks runtime status: Validated.' in doc and proof['at'] in doc
               and review['plan_sha256'] in doc, 'independent_exact_validation_required')
    with (HOME / 'apply-intent.json').open('x') as handle:
        json.dump({'at': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256']}, handle)
    fs.terraform(ROOT, 'apply', '-input=false', '-no-color', str(PLAN))
    rt.save(HOME / 'applied.json', {'at': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256']})
    verify()


def verify():
    review = check(live=False)
    rt.require(load(HOME / 'applied.json')['plan_sha256'] == review['plan_sha256'], 'matching_apply_required')
    expected = deepcopy(review['baseline'])
    for kind, image in review['images'].items():
        expected['protected']['runtime']['sites'][kind]['image'] = 'DOCKER|' + image
    current = baseline()
    result = {'at': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256'], 'images': review['images'],
              'protected_equal_except_two_images': current == expected,
              'all_four_settings_hashes_equal': current['protected']['settings_hashes'] == expected['protected']['settings_hashes'],
              'gateway_reapplied': False, 'optional_controls_enabled': False,
              'rbac_writes': 0, 'network_writes': 0, 'database_migrations': 0, 'backfills': 0}
    rt.save(HOME / 'verification.json', result)
    print(json.dumps(result), flush=True)
    rt.require(current == expected, 'protected_readback_mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['native', 'native-corrected', 'native-isolated', 'build', 'corrected-ingestion', 'plan', 'check', 'apply', 'verify'])
    action = parser.parse_args().action
    {'native': native, 'native-corrected': lambda: native(corrected=True), 'build': build,
        'corrected-ingestion': corrected_ingestion,
        'native-isolated': lambda: native(corrected=True, isolated=True),
     'plan': plan, 'check': check, 'apply': apply, 'verify': verify}[action]()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'runtime_release_failed_sensitive_detail_suppressed'}), flush=True)
        raise SystemExit(1)