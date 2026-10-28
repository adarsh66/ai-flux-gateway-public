"""One fresh ACR validation attempt only; no image publication or deployment."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess

from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt

DOCKERFILE = "infra/image-build/FinOpsValidation.Dockerfile"
REQUIRED = {
    "packages/ui/src/modelPresentation.ts",
    "packages/ui/src/modelPresentation.test.ts",
    "packages/ui/src/pages/TokenExchangePages.tsx",
    "packages/ui/src/token-exchange.test.tsx",
}


def redact(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', text)
    return re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~-]+", r"\1[redacted]", text)


def build_args() -> list[str]:
    return ["acr", "build", "--registry", portals.REGISTRY,
            "--subscription", rt.SUB, "--platform", "linux/amd64",
            "--timeout", "1800", "--no-push", "--file", DOCKERFILE, "."]


def no_published_images(images) -> bool:
    # ACR represents an untagged --no-push build as [null], not always [].
    return images is None or (isinstance(images, list) and all(image is None for image in images))


def verify_existing(name: str) -> int:
    """Reconcile a completed attempt read-only; never submits a build."""
    rt.require(bool(re.fullmatch(r"customer-catalog-copy-\d{8}T\d{12}Z", name)), "invalid_evidence_name")
    folder = rt.HOME / name
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    intent = json.loads((folder / "build-intent.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
    rt.require(intent["args"] == build_args() and intent["no_push"] and result["no_push"], "intent_changed")
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT
               and account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_scope")
    run = rt.cli(["acr", "task", "show-run", "--registry", portals.REGISTRY,
                  "--run-id", result["run_id"], "--subscription", rt.SUB])
    rt.require(run["status"] == "Succeeded" and run["finishTime"] == result["finishTime"]
               and no_published_images(run.get("outputImages")), "run_status_or_images")
    entries = manifest["entries"]
    rt.require(REQUIRED <= {e["path"] for e in entries}, "required_sources_missing")
    rt.require(manifest["source_sha256"] == result["source_sha256"] == portals.digest(
        json.dumps(entries, sort_keys=True).encode()), "manifest_hash")
    for entry in entries:
        relative = Path(entry["path"])
        rt.require(not relative.is_absolute() and ".." not in relative.parts, "invalid_source_path")
        rt.require(all(portals.digest((base / relative).read_bytes()) == entry["sha256"]
                       for base in (rt.ROOT, folder / "context")), "source_hash_changed")
    text = (folder / "validation.log").read_text(encoding="utf-8")
    rt.require(result["exit_code"] == 0 and all(result["proof_markers"].values()), "build_proof_missing")
    tests = re.search(r"Tests\s+(\d+) passed \((\d+)\)", text)
    files = re.search(r"Test Files\s+(\d+) passed \((\d+)\)", text)
    rt.require(tests is not None and files is not None, "test_summary_missing")
    proof = {**result, "passed": True, "verified_at_utc": datetime.now(UTC).isoformat(),
             "reconciliation_only": True, "additional_builds": 0,
             "tests_passed": int(tests[1]), "test_files_passed": int(files[1]),
             "validation_log_sha256": portals.digest(text.encode()),
             "no_published_images_verified": True,
             "original_false_failure": "ACR outputImages [null] incorrectly treated as a published image"}
    rt.save(folder / "verification.json", proof)
    print(json.dumps(proof, indent=2), flush=True)
    return 0


def stage(folder: Path) -> dict:
    """Use the established allowlist, including untracked/new UI source files."""
    files = sorted(set(portals.source_files() + [rt.ROOT / DOCKERFILE]))
    entries = []
    for path in files:
        relative = path.relative_to(rt.ROOT)
        rt.require(not any(p.is_symlink() for p in (path, *path.parents)), "source_symlink")
        rt.require(path.resolve().is_relative_to(rt.ROOT.resolve()), "source_outside_workspace")
        rt.require(path.suffix.lower() not in {".pem", ".key", ".pfx", ".env"}, "secret_extension")
        raw = path.read_bytes()
        rt.require(not re.search(
            rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", raw),
            "source_secret:" + relative.as_posix())
        target = folder / "context" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(raw)
        entries.append({"path": relative.as_posix(), "sha256": portals.digest(raw)})
    rt.require(REQUIRED <= {e["path"] for e in entries}, "required_copy_sources_missing")
    return {"entries": entries, "source_sha256": portals.digest(json.dumps(entries, sort_keys=True).encode()),
            "source_collection": "portal_fix.source_files plus existing validation Dockerfile"}


def validate() -> int:
    rt.require(Path(rt.CA).is_file(), "corporate_ca_missing")
    rt.require(rt.ENV.get("AZURE_CLI_DISABLE_CONNECTION_VERIFICATION", "").lower()
               not in {"1", "true", "yes"}, "tls_verification_disabled")
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT
               and account["state"] == "Enabled"
               and account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_scope")
    registry = rt.cli(["acr", "show", "--name", portals.REGISTRY, "--subscription", rt.SUB])
    rt.require(registry["id"].lower() == (rt.RG + "/providers/Microsoft.ContainerRegistry/registries/"
               + portals.REGISTRY).lower() and registry["loginServer"] == portals.HOST
               and not registry["adminUserEnabled"], "registry_scope_or_security")
    folder = rt.HOME / ("customer-catalog-copy-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(parents=True, exist_ok=False)
    with (folder / "build-intent.json").open("x", encoding="utf-8") as handle:
        json.dump({"at_utc": datetime.now(UTC).isoformat(), "args": build_args(), "no_push": True,
                   "max_builds": 1, "deployed": False, "account_scope_verified": True}, handle, indent=2)
    manifest = stage(folder)
    rt.save(folder / "sources.json", manifest)
    rt.save(folder / "launcher-sources.json", {p: portals.digest((rt.ROOT / p).read_bytes()) for p in (
        "scripts/deployment/customer_catalog_validate.py", "scripts/deployment/portal_fix.py",
        "scripts/deployment/runtime_rollout.py")})
    print("VALIDATION_EVIDENCE=" + folder.relative_to(rt.ROOT).as_posix(), flush=True)
    print("Submitting exactly one bounded linux/amd64 --no-push validation build", flush=True)
    process = subprocess.run(rt.CLI + build_args(), cwd=folder / "context", env=rt.ENV,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    text = redact(process.stdout + process.stderr)
    (folder / "validation.log").write_text(text, encoding="utf-8")
    runs = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
    result = {"at_utc": datetime.now(UTC).isoformat(), "exit_code": process.returncode,
              "run_id": runs[-1] if runs else None, "no_push": True, "deployed": False,
              "source_sha256": manifest["source_sha256"], "source_count": len(manifest["entries"]),
              "evidence": folder.relative_to(rt.ROOT).as_posix(), "status": "Unverified"}
    rt.save(folder / "result.json", result)
    if runs:
        run = rt.cli(["acr", "task", "show-run", "--registry", portals.REGISTRY,
                      "--run-id", runs[-1], "--subscription", rt.SUB])
        result.update({k: run.get(k) for k in ("status", "createTime", "startTime", "finishTime", "outputImages")})
    result["sources_unchanged"] = all(
        portals.digest((rt.ROOT / e["path"]).read_bytes()) == e["sha256"] for e in manifest["entries"])
    result["context_hashes_verified"] = all(
        portals.digest((folder / "context" / e["path"]).read_bytes()) == e["sha256"] for e in manifest["entries"])
    result["proof_markers"] = {marker: marker in text for marker in (
        "RUN npm run typecheck", "RUN npm test", "RUN npm run build", "Test Files", "Tests",
        "modelPresentation.test.ts", "token-exchange.test.tsx", "@aiflux/customer-portal", "Successfully built")}
    result["passed"] = (process.returncode == 0 and result["status"] == "Succeeded"
                        and no_published_images(result.get("outputImages")) and result["sources_unchanged"]
                        and result["context_hashes_verified"] and all(result["proof_markers"].values()))
    rt.save(folder / "result.json", result)
    print(json.dumps(result, indent=2), flush=True)
    print("\n".join(text.splitlines()[-100:]), flush=True)
    return 0 if result["passed"] else (process.returncode or 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-push", action="store_true", required=True)
    parser.add_argument("--verify-existing", help="Read-only reconciliation of an existing completed attempt")
    args = parser.parse_args()
    raise SystemExit(verify_existing(args.verify_existing) if args.verify_existing else validate())