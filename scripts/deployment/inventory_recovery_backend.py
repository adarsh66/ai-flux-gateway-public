"""One read-only backend readiness check before any production image push."""
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from scripts.deployment import inventory_recovery_oct29 as r
from scripts.deployment.inventory_recovery_native import package


def main(folder):
    r.rt.require(folder.parent == r.rt.HOME and folder.name.startswith("inventory-recovery-20261029-"), "fresh_scope")
    native = r.load(folder / "native.json")
    r.rt.require(native["passed"] and native["package_sha256"] == r.fs.sha(package(folder)), "actual_native_proof_required")
    r.write(folder, "backend-read-intent.json", {"at_utc": datetime.now(UTC).isoformat(), "read_only": True, "no_plan_no_apply": True})
    root = folder / "backend-preflight/infra/terraform"
    root.mkdir(parents=True, exist_ok=False)
    for path in (r.rt.ROOT / "infra/terraform").iterdir():
        if path.is_file() and (path.name.endswith((".tf", ".tf.json")) or path.name == ".terraform.lock.hcl"):
            shutil.copyfile(path, root / path.name)
    for name in ("infra/models", "gateway/catalog", "gateway/policies"):
        shutil.copytree(r.rt.ROOT / name, folder / "backend-preflight" / name,
                        ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tfplan", "__pycache__"))
    for path in (r.rt.ROOT / "gateway").glob("*.json"):
        shutil.copyfile(path, folder / "backend-preflight/gateway" / path.name)
    args = [r.rt.TF, "-chdir=" + str(root), "init", "-input=false", "-lockfile=readonly", "-no-color",
            "-backend-config=" + str(r.rt.ROOT / "infra/terraform/backend.hcl")]
    result = subprocess.run(args, cwd=r.rt.ROOT, env=r.rt.ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    text = result.stdout + result.stderr
    with (folder / "backend-init-private.log").open("x", encoding="utf-8") as handle:
        handle.write(text)
    categories = sorted(set(re.findall(r"AuthorizationFailure|AuthorizationFailed|ForbiddenByRbac|ForbiddenByFirewall|AADSTS\d+", text)))
    proof = {"at_utc": datetime.now(UTC).isoformat(), "exit_code": result.returncode,
             "status": "backend_initialized_no_plan_no_apply" if result.returncode == 0 else "blocked_backend_read_no_network_change",
             "error_categories": categories, "request_ids": re.findall(r"RequestId:([a-fA-F0-9-]+)", text),
             "azure_error_timestamps": re.findall(r"Time:([^\r\n]+)", text),
             "backend": {"account": "projpoctokenex", "container": "tfstate", "key": "poc-ids-token-ex/main.tfstate",
                         "subscription_id": r.rt.SUB, "tenant_id": r.rt.TENANT},
             "cloud_configuration_writes": 0, "network_changes": 0, "permission_changes": 0,
             "image_build_pushes": 0, "plans": 0, "applies": 0,
             "log_sha256": r.sha(text), "source_bound_native_run": native["run_id"]}
    r.write(folder, "backend-readiness.json", proof)
    print(json.dumps(proof), flush=True)
    return 0 if result.returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve()))