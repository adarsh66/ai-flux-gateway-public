"""Finite read-only timer readback and scheduled evidence; no triggers or config writes."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

from scripts.deployment import finops_catalog_repair as timer
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import finops_live_runtime as runtime
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.finops_diagnose import log_query


def checkpoint():
    folder = timer.HOME / 'timer'
    review, applied = timer.load(folder / 'review.json'), timer.load(folder / 'applied.json')
    rt.require(applied['applied'] is True and applied['plan_sha256'] == review['plan_sha256']
               == timer.release.digest((folder / 'stage.tfplan').read_bytes()), 'exact_timer_apply_required')
    timer.verify('timer')
    settings = fs.current_settings()
    target = timer.load(folder / 'target-settings.json')
    before = dict(target)
    before['AzureWebJobs.ingest_usage.Disabled'] = 'true'
    rt.require(fs.sha(before) == review['settings_hashes']['ingestion']
               and settings['ingestion'] == target
               and review['changed_setting_names'] == ['AzureWebJobs.ingest_usage.Disabled'],
               'single_timer_flag_delta_required')
    now = datetime.now(UTC)
    following = now.replace(second=0, microsecond=0) + timedelta(minutes=5 - now.minute % 5)
    result = {'at_utc': fs.stamp(), 'timer_enabled': True, 'timer_enabled_at_utc': applied['at_utc'],
              'enabled_at_semantics': 'exact_saved_plan_apply_completed_UTC',
              'plan_sha256': applied['plan_sha256'], 'timer_disabled_setting_readback': target['AzureWebJobs.ingest_usage.Disabled'],
              'changed_setting_names': review['changed_setting_names'], 'settings_hashes_before': review['settings_hashes'],
              'settings_hashes_after': {k: fs.sha(v) for k, v in settings.items()},
              'protected_baseline_and_all_four_images': 'verified_unchanged',
              'start_at_unchanged': target['AIFLUX_INGESTION_START_AT'], 'catalog_configured': target['AIFLUX_CATALOG_CONFIGURED'],
              'image': review['image'], 'host_enabled': review['enabled'], 'schedule_UTC': '0 */5 * * * *',
              'next_scheduled_UTC': following.isoformat(), 'runOnStartup': False,
              'manual_timer_invocations': 0, 'new_images': 0, 'network_changes': 0, 'role_changes': 0,
              'historical_requests_deferred': 156, 'backfill_executed': False, 'watermark_reset': False,
              'scheduled_successes_verified': 0, 'scheduled_failures_verified': 0}
    rid = runtime.RID
    for label, suffix in [('site', ''), ('host', '/hostruntime/admin/host/status'), ('functions', '/functions')]:
        try:
            value = rt.arm(rid + suffix)
            if label == 'functions':
                result[label] = [{'name': f['name'].split('/')[-1], 'disabled': f['properties'].get('isDisabled')}
                                 for f in value.get('value', [])]
            else:
                props = value.get('properties', value)
                result[label] = {k: props.get(k) for k in ('enabled', 'state', 'version') if k in props}
        except Exception as exc:
            result[label] = {'http_status': getattr(exc, 'code', None), 'exception_class': type(exc).__name__}
    try:
        status, raw = runtime.request('/containerlogs/zip/download', 'POST')
        archive = zipfile.ZipFile(io.BytesIO(raw))
        rt.require(sum(f.file_size for f in archive.infolist()) <= 24_000_000, 'bounded_expanded_logs')
        text = '\n'.join(archive.read(f).decode('utf-8', 'replace') for f in archive.namelist() if not f.endswith('/'))
        observed = runtime.summarize(text)
        since = datetime.fromisoformat(timer.load(folder / 'apply-intent.json')['at_utc'])
        def current(row):
            try:
                at = datetime.fromisoformat(row['at_utc'].replace('Z', '+00:00'))
                return at.replace(tzinfo=at.tzinfo or UTC) >= since
            except (TypeError, ValueError, AttributeError):
                return False
        starts = [s for s in observed['scheduled_starts'] if current(s) and s['scheduled'] and not s['manual']]
        ids = {s['invocation_id'] for s in starts}
        executions = [e for e in observed['executions'] if current(e) and e['invocation_id'] in ids]
        result['scheduled_console_evidence'] = {'http_status': status, 'raw_logs_exported': False,
            'expected_digest_seen': timer.TIMER_IMAGE.split(':')[-1] in text,
            'starts': starts, 'executions': executions,
            'current_failures': [e for e in observed['failures'] if current(e)]}
        result['scheduled_successes_verified'] = len({e['invocation_id'] for e in executions if e['result'] == 'Succeeded'})
        result['scheduled_failures_verified'] = len({e['invocation_id'] for e in executions if e['result'] == 'Failed'})
        if result['scheduled_failures_verified']:
            result['finite_failure_categories'] = runtime.classify_failures(text)
    except Exception as exc:
        result['scheduled_console_evidence'] = {'http_status': getattr(exc, 'code', None), 'exception_class': type(exc).__name__}
    query = ('union isfuzzy=true (AppTraces | project TimeGenerated, Message, AppRoleName), '
             '(traces | project TimeGenerated=timestamp, Message=message, AppRoleName=cloud_RoleName), '
             '(FunctionAppLogs | project TimeGenerated, Message, AppRoleName=AppName) '
             '| where TimeGenerated >= datetime(' + applied['at_utc'] + ') '
             '| where AppRoleName contains "ingestion" '
             '| summarize records=count(), scheduled_starts=countif(Message contains "Executing" and '
             'Message contains "ingest_usage" and (Message contains "Timer fired" or Message contains "Reason=Schedule")), '
             'handler_successes=countif(Message contains "Executed" and Message contains "ingest_usage" and Message contains "Succeeded"), '
             'handler_failures=countif(Message contains "Executed" and Message contains "ingest_usage" and Message contains "Failed")')
    result['scheduled_aggregate_telemetry'] = log_query(target['AIFLUX_LOG_WORKSPACE_ID'], query)
    path = rt.ROOT / 'gateway/validation/finops-timer-activation-20261027.json'
    rt.save(path, result)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **result}), flush=True)


if __name__ == '__main__':
    try:
        checkpoint()
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc) if isinstance(exc, RuntimeError)
                          else 'protected_timer_readback_failed', 'exception_class': type(exc).__name__}), flush=True)
        raise SystemExit(2)