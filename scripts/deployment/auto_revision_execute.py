"""Exact once-only offline revision execution and separate readback commands.

No plan/rebuild/retry, online transition, diagnostic policy or inference path.
"""
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from scripts.deployment import auto_revision_validate as v

p = v.p
HOME = v.HOME


def integrity():
    proof = v.load("validation01/validation.json")
    p.rt.require(proof["checks_passed"] and proof["saved_plan_sha256"] == v.PLAN_SHA
                 and proof["independent_native_review_retained"], "actual_review_validation_required")
    p.rt.require(datetime.now(UTC) - datetime.fromisoformat(proof["at_utc"]) < timedelta(minutes=30), "validation_freshness_expired_STOP")
    for name, value in proof["evidence"].items():
        path = HOME / "validation01" / name
        p.rt.require(path.resolve().is_relative_to(HOME / "validation01") and p.sha(path) == value, "validation_evidence_changed:" + name)
    p.rt.require(p.sha(v.REVIEW) == v.load("validation01/native-review.json")["sha256"], "native_review_changed")
    p.rt.require(p.sha(HOME / "offline-revision.tfplan") == v.PLAN_SHA, "exact_target_sha")
    return proof


def acknowledgements():
    integrity()
    doc = (p.rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    p.rt.require("2026-10-29T06:12:54.555263+00:00" in doc[:10000] and v.PLAN_SHA in doc[:10000], "actual_section7_required")
    for step in ("RecordProof", "ResolveErrors"):
        v.workflow(step)


def complete():
    integrity()
    p.rt.require(json.loads((p.rt.ROOT / ".azure/validate-status.json").read_bytes()) == {"completedStep": "ResolveErrors"}, "actual_resolve_errors_required")
    doc = (p.rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    p.rt.require("Status: **Validated; offline revision2 create ONLY" in doc[:700], "current_scope_status_required")
    v.workflow("UpdateStatus")
    v.save("completion.json", {"at_utc": p.now(), "status": "Validated", "official_workflow_complete": True,
           "validation_sha256": p.sha(HOME / "validation01/validation.json"), "saved_plan_sha256": v.PLAN_SHA,
           "workflow": {step: p.sha(HOME / "validation01" / ("workflow-" + step + ".json"))
                        for step in ("RecordProof", "ResolveErrors", "UpdateStatus")}})


def apply_once():
    out = HOME / "execution01"
    p.rt.require(not out.exists() and not list(HOME.rglob("*apply-intent*")), "existing_execution_reconcile_ONLY")
    proof = integrity()
    complete = v.load("validation01/completion.json")
    p.rt.require(complete["official_workflow_complete"] and complete["status"] == "Validated"
                 and complete["validation_sha256"] == p.sha(HOME / "validation01/validation.json"), "completed_actual_workflow")
    p.rt.require(json.loads((p.rt.ROOT / ".azure/validate-status.json").read_bytes()) == {"completedStep": "UpdateStatus"}, "official_workflow_status")
    doc = (p.rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    p.rt.require("Status: **Validated; offline revision2 create ONLY" in doc[:700], "current_validated_scope")
    p.release.fs.protect(out)
    v.OUT = out
    p.persistence.transport()
    account = p.rt.cli(["account", "show"])
    p.rt.require(account["id"] == p.rt.SUB and account["tenantId"] == p.rt.TENANT, "exact_account")
    v.fresh("immediately-before")
    p.rt.require(v.tf("workspace", "show").strip() == "default", "default_workspace")
    p.rt.require(v.archive(HOME / "offline-revision.tfplan") == {k: v.load("state-owner.json")[k] for k in ("lineage", "serial")}, "embedded_state")
    integrity()
    p.backend.save(HOME, "live-apply-intent.json", {"at_utc": p.now(), "pid": os.getpid(),
        "saved_plan_sha256": v.PLAN_SHA, "source_sha256": proof["source_sha256"], "attempts": 1,
        "authorization": "explicit user same-existing-API offline revision create once",
        "execution_sha256": p.sha(Path(__file__)), "validator_sha256": p.sha(Path(v.__file__)),
        "never_retry": True, "companion_never_apply": True, "scoring_budget": 0, "completion_budget": 0})
    started = p.now()
    with (out / "apply.stdout.private.log").open("xb") as stdout, (out / "apply.stderr.private.log").open("xb") as stderr:
        child = subprocess.Popen([p.rt.TF, "-chdir=" + str(p.ROOT), "apply", "-input=false", "-no-color",
                                  "-lock-timeout=30s", str(HOME / "offline-revision.tfplan")],
                                 cwd=p.rt.ROOT, env=v.environment(), stdout=stdout, stderr=stderr)
        v.save("process.json", {"at_utc": p.now(), "pid": child.pid, "parent": os.getpid()})
        code = child.wait()
    text = (out / "apply.stdout.private.log").read_text(encoding="utf-8", errors="replace")
    counts = re.findall(r"Apply complete! Resources: (\d+) added, (\d+) changed, (\d+) destroyed\.", text)
    result = {"started_at_utc": started, "finished_at_utc": p.now(), "exit_code": code,
              "summary": [int(x) for x in counts[0]] if len(counts) == 1 else None,
              "saved_plan_sha256": v.PLAN_SHA, "attempts": 1, "retry_authorized": False,
              "stdout_sha256": p.sha(out / "apply.stdout.private.log"),
              "stderr_sha256": p.sha(out / "apply.stderr.private.log"), "independent_readback_required": True}
    v.save("apply-result.json", result)
    print(json.dumps(result), flush=True)
    p.rt.require(code == 0 and result["summary"] == [1, 0, 0], "actual_apply_failure_reconcile_NO_RETRY")


def verify_once():
    out = HOME / "readback01"
    p.rt.require(not out.exists(), "existing_readback_reconcile_no_replay")
    p.release.fs.protect(out)
    v.OUT = out
    p.persistence.transport()
    p.require_no_competing_workers(p.backend.workers())
    selection = v.load("result.json")["reservation"]
    run = p.release.ProductRun()
    api = run.arm("/apis/" + p.API + ";rev=" + selection["revision"])
    props = api["properties"]
    v.save("revision-metadata.json", {"at_utc": p.now(), "id": api["id"],
           **{k: props.get(k) for k in ("apiRevision", "isCurrent", "isOnline", "path", "subscriptionRequired", "apiRevisionDescription", "provisioningState")}})
    # Record actual metadata before enforcing offline so a failed assertion is
    # not mistaken for an absent revision or permission to replay the create.
    baseline = p.release.snapshot()
    v.save("protected-after.json", baseline)
    supplement = v.supplemental(baseline)
    v.save("supplemental-after.json", supplement)
    protected_equal = baseline == v.load("protected-before.json")
    supplemental_equal = supplement == v.load("supplemental-before.json")
    state = json.loads((p.ROOT / "terraform.tfstate").read_bytes())
    owner = v.load("state-owner.json")
    resources = [r for r in state["resources"] if r["type"] == "azapi_resource" and r["name"] == "auto_stage_revision"]
    v.save("state-owner-after.json", {"at_utc": p.now(), "lineage": state["lineage"], "serial": state["serial"],
           "sha256": p.sha(p.ROOT / "terraform.tfstate"), "owned_revision_resources": len(resources)})
    owner_match = (props.get("apiRevisionDescription") == p.expected_body(selection)["properties"]["apiRevisionDescription"])
    result = {"at_utc": p.now(), "pid": os.getpid(), "revision": props.get("apiRevision"),
              "is_current": props.get("isCurrent"), "is_online": props.get("isOnline"),
              "owner_match": owner_match, "all13_protected_equal": protected_equal,
              "supplemental_equal": supplemental_equal, "lineage_unchanged": state["lineage"] == owner["lineage"],
              "serial_before": owner["serial"], "serial_after": state["serial"],
              "auto_enabled": False, "scoring_requests": 0, "completion_requests": 0,
              "runtime_scoring_proven": False, "retry_create_authorized": False}
    result["offline_creation_verified"] = (props.get("isCurrent") is False and props.get("isOnline") is False
        and props.get("subscriptionRequired") is True and owner_match and protected_equal and supplemental_equal
        and props.get("path") == "dev/llm/v1" and result["lineage_unchanged"] and len(resources) == 1)
    v.save("verification.json", result)
    print(json.dumps(result), flush=True)
    p.rt.require(result["offline_creation_verified"], "actual_offline_readback_NOT_proven_STOP")


def reconcile_revision_list():
    """Use explicit flat ApiRevisionContract flags, never default missing to false."""
    out = HOME / "revision-list-readback01"
    p.rt.require(not out.exists(), "existing_revision_list_reconcile_no_replay")
    p.release.fs.protect(out)
    v.OUT = out
    p.persistence.transport()
    p.require_no_competing_workers(p.backend.workers())
    rows = p.collection("https://management.azure.com" + p.APIM + "/apis/" + p.API
                        + "/revisions?api-version=" + p.VERSION)
    v.save("revisions.json", rows)
    summary = [p.summarize_revision(r) for r in rows]
    v.save("summary.json", summary)
    print(json.dumps(summary), flush=True)


def main():
    actions = {"record-resolve": acknowledgements, "complete-workflow": complete,
               "apply-once": apply_once, "verify-once": verify_once,
               "reconcile-revision-list": reconcile_revision_list}
    p.rt.require(len(sys.argv) == 2 and sys.argv[1] in actions, "explicit_action_required")
    try:
        actions[sys.argv[1]]()
        return 0
    except Exception as exc:
        value = {"at_utc": p.now(), "action": sys.argv[1], "type": type(exc).__name__,
                 "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed",
                 "retry_authorized": False, "apply_intent_exists": (HOME / "live-apply-intent.json").exists()}
        if v.OUT.exists():
            v.save("failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", value)
        print(json.dumps(value), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())