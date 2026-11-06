"""Read-only baseline for the approved eight-model addition. No write operation."""
from datetime import UTC, datetime
import hashlib
import json

from scripts.deployment import runtime_rollout as rt

ALIASES = frozenset({"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5-fast",
    "claude-haiku-5-5", "gpt-6.1-terra", "gpt-6-luna", "claude-opus-4-8", "Mistral-Large-3"})


def get(path):
    rt.require(path.startswith(rt.RG + "/providers/"), "read_scope")
    return rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + path])


def main():
    folder = rt.HOME / "foundry-eight-20261030"
    rt.require(not folder.exists(), "existing_preflight_reconcile_only")
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    folder.mkdir()
    def save(name, value):
        with (folder / name).open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
    save("read-intent.json", {"at": datetime.now(UTC).isoformat(), "writes": 0, "inference": 0})
    foundry = rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
    data = get(foundry + "/deployments?api-version=2025-06-01")
    rt.require(not data.get("nextLink"), "pagination_requires_explicit_continuation")
    save("deployments.json", data)
    selected = {d["name"]: d for d in data["value"] if d["name"] in ALIASES}
    rt.require(set(selected) == ALIASES, "exact_requested_deployments")
    for alias, deployment in selected.items():
        p = deployment["properties"]
        rt.require(p["provisioningState"] == "Succeeded" and deployment["sku"]["capacity"] > 0,
                   "deployment_not_ready:" + alias)
    save("requested.json", selected)
    apim = rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"
    for name, suffix in {
        "policy": "/apis/aiflux-dev-unified/policies/policy?format=rawxml&api-version=2024-05-01",
        "backends": "/backends?api-version=2024-05-01",
        "api": "/apis/aiflux-dev-unified?api-version=2024-05-01",
        "global": "/policies/policy?format=rawxml&api-version=2024-05-01",
    }.items():
        value = get(apim + suffix)
        rt.require(not value.get("nextLink"), "apim_pagination:" + name)
        save(name + ".json", value)
    sites = {}
    for kind in ("api", "admin", "customer", "ingestion"):
        name = "poc-ids-token-ex-" + kind
        if kind == "ingestion":
            name = "poc-ids-token-ex-ingestion"
        path = rt.RG + "/providers/Microsoft.Web/sites/" + name
        site = get(path + "?api-version=2024-04-01")
        web = get(path + "/config/web?api-version=2024-04-01")
        sites[kind] = {"image": web["properties"]["linuxFxVersion"], "identity": site.get("identity"),
                       "publicNetworkAccess": site["properties"].get("publicNetworkAccess")}
    save("sites.json", sites)
    save("read-complete.json", {"at": datetime.now(UTC).isoformat(), "writes": 0,
         "inference": 0, "deployments": len(data["value"]), "requested": sorted(selected),
         "hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.json")}})
    print(json.dumps({"complete": True, "requested": {k: {"model": v["properties"]["model"],
          "sku": v["sku"], "capabilities": v["properties"].get("capabilities")} for k, v in selected.items()},
          "sites": sites}), flush=True)


if __name__ == "__main__":
    main()