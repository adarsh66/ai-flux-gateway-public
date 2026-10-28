"""Finite offline/native-Linux validation only. No deployment or gateway calls."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime

from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt


def offline():
    commands = [
        [sys.executable, "-m", "pytest", "-q", "tests/unit/test_poc_controls.py",
         "tests/unit/test_gateway_settings.py", "tests/unit/test_managed_controls.py",
         "tests/unit/test_admin_subscriptions.py", "tests/contract/test_gateway_dev_policy.py",
         "-k", "not migration", "--junitxml=gateway/validation/poc-controls-offline-tests-20261027.xml"],
        ["C:/Program Files/nodejs/node.exe", "node_modules/typescript/bin/tsc", "--noEmit", "-p", "packages/ui/tsconfig.json"],
    ]
    for args in commands:
        p = subprocess.run(args, cwd=rt.ROOT, env=rt.ENV, check=False)
        if p.returncode:
            return p.returncode
    return 0


def guidance():
    exe = "C:/Program Files/Microsoft VS Code/Extensions/ms-azuretools.vscode-azure-mcp-server-3.0.51-win32-x64/server/azmcp.exe"
    return subprocess.run([exe, "azureterraformbestpractices", "get"], env=rt.ENV, check=False).returncode


def terraform():
    args = [rt.TF, "-chdir=infra/project-route"]
    for command in [["validate", "-no-color"],
                    ["test", "-no-color", "-filter=tests\\defaults.tftest.hcl", "-filter=tests\\external.tftest.hcl",
                     "-filter=tests\\poc-controls.tftest.hcl"]]:
        p = subprocess.run(args + command, cwd=rt.ROOT, env=rt.ENV, check=False)
        if p.returncode:
            return p.returncode
    return 0


def linux(corrected=False):
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    folder = rt.HOME / "poc-controls-20261027" / ("linux-validation-corrected" if corrected else "linux-validation")
    if corrected:
        prior = json.loads((rt.ROOT / "gateway/validation/poc-controls-linux-validation-20261027.json").read_text())
        rt.require(prior["run_id"] == "cm26" and prior["exit_code"] == 1 and prior["no_push"], "prior_validation_failure")
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "build-intent.json").open("x") as f:
        json.dump({"at": datetime.now(UTC).isoformat(), "no_push": True}, f)
    files = portals.source_files() + [rt.ROOT / "infra/image-build/FinOpsValidation.Dockerfile"]
    context = folder / "context"
    entries = []
    for path in files:
        target = context / path.relative_to(rt.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        entries.append({"path": path.relative_to(rt.ROOT).as_posix(), "sha256": portals.digest(path.read_bytes())})
    rt.save(folder / "sources.json", {"entries": entries})
    p = subprocess.run(rt.CLI + ["acr", "build", "--registry", portals.REGISTRY,
        "--subscription", rt.SUB, "--platform", "linux/amd64", "--timeout", "1800", "--no-push",
        "--file", "infra/image-build/FinOpsValidation.Dockerfile", "."], cwd=context, env=rt.ENV,
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', p.stdout + p.stderr)
    (folder / "validation.log").write_text(text, encoding="utf-8")
    runs = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
    result = {"at_utc": datetime.now(UTC).isoformat(), "exit_code": p.returncode,
              "run_id": runs[-1] if runs else None, "no_push": True, "deployed": False,
              "sources_sha256": portals.digest(json.dumps(entries, sort_keys=True).encode())}
    name = "poc-controls-linux-validation-corrected-20261027.json" if corrected else "poc-controls-linux-validation-20261027.json"
    rt.save(rt.ROOT / "gateway/validation" / name, result)
    print(json.dumps(result), flush=True)
    print("\n".join(text.splitlines()[-100:]), flush=True)
    return p.returncode


def linux_api():
    """Validate the existing curated production package; do not publish an image."""
    from scripts.deployment.glm_runtime_release import api_sources
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    folder = rt.HOME / "poc-controls-20261027/linux-api-validation"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "build-intent.json").open("x") as handle:
        json.dump({"at": datetime.now(UTC).isoformat(), "no_push": True, "scope": "api-only"}, handle)
    files = api_sources() + [rt.ROOT / ("tests/unit/" + name) for name in (
        "conftest.py", "test_poc_controls.py", "test_gateway_settings.py",
        "test_managed_controls.py", "test_admin_subscriptions.py")]
    files += [rt.ROOT / "gateway/policies/poc-settings-defaults.xml"]
    context = folder / "context"
    entries = []
    for path in files:
        raw = path.read_bytes()
        rt.require(not path.is_symlink() and not re.search(
            rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", raw),
            "source_secret_or_symlink")
        target = context / path.relative_to(rt.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        entries.append({"path": path.relative_to(rt.ROOT).as_posix(), "sha256": portals.digest(raw)})
    # The existing release packager explicitly excludes the sandbox-only
    # duplicate 0003_portal_users migration. No migration source is modified.
    rt.require(not (context / "services/control-plane/migrations/versions/0003_portal_users.py").exists(),
               "existing_production_migration_packaging_required")
    docker = (context / "services/control-plane/Dockerfile").read_text()
    docker += ('\nRUN python -m pip install --user --no-cache-dir pytest==8.4.0\n'
               'COPY tests/unit /app/tests/unit\n'
               'COPY gateway/policies/poc-settings-defaults.xml /app/gateway/policies/poc-settings-defaults.xml\n'
               'RUN python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path(\'/app/services/control-plane/src\').rglob(\'*.py\')]"\n'
               'RUN python -m pytest -q tests/unit --junitxml=/tmp/poc-backend.xml\n')
    (context / "PocApiValidation.Dockerfile").write_text(docker, encoding="utf-8")
    rt.save(folder / "sources.json", {"entries": entries,
        "validation_dockerfile_sha256": portals.digest(docker.encode())})
    p = subprocess.run(rt.CLI + ["acr", "build", "--registry", portals.REGISTRY,
        "--subscription", rt.SUB, "--platform", "linux/amd64", "--timeout", "1800", "--no-push",
        "--file", "PocApiValidation.Dockerfile", "."], cwd=context, env=rt.ENV,
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', p.stdout + p.stderr)
    (folder / "validation.log").write_text(text, encoding="utf-8")
    runs = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
    result = {"at_utc": datetime.now(UTC).isoformat(), "exit_code": p.returncode,
              "run_id": runs[-1] if runs else None, "no_push": True, "deployed": False,
              "scope": "api-only", "migration_source_changes": 0,
              "sources_sha256": portals.digest(json.dumps(entries, sort_keys=True).encode())}
    rt.save(rt.ROOT / "gateway/validation/poc-controls-linux-api-validation-20261027.json", result)
    print(json.dumps(result), flush=True)
    print("\n".join(text.splitlines()[-65:]), flush=True)
    return p.returncode


if __name__ == "__main__":
    raise SystemExit({"offline": offline, "guidance": guidance, "linux": linux,
                      "linux-corrected": lambda: linux(True), "linux-api": linux_api,
                      "terraform": terraform}[sys.argv[1]]())