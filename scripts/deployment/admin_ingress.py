"""Explicit-CIDR, fail-closed App Service ingress. No discovery of operator IPs.

The reusable operation changes only a site's public switch and access rules.
The CLI is deliberately scoped to the existing admin; no settings/credentials,
private endpoints, customer/API/SQL changes, role grants or resource creation.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re

from scripts.deployment import deploy_portals as portals
from scripts.deployment import run_private_sql as runner

WEB = portals.WEB
LEGACY_ADMIN = "sha256:82e2cd7b36d6da18288c939b02532f361a6ac414661e8e8ae10b995c26ed9be3"
# Conservative exclusions: reject entire special-purpose blocks, even where
# IANA defines individual globally reachable exceptions within them.
SPECIAL = tuple(ipaddress.ip_network(x) for x in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
    "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/3",
    "2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20",
))


def public_cidrs(values: list[str]) -> list[str]:
    """Require explicit canonical CIDRs; never widen a host address/network."""
    if not values or len(values) > 500:
        raise runner.RunnerError("explicit_public_cidrs_required")
    result = []
    for value in values:
        try:
            if not isinstance(value, str) or "/" not in value or "%" in value:
                raise ValueError
            network = ipaddress.ip_network(value, strict=True)
            if (value != str(network) or network.prefixlen == 0 or not network.is_global
                    or not network.network_address.is_global or not network.broadcast_address.is_global
                    or any(network.version == block.version and network.overlaps(block) for block in SPECIAL)
                    or (network.version == 6 and not network.subnet_of(ipaddress.ip_network("2000::/3")))):
                raise ValueError
        except (ValueError, TypeError):
            raise runner.RunnerError("invalid_public_cidr") from None
        if str(network) not in result:
            result.append(str(network))
    return result


def restriction_properties(cidrs: list[str]) -> dict:
    return {
        "ipSecurityRestrictionsDefaultAction": "Deny",
        "ipSecurityRestrictions": [
            {"name": f"operator-{i}", "ipAddress": cidr, "action": "Allow", "priority": 100 + i}
            for i, cidr in enumerate(cidrs)
        ] + [{"name": "Deny all", "ipAddress": "Any", "action": "Deny", "priority": 2147483647}],
        "scmIpSecurityRestrictionsUseMain": False,
        "scmIpSecurityRestrictionsDefaultAction": "Deny",
        "scmIpSecurityRestrictions": [
            {"name": "Deny all", "ipAddress": "Any", "action": "Deny", "priority": 2147483647}
        ],
    }


def verify_rules(config: dict, cidrs: list[str]) -> None:
    expected = restriction_properties(cidrs)
    for key in ("ipSecurityRestrictionsDefaultAction", "scmIpSecurityRestrictionsDefaultAction",
                "scmIpSecurityRestrictionsUseMain"):
        portals.require(config.get(key) == expected[key], "ingress_defaults_mismatch")
    for key in ("ipSecurityRestrictions", "scmIpSecurityRestrictions"):
        actual = config.get(key)
        portals.require(isinstance(actual, list) and len(actual) == len(expected[key]), "ingress_rules_mismatch")
        # ARM may append description/tag metadata. Reject alternate selectors,
        # headers, multi-source values or changed priorities/actions explicitly.
        for rule, wanted in zip(sorted(actual, key=lambda x: x.get("priority", 0)), expected[key]):
            portals.require(all(rule.get(k) == v for k, v in wanted.items()) and
                            not any(rule.get(k) for k in ("headers", "vnetSubnetResourceId", "subnetMask")) and
                            rule.get("tag") in (None, "Default"), "ingress_rules_mismatch")


def set_public(arm: runner.Arm, resource: str, state: str) -> None:
    arm.request("PATCH", resource, WEB, {"properties": {"publicNetworkAccess": state}})
    portals.require(arm.get(resource, WEB)["properties"].get("publicNetworkAccess") == state,
                    "public_switch_not_confirmed")


def configure_ingress(arm: runner.Arm, resource: str, values: list[str]) -> dict:
    # Complete validation before any Azure read/write; missing input is a no-op.
    cidrs = public_cidrs(values)
    portals.require(re.fullmatch(r"/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[^/]+/providers/"
                                r"Microsoft.Web/sites/[a-zA-Z0-9-]+", resource), "site_resource_required")
    try:
        app = arm.get(resource, WEB)
        portals.require(app and app["properties"].get("httpsOnly") is True, "https_only_required")
        # Even a previously public site is closed before replacing any rules.
        set_public(arm, resource, "Disabled")
        arm.request("PATCH", resource + "/config/web", WEB,
                    {"properties": restriction_properties(cidrs)})
        verify_rules(arm.get(resource + "/config/web", WEB)["properties"], cidrs)
        portals.require(arm.get(resource, WEB)["properties"].get("publicNetworkAccess") == "Disabled",
                        "public_changed_before_enable")
        # Only the successfully read-back deny/allow config can precede Enabled.
        set_public(arm, resource, "Enabled")
        verify_rules(arm.get(resource + "/config/web", WEB)["properties"], cidrs)
    except BaseException:
        # Do not restore an unsafe prior public state. Also covers interrupted
        # writes and success-at-server/timeout-at-client outcomes.
        try:
            set_public(arm, resource, "Disabled")
        except BaseException:
            raise runner.RunnerError("ingress_failed_rollback_unconfirmed") from None
        raise runner.RunnerError("ingress_failed_public_disabled") from None
    return {"public": "Enabled", "main_default": "Deny", "allowed_cidrs": cidrs,
            "scm_default": "Deny", "scm_use_main": False, "scm_allows": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-cidr", action="append", required=True,
                        help="Operator-specified canonical public CIDR; repeat for each range")
    parser.add_argument("--apply", action="store_true", help="Explicitly enable verified allowlisted ingress")
    parser.add_argument("--admin-image-digest", help="Independently validated same-origin admin release digest")
    args = parser.parse_args()
    try:
        cidrs = public_cidrs(args.allow_cidr)
        if not args.apply:
            print(json.dumps({"status": "validated_input_only", "allowed_cidrs": cidrs, "azure_changed": False}))
            return 0
        portals.require(args.admin_image_digest and
                        re.fullmatch(r"sha256:[a-f0-9]{64}", args.admin_image_digest) and
                        args.admin_image_digest != LEGACY_ADMIN, "same_origin_admin_release_required")
        redactor = runner.Redactor()
        account = runner.cli(["account", "show"], redactor)
        portals.require(account["id"] == runner.SUB and account["tenantId"] == runner.TENANT and
                        account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_mismatch")
        arm = runner.Arm(redactor)
        # This CLI is admin-only. Do not use the reusable function on API/SQL/customer.
        app = arm.get(portals.site("admin"), WEB)
        config = arm.get(portals.site("admin") + "/config/web", WEB)["properties"]
        portals.network_proof(arm, "admin", app, config)
        portals.require((app["properties"].get("virtualNetworkSubnetId") or "").lower() == portals.INTEGRATION.lower(),
                        "admin_private_api_route_required")
        # A new same-origin image must be independently built/validated/deployed
        # while private; the known direct-API r1 must never be publicly enabled.
        portals.require(config.get("linuxFxVersion") == "DOCKER|" + runner.REGISTRY_HOST +
                        "/aiflux-admin@" + args.admin_image_digest and
                        config.get("acrUseManagedIdentityCreds") is True and
                        config.get("acrUserManagedIdentityID") == portals.CLIENTS["admin"],
                        "same_origin_admin_release_required")
        portals.network_proof(arm, "api", arm.get(portals.site("api"), WEB),
                              arm.get(portals.site("api") + "/config/web", WEB)["properties"])
        portals.require(arm.get(runner.SQL, "2023-08-01")["properties"].get("publicNetworkAccess") == "Disabled",
                        "sql_public_exposed")
        print(json.dumps(configure_ingress(arm, portals.site("admin"), cidrs)))
        return 0
    except runner.RunnerError as exc:
        print(json.dumps({"status": "failed", "code": exc.code}))
        return 1
    except Exception:
        print(json.dumps({"status": "failed", "code": "unexpected_error"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())