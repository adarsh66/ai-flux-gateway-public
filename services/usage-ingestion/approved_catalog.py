"""Build the ingestion catalog from accepted inventories, never legacy aliases/prices."""
from datetime import UTC, datetime
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
FOUNDRY_EIGHT = {
    'claude-sonnet-5-5': ('Anthropic', '2', 5000),
    'claude-opus-5-5': ('Anthropic', '2', 5000),
    'claude-opus-5-5-fast': ('Anthropic', '2', 2000),
    'claude-haiku-5-5': ('Anthropic', '2', 5000),
    'claude-opus-4-8': ('Anthropic', '2', 5000),
    'gpt-6.1-terra': ('OpenAI', '2026-10-26', 5000),
    'gpt-6-luna': ('OpenAI', '2026-09-22', 5000),
    'Mistral-Large-3': ('Mistral AI', '1', 5000),
}
ANTHROPIC_URL = 'https://poc-ids-token-ex-foundry.services.ai.azure.com/anthropic/v1'
GATEWAY_URL = 'https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1'
FOUNDRY_URL = 'https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1'
ACCOUNT_ID = ('/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/'
              'IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry')


def _validate_eight(catalog: Path, inventory: dict, project: dict, binding: dict) -> None:
    """Validate public acceptance separately from the native provider contract.

    ARM deployment metadata alone is never gateway acceptance. This function
    reads evidence only; it cannot set gateway_validated or emit an inventory.
    """
    from aiflux.foundry_inventory import FoundryInventory

    predecessor = json.loads((catalog / 'fireworks-candidate-routes.json').read_text(encoding='utf-8'))
    old = ORIGINAL_FOUNDRY | FIREWORKS.keys()
    expected = old | FOUNDRY_EIGHT.keys()
    assert set(predecessor['routes']) == old, 'exact twelve-route predecessor required'
    assert {k: v for k, v in project.items() if k != 'routes'} == {
        k: v for k, v in predecessor.items() if k != 'routes'
    }, 'manifest scope must preserve predecessor'
    assert (project['gateway_url'] == GATEWAY_URL and project['upstream_url'] == FOUNDRY_URL
            and binding['foundry']['url'] == FOUNDRY_URL
            and binding['fireworks']['url'] == FIREWORKS_URL
            and binding['foundry']['region'] == binding['fireworks']['region'] == 'eastus'
            and binding['external']['region'] == 'ap-southeast-1'), 'exact provider scope required'
    assert set(project['routes']) == expected, 'exact twenty Foundry routes required'
    assert {a: project['routes'][a] for a in old} == predecessor['routes'], 'old twelve contracts must be unchanged'
    for alias, (provider, version, capacity) in FOUNDRY_EIGHT.items():
        anthropic = provider == 'Anthropic'
        upstream = ANTHROPIC_URL if anthropic else FOUNDRY_URL if provider == 'OpenAI' else FIREWORKS_URL
        assert project['routes'][alias] == {
            'model_name': alias, 'version': version, 'provider': provider,
            'sku': 'GlobalStandard', 'capacity': capacity,
            'token_parameter': 'max_completion_tokens' if provider == 'OpenAI' else 'max_tokens',
            'upstream_url': upstream,
            'api_format': 'anthropic-messages' if anthropic else 'openai-chat-completions',
        }, 'exact new native provider contract required'
    evidence = FoundryInventory.model_validate(inventory)
    assert (evidence.account_resource_id == ACCOUNT_ID
            and evidence.project_resource_id == ACCOUNT_ID + '/projects/poc-ids-token-ex-foundry-project'
            and evidence.project_endpoint == project['project_endpoint']
            == 'https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project'
            and evidence.verified_at.tzinfo is not None and evidence.verified_at <= datetime.now(UTC)
            and not evidence.connection_ids), 'accepted parent scope required'
    assert (len(evidence.routes) == len(expected)
            and {r.alias for r in evidence.routes} == expected
            and len(evidence.deployments) == len(expected) + 1
            and {d.name for d in evidence.deployments} == expected | {'Decision-1'}), 'exact accepted inventory required'
    assert all(d.id == ACCOUNT_ID + '/deployments/' + d.name for d in evidence.deployments), 'exact parent deployment required'
    for route in evidence.routes:
        assert (evidence.route(route.alias) is not None and route.gateway_validated is True
                and route.endpoint_url == GATEWAY_URL
                and route.api_format == 'openai-chat-completions'
                and route.capabilities == ['chat']
                and route.upstream_token_parameter == project['routes'][route.alias]['token_parameter']), 'accepted public gateway route required'
        if route.alias in FOUNDRY_EIGHT:
            assert route.max_completion_tokens == 1024, 'approved new route output cap required'
    decision = next(d for d in evidence.deployments if d.name == 'Decision-1')
    assert decision.decision and not decision.chat_completion and decision.model_format == 'Microsoft', 'disabled Decision-1 required'


