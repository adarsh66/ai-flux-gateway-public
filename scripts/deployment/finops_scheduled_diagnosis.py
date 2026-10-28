"""Bounded timer diagnostics and explicit one-shot repair; no raw logs or secrets."""
import io
import json
import re
import argparse
import ssl
import zipfile
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen
from urllib.parse import quote
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_live_runtime as live
from scripts.deployment import finops_function_stage as fs
from scripts.deployment.finops_diagnose import log_query


def verify_reconciled_baseline(actual, expected, settings, expected_hashes):
    """No metadata/settings/image/identity/ingress drift waiver."""
    rt.require(actual == expected, 'protected_baseline_drift')
    rt.require({k: fs.sha(v) for k, v in settings.items()} == expected_hashes,
               'complete_settings_drift')


def scheduled_evidence(events, since):
    """Require a current schedule reason and matching successful invocation ID."""
    boundary = datetime.fromisoformat(since.replace('Z', '+00:00'))
    rt.require(boundary.tzinfo is not None, 'utc_evidence_boundary_required')
    def current(row):
        try:
            at = datetime.fromisoformat(row['at_utc'].replace('Z', '+00:00'))
            return at.tzinfo is not None and at >= boundary
        except (KeyError, TypeError, ValueError, AttributeError):
            return False
    starts = {s['invocation_id']: s for s in events['scheduled_starts']
              if current(s) and s['scheduled'] and not s['manual']}
    executions = {e['invocation_id']: e for e in events['executions']
                  if current(e) and e['function'] == 'ingest_usage'
                  and e['invocation_id'] in starts}
    return {'starts': list(starts.values()), 'executions': list(executions.values()),
            'successes': sum(e['result'] == 'Succeeded' for e in executions.values()),
            'failures': sum(e['result'] == 'Failed' for e in executions.values())}


