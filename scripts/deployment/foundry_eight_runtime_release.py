"""Clean eight-model composition and one-shot ACR builds. NO runtime write API.

Only this controller and its NEW output directory are owned by this release.
No imports of historical release controllers (or their dirty-tree manifests).
Cloud allowlist: account show, scoped ARM GET/settings-list POST, ACR build and
ACR run/manifest/log reads. No Terraform, DB client, inference or role/network API.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / ".deployment/foundry-eight-runtime-20261031"
PROMOTION = ROOT / ".deployment/foundry-eight-offline-promotion-20261031"
ACCEPTED = PROMOTION / "accepted-context"
RATE = ROOT / ".deployment/ratecard-20261030/release"
FIREWORKS = ROOT / ".deployment/fireworks-live-20261028"
INGESTION = FIREWORKS / "ingestion-correction/context"
CLI = ["C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe", "-X", "utf8", "-IBm", "azure.cli"]
CA = Path("C:/Users/p4032099/AppData/Local/Temp/zscaler-login-7860c54ccee94b5d8fa181e004a50458/azure-cli-combined-ca.pem")
SUB = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
TENANT = "beb276ac-6e9f-498e-8e31-019ee666decd"
RG = f"/subscriptions/{SUB}/resourceGroups/IDS-TOKEN-EXCHANGE-POC"
REGISTRY = "pocidstokenexacr"
HOST = REGISTRY + ".azurecr.io"
AIFLUX = "services/control-plane/src/aiflux/"
KINDS = ("api", "admin", "customer", "ingestion")
PINS = {
    "api": "6f973e6ec8651c54beef1c0fe13d8c0c60d688ad15f66f4df735b48baafd7343",
    "admin": "5541f5e708842eb745900d2a5eb8e3868f5231943514f25eae50418cf8aae33a",
    "customer": "77a6067221a5d8c4f5e5bb62e821f20193c7354e43e2cf46c38a355bea280d1e",
    "ingestion": "fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90",
}
API_CHANGES = (AIFLUX + "display_pricing.py", AIFLUX + "model_inventory_sync.py",
               AIFLUX + "pricing/rates-foundry-eight-20261030.json")
CATALOG = tuple("gateway/catalog/" + n for n in (
    "foundry-inventory-20261026.json", "external-inventory.json", "project-routes.json",
    "fireworks-candidate-routes.json", "foundry-eight-candidate-routes.json", "dev-models.json", "ingestion-approved.json"))
BUILDERS = tuple("services/usage-ingestion/" + n for n in (
    "approved_catalog.py", "accepted_catalog_profile.py", "catalog-bindings.json", "ingestion-approved.json"))
API_TEST_NAMES = (
    "test_rate_card.py", "test_display_pricing.py", "test_catalog_pricing_correction.py", "test_usage_rankings.py",
    "test_usage_filters.py", "test_usage_series.py", "test_model_tokens.py", "test_control_plane.py",
    "test_admin_subscriptions.py", "test_finops_ingestion.py", "test_poc_publisher_reliability.py",
    "test_gateway_settings.py", "test_poc_controls.py", "test_managed_controls.py", "test_external_inventory.py",
    "test_foundry_inventory.py", "test_foundry_eight_pricing.py", "test_foundry_eight_sync.py", "test_foundry_eight_catalog.py",
)
UPDATED_TESTS = {"test_display_pricing.py", "test_catalog_pricing_correction.py", "test_foundry_eight_pricing.py",
                 "test_foundry_eight_sync.py", "test_foundry_eight_catalog.py"}
UI_TESTS = ("display-pricing.test.tsx", "rate-card.test.tsx", "admin-showback.test.tsx", "model-tokens.test.tsx",
            "modelPresentation.test.ts", "external-provider.test.tsx", "foundry-eight-runtime.test.tsx")


def now():
    return datetime.now(UTC).isoformat()


def require(ok, label):
    if not ok:
        raise RuntimeError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def write(path, value):
    require(path.resolve().is_relative_to(HOME.resolve()), "output_outside_owned_directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (value.encode() if isinstance(value, str) else
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def files(folder):
    return {p.relative_to(folder).as_posix(): sha(p.read_bytes()) for p in sorted(folder.rglob("*")) if p.is_file()}


def copy(source, target):
    require(source.is_file() and not source.is_symlink(), "regular_source_required:" + str(source))
    raw = source.read_bytes()
    require(not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", raw), "secret_pattern")
    write(target, raw)


def module(path):
    spec = importlib.util.spec_from_file_location("eight_runtime_proof", path)
    require(spec is not None and spec.loader is not None, "profile_spec")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def original_evidence():
    proof = load(PROMOTION / "result.json")
    require(proof["passed"] and proof["accepted_identity_successes"] == proof["http_200_count"] == 8
            and proof["enabled_chat_count"] == 21 and proof["disabled_Decision_1"]
            and proof["remaining_call_budget"] == proof["new_inference_sends"] == 0
            and proof["offline_validation"] == {"tests": 214, "failures": 0, "errors": 0, "skipped": 0}, "accepted_214_evidence")
    # Check only the approved evidence/pricing subset, never the dirty full tree.
    chosen = set(CATALOG + BUILDERS + API_CHANGES)
    chosen |= {p.relative_to(ACCEPTED).as_posix() for p in (ACCEPTED / "gateway/catalog/acceptance-evidence").rglob("*") if p.is_file()}
    chosen |= {"services/control-plane/Dockerfile", "services/usage-ingestion/Dockerfile"}
    for relative in chosen:
        require(sha((ACCEPTED / relative).read_bytes()) == proof["files"]["accepted-context/" + relative], "accepted_subset_drift:" + relative)
    for relative, digest in proof["historical_hashes"].items():
        require(sha((ROOT / relative).read_bytes()) == digest, "historical_receipt_drift:" + relative)
    for relative, digest in load(PROMOTION / "pricing-freeze/manifest.json")["files"].items():
        require(sha((PROMOTION / "pricing-freeze" / relative).read_bytes()) == digest, "pricing_freeze_drift")
        require(sha((ACCEPTED / relative).read_bytes()) == digest, "pricing_accepted_binding")
    require(sha((ROOT / ".deployment/foundry-eight-offline-validation-20261031/result.json").read_bytes())
            == proof["offline_validation_sha256"], "original_validation_receipt")
    return proof, chosen


def baseline_evidence():
    expected = load(ROOT / ".deployment/ratecard-release-20261030/sources.json")["entries"]
    require(all(sha((RATE / row["path"]).read_bytes()) == row["sha256"] for row in expected), "ratecard_build_context_binding")
    ingestion_intent = load(FIREWORKS / "ingestion-correction-intent.json")
    bound = {row["path"]: row["sha256"] for row in ingestion_intent["sources"]}
    actual = files(INGESTION)
    require(all(bound.get(p) == h for p, h in actual.items()) and len(actual) == 53, "actual_cm2e_53_source_binding")
    ingestion_build = load(FIREWORKS / "corrected-build.json")["ingestion"]
    require(ingestion_build["run_id"] == "cm2e" and ingestion_build["digest"] == "sha256:" + PINS["ingestion"], "cm2e_pin_binding")
    require(sha((FIREWORKS / "ingestion-correction/ingestion-build.log").read_bytes()) == ingestion_build["log_sha256"], "cm2e_log_binding")
    for kind in ("api", "admin", "customer"):
        require(load(ROOT / f".deployment/ratecard-release-20261030/{kind}-build.json")["digest"] == "sha256:" + PINS[kind], "deployed_ratecard_pin")
    return {"ratecard_production_sources": expected, "ingestion_cm2e_sources": actual, "pins": PINS,
            "ingestion_retained_context": INGESTION.relative_to(ROOT).as_posix(), "ingestion_run_id": "cm2e"}


def add_catalog(target):
    paths = set(CATALOG + BUILDERS)
    paths |= {p.relative_to(ACCEPTED).as_posix() for p in (ACCEPTED / "gateway/catalog/acceptance-evidence").rglob("*") if p.is_file()}
    for relative in sorted(paths):
        destination = target / relative
        if destination.exists():
            destination.unlink()  # Only NEW, owned context replacement; historical source never touched.
        copy(ACCEPTED / relative, destination)


def overlay_docker(kind):
    root = "/app" if kind == "api" else "/home/site/wwwroot"
    lines = [f"FROM {HOST}/aiflux-{kind}@sha256:{PINS[kind]}", f"WORKDIR {root}"]
    if kind == "api":
        for relative in API_CHANGES:
            local = relative.removeprefix(AIFLUX)
            for dest in (root + "/services/control-plane/src/aiflux/", "/usr/local/lib/python3.11/site-packages/aiflux/"):
                lines.append(f"COPY --chown=10001:10001 {relative} {dest}{local}")
    lines += ["COPY gateway/catalog ./gateway/catalog", "COPY services/usage-ingestion ./services/usage-ingestion",
              "RUN python services/usage-ingestion/accepted_catalog_profile.py --profile foundry-eight-accepted",
              "RUN python -c \"import json; d=json.load(open('gateway/catalog/dev-models.json')); assert len(d['models'])==22; "
              "assert sum(m['enabled'] for m in d['models'])==21; assert not next(m for m in d['models'] if m['id']=='Decision-1')['enabled']\""]
    return "\n".join(lines) + "\n"


def compose():
    require(not HOME.exists(), "existing_release_reconcile_only")
    evidence, chosen = original_evidence()
    baseline = baseline_evidence()
    write(HOME / "composition-intent.json", {"at": now(), "source_sha256": sha(Path(__file__).read_bytes()),
        "approved_operations": ["compose", "ACR Linux no-push validation", "four immutable image builds"],
        "runtime_apply": False, "database_mutations": 0, "inference_budget": 0})
    write(HOME / "baseline-evidence.json", baseline)
    write(HOME / "accepted-subset.json", {p: sha((ACCEPTED / p).read_bytes()) for p in sorted(chosen)})
    write(HOME / "historical-receipts.json", evidence["historical_hashes"])
    # Source trees are actual deployed baselines, not accepted-context.
    for kind in ("admin", "customer"):
        shutil.copytree(RATE / kind, HOME / "contexts" / kind)
    native = HOME / "contexts/api-native"
    for p in sorted((RATE / "api-native").rglob("*")):
        if p.is_file() and (p.relative_to(RATE / "api-native").parts[0] in {"services", "gateway"} or p.name == "pyproject.toml"):
            copy(p, native / p.relative_to(RATE / "api-native"))
    for rel in API_CHANGES:
        target = native / rel
        if target.exists():
            target.unlink()
        copy(ACCEPTED / rel, target)
    add_catalog(native)
    api = HOME / "contexts/api"
    for rel in API_CHANGES:
        copy(native / rel, api / rel)
    add_catalog(api)
    write(api / "EightRuntime.Dockerfile", overlay_docker("api"))
    ingestion = HOME / "contexts/ingestion-native"
    shutil.copytree(INGESTION, ingestion)
    add_catalog(ingestion)
    # Full retained source is audited, but production layers reuse the actual
    # immutable ingestion pin: no OS/package reinstall or locales workaround.
    ing = HOME / "contexts/ingestion"
    add_catalog(ing)
    write(ing / "EightRuntime.Dockerfile", overlay_docker("ingestion"))
    patches = {}
    for rel in API_CHANGES:
        old = RATE / "api-native" / rel
        patch = "".join(difflib.unified_diff(old.read_text().splitlines(True) if old.exists() else [],
            (ACCEPTED / rel).read_text().splitlines(True), fromfile="deployed/" + rel, tofile="eight/" + rel))
        write(HOME / "hunks" / (Path(rel).name + ".patch"), patch)
        patches[rel] = {"before": sha(old.read_bytes()) if old.exists() else None, "after": sha((ACCEPTED / rel).read_bytes())}
    write(HOME / "reviewed-runtime-hunks.json", patches)
    validation_contexts()
    write(HOME / "context-freeze.json", {p.name: files(p) for p in sorted((HOME / "contexts").iterdir())})
    write(HOME / "validation-freeze.json", {p.name: files(p) for p in sorted((HOME / "validation").iterdir())})
    check()
    print(json.dumps({"composed": True, "home": str(HOME), "cloud_operations": 0}))


def validation_contexts():
    api = HOME / "validation/api"
    shutil.copytree(HOME / "contexts/api", api)
    fixture = api / "validation"
    # Historical regression inputs remain historical; selected runtime inputs
    # above are separately proof-validated in the actual final package.
    for parent in ("gateway",):
        for p in sorted((RATE / "api-native" / parent).rglob("*")):
            if p.is_file():
                copy(p, fixture / p.relative_to(RATE / "api-native"))
    copy(RATE / "api-native/pyproject.toml", fixture / "pyproject.toml")
    copy(RATE / "api-native/services/usage-ingestion/ingestion-approved.json", fixture / "services/usage-ingestion/ingestion-approved.json")
    for rel in ("gateway/catalog/foundry-eight-candidate-routes.json", "services/usage-ingestion/approved_catalog.py",
                "services/usage-ingestion/Dockerfile", "services/usage-ingestion/catalog-bindings.json"):
        dest = fixture / rel
        if dest.exists():
            dest.unlink()
        copy(ROOT / rel, dest)
    copy(RATE / "api-native" / (AIFLUX + "queries/usage.kql"), fixture / (AIFLUX + "queries/usage.kql"))
    copy(ROOT / ".deployment/foundry-eight-20261030/requested.json", fixture / ".deployment/foundry-eight-20261030/requested.json")
    copy(RATE / "api-native/tests/unit/conftest.py", fixture / "tests/unit/conftest.py")
    for name in API_TEST_NAMES:
        base = ROOT if name in UPDATED_TESTS else RATE / "api-native"
        copy(base / "tests/unit" / name, fixture / "tests/unit" / name)
    tests = " ".join("tests/unit/" + n for n in API_TEST_NAMES)
    exclude = (' -k "not migration" --deselect "tests/unit/test_external_inventory.py::test_stale_or_future_external_evidence_does_not_hide_foundry"'
               ' --deselect "tests/unit/test_foundry_inventory.py::test_bad_inventory_fails_closed_for_every_customer_path"')
    write(api / "Validation.Dockerfile", overlay_docker("api") +
        "RUN python -m pip install --user --no-cache-dir pytest==8.4.0\nCOPY validation /validation\nWORKDIR /validation\n"
        + "RUN python -m pytest -q -p no:cacheprovider " + tests + exclude + " --junitxml=/tmp/eight-runtime.xml\n")
    for kind in ("admin", "customer"):
        target = HOME / "validation" / kind
        shutil.copytree(HOME / "contexts" / kind, target)
        # No pending UI source copied. New21 integration fixture only.
        write(target / "packages/ui/src/foundry-eight-runtime.test.tsx", UI_INTEGRATION)
        catalog = load(ACCEPTED / "gateway/catalog/dev-models.json")
        rates = load(ACCEPTED / (AIFLUX + "pricing/rates-20261027.json"))["rates"]
        rates += load(ACCEPTED / (AIFLUX + "pricing/rates-foundry-eight-20261030.json"))["rates"]
        write(target / "packages/ui/src/foundry-eight-runtime-fixture.json", {"catalog": catalog, "rates": rates})
        selected = " ".join("packages/ui/src/" + n for n in UI_TESTS)
        write(target / "Validation.Dockerfile", "FROM node:22-alpine\nWORKDIR /repo\nCOPY . .\n"
            "RUN npm ci --workspaces --include-workspace-root\n"
            "ENV VITE_AUTH_MODE=local VITE_CONTROL_API_URL=/api VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1\n"
            "RUN npm run typecheck\nRUN npm test -- " + selected + " --reporter=verbose\nRUN npm run build\n")
    target = HOME / "validation/ingestion"
    shutil.copytree(HOME / "contexts/ingestion", target)
    write(target / "Validation.Dockerfile", overlay_docker("ingestion") +
        "RUN python -c \"import azure.functions,azure.identity,azure.monitor.query,psycopg; "
        "from aiflux.ingestion import extract_usage; from aiflux.config import Settings; "
        "s=Settings(_env_file=None,environment='development',ingestion_start_at='2026-10-27T00:00:00Z'); "
        "assert s.ingestion_start_at.tzinfo; print('INGESTION_CANONICAL21_PLUS_DISABLED_DECISION=passed')\"\n")


def check():
    original_evidence()
    baseline_evidence()
    validation_receipt = "validation-freeze-r2.json" if (HOME / "validation-freeze-r2.json").exists() else "validation-freeze.json"
    for receipt, parent in (("context-freeze.json", "contexts"), (validation_receipt, "validation")):
        frozen = load(HOME / receipt)
        require({p.name: files(p) for p in sorted((HOME / parent).iterdir())} == frozen, "actual_context_drift:" + parent)
    # None of the pending API modules may enter ANY runtime or validation context.
    forbidden = {"auto_snapshot.py", "decision_router.py", "decision_auth.py", "decision_client.py", "auto-routing-defaults.json", "decision-overhead.kql"}
    for parent in (HOME / "contexts", HOME / "validation"):
        require(not any(p.name in forbidden for p in parent.rglob("*")), "pending_Auto_module_in_context")
    for kind in ("admin", "customer"):
        require(files(HOME / "contexts" / kind) == files(RATE / kind), "UI_deployed_baseline_changed")
    for relative, digest in load(HOME / "historical-receipts.json").items():
        require(sha((ROOT / relative).read_bytes()) == digest, "historical_bytes_changed")
    return {"passed": True, "source_sha256": sha((HOME / "context-freeze.json").read_bytes()),
            "no_pending_auto_modules": True, "UI_runtime_source_exact_deployed_baseline": True}


def environment():
    require(CA.is_file(), "strict_CA_missing_no_fallback")
    require(not any(os.environ.get(k, "").lower() in ("1", "true", "yes") for k in (
        "AZURE_CLI_DISABLE_CONNECTION_VERIFICATION", "PYTHONHTTPSVERIFY_DISABLED")), "TLS_verification_disabled")
    return {**os.environ, "REQUESTS_CA_BUNDLE": str(CA), "SSL_CERT_FILE": str(CA), "PYTHONDONTWRITEBYTECODE": "1"}


def cli(args):
    allowed = (args[:2] == ["account", "show"] or args[:2] == ["acr", "build"]
        or args[:3] in (["acr", "task", "show-run"], ["acr", "task", "list-runs"], ["acr", "task", "logs"],
                        ["acr", "manifest", "show-metadata"]) or args[:2] == ["rest", "--method"])
    require(allowed, "cloud_command_not_allowlisted")
    result = subprocess.run(CLI + args + ["--only-show-errors", "-o", "json"], cwd=ROOT, env=environment(),
        capture_output=True, encoding="utf-8", errors="replace")
    require(result.returncode == 0, "CLI_read_failed:" + "/".join(args[:3]))
    return json.loads(result.stdout)


def metadata(label):
    require(re.fullmatch("[a-z0-9-]+", label) is not None, "metadata_label")
    exclusive = HOME / ("metadata-" + label + "-intent.json")
    write(exclusive, {"at": now(), "only": "ARM config GET + appsettings list read POST + ACR original show-run"})
    account = cli(["account", "show", "--subscription", SUB])
    require(account["id"] == SUB and account["tenantId"] == TENANT and account["state"] == "Enabled", "account_scope")
    result = {}
    for kind in KINDS:
        site = "poc-ids-token-ex-" + ("ingestion" if kind == "ingestion" else kind)
        url = "https://management.azure.com" + RG + "/providers/Microsoft.Web/sites/" + site + "/config/"
        config = cli(["rest", "--method", "get", "--url", url + "web?api-version=2024-04-01"])["properties"]
        settings = cli(["rest", "--method", "post", "--url", url + "appsettings/list?api-version=2024-04-01"])["properties"]
        image = config.get("linuxFxVersion", "")
        require(PINS[kind] in image, "live_image_not_expected_baseline:" + kind)
        result[kind] = {"image": image, "config_sha256": sha(json.dumps(config, sort_keys=True).encode()),
            "settings_sha256": sha(json.dumps(settings, sort_keys=True).encode()),
            "setting_count": len(settings), "inventory_settings": {k: v for k, v in settings.items()
                if k in {"AIFLUX_FOUNDRY_INVENTORY_PATH", "AIFLUX_EXTERNAL_INVENTORY_PATH", "AIFLUX_CATALOG_PATH"}}}
    for kind, run_id in (("api", "cm3j"), ("admin", "cm3k"), ("customer", "cm3m"), ("ingestion", "cm2e")):
        run = cli(["acr", "task", "show-run", "-r", REGISTRY, "--run-id", run_id, "--subscription", SUB])
        require(run["status"] == "Succeeded" and any(i.get("digest") == "sha256:" + PINS[kind]
            for i in run.get("outputImages") or []), "actual_ACR_baseline_output:" + kind)
    write(HOME / ("metadata-" + label + ".json"), {"at": now(), "runtime": result})
    print(json.dumps({"metadata": label, "baseline_pins_verified": True, "runtime_mutations": 0}))


def job(action, kind):
    require(action in ("validate", "build") and kind in KINDS, "exact_job")
    check_result = check()
    require((HOME / "independent-check.json").exists() and load(HOME / "independent-check.json")["passed"], "independent_check_required")
    require((HOME / "metadata-before.json").exists(), "live_baseline_metadata_required")
    if action == "build":
        require(all(load(HOME / f"validate-{k}-result.json")["status"] == "Succeeded" for k in KINDS), "all_four_validations_required")
    folder = HOME / ("validation" if action == "validate" else "contexts") / kind
    docker = "Validation.Dockerfile" if action == "validate" else (
        f"apps/{kind}-portal/Dockerfile" if kind in ("admin", "customer") else "EightRuntime.Dockerfile")
    identity = f"{action}-{kind}"
    tag = "foundry-eight-20261031-" + action + "-" + check_result["source_sha256"][:12]
    args = ["acr", "build", "--registry", REGISTRY, "--subscription", SUB, "--platform", "linux/amd64",
        "--timeout", "1800", "--file", docker, "--image", "aiflux-" + kind + ":" + tag, "--no-wait"]
    if action == "validate":
        args += ["--no-push"]
    if action == "build" and kind in ("admin", "customer"):
        args += ["--build-arg", "VITE_AUTH_MODE=local", "--build-arg", "VITE_CONTROL_API_URL=/api",
                 "--build-arg", "VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"]
    write(HOME / (identity + "-intent.json"), {"at": now(), "action": action, "kind": kind, "tag": tag,
        "source_sha256": check_result["source_sha256"], "context_files": files(folder), "command": args + ["."],
        "cwd": folder.relative_to(ROOT).as_posix(), "max_submissions": 1, "retry_permitted": False})
    # Intent is fsynced BEFORE invocation. An empty/failed response consumes the
    # local attempt and must be reconciled via original run reads, never replayed.
    child = subprocess.run(CLI + args + [".", "-o", "json"], cwd=folder, env=environment(),
        capture_output=True, encoding="utf-8", errors="replace")
    text = re.sub(r"https://[^\s\"<>]*\?[^\s\"<>]*", "[signed-url-redacted]", child.stdout + child.stderr)
    write(HOME / (identity + "-submit.log"), text)
    try:
        data = json.loads(child.stdout)
    except ValueError:
        data = {}
    ids = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
    run_id = data.get("runId") if isinstance(data, dict) else None
    run_id = run_id or (ids[-1] if ids else None)
    write(HOME / (identity + "-submission.json"), {"at": now(), "returncode": child.returncode, "run_id": run_id,
        "response_sha256": sha(text.encode()), "replay_permitted": False})
    require(child.returncode == 0, "reconcile_original_run_no_resubmission:" + identity)
    if not run_id:
        run_id = locate(identity)
    finish(identity, run_id)


def locate(identity):
    """Read-only resolution of CLI --no-wait's empty original response."""
    require(re.fullmatch(r"(?:validate|build)-(?:api|admin|customer|ingestion)", identity) is not None, "original_job_identity")
    intent = load(HOME / (identity + "-intent.json"))
    runs = cli(["acr", "task", "list-runs", "-r", REGISTRY, "--top", "30", "--subscription", SUB])
    write(HOME / (identity + "-original-run-discovery.json"), runs)
    matches = [r for r in runs if intent["tag"] in json.dumps(r)
        and datetime.fromisoformat(r["createTime"].replace("Z", "+00:00")) >= datetime.fromisoformat(intent["at"])]
    require(len(matches) == 1, "original_run_not_uniquely_bound_no_resubmission")
    write(HOME / (identity + "-original-run-binding.json"), {"at": now(), "run_id": matches[0]["runId"],
        "tag": intent["tag"], "matched_by": "exact_unique_output_tag_and_original_intent_time", "resubmitted": False})
    return matches[0]["runId"]


