"""Prepare one OFFLINE existing-API revision plan; deliberately no apply path.

No historical entrypoint is invoked. Full plans are NEVER APPLY companions.
Independent agent review, policy compilation and actual gateway-MI proof are
distinct gates and are never manufactured by this preparation controller.
"""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import backend_connection_restore_oct29 as backend
from scripts.deployment import inventory_persistence_release as persistence
from scripts.deployment import poc_activation_release as release
from scripts.deployment.auto_identity_readback import collection
from scripts.deployment.auto_live_gate import API, VERSION, require_no_competing_workers, summarize_revision
from scripts.deployment.apim_route_repair import APIM
from scripts.deployment.project_route_demo import policy_structure
from scripts.deployment.project_route_product_access import any_unknown

ROOT = rt.ROOT / "infra/project-route"
ADDRESS = "azapi_resource.auto_stage_revision[0]"
POLICY = "azapi_resource.project_policy[0]"
LINEAGE = "8b19b704-7224-db80-7600-ef2a0cbeef10"
PRIOR_INPUT = rt.HOME / "poc-fragment-bootstrap-20261028-targeted01/inputs.tfvars.json"


def now():
    return datetime.now(UTC).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reservation(revision, nonce, baseline_sha256):
    rt.require(isinstance(revision, str) and re.fullmatch(r"[1-9][0-9]{0,5}", revision)
               and int(revision) > 1, "exact_noncurrent_revision")
    rt.require(re.fullmatch(r"[a-f0-9]{32}", nonce) is not None, "exact_owner_nonce")
    rt.require(re.fullmatch(r"[a-f0-9]{64}", baseline_sha256) is not None, "exact_complete_baseline_hash")
    return {"revision": revision, "owner_nonce": nonce, "baseline_sha256": baseline_sha256}


def expected_body(value):
    value = reservation(value["revision"], value["owner_nonce"], value["baseline_sha256"])
    return {"properties": {"path": "dev/llm/v1", "sourceApiId": APIM + "/apis/" + API,
        "apiRevision": value["revision"], "isCurrent": False, "isOnline": False,
        "apiRevisionDescription": "Auto offline stage owner=" + value["owner_nonce"]
        + " baseline=" + value["baseline_sha256"]}}


def require_absent_revision(rows, revision):
    rt.require(rows and sum(r["is_current"] is True for r in rows) == 1,
               "one_actual_current_revision_required")
    rt.require(not any(r["revision"] == revision for r in rows), "revision_collision_no_adoption")
    rt.require(all(r["revision"].isdecimal() for r in rows), "revision_list_shape")


def guard_target(plan, companion, supplied):
    rt.require(plan.get("applyable") is True and not plan.get("errored")
               and not plan.get("deferred_changes"), "target_resolved")
    rt.require(not companion.get("errored") and not companion.get("deferred_changes")
               and companion.get("checks")
               and all(c["status"] == "pass" for c in companion["checks"]), "full_checks_required")
    rt.require(plan.get("variables") == companion.get("variables")
               and plan.get("configuration") == companion.get("configuration"), "identical_full_companion")
    values = {k: v["value"] for k, v in plan["variables"].items()}
    rt.require(all(values.get(k) == v for k, v in supplied.items()), "exact_supplied_inputs")
    rt.require(values.get("auto_routing_enabled") is False
               and values.get("poc_controls_enabled") is False
               and values.get("allow_product_subscriptions") is True, "all_activation_off")
    writes = [r for r in plan["resource_changes"] if r["change"]["actions"] not in (["read"], ["no-op"])]
    rt.require(len(writes) == 1 and writes[0]["address"] == ADDRESS, "offline_revision_only")
    item = writes[0]
    c = item["change"]
    rt.require(item.get("mode") == "managed" and c["actions"] == ["create"]
               and c.get("before") is None, "new_owned_revision_only")
    after = c["after"]
    selection = supplied["auto_staging_revision"]
    rt.require(after["type"] == "Microsoft.ApiManagement/service/apis@2024-05-01"
               and after["parent_id"].lower() == APIM.lower()
               and after["name"] == API + ";rev=" + selection["revision"]
               and after["body"] == expected_body(selection), "exact_offline_body")
    rt.require(not any(any_unknown(v) for k, v in c.get("after_unknown", {}).items()
                       if k not in {"id", "output"}), "unknown_writable_input")
    full = next(r for r in companion["resource_changes"] if r["address"] == ADDRESS)
    rt.require(c == full["change"], "exact_companion_target")
    checks = {json.dumps(c["address"], sort_keys=True): c["status"] for c in companion["checks"]}
    rt.require(plan.get("checks") and all(checks.get(json.dumps(c["address"], sort_keys=True)) == "pass"
               and c["status"] in {"pass", "unknown"} for c in plan["checks"]), "bound_target_checks")
    return {"address": ADDRESS, "actions": ["create"], "is_current": False, "is_online": False,
            "companion_never_apply": True, "scoring_budget": 0, "completion_budget": 0}


