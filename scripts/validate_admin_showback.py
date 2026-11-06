"""Fresh source-bound UI validation only: existing ACR, no push or deployment.

Reuses the established curated source collector and validation Dockerfile, not
any release intent, saved plan, image publisher, or activation workflow.
"""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess

from scripts.deployment import customer_catalog_validate as native
from scripts.deployment.glm_resume import bestpractices

REQUIRED = {
    "packages/ui/src/components/AdminUsage.tsx", "packages/ui/src/pages/UsagePage.tsx",
    "packages/ui/src/admin-showback.test.tsx", "packages/ui/src/client.ts", "packages/ui/src/types.ts",
}


def validate():
    rt, portals = native.rt, native.portals
    bestpractices()
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
    folder = rt.HOME / ("admin-showback-native-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(parents=True, exist_ok=False)
    manifest = native.stage(folder)
    rt.require(REQUIRED <= {entry["path"] for entry in manifest["entries"]}, "admin_sources_missing")
    rt.save(folder / "sources.json", manifest)
    with (folder / "build-intent.json").open("x", encoding="utf-8") as handle:
        json.dump({"args": native.build_args(), "no_push": True, "deployed": False,
                   "max_builds": 1, "source_sha256": manifest["source_sha256"]}, handle)
    print("EVIDENCE=" + folder.relative_to(rt.ROOT).as_posix(), flush=True)
    process = subprocess.run(rt.CLI + native.build_args(), cwd=folder / "context", env=rt.ENV,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    text = native.redact(process.stdout + process.stderr)
    (folder / "validation.log").write_text(text, encoding="utf-8")
    runs = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
    result = {"exit_code": process.returncode, "run_id": runs[-1] if runs else None,
              "no_push": True, "deployed": False, "source_sha256": manifest["source_sha256"]}
    rt.save(folder / "result.json", result)
    if runs:
        run = rt.cli(["acr", "task", "show-run", "--registry", portals.REGISTRY,
                      "--run-id", runs[-1], "--subscription", rt.SUB])
        result.update({k: run.get(k) for k in ("status", "finishTime", "outputImages")})
    result["sources_unchanged"] = all(portals.digest((base / e["path"]).read_bytes()) == e["sha256"]
                                      for e in manifest["entries"] for base in (rt.ROOT, folder / "context"))
    result["proof_markers"] = {marker: marker in text for marker in (
        "RUN npm run typecheck", "RUN npm test", "RUN npm run build",
        "admin-showback.test.tsx", "Test Files", "Tests", "Successfully built")}
    result["passed"] = (process.returncode == 0 and result.get("status") == "Succeeded"
                        and native.no_published_images(result.get("outputImages"))
                        and result["sources_unchanged"] and all(result["proof_markers"].values()))
    rt.save(folder / "result.json", result)
    print(json.dumps(result), flush=True)
    print("\n".join(text.splitlines()[-120:]), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-push", action="store_true", required=True)
    parser.parse_args()
    raise SystemExit(validate())