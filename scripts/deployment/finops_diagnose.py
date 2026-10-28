"""Read-only FinOps evidence. Never persist settings, credentials or raw log rows."""
import argparse
import ipaddress
import json
import re
import socket
import ssl
import subprocess
from datetime import UTC, datetime
from urllib.request import Request, urlopen

from sqlalchemy.engine import make_url

from scripts.deployment import runtime_rollout as rt


# Storage-only approval executed/read back 2026-10-27; never reuse for app/DB ACLs.
APPROVED_STATE_STORAGE_IPS = frozenset({"167.103.66.248", "167.103.66.93", "167.103.65.36"})


def scm_health_result(value):
    """Kudu transport success is not application health; discard all raw output."""
    if not isinstance(value, dict):
        return {"status": "unverified", "reason": "invalid_scm_response"}
    output = value.get("Output", value.get("output"))
    exit_code = value.get("ExitCode", value.get("exitCode"))
    match = re.fullmatch(r"[1-5][0-9]{2}", output.strip()) if isinstance(output, str) else None
    code = int(match[0]) if match else None
    return {"status": "verified" if type(exit_code) is int and exit_code == 0 and code == 200 else "unverified",
            "exit_code": exit_code if type(exit_code) is int else None, "http_status": code}


def existing_scm_probe():
    """Fixed read-only health/readiness GETs via the existing admin SCM path.

    /ready performs SELECTs using the API's identity; it is not DB DML, ownership,
    ingester permission or replay proof. Never return stdout/stderr or credentials.
    """
    from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                    "--resource", "https://management.azure.com/"])["accessToken"]
    opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=rt.CA)))
    report = {}
    for path in ("health", "ready"):
        try:
            command = "curl -sS --connect-timeout 5 --max-time 15 -o /dev/null -w '%{http_code}' https://poc-ids-token-ex-api.azurewebsites.net/" + path
            request = Request("https://poc-ids-token-ex-admin.scm.azurewebsites.net/api/command",
                data=json.dumps({"command": command, "dir": "/home"}).encode(),
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            with opener.open(request, timeout=30) as response:
                raw = response.read(8193)
                rt.require(len(raw) <= 8192, "scm_response_too_large")
                value = json.loads(raw)
                report[path] = {"scm_status": response.status, **scm_health_result(value)}
        except Exception as exc:
            report[path] = {"status": "unverified", "collection_error": type(exc).__name__, "http_status": getattr(exc, "code", None)}
    return report


def private_paths():
    """Inventory existing hosts only. Never invoke a job, restart a site or widen access."""
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    report = {"at": datetime.now(UTC).isoformat(), "read_only": True, "sites": {}}
    resources = rt.cli(["resource", "list", "--subscription", rt.SUB,
                        "--resource-group", "IDS-TOKEN-EXCHANGE-POC"])
    kinds = {"microsoft.compute/virtualmachines", "microsoft.containerinstance/containergroups", "microsoft.app/jobs"}
    report["existing_runner_candidates"] = [{"name": r["name"], "type": r["type"]}
        for r in resources if r.get("type", "").lower() in kinds]
    for kind in ("api", "admin", "customer", "ingestion"):
        path = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind
        try:
            site = rt.arm(path)
            config = rt.arm(path + "/config/web")["properties"]
            props = site["properties"]
            attached = site.get("identity", {}).get("userAssignedIdentities", {})
            report["sites"][kind] = {
                "state": props.get("state"), "image": config.get("linuxFxVersion"),
                "public_network_access": props.get("publicNetworkAccess"),
                "vnet_integration": props.get("virtualNetworkSubnetId"),
                "scm_default_action": config.get("scmIpSecurityRestrictionsDefaultAction"),
                "scm_use_main": config.get("scmIpSecurityRestrictionsUseMain"),
                "scm_explicit_allow_rules": sum(r.get("action") == "Allow" for r in config.get("scmIpSecurityRestrictions", [])),
                "attached_identities": [{"client_id": v.get("clientId"), "object_id": v.get("principalId")}
                                        for v in attached.values()],
            }
        except Exception as exc:
            report["sites"][kind] = {"collection_error": type(exc).__name__, "status": getattr(exc, "code", None)}
    report["database_network"] = rt.arm(rt.RG + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg")["properties"].get("network")
    report["postgres_firewall_rule_count"] = len(rt.arm(rt.RG + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg/firewallRules").get("value", []))
    report["workstation_database_probe"] = private_database_probe()
    report["existing_admin_scm_probe"] = existing_scm_probe()
    report["retention_and_role_metadata"] = retention_and_roles(report["sites"])
    report["state_storage"] = state_storage_probe()
    return report


def state_storage_probe():
    """ACL and container existence only; never read/list state blob contents."""
    report = {}
    try:
        value = rt.cli(["storage", "account", "show", "--name", "projpoctokenex",
                        "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--subscription", rt.SUB])
        rules = value.get("networkRuleSet", {})
        approved = APPROVED_STATE_STORAGE_IPS
        ips = {r.get("ipAddressOrRange") for r in rules.get("ipRules", [])}
        report.update(default_action=rules.get("defaultAction"), approved_ips_present=sorted(ips & approved),
                      other_ip_rule_count=len(ips - approved))
        report.update(container_metadata_access=container_metadata_probe())
    except Exception as exc:
        report.update(container_metadata_access="blocked", exception_type=type(exc).__name__,
                      error_codes=[code for code in ("AuthorizationFailure", "AuthorizationFailed", "ForbiddenByFirewall")
                                   if code in str(exc)])
    return report


def container_metadata_probe():
    """Capture CLI errors in memory; emit fixed classifications, never raw lines."""
    command = rt.CLI + ["storage", "container", "exists", "--account-name", "projpoctokenex", "--name", "tfstate",
                        "--auth-mode", "login", "--subscription", rt.SUB, "--only-show-errors", "-o", "json"]
    result = subprocess.run(command, cwd=rt.ROOT, env=rt.ENV, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=60)
    if result.returncode == 0:
        return {"status": "verified" if json.loads(result.stdout).get("exists") is True else "not_found"}
    text = result.stdout + result.stderr
    labels = {"network_rule_denial": r"blocked by network rules|network rules.*storage account|IP.*not authorized",
              "authorization_failure": r"AuthorizationFailure|AuthorizationFailed|AuthorizationPermissionMismatch",
              "authentication_failure": r"AuthenticationFailed|AADSTS\d+",
              "tls_failure": r"CERTIFICATE_VERIFY_FAILED|certificate verify failed",
              "transport_failure": r"ConnectionError|connect.*timed out|ReadTimeout|NameResolutionError"}
    return {"status": "blocked", "cli_exit": result.returncode,
            "categories": [label for label, pattern in labels.items() if re.search(pattern, text, re.I)]}


def retention_and_roles(sites):
    """Configuration/role-assignment evidence, NOT successful MI data-plane proof."""
    report = {"managed_identity_data_plane_verified": False}
    workspace_path = rt.RG + "/providers/Microsoft.OperationalInsights/workspaces/poc-ids-token-ex-logs"
    storage_path = rt.RG + "/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc"
    try:
        def metadata(path, version):
            return rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + path + "?api-version=" + version])

        workspace = metadata(workspace_path, "2023-09-01")["properties"]
        settings = rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/config/appsettings/list", "POST")["properties"]
        report["api_workspace_matches"] = settings.get("AIFLUX_LOG_WORKSPACE_ID") == workspace.get("customerId")
        report["workspace_retention_days"] = workspace.get("retentionInDays")
        report["tables"] = {}
        for table in ("ApiManagementGatewayLogs", "ApiManagementGatewayLlmLog"):
            props = metadata(workspace_path + "/tables/" + table, "2022-10-01")["properties"]
            report["tables"][table] = {k: props.get(k) for k in ("retentionInDays", "totalRetentionInDays", "plan")}
        assignments = rt.cli(["role", "assignment", "list", "--subscription", rt.SUB, "--all", "--include-inherited"])
        allowed_names = {"Reader", "Contributor", "Owner", "Monitoring Reader", "Monitoring Metrics Publisher",
                         "Log Analytics Reader", "Log Analytics Contributor", "Storage Blob Data Owner",
                         "Storage Blob Data Contributor", "Storage Queue Data Contributor", "Storage Table Data Contributor"}
        report["roles"] = {}
        for kind in ("api", "ingestion"):
            principals = {v["object_id"] for v in sites.get(kind, {}).get("attached_identities", [])}
            result = {}
            for label, scope in (("monitor_workspace", workspace_path), ("function_host_storage", storage_path)):
                applicable = [r for r in assignments if r.get("principalId") in principals and
                              (scope.lower() == r.get("scope", "").lower() or
                               scope.lower().startswith(r.get("scope", "").lower().rstrip("/") + "/"))]
                names = {r.get("roleDefinitionName") for r in applicable}
                result[label] = {"known_builtin_role_names": sorted(names & allowed_names),
                                 "other_assignment_count": sum(r.get("roleDefinitionName") not in allowed_names for r in applicable)}
            report["roles"][kind] = result
    except Exception as exc:
        report.update(collection_error=type(exc).__name__, status=getattr(exc, "code", None))
    return report


def log_query(workspace, query):
    token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                    "--resource", "https://api.loganalytics.io/"])["accessToken"]
    request = Request("https://api.loganalytics.azure.com/v1/workspaces/" + workspace + "/query",
                      data=json.dumps({"query": query}).encode(),
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urlopen(request, context=ssl.create_default_context(cafile=rt.CA), timeout=90) as response:
            result = json.load(response)
        return {"partial": "error" in result, "tables": result.get("tables", [])}
    except Exception as exc:
        return {"collection_error": type(exc).__name__, "status": getattr(exc, "code", None)}


def telemetry_contract():
    """Aggregate-only source/trace shape and retained-history dry run. No DB writes."""
    path = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/config/appsettings/list"
    values = rt.arm(path, "POST")["properties"]
    workspace, resource = values["AIFLUX_LOG_WORKSPACE_ID"], values["AIFLUX_APIM_RESOURCE_ID"]
    base = ('ApiManagementGatewayLogs | where TimeGenerated >= ago(30d) | where _ResourceId =~ '
            + json.dumps(resource) + ' | where ProductId == "aiflux" and OperationId == "chat" ')
    return {
        "at": datetime.now(UTC).isoformat(), "dry_run_only": True,
        "gateway_schema": log_query(workspace, "ApiManagementGatewayLogs | getschema | project ColumnName, DataType"),
        "llm_schema": log_query(workspace, "ApiManagementGatewayLlmLog | getschema | project ColumnName, DataType"),
        "trace_contract": log_query(workspace, base +
            '| mv-expand t=todynamic(TraceRecords) | where tostring(t.source) == "aiflux" '
            '| extend m=todynamic(t.metadata) | where tostring(m.category) == "usage" '
            '| extend u=parse_json(tostring(m.payload)) '
            '| summarize usage_events=count(), valid_schema=countif(tostring(u.schema) == "finops-v1"), '
            'measured=countif(isnotnull(u.input_tokens) and isnotnull(u.output_tokens)), '
            'glm=countif(tostring(u.model) == "glm-5.3"), inputs=sum(tolong(u.input_tokens)), '
            'outputs=sum(tolong(u.output_tokens))'),
        "retained_daily": log_query(workspace, base +
            '| summarize requests=count(), trace_rows=countif(isnotempty(TraceRecords)) by bin(TimeGenerated, 1d) '
            '| order by TimeGenerated asc'),
        "backfill": "blocked until activation cutoff, ownership and approved private database evidence; no watermark changes",
    }


def destination(value):
    if not value:
        return None
    url = make_url(value)
    engine = url.get_backend_name()
    # An override's mere presence does not establish that two schemas match.
    # Never export arbitrary query values: they can contain credentials.
    return {"engine": engine, "host": url.host, "port": url.port or (
        5432 if engine == "postgresql" else 1433), "database": url.database,
        "schema_override_present": any(k in url.query for k in ("options", "schema", "search_path"))}


def private_database_probe():
    """Workstation transport only. DB proof belongs on the existing MI host.

    Never substitute the human operator token for the app's managed identity.
    """
    from scripts.deployment.finops_private_probe import private_addresses

    host = "poc-ids-token-ex-pg.postgres.database.azure.com"
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, 5432, type=socket.SOCK_STREAM)}
        if not private_addresses(addresses):
            return {"status": "blocked", "reason": "private_dns_route_unavailable"}
        with socket.create_connection((host, 5432), timeout=5):
            pass
        return {"status": "transport_only", "reason": "private_host_managed_identity_probe_required",
                "database_authenticated": False}
    except Exception as exc:
        return {"status": "blocked", "exception_type": type(exc).__name__}


