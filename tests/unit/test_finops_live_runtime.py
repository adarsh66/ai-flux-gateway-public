import copy

import pytest

from scripts.deployment.finops_live_runtime import logging_target, summarize, classify_failures


def test_finite_failure_classifier_distinguishes_storage_from_monitor_without_messages():
    text = ('Status: 403\nErrorCode: AuthorizationPermissionMismatch\n'
            'https://private.queue.core.windows.net/secret?sig=never\n'
            'azure.storage.queue HttpResponseError\n'
            'psycopg.errors.InsufficientPrivilege: password=never\nSQLSTATE: 42501')
    result = classify_failures(text)
    assert result['azure_error_codes'] == ['AuthorizationPermissionMismatch']
    assert result['services_seen'] == ['postgresql', 'storage_queue']
    assert result['http_statuses'] == [403]
    assert result['sqlstates'] == ['42501']
    assert 'never' not in str(result) and 'private' not in str(result)


def test_finite_classifier_rejects_arbitrary_status_codes_and_exception_text():
    result = classify_failures('ErrorCode: SecretValue\nStatus: 987\nSQLSTATE: abcde\n'
                               'azure.monitor.query HttpResponseError InsufficientAccessError')
    assert result['azure_error_codes'] == ['InsufficientAccessError']
    assert result['services_seen'] == ['monitor_logs']
    assert result['http_statuses'] == []
    assert result['sqlstates'] == []


def test_storage_denial_is_not_reported_as_monitor_denial():
    result = summarize('2026-10-27T07:11:55Z AuthorizationPermissionMismatch\n'
                       '2026-10-27T07:12:25Z InsufficientAccessError')
    assert result['failures'] == [
        {'at_utc': '2026-10-27T07:11:55Z', 'category': 'storage_access_error'},
        {'at_utc': '2026-10-27T07:12:25Z', 'category': 'monitor_access_error'},
    ]


def test_http_readiness_rejects_non_http_admin_invocation_before_cloud_call(monkeypatch):
    from scripts.deployment import finops_live_runtime as live
    monkeypatch.setattr(live, 'request', lambda *args: pytest.fail('must not invoke incompatible trigger'))
    with pytest.raises(RuntimeError, match='http_readiness_requires_http_trigger_channel'):
        live.invoke_ready()


def test_private_result_drops_untrusted_messages_and_non_boolean_claims():
    from scripts.deployment.finops_live_runtime import safe_private_result
    assert safe_private_result({'monitor_exact_query_passed': 'true', 'failed': True,
        'exception_class': 'HttpResponseError', 'http_status': 403, 'message': 'never-export',
        'token': 'never-export'}) == {'failed': True, 'exception_class': 'HttpResponseError', 'http_status': 403}
    assert safe_private_result({'exception_class': 'never-export', 'http_status': True}) == {}


def test_temporary_capture_changes_exactly_one_non_application_setting():
    value = {'httpLogs': {'fileSystem': {'enabled': False, 'retentionInMb': 35},
                         'azureBlobStorage': {'enabled': False, 'sasUrl': None}},
             'applicationLogs': {'fileSystem': {'level': 'Off'}}, 'preserved': {'exact': True}}
    before = copy.deepcopy(value)
    target = logging_target(value)
    target['httpLogs']['fileSystem']['enabled'] = False
    assert target == before == value


def test_logging_rejects_secret_or_already_enabled_baseline():
    with pytest.raises(RuntimeError):
        logging_target({'httpLogs': {'fileSystem': {'enabled': True}}})
    with pytest.raises(RuntimeError):
        logging_target({'httpLogs': {'fileSystem': {'enabled': False}, 'azureBlobStorage': {'sasUrl': 'not-exportable'}}})


def test_metadata_only_parser_does_not_export_untrusted_lines():
    result = summarize('2026-10-27T07:00:00Z secret SQL prompt password\n'
                       'OperationalError: do-not-export-this-host-or-row\n'
                       'FinOps runtime readiness {"sql_tables_readable": true, "enabled_models": 11, '
                       '"owned_subscriptions": 1, "price_rules": 8, "watermark": null, "secret":"never"}')
    assert result['ready_results'][0]['sql_tables_readable'] is True
    assert result['failures'] == [{'at_utc': None, 'category': 'database_error'}]
    assert 'secret' not in str(result) and 'do-not-export' not in str(result)


def test_scheduled_start_is_not_manual_or_merely_an_execution_success():
    invocation = '11111111-2222-3333-4444-555555555555'
    result = summarize(f"2026-10-27T07:05:00Z Executing 'Functions.ingest_usage' (Reason='Timer fired at 2026-10-27T07:05:00Z', Id={invocation})\n"
                       f"2026-10-27T07:05:02Z Executed 'Functions.ingest_usage' (Succeeded, Id={invocation}, Duration=2000ms)")
    assert result['scheduled_starts'][0]['scheduled'] is True
    assert result['scheduled_starts'][0]['manual'] is False
    assert result['executions'][0]['invocation_id'] == invocation
    assert result['executions'][0]['result'] == 'Succeeded'