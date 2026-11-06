"""Synthetic accepted inventory + isolated SQLite, no Azure or inference traffic."""
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4

import pytest
from aiflux.auth import Principal
from aiflux.external_inventory import AcceptedInventory
from aiflux.model_inventory_sync import sync_verified_models
from aiflux.models import AuditEvent, ManagedModelEndpoint, ModelRouterConfig, TeamSubscription
from conftest import ADMIN_USER, HOME
from sqlalchemy import event, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
NEW = {
    'claude-sonnet-5-5', 'claude-opus-5-5', 'claude-opus-5-5-fast',
    'claude-haiku-5-5', 'claude-opus-4-8', 'gpt-6.1-terra', 'gpt-6-luna', 'Mistral-Large-3',
}


def snapshot(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def principal(env):
    return Principal(env.orgs['admin'], 'IDS', HOME, ADMIN_USER, 'ids_admin')


@pytest.fixture
def accepted_eight(env, tmp_path):
    """Install explicit test-only acceptance, never modify repository artifacts."""
    manifest = json.loads((ROOT / 'gateway/catalog/foundry-eight-candidate-routes.json').read_text())
    data = json.loads((ROOT / 'gateway/catalog/foundry-inventory-20261026.json').read_text())
    requested = json.loads((ROOT / '.deployment/foundry-eight-20261030/requested.json').read_text())
    for route in data['routes']:
        route['endpoint_url'] = manifest['gateway_url']
    for alias in sorted(NEW):
        native = requested[alias]
        model = native['properties']['model']
        data['deployments'].append({
            'id': native['id'], 'name': alias, 'model_name': model['name'],
            'model_version': model['version'], 'model_format': model['format'],
            'provisioning_state': 'Succeeded', 'capacity': native['sku']['capacity'],
            'sku': native['sku']['name'], 'chat_completion': True,
        })
        data['routes'].append({
            'alias': alias, 'deployment_id': native['id'], 'backend_model': alias,
            'model_name': model['name'], 'model_version': model['version'],
            'endpoint_url': manifest['gateway_url'], 'api_format': 'openai-chat-completions',
            'capabilities': ['chat'], 'max_completion_tokens': 1024,
            'upstream_token_parameter': manifest['routes'][alias]['token_parameter'],
            'gateway_validated': True,  # Synthetic test-only acceptance.
        })
    data['verified_at'] = datetime.now(UTC).isoformat()
    # Same configured filename, isolated release context; no appsetting change.
    path = tmp_path / 'foundry-inventory-20261026.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    env.settings.foundry_inventory_path = path
    external = json.loads((ROOT / 'gateway/catalog/external-inventory.json').read_text())
    external['routes'][0].pop('metadata_renewal', None)
    external['routes'][0]['verified_at'] = datetime.now(UTC).isoformat()
    external_path = tmp_path / 'external.json'
    external_path.write_text(json.dumps(external), encoding='utf-8')
    env.settings.external_inventory_path = external_path
    models = [{
        'id': alias, 'provider': metadata['provider'], 'backend_model': alias,
        'capabilities': ['chat'], 'enabled': True, 'max_completion_tokens': 1024,
    } for alias, metadata in manifest['routes'].items()]
    models += [{'id': 'glm-5.3', 'provider': 'ModelArts', 'backend_model': 'glm-5.3',
                'capabilities': ['chat'], 'enabled': True, 'max_completion_tokens': 1024}]
    from aiflux.display_pricing import manifest as pricing_manifest
    scopes = {r['model']: r for r in pricing_manifest()['rates']}
    for model in models:
        model['region'] = scopes[model['id']]['region']
    env.settings.catalog_path.write_text(json.dumps({'models': models}), encoding='utf-8')
    env.settings.catalog_configured = True
    return set(manifest['routes']) | {'glm-5.3'}


@pytest.mark.parametrize('router_enabled', [False, True])
def test_opt_out_preserves_every_router_byte_and_operator_field(env, accepted_eight, router_enabled):
    with Session(env.db_engine) as db:
        db.add(ModelRouterConfig(
            id='default', enabled=router_enabled, strategy='operator-strategy',
            decision_endpoint='https://operator.invalid/decision', default_model='operator-default',
            candidate_models_json='[ "gpt-4o", "glm-5.3" ]\n',
            rules_json='[ { "preserve": true } ]\n', updated_at=datetime(2026, 1, 1, tzinfo=UTC)))
        for alias in ('gpt-4o', 'glm-5.3', 'claude-sonnet-5-5'):
            db.add(ManagedModelEndpoint(
                id=alias, display_name='Operator ' + alias, provider='operator-provider',
                vendor='operator-vendor', region='operator-region', backend_model='stale',
                endpoint_url='https://stale.invalid/v1', enabled=False, coming_soon=True,
                content_safety_enabled=False, priority=7, context_window=3333,
                input_per_million=Decimal('7.25'), output_per_million=Decimal('9.5'),
                cached_input_per_million=Decimal('1.125'), currency='SGD', description='Keep exactly'))
        db.add(ManagedModelEndpoint(id='unrelated', display_name='Unrelated', provider='operator',
                                    vendor='operator', backend_model='unrelated', enabled=False))
        db.commit()
        router_before = snapshot(db.get(ModelRouterConfig, 'default'))
        existing_before = {alias: snapshot(db.get(ManagedModelEndpoint, alias))
                           for alias in ('gpt-4o', 'glm-5.3', 'claude-sonnet-5-5', 'unrelated')}
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(env.db_engine, 'before_cursor_execute', record)
    try:
        with Session(env.db_engine) as db:
            first = sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
            second = sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
    finally:
        event.remove(env.db_engine, 'before_cursor_execute', record)
    assert not any('model_router_configs' in statement for statement in statements)
    assert set(first['accepted_models']) == accepted_eight and len(accepted_eight) == 21
    assert set(first['changed']) == accepted_eight - set(existing_before)
    assert second['changed'] == []
    assert first['auto_enabled'] is None  # Router state intentionally not read.
    assert first['gateway_published'] is False and first['prices_changed'] is False
    with Session(env.db_engine) as db:
        assert snapshot(db.get(ModelRouterConfig, 'default')) == router_before
        for alias, before in existing_before.items():
            row = db.get(ManagedModelEndpoint, alias)
            after = snapshot(row)
            assert after == before
        assert {row.id for row in db.scalars(select(ManagedModelEndpoint))} == accepted_eight | {'unrelated'}
        assert db.get(ManagedModelEndpoint, 'Mistral-Large-3').provider == 'Mistral AI'
        assert db.get(ManagedModelEndpoint, 'Mistral-Large-3').region == 'eastus'
        assert db.get(ManagedModelEndpoint, 'Decision-1') is None
        audits = list(db.scalars(select(AuditEvent)))
        assert len(audits) == 18
        assert {a.action for a in audits} == {'model_inventory.synchronized'}


def test_opt_out_does_not_create_router(env, accepted_eight):
    with Session(env.db_engine) as db:
        assert db.get(ModelRouterConfig, 'default') is None
        sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
        assert db.get(ModelRouterConfig, 'default') is None


def test_chat_only_adds_exact_eight_and_leaves_existing_thirteen_unchanged(env, accepted_eight):
    inventory = AcceptedInventory.load(env.settings)
    old = accepted_eight - NEW
    assert len(old) == 13
    with Session(env.db_engine) as db:
        for alias in sorted(old):
            route = inventory.route(alias)
            db.add(ManagedModelEndpoint(
                id=alias, display_name='Operator ' + alias, provider=inventory.provider(alias),
                vendor='operator', region='operator-region', enabled=False, coming_soon=True,
                backend_model=route.backend_model, endpoint_url=route.endpoint_url,
                max_completion_tokens=route.max_completion_tokens,
                capabilities_json=json.dumps(route.capabilities), priority=7,
                input_per_million=Decimal('7.25'), output_per_million=Decimal('9.5')))
        db.commit()
        before = {alias: snapshot(db.get(ManagedModelEndpoint, alias)) for alias in old}
        first = sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
        assert set(first['changed']) == NEW
        assert sync_verified_models(db, env.settings, principal(env), reconcile_router=False)['changed'] == []
        assert {alias: snapshot(db.get(ManagedModelEndpoint, alias)) for alias in old} == before
        assert len(list(db.scalars(select(AuditEvent)))) == 8
        assert db.get(ModelRouterConfig, 'default') is None


@pytest.mark.parametrize('explicit_true', [False, True])
def test_historical_callers_retain_router_reconciliation(env, accepted_eight, explicit_true):
    with Session(env.db_engine) as db:
        db.add(ModelRouterConfig(id='default', enabled=True, default_model='stale',
                                 candidate_models_json='[ "stale" ]'))
        db.commit()
        kwargs = {'reconcile_router': True} if explicit_true else {}
        result = sync_verified_models(db, env.settings, principal(env), **kwargs)
        router = db.get(ModelRouterConfig, 'default')
        assert router.enabled is False
        assert router.default_model == 'gpt-5.6-luna'
        assert json.loads(router.candidate_models_json) == sorted(accepted_eight)
        assert 'router:default' in result['changed']
        assert sync_verified_models(db, env.settings, principal(env), **kwargs)['changed'] == []


def test_pending_new_route_never_synchronized(env, accepted_eight):
    path = env.settings.foundry_inventory_path
    data = json.loads(path.read_text())
    next(r for r in data['routes'] if r['alias'] == 'claude-opus-5-5')['gateway_validated'] = False
    path.write_text(json.dumps(data), encoding='utf-8')
    with Session(env.db_engine) as db:
        result = sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
        assert set(result['accepted_models']) == accepted_eight - {'claude-opus-5-5'}
        assert db.get(ManagedModelEndpoint, 'claude-opus-5-5') is None
        assert db.get(ManagedModelEndpoint, 'glm-5.3') is not None


def test_existing_and_new_eligible_subscriptions_need_no_new_gate_and_gets_do_not_write(env, accepted_eight):
    def subscription(name):
        return TeamSubscription(id=str(uuid4()), organization_id=env.orgs['customer'],
                                name=name, team='eligible', state='active', desired_state='active',
                                idempotency_key=str(uuid4()))

    with Session(env.db_engine) as db:
        old = subscription('Existing eligible')
        db.add(old)
        db.commit()
        old_id = old.id
        before = snapshot(old)
        sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
        assert snapshot(db.get(TeamSubscription, old_id)) == before
        fresh = subscription('New eligible')
        db.add(fresh)
        db.commit()
        fresh_id = fresh.id
    writes = []

    def record(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE'}:
            writes.append(statement)

    event.listen(env.db_engine, 'before_cursor_execute', record)
    try:
        for _ in range(2):
            response = env.client.get('/api/models', headers=env.customer)
            assert response.status_code == 200
            assert {m['id'] for m in response.json()['items']} == accepted_eight
        subscriptions = env.client.get('/api/subscriptions', headers=env.customer)
        assert subscriptions.status_code == 200
        assert {s['id'] for s in subscriptions.json()['items']} >= {old_id, fresh_id}
        assert AcceptedInventory.load(env.settings).accepted_aliases(env.settings) == accepted_eight
    finally:
        event.remove(env.db_engine, 'before_cursor_execute', record)
    assert writes == []
    assert env.apim.calls == []