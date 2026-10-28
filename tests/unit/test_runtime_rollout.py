"""Offline rejection tests for the live rollout's exact saved-plan guard."""
from copy import deepcopy

import pytest

from scripts.deployment.runtime_rollout import (
    RG, diagnostic_categories, guard, guard_containment, log_summary, reference_metadata,
)


def candidate():
    release = {'results': {}}
    resources = []
    for name in ['api', 'admin', 'customer']:
        image = 'aiflux-' + name + '@sha256:' + 'a' * 64
        release['results'][name] = {'image': 'pocidstokenexacr.azurecr.io/' + image}
        before = {'site_config': [{'application_stack': [{'docker_image_name': 'old',
                    'docker_registry_url': 'https://pocidstokenexacr.azurecr.io'}],
                    'ip_restriction_default_action': 'Deny'}], 'app_settings': {}}
        after = deepcopy(before)
        after['site_config'][0]['application_stack'][0]['docker_image_name'] = image
        if name == 'api':
            after['app_settings'] = {
                'AIFLUX_LOCAL_JWT_SECRET': '@Microsoft.KeyVault(SecretUri=https://pocidstokenexkv.vault.azure.net/secrets/aiflux-local-jwt-signing-secret)',
                'AIFLUX_LOCAL_AUTH_ENABLED': 'true', 'AIFLUX_ENVIRONMENT': 'production',
                'AIFLUX_DATABASE_URL': 'postgresql://poc-ids-token-ex-api-identity@poc-ids-token-ex-pg.postgres.database.azure.com:5432/turnstile?sslmode=require',
                **{k: 'false' for k in ['CONTROL_PLANE_ENABLED', 'GATEWAY_PUBLICATION_WORKER_ENABLED',
                     'GATEWAY_RELEASE_WORKER_ENABLED', 'GATEWAY_APPLICATION_PROVISIONING_ENABLED']}}
        resources.append({'address': f'azurerm_linux_web_app.main["{name}"]', 'mode': 'managed',
                          'change': {'actions': ['update'], 'before': before, 'after': after, 'after_unknown': {}}})
    return {'resource_changes': resources}, release


def test_exact_rollout_allowed():
    plan, release = candidate()
    assert guard(plan, release)


@pytest.mark.parametrize('mutation', ['network', 'replacement', 'unrelated', 'unknown', 'direct_secret',
                                    'bootstrap_password', 'worker', 'image', 'missing_app', 'wrong_database'])
def test_reject_unsafe_rollout(mutation):
    plan, release = candidate()
    resource = plan['resource_changes'][0]
    change = resource['change']
    settings = change['after']['app_settings']
    if mutation == 'network':
        change['after']['site_config'][0]['ip_restriction_default_action'] = 'Allow'
    elif mutation == 'replacement':
        change['actions'] = ['delete', 'create']
    elif mutation == 'unrelated':
        resource['address'] = 'azurerm_key_vault.main'
    elif mutation == 'unknown':
        change['after_unknown'] = {'site_config': [{'ip_restriction': True}]}
    elif mutation == 'direct_secret':
        settings['AIFLUX_LOCAL_JWT_SECRET'] = 'not-a-key-vault-reference'
    elif mutation == 'bootstrap_password':
        settings['AIFLUX_BOOTSTRAP_ADMIN_PASSWORD'] = 'forbidden-test-only'
    elif mutation == 'worker':
        settings['GATEWAY_RELEASE_WORKER_ENABLED'] = 'true'
    elif mutation == 'image':
        change['after']['site_config'][0]['application_stack'][0]['docker_image_name'] = 'latest'
    elif mutation == 'missing_app':
        plan['resource_changes'].pop()
    elif mutation == 'wrong_database':
        settings['AIFLUX_DATABASE_URL'] = 'postgresql://wrong@other/db'
    with pytest.raises(RuntimeError):
        guard(plan, release)


@pytest.mark.parametrize('wrapper', ['map', 'properties', 'status_map', 'collection', 'nested_collection', 'value_map'])
def test_reference_metadata_wrappers(wrapper):
    metadata = {'status': 'OtherReasons', 'vaultName': 'test-vault', 'secretName': 'test-secret',
                'identityType': 'UserAssigned', 'details': 'network CANARY-DO-NOT-EMIT',
                'reference': 'CANARY-DO-NOT-EMIT', 'value': 'CANARY-DO-NOT-EMIT'}
    keyed = {'AIFLUX_LOCAL_JWT_SECRET': metadata}
    collection = {'value': [{'name': 'OTHER', 'properties': {'status': 'Resolved'}},
                            {'name': 'AIFLUX_LOCAL_JWT_SECRET', 'properties': metadata}]}
    response = {'map': keyed, 'properties': {'properties': keyed},
                'status_map': {'properties': {'keyToReferenceStatuses': keyed}},
                'collection': collection, 'nested_collection': {'properties': collection},
                'value_map': {'value': keyed}}[wrapper]
    result = reference_metadata(response)
    assert result == {'status': 'OtherReasons', 'vaultName': 'test-vault', 'secretName': 'test-secret',
                      'identityType': 'UserAssigned', 'resolved': False, 'metadataFound': True,
                      'detailCategories': ['network']}
    assert 'CANARY' not in str(result)


