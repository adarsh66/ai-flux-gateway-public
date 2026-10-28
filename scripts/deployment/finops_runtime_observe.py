"""Metadata-only Function host and sanitized native telemetry observation; no keys."""
import json
from datetime import UTC, datetime

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import finops_catalog_repair as repair
from scripts.deployment.finops_diagnose import log_query


def observe():
    rid = rt.RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-ingestion'
    result = {'at_utc': fs.stamp(), 'no_host_keys_read': True, 'manual_timer_invocations': 0}
    for label, path in [('site', ''), ('functions', '/functions'), ('host', '/hostruntime/admin/host/status')]:
        try:
            value = rt.arm(rid + path)
            if label == 'site':
                result[label] = {k: value['properties'].get(k) for k in ('enabled', 'state', 'availabilityState')}
            elif label == 'functions':
                result[label] = [{'name': f['name'].split('/')[-1],
                                  'disabled': f['properties'].get('isDisabled'),
                                  'config': {k: f['properties'].get('config', {}).get(k) for k in ('entryPoint',)}} for f in value['value']]
            else:
                result[label] = {k: value.get(k) for k in ('state', 'version', 'errors') if k != 'errors'}
        except Exception as exc:
            result[label] = {'error_type': type(exc).__name__, 'status': getattr(exc, 'code', None)}
    settings = fs.current_settings()['ingestion']
    workspace = settings['AIFLUX_LOG_WORKSPACE_ID']
    start = repair.load(repair.HOME / 'boundary.json')['start_at']
    result['function_logs'] = log_query(workspace,
        'union isfuzzy=true (AppTraces | project TimeGenerated, Message, AppRoleName), '
        '(traces | project TimeGenerated=timestamp, Message=message, AppRoleName=cloud_RoleName), '
        '(FunctionAppLogs | project TimeGenerated, Message, AppRoleName=AppName) '
        '| where TimeGenerated > ago(30m) | where AppRoleName contains "ingestion" '
        '| summarize records=count(), scheduled_started=countif(Message contains "Timer fired" or Message contains "Reason=\'Timer fired"), '
        'successes=countif(Message contains "Executed" and Message contains "Succeeded"), '
        'failures=countif(Message contains "Executed" and Message contains "Failed"), '
        'storage_errors=countif(Message contains "AzureWebJobsStorage" or Message contains "listener"), '
        'database_errors=countif(Message contains "psycopg" or Message contains "OperationalError"), '
        'config_errors=countif(Message contains "ValidationError" or Message contains "ModuleNotFoundError")')
    result['native_usage'] = log_query(workspace,
        'ApiManagementGatewayLogs | where TimeGenerated >= datetime(' + start + ') '
        '| where _ResourceId =~ ' + json.dumps(settings['AIFLUX_APIM_RESOURCE_ID']) + ' '
        '| where ProductId == "aiflux" and OperationId in ("chat", "chat-completions") '
        '| mv-expand t=todynamic(TraceRecords) | where tostring(t.source)=="aiflux" '
        '| extend m=todynamic(t.metadata) | where tostring(m.category)=="usage" '
        '| extend u=parse_json(tostring(m.payload)) '
        '| summarize requests=count(), measured=countif(isnotnull(u.input_tokens) and isnotnull(u.output_tokens)), '
        'inputs=sum(tolong(u.input_tokens)), outputs=sum(tolong(u.output_tokens)) by model=tostring(u.model)')
    path = rt.ROOT / 'gateway/validation' / ('finops-runtime-observation-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json')
    rt.save(path, result)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **result}), flush=True)


if __name__ == '__main__':
    observe()