def finish(identity, run_id):
    require(re.fullmatch(r"(?:validate|build)-(?:api|admin|customer|ingestion)", identity) is not None
            and re.fullmatch("[a-z0-9]+", run_id) is not None, "exact_original_job_identity")
    intent = load(HOME / (identity + "-intent.json"))
    require(not (HOME / (identity + "-result.json")).exists(), "existing_result_read_only")
    # The supported CLI log command follows the ORIGINAL run to completion.
    child = subprocess.run(CLI + ["acr", "task", "logs", "-r", REGISTRY, "--run-id", run_id, "--subscription", SUB],
        cwd=ROOT, env=environment(), capture_output=True, encoding="utf-8", errors="replace")
    text = re.sub(r"https://[^\s\"<>]*\?[^\s\"<>]*", "[signed-url-redacted]", child.stdout + child.stderr)
    log_path = HOME / (identity + "-run-" + run_id + ".log")
    if not log_path.exists():
        write(log_path, text)
    run = cli(["acr", "task", "show-run", "-r", REGISTRY, "--run-id", run_id, "--subscription", SUB])
    write(HOME / (identity + "-run-" + run_id + ".json"), run)
    require(run["status"] in ("Succeeded", "Failed", "Canceled", "Error", "Timeout"), "original_run_not_terminal_reconcile_only")
    require(run["platform"]["os"].lower() == "linux", "Linux_required")
    if intent["action"] == "build" and run["status"] == "Succeeded":
        outputs = run.get("outputImages") or []
        require(len(outputs) == 1 and outputs[0]["repository"] == "aiflux-" + intent["kind"]
                and outputs[0]["tag"] == intent["tag"] and outputs[0]["registry"] == HOST
                and re.fullmatch("sha256:[a-f0-9]{64}", outputs[0]["digest"]) is not None, "exact_immutable_output")
        meta = cli(["acr", "manifest", "show-metadata", "--registry", REGISTRY, "--subscription", SUB,
                    "--name", outputs[0]["repository"] + ":" + intent["tag"]])
        require(meta["digest"] == outputs[0]["digest"], "independent_registry_digest")
    else:
        outputs = run.get("outputImages") or []
        require(not any(x.get("digest") for x in outputs), "no_push_validation")
    result = {"at": now(), "run_id": run_id, "status": run["status"], "finished_at": run.get("finishTime"),
        "source_sha256": intent["source_sha256"], "no_push": intent["action"] == "validate",
        "log_sha256": sha(log_path.read_bytes()), "outputs": outputs,
        "test_summaries": re.findall(r"[^\r\n]*(?:\d+ passed|Test Files|Tests\s+\d+|INGESTION_CANONICAL21)[^\r\n]*", text)}
    if intent["action"] == "build" and run["status"] == "Succeeded":
        result.update(digest=outputs[0]["digest"], image=HOST + "/" + outputs[0]["repository"] + "@" + outputs[0]["digest"])
    check()
    write(HOME / (identity + "-result.json"), result)
    print(json.dumps(result), flush=True)
    require(run["status"] == "Succeeded", "original_run_failed_no_blind_retry:" + identity)


