"""New authorized corrected-image session; never overwrite/replay historical proof."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import secrets
import shutil
import subprocess

from scripts.deployment import finops_runner_build as build
from scripts.deployment import finops_runner_execute as ex
from scripts.deployment import finops_runner_fresh as fresh
from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_preflight as p
from scripts.deployment import finops_runner_prepare as prep

PREVIOUS = ("2f75015b55d1", "9461fb0c1a35", "3788be5dd201", "a9aa663c1748")
HISTORICAL_IMAGE = build.OUT
HISTORICAL_PREPARATION = prep.OUT


def bind(nonce):
    g.require(__import__("re").fullmatch("[0-9a-f]{12}", nonce) and nonce not in (*PREVIOUS, "05a9ff859f48", "23667d8c9b50"), "new_nonce_required")
    build.OUT = p.ROOT / ("gateway/validation/finops-corrected-image-" + nonce + ".json")
    prep.OUT = p.ROOT / ("gateway/validation/finops-corrected-package-" + nonce + ".json")
    return p.ROOT / ("gateway/validation/finops-corrected-session-" + nonce + ".json")


def prepare_build():
    nonce = secrets.token_hex(6)
    output = bind(nonce)
    report = {"owner_nonce": nonce, "started_at_utc": p.now(), "approval": "20261027_corrected_probe_only_build_then_two_once_sequential_MI",
        "database_writes": 0, "app_release": False, "probe_retries": 0, "activation_cutoff": None}
    try:
        report["live_prerequisites"] = fresh.prerequisites()
        report["previous_exact_absence"] = {n: fresh.exact_absence(g.owned_ids(n)) for n in PREVIOUS}
        report["preservation_before_build"] = prep.preservation_readback()
        historical = ex.load(HISTORICAL_IMAGE)
        prior = ex.load(HISTORICAL_PREPARATION)
        context = p.ROOT / ".deployment/finops-runner" / nonce / "image-context"
        g.require(not context.exists(), "image_context_collision")
        context.mkdir(parents=True)
        retained = p.ROOT / ".deployment/finops-runner" / historical["owner_nonce"] / "image-context"
        for name, expected in historical["context_files_sha256"].items():
            g.require(prep.digest(retained / name) == expected, "retained_dependency_evidence_changed")
            if name == "requirements.lock.txt" or name.startswith("wheels/"):
                target = context / name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(retained / name, target)
        sources = {"Dockerfile": prep.FOLDER / "Dockerfile", "requirements.txt": prep.FOLDER / "requirements.txt",
            "entrypoint.py": prep.FOLDER / "entrypoint.py", "linux_contract.py": prep.FOLDER / "linux_contract.py",
            "finops_private_probe.py": p.ROOT / "scripts/deployment/finops_private_probe.py"}
        g.require(prep.digest(sources["requirements.txt"]) == historical["context_files_sha256"]["requirements.txt"], "dependency_upgrade_forbidden")
        g.require(sources["Dockerfile"].read_text().splitlines()[0] == (retained / "Dockerfile").read_text().splitlines()[0], "base_upgrade_forbidden")
        for name, path in sources.items(): shutil.copyfile(path, context / name)
        # Fresh scan before any paid build. Staging is not historical evidence.
        ex.write(prep.FOLDER / "network.arm.json", prep.network_template(nonce))
        prep.unbound_group_templates(nonce)
        scan = prep.security_scan()
        g.require(scan["security_gate_passed"], "fresh_security_scan_failed")
        package = {"owner_nonce": nonce, "updated_at_utc": p.now(), "security_scan": scan,
            "pricing": prior["pricing"], "image_dependency_lock": prior["image_dependency_lock"],
            "image_package": {"context": str(context.relative_to(p.ROOT)).replace("\\", "/"),
                "files_sha256": {name: prep.digest(path) for name, path in sources.items()}}}
        ex.write(prep.OUT, package)
        report.update(security_scan=scan, pricing=prior["pricing"], package_sha256=prep.digest(prep.OUT),
            source_probe_sha256=prep.digest(sources["finops_private_probe.py"]),
            source_entrypoint_sha256=prep.digest(sources["entrypoint.py"]),
            linux_contract_sha256=prep.digest(sources["linux_contract.py"]))
        # Installed CLI emits no JSON for --no-wait. Reconcile one submission
        # against a pre-submission run-ID baseline; NEVER automatically resubmit.
        runs = build.az(["acr", "task", "list-runs", "--registry", "pocidstokenexacr", "--top", "100"])
        baseline = {r["runId"] for r in runs}
        report.update(build_submission_intent_at_utc=p.now(), prior_run_ids=sorted(baseline))
        ex.write(output, report)
        intent = {"started_at_utc": p.now(), "cloud_build_runs": 1, "submission_intent_at_utc": p.now()}
        ex.write(build.OUT, intent)
        child = subprocess.run([p.AZ, "acr", "build", "--registry", "pocidstokenexacr", "--image", "aiflux-finops-probe:probe-" + nonce,
            "--file", str(context / "Dockerfile"), "--platform", "linux/amd64", "--timeout", "900", "--no-wait", "--no-logs",
            str(context), "--subscription", g.SUB, "--only-show-errors", "-o", "json"],
            capture_output=True, env=p.ENV, timeout=150)
        report["submission_cli_exit_code"] = child.returncode
        new = [r for r in build.az(["acr", "task", "list-runs", "--registry", "pocidstokenexacr", "--top", "100"]) if r["runId"] not in baseline]
        g.require(len(new) == 1, "single_build_submission_unverified_no_resubmit")
        intent.update(run_id=new[0]["runId"], submission_reconciliation="exactly_one_new_run_after_recorded_baseline_no_resubmission")
        ex.write(build.OUT, intent)
        report["run_id"] = intent["run_id"]
        ex.write(output, report)
        code = build.main()
        g.require(code == 0, "corrected_linux_build_blocked")
        image = ex.load(build.OUT)
        run = build.az(["acr", "task", "show-run", "--registry", "pocidstokenexacr", "--run-id", image["run_id"]])
        g.require(run.get("timeout") in (None, 900), "build_timeout_changed")
        report.update(build=image, linux_native_contract_passed_in_bound_dockerfile=True,
            main_review="accepted_corrected_source_exact_lock_native_contract_scanner_and_immutable_image",
            build_duration_seconds=(datetime.fromisoformat(image["build_finished_at_utc"].replace("Z", "+00:00")) -
                datetime.fromisoformat(image["build_started_at_utc"].replace("Z", "+00:00"))).total_seconds(), exit_code=0)
    except Exception as exc:
        report.update(exit_code=2, reason=str(exc) if isinstance(exc, g.GuardBlocked) else "sanitized_corrected_build_failure",
            exception_type=type(exc).__name__ if type(exc).__name__ in {"KeyError", "ValueError", "TimeoutExpired", "FileNotFoundError"} else "unknown")
    report["updated_at_utc"] = p.now()
    ex.write(output, report)
    print(json.dumps({k: report.get(k) for k in ("owner_nonce", "run_id", "exit_code", "reason", "exception_type", "build_duration_seconds")}), flush=True)
    return report["exit_code"]


def execute(nonce):
    output = bind(nonce)
    report = ex.load(output)
    g.require(report.get("exit_code") == 0 and report.get("main_review") and not report.get("execution_intent"), "accepted_unexecuted_corrected_image_required")
    report["execution_intent"] = p.now()
    ex.write(output, report)
    # Both previous watchdog sessions remain untouched and exact-ID disjoint.
    report["previous_absence_before_network"] = {n: fresh.exact_absence(g.owned_ids(n)) for n in PREVIOUS}
    g.require(ex.deadline_test() == 0, "fresh_detached_cleanup_test_failed")
    runtime = secrets.token_hex(6)
    g.require(all(not set(g.owned_ids(runtime).values()) & set(g.owned_ids(n).values()) for n in (*PREVIOUS, nonce)), "watchdog_id_overlap")
    fresh.secrets.token_hex = lambda size: runtime
    report["runtime_nonce"] = runtime
    ex.write(output, report)
    code = fresh.prepare()
    if code == 0:
        path = p.ROOT / ("gateway/validation/finops-fresh-preparation-" + runtime + ".json")
        report["execution_exit_code"] = fresh.execute(path, prep.digest(path))
        report["independent_verification_exit_code"] = fresh.verify_completed(runtime)
        report["previous_absence_after_cleanup"] = {n: fresh.exact_absence(g.owned_ids(n)) for n in PREVIOUS}
    else:
        report["execution_exit_code"] = 2
        report["reason"] = "corrected_network_preparation_blocked"
    report["finished_at_utc"] = p.now()
    ex.write(output, report)
    print(json.dumps({k: report.get(k) for k in ("owner_nonce", "runtime_nonce", "execution_exit_code", "independent_verification_exit_code", "reason")}), flush=True)
    return report["execution_exit_code"]


def outcome(nonce):
    """Independent GET-only final report, including actual observed lifetimes."""
    session_path = bind(nonce)
    session = ex.load(session_path)
    runtime = session["runtime_nonce"]
    execution_path = p.ROOT / ("gateway/validation/finops-fresh-execution-" + runtime + ".json")
    final_path = p.ROOT / ("gateway/validation/finops-fresh-final-" + runtime + ".json")
    execution, final = ex.load(execution_path), ex.load(final_path)
    output = p.ROOT / ("gateway/validation/finops-corrected-outcome-" + nonce + ".json")
    g.require(not output.exists(), "outcome_evidence_already_exists")
    g.require(execution["cleanup"]["exit_code"] == 0 and final["exit_code"] == 0, "cleanup_proof_required")
    report = {"at_utc": p.now(), "image_nonce": nonce, "runtime_nonce": runtime,
        "build": session["build"], "execution_evidence_sha256": prep.digest(execution_path),
        "final_evidence_sha256": prep.digest(final_path), "probes": execution["probes"],
        "independent_absence": fresh.exact_absence(g.owned_ids(runtime)),
        "previous_independent_absence": {n: fresh.exact_absence(g.owned_ids(n)) for n in PREVIOUS},
        "preservation": prep.preservation_readback(), "created_resource_ids": execution["created_resource_ids"],
        "outstanding_resource_ids": [], "historical_failure_cause": "unknown",
        "database_writes": 0, "probe_retries": 0, "app_release": False, "timer_enabled": False,
        "replay_executed": False, "activation_cutoff": None,
        "database_readiness_accepted": final["database_readiness_accepted"],
        "application_source_matches_prior_manifest": final["application_source_matches_prior_manifest"],
        "table_grants_and_usage_aggregates": "unknown" if not final["database_readiness_accepted"] else "see_accepted_probe_JSON",
        "raw_messages_exported": False, "new_roles": 0}
    events = execution["arm_events"]
    def timestamp(value): return datetime.fromisoformat(value.replace("Z", "+00:00"))
    lifetimes = {}
    for key, rid in execution["ids"].items():
        puts = [e for e in events if e["resource_id"] == rid and e["method"] == "PUT" and 200 <= e["http_status"] < 300]
        if not puts: continue
        put = puts[0]["at_utc"]
        deletes = [e for e in events if e["resource_id"] == rid and e["method"] == "DELETE" and 200 <= e["http_status"] < 300]
        g.require(bool(deletes), "observed_owned_delete_required")
        deleted = deletes[-1]["at_utc"]
        absent = next(e["at_utc"] for e in events if e["resource_id"] == rid and e["method"] == "GET" and
            e["http_status"] == 404 and timestamp(e["at_utc"]) >= timestamp(deleted))
        lifetimes[key] = {"resource_id": rid, "put_response_at_utc": put, "delete_response_at_utc": deleted,
            "get404_at_utc": absent, "observed_lifetime_seconds": (timestamp(absent) - timestamp(put)).total_seconds()}
    report["actual_observed_resource_lifetimes"] = lifetimes
    seconds = lambda key: lifetimes[key]["observed_lifetime_seconds"]
    build_seconds = session["build_duration_seconds"]
    components = {"acr_build_2vcpu_observed_seconds": build_seconds * 2 * 0.0001,
        "nat_observed_seconds": seconds("nat") / 3600 * 0.045,
        "pip_observed_seconds": seconds("pip") / 3600 * 0.005,
        "aci_both_creation_to_absence_envelopes": sum(seconds(k) for k in g.IDENTITIES) / 3600 * (0.0506 + 1.5 * 0.00553)}
    report["cost"] = {"currency": "USD", "actual_billed_total": None,
        "observed_duration_priced_components_not_invoice": components,
        "observed_duration_priced_subtotal_usd": round(sum(components.values()), 8),
        "reviewed_scenario_estimate_usd": 0.778895, "contingency_usd": 1,
        "planning_envelope_usd": 1.778895, "hard_billing_cap": False,
        "price_evidence": str(HISTORICAL_PREPARATION.relative_to(p.ROOT)).replace("\\", "/"),
        "exclusions_and_limits": ["not invoice or actual metered CPU billing; ACI provisioning included conservatively",
            "NAT/PIP minimum billing increments, registry storage retention, transfer/NAT bytes, private-link and tax not measured",
            "retained image storage continues; incremental cloud work and cost are not zero"]}
    report["watchdogs"] = final["watchdogs"]
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    report["previous_watchdogs"] = []
    for old in PREVIOUS:
        folder = p.ROOT / ".deployment/finops-runner" / old / "execution"
        ready = ex.load(folder / "watchdog-ready.json")
        pid = ready["pid"]
        bound = ex.bound_session(folder / "session.json", ready["session_sha256"])
        handle = kernel.OpenProcess(0x1000, False, pid)
        code = ctypes.c_ulong()
        active = bool(handle and kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259)
        if handle: kernel.CloseHandle(handle)
        g.require(not set(bound["ids"].values()) & set(execution["ids"].values()), "old_watchdog_overlap")
        report["previous_watchdogs"].append({"pid": pid, "owner_nonce": old, "session_sha256": ready["session_sha256"],
            "active_observed": active, "stopped": False, "deadline_utc": bound["deadline_utc"],
            "original_ready_controller_sha256": ready.get("code_sha256"),
            "original_ready_guard_sha256": ready.get("guard_sha256"),
            "ids_disjoint": True})
    current_session = ex.load(p.ROOT / ".deployment/finops-runner" / runtime / "execution/session.json")
    report["controller_unchanged_during_current_attempt"] = prep.digest(Path(ex.__file__)) == current_session["controller_sha256"]
    report["guard_unchanged_during_current_attempt"] = prep.digest(Path(g.__file__)) == current_session["guard_sha256"]
    report["old_watchdogs_stopped_by_controller"] = False
    report["remaining_plan"] = ["Do not repeat provisioning or infer historical runtime cause.",
        "If blocked, resolve exact session-proof invariant with a separately approved bounded diagnostic; no automatic role/grant/network expansion.",
        "Production Function configuration requires a precise proposed diff and separate consent before edits.",
        "Replay stays dry-run only. No timer, replay or application image release is authorized by probe acceptance.",
        "FinOps repair requires deployed source/API/UI acceptance, retained ownership mapping and approved activation cutoff."]
    ex.write(output, report)
    print(json.dumps({"outcome": str(output.relative_to(p.ROOT)).replace("\\", "/"),
        "outstanding_resource_ids": [], "cost": report["cost"], "probes": report["probes"]}), flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--build", action="store_true")
    modes.add_argument("--execute")
    modes.add_argument("--outcome")
    args = parser.parse_args()
    raise SystemExit(prepare_build() if args.build else outcome(args.outcome) if args.outcome else execute(args.execute))