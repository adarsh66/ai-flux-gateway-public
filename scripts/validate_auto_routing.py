"""Fresh Auto UI Linux validation; one ACR no-push submission, never a release."""
import argparse
from datetime import UTC, datetime
import json
import re
import subprocess

from scripts.deployment import customer_catalog_validate as native

REQUIRED = {
    "packages/ui/src/auto-routing.test.tsx", "packages/ui/src/autoRouting.ts",
    "packages/ui/src/pages/AdminAutoRouterPage.tsx", "packages/ui/src/pages/PlaygroundPage.tsx",
    "packages/ui/src/chat.ts", "packages/ui/src/chat.test.ts",
}


def reconcile(folder):
    """Read only the existing run; never rebuild on a wrapper/encoding failure."""
    rt, portals = native.rt, native.portals
    intent = json.loads((folder / "build-intent.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
    rt.require(intent["args"] == native.build_args() and intent["no_push"], "intent_changed")
    text = (folder / "validation.log").read_text(encoding="utf-8")
    runs = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
    rt.require(bool(runs), "run_id_unknown_do_not_resubmit")
    run = rt.cli(["acr", "task", "show-run", "--registry", portals.REGISTRY,
                  "--run-id", runs[-1], "--subscription", rt.SUB])
    unchanged = all(portals.digest((base / e["path"]).read_bytes()) == e["sha256"]
                    for e in manifest["entries"] for base in (rt.ROOT, folder / "context"))
    tests = re.search(r"Tests\s+(\d+) passed \((\d+)\)", text)
    files = re.search(r"Test Files\s+(\d+) passed \((\d+)\)", text)
    markers = {s: s in text for s in ("RUN npm run typecheck", "RUN npm test", "RUN npm run build",
        "auto-routing.test.tsx", "@aiflux/ui", "@aiflux/admin-portal", "@aiflux/customer-portal", "Successfully built")}
    result = {"at_utc": datetime.now(UTC).isoformat(), "run_id": runs[-1],
        "status": run["status"], "finishTime": run.get("finishTime"), "outputImages": run.get("outputImages"),
        "no_push": True, "deployed": False, "source_sha256": manifest["source_sha256"],
        "source_count": len(manifest["entries"]), "sources_and_context_unchanged": unchanged,
        "log_sha256": portals.digest(text.encode()), "proof_markers": markers,
        "tests_passed": int(tests[1]) if tests else None, "test_files_passed": int(files[1]) if files else None,
        "excluded": ["Playwright browser E2E", "live MI/scoring/inference", "APIM C# runtime compilation"]}
    result["passed"] = (run["status"] == "Succeeded" and native.no_published_images(run.get("outputImages"))
        and unchanged and tests is not None and files is not None and all(markers.values()))
    rt.save(folder / "result.json", result)
    print(json.dumps({"evidence": folder.relative_to(rt.ROOT).as_posix(), **result}, indent=2), flush=True)
    print("\n".join(text.splitlines()[-100:]), flush=True)
    return 0 if result["passed"] else 1


def validate():
    rt, portals = native.rt, native.portals
    rt.require(native.Path(rt.CA).is_file(), "corporate_ca_missing")
    rt.require(rt.ENV.get("AZURE_CLI_DISABLE_CONNECTION_VERIFICATION", "").lower()
               not in {"1", "true", "yes"}, "tls_verification_disabled")
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT and account["state"] == "Enabled"
        and account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_scope")
    registry = rt.cli(["acr", "show", "--name", portals.REGISTRY, "--subscription", rt.SUB])
    rt.require(registry["id"].lower() == (rt.RG + "/providers/Microsoft.ContainerRegistry/registries/"
        + portals.REGISTRY).lower() and registry["loginServer"] == portals.HOST
        and not registry["adminUserEnabled"], "registry_scope_or_security")
    folder = rt.HOME / ("auto-routing-native-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(parents=True, exist_ok=False)
    manifest = native.stage(folder)
    rt.require(REQUIRED <= {e["path"] for e in manifest["entries"]}, "auto_sources_missing")
    rt.save(folder / "sources.json", manifest)
    rt.save(folder / "launcher-sources.json", {p: portals.digest((rt.ROOT / p).read_bytes()) for p in (
        "scripts/validate_auto_routing.py", "scripts/deployment/customer_catalog_validate.py",
        "scripts/deployment/portal_fix.py", "scripts/deployment/runtime_rollout.py")})
    with (folder / "build-intent.json").open("x", encoding="utf-8") as handle:
        json.dump({"args": native.build_args(), "no_push": True, "max_builds": 1,
                   "source_sha256": manifest["source_sha256"]}, handle)
    print("EVIDENCE=" + folder.relative_to(rt.ROOT).as_posix(), flush=True)
    process = subprocess.run(rt.CLI + native.build_args(), cwd=folder / "context", env=rt.ENV,
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    (folder / "validation.log").write_text(native.redact(process.stdout + process.stderr), encoding="utf-8")
    rt.save(folder / "command-result.json", {"exit_code": process.returncode, "args": native.build_args()})
    return reconcile(folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-push", action="store_true", required=True)
    parser.add_argument("--reconcile", help="Existing evidence directory name; read-only, no submission")
    args = parser.parse_args()
    if args.reconcile:
        native.rt.require(bool(re.fullmatch(r"auto-routing-native-\d{8}T\d{12}Z", args.reconcile)), "invalid_evidence_name")
    raise SystemExit(reconcile(native.rt.HOME / args.reconcile) if args.reconcile else validate())