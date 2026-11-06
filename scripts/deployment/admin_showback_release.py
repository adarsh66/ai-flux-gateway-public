"""Exclusive Showback API/admin image release. No policy/settings/DDL write path."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from scripts.deployment import poc_activation_release as r
from scripts.deployment import customer_catalog_validate as ui
from scripts.deployment.glm_runtime_release import api_sources
from scripts.deployment.fireworks_runtime import remote_build

HOME = r.rt.HOME / "admin-showback-release-20261028"
ROOT = HOME / "infra/terraform"
PLAN = HOME / "api-admin-only.tfplan"
FULL = HOME / "validation-only-NEVER-APPLY.tfplan"
UI = r.rt.HOME / "admin-showback-native-20261028T105813526933Z"
UI_HASH = "d2c3cf5e830c52e63b93b8ee3b0b2b9d2e33b12ea79f3a9ab18adced8f283525"
KINDS = ("api", "admin")
ADDRESSES = {f'azurerm_linux_web_app.main["{k}"]': k for k in KINDS}
TESTS = ["test_usage_rankings.py", "test_usage_filters.py", "test_usage_series.py", "test_model_tokens.py",
         "test_control_plane.py", "test_admin_subscriptions.py", "test_display_pricing.py", "test_finops_ingestion.py",
         "test_poc_publisher_reliability.py", "test_gateway_settings.py", "test_poc_controls.py",
         "test_managed_controls.py", "test_external_inventory.py", "test_foundry_inventory.py"]
PINS = {"api": "a855d6294bcd597d7a898c4f14bf75620f934c8a21ad1d369e1eda70f54ef734",
        "admin": "adae6a6375291581f6547e90873f4075ba60731e6c213db603aad167b89dbb7f",
        "customer": "d9d8b4b21283801feb2aff3ad12707155f5c38c59b6fc09091a4c22c35e71ea3",
        "ingestion": "fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90"}
load = r.prep.load


def exclusive(name, value):
    r.exclusive(HOME, name, value)


def checkpoint(stage, **values):
    value = {"at": r.fs.stamp(), "stage": stage, "release": HOME.relative_to(r.rt.ROOT).as_posix(), **values}
    r.rt.save(HOME / "current-result.json", value)
    print(json.dumps(value), flush=True)


def account():
    a = r.rt.cli(["account", "show"])
    r.rt.require(a["id"] == r.rt.SUB and a["tenantId"] == r.rt.TENANT and a["state"] == "Enabled"
                 and a["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_scope")
    r.rt.require(Path(r.rt.CA).is_file() and r.rt.ENV.get("AZURE_CLI_DISABLE_CONNECTION_VERIFICATION", "").lower()
                 not in {"true", "1", "yes"}, "strict_tls_required")


def ui_proof(remote=False):
    manifest, proof = load(UI / "sources.json"), load(UI / "result.json")
    paths = {p.relative_to(r.rt.ROOT).as_posix() for p in r.portals.source_files()} | {ui.DOCKERFILE}
    r.rt.require({e["path"] for e in manifest["entries"]} == paths and manifest["source_sha256"] == UI_HASH
                 and proof["passed"] and proof["run_id"] == "cm2t" and proof["source_sha256"] == UI_HASH,
                 "exact_retained_ui_proof")
    r.rt.require(all(r.sha((base / e["path"]).read_bytes()) == e["sha256"]
        for e in manifest["entries"] for base in (r.rt.ROOT, UI / "context")), "current_ui_manifest_drift")
    if remote:
        run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", "cm2t", "--subscription", r.rt.SUB])
        r.rt.require(run["status"] == "Succeeded" and run["finishTime"] == proof["finishTime"]
                     and ui.no_published_images(run.get("outputImages")), "retained_ui_remote_proof")
    return manifest


def manifest():
    paths = set(api_sources()) | set(r.portals.source_files())
    paths |= {r.rt.ROOT / "tests/unit" / n for n in ["conftest.py", *TESTS]}
    paths |= set((r.rt.ROOT / "gateway/tools").glob("*.py"))
    paths |= {r.rt.ROOT / "gateway/policies/poc-settings-defaults.xml",
              r.rt.ROOT / "services/usage-ingestion/ingestion-approved.json"}
    entries = []
    for path in sorted(paths):
        r.rt.require(path.resolve().is_relative_to(r.rt.ROOT.resolve()) and not any(p.is_symlink() for p in (path, *path.parents))
                     and path.suffix.lower() not in {".key", ".pem", ".pfx", ".env"}, "curated_source_path")
        raw = path.read_bytes()
        r.rt.require(not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", raw), "source_secret")
        entries.append({"path": path.relative_to(r.rt.ROOT).as_posix(), "sha256": r.sha(raw)})
    return {"entries": entries, "sha256": r.fs.sha(entries)}


def tooling():
    paths = set((r.rt.ROOT / "scripts/deployment").glob("*.py"))
    paths |= {r.rt.ROOT / "tests/unit/test_admin_showback_release.py"}
    paths |= set((r.rt.ROOT / "infra/terraform").glob("*.tf")) | set((r.rt.ROOT / "infra/terraform").glob("*.tf.json"))
    paths |= {r.rt.ROOT / "infra/terraform/.terraform.lock.hcl", r.rt.ROOT / "infra/terraform/backend.hcl",
              r.rt.HOME / "rebuild-platform.tfvars.json", r.rt.HOME / "jwt-runtime.tfvars.json"}
    return {str(p): r.sha(p.read_bytes()) for p in sorted(paths)}


def sources():
    value = manifest()
    r.rt.require(value == load(HOME / "sources.json") and tooling() == load(HOME / "tooling.json"), "source_or_tooling_drift")
    ui_proof()
    return value


def context(name):
    value = sources()
    folder = HOME / name / "context"
    for entry in value["entries"]:
        dest = folder / entry["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as handle:
            handle.write((r.rt.ROOT / entry["path"]).read_bytes())
    r.rt.require(not (folder / "services/control-plane/migrations/versions/0003_portal_users.py").exists(), "production_package_excludes_known_migration")
    return folder


def junit(path, minimum):
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    counts = {k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "errors", "failures", "skipped")}
    r.rt.require(counts["tests"] >= minimum and all(counts[k] == 0 for k in ("errors", "failures", "skipped")), "actual_clean_junit")
    return {**counts, "sha256": r.sha(path.read_bytes())}


def prepare():
    r.rt.require(not HOME.exists(), "existing_showback_release_reconcile_only")
    account()
    ui_proof(remote=True)
    previous = load(r.rt.HOME / "poc-publisher-reliability-20261028/api-sources.json")
    prior = {e["path"]: e["sha256"] for e in previous["entries"]}
    delta = [p.relative_to(r.rt.ROOT).as_posix() for p in api_sources()
             if prior.get(p.relative_to(r.rt.ROOT).as_posix()) != r.sha(p.read_bytes())]
    r.rt.require(set(delta) == {"services/control-plane/src/aiflux/" + p for p in ("app.py", "finops.py", "schemas.py")},
                 "unexpected_api_bundle_delta:" + ",".join(delta))
    before = r.snapshot()
    for kind, pin in PINS.items():
        r.rt.require(before["runtime"]["sites"][kind]["image"] == "DOCKER|" + r.portals.HOST + "/aiflux-" + kind + "@sha256:" + pin,
                     "current_predecessor:" + kind)
    settings = r.fs.current_settings()
    r.rt.require({k: r.fs.sha(v) for k, v in settings.items()} == before["settings_hashes"], "complete_settings_baseline")
    r.rt.require(all(settings["api"].get(k) == v for k, v in r.FLAGS.items()), "preserve_existing_poc_flags")
    r.fs.protect(HOME)
    exclusive("baseline.json", before)
    exclusive("sources.json", manifest())
    exclusive("tooling.json", tooling())
    exclusive("scope-review.json", {"at": r.fs.stamp(), "api_delta_vs_live_predecessor": delta,
        "terraform_fireworks_compatibility_local_only": True, "publisher_runtime_sources_unchanged": True,
        "ui_validation_run": "cm2t", "ui_validation_sha256": UI_HASH,
        "backend_local": junit(r.rt.HOME / "admin-showback-backend.xml", 138), "no_ddl_or_indexes": True})
    exclusive("release-intent.json", {"at": r.fs.stamp(), "scope": list(KINDS), "max_applies": 1,
        "settings_changes": 0, "policy_changes": 0, "inference_requests": 0})
    checkpoint("prepared", source_sha256=manifest()["sha256"], api_source_delta=delta)


def native():
    value = sources()
    exclusive("native-intent.json", {"at": r.fs.stamp(), "source_sha256": value["sha256"], "no_push": True})
    folder = context("native-api")
    docker = (folder / "services/control-plane/Dockerfile").read_text(encoding="utf-8")
    docker += ('\nRUN python -m pip install --user --no-cache-dir pytest==8.4.0\n'
               'COPY tests/unit /app/tests/unit\nCOPY gateway/tools /app/gateway/tools\n'
               'COPY services/usage-ingestion/ingestion-approved.json /app/services/usage-ingestion/ingestion-approved.json\n'
               'COPY gateway/policies/poc-settings-defaults.xml /app/gateway/policies/poc-settings-defaults.xml\n'
               'RUN python -m pytest -q ' + ' '.join('tests/unit/' + n for n in TESTS) + ' -k "not migration"\n')
    # Generated build input only; never edits a workspace source file.
    with (folder / "ShowbackNative.Dockerfile").open("x", encoding="utf-8") as handle:
        handle.write(docker)
    result = remote_build(folder, "ShowbackNative.Dockerfile")
    run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", result["run_id"], "--subscription", r.rt.SUB])
    r.rt.require(ui.no_published_images(run.get("outputImages")), "native_no_push")
    log = (folder.parent / "native-validation-build.log").read_text(encoding="utf-8")
    counts = re.findall(r"(\d+) passed", log)
    r.rt.require(counts and int(counts[-1]) >= 138 and "test_usage_rankings.py" in log, "native_backend_test_proof")
    sources()
    exclusive("native.json", {**result, "source_sha256": value["sha256"], "passed": True, "tests_passed": int(counts[-1]),
        "migration_tests_excluded": True, "live_postgres_load_test": False})
    checkpoint("native_api_validated", **load(HOME / "native.json"))


def build():
    value = sources()
    proof = load(HOME / "native.json")
    r.rt.require(proof["passed"] and proof["source_sha256"] == value["sha256"], "native_required")
    r.rt.require(r.snapshot() == load(HOME / "baseline.json"), "prebuild_complete_baseline_drift")
    for kind in KINDS:
        tag = "showback-" + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz") + "-" + value["sha256"][:12]
        exclusive(kind + "-build-intent.json", {"at": r.fs.stamp(), "tag": tag, "source_sha256": value["sha256"]})
        folder = context("build-" + kind)
        if kind == "api":
            result = remote_build(folder, "services/control-plane/Dockerfile", kind, tag)
        else:
            args = r.rt.CLI + ["acr", "build", "--registry", r.portals.REGISTRY, "--subscription", r.rt.SUB,
                "--platform", "linux/amd64", "--timeout", "1800", "--file", "apps/admin-portal/Dockerfile",
                "--image", "aiflux-admin:" + tag, "--build-arg", "VITE_AUTH_MODE=local", "--build-arg", "VITE_CONTROL_API_URL=/api",
                "--build-arg", "VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1", "."]
            child = subprocess.run(args, cwd=folder, env=r.rt.ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2100)
            text = ui.redact(child.stdout + child.stderr)
            (folder.parent / "admin-build.log").write_text(text, encoding="utf-8")
            ids = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
            r.rt.require(child.returncode == 0 and ids, "admin_build_failed_reconcile_no_replay")
            run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", ids[-1], "--subscription", r.rt.SUB])
            outputs = run.get("outputImages")
            r.rt.require(run["status"] == "Succeeded" and len(outputs or []) == 1, "admin_output")
            digest = outputs[0]["digest"]
            r.rt.require(outputs == [{"digest": digest, "registry": r.portals.HOST, "repository": "aiflux-admin", "tag": tag}], "admin_exact_output")
            result = {"run_id": ids[-1], "finished_at": run["finishTime"], "tag": tag, "digest": digest,
                      "image": r.portals.HOST + "/aiflux-admin@" + digest, "log_sha256": r.sha(text)}
        sources()
        exclusive(kind + "-build.json", {**result, "source_sha256": value["sha256"]})
        checkpoint(kind + "_image_built", **result)


def built(remote=True):
    value = sources()
    images = {}
    for kind in KINDS:
        item = load(HOME / (kind + "-build.json"))
        r.rt.require(item["source_sha256"] == value["sha256"], "build_source_binding")
        if remote:
            run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", item["run_id"], "--subscription", r.rt.SUB])
            meta = r.rt.cli(["acr", "manifest", "show-metadata", "--registry", r.portals.REGISTRY,
                             "--name", "aiflux-" + kind + ":" + item["tag"], "--subscription", r.rt.SUB])
            r.rt.require(run["status"] == "Succeeded" and run["finishTime"] == item["finished_at"] and meta["digest"] == item["digest"]
                and run["outputImages"] == [{"digest": item["digest"], "registry": r.portals.HOST, "repository": "aiflux-" + kind, "tag": item["tag"]}], "immutable_build_binding")
        images[kind] = item["image"]
    return images


def guard(plan, images, before):
    r.rt.require(set(images) == set(KINDS) and plan.get("applyable") is True and not plan.get("errored")
                 and not plan.get("deferred_changes"), "resolved_exact_two_images")
    seen = set()
    for item in plan.get("resource_changes", []):
        c = item["change"]
        if c["actions"] == ["no-op"] or (c["actions"] == ["read"] and item.get("mode") == "data"):
            continue
        address = item["address"]
        r.rt.require(item.get("mode") == "managed" and address in ADDRESSES and address not in seen and c["actions"] == ["update"], "exact_api_admin_only")
        seen.add(address)
        old, new = deepcopy(c["before"]), deepcopy(c["after"])
        unknown = c.get("after_unknown") or {}
        r.rt.require(not any(r.any_unknown(v) for k, v in unknown.items() if k not in r.fs.COMPUTED), "unknown_writable")
        for key in r.fs.COMPUTED:
            if r.any_unknown(unknown.get(key)):
                new[key] = old.get(key)
        kind = ADDRESSES[address]
        image = images[kind]
        r.rt.require(re.fullmatch(re.escape(r.portals.HOST + "/aiflux-" + kind + "@sha256:") + "[a-f0-9]{64}", image), "immutable_pin")
        r.rt.require(len(old["site_config"]) == len(new["site_config"]) == 1, "site_shape")
        a, b = old["site_config"][0]["application_stack"], new["site_config"][0]["application_stack"]
        r.rt.require(len(a) == len(b) == 1 and "DOCKER|" + r.portals.HOST + "/" + a[0]["docker_image_name"]
            == before["runtime"]["sites"][kind]["image"] and b[0]["docker_image_name"] == image.split("/", 1)[1]
            and b[0]["docker_registry_url"] == "https://" + r.portals.HOST, "current_predecessor_exact_target")
        b[0]["docker_image_name"] = a[0]["docker_image_name"]
        r.rt.require(old == new and c["before"] != c["after"], "nonimage_change_rejected")
    r.rt.require(seen == set(ADDRESSES) and plan.get("checks") and all(c["status"] == "pass" for c in plan["checks"]), "two_updates_all_checks_required")


def data():
    target = r.parsed(ROOT, PLAN)
    if FULL.exists():
        target = r.resolve(target, r.parsed(ROOT, FULL), set(ADDRESSES))
    return target


def plan():
    account()
    images = built()
    before = r.snapshot()
    r.rt.require(before == load(HOME / "baseline.json"), "fresh_complete_baseline_drift")
    r.rt.require(not ROOT.exists(), "existing_plan_context_reconcile_only")
    ROOT.mkdir(parents=True)
    for p in (r.rt.ROOT / "infra/terraform").iterdir():
        if p.is_file() and (p.name.endswith((".tf", ".tf.json")) or p.name == ".terraform.lock.hcl"):
            shutil.copyfile(p, ROOT / p.name)
    for path in ("infra/models", "gateway/catalog", "gateway/policies"):
        shutil.copytree(r.rt.ROOT / path, HOME / path, ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tfplan", "__pycache__"))
    for p in (r.rt.ROOT / "gateway").glob("*.json"):
        shutil.copyfile(p, HOME / "gateway" / p.name)
    variables = r.runtime_variables(images, before["runtime"])
    variables.update(ingestion_container_image=before["runtime"]["sites"]["ingestion"]["image"].removeprefix("DOCKER|"),
        ingestion_enabled=True, ingestion_timer_enabled=True, ingestion_start_at=before["cutoff"], ingestion_catalog_accepted=True)
    r.rt.save(HOME / "inputs.tfvars.json", variables)
    settings = r.fs.current_settings()
    r.rt.require({k: r.fs.sha(v) for k, v in settings.items()} == before["settings_hashes"], "complete_settings_preserved")
    r.rt.save(ROOT / "showback_preserved.tf.json", {"locals": {"showback_settings": r.fs.literal(r.fs.preserved_web_settings(settings))}})
    r.rt.save(ROOT / "zzzz_showback_override.tf.json", {"resource": {"azurerm_linux_web_app": {"main": {"app_settings": "${local.showback_settings[each.key]}"}}}})
    args = ["-var-file=" + str(p) for p in (r.rt.HOME / "rebuild-platform.tfvars.json", HOME / "inputs.tfvars.json", r.rt.HOME / "jwt-runtime.tfvars.json")]
    r.fs.terraform(ROOT, "init", "-input=false", "-lockfile=readonly", "-no-color", "-backend-config=" + str(r.rt.ROOT / "infra/terraform/backend.hcl"))
    r.rt.require(r.fs.terraform(ROOT, "workspace", "show").strip() == "default", "default_workspace")
    r.fs.terraform(ROOT, "validate", "-no-color")
    exclusive("plan-intent.json", {"at": r.fs.stamp(), "targets": list(ADDRESSES), "max_applies": 1})
    r.fs.terraform(ROOT, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *args,
                   *["-target=" + a for a in ADDRESSES], "-out=" + str(PLAN))
    target = r.parsed(ROOT, PLAN)
    if any(c["status"] != "pass" for c in target.get("checks", [])):
        exclusive("companion-intent.json", {"at": r.fs.stamp(), "target_sha256": r.sha(PLAN.read_bytes()), "never_apply": True})
        r.fs.terraform(ROOT, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *args, "-out=" + str(FULL))
    guard(data(), images, before)
    artifacts = [PLAN, HOME / "inputs.tfvars.json", *ROOT.glob("*.tf"), *ROOT.glob("*.tf.json"), ROOT / ".terraform.lock.hcl"]
    if FULL.exists():
        artifacts.append(FULL)
    review = {"at": r.fs.stamp(), "plan_sha256": r.sha(PLAN.read_bytes()), "images": images,
        "tooling": tooling(), "source_sha256": sources()["sha256"], "baseline": before,
        "artifacts": {str(p): r.sha(p.read_bytes()) for p in artifacts}, "companion_never_apply": True,
        "companion_unapproved_writes": [{"address": c["address"], "actions": c["change"]["actions"]}
            for c in (r.parsed(ROOT, FULL).get("resource_changes", []) if FULL.exists() else [])
            if c["change"]["actions"] not in (["no-op"], ["read"]) and c["address"] not in ADDRESSES]}
    exclusive("review.json", review)
    checkpoint("plan_guarded_not_validated", plan_sha256=review["plan_sha256"], images=images,
               companion_unapproved_writes=review["companion_unapproved_writes"])


def check(live=True):
    review = load(HOME / "review.json")
    r.rt.require(review["source_sha256"] == sources()["sha256"] and review["tooling"] == tooling()
        and all(r.sha(Path(p).read_bytes()) == h for p, h in review["artifacts"].items())
        and review["plan_sha256"] == r.sha(PLAN.read_bytes()) and review["images"] == built(remote=live), "exact_source_input_plan_binding")
    guard(data(), review["images"], review["baseline"])
    if live:
        account()
        r.rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at"]) < timedelta(hours=2), "stale_plan")
        r.rt.require(r.snapshot() == review["baseline"], "complete_protected_baseline_drift")
    return review


def apply():
    r.rt.require(not (HOME / "apply-intent.json").exists(), "attempted_apply_reconcile_never_retry")
    review = check()
    proof = load(HOME / "validation.json")
    doc = (r.rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    r.rt.require(proof["checks_passed"] and proof["plan_sha256"] == review["plan_sha256"] and proof["tooling"] == tooling()
        and proof["at"] in doc and review["plan_sha256"] in doc and "Admin Showback release status: Validated." in doc
        and load(r.rt.ROOT / ".azure/validate-status.json")["completedStep"] == "UpdateStatus", "independent_workflow_section7_required")
    exclusive("apply-intent.json", {"at": r.fs.stamp(), "plan_sha256": review["plan_sha256"]})
    checkpoint("apply_intent_recorded_never_retry", plan_sha256=review["plan_sha256"])
    # Provider may update in parallel. New UI has explicit optional-endpoint errors;
    # no auth/access gate depends on rankings during this bounded transition.
    output = r.fs.terraform(ROOT, "apply", "-input=false", "-no-color", "-parallelism=1", str(PLAN))
    exclusive("applied.json", {"at": r.fs.stamp(), "plan_sha256": review["plan_sha256"],
        "summary": re.findall(r"Apply complete! Resources: [^\r\n]+", output)})
    checkpoint("applied_once_readback_pending", **load(HOME / "applied.json"))


def verify():
    review = check(live=False)
    r.rt.require(load(HOME / "applied.json")["plan_sha256"] == review["plan_sha256"], "matching_apply")
    current = r.snapshot()
    expected = deepcopy(review["baseline"])
    for kind, image in review["images"].items():
        expected["runtime"]["sites"][kind]["image"] = "DOCKER|" + image
    passed = current == expected
    exclusive("verified.json", {"at": r.fs.stamp(), "passed": passed, "baseline": current,
        "plan_sha256": review["plan_sha256"], "all_four_settings_hashes_equal": current["settings_hashes"] == expected["settings_hashes"]})
    checkpoint("protected_readback_passed" if passed else "protected_readback_failed_no_reapply", passed=passed, images=review["images"])
    r.rt.require(passed, "complete_protected_readback_failed_no_reapply")


if __name__ == "__main__":
    try:
        r.rt.require(len(sys.argv) == 2 and sys.argv[1] in ("prepare", "native", "build", "plan", "apply", "verify"), "action_required")
        globals()[sys.argv[1]]()
    except Exception as error:
        reason = str(error) if isinstance(error, RuntimeError) else "sensitive_detail_suppressed"
        if HOME.exists():
            checkpoint("blocked_reconcile_before_any_retry", error_type=type(error).__name__, reason=reason)
        print(json.dumps({"error_type": type(error).__name__, "reason": reason}), flush=True)
        raise SystemExit(1)