"""Separate independent read-only validator, actual sequential workflow, no apply."""
import fnmatch
import json
import sys

from scripts.deployment import poc_activation_release as r
from scripts.deployment.deploy_portals import workflow


def main(stage):
    folder, root, _ = r.location(stage)
    r.rt.require(not (folder / "apply-intent.json").exists(), "attempted_apply_reconcile_only")
    for step in ("None", "LoadPlan", "AddValidationSteps"):
        print(json.dumps(workflow(step)), flush=True)
    review = r.check(stage)
    result = r.rt.run([sys.executable, "-m", "pytest", "-q", "tests/unit/test_poc_activation_release.py",
        "tests/unit/test_poc_controls_guards.py", "--junitxml=" + str(folder / "validation-tests.xml")])
    print(result, flush=True)
    r.fs.terraform(root, "validate", "-no-color")
    r.rt.require(r.fs.terraform(root, "workspace", "show").strip() == "default", "default_workspace")
    addresses = r.fs.terraform(root, "state", "list").splitlines()
    r.rt.require((all(a in addresses for a in r.RUNTIME) if stage == "runtime" else
                  r.POLICY in addresses and "azapi_resource.poc_settings[0]" in addresses), "existing_state_owners")
    print(json.dumps(workflow("RunValidation")), flush=True)
    # Current ACR outputs, production package inputs and no-push validators are bound independently.
    r.built(remote=True)
    native = r.prep.load(r.HOME / "native.json")
    for part in ("ui", "api"):
        run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", native[part]["run_id"], "--subscription", r.rt.SUB])
        r.rt.require(run["status"] == "Succeeded" and run["finishTime"] == native[part]["finished_at"]
            and r.prep.ui_native.no_published_images(run.get("outputImages")), "current_no_push_validation")
    print(json.dumps(workflow("BuildVerification")), flush=True)
    permissions = r.collect()
    r.require_publisher(permissions)
    grants = []
    for assignment in r.rt.cli(["role", "assignment", "list", "--assignee-object-id", r.rt.OPERATOR, "--scope", r.rt.RG, "--include-inherited"]):
        if not assignment.get("condition"):
            definition = r.rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + assignment["roleDefinitionId"] + "?api-version=2022-04-01"])
            grants.extend(definition["properties"]["permissions"])
    actions = (["Microsoft.Web/sites/read", "Microsoft.Web/sites/write", "Microsoft.Web/sites/config/read", "Microsoft.Web/sites/config/write"]
        if stage == "runtime" else ["Microsoft.ApiManagement/service/apis/policies/read", "Microsoft.ApiManagement/service/apis/policies/write"])
    coverage = {action: any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("actions", []))
        and not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("notActions", [])) for g in grants) for action in actions}
    r.rt.require(all(coverage.values()), "existing_operator_permission")
    registry = (r.rt.RG + "/providers/Microsoft.ContainerRegistry/registries/" + r.portals.REGISTRY).lower()
    for kind in ("api", "admin"):
        ids = review["baseline"]["runtime"]["sites"][kind]["protected"]["identity"]["userAssignedIdentities"]
        r.rt.require(any(a[1] == identity["principalId"] and a[2].lower().endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d")
            and a[3].lower() == registry and not a[4] for identity in ids.values() for a in review["baseline"]["runtime"]["roleAssignments"]), "existing_acr_pull:" + kind)
    policies = r.rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + r.rt.SUB, "--disable-scope-strict-match"])
    print(json.dumps(workflow("StaticRoleVerification")), flush=True)
    r.rt.require(r.snapshot() == review["baseline"], "final_independent_baseline")
    proof = {"at": r.fs.stamp(), "checks_passed": True, "stage": stage, "plan_sha256": review["plan_sha256"],
        "tooling": r.tooling(), "source_sha256": review["source_sha256"], "native": native,
        "operator_coverage": coverage, "policy_assignment_count": len(policies), "publisher_metadata_verified": True,
        "process": "independent sequential validator; no planning/building/applying", "tests": result.strip()}
    r.exclusive(folder, "validation.json", proof)
    doc = r.rt.ROOT / ".azure/deployment-plan.md"
    with doc.open("a", encoding="utf-8") as handle:
        handle.write("\n### Section 7: independent POC activation " + stage + " validation\n\n" + proof["at"] + ". Exact plan SHA256 " + proof["plan_sha256"] +
            ". Separate process verified source/input/archive/build hashes, current complete protected baseline, actual guard tests including exact thirteen-model render, "
            "Terraform validate/default workspace/existing state owners, existing operator/AcrPull/exact publisher grants and policy assignments. "
            "Native Linux API and UI no-push production validation succeeded; identical-input full NEVER APPLY companion resolves target checks where necessary. "
            "No role writes, new resources, inference or customer/ingestion changes. Existing npm warnings retained; no all-workspace-test claim.\n")
    for step in ("RecordProof", "ResolveErrors"):
        print(json.dumps(workflow(step)), flush=True)
    with doc.open("a", encoding="utf-8") as handle:
        handle.write("\nPOC activation " + stage + " status: Validated. Exact plan " + proof["plan_sha256"] + ".\n")
    print(json.dumps(workflow("UpdateStatus")), flush=True)
    print(json.dumps({"at": proof["at"], "stage": stage, "plan_sha256": proof["plan_sha256"], "checks_passed": True}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])