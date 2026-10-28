"""Finite ingestion image-only repair; never rolls back an applied activation.

Plans preserve the actual full ARM settings and enabled state. An enabled host
is accepted only against the exact previously validated and applied host plan.
No four-image guard, existing build marker or applied plan is relaxed/replayed.
"""
from __future__ import annotations

import argparse
import copy
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from scripts.deployment import finops_catalog_repair as catalog
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import finops_release as release
from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt

HOST_PLAN_SHA256 = 'ea9b870207abadb7efa6dcaf7e6b71bf762cf7cc90979bd56fb60fde9355e31c'
HOST_CONTROLLER_SHA256 = 'd577967c86042fa061e1b54ce34e54c98f8750296b6f39eca80ef3d2e526b98c'
HOST_SETTINGS_SHA256 = '8d9eb39a189c8024c5288c86b125a2897ae95974be868f4f66f3aa8c2434d410'
PLAN_FOLDER = 'ingestion-image-only-applied-host'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def build_proof(tag):
    rt.require(re.fullmatch(r'finops-\d{8}t\d{6}z', tag), 'invalid_build_tag')
    folder = rt.HOME / 'finops' / tag
    result, manifest = load(folder / 'results.json'), load(folder / 'source-manifest.json')
    rt.require(result['tag'] == tag and result['exit_code'] == 0
               and result['requested_components'] == ['ingestion']
               and set(result['components']) == {'ingestion'}, 'single_ingestion_build_required')
    rt.require(manifest == release.source_manifest() and result['source_manifest_sha256'] ==
               release.digest((folder / 'source-manifest.json').read_bytes()), 'current_source_binding')
    original = load(rt.HOME / 'finops' / catalog.BASE_TAG / 'source-manifest.json')
    rt.require(all(manifest['components'][k] == original['components'][k]
                   for k in ('api', 'admin', 'customer')), 'other_application_sources_changed')
    for entry in manifest['components']['ingestion']['entries']:
        rt.require(release.digest((folder / 'context' / entry['path']).read_bytes()) == entry['sha256'],
                   'retained_build_context_changed')
    item = result['components']['ingestion']
    rt.require(item['status'] == 'Succeeded' and item['submissions'] == 1 and item['cli_exit_code'] == 0
               and item['source_sha256'] == manifest['components']['ingestion']['source_sha256'], 'build_failed')
    run = rt.cli(['acr', 'task', 'show-run', '--registry', 'pocidstokenexacr', '--subscription', rt.SUB,
                  '--run-id', item['run_id']])
    meta = rt.cli(['acr', 'manifest', 'show-metadata', '--registry', 'pocidstokenexacr', '--subscription', rt.SUB,
                   '--name', 'aiflux-ingestion:' + tag])
    rt.require(re.fullmatch(r'sha256:[a-f0-9]{64}', meta['digest']), 'immutable_digest_required')
    rt.require(run['status'] == 'Succeeded' and run['platform']['os'].lower() == 'linux'
               and run['finishTime'] == item['finished_at_utc']
               and run['outputImages'] == [{'digest': meta['digest'], 'registry': release.REGISTRY,
                                           'repository': 'aiflux-ingestion', 'tag': tag}]
               and item['image'] == release.REGISTRY + '/aiflux-ingestion@' + meta['digest'], 'remote_acr_binding')
    log = (folder / 'ingestion-build.log').read_text(encoding='utf-8')
    rt.require(all(text in log for text in ('python services/usage-ingestion/approved_catalog.py',
               'import azure.functions, azure.identity, azure.monitor.query, psycopg', 'Successfully built')),
               'native_linux_validation_missing')
    return {'tag': tag, 'run_id': item['run_id'], 'image': item['image'], 'digest': meta['digest'],
            'source_sha256': item['source_sha256'], 'manifest_sha256': result['source_manifest_sha256'],
            'native_linux_validation': True, 'catalog': catalog.catalog_proof()}


