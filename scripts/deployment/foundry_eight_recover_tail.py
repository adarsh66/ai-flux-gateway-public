"""One exclusive missing-read tail after continuation01's ARM casing rejection.

Do not invoke either consumed collector. Reuse its retained APIM GET artifacts;
canonicalize ONLY the exact known fragment resource type after casefold identity
validation. No permission, HTTP method, TLS, scope or pagination guard is relaxed.
"""
import json
import os
from pathlib import Path
import re

from scripts.deployment import foundry_eight_continue as c


def fragment_path(row):
    name = row["name"]
    c.require(bool(re.fullmatch(r"[A-Za-z0-9._-]+", name)), "fragment_name_rejected")
    expected = c.APIM + "/policyFragments/" + name
    c.require(row["id"].casefold() == expected.casefold(), "fragment_identity_mismatch")
    return expected


def collect(reader, prior):
    fragments = c.load(prior / "fragments.json")
    for index, row in enumerate(fragments["value"]):
        path = fragment_path(row)
        for fmt in ("rawxml", "xml"):
            reader.section(f"fragment-{index:02d}-{fmt}", lambda path=path, fmt=fmt:
                reader.get(path + f"?format={fmt}&api-version=2024-05-01"))
    reader.section("runtime", lambda: c.runtime(reader))
    reader.section("storage", lambda: c.storage(reader))
    for name, suffix, version in (
        ("vault", "/Microsoft.KeyVault/vaults/pocidstokenexkv", "2023-07-01"),
        ("postgres", "/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg", "2024-08-01"),
        ("postgres-rules", "/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg/firewallRules", "2024-08-01"),
        ("jwt-reference", "/Microsoft.Web/sites/poc-ids-token-ex-api/config/configreferences/appsettings", "2024-04-01"),
    ):
        def protected(name=name, suffix=suffix, version=version):
            value = reader.get(c.rt.RG + "/providers" + suffix + "?api-version=" + version)
            if name == "jwt-reference":
                return c.rt.reference_metadata(value)
            if name == "postgres-rules":
                c.require(not value.get("nextLink"), "protected_pagination_incomplete")
                return value
            keys = ("network", "authConfig", "publicNetworkAccess", "networkAcls", "privateEndpointConnections", "enableRbacAuthorization")
            return {key: value["properties"].get(key) for key in keys}
        reader.section(name, protected)
    reader.section("role-assignments", lambda: reader.collection("/subscriptions/" + c.rt.SUB +
        "/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01"))
    reader.section("policy-summary", lambda: c.policy_summary(c.load(prior / "policy-xml.json")))
    reader.section("retained-routing", c.retained_routing)
    # No fresh duplicate policy GET: only use retained unredacted expression XML.
    policy = c.load(prior / "policy-xml.json")
    c.require("[REDACTED]" not in policy["properties"]["value"], "retained_policy_redacted_comparison_unavailable")
    reader.cache["https://management.azure.com" + c.API + "/policies/policy?format=xml&api-version=2024-05-01"] = policy
    reader.section("protected-snapshot", lambda: c.comparison(reader))


def main():
    prior = c.HOME / "continuation01"
    folder = c.HOME / "continuation-tail01"
    c.require(c.load(prior / "failure.json")["category"] == "fragment_scope_rejected", "exact_prior_failure_required")
    intent = c.load(c.HOME / "continuation-intent.json")
    c.require(c.sha(Path(c.__file__).read_bytes()) == intent["continuation_source_sha256"], "consumed_source_changed")
    bindings = {str(p.relative_to(c.HOME)): c.sha(p.read_bytes()) for p in
                [*(c.HOME / name for name in c.ORIGINAL_FILES), *prior.glob("*.json"), c.HOME / "continuation-intent.json"]}
    c.exclusive(c.HOME, "continuation-tail-intent.json", {"at": c.stamp(), "pid": os.getpid(),
        "previous_artifacts": bindings, "source_sha256": c.sha(Path(__file__).read_bytes()),
        "writes": 0, "method": "GET", "inference": 0, "scope": "only_unattempted_missing_tail"})
    folder.mkdir()
    reader = c.Reader(folder)
    try:
        reader.guard()
        collect(reader, prior)
        c.require(bindings == {name: c.sha((c.HOME / name).read_bytes()) for name in bindings}, "previous_artifacts_changed")
        snapshot = c.load(folder / "protected-snapshot.json") if (folder / "protected-snapshot.json").exists() else None
        result = {"at": c.stamp(), "status": "complete" if not reader.errors else "incomplete",
            "failures": reader.errors, "previous_artifacts_unchanged": True, "deployments_reread": False,
            "scope": {"subscription": c.rt.SUB, "tenant": c.rt.TENANT, "operator": c.rt.OPERATOR},
            "baseline_compared_components_equal": snapshot["compared_components_equal"] if snapshot else None,
            "writes": 0, "inference": 0, "browser_actions": 0, "http_method": "GET",
            "apim_artifacts": "../continuation01", "artifacts":
                {p.name: c.sha(p.read_bytes()) for p in sorted(folder.glob("*.json"))}}
        c.exclusive(folder, "result.json", result)
        print(json.dumps({k: v for k, v in result.items() if k != "artifacts"}), flush=True)
        return 0 if not reader.errors else 2
    except Exception as error:
        result = {"at": c.stamp(), "status": "blocked", **c.failure(error), "writes": 0, "inference": 0}
        c.exclusive(folder, "failure.json", result)
        print(json.dumps(result), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())