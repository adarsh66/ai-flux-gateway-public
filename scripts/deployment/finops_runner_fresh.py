"""Fresh approved, isolated runner session; never replay the legacy execution.

Preparation is read-only in Azure. Execution delegates to exact-ID finally cleanup.
No image build, role changes, production settings, SQL writes or raw logs.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import secrets
import subprocess

from scripts.deployment import finops_runner_build as build
from scripts.deployment import finops_runner_execute as ex
from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_preflight as p
from scripts.deployment import finops_runner_prepare as prep

LEGACY = "2f75015b55d1"


def verify_image():
    image = ex.load(build.OUT)
    g.require(image.get("status") == "Succeeded" and image.get("exit_code") == 0 and
        image.get("linux_dependency_imports_and_pip_check_passed") is True, "linux_image_proof_required")
    files = image["context_files_sha256"]
    for name, path in {"entrypoint.py": prep.FOLDER / "entrypoint.py",
        "finops_private_probe.py": p.ROOT / "scripts/deployment/finops_private_probe.py",
        "Dockerfile": prep.FOLDER / "Dockerfile", "requirements.txt": prep.FOLDER / "requirements.txt"}.items():
        g.require(prep.digest(path) == files[name], "image_source_mismatch")
    context = p.ROOT / ".deployment/finops-runner" / image["owner_nonce"] / "image-context"
    actual = {str(f.relative_to(context)).replace("\\", "/"): prep.digest(f)
        for f in context.rglob("*") if f.is_file()}
    g.require(actual == files and hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest()
        == image["context_manifest_sha256"], "image_context_mismatch")
    run = build.az(["acr", "task", "show-run", "--registry", "pocidstokenexacr", "--run-id", image["run_id"]])
    digest = "sha256:" + image["manifest_content_sha256"]
    g.require(run.get("status") == "Succeeded" and run.get("outputImages") == [{"digest": digest,
        "registry": "pocidstokenexacr.azurecr.io", "repository": "aiflux-finops-probe",
        "tag": "probe-" + image["owner_nonce"]}], "live_build_image_binding_failed")
    child = subprocess.run([p.AZ, "acr", "manifest", "show", "--registry", "pocidstokenexacr",
        "--name", "aiflux-finops-probe@" + digest, "--raw", "--subscription", g.SUB, "--only-show-errors"],
        capture_output=True, env=p.ENV, timeout=90)
    g.require(child.returncode == 0, "immutable_manifest_read_failed")
    raw = child.stdout
    candidates = (raw, raw.rstrip(b"\r\n"), raw.replace(b"\r\n", b"\n"), raw.replace(b"\r\n", b"\n").rstrip(b"\n"))
    g.require(any(hashlib.sha256(x).hexdigest() == digest[7:] for x in candidates), "immutable_manifest_hash_failed")
    return {"at_utc": p.now(), "image": image["immutable_image"], "source_probe_sha256": image["source_probe_sha256"],
        "source_entrypoint_sha256": image["source_entrypoint_sha256"], "context_manifest_sha256": image["context_manifest_sha256"],
        "live_build_and_manifest_binding_verified": True, "linux_validation_from_bound_build": True,
        "new_builds": 0, "image_evidence_sha256": prep.digest(build.OUT)}


def exact_absence(ids):
    arm = ex.Arm({"ids": ids})
    for rid in ids.values():
        g.require(arm.get(rid) is None, "fresh_or_legacy_resource_not_absent")
    return arm.events


def prerequisites():
    account = p.cli(["account", "show"])
    g.require(account["id"] == g.SUB and account["tenantId"] == g.TENANT and
        account["environmentName"] == "AzureCloud" and account["user"]["name"] == "xv.puneet.devadiga@singtel.com", "account_scope_mismatch")
    usage = p.get(f"/subscriptions/{g.SUB}/providers/Microsoft.ContainerInstance/locations/southeastasia/usages", "2023-05-01")
    quota = {x["name"]["value"]: {"used": x["currentValue"], "limit": x["limit"]}
        for x in usage["value"] if x["name"]["value"] in {"ContainerGroups", "StandardCores"}}
    g.require(len(quota) == 2 and all(x["limit"] - x["used"] >= 1 for x in quota.values()), "fresh_aci_quota_required")
    provider = p.get(f"/subscriptions/{g.SUB}/providers/Microsoft.ContainerInstance", "2021-04-01")
    g.require(provider["registrationState"] == "Registered" and any("Southeast Asia" in x.get("locations", [])
        for x in provider["resourceTypes"] if x["resourceType"] == "containerGroups"), "fresh_aci_region_required")
    identities = {}
    expected = {"ingestion": ("e1d25c87-9df1-4225-9744-ce22121cf462", "edbfc3e2-a8e5-4652-9bb0-311233756d42"),
        "api": ("f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1", "4e7b70ed-9868-47ba-9b61-304f1e1fdd89")}
    registry = g.RG + "/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr"
    roles = p.get(registry + "/providers/Microsoft.Authorization/roleAssignments", "2022-04-01")["value"]
    for phase, rid in g.IDENTITIES.items():
        props = p.get(rid, "2023-01-31")["properties"]
        g.require((props["clientId"], props["principalId"]) == expected[phase] and props["tenantId"] == g.TENANT, "selected_identity_mismatch")
        g.require(any(x["properties"]["principalId"] == props["principalId"] and
            x["properties"]["roleDefinitionId"].endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d") and
            x["properties"]["scope"].lower() == registry.lower() for x in roles), "existing_acrpull_missing")
        identities[phase] = {"client_object_tenant_verified": True, "existing_registry_acrpull_verified": True}
    return {"at_utc": p.now(), "account_scope_verified": True, "aci_quota": quota,
        "aci_registered_and_region_listed": True, "identities": identities, "new_roles": 0}


def prepare():
    nonce = secrets.token_hex(6)
    g.require(nonce != LEGACY and not set(g.owned_ids(nonce).values()) & set(g.owned_ids(LEGACY).values()), "legacy_id_overlap")
    folder = p.ROOT / ".deployment/finops-runner" / nonce
    folder.mkdir(parents=True, exist_ok=False)
    output = p.ROOT / ("gateway/validation/finops-fresh-preparation-" + nonce + ".json")
    report = {"started_at_utc": p.now(), "owner_nonce": nonce, "subscription": g.SUB, "tenant": g.TENANT,
        "region": "southeastasia", "ids": g.owned_ids(nonce), "cloud_resource_creates": 0,
        "legacy_artifacts_unchanged": True, "approval": "user_scoped_temporary_runner_both_sequential_identities",
        "output": str(output.relative_to(p.ROOT)).replace("\\", "/")}
    try:
        report["live_prerequisites"] = prerequisites()
        report["legacy_all_six_get404"] = exact_absence(g.owned_ids(LEGACY))
        report["fresh_all_six_get404"] = exact_absence(g.owned_ids(nonce))
        report["preservation"] = prep.preservation_readback()
        report["image_reuse"] = verify_image()
        report["fresh_network_capacity"] = g.network_capacity(p.get(g.VNET, "2024-05-01"))
        baseline = p.cli(["resource", "list", "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--query", "[].id"])
        report["preview_baseline"] = {"at_utc": p.now(), "resource_ids": baseline}
        ex.write(folder / "ownership-journal.json", {"owner_nonce": nonce, "ids": g.owned_ids(nonce),
            "baseline_absent": {k: True for k in g.owned_ids(nonce)}, "write_intents": [],
            "legacy_ids_disjoint": True, "baseline_at_utc": p.now()})
        template = prep.network_template(nonce)
        prep.guard_network(template, nonce)
        path = prep.FOLDER / "network.arm.json"
        ex.write(path, template)
        prep.unbound_group_templates(nonce)
        # Snapshot the exact four-object input outside the shared staging location.
        pinned = folder / "network.arm.json"
        ex.write(pinned, template)
        report["network_template"] = {"path": str(pinned.relative_to(p.ROOT)).replace("\\", "/"),
            "sha256": prep.digest(pinned), "inbound": "10.240.0.0/16_to_10.240.5.0/24_tcp19390_priority100_then_deny_all_priority200"}
        report["security_scan"] = prep.security_scan()
        g.require(report["security_scan"]["security_gate_passed"], "fresh_security_scan_failed")
        report["arm_network_preview"] = prep.validation(pinned, nonce, baseline)
        preview = report["arm_network_preview"]
        g.require(preview["validate"]["exit_code"] == 0 and preview["validate"].get("validation_returned_without_error") and
            preview["what-if"].get("exact_create_only_guard_passed"), "fresh_exact_four_create_preview_failed")
        prior = ex.load(prep.OUT)["pricing"]
        g.require(prior["all_in_scenario_estimate_usd"] == 0.778895 and
            prior["planning_envelope_with_contingency_usd"] == 1.778895 and not prior["hard_billing_cap"], "reviewed_price_scenario_missing")
        report["pricing"] = prior
        report["exit_code"] = 0
    except Exception as exc:
        report.update(exit_code=2, reason=str(exc) if isinstance(exc, g.GuardBlocked) else "sanitized_fresh_preparation_failure")
    report["updated_at_utc"] = p.now()
    ex.write(output, report)
    print(json.dumps({k: report.get(k) for k in ("owner_nonce", "exit_code", "reason", "output", "updated_at_utc")}), flush=True)
    return report["exit_code"]


def execute(path, expected_hash):
    g.require(prep.digest(path) == expected_hash, "fresh_preparation_hash_mismatch")
    report = ex.load(path)
    nonce = report["owner_nonce"]
    g.require(nonce != LEGACY and report["exit_code"] == 0 and report["ids"] == g.owned_ids(nonce), "invalid_fresh_preparation")
    g.require(not set(report["ids"].values()) & set(g.owned_ids(LEGACY).values()), "legacy_id_overlap")
    g.require((datetime.now(UTC) - datetime.fromisoformat(report["updated_at_utc"])).total_seconds() < 1800, "fresh_preparation_expired")
    g.require(prep.digest(build.OUT) == report["image_reuse"]["image_evidence_sha256"], "image_evidence_changed")
    output = p.ROOT / ("gateway/validation/finops-fresh-execution-" + nonce + ".json")
    return ex.main(preparation=path, output=output)


def verify_completed(nonce):
    """Independent GET-only reconciliation. Never retry a probe or DELETE."""
    import ctypes
    from scripts.deployment import finops_release
    path = p.ROOT / ("gateway/validation/finops-fresh-execution-" + nonce + ".json")
    output = p.ROOT / ("gateway/validation/finops-fresh-final-" + nonce + ".json")
    g.require(not output.exists(), "final_evidence_already_exists")
    execution = ex.load(path)
    session_path = p.ROOT / ".deployment/finops-runner" / nonce / "execution/session.json"
    expected_hash = execution["independent_watchdog_ready"]["session_sha256"]
    session = ex.bound_session(session_path, expected_hash)
    g.require(execution["ids"] == session["ids"] and execution["owner_nonce"] == nonce, "execution_binding_changed")
    report = {"started_at_utc": p.now(), "owner_nonce": nonce, "session_sha256": expected_hash,
        "mode": "read_only_final_verification_no_provision_probe_retry_or_delete",
        "execution_sha256": prep.digest(path), "private_database_aggregates": None,
        "created_resource_count": len(execution["created_resource_ids"]),
        "database_writes": 0, "probe_retries": 0, "app_release": False, "timer_enabled": False}
    try:
        report["fresh_exact_id_gets"] = exact_absence(session["ids"])
        report["legacy_exact_id_gets"] = exact_absence(g.owned_ids(LEGACY))
        report["outstanding_resource_ids"] = []
        report["preservation"] = prep.preservation_readback()
        report["image_reuse"] = verify_image()
        report["probes"] = execution["probes"]
        g.require(set(report["probes"]) == set(g.IDENTITIES), "both_probe_results_required")
        g.require(all(x["arm_logs_nonempty"] and x["state"] == "Terminated" and x["restart_count"] == 0
            and x["session_sha256"] == expected_hash for x in report["probes"].values()), "actual_probe_output_required")
        report["database_readiness_accepted"] = all(x["probe_exit_code"] == 0 for x in report["probes"].values())
        report["database_failure_not_classified_as_permission_denial"] = not report["database_readiness_accepted"]
        report["ingestion_destination_constructed_for_probe_not_live_function_config"] = True
        report["production_configuration_and_cutoff_still_require_separate_review"] = True
        prior = ex.load(p.ROOT / ".deployment/finops/source-manifest.json")
        current = finops_release.source_manifest()
        report["current_application_source_sha256"] = {k: v["source_sha256"] for k, v in current["components"].items()}
        report["application_source_matches_prior_manifest"] = all(v["source_sha256"] == prior["components"][k]["source_sha256"]
            for k, v in current["components"].items())
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        report["watchdogs"] = []
        for pid, bound in ((10156, LEGACY), (execution["watchdog_pid"], nonce)):
            handle = kernel.OpenProcess(0x1000, False, pid)
            code = ctypes.c_ulong()
            active = bool(handle and kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259)
            if handle: kernel.CloseHandle(handle)
            report["watchdogs"].append({"pid": pid, "owner_nonce": bound, "active_observed": active, "stopped": False})
        report["cleanup_marker_present"] = (session_path.parent / "cleanup-started.json").is_file()
        report["exit_code"] = 0
    except Exception as exc:
        report.update(exit_code=2, reason=str(exc) if isinstance(exc, g.GuardBlocked) else "sanitized_final_verification_failure")
    report["finished_at_utc"] = p.now()
    ex.write(output, report)
    print(json.dumps(report), flush=True)
    return report["exit_code"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-approved", action="store_true")
    modes.add_argument("--execute-prepared", type=Path)
    modes.add_argument("--verify-completed")
    parser.add_argument("--preparation-sha256")
    args = parser.parse_args()
    raise SystemExit(prepare() if args.prepare_approved else verify_completed(args.verify_completed)
        if args.verify_completed else execute(args.execute_prepared, args.preparation_sha256))