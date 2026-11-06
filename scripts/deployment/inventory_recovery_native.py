"""Exclusive native no-push proof for metadata-only image recovery."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import sys

from scripts.deployment import inventory_recovery_oct29 as recovery
from scripts.deployment.fireworks_runtime import remote_build
from scripts.deployment.customer_catalog_validate import no_published_images

rt, fs = recovery.rt, recovery.fs
TESTS = ["test_usage_rankings.py", "test_usage_filters.py", "test_usage_series.py", "test_model_tokens.py",
         "test_control_plane.py", "test_admin_subscriptions.py", "test_display_pricing.py", "test_finops_ingestion.py",
         "test_poc_publisher_reliability.py", "test_gateway_settings.py", "test_poc_controls.py",
         "test_managed_controls.py", "test_external_inventory.py", "test_foundry_inventory.py"]


def package(folder):
    manifest = recovery.load(folder / "package-manifest.json")
    rt.require(manifest["base_image"] == recovery.IMAGE and manifest["auto_excluded"]
               and manifest["source_changes"] == [], "image_derived_metadata_only")
    root = folder / "context"
    rt.require({p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} == {e["path"] for e in manifest["entries"]}, "exact_package_membership")
    for entry in manifest["entries"]:
        rt.require(recovery.sha((root / entry["path"]).read_bytes()) == entry["sha256"], "package_drift")
    rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(manifest["observed_at_utc"]) < timedelta(hours=2), "release_metadata_evidence_too_old")
    return manifest


def main(folder):
    rt.require(folder.parent == rt.HOME and folder.name.startswith("inventory-recovery-20261029-"), "fresh_scope")
    source, _ = recovery.retained_sources()
    manifest = package(folder)
    recovery.write(folder, "native-intent.json", {"at_utc": datetime.now(UTC).isoformat(), "package_sha256": fs.sha(manifest), "no_push": True})
    root = folder / "native/context"
    shutil.copytree(folder / "context", root)
    for entry in source["entries"]:
        name = entry["path"]
        if name.startswith(("tests/unit/", "gateway/tools/")) or name in {
                "gateway/policies/poc-settings-defaults.xml", "services/usage-ingestion/ingestion-approved.json"}:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(recovery.BASE / name, target)
    shutil.copyfile(rt.ROOT / "scripts/deployment/inventory_image_attestation.py", root / "image_attestation.py")
    recovery.write(root, "retained-source-manifest.json", source)
    docker = ("FROM " + recovery.IMAGE + "\n"
              "COPY image_attestation.py retained-source-manifest.json /tmp/\n"
              "RUN python /tmp/image_attestation.py /tmp/retained-source-manifest.json before\n"
              "COPY --chown=10001:10001 gateway/catalog/foundry-inventory-20261026.json /app/gateway/catalog/foundry-inventory-20261026.json\n"
              "COPY --chown=10001:10001 gateway/catalog/external-inventory.json /app/gateway/catalog/external-inventory.json\n"
              "RUN python /tmp/image_attestation.py /tmp/retained-source-manifest.json after\n"
              "RUN python -m pip install --user --no-cache-dir pytest==8.4.0\n"
              "COPY tests/unit /app/tests/unit\nCOPY gateway/tools /app/gateway/tools\n"
              "COPY services/usage-ingestion/ingestion-approved.json /app/services/usage-ingestion/ingestion-approved.json\n"
              "COPY gateway/policies/poc-settings-defaults.xml /app/gateway/policies/poc-settings-defaults.xml\n"
              "RUN python -m pytest -q " + " ".join("tests/unit/" + name for name in TESTS) + ' -k "not migration"\n')
    (root / "NativeInventory.Dockerfile").write_text(docker, encoding="utf-8")
    recovery.write(folder, "native-input-manifest.json", {"entries": [{"path": p.relative_to(root).as_posix(), "sha256": recovery.sha(p.read_bytes())}
        for p in sorted(root.rglob("*")) if p.is_file()]})
    rt.CLI = ["C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"]
    result = remote_build(root, "NativeInventory.Dockerfile")
    log = (root.parent / "native-validation-build.log").read_text(encoding="utf-8")
    rt.require('"image_attestation": "before"' in log and '"image_attestation": "after"' in log, "actual_image_attestation_required")
    counts = re.findall(r"(\d+) passed", log)
    rt.require(counts and int(counts[-1]) >= 300, "actual_retained_regressions_required")
    package(folder)
    run = rt.cli(["acr", "task", "show-run", "-r", "pocidstokenexacr", "--run-id", result["run_id"], "--subscription", rt.SUB])
    rt.require(no_published_images(run.get("outputImages")), "native_must_not_publish")
    proof = {**result, "at_utc": datetime.now(UTC).isoformat(), "passed": True, "tests_passed": int(counts[-1]),
             "package_sha256": fs.sha(manifest), "base_image_filesystem_verified": True,
             "expired_base_http503_reproduced": True, "candidate_13_routes_verified": True,
             "api_sources_installed_and_packaged_unchanged": True, "unshipped_auto_excluded": True,
             "known_migration_tests_deselected": True, "inference_requests": 0}
    recovery.write(folder, "native.json", proof)
    print(json.dumps(proof), flush=True)


def finalize_existing(folder, run_id):
    """Reconcile the submitted run; wrapper encoding failure is not a retry."""
    rt.require(run_id == "cm30" and not (folder / "native.json").exists(), "existing_exact_native_run_only")
    manifest = package(folder)
    intent = recovery.load(folder / "native-intent.json")
    rt.require(intent["package_sha256"] == fs.sha(manifest), "native_package_binding")
    inputs = recovery.load(folder / "native-input-manifest.json")
    root = folder / "native/context"
    rt.require(all(recovery.sha((root / e["path"]).read_bytes()) == e["sha256"] for e in inputs["entries"]), "native_inputs_unchanged")
    rt.CLI = ["C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe", "-X", "utf8", "-IBm", "azure.cli"]
    run = rt.cli(["acr", "task", "show-run", "-r", "pocidstokenexacr", "--run-id", run_id, "--subscription", rt.SUB])
    rt.require(run["status"] == "Succeeded" and run.get("finishTime") and no_published_images(run.get("outputImages")), "existing_run_not_successfully_finished")
    log = (folder / ("run-" + run_id + "-readback.log")).read_text(encoding="utf-8")
    rt.require('"image_attestation": "before"' in log and '"image_attestation": "after"' in log
               and "309 passed, 2 deselected" in log and "was successful" in log, "actual_complete_native_proof")
    proof = {"at_utc": datetime.now(UTC).isoformat(), "run_id": run_id, "status": run["status"],
             "finished_at": run["finishTime"], "passed": True, "no_push": True, "tests_passed": 309,
             "package_sha256": fs.sha(manifest), "base_image_filesystem_verified": True,
             "expired_base_http503_reproduced": True, "candidate_13_routes_verified": True,
             "api_sources_installed_and_packaged_unchanged": True, "unshipped_auto_excluded": True,
             "known_migration_tests_deselected": 2, "inference_requests": 0,
             "wrapper_error": "az.cmd cp1252 log streaming only; no resubmission",
             "log_sha256": recovery.sha(log), "native_input_manifest_sha256": fs.sha(inputs)}
    recovery.write(folder, "native.json", proof)
    print(json.dumps(proof), flush=True)


if __name__ == "__main__":
    try:
        if sys.argv[1] == "--finalize-existing":
            finalize_existing(Path(sys.argv[2]).resolve(), sys.argv[3])
        else:
            main(Path(sys.argv[1]).resolve())
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__, "safe_error": str(error) if isinstance(error, RuntimeError) else "native_failed_reconcile_existing_run_before_any_retry"}), flush=True)
        raise SystemExit(2)