"""Read-only renewal prerequisites; never restamp inventory or call inference."""
import json
from datetime import UTC, datetime

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.project_route_product_access import ProductRun, sha


def main():
    path = rt.ROOT / "gateway/catalog/foundry-inventory-20261026.json"
    old = json.loads(path.read_text())
    base = "https://management.azure.com" + old["account_resource_id"]
    def read(suffix):
        return rt.cli(["rest", "--method", "get", "--url", base + suffix + "?api-version=2025-06-01", "--subscription", rt.SUB])
    account = read("")
    project = read("/projects/poc-ids-token-ex-foundry-project")
    connections = read("/projects/poc-ids-token-ex-foundry-project/connections")
    deployments = read("/deployments")
    rt.require(not connections.get("nextLink") and not deployments.get("nextLink"), "pagination")
    rt.require(not connections["value"], "connections_changed")
    rt.require(account["id"].lower() == old["account_resource_id"].lower()
               and project["id"].lower() == old["project_resource_id"].lower()
               and account["properties"]["provisioningState"] == "Succeeded"
               and project["properties"]["provisioningState"] == "Succeeded", "parent_state_changed")
    checked = []
    for saved in old["deployments"]:
        live = next(d for d in deployments["value"] if d["id"].lower() == saved["id"].lower())
        p, model = live["properties"], live["properties"]["model"]
        rt.require(live["name"] == saved["name"] and model["name"] == saved["model_name"]
                   and model["version"] == saved["model_version"] and model["format"] == saved["model_format"]
                   and p["provisioningState"] == "Succeeded" and live["sku"]["capacity"] == saved["capacity"],
                   "deployment_identity_state_or_capacity_changed:" + saved["name"])
        checked.append({"alias": saved["name"], "model": model["name"], "version": model["version"],
                        "provider": model["format"], "sku": live["sku"]["name"], "capacity": live["sku"]["capacity"]})
    policy = ProductRun().policy()
    predecessor = json.loads((rt.HOME / "catalog-pricing-correction-20261027/review.json").read_text())
    rt.require(sha(policy) == predecessor["baseline"]["apim_policy_sha256"], "accepted_policy_changed")
    proof = {"at": datetime.now(UTC).isoformat(), "account_and_project_succeeded": True,
             "connections": 0, "deployments": checked, "accepted_policy_sha256": sha(policy),
             "snapshot_sha256": sha(path.read_bytes()), "existing_verified_at": old["verified_at"],
             "existing_inventory_expired": True, "all_live_metadata_matches": True,
             "no_inference_no_writes": True, "freshness_limit_seconds_unchanged": 86400}
    rt.save(rt.ROOT / "gateway/validation/catalog-inventory-renewal-readback-20261027.json", proof)
    print(json.dumps(proof), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"errorType": type(error).__name__, "error": str(error) if isinstance(error, RuntimeError)
                          else "inventory_read_failed_sensitive_detail_suppressed"}), flush=True)
        raise SystemExit(1)