"""Fresh exact-scope publisher RBAC evidence; no configuration or key writes."""
from datetime import UTC, datetime
import hashlib
import json

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.poc_controls_preflight import ACTIONS, allowed_actions, selected_publisher
from scripts.deployment.apim_route_repair import APIM

PRINCIPAL = "4e7b70ed-9868-47ba-9b61-304f1e1fdd89"
CLIENT = "f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1"
SCOPE = APIM + "/policyFragments/aiflux-dev-unified-poc-settings"


def get(path, version="2022-04-01"):
    return rt.cli(["rest", "--method", "get", "--url",
                   "https://management.azure.com" + path + "?api-version=" + version,
                   "--subscription", rt.SUB])


def main():
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    site = rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api")
    from scripts.deployment.finops_function_stage import current_settings
    settings = current_settings()["api"]
    rt.require(settings.get("AZURE_CLIENT_ID") == CLIENT, "selected_client_mismatch")
    rt.require(selected_publisher(site["identity"], CLIENT) == PRINCIPAL, "selected_principal_mismatch")
    assignments = rt.cli(["role", "assignment", "list", "--assignee-object-id", PRINCIPAL,
                          "--scope", SCOPE, "--include-inherited", "--include-groups",
                          "--subscription", rt.SUB])
    grants = []
    for assignment in assignments:
        scope = assignment["scope"].lower().rstrip("/")
        rt.require(SCOPE.lower() == scope or SCOPE.lower().startswith(scope + "/"), "nonapplicable_scope")
        definition = get(assignment["roleDefinitionId"])
        properties = definition["properties"]
        grants.append({"assignment_id": assignment["id"], "principal_id": assignment["principalId"],
                       "scope": assignment["scope"], "condition": assignment.get("condition"),
                       "condition_version": assignment.get("conditionVersion"),
                       "role_definition_id": definition["id"], "role_name": properties["roleName"],
                       "permissions": properties["permissions"]})
    eligible = [p for g in grants if not g["condition"] for p in g["permissions"]]
    coverage = allowed_actions(eligible)
    fragment = rt.cli([
        "rest", "--method", "get", "--url", "https://management.azure.com" + SCOPE +
        "?api-version=2024-05-01&format=rawxml", "--subscription", rt.SUB])
    # Deny assignments are reported separately: role coverage alone is not runtime proof.
    denies = {}
    for scope in ("/subscriptions/" + rt.SUB, rt.RG, APIM, SCOPE):
        try:
            data = get(scope + "/providers/Microsoft.Authorization/denyAssignments")
            denies[scope] = {"observable": True, "count": len(data.get("value", [])),
                             "next_link": bool(data.get("nextLink"))}
        except RuntimeError as error:
            denies[scope] = {"observable": False, "error": str(error)}
    proof = {"at_utc": datetime.now(UTC).isoformat(), "selected_principal": PRINCIPAL,
             "selected_client": CLIENT, "scope": SCOPE, "required_actions": ACTIONS,
             "grants": grants, "unconditional_action_coverage": coverage,
             "publisher_permission_metadata_verified": all(coverage.values()),
             "deny_assignment_observation": denies,
             "fragment": {"id": fragment["id"],
                          "provisioning_state": fragment["properties"].get("provisioningState"),
                          "value_sha256": hashlib.sha256(fragment["properties"]["value"].encode()).hexdigest()},
             "api_control_flags": {key: settings.get(key) for key in (
                 "AIFLUX_GATEWAY_CONTROLS_POC_ENABLED", "AIFLUX_GATEWAY_CONTROLS_V2_ENABLED",
                 "AIFLUX_GATEWAY_SETTINGS_SCOPES")},
             "cloud_configuration_writes": 0, "inference_requests": 0,
             "runtime_mi_write_proven": False}
    path = rt.ROOT / ("gateway/validation/poc-activation-permissions-" +
                      datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    rt.require(not path.exists(), "evidence_exists")
    rt.save(path, proof)
    print(json.dumps({"evidence": path.relative_to(rt.ROOT).as_posix(), **proof}), flush=True)


if __name__ == "__main__":
    main()