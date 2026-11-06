"""Chat-only sync and read-only accepted attribution, SQLite/synthetic evidence only."""
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from aiflux.display_pricing import detail_estimates, estimate_summary, manifest
from aiflux.external_inventory import AcceptedInventory
from aiflux.model_inventory_sync import sync_verified_models
from aiflux.models import AuditEvent, ManagedModelEndpoint, ModelRouterConfig, UsageRecord
from aiflux.rate_card import get_rate_card, periods
from test_foundry_eight_sync import accepted_eight, NEW, principal, snapshot


def test_existing_endpoint_false_no_router_reads_and_all_21_operator_rows_exact(env, accepted_eight):
    with Session(env.db_engine) as db:
        for i in range(21):
            db.add(ManagedModelEndpoint(id='operator-' + str(i), display_name='keep', provider='operator',
                                       vendor='operator', backend_model='keep', enabled=False, coming_soon=True, region='keep'))
        db.add(ModelRouterConfig(id='default', enabled=True, candidate_models_json='[ "keep" ]'))
        db.commit()
        before = {r.id: snapshot(r) for r in db.scalars(select(ManagedModelEndpoint))}
        router = snapshot(db.get(ModelRouterConfig, 'default'))
    statements = []
    def record(conn, cursor, statement, params, context, many):
        statements.append(statement.lower())
    event.listen(env.db_engine, 'before_cursor_execute', record)
    try:
        response = env.client.post('/api/admin/model-deployments/sync?reconcile_router=false', headers=env.admin)
    finally:
        event.remove(env.db_engine, 'before_cursor_execute', record)
    assert response.status_code == 200 and response.json()['auto_enabled'] is None
    assert not any('model_router_configs' in s for s in statements)
    assert not any(s.lstrip().startswith(('update ', 'delete ')) for s in statements)
    with Session(env.db_engine) as db:
        assert {k: snapshot(db.get(ManagedModelEndpoint, k)) for k in before} == before
        assert snapshot(db.get(ModelRouterConfig, 'default')) == router
        for alias in NEW:
            row = db.get(ManagedModelEndpoint, alias)
            assert row.region == 'eastus' and row.enabled and not row.coming_soon
        assert get_rate_card(db, env.settings).total == 21
    assert env.client.post('/api/admin/model-deployments/sync?reconcile_router=false', headers=env.customer).status_code == 403
    assert env.client.post('/api/admin/model-deployments/sync?reconcile_router=false').status_code == 401
    assert env.apim.calls == []


def test_commit_failure_rolls_back_insert_and_audit(env, accepted_eight, monkeypatch):
    with Session(env.db_engine) as db:
        def fail():
            db.flush()
            raise RuntimeError('synthetic commit failure')
        monkeypatch.setattr(db, 'commit', fail)
        with pytest.raises(RuntimeError, match='synthetic commit failure'):
            sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
        assert list(db.scalars(select(ManagedModelEndpoint))) == []
        assert list(db.scalars(select(AuditEvent))) == []


def test_missing_catalog_region_rolls_back_all_insertions(env, accepted_eight):
    data = json.loads(env.settings.catalog_path.read_text())
    next(m for m in data['models'] if m['id'] == 'gpt-6.1-terra')['region'] = ''
    env.settings.catalog_path.write_text(json.dumps(data))
    with Session(env.db_engine) as db:
        with pytest.raises(Exception, match='Accepted catalog provider/region'):
            sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
        assert list(db.scalars(select(ManagedModelEndpoint))) == []
        assert list(db.scalars(select(AuditEvent))) == []


def test_unknown_usage_exact_accepted_scope_history_scoping_and_no_finance_writes(env, accepted_eight):
    inventory = AcceptedInventory.load(env.settings)
    boundary = datetime(2026, 10, 30, 12, tzinfo=UTC)
    entries = [{'model': 'gpt-6.1-terra', 'provider': 'OpenAI', 'region': 'eastus',
                'origin': 'configured', 'input': '3', 'output': '7', 'valid_from': boundary}]
    with Session(env.db_engine) as db:
        for ident, alias, provider, region, when, cache in [
            ('before', 'gpt-6.1-terra', 'unknown', 'unknown', boundary-timedelta(seconds=1), 0),
            ('after', 'gpt-6.1-terra', 'unknown', 'unknown', boundary, 0),
            ('other-org', 'gpt-6.1-terra', 'unknown', 'unknown', boundary, 0),
            ('wrong-case', 'GPT-6.1-terra', 'unknown', 'unknown', boundary, 0),
            ('conflict', 'gpt-6.1-terra', 'wrong', 'eastus', boundary, 0),
            ('wrong-region', 'gpt-6.1-terra', 'OpenAI', 'westus', boundary, 0),
            ('cache-unknown', 'claude-sonnet-5-5', 'unknown', 'unknown', boundary, None),
        ]:
            db.add(UsageRecord(id=ident, organization_id='other' if ident == 'other-org' else 'org',
                subscription_id='sub', model=alias, provider=provider, region=region, occurred_at=when,
                input_tokens=100, output_tokens=20, cached_input_tokens=cache, cache_write_tokens=cache,
                cost=Decimal('12.50'), currency='SGD', status_code=200, completeness='complete'))
        db.commit()
        before = {r.id: snapshot(r) for r in db.scalars(select(UsageRecord))}
        writes = []
        def record(conn, cursor, statement, params, context, many):
            if statement.lstrip().split()[0].upper() in {'INSERT','UPDATE','DELETE'}:
                writes.append(statement)
        event.listen(env.db_engine, 'before_cursor_execute', record)
        try:
            args = {'periods': periods(entries), 'inventory': inventory}
            values = detail_estimates(db, list(before), **args)
            assert values['before']['estimated_cost_usd'] == '0.000200000000'
            assert values['after']['estimated_cost_usd'] == '0.000440000000'
            for ident in ('wrong-case', 'conflict', 'wrong-region', 'cache-unknown'):
                assert values[ident]['estimated_cost_usd'] is None
            summary = estimate_summary(db, [UsageRecord.organization_id == 'org', UsageRecord.subscription_id == 'sub'], **args)[0]
            assert summary['estimated_requests'] == 2 and summary['unestimated_requests'] == 4
            assert {r.id: snapshot(r) for r in db.scalars(select(UsageRecord))} == before
            # A tariff or alias alone is never provenance.
            assert detail_estimates(db, ['after'], periods=periods(entries))['after']['estimated_cost_usd'] is None
            path = env.settings.foundry_inventory_path
            raw = json.loads(path.read_text())
            next(r for r in raw['routes'] if r['alias'] == 'gpt-6.1-terra')['gateway_validated'] = False
            path.write_text(json.dumps(raw))
            assert detail_estimates(db, ['after'], inventory=AcceptedInventory.load(env.settings))['after']['estimated_cost_usd'] is None
        finally:
            event.remove(env.db_engine, 'before_cursor_execute', record)
        assert writes == []