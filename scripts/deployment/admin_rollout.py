"""Approved admin-only release; no settings, secrets, roles or other site writes."""
from __future__ import annotations

import argparse
import json

from scripts.deployment import admin_ingress as ingress
from scripts.deployment import deploy_portals as portals
from scripts.deployment import run_private_sql as runner

DIGEST = "sha256:dd71e8fa9d75bc3b5f4bd4f8393ad1de09cac1fdbfab3564be6c1438a4243c60"
TAG = "sql-poc-20261023-admin-proxy-r1"
IMAGE = "DOCKER|" + runner.REGISTRY_HOST + "/aiflux-admin@" + DIGEST
BASELINE = runner.HOME / "admin-ingress-baseline-20261023.json"


def snapshot(arm: runner.Arm) -> dict:
    """Only public configuration. Never request app settings or credentials."""
    result = {}
    for kind in portals.CLIENTS:
        app = arm.get(portals.site(kind), portals.WEB)
        config = arm.get(portals.site(kind) + "/config/web", portals.WEB)["properties"]
        result[kind] = {"image": config.get("linuxFxVersion"),
            "public": app["properties"].get("publicNetworkAccess"),
            "integration": app["properties"].get("virtualNetworkSubnetId"),
            "identity": app.get("identity"),
            "acr_mi": config.get("acrUseManagedIdentityCreds"),
            "acr_client": config.get("acrUserManagedIdentityID"),
            **{key: config.get(key) for key in ingress.restriction_properties([])}}
    result["sql_public"] = arm.get(runner.SQL, "2023-08-01")["properties"].get("publicNetworkAccess")
    return result


