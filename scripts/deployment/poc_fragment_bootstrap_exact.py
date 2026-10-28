"""Preserve refreshed rejection, resolve APIM export-only drift without writes.

No lifecycle ignore is added to the API policy, and no refresh-only apply/state
mutation is used. A fresh full refreshed companion authenticates real reads;
the release is full-root with refresh=false and exactly one create. All existing
objects must be no-op in both plans, except the proved XML export representation.
"""
from datetime import UTC, datetime
import json

from scripts.deployment import poc_fragment_bootstrap as b
from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment.project_route_demo import policy_structure

COMPANION = b.HOME / "rejected-refreshed-never-apply.tfplan"


def companion_guard(run):
    original = json.loads(run.terraform("show", "-json", str(COMPANION)))
    rt.require(original["applyable"] and not original.get("errored")
               and all(c["status"] == "pass" for c in original.get("checks", [])), "companion_must_be_resolved")
    writes = {r["address"]: r["change"] for r in original["resource_changes"]
              if r["change"]["actions"] not in (["read"], ["no-op"])}
    rt.require(set(writes) == {b.ADDRESS, "azapi_resource.project_policy[0]"}
               and writes[b.ADDRESS]["actions"] == ["create"]
               and writes["azapi_resource.project_policy[0]"]["actions"] == ["update"], "only_known_representation_drift_allowed")
    change = writes["azapi_resource.project_policy[0]"]
    before, after = [change[k]["body"]["properties"] for k in ("before", "after")]
    rt.require(before["format"] == "xml" and after["format"] == "rawxml"
               and policy_structure(before["value"]) == policy_structure(after["value"]), "export_representation_only")
    old, new = b.deepcopy(change["before"]), b.deepcopy(change["after"])
    new["body"], new["output"] = old["body"], old.get("output")
    rt.require(old == new, "no_nonrepresentation_policy_delta")
    rt.require(policy_structure(run.policy()) == policy_structure(after["value"]), "live_policy_not_equivalent")
    state = json.loads(run.terraform("show", "-json"))
    stored = next(r["values"] for r in state["values"]["root_module"]["resources"]
                  if r["address"] == "azapi_resource.project_policy[0]")
    rt.require(stored["body"] == change["after"]["body"], "stored_desired_policy_must_already_match_exactly")
    return original


def prepare():
    run = b.Bootstrap()
    rt.require(not (b.HOME / "apply-intent.json").exists()
               and not (b.HOME / "representation-plan-intent.json").exists(), "new_never_applied_attempt_only")
    # Copy bytes before replacing the output path; retain original evidence forever.
    with COMPANION.open("xb") as handle:
        handle.write(b.PLAN.read_bytes())
    b.checkpoint("representation_companion_archived", rejected_plan_sha256=b.sha(COMPANION.read_bytes()), cloud_writes=0)
    companion_guard(run)
    rt.require(run.protected_complete() == b.load(b.HOME / "baseline.json"), "fresh_full_baseline_changed")
    rt.require(run.exact() is None, "fragment_exists_no_overwrite")
    rt.require(b.sha((b.TFROOT / "terraform.tfstate").read_bytes()) == b.load(b.HOME / "state-before-summary.json")["sha256"], "existing_state_changed")
    with (b.HOME / "representation-plan-intent.json").open("x") as handle:
        json.dump({"at_utc": datetime.now(UTC).isoformat(), "companion_sha256": b.sha(COMPANION.read_bytes()),
                   "reason": "fresh_refreshed_companion_proves_only_xml_export_drift", "companion_never_apply": True}, handle)
    run.terraform("validate", "-no-color")
    run.terraform("plan", "-refresh=false", "-input=false", "-no-color", "-lock-timeout=30s",
                  "-var-file=" + str(b.INPUT), "-out=" + str(b.PLAN))
    parsed = json.loads(run.terraform("show", "-json", str(b.PLAN)))
    summary = b.guard(parsed)
    rt.require(parsed["variables"] == json.loads(run.terraform("show", "-json", str(COMPANION)))["variables"], "companion_inputs_must_match_exactly")
    review = {"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": b.sha(b.PLAN.read_bytes()),
              "sources": run.sources(), "baseline_sha256": fs.sha(b.load(b.HOME / "baseline.json")),
              "scope": summary, "tests": b.load(b.HOME / "tests.json"),
              "refreshed_companion_sha256": b.sha(COMPANION.read_bytes()),
              "refresh_representation_resolved_without_policy_or_state_write": True}
    rt.save(b.HOME / "review.json", review)
    b.checkpoint("saved_plan_guard_passed", plan_sha256=review["plan_sha256"], scope=summary,
                 refreshed_companion_sha256=review["refreshed_companion_sha256"], cloud_writes=0)


if __name__ == "__main__":
    try:
        prepare()
    except Exception as error:
        b.checkpoint("stage_failed", failed_stage="representation_resolved_plan",
                     error_type=type(error).__name__, reason=str(error) if isinstance(error, RuntimeError) else "sensitive_diagnostic_suppressed")
        raise SystemExit(1) from None