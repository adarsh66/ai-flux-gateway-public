"""Synthetic offline successor contracts; no live acceptance or metadata writes."""
from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from aiflux import display_pricing as pricing
from aiflux.external_inventory import AcceptedInventory
from aiflux.finops import usage_models
from aiflux.models import ManagedModelEndpoint, UsageRecord
from test_foundry_eight_sync import accepted_eight, NEW

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('test_successor22_builder', ROOT / 'services/usage-ingestion/successor22_catalog.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
NINTH = builder.NINTH


def test_exact_manifest_adds_only_ninth_preserves_all21():
    old = json.loads((ROOT / 'gateway/catalog/foundry-eight-candidate-routes.json').read_bytes())
    new = json.loads((ROOT / 'gateway/catalog/foundry-successor22-candidate-routes.json').read_bytes())
    assert new == {**old, 'routes': {**old['routes'], NINTH: builder.CONTRACT}}
    assert len(set(new['routes']) | {'glm-5.3'}) == 22
    assert not {'auto', 'Decision-1'} & set(new['routes'])


def test_default_catalog_cannot_claim_future_acceptance():
    with pytest.raises(ValueError, match='future independently reviewed proof required'):
        builder.build(ROOT)
    spec = importlib.util.spec_from_file_location('test_explicit_successor_profile', ROOT / 'services/usage-ingestion/accepted_catalog_profile.py')
    accepted = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(accepted)
    with pytest.raises(ValueError, match='future independently reviewed proof required'):
        accepted.build(ROOT, profile=builder.PROFILE)


@pytest.fixture
def ninth_proof():
    # All receipts here are synthetic fixtures; none is emitted into production
    # acceptance evidence or used to promote/package the ninth deployment.
    alias = NINTH
    deploy_id = '/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry/deployments/' + alias
    deployment = {'id': deploy_id, 'name': alias, 'model_name': alias, 'model_version': '1',
        'model_format': 'Mistral AI', 'sku': 'GlobalStandard', 'capacity': 5000,
        'provisioning_state': 'Succeeded', 'chat_completion': True}
    route = {'alias': alias, 'deployment_id': deploy_id, 'backend_model': alias, 'model_version': '1',
        'endpoint_url': builder.GATEWAY, 'gateway_validated': True, 'capabilities': ['chat'],
        'api_format': 'openai-chat-completions', 'upstream_token_parameter': 'max_tokens', 'max_completion_tokens': 1024}
    intent = {'alias': alias, 'consumed_before_send': True, 'max_requests': 1, 'retries': 0,
        'fallback': False, 'max_completion_tokens': 128, 'client_request_id': str(uuid4()), 'policy_sha256': 'a' * 64}
    raw_body = {'id': 'synthetic-response', 'model': alias, 'choices': [{'message': {'role': 'assistant',
        'content': 'Fixture only.'}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 18, 'completion_tokens': 13, 'total_tokens': 31}}
    body = json.dumps(raw_body).encode()
    intent_raw = json.dumps(intent).encode()
    response = {'at': datetime.now(UTC).isoformat(), 'alias': alias, 'status': 200, 'assistant_nonempty': True,
        'transport_invocations': 1, 'finish_reason': 'stop', 'client_request_id': intent['client_request_id'],
        'intent_sha256': builder.sha(intent_raw), 'policy_sha256': intent['policy_sha256'],
        'response_sha256': builder.sha(body), 'response_id': raw_body['id'], 'response_model': alias,
        'correlation_id': str(uuid4()), 'usage': raw_body['usage']}
    arm = {'id': deploy_id, 'name': alias, 'sku': {'name': 'GlobalStandard', 'capacity': 5000},
        'properties': {'model': {'format': 'Mistral AI', 'name': alias, 'version': '1'},
            'currentCapacity': 5000, 'provisioningState': 'Succeeded', 'capabilities': {'chatCompletion': 'true'},
            'raiPolicyName': 'Microsoft.DefaultV2'}}
    receipts = {'intent': intent_raw, 'response': json.dumps(response).encode(),
                'deployment': json.dumps(arm).encode(), 'raw_response': body}
    proof = {'profile': builder.PROFILE, 'alias': alias, 'total_consumed_calls': 1,
        'remaining_call_budget': 0, 'policy_sha256': intent['policy_sha256'],
        **{k: {'path': k, 'sha256': builder.sha(v)} for k, v in receipts.items()}}
    return deployment, route, proof, receipts


def test_synthetic_future_proof_contract(ninth_proof):
    d, r, proof, receipts = ninth_proof
    assert builder.validate_ninth(d, r, proof, read=receipts.__getitem__)['alias'] == NINTH


@pytest.mark.parametrize('defect', ['unaccepted', 'native-endpoint', 'wrong-backend', 'version', 'sku',
    'provider', 'capacity', 'response-tamper', 'no-budget', 'foreign-alias', 'fabricated-flag-only'])
def test_future_proof_fails_closed(ninth_proof, defect):
    d, r, proof, receipts = deepcopy(ninth_proof)
    if defect == 'unaccepted': r['gateway_validated'] = False
    elif defect == 'native-endpoint': r['endpoint_url'] = builder.CONTRACT['upstream_url']
    elif defect == 'wrong-backend': r['backend_model'] = 'Mistral-Large-3'
    elif defect == 'version': d['model_version'] = '2'
    elif defect == 'sku': d['sku'] = 'Standard'
    elif defect == 'provider': d['model_format'] = 'Mistral'
    elif defect == 'capacity': d['capacity'] = 1
    elif defect == 'response-tamper': receipts['response'] += b' '
    elif defect == 'no-budget': proof['total_consumed_calls'] = 2
    elif defect == 'foreign-alias': proof['alias'] = 'Mistral-Medium-3-5'
    elif defect == 'fabricated-flag-only': proof.pop('response')
    with pytest.raises((ValueError, KeyError)):
        builder.validate_ninth(d, r, proof, read=receipts.__getitem__)


def test_pricing_default21_then_explicit22_old_rates_identical():
    old = pricing.manifest()
    new = pricing.manifest(True, True)
    assert NINTH not in {r['model'] for r in old['rates']}
    assert {r['model'] for r in new['rates']} == {r['model'] for r in old['rates']} | {NINTH}
    assert new['rates'][:-1] == old['rates']
    assert new['source_sha256'].items() >= old['source_sha256'].items()
    ninth = new['rates'][-1]
    assert ninth['status'] == 'platform_default'
    assert (ninth['input'], ninth['output']) == ('0.50', '1.50')
    assert 'NOT a Medium 3.5 tariff' in ninth['source_model']
    assert 'cached' not in ninth and 'write' not in ninth
    historical = (ROOT / 'services/control-plane/src/aiflux/pricing/rates-20261027.json').read_bytes()
    assert pricing.manifest(False)['sha256'] == builder.sha(historical)
    assert not (ROOT / 'services/control-plane/src/aiflux/pricing/successor22-activation.json').exists()


def test_usage_selectors_include_current_exact21_and_later22_no_DML(env, accepted_eight):
    for selected in (accepted_eight, accepted_eight | {NINTH}):
        with Session(env.db_engine) as db:
            statements = []
            def record(conn, cursor, statement, params, context, many):
                statements.append(statement.lower())
            event.listen(env.db_engine, 'before_cursor_execute', record)
            try:
                result = usage_models(db, env.orgs['customer'], 30, None, current_models=sorted(selected))
                assert set(result['items']) == selected
                assert result['total'] == len(selected)
                assert not list(db.scalars(select(UsageRecord)))
            finally:
                event.remove(env.db_engine, 'before_cursor_execute', record)
            assert not any(v.lstrip().startswith(('insert ', 'update ', 'delete ')) for v in statements)


def test_original_binding_regression_native_vs_public_no_metadata_write(env, accepted_eight):
    inventory = AcceptedInventory.load(env.settings)
    original13 = accepted_eight - NEW
    assert len(original13) == 13
    for alias in original13:
        route = inventory.route(alias)
        assert inventory.matches(alias, route.backend_model, [route.endpoint_url])
        native = ('https://api-ap-southeast-1.modelarts-maas.com/v1' if alias == 'glm-5.3'
                  else 'https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1')
        assert not inventory.matches(alias, route.backend_model, [native])
        assert not inventory.matches(alias, 'wrong-' + route.backend_model, [route.endpoint_url])


def test_both_portal_usage_model_APIs_follow_current_catalog(env, accepted_eight):
    # This fixture supplies accepted configured21; the same endpoint list is
    # used by admin and customer, including a new org with no usage records.
    for headers in (env.customer, env.admin):
        models = env.client.get('/api/models', headers=headers)
        assert models.status_code == 200
        expected = {m['id'] for m in models.json()['items']}
        path = '/api/admin/usage/models' if headers is env.admin else '/api/usage/models'
        response = env.client.get(path, headers=headers)
        assert response.status_code == 200
        assert set(response.json()['items']) == expected == accepted_eight