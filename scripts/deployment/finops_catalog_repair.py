"""Finite ingestion-only catalog repair. Never reads provider credentials."""
from __future__ import annotations

import argparse
import json
import os
import copy
import re
import shutil
import subprocess
from pathlib import Path
from datetime import UTC, datetime

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import finops_release as release
from scripts.deployment import portal_fix as portals

BASE_TAG = 'finops-20261027t040422z'
CATALOG_PATH = '/home/site/wwwroot/gateway/catalog/ingestion-approved.json'
HOME = rt.HOME / 'finops/catalog-repair'
REGISTRY_SETTINGS = {'DOCKER_REGISTRY_SERVER_URL': 'https://' + release.REGISTRY,
                     'DOCKER_REGISTRY_SERVER_USERNAME': '', 'DOCKER_REGISTRY_SERVER_PASSWORD': ''}
TIMER_IMAGE_PLAN = '34cfcd4883bbfe6848b6a35c443bf56189d2770241149597ea5e3d95e753e6b3'
TIMER_IMAGE_TAG = 'finops-20261027t062458z'
TIMER_IMAGE = release.REGISTRY + '/aiflux-ingestion@sha256:d2bdae4edbd2faf0f6c5a5b28c83882e36222767f88de9625071b251d4114c0b'
DATAPLANE_EVIDENCE = 'gateway/validation/finops-dataplane-execution-b70760141b5d.json'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def expected_catalog():
    import importlib.util
    spec = importlib.util.spec_from_file_location('approved_catalog', rt.ROOT / 'services/usage-ingestion/approved_catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = module.build(rt.ROOT)
    rt.require(load(rt.ROOT / 'services/usage-ingestion/ingestion-approved.json') == expected,
               'committed_catalog_inventory_drift')
    return expected


def catalog_proof():
    os.environ['REQUESTS_CA_BUNDLE'] = rt.CA
    from scripts.deployment.project_route_live import CandidateRun
    from scripts.deployment.finops_activation_preflight import published_aliases, POLICY_SHA256
    arm = CandidateRun()
    policy = arm.arm('/apis/aiflux-dev-unified/policies/policy?format=rawxml')['properties']['value']
    rt.require(release.digest(policy.encode()) == POLICY_SHA256, 'live_policy_drift')
    catalog = expected_catalog()
    aliases = [m['id'] for m in catalog['models'] if m['enabled']]
    rt.require(len(aliases) == 11 and set(aliases) == set(published_aliases(policy)), 'live_catalog_membership')
    backends = {x['name']: x['properties']['url'] for x in arm.arm('/backends')['value']}
    bindings = load(rt.ROOT / 'services/usage-ingestion/catalog-bindings.json')
    rt.require(backends['aiflux-project-gpt-5-6-luna'] == bindings['foundry']['url']
               and backends['aiflux-external-glm-5-3'] == bindings['external']['url'], 'backend_binding_drift')
    resource = rt.RG + '/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry'
    account = rt.cli(['rest', '--method', 'get', '--url', 'https://management.azure.com' + resource + '?api-version=2024-10-01'])
    rt.require(account['location'] == bindings['foundry']['region'], 'account_region_drift')
    content = (rt.ROOT / 'services/usage-ingestion/ingestion-approved.json').read_bytes()
    return {'aliases': sorted(aliases), 'catalog_sha256': release.digest(content),
            'live_policy_sha256': POLICY_SHA256, 'catalog_path': CATALOG_PATH,
            'decision_selectable': False, 'prices_invented': False}


def build():
    proof = catalog_proof()
    rt.require(not (HOME / 'build.json').exists(), 'build_already_submitted_reconcile')
    fs.protect(HOME)
    manifest = release.source_manifest()['components']['ingestion']
    original = load(rt.HOME / 'finops' / BASE_TAG / 'source-manifest.json')
    current = release.source_manifest()
    rt.require(all(current['components'][k] == original['components'][k] for k in ('api', 'admin', 'customer')),
               'unchanged_three_sources_required')
    context = HOME / 'context'
    for entry in manifest['entries']:
        target = context / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rt.ROOT / entry['path'], target)
        rt.require(release.digest(target.read_bytes()) == entry['sha256'], 'context_hash')
    rt.save(HOME / 'manifest.json', manifest)
    tag = 'finops-catalog-' + datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')
    result = {'at_utc': fs.stamp(), 'tag': tag, 'submissions': 1, 'catalog': proof,
              'source_sha256': manifest['source_sha256'], 'status': 'submission_intent'}
    rt.save(HOME / 'build.json', result)
    process = subprocess.run(rt.CLI + ['acr', 'build', '--registry', 'pocidstokenexacr', '--subscription', rt.SUB,
        '--platform', 'linux/amd64', '--timeout', '1800', '--file', 'services/usage-ingestion/Dockerfile',
        '--image', 'aiflux-ingestion:' + tag, '.'], cwd=context, env=rt.ENV, capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=2100)
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', process.stdout + process.stderr)
    (HOME / 'build.log').write_text(text, encoding='utf-8')
    runs = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
    result.update(exit_code=process.returncode, run_id=runs[-1] if runs else None)
    rt.save(HOME / 'build.json', result)
    rt.require(process.returncode == 0 and result['run_id'], 'build_failed_no_resubmission')
    run = rt.cli(['acr', 'task', 'show-run', '--registry', 'pocidstokenexacr', '--subscription', rt.SUB, '--run-id', result['run_id']])
    rt.require(run['status'] == 'Succeeded' and len(run['outputImages']) == 1, 'successful_native_build_required')
    item = run['outputImages'][0]
    rt.require(item['repository'] == 'aiflux-ingestion' and item['tag'] == tag and item['registry'] == release.REGISTRY, 'build_output_binding')
    result.update(status='Succeeded', image=release.REGISTRY + '/aiflux-ingestion@' + item['digest'],
                  finish_time=run['finishTime'], native_linux_validation=True)
    rt.save(HOME / 'build.json', result)
    print(json.dumps(result), flush=True)


