"""Separate read-only validator, actual sequential workflow; no plan/build/apply."""
import fnmatch
import json
import sys

from scripts.deployment import admin_showback_release as s
from scripts.deployment.deploy_portals import workflow

r = s.r


def main():
    r.rt.require(not (s.HOME / "apply-intent.json").exists(), "attempted_apply_reconcile_only")
    for step in ("None", "LoadPlan", "AddValidationSteps"):
        print(json.dumps(workflow(step)), flush=True)
    review = s.check()
    output = r.rt.run([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "tests/unit/test_admin_showback_release.py",
        "tests/unit/test_usage_rankings.py", "tests/unit/test_poc_fireworks_compatibility.py",
        "--junitxml=" + str(s.HOME / "independent-tests.xml")])
    counts = s.junit(s.HOME / "independent-tests.xml", 15)
    r.fs.terraform(s.ROOT, "fmt", "-check")
    r.fs.terraform(s.ROOT, "validate", "-no-color")
    r.rt.require(r.fs.terraform(s.ROOT, "workspace", "show").strip() == "default", "default_workspace")
    state = r.fs.terraform(s.ROOT, "state", "list").splitlines()
    r.rt.require(set(s.ADDRESSES) <= set(state), "existing_state_ownership")
    print(json.dumps(workflow("RunValidation")), flush=True)
    s.ui_proof(remote=True)
    native = s.load(s.HOME / "native.json")
    run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", native["run_id"], "--subscription", r.rt.SUB])
    r.rt.require(native["passed"] and native["source_sha256"] == review["source_sha256"] and run["status"] == "Succeeded"
        and run["finishTime"] == native["finished_at"] and s.ui.no_published_images(run.get("outputImages")), "current_native_provenance")
    s.built()
    print(json.dumps(workflow("BuildVerification")), flush=True)
    runtime = review["baseline"]["runtime"]
    registry = (r.rt.RG + "/providers/Microsoft.ContainerRegistry/registries/" + r.portals.REGISTRY).lower()
    for kind in s.KINDS:
        ids = runtime["sites"][kind]["protected"]["identity"]["userAssignedIdentities"]
        r.rt.require(any(a[1] == identity["principalId"] and a[2].lower().endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d")
            and a[3].lower() == registry and not a[4] for identity in ids.values() for a in runtime["roleAssignments"]), "existing_acr_pull:" + kind)
    grants = []
    for assignment in r.rt.cli(["role", "assignment", "list", "--assignee-object-id", r.rt.OPERATOR, "--scope", r.rt.RG, "--include-inherited"]):
        if not assignment.get("condition"):
            definition = r.rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + assignment["roleDefinitionId"] + "?api-version=2022-04-01"])
            grants.extend(definition["properties"]["permissions"])
    actions = ["Microsoft.Web/sites/read", "Microsoft.Web/sites/write", "Microsoft.Web/sites/config/read", "Microsoft.Web/sites/config/write"]
    coverage = {a: any(any(fnmatch.fnmatchcase(a.lower(), p.lower()) for p in g.get("actions", [])) and
        not any(fnmatch.fnmatchcase(a.lower(), p.lower()) for p in g.get("notActions", [])) for g in grants) for a in actions}
    r.rt.require(all(coverage.values()), "existing_operator_permissions")
    policies = r.rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + r.rt.SUB, "--disable-scope-strict-match"])
    print(json.dumps(workflow("StaticRoleVerification")), flush=True)
    r.rt.require(r.snapshot() == review["baseline"], "final_independent_complete_baseline")
    proof = {"at": r.fs.stamp(), "checks_passed": True, "plan_sha256": review["plan_sha256"], "tooling": s.tooling(),
        "source_sha256": review["source_sha256"], "images": review["images"], "tests": counts, "native": native,
        "ui_run": "cm2t", "operator_coverage": coverage, "policy_assignment_count": len(policies),
        "process": "independent sequential validator; no planning/building/applying", "companion_never_apply": True}
    s.exclusive("validation.json", proof)
    s.checkpoint("independent_checks_passed_section7_workflow_completion_pending", at=proof["at"], plan_sha256=proof["plan_sha256"], tests=counts)
    print(output, flush=True)


if __name__ == "__main__":
    main()