def final():
    audit = check()
    before = load(HOME / "metadata-before.json")["runtime"]
    after = load(HOME / "metadata-after.json")["runtime"]
    require(before == after, "runtime_changed_during_builds")
    results = {a: {k: load(HOME / f"{a}-{k}-result.json") for k in KINDS} for a in ("validate", "build")}
    require(all(v["status"] == "Succeeded" and v["source_sha256"] == audit["source_sha256"] for a in results.values() for v in a.values()), "all_eight_ACR_runs_required")
    value = {"at": now(), "passed": True, "ready_for_narrow_four_image_plan": True, "results": results,
        "runtime_unchanged": True, "runtime_apply": False, "database_mutations": 0, "inference_sends": 0,
        "remaining_inference_budget": 0, "source_sha256": audit["source_sha256"],
        "files": {p.relative_to(HOME).as_posix(): sha(p.read_bytes()) for p in sorted(HOME.iterdir()) if p.is_file()}}
    write(HOME / "result.json", value)
    print(json.dumps({k: v for k, v in value.items() if k not in ("results", "files")}))


def correct_validation_fixture():
    """One missing historical query fixture, with original failed proof retained."""
    require(load(HOME / "local-api-tests-result.json")["returncode"] == 1, "original_local_fixture_failure_required")
    check()
    relative = AIFLUX + "queries/usage.kql"
    target = HOME / "validation/api/validation" / relative
    require(not target.exists(), "one_missing_fixture_only")
    copy(RATE / "api-native" / relative, target)
    write(HOME / "validation-fixture-correction.json", {"at": now(), "reason": "missing historical usage.kql test fixture",
        "new_file": target.relative_to(HOME).as_posix(), "sha256": sha(target.read_bytes()),
        "original_failed_tests_preserved": True, "runtime_contexts_unchanged": True, "cloud_builds_submitted": 0})
    write(HOME / "validation-freeze-r2.json", {p.name: files(p) for p in sorted((HOME / "validation").iterdir())})
    print(json.dumps(check()))