def verified_build():
    b = load(HOME / 'build.json')
    rt.require(b['status'] == 'Succeeded' and b['submissions'] == 1 and b['exit_code'] == 0, 'build_not_verified')
    manifest = release.source_manifest()['components']['ingestion']
    rt.require(manifest == load(HOME / 'manifest.json'), 'ingestion_source_drift')
    for entry in manifest['entries']:
        rt.require(release.digest((HOME / 'context' / entry['path']).read_bytes()) == entry['sha256'], 'retained_context_drift')
    rt.require(catalog_proof() == b['catalog'], 'catalog_proof_changed')
    run = rt.cli(['acr', 'task', 'show-run', '--registry', 'pocidstokenexacr', '--subscription', rt.SUB, '--run-id', b['run_id']])
    rt.require(run['status'] == 'Succeeded' and run['finishTime'] == b['finish_time']
               and any(release.REGISTRY + '/aiflux-ingestion@' + i['digest'] == b['image'] for i in run['outputImages']), 'remote_build_drift')
    return b


def target_settings(mode, current, boundary=None):
    target = dict(current)
    rt.require(all(current.get(k) == v for k, v in REGISTRY_SETTINGS.items()), 'registry_settings_must_match')
    if mode == 'catalog':
        rt.require(current.get('AzureWebJobs.ingest_usage.Disabled') == 'true'
                   and not current.get('AIFLUX_INGESTION_START_AT'), 'disabled_no_cutoff_required')
        target['AIFLUX_CATALOG_PATH'] = CATALOG_PATH
    elif mode == 'host':
        rt.require(current.get('AIFLUX_CATALOG_PATH') == CATALOG_PATH
                   and current.get('AIFLUX_CATALOG_CONFIGURED') == 'false'
                   and current.get('AzureWebJobs.ingest_usage.Disabled') == 'true'
                   and not current.get('AIFLUX_INGESTION_START_AT'), 'catalog_stage_required')
        parsed = datetime.fromisoformat(boundary)
        rt.require(parsed.tzinfo is not None, 'utc_boundary_required')
        target.update(AIFLUX_CATALOG_CONFIGURED='true', AIFLUX_INGESTION_START_AT=boundary)
    elif mode == 'timer':
        rt.require(current.get('AIFLUX_CATALOG_CONFIGURED') == 'true'
                   and current.get('AIFLUX_CATALOG_PATH') == CATALOG_PATH
                   and current.get('AzureWebJobs.ingest_usage.Disabled') == 'true'
                   and current.get('AIFLUX_INGESTION_START_AT') == boundary, 'healthy_host_boundary_required')
        target['AzureWebJobs.ingest_usage.Disabled'] = 'false'
    else:
        raise RuntimeError('invalid_stage')
    return target


