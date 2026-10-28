import copy

import pytest

from scripts.deployment import finops_ingestion_image_repair as repair
from test_finops_catalog_repair import stage_fixture


def fixture():
    plan, image, _ = stage_fixture('catalog')
    change = plan['resource_changes'][0]['change']
    change['after']['app_settings'] = copy.deepcopy(change['before']['app_settings'])
    return plan, image


def test_image_only_preserves_every_setting_and_guard_does_not_mutate_plan():
    plan, image = fixture()
    original = copy.deepcopy(plan)
    repair.guard(plan, image)
    assert plan == original


@pytest.mark.parametrize('defect', ['host_already_enabled', 'host_activation', 'timer', 'catalog', 'cutoff',
                                  'setting', 'identity', 'network', 'tls', 'unknown', 'image', 'other',
                                  'create', 'delete', 'missing', 'duplicate', 'same_image', 'registry_credentials'])
def test_rejects_settings_activation_and_all_non_image_changes(defect):
    plan, image = fixture()
    change = plan['resource_changes'][0]['change']
    after = change['after']
    if defect == 'host_already_enabled':
        change['before']['enabled'] = after['enabled'] = True
    elif defect == 'host_activation':
        after['enabled'] = True
    elif defect in ('timer', 'catalog', 'cutoff', 'setting'):
        name, value = {'timer': ('AzureWebJobs.ingest_usage.Disabled', 'false'),
                       'catalog': ('AIFLUX_CATALOG_CONFIGURED', 'true'),
                       'cutoff': ('AIFLUX_INGESTION_START_AT', '2026-10-27T06:06:02+00:00'),
                       'setting': ('extra', 'true')}[defect]
        after['app_settings'][name] = value
    elif defect in ('identity', 'network'):
        after[defect] = 'foreign'
    elif defect == 'tls':
        after['site_config'][0]['minimum_tls_version'] = '1.0'
    elif defect == 'unknown':
        change['after_unknown'] = {'app_settings': True}
    elif defect == 'image':
        after['site_config'][0]['application_stack'][0]['docker'][0]['image_tag'] = 'c' * 64
    elif defect == 'registry_credentials':
        after['site_config'][0]['application_stack'][0]['docker'][0]['registry_password'] = 'unexpected'
    elif defect == 'other':
        plan['resource_changes'][0]['address'] = 'azurerm_role_assignment.foreign'
    elif defect in ('create', 'delete'):
        change['actions'] = [defect]
    elif defect == 'missing':
        plan['resource_changes'] = []
    elif defect == 'duplicate':
        plan['resource_changes'].append(copy.deepcopy(plan['resource_changes'][0]))
    else:
        after['site_config'] = copy.deepcopy(change['before']['site_config'])
    with pytest.raises(RuntimeError):
        repair.guard(plan, image)


@pytest.mark.parametrize('name,value', [('AIFLUX_CATALOG_CONFIGURED', 'true'),
                                     ('AIFLUX_INGESTION_START_AT', '2026-10-27T06:06:02+00:00')])
def test_already_applied_activation_is_not_silently_accepted_or_rolled_back(name, value):
    plan, image = fixture()
    change = plan['resource_changes'][0]['change']
    change['before']['app_settings'][name] = change['after']['app_settings'][name] = value
    with pytest.raises(RuntimeError, match='catalog_false_no_cutoff'):
        repair.guard(plan, image)


def test_existing_four_image_and_catalog_controllers_are_not_relaxed():
    from scripts.deployment import finops_release, finops_catalog_repair

    plan, image = fixture()
    with pytest.raises(ValueError, match='four_component'):
        finops_release.guard_image_plan(plan, {'ingestion': image})
    assert finops_catalog_repair.HOME.name == 'catalog-repair'


