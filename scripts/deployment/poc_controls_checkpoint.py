"""Read-only final checkpoint for the explicitly blocked POC rollout."""
from datetime import UTC, datetime
import json
import re
from xml.etree import ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import poc_controls_preflight as preflight
from scripts.deployment.finops_function_stage import sha
from scripts.deployment.portal_fix import REGISTRY


def junit(path):
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    return {key: sum(int(s.get(key, "0")) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")}


def main():
    fresh = preflight.collect()
    rt.require(fresh["protected_baseline_equal_previous_preflight"]
               and fresh["policy_equal_previous_preflight"], "live_protected_baseline_changed")
    home = rt.HOME / "poc-controls-20261027"
    builds = {}
    for kind, artifact, folder in (
        ("ui", "poc-controls-linux-validation-corrected-20261027.json", "linux-validation-corrected"),
        ("api", "poc-controls-linux-api-validation-20261027.json", "linux-api-validation"),
    ):
        proof = json.loads((rt.ROOT / "gateway/validation" / artifact).read_text())
        rt.require(proof["exit_code"] == 0 and proof["no_push"] and not proof["deployed"], "successful_no_push_validation_required")
        sources = json.loads((home / folder / "sources.json").read_text())
        for item in sources["entries"]:
            rt.require(preflight.sha((rt.ROOT / item["path"]).read_bytes()) == item["sha256"], "validated_source_changed")
        run = rt.cli(["acr", "task", "show-run", "--registry", REGISTRY,
                      "--run-id", proof["run_id"], "--subscription", rt.SUB])
        # ACR represents a no-push quick run as outputImages=[null]. Reject
        # every actual output image, not the service's null placeholder.
        rt.require(run["status"] == "Succeeded" and not any(run.get("outputImages") or []),
               "native_run_not_successful_no_push")
        log = (home / folder / "validation.log").read_text(encoding="utf-8")
        tests = re.findall(r"(?:Tests\s+(\d+) passed|(?:^|\n)(\d+) passed,)", log)
        rt.require(bool(tests), "native_test_count_missing")
        builds[kind] = {**proof, "tests_passed": int(next(x for x in tests[-1] if x)),
                        "acr_status": run["status"], "finished_at": run.get("finishTime"),
                        "log_sha256": preflight.sha(log)}
    release_tests = junit(rt.ROOT / "gateway/validation/poc-controls-release-tests-20261027.xml")
    rt.require(release_tests["tests"] >= 185 and release_tests["failures"] == release_tests["errors"] == 0,
               "release_regressions_failed")
    markers = sorted(p.relative_to(home).as_posix() for p in home.rglob("*intent*.json"))
    rt.require(not any("apply" in m or "plan" in m for m in markers), "unexpected_live_release_intent")
    blocked = not fresh["publisher_fragment_permission_verified"]
    result = {"at_utc": datetime.now(UTC).isoformat(),
              "status": "BLOCKED_EXACT_PUBLISHER_RBAC" if blocked else "PREFLIGHT_ONLY_NOT_DEPLOYED",
              "deployed": False, "live_configuration_writes": 0, "rbac_writes": 0,
              "image_pushes": 0, "inference_tests": "SKIPPED_USER_REQUEST", "gateway_traffic_tests": "SKIPPED_USER_REQUEST",
              "saved_plan_created": False, "apply_attempts": 0, "initial_db_revision_created": False,
              "protected_baseline_equal": True, "policy_equal": True,
              "protected_baseline_sha256": sha(fresh["protected"]), "policy_sha256": fresh["policy_sha256"],
              "live_images": {k: v["image"] for k, v in fresh["protected"]["runtime"]["sites"].items()},
              "selected_publisher_principal_id": fresh["selected_publisher_principal_id"],
              "required_actions": fresh["required_actions"], "required_fragment_scope": fresh["required_fragment_scope"],
              "api_control_flags": fresh["api_control_flags"], "native_validation": builds,
              "release_regressions": release_tests,
              "unfiltered_workspace_tests": junit(rt.ROOT / "gateway/validation/poc-controls-offline-tests-20261027.xml"),
              "workspace_migration_failures": "Duplicate revision 0003 in sandbox portal_users and stable_teams; existing production packager excludes sandbox portal_users; both migrations tests pass in native package. No migration source edited.",
              "foundry_bindings": fresh["foundry_bindings"], "foundry_policies": fresh["foundry_policies"],
              "build_intent_markers": markers,
              "rbac_authorization": "Exact missing grant requested; no explicit authorization returned. No grant inferred.",
              "pending": ["Exact two-action fragment publisher grant authorization and provisioning",
                          "Fresh independent guarded saved-plan validation",
                          "Stage safe default fragment before API policy include",
                          "Publish immutable API/admin images only and enable exact three API flags",
                          "Audited initial DB revision via existing authenticated admin release session",
                          "Management-plane XML/readback and benign same-value org/sub save/remove acceptance; no inference"]}
    path = rt.ROOT / "gateway/validation/poc-controls-checkpoint-20261027.json"
    rt.save(path, result)
    print(json.dumps({k: v for k, v in result.items() if k not in (
        "foundry_bindings", "foundry_policies", "pending", "unfiltered_workspace_tests")}), flush=True)


if __name__ == "__main__":
    main()