def collect():
    settings = fs.current_settings()['ingestion']
    site = rt.arm(live.RID)['properties']
    web = rt.arm(live.RID + '/config/web')['properties']
    plan = rt.arm(site['serverFarmId'])
    result = {'at_utc': datetime.now(UTC).isoformat(), 'read_only': True,
              'always_on': web.get('alwaysOn'), 'plan_sku': plan.get('sku'),
              'web_readback': {k: web.get(k) for k in ('remoteDebuggingEnabled', 'remoteDebuggingVersion', 'virtualApplications')},
              'timer_disabled': settings.get('AzureWebJobs.ingest_usage.Disabled'),
              'cutoff': settings.get('AIFLUX_INGESTION_START_AT')}
    status, raw = live.request('/containerlogs/zip/download', 'POST')
    archive = zipfile.ZipFile(io.BytesIO(raw))
    rt.require(sum(f.file_size for f in archive.infolist()) <= 24_000_000, 'bounded_logs')
    result['console_status'] = status
    result['files'] = []
    for f in archive.infolist():
        if f.is_dir():
            continue
        text = archive.read(f).decode('utf-8', 'replace')
        stamps = re.findall(r'20\d\d-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?Z?', text)
        result['files'].append({'bytes': f.file_size, 'archive_date': list(f.date_time),
            'first_timestamp': min(stamps) if stamps else None,
            'last_timestamp': max(stamps) if stamps else None,
            'expected_image': 'd2bdae4edbd2faf0f6c5a5b28c83882e36222767f88de9625071b251d4114c0b' in text,
            'events': live.summarize(text), 'categories': live.classify_failures(text),
            'timer_listener_mentions': len(re.findall(r'timer|listener|schedule', text, re.I))})
    connection = settings.get('APPLICATIONINSIGHTS_CONNECTION_STRING', '')
    key = settings.get('APPINSIGHTS_INSTRUMENTATIONKEY')
    if not key:
        match = re.search(r'(?:^|;)InstrumentationKey=([^;]+)', connection, re.I)
        key = match[1] if match else None
    result['appinsights_configured'] = bool(key)
    result['appinsights_authentication_setting_present'] = bool(settings.get('APPLICATIONINSIGHTS_AUTHENTICATION_STRING'))
    now = datetime.now(UTC)
    result['schedule_UTC'] = '0 */5 * * * *'
    result['next_scheduled_UTC'] = (now.replace(second=0, microsecond=0)
        + timedelta(minutes=5 - now.minute % 5)).isoformat()
    result['manual_timer_invocations'] = 0
    applied = json.loads((rt.ROOT / 'gateway/validation/finops-always-on-applied-20261027.json').read_text())
    combined = {k: [] for k in ('scheduled_starts', 'executions')}
    for item in result['files']:
        for kind in combined:
            combined[kind].extend(item['events'][kind])
    result['scheduled_console_since_always_on'] = scheduled_evidence(combined, applied['at_utc'])
    result['always_on_applied_at_utc'] = applied['at_utc']
    result['host_status'] = {k: v for k, v in rt.arm(live.RID + '/hostruntime/admin/host/status').items()
                             if k in ('state', 'version')}
    components = rt.cli(['rest', '--method', 'get', '--url',
        'https://management.azure.com' + rt.RG + '/providers/Microsoft.Insights/components?api-version=2020-02-02'])
    matches = [c for c in components.get('value', []) if key and c['properties'].get('InstrumentationKey') == key]
    site_resource = rt.arm(live.RID)
    links = {str(v).lower() for k, v in site_resource.get('tags', {}).items()
             if k.lower() == 'hidden-link: /app-insights-resource-id'}
    if not matches:
        matches = [c for c in components.get('value', []) if c['id'].lower() in links]
    result['appinsights_linked_resource_count'] = len(matches)
    result['matching_appinsights'] = []
    for component in matches:
        props = component['properties']
        workspace_id = props.get('WorkspaceResourceId')
        entry = {'resource_id': component['id'], 'workspace_resource_id': workspace_id,
             'binding': 'instrumentation_key' if key else 'site_resource_link_not_runtime_configuration',
                 'retention_days': props.get('RetentionInDays')}
        if workspace_id:
            workspace = rt.cli(['rest', '--method', 'get', '--url',
                'https://management.azure.com' + workspace_id + '?api-version=2023-09-01'])['properties']['customerId']
            for table in ('AppTraces', 'AppRequests'):
                query = (table + ' | where TimeGenerated >= datetime(' + applied['at_utc'] + ') '
                         + '| where _ResourceId =~ ' + json.dumps(component['id']) + ' ')
                if table == 'AppTraces':
                    query += '| where AppRoleName contains "ingestion" | extend invocation=tostring(Properties.InvocationId) | project TimeGenerated, invocation, scheduled=Message contains "Timer fired" or Message contains "Reason=Schedule", success=Message contains "Succeeded", failed=Message contains "Failed", function=Message contains "ingest_usage" | where function or scheduled | order by TimeGenerated desc | take 30'
                elif table == 'AppRequests':
                    query += '| where AppRoleName contains "ingestion" and Name contains "ingest_usage" | project TimeGenerated, Success, DurationMs, InvocationId=tostring(Properties.InvocationId) | order by TimeGenerated desc | take 30'
                entry[table] = log_query(workspace, query)
        result['matching_appinsights'].append(entry)
    path = rt.ROOT / 'gateway/validation' / ('finops-scheduled-diagnosis-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json')
    rt.save(path, result)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **result}), flush=True)


