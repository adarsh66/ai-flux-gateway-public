"""Explicit proof-required successor22 adapter; never manufactures acceptance.

Historical approved_catalog.py remains byte-bound and unchanged. Callers must
provide the independently reviewed SHA256 of a FUTURE successful probe proof.
No proof or selected accepted inventory is created by this module.
"""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from uuid import UUID

PROFILE = 'foundry-successor22-accepted'
NINTH = 'mistral-medium-3-5'
GATEWAY = 'https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1'
CONTRACT = {'model_name': NINTH, 'version': '1', 'provider': 'Mistral AI',
            'sku': 'GlobalStandard', 'capacity': 5000, 'token_parameter': 'max_tokens',
            'upstream_url': 'https://poc-ids-token-ex-foundry.services.ai.azure.com/openai/v1',
            'api_format': 'openai-chat-completions'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def module(root, name):
    spec = importlib.util.spec_from_file_location('successor22_' + name,
        root / 'services/usage-ingestion' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def validate_ninth(deployment, route, proof, *, read):
    """Validate source-bound actual intent/response/metadata/correlation receipts.

    ``read`` must return immutable bytes identified by the reviewed proof's
    hashes; injectable solely to allow offline synthetic contract fixtures.
    """
    def receipt(key):
        entry = proof[key]
        raw = read(entry['path'])
        require(sha(raw) == entry['sha256'], 'bound original receipt bytes:' + key)
        return json.loads(raw)
    intent, response, arm = (receipt(k) for k in ('intent', 'response', 'deployment'))
    require(proof['profile'] == PROFILE and proof['alias'] == NINTH
            and proof['total_consumed_calls'] == 1 and proof['remaining_call_budget'] == 0,
            'one genuine ninth call only')
    require(intent['alias'] == NINTH and intent['consumed_before_send'] is True
            and intent['max_requests'] == 1 and intent['retries'] == 0
            and intent['fallback'] is False and 1 <= intent['max_completion_tokens'] <= 128,
            'bounded no-retry original intent')
    require(response['alias'] == NINTH and response['status'] == 200
            and response['assistant_nonempty'] is True and response['transport_invocations'] == 1
            and response['finish_reason'] == 'stop' and not response.get('parse_failed')
            and not response.get('usage_invalid')
            and response['client_request_id'] == intent['client_request_id']
            and response['intent_sha256'] == proof['intent']['sha256']
            and response['policy_sha256'] == intent['policy_sha256'] == proof['policy_sha256'],
            'actual successful original gateway response')
    raw_response = read(proof['raw_response']['path'])
    require(sha(raw_response) == proof['raw_response']['sha256'] == response['response_sha256'], 'original response body hash')
    body = json.loads(raw_response)
    require(body['id'] == response['response_id'] and body['model'] == response['response_model']
            and body['choices'][0]['message']['role'] == 'assistant'
            and isinstance(body['choices'][0]['message']['content'], str)
            and bool(body['choices'][0]['message']['content'].strip())
            and body['choices'][0]['finish_reason'] == 'stop', 'actual nonempty assistant body')
    UUID(response['correlation_id'])
    UUID(intent['client_request_id'])
    observed = datetime.fromisoformat(response['at'].replace('Z', '+00:00'))
    require(observed.tzinfo is not None and observed <= datetime.now(UTC), 'actual past probe timestamp')
    props = arm['properties']
    require(arm['id'] == deployment['id'] and arm['name'] == NINTH
            and props['model'] == {'format': 'Mistral AI', 'name': NINTH, 'version': '1'}
            and arm['sku']['name'] == deployment['sku'] == 'GlobalStandard'
            and arm['sku']['capacity'] == props['currentCapacity'] == deployment['capacity'] == 5000
            and props['provisioningState'] == deployment['provisioning_state'] == 'Succeeded'
            and props['capabilities']['chatCompletion'] == 'true'
            and props['raiPolicyName'] == 'Microsoft.DefaultV2', 'fresh exact ARM contract')
    require(deployment['name'] == deployment['model_name'] == route['alias'] == route['backend_model'] == NINTH
            and deployment['model_format'] == 'Mistral AI' and deployment['model_version'] == route['model_version'] == '1'
            and deployment['chat_completion'] is True and route['deployment_id'] == deployment['id']
            and route['endpoint_url'] == GATEWAY and route['gateway_validated'] is True
            and route['capabilities'] == ['chat'] and route['api_format'] == 'openai-chat-completions'
            and route['upstream_token_parameter'] == 'max_tokens' and route['max_completion_tokens'] == 1024,
            'accepted public binding not native endpoint')
    identity = response['response_model']
    # No arbitrary casefold/prefix/version mapping. A non-exact response must
    # have a reviewed explicit mapping and exact correlated deployment logs.
    if identity != NINTH:
        correlated = receipt('correlated')
        mapping = proof['identity_mapping']
        require(mapping == {'response_model': identity, 'deployment_name': NINTH,
                'model_name': NINTH, 'model_version': '1', 'model_format': 'Mistral AI'}, 'explicit exact identity map')
        llm, gateway = correlated['llm_row'], correlated['gateway_row']
        require(correlated['llm_row_count_returned'] == correlated['gateway_row_count_returned'] == 1
                and correlated['original_response_sha256'] == response['response_sha256']
                and llm['RequestId'] == response['response_id'] and llm['DeploymentName'] == NINTH
                and llm['ModelName'] == identity and llm['CorrelationId'] == gateway['CorrelationId'] == response['correlation_id']
                and gateway['ResponseCode'] == gateway['BackendResponseCode'] == 200, 'exact correlated identity')
    usage = response['usage']
    require(all(type(usage[k]) is int for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
            and usage['prompt_tokens'] > 0 and 1 <= usage['completion_tokens'] <= intent['max_completion_tokens']
            and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
            and all(body['usage'][k] == usage[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')),
            'actual measured usage')
    return response


def build(root, *, inventory_path=None, proof_path=None, proof_sha256=None):
    require(inventory_path is not None and proof_path is not None
            and isinstance(proof_sha256, str) and len(proof_sha256) == 64, 'future independently reviewed proof required')
    root = Path(root)
    def selected(path):
        path = Path(path)
        return path if path.is_absolute() else root / path
    selected_inventory = json.loads(selected(inventory_path).read_bytes())
    proof_file = selected(proof_path)
    raw = proof_file.read_bytes()
    require(sha(raw) == proof_sha256, 'independently reviewed future proof hash')
    proof = json.loads(raw)
    def read(path):
        path = Path(path)
        require(not path.is_absolute() and '..' not in path.parts, 'proof path escape')
        return (proof_file.parent / path).read_bytes()
    predecessor = json.loads((root / 'gateway/catalog/foundry-eight-candidate-routes.json').read_bytes())
    manifest = json.loads((root / 'gateway/catalog/foundry-successor22-candidate-routes.json').read_bytes())
    require(manifest == {**predecessor, 'routes': {**predecessor['routes'], NINTH: CONTRACT}}, 'exact successor manifest')
    require({r['alias'] for r in selected_inventory['routes']} == set(manifest['routes'])
            and len(selected_inventory['routes']) == 21
            and {d['name'] for d in selected_inventory['deployments']} == set(manifest['routes']) | {'Decision-1'}
            and len(selected_inventory['deployments']) == 22, 'exact21 Foundry plus disabled Decision inventory')
    route = next(r for r in selected_inventory['routes'] if r['alias'] == NINTH)
    deployment = next(d for d in selected_inventory['deployments'] if d['name'] == NINTH)
    validate_ninth(deployment, route, proof, read=read)
    projected = deepcopy(selected_inventory)
    projected['routes'] = [r for r in projected['routes'] if r['alias'] != NINTH]
    projected['deployments'] = [d for d in projected['deployments'] if d['name'] != NINTH]
    historical = module(root, 'accepted_catalog_profile')
    # Historical exact proof comparison checks every predecessor byte/property.
    with tempfile.TemporaryDirectory(prefix='successor22-historical-proof-') as temp:
        path = Path(temp) / 'projected.json'
        path.write_text(json.dumps(projected), encoding='utf-8')
        result = historical.build(root, inventory_path=path)
    result['models'].insert(-1, {'id': NINTH, 'provider': 'Mistral AI', 'enabled': True,
        'capabilities': ['chat'], 'backend_model': NINTH, 'region': 'eastus', 'max_completion_tokens': 1024})
    require({r['id'] for r in result['models'] if r['enabled']} == set(manifest['routes']) | {'glm-5.3'}, 'exact22 catalog set')
    return result


def verify_packaged(root, **kwargs):
    expected = build(root, **kwargs)
    for path in ('gateway/catalog/ingestion-approved.json', 'gateway/catalog/dev-models.json',
                 'gateway/catalog/models.json', 'services/usage-ingestion/ingestion-approved.json'):
        require(json.loads((root / path).read_bytes()) == expected, 'all effective packaged catalog paths exact22')