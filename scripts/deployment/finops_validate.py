"""Validation-only Linux ACR build. No image push, deploy, settings or Terraform reads."""
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime

from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt


def main():
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    files = portals.source_files() + [rt.ROOT / "infra/image-build/FinOpsValidation.Dockerfile"]
    entries = [{"path": p.relative_to(rt.ROOT).as_posix(), "sha256": portals.digest(p.read_bytes())} for p in files]
    source_hash = portals.digest(json.dumps(entries, sort_keys=True).encode())
    folder = rt.HOME / "finops" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + source_hash[:12])
    context = folder / "context"
    for path in files:
        target = context / path.relative_to(rt.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    rt.save(folder / "source-manifest.json", {"source_hash": source_hash, "entries": entries})
    print(json.dumps({"validation_folder": folder.relative_to(rt.ROOT).as_posix(), "source_hash": source_hash}), flush=True)
    args = rt.CLI + ["acr", "build", "--registry", portals.REGISTRY, "--subscription", rt.SUB,
                     "--platform", "linux/amd64", "--timeout", "1800", "--no-push",
                     "--file", "infra/image-build/FinOpsValidation.Dockerfile", "."]
    process = subprocess.run(args, cwd=context, env=rt.ENV, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', process.stdout + process.stderr)
    (folder / "validation.log").write_text(text, encoding="utf-8")
    runs = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
    result = {"at": datetime.now(UTC).isoformat(), "source_hash": source_hash,
              "exit_code": process.returncode, "run_id": runs[-1] if runs else None,
              "no_push": True, "deployed": False}
    if runs:
        run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", runs[-1], "--subscription", rt.SUB])
        result["status"] = run["status"]
    rt.save(folder / "result.json", result)
    print(json.dumps(result), flush=True)
    print("\n".join(text.splitlines()[-100:]), flush=True)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())