def reconcile():
    from scripts.deployment import finops_catalog_repair as timer
    from scripts.deployment import portal_fix as portals
    baseline = timer.load(timer.HOME / 'timer/baseline.json')
    proof = timer.load(timer.HOME / 'timer/review.json')
    baseline['sites']['ingestion']['image'] = 'DOCKER|' + proof['image']
    baseline['sites']['ingestion']['protected']['enabled'] = proof['enabled']
    baseline['sites']['ingestion']['protected']['web']['alwaysOn'] = True
    actual = portals.baseline()
    settings = fs.current_settings()
    expected = timer.load(timer.HOME / 'timer/target-settings.json')
    result = {'at_utc': fs.stamp(), 'read_only': True,
              'full_protected_baseline_except_approved_always_on_matches': actual == baseline,
              'ingestion_exact_settings_preserved': settings['ingestion'] == expected,
              'settings_sha256': {k: fs.sha(v) for k, v in settings.items()},
              'web_metadata': {k: rt.arm(live.RID + '/config/web')['properties'].get(k)
                               for k in ('alwaysOn', 'remoteDebuggingEnabled', 'remoteDebuggingVersion', 'virtualApplications')}}
    web = rt.arm(live.RID + '/config/web')['properties']
    original_plan = timer.load(rt.ROOT / 'gateway/validation/finops-always-on-plan-20261027.json')
    plan_body = {k: v for k, v in original_plan.items() if k != 'plan_sha256'}
    intent = timer.load(rt.ROOT / 'gateway/validation/finops-always-on-intent-20261027.json')
    applied = timer.load(rt.ROOT / 'gateway/validation/finops-always-on-applied-20261027.json')
    rt.require(fs.sha(plan_body) == original_plan['plan_sha256'] == intent['plan_sha256']
               == applied['plan_sha256'] and intent['single_put'] is True
               and applied['http_status'] == 200 and applied['always_on'] is True,
               'existing_apply_provenance_mismatch')
    matches = []
    application_candidates = [None, []]
    for physical in ('site\\wwwroot', 'site/wwwroot', '/home/site/wwwroot'):
        for preload in (None, False, True):
            for directories in (None, []):
                application_candidates.append([{'virtualPath': '/', 'physicalPath': physical,
                    'preloadEnabled': preload, 'virtualDirectories': directories}])
            application_candidates.append([{'virtualPath': '/', 'physicalPath': physical,
                'preloadEnabled': preload}])
    for version in (None, '', 'VS2012', 'VS2013', 'VS2015', 'VS2017', 'VS2019', 'VS2022'):
        for applications in application_candidates:
            candidate = {**web, 'alwaysOn': False, 'remoteDebuggingVersion': version,
                         'virtualApplications': applications}
            if (fs.sha(candidate) == original_plan['before_web_sha256']
                    and fs.sha({**candidate, 'alwaysOn': True}) == original_plan['target_web_sha256']):
                matches.append({'remoteDebuggingVersion': version, 'virtualApplications': applications})
    result['hash_verified_prior_web_metadata'] = matches
    rt.save(rt.ROOT / 'gateway/validation/finops-always-on-reconciliation-20261027.json', result)
    rt.require(len(matches) == 1, 'prior_web_metadata_not_hash_authenticated')
    verify_reconciled_baseline(actual, baseline, settings, original_plan['settings_sha256'])
    rt.require(web.get('alwaysOn') is True and settings['ingestion'] == expected,
               'always_on_or_ingestion_settings_drift')
    print(json.dumps(result), flush=True)


def timer_storage():
    """Existing schedule status GETs only; no leases, keys or storage writes."""
    token = rt.cli(['account', 'get-access-token', '--subscription', rt.SUB,
                    '--resource', 'https://storage.azure.com/'])['accessToken']
    base = 'https://pocidstokenexfunc.blob.core.windows.net/azure-webjobs-hosts/'
    def get(suffix):
        req = Request(base + suffix, headers={'Authorization': 'Bearer ' + token,
                                             'x-ms-version': '2023-11-03'})
        with urlopen(req, context=ssl.create_default_context(cafile=rt.CA), timeout=30) as response:
            raw = response.read(100_001)
            rt.require(len(raw) <= 100_000, 'bounded_timer_metadata')
            return raw
    result = {'at_utc': fs.stamp(), 'read_only': True, 'storage_writes': 0, 'schedule_status': []}
    try:
        listing = ET.fromstring(get('?restype=container&comp=list&prefix=timers%2F&maxresults=100'))
        names = [e.text for e in listing.findall('./Blobs/Blob/Name')]
        for name in names:
            if name and name.endswith('/ingest_usage/status'):
                value = json.loads(get(quote(name, safe='/')))
                result['schedule_status'].append({k: value.get(k) for k in ('Last', 'Next', 'LastUpdated')})
        result['http_status'] = 200
    except HTTPError as exc:
        result['http_status'] = exc.code
    rt.save(rt.ROOT / 'gateway/validation/finops-timer-storage-status-20261027.json', result)
    print(json.dumps(result), flush=True)


