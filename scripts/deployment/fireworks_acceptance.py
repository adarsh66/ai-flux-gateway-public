"""Join actual Fireworks smoke to fresh metadata; preserve old functional proof."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import importlib.util
import json

from aiflux.external_inventory import ExternalRoute, historical_acceptance_sha256
from aiflux.foundry_inventory import FoundryInventory
from scripts.deployment import runtime_rollout as rt
from scripts.deployment import fireworks_release as gateway
from scripts.deployment.project_route_product_access import ProductRun, sha
from scripts.deployment.glm_apim_secret import internal_ready

HOME = rt.HOME / 'fireworks-live-20261028'
CATALOG = rt.ROOT / 'gateway/catalog'


def joined_inventory(old, metadata, probes, at):
    result = deepcopy(old)
    rt.require(metadata['account']['id'].lower() == old['account_resource_id'].lower()
               and metadata['project']['id'].lower() == old['project_resource_id'].lower()
               and all(metadata[k]['properties']['provisioningState'] == 'Succeeded'
                       for k in ('account', 'project'))
               and not metadata['connections'].get('nextLink')
               and metadata['connections']['value'] == []
               and not metadata['deployments'].get('nextLink'), 'exact_parent_and_connections')
    live = {d['name']: d for d in metadata['deployments']['value']}
    rt.require(set(live) == {d['name'] for d in old['deployments']} | gateway.NEW.keys(),
               'exact_thirteen_deployments_required')
    for saved in old['deployments']:
        d = live[saved['name']]
        p = d['properties']
        rt.require(d['id'].lower() == saved['id'].lower()
                   and p['model'] == {'format': saved['model_format'], 'name': saved['model_name'],
                                      'version': saved['model_version']}
                   and p['provisioningState'] == saved['provisioning_state'] == 'Succeeded'
                   and d['sku']['capacity'] == saved['capacity'], 'old_metadata_changed:' + saved['name'])
    rt.require({p['alias'] for p in probes} == set(gateway.NEW) and len(probes) == 2,
               'actual_two_probes_required')
    for alias, (version, sku) in gateway.NEW.items():
        d, probe = live[alias], next(p for p in probes if p['alias'] == alias)
        p = d['properties']
        rt.require(p['model'] == {'format': 'Fireworks', 'name': alias, 'version': version}
                   and p['provisioningState'] == 'Succeeded' and p['capabilities']['chatCompletion'] == 'true'
                   and d['sku'] == {'name': sku, 'capacity': 250}
                   and p.get('raiPolicyName') == 'Microsoft.Nil', 'new_metadata_contract:' + alias)
        rt.require(probe['status'] == 200 and probe['response_model'] == alias
                   and probe['assistant_nonempty'] is True and probe['finish_reason'] == 'stop'
                   and probe['prompt_tokens'] >= 0 and 1 <= probe['completion_tokens'] <= 512
                   and probe['total_tokens'] == probe['prompt_tokens'] + probe['completion_tokens']
                   and timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(probe['at_utc'])
                       < timedelta(hours=2), 'new_actual_metered_probe_required:' + alias)
        result['deployments'].append({'id': d['id'], 'name': alias, 'model_name': alias,
            'model_version': version, 'model_format': 'Fireworks', 'provisioning_state': 'Succeeded',
            'deployment_state': None, 'capacity': 250, 'chat_completion': True, 'decision': False, 'sku': sku})
        result['routes'].append({'alias': alias, 'deployment_id': d['id'], 'backend_model': alias,
            'model_name': alias, 'model_version': version, 'endpoint_url': gateway.URL,
            'api_format': 'openai-chat-completions', 'capabilities': ['chat'], 'max_completion_tokens': 1024,
            'gateway_validated': True, 'upstream_token_parameter': 'max_tokens', 'expires_at': None})
    result['verified_at'] = at
    FoundryInventory.model_validate(result)
    return result


def prepare():
    rt.require(not (HOME / 'acceptance.json').exists(), 'acceptance_already_prepared_no_overwrite')
    proof = json.loads((HOME / 'readback.json').read_text())
    rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(proof['at_utc']) < timedelta(hours=2),
               'fresh_metadata_required')
    internal = proof['external_internal_reference']
    rt.require(internal_ready(internal), 'exact_internal_reference_required')
    run = gateway.Release()
    review, expected = run.check(live=False)
    rt.require(review['plan_sha256'] == '9f32083df4f47c2a5b93ee56bfa4d783446d6f54cbbbb1e33f56731a192dff66'
               and gateway.policy_structure(expected) == gateway.policy_structure(run.policy()),
               'already_applied_exact_policy_required')
    previous_backends = json.loads((gateway.HOME / 'backends.json').read_text())
    current_backends = run.arm('/backends')
    from scripts.deployment.fireworks_gateway_stage import check_backend_delta
    check_backend_delta(previous_backends, current_backends)
    # Authenticated full-policy additive guard above preserves the entire external
    # route; existing backend objects must be byte-structurally unchanged too.
    external_backends = [b for b in previous_backends['value'] if 'glm' in b['name'].lower()]
    rt.require(len(external_backends) == 1, 'unique_existing_external_backend_required')
    before_external = json.loads((CATALOG / 'external-inventory.json').read_text())
    old_route = ExternalRoute.model_validate(before_external['routes'][0])
    rt.require(old_route.gateway_validated and old_route.metadata_renewal is None,
               'unchanged_original_external_smoke_required')
    renewed = deepcopy(before_external)
    renewed['routes'][0]['metadata_renewal'] = {
        'kind': 'unchanged_apim_metadata', 'observed_at': proof['at_utc'],
        'historical_acceptance_sha256': historical_acceptance_sha256(old_route),
        'policy_sha256': proof['policy_sha256'],
        'backend_sha256': sha(json.dumps(external_backends[0], sort_keys=True)),
        'reference_metadata_sha256': sha(json.dumps(internal, sort_keys=True)),
        'named_value_resource_id': internal['resource_id'], 'secret_storage': 'apim_internal_secret',
        'fresh_credential_health_verified': False, 'smoke_repeated': False}
    ExternalRoute.model_validate(renewed['routes'][0])
    probes = json.loads((gateway.FAILED_HOME / 'live-rollout-result.json').read_text())['functional_probes']
    old = json.loads((CATALOG / 'foundry-inventory-20261026.json').read_text())
    metadata = json.loads((HOME / 'foundry-metadata.json').read_text())
    accepted = joined_inventory(old, metadata, probes, proof['at_utc'])
    for name in ('foundry-inventory-20261026.json', 'external-inventory.json'):
        rt.save(HOME / ('before-' + name), json.loads((CATALOG / name).read_text()))
    rt.save(CATALOG / 'foundry-inventory-20261026.json', accepted)
    rt.save(CATALOG / 'external-inventory.json', renewed)
    spec = importlib.util.spec_from_file_location('accepted_builder', rt.ROOT / 'services/usage-ingestion/approved_catalog.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    catalog = builder.build(rt.ROOT)
    rt.save(rt.ROOT / 'services/usage-ingestion/ingestion-approved.json', catalog)
    rt.save(HOME / 'acceptance.json', {
        'at_utc': datetime.now(UTC).isoformat(), 'metadata_at_utc': proof['at_utc'],
        'historical_external_smoke_at': before_external['routes'][0]['verified_at'],
        'historical_external_smoke_unchanged': True, 'fresh_external_credential_health_verified': False,
        'external_inference_requests': 0, 'new_model_probes': probes,
        'enabled_chat_models': sorted(m['id'] for m in catalog['models'] if m['enabled']),
        'gateway_plan_sha256': review['plan_sha256'], 'gateway_applied_again': False,
        'foundry_sha256': sha((CATALOG / 'foundry-inventory-20261026.json').read_bytes()),
        'external_sha256': sha((CATALOG / 'external-inventory.json').read_bytes()),
        'ingestion_catalog_sha256': sha(json.dumps(catalog, sort_keys=True)),
        'freshness_limit_seconds': 86400, 'cloud_configuration_writes': 0})
    print(json.dumps({'acceptance_prepared': True, 'enabled': 13, 'external_smoke_restamped': False,
                      'gateway_reapplied': False, 'cloud_configuration_writes': 0}), flush=True)


if __name__ == '__main__':
    try:
        prepare()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'acceptance_failed_sensitive_detail_suppressed'}), flush=True)
        raise SystemExit(1)