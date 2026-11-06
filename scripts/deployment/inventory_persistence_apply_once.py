"""One authorized saved-plan apply; durable intent forbids all mutation retries.

Separate from immutable release tooling. No plan, build, init, refresh or recovery
write exists here. Reconciliation/verification must run in another process.
"""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from scripts.deployment import inventory_persistence_release as r

HOME = r.rt.HOME / "inventory-persistence-20261029-urgent01"
OUT = HOME / "apply-execution01"
ROOT = HOME / "plan/infra/terraform"
PLAN_SHA = "c635c2d09425f840e5340e6ff6475a25a29f8a5dd391fdc444f290d2f59d7e18"
SOURCE_SHA = "47d64e16531ea19d1a77c4da9717a2920701e4abd5c41047f7ca1245de57a7d1"
IMAGE = "pocidstokenexacr.azurecr.io/aiflux-api@sha256:29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64"


def now():
    return datetime.now(UTC).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    r.backend.save(OUT, name, value)


def require(value, code):
    r.rt.require(value, code)


def integrity():
    review = r.old.load(HOME / "review.json")
    handoff = r.old.load(HOME / "handoff.json")
    completed = r.old.load(r.rt.ROOT / ".azure/inventory-persistence-validation-completion.json")
    proof_path = HOME / "independent-validation01/validation.json"
    proof = r.old.load(proof_path)
    require(sha(proof_path) == completed["actual_validation_proof_sha256"] ==
            "12bfb9d82290f1315c577decf6566a0c1f130e10f0d6e5a2c422290bc840be0d", "validation_proof_bytes")
    require(proof["checks_passed"] and completed["status"] == "Validated" and
            completed["official_workflow_complete"] and completed["unresolved_validation_errors"] == [], "official_validation_complete")
    require(r.old.load(r.rt.ROOT / ".azure/validate-status.json") == {"completedStep": "UpdateStatus"}, "persisted_workflow_complete")
    document = (r.rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    require("Status: **Validated." in document[:900] and "### Section 7: Current independent exact-plan validation proof" in document[:1800], "current_validated_section7")
    require([x["completed_step"] for x in completed["workflow_acknowledgements"]] ==
            ["RecordProof", "ResolveErrors", "UpdateStatus"] and all(x["exit_code"] == 0 for x in completed["workflow_acknowledgements"]), "actual_workflow_acknowledgements")
    for record in (review, handoff, proof, completed):
        require(record["plan_sha256"] == PLAN_SHA and record["source_sha256"] == SOURCE_SHA and record["image"] == IMAGE, "release_binding")
    for name, value in proof["evidence"].items():
        require(sha(HOME / "independent-validation01" / name) == value, "retained_evidence_changed:" + name)
    for name, value in review["artifacts"].items():
        path = HOME / name
        require(path.resolve().is_relative_to(HOME) and sha(path) == value, "artifact_changed:" + name)
    for name, value in handoff["tooling"].items():
        require(sha(r.rt.ROOT / name) == value, "bound_tooling_changed:" + name)
    require(r.fs.sha(r.package(HOME)) == SOURCE_SHA and sha(HOME / "api-only.tfplan") == PLAN_SHA, "exact_source_plan")
    historical = r.old.load(HOME / "historical-intents.json")
    markers = r.backend.markers()
    require(all(markers.get(p) == h for p, h in historical.items()), "historical_intents_changed")
    prefix = HOME.relative_to(r.rt.ROOT).as_posix() + "/"
    require(all(p.startswith(prefix) for p in set(markers) - set(historical)), "foreign_release_intent")
    r.fresh(HOME)
    return {"at_utc": now(), "retained_evidence_hashes": len(proof["evidence"]),
            "review_artifacts": len(review["artifacts"]), "tooling_hashes": len(handoff["tooling"]),
            "plan_sha256": PLAN_SHA, "source_sha256": SOURCE_SHA, "image": IMAGE,
            "validation_sha256": sha(proof_path), "historical_intents_unchanged": True}


def workers(name):
    values = r.backend.workers()
    competing = [w for w in values if w["pid"] != os.getpid() and (w["mutation_worker"] or w["name"].lower().startswith("terraform"))]
    save(name, {"at_utc": now(), "own_pid": os.getpid(), "workers": values, "competing_mutation_workers": len(competing)})
    require(not competing, "competing_mutation_worker")
    return values


def env():
    require(Path(r.rt.CA).is_file() and r.rt.ENV.get("AZURE_CLI_DISABLE_CONNECTION_VERIFICATION", "").lower()
            not in {"true", "1", "yes"}, "strict_tls_required")
    # No inherited Terraform command arguments or variable/workspace/data-dir overrides.
    value = {k: v for k, v in r.rt.ENV.items() if not k.startswith(("TF_CLI_ARGS", "TF_VAR_", "TF_LOG"))
             and k not in {"TF_WORKSPACE", "TF_DATA_DIR"}}
    value.update(TF_IN_AUTOMATION="1", TF_INPUT="0", TF_WORKSPACE="default",
                 TF_DATA_DIR=str(ROOT / ".terraform"), PYTHONUTF8="1")
    return value


def tf_read(*args):
    require(args == ("workspace", "show") or args == ("state", "pull"), "only_read_only_state_commands")
    p = subprocess.run([r.rt.TF, "-chdir=" + str(ROOT), *args], cwd=r.rt.ROOT, env=env(),
                       capture_output=True, encoding="utf-8", errors="replace", check=False)
    require(p.returncode == 0, "read_only_terraform_failed")
    return p.stdout


def supplemental(baseline):
    def arm(path, version):
        return r.rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + path + "?api-version=" + version])

    def collection(path, version):
        result = arm(path, version)
        require(isinstance(result.get("value"), list) and not result.get("nextLink"), "complete_supplemental_collection")
        return result

    definitions = {rid: arm(rid, "2022-04-01") for rid in sorted({a[2] for a in baseline["runtime"]["roleAssignments"]})}
    account = r.rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
    policies = collection(account + "/raiPolicies", "2025-06-01")
    deployments = collection(account + "/deployments", "2025-06-01")
    require(len(deployments["value"]) == 13, "13_deployment_bindings")
    networks = {}
    for name in ("virtualNetworks", "networkSecurityGroups", "privateEndpoints", "routeTables"):
        result = collection(r.rt.RG + "/providers/Microsoft.Network/" + name, "2024-05-01")
        networks[name] = {"count": len(result["value"]), "sha256": r.fs.sha(result)}
    return {"role_definition_count": len(definitions), "role_definitions_sha256": r.fs.sha(definitions),
            "role_definition_hashes": {k: r.fs.sha(v) for k, v in definitions.items()},
            "rai_policy_count": len(policies["value"]), "rai_policies_sha256": r.fs.sha(policies),
            "rai_bindings_sha256": r.fs.sha({d["name"]: d["properties"].get("raiPolicyName") for d in deployments["value"]}),
            "networks": networks}


