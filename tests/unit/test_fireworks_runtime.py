"""Synthetic exact two-image guard mutations; never live deployment evidence."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest

from scripts.deployment import fireworks_runtime as release


def fixture():
    images = {k: release.portals.HOST + '/aiflux-' + k + '@sha256:' + 'b' * 64 for k in release.KINDS}
    api = {'app_settings': {'unchanged': 'true'}, 'identity': {'type': 'UserAssigned'},
           'site_config': [{'always_on': True, 'application_stack': [{
               'docker_registry_url': 'https://' + release.portals.HOST,
               'docker_image_name': 'aiflux-api@sha256:' + 'a' * 64}]}]}
    ingestion = {'enabled': True, 'app_settings': {'AzureWebJobs.ingest_usage.Disabled': 'false',
        'AIFLUX_CATALOG_CONFIGURED': 'true', 'AIFLUX_INGESTION_START_AT': '2026-10-27T06:06:02.045288+00:00'},
        'site_config': [{'always_on': True, 'application_stack': [{'docker': [{
            'image_name': 'aiflux-ingestion@sha256', 'image_tag': 'a' * 64,
            'registry_url': 'https://' + release.portals.HOST,
            'registry_username': '', 'registry_password': ''}]}]}]}
    resources = []
    for address, kind in release.ADDRESSES.items():
        before = api if kind == 'api' else ingestion
        after = deepcopy(before)
        if kind == 'api':
            after['site_config'][0]['application_stack'][0]['docker_image_name'] = images[kind].split('/', 1)[1]
        else:
            after['site_config'][0]['application_stack'][0]['docker'][0]['image_tag'] = 'b' * 64
        resources.append({'address': address, 'mode': 'managed',
                          'change': {'actions': ['update'], 'before': before, 'after': after, 'after_unknown': {}}})
    return {'applyable': True, 'errored': False, 'checks': [{'status': 'pass'}], 'resource_changes': resources}, images


def test_exact_two_image_plan_passes_without_mutating_input():
    plan, images = fixture()
    original = deepcopy(plan)
    release.guard(plan, images)
    assert plan == original


@pytest.mark.parametrize('defect', ['timer', 'cutoff', 'catalog', 'always_on', 'disabled', 'credentials',
                                  'registry', 'function_name', 'api_settings', 'api_identity', 'api_registry',
                                  'foreign_resource', 'create', 'delete', 'unknown', 'missing', 'duplicate',
                                  'failed_check', 'unknown_check', 'deferred', 'errored', 'unapplyable'])
def test_exact_two_image_guard_rejects_every_nonimage_delta(defect):
    plan, images = fixture()
    api, function = plan['resource_changes']
    f = function['change']['after']
    docker = f['site_config'][0]['application_stack'][0]['docker'][0]
    if defect == 'timer':
        f['app_settings']['AzureWebJobs.ingest_usage.Disabled'] = 'true'
    elif defect == 'cutoff':
        f['app_settings']['AIFLUX_INGESTION_START_AT'] = '2020-01-01T00:00:00Z'
    elif defect == 'catalog':
        f['app_settings']['AIFLUX_CATALOG_CONFIGURED'] = 'false'
    elif defect == 'always_on':
        f['site_config'][0]['always_on'] = False
    elif defect == 'disabled':
        f['enabled'] = False
    elif defect == 'credentials':
        docker['registry_password'] = 'synthetic-only'
    elif defect == 'registry':
        docker['registry_url'] = 'https://foreign.invalid'
    elif defect == 'function_name':
        docker['image_name'] = 'different@sha256'
    elif defect == 'api_settings':
        api['change']['after']['app_settings']['optional_controls'] = 'true'
    elif defect == 'api_identity':
        api['change']['after']['identity'] = {'type': 'SystemAssigned'}
    elif defect == 'api_registry':
        api['change']['after']['site_config'][0]['application_stack'][0]['docker_registry_url'] = 'http://foreign'
    elif defect == 'foreign_resource':
        function['address'] = 'azurerm_role_assignment.unapproved'
    elif defect in ('create', 'delete'):
        function['change']['actions'] = [defect]
    elif defect == 'unknown':
        function['change']['after_unknown'] = {'app_settings': True}
    elif defect == 'missing':
        plan['resource_changes'].pop()
    elif defect == 'duplicate':
        plan['resource_changes'].append(deepcopy(function))
    elif defect in ('failed_check', 'unknown_check'):
        plan['checks'][0]['status'] = 'fail' if defect == 'failed_check' else 'unknown'
    elif defect == 'deferred':
        plan['deferred_changes'] = [{'change': 'unknown'}]
    elif defect == 'errored':
        plan['errored'] = True
    else:
        plan['applyable'] = False
    with pytest.raises(RuntimeError):
        release.guard(plan, images)


@pytest.mark.parametrize('pin', ['latest', 'sha256:abc', 'sha256:' + 'c' * 64])
def test_no_mutable_or_wrong_image_pin(pin):
    plan, images = fixture()
    images['api'] = release.portals.HOST + '/different-api@' + pin
    with pytest.raises(RuntimeError):
        release.guard(plan, images)


@pytest.mark.parametrize('defect', [None, 'variables', 'configuration', 'change',
                                  'failed', 'missing', 'target_failed', 'deferred'])
def test_target_unknown_requires_real_identical_companion(defect):
    target, _ = fixture()
    target.update(configuration={'root_module': 'synthetic'}, variables={'approved': True})
    target['checks'] = [{'address': {'kind': 'var', 'name': 'approved'}, 'status': 'unknown'}]
    full = deepcopy(target)
    full['checks'][0]['status'] = 'pass'
    if defect in ('variables', 'configuration'):
        full[defect] = {'drift': True}
    elif defect == 'change':
        full['resource_changes'][0]['change']['after']['app_settings']['drift'] = 'true'
    elif defect == 'failed':
        full['checks'][0]['status'] = 'fail'
    elif defect == 'missing':
        full['checks'][0]['address']['name'] = 'different'
    elif defect == 'target_failed':
        target['checks'][0]['status'] = 'fail'
    elif defect == 'deferred':
        full['deferred_changes'] = [{}]
    if defect is None:
        assert release.resolve_checks(target, full) == full['checks']
        assert target['checks'][0]['status'] == 'unknown'
    else:
        with pytest.raises(RuntimeError):
            release.resolve_checks(target, full)


@pytest.mark.parametrize('defect', [None, 'policy', 'backend', 'reference', 'expired', 'future'])
def test_fresh_live_external_binding_required(monkeypatch, defect):
    from aiflux import external_inventory as inventory
    from scripts.deployment import glm_apim_secret as secret
    policy = 'synthetic-policy'
    backend = {'name': 'glm-synthetic', 'properties': {'url': inventory.GLM_UPSTREAM}}
    reference = {'synthetic_reference': True}
    at = datetime.now(UTC)
    if defect == 'expired':
        at -= timedelta(seconds=86401)
    elif defect == 'future':
        at += timedelta(minutes=5)
    renewal = SimpleNamespace(observed_at=at, policy_sha256=release.sha(policy),
        backend_sha256=release.sha(json.dumps(backend, sort_keys=True)),
        reference_metadata_sha256=release.sha(json.dumps(reference, sort_keys=True)))
    route = SimpleNamespace(metadata_renewal=renewal, verified_at=at - timedelta(days=2))
    monkeypatch.setattr(inventory.ExternalRoute, 'model_validate', lambda value: route)
    monkeypatch.setattr(release, 'load', lambda path: {'routes': [{}], 'external_internal_reference': reference})
    monkeypatch.setattr(secret, 'metadata', lambda value: value)
    monkeypatch.setattr(secret, 'internal_ready', lambda value: True)
    class Run:
        def policy(self):
            return policy + ('changed' if defect == 'policy' else '')
        def arm(self, suffix):
            if suffix == '/backends':
                value = deepcopy(backend)
                if defect == 'backend':
                    value['properties']['url'] = 'https://foreign.invalid'
                return {'value': [value]}
            return {'changed': True} if defect == 'reference' else reference
    monkeypatch.setattr(release, 'ProductRun', Run)
    if defect is None:
        proof = release.verify_external_metadata()
        assert proof['metadata_binding_verified'] and not proof['fresh_credential_health_verified']
    else:
        with pytest.raises(RuntimeError):
            release.verify_external_metadata()