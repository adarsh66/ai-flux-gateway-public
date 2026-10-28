"""Read-only POC controls preflight. Never reads keys or emits settings values."""
from datetime import UTC, datetime
import fnmatch
import json

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.project_route_product_access import ProductRun, sha

FRAGMENT_NAME = "aiflux-dev-unified-poc-settings"
ACTIONS = ["Microsoft.ApiManagement/service/policyFragments/" + a for a in ("read", "write")]


def selected_publisher(identity, client_id):
    """DefaultAzureCredential selects AZURE_CLIENT_ID or the system identity."""
    if client_id:
        matches = [v for v in identity.get("userAssignedIdentities", {}).values()
                   if v.get("clientId") == client_id]
        rt.require(len(matches) == 1, "selected_publisher_identity_not_attached")
        return matches[0]["principalId"]
    rt.require(bool(identity.get("principalId")), "system_publisher_identity_unavailable")
    return identity["principalId"]


def allowed_actions(grants):
    return {action: any(
        any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("actions", []))
        and not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("notActions", []))
        for g in grants) for action in ACTIONS}


def collect():
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    run = ProductRun()
    protected = run.protected()
    site = rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api")
    identity = site["identity"]
    from scripts.deployment.finops_function_stage import current_settings
    # Complete app settings stay in process; never print/store secret values.
    settings = current_settings()["api"]
    principal = selected_publisher(identity, settings.get("AZURE_CLIENT_ID"))
    permissions = []
    target = run.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]
    from scripts.deployment.apim_route_repair import APIM
    fragment_scope = APIM + "/policyFragments/" + FRAGMENT_NAME
    for principal in [principal]:
        assignments = rt.cli(["role", "assignment", "list", "--assignee-object-id", principal,
                      "--scope", fragment_scope, "--include-inherited"])
        grants = []
        for assignment in assignments:
            if assignment.get("condition"):
                continue  # Conditional grants are not proof of unconditional access.
            role = rt.cli(["role", "definition", "list", "--name", assignment["roleDefinitionId"]])
            for definition in role:
                for permission in definition["permissions"]:
                    grants.append(permission)
        permissions.append({"principal_id": principal, "fragment_actions": allowed_actions(grants),
                            "assignment_metadata": [{k: a.get(k) for k in
                                ("id", "roleDefinitionId", "scope", "condition")} for a in assignments]})
    account_id = rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
    deployments = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" +
                          account_id + "/deployments?api-version=2025-06-01"])
    bindings = [{"deployment": d["name"], "raiPolicyName": d["properties"].get("raiPolicyName"),
                 "model": d["properties"].get("model"), "sku": d.get("sku")}
                for d in deployments["value"]]
    policies = {}
    for name in sorted({d["raiPolicyName"] for d in bindings if d["raiPolicyName"]}):
        try:
            value = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" +
                            account_id + "/raiPolicies/" + name + "?api-version=2025-06-01"])
            policies[name] = {"name": value["name"], "properties": value.get("properties")}
        except RuntimeError:
            policies[name] = {"name": name, "policy_definition_read": "unavailable",
                              "deployment_binding_read": "verified", "mutated": False}
    report = {"at_utc": datetime.now(UTC).isoformat(), "cloud_writes": 0,
              "protected": protected, "policy_sha256": sha(target),
              "publisher_permissions": permissions, "foundry_bindings": bindings,
              "foundry_policies": policies, "inference_tests": "SKIPPED_USER_REQUEST"}
    report["publisher_fragment_permission_verified"] = any(
        all(p["fragment_actions"].values()) for p in permissions)
    report["selected_publisher_principal_id"] = principal
    report["required_fragment_scope"] = fragment_scope
    report["required_actions"] = ACTIONS
    report["api_control_flags"] = {key: settings.get(key) for key in (
        "AIFLUX_GATEWAY_CONTROLS_POC_ENABLED", "AIFLUX_GATEWAY_CONTROLS_V2_ENABLED",
        "AIFLUX_GATEWAY_SETTINGS_SCOPES")}
    prior = rt.ROOT / "gateway/validation/poc-controls-preflight-20261027.json"
    if prior.exists():
        previous = json.loads(prior.read_text())
        report["protected_baseline_equal_previous_preflight"] = protected == previous["protected"]
        report["policy_equal_previous_preflight"] = sha(target) == previous["policy_sha256"]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = rt.ROOT / f"gateway/validation/poc-controls-preflight-{stamp}.json"
    rt.require(not path.exists(), "preflight_evidence_already_exists")
    rt.save(path, report)
    print(json.dumps({"evidence": path.relative_to(rt.ROOT).as_posix(), **{
        k: v for k, v in report.items() if k not in ("protected", "foundry_bindings", "foundry_policies")}}), flush=True)
    return report


if __name__ == "__main__":
    collect()