"""Customer Send lifecycle release preparation. No apply/Auto/policy entrypoint.

prepare performs metadata reads and local curation only. build is a separate,
parent-review-gated one-shot operation; it is NEVER chained from prepare.
plan requires a real built digest; its full companion is NEVER applicable here.
Historical controllers are imported for helpers, never invoked as workflows.
"""
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

from scripts.deployment import customer_login_release as login
from scripts.deployment import auto_revision_arm_once as owner
from scripts.deployment import auto_live_gate as gate
from scripts.deployment import inventory_persistence_release as persistence
from scripts.deployment.inventory_persistence_apply_once import supplemental

rt, fs, portals = login.rt, login.fs, login.portals
UI = rt.HOME / "auto-routing-native-20261029T104010824145Z"
SOURCE = "18341f9ac56523fdd1af41dab2b0bcbff653657abf4d5165b98162e795268a48"
DOCKER = "apps/customer-portal/Dockerfile"
TEST = "tests/unit/test_customer_send_release.py"
DOC = "docs/customer-send-release-20261029.md"
TEST_RECEIPT = ".deployment/customer-send-offline-tests-bound-20261029.xml"
PINS = {**login.PINS,
        "api": "29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64",
        "customer": "a30d513ce0dd7c529491689a49ce311f7794f4785e1dd5c5577ae62da9f1b975"}
ADDRESS = login.ADDRESS
require = rt.require
load = login.load


def now():
    return datetime.now(UTC).isoformat()


def sha(path):
    return login.sha(path.read_bytes())


