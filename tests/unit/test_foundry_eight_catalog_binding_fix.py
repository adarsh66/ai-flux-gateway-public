"""Exact retained eight usage shapes; synthetic SQLite, no runtime writes."""
import csv
import io
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from aiflux.display_pricing import detail_estimates, estimate_summary
from aiflux.external_inventory import AcceptedInventory
from aiflux.model_inventory_sync import sync_verified_models
from aiflux.models import ManagedModelEndpoint, ModelRouterConfig, UsageRecord
from test_foundry_eight_sync import NEW, accepted_eight, principal, snapshot


def test_effective_unconfigured_path_inserts_only_missing_eight_preserves_live_21(env, accepted_eight):
    # Production uses the packaged accepted catalog at models.json while the
    # configured flag remains false. It does NOT use SQL as catalog authority.
    env.settings.catalog_configured = False
    env.settings.local_auth_enabled = True
    inventory = AcceptedInventory.load(env.settings)
    old = accepted_eight - NEW
    assert len(old) == 13
    with Session(env.db_engine) as db:
        for alias in sorted(old | {'operator-' + str(i) for i in range(8)}):
            db.add(ManagedModelEndpoint(id=alias, display_name='keep', provider='operator',
                vendor='keep', region='keep', backend_model='keep', enabled=False, coming_soon=True,
                input_per_million=Decimal('7.25'), output_per_million=Decimal('9.5')))
        db.add(ModelRouterConfig(id='default', enabled=True, candidate_models_json='[ "keep" ]'))
        db.commit()
        before = {r.id: snapshot(r) for r in db.scalars(select(ManagedModelEndpoint))}
        router = snapshot(db.get(ModelRouterConfig, 'default'))
        assert len(before) == 21
        result = sync_verified_models(db, env.settings, principal(env), reconcile_router=False)
        assert set(result['changed']) == NEW
        assert {k: snapshot(db.get(ManagedModelEndpoint, k)) for k in before} == before
        assert snapshot(db.get(ModelRouterConfig, 'default')) == router
        for alias in NEW:
            row = db.get(ManagedModelEndpoint, alias)
            route = inventory.route(alias)
            assert row.provider == inventory.provider(alias) and row.region == 'eastus'
            assert row.backend_model == route.backend_model and row.endpoint_url == route.endpoint_url
            assert row.enabled and not row.coming_soon
        assert sync_verified_models(db, env.settings, principal(env), reconcile_router=False)['changed'] == []


def test_exact_eight_backend_missing_sql_detail_summary_csv_and_stored_finance(env, accepted_eight):
    inventory = AcceptedInventory.load(env.settings)
    with Session(env.db_engine) as db:
        for alias in sorted(NEW):
            cache = None if alias == 'Mistral-Large-3' else 0
            db.add(UsageRecord(id=alias, organization_id=env.orgs['customer'], subscription_id='sub',
                model=alias, provider='', region='', occurred_at=datetime(2026, 10, 30, 18, tzinfo=UTC),
                input_tokens=18, output_tokens=13, cached_input_tokens=cache, cache_write_tokens=cache,
                status_code=200, completeness='backend_attribution_missing', cost=None, currency=None))
        db.commit()
        before = {r.id: snapshot(r) for r in db.scalars(select(UsageRecord))}
        db.info['settings'] = env.settings
        statements = []
        def record(conn, cursor, statement, params, context, many):
            statements.append(statement.lower())
        event.listen(env.db_engine, 'before_cursor_execute', record)
        try:
            details = detail_estimates(db, sorted(NEW), inventory=inventory)
            summary = estimate_summary(db, [UsageRecord.organization_id == env.orgs['customer']], inventory=inventory)[0]
            assert summary['estimated_requests'] == 7 and summary['unestimated_requests'] == 1
            assert summary['approximate_requests'] == 0
            assert details['Mistral-Large-3']['estimated_cost_usd'] is None
            assert sum(Decimal(d['estimated_cost_usd'] or '0') for d in details.values()) == Decimal(summary['estimated_cost_usd'])
            for alias in NEW - {'Mistral-Large-3'}:
                assert Decimal(details[alias]['estimated_cost_usd']) > 0
                assert details[alias]['estimate_basis'] == 'measured_cache_detail'
            response = env.client.get('/api/usage/export', headers=env.customer)
            assert response.status_code == 200
            rows = list(csv.DictReader(io.StringIO(response.text)))
            actual = {r['model']: r for r in rows if r['model'] in NEW}
            assert set(actual) == NEW
            for alias in NEW:
                assert (actual[alias]['estimated_cost_usd'] or None) == details[alias]['estimated_cost_usd']
            assert {r.id: snapshot(r) for r in db.scalars(select(UsageRecord))} == before
        finally:
            event.remove(env.db_engine, 'before_cursor_execute', record)
        assert not any(s.lstrip().startswith(('insert ', 'update ', 'delete ')) for s in statements)


@pytest.mark.parametrize('mutation', ['no-inventory', 'unaccepted', 'version', 'sku', 'provider', 'region',
    'case', 'retry', 'missing-tokens', 'failed', 'negative-cache', 'excess-cache', 'old-alias', 'known-fields'])
def test_backend_missing_projection_fail_closed(env, accepted_eight, mutation):
    inventory = AcceptedInventory.load(env.settings)
    row = UsageRecord(id='negative', organization_id='org', subscription_id='sub',
        model='gpt-6.1-terra', provider='', region='', occurred_at=datetime(2026, 10, 30, 18, tzinfo=UTC),
        input_tokens=18, output_tokens=13, cached_input_tokens=0, cache_write_tokens=0,
        status_code=200, completeness='backend_attribution_missing', cost=Decimal('123'), currency='SGD')
    if mutation == 'no-inventory': inventory = None
    elif mutation in ('unaccepted', 'version', 'sku'):
        if mutation == 'unaccepted':
            next(r for r in inventory.foundry.routes if r.alias == row.model).gateway_validated = False
        else:
            d = next(d for d in inventory.foundry.deployments if d.name == row.model)
            setattr(d, 'model_version' if mutation == 'version' else 'sku', 'wrong')
    elif mutation == 'provider': row.provider = 'wrong'
    elif mutation == 'region': row.region = 'westus'
    elif mutation == 'case': row.model = 'GPT-6.1-terra'
    elif mutation == 'retry': row.completeness = 'retry_usage_unknown'
    elif mutation == 'missing-tokens': row.input_tokens = None
    elif mutation == 'failed': row.status_code = 500
    elif mutation == 'negative-cache': row.cached_input_tokens = -1
    elif mutation == 'excess-cache': row.cached_input_tokens = 19
    elif mutation == 'old-alias': row.model = 'gpt-4o'
    elif mutation == 'known-fields': row.provider, row.region = 'OpenAI', 'eastus'
    with Session(env.db_engine) as db:
        db.add(row); db.commit()
        before = snapshot(row)
        assert detail_estimates(db, [row.id], inventory=inventory)[row.id]['estimated_cost_usd'] is None
        assert snapshot(row) == before