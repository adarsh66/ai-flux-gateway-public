"""Separate actual sequential validator for exact policy successor, never apply."""
import fnmatch
import json
import sys

from scripts.deployment import poc_policy_successor as release
from scripts.deployment.deploy_portals import workflow

r = release.r


def main():
    r.rt.require(not (release.HOME / "apply-intent.json").exists(), "existing_apply_reconcile_only")
    for step in ("None", "LoadPlan", "AddValidationSteps"):
        print(json.dumps(workflow(step)), flush=True)
    review = release.check()
    result = r.rt.run([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "tests/unit/test_poc_fireworks_compatibility.py",
        "tests/unit/test_poc_controls_guards.py", "tests/unit/test_poc_activation_release.py", "tests/unit/test_poc_policy_successor.py",
        "--junitxml=" + str(release.HOME / "validation-tests.xml")])
    print(result, flush=True)
    r.fs.terraform(release.ROOT, "validate", "-no-color")
    r.rt.require(r.fs.terraform(release.ROOT, "workspace", "show").strip() == "default", "default_workspace")
    addresses = r.fs.terraform(release.ROOT, "state", "list").splitlines()
    r.rt.require(r.POLICY in addresses and "azapi_resource.poc_settings[0]" in addresses and "azapi_resource.fireworks_backend[0]" in addresses, "all_existing_state_owners")
    print(json.dumps(workflow("RunValidation")), flush=True)
    offline = r.prep.load(release.api.native.HOME / "offline-review.json")
    r.rt.require(offline["passed"] and all(r.sha((r.rt.ROOT / p).read_bytes()) == h for p, h in offline["sources"].items()), "independent_compatibility_review_binding")
    release.api.check(live=False)
    release.acceptance()
    print(json.dumps(workflow("BuildVerification")), flush=True)
    r.require_publisher(r.collect())
    grants = []
    for assignment in r.rt.cli(["role", "assignment", "list", "--assignee-object-id", r.rt.OPERATOR, "--scope", r.rt.RG, "--include-inherited"]):
        if not assignment.get("condition"):
            definition = r.rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + assignment["roleDefinitionId"] + "?api-version=2022-04-01"])
            grants.extend(definition["properties"]["permissions"])
    actions = ["Microsoft.ApiManagement/service/apis/policies/read", "Microsoft.ApiManagement/service/apis/policies/write"]
    coverage = {action: any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("actions", [])) and
        not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("notActions", [])) for g in grants) for action in actions}
    r.rt.require(all(coverage.values()), "existing_policy_operator_permissions")
    policies = r.rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + r.rt.SUB, "--disable-scope-strict-match"])
    print(json.dumps(workflow("StaticRoleVerification")), flush=True)
    r.rt.require(r.snapshot() == review["baseline"], "final_complete_policy_baseline")
    proof = {"at": r.fs.stamp(), "checks_passed": True, "plan_sha256": review["plan_sha256"], "tooling": release.tooling(),
             "operator_coverage": coverage, "policy_assignment_count": len(policies), "publisher_live_no502_verified": True,
             "compatibility_review": offline["at"], "tests": result.strip(), "process": "independent validator; no planning/build/apply"}
    r.exclusive(release.HOME, "validation.json", proof)
    doc = r.rt.ROOT / ".azure/deployment-plan.md"
    with doc.open("a", encoding="utf-8") as handle:
        handle.write("\n### Section 7: exact POC policy successor validation\n\n" + proof["at"] + ". Exact saved plan SHA256 " + proof["plan_sha256"] +
            ". Separate process verified all real plan checks, exact one existing-policy update with unchanged fragment/backend/model routes, full protected baseline, "
            "source/input/artifact hashes, independent Fireworks compatibility tests and actual thirteen-model render delta, Terraform validate/default workspace/existing owners, "
            "current operator/publisher grants and Azure policy assignments. Fresh API-only correction independently applied/verified; authenticated content-changing limits/safety "
            "save/restore returned HTTP200 without reconcile and restored published defaults before policy preparation. Rejected 7d200ba9 plan remains NEVER APPLY. "
            "No inference, role/key/subscription/network/DB/FinOps/customer/ingestion mutation. Existing Starlette warning disclosed.\n")
    for step in ("RecordProof", "ResolveErrors"):
        print(json.dumps(workflow(step)), flush=True)
    with doc.open("a", encoding="utf-8") as handle:
        handle.write("\nPOC policy successor status: Validated. Exact plan " + proof["plan_sha256"] + ".\n")
    print(json.dumps(workflow("UpdateStatus")), flush=True)
    print(json.dumps({"at": proof["at"], "plan_sha256": proof["plan_sha256"], "checks_passed": True}), flush=True)


if __name__ == "__main__":
    main()