def write(folder, name, value):
    with (folder / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def safe_path(name):
    p = PurePosixPath(name)
    require(bool(name) and not p.is_absolute() and ".." not in p.parts
            and not any(x.startswith(".") for x in p.parts)
            and not re.search(r"[:\\]", name) and p.as_posix() == name,
            "unsafe_source_path")
    return Path(name)


def subset(entries):
    """Exactly the COPY inputs of the retained customer Dockerfile, no API/admin."""
    return [e for e in entries if e["path"] in {
        "package.json", "package-lock.json", "tsconfig.base.json"}
        or e["path"].startswith(("packages/ui/", "apps/customer-portal/"))]


def retained():
    manifest, result = load(UI / "sources.json"), load(UI / "result.json")
    entries = manifest["entries"]
    require(manifest["source_sha256"] == SOURCE == result["source_sha256"]
            == portals.digest(json.dumps(entries, sort_keys=True).encode()), "cm37_source_binding")
    require(result["run_id"] == "cm37" and result["passed"] is True
            and result["status"] == "Succeeded" and result["no_push"] is True
            and result["deployed"] is False and result["tests_passed"] == 160
            and result["test_files_passed"] == 17 and result["source_count"] == len(entries) == 77
            and login.ui.no_published_images(result["outputImages"])
            and all(result["proof_markers"].values()), "actual_retained_native_result")
    paths = [e["path"] for e in entries]
    expected = {p.relative_to(rt.ROOT).as_posix() for p in portals.source_files()}
    expected.add(login.ui.DOCKERFILE)
    require(len(paths) == len(set(paths)) and set(paths) == expected, "exact_cm37_membership")
    for e in entries:
        p = safe_path(e["path"])
        for base in (rt.ROOT, UI / "context"):
            f = base / p
            require(not any(x.is_symlink() for x in (f, *f.parents))
                    and sha(f) == e["sha256"], "cm37_context_source_drift:" + e["path"])
            require(not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", f.read_bytes()), "source_secret")
    launchers = load(UI / "launcher-sources.json")
    require(len(launchers) == 4 and all(sha(rt.ROOT / safe_path(p)) == h for p, h in launchers.items()), "cm37_launcher_drift")
    text = (UI / "validation.log").read_text(encoding="utf-8")
    require(portals.digest(text.encode()) == result["log_sha256"], "cm37_log_drift")
    return manifest


def context_guard(folder, entries):
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    require(not any(p.is_symlink() for p in folder.rglob("*")), "context_symlink")
    require({p.relative_to(folder).as_posix() for p in files} == {e["path"] for e in entries}, "exact_customer_context")
    require(all(sha(folder / safe_path(e["path"])) == e["sha256"] for e in entries), "customer_context_hash")


def tooling():
    paths = set((rt.ROOT / "scripts/deployment").glob("*.py"))
    paths |= set((rt.ROOT / "infra/terraform").glob("*.tf")) | set((rt.ROOT / "infra/terraform").glob("*.tf.json"))
    paths |= {rt.ROOT / p for p in (TEST, DOC, TEST_RECEIPT, "infra/terraform/.terraform.lock.hcl", "infra/terraform/backend.hcl")}
    paths |= {rt.HOME / p for p in ("rebuild-platform.tfvars.json", "jwt-runtime.tfvars.json")}
    return {p.relative_to(rt.ROOT).as_posix(): sha(p) for p in sorted(paths)}


@contextmanager
def read_transport():
    # Existing bounded metadata transport only; undo its module bindings on exit.
    cli, command, product = rt.cli, rt.CLI, persistence.release.ProductRun
    try:
        persistence.transport()
        yield
    finally:
        rt.cli, rt.CLI, persistence.release.ProductRun = cli, command, product


def collect():
    gate.require_no_competing_workers(persistence.backend.workers())
    login.account()
    state = owner.state_owner()
    reads = owner.Reads()
    rows, _ = reads.get("/revisions")
    require(not rows.get("nextLink"), "complete_revision_list")
    revisions = [gate.summarize_revision(r) for r in rows["value"]]
    require(len(revisions) == 2 and {r["revision"] for r in revisions} == {"1", "2"}, "exact_two_revisions")
    for r in revisions:
        expected = r["revision"] == "1"
        require(r["is_online"] is expected and r["is_current"] is expected, "revision_flags_changed")
    current, _ = reads.get("")
    cleanup = load(owner.HOME / "scoring-diagnostic06/offline-after-capture.json")
    require(fs.sha(current) == cleanup["current_api_sha256"], "current1_metadata_drift")
    with read_transport():
        baseline = persistence.release.snapshot()
        extra = supplemental(baseline)
        run = rt.cli(["acr", "task", "show-run", "--registry", portals.REGISTRY,
                      "--run-id", "cm37", "--subscription", rt.SUB])
        require(run["status"] == "Succeeded" and login.ui.no_published_images(run.get("outputImages"))
                and run["finishTime"] == load(UI / "result.json")["finishTime"], "remote_cm37_binding")
        head = persistence.backend.blob_head()
        storage = persistence.backend.arm_read()["account"]
    require(len(baseline) == 13 and baseline == load(owner.HOME / "protected-before.json")
            and fs.sha(baseline) == cleanup["baseline_sha256"], "original_full13_baseline_drift")
    require(extra == load(owner.HOME / "supplemental-before.json")
            and fs.sha(extra) == cleanup["supplemental_sha256"], "supplemental_drift")
    for k, pin in PINS.items():
        require(baseline["runtime"]["sites"][k]["image"] == "DOCKER|" + portals.HOST + "/aiflux-" + k + "@sha256:" + pin, "predecessor_pin:" + k)
    acl = storage["properties"]["networkAcls"]
    require(acl["defaultAction"] == "Deny" and any(r == {"value": "167.103.66.248", "action": "Allow"} for r in acl["ipRules"]), "existing_state_ip_rule_required_no_acl_write")
    require(head["status"] == 200 and head["lease_state"] == "available" and head["lease_status"] == "unlocked", "state_access_or_lease_blocked")
    return {"at_utc": now(), "baseline": baseline, "supplemental": extra, "state_owner": state,
            "revisions": revisions, "current_api_sha256": fs.sha(current), "remote_head": head,
            "storage_sha256": fs.sha(storage), "state_ip": "167.103.66.248", "state_default_action": "Deny"}


def guard(plan, image, before, settings):
    require(before["runtime"]["sites"]["customer"]["image"] == "DOCKER|" + portals.HOST + "/aiflux-customer@sha256:" + PINS["customer"], "fixed_customer_predecessor")
    login.guard(plan, image, before)
    writes = [r for r in plan["resource_changes"] if r["change"]["actions"] == ["update"]]
    require(writes[0]["change"]["before"]["app_settings"] == settings, "complete_customer_settings_predecessor")
    require(image != before["runtime"]["sites"]["customer"]["image"].removeprefix("DOCKER|"), "new_image_required")


def clean_environment():
    env = {k: v for k, v in rt.ENV.items() if not k.startswith(("TF_CLI_ARGS", "TF_VAR_", "TF_LOG"))
           and k not in {"TF_WORKSPACE", "TF_DATA_DIR", "ARM_ACCESS_KEY", "ARM_SAS_TOKEN",
                         "ARM_CLIENT_SECRET", "ARM_OIDC_TOKEN"}}
    env.update(TF_WORKSPACE="default", TF_IN_AUTOMATION="1", TF_INPUT="0", PYTHONUTF8="1")
    return env


@contextmanager
def terraform_environment(root):
    old = rt.ENV
    rt.ENV = {**clean_environment(), "TF_DATA_DIR": str(root / ".terraform")}
    try:
        yield
    finally:
        rt.ENV = old


class Release:
    def __init__(self, name):
        require(re.fullmatch(r"customer-send-20261029T[0-9]{12}Z", name), "fresh_customer_send_name")
        self.home = rt.HOME / name
        self.root = self.home / "infra/terraform"
        self.target = self.home / "customer-only.tfplan"
        self.full = self.home / "validation-only-NEVER-APPLY.tfplan"

    def prepare(self):
        require(not self.home.exists(), "existing_package_reconcile_never_reprepare")
        self.home.mkdir()
        fs.protect(self.home)
        write(self.home, "prepare-intent.json", {"at_utc": now(), "configuration_writes": 0, "builds": 0, "plans": 0})
        manifest = retained()
        capture = collect()
        write(self.home, "capture.json", capture)
        entries = subset(manifest["entries"])
        context = self.home / "context"
        for e in entries:
            dest = context / safe_path(e["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as handle:
                handle.write((UI / "context" / e["path"]).read_bytes())
        context_guard(context, entries)
        prior = rt.HOME / "admin-showback-native-20261028T121721699258Z"
        old = {e["path"]: e["sha256"] for e in load(prior / "sources.json")["entries"]}
        delta = [e["path"] for e in manifest["entries"] if old.get(e["path"]) != e["sha256"]]
        diffs = []
        for name in delta:
            p = prior / "context" / name
            diffs.extend(difflib.unified_diff(p.read_text(encoding="utf-8").splitlines(True) if p.exists() else [],
                (rt.ROOT / name).read_text(encoding="utf-8").splitlines(True), fromfile="deployed/" + name, tofile="cm37/" + name))
        (self.home / "bundle-scope.diff").write_text("".join(diffs), encoding="utf-8")
        package = {"at_utc": now(), "status": "PREPARED_NOT_REVIEWED_NOT_VALIDATED", "source_sha256": SOURCE,
            "entries": entries, "customer_context_sha256": fs.sha(entries), "tooling": tooling(),
            "capture_sha256": sha(self.home / "capture.json"), "delta_vs_customer_login": delta,
            "diff_sha256": sha(self.home / "bundle-scope.diff"), "max_builds": 1, "max_applies": 0,
            "only_future_target": ADDRESS, "api_image_unchanged": PINS["api"],
            "cm37_artifacts": {n: sha(UI / n) for n in ("sources.json", "result.json", "launcher-sources.json", "validation.log")},
            "build_argv": self.build_args(), "build_cwd": context.relative_to(rt.ROOT).as_posix(),
            "next_parent_reviewed_build_argv": ["C:/Program Files/Python313/python.exe", "-X", "utf8", "-u", "-m", "scripts.deployment.customer_send_release", "build", "--name", self.home.name],
            "compatibility": "Missing/failed availability cannot gate explicit models; only ready===true shows Auto. Existing reveal request body unchanged; optional AbortSignal local only. No API/admin/ingestion code packaged or flags changed.",
            "requires_parent_review": True, "auto_enablement": False, "actual_page_acceptance": False}
        write(self.home, "package.json", package)
        # A second full snapshot detects concurrent drift while local files were staged.
        with read_transport():
            after = persistence.release.snapshot()
        require(after == capture["baseline"], "full13_changed_during_preparation")
        write(self.home, "prepared.json", {"at_utc": now(), "package_sha256": sha(self.home / "package.json"),
            "all13_equal_after": True, "builds": 0, "pushes": 0, "plans": 0, "applies": 0, "auto_enabled": False})
        return package

    def check(self):
        p = load(self.home / "package.json")
        require(load(self.home / "prepared.json")["package_sha256"] == sha(self.home / "package.json")
                and p["tooling"] == tooling() and p["entries"] == subset(retained()["entries"])
                and p["build_argv"] == self.build_args(), "package_source_tooling_binding")
        require(all(sha(UI / n) == h for n, h in p["cm37_artifacts"].items())
                and p["capture_sha256"] == sha(self.home / "capture.json")
                and p["diff_sha256"] == sha(self.home / "bundle-scope.diff"), "evidence_binding")
        context_guard(self.home / "context", p["entries"])
        return p

    def build_args(self):
        return ["acr", "build", "--registry", portals.REGISTRY, "--subscription", rt.SUB,
                "--platform", "linux/amd64", "--timeout", "1800", "--file", DOCKER,
                "--image", "aiflux-customer:" + self.home.name.lower() + "-" + SOURCE[:12],
                "--build-arg", "VITE_AUTH_MODE=local", "--build-arg", "VITE_CONTROL_API_URL=/api",
                "--build-arg", "VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1", "."]

    def reviewed(self):
        self.check()
        review = load(self.home / "parent-build-review.json")
        require(review["scope"] == "CUSTOMER_SEND_IMAGE_BUILD_ONLY" and review["decision"] == "PASS"
                and review["package_sha256"] == sha(self.home / "package.json")
                and review["reviewer_pid"] != os.getpid() and isinstance(review["reviewer_pid"], int)
                and review["reviewer_pid"] > 0 and review["actual_independent_review"] is True,
                "actual_parent_source_review_required")
        summary = self.home / safe_path(review["summary_file"])
        require(sha(summary) == review["summary_sha256"] and summary.stat().st_size > 0, "actual_review_summary_binding")
        require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at_utc"]) < timedelta(hours=2), "stale_parent_review")

    def build(self):
        require(not (self.home / "build-intent.json").exists(), "build_consumed_reconcile_never_retry")
        self.reviewed()
        captured = collect()
        old = load(self.home / "capture.json")
        require(all(captured[k] == old[k] for k in ("baseline", "supplemental", "state_owner", "revisions", "current_api_sha256", "storage_sha256")), "fresh_prebuild_protected_drift")
        self.check()
        write(self.home, "build-intent.json", {"at_utc": now(), "args": self.build_args(), "package_sha256": sha(self.home / "package.json"), "attempts": 1})
        p = subprocess.run(rt.CLI + self.build_args(), cwd=self.home / "context", env=clean_environment(),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2100)
        text = login.ui.redact(p.stdout + p.stderr)
        (self.home / "customer-build.log").write_text(text, encoding="utf-8")
        write(self.home, "build-exit.json", {"at_utc": now(), "exit_code": p.returncode, "log_sha256": sha(self.home / "customer-build.log")})
        ids = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
        require(p.returncode == 0 and ids, "build_unknown_or_failed_no_retry")
        run = rt.cli(["acr", "task", "show-run", "--registry", portals.REGISTRY, "--run-id", ids[-1], "--subscription", rt.SUB])
        output = run.get("outputImages") or []
        require(run["status"] == "Succeeded" and len(output) == 1 and isinstance(output[0], dict), "single_customer_output")
        digest = output[0]["digest"]
        require(re.fullmatch(r"sha256:[a-f0-9]{64}", digest) and output == [{"registry": portals.HOST,
            "repository": "aiflux-customer", "tag": self.home.name.lower() + "-" + SOURCE[:12], "digest": digest}]
            and "syntax is ok" in text and "test is successful" in text, "customer_native_build_proof")
        self.check()
        write(self.home, "build.json", {"at_utc": now(), "run_id": ids[-1], "image": portals.HOST + "/aiflux-customer@" + digest,
            "output": output, "finish_time": run["finishTime"], "package_sha256": sha(self.home / "package.json"),
            "log_sha256": sha(self.home / "customer-build.log")})

    def built(self):
        self.check()
        built = load(self.home / "build.json")
        require(built["package_sha256"] == sha(self.home / "package.json")
            and re.fullmatch(re.escape(portals.HOST + "/aiflux-customer@sha256:") + "[a-f0-9]{64}", built["image"])
            and sha(self.home / "customer-build.log") == built["log_sha256"]
            and load(self.home / "build-exit.json")["exit_code"] == 0, "real_build_binding")
        run = rt.cli(["acr", "task", "show-run", "--registry", portals.REGISTRY, "--run-id", built["run_id"], "--subscription", rt.SUB])
        tag = self.home.name.lower() + "-" + SOURCE[:12]
        meta = rt.cli(["acr", "manifest", "show-metadata", "--registry", portals.REGISTRY, "--name", "aiflux-customer:" + tag, "--subscription", rt.SUB])
        expected = [{"registry": portals.HOST, "repository": "aiflux-customer", "tag": tag, "digest": built["image"].split("@", 1)[1]}]
        require(run["status"] == "Succeeded" and run["finishTime"] == built["finish_time"]
            and run.get("outputImages") == built["output"] == expected
            and meta["digest"] == expected[0]["digest"], "actual_remote_customer_build")
        return built

    def plan(self):
        # Future preparation only. A real immutable output is mandatory; no placeholder plan.
        built = self.built()
        require(built["package_sha256"] == sha(self.home / "package.json") and not self.root.exists(), "real_build_fresh_plan_required")
        before = collect()
        require(before["baseline"] == load(self.home / "capture.json")["baseline"], "preplan_baseline_drift")
        image = built["image"]
        self.root.mkdir(parents=True)
        for p in (rt.ROOT / "infra/terraform").iterdir():
            if p.is_file() and (p.name.endswith((".tf", ".tf.json")) or p.name == ".terraform.lock.hcl"):
                shutil.copyfile(p, self.root / p.name)
        for name in ("infra/models", "gateway/catalog", "gateway/policies"):
            shutil.copytree(rt.ROOT / name, self.home / name, ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tfplan", "__pycache__"))
        for p in (rt.ROOT / "gateway").glob("*.json"):
            shutil.copyfile(p, self.home / "gateway" / p.name)
        variables = portals.runtime_variables({"portals": ["customer"], "results": {"customer": {"image": image}}}, before["baseline"]["runtime"])
        variables.update(ingestion_container_image=before["baseline"]["runtime"]["sites"]["ingestion"]["image"].removeprefix("DOCKER|"),
            ingestion_enabled=True, ingestion_timer_enabled=True, ingestion_start_at=before["baseline"]["cutoff"], ingestion_catalog_accepted=True)
        write(self.home, "inputs.tfvars.json", variables)
        settings = fs.current_settings()
        require({k: fs.sha(v) for k, v in settings.items()} == before["baseline"]["settings_hashes"], "four_full_settings_hashes")
        preserved = fs.preserved_web_settings(settings)
        write(self.root, "send_preserved.tf.json", {"locals": {"send_settings": fs.literal(preserved)}})
        write(self.root, "zzzz_send_override.tf.json", {"resource": {"azurerm_linux_web_app": {"main": {"app_settings": "${local.send_settings[each.key]}"}}}})
        args = ["-var-file=" + str(p) for p in (rt.HOME / "rebuild-platform.tfvars.json", self.home / "inputs.tfvars.json", rt.HOME / "jwt-runtime.tfvars.json")]
        with terraform_environment(self.root):
            fs.terraform(self.root, "init", "-input=false", "-lockfile=readonly", "-no-color", "-backend-config=" + str(rt.ROOT / "infra/terraform/backend.hcl"))
            fs.terraform(self.root, "validate", "-no-color")
            require(fs.terraform(self.root, "workspace", "show").strip() == "default", "default_workspace")
            write(self.home, "plan-intent.json", {"at_utc": now(), "target": ADDRESS, "apply_authorized": False})
            fs.terraform(self.root, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *args, "-target=" + ADDRESS, "-out=" + str(self.target))
            fs.terraform(self.root, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *args, "-out=" + str(self.full))
            target, full = login.parsed(self.root, self.target), login.parsed(self.root, self.full)
        resolved = login.resolve(target, full, {ADDRESS})
        guard(resolved, image, before["baseline"], preserved["customer"])
        after = collect()
        require(all(after[k] == before[k] for k in ("baseline", "supplemental", "state_owner", "revisions", "current_api_sha256", "storage_sha256")), "protected_drift_during_planning")
        write(self.home, "plan-review.json", {"at_utc": now(), "status": "NOT_VALIDATED_NO_APPLY", "target_sha256": sha(self.target),
            "companion_never_apply_sha256": sha(self.full), "image": image, "package_sha256": sha(self.home / "package.json"),
            "artifacts": {p.relative_to(self.home).as_posix(): sha(p) for p in [self.target, self.full, self.home / "inputs.tfvars.json", *self.root.glob("*.tf"), *self.root.glob("*.tf.json"), self.root / ".terraform.lock.hcl"]}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "check", "build", "plan"))
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    release = Release(args.name)
    try:
        getattr(release, args.stage)()
        print(json.dumps({"stage": args.stage, "evidence": release.home.relative_to(rt.ROOT).as_posix(), "completed_at_utc": now()}), flush=True)
        return 0
    except Exception as exc:
        # No raw Azure error, settings, tokens, body or Terraform output is exported.
        if release.home.exists():
            write(release.home, "failure-" + args.stage + "-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json",
                  {"at_utc": now(), "error_type": type(exc).__name__, "http_status": getattr(exc, "code", None),
                   "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed", "retry_authorized": False})
        print(json.dumps({"stage": args.stage, "status": "BLOCKED_RECONCILE_NO_RETRY", "error_type": type(exc).__name__}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())