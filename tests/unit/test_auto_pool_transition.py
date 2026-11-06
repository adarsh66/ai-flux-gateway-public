"""Synthetic reviewed-transition regressions; no real rows, credentials or sockets."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux import auto_pool_transition as transition, auto_pricing
from aiflux.gateway_settings import fingerprint, render_revision
from aiflux.models import AuditEvent, GatewaySettings, GatewaySettingsRevision
from aiflux.poc_controls import render
from aiflux.schemas import PocGatewayConfiguration
from test_gateway_settings import FragmentApim

URL = '/api/admin/gateway-settings/dev-unified'
SAFETY = '/api/admin/content-safety-settings/dev-unified'

def rehash(value):
    value['sha256'] = hashlib.sha256(auto_pricing.compact(
        {k: v for k, v in value.items() if k != 'sha256'}).encode()).hexdigest()
    return value

@pytest.fixture
def case(env, monkeypatch):
    env.settings.gateway_controls_poc_enabled = True
    env.settings.gateway_controls_v2_enabled = False
    env.settings.gateway_settings_scopes = ['dev-unified']
    env.settings.auto_pricing_sync_enabled = True
    env.settings.auto_routing_enabled = True
    receipt = transition.REVIEWED_TRANSITIONS[0]
    aliases = list('abcdef')
    old = rehash({'schema': 1, 'pool_version': receipt['from_pool'], 'rate_card_version': 2,
        'revision': 'rate-card-v2', 'source': 'rate-card', 'prices': {alias: {
            'input': '0', 'output': '2', 'status': 'configured', 'revision': 'rate-card-v2',
            'source_url': '', 'source_model': alias, 'currency': 'USD', 'unit': 'per_million_tokens'}
            for alias in aliases}})
    new = rehash({**deepcopy(old), 'pool_version': receipt['to_pool']})
    config = PocGatewayConfiguration().model_dump(mode='json')
    stored = {'configuration': config, 'bindings': [], 'unrelated': {'retain': True},
        'auto_pricing': {'applied': old, 'desired': new, 'state': 'pending', 'attempts': 10,
            'attempted_hash': None, 'attempt_predecessor_hash': None}}
    baseline = auto_pricing.envelope(render(PocGatewayConfiguration(), []), old)
    current = auto_pricing.envelope(auto_pricing.controls_only(baseline), new)
    snapshot = {'version': receipt['to_pool'], 'candidates': [{'id': a} for a in aliases]}
    monkeypatch.setattr(transition.auto_snapshot, 'defaults', lambda _: snapshot)
    monkeypatch.setattr(transition.auto_snapshot, 'publication', lambda *_: {'policy_sha256': receipt['policy_sha256']})
    monkeypatch.setattr(transition.AcceptedInventory, 'load', lambda _: SimpleNamespace(accepted_aliases=lambda _: set(aliases)))
    monkeypatch.setattr(transition.completion_limits, 'load', lambda *_: (object(), receipt['completion_contract_sha256']))
    with Session(env.db_engine) as db:
        db.add(GatewaySettings(scope='dev-unified', version=13, published_version=13))
        db.add(GatewaySettingsRevision(scope='dev-unified', version=13, state='published',
            reason='synthetic predecessor', object_id='synthetic', configuration=json.dumps(stored),
            base_hash=fingerprint(baseline), base_etag='"old"'))
        db.commit()
    apim = FragmentApim()
    apim.values['dev-unified'] = current
    env.app.state.apim = apim
    return SimpleNamespace(env=env, receipt=receipt, old=old, new=new, stored=stored,
        baseline=baseline, current=current, snapshot=snapshot, config=config, apim=apim)

def save(case, config, version=13):
    return case.env.client.put(URL, headers=case.env.admin, json={
        'expected_version': version, 'configuration': config, 'reason': 'Reviewed synthetic pool adoption'})

def test_normal_gateway_save_adopts_exact_release_and_appends_without_history_rewrite(case):
    with Session(case.env.db_engine) as db:
        original = db.scalar(select(GatewaySettingsRevision)).configuration
    config = deepcopy(case.config)
    config['defaults']['rpm'] = 59
    response = save(case, config)
    assert response.status_code == 200, response.text
    assert response.json()['version'] == response.json()['published_version'] == 14
    assert len(case.apim.writes) == 1 and case.apim.writes[0][2] == '"1"'
    with Session(case.env.db_engine) as db:
        rows = list(db.scalars(select(GatewaySettingsRevision).order_by(GatewaySettingsRevision.version)))
        assert len(rows) == 2 and rows[0].configuration == original
        stored = json.loads(rows[1].configuration)
        assert stored['auto_pricing']['applied'] == case.new
        assert stored['auto_pricing']['applied']['prices'] == case.old['prices']
        assert stored['unrelated'] == {'retain': True}
        assert stored['auto_pricing_pool_transition']['predecessor_version'] == 13
        assert fingerprint(render_revision('dev-unified', rows[1])) == fingerprint(case.apim.values['dev-unified'])
        actions = [item.action for item in db.scalars(select(AuditEvent))]
        assert 'gateway.settings.pool-binding-adopted' in actions
    assert save(case, case.config, 14).status_code == 200
    assert len(case.apim.writes) == 2

def test_normal_safety_save_uses_same_adoption_and_preserves_gateway(case):
    body = {'expected_version': 13, 'configuration': {**case.config['safety'], 'hate': 0},
        'reason': 'Synthetic stricter safety', 'acknowledge_relaxation': False}
    response = case.env.client.put(SAFETY, headers=case.env.admin, json=body)
    assert response.status_code == 200, response.text
    assert response.json()['desired']['configuration']['defaults'] == case.config['defaults']
    body.update(expected_version=14, configuration=case.config['safety'], acknowledge_relaxation=True)
    assert case.env.client.put(SAFETY, headers=case.env.admin, json=body).status_code == 200

@pytest.mark.parametrize('fault', ['price', 'control', 'pool', 'hash', 'extra', 'policy', 'contract', 'unpublished', 'aliases'])
def test_external_drift_or_unbound_release_still_rejected_without_revision_or_put(case, monkeypatch, fault):
    changed = deepcopy(case.new)
    if fault == 'price':
        changed['prices']['a']['input'] = '9'
        rehash(changed)
    elif fault == 'pool':
        changed['pool_version'] = 'e' * 64
        rehash(changed)
    elif fault == 'hash':
        changed['sha256'] = '0' * 64
        case.apim.values['dev-unified'] = case.current.replace(case.new['sha256'], changed['sha256'])
    elif fault == 'extra':
        case.apim.values['dev-unified'] = case.current.replace('</fragment>', '<set-variable name="foreign" value="1" /></fragment>')
    elif fault == 'control':
        case.apim.values['dev-unified'] = case.current.replace('@(60)', '@(58)')
    elif fault == 'policy':
        monkeypatch.setattr(transition.auto_snapshot, 'publication', lambda *_: {'policy_sha256': '0' * 64})
    elif fault == 'unpublished':
        monkeypatch.setattr(transition.auto_snapshot, 'publication', lambda *_: None)
    elif fault == 'contract':
        monkeypatch.setattr(transition.completion_limits, 'load', lambda *_: (object(), '0' * 64))
    else:
        case.snapshot['candidates'][0]['id'] = 'foreign'
    if fault in ('price', 'pool'):
        case.apim.values['dev-unified'] = auto_pricing.envelope(auto_pricing.controls_only(case.baseline), changed)
    response = save(case, case.config)
    assert response.status_code == 409, response.text
    assert case.apim.writes == []
    with Session(case.env.db_engine) as db:
        assert db.get(GatewaySettings, 'dev-unified').version == 13
        assert len(list(db.scalars(select(GatewaySettingsRevision)))) == 1

def test_stale_cas_denied_before_adoption_or_put(case):
    assert save(case, case.config, 12).status_code == 409
    assert case.apim.writes == []


def test_nested_predecessor_price_envelope_is_not_the_reviewed_successor(case):
    case.apim.values['dev-unified'] = auto_pricing.envelope(case.baseline, case.new)
    assert save(case, case.config).status_code == 409
    assert case.apim.writes == []
    with Session(case.env.db_engine) as db:
        assert db.get(GatewaySettings, 'dev-unified').version == 13
        assert len(list(db.scalars(select(GatewaySettingsRevision)))) == 1

def test_unknown_put_retains_failed_new_head_and_does_not_repeat(case):
    case.apim.uncertain = True
    config = deepcopy(case.config)
    config['defaults']['rpm'] = 59
    response = save(case, config)
    assert response.status_code == 502
    assert len(case.apim.writes) == 1
    assert save(case, config, 14).status_code == 409
    assert len(case.apim.writes) == 1