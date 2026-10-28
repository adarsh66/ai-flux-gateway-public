"""Build the ingestion catalog from accepted inventories, never legacy aliases/prices."""
import json
from pathlib import Path

from aiflux.catalog import Catalog

ORIGINAL_FOUNDRY = frozenset({
    'gpt-5.6-luna', 'gpt-6.1-sol', 'gpt-5.4-mini', 'gpt-4o',
    'DeepSeek-V4-Flash', 'DeepSeek-V4-Pro', 'Kimi-K2.7-Code',
    'grok-4.3', 'grok-4-20-reasoning', 'grok-4-1-fast-reasoning',
})
FIREWORKS = {
    'FW-GLM-5.3': ('2', 'GlobalStandard'),
    'FW-MiniMax-M3': ('1', 'DataZoneStandard'),
}
FIREWORKS_URL = 'https://poc-ids-token-ex-foundry.services.ai.azure.com/openai/v1'


def build(root: Path) -> dict:
    catalog = root / 'gateway/catalog'
    inventory = json.loads((catalog / 'foundry-inventory-20261026.json').read_text())
    project = json.loads((catalog / 'project-routes.json').read_text())
    # Keep the already-applied gateway's source-bound predecessor immutable.
    # The separately reviewed additive manifest is selected only by exact
    # accepted inventory membership, never by a permissive count fallback.
    if ({r['alias'] for r in inventory['routes']} == ORIGINAL_FOUNDRY | FIREWORKS.keys()
            and set(project['routes']) == ORIGINAL_FOUNDRY):
        project = json.loads((catalog / 'fireworks-candidate-routes.json').read_text())
    external = json.loads((catalog / 'external-inventory.json').read_text())
    binding = json.loads((root / 'services/usage-ingestion/catalog-bindings.json').read_text())
    membership = set(project['routes'])
    assert membership in (ORIGINAL_FOUNDRY, ORIGINAL_FOUNDRY | FIREWORKS.keys()), 'reviewed exact membership required'
    assert (len(inventory['routes']) == len(project['routes'])
            and {r['alias'] for r in inventory['routes']} == set(project['routes'])), 'accepted route membership required'
    models = []
    for alias, metadata in project['routes'].items():
        routes = [r for r in inventory['routes'] if r['alias'] == alias]
        assert len(routes) == 1, 'unique accepted route required'
        route = routes[0]
        deployments = [d for d in inventory['deployments'] if d['id'] == route['deployment_id']]
        assert len(deployments) == 1, 'unique deployment required'
        deployment = deployments[0]
        if alias in FIREWORKS:
            version, sku = FIREWORKS[alias]
            assert (metadata['provider'] == deployment['model_format'] == 'Fireworks'
                    and metadata['version'] == version and deployment['sku'] == sku
                    and metadata.get('upstream_url') == FIREWORKS_URL
                    and binding['fireworks']['url'] == FIREWORKS_URL), 'exact Fireworks binding required'
            provider_binding = binding['fireworks']
        else:
            provider_binding = binding['foundry']
        assert (route['gateway_validated'] is True and deployment['chat_completion'] is True
                and deployment['provisioning_state'] == 'Succeeded' and deployment['capacity'] > 0
                and route['backend_model'] == deployment['name'] == alias
                and route['model_name'] == deployment['model_name'] == metadata.get('model_name', alias)
                and metadata['provider'] == deployment['model_format']
                and metadata['version'] == route['model_version'] == deployment['model_version']
                and route['endpoint_url'] == metadata.get('upstream_url', project['upstream_url']) == provider_binding['url'])
        models.append({'id': alias, 'provider': deployment['model_format'], 'enabled': True,
                       'capabilities': ['chat'], 'backend_model': route['backend_model'],
                       'region': provider_binding['region'], 'max_completion_tokens': route['max_completion_tokens']})
    assert len(models) == len(membership)
    assert len(external['routes']) == 1
    route = external['routes'][0]
    assert (route['alias'] == 'glm-5.3' and route['backend_model'] == 'glm-5.3'
            and route['gateway_validated'] is True and route['credential_healthy'] is True
            and route['probe_status'] == 200 and route['assistant_nonempty'] is True
            and route['upstream_url'] == binding['external']['url'])
    models.append({'id': route['alias'], 'provider': route['provider'], 'enabled': True,
                   'capabilities': ['chat'], 'backend_model': route['backend_model'],
                   'region': binding['external']['region'], 'max_completion_tokens': route['max_completion_tokens']})
    decision = [d for d in inventory['deployments'] if d.get('decision')]
    assert len(decision) == 1 and not decision[0]['chat_completion']
    models.append({'id': decision[0]['name'], 'provider': decision[0]['model_format'],
                   'enabled': False, 'capabilities': ['routing'], 'backend_model': decision[0]['name'],
                   'region': binding['foundry']['region']})
    result = {'models': models}
    Catalog.model_validate(result)
    return result


def verify_packaged(root: Path) -> None:
    """Reject stale committed/package inputs instead of silently regenerating them."""
    expected = build(root)
    for name in ('ingestion-approved.json', 'dev-models.json'):
        target = root / 'gateway/catalog' / name
        if json.loads(target.read_text(encoding='utf-8')) != expected:
            raise ValueError('packaged catalog differs from reviewed inventory')
        loaded = Catalog.load(target)
        assert sum(m.enabled for m in loaded.models) == len(expected['models']) - 1
        assert not next(m for m in loaded.models if m.id == 'Decision-1').enabled


if __name__ == '__main__':
    verify_packaged(Path.cwd())