def guard(plan, mode, image, target, enabled, applied_resource=None):
    rt.require(plan.get('applyable') is True and not plan.get('errored') and not plan.get('deferred_changes'), 'unresolved_plan')
    seen = []
    for resource in plan.get('resource_changes', []):
        c = resource['change']
        if c['actions'] == ['no-op']:
            continue
        rt.require(resource['address'] == fs.FUNCTION and resource.get('mode') == 'managed'
                   and c['actions'] == ['update'], 'function_only_update_required')
        seen.append(resource['address'])
        before, after = copy.deepcopy(c['before']), copy.deepcopy(c['after'])
        if applied_resource is not None:
            rt.require(mode == 'timer' and
                       {k: v for k, v in before.items() if k not in fs.COMPUTED} ==
                       {k: v for k, v in applied_resource.items() if k not in fs.COMPUTED},
                       'exact_applied_image_resource_required')
        unknown = c.get('after_unknown') or {}
        rt.require(not any(release.any_unknown(v) for k, v in unknown.items() if k not in fs.COMPUTED), 'unknown_writable_input')
        for key in fs.COMPUTED:
            if release.any_unknown(unknown.get(key)):
                after[key] = before.get(key)
        expected = {k: v for k, v in target.items() if k not in REGISTRY_SETTINGS}
        for name, field in {'AzureWebJobsStorage__accountName': 'storage_account_name',
                            'FUNCTIONS_EXTENSION_VERSION': 'functions_extension_version'}.items():
            if name not in before['app_settings']:
                rt.require(expected.pop(name) == before[field], 'provider_owned_setting')
        rt.require(after['app_settings'] == expected and after['enabled'] is enabled, 'exact_settings_and_host_required')
        oldsettings = {**before['app_settings'], **REGISTRY_SETTINGS}
        for name, field in {'AzureWebJobsStorage__accountName': 'storage_account_name',
                            'FUNCTIONS_EXTENSION_VERSION': 'functions_extension_version'}.items():
            oldsettings.setdefault(name, before[field])
        boundary = target.get('AIFLUX_INGESTION_START_AT')
        rt.require(target_settings(mode, oldsettings, boundary) == target, 'finite_transition_mismatch')
        rt.require(before['enabled'] is (mode == 'timer'), 'unexpected_initial_host')
        after['app_settings'] = before['app_settings']
        after['enabled'] = before['enabled']
        oldstack = before['site_config'][0]['application_stack'][0]
        newstack = after['site_config'][0]['application_stack'][0]
        repo, pin = image.split('@sha256:')
        docker = newstack['docker'][0]
        rt.require(docker['image_name'] == repo.split('/', 1)[1] + '@sha256' and docker['image_tag'] == pin
                   and docker['registry_url'] == 'https://' + release.REGISTRY
                   and not docker.get('registry_username') and not docker.get('registry_password'), 'exact_immutable_ingestion_image')
        if mode == 'catalog':
            newstack['docker'][0]['image_name'] = oldstack['docker'][0]['image_name']
            newstack['docker'][0]['image_tag'] = oldstack['docker'][0]['image_tag']
        rt.require(before == after, 'unapproved_configuration_change')
    rt.require(seen == [fs.FUNCTION], 'exact_single_update_required')


