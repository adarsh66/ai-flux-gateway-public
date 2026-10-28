import copy
import importlib.util
import json
from pathlib import Path

import pytest
from scripts.deployment import finops_catalog_repair as repair

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('approved_catalog', ROOT / 'services/usage-ingestion/approved_catalog.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def test_committed_catalog_matches_reviewed_generator_and_published_membership():
    from aiflux.catalog import Catalog

    path = ROOT / 'services/usage-ingestion/ingestion-approved.json'
    result = json.loads(path.read_text())
    assert result == catalog.build(ROOT)
    parsed = Catalog.load(path)
    expected = {
        'DeepSeek-V4-Flash', 'Kimi-K2.7-Code', 'glm-5.3', 'gpt-4o',
        'gpt-5.4-mini', 'gpt-6.1-sol', 'grok-4-1-fast-reasoning',
        'grok-4-20-reasoning', 'grok-4.3', 'gpt-5.6-luna', 'DeepSeek-V4-Pro',
    }
    published = json.loads((ROOT / 'gateway/validation/finops-activation-preflight-20261027T050908517678Z.json').read_text())
    assert expected == set(published['catalog']['live_published_aliases'])
    assert {m.id for m in parsed.models if m.enabled} == expected | set(catalog.FIREWORKS)
    assert not any(m.enabled and (m.placeholder or m.id == 'Decision-1') for m in parsed.models)


def test_ingester_copies_accepted_source_to_both_existing_paths():
    dockerfile = (ROOT / 'services/usage-ingestion/Dockerfile').read_text()
    source = 'services/usage-ingestion/ingestion-approved.json'
    assert f'COPY {source} ./gateway/catalog/dev-models.json' in dockerfile
    assert f'COPY {source} ./gateway/catalog/ingestion-approved.json' in dockerfile
    assert 'COPY gateway/catalog/dev-models.json' not in dockerfile


def test_catalog_source_is_manifest_bound_only_to_ingestion():
    from scripts.deployment.finops_release import source_manifest

    source = 'services/usage-ingestion/ingestion-approved.json'
    manifests = source_manifest()['components']
    for kind, manifest in manifests.items():
        assert (source in {e['path'] for e in manifest['entries']}) is (kind == 'ingestion')


def test_release_catalog_proof_hashes_actual_source_bytes_without_cloud_calls(monkeypatch):
    from types import SimpleNamespace
    from scripts.deployment import finops_activation_preflight as preflight
    from scripts.deployment import project_route_live

    result = repair.expected_catalog()
    policy = '<set-body>' + json.dumps({'data': [{'id': m['id']} for m in result['models'] if m['enabled']]}) + '</set-body>'
    monkeypatch.setattr(preflight, 'POLICY_SHA256', repair.release.digest(policy.encode()))
    bindings = json.loads((ROOT / 'services/usage-ingestion/catalog-bindings.json').read_text())
    backends = [{'name': name, 'properties': {'url': bindings[kind]['url']}}
                for kind, name in [('foundry', 'aiflux-project-gpt-5-6-luna'), ('external', 'aiflux-external-glm-5-3')]]

    def arm(path):
        if path == '/backends':
            return {'value': backends}
        assert path == '/apis/aiflux-dev-unified/policies/policy?format=rawxml'
        return {'properties': {'value': policy}}

    monkeypatch.setattr(project_route_live, 'CandidateRun', lambda: SimpleNamespace(arm=arm))
    monkeypatch.setattr(repair.rt, 'cli', lambda *_: {'location': bindings['foundry']['region']})
    # Never broaden/replay the historical eleven-model activation controller.
    with pytest.raises(RuntimeError, match='live_catalog_membership'):
        repair.catalog_proof()


@pytest.mark.parametrize('defect', [None, 'provider', 'region', 'backend_model', 'alias', 'decision', 'duplicate'])
@pytest.mark.parametrize('filename', ['dev-models.json', 'ingestion-approved.json'])
def test_packaging_verifies_both_paths_without_regeneration(tmp_path, defect, filename):
    for name in ['gateway/catalog/foundry-inventory-20261026.json', 'gateway/catalog/project-routes.json',
                 'gateway/catalog/fireworks-candidate-routes.json',
                 'gateway/catalog/external-inventory.json', 'services/usage-ingestion/catalog-bindings.json']:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    result = catalog.build(tmp_path)
    for name in ('dev-models.json', 'ingestion-approved.json'):
        (tmp_path / 'gateway/catalog' / name).write_text(json.dumps(result))
    path = tmp_path / 'gateway/catalog' / filename
    if defect:
        changed = copy.deepcopy(result)
        if defect == 'decision':
            changed['models'][-1]['enabled'] = True
            changed['models'][0]['enabled'] = False  # Still eleven enabled: must fail.
        elif defect == 'duplicate':
            changed['models'][0] = copy.deepcopy(changed['models'][1])
        else:
            changed['models'][0]['id' if defect == 'alias' else defect] = 'foreign'
        path.write_text(json.dumps(changed))
    before = path.read_bytes()
    if defect:
        with pytest.raises(ValueError, match='differs from reviewed inventory'):
            catalog.verify_packaged(tmp_path)
    else:
        catalog.verify_packaged(tmp_path)
    assert path.read_bytes() == before


def test_accepted_bindings_match_retained_apim_and_account_inspection():
    bindings = json.loads((ROOT / 'services/usage-ingestion/catalog-bindings.json').read_text())
    evidence = json.loads((ROOT / bindings['evidence']).read_text())
    backends = {b['name']: b['url'] for b in evidence['backends']}
    assert bindings['live_policy_sha256'] == evidence['policy_sha256']
    assert bindings['foundry']['url'] == backends['aiflux-project-gpt-5-6-luna']
    assert bindings['external']['url'] == backends['aiflux-external-glm-5-3']
    assert bindings['foundry']['region'] == evidence['foundry_location']
    assert bindings['external']['url'].split('/')[2] == 'api-' + bindings['external']['region'] + '.modelarts-maas.com'
    project = json.loads((ROOT / 'gateway/catalog/project-routes.json').read_text())
    project['routes'].update(json.loads((ROOT / 'gateway/catalog/fireworks-candidate-routes.json').read_text())['routes'])
    external = json.loads((ROOT / 'gateway/catalog/external-inventory.json').read_text())['routes'][0]
    for model in catalog.build(ROOT)['models']:
        if not model['enabled']:
            continue
        approved = external if model['id'] == external['alias'] else project['routes'][model['id']]
        assert model['provider'] == approved['provider']
        assert model['backend_model'] == (external['backend_model'] if model['id'] == external['alias'] else model['id'])


def test_glm_unknown_price_stays_null_with_accepted_catalog(env):
    from datetime import UTC, datetime
    from aiflux.catalog import Catalog
    from aiflux.ingestion import ingest_rows
    from aiflux.models import UsageRecord
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from test_control_plane import create_key

    key = create_key(env)
    source = {'subscription_id': key['id'], 'correlation_id': 'accepted-glm-price-unknown',
              'resource_id': env.settings.apim_resource_id, 'occurred_at': datetime.now(UTC),
              'model': 'glm-5.3', 'backend_id': 'aiflux-external-glm-5-3',
              'gateway_region': 'not-the-provider-region', 'status_code': 200,
              'input_tokens': 25, 'output_tokens': 52}
    with Session(env.db_engine) as db:
        ingest_rows(db, [source], Catalog.load(ROOT / 'services/usage-ingestion/ingestion-approved.json'))
        db.commit()
        row = db.scalar(select(UsageRecord))
        assert (row.model, row.provider, row.region) == ('glm-5.3', 'ModelArts', 'ap-southeast-1')
        assert row.cost is None and row.currency is None and row.completeness == 'price_missing'


def test_approved_catalog_exact_membership_and_bindings():
    result = catalog.build(ROOT)
    routes = json.loads((ROOT / 'gateway/catalog/project-routes.json').read_text())['routes']
    enabled = [m for m in result['models'] if m['enabled']]
    assert {m['id'] for m in enabled} == set(routes) | set(catalog.FIREWORKS) | {'glm-5.3'}
    assert len(enabled) == 13
    assert all(m['backend_model'] == m['id'] for m in enabled)
    assert all(m['region'] == ('ap-southeast-1' if m['id'] == 'glm-5.3' else 'eastus') for m in enabled)
    assert not next(m for m in result['models'] if m['id'] == 'Decision-1')['enabled']
    assert all(not any('price' in k or 'cost' in k for k in m) for m in result['models'])


@pytest.mark.parametrize('defect', ['provider', 'version', 'enabled', 'endpoint', 'decision'])
def test_inventory_drift_rejected(tmp_path, defect):
    for name in ['gateway/catalog/foundry-inventory-20261026.json', 'gateway/catalog/project-routes.json',
                 'gateway/catalog/fireworks-candidate-routes.json',
                 'gateway/catalog/external-inventory.json', 'services/usage-ingestion/catalog-bindings.json']:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    path = tmp_path / 'gateway/catalog/foundry-inventory-20261026.json'
    data = json.loads(path.read_text())
    if defect == 'provider':
        data['deployments'][1]['model_format'] = 'wrong'
    elif defect == 'version':
        data['routes'][0]['model_version'] = 'wrong'
    elif defect == 'enabled':
        data['routes'][0]['gateway_validated'] = False
    elif defect == 'endpoint':
        data['routes'][0]['endpoint_url'] = 'https://wrong.invalid'
    else:
        data['deployments'][0]['chat_completion'] = True
    path.write_text(json.dumps(data))
    with pytest.raises(AssertionError):
        catalog.build(tmp_path)


def stage_fixture(mode):
    settings = {'AIFLUX_CATALOG_PATH': 'old', 'AIFLUX_CATALOG_CONFIGURED': 'false',
                'AzureWebJobs.ingest_usage.Disabled': 'true', 'preserved': 'exact',
                'AzureWebJobsStorage__accountName': 'storage', 'FUNCTIONS_EXTENSION_VERSION': '~4'}
    boundary = '2026-10-27T06:00:00+00:00'
    if mode != 'catalog':
        settings['AIFLUX_CATALOG_PATH'] = repair.CATALOG_PATH
    if mode == 'timer':
        settings.update(AIFLUX_CATALOG_CONFIGURED='true', AIFLUX_INGESTION_START_AT=boundary)
    target = repair.target_settings(mode, {**settings, **repair.REGISTRY_SETTINGS}, boundary)
    before = {'enabled': mode == 'timer', 'app_settings': settings,
              'storage_account_name': 'storage', 'functions_extension_version': '~4',
              'identity': ['original'], 'network': 'private',
              'site_config': [{'minimum_tls_version': '1.2', 'application_stack': [{'docker': [{
                  'registry_url': 'https://' + repair.release.REGISTRY, 'image_name': 'aiflux-ingestion@sha256',
                  'image_tag': 'a' * 64, 'registry_username': '', 'registry_password': ''}]}]}]}
    after = copy.deepcopy(before)
    after['enabled'] = mode != 'catalog'
    after['app_settings'] = {k: v for k, v in target.items() if k not in repair.REGISTRY_SETTINGS}
    if mode == 'catalog':
        after['site_config'][0]['application_stack'][0]['docker'][0]['image_tag'] = 'b' * 64
    image = repair.release.REGISTRY + '/aiflux-ingestion@sha256:' + ('b' if mode == 'catalog' else 'a') * 64
    plan = {'applyable': True, 'resource_changes': [{'address': repair.fs.FUNCTION,
            'mode': 'managed', 'change': {'actions': ['update'], 'before': before, 'after': after, 'after_unknown': {}}}]}
    return plan, image, target


@pytest.mark.parametrize('mode', ['catalog', 'host', 'timer'])
def test_finite_single_function_stages(mode):
    plan, image, target = stage_fixture(mode)
    original = copy.deepcopy(plan)
    repair.guard(plan, mode, image, target, mode != 'catalog')
    assert plan == original


def test_timer_cannot_use_historical_catalog_build_without_applied_correction():
    with pytest.raises(RuntimeError, match='timer_requires_explicit_applied_image_tag'):
        repair.stage_build('timer')


def test_corrected_image_cannot_replay_host_or_catalog_stage():
    for mode in ('host', 'catalog'):
        with pytest.raises(RuntimeError, match='corrected_image_only_for_timer_stage'):
            repair.stage_build(mode, 'finops-20261027t062458z')


def test_timer_accepts_only_exact_applied_resource_without_mutating_plan():
    plan, image, target = stage_fixture('timer')
    before = copy.deepcopy(plan['resource_changes'][0]['change']['before'])
    repair.guard(plan, 'timer', image, target, True, before)
    for field in ('identity', 'network', 'app_settings', 'site_config'):
        drift = copy.deepcopy(before)
        drift[field] = 'foreign'
        with pytest.raises(RuntimeError, match='exact_applied_image_resource_required'):
            repair.guard(plan, 'timer', image, target, True, drift)


@pytest.mark.parametrize('defect', [None, 'image', 'tag', 'review', 'marker', 'not_applied',
    'not_validated', 'artifact', 'host', 'settings', 'identity', 'postgres', 'monitor',
    'claims', 'http', 'database_write', 'storage_write', 'cleanup', 'missing_service'])
def test_timer_provenance_requires_actual_applied_image_and_substantive_MI_proof(tmp_path, monkeypatch, defect):
    from scripts.deployment import finops_ingestion_image_repair as image

    folder = tmp_path / 'finops' / repair.TIMER_IMAGE_TAG / image.PLAN_FOLDER
    folder.mkdir(parents=True)
    (folder / 'image-only.tfplan').write_bytes(b'exact-plan')
    pin = repair.release.digest(b'exact-plan')
    monkeypatch.setattr(repair, 'TIMER_IMAGE_PLAN', pin)
    monkeypatch.setattr(repair.rt, 'HOME', tmp_path)
    b = {'image': repair.TIMER_IMAGE}
    hashes = {'ingestion': 'complete-preserved-settings'}
    host = {'plan_sha256': image.HOST_PLAN_SHA256, 'boundary': '2026-10-27T06:06:02.045288+00:00',
            'resource': {}, 'baseline': {'sites': {'ingestion': {'image': 'DOCKER|old-approved'}}}, 'settings_hashes': hashes}
    review = {'plan_sha256': pin, 'build': b.copy(), 'artifacts': {}, 'host_enabled': True,
              'timer_disabled': 'true', 'catalog_configured': 'true', 'settings_hashes': hashes.copy(),
              'host_provenance': {k: v for k, v in host.items() if k not in ('resource', 'baseline', 'settings_hashes')}}
    evidence = json.loads((ROOT / repair.DATAPLANE_EVIDENCE).read_text())
    records = {'review.json': review, 'validation.json': {'plan_sha256': pin, 'all_checks_passed': True},
               'apply-intent.json': {'plan_sha256': pin}, 'applied.json': {'plan_sha256': pin, 'applied': True},
               'baseline.json': {'sites': {'ingestion': {'image': 'old'}}},
               Path(repair.DATAPLANE_EVIDENCE).name: evidence}
    result = evidence['probes']['ingestion']['sanitized_result']
    if defect == 'image':
        b['image'] = repair.TIMER_IMAGE.replace('d2bdae', 'aaaaaa')
    elif defect == 'review':
        review['plan_sha256'] = 'foreign'
    elif defect == 'marker':
        records['apply-intent.json']['plan_sha256'] = 'foreign'
    elif defect == 'not_applied':
        records['applied.json']['applied'] = False
    elif defect == 'not_validated':
        records['validation.json']['all_checks_passed'] = False
    elif defect == 'artifact':
        review['artifacts'] = {'image-only.tfplan': 'foreign'}
    elif defect == 'host':
        review['host_provenance']['boundary'] = 'foreign'
    elif defect == 'settings':
        review['settings_hashes']['ingestion'] = 'foreign'
    elif defect == 'identity':
        result['identity_source'] = 'operator'
    elif defect in ('postgres', 'monitor'):
        result['checks'][defect]['status'] = 'metadata_only'
    elif defect == 'claims':
        result['checks']['table']['claims_verified'] = False
    elif defect == 'http':
        result['checks']['monitor']['http_status'] = 403
    elif defect in ('database_write', 'storage_write'):
        result[defect + 's'] = 1
    elif defect == 'cleanup':
        evidence['cleanup']['absence'][0]['http_status'] = 200
    elif defect == 'missing_service':
        del result['checks']['queue']
    monkeypatch.setattr(repair, 'load', lambda path: copy.deepcopy(records[path.name]))
    monkeypatch.setattr(image, 'host_provenance', lambda: host)
    monkeypatch.setattr(image, 'load_plan', lambda _: {'resource_changes': [
        {'address': repair.fs.FUNCTION, 'change': {'after': {'enabled': True,
            'site_config': [{'linux_fx_version': 'DOCKER|old-approved'}]}}}]})
    monkeypatch.setattr(image, 'guard', lambda *_: None)
    tag = 'finops-20261027t060657z' if defect == 'tag' else repair.TIMER_IMAGE_TAG
    if defect:
        with pytest.raises(RuntimeError):
            repair.timer_provenance(b, tag)
    else:
        proof = repair.timer_provenance(b, tag)
        assert proof['boundary'] == host['boundary']
        assert proof['settings_hashes'] == hashes
        assert proof['baseline']['sites']['ingestion']['image'] == 'DOCKER|' + repair.TIMER_IMAGE


@pytest.mark.parametrize('defect', ['cutoff', 'catalog', 'host', 'timer', 'unknown_cutoff'])
def test_timer_preserves_exact_cutoff_catalog_host_and_known_values(defect):
    plan, image, target = stage_fixture('timer')
    c = plan['resource_changes'][0]['change']
    if defect == 'cutoff':
        c['after']['app_settings']['AIFLUX_INGESTION_START_AT'] = '2026-10-27T07:00:00+00:00'
    elif defect == 'catalog':
        c['after']['app_settings']['AIFLUX_CATALOG_CONFIGURED'] = 'false'
    elif defect == 'host':
        c['after']['enabled'] = False
    elif defect == 'timer':
        c['after']['app_settings']['AzureWebJobs.ingest_usage.Disabled'] = 'true'
    else:
        c['after_unknown'] = {'app_settings': {'AIFLUX_INGESTION_START_AT': True}}
    with pytest.raises(RuntimeError):
        repair.guard(plan, 'timer', image, target, True)


@pytest.mark.parametrize('mode', ['catalog', 'host', 'timer'])
@pytest.mark.parametrize('defect', ['network', 'identity', 'tls', 'setting', 'unknown', 'image', 'create', 'other', 'missing', 'duplicate'])
def test_stage_rejects_all_unapproved_changes(mode, defect):
    plan, image, target = stage_fixture(mode)
    resource = plan['resource_changes'][0]
    after = resource['change']['after']
    if defect in ('network', 'identity'):
        after[defect] = 'foreign'
    elif defect == 'tls':
        after['site_config'][0]['minimum_tls_version'] = '1.0'
    elif defect == 'setting':
        after['app_settings']['unapproved'] = 'true'
    elif defect == 'unknown':
        resource['change']['after_unknown'] = {'app_settings': True}
    elif defect == 'image':
        after['site_config'][0]['application_stack'][0]['docker'][0]['image_tag'] = 'c' * 64
    elif defect == 'create':
        resource['change']['actions'] = ['delete', 'create']
    elif defect == 'other':
        resource['address'] = 'azurerm_role_assignment.foreign'
    elif defect == 'missing':
        plan['resource_changes'] = []
    else:
        plan['resource_changes'].append(copy.deepcopy(resource))
    with pytest.raises(RuntimeError):
        repair.guard(plan, mode, image, target, mode != 'catalog')