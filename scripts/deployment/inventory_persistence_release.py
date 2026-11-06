"""Fresh source-bound two-module API overlay. Deliberately NO APPLY entrypoint."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from scripts.deployment import inventory_recovery_oct29 as old
from scripts.deployment import inventory_recovery_native as retained
from scripts.deployment import backend_connection_restore_oct29 as backend
from scripts.deployment import poc_activation_release as release
from scripts.deployment import portal_fix as portals
from scripts.deployment.catalog_pricing_release import guard
from scripts.deployment.customer_catalog_validate import no_published_images
from scripts.deployment.fireworks_runtime import remote_build

rt, fs = old.rt, old.fs
MODULES = {"foundry_inventory.py", "external_inventory.py"}
PREFIX = "services/control-plane/src/aiflux/"
CLI = ["C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe", "-X", "utf8", "-IBm", "azure.cli"]
ADDRESS = 'azurerm_linux_web_app.main["api"]'
DOCKER = "PersistentInventory.Dockerfile"


def now():
    return datetime.now(UTC).isoformat()


def save(folder, name, value):
    backend.save(folder, name, value)


def transport():
    old.install_read_transport()
    rt.CLI = CLI


def source_entries(root):
    return [{"path": p.relative_to(root).as_posix(), "sha256": old.sha(p.read_bytes())}
            for p in sorted(root.rglob("*")) if p.is_file()]


def dockerfile():
    # Both locations are known from the actual deployed source/install attestation.
    return "FROM " + old.IMAGE + "\n" + "".join(
        "COPY --chown=10001:10001 modules/" + name + " " + dest + name + "\n"
        for name in sorted(MODULES) for dest in ("/app/" + PREFIX, "/usr/local/lib/python3.11/site-packages/aiflux/"))


def package_guard(manifest, entries, docker):
    rt.require(manifest["base_image"] == old.IMAGE and set(manifest["changed_modules"]) == MODULES,
               "exact_approved_runtime_modules")
    rt.require(docker == dockerfile() and {e["path"] for e in entries} == {DOCKER, *("modules/" + n for n in MODULES)},
               "no_auto_config_settings_catalog_othercode")
    rt.require(len(entries) == 3 and entries == manifest["entries"], "immutable_package_membership_hashes")


def package(folder):
    manifest = old.load(folder / "package.json")
    root = folder / "context"
    package_guard(manifest, source_entries(root), (root / DOCKER).read_text())
    for name in MODULES:
        rt.require(not (rt.ROOT / PREFIX / name).is_symlink()
                   and old.sha((rt.ROOT / PREFIX / name).read_bytes()) == manifest["changed_modules"][name], "workspace_runtime_source_changed")
    return manifest


def unchanged(folder, label):
    current = release.snapshot()
    save(folder, label + ".json", current)
    rt.require(current == old.load(folder / "baseline.json"), "all13_protected_components_drift:" + label)
    return current


def fresh(folder):
    value = old.load(folder / "metadata.json")
    rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(value["observed_at_utc"]) < timedelta(hours=2), "release_proof_freshness_required")
    return value


def prepare(folder):
    rt.require(not folder.exists(), "existing_release_reconcile_only")
    fs.protect(folder)
    # Persist marker before any remote operation; fresh workflow never calls old entrypoints.
    workers = backend.workers()
    save(folder, "workers-before.json", workers)
    rt.require(not any(w["mutation_worker"] for w in workers), "competing_worker_reconcile_required")
    save(folder, "historical-intents.json", backend.markers())
    source, built = old.retained_sources()
    save(folder, "retained-source.json", source)
    rt.require(all((rt.ROOT / PREFIX / n).read_bytes() != (old.BASE / PREFIX / n).read_bytes() for n in MODULES), "actual_inventory_module_fix_required")
    transport()
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    baseline = release.snapshot()
    rt.require(len(baseline) == 13 and all(baseline["runtime"]["sites"][k]["image"].endswith("@sha256:" + v) for k, v in old.PINS.items()), "exact_all13_current_baseline_pins")
    save(folder, "baseline.json", baseline)
    old_foundry = old.load(old.BASE / old.FOUNDRY)
    live = {}
    for kind, suffix in (("account", ""), ("project", "/projects/poc-ids-token-ex-foundry-project"),
                         ("connections", "/projects/poc-ids-token-ex-foundry-project/connections"), ("deployments", "/deployments")):
        live[kind] = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + old_foundry["account_resource_id"] + suffix + "?api-version=2025-06-01"])
    at = now()
    # Reuse pure full joined-contract verifier only. Discard its restamped result.
    old.renew_foundry(old_foundry, live, at)
    run = old.reads.ReadOnlyProductRun()
    policy = run.policy()
    backends = run.arm("/backends")
    rt.require(not backends.get("nextLink"), "complete_backends")
    matching = [b for b in backends["value"] if "glm" in b["name"].lower()]
    rt.require(len(matching) == 1, "exact_external_backend")
    reference = old.metadata(run.arm("/namedValues/" + old.NAME))
    old.renew_external(old.load(old.BASE / old.EXTERNAL), policy, matching[0], reference, at)
    save(folder, "metadata.json", {"observed_at_utc": at, "foundry": live, "external_backend": matching[0],
        "reference_metadata": reference, "policy_sha256": old.sha(policy), "timestamps_restamped": False,
        "credential_health_retested": False, "inference_requests": 0})
    root = folder / "context"
    (root / "modules").mkdir(parents=True)
    for name in sorted(MODULES):
        shutil.copyfile(rt.ROOT / PREFIX / name, root / "modules" / name)
    (root / DOCKER).write_text(dockerfile(), encoding="utf-8")
    manifest = {"base_image": old.IMAGE, "changed_modules": {n: old.sha((root / "modules" / n).read_bytes()) for n in sorted(MODULES)},
                "entries": source_entries(root), "retained_source_sha256": source["sha256"], "inventory_json_unchanged": True}
    save(folder, "package.json", manifest)
    package(folder)
    unchanged(folder, "after-prepare")
    save(folder, "prepared.json", {"at_utc": now(), "source_sha256": fs.sha(manifest), "status": "prepared_no_apply_authorized"})
    print(json.dumps({"stage": "prepared", "evidence": folder.relative_to(rt.ROOT).as_posix(), "source_sha256": fs.sha(manifest)}), flush=True)


def native(folder, attempt="native"):
    manifest = package(folder)
    fresh(folder)
    transport()
    unchanged(folder, "before-" + attempt)
    save(folder, attempt + "-intent.json", {"at_utc": now(), "source_sha256": fs.sha(manifest), "no_push": True})
    root = folder / attempt / "context"
    shutil.copytree(folder / "context", root)
    source = old.load(folder / "retained-source.json")
    for entry in source["entries"]:
        name = entry["path"]
        if name.startswith(("tests/unit/", "gateway/tools/")) or name in {"gateway/policies/poc-settings-defaults.xml", "services/usage-ingestion/ingestion-approved.json"}:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old.BASE / name, target)
    # Only the targeted changed assertions; every other legacy regression stays original.
    for name in ("test_foundry_inventory.py", "test_external_inventory.py", "test_external_metadata_renewal.py", "test_inventory_persistent_acceptance.py"):
        shutil.copyfile(rt.ROOT / "tests/unit" / name, root / "tests/unit" / name)
    shutil.copyfile(rt.ROOT / "scripts/deployment/inventory_persistence_attestation.py", root / "attest.py")
    save(root, "attestation.json", {"retained": source, "changed": manifest["changed_modules"]})
    tests = [*retained.TESTS, "test_external_metadata_renewal.py", "test_inventory_persistent_acceptance.py"]
    docker = "FROM " + old.IMAGE + "\nCOPY attest.py attestation.json /tmp/\nRUN python /tmp/attest.py before\n"
    docker += dockerfile().split("\n", 1)[1]
    docker += ("RUN python /tmp/attest.py after\nRUN python -m pip install --user --no-cache-dir pytest==8.4.0\n"
        "COPY tests/unit /app/tests/unit\nCOPY gateway/tools /app/gateway/tools\n"
        "COPY services/usage-ingestion/ingestion-approved.json /app/services/usage-ingestion/ingestion-approved.json\n"
        "COPY gateway/policies/poc-settings-defaults.xml /app/gateway/policies/poc-settings-defaults.xml\n"
        "RUN python -m pytest -q " + " ".join("tests/unit/" + n for n in tests) + ' -k "not migration"\n')
    (root / "Native.Dockerfile").write_text(docker, encoding="utf-8")
    save(folder, attempt + "-inputs.json", source_entries(root))
    result = remote_build(root, "Native.Dockerfile")
    log = (root.parent / "native-validation-build.log").read_text(encoding="utf-8")
    counts = re.findall(r"(\d+) passed", log)
    rt.require(counts and int(counts[-1]) >= 309 and '"persistence_attestation": "after"' in log, "actual_native_proof_required")
    run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", result["run_id"], "--subscription", rt.SUB])
    rt.require(no_published_images(run.get("outputImages")), "native_no_push_required")
    rt.require(source_entries(root) == old.load(folder / (attempt + "-inputs.json")), "native_input_drift")
    package(folder)
    unchanged(folder, "after-" + attempt)
    save(folder, "native.json", {**result, "tests_passed": int(counts[-1]), "source_sha256": fs.sha(manifest), "all13_100days": True})
    print(json.dumps({"stage": "native_passed", "run_id": result["run_id"], "tests_passed": int(counts[-1]), "no_push": True}), flush=True)


def native02(folder):
    transport()
    run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", "cm31", "--subscription", rt.SUB])
    rt.require(run["status"] == "Failed" and run.get("finishTime") and no_published_images(run.get("outputImages")), "original_native_not_terminal_failed")
    log = (folder / "native/native-validation-build.log").read_text(encoding="utf-8")
    rt.require("path.relative_to" in log and "Step 3/14" in log and "cm31" in log, "exact_harness_failure_required")
    save(folder, "native01-reconciled.json", {"run_id": "cm31", "status": run["status"], "finished_at": run["finishTime"],
        "no_published_images": True, "log_sha256": old.sha(log), "cause": "attestation_relative_catalog_path_not_runtime"})
    native(folder, "native02")


def build(folder):
    manifest = package(folder)
    fresh(folder)
    rt.require(old.load(folder / "native.json")["source_sha256"] == fs.sha(manifest), "native_source_binding")
    transport()
    unchanged(folder, "before-build")
    save(folder, "build-intent.json", {"at_utc": now(), "source_sha256": fs.sha(manifest), "one_api_image": True})
    result = remote_build(folder / "context", DOCKER, "api", folder.name)
    package(folder)
    unchanged(folder, "after-build")
    save(folder, "build.json", {**result, "source_sha256": fs.sha(manifest)})
    print(json.dumps({"stage": "built_not_deployed", **result, "source_sha256": fs.sha(manifest)}), flush=True)


def strict(plan, image, baseline):
    guard(plan, image)
    rows = [r for r in plan["resource_changes"] if r["address"] == ADDRESS]
    rt.require(len(rows) == 1, "exact_api_resource")
    stack = rows[0]["change"]["before"]["site_config"][0]["application_stack"][0]
    rt.require("DOCKER|" + portals.HOST + "/" + stack["docker_image_name"] == baseline["runtime"]["sites"]["api"]["image"], "exact_live_predecessor")
    rt.require(plan.get("checks") and all(c["status"] == "pass" for c in plan["checks"]), "every_plan_check_passed")


def plan(folder):
    manifest = package(folder)
    fresh(folder)
    transport()
    before = unchanged(folder, "before-plan")
    built = old.load(folder / "build.json")
    rt.require(built["source_sha256"] == fs.sha(manifest), "build_source_binding")
    remote = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", built["run_id"], "--subscription", rt.SUB])
    rt.require(remote["status"] == "Succeeded" and remote["finishTime"] == built["finished_at"], "actual_built_image")
    root = folder / "plan/infra/terraform"
    rt.require(not root.exists(), "existing_plan_reconcile_only")
    root.mkdir(parents=True)
    original = rt.ROOT / "infra/terraform"
    for p in original.iterdir():
        if p.is_file() and (p.name.endswith((".tf", ".tf.json")) or p.name == ".terraform.lock.hcl"):
            rt.require(not p.is_symlink(), "infra_symlink")
            shutil.copyfile(p, root / p.name)
    for path in ("infra/models", "gateway/catalog", "gateway/policies"):
        shutil.copytree(rt.ROOT / path, folder / "plan" / path, ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tfplan", "__pycache__"))
    for p in (rt.ROOT / "gateway").glob("*.json"):
        shutil.copyfile(p, folder / "plan/gateway" / p.name)
    variables = portals.runtime_variables({"portals": ["admin", "customer"], "results": {
        k: {"image": before["runtime"]["sites"][k]["image"].removeprefix("DOCKER|")} for k in ("admin", "customer")}}, before["runtime"])
    variables["apps"]["api"]["image"] = built["image"].split("/", 1)[1]
    variables.update(ingestion_container_image=before["runtime"]["sites"]["ingestion"]["image"].removeprefix("DOCKER|"),
        ingestion_enabled=True, ingestion_timer_enabled=True, ingestion_start_at=before["cutoff"], ingestion_catalog_accepted=True)
    save(folder, "inputs.tfvars.json", variables)
    settings = fs.current_settings()
    rt.require({k: fs.sha(v) for k, v in settings.items()} == before["settings_hashes"], "all_settings_preserved")
    save(root, "poc_preserved.tf.json", {"locals": {"poc_release_settings": fs.literal(fs.preserved_web_settings(settings))}})
    save(root, "zzzz_poc_override.tf.json", {"resource": {"azurerm_linux_web_app": {"main": {"app_settings": "${local.poc_release_settings[each.key]}"}}}})
    args = ["-var-file=" + str(p) for p in (rt.HOME / "rebuild-platform.tfvars.json", folder / "inputs.tfvars.json", rt.HOME / "jwt-runtime.tfvars.json")]
    save(folder, "plan-intent.json", {"at_utc": now(), "source_sha256": fs.sha(manifest), "apply_authorized": False})
    fs.terraform(root, "init", "-input=false", "-lockfile=readonly", "-no-color", "-backend-config=" + str(original / "backend.hcl"))
    rt.require(fs.terraform(root, "workspace", "show").strip() == "default", "default_workspace")
    fs.terraform(root, "fmt", "-check")
    fs.terraform(root, "validate", "-no-color")
    target = folder / "api-only.tfplan"
    fs.terraform(root, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *args, "-target=" + ADDRESS, "-out=" + str(target))
    data = release.parsed(root, target)
    companion = folder / "validation-only-NEVER-APPLY.tfplan"
    if any(c["status"] != "pass" for c in data.get("checks", [])):
        save(folder, "companion-intent.json", {"at_utc": now(), "target_sha256": old.sha(target.read_bytes()), "never_apply": True})
        fs.terraform(root, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *args, "-out=" + str(companion))
        data = release.resolve(data, release.parsed(root, companion), {ADDRESS})
    strict(data, built["image"], before)
    unchanged(folder, "after-plan")
    artifacts = [target, folder / "inputs.tfvars.json", *root.glob("*.tf"), *root.glob("*.tf.json"), root / ".terraform.lock.hcl"]
    if companion.exists():
        artifacts.append(companion)
    review = {"at_utc": now(), "status": "ready_for_parent_independent_validation_NOT_APPLIED", "image": built["image"],
        "plan_sha256": old.sha(target.read_bytes()), "source_sha256": fs.sha(manifest),
        "artifacts": {p.relative_to(folder).as_posix(): old.sha(p.read_bytes()) for p in artifacts},
        "baseline_sha256": fs.sha(before), "all13_protected_components_unchanged": True, "apply_authorized": False}
    save(folder, "review.json", review)
    print(json.dumps({k: review[k] for k in ("status", "image", "plan_sha256", "source_sha256", "baseline_sha256")}), flush=True)


if __name__ == "__main__":
    folder = Path(sys.argv[2]).resolve()
    rt.require(folder.parent == rt.HOME and folder.name.startswith("inventory-persistence-20261029-"), "fresh_exclusive_scope")
    try:
        {"prepare": prepare, "native": native, "native02": native02, "build": build, "plan": plan}[sys.argv[1]](folder)
    except Exception as error:
        result = {"stage": sys.argv[1], "status": "blocked_reconcile_before_retry", "at_utc": now(),
            "error_type": type(error).__name__, "safe_error": str(error) if isinstance(error, RuntimeError) else "details_suppressed",
            "apply_authorized": False}
        if folder.exists():
            save(folder, sys.argv[1] + "-blocked.json", result)
        print(json.dumps(result), flush=True)
        raise SystemExit(2)