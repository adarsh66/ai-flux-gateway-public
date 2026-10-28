"""Approved runner preparation only: prices, isolated package, ARM validate/what-if.

No provisioning, image upload, identity attachment, DELETE or database path.
Network validation deliberately remains possible with platform support unresolved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_preflight as p

ROOT = p.ROOT
FOLDER = ROOT / "infra/finops-runner"
OUT = ROOT / "gateway/validation/finops-runner-preparation-20261027.json"
SCHEMA = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rule(name, priority, direction, access, protocol, destination, port):
    return {"name": name, "properties": {"priority": priority, "direction": direction,
        "access": access, "protocol": protocol, "sourcePortRange": "*",
        "destinationPortRange": port, "sourceAddressPrefix": "*" if direction == "Inbound" else g.CIDR,
        "destinationAddressPrefix": destination}}


def network_template(nonce, *, profile="postgres"):
    g.require(profile in {"postgres", "ingestion_dataplane"}, "unreviewed_network_profile")
    ids = g.owned_ids(nonce)
    tags = {"finops-owner": nonce, "purpose": "temporary-read-only-finops-probe"}
    def resource(key, kind, props, **extras):
        return {"type": "Microsoft.Network/" + kind, "apiVersion": "2024-05-01",
            "name": ids[key].split("/providers/Microsoft.Network/")[1].split("/", 1)[1],
            "location": "southeastasia", "tags": tags, "properties": props, **extras}
    # Explicit user-approved exception. Learn's VNet limitations document
    # inbound VNet addresses and management TCP 19390; they do NOT document
    # AzureCloud/Internet as a required source or any application listening port.
    # Use the actual VNet prefix, not VirtualNetwork (which includes peers/UDRs).
    management = rule("AllowVnetManagement19390", 100, "Inbound", "Allow", "Tcp", g.CIDR, "19390")
    management["properties"]["sourceAddressPrefix"] = "10.240.0.0/16"
    rules = [management, rule("DenyAllInbound", 200, "Inbound", "Deny", "*", "*", "*")]
    for i, (name, protocol, dest, port) in enumerate([
        ("Postgres", "Tcp", "10.240.3.12/32", "5432"),
        ("DnsUdp", "Udp", "168.63.129.16/32", "53"),
        ("DnsTcp", "Tcp", "168.63.129.16/32", "53"),
        ("Imds", "Tcp", "169.254.169.254/32", "80"),
        ("Entra", "Tcp", "AzureActiveDirectory", "443"),
        ("Acr", "Tcp", "AzureContainerRegistry.SoutheastAsia", "443"),
        ("ImageLayers", "Tcp", "Storage.SoutheastAsia", "443"),
    ]):
        rules.append(rule("Allow" + name, 110 + i * 10, "Outbound", "Allow", protocol, dest, port))
    if profile == "ingestion_dataplane":
        # Existing ARM-verified host-storage PEs only; no VNet-wide HTTPS.
        for i, (name, destination) in enumerate((("HostBlob", "10.240.3.6/32"),
                ("HostQueue", "10.240.3.7/32"), ("HostTable", "10.240.3.8/32"),
                ("MonitorQuery", "AzureMonitor"))):
            rules.append(rule("Allow" + name, 210 + i * 10, "Outbound", "Allow", "Tcp", destination, "443"))
    rules.append(rule("DenyOtherOutbound", 4000, "Outbound", "Deny", "*", "*", "*"))
    resources = [resource("pip", "publicIPAddresses", {"publicIPAllocationMethod": "Static",
        "publicIPAddressVersion": "IPv4", "idleTimeoutInMinutes": 4}, sku={"name": "Standard", "tier": "Regional"}),
        resource("nsg", "networkSecurityGroups", {"securityRules": rules}),
        resource("nat", "natGateways", {"idleTimeoutInMinutes": 4, "publicIpAddresses": [{"id": ids["pip"]}]},
                 sku={"name": "Standard"}, dependsOn=[ids["pip"]])]
    resources.append({"type": "Microsoft.Network/virtualNetworks/subnets", "apiVersion": "2024-05-01",
        "name": "poc-ids-token-ex-vnet/" + ids["subnet"].rsplit("/", 1)[1],
        "dependsOn": [ids["nsg"], ids["nat"]], "properties": {"addressPrefix": g.CIDR,
        "defaultOutboundAccess": False, "networkSecurityGroup": {"id": ids["nsg"]},
        "natGateway": {"id": ids["nat"]}, "delegations": [{"name": "aci", "properties": {"serviceName": g.DELEGATION}}]}})
    return {"$schema": SCHEMA, "contentVersion": "1.0.0.0", "resources": resources}


def group_resource(nonce, phase, image, source_hash):
    g.require(phase in g.IDENTITIES, "invalid_phase")
    group = {"id": g.owned_ids(nonce)[phase], "type": "Microsoft.ContainerInstance/containerGroups",
        "apiVersion": "2023-05-01", "name": g.owned_ids(nonce)[phase].rsplit("/", 1)[1],
        "location": "southeastasia", "tags": {"finops-owner": nonce}, "identity": {
        "type": "UserAssigned", "userAssignedIdentities": {g.IDENTITIES[phase]: {}}}, "properties": {
        "osType": "Linux", "restartPolicy": "Never", "subnetIds": [{"id": g.owned_ids(nonce)["subnet"]}],
        "dnsConfig": {"nameServers": ["168.63.129.16"]}, "imageRegistryCredentials": [{
            "server": "pocidstokenexacr.azurecr.io", "identity": g.IDENTITIES[phase]}],
        "containers": [{"name": "probe", "properties": {"image": image,
            "command": ["python", "-I", "/probe/entrypoint.py", "--probe-sha256", source_hash, "--identity", phase],
            "resources": {"requests": {"cpu": 1, "memoryInGB": 1.5}, "limits": {"cpu": 1, "memoryInGB": 1.5}}}}]}}
    return group


def group_template(nonce, phase, image, source_hash):
    group = group_resource(nonce, phase, image, source_hash)
    g.guard_probe_group(group, nonce=nonce, phase=phase, image=image, source_hash=source_hash, prior_group_absent=True)
    del group["id"]
    return {"$schema": SCHEMA, "contentVersion": "1.0.0.0", "resources": [group]}


def unbound_group_templates(nonce):
    """Offline shape/schema scan only. No fake image digest or deployment claim."""
    source_hash = digest(ROOT / "scripts/deployment/finops_private_probe.py")
    results = {}
    for phase in g.IDENTITIES:
        resource = group_resource(nonce, phase,
            "[concat('pocidstokenexacr.azurecr.io/aiflux-finops-probe@sha256:', parameters('verifiedImageDigest'))]", source_hash)
        del resource["id"]
        template = {"$schema": SCHEMA, "contentVersion": "1.0.0.0",
            "metadata": {"status": "unbound_offline_shape_only_not_validated_for_apply"},
            "parameters": {"verifiedImageDigest": {"type": "string", "minLength": 64, "maxLength": 64,
                "metadata": {"description": "No default; execution requires real Linux build digest and source/dependency proof."}}},
            "resources": [resource]}
        path = FOLDER / (phase + ".unbound.arm.json")
        path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
        results[phase] = {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path),
            "image_digest": None, "arm_validate_run": False, "what_if_run": False,
            "prior_group_absence_must_be_verified_before_binding": True, "apply_ready": False}
    return results


def guard_network(template, nonce, *, profile="postgres"):
    """Byte-structural exact allowlist: catches any ingress or wider egress edit."""
    g.require(template == network_template(nonce, profile=profile), "network_template_changed")
    return True


def package(nonce):
    folder = ROOT / ".deployment/finops-runner" / nonce / "image-context"
    folder.mkdir(parents=True, exist_ok=True)
    sources = {"Dockerfile": FOLDER / "Dockerfile", "requirements.txt": FOLDER / "requirements.txt",
        "entrypoint.py": FOLDER / "entrypoint.py", "finops_private_probe.py": ROOT / "scripts/deployment/finops_private_probe.py"}
    for name, path in sources.items():
        shutil.copyfile(path, folder / name)
    g.require({x.name for x in folder.iterdir()} <= set(sources) | {"wheels", "requirements.lock.txt"}, "unreviewed_image_context_files")
    return {"context": str(folder.relative_to(ROOT)).replace("\\", "/"),
        "files_sha256": {name: digest(path) for name, path in sources.items()},
        "built": False, "pushed": False, "immutable_image": None,
        "top_level_dependencies_pinned": True, "transitive_lock_and_linux_build_verified": False}


def lock_image(nonce):
    """Download Linux wheels with verified TLS; no cloud build or image upload."""
    context = ROOT / ".deployment/finops-runner" / nonce / "image-context"
    wheels = context / "wheels"
    wheels.mkdir(exist_ok=True)
    result = subprocess.run([sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
        "--cert", p.CA, "--only-binary=:all:", "--platform", "manylinux2014_x86_64",
        "--platform", "manylinux_2_28_x86_64", "--python-version", "313", "--implementation", "cp", "--abi", "cp313",
        "--dest", str(wheels), "-r", str(FOLDER / "requirements.txt")],
        capture_output=True, text=True, env=p.ENV, timeout=180)
    g.require(result.returncode == 0, "linux_wheel_resolution_failed")
    from packaging.utils import parse_wheel_filename
    entries, files = [], {}
    packages = set()
    for path in sorted(wheels.iterdir()):
        g.require(path.suffix == ".whl", "nonwheel_dependency")
        name, version, _, _ = parse_wheel_filename(path.name)
        g.require(name not in packages, "duplicate_dependency_version")
        packages.add(name)
        entries.append(f"{name}=={version} --hash=sha256:{digest(path)}")
        files[path.name] = {"sha256": digest(path), "bytes": path.stat().st_size}
    g.require({"azure-identity", "psycopg", "psycopg-binary", "sqlalchemy"} <= packages, "missing_image_dependency")
    lock = context / "requirements.lock.txt"
    lock.write_text("\n".join(entries) + "\n", encoding="utf-8")
    tls = ssl.create_default_context(cafile=p.CA)
    with urlopen("https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull", context=tls, timeout=30) as response:
        token = json.load(response)["token"]
    request = Request("https://registry-1.docker.io/v2/library/python/manifests/3.13-slim-bookworm", headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"})
    with urlopen(request, context=tls, timeout=30) as response:
        manifest = json.load(response)
    platforms = [x for x in manifest["manifests"] if x.get("platform", {}).get("os") == "linux" and x["platform"].get("architecture") == "amd64"]
    g.require(len(platforms) == 1, "base_platform_ambiguous")
    base = "python@" + platforms[0]["digest"]
    g.require(platforms[0]["digest"] in (FOLDER / "Dockerfile").read_text(encoding="utf-8"), "pinned_base_digest_not_current_manifest")
    return {"at_utc": p.now(), "linux_target": "linux/amd64 CPython 3.13", "base_image": base,
        "base_digest_observed_from_verified_registry_manifest": True, "lock_sha256": digest(lock),
        "wheel_count": len(files), "wheels": files, "total_wheel_bytes": sum(x["bytes"] for x in files.values()),
        "dependencies_downloaded_not_executed_on_linux": True, "linux_build_passed": False,
        "cloud_build_runs": 0, "image_pushed": False}


def collect_prices():
    """Two narrow fresh requests, finite pagination; stop on 429, no tight retries."""
    rows = p.prices("serviceName eq 'Container Registry' and armRegionName eq 'southeastasia' and priceType eq 'Consumption'")
    keys = ("productName", "skuName", "meterName", "unitOfMeasure", "armRegionName", "retailPrice",
            "tierMinimumUnits", "meterId", "effectiveStartDate", "currencyCode", "type")
    acr = [{k: row.get(k) for k in keys} for row in rows if row.get("skuName") == "Basic"]
    build = [x for x in acr if x["meterName"] == "Task vCPU Duration" and x["unitOfMeasure"] == "1 Second" and x["retailPrice"] > 0]
    storage = [x for x in acr if x["meterName"] == "Data Stored" and x["unitOfMeasure"] == "1 GB/Month"]
    g.require(len(build) == len(storage) == 1, "acr_meter_ambiguous")
    rows = p.prices("serviceName eq 'Bandwidth' and armRegionName eq 'southeastasia' and priceType eq 'Consumption'")
    transfer = [{k: row.get(k) for k in keys} for row in rows if row.get("productName") == "Rtn Preference: MGN" and row.get("meterName") == "Standard Data Transfer Out" and row.get("retailPrice", 0) > 0]
    # Retail names the standard Microsoft global network routing product MGN.
    g.require(transfer and all(x["unitOfMeasure"] == "1 GB" for x in transfer), "bandwidth_meter_missing")
    rate = max(x["retailPrice"] for x in transfer)
    prior = json.loads(p.OUT.read_text(encoding="utf-8"))["verified_same_session_price_observations"]
    fixed = prior["one_combined_hour_cpu_1_memory_gib_1_5_with_nat_and_ip_subtotal_usd"]
    # Upper scenario, NOT a metered cap: 2 vCPU x 15min build, <=1GB retained 30d,
    # <=2GB NAT transfer, <=2GB charged egress despite same-region image pulls.
    components = {"aci_nat_ip_one_combined_hour": fixed,
        "acr_build_1800_vcpu_seconds": build[0]["retailPrice"] * 1800,
        "image_storage_one_gb_30_days_conservative_overage": storage[0]["retailPrice"],
        "nat_data_two_gb": prior["additional_nat_data_usd_per_gb"] * 2,
        "charged_transfer_two_gb_conservative": rate * 2,
        "existing_private_endpoint_two_gb_in_plus_two_gb_out": 0.01 * 4,
        "inter_zone_one_gb_each_direction_conservative": 0.01 * 2}
    return {"collected_at_utc": p.now(), "currency": "USD", "acr_basic_meters": acr,
        "bandwidth_meters": transfer, "components_usd": components,
        "all_in_scenario_estimate_usd": round(sum(components.values()), 6),
        "existing_basic_registry_sku_incremental_cost_usd": 0,
        "uses_paid_build_tier_even_if_free_quota_remaining": True,
        "assumptions": {"combined_network_and_aci_minutes": 60, "probe_minutes_each": 10,
            "one_build_vcpu": 2, "build_timeout_seconds": 900, "max_compressed_image_gb": 1,
            "retained_image_days_priced": 30, "nat_transfer_gb": 2, "charged_egress_gb": 2},
        "private_link_rate_source": "https://azure.microsoft.com/en-us/pricing/details/private-link/",
        "private_link_rate_usd_per_gb_each_direction": 0.01,
        "zone_rate_source": "fresh Bandwidth Rtn Preference: MGN Standard Inter-Availability Zone meters, southeastasia",
        "hard_billing_cap": False, "no_inference_calls": True,
        "residuals": ["taxes/contract currency not quoted", "cleanup or build cancellation failure can exceed scenario",
            "image retained beyond 30 days continues storage overage if baseline allowance exhausted",
            "dependency/base downloads are inbound; source upload and ARM JSON are small; no log workspace or disk created",
            "preexisting registry/private endpoint/DNS/DB hourly baseline excluded; small query/ARM/DNS use covered by contingency only"],
        "planning_contingency_usd": 1.0,
        "planning_envelope_with_contingency_usd": round(sum(components.values()) + 1.0, 6)}


def validation(template_path, nonce, baseline_ids):
    results = {}
    for action in ("validate", "what-if"):
        args = [p.AZ, "deployment", "group", action, "--resource-group", "IDS-TOKEN-EXCHANGE-POC",
            "--name", "finops-probe-" + nonce + "-network-preview", "--mode", "Incremental",
            "--template-file", str(template_path), "--subscription", g.SUB, "--only-show-errors", "-o", "json"]
        if action == "what-if":
            args.extend(["--no-pretty-print", "--result-format", "FullResourcePayloads"])
        child = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=p.ENV, timeout=240)
        result = {"exit_code": child.returncode, "cloud_resource_create": False}
        try:
            value = json.loads(child.stdout)
        except Exception:
            value = None
        if child.returncode == 0 and isinstance(value, dict):
            if action == "what-if":
                result["status"] = value.get("status")
                result["changes"] = [{"resourceId": c.get("resourceId"), "changeType": c.get("changeType")} for c in value.get("changes", [])]
                try:
                    result["exact_create_only_guard_passed"] = g.guard_what_if(value, nonce, "network", baseline_ids=baseline_ids)
                except g.GuardBlocked:
                    result["exact_create_only_guard_passed"] = False
            else:
                result["provisioning_state"] = value.get("properties", {}).get("provisioningState")
                result["validation_returned_without_error"] = not value.get("error")
        else:
            # Only known labels; no arbitrary stdout/stderr in committed evidence.
            codes = ("AuthorizationFailed", "InvalidTemplate", "InvalidResourceReference", "InvalidRequestContent",
                     "RequestDisallowedByPolicy", "InvalidApiVersionParameter", "InvalidResourceType", "MissingSubscriptionRegistration")
            result["error_codes"] = [code for code in codes if code in child.stderr or code in child.stdout]
            result["reason"] = "validation_failed_or_unparseable"
        results[action] = result
    return results


def security_scan():
    tools = ROOT / ".deployment/finops-runner/security-tools"
    executable = tools / "bin/checkov"
    g.require(executable.is_file(), "isolated_checkov_missing")
    env = {**p.ENV, "PYTHONPATH": str(tools), "CKV_SKIP_UPDATE_CHECK": "true", "LOG_LEVEL": "ERROR"}
    env.pop("BC_API_KEY", None)
    names = ["network.arm.json", "Dockerfile"] + [phase + ".unbound.arm.json" for phase in g.IDENTITIES
        if (FOLDER / (phase + ".unbound.arm.json")).is_file()]
    file_args = [arg for name in names for arg in ("--file", str(FOLDER / name))]
    result = subprocess.run([sys.executable, str(executable), *file_args, "--framework", "arm", "dockerfile", "--skip-download",
        "--output", "json", "--quiet", "--compact"],
        capture_output=True, text=True, env=env, timeout=180)
    report = {"at_utc": p.now(), "scanner": "checkov==3.2.495", "exit_code": result.returncode,
        "cloud_operations": False, "remote_policy_downloads": False, "api_key_forwarded": False,
        "artifacts_sha256": {name: digest(FOLDER / name) for name in names},
        "security_gate_passed": False}
    try:
        values = json.loads(result.stdout)
        values = values if isinstance(values, list) else [values]
        report["frameworks"] = [{"check_type": item["check_type"], "summary": item["summary"],
            "failures": [{key: check.get(key) for key in ("check_id", "check_name", "resource", "severity")}
                         for check in item["results"].get("failed_checks", [])]} for item in values]
        report["security_gate_passed"] = (result.returncode == 0 and bool(values)
            and all(item["summary"].get("failed", 0) == 0 and item["summary"].get("parsing_errors", 0) == 0 for item in values)
            and sum(item["summary"].get("passed", 0) for item in values) > 0)
    except Exception:
        report["reason"] = "scanner_failed_or_unparseable"
    return report


def preservation_readback():
    account = p.cli(["account", "show"])
    g.require(account["id"] == g.SUB and account["tenantId"] == g.TENANT, "account_scope_mismatch")
    pg_id = g.RG + "/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg"
    pg = p.get(pg_id, "2024-08-01")
    rules = p.get(pg_id + "/firewallRules", "2024-08-01")["value"]
    storage = p.get(g.RG + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex", "2023-05-01")
    acl = storage["properties"]["networkAcls"]
    ips = sorted(x["value"] for x in acl.get("ipRules", []))
    network = pg["properties"]["network"]
    g.require(network["publicNetworkAccess"] == "Disabled" and not rules, "postgres_containment_changed")
    g.require(acl["defaultAction"] == "Deny" and ips == ["167.103.65.36", "167.103.66.248", "167.103.66.93"], "approved_state_acl_changed")
    return {"at_utc": p.now(), "postgres_public_network_access": network["publicNetworkAccess"],
        "postgres_firewall_rule_count": len(rules), "state_storage_default_action": acl["defaultAction"],
        "state_storage_approved_ips": ips, "configuration_writes": 0, "preservation_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", action="store_true")
    parser.add_argument("--validate-network", action="store_true")
    parser.add_argument("--lock-image", action="store_true")
    parser.add_argument("--scan-security", action="store_true")
    parser.add_argument("--verify-preservation", action="store_true")
    parser.add_argument("--prepare-unbound-groups", action="store_true")
    args = parser.parse_args()
    prior = json.loads(p.OUT.read_text(encoding="utf-8"))
    nonce = prior["owner_nonce"]
    report = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    report.update({"updated_at_utc": p.now(), "approval_retained": True, "owner_nonce": nonce,
        "resource_creates": 0, "identity_attachments": 0, "database_probe_exits": {"ingestion": None, "api": None},
        "platform_support_status": "approved_vnet_only_tcp19390_runtime_not_yet_tested",
        "port_exception_added": True, "approval_missing": False})
    try:
        template = network_template(nonce)
        guard_network(template, nonce)
        path = FOLDER / "network.arm.json"
        path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
        report["network_template"] = {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path),
            "structural_guard_passed": True, "new_resource_ids": {k: v for k, v in g.owned_ids(nonce).items() if k not in g.IDENTITIES},
            "inbound": "10.240.0.0/16_to_10.240.5.0/24_tcp19390_priority100_then_deny_all_priority200",
            "platform_port_allow_added": True, "application_ports": [], "apply_ready": False,
            "documentation": ["https://learn.microsoft.com/azure/container-instances/container-instances-virtual-network-concepts#other-limitations",
                "https://learn.microsoft.com/azure/container-instances/container-instances-egress-ip-address#configure-rules-on-the-firewall"],
            "scope_note": "VNet CIDR only, not Internet/AzureCloud/expanded VirtualNetwork tag; no claim that docs prove this NSG path sufficient."}
        report["image_package"] = package(nonce)
        if args.prepare_unbound_groups:
            report["unbound_group_templates"] = unbound_group_templates(nonce)
        if args.lock_image:
            try:
                report["image_dependency_lock"] = lock_image(nonce)
            except Exception as exc:
                report["image_dependency_lock_attempt"] = {"at_utc": p.now(), "reason": str(exc) if isinstance(exc, g.GuardBlocked) else "dependency_lock_failed",
                    "http_status": exc.code if isinstance(exc, HTTPError) else None}
        if args.scan_security:
            if "security_scan" in report:
                report.setdefault("security_scan_history", []).append(report["security_scan"])
            report["security_scan"] = security_scan()
        if args.verify_preservation:
            report["preservation"] = preservation_readback()
        if args.prices:
            try:
                report["pricing"] = collect_prices()
            except Exception as exc:
                report["pricing_attempt"] = {"at_utc": p.now(), "reason": str(exc) if isinstance(exc, g.GuardBlocked) else "price_query_failed",
                    "http_status": exc.code if isinstance(exc, HTTPError) else None, "automatic_retry": False}
        if args.validate_network:
            account = p.cli(["account", "show"])
            g.require(account["id"] == g.SUB and account["tenantId"] == g.TENANT and account["user"]["name"] == "xv.puneet.devadiga@singtel.com", "account_scope_mismatch")
            report["fresh_network_capacity"] = g.network_capacity(p.get(g.VNET, "2024-05-01"))
            inventory = p.cli(["resource", "list", "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--query", "[].id"])
            report["preview_baseline"] = {"at_utc": p.now(), "resource_ids": inventory}
            report["arm_network_preview"] = validation(path, nonce, inventory)
        report["preparation_exit_code"] = 0
    except Exception as exc:
        report["preparation_exit_code"] = 2
        report["reason"] = str(exc) if isinstance(exc, g.GuardBlocked) else "preparation_failed"
    finally:
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report), flush=True)
    return report["preparation_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())