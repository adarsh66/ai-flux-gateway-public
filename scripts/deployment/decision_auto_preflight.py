"""Decision-1 read-only gate. No inference, keys, Terraform, or configuration writes."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.deployment import runtime_rollout as rt


def main():
    folder = rt.HOME / ("decision-auto-preflight-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(exist_ok=False)
    report = {"at_utc": datetime.now(UTC).isoformat(), "inference_requests": 0,
              "cloud_writes": 0, "status": "blocked", "tls_verification": True}
    try:
        account = rt.cli(["account", "show"])
        rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
        # Record local intents structurally, never execute a historical entrypoint.
        markers = sorted(p for p in rt.HOME.rglob("*") if p.is_file()
                         and ("intent" in p.name or p.name.endswith(".lock")))
        report["retained_marker_hashes"] = {p.relative_to(rt.ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in markers}
        sites = {}
        for name in ("api", "admin", "customer", "ingestion"):
            site = rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + name)
            sites[name] = {"image": site["properties"]["siteConfig"].get("linuxFxVersion"),
                           "identity": site.get("identity"),
                           "publicNetworkAccess": site["properties"].get("publicNetworkAccess")}
        report["sites"] = sites
        apim = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + rt.RG
                   + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim?api-version=2024-05-01"])
        report["apim_identity"] = apim.get("identity")
        foundry = rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
        deployments = rt.cli(["rest", "--method", "get", "--url",
                      "https://management.azure.com" + foundry + "/deployments?api-version=2025-06-01"])
        report["decision_deployments"] = [{"name": d["name"], "model": d["properties"]["model"],
            "state": d["properties"].get("provisioningState"), "sku": d.get("sku")}
            for d in deployments["value"] if "decision" in json.dumps(d["properties"]["model"]).lower()]
        assignments = rt.cli(["role", "assignment", "list", "--scope", foundry,
                              "--include-inherited", "--all", "--subscription", rt.SUB])
        report["foundry_effective_assignment_metadata"] = [{k: r.get(k) for k in
            ("principalId", "roleDefinitionId", "roleDefinitionName", "scope", "condition")}
            for r in assignments]
        report["status"] = "readonly_metadata_collected_identity_inference_not_proven"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["http_status"] = getattr(exc, "code", None)
        # Never serialize arbitrary Azure response bodies or credential failures.
    (folder / "readiness.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": folder.relative_to(rt.ROOT).as_posix(), "status": report["status"],
                      "error_type": report.get("error_type"), "http_status": report.get("http_status")}))
    return 0 if report["status"].startswith("readonly_") else 2


if __name__ == "__main__":
    raise SystemExit(main())