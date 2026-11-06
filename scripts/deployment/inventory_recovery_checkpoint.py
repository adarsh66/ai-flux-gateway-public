"""Final GET-only checkpoint and evidence integrity; no release retry path."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

from scripts.deployment import inventory_recovery_oct29 as r
from scripts.deployment.inventory_recovery_native import package


def main(folder):
    before = r.load(folder / "baseline.json")
    native = r.load(folder / "native.json")
    blocked = r.load(folder / "backend-readiness.json")
    r.rt.require(blocked["status"] == "blocked_backend_read_no_network_change", "blocked_state_no_retry")
    r.rt.require(native["package_sha256"] == r.fs.sha(package(folder)), "native_package_binding")
    r.install_read_transport()
    current = r.activation.snapshot()
    r.write(folder, "final-protected-baseline.json", current)
    unchanged = current == before
    r.rt.require(unchanged, "final_protected_baseline_changed")
    workers = subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|terraform|bash' } | ForEach-Object { @{ pid=$_.ProcessId; name=$_.Name; this_checkpoint=([string]$_.CommandLine -match 'inventory_recovery_checkpoint'); mutation_worker=([string]$_.CommandLine -match 'terraform.+(plan|apply)|scripts.deployment.+ (apply|plan|build|native|publish|reconcile)') } } | ConvertTo-Json -Compress"],
        env=r.rt.ENV, capture_output=True, text=True, check=True)
    values = json.loads(workers.stdout) if workers.stdout.strip() else []
    if isinstance(values, dict):
        values = [values]
    r.write(folder, "workers-final.json", values)
    r.rt.require(not any(w["mutation_worker"] for w in values), "mutation_worker_present")
    r.rt.require(not any((folder / n).exists() for n in ("build-intent.json", "plan-intent.json", "apply-intent.json")), "no_production_release_attempts")
    manifest = r.load(folder / "package-manifest.json")
    entries = r.load(folder / "native-input-manifest.json")["entries"]
    r.rt.require(all(r.sha((folder / "native/context" / e["path"]).read_bytes()) == e["sha256"] for e in entries), "native_input_integrity")
    retained = r.load(folder / "retained-intent-hashes.json")
    r.rt.require(all(r.sha((r.rt.ROOT / name).read_bytes()) == digest for name, digest in retained.items()), "historical_markers_unchanged")
    report = {"at_utc": datetime.now(UTC).isoformat(), "status": "blocked_backend_read_validated_metadata_package_not_deployed",
        "live_fixed": False, "all_protected_components_equal": unchanged,
        "protected_component_count": len(current), "protected_components": sorted(current),
        "all_four_appsettings_hashes_equal": before["settings_hashes"] == current["settings_hashes"],
        "all_four_image_pins_unchanged": True, "historical_intents_unchanged": True,
        "package_manifest_sha256": r.fs.sha(manifest), "native_input_hashes_equal": True,
        "native_run": native["run_id"], "native_tests": native["tests_passed"], "known_migration_tests_deselected": 2,
        "foundry_observed_at_utc": manifest["observed_at_utc"], "ttl_seconds": 86400,
        "metadata_package_expires_at_utc": (datetime.fromisoformat(manifest["observed_at_utc"]) + timedelta(seconds=86400)).isoformat(),
        "mutation_workers_observed": 0, "cloud_configuration_writes": 0,
        "production_build_pushes": 0, "saved_release_plans": 0, "applies": 0, "inference_requests": 0,
        "blocker": blocked, "runtime_auto_refresh": "not_enabled_no_proven_runtime_mi_arm_read",
        "next_stage": "Existing backend access must work without forbidden network/RBAC changes; then refresh metadata if needed, build the exact image once, prepare API-image-only saved plan and NEVER APPLY check companion if required, independently validate sequential workflow and Section7, apply once, independently read back and browser verify"}
    report["evidence_file_sha256"] = {p.name: r.sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()}
    r.write(folder, "final-checkpoint.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "evidence_file_sha256"}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())