def timer_provenance(b, image_tag):
    """Bind the approved actual image apply and substantive MI proof, not old HTTP binding."""
    from scripts.deployment import finops_ingestion_image_repair as image
    rt.require(image_tag == TIMER_IMAGE_TAG and b['image'] == TIMER_IMAGE, 'approved_timer_image_required')
    folder = rt.HOME / 'finops' / image_tag / image.PLAN_FOLDER
    review = load(folder / 'review.json')
    rt.require(review['plan_sha256'] == TIMER_IMAGE_PLAN and review['build'] == b,
               'exact_applied_image_required')
    for name in ('validation.json', 'apply-intent.json', 'applied.json'):
        rt.require(load(folder / name)['plan_sha256'] == TIMER_IMAGE_PLAN, 'image_marker_plan_mismatch')
    rt.require(load(folder / 'applied.json')['applied'] is True and
               load(folder / 'validation.json')['all_checks_passed'] is True, 'validated_image_apply_required')
    for name, digest in review['artifacts'].items():
        rt.require(release.digest((folder / name).read_bytes()) == digest, 'image_provenance_artifact_changed')
    rt.require(release.digest((folder / 'image-only.tfplan').read_bytes()) == TIMER_IMAGE_PLAN,
               'image_saved_plan_changed')
    host = image.host_provenance()
    rt.require(review['host_provenance'] == {k: v for k, v in host.items()
               if k not in ('resource', 'baseline', 'settings_hashes')}, 'image_host_provenance_changed')
    parsed = image.load_plan(folder)
    image.guard(parsed, b['image'], host)
    resource = copy.deepcopy(next(r['change']['after'] for r in parsed['resource_changes'] if r['address'] == fs.FUNCTION))
    # Provider retained the old computed linux_fx_version in the image-only plan;
    # the applied docker input and ARM baseline independently bind the new digest.
    fx = resource['site_config'][0]['linux_fx_version']
    rt.require(fx in (host['baseline']['sites']['ingestion']['image'], 'DOCKER|' + b['image']),
               'unexpected_applied_computed_image')
    resource['site_config'][0]['linux_fx_version'] = 'DOCKER|' + b['image']
    baseline = load(folder / 'baseline.json')
    baseline['sites']['ingestion']['image'] = 'DOCKER|' + b['image']
    rt.require(review['host_enabled'] is True and review['timer_disabled'] == 'true'
               and review['catalog_configured'] == 'true'
               and review['settings_hashes'] == host['settings_hashes'], 'image_settings_provenance_changed')
    evidence_path = rt.ROOT / DATAPLANE_EVIDENCE
    evidence = load(evidence_path)
    probe = evidence['probes']['ingestion']
    result = probe['sanitized_result']
    rt.require(evidence['owner_nonce'] == 'b70760141b5d' and evidence['exit_code'] == 0
               and probe['os_exit_code'] == 0 and probe['probe_exit_code'] == 0
               and result['status'] == 'verified_data_plane'
               and result['identity_source'] == 'explicit_ingestion_managed_identity'
               and result['database_writes'] == 0 and result['storage_writes'] == 0
               and set(result['checks']) == {'postgres', 'monitor', 'blob', 'queue', 'table'}
               and all(c['status'] == 'passed' and c['stage'] == 'complete' and c['claims_verified'] is True
                       and c['reason'] == 'verified' for c in result['checks'].values())
               and all(result['checks'][k]['http_status'] == 200 for k in ('monitor', 'blob', 'queue', 'table')),
               'substantive_ingestion_MI_dataplane_proof_required')
    rt.require(evidence['cleanup']['exit_code'] == 0 and len(evidence['cleanup']['absence']) == 6
               and all(c['http_status'] == 404 for c in evidence['cleanup']['absence']), 'probe_cleanup_required')
    return {'baseline': baseline, 'settings_hashes': review['settings_hashes'], 'resource': resource,
            'boundary': host['boundary'], 'dataplane_sha256': release.digest(evidence_path.read_bytes())}


