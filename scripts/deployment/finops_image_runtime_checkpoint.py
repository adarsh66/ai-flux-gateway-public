"""Finite read-only post-image checks; no keys, SCM change or timer invocation."""
import argparse
import json
from datetime import UTC, datetime

from scripts.deployment import finops_ingestion_image_repair as image
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.finops_diagnose import log_query


def checkpoint(tag):
    folder = rt.HOME / 'finops' / tag / image.PLAN_FOLDER
    applied, review = image.load(folder / 'applied.json'), image.load(folder / 'review.json')
    rt.require(applied['applied'] is True and applied['plan_sha256'] == review['plan_sha256'], 'exact_apply_required')
    image.verify(tag)
    build = image.build_proof(tag)
    result = {'at_utc': fs.stamp(), 'image': build['image'], 'run_id': build['run_id'],
              'image_plan_sha256': applied['plan_sha256'], 'image_applied_at_utc': applied['at_utc'],
              'host_plan_sha256': review['host_provenance']['plan_sha256'],
              'cutoff': review['host_provenance']['boundary'], 'host_enabled': True,
              'catalog_configured': True, 'timer_disabled': True, 'all_settings_preserved': True,
              'other_three_pins_preserved': True, 'security': review['security'],
              'scanner': review['scanner'], 'host_keys_read': 0, 'manual_timer_invocations': 0,
              'new_runners': 0, 'database_writes': 0, 'scheduled_successes_verified': 0,
              'configured_image_verified': True, 'running_image_independently_verified': False}
    rid = rt.RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-ingestion'
    for label, suffix in [('site', ''), ('functions', '/functions'),
                           ('host', '/hostruntime/admin/host/status'),
                           ('runtime_readiness', '/hostruntime/api/ingestion-ready')]:
        try:
            value = rt.arm(rid + suffix)
            if label == 'site':
                result[label] = {k: value['properties'].get(k) for k in ('enabled', 'state', 'availabilityState')}
            elif label == 'functions':
                result[label] = [{'name': f['name'].split('/')[-1], 'disabled': f['properties'].get('isDisabled')}
                                 for f in value.get('value', [])]
            elif label == 'host':
                result[label] = {k: value.get(k) for k in ('state', 'version')}
            else:
                result[label] = {k: value.get(k) for k in ('sql_tables_readable', 'enabled_models',
                    'owned_subscriptions', 'price_rules', 'watermark')}
        except Exception as exc:
            result[label] = {'status': getattr(exc, 'code', None), 'error_type': type(exc).__name__}
    settings = fs.current_settings()['ingestion']
    since = 'datetime(' + applied['at_utc'] + ')'
    query = ('union isfuzzy=true (AppTraces | project TimeGenerated, Message, AppRoleName), '
        '(traces | project TimeGenerated=timestamp, Message=message, AppRoleName=cloud_RoleName), '
        '(FunctionAppLogs | project TimeGenerated, Message, AppRoleName=AppName) '
        '| where TimeGenerated >= ' + since + ' | where AppRoleName contains "ingestion" '
        '| summarize records=count(), scheduled_started=countif(Message contains "Timer fired"), '
        'successes=countif(Message contains "Executed" and Message contains "Succeeded"), '
        'failures=countif(Message contains "Executed" and Message contains "Failed"), '
        'storage_errors=countif(Message contains "AzureWebJobsStorage" or Message contains "listener"), '
        'database_errors=countif(Message contains "psycopg" or Message contains "OperationalError"), '
        'import_errors=countif(Message contains "ModuleNotFoundError" or Message contains "ImportError"), '
        'configuration_errors=countif(Message contains "ValidationError"), '
        'runtime_readiness_records=countif(Message contains "FinOps runtime readiness")')
    result['post_image_telemetry'] = log_query(settings['AIFLUX_LOG_WORKSPACE_ID'], query)
    result['ready_for_timer'] = False
    result['reason'] = 'runtime_MI_database_and_host_storage_readiness_not_verified'
    path = rt.ROOT / 'gateway/validation' / ('finops-applied-host-image-runtime-' +
                                           datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json')
    rt.save(path, result)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **result}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    try:
        checkpoint(args.tag)
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc) if isinstance(exc, RuntimeError)
                          else 'protected_checkpoint_failed', 'exception_type': type(exc).__name__}), flush=True)
        raise SystemExit(2)