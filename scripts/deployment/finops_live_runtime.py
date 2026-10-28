"""Finite ingestion-only console observation; never exports raw logs or keys."""
from __future__ import annotations

import argparse
import base64
import copy
from datetime import UTC, datetime
import io
import json
import re
import ssl
from urllib.request import Request, urlopen
import zipfile

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs

RID = rt.RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-ingestion'
HOME = rt.HOME / 'finops/finops-20261027t062458z/runtime-evidence'


def request(suffix, method='GET', value=None):
    rt.require(suffix in {'/config/logs', '/containerlogs/zip/download',
                         '/hostruntime/admin/functions/ingestion_ready'}, 'finite_runtime_path')
    rt.require(method == 'GET' or (method == 'PUT' and suffix == '/config/logs') or
               (method == 'POST' and suffix != '/config/logs'), 'finite_runtime_method')
    token = rt.cli(['account', 'get-access-token', '--subscription', rt.SUB,
                    '--resource', 'https://management.azure.com/'])['accessToken']
    body = json.dumps(value).encode() if value is not None else (b'' if method == 'POST' else None)
    req = Request('https://management.azure.com' + RID + suffix + '?api-version=2024-04-01',
                  data=body, method=method,
                  headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urlopen(req, context=ssl.create_default_context(cafile=rt.CA), timeout=100) as response:
        raw = response.read(12_000_001)
        rt.require(len(raw) <= 12_000_000, 'bounded_runtime_response')
        return response.status, raw


def logging_target(original):
    target = copy.deepcopy(original)
    rt.require(all(not original.get(group, {}).get(kind, {}).get('sasUrl')
                   for group, kind in [('applicationLogs', 'azureTableStorage'),
                                       ('applicationLogs', 'azureBlobStorage'),
                                       ('httpLogs', 'azureBlobStorage')]), 'no_logging_secrets')
    rt.require(original['httpLogs']['fileSystem']['enabled'] is False, 'unexpected_logging_baseline')
    target['httpLogs']['fileSystem']['enabled'] = True
    return target


def enable_logging():
    fs.protect(HOME)
    rt.require(not (HOME / 'logging-intent.json').exists(), 'logging_intent_exists_reconcile')
    original = json.loads(request('/config/logs')[1])['properties']
    target = logging_target(original)
    rt.save(HOME / 'logging-intent.json', {'at_utc': fs.stamp(), 'original': original,
            'target': target, 'scope': 'temporary_ingestion_stdout_only_no_appsettings_change'})
    request('/config/logs', 'PUT', {'properties': target})
    rt.require(json.loads(request('/config/logs')[1])['properties'] == target, 'logging_readback_mismatch')
    print(json.dumps({'at_utc': fs.stamp(), 'temporary_ingestion_console_capture': True,
                      'changed_field': 'httpLogs.fileSystem.enabled', 'application_settings_writes': 0}), flush=True)


def restore_logging():
    intent = json.loads((HOME / 'logging-intent.json').read_text())
    current = json.loads(request('/config/logs')[1])['properties']
    rt.require(current in (intent['target'], intent['original']), 'logging_drift_no_overwrite')
    if current != intent['original']:
        request('/config/logs', 'PUT', {'properties': intent['original']})
    rt.require(json.loads(request('/config/logs')[1])['properties'] == intent['original'], 'logging_restore_readback')
    result = {'at_utc': fs.stamp(), 'exact_logging_baseline_restored': True}
    rt.save(HOME / 'logging-restored.json', result)
    print(json.dumps(result), flush=True)


def restart_for_capture():
    rt.require((HOME / 'logging-intent.json').is_file(), 'logging_intent_required')
    rt.require(not (HOME / 'capture-restart-intent.json').exists(), 'restart_already_requested_no_retry')
    settings = fs.current_settings()['ingestion']
    rt.require(settings['AzureWebJobs.ingest_usage.Disabled'] == 'true'
               and settings['AIFLUX_INGESTION_START_AT'] == '2026-10-27T06:06:02.045288+00:00',
               'disabled_timer_exact_boundary_required')
    rt.save(HOME / 'capture-restart-intent.json', {'at_utc': fs.stamp(), 'timer_disabled': True})
    rt.run(rt.CLI + ['functionapp', 'restart', '--subscription', rt.SUB,
                    '--resource-group', 'IDS-TOKEN-EXCHANGE-POC',
                    '--name', 'poc-ids-token-ex-ingestion', '--only-show-errors'])
    result = {'at_utc': fs.stamp(), 'existing_function_restarted_for_stdout_capture': True,
              'image_or_settings_writes': 0, 'manual_timer_invocations': 0}
    rt.save(HOME / 'capture-restarted.json', result)
    print(json.dumps(result), flush=True)


def invoke_ready():
    # The admin/functions input API is for non-HTTP triggers. A 202 accepted the
    # operation but the live host failed binding the string to the HTTP request;
    # verify_runtime never ran. Do not retry or mistake acceptance for readiness.
    raise RuntimeError('http_readiness_requires_http_trigger_channel')


def summarize(text):
    results = {'ready_results': [], 'executions': [], 'scheduled_starts': [], 'failures': []}
    for line in text.splitlines():
        stamp = re.search(r'20\d\d-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?Z?', line)
        at = stamp.group() if stamp else None
        if 'FinOps runtime readiness ' in line:
            try:
                value = json.JSONDecoder().raw_decode(line.split('FinOps runtime readiness ', 1)[1])[0]
                safe = {k: value.get(k) for k in ('sql_tables_readable', 'enabled_models', 'owned_subscriptions', 'price_rules', 'watermark')}
                rt.require(safe['sql_tables_readable'] is True and type(safe['enabled_models']) is int
                           and all(type(safe[k]) is int for k in ('owned_subscriptions', 'price_rules')),
                           'invalid_readiness_shape')
                rt.require(safe['watermark'] is None or re.fullmatch(r'[0-9T:Z.+-]+', safe['watermark']), 'invalid_watermark')
                results['ready_results'].append({'at_utc': at, **safe})
            except (ValueError, TypeError, RuntimeError):
                results['failures'].append({'at_utc': at, 'category': 'invalid_readiness_shape'})
        match = re.search(r"Executed 'Functions\.(ingestion_ready|ingest_usage)' \((Succeeded|Failed), Id=([a-fA-F0-9-]{36})", line)
        if match:
            results['executions'].append({'at_utc': at, 'function': match[1], 'result': match[2], 'invocation_id': match[3]})
        match = re.search(r"Executing 'Functions\.ingest_usage'.*Reason='([^']*)'.*Id=([a-fA-F0-9-]{36})", line)
        if match:
            results['scheduled_starts'].append({'at_utc': at, 'invocation_id': match[2],
                'scheduled': 'Timer fired' in match[1], 'manual': 'programmatically' in match[1].lower()})
        for label, pattern in {'database_error': r'OperationalError|psycopg\..*Error|sqlalchemy.exc',
                               'binding_error': r'cannot convert|cannot decode|unable to decode',
                               'monitor_access_error': r'InsufficientAccessError|UnauthorizedClient|InvalidAuthenticationTokenAudience',
                               'storage_access_error': r'AuthorizationPermissionMismatch',
                               'authorization_error': r'AuthorizationFailed',
                               'settings_error': r'ValidationError|validation error for Settings',
                               'import_error': r'ModuleNotFoundError|ImportError'}.items():
            if re.search(pattern, line, re.I):
                results['failures'].append({'at_utc': at, 'category': label})
    return results


def classify_failures(text):
    """Fixed vocabulary only; never export messages, headers, URLs or DSNs."""
    codes = ('InsufficientAccessError', 'UnauthorizedClient', 'AuthorizationFailed',
             'AuthorizationPermissionMismatch', 'AuthenticationFailed',
             'InvalidAuthenticationToken', 'InvalidAuthenticationTokenAudience',
             'BadArgumentError', 'SemanticError', 'SyntaxError', 'ForbiddenByFirewall',
             'PublicNetworkAccessDisabled', 'ResourceNotFound', 'AuthorizationFailure')
    services = {'monitor_logs': r'azure\.monitor\.query|api\.loganalytics\.',
                'storage_blob': r'azure\.storage\.blobs?|\.blob\.core\.windows\.net|\bBlobServiceClient\b|\bBlobContainerClient\b',
                'storage_queue': r'azure\.storage\.queue|\.queue\.core\.windows\.net|\bQueueServiceClient\b',
                'storage_table': r'azure\.data\.tables|\.table\.core\.windows\.net|\bTableServiceClient\b',
                'postgresql': r'psycopg|sqlalchemy\.exc'}
    return {'azure_error_codes': sorted(code for code in codes if re.search(r'\b' + code + r'\b', text)),
            'http_statuses': sorted({int(x) for x in re.findall(
                r'(?i)(?:status(?:\s*code)?|HTTP(?:/1\.[01])?)\s*[:= ]\s*(400|401|403|404|408|429|500|502|503|504)\b', text)}),
            'sqlstates': sorted(set(re.findall(r'(?:SQLSTATE|sqlstate)\s*[:= ]\s*(42501|28000|28P01|3F000|42P01|08001|08006)', text))),
            'services_seen': sorted(k for k, pattern in services.items() if re.search(pattern, text, re.I)),
            'exception_classes': sorted(k for k in ('HttpResponseError', 'ClientAuthenticationError',
                'CredentialUnavailableError', 'OperationalError', 'ProgrammingError', 'InsufficientPrivilege',
                'ServiceRequestError', 'ServiceResponseError', 'RequestFailedException',
                'FunctionInvocationException', 'TimeoutException', 'TypeError', 'ValueError',
                'AttributeError', 'KeyError', 'JSONDecodeError') if re.search(r'\b' + k + r'\b', text)),
            'host_context': sorted(k for k, pattern in {
                'host_lock': r'host lock|HostLock|SingletonManager',
                'secret_repository': r'SecretRepository|secret storage|secrets from Blob|secrets initialization',
                'table_logging': r'TableStorage|TableLogWriter|FunctionInstanceLog',
                'worker_failure': r'Worker failed|worker process exited|RpcException',
                'binding_failure': r'cannot convert|cannot decode|unable to decode|binding.*exception|binding parameters|binding parameter',
                'http_request_binding': r'HttpRequest|httpTrigger|http request',
                'request_parameter_missing': r'No value was provided for parameter|missing.*request|request.*missing',
                'string_to_http_request_binding': r'(?:string|String).*(?:HttpRequest|HTTP request)|(?:HttpRequest|HTTP request).*(?:string|String)',
                'table_logging_write_failure': r'error.*(?:writing|write).*table|table.*(?:write|writing).*error',
                'table_logging_flush': r'flush.*log|log.*flush|log writer|TableLogWriter',
                'identity_environment': r'EnvironmentCredential|ManagedIdentityCredential',
                'storage_forbidden': r'AuthorizationPermissionMismatch',
            }.items() if re.search(pattern, text, re.I)),
            'stages_seen': sorted(k for k in ('runtime_check.py', 'handlers.py', 'ingestion.py',
                'query_workspace', 'verify_runtime', 'engine_for', 'get_token') if k in text)}


def safe_private_result(output):
    result = {k: output[k] for k in ('monitor_exact_query_passed', 'postgres_readiness_passed', 'failed')
              if type(output.get(k)) is bool}
    if output.get('exception_class') in ('HttpResponseError', 'ClientAuthenticationError', 'ModuleNotFoundError',
            'AssertionError', 'OperationalError', 'RuntimeError', 'ServiceRequestError', 'OtherError'):
        result['exception_class'] = output['exception_class']
    if type(output.get('http_status')) is int and output['http_status'] in (400, 401, 403, 404, 429, 500, 503, 504):
        result['http_status'] = output['http_status']
    return result


def diagnose_metadata():
    """Existing resource metadata only, no keys/role/network/config writes."""
    settings = fs.current_settings()['ingestion']
    site = rt.arm(RID)
    identities = site.get('identity', {}).get('userAssignedIdentities', {})
    selected = [v for v in identities.values() if v.get('clientId') == settings.get('AZURE_CLIENT_ID')]
    rt.require(len(selected) == 1, 'selected_ingestion_identity_not_attached')
    workspace_path = rt.RG + '/providers/Microsoft.OperationalInsights/workspaces/poc-ids-token-ex-logs'
    workspace = rt.cli(['rest', '--method', 'get', '--url', 'https://management.azure.com' + workspace_path + '?api-version=2023-09-01'])['properties']
    roles = rt.cli(['role', 'assignment', 'list', '--subscription', rt.SUB, '--all', '--include-inherited'])
    scopes = {'monitor': workspace_path, 'host_storage': rt.RG + '/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc'}
    allowed = {'Log Analytics Reader', 'Storage Blob Data Owner', 'Storage Blob Data Contributor',
               'Storage Queue Data Contributor', 'Storage Table Data Contributor', 'Storage Account Contributor'}
    result = {'at_utc': fs.stamp(), 'read_only': True,
              'workspace_guid_matches': settings.get('AIFLUX_LOG_WORKSPACE_ID') == workspace.get('customerId'),
              'workspace_query_public_network': workspace.get('publicNetworkAccessForQuery'),
              'selected_identity_attached': True,
              'host_storage_identity_matches': settings.get('AzureWebJobsStorage__clientId') == settings.get('AZURE_CLIENT_ID'),
              'host_storage_managedidentity': settings.get('AzureWebJobsStorage__credential') == 'managedidentity',
              'host_storage_uris_expected': all(settings.get('AzureWebJobsStorage__' + service + 'ServiceUri') ==
                  'https://pocidstokenexfunc.' + service + '.core.windows.net' for service in ('blob', 'queue', 'table')),
              'timer_disabled': settings.get('AzureWebJobs.ingest_usage.Disabled') == 'true',
              'catalog_enabled': settings.get('AIFLUX_CATALOG_CONFIGURED') == 'true',
              'cutoff_preserved': settings.get('AIFLUX_INGESTION_START_AT') == '2026-10-27T06:06:02.045288+00:00',
              'roles': {}}
    result['legacy_dashboard_setting_present'] = bool(settings.get('AzureWebJobsDashboard'))
    result['host_secret_storage_explicit_files'] = settings.get('AzureWebJobsSecretStorageType') == 'files'
    result['host_status'] = {k: v for k, v in rt.arm(RID + '/hostruntime/admin/host/status').items()
                             if k in ('state', 'version')}
    from scripts.deployment.finops_diagnose import state_storage_probe
    result['state_storage'] = state_storage_probe()
    pg = rt.RG + '/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg'
    result['postgres_public_network'] = rt.arm(pg)['properties']['network']['publicNetworkAccess']
    result['postgres_firewall_rules'] = len(rt.arm(pg + '/firewallRules').get('value', []))
    for label, scope in scopes.items():
        applicable = [r for r in roles if r.get('principalId') == selected[0]['principalId'] and
                      (scope.lower() == r.get('scope', '').lower() or scope.lower().startswith(r.get('scope', '').lower().rstrip('/') + '/'))]
        result['roles'][label] = [{'role': r['roleDefinitionName'], 'condition_present': bool(r.get('condition'))}
                                  for r in applicable if r.get('roleDefinitionName') in allowed]
    from urllib.error import HTTPError
    token = rt.cli(['account', 'get-access-token', '--subscription', rt.SUB,
                    '--resource', 'https://management.azure.com/'])['accessToken']
    prep = json.loads((rt.ROOT / 'gateway/validation/finops-fresh-preparation-2be1b356c1dd.json').read_text())
    result['prepared_runner_absence'] = {}
    for label, path in prep['ids'].items():
        try:
            version = '2023-05-01' if label in ('ingestion', 'api') else '2024-05-01'
            req = Request('https://management.azure.com' + path + '?api-version=' + version,
                          headers={'Authorization': 'Bearer ' + token})
            with urlopen(req, context=ssl.create_default_context(cafile=rt.CA), timeout=30):
                result['prepared_runner_absence'][label] = False
        except HTTPError as exc:
            result['prepared_runner_absence'][label] = True if exc.code == 404 else {'unverified_http_status': exc.code}
    path = rt.ROOT / 'gateway/validation' / ('finops-authorization-metadata-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json')
    rt.save(path, result)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **result}), flush=True)


