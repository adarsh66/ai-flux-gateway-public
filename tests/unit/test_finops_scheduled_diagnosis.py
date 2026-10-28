from copy import deepcopy

import pytest

from scripts.deployment.finops_scheduled_diagnosis import (
    always_on_target, scheduled_evidence, verify_reconciled_baseline,
)
from scripts.deployment.finops_function_stage import sha
from scripts.deployment import finops_scheduled_diagnosis as diagnosis


def test_always_on_only_preserves_every_other_field():
    before = {'alwaysOn': False, 'linuxFxVersion': 'DOCKER|immutable',
              'nested': {'protected': True}, 'healthCheckPath': '/admin/host/status'}
    after = always_on_target(before)
    assert before['alwaysOn'] is False
    assert after == {**before, 'alwaysOn': True}
    assert [k for k in before if before[k] != after[k]] == ['alwaysOn']


@pytest.mark.parametrize('value', [True, None, 'false', 0])
def test_no_reapply_or_unknown_baseline(value):
    with pytest.raises(RuntimeError, match='always_on_already_enabled_no_reapply'):
        always_on_target({'alwaysOn': value})


@pytest.mark.parametrize('field', ['image', 'ingress', 'identity', 'enabled', 'sku', 'alwaysOn'])
def test_readback_rejects_any_other_protected_change(field):
    expected = {'sites': {'ingestion': {'image': 'digest', 'ingress': 'Deny',
        'identity': 'existing', 'enabled': True, 'alwaysOn': True, 'sku': 'B1'}}}
    actual = deepcopy(expected)
    actual['sites']['ingestion'][field] = 'unexpected'
    with pytest.raises(RuntimeError, match='protected_baseline_drift'):
        verify_reconciled_baseline(actual, expected, {}, {})


@pytest.mark.parametrize('component', ['ingestion', 'api', 'admin', 'customer'])
@pytest.mark.parametrize('field', ['timer', 'cutoff', 'image', 'any_setting'])
def test_readback_rejects_any_setting_change(component, field):
    original = {name: {'timer': 'false', 'cutoff': 'fixed', 'image': 'digest', 'any_setting': 'fixed'}
                for name in ('ingestion', 'api', 'admin', 'customer')}
    actual = deepcopy(original)
    actual[component][field] = 'unexpected'
    with pytest.raises(RuntimeError, match='complete_settings_drift'):
        verify_reconciled_baseline({}, {}, actual, {k: sha(v) for k, v in original.items()})


def test_exact_protected_readback_accepted():
    verify_reconciled_baseline({'alwaysOn': True}, {'alwaysOn': True},
                               {'ingestion': {'timer': 'false'}},
                               {'ingestion': sha({'timer': 'false'})})


def test_existing_intent_prevents_any_reapply_or_cloud_call(tmp_path, monkeypatch):
    home = tmp_path / 'gateway' / 'validation'
    home.mkdir(parents=True)
    (home / 'finops-always-on-intent-20261027.json').write_text('{}')
    monkeypatch.setattr(diagnosis.rt, 'ROOT', tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('cloud call after existing intent')
    monkeypatch.setattr(diagnosis.fs, 'current_settings', forbidden)
    monkeypatch.setattr(diagnosis.rt, 'arm', forbidden)
    monkeypatch.setattr(diagnosis, 'urlopen', forbidden)
    with pytest.raises(RuntimeError, match='existing_always_on_intent_reconcile_no_retry'):
        diagnosis.repair_always_on()


def test_schedule_proof_excludes_stale_manual_unmatched_and_duplicate_events():
    def start(identifier, **kwargs):
        return {'at_utc': '2026-10-27T08:40:00Z', 'invocation_id': identifier,
                'scheduled': True, 'manual': False, **kwargs}
    def end(identifier, **kwargs):
        return {'at_utc': '2026-10-27T08:40:01Z', 'invocation_id': identifier,
                'function': 'ingest_usage', 'result': 'Succeeded', **kwargs}
    events = {'scheduled_starts': [start('real'), start('real'), start('manual', manual=True),
        start('stale', at_utc='2026-10-27T07:30:00Z'), start('naive', at_utc='2026-10-27T08:40:00'),
        start('second', at_utc='2026-10-27T08:45:00Z')],
        'executions': [end('real'), end('real'), end('manual'), end('stale'), end('naive'),
                       end('unmatched'), end('second', at_utc='2026-10-27T08:45:01Z')]}
    proof = scheduled_evidence(events, '2026-10-27T08:36:45Z')
    assert proof['successes'] == 2
    assert proof['failures'] == 0
    assert {e['invocation_id'] for e in proof['executions']} == {'real', 'second'}