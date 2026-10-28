"""Pure fail-closed guards for the approved temporary FinOps runner.

No provisioning entrypoint. In particular, a successful ARM what-if is not
evidence that deny-all ingress supports ACI's platform management channel.
Cleanup accepts injected GET/DELETE operations so ownership is testable offline;
this module does not install or claim an independent cleanup controller.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re

SUB = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
TENANT = "beb276ac-6e9f-498e-8e31-019ee666decd"
RG = f"/subscriptions/{SUB}/resourceGroups/IDS-TOKEN-EXCHANGE-POC"
VNET = RG + "/providers/Microsoft.Network/virtualNetworks/poc-ids-token-ex-vnet"
SUBNET = VNET + "/subnets/poc-ids-token-ex-finops-probe"
CIDR = "10.240.5.0/24"
DELEGATION = "Microsoft.ContainerInstance/containerGroups"
MI_PREFIX = RG + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/"
IDENTITIES = {
    "ingestion": MI_PREFIX + "poc-ids-token-ex-ingestion-identity",
    "api": MI_PREFIX + "poc-ids-token-ex-api-identity",
}


class GuardBlocked(ValueError):
    """Fixed labels only; never raw provider/SQL/identity output."""


def require(condition, label):
    if not condition:
        raise GuardBlocked(label)


def owned_ids(nonce):
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{12}", nonce), "invalid_owner_nonce")
    prefix = "poc-ids-token-ex-finops-probe-" + nonce
    return {
        "ingestion": RG + "/providers/Microsoft.ContainerInstance/containerGroups/" + prefix + "-ingestion",
        "api": RG + "/providers/Microsoft.ContainerInstance/containerGroups/" + prefix + "-api",
        # Preserve the already-running legacy reaper's exact ID mapping only.
        # Every later session has a different subnet ARM ID as well as tags.
        "subnet": SUBNET if nonce == "2f75015b55d1" else VNET + "/subnets/" + prefix + "-subnet",
        "nsg": RG + "/providers/Microsoft.Network/networkSecurityGroups/" + prefix + "-nsg",
        "nat": RG + "/providers/Microsoft.Network/natGateways/" + prefix + "-nat",
        "pip": RG + "/providers/Microsoft.Network/publicIPAddresses/" + prefix + "-pip",
    }


def network_capacity(vnet):
    """Fresh address-space/subnet collision check; never infer empty == unowned."""
    require(vnet.get("id", "").lower() == VNET.lower(), "wrong_vnet")
    require(vnet.get("location") == "southeastasia", "wrong_region")
    props = vnet["properties"]
    proposed = ipaddress.ip_network(CIDR)
    require(any(proposed.subnet_of(ipaddress.ip_network(p))
                for p in props["addressSpace"]["addressPrefixes"]), "outside_vnet")
    for subnet in props.get("subnets", []):
        require(subnet.get("id", "").lower() != SUBNET.lower(), "subnet_name_collision")
        s = subnet["properties"]
        prefixes = s.get("addressPrefixes") or [s["addressPrefix"]]
        require(not any(proposed.overlaps(ipaddress.ip_network(p)) for p in prefixes), "subnet_cidr_collision")
    return {"cidr": CIDR, "usable_addresses_after_azure_reservation": proposed.num_addresses - 5,
            "existing_subnets": len(props.get("subnets", [])), "collision": False}


def guard_what_if(value, nonce, phase, *, baseline_ids=()):
    """Only exact CREATEs; reject existing-resource changes and unexpanded plans."""
    ids = owned_ids(nonce)
    require(phase in {"network", "ingestion", "api"}, "invalid_phase")
    expected = {ids[k].lower() for k in ("subnet", "nsg", "nat", "pip")} if phase == "network" else {ids[phase].lower()}
    require(value.get("status") == "Succeeded" and not value.get("error"), "what_if_failed")
    seen = set()
    baseline = {rid.lower() for rid in baseline_ids}
    for change in value.get("changes", []):
        rid = change.get("resourceId", "").lower()
        # Incremental ARM previews report untouched preexisting objects as Ignore.
        # Accept ONLY a freshly inventoried object, never Ignore on a planned ID.
        if change.get("changeType") == "Ignore":
            require(rid in baseline and rid not in expected and not change.get("delta"),
                    "unverified_ignored_resource")
            continue
        require(rid in expected and change.get("changeType") == "Create", "foreign_or_existing_change")
        require(rid not in seen and not change.get("before"), "resource_collision")
        seen.add(rid)
    require(seen == expected, "incomplete_plan")
    return True


def guard_private_ip(value):
    """Accept omitted terminal metadata or ARM's private IPv4 readback, not a listener."""
    if value is None:
        return
    require(isinstance(value, dict) and set(value) <= {"type", "ports", "ip"}, "published_ports")
    require(value.get("type") == "Private" and value.get("ports") in (None, []), "published_ports")
    address = value.get("ip")
    if address is not None:
        require(isinstance(address, str), "invalid_private_ip")
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            raise GuardBlocked("invalid_private_ip") from None
        require(parsed.version == 4 and parsed in ipaddress.ip_network(CIDR), "invalid_private_ip")