def always_on_target(web):
    rt.require(web.get('alwaysOn') is False, 'always_on_already_enabled_no_reapply')
    return {**web, 'alwaysOn': True}


def repair_always_on():
    """One approved existing-B1 setting only; exact comparison and no retries."""
    home = rt.ROOT / 'gateway/validation'
    intent = home / 'finops-always-on-intent-20261027.json'
    rt.require(not intent.exists(), 'existing_always_on_intent_reconcile_no_retry')
    before_settings = fs.current_settings()
    rt.require(before_settings['ingestion']['AzureWebJobs.ingest_usage.Disabled'] == 'false'
               and before_settings['ingestion']['AIFLUX_INGESTION_START_AT'] ==
               '2026-10-27T06:06:02.045288+00:00', 'protected_timer_and_cutoff')
    web = rt.arm(live.RID + '/config/web')['properties']
    plan_id = rt.arm(live.RID)['properties']['serverFarmId']
    sku = rt.arm(plan_id)['sku']
    rt.require(sku['name'] == 'B1', 'existing_B1_required')
    target = always_on_target(web)
    plan = {'at_utc': fs.stamp(), 'resource_id': live.RID + '/config/web',
            'approved_scope': 'existing_dedicated_plan_always_on_only',
            'changed_fields': ['alwaysOn'], 'before': False, 'after': True,
            'before_web_sha256': fs.sha(web), 'target_web_sha256': fs.sha(target),
            'settings_sha256': {k: fs.sha(v) for k, v in before_settings.items()},
            'plan_sku': sku, 'new_resources': 0, 'timer_invocations': 0}
    plan['plan_sha256'] = fs.sha(plan)
    rt.save(home / 'finops-always-on-plan-20261027.json', plan)
    rt.require(rt.arm(live.RID + '/config/web')['properties'] == web, 'web_drift_no_write')
    rt.save(intent, {'at_utc': fs.stamp(), 'plan_sha256': plan['plan_sha256'], 'single_put': True})
    token = rt.cli(['account', 'get-access-token', '--subscription', rt.SUB,
                    '--resource', 'https://management.azure.com/'])['accessToken']
    req = Request('https://management.azure.com' + live.RID + '/config/web?api-version=2024-04-01',
                  data=json.dumps({'properties': target}).encode(), method='PUT',
                  headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urlopen(req, context=ssl.create_default_context(cafile=rt.CA), timeout=90) as response:
        response.read(8_000_001)
        status = response.status
    after = rt.arm(live.RID + '/config/web')['properties']
    delta = sorted(k for k in set(web) | set(after) if web.get(k) != after.get(k))
    settings_unchanged = fs.current_settings() == before_settings
    plan_unchanged = rt.arm(plan_id)['sku'] == sku
    result = {'at_utc': fs.stamp(), 'http_status': status, 'plan_sha256': plan['plan_sha256'],
              'changed_fields': delta, 'always_on': after.get('alwaysOn'),
              'all_four_settings_unchanged': settings_unchanged, 'plan_sku_unchanged': plan_unchanged,
              'all_four_images_unchanged': web.get('linuxFxVersion') == after.get('linuxFxVersion') and settings_unchanged,
              'manual_timer_invocations': 0, 'network_changes': 0, 'role_changes': 0}
    rt.save(home / 'finops-always-on-applied-20261027.json', result)
    rt.require(delta == ['alwaysOn'] and settings_unchanged and plan_unchanged,
               'unexpected_always_on_readback_delta')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair-always-on', action='store_true')
    parser.add_argument('--reconcile', action='store_true')
    parser.add_argument('--timer-storage', action='store_true')
    args = parser.parse_args()
    if args.timer_storage:
        timer_storage()
    elif args.reconcile:
        reconcile()
    else:
        repair_always_on() if args.repair_always_on else collect()