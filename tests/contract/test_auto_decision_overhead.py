"""Offline render/XML/C# source contracts, not APIM execution or ingestion proof."""
import base64
import json
from pathlib import Path
import re
from string import Formatter
import xml.etree.ElementTree as ET

import pytest

from test_auto_gateway_policy import render

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "gateway/policies/auto-resolve.xml.tftpl"
QUERY = ROOT / "services/control-plane/src/aiflux/queries/decision-overhead.kql"
FIELDS = {
    "schema", "request_id", "routing_profile", "selected_model", "config_version",
    "latency_ms", "usage", "input_tokens", "output_tokens", "cost_usd",
}


@pytest.fixture(scope="module")
def compiled():
    # Existing Terraform console: local expression evaluation only, no plan/init.
    return render([
        f"-var=route_manifest_path={ROOT / 'gateway/catalog/fireworks-candidate-routes.json'}",
        "-var=glm_enabled=true",
    ])


def trace_expression(tree):
    traces = tree.findall('.//trace[@source="aiflux"]')
    traces = [t for t in traces if any(
        m.get("name") == "category" and m.get("value") == "decision-overhead"
        for m in t.findall("metadata")
    )]
    assert len(traces) == 1
    trace = traces[0]
    assert trace.get("severity") == "information"
    assert {m.get("name") for m in trace.findall("metadata")} == {"category", "payload"}
    return trace, trace.find('metadata[@name="payload"]').get("value")


def test_trace_projects_only_validated_bounded_fields_and_gateway_request_id():
    tree = ET.fromstring("<root>" + SOURCE.read_text(encoding="utf-8") + "</root>")
    _, expression = trace_expression(tree)
    assert set(re.findall(r'\["([a-z_]+)"\] =(?!=)', expression)) == FIELDS
    assert '["schema"] = "decision-overhead-v1"' in expression
    assert '["request_id"] = context.RequestId.ToString()' in expression
    assert 'JObject.Parse((string)context.Variables["aiflux-auto-result"])' in expression
    assert '["cost_usd"] = JValue.CreateNull()' in expression
    assert 'overhead["usage"]["input_tokens"]' in expression
    assert 'overhead["usage"]["output_tokens"]' in expression
    assert "Newtonsoft.Json.Formatting.None" in expression
    assert set(re.findall(r'context\.Variables\["([^"]+)"\]', expression)) == {"aiflux-auto-result"}
    for excluded in ("Headers", "Body", "aiflux-auto-scoring-token", "Exception", "response.",
                     "snapshot", "probabilities", "messages", "Subscription", "Authorization"):
        assert excluded not in expression
    # Nullable bounded counters already validated by the resolver; do not zero-fill.
    result = tree.find('.//set-variable[@name="aiflux-auto-result"]').get("value")
    assert '["input_tokens"] = JValue.CreateNull(), ["output_tokens"] = JValue.CreateNull()' in result
    assert "value.Type == JTokenType.Integer" in result and "2147483647" in result
    assert "latency >= 0 && latency <= 120000" in result


def test_one_success_trace_after_rejection_before_any_selected_provider_work(compiled):
    tree = ET.fromstring(compiled["on"])
    trace, _ = trace_expression(tree)
    parents = {child: parent for parent in tree.iter() for child in parent}
    branch = parents[trace]
    assert branch.tag == "when"
    assert branch.get("condition") == '@((bool)context.Variables["aiflux-auto"])'
    children = list(branch)
    index = children.index(trace)
    rejection = children[index - 1]
    assert rejection.tag == "choose"
    assert "IsNullOrEmpty" in rejection.find("when").get("condition")
    assert rejection.find("when/return-response/set-status").get("code") == "503"
    assert children[index + 1].get("name") == "aiflux-model"
    inbound = compiled["on"].split("</inbound>")[0]
    assert inbound.index('value="decision-overhead"') < inbound.index("<set-backend-service")
    assert inbound.count('value="decision-overhead"') == 1
    assert len(tree.findall('.//send-request[@id="aiflux-auto-resolver"]')) == 1
    assert not tree.findall(".//retry//trace/metadata[@value='decision-overhead']")
    assert not tree.findall(".//outbound//trace/metadata[@value='decision-overhead']")
    assert not tree.findall(".//on-error//trace/metadata[@value='decision-overhead']")
    # Success here is selection only, not a second completion or a provider retry.
    assert len(tree.findall('.//set-body[@id="aiflux-auto-metadata"]')) == 1


