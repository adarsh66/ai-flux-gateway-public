"""Continue only unconsumed metadata reads; preserve original exclusive receipts."""
import json
from read_metadata import BASE, HERE, read

resources = json.loads((HERE / "resources01.json").read_text())
for resource in resources:
    kind, name = resource["type"].lower(), resource["name"]
    if kind == "microsoft.operationalinsights/workspaces" and name == "poc-ids-token-ex-logs":
        read("gateway-workspace02", ["rest", "--method", "get", "--url", BASE +
            f"Microsoft.OperationalInsights/workspaces/{name}?api-version=2023-09-01",
            "--query", "{id:id,name:name,customerId:properties.customerId,retentionInDays:properties.retentionInDays,publicNetworkAccessForQuery:properties.publicNetworkAccessForQuery}"])
    elif kind == "microsoft.web/sites" and name in ("poc-ids-token-ex-api", "poc-ids-token-ex-admin", "poc-ids-token-ex-customer"):
        read(name + "02", ["rest", "--method", "get", "--url", BASE +
            f"Microsoft.Web/sites/{name}?api-version=2023-12-01",
            "--query", "{id:id,name:name,state:properties.state,host:properties.defaultHostName,lastModifiedTimeUtc:properties.lastModifiedTimeUtc}"])
        if name.endswith("-api"):
            read("api-image02", ["rest", "--method", "get", "--url", BASE +
                f"Microsoft.Web/sites/{name}/config/web?api-version=2023-12-01",
                "--query", "{image:properties.linuxFxVersion}"])
    elif kind == "microsoft.insights/components" and name == "poc-ids-token-ex-insights":
        read("gateway-appinsights02", ["rest", "--method", "get", "--url", BASE +
            f"Microsoft.Insights/components/{name}?api-version=2020-02-02",
            "--query", "{id:id,name:name,workspaceResourceId:properties.WorkspaceResourceId,retentionInDays:properties.RetentionInDays}"])