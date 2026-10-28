"""Fixed-scope existing-site deployment; secrets travel only in verified ARM bodies.

No Terraform, role grants, public-access changes, SQL writes or SCM access.
The approved admin private endpoint is the only persistent resource addition.
Uses the reviewed runner's authenticated ARM client and ownership-safe cleanup.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import logging
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from scripts.deployment import run_private_sql as runner

ROOT = runner.ROOT
WEB = "2023-12-01"
DNS = "2020-06-01"
ZONE = runner.RG + "/providers/Microsoft.Network/privateDnsZones/privatelink.azurewebsites.net"
PE_SUBNET = runner.VNET + "/subnets/" + runner.PREFIX + "-private-endpoints"
INTEGRATION = runner.VNET + "/subnets/" + runner.PREFIX + "-app-service-integration"
CLIENTS = {"api": "f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1",
           "customer": "229200b4-fe7a-4aec-a215-57516d4a5145",
           "admin": "3143ef2e-4a97-40cf-9a8c-2880d697f64b"}
TAGS = {"api": "sql-poc-20261022-r1", "customer": "sql-poc-20261022-private-r2",
        "admin": "sql-poc-20261022-r1"}
DIGESTS = {"api": "sha256:5e7e41ad72185b6ce28494fcf78a79e1071466bb2d200fa124c5703331e65532",
           "customer": "sha256:c8dffdbd29ab1a6388d04e6446a4c72cd0df8a0c37db43ba322360b829d864ba",
           "admin": "sha256:82e2cd7b36d6da18288c939b02532f361a6ac414661e8e8ae10b995c26ed9be3"}
GATEWAY = "https://poc-ids-token-ex-apim.azure-api.net"
AUTH_FILES = ("app.py", "config.py", "portal_auth.py", "db.py")


def require(condition: object, code: str) -> None:
    if not condition:
        raise runner.RunnerError(code)


def site(kind: str) -> str:
    return runner.RG + "/providers/Microsoft.Web/sites/" + runner.PREFIX + "-" + kind


def image(kind: str) -> str:
    return runner.REGISTRY_HOST + "/aiflux-" + kind + "@" + DIGESTS[kind]


def save(name: str, value: dict) -> None:
    runner.protect_directory(runner.HOME)
    (runner.HOME / ("portals-" + name + ".json")).write_text(
        json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), **value}, indent=2),
        encoding="utf-8")


def read_settings(arm: runner.Arm, kind: str) -> dict:
    return arm.request("POST", site(kind) + "/config/appsettings/list", WEB).json()["properties"]


def network_proof(arm: runner.Arm, kind: str, app: dict, config: dict) -> dict:
    """No blanket private-route waiver: exact target, subnet, zone and A record."""
    p = app["properties"]
    require(config.get("scmIpSecurityRestrictionsDefaultAction") == "Deny", "scm_not_denied")
    require(not any(r.get("action") == "Allow" for r in config.get("scmIpSecurityRestrictions", [])),
            "scm_allow_rule")
    if kind == "customer":
        require(p.get("publicNetworkAccess") == "Enabled" and
                config.get("ipSecurityRestrictionsDefaultAction") == "Allow" and
                config.get("scmIpSecurityRestrictionsUseMain") is False, "customer_ingress_mismatch")
        require(p.get("virtualNetworkSubnetId", "").lower() == INTEGRATION.lower(),
                "customer_integration_mismatch")
        return {"public": "Enabled", "integration_verified": True, "scm": "Deny"}
    require(p.get("publicNetworkAccess") == "Disabled" and
            config.get("ipSecurityRestrictionsDefaultAction") == "Deny", "private_site_exposed")
    require(not any(r.get("action") == "Allow" for r in config.get("ipSecurityRestrictions", [])),
            "private_site_allow_rule")
    endpoint = runner.RG + "/providers/Microsoft.Network/privateEndpoints/" + runner.PREFIX + "-" + kind + "-pe"
    pe = arm.get(endpoint)
    require(pe and pe["properties"].get("provisioningState") == "Succeeded", "private_endpoint_missing")
    props = pe["properties"]
    require(props.get("subnet", {}).get("id", "").lower() == PE_SUBNET.lower(), "pe_subnet_mismatch")
    connections = props.get("privateLinkServiceConnections", [])
    require(len(connections) == 1, "pe_connection_ambiguous")
    conn = connections[0]["properties"]
    require(conn.get("privateLinkServiceId", "").lower() == site(kind).lower() and
            conn.get("groupIds") == ["sites"] and
            conn.get("privateLinkServiceConnectionState", {}).get("status") == "Approved", "pe_target_mismatch")
    groups = arm.get(endpoint + "/privateDnsZoneGroups", runner.NET_API)["value"]
    require(any(c["properties"].get("privateDnsZoneId", "").lower() == ZONE.lower()
                for g in groups for c in g["properties"].get("privateDnsZoneConfigs", [])), "pe_dns_group_missing")
    links = arm.get(ZONE + "/virtualNetworkLinks", DNS)["value"]
    require(any(l["properties"].get("virtualNetwork", {}).get("id", "").lower() == runner.VNET.lower()
                and l["properties"].get("provisioningState") == "Succeeded" for l in links), "dns_link_missing")
    record = arm.get(ZONE + "/A/" + runner.PREFIX + "-" + kind, DNS)
    addresses = [x["ipv4Address"] for x in (record or {}).get("properties", {}).get("aRecords", [])]
    require(addresses and all(ipaddress.ip_address(x) in ipaddress.ip_network("10.240.3.0/24")
                              for x in addresses), "private_dns_record_mismatch")
    if kind == "api":
        require(p.get("virtualNetworkSubnetId", "").lower() == INTEGRATION.lower(), "api_integration_mismatch")
    return {"public": "Disabled", "endpoint": endpoint, "addresses": addresses,
            "approved_sites_target": True, "dns_zone_group_and_vnet_link": True, "scm": "Deny"}


def snapshot(arm: runner.Arm) -> dict:
    result = {}
    for kind in CLIENTS:
        app = arm.get(site(kind), WEB)
        config = arm.get(site(kind) + "/config/web", WEB)["properties"]
        result[kind] = {"image": config.get("linuxFxVersion"),
                        "acr_mi": config.get("acrUseManagedIdentityCreds"),
                        "acr_client": config.get("acrUserManagedIdentityID"),
                        "public": app["properties"].get("publicNetworkAccess"),
                        "setting_names": sorted(read_settings(arm, kind)),
                        "site_default": config.get("ipSecurityRestrictionsDefaultAction"),
                        "scm_default": config.get("scmIpSecurityRestrictionsDefaultAction")}
    return result


def prepare(arm: runner.Arm, redactor: runner.Redactor) -> dict:
    baseline = runner.HOME / "portals-baseline.json"
    if not baseline.exists():
        save("baseline", {"apps": snapshot(arm)})
    # Network-only preparation already explicitly approved; never changes public ingress.
    endpoint = runner.RG + "/providers/Microsoft.Network/privateEndpoints/" + runner.PREFIX + "-admin-pe"
    pe = arm.get(endpoint)
    if pe is None:
        arm.operation("PUT", endpoint, body={"location": runner.LOCATION,
            "tags": {"purpose": "approved-private-admin-ingress"}, "properties": {
                "subnet": {"id": PE_SUBNET}, "privateLinkServiceConnections": [{
                    "name": runner.PREFIX + "-admin-private", "properties": {
                        "privateLinkServiceId": site("admin"), "groupIds": ["sites"]}}]}})
    else:
        require(pe["properties"]["subnet"]["id"].lower() == PE_SUBNET.lower(), "admin_pe_conflict")
        require(pe["properties"]["privateLinkServiceConnections"][0]["properties"]["privateLinkServiceId"].lower()
                == site("admin").lower(), "admin_pe_conflict")
    arm.operation("PUT", endpoint + "/privateDnsZoneGroups/default", body={"properties": {
        "privateDnsZoneConfigs": [{"name": "app-service", "properties": {"privateDnsZoneId": ZONE}}]}})
    runner.cli(["acr", "repository", "update", "--name", runner.REGISTRY, "--image",
                "aiflux-customer:" + TAGS["customer"], "--write-enabled", "false", "--delete-enabled", "false"], redactor)
    _, credentials = runner.credentials(redactor)
    workspace = arm.get(runner.RG + "/providers/Microsoft.OperationalInsights/workspaces/" + runner.PREFIX + "-logs",
                        "2022-10-01")
    api_settings = {"AIFLUX_ENVIRONMENT": "production", "AIFLUX_DATABASE_URL": runner.DATABASE_URL,
        "AIFLUX_HOME_TENANT_ID": runner.TENANT, "AIFLUX_PORTAL_LOGIN_ENABLED": "true",
        "AIFLUX_PORTAL_LOGIN_SECRET": credentials["portal_login_secret"],
        "AIFLUX_GATEWAY_URL": GATEWAY,
        "AIFLUX_APIM_RESOURCE_ID": runner.RG + "/providers/Microsoft.ApiManagement/service/" + runner.PREFIX + "-apim",
        "AIFLUX_CATALOG_PATH": "/app/gateway/catalog/dev-models.json",
        # Capability acceptance is not inferred from successful image builds.
        "AIFLUX_CATALOG_CONFIGURED": "false",
        "AIFLUX_LOG_WORKSPACE_ID": workspace["properties"]["customerId"],
        "AIFLUX_CORS_ORIGINS": json.dumps(["https://" + runner.PREFIX + "-admin.azurewebsites.net",
                                             "https://" + runner.PREFIX + "-customer.azurewebsites.net"])}
    for kind in CLIENTS:
        settings = read_settings(arm, kind)
        settings.update({"AZURE_CLIENT_ID": CLIENTS[kind], "WEBSITES_PORT": "8000" if kind == "api" else "8080",
                         "WEBSITES_ENABLE_APP_SERVICE_STORAGE": "false"})
        if kind == "api":
            settings.update(api_settings)
            settings.pop("AIFLUX_PORTAL_SEED_USERS", None)
        else:
            settings.update({"GATEWAY_ORIGIN": GATEWAY,
                             "CONTROL_ORIGIN": "https://" + runner.PREFIX + "-api.azurewebsites.net"})
        # Response may contain secrets: never log or serialize it.
        arm.request("PUT", site(kind) + "/config/appsettings", WEB, {"properties": settings})
    result = {"settings_configured": list(CLIENTS), "startup_seed_absent": True,
              "customer_image_locked": True, "admin_private_endpoint_prepared": True}
    save("prepare", result)
    return result


def validate(arm: runner.Arm, redactor: runner.Redactor, deployed: bool = False) -> dict:
    account = runner.cli(["account", "show"], redactor)
    require(account["id"] == runner.SUB and account["tenantId"] == runner.TENANT and
            account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_context_mismatch")
    sql = arm.get(runner.SQL, "2023-08-01")
    require(sql["properties"].get("publicNetworkAccess") == "Disabled", "sql_public_exposed")
    result = {"account_context_verified": True, "sql_public": "Disabled", "apps": {}}
    registry = runner.RG + "/providers/Microsoft.ContainerRegistry/registries/" + runner.REGISTRY
    for kind, client in CLIENTS.items():
        app = arm.get(site(kind), WEB)
        config = arm.get(site(kind) + "/config/web", WEB)["properties"]
        require("linux" in app["kind"] and "functionapp" not in app["kind"], "wrong_site_kind")
        proof = network_proof(arm, kind, app, config)
        identities = app.get("identity", {}).get("userAssignedIdentities", {})
        selected = [x for x in identities.values() if x.get("clientId") == client]
        require(len(selected) == 1, "attached_identity_mismatch")
        roles = runner.cli(["role", "assignment", "list", "--assignee-object-id", selected[0]["principalId"],
                            "--scope", registry, "--include-inherited"], redactor)
        require(any(x.get("roleDefinitionId", "").lower().endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d")
                    and not x.get("condition") for x in roles), "acrpull_missing")
        meta = runner.cli(["acr", "repository", "show", "--name", runner.REGISTRY,
                           "--image", "aiflux-" + kind + ":" + TAGS[kind]], redactor)
        require(meta["digest"] == DIGESTS[kind] and meta["changeableAttributes"]["writeEnabled"] is False
                and meta["changeableAttributes"]["deleteEnabled"] is False, "image_not_locked_or_mismatch")
        settings = read_settings(arm, kind)
        require(settings.get("AZURE_CLIENT_ID") == client, "runtime_client_mismatch")
        if kind == "api":
            from aiflux.config import Settings
            values = {k.removeprefix("AIFLUX_").lower(): v for k, v in settings.items() if k.startswith("AIFLUX_")}
            for key in ("cors_origins", "gateway_settings_scopes"):
                if key in values:
                    values[key] = json.loads(values[key])
            validated = Settings(_env_file=None, **values)
            require(not validated.identity_errors(), "api_identity_settings_invalid")
            require(settings.get("AIFLUX_DATABASE_URL") == runner.DATABASE_URL and
                    settings.get("AIFLUX_ENVIRONMENT") == "production" and
                    not settings.get("AIFLUX_PORTAL_SEED_USERS"), "api_sql_or_seed_mismatch")
        if deployed:
            require(config.get("linuxFxVersion") == "DOCKER|" + image(kind) and
                    config.get("acrUseManagedIdentityCreds") is True and
                    config.get("acrUserManagedIdentityID") == client, "deployed_image_config_mismatch")
        result["apps"][kind] = {"network": proof, "acrpull": True, "image": image(kind),
                                 "tag_locked": True, "client_id": client}
    save("deployed-validation" if deployed else "validation", result)
    return result


def deploy(arm: runner.Arm, redactor: runner.Redactor) -> dict:
    plan = (ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    state = json.loads((ROOT / ".azure/validate-status.json").read_text(encoding="utf-8"))
    require("Status: Validated" in plan and state.get("completedStep") == "UpdateStatus", "validation_workflow_incomplete")
    validate(arm, redactor)
    for kind, client in CLIENTS.items():
        arm.request("PATCH", site(kind) + "/config/web", WEB, {"properties": {
            "linuxFxVersion": "DOCKER|" + image(kind), "acrUseManagedIdentityCreds": True,
            "acrUserManagedIdentityID": client, "alwaysOn": True,
            "healthCheckPath": "/health" if kind == "api" else "/healthz"}})
    # Config readback alone is not activation proof. Explicitly restart after all
    # three writes; callers must still perform live HTTP/readiness smoke tests.
    for kind in CLIENTS:
        arm.request("POST", site(kind) + "/restart", WEB)
    return validate(arm, redactor, deployed=True)


def smoke(redactor: runner.Redactor) -> dict:
    import requests
    _, creds = runner.credentials(redactor)
    base = "https://" + runner.PREFIX + "-customer.azurewebsites.net"
    session = requests.Session()
    session.verify = runner.CA
    checks = []
    def request(path: str, expected: int, token: str = "", payload: dict | None = None):
        headers = {"Authorization": "Bearer " + token} if token else {}
        response = session.request("POST" if payload else "GET", base + path, json=payload,
                                   headers=headers, timeout=(15, 90), allow_redirects=False)
        checks.append({"path": path, "status": response.status_code, "expected": expected})
        require(response.status_code == expected, "public_smoke_status_mismatch")
        return response
    request("/", 200)
    request("/healthz", 200)
    request("/api/me", 401)
    request("/api/admin/organizations", 403)
    for user in creds["portal_seed_users"]:
        if user["role"] != "customer":
            continue
        result = request("/api/auth/login", 200, payload={"username": user["username"], "password": user["password"]}).json()
        token = redactor.add(result["token"])
        require(result["user"]["role"] == "customer", "customer_role_mismatch")
        request("/api/me", 200, token)
        request("/api/subscriptions", 200, token)
    request("/api/auth/login", 401, payload={"username": "customer1", "password": "intentionally-invalid-smoke-password"})
    for kind in ("api", "admin"):
        response = session.get("https://" + runner.PREFIX + "-" + kind + ".azurewebsites.net/health" +
                               ("z" if kind == "admin" else ""), timeout=(15, 60))
        require(response.status_code == 403, "private_site_public_probe_not_denied")
        checks.append({"site": kind, "public_status": response.status_code})
    result = {"status": "passed", "checks": checks}
    save("smoke", result)
    return result


# Public program only. Credentials are secureValue environment fields, never command args.
PRIVATE_PROBE = r'''
import json,os,socket,ipaddress,hashlib,urllib.request,urllib.error
checks=[]
def call(base,path,expected=200,payload=None,token=None):
    data=json.dumps(payload).encode() if payload else None
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request(base+path,data=data,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=90) as r: status=r.status;body=r.read()
    except urllib.error.HTTPError as e: status=e.code;body=e.read()
    checks.append({'path':path,'status':status,'expected':expected})
    assert status==expected
    return json.loads(body) if body.startswith(b'{') else None
try:
    api='https://poc-ids-token-ex-api.azurewebsites.net'
    admin='https://poc-ids-token-ex-admin.azurewebsites.net'
    for host in [api[8:],admin[8:],'poc-ids-token-ex-sql.database.windows.net']:
        ips=sorted({i[4][0] for i in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
        assert ips and all(ipaddress.ip_address(ip) in ipaddress.ip_network('10.240.3.0/24') for ip in ips)
        checks.append({'dns':host,'private':True,'addresses':ips})
    expected=json.loads(os.environ['EXPECTED_SOURCE_HASHES'])
    for name,digest in expected.items():
        assert hashlib.sha256(open('/app/services/control-plane/src/aiflux/'+name,'rb').read()).hexdigest()==digest
    checks.append({'api_image_auth_source_matches_workspace':True})
    call(api,'/health');call(api,'/ready');call(api,'/api/me',401)
    call(admin,'/healthz');call(admin,'/admin/')
    call(admin,'/api/me',401)
    for user in json.loads(os.environ['PORTAL_SMOKE_USERS']):
        login=call(api,'/api/auth/login',payload={'username':user['username'],'password':user['password']})
        assert login['user']['role']==user['role']
        token=login['token'];call(api,'/api/me',token=token)
        call(api,'/api/admin/gateway-settings',200 if user['role']=='ids_admin' else 403,token=token)
        login=call(admin,'/api/auth/login',payload={'username':user['username'],'password':user['password']})
        assert login['user']['role']==user['role']
        token=login['token'];call(admin,'/api/me',token=token)
        for path in ['/api/admin/gateway-settings','/api/admin/organizations']:
            call(admin,path,200 if user['role']=='ids_admin' else 403,token=token)
    call(api,'/api/auth/login',401,payload={'username':'customer1','password':'invalid-smoke-only'})
    call(admin,'/api/auth/login',401,payload={'username':'admin','password':'invalid-smoke-only'})
    print(json.dumps({'status':'passed','checks':checks}))
except Exception as e:
    print(json.dumps({'status':'failed','checks':checks,'exception_type':type(e).__name__}));raise SystemExit(1)
'''


def private_smoke(arm: runner.Arm, redactor: runner.Redactor) -> dict:
    pre = runner.preflight(arm, redactor)
    _, creds = runner.credentials(redactor)
    execution = runner.Execution(arm, redactor, uuid4().hex)
    try:
        tags = {runner.OWNER_KEY: execution.run_id, "purpose": "temporary-private-application-smoke"}
        execution.create(runner.IP, {"location": runner.LOCATION, "tags": tags, "sku": {"name": "Standard"},
            "properties": {"publicIPAllocationMethod": "Static", "publicIPAddressVersion": "IPv4"}})
        execution.create(runner.NAT, {"location": runner.LOCATION, "tags": tags, "sku": {"name": "Standard"},
            "properties": {"idleTimeoutInMinutes": 4, "publicIpAddresses": [{"id": runner.IP}]}})
        execution.create(runner.SUBNET, {"properties": {"addressPrefix": runner.CIDR,
            "natGateway": {"id": runner.NAT}, "delegations": [{"name": "aiflux-run-" + execution.run_id,
                "properties": {"serviceName": "Microsoft.ContainerInstance/containerGroups"}}]}})
        hashes = {name: hashlib.sha256((ROOT / "services/control-plane/src/aiflux" / name).read_bytes()).hexdigest()
                  for name in AUTH_FILES}
        body = {"location": runner.LOCATION, "tags": tags,
            "identity": {"type": "UserAssigned", "userAssignedIdentities": {pre["identity_id"]: {}}},
            "properties": {"osType": "Linux", "restartPolicy": "Never", "subnetIds": [{"id": runner.SUBNET}],
                "dnsConfig": {"nameServers": ["168.63.129.16"]}, "imageRegistryCredentials": [{
                    "server": runner.REGISTRY_HOST, "identity": pre["identity_id"]}],
                "containers": [{"name": "portal-smoke", "properties": {"image": image("api"),
                    "command": ["python", "-c", PRIVATE_PROBE],
                    "resources": {"requests": {"cpu": 1, "memoryInGB": 1.5}},
                    "environmentVariables": [{"name": "PORTAL_SMOKE_USERS", "secureValue": json.dumps(creds["portal_seed_users"])},
                                             {"name": "EXPECTED_SOURCE_HASHES", "value": json.dumps(hashes)}]}}]}}
        execution.create(runner.ACI, body, runner.ACI_API)
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            group = arm.get(runner.ACI, runner.ACI_API)
            state = group["properties"]["containers"][0]["properties"].get("instanceView", {}).get("currentState", {})
            if state.get("state") == "Terminated":
                logs = arm.request("GET", runner.ACI + "/containers/portal-smoke/logs", runner.ACI_API).json()
                parsed = json.loads(logs.get("content", "").strip().splitlines()[-1])
                # Public program emits only fixed paths/statuses, DNS addresses, finite exception types.
                require(parsed.get("status") in {"passed", "failed"}, "private_smoke_log_invalid")
                execution.report["probe"] = parsed
                require(state.get("exitCode") == 0 and parsed["status"] == "passed", "private_smoke_failed")
                execution.report["status"] = "succeeded"
                break
            time.sleep(10)  # Bounded workload-state polling, not terminal polling.
        else:
            raise runner.RunnerError("private_smoke_timeout")
    except BaseException:
        execution.report["status"] = "failed"
        raise
    finally:
        execution.cleanup()
        if any(x["status"] != "verified_absent" for x in execution.report["cleanup"]):
            execution.report["status"] = "cleanup_failed"
        execution.save()
        save("private-smoke", execution.report)
    require(all(x["status"] == "verified_absent" for x in execution.report["cleanup"]), "smoke_cleanup_incomplete")
    return execution.report


WORKFLOW_STEPS = ("None", "LoadPlan", "AddValidationSteps", "RunValidation", "BuildVerification",
                  "StaticRoleVerification", "RecordProof", "ResolveErrors", "UpdateStatus")
WORKFLOW_ACTIONS = ("Read deployment plan and AZCLI recipe", "Add recipe validation steps to plan",
                    "Execute recipe-specific validation", "Verify project/container builds",
                    "Review static identity/RBAC assignments", "Record timestamped Section 7 proof",
                    "Resolve all validation failures", "Set Validated only after all checks pass",
                    "Validation complete: invoke azure-deploy")


def workflow(step: str) -> dict:
    """Faithful transition/status equivalent of workflow.ps1, blocked by CLM.

    It records progress, not validation success. Actions must be actually performed
    before the caller acknowledges each next step, just like the original script.
    """
    path = ROOT / ".azure/validate-status.json"
    index = WORKFLOW_STEPS.index(step)
    previous = json.loads(path.read_text()) if path.exists() else {"completedStep": "None"}
    require(index <= WORKFLOW_STEPS.index(previous["completedStep"]) + 1, "workflow_step_skipped")
    path.write_text(json.dumps({"completedStep": step, "implementation": "Python faithful CLM adaptation",
                               "source": "azure-validate/references/scripts/workflow.ps1"}, indent=2) + "\n")
    return {"completedStep": step, "action": WORKFLOW_ACTIONS[index],
            "next": WORKFLOW_STEPS[index + 1] if index + 1 < len(WORKFLOW_STEPS) else None}


def main() -> int:
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "prepare", "validate", "deploy", "verify", "smoke", "private-smoke", "workflow"))
    parser.add_argument("--completed-step", choices=WORKFLOW_STEPS, default="None")
    args = parser.parse_args()
    redactor = runner.Redactor()
    try:
        if args.action == "workflow":
            result = workflow(args.completed_step)
        elif args.action == "smoke":
            result = smoke(redactor)
        else:
            arm = runner.Arm(redactor)
            if args.action == "snapshot":
                result = snapshot(arm)
            elif args.action == "prepare":
                result = prepare(arm, redactor)
            elif args.action in {"validate", "verify"}:
                result = validate(arm, redactor, args.action == "verify")
            elif args.action == "private-smoke":
                result = private_smoke(arm, redactor)
            else:
                result = deploy(arm, redactor)
        print(json.dumps(result, indent=2))
        return 0
    except runner.RunnerError as error:
        # ARM errors can echo request properties. Never print message/details.
        print(json.dumps({"status": "failed", "code": error.code,
                          "http_status": error.details.get("http_status"),
                          "azure_code": error.details.get("azure_code")}))
    except Exception as error:
        print(json.dumps({"status": "failed", "exception_type": type(error).__name__}))
    return 1


if __name__ == "__main__":
    sys.exit(main())