def host_provenance():
    """Authenticate retained provenance, not an arbitrary observed live baseline."""
    folder = catalog.HOME / 'host'
    review = load(folder / 'review.json')
    rt.require(review['plan_sha256'] == HOST_PLAN_SHA256
               and review['controller_sha256'] == HOST_CONTROLLER_SHA256
               and review['target_settings_hash'] == HOST_SETTINGS_SHA256
               and review['mode'] == 'host' and review['enabled'] is True
               and review['guard'] == 'passed', 'unapproved_host_provenance')
    for name in ('validation.json', 'apply-intent.json', 'applied.json'):
        marker = load(folder / name)
        rt.require(marker['plan_sha256'] == HOST_PLAN_SHA256, 'host_marker_plan_mismatch')
    rt.require(load(folder / 'applied.json')['applied'] is True
               and load(folder / 'validation.json')['source_build_catalog_baseline_settings_guard'] == 'passed',
               'host_not_validated_and_applied')
    for name, digest in review['artifacts'].items():
        rt.require(release.digest((folder / name).read_bytes()) == digest, 'host_provenance_artifact_changed')
    rt.require(release.digest((folder / 'stage.tfplan').read_bytes()) == HOST_PLAN_SHA256,
               'host_saved_plan_changed')
    target = load(folder / 'target-settings.json')
    rt.require(fs.sha(target) == HOST_SETTINGS_SHA256
               and target['AIFLUX_INGESTION_START_AT'] == review['boundary']
               and load(catalog.HOME / 'boundary.json')['start_at'] == review['boundary']
               and target['AIFLUX_CATALOG_CONFIGURED'] == 'true'
               and target['AIFLUX_CATALOG_PATH'] == catalog.CATALOG_PATH
               and target['AzureWebJobs.ingest_usage.Disabled'] == 'true', 'host_target_drift')
    parsed = json.loads(fs.terraform(folder / 'infra/terraform', 'show', '-json', str(folder / 'stage.tfplan')))
    catalog.guard(parsed, 'host', review['image'], target, True)
    resource = next(r['change']['after'] for r in parsed['resource_changes'] if r['address'] == fs.FUNCTION)
    baseline = load(folder / 'baseline.json')
    baseline['sites']['ingestion']['image'] = 'DOCKER|' + review['image']
    baseline['sites']['ingestion']['protected']['enabled'] = True
    return {'plan_sha256': HOST_PLAN_SHA256, 'target_settings_hash': HOST_SETTINGS_SHA256,
            'boundary': review['boundary'], 'applied_at_utc': load(folder / 'applied.json')['at_utc'],
            'resource': resource, 'baseline': baseline,
            'settings_hashes': {**review['settings_hashes'], 'ingestion': HOST_SETTINGS_SHA256}}


