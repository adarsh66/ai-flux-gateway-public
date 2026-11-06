"""Independent actual sequential azure-validate for fresh API-only saved plan."""
import fnmatch
import json
import sys

from scripts.deployment import poc_reliability_release as release
from scripts.deployment.deploy_portals import workflow

r = release.r


def main():
    r.rt.require(not (release.HOME / "apply-intent.json").exists(), "attempted_apply_reconcile_only")
    for step in ("None", "LoadPlan", "AddValidationSteps"):
        print(json.dumps(workflow(step)), flush=True)
    review = release.check()
    result = r.rt.run([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "tests/unit/test_poc_reliability_release.py",
                       "tests/unit/test_poc_publisher_reliability.py", "--junitxml=" + str(release.HOME / "validation-tests.xml")])
    print(result, flush=True)
    r.fs.terraform(release.ROOT, "validate", "-no-color")
    r.rt.require(r.fs.terraform(release.ROOT, "workspace", "show").strip() == "default", "default_workspace")
    r.rt.require(release.ADDRESS in r.fs.terraform(release.ROOT, "state", "list").splitlines(), "existing_state_owner")
    print(json.dumps(workflow("RunValidation")), flush=True)
    native = r.prep.load(release.native.HOME / "api-native.json")
    run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", native["run_id"], "--subscription", r.rt.SUB])
    r.rt.require(run["status"] == "Succeeded" and run["finishTime"] == native["finished_at"] and
                 r.prep.ui_native.no_published_images(run.get("outputImages")), "current_native_no_push_binding")
    release.built()
    print(json.dumps(workflow("BuildVerification")), flush=True)
    r.require_publisher(r.collect())
    grants = []
    for assignment in r.rt.cli(["role", "assignment", "list", "--assignee-object-id", r.rt.OPERATOR, "--scope", r.rt.RG, "--include-inherited"]):
        if not assignment.get("condition"):
            definition = r.rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + assignment["roleDefinitionId"] + "?api-version=2022-04-01"])
            grants.extend(definition["properties"]["permissions"])
    actions = ["Microsoft.Web/sites/read", "Microsoft.Web/sites/write", "Microsoft.Web/sites/config/read", "Microsoft.Web/sites/config/write"]
    coverage = {action: any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("actions", [])) and
                not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("notActions", [])) for g in grants) for action in actions}
    r.rt.require(all(coverage.values()), "existing_operator_permissions")
    registry = (r.rt.RG + "/providers/Microsoft.ContainerRegistry/registries/" + r.portals.REGISTRY).lower()
    current = review["baseline"]["runtime"]
    ids = current["sites"]["api"]["protected"]["identity"]["userAssignedIdentities"]
    r.rt.require(any(a[1] == identity["principalId"] and a[2].lower().endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d") and
        a[3].lower() == registry and not a[4] for identity in ids.values() for a in current["roleAssignments"]), "existing_api_acr_pull")
    policies = r.rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + r.rt.SUB, "--disable-scope-strict-match"])
    print(json.dumps(workflow("StaticRoleVerification")), flush=True)
    r.rt.require(r.snapshot() == review["baseline"], "final_independent_complete_baseline")
    proof = {"at": r.fs.stamp(), "checks_passed": True, "plan_sha256": review["plan_sha256"], "tooling": release.tooling(),
             "source_sha256": review["source_sha256"], "native": native, "operator_coverage": coverage,
             "policy_assignment_count": len(policies), "publisher_metadata_verified": True,
             "process": "independent sequential validator; no planning/building/applying", "tests": result.strip()}
    r.exclusive(release.HOME, "validation.json", proof)
    doc = r.rt.ROOT / ".azure/deployment-plan.md"
    with doc.open("a", encoding="utf-8") as handle:
        handle.write("\n### Section 7: fresh API-only publisher reliability validation\n\n" + proof["at"] + ". Exact saved plan SHA256 " + proof["plan_sha256"] +
            ". Separate process verified current source/inputs/artifacts/immutable API build and Linux no-push native validation, exact one API image-only guard, "
            "all targeted checks resolved from identical-input full NEVER APPLY companion, complete protected baseline including schema3 fragment and actual exact grant, "
            "all four settings hashes, unchanged admin/customer/ingestion, Terraform validate/default workspace/existing state owner, existing operator/AcrPull and policy assignments. "
            "No roles, network, DB migration, FinOps, inference or policy mutation. Preexisting Starlette warning disclosed; no all-workspace or live publisher proof claimed.\n")
    for step in ("RecordProof", "ResolveErrors"):
        print(json.dumps(workflow(step)), flush=True)
    with doc.open("a", encoding="utf-8") as handle:
        handle.write("\nPublisher reliability correction status: Validated. Exact plan " + proof["plan_sha256"] + ".\n")
    print(json.dumps(workflow("UpdateStatus")), flush=True)
    print(json.dumps({"at": proof["at"], "plan_sha256": proof["plan_sha256"], "checks_passed": True}), flush=True)


if __name__ == "__main__":
    main()