def build(root: Path, *, profile: str = 'historical', inventory_path: Path | None = None) -> dict:
    """Explicit additive selection; defaults retain the historical upstream contract.

    Relative inventory paths are rooted at root. Release contexts may package
    selected accepted bytes under the existing configured historical filename.
    Neither route counts nor deployment metadata select/accept the new profile.
    """
    if profile not in ('historical', 'foundry-eight'):
        raise ValueError('unknown approved catalog profile')
    catalog = root / 'gateway/catalog'
    selected = inventory_path if inventory_path is not None else catalog / 'foundry-inventory-20261026.json'
    if inventory_path is not None and not selected.is_absolute():
        selected = root / selected
    inventory = json.loads(selected.read_text())
    project = json.loads((catalog / 'project-routes.json').read_text())
    # Keep the already-applied gateway's source-bound predecessor immutable.
    # The separately reviewed additive manifest is selected only by exact
    # accepted inventory membership, never by a permissive count fallback.
    if (profile == 'historical'
            and {r['alias'] for r in inventory['routes']} == ORIGINAL_FOUNDRY | FIREWORKS.keys()
            and set(project['routes']) == ORIGINAL_FOUNDRY):
        project = json.loads((catalog / 'fireworks-candidate-routes.json').read_text())
    external = json.loads((catalog / 'external-inventory.json').read_text())
    binding = json.loads((root / 'services/usage-ingestion/catalog-bindings.json').read_text())
    if profile == 'foundry-eight':
        project = json.loads((catalog / 'foundry-eight-candidate-routes.json').read_text(encoding='utf-8'))
        _validate_eight(catalog, inventory, project, binding)
    membership = set(project['routes'])
    allowed = (ORIGINAL_FOUNDRY | FIREWORKS.keys() | FOUNDRY_EIGHT.keys(),) if profile == 'foundry-eight' else (
        ORIGINAL_FOUNDRY, ORIGINAL_FOUNDRY | FIREWORKS.keys())
    assert membership in allowed, 'reviewed exact membership required'
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
        if profile == 'foundry-eight' and alias in FOUNDRY_EIGHT:
            assert (deployment['sku'] == metadata['sku']
                and deployment['capacity'] == metadata['capacity']), 'exact new deployment capacity and SKU required'
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
                 and (route['endpoint_url'] == GATEWAY_URL if profile == 'foundry-eight' else
                     route['endpoint_url'] == metadata.get('upstream_url', project['upstream_url']) == provider_binding['url']))
        models.append({'id': alias, 'provider': deployment['model_format'], 'enabled': True,
                       'capabilities': ['chat'], 'backend_model': route['backend_model'],
                       'region': provider_binding['region'], 'max_completion_tokens': route['max_completion_tokens']})
    assert len(models) == len(membership)
    assert len(external['routes']) == 1
    route = external['routes'][0]
    if profile == 'foundry-eight':
        from aiflux.external_inventory import ExternalInventory

        accepted = ExternalInventory.model_validate(external).routes[0]
        assert (accepted.endpoint_url == GATEWAY_URL and accepted.verified_at is not None
                and accepted.verified_at.tzinfo is not None and accepted.verified_at <= datetime.now(UTC)
                and (accepted.metadata_renewal is None
                     or accepted.metadata_renewal.observed_at <= datetime.now(UTC))), 'accepted external gateway evidence required'
    assert (route['alias'] == 'glm-5.3' and route['backend_model'] == 'glm-5.3'
            and route['gateway_validated'] is True and route['credential_healthy'] is True
            and route['probe_status'] == 200 and route['assistant_nonempty'] is True
            and route['upstream_url'] == binding['external']['url'])
    models.append({'id': route['alias'], 'provider': route['provider'], 'enabled': True,
                   'capabilities': ['chat'], 'backend_model': route['backend_model'],
                   'region': binding['external']['region'], 'max_completion_tokens': route['max_completion_tokens']})
    decision = [d for d in inventory['deployments'] if d.get('decision')
                and (profile == 'historical' or d['name'] == 'Decision-1')]
    assert len(decision) == 1 and not decision[0]['chat_completion']
    models.append({'id': decision[0]['name'], 'provider': decision[0]['model_format'],
                   'enabled': False, 'capabilities': ['routing'], 'backend_model': decision[0]['name'],
                   'region': binding['foundry']['region']})
    result = {'models': models}
    Catalog.model_validate(result)
    return result


def verify_packaged(root: Path, *, profile: str = 'historical', inventory_path: Path | None = None) -> None:
    """Reject stale committed/package inputs instead of silently regenerating them."""
    expected = build(root, profile=profile, inventory_path=inventory_path)
    for name in ('ingestion-approved.json', 'dev-models.json'):
        target = root / 'gateway/catalog' / name
        if json.loads(target.read_text(encoding='utf-8')) != expected:
            raise ValueError('packaged catalog differs from reviewed inventory')
        loaded = Catalog.load(target)
        assert sum(m.enabled for m in loaded.models) == len(expected['models']) - 1
        assert not next(m for m in loaded.models if m.id == 'Decision-1').enabled


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('historical', 'foundry-eight'), default='historical')
    parser.add_argument('--inventory-path', type=Path)
    args = parser.parse_args()
    verify_packaged(Path.cwd(), profile=args.profile, inventory_path=args.inventory_path)