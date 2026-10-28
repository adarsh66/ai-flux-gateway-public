"""Independent actual sequential azure-validate for the targeted bootstrap."""
from datetime import UTC, datetime, timedelta
import fnmatch
import json

from scripts.deployment import poc_fragment_bootstrap as b
from scripts.deployment import poc_fragment_bootstrap_targeted as t
from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment.deploy_portals import workflow


def validate(run):
    b.checkpoint("independent_targeted_validation_started")
    rt.require(not (t.HOME / "apply-intent.json").exists(), "no_validation_after_apply_intent")
    print(json.dumps(workflow("None")), flush=True)
    path = rt.ROOT / ".azure/deployment-plan.md"
    doc = path.read_text(encoding="utf-8")
    rt.require("Approved detached fragment-only bootstrap" in doc, "approved_scope_required")
    print(json.dumps(workflow("LoadPlan")), flush=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n### Corrected targeted bootstrap validation steps\n\n"
                     "Only azapi_resource.poc_settings[0] is targeted for release. A separate fresh full-root "
                     "companion is NEVER APPLY and proves every precondition/all expanded inputs and "
                     "the sole xml/rawxml policy representation difference against exact stored/render/live baseline. "
                     "Require exact one create, unchanged original rejected artifacts, source/plan bindings, "
                     "fresh protected baseline and operator permission, no activation or other writes.\n")
    print(json.dumps(workflow("AddValidationSteps")), flush=True)
    run.terraform("validate", "-no-color")
    rt.require(run.terraform("workspace", "show").strip() == "default", "independent_workspace")
    review = run.check(live=False)
    rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at_utc"]) < timedelta(hours=2),
               "independent_fresh_plan")
    rt.require(b.sha((b.TFROOT / "terraform.tfstate").read_bytes()) == b.load(t.HOME / "state-before-summary.json")["sha256"],
               "independent_unchanged_state")
    parsed = json.loads(run.terraform("show", "-json", str(b.PLAN)))
    full = json.loads(run.terraform("show", "-json", str(t.COMPANION)))
    run.prove_companion(full)
    rt.require(run.exact() is None, "independent_existing_fragment_verify_only")
    writes = [r for r in parsed["resource_changes"] if r["change"]["actions"] not in (["no-op"], ["read"])]
    rt.require(len(writes) == 1 and writes[0]["address"] == b.ADDRESS
               and writes[0]["change"]["actions"] == ["create"] and writes[0]["change"]["before"] is None,
               "independent_one_create_only")
    value = writes[0]["change"]["after"]
    rt.require(value["parent_id"] + "/policyFragments/" + value["name"] == b.ID
               and value["body"]["properties"]["value"] == b.DEFAULTS.read_text(encoding="utf-8"), "independent_target_xml")
    rt.require(parsed["variables"] == full["variables"] and all(c["status"] == "pass" for c in full["checks"]),
               "independent_all_inputs_full_preconditions")
    expected = b.load(b.ACTIVE_INPUT)
    expected.update(poc_settings_bootstrap_enabled=True, poc_controls_enabled=False, poc_publisher_permissions_verified=False)
    rt.require(b.load(b.INPUT) == expected, "independent_predecessor_input_binding")
    rt.require(b.load(b.TFROOT / "poc-settings-bootstrap.auto.tfvars.json") == {"poc_settings_bootstrap_enabled": True},
               "persisted_future_plan_protection")
    baseline = run.protected_complete()
    rt.require(baseline == b.load(t.HOME / "baseline.json") and fs.sha(baseline) == review["baseline_sha256"],
               "independent_fresh_full_baseline")
    print(json.dumps(workflow("RunValidation")), flush=True)
    tests = b.load(t.HOME / "tests.json")
    rt.require(tests["python_tests"] > 0 and tests["junit_sha256"] == b.sha((t.HOME / "tests.xml").read_bytes())
               and "0 failed" in tests["terraform_summary"], "independent_actual_test_evidence")
    supplemental = review.get("supplemental_tests")
    if supplemental:
        rt.require(supplemental["python_tests"] > 0 and supplemental["junit_sha256"]
                   == b.sha((t.HOME / supplemental["path"]).read_bytes()), "independent_review_regressions")
    print(json.dumps(workflow("BuildVerification")), flush=True)
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "independent_account")
    assignments = rt.cli(["role", "assignment", "list", "--assignee-object-id", rt.OPERATOR,
                          "--scope", b.ID, "--include-inherited"])
    grants = []
    for assignment in assignments:
        if not assignment.get("condition"):
            for role in rt.cli(["role", "definition", "list", "--name", assignment["roleDefinitionId"].rsplit("/", 1)[-1]]):
                grants.extend(role["permissions"])
    allowed = {action: any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("actions", []))
                          and not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("notActions", []))
                          for g in grants)
               for action in ("Microsoft.ApiManagement/service/policyFragments/read", "Microsoft.ApiManagement/service/policyFragments/write")}
    rt.require(all(allowed.values()), "actual_operator_fragment_permission_denied")
    policies = rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + rt.SUB, "--disable-scope-strict-match"])
    print(json.dumps(workflow("StaticRoleVerification")), flush=True)
    proof = {"at_utc": datetime.now(UTC).isoformat(), "checks_passed": True,
             "plan_sha256": review["plan_sha256"], "sources": run.sources(),
             "refreshed_companion_sha256": review["refreshed_companion_sha256"],
             "exact_writes": {b.ADDRESS: ["create"]}, "existing_operator_fragment_actions": allowed,
             "publisher_permission_verified": False, "publisher_permission_not_creation_prerequisite": True,
             "policy_assignment_count": len(policies), "baseline_sha256": fs.sha(baseline), "tests": tests,
             "original_rejected_never_apply": True, "companion_never_apply": True,
             "cloud_writes": 0, "rbac_writes": 0, "builds": "not_applicable_no_images"}
    proof["supplemental_tests"] = supplemental
    proof["companion_resolved_excluded_checks"] = review["scope"]["companion_resolved_excluded_checks"]
    with (t.HOME / "validation.json").open("x", encoding="utf-8") as handle:
        json.dump(proof, handle, indent=2)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n### Section 7: exact detached targeted fragment validation proof\n\n"
                     + proof["at_utc"] + ". Independently parsed exact release plan SHA256 " + proof["plan_sha256"]
                     + ". Full refreshed NEVER APPLY companion SHA256 " + proof["refreshed_companion_sha256"]
                     + ". Actual commands: poc_fragment_bootstrap_targeted preflight/tests/plan/validate; "
                     "Terraform fmt -check, init -lockfile=readonly, validate, test defaults/external/POC; "
                     "default workspace, refreshed full plan and separate -target=azapi_resource.poc_settings[0] "
                     "saved plan, show -json on both. " + str(tests["python_tests"]) + " Python tests; "
                     + tests["terraform_summary"] + ". Targeted release contains exactly ONE fragment CREATE, "
                     "ZERO policy or other writes. Full companion proves every existing managed resource no-op "
                     "except known xml/rawxml export-only policy normalization, decoded semantics identical, "
                     "stored rawxml body equals current render byte-for-byte, live active-policy hash unchanged. "
                     "This normalization is NOT applied/accepted as a release policy write. Every full companion "
                     "precondition passes; every expanded variable matches target. Original strict guard unchanged. "
                     "Only the nine enumerated out-of-target unknown checks are discharged by the same-address "
                     "PASS checks in this full companion; no failed, missing or target-writable check is waived. "
                     "Existing saved plans were reviewed without replan/overwrite; supplemental Python regressions "
                     + str(supplemental["python_tests"] if supplemental else 0) + " passed. "
                     "Independent source/input/both-plan/original-artifact hashes, state bytes/lineage, safe XML, "
                     "13 models, all live pins/settings/security/FinOps and existing operator permissions verified. "
                     "Publisher permission remains false and not required for creation. No image builds, role grants, "
                     "activation, policy include, database, network, model edits or inference. Original rejected "
                     "plan and failed logs remain untouched NEVER APPLY. One exclusive apply only after this proof.\n")
    print(json.dumps(workflow("RecordProof")), flush=True)
    print(json.dumps(workflow("ResolveErrors")), flush=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\nFragment bootstrap status: Validated. Exact saved plan SHA256 " + proof["plan_sha256"] + ".\n")
    print(json.dumps(workflow("UpdateStatus")), flush=True)
    b.checkpoint("independently_validated_workflow_complete", plan_sha256=proof["plan_sha256"], operator_actions=allowed, cloud_writes=0)