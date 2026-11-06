"""Historical drafts are detached GETs, never price writes or resolver changes."""
from datetime import UTC, datetime, timedelta
import json

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from test_external_pricing_api import pricing_env, clock, initialize, put, row, org_path, ALIAS  # noqa: F401
from test_catalog_pricing_correction import accepted  # noqa: F401
from aiflux import external_pricing as external, pricing_history as history, rate_card
from aiflux.models import ExternalPriceCardRevision, GatewaySettingsRevision

DEFAULT = '/api/admin/external-rate-card/history'
INTERNAL = '/api/admin/rate-card/history'


def get(env, path=DEFAULT, **params):
    response = env.client.get(path, headers=env.admin, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def detail(env, path, point):
    return get(env, path + '/detail', revision=point['id'])


def test_admin_only_readonly_no_seed_no_crossorg_and_pagination(accepted):
    env, _ = accepted
    paths = (DEFAULT, INTERNAL, org_path(env.orgs['customer']) + '/history')
    statements = []
    def observe(conn, cursor, statement, params, context, many):
        statements.append(statement)
    event.listen(env.db_engine, 'before_cursor_execute', observe)
    try:
        for path in paths:
            assert env.client.get(path, headers=env.customer).status_code == 403
            assert env.client.get(path + '/detail', headers=env.customer, params={'revision': 'i1'}).status_code == 403
            assert get(env, path)['items'] == []
            assert env.client.get(path + '/detail', headers=env.admin, params={'revision': 'i0'}).status_code == 404
    finally:
        event.remove(env.db_engine, 'before_cursor_execute', observe)
    assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for s in statements)
    initialize(env)
    assert put(env, input='8', output='12').status_code == 200
    assert put(env, version=2, input='9', output='13').status_code == 200
    first = get(env, limit=1)
    assert first['next_offset'] == 1 and first['total'] >= 3
    ids = first['items'] + get(env, limit=100, offset=first['next_offset'])['items']
    assert len({p['id'] for p in ids}) == first['total']
    assert get(env, INTERNAL)['items'] == []  # No synthetic internal v0.
    assert env.client.get(DEFAULT, headers=env.admin, params={'limit': 101}).status_code == 422


def test_external_default_driven_orgv0_effective_copy_forward_unknown_and_cas(pricing_env, clock):
    env = pricing_env
    assert put(env, input='8', output='12', cached='0').status_code == 200
    original_at = clock.at
    clock.at += timedelta(minutes=5)
    assert put(env, version=2, input='99', output='199').status_code == 200
    path = org_path(env.orgs['customer']) + '/history'
    point = next(p for p in get(env, path)['items'] if p['default_version'] == 2)
    old = detail(env, path, point)
    assert point['organization_version'] == 0
    assert old['current_version'] == 0
    assert row(old)['input'] == '8' and row(old)['cached'] == '0'
    assert 'provenance' not in json.dumps(old) and 'source_url' not in json.dumps(old)
    before = external.snapshot
    # Existing explicit Save appends now, preserves pre-save estimates and CAS.
    clock.at += timedelta(minutes=5)
    saved = put(env, org=env.orgs['customer'], input=row(old)['input'], output=row(old)['output'], cached='0')
    assert saved.status_code == 200 and saved.json()['version'] == 1
    assert put(env, org=env.orgs['customer'], input='7', output='8').status_code == 409
    with Session(env.db_engine) as db:
        context = before(db, env.orgs['customer'])
        key = (row(old)['canonical_model'], row(old)['provider'], row(old)['region'])
        assert context._resolve(key, original_at + timedelta(seconds=1))['input'] == '8'
        assert context._resolve(key, clock.at - timedelta(seconds=1))['input'] == '99'
        assert context._resolve(key, clock.at)['input'] == '8'
        assert context._resolve(key, clock.at)['owner'] == 'org:' + env.orgs['customer']
    assert put(env, org=env.orgs['customer'], version=1, operation='unknown').status_code == 200
    unknown_point = next(p for p in get(env, path)['items'] if p['organization_version'] == 2)
    unknown = row(detail(env, path, unknown_point))
    assert unknown['state'] == 'unknown' and unknown['input'] is None
    assert unknown['input'] != '0'
    # Other owner's point is not accepted by a default detail endpoint.
    assert env.client.get(DEFAULT + '/detail', headers=env.admin,
        params={'revision': unknown_point['id']}).status_code == 404