def stage_build(mode, image_tag=None):
    """Use the actually applied correction for timer enablement, never cm1t."""
    if image_tag is None:
        rt.require(mode != 'timer', 'timer_requires_explicit_applied_image_tag')
        return verified_build()
    rt.require(mode == 'timer', 'corrected_image_only_for_timer_stage')
    from scripts.deployment import finops_ingestion_image_repair as image
    b = image.build_proof(image_tag)
    timer_provenance(b, image_tag)
    return b


def prepare(mode, image_tag=None):
    b = stage_build(mode, image_tag)
    folder = HOME / mode
    if folder.exists():
        rt.require(not any((folder / n).exists() for n in ('review.json', 'apply-intent.json', 'applied.json')), 'stage_exists_no_overwrite')
        parsed = json.loads(fs.terraform(folder / 'infra/terraform', 'show', '-json', str(folder / 'stage.tfplan')))
        if mode == 'timer' and parsed.get('applyable') is True:
            prior = timer_provenance(b, image_tag)
            target = target_settings('timer', load(HOME / 'host/target-settings.json'), prior['boundary'])
            guard(parsed, 'timer', b['image'], target, True, prior['resource'])
        else:
            rt.require(parsed.get('errored') is True and parsed.get('applyable') is False, 'only_failed_unreviewed_plan_can_be_archived')
        folder.rename(HOME / (mode + '-failed-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')))
    fs.protect(folder)
    baseline = portals.baseline()
    settings = fs.current_settings()
    provenance = timer_provenance(b, image_tag) if mode == 'timer' else None
    if provenance is not None:
        rt.require(baseline == provenance['baseline'] and
                   {k: fs.sha(v) for k, v in settings.items()} == provenance['settings_hashes'],
                   'live_baseline_not_exact_applied_image')
    boundary = None
    if mode == 'host':
        rt.require((HOME / 'catalog/applied.json').exists(), 'catalog_apply_required')
        # One future boundary, selected only now after immutable membership proof.
        from datetime import timedelta
        if (HOME / 'boundary.json').exists():
            boundary = load(HOME / 'boundary.json')['start_at']
            rt.require(datetime.fromisoformat(boundary) > datetime.now(UTC), 'persisted_boundary_expired')
        else:
            boundary = (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
            rt.save(HOME / 'boundary.json', {'start_at': boundary, 'selected_at': fs.stamp(),
                'mode': 'forward_only', 'historical_requests_deferred': 156, 'historical_tokens_deferred': 11143,
                'watermark_reset': False, 'reason': 'fresh future boundary before host startup; overlap clamped by runtime'})
    elif mode == 'timer':
        boundary = provenance['boundary']
    target = target_settings(mode, settings['ingestion'], boundary)
    original = rt.HOME / 'finops' / BASE_TAG / fs.STAGE_NAME
    root = folder / 'infra/terraform'
    shutil.copytree(original / 'infra/terraform', root, ignore=shutil.ignore_patterns('.terraform', '*override.tf.json', '*.tfstate*'))
    for name in ('apps.tf', 'variables.tf'):
        shutil.copyfile(rt.ROOT / 'infra/terraform' / name, root / name)
    for name in ('infra/models', 'gateway'):
        shutil.copytree(original / name, folder / name)
    variables = load(original / 'runtime.tfvars.json')
    variables.update(ingestion_container_image=b['image'], ingestion_enabled=mode != 'catalog',
                     ingestion_timer_enabled=mode == 'timer', ingestion_start_at=boundary or '',
                     ingestion_catalog_accepted=mode != 'catalog')
    rt.save(folder / 'runtime.tfvars.json', variables)
    fs.terraform(root, 'init', '-input=false', '-lockfile=readonly', '-no-color', '-backend-config=' + str(rt.ROOT / 'infra/terraform/backend.hcl'))
    client = target['AZURE_CLIENT_ID']
    function = fs.preserved_function(root, {k: v for k, v in target.items() if k not in REGISTRY_SETTINGS}, b['image'], client)
    function['enabled'] = mode != 'catalog'
    rt.save(root / 'zzzz_finops_catalog_override.tf.json', {'resource': {
        'azurerm_linux_web_app': {'main': {'app_settings': '${local.finops_preserved_web_settings[each.key]}'}},
        'azurerm_linux_function_app': {'ingestion': function}}})
    # Preserve current exact three web settings, not historic generated values.
    rt.save(root / 'finops_preserved.tf.json', {'locals': {'finops_preserved_web_settings': fs.literal(fs.preserved_web_settings(settings))}})
    fs.terraform(root, 'validate', '-no-color')
    rt.require(fs.terraform(root, 'workspace', 'show').strip() == 'default', 'wrong_workspace')
    plan = folder / 'stage.tfplan'
    fs.terraform(root, 'plan', '-input=false', '-no-color', '-lock-timeout=60s',
                 '-var-file=' + str(rt.HOME / 'rebuild-platform.tfvars.json'),
                 '-var-file=' + str(folder / 'runtime.tfvars.json'),
                 '-var-file=' + str(rt.HOME / 'jwt-runtime.tfvars.json'),
                 '-target=' + fs.FUNCTION, '-out=' + str(plan))
    parsed_plan = json.loads(fs.terraform(root, 'show', '-json', str(plan)))
    applied_resource = provenance['resource'] if provenance else None
    guard(parsed_plan, mode, b['image'], target, mode != 'catalog', applied_resource)
    rt.save(folder / 'baseline.json', baseline)
    rt.save(folder / 'target-settings.json', target)
    review = {'at_utc': fs.stamp(), 'mode': mode, 'image': b['image'], 'image_tag': image_tag, 'plan_sha256': release.digest(plan.read_bytes()),
        'controller_sha256': release.digest(Path(__file__).read_bytes()), 'catalog': b['catalog'],
        'settings_hashes': {k: fs.sha(v) for k, v in settings.items()}, 'target_settings_hash': fs.sha(target),
        'changed_setting_names': sorted(portals.changed(settings['ingestion'], target)),
        'enabled': mode != 'catalog', 'boundary': boundary, 'guard': 'passed',
        'dataplane_sha256': provenance['dataplane_sha256'] if provenance else None,
        'artifacts': {p.relative_to(folder).as_posix(): release.digest(p.read_bytes()) for p in folder.rglob('*')
                      if p.is_file() and '.terraform' not in p.parts}}
    rt.save(folder / 'review.json', review)
    print(json.dumps({k: v for k, v in review.items() if k != 'artifacts'}), flush=True)


def validate(mode):
    folder = HOME / mode
    proof = load(folder / 'review.json')
    b = stage_build(mode, proof.get('image_tag'))
    provenance = timer_provenance(b, proof.get('image_tag')) if mode == 'timer' else None
    if provenance is not None:
        rt.require(load(folder / 'baseline.json') == provenance['baseline']
                   and proof['settings_hashes'] == provenance['settings_hashes']
                   and proof['boundary'] == provenance['boundary']
                   and proof['dataplane_sha256'] == provenance['dataplane_sha256'], 'timer_provenance_drift')
    rt.require(proof['controller_sha256'] == release.digest(Path(__file__).read_bytes()), 'controller_changed')
    rt.require(b['image'] == proof['image'], 'build_changed')
    for name, digest in proof['artifacts'].items():
        rt.require(release.digest((folder / name).read_bytes()) == digest, 'artifact_changed')
    rt.require(0 <= (datetime.now(UTC) - datetime.fromisoformat(proof['at_utc'])).total_seconds() < 3600, 'plan_expired')
    rt.require(portals.baseline() == load(folder / 'baseline.json'), 'protected_baseline_drift')
    rt.require({k: fs.sha(v) for k, v in fs.current_settings().items()} == proof['settings_hashes'], 'settings_drift')
    root = folder / 'infra/terraform'
    fs.terraform(root, 'validate', '-no-color')
    guard(json.loads(fs.terraform(root, 'show', '-json', str(folder / 'stage.tfplan'))), mode,
            b['image'], load(folder / 'target-settings.json'), proof['enabled'],
            provenance['resource'] if provenance else None)
    result = {'at_utc': fs.stamp(), 'mode': mode, 'plan_sha256': proof['plan_sha256'],
              'source_build_catalog_baseline_settings_guard': 'passed', 'cloud_writes': 0}
    rt.save(folder / 'validation.json', result)
    print(json.dumps(result), flush=True)


def apply(mode):
    folder = HOME / mode
    rt.require(not (folder / 'apply-intent.json').exists(), 'prior_apply_intent_reconcile_no_replay')
    proof = load(folder / 'review.json')
    status = load(rt.ROOT / '.azure/validate-status.json')
    doc = (rt.ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
    rt.require(status.get('completedStep') == 'UpdateStatus' and proof['plan_sha256'] in doc
               and 'FinOps ' + mode + ' status: Validated' in doc, 'fresh_stage_validation_required')
    rt.require(load(folder / 'validation.json')['plan_sha256'] == proof['plan_sha256'], 'validation_proof_required')
    validate(mode)
    if mode == 'host':
        rt.require(datetime.fromisoformat(proof['boundary']) > datetime.now(UTC), 'prospective_boundary_expired_do_not_apply')
    rt.save(folder / 'apply-intent.json', {'at_utc': fs.stamp(), 'plan_sha256': proof['plan_sha256']})
    fs.terraform(folder / 'infra/terraform', 'apply', '-input=false', '-no-color', str(folder / 'stage.tfplan'))
    rt.save(folder / 'applied.json', {'at_utc': fs.stamp(), 'plan_sha256': proof['plan_sha256'], 'applied': True})
    verify(mode)


def verify(mode):
    folder = HOME / mode
    proof = load(folder / 'review.json')
    baseline = load(folder / 'baseline.json')
    current = portals.baseline()
    baseline['sites']['ingestion']['image'] = 'DOCKER|' + proof['image']
    baseline['sites']['ingestion']['protected']['enabled'] = proof['enabled']
    rt.require(current == baseline, 'post_apply_protected_baseline_mismatch')
    settings = fs.current_settings()
    rt.require(fs.sha(settings['ingestion']) == proof['target_settings_hash'], 'post_apply_ingestion_settings_mismatch')
    rt.require(all(fs.sha(settings[k]) == proof['settings_hashes'][k] for k in ('api', 'admin', 'customer')), 'other_settings_changed')
    result = {'at_utc': fs.stamp(), 'mode': mode, 'protected_baseline_and_all_settings': 'verified',
              'image': proof['image'], 'catalog': proof['catalog'], 'enabled': proof['enabled'],
              'timer_disabled': settings['ingestion']['AzureWebJobs.ingest_usage.Disabled'],
              'boundary': settings['ingestion'].get('AIFLUX_INGESTION_START_AT'),
              'scheduled_successes_verified': 0}
    rt.save(folder / ('verification-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json'), result)
    print(json.dumps(result), flush=True)


def reconcile_expired_unapplied_boundary():
    """Never reset cloud config/watermarks; retain an expired never-applied plan."""
    folder = HOME / 'host'
    proof = load(folder / 'review.json')
    rt.require(not (folder / 'apply-intent.json').exists() and not (folder / 'applied.json').exists(), 'apply_intent_exists_no_replan')
    rt.require(datetime.fromisoformat(proof['boundary']) < datetime.now(UTC), 'boundary_not_expired')
    settings = fs.current_settings()
    rt.require(not settings['ingestion'].get('AIFLUX_INGESTION_START_AT')
               and settings['ingestion'].get('AzureWebJobs.ingest_usage.Disabled') == 'true'
               and {k: fs.sha(v) for k, v in settings.items()} == proof['settings_hashes'], 'cloud_boundary_or_settings_changed')
    rt.require(portals.baseline() == load(folder / 'baseline.json'), 'baseline_changed')
    suffix = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    rt.save(folder / 'superseded-unapplied.json', {'at_utc': fs.stamp(), 'reason': 'boundary_expired_during_failed_precondition_repair',
        'cloud_boundary_absent_verified': True, 'apply_intent_absent': True, 'historical_ingestion_authorized': False,
        'plan_sha256': proof['plan_sha256'], 'expired_candidate': proof['boundary']})
    folder.rename(HOME / ('host-expired-never-applied-' + suffix))
    (HOME / 'boundary.json').rename(HOME / ('boundary-expired-never-applied-' + suffix + '.json'))
    print(json.dumps({'status': 'unapplied_expired_plan_retained', 'cloud_writes': 0, 'watermark_reset': False}), flush=True)


def inspect():
    os.environ['REQUESTS_CA_BUNDLE'] = rt.CA
    from scripts.deployment.project_route_live import CandidateRun
    account = rt.cli(['account', 'show'])
    rt.require(account['id'] == rt.SUB and account['tenantId'] == rt.TENANT, 'account_scope')
    arm = CandidateRun()
    policy = arm.arm('/apis/aiflux-dev-unified/policies/policy?format=rawxml')['properties']['value']
    import re
    backends = arm.arm('/backends')['value']
    safe = [{'name': x['name'], 'url': x['properties'].get('url'),
             'resourceId': x['properties'].get('resourceId')} for x in backends]
    settings = fs.current_settings()
    resource = rt.RG + '/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry'
    foundry = rt.cli(['rest', '--method', 'get', '--url',
                     'https://management.azure.com' + resource + '?api-version=2024-10-01'])
    result = {'at_utc': fs.stamp(), 'subscription': account['id'], 'tenant': account['tenantId'],
              'policy_sha256': release.digest(policy.encode()), 'backends': safe,
              'policy_backend_ids': sorted(set(re.findall(r'<set-backend-service backend-id="([^"]+)"', policy))),
              'foundry_location': foundry['location'],
              'ingestion': {k: settings['ingestion'].get(k) for k in
                            ('AIFLUX_CATALOG_PATH', 'AIFLUX_CATALOG_CONFIGURED',
                             'AzureWebJobs.ingest_usage.Disabled', 'AIFLUX_INGESTION_START_AT')},
              'settings_hashes': {k: fs.sha(v) for k, v in settings.items()}}
    path = rt.ROOT / 'gateway/validation' / ('finops-catalog-inspection-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json')
    rt.save(path, result)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **result}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'build', 'plan', 'validate', 'apply', 'verify', 'reconcile-expired'])
    parser.add_argument('--stage', choices=['catalog', 'host', 'timer'])
    parser.add_argument('--image-tag', help='Exact already-applied corrected ingestion build; timer stage only')
    args = parser.parse_args()
    try:
        if args.action == 'reconcile-expired':
            reconcile_expired_unapplied_boundary()
        elif args.action in ('inspect', 'build'):
            globals()[args.action]()
        else:
            rt.require(args.stage is not None, 'stage_required')
            if args.action == 'plan':
                prepare(args.stage, args.image_tag)
            else:
                rt.require(args.image_tag is None, 'image_tag_bound_in_saved_review')
                {'validate': validate, 'apply': apply, 'verify': verify}[args.action](args.stage)
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'exception_type': type(exc).__name__,
                          'reason': str(exc) if isinstance(exc, RuntimeError) else 'protected_operation_failed'}), flush=True)
        raise SystemExit(2)