def apply_once():
    require(not OUT.exists(), "existing_execution_reconcile_only")
    require(not list(HOME.rglob("*apply-intent*")) and not (HOME / "applied.json").exists(), "existing_apply_intent_reconcile_only")
    r.fs.protect(OUT)
    workers("workers-before.json")
    save("integrity-before.json", integrity())
    r.transport()
    account = r.rt.cli(["account", "show"])
    require(account["id"] == r.rt.SUB and account["tenantId"] == r.rt.TENANT, "exact_account_context")
    cache = r.old.load(ROOT / ".terraform/terraform.tfstate")
    config = cache["backend"]["config"]
    require(cache["backend"]["type"] == "azurerm", "existing_backend")
    for key, expected in {"subscription_id": r.rt.SUB, "tenant_id": r.rt.TENANT, "storage_account_name": "projpoctokenex",
                          "container_name": "tfstate", "key": "poc-ids-token-ex/main.tfstate", "use_cli": True, "use_azuread_auth": True}.items():
        require(config.get(key) == expected, "backend_binding:" + key)
    require(tf_read("workspace", "show").strip() == "default", "default_workspace")
    state = json.loads(tf_read("state", "pull"))
    expected_state = r.old.load(HOME / "independent-validation01/preflight.json")["state_lineage_serial"]
    require(all(state[k] == expected_state[k] for k in ("lineage", "serial")), "current_saved_state_identity")
    save("state-before-private.json", state)
    baseline = r.release.snapshot()
    save("baseline-before.json", baseline)
    expected = r.old.load(HOME / "baseline.json")
    require(len(baseline) == 13 and baseline == expected, "STOP_current_protected_baseline_changed")
    require(r.fs.sha(baseline) == r.old.load(HOME / "review.json")["baseline_sha256"], "baseline_review_hash")
    supplement = supplemental(baseline)
    save("supplemental-before.json", supplement)
    require(supplement == r.old.load(HOME / "independent-validation01/supplemental-baseline.json")["protected"], "STOP_supplemental_baseline_changed")
    head = r.backend.blob_head()
    save("state-head-before.json", head)
    prior = r.old.load(HOME / "independent-validation01/state-head-after.json")
    require(all(head[k] == prior[k] for k in ("etag", "content_length", "last_modified", "lease_status", "lease_state")), "STOP_state_head_changed")
    require(head["lease_state"] == "available" and head["lease_status"] == "unlocked", "backend_lock_not_available")
    workers("workers-immediately-before.json")
    save("integrity-immediately-before.json", integrity())
    # Atomic x-mode intent is the single mutation boundary. Never remove/reset it.
    r.backend.save(HOME, "live-apply-intent.json", {"at_utc": now(), "pid": os.getpid(), "plan_sha256": PLAN_SHA,
        "source_sha256": SOURCE_SHA, "image": IMAGE, "execution_module_sha256": sha(Path(__file__)),
        "authorization": "explicit user LIVE exact saved target once", "attempt": 1,
        "never_apply_companion": True, "no_retry_even_if_wrapper_fails": True})
    started = now()
    command = [r.rt.TF, "-chdir=" + str(ROOT), "apply", "-input=false", "-no-color", "-lock-timeout=60s", str(HOME / "api-only.tfplan")]
    # stdout/stderr can include secrets: private ACL-protected files only.
    with (OUT / "apply.stdout.private.log").open("xb") as stdout, (OUT / "apply.stderr.private.log").open("xb") as stderr:
        child = subprocess.Popen(command, cwd=r.rt.ROOT, env=env(), stdout=stdout, stderr=stderr)
        save("terraform-process.json", {"at_utc": now(), "pid": child.pid, "parent_pid": os.getpid(), "plan_sha256": PLAN_SHA})
        code = child.wait()
    text = (OUT / "apply.stdout.private.log").read_text(encoding="utf-8", errors="replace")
    counts = re.findall(r"Apply complete! Resources: (\d+) added, (\d+) changed, (\d+) destroyed\.", text)
    result = {"started_at_utc": started, "finished_at_utc": now(), "exit_code": code,
              "apply_attempts": 1, "plan_sha256": PLAN_SHA, "source_sha256": SOURCE_SHA, "image": IMAGE,
              "summary": [int(x) for x in counts[0]] if len(counts) == 1 else None,
              "stdout_sha256": sha(OUT / "apply.stdout.private.log"), "stderr_sha256": sha(OUT / "apply.stderr.private.log"),
              "independent_verification_required": True, "retry_authorized": False}
    save("apply-result.json", result)
    print(json.dumps(result), flush=True)
    # Even nonzero/ambiguous results leave reconciliation to separate read-only process.
    require(code == 0 and result["summary"] == [0, 1, 0], "apply_result_requires_read_only_reconciliation_NO_RETRY")


if __name__ == "__main__":
    try:
        require(sys.argv[1:] == ["apply-once"], "explicit_apply_once_argument_required")
        apply_once()
    except Exception as exc:
        failure = {"at_utc": now(), "error_type": type(exc).__name__,
                   "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed",
                   "http_status": getattr(exc, "code", None), "retry_authorized": False,
                   "apply_intent_exists": (HOME / "live-apply-intent.json").exists()}
        if OUT.exists():
            save("failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", failure)
        print(json.dumps(failure), flush=True)
        raise SystemExit(2)