"""Offline contracts for the approved three-check ingestion-MI probe."""
import base64
from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from scripts.deployment import finops_dataplane_probe as probe
from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_prepare as prep

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('dataplane_supervisor', ROOT / 'infra/finops-dataplane-probe/entrypoint.py')
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


def token(**changes):
    claims = {'tid': probe.TENANT, 'oid': probe.OBJECT, 'aud': 'https://storage.azure.com', 'exp': int(time.time()) + 3600}
    claims.update(changes)
    return 'header.' + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=') + '.signature'


@pytest.mark.parametrize('changes', [{'tid': 'wrong'}, {'oid': 'wrong'}, {'aud': 'https://management.azure.com'},
                                    {'exp': 1}, {'exp': 'secret'}, {'aud': None}])
def test_wrong_claims_are_finite(changes):
    with pytest.raises(probe.Blocked, match='^claims_mismatch$'):
        probe.claims(token(**changes), 'https://storage.azure.com')


def test_valid_claims():
    probe.claims(token(), 'https://storage.azure.com')


@pytest.mark.parametrize('code', sorted(probe.ERRORS))
def test_service_denials_do_not_leak_messages(code):
    class HttpResponseError(Exception):
        status_code = 403
        error_code = code
    def operation(progress):
        progress['stage'] = 'list_metadata'
        progress['claims_verified'] = True
        raise HttpResponseError('SECRET URI account and username')
    result = probe.outcome('table', operation)
    assert result['http_status'] == 403 and result['azure_error_code'] == code
    assert result['stage'] == 'list_metadata' and result['reason'] == 'service_rejected'
    assert 'SECRET' not in json.dumps(result)


def test_unknown_values_are_not_exported():
    class Error(Exception):
        status_code = 'SECRET'
        error_code = 'SECRET'
    def fail(progress): raise Error('SECRET')
    result = probe.outcome('monitor', fail)
    assert result['http_status'] is None and result['azure_error_code'] is None
    assert 'SECRET' not in json.dumps(result)


def good_report():
    def operation(progress):
        progress.update(claims_verified=True, http_status=200)
    return {'status': 'verified_data_plane', 'checks': {s: probe.outcome(s, operation) for s in probe.SERVICES},
            'database_writes': 0, 'storage_writes': 0, 'retries': 0,
            'storage_write_permission_proven': False, 'identity_source': 'explicit_ingestion_managed_identity'}


def test_output_double_sanitization():
    report = good_report()
    assert supervisor.sanitize(json.dumps(report), 0) == report
    assert supervisor.sanitize(json.dumps(supervisor.sanitize(json.dumps(report), 0)), 0) == report


@pytest.mark.parametrize('field,value', [('reason', 'SECRET'), ('stage', 'SECRET'), ('http_status', 999),
    ('azure_error_code', 'SECRET'), ('claims_verified', False), ('started_at_utc', 'SECRET')])
def test_nested_output_fail_closed(field, value):
    report = good_report()
    report['checks']['table'][field] = value
    assert supervisor.sanitize(json.dumps(report), 0) == supervisor.failure()


def test_no_missing_service_accepted():
    report = good_report()
    del report['checks']['table']
    assert supervisor.sanitize(json.dumps(report), 0) == supervisor.failure()


def test_profile_egress_exact_and_legacy_unchanged():
    nonce = '123456abcdef'
    old = prep.network_template(nonce)
    new = prep.network_template(nonce, profile='ingestion_dataplane')
    old_rules = old['resources'][1]['properties']['securityRules']
    new_rules = new['resources'][1]['properties']['securityRules']
    added = [r for r in new_rules if r not in old_rules]
    assert {r['properties']['destinationAddressPrefix'] for r in added} == {
        '10.240.3.6/32', '10.240.3.7/32', '10.240.3.8/32', 'AzureMonitor'}
    assert all(r['properties']['protocol'] == 'Tcp' and r['properties']['destinationPortRange'] == '443' and
               r['properties']['sourceAddressPrefix'] == g.CIDR for r in added)
    assert prep.guard_network(new, nonce, profile='ingestion_dataplane')
    with pytest.raises(g.GuardBlocked): prep.guard_network(new, nonce)
    new['resources'][1]['properties']['securityRules'][0]['properties']['sourceAddressPrefix'] = 'Internet'
    with pytest.raises(g.GuardBlocked): prep.guard_network(new, nonce, profile='ingestion_dataplane')


def test_postgres_select_and_rollback_only(monkeypatch):
    import psycopg
    statements = []
    class DB:
        rolled_back = False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return self
        def execute(self, query):
            assert query.startswith('SELECT ') and not any(word in query for word in ('INSERT', 'UPDATE', 'DELETE', 'CREATE'))
            statements.append(query)
        def fetchone(self): return (1, 'turnstile', probe.ROLE, probe.ROLE, 'public', 'on', 0)
        def rollback(self): self.rolled_back = True
    db = DB()
    def connect(**kw):
        assert kw['hostaddr'] == '10.240.3.12' and kw['sslmode'] == 'verify-full'
        assert 'default_transaction_read_only=on' in kw['options']
        return db
    monkeypatch.setattr(psycopg, 'connect', connect)
    monkeypatch.setattr(probe, 'private_dns', lambda *args: None)
    monkeypatch.setattr(probe, 'acquire', lambda *args: SimpleNamespace(token='synthetic'))
    probe.postgres(None, {})
    assert len(statements) == 1 and db.rolled_back


def test_source_has_no_app_or_seeding():
    source = (ROOT / 'scripts/deployment/finops_dataplane_probe.py').read_text()
    assert 'import aiflux' not in source and 'DefaultAzureCredential' not in source
    assert 'get_entity' not in source and 'receive_messages' not in source and 'create_table' not in source
    assert 'retry_total=0' in source


def test_dataplane_cleanup_uses_exact_reviewed_profile(tmp_path):
    from scripts.deployment import finops_runner_execute as ex
    from tests.unit.test_finops_runner_execution import session, objects, FakeArm
    s = session()
    s['network_profile'] = 'ingestion_dataplane'
    values = objects(s)
    rules = prep.network_template(s['owner_nonce'], profile='ingestion_dataplane')['resources'][1]
    values[s['ids']['nsg']] = {**rules, 'id': s['ids']['nsg']}
    # This task never creates/attaches the API identity.
    del values[s['ids']['api']]
    arm = FakeArm(values)
    result = ex.cleanup(s, tmp_path, arm)
    assert result['exit_code'] == 0 and len(result['deleted_resource_ids']) == 5
    assert s['ids']['api'] not in result['deleted_resource_ids']
    assert len(result['absence']) == 6 and all(item['http_status'] == 404 for item in result['absence'])