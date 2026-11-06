"""Offline synthetic acceptance contracts, NOT acceptance of the eight live routes.

All fixture edits are confined to tmp_path. requested.json proves only native
deployment metadata; gateway_validated=True below is synthetic test input only.
"""
from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'foundry_eight_approved_catalog', ROOT / 'services/usage-ingestion/approved_catalog.py')
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
NEW = {
    'claude-sonnet-5-5', 'claude-opus-5-5', 'claude-opus-5-5-fast',
    'claude-haiku-5-5', 'claude-opus-4-8', 'gpt-6.1-terra', 'gpt-6-luna', 'Mistral-Large-3',
}
FROZEN = (
    'gateway/catalog/foundry-inventory-20261026.json',
    'gateway/catalog/project-routes.json',
    'gateway/catalog/fireworks-candidate-routes.json',
    'gateway/catalog/foundry-eight-candidate-routes.json',
    'gateway/catalog/external-inventory.json',
    'gateway/catalog/dev-models.json',
    'services/usage-ingestion/ingestion-approved.json',
    'services/usage-ingestion/catalog-bindings.json',
    '.deployment/foundry-eight-20261030/requested.json',
)


def write(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')


@pytest.fixture
def eight(tmp_path):
    for name in FROZEN:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    catalog = tmp_path / 'gateway/catalog'
    manifest = json.loads((catalog / 'foundry-eight-candidate-routes.json').read_text())
    requested = json.loads((tmp_path / FROZEN[-1]).read_text())
    data = json.loads((catalog / 'foundry-inventory-20261026.json').read_text())
    for route in data['routes']:
        route['endpoint_url'] = manifest['gateway_url']
    for alias in sorted(NEW):
        native = requested[alias]
        model = native['properties']['model']
        data['deployments'].append({
            'id': native['id'], 'name': alias, 'model_name': model['name'],
            'model_version': model['version'], 'model_format': model['format'],
            'provisioning_state': native['properties']['provisioningState'],
            'capacity': native['sku']['capacity'], 'sku': native['sku']['name'],
            'chat_completion': True,
            # gpt-6-luna also advertises decision; it remains a chat route,
            # never a substitute for the disabled routing-only Decision-1.
            'decision': native['properties']['capabilities'].get('decision') == 'true',
        })
        data['routes'].append({
            'alias': alias, 'deployment_id': native['id'], 'backend_model': alias,
            'model_name': model['name'], 'model_version': model['version'],
            'endpoint_url': manifest['gateway_url'], 'api_format': 'openai-chat-completions',
            'capabilities': ['chat'], 'max_completion_tokens': 1024,
            'upstream_token_parameter': manifest['routes'][alias]['token_parameter'],
            'gateway_validated': True,  # Synthetic acceptance only in tmp_path.
        })
    data['verified_at'] = datetime.now(UTC).isoformat()
    selected = catalog / 'synthetic-accepted-eight.json'
    write(selected, data)
    return tmp_path, selected, data


def test_historical_default_and_original_bytes_unchanged(eight):
    root, selected, _ = eight
    before = {name: (ROOT / name).read_bytes() for name in FROZEN}
    expected = json.loads((ROOT / 'services/usage-ingestion/ingestion-approved.json').read_text())
    assert builder.build(ROOT) == expected
    assert builder.build(root) == expected
    builder.build(root, profile='foundry-eight', inventory_path=selected)
    assert {name: (ROOT / name).read_bytes() for name in FROZEN} == before
    # Merely creating an additive source must not select it automatically.
    assert len(builder.build(root)['models']) == 14


def test_explicit_profile_exact_twenty_one_plus_disabled_decision(eight):
    root, selected, _ = eight
    result = builder.build(root, profile='foundry-eight', inventory_path=selected)
    models = {m['id']: m for m in result['models']}
    assert len(models) == 22
    assert {a for a, m in models.items() if m['enabled']} == (
        builder.ORIGINAL_FOUNDRY | builder.FIREWORKS.keys() | NEW | {'glm-5.3'})
    assert models['Mistral-Large-3']['provider'] == 'Mistral AI'
    assert models['glm-5.3']['provider'] == 'ModelArts'
    assert models['FW-GLM-5.3']['provider'] == 'Fireworks'
    assert models['gpt-6-luna']['enabled'] is True
    assert models['Decision-1']['enabled'] is False
    assert models['Decision-1']['capabilities'] == ['routing']
    assert all(m['region'] == ('ap-southeast-1' if a == 'glm-5.3' else 'eastus')
               for a, m in models.items())
    assert all(not any('price' in k or 'cost' in k for k in m) for m in models.values())
    historical = {m['id']: m for m in builder.build(ROOT)['models']}
    assert {alias: models[alias] for alias in historical} == historical
    assert result == builder.build(root, profile='foundry-eight', inventory_path=selected.relative_to(root))


def test_expanded_inventory_is_never_auto_selected_by_count(eight):
    root, selected, data = eight
    with pytest.raises(AssertionError):
        builder.build(root, inventory_path=selected)
    write(root / 'gateway/catalog/foundry-inventory-20261026.json', data)
    with pytest.raises(AssertionError):
        builder.build(root)
    with pytest.raises(ValueError, match='unknown approved catalog profile'):
        builder.build(root, profile='twenty')


def test_profile_requires_accepted_evidence_not_just_new_manifest(eight):
    root, _, _ = eight
    with pytest.raises(AssertionError):
        builder.build(root, profile='foundry-eight')


@pytest.mark.parametrize('defect', [
    'unverified', 'missing', 'duplicate', 'foreign_same_count', 'upstream_endpoint',
    'anthropic_public_format', 'token_parameter', 'model_version', 'backend',
    'provider', 'mistral_wrong_format', 'sku', 'capacity', 'zero_capacity',
    'inactive', 'not_chat', 'capabilities', 'outside_parent', 'decision',
    'duplicate_deployment', 'wrong_project', 'connections', 'future_time', 'output_cap',
])
def test_evidence_drift_fails_closed(eight, defect):
    root, selected, original = eight
    data = deepcopy(original)
    route = next(r for r in data['routes'] if r['alias'] == 'claude-sonnet-5-5')
    deployment = next(d for d in data['deployments'] if d['name'] == route['alias'])
    if defect == 'unverified':
        route['gateway_validated'] = False
    elif defect == 'missing':
        data['routes'].remove(route)
    elif defect == 'duplicate':
        data['routes'][-1] = deepcopy(data['routes'][0])
    elif defect == 'foreign_same_count':
        route['alias'] = 'foreign'
    elif defect == 'upstream_endpoint':
        route['endpoint_url'] = builder.ANTHROPIC_URL
    elif defect == 'anthropic_public_format':
        route['api_format'] = 'anthropic-messages'
    elif defect == 'token_parameter':
        route['upstream_token_parameter'] = 'max_completion_tokens'
    elif defect == 'model_version':
        route['model_version'] = 'unreviewed'
    elif defect == 'backend':
        route['backend_model'] = 'foreign'
    elif defect == 'provider':
        deployment['model_format'] = 'OpenAI'
    elif defect == 'mistral_wrong_format':
        next(d for d in data['deployments'] if d['name'] == 'Mistral-Large-3')['model_format'] = 'Mistral'
    elif defect == 'sku':
        deployment['sku'] = 'DataZoneStandard'
    elif defect == 'capacity':
        deployment['capacity'] = 1
    elif defect == 'zero_capacity':
        deployment['capacity'] = 0
    elif defect == 'inactive':
        deployment['deployment_state'] = 'Disabled'
    elif defect == 'not_chat':
        deployment['chat_completion'] = False
    elif defect == 'capabilities':
        route['capabilities'] = ['embeddings']
    elif defect == 'outside_parent':
        deployment['id'] = route['deployment_id'] = '/foreign/deployments/' + route['alias']
    elif defect == 'decision':
        next(d for d in data['deployments'] if d['name'] == 'Decision-1')['chat_completion'] = True
    elif defect == 'duplicate_deployment':
        data['deployments'][-1] = deepcopy(data['deployments'][0])
    elif defect == 'wrong_project':
        data['project_endpoint'] += '-foreign'
    elif defect == 'connections':
        data['connection_ids'] = ['/unverified/connection']
    elif defect == 'output_cap':
        route['max_completion_tokens'] = 2048
    else:
        data['verified_at'] = '2999-01-01T00:00:00Z'
    write(selected, data)
    with pytest.raises((AssertionError, ValueError)):
        builder.build(root, profile='foundry-eight', inventory_path=selected)


@pytest.mark.parametrize('alias,field,value', [
    ('claude-sonnet-5-5', 'upstream_url', builder.FOUNDRY_URL),
    ('claude-sonnet-5-5', 'api_format', 'openai-chat-completions'),
    ('claude-sonnet-5-5', 'token_parameter', 'max_completion_tokens'),
    ('claude-opus-5-5-fast', 'capacity', 5000),
    ('Mistral-Large-3', 'provider', 'Mistral'),
    ('Mistral-Large-3', 'upstream_url', builder.FOUNDRY_URL),
    ('gpt-6-luna', 'version', '2'),
    ('gpt-4o', 'version', 'foreign'),
    ('FW-GLM-5.3', 'provider', 'ModelArts'),
])
def test_exact_native_manifest_contracts(eight, alias, field, value):
    root, selected, _ = eight
    path = root / 'gateway/catalog/foundry-eight-candidate-routes.json'
    data = json.loads(path.read_text())
    data['routes'][alias][field] = value
    write(path, data)
    with pytest.raises(AssertionError):
        builder.build(root, profile='foundry-eight', inventory_path=selected)


@pytest.mark.parametrize('field,value', [
    ('gateway_validated', False), ('credential_healthy', False),
    ('endpoint_url', builder.FIREWORKS_URL), ('probe_total_tokens', 0),
    ('assistant_nonempty', False), ('verified_at', '2999-01-01T00:00:00Z'),
])
def test_external_glm_still_requires_its_own_acceptance(eight, field, value):
    root, selected, _ = eight
    path = root / 'gateway/catalog/external-inventory.json'
    data = json.loads(path.read_text())
    data['routes'][0][field] = value
    write(path, data)
    with pytest.raises((AssertionError, ValueError)):
        builder.build(root, profile='foundry-eight', inventory_path=selected)


def test_packaged_selection_keeps_configured_filename_and_checks_both_catalogs(eight):
    root, selected, data = eight
    result = builder.build(root, profile='foundry-eight', inventory_path=selected)
    write(root / 'gateway/catalog/foundry-inventory-20261026.json', data)
    for name in ('dev-models.json', 'ingestion-approved.json'):
        write(root / 'gateway/catalog' / name, result)
    builder.verify_packaged(root, profile='foundry-eight')
    path = root / 'gateway/catalog/dev-models.json'
    stale = deepcopy(result)
    stale['models'][0]['enabled'] = False
    write(path, stale)
    with pytest.raises(ValueError, match='packaged catalog differs'):
        builder.verify_packaged(root, profile='foundry-eight')


def test_docker_selection_is_build_time_only_and_defaults_historical():
    text = (ROOT / 'services/usage-ingestion/Dockerfile').read_text()
    assert 'ARG APPROVED_CATALOG_PROFILE=historical' in text
    assert 'ARG APPROVED_INVENTORY_PATH=gateway/catalog/foundry-inventory-20261026.json' in text
    assert 'COPY ${APPROVED_INVENTORY_PATH} ./gateway/catalog/foundry-inventory-20261026.json' in text
    assert '--profile "$APPROVED_CATALOG_PROFILE"' in text
    assert 'COPY gateway/catalog/foundry-eight-candidate-routes.json ./gateway/catalog/' in text
    assert 'ENV APPROVED_' not in text


@pytest.mark.parametrize('provider', ['foundry', 'fireworks', 'external'])
def test_additive_region_binding_cannot_silently_change_attribution(eight, provider):
    root, selected, _ = eight
    path = root / 'services/usage-ingestion/catalog-bindings.json'
    data = json.loads(path.read_text())
    data[provider]['region'] = 'foreign'
    write(path, data)
    with pytest.raises(AssertionError, match='provider scope'):
        builder.build(root, profile='foundry-eight', inventory_path=selected)