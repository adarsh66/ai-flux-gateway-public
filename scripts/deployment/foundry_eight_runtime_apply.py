"""ONE exact saved-plan apply; additive receipts, strict readback, no replay.

No init/plan/build/DB/catalog/inference/Auto/permission/network write entrypoint.
The initialized isolated ROOT retains its existing remote main-state backend.
An interrupted observer must reconcile the original PID and logs, never rerun.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPSHandler, Request
import zipfile

from scripts.deployment import foundry_eight_runtime_plan as p

HOME = p.rt.HOME / "foundry-eight-runtime-apply-20261031"
VALIDATION = p.HOME / "validation-continuation-01"
OWN = Path(__file__).resolve().relative_to(p.rt.ROOT).as_posix()
APPROVED = "06c9738fdf4057a5cd6d74ddfe3750ab5ee89cb6c785d0bc8fd937e96a15b7f8"
FINAL_SHA = "63731e71ba6f0b420386dfd1b9701729b8441bfd9b518bd7898d64aecdaa0ba6"
COMPOSITION_SHA = "acba6973b9d3b89ae36c1db3e97144619422726185c48c1d51d54ee6e85cd5fc"
LINEAGE = "b05cbf70-2d31-0e6e-34b7-c97e8f617ed6"
require, sha, load, now = p.require, p.sha, p.load, p.now


def write(name, value):
    path = HOME / name
    require(path.resolve().is_relative_to(HOME.resolve()), "owned_output_only")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return sha(raw)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "local_review_module")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def normalized_state(value):
    """Only the documented unique top-level check_results order is normalized."""
    result = deepcopy(value)
    checks = result.get("check_results")
    if checks is not None:
        keys = [(v["object_kind"], v["config_addr"]) for v in checks]
        require(len(set(keys)) == len(keys), "unique_state_check_identities")
        result["check_results"] = sorted(checks, key=lambda v: (v["object_kind"], v["config_addr"]))
    return result


def checked_hashes(root, entries, reason):
    require(all(sha((root / f).read_bytes()) == h for f, h in entries.items()), reason)


def embedded_state_guard(embedded, original):
    # Actual saved archive has check_results:null; remote state has its retained
    # check-result list. This is NOT the remote-state ordering normalization.
    # Bind this finite archive representation, then compare EVERY other field.
    require(embedded.get("check_results") is None and isinstance(original.get("check_results"), list),
            "actual_archive_null_checks_remote_retained_checks")
    value = deepcopy(embedded)
    value["check_results"] = original["check_results"]
    require(value == original and embedded["serial"] == 114 and embedded["lineage"] == LINEAGE,
            "all_embedded_remote_noncheck_fields_exact")


def bindings():
    require(sha(p.PLAN.read_bytes()) == APPROVED, "exact_user_authorized_plan")
    require(sha((VALIDATION / "final-integrity.json").read_bytes()) == FINAL_SHA,
            "actual_final_validation_integrity")
    final = load(VALIDATION / "final-integrity.json")
    require(final["passed"] and final["plan_sha256"] == APPROVED and final["official_steps"] == 9,
            "actual_completed_validation")
    checked_hashes(VALIDATION, final["evidence_sha256"], "immutable_validation_evidence")
    checked_hashes(p.HOME, load(VALIDATION / "original-files.json"), "all_original_package_bytes")
    expected = load(p.HOME / "historical-inputs.json")
    checked_hashes(p.rt.ROOT, expected, "all_1111_historical_bytes")
    actual = p.history()
    require(actual.pop(OWN, None) == sha(Path(__file__).read_bytes()) and actual == expected and len(expected) == 1111,
            "only_new_apply_controller_added_to_historical_glob")
    context = load(p.HOME / "plan-context.json")
    checked_hashes(p.rt.ROOT, context, "all_48_context_bytes")
    require(len(context) == 48 and sha((p.HOME / "source-composition.json").read_bytes()) == COMPOSITION_SHA,
            "accepted_source_composition")
    require(sha(p.WORKFLOW.read_bytes()) == p.WORKFLOW_SHA and
            load(VALIDATION / ".azure/validate-status.json")["completedStep"] == "UpdateStatus" and
            "Status: Validated" in (VALIDATION / ".azure/deployment-plan.md").read_text(), "official_Bash_completed")
    steps = load(VALIDATION / "final-report.json")["official_steps"]
    require(steps == ["None", "LoadPlan", "AddValidationSteps", "RunValidation", "BuildVerification",
                      "StaticRoleVerification", "RecordProof", "ResolveErrors", "UpdateStatus"], "nine_actual_steps")
    require(all(load(VALIDATION / ("commands/official-" + n + "-result.json"))["exit_code"] == 0 for n in steps),
            "all_official_exits_zero")
    guard = module("runtime_apply_saved_guard", VALIDATION / "guard.py")
    data = load(p.HOME / "plan.json")
    require(sha((p.HOME / "plan.json").read_bytes()) == guard.JSON_SHA and
            (p.HOME / "plan.json").read_bytes() == (p.HOME / "commands/show-plan.stdout.txt").read_bytes(),
            "exact_original_native_show_bytes")
    report = guard.review(data, load(VALIDATION / "input-proof.json"),
                          guard.predicates(p.ROOT), load(p.GATEWAY / "postapply-snapshot.json")["baseline"])
    retained = load(VALIDATION / "guard-review.json")
    require(all(retained[k] == v for k, v in report.items()) and
            load(VALIDATION / "independent-review.json")["passed"], "actual_all49_rationale_and_independent_leaf_review")
    with zipfile.ZipFile(p.PLAN) as archive:
        config = {"tfconfig/m-/" + f.name: f.read_bytes() for f in p.ROOT.iterdir()
                  if f.is_file() and f.name.endswith((".tf", ".tf.json"))}
        require({n for n in archive.namelist() if n.startswith("tfconfig/m-/")} == set(config) and
                all(archive.read(k) == v for k, v in config.items()) and
                archive.read(".terraform.lock.hcl") == (p.ROOT / ".terraform.lock.hcl").read_bytes(),
                "embedded_config_and_lock_exact")
        embedded = json.loads(archive.read("tfstate"))
    original = load(p.HOME / "commands/state-before.stdout.txt")
    embedded_state_guard(embedded, original)
    backend = load(p.ROOT / ".terraform/terraform.tfstate")["backend"]
    cfg = backend["config"]
    require(backend["type"] == "azurerm" and cfg["storage_account_name"] == "projpoctokenex" and
            cfg["container_name"] == "tfstate" and cfg["key"] == "poc-ids-token-ex/main.tfstate" and
            cfg["subscription_id"] == p.rt.SUB and cfg["tenant_id"] == p.rt.TENANT and
            cfg["resource_group_name"] == "IDS-TOKEN-EXCHANGE-POC" and cfg["use_azuread_auth"] is True and
            cfg["use_cli"] is True and not any(cfg.get(k) for k in ("access_key", "sas_token", "client_secret")),
            "existing_ROOT_remote_backend_only")
    require(not (p.ROOT / "terraform.tfstate").exists() and
            not any(k.startswith("TF_CLI_ARGS") for k in p.rt.ENV) and
            not any(k.startswith("TF_CLI_ARGS") for k in os.environ), "no_local_state_or_hidden_arguments")
    require(Path(p.rt.CA).is_file() and Path(p.rt.TF).is_file(), "existing_strict_CA_and_terraform")
    p.build_binding(remote=False)
    return {"at": now(), "plan_sha256": APPROVED, "plan_json_sha256": guard.JSON_SHA,
            "controller_sha256": sha(Path(__file__).read_bytes()), "historical_inputs": len(expected),
            "context_files": len(context), "validation_integrity_sha256": FINAL_SHA,
            "source_composition_sha256": COMPOSITION_SHA, "changes": report["changes"],
            "saved_check_counts": report["saved_check_counts"], "check_rationale": "16_saved_pass_28_variables_44_predicates_5_zero_instance_NOT_pass",
            "embedded_state_representation": "archive_check_results_null_all_other_fields_exact_original_remote_checks_never_removed",
            "backend_metadata_sha256": sha((p.ROOT / ".terraform/terraform.tfstate").read_bytes()),
            "ca_sha256": sha(Path(p.rt.CA).read_bytes()), "terraform_sha256": sha(Path(p.rt.TF).read_bytes())}


def access_token(resource):
    child = subprocess.run(p.rt.CLI + ["account", "get-access-token", "--subscription", p.rt.SUB,
        "--resource", resource, "--only-show-errors", "-o", "json"], env=p.rt.ENV,
        capture_output=True, encoding="utf-8", timeout=90)
    require(child.returncode == 0, "scoped_read_token_failed")
    token = json.loads(child.stdout)["accessToken"]
    part = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    require(claims["tid"] == p.rt.TENANT and claims["oid"] == p.rt.OPERATOR and
            claims["exp"] > datetime.now(UTC).timestamp() + 60, "exact_token_identity_and_lifetime")
    return token, claims["exp"]


def strict_opener():
    tls = ssl.create_default_context(cafile=p.rt.CA)
    require(tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED, "strict_CA_verification")
    return build_opener(HTTPSHandler(context=tls), p.gateway.NoRedirect())


class ReadOnly(p.ReadOnly):
    request = p.gateway.rebound(p.gateway.AttemptReader.request, exclusive=write)
    cli = p.gateway.rebound(p.gateway.AttemptReader.cli, exclusive=write)

    def __init__(self, label):
        token, expiry = access_token("https://management.azure.com/")
        remaining = expiry - datetime.now(UTC).timestamp() - 45
        self.token, self.count, self.label, self.cache = token, 0, label, {}
        self.deadline = time.monotonic() + min(1800, remaining)
        self.opener = strict_opener()
        write(label + "-transport.json", {"at": now(), "snapshot_bound_seconds": min(1800, remaining),
              "per_endpoint_max_seconds": 240, "expiry_margin_seconds": 45, "strict_CA": True,
              "write_methods": [], "settings_list_POST_is_read_only": True})


def capture(label):
    write(label + "-intent.json", {"at": now(), "pid": os.getpid(), "methods": ["GET", "exact_four_settings_list_POST_reads"]})
    operation = p.gateway.rebound(p.gateway_apply.capture, ReadOnly=ReadOnly, write=write)
    snapshot, active, backends = operation(label)
    proof = load(p.GATEWAY / "verified.json")
    require(sha(active.encode()) == proof["current_policy_sha256"] and proof["actual_advertised_count"] == 21 and
            set(p.gateway.advertised(p.gateway.xml_node(active, exported=True))) == set(proof["actual_advertised_aliases"]),
            "exact_postgateway_twentyone_policy")
    require(sha(p.gateway.OWNER.read_bytes()) == proof["state"]["sha256"], "separate_gateway_state_unchanged")
    require({r["name"]: sha(r) for r in backends["value"]} == load(p.GATEWAY / "postapply-backend-hashes.json"),
            "all_APIM_backends_unchanged")
    return snapshot


def state_pull(label):
    argv = [p.rt.TF, "-chdir=" + str(p.ROOT), "state", "pull"]
    write(label + "-intent.json", {"at": now(), "argv": argv, "read_only": True})
    child = subprocess.run(argv, env=p.rt.ENV, capture_output=True, timeout=180)
    write(label + ".stdout.txt", child.stdout)
    write(label + ".stderr.txt", child.stderr)
    write(label + "-result.json", {"at": now(), "exit_code": child.returncode,
          "stdout_sha256": sha(child.stdout), "stderr_sha256": sha(child.stderr)})
    require(child.returncode == 0, "remote_state_read_failed")
    return json.loads(child.stdout), child.stdout


def backend_head(label):
    token, _ = access_token("https://storage.azure.com/")
    url = "https://projpoctokenex.blob.core.windows.net/tfstate/poc-ids-token-ex/main.tfstate"
    write(label + "-intent.json", {"at": now(), "method": "HEAD", "url": url})
    req = Request(url, method="HEAD", headers={"Authorization": "Bearer " + token,
        "x-ms-version": "2023-11-03", "x-ms-date": datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")})
    with strict_opener().open(req, timeout=90) as response:
        result = {"at": now(), "status": response.status, "etag": response.headers.get("ETag"),
            "lease_state": response.headers.get("x-ms-lease-state"), "lease_status": response.headers.get("x-ms-lease-status"),
            "length": response.headers.get("Content-Length"), "request_id": response.headers.get("x-ms-request-id")}
    write(label + "-result.json", result)
    require(result["status"] == 200 and result["lease_state"] == "available" and result["lease_status"] == "unlocked",
            "existing_backend_unlocked_no_force_unlock")
    return result


def protected_comparison(before, after):
    value = deepcopy(after)
    pins = {}
    for kind in p.KINDS:
        site = value["baseline"]["runtime"]["sites"][kind]
        expected = "DOCKER|" + p.builds.HOST + "/aiflux-" + kind + "@sha256:" + p.DIGESTS[kind]
        require(site["image"] == expected, "actual_new_pin:" + kind)
        pins[kind] = site["image"]
        site["image"] = before["baseline"]["runtime"]["sites"][kind]["image"]
    require(value == before, "STOP_any_nonimage_protected_drift")
    return {"at": now(), "passed": True, "current_pins": pins, "all_four_settings_equal": True,
            "all_other_protected_fields_equal": True, "normalized_after_sha256": sha(value), "before_sha256": sha(before),
            "includes": ["all_settings", "roles", "networks_five_storage_IPs", "identities", "ingestion_timer_cutoff",
                         "APIM_global_API_product_operation_policies", "backends", "subscriptions_counter_policy", "Foundry_deployments"],
            "counter_limit_configuration_unchanged": True, "live_volatile_counter_values_not_reset_or_claimed_read": True}


def state_pin_check(state):
    require(state["lineage"] == LINEAGE and state["serial"] > 114, "postapply_main_owner_and_serial")
    observed = {}
    for row in state["resources"]:
        if row["mode"] != "managed":
            continue
        for instance in row["instances"]:
            kind = (instance.get("index_key") if row["type"] == "azurerm_linux_web_app" and row["name"] == "main"
                    else "ingestion" if row["type"] == "azurerm_linux_function_app" and row["name"] == "ingestion" else None)
            if kind not in p.KINDS:
                continue
            attrs = instance["attributes"]
            require(attrs["id"] == p.rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind,
                    "postapply_state_site_owner")
            stack = attrs["site_config"][0]["application_stack"][0]
            pin = stack["docker"][0]["image_tag"] if kind == "ingestion" else stack["docker_image_name"].split("@sha256:")[1]
            require(kind not in observed and pin == p.DIGESTS[kind], "postapply_state_exact_pin")
            observed[kind] = pin
    require(set(observed) == set(p.KINDS), "all_four_remote_state_pins")
    return {"at": now(), "passed": True, "serial": state["serial"], "lineage": state["lineage"], "pins": observed}


def readiness():
    # These retained handlers do not seed DB/catalog or invoke a model. /ready
    # performs SELECTs only; its bootstrap_fragment reads a packaged local file.
    endpoints = [("api_health", "api", "/health", {"status": "alive"}),
                 ("api_automatic_readiness", "api", "/ready", {"status": "ready"}),
                 ("admin_health", "admin", "/healthz", None),
                 ("customer_health", "customer", "/healthz", None)]
    result = []
    for name, kind, path, expected in endpoints:
        url = "https://poc-ids-token-ex-" + kind + ".azurewebsites.net" + path
        write("health/" + name + "-intent.json", {"at": now(), "url": url, "method": "GET", "max_requests": 1,
              "no_auth_bypass_no_startup_seed_no_inference": True})
        row = {"at": now(), "url": url, "requests": 1, "ready": False, "response_body_persisted": False}
        try:
            with strict_opener().open(Request(url, method="GET"), timeout=90) as response:
                raw = response.read(1024 * 1024 + 1)
                require(len(raw) <= 1024 * 1024, "bounded_health_body")
                row.update(status=response.status, body_sha256=sha(raw))
                row["ready"] = response.status == 200 and (json.loads(raw) == expected if expected else raw.strip() == b"ok")
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
            row.update(status=exc.code if isinstance(exc, HTTPError) else None, error_type=type(exc).__name__)
            if isinstance(exc, HTTPError):
                exc.close()
        row["disposition"] = "ready" if row["ready"] else "pending_coldstart_or_access_no_retry_no_reapply"
        write("health/" + name + "-result.json", row)
        result.append(row)
    report = {"at": now(), "observations": result, "all_ready": all(r["ready"] for r in result),
              "inference_requests": 0, "DB_sync": 0, "catalog_sync": 0, "health_retries": 0}
    write("readiness.json", report)
    return report


def apply_once():
    # This first exclusive file is permanent even on preflight failure.
    write("execution-intent.json", {"at": now(), "pid": os.getpid(), "parent_pid": os.getppid(),
          "authorization": "user_exact_saved_four_runtime_images_apply_once_protected_readback_no_inference_DBsync_build_replan",
          "plan_sha256": APPROVED, "controller_sha256": sha(Path(__file__).read_bytes()), "replay": False,
          "max_apply_commands": 1, "inference_budget": 0})
    write("workers-before.json", p.gateway.worker_gate())
    initial = bindings()
    write("bindings-before.json", initial)
    before_started = time.monotonic()
    before = capture("preapply")
    require(before == load(p.GATEWAY / "postapply-snapshot.json") == load(p.HOME / "sole-plan-preplan-snapshot.json"),
            "fresh_entire_protected_baseline_no_drift")
    for kind in p.KINDS:
        require(before["baseline"]["runtime"]["sites"][kind]["image"] ==
                "DOCKER|" + p.builds.HOST + "/aiflux-" + kind + "@sha256:" + p.builds.PINS[kind], "fresh_four_old_pins")
    head = backend_head("backend-before")
    current, raw = state_pull("state-before")
    original_raw = (p.HOME / "commands/state-before.stdout.txt").read_bytes()
    require(normalized_state(current) == normalized_state(json.loads(original_raw)) and current["serial"] == 114 and
            current["lineage"] == LINEAGE, "fresh_remote_state_identity_and_stale_plan_guard")
    state_checked = time.monotonic()
    write("fresh-guard.json", {"at": now(), "passed": True, "state_serial": 114, "state_lineage": LINEAGE,
          "state_raw_bytes_equal": raw == original_raw, "state_raw_sha256": sha(raw), "state_semantically_exact": True,
          "normalization": "sort_only_unique_top_level_check_results_object_kind_config_addr",
          "full_protected_snapshot_equal": True, "four_old_pins": True, "backend": head})
    final = bindings()
    require({k: v for k, v in final.items() if k != "at"} == {k: v for k, v in initial.items() if k != "at"},
            "all_bindings_unchanged_immediately_before_command")
    write("workers-immediate.json", p.gateway.worker_gate())
    require(time.monotonic() - before_started < 1800 and time.monotonic() - state_checked < 90,
            "bounded_fresh_protected_and_state_guard")
    argv = [p.rt.TF, "-chdir=" + str(p.ROOT), "apply", "-input=false", "-no-color",
            "-lock-timeout=60s", "-parallelism=1", str(p.PLAN)]
    # No -var-file, target, -state, lock=false, auto-approve, replan or retry.
    write("apply-intent.json", {"at": now(), "pid": os.getpid(), "argv": argv, "max_invocations": 1,
          "bindings": final, "all_historical_hashes": load(p.HOME / "historical-inputs.json"),
          "all_context_hashes": load(p.HOME / "plan-context.json"), "validation_hashes": load(VALIDATION / "final-integrity.json"),
          "additive_evidence_before_apply": {f.relative_to(HOME).as_posix(): sha(f.read_bytes())
              for f in HOME.rglob("*") if f.is_file() and "__pycache__" not in f.parts},
          "fresh_guard_sha256": sha((HOME / "fresh-guard.json").read_bytes()), "replay": False})
    # Files are opened before Popen. Native output is durable while the original
    # worker runs, even if a terminal observer returns an empty response.
    with (HOME / "apply.stdout.txt").open("xb", buffering=0) as stdout, (HOME / "apply.stderr.txt").open("xb", buffering=0) as stderr:
        child = subprocess.Popen(argv, cwd=p.rt.ROOT, env=p.rt.ENV, stdout=stdout, stderr=stderr)
        write("apply-worker.json", {"at": now(), "pid": child.pid, "parent_pid": os.getpid(), "argv": argv,
              "reconcile_original_worker_only": True, "replay": False})
        print(json.dumps({"at": now(), "apply_pid": child.pid, "parent_pid": os.getpid(), "replay": False}), flush=True)
        try:
            code = child.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            write("apply-pending.json", {"at": now(), "original_pid": child.pid, "exit_code": None,
                  "worker_not_terminated": True, "reconcile_original_only": True, "replay": False})
            return 3
    write("apply-result.json", {"at": now(), "pid": child.pid, "exit_code": code, "plan_sha256": APPROVED,
          "stdout_sha256": sha((HOME / "apply.stdout.txt").read_bytes()),
          "stderr_sha256": sha((HOME / "apply.stderr.txt").read_bytes()), "apply_commands": 1, "replay": False})
    # Reconciliation reads never cause reapply, including an apply nonzero exit.
    after = capture("postapply")
    comparison = protected_comparison(before, after)
    write("protected-comparison.json", comparison)
    state, _ = state_pull("state-after")
    write("state-after-proof.json", state_pin_check(state))
    after_head = backend_head("backend-after")
    require(after_head["etag"] != head["etag"], "actual_remote_state_write_observed")
    health = readiness()
    write("bindings-after.json", bindings())
    write("workers-after.json", p.gateway.worker_gate())
    report = {"at": now(), "status": "APPLIED_PROTECTED_VERIFIED" if code == 0 else "APPLY_NONZERO_READBACK_RECONCILED_NO_RETRY",
          "apply_exit_code": code, "apply_commands": 1, "plan_sha256": APPROVED,
          "current_pins": comparison["current_pins"], "protected_comparison_passed": True,
          "state_serial": state["serial"], "state_lineage": state["lineage"], "backend_unlocked": True,
          "all_historical_hashes_unchanged": True, "readiness": "ready" if health["all_ready"] else "pending",
          "inference_requests": 0, "DB_sync": 0, "catalog_sync": 0, "builds": 0, "replans": 0,
          "Auto": "HOLD_unchanged", "no_permission_network_or_TLS_changes": True, "replay": False}
    write("handoff.json", report)
    write("handoff.md", ("# Exact saved four-image runtime apply\n\n" +
        "Actual machine UTC: " + report["at"] + ". Session label remains 2026-10-31.\n\n" +
        "Apply exit: " + str(code) + "; commands: 1; protected comparison: PASS; readiness: " + report["readiness"] + ".\n\n" +
        "State serial: " + str(state["serial"]) + "; lineage: " + state["lineage"] + ". Backend unlocked.\n\n" +
        "\n".join("- " + k + ": " + v for k, v in comparison["current_pins"].items()) +
        "\n\nAll historical bytes, all settings/roles/network/identities/ingestion timer/cutoff and APIM policy/backends/counter configuration unchanged.\n" +
        "Health observations are single bounded GETs, not inference or authenticated functional acceptance. Pending is not permission to reapply.\n" +
        "No DB/catalog sync, build, replan, Auto, permission/network write or TLS bypass. No volatile counter-value claim.\n").encode())
    write("evidence-integrity.json", {"at": now(), "files": {f.relative_to(HOME).as_posix(): sha(f.read_bytes())
          for f in HOME.rglob("*") if f.is_file() and "__pycache__" not in f.parts}})
    print(json.dumps(report), flush=True)
    return 0 if code == 0 else 2


def main():
    require(sys.argv[1:] in (["audit"], ["apply-once"]), "finite_exact_actions_only")
    if sys.argv[1] == "audit":
        print(json.dumps(bindings()), flush=True)
        return 0
    try:
        proof = load(HOME / "offline-tests-corrected.json")
        require(proof["passed"] and proof["controller_sha256"] == sha(Path(__file__).read_bytes()) and
                proof["tests_sha256"] == sha((HOME / "test_apply_guards.py").read_bytes()), "actual_final_offline_tests_required")
        return apply_once()
    except Exception as exc:
        # Never overwrite existing receipts or expose tokens/settings/error bodies.
        reason = str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Za-z0-9_:.-]+", str(exc)) else "private_diagnostic_not_printed"
        if not (HOME / "failure.json").exists():
            write("failure.json", {"at": now(), "pid": os.getpid(), "error_type": type(exc).__name__, "reason": reason,
                  "apply_intent_exists": (HOME / "apply-intent.json").exists(),
                  "apply_result_exists": (HOME / "apply-result.json").exists(), "replay": False})
        print(json.dumps({"error_type": type(exc).__name__, "reason": reason, "replay": False}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())