def private_query():
    """One bounded attempt through existing ingestion SCM, no keys or new host."""
    from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    settings = fs.current_settings()['ingestion']
    rt.require(settings.get('AzureWebJobs.ingest_usage.Disabled') == 'true' and
               settings.get('AIFLUX_INGESTION_START_AT') == '2026-10-27T06:06:02.045288+00:00', 'protected_cutoff_timer')
    # Execute only retained application SELECT code and a read-only exact KQL
    # window; never call main/run_once/ingest_rows or mutate a checkpoint.
    code = '''import json,logging,os,sys
logging.disable(logging.CRITICAL)
sys.path.insert(0,"/home/site/wwwroot")
out={}
try:
 from datetime import datetime,timedelta
 from azure.identity import ManagedIdentityCredential
 from azure.monitor.query import LogsQueryClient
 from aiflux.config import get_settings
 from aiflux.ingestion import query_rows
 from runtime_check import verify_runtime
 s=get_settings()
 assert s.ingestion_start_at.isoformat()=="2026-10-27T06:06:02.045288+00:00"
 with ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"]) as credential:
  with LogsQueryClient(credential,retry_total=0,connection_timeout=5,read_timeout=30) as client:
   rows=query_rows(client,s,s.ingestion_start_at,s.ingestion_start_at+timedelta(minutes=1))
   out["monitor_exact_query_passed"]=True
  out["postgres_readiness_passed"]=verify_runtime()["sql_tables_readable"] is True
except Exception as exc:
 out["failed"]=True
 out["exception_class"]=type(exc).__name__ if type(exc).__name__ in ("HttpResponseError","ClientAuthenticationError","ModuleNotFoundError","AssertionError","OperationalError","RuntimeError","ServiceRequestError") else "OtherError"
 out["http_status"]=getattr(exc,"status_code",None) if getattr(exc,"status_code",None) in (400,401,403,404,429,500,503,504) else None
print(json.dumps(out))
'''
    command = "timeout 65s python -c \"import base64;exec(base64.b64decode('" + base64.b64encode(code.encode()).decode() + "'))\""
    token = rt.cli(['account', 'get-access-token', '--subscription', rt.SUB,
                    '--resource', 'https://management.azure.com/'])['accessToken']
    req = Request('https://poc-ids-token-ex-ingestion.scm.azurewebsites.net/api/command',
                  data=json.dumps({'command': command, 'dir': '/home/site/wwwroot'}).encode(),
                  headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    result = {'at_utc': fs.stamp(), 'existing_ingestion_scm_only': True, 'new_resources': 0,
              'keys_read': 0, 'timer_invocations': 0, 'database_writes': 0}
    try:
        opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=rt.CA)))
        with opener.open(req, timeout=80) as response:
            raw = response.read(16_385)
            rt.require(len(raw) <= 16_384, 'bounded_scm_response')
            value = json.loads(raw)
            output = json.loads(value.get('Output', value.get('output', '')))
            result['proof'] = safe_private_result(output)
            result['scm_http_status'] = response.status
    except Exception as exc:
        result['blocked'] = True
        result['http_status'] = getattr(exc, 'code', None)
        result['exception_class'] = type(exc).__name__ if type(exc).__name__ in ('HTTPError', 'URLError', 'TimeoutError', 'JSONDecodeError') else 'OtherError'
    path = rt.ROOT / 'gateway/validation' / ('finops-existing-private-query-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json')
    rt.save(path, result)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **result}), flush=True)


