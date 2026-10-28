"""Collect fresh, sanitized preprovision gates. This command cannot create resources.

Approval is already recorded. The current failed gate is platform compatibility,
NOT missing user authorization. Do not treat this collector as a provisioner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.deployment import finops_runner_guards as g

ROOT = Path(__file__).resolve().parents[2]
AZ = "C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"
CA = "C:/Users/p4032099/AppData/Local/Temp/zscaler-login-7860c54ccee94b5d8fa181e004a50458/azure-cli-combined-ca.pem"
OUT = ROOT / "gateway/validation/finops-runner-preflight-20261027.json"
ENV = {**os.environ, "REQUESTS_CA_BUNDLE": CA, "SSL_CERT_FILE": CA,
       "AZURE_CORE_COLLECT_TELEMETRY": "false", "AZURE_EXTENSION_USE_DYNAMIC_INSTALL": "no"}


def now():
    return datetime.now(UTC).isoformat()


def cli(args):
    # This file deliberately has no create/update/delete/build/deployment path.
    allowed = (args[:2] == ["account", "show"] or args[:2] == ["resource", "list"] or
               args[:3] == ["rest", "--method", "get"])
    g.require(allowed, "read_only_command_required")
    result = subprocess.run([AZ, *args, "--subscription", g.SUB, "--only-show-errors", "-o", "json"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            env=ENV, timeout=70)
    if result.returncode:
        # Error bodies can contain arbitrary values; expose neither stdout nor stderr.
        raise g.GuardBlocked("read_only_azure_command_failed")
    return json.loads(result.stdout)


def get(rid, version):
    return cli(["rest", "--method", "get", "--url",
                "https://management.azure.com" + rid + "?api-version=" + version])


def prices(filt):
    url = "https://prices.azure.com/api/retail/prices?" + urlencode({"$filter": filt, "currencyCode": "USD"})
    items = []
    for _ in range(5):
        with urlopen(url, context=ssl.create_default_context(cafile=CA), timeout=30) as response:
            value = json.load(response)
        items.extend(value["Items"])
        url = value.get("NextPageLink")
        if not url:
            return items
        g.require(url.startswith("https://prices.azure.com/"), "untrusted_price_pagination")
    raise g.GuardBlocked("price_pagination_incomplete")


def meter(items, *, product, name, unit, region, sku="Standard"):
    matches = [p for p in items if p.get("productName") == product and p.get("meterName") == name
               and p.get("skuName") == sku and p.get("unitOfMeasure") == unit and
               p.get("armRegionName") == region and p.get("currencyCode") == "USD" and
               p.get("type") == "Consumption"]
    g.require(len(matches) == 1, "price_meter_ambiguous_or_missing")
    return {k: matches[0][k] for k in ("productName", "skuName", "meterName", "unitOfMeasure",
                                       "armRegionName", "currencyCode", "retailPrice", "meterId", "effectiveStartDate")}


def verify_absence():
    """Independent exact-ID HTTP GETs, not an inventory-based cleanup claim.

    No DELETE is available here. Tokens remain in memory and are never logged,
    decoded, returned in evidence, or passed as command-line arguments.
    """
    report = json.loads(OUT.read_text(encoding="utf-8"))
    ids = g.owned_ids(report["owner_nonce"])
    g.require(report["planned_resource_ids_not_created"] == ids and not report["created_resource_ids"],
              "unexpected_creation_requires_owned_cleanup")
    account = cli(["account", "show"])
    g.require(account["id"] == g.SUB and account["tenantId"] == g.TENANT, "account_scope_mismatch")
    token_result = subprocess.run([AZ, "account", "get-access-token", "--subscription", g.SUB,
        "--resource", "https://management.azure.com/", "--query", "accessToken", "-o", "tsv", "--only-show-errors"],
        capture_output=True, text=True, env=ENV, timeout=70)
    g.require(token_result.returncode == 0 and bool(token_result.stdout.strip()), "arm_authentication_failed")
    token = token_result.stdout.strip()
    result = {"started_at_utc": now(), "results": [], "delete_executed": False,
              "basis": "independent_exact_id_arm_http_get_not_inventory"}
    context = ssl.create_default_context(cafile=CA)
    try:
        for key, rid in ids.items():
            version = "2023-05-01" if key in g.IDENTITIES else "2024-05-01"
            request = Request("https://management.azure.com" + rid + "?api-version=" + version,
                              headers={"Authorization": "Bearer " + token})
            status = None
            try:
                with urlopen(request, context=context, timeout=25) as response:
                    status = response.status
            except HTTPError as exc:
                status = exc.code
                exc.close()
            result["results"].append({"resource_id": rid, "http_status": status, "checked_at_utc": now()})
            g.require(status == 404, "planned_resource_absence_unverified")
        result["all_six_ids_verified_absent"] = True
        report["probe_source_sha256"] = hashlib.sha256((ROOT / "scripts/deployment/finops_private_probe.py").read_bytes()).hexdigest()
    finally:
        result["finished_at_utc"] = now()
        report["absence_verification"] = result
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"exact_ids_verified_http_404": len(result["results"]), "delete_executed": False,
                      "finished_at_utc": result["finished_at_utc"]}), flush=True)
    return 0


def main():
    report = {"started_at_utc": now(), "approval": "explicit_user_approved_proposal_and_both_distinct_mi_exposures",
              "subscription": g.SUB, "tenant": g.TENANT, "region": "southeastasia",
              "status": "collecting", "created_resource_ids": [], "deleted_resource_ids": [],
              "identity_attachments": 0, "network_writes": 0, "new_role_assignments": 0,
              "database_writes": 0, "replay_executed": False, "timer_enabled": False,
              "app_release": False, "images_built": 0, "private_probe_executed": False,
              "ingestion_probe_exit": None, "api_probe_exit": None, "aggregates": None,
              "approved_activation_cutoff": None, "cleanup_required": False,
              "cloud_configuration_writes_this_continuation": 0,
              "historical_approved_state_ip_cloud_configuration_writes": 1}
    try:
        account = cli(["account", "show"])
        g.require(account["id"] == g.SUB and account["tenantId"] == g.TENANT and
                  account["user"]["name"] == "xv.puneet.devadiga@singtel.com", "account_scope_mismatch")
        report["account_scope_verified"] = True
        vnet = get(g.VNET, "2024-05-01")
        report["network_capacity"] = g.network_capacity(vnet)
        report["existing_subnets"] = [{"id": s["id"],
            "prefixes": s["properties"].get("addressPrefixes") or [s["properties"]["addressPrefix"]],
            "delegations": [d["properties"]["serviceName"] for d in s["properties"].get("delegations", [])],
            "purpose": s["properties"].get("purpose"),
            "private_endpoint_count": len(s["properties"].get("privateEndpoints", []))}
            for s in vnet["properties"]["subnets"]]
        g.require(not vnet["properties"].get("dhcpOptions", {}).get("dnsServers"), "custom_vnet_dns_requires_review")
        inventory = cli(["resource", "list", "--resource-group", "IDS-TOKEN-EXCHANGE-POC",
                         "--query", "[].{id:id,type:type}"])
        nonce = secrets.token_hex(6)
        ids = g.owned_ids(nonce)
        existing_ids = {r["id"].lower() for r in inventory} | {s["id"].lower() for s in vnet["properties"]["subnets"]}
        g.require(not (existing_ids & {rid.lower() for rid in ids.values()}), "owned_name_collision")
        report["owner_nonce"] = nonce
        report["planned_resource_ids_not_created"] = ids
        report["baseline_at_utc"] = now()
        report["baseline_resource_count"] = len(inventory)
        report["existing_aci_group_count"] = sum(r["type"].lower() == "microsoft.containerinstance/containergroups" for r in inventory)
        report["existing_nat_count"] = sum(r["type"].lower() == "microsoft.network/natgateways" for r in inventory)
        report["planned_ids_absent_from_fresh_inventory"] = True
        # Local journal precedes any possible future PUT; it explicitly has no write intents.
        journal = {"owner_nonce": nonce, "baseline_at_utc": report["baseline_at_utc"], "ids": ids,
                   "baseline_absent": {k: True for k in ids}, "write_intents": [],
                   "inventory_ids": sorted(existing_ids), "no_put_authorized_by_this_file": True}
        folder = ROOT / ".deployment/finops-runner" / nonce
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "ownership-journal.json").write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
        usage = get(f"/subscriptions/{g.SUB}/providers/Microsoft.ContainerInstance/locations/southeastasia/usages", "2023-05-01")
        report["aci_quota"] = {x["name"]["value"]: {"used": x["currentValue"], "limit": x["limit"]}
                               for x in usage["value"] if x["name"]["value"] in {"ContainerGroups", "StandardCores"}}
        g.require(all(x["limit"] - x["used"] >= 1 for x in report["aci_quota"].values()) and
                  len(report["aci_quota"]) == 2, "aci_quota_unavailable")
        provider = get(f"/subscriptions/{g.SUB}/providers/Microsoft.ContainerInstance", "2021-04-01")
        report["aci_provider_registered"] = provider["registrationState"] == "Registered"
        report["aci_region_listed"] = any("Southeast Asia" in x.get("locations", []) for x in provider["resourceTypes"]
                                         if x["resourceType"] == "containerGroups")
        g.require(report["aci_provider_registered"] and report["aci_region_listed"], "aci_region_unavailable")
        report["actual_regional_allocation_attempted"] = False
        registry = get(g.RG + "/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr", "2023-07-01")
        report["registry"] = {"sku": registry["sku"]["name"], "location": registry["location"],
                              "dedicated_data_endpoint_enabled": registry["properties"].get("dataEndpointEnabled", False)}
        storage = get(g.RG + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex", "2023-05-01")
        acl = storage["properties"]["networkAcls"]
        report["state_acl"] = {"default_action": acl["defaultAction"],
                               "ips": sorted(x["value"] for x in acl["ipRules"]), "writes": 0}
        g.require(report["state_acl"] == {"default_action": "Deny", "ips": sorted([
            "167.103.65.36", "167.103.66.93", "167.103.66.248"]), "writes": 0}, "state_acl_drift")
        pg = get(g.RG + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg", "2024-08-01")
        rules = get(g.RG + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg/firewallRules", "2024-08-01")
        report["postgres"] = {"public_network_access": pg["properties"]["network"]["publicNetworkAccess"],
                              "firewall_rule_count": len(rules["value"]), "authenticated_snapshot": False}
        g.require(report["postgres"]["public_network_access"] == "Disabled" and not rules["value"], "postgres_network_drift")
        regional = prices("armRegionName eq 'southeastasia' and priceType eq 'Consumption' and (serviceName eq 'Container Instances' or serviceName eq 'Virtual Network')")
        nat = prices("serviceName eq 'NAT Gateway' and priceType eq 'Consumption'")
        meters = {
            "aci_cpu": meter(regional, product="Container Instances", name="Standard vCPU Duration", unit="1 Hour", region="southeastasia"),
            "aci_memory": meter(regional, product="Container Instances", name="Standard Memory Duration", unit="1 GB Hour", region="southeastasia"),
            "static_ipv4": meter(regional, product="IP Addresses", name="Standard IPv4 Static Public IP", unit="1 Hour", region="southeastasia"),
            "nat_hour": meter(nat, product="NAT Gateway", name="Standard Gateway", unit="1 Hour", region="Global"),
            "nat_data": meter(nat, product="NAT Gateway", name="Standard Data Processed", unit="1 GB", region="Global")}
        report["pricing"] = {"collected_at_utc": now(), "currency": "USD", "price_type": "Consumption",
            "meters": meters, "nat_global_meter_not_us_government": True,
            "max_combined_resource_lifetime_minutes": 60, "max_per_probe_minutes": 10,
            "one_hour_fixed_resource_subtotal_usd": round(sum(meters[k]["retailPrice"] * quantity for k, quantity in
                (("aci_cpu", 1), ("aci_memory", 1.5), ("static_ipv4", 1), ("nat_hour", 1))), 6),
            "nat_data_usd_per_gb": meters["nat_data"]["retailPrice"],
            "all_in_estimate_usd": None, "billing_cap": False,
            "excluded_unincurred_costs": ["ACR remote build", "retained image storage", "image and other transfer"],
            "actual_runner_resource_cost_usd": 0, "creation_blocked_before_costs_incurred": True}
        report["probe_source_sha256"] = hashlib.sha256((ROOT / "scripts/deployment/finops_private_probe.py").read_bytes()).hexdigest()
        report["egress_review"] = {"postgres_tcp": "10.240.3.12/32:5432", "azure_dns_udp_tcp": "168.63.129.16/32:53",
            "linux_imds_tcp": "169.254.169.254/32:80", "https_candidates_not_deployed": ["AzureActiveDirectory",
                "AzureContainerRegistry.SoutheastAsia", "Storage.SoutheastAsia"],
            "blanket_internet_or_vnet_allowed": False, "platform_compatibility_verified": False}
        report["blocking_gate"] = {"label": "aci_nsg_platform_path_unresolved",
            "azure_resource_error": None, "kind": "unresolved_not_proven_required_nsg_inbound",
            "approval_missing": False, "approved_all_inbound_denied": True,
            "documented_port": 19390, "port_exception_added": False,
            "notes": "19390 portal WebSocket/client-firewall guidance does not establish a required subnet NSG ingress flow. No exception inferred; compatibility of this precise run-once no-listener topology remains unverified.",
            "sources": ["https://learn.microsoft.com/azure/container-instances/container-instances-egress-ip-address#configure-rules-on-the-firewall",
                        "https://learn.microsoft.com/azure/container-instances/container-instances-virtual-network-concepts#other-limitations",
                        "https://learn.microsoft.com/troubleshoot/azure/azure-container-instances/connectivity/web-socket-is-closed-or-could-not-be-opened"]}
        report["downstream_gates_not_executed"] = ["immutable_probe_build", "IaC_build_security_scan_validate_whatif",
            "independent_cleanup_controller_install_and_deadline_test", "sequential_private_mi_snapshots"]
        report["status"] = "approved_but_blocked_before_creation_by_platform_network_gate"
        g.platform_gate(all_inbound_denied=True, documented_management_port_required=True)
    except HTTPError as exc:
        report["exit_code"] = 2
        report["reason"] = "retail_price_http_error"
        report["price_http_status"] = exc.code
        report["status"] = "blocked_during_read_only_preflight"
        report["automatic_retry_performed"] = False
    except Exception as exc:
        report["exit_code"] = 2
        report["reason"] = str(exc) if isinstance(exc, g.GuardBlocked) else "sanitized_preflight_failure"
        if report["status"] == "collecting":
            report["status"] = "blocked_during_read_only_preflight"
    finally:
        report["finished_at_utc"] = now()
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: report.get(k) for k in ("status", "reason", "exit_code", "created_resource_ids",
                                                    "deleted_resource_ids", "private_probe_executed", "finished_at_utc")}), flush=True)
    return report.get("exit_code", 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-absence", action="store_true")
    args = parser.parse_args()
    raise SystemExit(verify_absence() if args.verify_absence else main())