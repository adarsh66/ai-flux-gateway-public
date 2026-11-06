"""One query-only Log Analytics POST, no ingest/control endpoints or secrets."""
import datetime
import json
import os
import subprocess
from read_metadata import BASE, CLI, HERE, read, save

save("logs03-intent.json", {"at": datetime.datetime.now(datetime.UTC).isoformat(),
     "operation": "Log Analytics query-only POST; no data/configuration mutation",
     "workspace": "004a359b-dde6-40fb-843c-4d5651785e17",
     "fields": "table schema names/types only", "prompts_or_raw_payload_export": False})
read("gateway-tables03", ["rest", "--method", "get", "--url", BASE +
     "Microsoft.OperationalInsights/workspaces/poc-ids-token-ex-logs/tables?api-version=2022-10-01",
     "--query", "value[].{name:name,plan:properties.plan,retentionInDays:properties.retentionInDays,totalRetentionInDays:properties.totalRetentionInDays}"])
query = "ApiManagementGatewayLogs | getschema | project ColumnName, DataType"
save("logs03-body.json", {"query": query})
env = dict(os.environ, REQUESTS_CA_BUNDLE=r"C:/Users/p4032099/.azure/ca-bundle-zscaler.pem")
args = [CLI, "-X", "utf8", "-IBm", "azure.cli", "rest", "--method", "post", "--url",
        "https://api.loganalytics.io/v1/workspaces/004a359b-dde6-40fb-843c-4d5651785e17/query",
        "--resource", "https://api.loganalytics.io", "--body", "@" + str(HERE / "logs03-body.json"),
        "--headers", "Content-Type=application/json", "--subscription", "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52",
        "--output", "json", "--only-show-errors"]
r = subprocess.run(args, capture_output=True, encoding="utf-8", env=env, timeout=180)
if r.returncode or not r.stdout.strip():
    save("logs03-error.json", {"exit": r.returncode, "stderr": r.stderr[:7000], "stdout_empty": not bool(r.stdout.strip())})
    print("LOGS_SCHEMA_QUERY_FAILED", r.returncode, r.stderr[:2000])
else:
    data = json.loads(r.stdout)
    save("logs03-schema.json", data)
    print("LOGS_SCHEMA", json.dumps(data))