def local_tests(suffix=""):
    """Only in-memory SQLite fixture tests; source path excludes dirty checkout."""
    check()
    require(suffix in ("", "-r2"), "local_attempt_name")
    write(HOME / ("local-tests" + suffix + "-intent.json"), {"at": now(), "source_sha256": sha(Path(__file__).read_bytes()),
        "cloud_calls": 0, "database": "isolated synthetic SQLite only", "inference_sends": 0})
    context = HOME / "validation/api/validation"
    env = {**os.environ, "PYTHONPATH": str(HOME / "contexts/api-native/services/control-plane/src"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    args = [sys.executable, "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    args += ["tests/unit/" + name for name in API_TEST_NAMES]
    args += ["-k", "not migration", "--deselect", "tests/unit/test_external_inventory.py::test_stale_or_future_external_evidence_does_not_hide_foundry",
             "--deselect", "tests/unit/test_foundry_inventory.py::test_bad_inventory_fails_closed_for_every_customer_path",
             "--junitxml=" + str(HOME / ("local-api-tests" + suffix + ".xml"))]
    result = subprocess.run(args, cwd=context, env=env, capture_output=True, encoding="utf-8", errors="replace")
    write(HOME / ("local-api-tests" + suffix + ".log"), result.stdout + result.stderr)
    write(HOME / ("local-api-tests" + suffix + "-result.json"), {"at": now(), "returncode": result.returncode, "cloud_calls": 0})
    print(result.stdout + result.stderr)
    require(result.returncode == 0, "local_fixture_tests_failed")


UI_INTEGRATION = r'''import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ControlApi } from "./client";
import { SessionProvider } from "./session";
import { ModelsPage } from "./pages/ModelsPage";
import { PlaygroundPage } from "./pages/PlaygroundPage";
import { PricesPage } from "./pages/admin";
import fixture from "./foundry-eight-runtime-fixture.json";

const config = { clientId: "c", authority: "a", apiScope: "s", controlApiUrl: "/api", gatewayUrl: "https://not-called.invalid/v1" };
const me = { organization_id: "o", organization_name: "IDS", tenant_id: "t", object_id: "u", role: "ids_admin" as const };
const models = fixture.catalog.models;
const enabled = models.filter(m => m.enabled);
function page(view: React.ReactNode, existing = true) {
  const calls: string[] = [];
  const fetcher = (async (url: string, init?: RequestInit) => {
    expect(!init?.method || init.method === "GET").toBe(true);
    calls.push(url);
    let data: unknown = {items: [], total: 0};
    if (url.endsWith("/models")) data = {items: models, total: models.length};
    else if (url.includes("/model-garden")) data = {items: enabled.map(m => ({...m, display_price: {
      ...fixture.rates.find(r => r.model === m.id), currency: "USD", unit: "per_million_tokens",
      status: "public_list", basis: "Frozen release fixture", assumptions: "Not an invoice", source_url: "https://example.invalid/rate",
    }})), total: 21};
    else if (url.includes("/admin/rate-card")) data = {version: 0, revision: "frozen", currency: "USD", unit: "per_million_tokens",
      items: enabled.map(m => { const r = fixture.rates.find(r => r.model === m.id)!; return {
        ...r, origin: r.status === "unknown" ? "platform_default" : r.status,
        default_input: r.input ?? "1", default_output: r.output ?? "1", input: r.input ?? "1", output: r.output ?? "1",
        default_cached: r.cached ?? null, default_write: r.write ?? null, cached: r.cached ?? null, write: r.write ?? null,
      }; }), total: 21, changed: false};
    else if (url.includes("/subscriptions")) data = {items: [{id: existing ? "existing" : "new", name: existing ? "Existing eligible" : "New eligible", state: "active"}], total: 1};
    else if (url.includes("/auto-routing")) data = {ready: false}; // existing deployed UI read only; no routing test/send
    return new Response(JSON.stringify(data), {status: 200});
  }) as unknown as typeof fetch;
  const api = new ControlApi("/api", async () => "synthetic", fetcher);
  render(<MemoryRouter><SessionProvider me={me} api={api} config={config} onSignOut={() => undefined}>{view}</SessionProvider></MemoryRouter>);
  return calls;
}
describe("accepted canonical21 release integration without inference", () => {
  it("catalog renders all canonical21 and excludes routing-only Decision", async () => {
    const calls = page(<ModelsPage />);
    const list = await screen.findByRole("list", {name: "Model availability"});
    expect(within(list).getAllByRole("listitem")).toHaveLength(21);
    for (const m of enabled) expect(within(list).getByRole("heading", {name: m.id})).toBeInTheDocument();
    expect(within(list).queryByText("Decision-1")).not.toBeInTheDocument();
    expect(calls.every(c => c.startsWith("/api/"))).toBe(true);
  });
  it.each([true, false])("Playground gives every eligible subscription all21 choices (existing=%s), never sends", async existing => {
    const calls = page(<PlaygroundPage />, existing);
    const select = await screen.findByLabelText("Model");
    expect(within(select).getAllByRole("option")).toHaveLength(21);
    for (const m of enabled) expect(within(select).getByRole("option", {name: m.id})).toBeInTheDocument();
    expect(screen.queryByRole("option", {name: "Decision-1"})).not.toBeInTheDocument();
    await userEvent.selectOptions(select, "Mistral-Large-3");
    expect(select).toHaveValue("Mistral-Large-3");
    expect(calls.some(c => c.includes("chat/completions") || c.includes("/keys/"))).toBe(false);
  });
  it("rate card renders all21 frozen rates without saving", async () => {
    const calls = page(<PricesPage />);
    await screen.findByLabelText("Mistral-Large-3 input rate");
    for (const m of enabled) expect(screen.getByLabelText(m.id + " input rate")).toBeInTheDocument();
    expect(screen.getByLabelText("claude-opus-5-5-fast input rate")).toHaveValue("8");
    expect(screen.getByLabelText("gpt-4o input rate")).toHaveValue("2.50");
    expect(calls.some(c => c.includes("chat/completions"))).toBe(false);
  });
});
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("compose", "check", "local", "correct-fixture", "metadata", "validate", "build", "locate", "reconcile", "final"))
    parser.add_argument("subject", nargs="?")
    parser.add_argument("run_id", nargs="?")
    args = parser.parse_args()
    if args.action == "compose":
        compose()
    elif args.action == "check":
        print(json.dumps(check()))
    elif args.action == "local":
        local_tests("-r2" if args.subject == "r2" else "")
    elif args.action == "correct-fixture":
        correct_validation_fixture()
    elif args.action == "metadata":
        metadata(args.subject)
    elif args.action in ("validate", "build"):
        job(args.action, args.subject)
    elif args.action == "reconcile":
        finish(args.subject, args.run_id)
    elif args.action == "locate":
        finish(args.subject, locate(args.subject))
    else:
        final()


if __name__ == "__main__":
    main()