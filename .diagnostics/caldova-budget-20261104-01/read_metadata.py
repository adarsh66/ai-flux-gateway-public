"""One-shot allowlisted production metadata GETs; no credentials or write APIs."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
CLI = r"C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe"
SUB = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
RG = "IDS-TOKEN-EXCHANGE-POC"
BASE = f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG}/providers/"


def save(name, value):
    with (HERE / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True)


def read(label, args):
    assert args[:2] in (["resource", "list"], ["rest", "--method"])
    if args[0] == "rest":
        assert args[2] == "get"
    save(label + "-intent.json", {"at": datetime.datetime.now(datetime.UTC).isoformat(), "args": args,
                                   "operation": "read-only management GET; projected metadata"})
    env = dict(os.environ, REQUESTS_CA_BUNDLE=r"C:/Users/p4032099/.azure/ca-bundle-zscaler.pem")
    result = subprocess.run([CLI, "-X", "utf8", "-IBm", "azure.cli", *args,
                             "--output", "json", "--only-show-errors"],
                            capture_output=True, encoding="utf-8", env=env, timeout=180)
    if result.returncode or not result.stdout.strip():
        # Errors only from these secret-free metadata endpoints.
        save(label + "-error.json", {"exit": result.returncode, "stderr": result.stderr[:4000],
                                     "stdout_empty": not bool(result.stdout.strip())})
        print(label, "ERROR", result.returncode)
        return None
    data = json.loads(result.stdout)
    save(label + ".json", data)
    print(label, json.dumps(data, ensure_ascii=True))
    return data


if __name__ == "__main__":
    resources = read("resources01", ["resource", "list", "--subscription", SUB, "--resource-group", RG,
        "--query", "[].{name:name,type:type,id:id,location:location}"])
    if resources is None:
        raise SystemExit(1)
    for resource in resources:
        kind, name = resource["type"].lower(), resource["name"]
        if kind == "microsoft.operationalinsights/workspaces":
            read("workspace01", ["rest", "--method", "get", "--url", BASE +
                f"Microsoft.OperationalInsights/workspaces/{name}?api-version=2023-09-01",
                "--query", "{id:id,name:name,customerId:properties.customerId,retentionInDays:properties.retentionInDays,publicNetworkAccessForQuery:properties.publicNetworkAccessForQuery}"])
        elif kind == "microsoft.web/sites" and name in ("poc-ids-token-ex-api", "poc-ids-token-ex-admin", "poc-ids-token-ex-customer"):
            read(name + "01", ["rest", "--method", "get", "--url", BASE +
                f"Microsoft.Web/sites/{name}?api-version=2023-12-01",
                "--query", "{id:id,name:name,state:properties.state,host:properties.defaultHostName,lastModifiedTimeUtc:properties.lastModifiedTimeUtc}"])
            if name.endswith("-api"):
                read("api-image01", ["rest", "--method", "get", "--url", BASE +
                    f"Microsoft.Web/sites/{name}/config/web?api-version=2023-12-01",
                    "--query", "{image:properties.linuxFxVersion}"])
        elif kind == "microsoft.insights/components":
            read("appinsights01", ["rest", "--method", "get", "--url", BASE +
                f"Microsoft.Insights/components/{name}?api-version=2020-02-02",
                "--query", "{id:id,name:name,workspaceResourceId:properties.WorkspaceResourceId,retentionInDays:properties.RetentionInDays}"])