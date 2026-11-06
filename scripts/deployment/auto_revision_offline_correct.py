"""Prepare ONLY a fresh take-offline successor after actual PUT ignored flags.

No apply/online/scoring entrypoint. Original plan, intent and readbacks are never
overwritten/replayed; the retained create review is NOT review of this successor.
"""
from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys

from scripts.deployment import auto_revision_execute as e

p, v = e.p, e.v
ADDRESS = "azapi_update_resource.auto_stage_offline[0]"


def guard(plan, selection):
    p.reservation(selection["revision"], selection["owner_nonce"], selection["baseline_sha256"])
    p.rt.require(plan.get("applyable") is True and not plan.get("errored")
                 and not plan.get("deferred_changes"), "resolved_offline_patch_plan")
    values = {k: value["value"] for k, value in plan["variables"].items()}
    p.rt.require(values.get("auto_staging_take_offline") is True
                 and values.get("auto_staging_revision") == selection
                 and values.get("auto_routing_enabled") is False
                 and values.get("poc_controls_enabled") is False
                 and values.get("admin_settings_enabled") is False, "exact_offline_inputs")
    writes = [r for r in plan["resource_changes"] if r["change"]["actions"] not in (["read"], ["no-op"])]
    p.rt.require(len(writes) == 1 and writes[0]["address"] == ADDRESS, "offline_patch_ONLY")
    row, change = writes[0], writes[0]["change"]
    p.rt.require(row.get("mode") == "managed" and change["actions"] == ["create"]
                 and change.get("before") is None, "new_patch_state_record_only")
    after = change["after"]
    p.rt.require(after["type"] == "Microsoft.ApiManagement/service/apis@2024-05-01"
                 and after["resource_id"].lower() == (p.APIM + "/apis/" + p.API + ";rev=" + selection["revision"]).lower()
                 and after["body"] == {"properties": {"isOnline": False}}
                 and after["body"]["properties"]["isOnline"] is False, "exact_offline_patch_body")
    p.rt.require(not any(p.any_unknown(value) for key, value in change.get("after_unknown", {}).items()
                         if key not in {"id", "output"}), "unknown_patch_input")
    return {"address": ADDRESS, "state_actions": ["create"], "cloud_operation": "PATCH existing owned revision",
            "body": {"properties": {"isOnline": False}}, "current_changes": 0,
            "api_creates": 0, "scoring_requests": 0, "completion_requests": 0}


