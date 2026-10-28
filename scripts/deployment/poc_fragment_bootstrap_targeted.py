"""Exclusive fragment-targeted correction; full refreshed companion NEVER APPLY.

Original rejected bytes and markers are immutable. No policy/state repair,
refresh=false plan, lifecycle waiver, publisher grant or activation is used.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from scripts.deployment import poc_fragment_bootstrap as b
from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment.project_route_demo import policy_structure

ORIGINAL = rt.HOME / "poc-fragment-bootstrap-20261028"
HOME = rt.HOME / "poc-fragment-bootstrap-20261028-targeted01"
COMPANION = HOME / "full-validation-NEVER-APPLY.tfplan"
POLICY = "azapi_resource.project_policy[0]"
EXCLUDED_CHECKS = frozenset({
    "azapi_resource.fireworks_backend", "azapi_resource.glm_backend", "azapi_resource.glm_named_value",
    "azapi_resource.project_child", "var.excluded_routes", "var.glm_credential_storage",
    "var.glm_secret_identifier", "var.global_policy_format", "var.rate_limit_window_seconds",
})


def configure():
    b.HOME = HOME
    b.INPUT = HOME / "inputs.tfvars.json"
    b.PLAN = HOME / "fragment-targeted.tfplan"


def resolved(plan):
    rt.require(plan.get("applyable") is True and not plan.get("errored")
               and not plan.get("deferred_changes"), "resolved_applyable_plan_required")
    rt.require(bool(plan.get("checks")) and all(c.get("status") == "pass" for c in plan["checks"]),
               "all_saved_plan_checks_required")


def companion_guard(plan, stored, live_policy):
    """Prove the full-root render; this plan is categorically not applyable here."""
    resolved(plan)
    writes = {r["address"]: r["change"] for r in plan["resource_changes"]
              if r["change"]["actions"] not in (["read"], ["no-op"])}
    rt.require(set(writes) == {b.ADDRESS, POLICY}, "companion_exact_known_changes_only")
    c = writes[POLICY]
    rt.require(c["actions"] == ["update"], "companion_policy_not_replacement")
    before, after = [c[k]["body"]["properties"] for k in ("before", "after")]
    rt.require(before["format"] == "xml" and after["format"] == "rawxml"
               and policy_structure(before["value"]) == policy_structure(after["value"])
               == policy_structure(live_policy), "companion_exact_live_policy_semantics")
    rt.require(stored["body"] == c["after"]["body"], "stored_policy_exact_current_render")
    old, new = deepcopy(c["before"]), deepcopy(c["after"])
    new["body"], new["output"] = old["body"], old.get("output")
    rt.require(old == new, "companion_no_other_policy_field_change")
    normalized = deepcopy(plan)
    pc = next(r["change"] for r in normalized["resource_changes"] if r["address"] == POLICY)
    pc["actions"] = ["no-op"]
    # This is companion-only proof, NOT a waiver of the original release guard.
    # The actual release must never contain a policy update at all.
    summary = b.guard(normalized)
    return {"scope": summary, "policy_before_format": before["format"],
            "policy_after_format": after["format"], "stored_equals_render_bytes": True,
            "live_semantics_equal": True, "stored_render_sha256": b.sha(after["value"]),
            "companion_never_apply": True}


def targeted_guard(plan, companion):
    resolved(companion)
    rt.require(plan.get("applyable") is True and not plan.get("errored")
               and not plan.get("deferred_changes"), "resolved_target_plan_required")
    rt.require(plan["variables"] == companion["variables"], "all_expanded_inputs_equal")
    writes = {r["address"]: r["change"]["actions"] for r in plan["resource_changes"]
              if r["change"]["actions"] not in (["read"], ["no-op"])}
    rt.require(writes == {b.ADDRESS: ["create"]}, "target_exact_one_fragment_create_no_policy_write")
    actual = next(r for r in plan["resource_changes"] if r["address"] == b.ADDRESS)
    full = next(r for r in companion["resource_changes"] if r["address"] == b.ADDRESS)
    rt.require(actual["change"] == full["change"], "target_fragment_matches_full_companion")
    def check_address(check):
        address = check["address"]
        return address["to_display"] if isinstance(address, dict) else address
    expected_checks = {check_address(c): c["status"] for c in companion["checks"]}
    rt.require(bool(plan.get("checks")) and all(expected_checks.get(check_address(c)) == "pass"
               and (c["status"] == "pass" or (c["status"] == "unknown" and check_address(c) in EXCLUDED_CHECKS))
               for c in plan["checks"]),
               "target_checks_bound_to_full_validation")
    # Reuse the unchanged original exact-body/profile guard with companion
    # coverage for objects intentionally excluded by -target. The targeted
    # resource_changes are checked above BEFORE any proof augmentation.
    combined = deepcopy(companion)
    policy = next(r["change"] for r in combined["resource_changes"] if r["address"] == POLICY)
    policy["actions"] = ["no-op"]
    summary = b.guard(combined)
    return {**summary, "target": b.ADDRESS, "full_companion_required": True,
            "policy_writes_in_release": 0,
            "companion_resolved_excluded_checks": sorted(check_address(c) for c in plan["checks"] if c["status"] == "unknown")}


class Targeted(b.Bootstrap):
    def collection(self):
        response = self.arm("/policyFragments")
        print(json.dumps({"keys": sorted(response), "count": response.get("count"),
                          "length": len(response["value"]), "has_next": bool(response.get("nextLink"))}), flush=True)

    def sources(self):
        result = super().sources()
        for path in (Path(__file__), rt.ROOT / "scripts/deployment/poc_fragment_targeted_validation.py"):
            result[path.relative_to(rt.ROOT).as_posix()] = b.sha(path.read_bytes())
        return result

    def preflight(self):
        rt.require(not (ORIGINAL / "apply-intent.json").exists(), "original_apply_intent_reconcile_only")
        rt.require(not (HOME / "preflight.json").exists(), "exclusive_preflight_already_recorded")
        super().preflight()
        b.checkpoint("original_rejection_retained", original_plan_sha256=b.sha((ORIGINAL / "fragment.tfplan").read_bytes()),
                     original_result_sha256=b.sha((ORIGINAL / "result.json").read_bytes()),
                     original_never_apply=True, original_failure="exactly_one_fragment_write", cloud_writes=0)

    def parsed_companion(self):
        return json.loads(self.terraform("show", "-json", str(COMPANION)))

    def prove_companion(self, plan):
        state = json.loads(self.terraform("show", "-json"))
        stored = next(r["values"] for r in state["values"]["root_module"]["resources"] if r["address"] == POLICY)
        return companion_guard(plan, stored, self.policy())

    def prepare(self):
        rt.require(not any((HOME / n).exists() for n in ("plan-intent.json", "apply-intent.json", COMPANION.name, b.PLAN.name)),
                   "exclusive_plan_exists_never_overwrite_or_replay")
        rt.require(self.exact() is None, "fragment_now_exists_verify_only")
        rt.require(self.protected_complete() == b.load(HOME / "baseline.json"), "fresh_full_baseline_changed")
        rt.require(b.sha((b.TFROOT / "terraform.tfstate").read_bytes()) == b.load(HOME / "state-before-summary.json")["sha256"],
                   "existing_state_changed")
        inputs = b.load(HOME / "predecessor-inputs.tfvars.json")
        inputs.update(poc_settings_bootstrap_enabled=True, poc_controls_enabled=False, poc_publisher_permissions_verified=False)
        rt.save(b.INPUT, inputs)
        rt.require(self.terraform("workspace", "show").strip() == "default", "default_workspace")
        self.terraform("init", "-input=false", "-lockfile=readonly", "-no-color")
        self.terraform("validate", "-no-color")
        with (HOME / "plan-intent.json").open("x") as handle:
            json.dump({"at_utc": datetime.now(UTC).isoformat(), "target": b.ADDRESS,
                       "full_companion_never_apply": True}, handle)
        b.checkpoint("fresh_full_validation_companion_started", cloud_writes=0)
        args = ("-input=false", "-no-color", "-lock-timeout=30s", "-var-file=" + str(b.INPUT))
        self.terraform("plan", *args, "-out=" + str(COMPANION))
        full = self.parsed_companion()
        diagnosis = self.prove_companion(full)
        rt.save(HOME / "policy-canonicalization-proof.json", diagnosis)
        b.checkpoint("full_companion_proven_never_apply", **diagnosis, cloud_writes=0)
        rt.require(self.exact() is None, "fragment_created_during_plan_verify_only")
        self.terraform("plan", *args, "-target=" + b.ADDRESS, "-out=" + str(b.PLAN))
        parsed = json.loads(self.terraform("show", "-json", str(b.PLAN)))
        summary = targeted_guard(parsed, full)
        rt.require(b.sha((b.TFROOT / "terraform.tfstate").read_bytes()) == b.load(HOME / "state-before-summary.json")["sha256"],
                   "planning_must_not_mutate_state")
        review = {"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": b.sha(b.PLAN.read_bytes()),
                  "sources": self.sources(), "baseline_sha256": fs.sha(b.load(HOME / "baseline.json")),
                  "scope": summary, "tests": b.load(HOME / "tests.json"),
                  "refreshed_companion_sha256": b.sha(COMPANION.read_bytes()),
                  "original_plan_sha256": b.sha((ORIGINAL / "fragment.tfplan").read_bytes()),
                  "original_result_sha256": b.sha((ORIGINAL / "result.json").read_bytes())}
        rt.save(HOME / "review.json", review)
        b.checkpoint("targeted_saved_plan_guard_passed", plan_sha256=review["plan_sha256"], scope=summary, cloud_writes=0)

    def check(self, live=True):
        review = b.load(HOME / "review.json")
        rt.require(review["sources"] == self.sources(), "source_or_input_drift")
        rt.require(review["plan_sha256"] == b.sha(b.PLAN.read_bytes())
                   and review["refreshed_companion_sha256"] == b.sha(COMPANION.read_bytes()), "bound_saved_plan_drift")
        rt.require(review["original_plan_sha256"] == b.sha((ORIGINAL / "fragment.tfplan").read_bytes())
                   and review["original_result_sha256"] == b.sha((ORIGINAL / "result.json").read_bytes())
                   and not (ORIGINAL / "apply-intent.json").exists(), "original_rejection_must_remain_untouched")
        full = self.parsed_companion()
        targeted_guard(json.loads(self.terraform("show", "-json", str(b.PLAN))), full)
        if live:
            rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at_utc"]) < timedelta(hours=2), "plan_expired")
            rt.require(b.sha((b.TFROOT / "terraform.tfstate").read_bytes()) == b.load(HOME / "state-before-summary.json")["sha256"],
                       "preapply_state_changed")
            self.prove_companion(full)
            rt.require(self.protected_complete() == b.load(HOME / "baseline.json"), "live_full_baseline_drift")
            # Last resource read before the exclusive apply marker: do not leave
            # a full-baseline collection window between existence check/apply.
            rt.require(self.exact() is None, "fragment_exists_verify_only_no_overwrite")
        return review

    def review_existing(self):
        """Resolve excluded checks from real full proof; NEVER replan/overwrite."""
        rt.require(not any((HOME / n).exists() for n in ("review-intent.json", "review.json", "apply-intent.json")),
                   "exclusive_existing_review_only")
        rt.require((HOME / "plan-intent.json").exists() and b.PLAN.exists() and COMPANION.exists(), "both_existing_plans_required")
        plan_hash, companion_hash = b.sha(b.PLAN.read_bytes()), b.sha(COMPANION.read_bytes())
        with (HOME / "review-intent.json").open("x") as handle:
            json.dump({"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": plan_hash,
                       "companion_sha256": companion_hash, "no_replan_or_overwrite": True}, handle)
        frozen = self.sources()
        junit = HOME / "existing-plan-review-tests.xml"
        rt.require(not junit.exists(), "review_test_proof_exists")
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/unit/test_poc_fragment_bootstrap.py",
                            "tests/unit/test_poc_controls.py", "tests/unit/test_fireworks_addition.py",
                            "tests/contract/test_gateway_dev_policy.py", "--junitxml=" + str(junit)],
                           cwd=rt.ROOT, env=rt.ENV, capture_output=True, text=True, encoding="utf-8")
        with (HOME / "existing-plan-review-pytest.log").open("x", encoding="utf-8") as handle:
            handle.write(p.stdout + p.stderr)
        rt.require(p.returncode == 0, "existing_review_tests_failed")
        suites = list(ET.parse(junit).getroot())
        passed = sum(int(s.get("tests", 0)) for s in suites)
        rt.require(passed > 0 and not any(int(s.get(k, 0)) for s in suites for k in ("errors", "failures")), "supplemental_tests_required")
        rt.require(frozen == self.sources(), "source_changed_during_review_tests")
        full = self.parsed_companion()
        diagnosis = self.prove_companion(full)
        parsed = json.loads(self.terraform("show", "-json", str(b.PLAN)))
        summary = targeted_guard(parsed, full)
        rt.require(b.sha((b.TFROOT / "terraform.tfstate").read_bytes()) == b.load(HOME / "state-before-summary.json")["sha256"],
                   "existing_state_changed")
        rt.require(b.sha(b.PLAN.read_bytes()) == plan_hash and b.sha(COMPANION.read_bytes()) == companion_hash,
                   "existing_plan_bytes_changed")
        review = {"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": plan_hash,
                  "sources": frozen, "baseline_sha256": fs.sha(b.load(HOME / "baseline.json")), "scope": summary,
                  "tests": b.load(HOME / "tests.json"), "refreshed_companion_sha256": companion_hash,
                  "original_plan_sha256": b.sha((ORIGINAL / "fragment.tfplan").read_bytes()),
                  "original_result_sha256": b.sha((ORIGINAL / "result.json").read_bytes()),
                  "supplemental_tests": {"python_tests": passed, "junit_sha256": b.sha(junit.read_bytes()), "path": junit.name},
                  "policy_canonicalization": diagnosis, "no_plan_replay_or_overwrite": True}
        with (HOME / "review.json").open("x", encoding="utf-8") as handle:
            json.dump(review, handle, indent=2)
        b.checkpoint("existing_targeted_plan_review_passed", plan_sha256=plan_hash, scope=summary,
                     supplemental_python_tests=passed, cloud_writes=0, no_plan_replay_or_overwrite=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("preflight", "tests", "plan", "review", "validate", "apply", "verify", "collection"))
    stage = parser.parse_args().stage
    configure()
    try:
        run = Targeted()
        if stage == "validate":
            from scripts.deployment.poc_fragment_targeted_validation import validate
            validate(run)
        else:
            getattr(run, {"plan": "prepare", "review": "review_existing"}.get(stage, stage))()
    except Exception as error:
        b.checkpoint("stage_failed", failed_stage=stage, error_type=type(error).__name__,
                     reason=str(error) if isinstance(error, RuntimeError) else "sensitive_diagnostic_suppressed",
                     apply_intent_exists=(HOME / "apply-intent.json").exists())
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()