def test_all_thirteen_explicit_paths_off_remain_byte_identical(compiled):
    assert len(compiled["aliases"]) == 13
    assert compiled["off"].encode() == compiled["old"].encode()
    assert "decision-overhead" not in compiled["off"]
    assert "decision-overhead-v1" not in compiled["off"]
    assert "aiflux-auto" not in compiled["off"]
    # Emission lives in Auto-only composition, never the shared template.
    assert "decision-overhead" not in (ROOT / "gateway/policies/dev-openai.xml.tftpl").read_text()


def test_payload_bound_from_immutable_snapshot_and_numeric_limits(compiled):
    """Size proof for the allowlisted shape, not execution of the C# expression."""
    snapshot = json.loads(base64.b64decode(compiled["snapshot"]))
    assert re.fullmatch(r"[0-9a-f]{64}", snapshot["version"])
    assert set(snapshot["profiles"]) == {"balanced", "cost", "quality"}
    for profile, spec in snapshot["profiles"].items():
        for alias in spec["candidate_models"]:
            assert alias.isascii() and len(alias) <= 128
            for tokens in (None, 2147483647):
                payload = {
                    "schema": "decision-overhead-v1", "request_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                    "routing_profile": profile, "selected_model": alias, "config_version": snapshot["version"],
                    "latency_ms": 119999.99999999999,
                    "usage": {"input_tokens": tokens, "output_tokens": tokens}, "cost_usd": None,
                }
                assert len(json.dumps(payload, separators=(",", ":")).encode()) <= 2048


def test_query_is_separate_scoped_deduplicated_parent_correlated_allowlist():
    query = QUERY.read_text(encoding="utf-8")
    fields = {name for _, name, _, _ in Formatter().parse(query) if name}
    assert fields == {"start", "end", "resource", "product", "row_limit"}
    rendered = query.format(start="2026-10-29T00:00:00Z", end="2026-10-29T01:00:00Z",
                            resource=json.dumps("/test/apim"), product=json.dumps("test"), row_limit=100)
    for required in ('_ResourceId =~ "/test/apim"', 'ProductId == "test"',
                     'OperationId in ("chat", "chat-completions")',
                     'tostring(record.source) == "aiflux"', 'tostring(metadata.category) == "decision-overhead"',
                     'parse_json(tostring(record.metadata))', 'tostring(decision.schema) == "decision-overhead-v1"',
                     "tolower(tostring(decision.request_id)) == correlation_id",
                     "decision_trace_count == 1", "strlen(payload_text) <= 2048",
                     "join kind=inner decisions on resource_id, correlation_id",
                     "arg_max(TimeGenerated, *) by resource_id, correlation_id", "| take 100"):
        assert required in rendered
    assert "coalesce(" not in query and "sum(" not in query
    assert "ApiManagementGatewayLlmLog" not in query
    projection = query.split("| project resource_id, correlation_id, occurred_at")[-1]
    assert "trace_records" not in projection and "payload" not in projection
    assert "decision_input_tokens" in projection and "parent_status_code" in projection
    # This file is packaged by the existing wildcard, not wired to SQL ingestion.
    ingestion = (ROOT / "services/control-plane/src/aiflux/ingestion.py").read_text()
    assert 'joinpath("usage.kql")' in ingestion
    assert "decision-overhead" not in ingestion
    assert 'aiflux = ["queries/*.kql", "pricing/*.json"]' in (ROOT / "pyproject.toml").read_text()


def test_existing_trace_diagnostics_source_supports_information_without_new_infra():
    source = (ROOT / "infra/terraform/apim.tf").read_text(encoding="utf-8")
    diagnostic = source.split('resource "azapi_resource" "monitor_diagnostic"')[1].split(
        'resource "azurerm_monitor_diagnostic_setting" "apim"')[0]
    assert 'verbosity          = "information"' in diagnostic
    assert 'percentage = 100' in diagnostic
    assert 'loggerId           = azapi_resource.monitor_logger.id' in diagnostic
    assert 'logClientIp        = false' in diagnostic
    assert 'body = { bytes = 0 }' in diagnostic
    destination = source.split('resource "azurerm_monitor_diagnostic_setting" "apim"')[1]
    assert 'category = "GatewayLogs"' in destination
    assert 'log_analytics_destination_type = "Dedicated"' in destination
    # Source evidence only; this deliberately makes no actual-configuration claim.