def guard_companion(plan, live_policy):
    """Only a semantically identical API-policy format delta may accompany stage."""
    writes = [r for r in plan["resource_changes"] if r["change"]["actions"] not in (["read"], ["no-op"])]
    rt.require({r["address"] for r in writes} <= {ADDRESS, POLICY}
               and any(r["address"] == ADDRESS for r in writes), "companion_unapproved_write")
    for r in writes:
        if r["address"] == POLICY:
            c = r["change"]
            rt.require(c["actions"] == ["update"], "companion_no_policy_replacement")
            old, new = deepcopy(c["before"]), deepcopy(c["after"])
            rt.require(policy_structure(old["body"]["properties"]["value"])
                       == policy_structure(new["body"]["properties"]["value"])
                       == policy_structure(live_policy), "companion_current_policy_not_equal")
            new["body"], new["output"] = old["body"], old.get("output")
            rt.require(old == new, "companion_other_policy_attribute")
    return {"writes": [{"address": r["address"], "actions": r["change"]["actions"]} for r in writes],
            "never_apply": True, "existing_policy_semantics_unchanged": True}


def sources():
    paths = [*ROOT.glob("*.tf"), ROOT / ".terraform.lock.hcl", Path(__file__),
             rt.ROOT / "tests/unit/test_auto_revision_prepare.py", PRIOR_INPUT,
             * (rt.ROOT / "gateway/policies").glob("*.xml*"),
             * (rt.ROOT / "gateway/catalog").glob("*.json"),
             * (rt.ROOT / "services/control-plane/src/aiflux/pricing").glob("*.json")]
    return {p.relative_to(rt.ROOT).as_posix(): sha(p) for p in paths}