def guard_probe_group(group, *, nonce, phase, image, source_hash, prior_group_absent):
    """Bind the only MI, immutable image and reviewed no-server entrypoint."""
    ids = owned_ids(nonce)
    require(phase in IDENTITIES, "invalid_phase")
    require(prior_group_absent is True, "previous_identity_still_attached")
    require(group.get("id", "").lower() == ids[phase].lower(), "foreign_group")
    require(group.get("location") == "southeastasia", "wrong_region")
    require(re.fullmatch(r"pocidstokenexacr\.azurecr\.io/aiflux-finops-probe@sha256:[0-9a-f]{64}", image), "mutable_or_foreign_image")
    require(re.fullmatch(r"[0-9a-f]{64}", source_hash), "invalid_probe_hash")
    identity = group.get("identity", {})
    require(identity.get("type") == "UserAssigned" and
            {key.lower() for key in identity.get("userAssignedIdentities", {})} == {IDENTITIES[phase].lower()}, "wrong_identity_attachment")
    props = group["properties"]
    require(props.get("osType") == "Linux" and props.get("restartPolicy") == "Never", "runtime_policy")
    require(len(props.get("subnetIds", [])) == 1 and
            props["subnetIds"][0].get("id", "").lower() == ids["subnet"].lower(), "wrong_subnet")
    require(not any(props.get(k) for k in ("volumes", "diagnostics", "initContainers", "extensions")), "extra_runtime_surface")
    guard_private_ip(props.get("ipAddress"))
    require(props.get("dnsConfig") == {"nameServers": ["168.63.129.16"]}, "unapproved_dns")
    registry = props.get("imageRegistryCredentials", [])
    require(len(registry) == 1 and registry[0].get("server") == "pocidstokenexacr.azurecr.io" and
            registry[0].get("identity", "").lower() == IDENTITIES[phase].lower() and
            not registry[0].get("username") and not registry[0].get("password"), "registry_auth")
    containers = props.get("containers", [])
    require(len(containers) == 1, "extra_container")
    container = containers[0]["properties"]
    require(container.get("image") == image and container.get("command") ==
            ["python", "-I", "/probe/entrypoint.py", "--probe-sha256", source_hash, "--identity", phase], "unreviewed_entrypoint")
    require(container.get("resources") == {"requests": {"cpu": 1, "memoryInGB": 1.5},
                                          "limits": {"cpu": 1, "memoryInGB": 1.5}}, "resource_limit")
    require(not any(container.get(k) for k in ("ports", "volumeMounts", "environmentVariables",
                                              "livenessProbe", "readinessProbe")), "unreviewed_container_options")
    return True


def verify_source(content, expected):
    require(hashlib.sha256(content).hexdigest() == expected, "probe_source_changed")


