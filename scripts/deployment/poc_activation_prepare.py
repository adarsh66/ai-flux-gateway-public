"""Exclusive current-source activation validation/builds. No deployment entrypoint."""
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
import sys

from scripts.deployment import runtime_rollout as rt, portal_fix as portals
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import customer_catalog_validate as ui_native
from scripts.deployment.glm_runtime_release import api_sources
from scripts.deployment.fireworks_runtime import remote_build
from scripts.deployment.poc_controls_guards import require_publisher
from scripts.deployment.poc_controls_preflight import collect
from scripts.deployment.project_route_product_access import sha

HOME = rt.HOME / "poc-activation-20261028-packaged"
BACKEND_TESTS = ["test_poc_controls.py", "test_gateway_settings.py", "test_managed_controls.py",
                 "test_admin_subscriptions.py", "test_external_inventory.py", "test_foundry_inventory.py",
                 "test_display_pricing.py"]
GUARD_TESTS = ["test_poc_controls_guards.py", "test_poc_fragment_readback.py"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def exclusive(name, value):
    with (HOME / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)


def manifest():
    api = set(api_sources()) | {rt.ROOT / "gateway/policies/poc-settings-defaults.xml"}
    ui = set(portals.source_files()) | {rt.ROOT / ui_native.DOCKERFILE}
    tests = {rt.ROOT / "tests/unit" / name for name in ["conftest.py", *BACKEND_TESTS, *GUARD_TESTS]}
    tests |= set((rt.ROOT / "gateway/tools").glob("*.py"))
    tests.add(rt.ROOT / "services/usage-ingestion/ingestion-approved.json")
    paths = api | ui | tests
    entries = []
    for path in sorted(paths):
        rt.require(not any(p.is_symlink() for p in (path, *path.parents)) and path.resolve().is_relative_to(rt.ROOT.resolve()), "source_path")
        raw = path.read_bytes()
        rt.require(path.suffix.lower() not in {".key", ".pem", ".pfx", ".env"} and not re.search(
            rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", raw), "source_secret")
        entries.append({"path": path.relative_to(rt.ROOT).as_posix(), "sha256": sha(raw)})
    return {"entries": entries, "source_sha256": sha(json.dumps(entries, sort_keys=True)),
            "api_paths": sorted(p.relative_to(rt.ROOT).as_posix() for p in api),
            "ui_paths": sorted(p.relative_to(rt.ROOT).as_posix() for p in ui)}


def check_sources():
    rt.require(load(HOME / "sources.json") == manifest(), "activation_source_drift")


def context(name):
    check_sources()
    folder = HOME / name / "context"
    for entry in load(HOME / "sources.json")["entries"]:
        target = folder / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write((rt.ROOT / entry["path"]).read_bytes())
    rt.require(not (folder / "services/control-plane/migrations/versions/0003_portal_users.py").exists(), "production_migration_packaging")
    return folder


def prepare():
    rt.require(not HOME.exists(), "existing_activation_reconcile_never_replay")
    proof = collect()
    require_publisher(proof)
    fs.protect(HOME)
    exclusive("permission-preflight.json", proof)
    exclusive("sources.json", manifest())
    exclusive("intent.json", {"at": fs.stamp(), "scope": ["api", "admin", "three_api_flags", "separate_exact_policy"],
        "no_inference": True, "customer_ingestion_unchanged": True, "fragment_creation": False})
    print(json.dumps({"prepared": True, "source_sha256": manifest()["source_sha256"]}), flush=True)


def offline():
    check_sources()
    exclusive("offline-intent.json", {"at": fs.stamp()})
    args = [sys.executable, "-m", "pytest", "-q", *["tests/unit/" + n for n in BACKEND_TESTS + GUARD_TESTS],
            "tests/contract/test_gateway_dev_policy.py", "-k", "not migration",
            "--junitxml=" + str(HOME / "offline-tests.xml")]
    print(rt.run(args), flush=True)
    from scripts.deployment.poc_controls_validate import terraform
    rt.require(terraform() == 0, "terraform_validation_failed")
    print(rt.run([rt.TF, "-chdir=infra/project-route", "fmt", "-check"]), flush=True)
    for project in ("packages/ui", "apps/admin-portal", "apps/customer-portal"):
        rt.run(["C:/Program Files/nodejs/node.exe", "node_modules/typescript/bin/tsc", "--noEmit", "-p", project + "/tsconfig.json"])
    exclusive("offline.json", {"at": fs.stamp(), "passed": True, "source_sha256": manifest()["source_sha256"],
        "unfiltered_workspace_tests_claimed": False, "migration_tests_excluded": True})


def native():
    check_sources()
    rt.require(load(HOME / "offline.json")["passed"], "offline_required")
    exclusive("native-intent.json", {"at": fs.stamp(), "no_push": True})
    ui = context("native-ui")
    ui_result = remote_build(ui, ui_native.DOCKERFILE)
    rt.require(ui_native.no_published_images(rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY,
        "--run-id", ui_result["run_id"], "--subscription", rt.SUB]).get("outputImages")), "ui_no_push_required")
    exclusive("native-ui.json", ui_result)
    api = context("native-api")
    docker = (api / "services/control-plane/Dockerfile").read_text()
    docker += ('\nRUN python -m pip install --user --no-cache-dir pytest==8.4.0\n'
               'COPY tests/unit /app/tests/unit\nCOPY gateway/tools /app/gateway/tools\n'
               'COPY services/usage-ingestion/ingestion-approved.json /app/services/usage-ingestion/ingestion-approved.json\n'
               'COPY gateway/policies/poc-settings-defaults.xml /app/gateway/policies/poc-settings-defaults.xml\n'
               'RUN python -m pytest -q ' + " ".join("tests/unit/" + n for n in BACKEND_TESTS) +
               ' -k "not migration" --junitxml=/tmp/poc-activation-backend.xml\n')
    (api / "PocActivationValidation.Dockerfile").write_text(docker, encoding="utf-8")
    result = remote_build(api, "PocActivationValidation.Dockerfile")
    rt.require(ui_native.no_published_images(rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY,
        "--run-id", result["run_id"], "--subscription", rt.SUB]).get("outputImages")), "api_no_push_required")
    check_sources()
    exclusive("native-api.json", result)
    exclusive("native.json", {"at": fs.stamp(), "ui": ui_result, "api": result,
        "source_sha256": manifest()["source_sha256"], "passed": True, "published_images": False})
    print(json.dumps(load(HOME / "native.json")), flush=True)