def validate(arm: runner.Arm, redactor: runner.Redactor) -> dict:
    account = runner.cli(["account", "show"], redactor)
    portals.require(account["id"] == runner.SUB and account["tenantId"] == runner.TENANT and
                    account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_mismatch")
    for kind in portals.CLIENTS:
        app = arm.get(portals.site(kind), portals.WEB)
        config = arm.get(portals.site(kind) + "/config/web", portals.WEB)["properties"]
        portals.network_proof(arm, kind, app, config)
        portals.require(app["properties"].get("httpsOnly") is True, "https_only_required")
        if kind == "admin":
            portals.require(config.get("linuxFxVersion") in
                            ("DOCKER|" + portals.image("admin"), IMAGE), "admin_image_conflict")
            portals.require(config.get("acrUseManagedIdentityCreds") is True and
                            config.get("acrUserManagedIdentityID") == portals.CLIENTS[kind], "admin_pull_mismatch")
            portals.require(app["properties"].get("virtualNetworkSubnetId") in
                            (None, "", portals.INTEGRATION), "admin_integration_conflict")
            identities = app.get("identity", {}).get("userAssignedIdentities", {})
            selected = [v for v in identities.values() if v.get("clientId") == portals.CLIENTS[kind]]
            portals.require(len(selected) == 1, "admin_identity_mismatch")
            roles = runner.cli(["role", "assignment", "list", "--assignee-object-id", selected[0]["principalId"],
                "--scope", runner.RG + "/providers/Microsoft.ContainerRegistry/registries/" + runner.REGISTRY,
                "--include-inherited"], redactor)
            portals.require(any(x.get("roleDefinitionId", "").lower().endswith(
                "/7f951dda-4ed3-4680-a7ca-43fe172d538d") and not x.get("condition") for x in roles), "acrpull_missing")
    portals.require(arm.get(runner.SQL, "2023-08-01")["properties"].get("publicNetworkAccess") == "Disabled",
                    "sql_public_exposed")
    subnet = arm.get(portals.INTEGRATION)["properties"]
    portals.require(subnet.get("provisioningState") == "Succeeded" and
                    subnet.get("addressPrefixes", [subnet.get("addressPrefix")]) == ["10.240.4.0/24"] and
                    any(d["properties"].get("serviceName") == "Microsoft.Web/serverFarms"
                        for d in subnet.get("delegations", [])), "integration_subnet_invalid")
    meta = runner.cli(["acr", "repository", "show", "--name", runner.REGISTRY,
                       "--image", "aiflux-admin:" + TAG], redactor)
    portals.require(meta["digest"] == DIGEST and meta["changeableAttributes"]["writeEnabled"] is False and
                    meta["changeableAttributes"]["deleteEnabled"] is False, "candidate_not_locked")
    run = runner.cli(["acr", "task", "show-run", "--registry", runner.REGISTRY, "--run-id", "cmd"], redactor)
    portals.require(run.get("status") == "Succeeded", "candidate_build_not_succeeded")
    return {"status": "validated", "candidate": IMAGE, "tag_locked": True, "acrpull": True,
            "existing_subnet": portals.INTEGRATION, "sql_public": "Disabled"}


def preserve_others(arm: runner.Arm, baseline: dict) -> None:
    current = snapshot(arm)
    for key in ("api", "customer", "sql_public"):
        portals.require(current[key] == baseline[key], "out_of_scope_state_changed")


def prepare(arm: runner.Arm, redactor: runner.Redactor) -> dict:
    validate(arm, redactor)
    runner.protect_directory(runner.HOME)
    if not BASELINE.exists():
        # Never overwrite the original release/config rollback evidence.
        BASELINE.write_text(json.dumps(snapshot(arm), indent=2), encoding="utf-8")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    try:
        ingress.set_public(arm, portals.site("admin"), "Disabled")
        arm.request("PATCH", portals.site("admin") + "/config/web", portals.WEB,
                    {"properties": ingress.restriction_properties([])})
        ingress.verify_rules(arm.get(portals.site("admin") + "/config/web", portals.WEB)["properties"], [])
        # Existing delegated subnet only; never rewrite the VNet or subnet.
        arm.request("PATCH", portals.site("admin"), portals.WEB,
                    {"properties": {"virtualNetworkSubnetId": portals.INTEGRATION}})
        app = arm.get(portals.site("admin"), portals.WEB)["properties"]
        portals.require(app.get("virtualNetworkSubnetId", "").lower() == portals.INTEGRATION.lower() and
                        app.get("publicNetworkAccess") == "Disabled", "admin_integration_not_confirmed")
        preserve_others(arm, baseline)
    except BaseException:
        ingress.set_public(arm, portals.site("admin"), "Disabled")
        raise
    return {"status": "prepared_private", "integration": portals.INTEGRATION, "scm": "independent_deny_all"}


def deploy(arm: runner.Arm, redactor: runner.Redactor) -> dict:
    plan = (portals.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    state = json.loads((portals.ROOT / ".azure/validate-status.json").read_text(encoding="utf-8"))
    portals.require("Admin ingress status: Validated" in plan and state.get("completedStep") == "UpdateStatus",
                    "admin_validation_incomplete")
    validate(arm, redactor)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    app = arm.get(portals.site("admin"), portals.WEB)["properties"]
    portals.require(app.get("virtualNetworkSubnetId") == portals.INTEGRATION, "admin_integration_required")
    ingress.verify_rules(arm.get(portals.site("admin") + "/config/web", portals.WEB)["properties"], [])
    try:
        arm.request("PATCH", portals.site("admin") + "/config/web", portals.WEB, {"properties": {
            "linuxFxVersion": IMAGE, "acrUseManagedIdentityCreds": True,
            "acrUserManagedIdentityID": portals.CLIENTS["admin"], "alwaysOn": True, "healthCheckPath": "/healthz"}})
        arm.request("POST", portals.site("admin") + "/restart", portals.WEB)
        result = validate(arm, redactor)
        portals.require(arm.get(portals.site("admin") + "/config/web", portals.WEB)["properties"].get(
                        "linuxFxVersion") == IMAGE, "candidate_readback_failed")
        preserve_others(arm, baseline)
        return {**result, "status": "deployed_private_pending_smoke"}
    except BaseException:
        ingress.set_public(arm, portals.site("admin"), "Disabled")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "prepare", "deploy", "snapshot"))
    args = parser.parse_args()
    redactor = runner.Redactor()
    try:
        arm = runner.Arm(redactor)
        result = snapshot(arm) if args.action == "snapshot" else globals()[args.action](arm, redactor)
        print(json.dumps(result))
        return 0
    except runner.RunnerError as exc:
        print(json.dumps({"status": "failed", "code": exc.code,
                          "http_status": exc.details.get("http_status"), "azure_code": exc.details.get("azure_code")}))
    except Exception as exc:
        print(json.dumps({"status": "failed", "exception_type": type(exc).__name__}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())