def main():
    rt.require(len(sys.argv) == 1, "preparation_only_no_arguments")
    folder = rt.HOME / ("auto-offline-revision-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    release.fs.protect(folder)
    save = lambda name, value: backend.save(folder, name, value)
    report = {"started_at_utc": now(), "pid": os.getpid(), "evidence": folder.relative_to(rt.ROOT).as_posix(),
              "cloud_configuration_writes": 0, "applies": 0, "scoring_requests": 0,
              "completion_requests": 0, "image_builds": 0, "image_pushes": 0,
              "independent_agent_review_passed": False, "live_auto_enabled": False}
    stage = "exclusive_ownership"

    def tf(*args):
        p = subprocess.run([rt.TF, "-chdir=" + str(ROOT), *args], cwd=rt.ROOT, env=rt.ENV,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        if args[0] not in {"show", "state"} or p.returncode:
            # Private retained diagnostics; never stream policy/state/settings.
            with (folder / ("terraform-" + args[0] + "-" + str(len(list(folder.glob("terraform-*")))) + ".log")).open("x", encoding="utf-8") as f:
                f.write(p.stdout + p.stderr)
        rt.require(p.returncode == 0, "terraform_" + args[0] + "_failed_private_diagnostic_retained")
        return p.stdout

    try:
        workers = backend.workers()
        save("workers-before.json", workers)
        require_no_competing_workers(workers)
        markers = backend.markers()
        save("historical-markers-before.json", markers)
        save("preparation-intent.json", {"at_utc": now(), "cloud_writes": 0,
             "only_plan": ADDRESS, "historical_replay": False, "no_apply_entrypoint": True})
        persistence.transport()
        account = rt.cli(["account", "show"])
        rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "exact_account_context")
        save("account-context.json", {"subscription": account["id"], "tenant": account["tenantId"]})
        stage = "complete_protected_baseline"
        before = release.snapshot()
        rt.require(len(before) == 13, "complete13_baseline")
        save("protected-before.json", before)
        from scripts.deployment.inventory_persistence_apply_once import supplemental
        supplement = supplemental(before)
        save("supplemental-before.json", supplement)
        stage = "revision_and_state_ownership"
        def revisions():
            return [summarize_revision(r) for r in collection("https://management.azure.com" + APIM
                    + "/apis/" + API + "/revisions?api-version=" + VERSION)]
        rows = revisions()
        save("revisions-before.json", rows)
        revision = str(max(int(r["revision"]) for r in rows) + 1)
        require_absent_revision(rows, revision)
        current = release.ProductRun().arm("/apis/" + API)["properties"]
        rt.require(current.get("isCurrent") is True and current["path"] == "dev/llm/v1"
                   and current["subscriptionRequired"] is True, "current_api_contract")
        save("current-api-metadata.json", {k: current.get(k) for k in (
            "apiRevision", "isCurrent", "isOnline", "path", "subscriptionRequired", "provisioningState")})
        state_path = ROOT / "terraform.tfstate"
        state_hash = sha(state_path)
        state = json.loads(state_path.read_bytes())
        rt.require(state["lineage"] == LINEAGE, "existing_root_state_lineage")
        rt.require(not any(r["name"] == "auto_stage_revision" for r in state["resources"]), "existing_stage_reconcile_not_recreate")
        save("state-owner.json", {"lineage": state["lineage"], "serial": state["serial"], "sha256": state_hash,
             "workspace": tf("workspace", "show").strip()})
        rt.require(not (ROOT / ".terraform.tfstate.lock.info").exists(), "existing_state_lock")
        save("remote-runtime-state-head.json", backend.blob_head())
        inputs = json.loads(PRIOR_INPUT.read_text(encoding="utf-8-sig"))
        inputs.update(auto_routing_enabled=False, auto_routing_runtime_evidence_sha256="",
                      auto_staging_revision=reservation(revision, secrets.token_hex(16), release.fs.sha(before)))
        save("inputs.tfvars.json", inputs)
        frozen = sources()
        save("sources.json", frozen)
        stage = "terraform_recipe_preflight"
        tf("init", "-input=false", "-lockfile=readonly", "-no-color")
        tf("fmt", "-check")
        validation = json.loads(tf("validate", "-json"))
        rt.require(validation.get("valid") is True, "actual_tf_validation_failed")
        save("terraform-validate.json", validation)
        addresses = tf("state", "list").splitlines()
        rt.require('azapi_resource.project_child["api"]' in addresses and POLICY in addresses,
                   "current_api_and_policy_existing_state_owner")
        save("managed-addresses.json", addresses)
        stage = "fresh_exact_saved_plans"
        require_no_competing_workers(backend.workers())
        require_absent_revision(revisions(), revision)
        rt.require(sha(state_path) == state_hash and frozen == sources(), "preplan_source_or_state_drift")
        save("plan-intent.json", {"at_utc": now(), "exact_target": ADDRESS,
             "full_companion_never_apply": True, "no_replan_or_retry": True})
        common = ("-input=false", "-no-color", "-lock-timeout=30s", "-var-file=" + str(folder / "inputs.tfvars.json"))
        full_path, target_path = folder / "full-NEVER-APPLY.tfplan", folder / "offline-revision.tfplan"
        tf("plan", *common, "-out=" + str(full_path))
        full = json.loads(tf("show", "-json", str(full_path)))
        companion_proof = guard_companion(full, release.ProductRun().policy())
        save("companion-review.json", companion_proof)
        tf("plan", *common, "-target=" + ADDRESS, "-out=" + str(target_path))
        target = json.loads(tf("show", "-json", str(target_path)))
        scope = guard_target(target, full, inputs)
        save("target-review.json", scope)
        stage = "fresh_complete_protected_comparison"
        after = release.snapshot()
        save("protected-after.json", after)
        rt.require(after == before and supplemental(after) == supplement, "complete_protected_drift")
        rt.require(sha(state_path) == state_hash and frozen == sources(), "planning_source_or_state_changed")
        require_absent_revision(revisions(), revision)
        latest = backend.markers()
        own = folder.relative_to(rt.ROOT).as_posix() + "/"
        rt.require(all(latest.get(k) == v for k, v in markers.items())
                   and all(k.startswith(own) for k in latest.keys() - markers.keys()), "foreign_intent_or_historical_drift")
        workers = backend.workers()
        save("workers-after.json", workers)
        require_no_competing_workers(workers)
        report.update(status="offline_revision_plan_prepared_NOT_independently_validated",
            failed_stage=None, revision=revision, reservation=inputs["auto_staging_revision"],
            saved_plan_sha256=sha(target_path), companion_sha256=sha(full_path),
            source_sha256=release.fs.sha(frozen), protected_baseline_sha256=release.fs.sha(before),
            all13_protected_equal=True, full_settings_and_all_images_unchanged=True,
            state_lineage=state["lineage"], state_serial=state["serial"], state_bytes_unchanged=True,
            scope=scope, blocker="independent_agent_execution_blocked_by_windows_group_policy",
            runtime_contract_proven=False, section7_validated=False)
    except Exception as exc:
        report.update(status="preparation_stopped_no_cloud_write", failed_stage=stage,
            error_type=type(exc).__name__, guard=str(exc) if isinstance(exc, RuntimeError) else "details_suppressed")
    report["finished_at_utc"] = now()
    save("result.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["status"].startswith("offline_revision_plan_prepared") else 2


if __name__ == "__main__":
    raise SystemExit(main())