def build():
    check_sources()
    rt.require(load(HOME / "native.json")["source_sha256"] == manifest()["source_sha256"], "native_source_binding")
    exclusive("build-intent.json", {"at": fs.stamp(), "components": ["api", "admin"]})
    folder = context("build")
    results = {}
    for kind in ("api", "admin"):
        check_sources()
        tag = "poc-activation-" + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz")
        exclusive(kind + "-build-intent.json", {"at": fs.stamp(), "tag": tag})
        if kind == "api":
            results[kind] = remote_build(folder, "services/control-plane/Dockerfile", kind, tag)
        else:
            args = rt.CLI + ["acr", "build", "--registry", portals.REGISTRY, "--subscription", rt.SUB,
                "--platform", "linux/amd64", "--timeout", "1800", "--file", "apps/admin-portal/Dockerfile",
                "--image", "aiflux-admin:" + tag, "--build-arg", "VITE_AUTH_MODE=local",
                "--build-arg", "VITE_CONTROL_API_URL=/api", "--build-arg",
                "VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1", "."]
            child = subprocess.run(args, cwd=folder, env=rt.ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2100)
            text = ui_native.redact(child.stdout + child.stderr)
            (HOME / "admin-build.log").write_text(text, encoding="utf-8")
            ids = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
            rt.require(child.returncode == 0 and ids, "admin_build_failed_reconcile")
            run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", ids[-1], "--subscription", rt.SUB])
            meta = rt.cli(["acr", "repository", "show", "-n", portals.REGISTRY, "--image", "aiflux-admin:" + tag, "--subscription", rt.SUB])
            rt.require(run["status"] == "Succeeded" and run["outputImages"] == [{"digest": meta["digest"], "registry": portals.HOST,
                "repository": "aiflux-admin", "tag": tag}], "admin_exact_output")
            results[kind] = {"run_id": ids[-1], "tag": tag, "digest": meta["digest"], "image": portals.HOST + "/aiflux-admin@" + meta["digest"],
                "finished_at": run["finishTime"], "log_sha256": sha(text)}
        rt.save(HOME / "build.json", results)
        print(json.dumps({kind: results[kind]}), flush=True)


if __name__ == "__main__":
    globals()[sys.argv[1]]()