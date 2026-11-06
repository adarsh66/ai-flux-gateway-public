"""Finite read-only KQL transport. Exclusive receipts, no raw trace export."""
import datetime
import json
import os
import re
import subprocess
from read_metadata import CLI, HERE, save

WORKSPACE = "004a359b-dde6-40fb-843c-4d5651785e17"
RESOURCE = "/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"


def query(label, kql):
    assert re.fullmatch(r"[a-z0-9-]+", label)
    assert not re.search(r"(?im)^\s*\.(?:set|append|create|alter|drop|delete|execute)", kql)
    save(label + "-intent.json", {"at": datetime.datetime.now(datetime.UTC).isoformat(),
        "workspace": WORKSPACE, "operation": "read-only KQL query", "query": kql,
        "raw_messages_headers_bodies_exported": False})
    body = label + "-body.json"
    save(body, {"query": kql})
    env = dict(os.environ, REQUESTS_CA_BUNDLE=r"C:/Users/p4032099/.azure/ca-bundle-zscaler.pem")
    r = subprocess.run([CLI, "-X", "utf8", "-IBm", "azure.cli", "rest", "--method", "post",
        "--url", f"https://api.loganalytics.io/v1/workspaces/{WORKSPACE}/query",
        "--resource", "https://api.loganalytics.io", "--body", "@" + str(HERE / body),
        "--headers", "Content-Type=application/json", "--subscription", "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52",
        "--output", "json", "--only-show-errors"], capture_output=True, encoding="utf-8", env=env, timeout=180)
    if r.returncode or not r.stdout.strip():
        save(label + "-error.json", {"exit": r.returncode, "stderr": r.stderr[:7000]})
        print(label, "FAILED", r.stderr[:1000], flush=True)
        return None
    result = json.loads(r.stdout)
    save(label + "-result.json", result)
    print(label, json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    at = datetime.datetime.now(datetime.UTC).isoformat()
    save("snapshot04.json", {"as_of": at, "start": "2026-11-01T00:00:00Z", "end_exclusive": "2026-12-01T00:00:00Z",
         "scope": "APIM resource only, all organizations; not Caldova ownership proof"})
    scope = f'ApiManagementGatewayLogs | where TimeGenerated >= datetime(2026-11-01) and TimeGenerated <= datetime({at}) | where _ResourceId =~ {json.dumps(RESOURCE)} '
    query("gateway-inventory04", scope + '| summarize rows=count(), first=min(TimeGenerated), last=max(TimeGenerated) by ProductId, OperationId, ResponseCode | order by ProductId asc, OperationId asc, ResponseCode asc')
    query("trace-categories04", scope + '| mv-expand record=TraceRecords | where tostring(record.source) == "aiflux" | extend m=parse_json(tostring(record.metadata)) | summarize traces=count() by category=tostring(m.category) | order by category asc')
    query("llm-schema04", 'ApiManagementGatewayLlmLog | getschema | project ColumnName, DataType')