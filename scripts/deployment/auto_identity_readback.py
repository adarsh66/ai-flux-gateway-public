"""Metadata-only Auto permission/audience audit. Never infer, grant or impersonate."""
from datetime import UTC, datetime
import json
from uuid import UUID

from scripts.deployment import runtime_rollout as rt

FOUNDRY = rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
PRINCIPALS = {"operator": rt.OPERATOR, "gateway": "bcf69911-f34e-4f33-acd8-a36f164db811",
              "api": "4e7b70ed-9868-47ba-9b61-304f1e1fdd89"}


def get(url):
    return rt.cli(["rest", "--method", "get", "--url", url])


def collection(url):
    items = []
    for _ in range(40):
        rt.require(url.startswith(("https://management.azure.com/", "https://graph.microsoft.com/")), "unexpected_pagination_host")
        data = get(url)
        items.extend(data["value"])
        url = data.get("nextLink") or data.get("@odata.nextLink")
        if not url:
            return items
    raise RuntimeError("pagination_limit")


def inference_permissions(definition):
    # Metadata patterns only, NOT a runtime authorization decision.
    return [{k: p.get(k, []) for k in ("actions", "notActions", "dataActions", "notDataActions")}
            for p in definition["properties"]["permissions"]]


def main():
    folder = rt.HOME / ("auto-identity-readback-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(exist_ok=False)
    report = {"at_utc": datetime.now(UTC).isoformat(), "cloud_writes": 0, "inference_requests": 0,
              "runtime_mi_access_proven": False, "tls_verification": True, "errors": {}}
    def attempt(label, call):
        try:
            return call()
        except Exception as exc:
            report["errors"][label] = {"type": type(exc).__name__, "status": getattr(exc, "code", None)}
            return None
    rt.require(rt.ENV.get("AZURE_CLI_DISABLE_CONNECTION_VERIFICATION", "").lower() not in {"1", "true", "yes"}, "tls_disabled")
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    report["subscription"], report["tenant"] = rt.SUB, rt.TENANT
    site = attempt("api_site", lambda: rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api"))
    report["api_identity"] = site.get("identity") if site else None
    web = attempt("api_web", lambda: rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/config/web"))
    report["api_image"] = web["properties"].get("linuxFxVersion") if web else None
    apim = attempt("apim", lambda: get("https://management.azure.com" + rt.RG
        + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim?api-version=2024-05-01"))
    report["gateway_identity"] = apim.get("identity") if apim else None
    # CLI projection emits only these known nonsecret identity/feature settings.
    names = ("AIFLUX_ENTRA_AUDIENCE", "AIFLUX_ENTRA_CLIENT_ID", "AIFLUX_HOME_TENANT_ID", "AZURE_CLIENT_ID",
             "AIFLUX_AUTO_ROUTING_ENABLED", "AIFLUX_AUTO_ROUTING_GATEWAY_READY", "AIFLUX_AUTO_ROUTING_CONTRACT_VERIFIED")
    query = "[?" + " || ".join("name=='" + n + "'" for n in names) + "].{name:name,value:value}"
    report["api_safe_identity_settings"] = attempt("safe_settings", lambda: rt.cli([
        "webapp", "config", "appsettings", "list", "--name", "poc-ids-token-ex-api",
        "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--subscription", rt.SUB, "--query", query]))
    auth = attempt("authsettings", lambda: rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/config/authsettingsV2"))
    azure = (auth or {}).get("properties", {}).get("identityProviders", {}).get("azureActiveDirectory", {})
    report["easy_auth_entra"] = {"enabled": azure.get("enabled"),
        "client_id": azure.get("registration", {}).get("clientId"),
        "issuer": azure.get("registration", {}).get("openIdIssuer"),
        "allowed_audiences": azure.get("validation", {}).get("allowedAudiences")}
    deployment = attempt("decision_deployment", lambda: get("https://management.azure.com" + FOUNDRY
        + "/deployments/Decision-1?api-version=2025-06-01"))
    report["decision_deployment"] = ({"id": deployment["id"], "model": deployment["properties"].get("model"),
        "sku": deployment.get("sku"), "state": deployment["properties"].get("provisioningState"),
        "capabilities": deployment["properties"].get("capabilities")} if deployment else None)
    raw_assignments = attempt("assignments", lambda: collection("https://management.azure.com" + FOUNDRY
        + "/deployments/Decision-1/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01&$filter=atScope()"))
    assignments = [{"id": r["id"], **r["properties"]} for r in raw_assignments] if raw_assignments is not None else None
    definitions = {}
    for role in sorted({r["roleDefinitionId"] for r in assignments or []}):
        definition = attempt("definition:" + role, lambda role=role: get(
            "https://management.azure.com" + role + "?api-version=2022-04-01"))
        if definition:
            definitions[role] = {"name": definition["properties"]["roleName"],
                "type": definition["properties"]["type"], "permissions": inference_permissions(definition)}
    report["definitions"] = definitions
    report["principals"] = {}
    for label, oid in PRINCIPALS.items():
        kind = "users" if label == "operator" else "servicePrincipals"
        groups = attempt(label + ":groups", lambda kind=kind, oid=oid: collection(
            f"https://graph.microsoft.com/v1.0/{kind}/{oid}/transitiveMemberOf/microsoft.graph.group?$select=id"))
        ids = {oid} | {g["id"] for g in groups or []}
        matching = [{k: r.get(k) for k in ("id", "principalId", "principalType", "roleDefinitionId", "scope", "condition", "conditionVersion")}
                    for r in assignments or [] if r["principalId"] in ids]
        report["principals"][label] = {"oid": oid, "group_coverage": "read" if groups is not None else "unknown_not_readable",
            "assignments_coverage": "decision_deployment_account_and_inherited" if assignments is not None else "unknown_not_readable",
            "group_ids": sorted(ids - {oid}), "assignments": matching,
            "observed_cognitive_wildcard_data_action": None if assignments is None else any(
                any(a.lower() in {"microsoft.cognitiveservices/*", "*"} for a in p["dataActions"])
                for r in matching if not r["condition"]
                for p in definitions.get(r["roleDefinitionId"], {}).get("permissions", []))}
    report["deny_assignments"] = {}
    for scope in ("/subscriptions/" + rt.SUB, rt.RG, FOUNDRY, FOUNDRY + "/deployments/Decision-1"):
        denies = attempt("deny:" + scope, lambda scope=scope: collection("https://management.azure.com" + scope
            + "/providers/Microsoft.Authorization/denyAssignments?api-version=2022-04-01&$filter=atScope()"))
        report["deny_assignments"][scope] = [{"id": d["id"], "properties": {k: d["properties"].get(k)
            for k in ("scope", "permissions", "principals", "excludePrincipals", "doNotApplyToChildScopes")}}
            for d in denies] if denies is not None else None
    settings = {s["name"]: s["value"] for s in report["api_safe_identity_settings"] or []}
    client_id = settings.get("AIFLUX_ENTRA_CLIENT_ID") or report["easy_auth_entra"]["client_id"]
    try:
        UUID(client_id or "")
    except ValueError:
        report["existing_entra_application"] = "no_uuid_client_id_observed_not_proof_of_absence"
    else:
        report["existing_entra_application"] = attempt("entra_application", lambda: collection(
            "https://graph.microsoft.com/v1.0/applications?$filter=appId eq '" + client_id
            + "'&$select=id,appId,identifierUris,api"))
    report["status"] = "readonly_metadata_collected_runtime_paths_unproven"
    rt.save(folder / "readback.json", report)
    print(json.dumps({"evidence": folder.relative_to(rt.ROOT).as_posix(), "status": report["status"],
        "errors": report["errors"], "principals": report["principals"], "api_safe_identity_settings": report["api_safe_identity_settings"],
        "easy_auth_entra": report["easy_auth_entra"], "decision_deployment": report["decision_deployment"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())