def observe():
    status, raw = request('/containerlogs/zip/download', 'POST')
    archive = zipfile.ZipFile(io.BytesIO(raw))
    rt.require(sum(x.file_size for x in archive.infolist()) <= 24_000_000, 'bounded_expanded_logs')
    text = '\n'.join(archive.read(x).decode('utf-8', 'replace') for x in archive.namelist() if not x.endswith('/'))
    result = {'at_utc': fs.stamp(), 'status': status, 'raw_logs_exported': False, 'host_keys_read': 0,
              'expected_digest_seen': 'd2bdae4edbd2faf0f6c5a5b28c83882e36222767f88de9625071b251d4114c0b' in text,
              **summarize(text), 'finite_diagnostics': classify_failures(text),
              'finite_error_contexts': [{'at_utc': (re.search(r'20\d\d-\d\d-\d\d[T ]\d\d:\d\d:\d\d', line).group()
                  if re.search(r'20\d\d-\d\d-\d\d[T ]\d\d:\d\d:\d\d', line) else None),
                  **classify_failures(line)} for line in text.splitlines()
                  if re.search(r'AuthorizationPermissionMismatch|Exception:|Result: Failure|ErrorCode:', line)][:40]}
    path = rt.ROOT / 'gateway/validation' / ('finops-live-runtime-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json')
    rt.save(path, result)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **result}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable-logging', 'restore-logging', 'restart-for-capture', 'ready', 'observe', 'metadata', 'private-query'])
    args = parser.parse_args()
    try:
        {'enable-logging': enable_logging, 'restore-logging': restore_logging, 'restart-for-capture': restart_for_capture,
         'ready': invoke_ready, 'observe': observe, 'metadata': diagnose_metadata, 'private-query': private_query}[args.action]()
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc) if isinstance(exc, RuntimeError)
                          else 'protected_runtime_operation_failed', 'exception_type': type(exc).__name__,
                          'http_status': getattr(exc, 'code', None)}), flush=True)
        raise SystemExit(2)