def deep_collect():
    report = collect()
    report["telemetry_contract"] = telemetry_contract()
    report["private_database"] = private_database_probe()
    report["connectivity"] = {}
    try:
        storage = rt.cli(["storage", "account", "show", "--name", "projpoctokenex",
                          "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--subscription", rt.SUB])
        rules = storage.get("networkRuleSet", {})
        allowed = APPROVED_STATE_STORAGE_IPS
        actual = {rule.get("ipAddressOrRange") for rule in rules.get("ipRules", [])}
        report["connectivity"]["state_storage"] = {"default_action": rules.get("defaultAction"),
            "approved_ips_present": sorted(allowed & actual), "other_ip_rule_count": len(actual - allowed)}
        with urlopen("https://api.ipify.org", context=ssl.create_default_context(cafile=rt.CA), timeout=15) as response:
            ip = response.read(64).decode().strip()
            ipaddress.ip_address(ip)
            report["connectivity"]["https_egress"] = ip
            report["connectivity"]["egress_previously_authorized"] = ip in allowed
    except Exception as exc:
        report["connectivity"]["collection_error"] = type(exc).__name__
    report["portal_images"] = {}
    for kind in ("admin", "customer"):
        path = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind
        try:
            props = rt.arm(path + "/config/web")["properties"]
            report["portal_images"][kind] = {"image": props.get("linuxFxVersion"),
                                           "scm_default_action": props.get("scmIpSecurityRestrictionsDefaultAction")}
        except Exception as exc:
            report["portal_images"][kind] = {"collection_error": type(exc).__name__}
    report["resource_health"] = {}
    for kind in ("api", "ingestion"):
        path = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind
        try:
            health = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + path +
                             "/providers/Microsoft.ResourceHealth/availabilityStatuses/current?api-version=2024-02-01"])
            report["resource_health"][kind] = {"availability": health.get("properties", {}).get("availabilityState")}
        except Exception as exc:
            report["resource_health"][kind] = {"collection_error": type(exc).__name__}
    # Verify existing SCM access without listing files, processes or settings.
    try:
        token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                        "--resource", "https://management.azure.com/"])["accessToken"]
        request = Request("https://poc-ids-token-ex-admin.scm.azurewebsites.net/api/command",
                          data=json.dumps({"command": "curl -sS --connect-timeout 5 --max-time 10 -o /dev/null -w '%{http_code}' https://poc-ids-token-ex-api.azurewebsites.net/health", "dir": "/home"}).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urlopen(request, context=ssl.create_default_context(cafile=rt.CA), timeout=30) as response:
            value = json.load(response)
            report["private_api_health"] = {"scm_status": response.status, **scm_health_result(value)}
    except Exception as exc:
        report["private_api_health"] = {"collection_error": type(exc).__name__, "status": getattr(exc, "code", None)}
    return report


def collect():
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    report = {"at": datetime.now(UTC).isoformat(), "read_only": True, "sites": {}}
    settings = {}
    allowed = ["AIFLUX_APIM_PRODUCT_ID", "AIFLUX_CATALOG_CONFIGURED", "AIFLUX_LOG_WORKSPACE_ID",
               "AIFLUX_APIM_RESOURCE_ID", "AIFLUX_INGESTION_START_AT", "AIFLUX_INGESTION_DELAY_MINUTES",
               "AIFLUX_INGESTION_BATCH_MINUTES", "AIFLUX_INGESTION_OVERLAP_MINUTES",
               "AzureWebJobs.ingest_usage.Disabled", "FUNCTIONS_WORKER_RUNTIME"]
    for kind in ("api", "ingestion"):
        path = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind
        try:
            site = rt.arm(path)["properties"]
            config = rt.arm(path + "/config/web")["properties"]
            values = rt.arm(path + "/config/appsettings/list", "POST")["properties"]
            settings[kind] = values
            report["sites"][kind] = {
                "state": site.get("state"), "publicNetworkAccess": site.get("publicNetworkAccess"),
                "always_on": config.get("alwaysOn"), "image": config.get("linuxFxVersion"),
                "database": destination(values.get("AIFLUX_DATABASE_URL")),
                "settings": {k: values.get(k) for k in allowed},
            }
            if kind == "ingestion":
                functions = rt.arm(path + "/functions").get("value", [])
                report["sites"][kind]["discovered_functions"] = [f["name"].split("/")[-1] for f in functions]
        except Exception as exc:
            report["sites"].setdefault(kind, {}).update({
                "collection_error": type(exc).__name__, "status": getattr(exc, "code", None)})
    if len(settings) == 2:
        api_db = destination(settings["api"].get("AIFLUX_DATABASE_URL"))
        ingestion_db = destination(settings["ingestion"].get("AIFLUX_DATABASE_URL"))
        report["same_database_destination"] = bool(api_db and ingestion_db and api_db == ingestion_db
                                                    and not api_db["schema_override_present"])
    reference = settings.get("ingestion", {}) if settings.get("ingestion", {}).get("AIFLUX_LOG_WORKSPACE_ID") else settings.get("api", {})
    workspace = reference.get("AIFLUX_LOG_WORKSPACE_ID")
    resource = reference.get("AIFLUX_APIM_RESOURCE_ID")
    if workspace and resource:
        token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                        "--resource", "https://api.loganalytics.io/"])["accessToken"]
        # Aggregate projection only; never export trace records or subscription IDs.
        query = ('ApiManagementGatewayLogs | where TimeGenerated >= ago(30d) '
                 '| where _ResourceId =~ ' + json.dumps(resource) +
                 ' | summarize requests=count(), recent48h=countif(TimeGenerated >= ago(48h)), '
                 'earliest_utc=min(TimeGenerated), latest_utc=max(TimeGenerated), '
                 'trace_present=countif(isnotempty(column_ifexists("TraceRecords", ""))) by ProductId, OperationId')
        request = Request("https://api.loganalytics.azure.com/v1/workspaces/" + workspace + "/query",
                          data=json.dumps({"query": query}).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urlopen(request, context=ssl.create_default_context(cafile=rt.CA), timeout=90) as response:
                result = json.load(response)
            report["logs"] = {"partial": "error" in result, "tables": result.get("tables", [])}
        except Exception as exc:
            report["logs"] = {"collection_error": type(exc).__name__, "status": getattr(exc, "code", None)}
            if hasattr(exc, "read"):
                try:
                    error = json.loads(exc.read()).get("error", {})
                    codes = []
                    for _ in range(5):
                        code = error.get("code")
                        if isinstance(code, str) and code.replace("_", "").isalnum():
                            codes.append(code)
                        error = error.get("innererror", {})
                    report["logs"]["error_codes"] = codes
                except (ValueError, AttributeError):
                    pass
    return report


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--deep", action="store_true")
        mode.add_argument("--private-paths", action="store_true")
        args = parser.parse_args()
        report = private_paths() if args.private_paths else deep_collect() if args.deep else collect()
        report = json.loads(json.dumps(report, default=str))
        name = "private-paths.json" if args.private_paths else "resume-live-diagnosis.json"
        rt.save(rt.HOME / "finops" / name, report)
        print(json.dumps(report), flush=True)
    except Exception as exc:
        print(json.dumps({"collection_error": type(exc).__name__}), flush=True)
        raise SystemExit(1)