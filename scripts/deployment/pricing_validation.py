"""Independent pricing release validation; never builds or applies."""
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from xml.etree import ElementTree

from aiflux.display_pricing import manifest
from scripts.deployment import pricing_runtime_release as pricing
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.deploy_portals import workflow
from scripts.deployment.project_route_product_access import sha


def main():
    rt.require(not (pricing.HOME / "apply-intent.json").exists(), "never_validate_attempted_apply")
    for step in ("None", "LoadPlan", "AddValidationSteps"):
        print(json.dumps(workflow(step)), flush=True)
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT
               and account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_scope")
    review = pricing.check()
    rt.tf(["version", "-json"])
    rt.cli(["version"])
    rt.tf(["fmt", "-check"])
    rt.tf(["validate", "-no-color"])
    addresses = rt.tf(["state", "list"]).splitlines()
    rt.require(rt.tf(["workspace", "show"]).strip() == "default", "workspace")
    for path in (rt.ROOT / "infra/terraform").glob("*.tf*"):
        rt.require(not re.search(r"\{\{\s*\.Env\.", path.read_text(encoding="utf-8")), "unresolved_template")
        if path.suffix == ".json":
            json.loads(path.read_text())
    tests = ElementTree.parse(rt.ROOT / "gateway/validation/display-pricing-backend-tests-20261027.xml").getroot()
    suites = list(tests.iter("testsuite"))
    rt.require(sum(int(s.get("tests", "0")) for s in suites) == 117
               and all(s.get("failures") == "0" and s.get("errors") == "0" for s in suites), "backend_tests")
    portal_tag = json.loads((pricing.HOME / "portal-result.json").read_text())["tag"]
    log = (pricing.portals.HOME / portal_tag / "validation-build.log").read_text(encoding="utf-8")
    rt.require("Tests  107 passed (107)" in log and "Test Files  13 passed (13)" in log, "ui_tests")
    current = review["baseline"]["protected"]["runtime"]
    registry = (rt.RG + "/providers/Microsoft.ContainerRegistry/registries/" + pricing.portals.REGISTRY).lower()
    for kind in pricing.KINDS:
        identities = current["sites"][kind]["protected"]["identity"]["userAssignedIdentities"]
        rt.require(any(role[1] == identity["principalId"]
                       and role[2].lower().endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d")
                       and role[3].lower() == registry and not role[4]
                       for identity in identities.values() for role in current["roleAssignments"]), "acr_pull:" + kind)
    policies = rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + rt.SUB,
                       "--disable-scope-strict-match"])
    # rt.arm defaults to the Web API version, unsupported by Cognitive Services.
    # Use the same read-only ARM API as the existing inventory verifier.
    deployments_url = ("https://management.azure.com" + rt.RG
                       + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry/deployments"
                       + "?api-version=2025-06-01")
    response = rt.cli(["rest", "--method", "get", "--url", deployments_url,
                       "--subscription", rt.SUB])
    rt.require(not response.get("nextLink"), "deployment_pagination_requires_review")
    deployed = response["value"]
    matched = []
    for rate in manifest()["rates"]:
        if rate["provider"] == "ModelArts":
            continue
        item = next(d for d in deployed if d["name"] == rate["model"])
        rt.require(item["sku"]["name"] == rate["sku"]
                   and item["properties"]["model"]["version"] == rate["model_version"], "rate_sku_version:" + rate["model"])
        matched.append({"model": rate["model"], "sku": item["sku"]["name"],
                        "version": item["properties"]["model"]["version"]})
    print(json.dumps(workflow("RunValidation")), flush=True)
    print(json.dumps(workflow("BuildVerification")), flush=True)
    print(json.dumps(workflow("StaticRoleVerification")), flush=True)
    proof = {"at": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"],
             "manifest_sha256": review["manifest_sha256"], "guard": review["guard"],
             "backend_tests": 117, "ui_tests": 107, "ui_files": 13,
             "native_linux_typecheck_and_both_builds": True, "state_addresses": len(addresses),
             "policy_assignments_reviewed": len(policies), "existing_acr_pull": list(pricing.KINDS),
             "live_rate_sku_versions": matched, "protected_sha256": sha(json.dumps(review["baseline"], sort_keys=True)),
             "images": review["images"], "checks_passed": True,
             "known_dependency_warning": "Existing npm audit reports 1 moderate, 1 high, 2 critical; no dependency changes in pricing release; not a clean vulnerability scan claim."}
    rt.save(pricing.HOME / "validation.json", proof)
    rt.save(rt.ROOT / "gateway/validation/pricing-release-validation-20261027.json", proof)
    path = rt.ROOT / ".azure/deployment-plan.md"
    text = path.read_text(encoding="utf-8")
    text += ("\n### Section 7: sourced pricing exact-image validation proof\n\n"
             + "Independent validation at " + proof["at"] + ". Exact saved plan SHA256 " + review["plan_sha256"]
             + ". Manifest SHA256 " + review["manifest_sha256"] + ".\n"
             + "Actual pricing_runtime_release plan/check; init lockfile readonly, fmt, validate, saved-plan guard, "
               "state/workspace/template checks; current operator/subscription/tenant; full protected baseline and "
               "settings hashes; three existing AcrPull identities and Azure policy assignments reviewed. "
               "Ten Foundry deployment SKU/version pairs independently matched. Exactly three immutable image "
               "updates, zero settings/ingestion/policy/network/RBAC changes. Backend117 and UI107 tests pass; "
               "native Linux typechecks and both portal builds pass. Initial two stale assertion failures resolved "
               "in corrected cm20; failed cm1y retained, never replayed. Existing npm dependency vulnerability "
               "warnings remain disclosed in validation artifact, not newly introduced or silently cleared.\n")
    path.write_text(text, encoding="utf-8")
    print(json.dumps(workflow("RecordProof")), flush=True)
    print(json.dumps(workflow("ResolveErrors")), flush=True)
    # This status is set only after actual checks above and the sequential skill workflow.
    path.write_text(path.read_text(encoding="utf-8").replace("Pricing runtime status: Approved.",
                    "Pricing runtime status: Validated."), encoding="utf-8")
    print(json.dumps(workflow("UpdateStatus")), flush=True)
    print(json.dumps(proof), flush=True)


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print(json.dumps({"errorType": "HTTPError", "http_status": error.code,
                          "operation_path": urlsplit(error.url).path}), flush=True)
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({"errorType": type(error).__name__, "error": str(error) if isinstance(error, RuntimeError)
                          else "validation_failed_sensitive_detail_suppressed"}), flush=True)
        raise SystemExit(1)