def main():
    p.rt.require(sys.argv[1:] == ["prepare-once"], "preparation_only_no_apply")
    # correction01 stopped at Terraform validate: update_resource has no
    # schema_validation_enabled attribute. No plan/write was attempted there.
    # Preserve that failure and use a distinct corrected preparation package.
    out = e.HOME / "offline-correction02"
    p.rt.require(not out.exists(), "existing_correction_reconcile_no_replan")
    p.release.fs.protect(out)
    v.OUT = out
    stage = "ownership"
    save = v.save
    try:
        p.persistence.transport()
        p.require_no_competing_workers(p.backend.workers())
        markers = p.backend.markers()
        save("historical-markers-before.json", markers)
        account = p.rt.cli(["account", "show"])
        p.rt.require(account["id"] == p.rt.SUB and account["tenantId"] == p.rt.TENANT, "exact_account")
        applied = v.load("execution01/apply-result.json")
        p.rt.require(applied["attempts"] == 1 and applied["exit_code"] == 0
                     and applied["saved_plan_sha256"] == v.PLAN_SHA, "original_create_receipt")
        selection = v.load("result.json")["reservation"]
        rows = [p.summarize_revision(r) for r in p.collection("https://management.azure.com" + p.APIM
                + "/apis/" + p.API + "/revisions?api-version=" + p.VERSION)]
        save("revisions-before.json", rows)
        owned = [r for r in rows if r["revision"] == selection["revision"]]
        p.rt.require(len(owned) == 1 and owned[0]["existing_noncurrent_candidate"]
                     and owned[0]["is_online"] is True
                     and sum(r["is_current"] is True and r["revision"] == "1" for r in rows) == 1,
                     "actual_owned_noncurrent_online_only")
        api = p.release.ProductRun().arm("/apis/" + p.API + ";rev=" + selection["revision"])
        p.rt.require(api["properties"]["apiRevisionDescription"] == p.expected_body(selection)["properties"]["apiRevisionDescription"]
                     and api["properties"]["path"] == "dev/llm/v1"
                     and api["properties"]["subscriptionRequired"] is True, "exact_owned_revision_metadata")
        state_path = p.ROOT / "terraform.tfstate"
        state = json.loads(state_path.read_bytes())
        state_hash = p.sha(state_path)
        p.rt.require(state["lineage"] == p.LINEAGE and not (p.ROOT / ".terraform.tfstate.lock.info").exists(), "existing_state_owner")
        owned_state = [r for r in state["resources"] if r["type"] == "azapi_resource" and r["name"] == "auto_stage_revision"]
        p.rt.require(len(owned_state) == 1 and len(owned_state[0]["instances"]) == 1
                     and owned_state[0]["instances"][0]["attributes"]["id"].lower() == api["id"].lower(), "exact_managed_owner")
        save("state-owner.json", {"lineage": state["lineage"], "serial": state["serial"], "sha256": state_hash})
        stage = "protected_baseline"
        before = p.release.snapshot()
        supplement = v.supplemental(before)
        p.rt.require(before == v.load("protected-before.json") and supplement == v.load("supplemental-before.json"), "all13_original_baseline")
        save("protected-before.json", before)
        save("supplemental-before.json", supplement)
        head = p.backend.blob_head()
        save("remote-head-before.json", head)
        inputs = deepcopy(v.load("inputs.tfvars.json"))
        inputs["auto_staging_take_offline"] = True
        save("inputs.tfvars.json", inputs)
        frozen = p.sources()
        for path in (Path(__file__), Path(e.__file__), Path(v.__file__),
                     p.rt.ROOT / "tests/unit/test_auto_revision_offline_correct.py"):
            frozen[path.relative_to(p.rt.ROOT).as_posix()] = p.sha(path)
        save("sources.json", frozen)
        stage = "actual_recipe_preflight"
        v.tf("init", "-input=false", "-lockfile=readonly", "-no-color")
        v.tf("fmt", "-check")
        validation = json.loads(v.tf("validate", "-json"))
        p.rt.require(validation["valid"] and not validation["error_count"], "actual_tf_validate")
        p.rt.require(v.tf("workspace", "show").strip() == "default", "default_workspace")
        save("terraform-validate.json", validation)
        stage = "fresh_plans"
        save("plan-intent.json", {"at_utc": p.now(), "only": ADDRESS, "no_apply_entrypoint": True,
             "original_create_never_replay": True, "companion_never_apply": True})
        def plan(name, target=False):
            path = out / name
            args = [p.rt.TF, "-chdir=" + str(p.ROOT), "plan", "-input=false", "-no-color", "-lock-timeout=30s",
                    "-var-file=" + str(out / "inputs.tfvars.json"), "-out=" + str(path)]
            if target:
                args.append("-target=" + ADDRESS)
            result = subprocess.run(args, cwd=p.rt.ROOT, env=v.environment(), capture_output=True,
                                    encoding="utf-8", errors="replace", timeout=900)
            with (out / (name + ".private.log")).open("x", encoding="utf-8") as f:
                f.write(result.stdout + result.stderr)
            p.rt.require(result.returncode == 0, "fresh_plan_failed_retained_no_retry")
            return json.loads(v.tf("show", "-json", str(path)))
        full = plan("full-NEVER-APPLY.tfplan")
        target = plan("take-offline.tfplan", target=True)
        scope = guard(target, selection)
        p.rt.require(target["configuration"] == full["configuration"] and target["variables"] == full["variables"], "exact_companion")
        p.rt.require(next(r for r in full["resource_changes"] if r["address"] == ADDRESS)["change"]
                     == next(r for r in target["resource_changes"] if r["address"] == ADDRESS)["change"], "exact_companion_patch")
        for path in (out / "full-NEVER-APPLY.tfplan", out / "take-offline.tfplan"):
            p.rt.require(v.archive(path) == {k: state[k] for k in ("lineage", "serial")}, "embedded_state")
        save("scope.json", scope)
        save("companion-writes.json", [{"address": r["address"], "actions": r["change"]["actions"]}
             for r in full["resource_changes"] if r["change"]["actions"] not in (["read"], ["no-op"])])
        stage = "roles_and_final_readback"
        v.policy_and_roles()
        after = p.release.snapshot()
        save("protected-after.json", after)
        p.rt.require(after == before and v.supplemental(after) == supplement, "protected_drift")
        p.rt.require(p.sha(state_path) == state_hash, "state_drift")
        p.rt.require(all(p.sha(p.rt.ROOT / name) == digest for name, digest in frozen.items()), "source_drift")
        latest = p.backend.markers()
        prefix = out.relative_to(p.rt.ROOT).as_posix() + "/"
        p.rt.require(all(latest.get(k) == value for k, value in markers.items())
                     and all(k.startswith(prefix) for k in latest.keys() - markers.keys()), "foreign_intent")
        p.require_no_competing_workers(p.backend.workers())
        save("result.json", {"at_utc": p.now(), "status": "prepared_NOT_independently_reviewed_NOT_Validated_NO_APPLY",
             "scope": scope, "saved_plan_sha256": p.sha(out / "take-offline.tfplan"),
             "companion_sha256": p.sha(out / "full-NEVER-APPLY.tfplan"), "source_sha256": p.release.fs.sha(frozen),
             "protected_baseline_sha256": p.release.fs.sha(before), "all13_protected_equal": True,
             "original_native_review_covers_successor": False, "new_independent_agent_review": False,
             "cloud_configuration_writes": 0, "applies": 0, "scoring_requests": 0, "completion_requests": 0,
             "original_create_never_replay": True})
        print((out / "result.json").read_text(encoding="utf-8"), flush=True)
        return 0
    except Exception as exc:
        failure = {"at_utc": p.now(), "stage": stage, "type": type(exc).__name__,
                   "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed",
                   "http_status": getattr(exc, "code", None), "retry_authorized": False, "applies": 0}
        save("failure.json", failure)
        print(json.dumps(failure), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())