def test_sameclock_later_owner_versions_and_backdated_baseline_are_bounded(pricing_env, clock):
    env = pricing_env
    assert put(env, input='5', output='6').status_code == 200
    assert put(env, version=2, input='50', output='60').status_code == 200
    assert put(env, org=env.orgs['customer'], input='7', output='8').status_code == 200
    path = org_path(env.orgs['customer']) + '/history'
    points = get(env, path)['items']
    p2 = next(p for p in points if p['default_version'] == 2 and p['source'] == 'default')
    assert p2['organization_version'] == 0 and p2['simultaneous']
    assert row(detail(env, path, p2))['input'] == '5'  # Not same-clock default v3/org v1.
    cohort = next(p for p in points if p['source'] == 'simultaneous cohort')
    assert cohort['default_version'] == 3 and cohort['organization_version'] == 1
    assert row(detail(env, path, cohort))['input'] == '7'
    baseline = next(p for p in points if p['default_version'] == 1 and p['source'] == 'default')
    baseline_row = row(detail(env, path, baseline))
    assert baseline_row['input'] not in ('5', '50', '7')


def test_internal_configured_and_reset_vectors_require_proven_identity_not_current_defaults(accepted, monkeypatch):
    env, _ = accepted
    for version, value in ((0, '7'), (1, '8')):
        response = env.client.put('/api/admin/rate-card', headers=env.admin, json={
            'expected_version': version, 'rates': [{'model': ALIAS, 'input': value, 'output': '10'}]})
        assert response.status_code == 200, response.text
    # Explicit fixture baseline freezes immutable metadata and config hashes.
    initialize(env)
    points = get(env, INTERNAL)['items']
    assert [p['internal_version'] for p in points] == [2, 1]
    old = detail(env, INTERNAL, points[1])
    assert row(old)['state'] == 'known' and row(old)['input'] == '7'
    assert old['current_version'] == 2 and old['requires_acknowledgement']
    # Unconfigured historical defaults are conservatively unavailable, not guessed.
    assert any(r['state'] == 'unavailable' for r in old['items'])
    scopes = rate_card.listed_scopes(env.settings)
    target = next(scope for alias, scope in scopes if alias == ALIAS)
    monkeypatch.setattr(rate_card, 'listed_scopes', lambda settings: [(ALIAS, {**target, 'sku': 'changed-sku'})])
    mismatch = detail(env, INTERNAL, points[1])
    assert row(mismatch)['state'] == 'unavailable' and row(mismatch)['input'] is None


def test_internal_no_frozen_provenance_unavailable_and_malformed_fails_closed(accepted):
    env, _ = accepted
    assert env.client.put('/api/admin/rate-card', headers=env.admin, json={
        'expected_version': 0, 'rates': [{'model': ALIAS, 'input': '7', 'output': '8'}]}).status_code == 200
    point = get(env, INTERNAL)['items'][0]
    body = detail(env, INTERNAL, point)
    assert all(r['state'] == 'unavailable' for r in body['items'])
    with Session(env.db_engine) as db:
        revision = db.scalar(select(GatewaySettingsRevision))
        revision.configuration = '{"schema":1,"entries":[{"model":"x","valid_from":"not-a-date"}]}'
        db.commit()
    assert env.client.get(INTERNAL, headers=env.admin).status_code == 409
    assert env.client.get('/api/admin/rate-card', headers=env.admin).status_code == 200  # Existing current fallback unchanged.


@pytest.mark.parametrize('bad', ['NaN', '-1', '100001', '0.000000001'])
def test_external_strict_parse_rejects_bad_vectors_without_internal_fallback(pricing_env, bad):
    env = pricing_env
    with Session(env.db_engine) as db:
        revision = db.scalar(select(ExternalPriceCardRevision))
        data = json.loads(revision.delta)
        data['entries'][0]['operation'] = 'set'
        data['entries'][0]['input'] = bad
        data['entries'][0]['output'] = '1'
        revision.delta = json.dumps(data)
        db.commit()
    response = env.client.get(DEFAULT, headers=env.admin)
    assert response.status_code == 409 and 'substituted' in response.text


def test_strict_duplicate_keys_and_naive_time_rejected():
    with pytest.raises(ValueError):
        history._data('{"schema":1,"schema":1,"entries":[]}', 'entries')
    with pytest.raises(ValueError):
        history._time('2026-01-01T00:00:00')
    assert history._vector({'input': '0', 'output': None}, scoring=True)['input'] == '0'
    with pytest.raises(ValueError):
        history._vector({'input': '1', 'output': '0'}, scoring=True)