def enabled_fixture():
    plan, image = fixture()
    change = plan['resource_changes'][0]['change']
    boundary = '2026-10-27T06:06:02.045288+00:00'
    for value in (change['before'], change['after']):
        value['enabled'] = True
        value['app_settings'].update(AIFLUX_CATALOG_CONFIGURED='true',
                                     AIFLUX_INGESTION_START_AT=boundary,
                                     AIFLUX_CATALOG_PATH=repair.catalog.CATALOG_PATH)
    host = {'plan_sha256': repair.HOST_PLAN_SHA256, 'target_settings_hash': repair.HOST_SETTINGS_SHA256,
            'boundary': boundary, 'resource': copy.deepcopy(change['before'])}
    return plan, image, host


def test_verified_applied_host_allows_only_image_preserving_exact_cutoff():
    plan, image, host = enabled_fixture()
    original = copy.deepcopy(plan)
    repair.guard(plan, image, host)
    assert plan == original


@pytest.mark.parametrize('field,value', [('enabled', False), ('AIFLUX_CATALOG_CONFIGURED', 'false'),
    ('AIFLUX_INGESTION_START_AT', '2026-10-27T07:00:00+00:00'),
    ('AzureWebJobs.ingest_usage.Disabled', 'false'), ('AIFLUX_CATALOG_PATH', '/foreign')])
@pytest.mark.parametrize('sides', [('before',), ('after',), ('before', 'after')])
def test_applied_host_drift_rejected_even_when_plan_preserves_drift(field, value, sides):
    plan, image, host = enabled_fixture()
    for side in sides:
        resource = plan['resource_changes'][0]['change'][side]
        if field == 'enabled':
            resource[field] = value
        else:
            resource['app_settings'][field] = value
    with pytest.raises(RuntimeError):
        repair.guard(plan, image, host)


@pytest.mark.parametrize('field', ['plan_sha256', 'target_settings_hash'])
def test_foreign_host_provenance_rejected(field):
    plan, image, host = enabled_fixture()
    host[field] = 'f' * 64
    with pytest.raises(RuntimeError, match='unapproved_host_provenance'):
        repair.guard(plan, image, host)


def test_live_enabled_baseline_without_provenance_still_rejected():
    plan, image, _ = enabled_fixture()
    with pytest.raises(RuntimeError, match='disabled_baseline'):
        repair.guard(plan, image)


@pytest.mark.parametrize('marker', ['validation.json', 'apply-intent.json', 'applied.json'])
def test_host_provenance_requires_matching_validated_intended_and_applied_plan(monkeypatch, marker):
    review = {'plan_sha256': repair.HOST_PLAN_SHA256, 'controller_sha256': repair.HOST_CONTROLLER_SHA256,
              'target_settings_hash': repair.HOST_SETTINGS_SHA256, 'mode': 'host', 'enabled': True, 'guard': 'passed'}
    def fake_load(path):
        return review if path.name == 'review.json' else {'plan_sha256': 'foreign' if path.name == marker else repair.HOST_PLAN_SHA256}
    monkeypatch.setattr(repair, 'load', fake_load)
    with pytest.raises(RuntimeError, match='host_marker_plan_mismatch'):
        repair.host_provenance()


def test_scanner_keeps_explicit_exception_identity_and_does_not_hide_skips(monkeypatch):
    import json
    from types import SimpleNamespace

    def run(args, **kwargs):
        assert '--quiet' not in args and '--skip-download' in args
        return SimpleNamespace(returncode=0, stdout=json.dumps({'summary': {'passed': 96, 'failed': 0,
            'skipped': 1, 'parsing_errors': 0}, 'results': {'passed_checks': [], 'failed_checks': [],
            'skipped_checks': [{'check_id': 'CKV_DOCKER_3', 'check_name': 'container user',
                                'check_result': {'result': 'SKIPPED', 'suppress_comment': 'explicit compatibility exception'}}]}}))
    monkeypatch.setattr(repair.subprocess, 'run', run)
    result = repair.scan()
    assert result['skipped_checks'][0]['check_id'] == 'CKV_DOCKER_3'
    assert result['skipped_checks'][0]['suppress_comment'] == 'explicit compatibility exception'