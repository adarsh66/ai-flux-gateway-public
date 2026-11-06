"""Reconcile completed apply and independent proof; never retry either entrypoint."""
from datetime import UTC, datetime
import json
import os

from scripts.deployment import inventory_persistence_apply_once as a


if __name__ == "__main__":
    r = a.r
    result = r.old.load(a.OUT / "apply-result.json")
    independent = a.HOME / "independent-live-verification01"
    proof = r.old.load(independent / "verification-failure.json")
    a.require(result["exit_code"] == 0 and result["summary"] == [0, 1, 0] and result["apply_attempts"] == 1, "actual_single_apply_result")
    a.require(proof["guard"] == "http_health_not_200_parent_must_review_NO_WRITE_RETRY" and
              proof["http_health"]["status"] == 403, "precise_retained_http_limitation")
    for key in ("all_other_protected_equal", "supplemental_equal", "all_four_settings_equal", "other_three_images_equal",
                "state_api_digest_verified", "backend_lock_released", "live_and_state_image_applied"):
        a.require(proof[key] is True, "independent_proof:" + key)
    a.require(proof["state_serial_before"] == 109 and proof["state_serial_after"] == 110 and proof["protected_components"] == 13,
              "independent_state_protected_binding")
    comparison = r.old.load(independent / "protected-comparison.json")
    a.require(comparison["other_drift_paths"] == [] and comparison["baseline_sha256"] == comparison["normalized_after_sha256"], "whole_protected_equality")
    integrity = a.integrity()
    intent = r.old.load(a.HOME / "live-apply-intent.json")
    a.require(a.sha(r.rt.ROOT / "scripts/deployment/inventory_persistence_apply_once.py") == intent["execution_module_sha256"], "executor_unchanged")
    for name in ("stdout", "stderr"):
        a.require(a.sha(a.OUT / ("apply." + name + ".private.log")) == result[name + "_sha256"], "private_output_integrity:" + name)
    workers = r.backend.workers()
    a.require(not any(w["mutation_worker"] or w["pid"] in {intent["pid"], r.old.load(a.OUT / "terraform-process.json")["pid"]}
                      for w in workers if w["pid"] != os.getpid()), "existing_apply_or_competing_worker_active")
    record = {
        "at_utc": datetime.now(UTC).isoformat(),
        "status": "applied_protected_state_verified_direct_http_403_parent_browser_pending",
        "release": a.HOME.relative_to(r.rt.ROOT).as_posix(),
        "plan_sha256": a.PLAN_SHA, "source_sha256": a.SOURCE_SHA, "image": a.IMAGE,
        "apply_started_at_utc": result["started_at_utc"], "apply_finished_at_utc": result["finished_at_utc"],
        "apply_exit_code": 0, "apply_attempts": 1,
        "terraform_resources": {"added": 0, "changed": 1, "destroyed": 0},
        "independent_verification_finished_at_utc": proof["finished_at_utc"],
        "protected_components": 13, "all_other_protected_equal": True,
        "all_four_settings_equal": True, "other_three_images_equal": True, "supplemental_equal": True,
        "baseline_sha256": comparison["baseline_sha256"],
        "normalized_after_sha256": comparison["normalized_after_sha256"],
        "state_lineage": proof["state_lineage"], "state_serial_before": 109, "state_serial_after": 110,
        "state_api_digest_verified": True, "backend_lock_released": True,
        "http_health": proof["http_health"], "http_health_verified": False,
        "browser_verified": False, "metadata_503_cleared_in_portals_verified": False,
        "parent_browser_confirmation_required": True, "overall_task_complete": False,
        "validation_reruns": 0, "builds": 0, "new_plans": 0, "inference_requests": 0,
        "permissions_network_identity_database_auto_writes": 0, "other_image_updates": 0,
        "metadata_timestamp_restamps": 0, "never_apply_companion_applied": False,
        "bound_tooling_changed": False, "final_artifact_integrity": integrity,
        "active_workers": workers, "competing_mutation_workers": 0, "apply_workers_active": 0,
        "evidence_sha256": {
            path.relative_to(a.HOME).as_posix(): a.sha(path) for path in (
                a.HOME / "live-apply-intent.json", a.OUT / "apply-result.json",
                independent / "verification-failure.json", independent / "protected-comparison.json",
                independent / "supplemental-after.json", independent / "state-head-after.json",
                independent / "http-health.json")},
        "retry_authorized": False,
        "next_action": "Parent checks normal authenticated admin model-router and customer models; no token extraction or inference. Do not retry apply.",
    }
    r.backend.save(a.HOME, "deployment-handoff.json", record)
    r.backend.save(r.rt.ROOT / ".azure", "inventory-persistence-deployment-result.json", record)
    print(json.dumps(record), flush=True)