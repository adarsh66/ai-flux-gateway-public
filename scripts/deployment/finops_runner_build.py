"""One approved isolated ACR build. Never rebuild a recorded run automatically."""
from __future__ import annotations

import json
import subprocess
import threading
import time

from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_preflight as p
from scripts.deployment import finops_runner_prepare as prep

OUT = p.ROOT / "gateway/validation/finops-runner-image-20261027.json"


def az(args, timeout=90):
    result = subprocess.run([p.AZ, *args, "--subscription", g.SUB, "--only-show-errors", "-o", "json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=p.ENV, timeout=timeout)
    g.require(result.returncode == 0, "acr_command_failed")
    return json.loads(result.stdout)


def save(report):
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    report = json.loads(OUT.read_text()) if OUT.exists() else {"started_at_utc": p.now(), "cloud_build_runs": 0}
    try:
        account = p.cli(["account", "show"])
        g.require(account["id"] == g.SUB and account["tenantId"] == g.TENANT, "account_scope_mismatch")
        evidence = json.loads(prep.OUT.read_text())
        nonce = evidence["owner_nonce"]
        g.require(evidence["security_scan"]["security_gate_passed"], "security_scan_required")
        lock = evidence["image_dependency_lock"]
        context = p.ROOT / evidence["image_package"]["context"]
        expected = dict(evidence["image_package"]["files_sha256"])
        expected["requirements.lock.txt"] = lock["lock_sha256"]
        expected.update({"wheels/" + name: item["sha256"] for name, item in lock["wheels"].items()})
        actual = {str(f.relative_to(context)).replace("\\", "/"): prep.digest(f) for f in context.rglob("*") if f.is_file()}
        g.require(actual == expected, "image_context_changed")
        report.update(owner_nonce=nonce, context_manifest_sha256=__import__("hashlib").sha256(
            json.dumps(actual, sort_keys=True).encode()).hexdigest(), context_files_sha256=actual,
            timeout_seconds=900, build_cpu=2, platform="linux/amd64", source_probe_sha256=actual["finops_private_probe.py"],
            source_entrypoint_sha256=actual["entrypoint.py"], logs_exported=False)
        tag = "aiflux-finops-probe:probe-" + nonce
        if "run_id" not in report:
            g.require(report["cloud_build_runs"] == 0, "build_submission_requires_manual_reconciliation")
            # Record submission intent BEFORE a potentially ambiguous network result.
            report.update(cloud_build_runs=1, submission_intent_at_utc=p.now())
            save(report)
            value = az(["acr", "build", "--registry", "pocidstokenexacr", "--image", tag,
                # Installed CLI has no --cpu flag. ACR quick builds default to
                # two CPUs; verify the returned run agent configuration below.
                "--file", str(context / "Dockerfile"), "--platform", "linux/amd64", "--timeout", "900",
                "--no-wait", "--no-logs", str(context)], timeout=150)
            run_id = value.get("runId") or value.get("name") or value.get("properties", {}).get("runId")
            g.require(isinstance(run_id, str) and __import__("re").fullmatch(r"[a-z0-9]+", run_id), "acr_run_id_unverified")
            report["run_id"] = run_id
            save(report)
        deadline = time.monotonic() + 960
        while True:
            value = az(["acr", "task", "show-run", "--registry", "pocidstokenexacr", "--run-id", report["run_id"]])
            report.update(status=value.get("status"), build_started_at_utc=value.get("startTime"),
                build_finished_at_utc=value.get("finishTime"), observed_at_utc=p.now())
            save(report)
            if report["status"] in {"Succeeded", "Failed", "Canceled", "Error", "Timeout"}:
                break
            if time.monotonic() >= deadline:
                az(["acr", "task", "cancel-run", "--registry", "pocidstokenexacr", "--run-id", report["run_id"]])
                raise g.GuardBlocked("acr_owned_build_deadline")
            threading.Event().wait(8)
        g.require(report["status"] == "Succeeded", "linux_build_failed")
        report["agent_configuration"] = value.get("agentConfiguration")
        g.require(value.get("agentConfiguration", {}).get("cpu") == 2, "acr_actual_cpu_unverified")
        metadata = az(["acr", "manifest", "show-metadata", "--registry", "pocidstokenexacr", "--name", tag])
        digest = metadata.get("digest", "")
        g.require(__import__("re").fullmatch(r"sha256:[0-9a-f]{64}", digest), "immutable_digest_missing")
        g.require(value.get("outputImages") == [{"digest": digest, "registry": "pocidstokenexacr.azurecr.io",
            "repository": "aiflux-finops-probe", "tag": "probe-" + nonce}], "build_output_digest_mismatch")
        # This CLI's show-metadata has no size field. Read and hash the actual
        # content-addressed manifest, then sum its compressed layer descriptors.
        manifest_result = subprocess.run([p.AZ, "acr", "manifest", "show", "--registry", "pocidstokenexacr",
            "--name", "aiflux-finops-probe@" + digest, "--raw", "--subscription", g.SUB, "--only-show-errors"],
            capture_output=True, env=p.ENV, timeout=90)
        g.require(manifest_result.returncode == 0, "manifest_read_failed")
        # Windows CLI text output expands the registry's LF bytes to CRLF.
        # Accept a normalization ONLY if its exact hash equals the registry digest.
        lf = manifest_result.stdout.replace(b"\r\n", b"\n")
        candidates = [manifest_result.stdout, manifest_result.stdout.rstrip(b"\r\n"), lf, lf.rstrip(b"\n")]
        raw = next((b for b in candidates if __import__("hashlib").sha256(b).hexdigest() == digest[7:]), None)
        g.require(raw is not None, "manifest_content_hash_mismatch")
        manifest = json.loads(raw)
        g.require(manifest.get("schemaVersion") == 2 and manifest.get("layers") and "manifests" not in manifest, "single_linux_manifest_required")
        size = sum(x["size"] for x in manifest["layers"]) + manifest["config"]["size"]
        g.require(type(size) is int and 0 < size <= 1_000_000_000, "compressed_image_bound")
        report.update(immutable_image="pocidstokenexacr.azurecr.io/aiflux-finops-probe@" + digest,
            manifest_content_sha256=digest.removeprefix("sha256:"), compressed_image_bytes=size,
            linux_dependency_imports_and_pip_check_passed=True, exit_code=0, reason=None)
    except Exception as exc:
        report.update(exit_code=2, reason=str(exc) if isinstance(exc, g.GuardBlocked) else "sanitized_image_build_failure")
    finally:
        report["updated_at_utc"] = p.now()
        save(report)
        print(json.dumps({k: report.get(k) for k in ("run_id", "status", "immutable_image", "compressed_image_bytes", "exit_code", "reason")}))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())