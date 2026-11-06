"""Frozen-cutoff metadata only; demo subset is NOT org-wide ledger evidence."""
import json
from query_readonly import HERE, RESOURCE, query, save

at = json.loads((HERE / "snapshot04.json").read_text())["as_of"]
sid = "e9f2abb0-930b-598a-b210-0ab0b279127f"
scope = f'ApiManagementGatewayLogs | where TimeGenerated >= datetime(2026-11-01) and TimeGenerated <= datetime({at}) | where _ResourceId =~ {json.dumps(RESOURCE)} '
save("telemetry05-scope.json", {"as_of": at, "demo_subscription_id": sid,
    "ownership_evidence": "gateway/validation/fireworks-live-acceptance-20261028.json scheduled_reporting",
    "ownership_limit": "Authenticated October28 evidence, not a fresh November DB ownership check; subset only",
    "all_organization_subscriptions_verified": False, "ledger_rows_exported": False})
query("gateway-inventory05", scope + '| summarize rows=count(), first_seen=min(TimeGenerated), last_seen=max(TimeGenerated) by ProductId, OperationId, ResponseCode | order by ProductId asc, OperationId asc, ResponseCode asc')
query("trace-keys05", scope + '| mv-expand record=TraceRecords | where tostring(record.source)=="aiflux" | extend m=parse_json(tostring(record.metadata)) | where tostring(m.category) in ("usage", "decision-overhead") | extend p=parse_json(tostring(m.payload)) | summarize traces=count() by category=tostring(m.category), schema=tostring(p.schema), keys=tostring(bag_keys(p))')
demo = scope + f'| where ApimSubscriptionId == "{sid}" | where OperationId in ("chat", "chat-completions") | extend resource_id=tolower(_ResourceId), correlation_id=tolower(tostring(CorrelationId)) | summarize arg_max(TimeGenerated, *) by resource_id, correlation_id '
query("demo-summary05", demo + '| summarize requests=count(), first_seen=min(TimeGenerated), last_seen=max(TimeGenerated) by ProductId, ResponseCode')
gateway = demo + '| project resource_id, correlation_id, occurred_at=TimeGenerated, subscription_id=ApimSubscriptionId, parent_status_code=ResponseCode, backend_id=BackendId, gateway_region=Region, ProductId, trace_records=TraceRecords'
usage = '''let usage = gateway
| mv-expand record=trace_records
| where tostring(record.source)=="aiflux"
| extend m=parse_json(tostring(record.metadata))
| where tostring(m.category)=="usage"
| extend p=parse_json(tostring(m.payload))
| summarize usage_trace_count=count(), schemas=make_set(tostring(p.schema),3), models=make_set(tostring(p.model),3), input_values=make_set(tolong(p.input_tokens),3), output_values=make_set(tolong(p.output_tokens),3), cached_values=make_set(tolong(p.cached_input_tokens),3), write_values=make_set(tolong(p.cache_write_tokens),3), attempts_values=make_set(tolong(p.attempts),3) by resource_id,correlation_id;
'''
llm = f'''let llm = ApiManagementGatewayLlmLog | where TimeGenerated >= datetime(2026-11-01) and TimeGenerated <= datetime({at}) | where _ResourceId =~ {json.dumps(RESOURCE)}
| extend resource_id=tolower(_ResourceId), correlation_id=tolower(tostring(CorrelationId))
| summarize llm_rows=count(), llm_input_max=max(PromptTokens), llm_output_max=max(CompletionTokens), llm_models=make_set(ModelName,3), llm_deployments=make_set(DeploymentName,3), backend_requests=make_set_if(RequestId,isnotempty(RequestId),3) by resource_id,correlation_id
| extend backend_request_count_capped=array_length(backend_requests) | project-away backend_requests;
'''
query("demo-completion-metadata05", 'let gateway = ' + gateway + ';\n' + usage + llm + '''gateway
| join kind=leftouter usage on resource_id,correlation_id
| join kind=leftouter llm on resource_id,correlation_id
| project resource_id, correlation_id, occurred_at, subscription_id, parent_status_code, backend_id, gateway_region, ProductId, usage_trace_count, schemas, models, input_values, output_values, cached_values, write_values, attempts_values, llm_rows, llm_input_max, llm_output_max, llm_models, llm_deployments, backend_request_count_capped
| order by occurred_at asc | take 1001''')
# Keep rejected trace counts instead of silently turning them into absence.
decisions = '''let decisions = gateway | mv-expand record=trace_records | where tostring(record.source)=="aiflux"
| extend m=parse_json(tostring(record.metadata)) | where tostring(m.category)=="decision-overhead"
| extend p=parse_json(tostring(m.payload))
| summarize decision_trace_count=count(), schema=take_any(tostring(p.schema)), request_id=take_any(tolower(tostring(p.request_id))), routing_profile=take_any(tostring(p.routing_profile)), selected_model=take_any(tostring(p.selected_model)), config_version=take_any(tostring(p.config_version)), input_tokens=take_any(tolong(p.usage.input_tokens)), output_tokens=take_any(tolong(p.usage.output_tokens)), latency_ms=take_any(todouble(p.latency_ms)), max_payload_chars=max(strlen(tostring(m.payload))) by resource_id,correlation_id;
'''
query("demo-scoring-metadata05", 'let gateway = ' + gateway + ';\n' + decisions + '''gateway
| join kind=inner decisions on resource_id,correlation_id
| project resource_id, correlation_id, occurred_at, subscription_id, parent_status_code, decision_trace_count, schema, request_id, routing_profile, selected_model, config_version, input_tokens, output_tokens, latency_ms, max_payload_chars
| order by occurred_at asc | take 1001''')