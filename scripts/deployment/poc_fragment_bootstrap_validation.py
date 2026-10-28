"""Independent exact fragment saved-plan review and real sequential workflow."""
from datetime import UTC, datetime
import fnmatch
import json

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment.deploy_portals import workflow
from scripts.deployment.poc_fragment_bootstrap import (
    HOME, PLAN, TFROOT, ID, ADDRESS, DEFAULTS, ACTIVE_INPUT, INPUT,
    load, sha, guard, checkpoint,
)


def validate(run):
    checkpoint("independent_validation_started")
    rt.require(not (HOME / "apply-intent.json").exists(), "cannot_validate_after_apply_attempt")
    for step in ("None", "LoadPlan", "AddValidationSteps"):
        print(json.dumps(workflow(step)), flush=True)
    review = load(HOME / "review.json")
    rt.require(review["plan_sha256"] == sha(PLAN.read_bytes()) and review["sources"] == run.sources(), "independent_bytes_binding")
    run.terraform("validate", "-no-color")
    rt.require(run.terraform("workspace", "show").strip() == "default", "independent_default_workspace")
    parsed = json.loads(run.terraform("show", "-json", str(PLAN)))
    from scripts.deployment.poc_fragment_bootstrap_exact import COMPANION, companion_guard
    rt.require(review["refreshed_companion_sha256"] == sha(COMPANION.read_bytes()), "fresh_refreshed_companion_binding")
    original = companion_guard(run)
    rt.require(original["variables"] == parsed["variables"], "identical_companion_inputs_required")
    writes = {r["address"]: r["change"]["actions"] for r in parsed["resource_changes"]
              if r["change"]["actions"] not in (["read"], ["no-op"])}
    rt.require(writes == {ADDRESS: ["create"]}, "independent_exact_one_create")
    fragment = next(r["change"] for r in parsed["resource_changes"] if r["address"] == ADDRESS)
    rt.require(fragment["before"] is None and
               fragment["after"]["parent_id"] + "/policyFragments/" + fragment["after"]["name"] == ID
               and fragment["after"]["body"]["properties"]["value"] == DEFAULTS.read_text(encoding="utf-8"), "independent_exact_target_and_xml")
    current = load(INPUT)
    expected = load(ACTIVE_INPUT)
    expected.update(poc_settings_bootstrap_enabled=True, poc_controls_enabled=False, poc_publisher_permissions_verified=False)
    rt.require(current == expected, "independent_thirteen_model_inputs_unchanged_except_bootstrap")
    rt.require(load(TFROOT / "poc-settings-bootstrap.auto.tfvars.json") == {"poc_settings_bootstrap_enabled": True}, "persisted_future_plan_protection")
    guard(parsed)
    rt.require(run.exact() is None, "independent_existing_fragment_no_overwrite")
    baseline = run.protected_complete()
    rt.require(baseline == load(HOME / "baseline.json") and fs.sha(baseline) == review["baseline_sha256"], "independent_full_live_baseline")
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "independent_account")
    assignments = rt.cli(["role", "assignment", "list", "--assignee-object-id", rt.OPERATOR,
                          "--scope", ID, "--include-inherited"])
    grants = []
    for assignment in assignments:
        if not assignment.get("condition"):
            for role in rt.cli(["role", "definition", "list", "--name", assignment["roleDefinitionId"].rsplit("/", 1)[-1]]):
                grants.extend(role["permissions"])
    actions = ["Microsoft.ApiManagement/service/policyFragments/" + a for a in ("read", "write")]
    allowed = {action: any(any(fnmatch.fnmatchcase(action.lower(), pattern.lower()) for pattern in grant.get("actions", []))
                          and not any(fnmatch.fnmatchcase(action.lower(), pattern.lower()) for pattern in grant.get("notActions", []))
                          for grant in grants) for action in actions}
    rt.require(all(allowed.values()), "actual_operator_fragment_permission_denied")
    policies = rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + rt.SUB, "--disable-scope-strict-match"])
    tests = load(HOME / "tests.json")
    rt.require(tests["python_tests"] > 0 and tests["junit_sha256"] == sha((HOME / "tests.xml").read_bytes()), "independent_test_proof")
    for step in ("RunValidation", "BuildVerification", "StaticRoleVerification"):
        print(json.dumps(workflow(step)), flush=True)
    proof = {"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"],
             "sources": run.sources(), "checks_passed": True, "exact_writes": writes,
             "existing_operator_fragment_actions": allowed, "publisher_permission_verified": False,
             "publisher_permission_not_creation_prerequisite": True, "policy_assignment_count": len(policies),
             "tests": tests, "baseline_sha256": fs.sha(baseline), "cloud_writes": 0,
             "builds": "not_applicable_fragment_only_no_images", "rbac_writes": 0}
    proof["refreshed_companion_sha256"] = review["refreshed_companion_sha256"]
    rt.save(HOME / "validation.json", proof)
    path = rt.ROOT / ".azure/deployment-plan.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n### Section 7: exact detached fragment bootstrap validation proof\n\n"
                     + proof["at_utc"] + ". Plan SHA256 " + proof["plan_sha256"]
                     + ". Independently parsed full saved plan: one azapi_resource.poc_settings[0] CREATE; every existing managed resource no-op. "
                     "Actual commands: poc_fragment_bootstrap tests; plan; validate; Terraform init -lockfile=readonly, "
                     "fmt -check, validate, test (defaults/external/POC profiles), default workspace, full locked plan and show -json. "
                     + str(tests["python_tests"]) + " focused Python tests and " + tests["terraform_summary"]
                     + ". Source/input/plan hashes, exact safe XML, existing state/owner, all saved-plan preconditions, "
                     "fresh full runtime/security/settings/model metadata and unchanged active-policy hash verified. "
                     "The full refreshed companion is retained NEVER APPLY: only API-policy xml/rawxml export representation differs; "
                     "parsed semantics equal and stored desired policy bytes already match. The full-root release uses -refresh=false "
                     "against that bound unchanged state, with every old managed object no-op, not an ignored policy change. "
                     "Existing operator read/write verified from real inherited role metadata. Missing API publisher permission "
                     "is explicitly NOT required for fragment creation and is not claimed verified. "
                     "No images/builds needed, no roles, activation, policy include, database, network, model or inference writes. "
                     "Persistent bootstrap true protects future plans; prevent_destroy and content-only runtime ownership retained.\n")
    for step in ("RecordProof", "ResolveErrors"):
        print(json.dumps(workflow(step)), flush=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\nFragment bootstrap status: Validated. Exact saved plan SHA256 " + proof["plan_sha256"] + ".\n")
    print(json.dumps(workflow("UpdateStatus")), flush=True)
    checkpoint("independently_validated_workflow_complete", plan_sha256=proof["plan_sha256"], operator_actions=allowed, cloud_writes=0)