@pytest.mark.parametrize('response', [None, [], {}, {'value': None}, {'value': [None, 'bad']}])
def test_missing_reference_is_not_resolved(response):
    result = reference_metadata(response)
    assert not result['resolved'] and not result['metadataFound']


def test_reference_resolved_and_ambiguous():
    entry = {'name': 'AIFLUX_LOCAL_JWT_SECRET', 'properties': {'status': 'Resolved'}}
    assert reference_metadata({'value': [entry]})['resolved']
    with pytest.raises(RuntimeError, match='ambiguous_jwt_reference_metadata'):
        reference_metadata({'value': [entry, entry]})


def test_log_categories_never_include_original_lines():
    text = ('Traceback (most recent call last): CANARY-TOKEN Authorization: Bearer hidden\n'
            'ValidationError: local_jwt_secret must be resolved from KeyVault\n'
            'application startup failed postgresql://user:CANARY-PASSWORD@host/db')
    result = diagnostic_categories(text)
    assert {'traceback', 'settings_validation', 'unresolved_jwt_reference', 'startup_failed'} <= set(result)
    assert 'CANARY' not in str(result)


@pytest.mark.parametrize('json_wrapped', [False, True])
def test_log_trace_preserves_only_timestamp_and_categories(json_wrapped):
    import json
    text = '2026-10-23T18:22:33.000Z application startup failed CANARY-PASSWORD\n'
    content = json.dumps({'message': text, 'unknown': 'CANARY-TOKEN'}) if json_wrapped else text
    result = log_summary(content.encode())
    assert result['trace'] == [{'timestamp': '2026-10-23T18:22:33.000Z', 'categories': ['startup_failed']}]
    assert 'CANARY' not in str(result)


def containment_candidate():
    server_id = RG + '/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg'
    before = {'id': server_id, 'public_network_access_enabled': True, 'authentication': [{'password_auth_enabled': False}]}
    after = {**deepcopy(before), 'public_network_access_enabled': False}
    rule = {'name': 'temporary-cloud-shell-bootstrap', 'server_id': server_id,
            'start_ip_address': '135.171.36.90', 'end_ip_address': '135.171.36.90'}
    plan = {'resource_changes': [
        {'address': 'azurerm_postgresql_flexible_server.main[0]', 'mode': 'managed',
         'change': {'actions': ['update'], 'before': before, 'after': after, 'after_unknown': {}}},
        {'address': 'azurerm_postgresql_flexible_server_firewall_rule.bootstrap_retired["temporary-cloud-shell-bootstrap"]',
         'mode': 'managed', 'change': {'actions': ['delete'], 'before': rule, 'after': None, 'after_unknown': {}}}]}
    return plan, {'network': {'publicNetworkAccess': 'Enabled'}}, [{'name': rule['name']}]


def test_containment_only_exact_closure_allowed():
    plan, server, rules = containment_candidate()
    assert len(guard_containment(plan, server, rules)) == 2
    assert guard_containment({'resource_changes': []}, {'network': {'publicNetworkAccess': 'Disabled'}}, []) == []


@pytest.mark.parametrize('mutation', ['errored', 'unknown', 'replace', 'unrelated', 'auth', 'wrong_server',
                                    'wrong_rule_server', 'wrong_rule_name', 'wrong_ip', 'create_rule',
                                    'widen_network', 'missing_server', 'missing_rule', 'duplicate'])
def test_containment_rejects_any_nonclosure(mutation):
    plan, server, rules = containment_candidate()
    resource, rule = plan['resource_changes']
    change = resource['change']
    rc = rule['change']
    if mutation == 'errored':
        plan['errored'] = True
    elif mutation == 'unknown':
        change['after_unknown'] = {'authentication': True}
    elif mutation == 'replace':
        change['actions'] = ['delete', 'create']
    elif mutation == 'unrelated':
        rule['address'] = 'azurerm_linux_web_app.main["api"]'
    elif mutation == 'auth':
        change['after']['authentication'][0]['password_auth_enabled'] = True
    elif mutation == 'wrong_server':
        change['before']['id'] += '-other'
    elif mutation == 'wrong_rule_server':
        rc['before']['server_id'] += '-other'
    elif mutation == 'wrong_rule_name':
        rc['before']['name'] = 'other'
    elif mutation == 'wrong_ip':
        rc['before']['start_ip_address'] = '0.0.0.0'
    elif mutation == 'create_rule':
        rc['actions'] = ['create']
    elif mutation == 'widen_network':
        change['after']['public_network_access_enabled'] = True
    elif mutation == 'missing_server':
        plan['resource_changes'].pop(0)
    elif mutation == 'missing_rule':
        plan['resource_changes'].pop()
    elif mutation == 'duplicate':
        plan['resource_changes'].append(deepcopy(rule))
    with pytest.raises(RuntimeError):
        guard_containment(plan, server, rules)