def guard(plan, image, host=None):
    """Exactly one changed docker pin; every other writable value is identical."""
    rt.require(re.fullmatch(re.escape(release.REGISTRY + '/aiflux-ingestion@sha256:') + '[a-f0-9]{64}', image),
               'immutable_ingestion_pin_required')
    rt.require(plan.get('applyable') is True and not plan.get('errored') and not plan.get('deferred_changes'),
               'unresolved_plan')
    seen = []
    for resource in plan.get('resource_changes', []):
        change = resource['change']
        if change['actions'] == ['no-op']:
            continue
        rt.require(resource['address'] == fs.FUNCTION and resource.get('mode') == 'managed'
                   and change['actions'] == ['update'], 'single_function_update_required')
        seen.append(resource['address'])
        before, after = copy.deepcopy(change['before']), copy.deepcopy(change['after'])
        unknown = change.get('after_unknown') or {}
        rt.require(not any(release.any_unknown(v) for k, v in unknown.items() if k not in fs.COMPUTED),
                   'unknown_writable_input')
        for key in fs.COMPUTED:
            if release.any_unknown(unknown.get(key)):
                after[key] = before.get(key)
        if host is None:
            rt.require(before['enabled'] is False and after['enabled'] is False, 'requested_host_disabled_baseline_not_true')
            for settings in (before['app_settings'], after['app_settings']):
                rt.require(settings.get('AzureWebJobs.ingest_usage.Disabled') == 'true'
                           and settings.get('AIFLUX_CATALOG_CONFIGURED') == 'false'
                           and not settings.get('AIFLUX_INGESTION_START_AT'), 'requested_catalog_false_no_cutoff_baseline_not_true')
        else:
            rt.require(host['plan_sha256'] == HOST_PLAN_SHA256
                       and host['target_settings_hash'] == HOST_SETTINGS_SHA256, 'unapproved_host_provenance')
            rt.require({k: v for k, v in before.items() if k not in fs.COMPUTED} ==
                       {k: v for k, v in host['resource'].items() if k not in fs.COMPUTED}, 'applied_host_baseline_drift')
            for value in (before, after):
                settings = value['app_settings']
                rt.require(value['enabled'] is True and settings['AzureWebJobs.ingest_usage.Disabled'] == 'true'
                           and settings['AIFLUX_CATALOG_CONFIGURED'] == 'true'
                           and settings['AIFLUX_CATALOG_PATH'] == catalog.CATALOG_PATH
                           and settings['AIFLUX_INGESTION_START_AT'] == host['boundary'], 'applied_host_settings_drift')
        rt.require(len(before['site_config']) == len(after['site_config']) == 1, 'site_config_shape')
        old, new = before['site_config'][0]['application_stack'], after['site_config'][0]['application_stack']
        rt.require(len(old) == len(new) == 1 and len(old[0].get('docker', [])) == len(new[0].get('docker', [])) == 1,
                   'existing_container_required')
        docker = new[0]['docker'][0]
        repo, pin = image.split('@sha256:')
        rt.require(docker.get('image_name') == repo.split('/', 1)[1] + '@sha256' and docker.get('image_tag') == pin
                   and docker.get('registry_url') == 'https://' + release.REGISTRY
                   and not docker.get('registry_username') and not docker.get('registry_password'), 'exact_image_required')
        rt.require(old[0]['docker'][0] != docker, 'new_image_required')
        for key in ('image_name', 'image_tag'):
            docker[key] = old[0]['docker'][0].get(key)
        rt.require(before == after, 'non_image_change_rejected')
    rt.require(seen == [fs.FUNCTION], 'exact_single_update_required')


def safety(baseline):
    rt.require(baseline['postgres']['network']['publicNetworkAccess'] == 'Disabled'
               and not baseline['postgresRules'], 'postgres_protection_drift')
    storage = rt.cli(['storage', 'account', 'show', '--subscription', rt.SUB, '--resource-group',
                      'IDS-TOKEN-EXCHANGE-POC', '--name', 'projpoctokenex'])['networkRuleSet']
    ips = sorted(r['ipAddressOrRange'] for r in storage['ipRules'])
    rt.require(storage['defaultAction'] == 'Deny' and ips ==
               ['167.103.65.36', '167.103.66.248', '167.103.66.93'], 'state_acl_drift')
    return {'state_default_action': 'Deny', 'state_ips': ips, 'postgres_public': 'Disabled', 'postgres_firewall_rules': 0}