def owned_resource(resource, *, nonce, key, journal):
    """Subnets cannot be tagged: require exact owned associations and journal proof."""
    ids = owned_ids(nonce)
    require(key in ids, "foreign_cleanup_key")
    require(journal.get("owner_nonce") == nonce and journal.get("baseline_absent", {}).get(key) is True
            and key in journal.get("write_intents", []), "missing_ownership_journal")
    require(resource.get("id", "").lower() == ids[key].lower(), "foreign_cleanup_id")
    if key == "subnet":
        p = resource["properties"]
        require(p.get("addressPrefix") == CIDR and p.get("defaultOutboundAccess") is False,
                "changed_subnet")
        require([d["properties"]["serviceName"] for d in p.get("delegations", [])] == [DELEGATION],
                "changed_delegation")
        require(p.get("natGateway", {}).get("id", "").lower() == ids["nat"].lower() and
                p.get("networkSecurityGroup", {}).get("id", "").lower() == ids["nsg"].lower() and
                not p.get("routeTable") and not p.get("privateEndpoints") and not p.get("ipConfigurations"),
                "changed_subnet_associations")
    else:
        require(resource.get("tags", {}).get("finops-owner") == nonce, "foreign_cleanup_owner")
        require(resource.get("location") == "southeastasia", "foreign_cleanup_region")
        # Ownership alone is insufficient if another workload has adopted the object.
        p = resource.get("properties", {})
        require(not p.get("ipConfigurations") and not p.get("networkInterfaces"), "resource_in_use")
        require(all(s.get("id", "").lower() == ids["subnet"].lower() for s in p.get("subnets", [])),
                "foreign_subnet_association")
        if key == "pip":
            require(not p.get("natGateway") or p["natGateway"].get("id", "").lower() == ids["nat"].lower(),
                    "foreign_nat_association")
    return True


def cleanup_owned(*, nonce, journal, get_resource, delete_resource):
    """Fail closed before ANY delete if one existing object lacks ownership proof.

    get_resource returns None ONLY for an independently verified HTTP 404. Any
    timeout, authorization denial or provider error must raise, not return None.
    delete_resource must finish its operation; each deletion is followed by GET.
    """
    ids = owned_ids(nonce)
    order = ("ingestion", "api", "subnet", "nsg", "nat", "pip")
    for key in order:
        resource = get_resource(ids[key])
        if resource is not None:
            owned_resource(resource, nonce=nonce, key=key, journal=journal)
    deleted = []
    for key in order:
        resource = get_resource(ids[key])
        if resource is None:
            continue
        owned_resource(resource, nonce=nonce, key=key, journal=journal)
        delete_resource(ids[key])
        require(get_resource(ids[key]) is None, "cleanup_not_absent")
        deleted.append(ids[key])
    require(all(get_resource(rid) is None for rid in ids.values()), "cleanup_final_get_failed")
    return deleted


def platform_gate(*, all_inbound_denied, documented_management_port_required,
                  requirement_applies_to_subnet_nsg=None):
    # Portal/client WebSocket firewall guidance alone is not subnet NSG proof.
    require(requirement_applies_to_subnet_nsg is not None, "aci_nsg_platform_path_unresolved")
    require(not (all_inbound_denied and documented_management_port_required and requirement_applies_to_subnet_nsg),
            "aci_platform_19390_conflicts_with_deny_all_inbound")


def safe_probe_failure(value):
    """Never return arbitrary container logs, driver errors, claim IDs or fields."""
    require(set(value) == {"status", "reason", "sqlstate", "database_writes", "replay_authorized"},
            "unreviewed_probe_output")
    require(value["status"] == "blocked" and value["database_writes"] == 0 and
            value["replay_authorized"] is False, "invalid_probe_result")
    require(value["reason"] in {"deadline_exceeded", "probe_source_changed", "private_endpoint_mismatch",
                                "managed_identity_claims", "unverified_runtime_failure"}, "unreviewed_failure_reason")
    require(value["sqlstate"] is None or re.fullmatch(r"[A-Z0-9]{5}", value["sqlstate"]), "unreviewed_sqlstate")
    return dict(value)