def scan():
    tools = rt.HOME / 'finops-runner/security-tools'
    env = {**rt.ENV, 'PYTHONPATH': str(tools), 'CKV_SKIP_UPDATE_CHECK': 'true', 'LOG_LEVEL': 'ERROR'}
    env.pop('BC_API_KEY', None)
    path = rt.ROOT / 'services/usage-ingestion/Dockerfile'
    result = subprocess.run([sys.executable, str(tools / 'bin/checkov'), '--file', str(path), '--framework',
                             'dockerfile', '--skip-download', '--output', 'json', '--compact'],
                            capture_output=True, text=True, env=env, timeout=180)
    parsed = json.loads(result.stdout)
    checks = [c for value in parsed['results'].values() if isinstance(value, list)
              for c in value if isinstance(c, dict)]
    skipped = [c for c in checks if c.get('check_result', {}).get('result') == 'SKIPPED']
    return {'at_utc': fs.stamp(), 'scanner': 'checkov==3.2.495', 'exit_code': result.returncode,
            'dockerfile_sha256': release.digest(path.read_bytes()), 'summary': parsed['summary'],
            'failed_checks': [{k: c.get(k) for k in ('check_id', 'check_name', 'resource')}
                              for c in parsed['results'].get('failed_checks', [])],
            'skipped_checks': [{'check_id': c['check_id'], 'check_name': c.get('check_name'),
                                'suppress_comment': c.get('check_result', {}).get('suppress_comment')}
                               for c in skipped],
            'remote_policy_downloads': False, 'dependencies_upgraded': False}


def prepare(tag):
    build = build_proof(tag)
    folder = rt.HOME / 'finops' / tag / PLAN_FOLDER
    rt.require(not folder.exists(), 'existing_plan_do_not_overwrite_or_replay')
    fs.protect(folder)
    baseline, settings = portals.baseline(), fs.current_settings()
    host = host_provenance()
    rt.require(baseline == host['baseline'] and {k: fs.sha(v) for k, v in settings.items()} == host['settings_hashes'],
               'live_baseline_not_exact_applied_host')
    protection = safety(baseline)
    rt.require(all(settings['ingestion'].get(k) == v for k, v in catalog.REGISTRY_SETTINGS.items()),
               'exact_provider_injected_registry_required')
    rt.save(folder / 'baseline.json', baseline)
    rt.save(folder / 'target-settings.json', settings['ingestion'])
    report = {'at_utc': fs.stamp(), 'build': build, 'security': protection,
              'settings_hashes': {k: fs.sha(v) for k, v in settings.items()},
              'host_enabled': baseline['sites']['ingestion']['protected']['enabled'],
              'timer_disabled': settings['ingestion'].get('AzureWebJobs.ingest_usage.Disabled'),
              'catalog_configured': settings['ingestion'].get('AIFLUX_CATALOG_CONFIGURED'),
              'cutoff_present': bool(settings['ingestion'].get('AIFLUX_INGESTION_START_AT')),
              'cloud_configuration_writes': 0, 'applied': False, 'status': 'preparing',
              'controller_sha256': release.digest(Path(__file__).read_bytes()),
              'host_provenance': {k: v for k, v in host.items() if k not in ('resource', 'baseline', 'settings_hashes')}}
    rt.save(folder / 'preparation.json', report)
    report['scanner'] = scan()
    rt.save(folder / 'preparation.json', report)
    # Derive from the already-applied catalog infrastructure but remove all old
    # overrides/plans/state. Preserve live settings and pins, not historic values.
    original = catalog.HOME / 'catalog'
    root = folder / 'infra/terraform'
    shutil.copytree(original / 'infra/terraform', root,
                    ignore=shutil.ignore_patterns('.terraform', '*override.tf.json', '*.tfstate*', '__pycache__'))
    for name in ('apps.tf', 'variables.tf'):
        shutil.copyfile(rt.ROOT / 'infra/terraform' / name, root / name)
    for name in ('infra/models', 'gateway'):
        shutil.copytree(original / name, folder / name, ignore=shutil.ignore_patterns('.terraform', '__pycache__'))
    variables = load(original / 'runtime.tfvars.json')
    for kind in ('api', 'admin', 'customer'):
        variables['apps'][kind]['image'] = baseline['sites'][kind]['image'].removeprefix('DOCKER|').split('/', 1)[1]
    variables.update(ingestion_container_image=build['image'], ingestion_enabled=report['host_enabled'],
                     ingestion_timer_enabled=False, ingestion_start_at=settings['ingestion'].get('AIFLUX_INGESTION_START_AT') or '',
                     ingestion_catalog_accepted=report['catalog_configured'] == 'true')
    rt.save(folder / 'runtime.tfvars.json', variables)
    fs.terraform(root, 'init', '-input=false', '-lockfile=readonly', '-no-color',
                 '-backend-config=' + str(rt.ROOT / 'infra/terraform/backend.hcl'))
    function = fs.preserved_function(root, {k: v for k, v in settings['ingestion'].items()
                                           if k not in catalog.REGISTRY_SETTINGS}, build['image'], settings['ingestion']['AZURE_CLIENT_ID'])
    function['enabled'] = report['host_enabled']
    rt.save(root / 'finops_preserved.tf.json', {'locals': {'finops_preserved_web_settings':
                                                         fs.literal(fs.preserved_web_settings(settings))}})
    rt.save(root / 'zzzz_ingestion_image_override.tf.json', {'resource': {
        'azurerm_linux_web_app': {'main': {'app_settings': '${local.finops_preserved_web_settings[each.key]}'}},
        'azurerm_linux_function_app': {'ingestion': function}}})
    fs.terraform(root, 'validate', '-no-color')
    rt.require(fs.terraform(root, 'workspace', 'show').strip() == 'default', 'wrong_workspace')
    plan = folder / 'image-only.tfplan'
    fs.terraform(root, 'plan', '-input=false', '-no-color', '-lock-timeout=60s',
                 '-var-file=' + str(rt.HOME / 'rebuild-platform.tfvars.json'),
                 '-var-file=' + str(folder / 'runtime.tfvars.json'),
                 '-var-file=' + str(rt.HOME / 'jwt-runtime.tfvars.json'), '-target=' + fs.FUNCTION, '-out=' + str(plan))
    parsed = load_plan(folder)
    report['plan_sha256'] = release.digest(plan.read_bytes())
    report['managed_changes'] = [{'address': r['address'], 'actions': r['change']['actions']}
                                 for r in parsed.get('resource_changes', []) if r['change']['actions'] != ['no-op']]
    try:
        guard(parsed, build['image'], host)
        rt.require(report['scanner']['exit_code'] == 0
               and report['scanner']['summary']['failed'] == 0
               and report['scanner']['summary']['parsing_errors'] == 0
               and [x['check_id'] for x in report['scanner']['skipped_checks']] == ['CKV_DOCKER_3'],
               'security_scanner_findings_require_review')
    except RuntimeError as exc:
        report.update(status='blocked', reason=str(exc))
        rt.save(folder / 'preparation.json', report)
        print(json.dumps({'evidence': (folder / 'preparation.json').relative_to(rt.ROOT).as_posix(), **report}), flush=True)
        return 2
    report.update(status='prepared', guard='passed', artifacts={p.relative_to(folder).as_posix(): release.digest(p.read_bytes())
                  for p in folder.rglob('*') if p.is_file() and '.terraform' not in p.parts})
    rt.save(folder / 'review.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'artifacts'}), flush=True)
    return 0


def load_plan(folder):
    return json.loads(fs.terraform(folder / 'infra/terraform', 'show', '-json', str(folder / 'image-only.tfplan')))


def validate(tag):
    folder = rt.HOME / 'finops' / tag / PLAN_FOLDER
    proof = load(folder / 'review.json')
    rt.require(proof['controller_sha256'] == release.digest(Path(__file__).read_bytes()), 'controller_changed')
    rt.require(0 <= (datetime.now(UTC) - datetime.fromisoformat(proof['at_utc'])).total_seconds() < 3600, 'plan_expired')
    rt.require(build_proof(tag) == proof['build'], 'source_image_binding_changed')
    for name, digest in proof['artifacts'].items():
        rt.require(release.digest((folder / name).read_bytes()) == digest, 'artifact_changed')
    rt.require(portals.baseline() == load(folder / 'baseline.json'), 'protected_baseline_changed')
    rt.require({k: fs.sha(v) for k, v in fs.current_settings().items()} == proof['settings_hashes'], 'full_settings_changed')
    rt.require(safety(load(folder / 'baseline.json')) == proof['security'], 'network_protection_changed')
    fs.terraform(folder / 'infra/terraform', 'validate', '-no-color')
    host = host_provenance()
    rt.require(proof['host_provenance'] == {k: v for k, v in host.items()
               if k not in ('resource', 'baseline', 'settings_hashes')}, 'host_provenance_changed')
    guard(load_plan(folder), proof['build']['image'], host)
    result = {'at_utc': fs.stamp(), 'plan_sha256': proof['plan_sha256'], 'all_checks_passed': True}
    rt.save(folder / 'validation.json', result)
    print(json.dumps(result), flush=True)


def apply(tag):
    folder = rt.HOME / 'finops' / tag / PLAN_FOLDER
    rt.require(not (folder / 'apply-intent.json').exists(), 'prior_apply_intent_no_replay')
    proof = load(folder / 'review.json')
    doc = (rt.ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
    rt.require(load(rt.ROOT / '.azure/validate-status.json')['completedStep'] == 'UpdateStatus'
               and 'FinOps ingestion image-only status: Validated' in doc and proof['plan_sha256'] in doc,
               'fresh_sequential_validation_required')
    rt.require(load(folder / 'validation.json')['plan_sha256'] == proof['plan_sha256'], 'validation_required')
    validate(tag)
    rt.save(folder / 'apply-intent.json', {'at_utc': fs.stamp(), 'plan_sha256': proof['plan_sha256']})
    fs.terraform(folder / 'infra/terraform', 'apply', '-input=false', '-no-color', str(folder / 'image-only.tfplan'))
    rt.save(folder / 'applied.json', {'at_utc': fs.stamp(), 'plan_sha256': proof['plan_sha256'], 'applied': True})
    verify(tag)


def verify(tag):
    folder = rt.HOME / 'finops' / tag / PLAN_FOLDER
    proof = load(folder / 'review.json')
    expected = load(folder / 'baseline.json')
    expected['sites']['ingestion']['image'] = 'DOCKER|' + proof['build']['image']
    rt.require(portals.baseline() == expected, 'protected_readback_mismatch')
    rt.require({k: fs.sha(v) for k, v in fs.current_settings().items()} == proof['settings_hashes'], 'full_settings_readback_mismatch')
    rt.require(safety(expected) == proof['security'], 'network_readback_mismatch')
    report = {'at_utc': fs.stamp(), 'image': proof['build']['image'], 'plan_sha256': proof['plan_sha256'],
              'protected_baseline_and_complete_settings': 'verified', 'host_enabled': proof['host_enabled'],
              'timer_enabled': False, 'catalog_configured': proof['catalog_configured'] == 'true',
              'cutoff': proof['host_provenance']['boundary'], 'cutoff_present': proof['cutoff_present'],
              'host_plan_sha256': proof['host_provenance']['plan_sha256'], 'live_ingestion_healthy': False}
    rt.save(folder / ('verification-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json'), report)
    print(json.dumps(report), flush=True)


def audit(tag):
    host = host_provenance()
    print(json.dumps({k: v for k, v in host.items() if k not in ('resource', 'baseline', 'settings_hashes')}), flush=True)
    scanner = scan()
    rt.save(rt.ROOT / 'gateway/validation/finops-functions-security-scan-20261027.json', scanner)
    print(json.dumps(scanner), flush=True)
    rt.require(scanner['exit_code'] == 0, 'scanner_failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'validate', 'apply', 'verify', 'audit'])
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    try:
        result = {'plan': prepare, 'validate': validate, 'apply': apply, 'verify': verify, 'audit': audit}[args.action](args.tag)
        raise SystemExit(result or 0)
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc) if isinstance(exc, RuntimeError)
                          else 'protected_operation_failed', 'exception_type': type(exc).__name__}), flush=True)
        raise SystemExit(2)