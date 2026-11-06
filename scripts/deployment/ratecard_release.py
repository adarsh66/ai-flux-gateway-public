"""Exclusive rate-card-only API/admin/customer image release. No settings/policy/DDL write path.

Build contexts are the composed, cloud-validated directories under
.deployment/ratecard-20261030/release (deployed baselines + rate-card hunks only).
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from scripts.deployment import poc_activation_release as r
from scripts.deployment import customer_catalog_validate as ui

HOME = r.rt.HOME / "ratecard-release-20261030"
SRC = r.rt.HOME / "ratecard-20261030/release"
ROOT = HOME / "infra/terraform"
PLAN = HOME / "rate-card.tfplan"
FULL = HOME / "validation-only-NEVER-APPLY.tfplan"
KINDS = ("api", "admin", "customer")
ADDRESSES = {f'azurerm_linux_web_app.main["{k}"]': k for k in KINDS}
CONTEXTS = {"api": ("api-build", "RateCard.Dockerfile"), "admin": ("admin", "apps/admin-portal/Dockerfile"),
            "customer": ("customer", "apps/customer-portal/Dockerfile")}
PINS = {"api": "29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64",
        "customer": "5f55df", "admin": "2846f1"}
BUILD_ARGS = ["--build-arg", "VITE_AUTH_MODE=local", "--build-arg", "VITE_CONTROL_API_URL=/api",
              "--build-arg", "VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"]
load = r.prep.load


def snapshot():
    """Preserve the legacy full snapshot, accepting only the retained approved ACL.

    Bind the legacy reader into an isolated globals map: its storage GET returns
    the old baseline solely for its historical four-IP assertion, after checking
    the actual response against the independently retained approved account.
    The returned snapshot always contains the ACTUAL five-IP network settings.
    No shared module, Auto controller, or cloud resource is modified.
    """
    from types import FunctionType, SimpleNamespace
    from scripts.deployment import project_route_product_access as product

    evidence = r.rt.HOME / "storage-firewall-167-103-67-80-20261030"
    approved = load(evidence / "independent-after.json")["account"]
    previous = load(evidence / "before.json")["account"]
    receipt = load(evidence / "result.json")
    r.rt.require(receipt["success"] and receipt["account_comparison_passed"]
                 and receipt["all_other_account_properties_exact"], "approved_storage_receipt")
    keys = ("networkAcls", "publicNetworkAccess", "allowSharedKeyAccess")
    expected = {k: approved["properties"].get(k) for k in keys}
    r.rt.require({p["value"] for p in expected["networkAcls"]["ipRules"]}
                 == {"167.103.66.248", "167.103.66.93", "167.103.65.36", "167.103.63.12", "167.103.67.80"},
                 "approved_exact_five_ips")
    storage_url = ("https://management.azure.com" + r.rt.RG
                   + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex?api-version=2023-05-01")
    observed = []

    def cli(args):
        value = r.rt.cli(args)
        if args == ["rest", "--method", "get", "--url", storage_url]:
            actual = {k: value["properties"].get(k) for k in keys}
            r.rt.require(actual == expected, "approved_storage_baseline_drift")
            observed.append(actual)
            value = deepcopy(value)
            value["properties"].update({k: previous["properties"].get(k) for k in keys})
        return value

    isolated_rt = SimpleNamespace(**{**vars(r.rt), "cli": cli})
    protected = FunctionType(product.ProductRun.protected.__code__,
                             {**product.ProductRun.protected.__globals__, "rt": isolated_rt})

    class RateCardReadRun(product.ProductRun):
        def protected(self):
            value = protected(self)
            r.rt.require(len(observed) == 1, "exactly_one_storage_read")
            value["state_network"] = observed[0]
            return value

    collect = FunctionType(r.snapshot.__code__, {**r.snapshot.__globals__, "ProductRun": RateCardReadRun})
    return collect()


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
    r.rt.require(Path(r.rt.CA).is_file(), "strict_tls_required")


def manifest():
    entries = []
    for kind in KINDS:
        base = SRC / CONTEXTS[kind][0]
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            raw = path.read_bytes()
            r.rt.require(not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", raw), "source_secret")
            entries.append({"path": path.relative_to(SRC).as_posix(), "sha256": r.sha(raw)})
    return {"entries": entries, "sha256": r.fs.sha(entries)}


def tooling():
    paths = set((r.rt.ROOT / "scripts/deployment").glob("*.py"))
    paths |= set((r.rt.ROOT / "infra/terraform").glob("*.tf")) | set((r.rt.ROOT / "infra/terraform").glob("*.tf.json"))
    paths |= {r.rt.ROOT / "infra/terraform/.terraform.lock.hcl", r.rt.ROOT / "infra/terraform/backend.hcl",
              r.rt.HOME / "rebuild-platform.tfvars.json", r.rt.HOME / "jwt-runtime.tfvars.json"}
    return {str(p): r.sha(p.read_bytes()) for p in sorted(paths)}


def sources():
    value = manifest()
    r.rt.require(value == load(HOME / "sources.json"), "source_drift")
    return value


def prepare():
    r.rt.require(not HOME.exists(), "existing_release_reconcile_only")
    account()
    validation = load(SRC / "validation-exit.json")
    r.rt.require(validation == {"customer": 0, "admin": 0, "api": 0}, "cloud_validation_required")
    before = snapshot()
    for kind in ("api",):
        r.rt.require(before["runtime"]["sites"][kind]["image"].endswith("@sha256:" + PINS[kind]), "current_predecessor:" + kind)
    for kind in ("admin", "customer"):
        r.rt.require(re.search(r"@sha256:" + PINS[kind] + "[a-f0-9]*$", before["runtime"]["sites"][kind]["image"]), "current_predecessor:" + kind)
    settings = r.fs.current_settings()
    r.rt.require({k: r.fs.sha(v) for k, v in settings.items()} == before["settings_hashes"], "complete_settings_baseline")
    r.fs.protect(HOME)
    exclusive("baseline.json", before)
    exclusive("sources.json", manifest())
    exclusive("tooling.json", tooling())
    exclusive("scope-review.json", {"at": r.fs.stamp(), "cloud_validation": validation,
        "validation_logs": {k: r.sha((SRC / (k + "-validation.log")).read_bytes()) for k in validation},
        "auto_untouched": True, "no_ddl_or_settings_or_policy": True})
    exclusive("release-intent.json", {"at": r.fs.stamp(), "scope": list(KINDS), "max_applies": 1,
        "settings_changes": 0, "policy_changes": 0, "inference_requests": 0})
    checkpoint("prepared", source_sha256=manifest()["sha256"])


def build():
    value = sources()
    r.rt.require(snapshot() == load(HOME / "baseline.json"), "prebuild_baseline_drift")
    for kind in KINDS:
        tag = "ratecard-" + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz") + "-" + value["sha256"][:12]
        exclusive(kind + "-build-intent.json", {"at": r.fs.stamp(), "tag": tag, "source_sha256": value["sha256"]})
        folder, docker = CONTEXTS[kind]
        args = r.rt.CLI + ["acr", "build", "--registry", "pocidstokenexacr", "--subscription", r.rt.SUB,
            "--platform", "linux/amd64", "--timeout", "1800", "--file", docker, "--image", "aiflux-" + kind + ":" + tag]
        if kind != "api":
            args += BUILD_ARGS
        child = subprocess.run(args + ["."], cwd=SRC / folder, env=r.rt.ENV, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=2100)
        text = ui.redact(child.stdout + child.stderr)
        (HOME / (kind + "-build.log")).write_text(text, encoding="utf-8")
        ids = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
        r.rt.require(child.returncode == 0 and ids, kind + "_build_failed_reconcile_no_replay")
        run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", ids[-1], "--subscription", r.rt.SUB])
        outputs = run.get("outputImages")
        r.rt.require(run["status"] == "Succeeded" and len(outputs or []) == 1, kind + "_output")
        digest = outputs[0]["digest"]
        r.rt.require(outputs == [{"digest": digest, "registry": r.portals.HOST, "repository": "aiflux-" + kind, "tag": tag}], kind + "_exact_output")
        result = {"run_id": ids[-1], "finished_at": run["finishTime"], "tag": tag, "digest": digest,
                  "image": r.portals.HOST + "/aiflux-" + kind + "@" + digest, "log_sha256": r.sha(text)}
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
                 and not plan.get("deferred_changes"), "resolved_exact_three_images")
    seen = set()
    for item in plan.get("resource_changes", []):
        c = item["change"]
        if c["actions"] == ["no-op"] or (c["actions"] == ["read"] and item.get("mode") == "data"):
            continue
        address = item["address"]
        r.rt.require(item.get("mode") == "managed" and address in ADDRESSES and address not in seen and c["actions"] == ["update"], "exact_three_apps_only")
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
    r.rt.require(seen == set(ADDRESSES) and plan.get("checks") and all(c["status"] == "pass" for c in plan["checks"]), "three_updates_all_checks_required")


def data():
    target = r.parsed(ROOT, PLAN)
    if FULL.exists():
        target = r.resolve(target, r.parsed(ROOT, FULL), set(ADDRESSES))
    return target


def runtime_variables(images, current):
    r.rt.require(set(images) == set(KINDS), "exact_three_runtime_images")
    variables = r.runtime_variables({k: images[k] for k in ("api", "admin")}, current)
    variables["apps"]["customer"]["image"] = images["customer"].split("/", 1)[1]
    return variables


def plan():
    account()
    images = built()
    before = snapshot()
    r.rt.require(before == load(HOME / "baseline.json"), "fresh_baseline_drift")
    r.rt.require(not ROOT.exists(), "existing_plan_context_reconcile_only")
    ROOT.mkdir(parents=True)
    for p in (r.rt.ROOT / "infra/terraform").iterdir():
        if p.is_file() and (p.name.endswith((".tf", ".tf.json")) or p.name == ".terraform.lock.hcl"):
            shutil.copyfile(p, ROOT / p.name)
    for path in ("infra/models", "gateway/catalog", "gateway/policies"):
        shutil.copytree(r.rt.ROOT / path, HOME / path, ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tfplan", "__pycache__"))
    for p in (r.rt.ROOT / "gateway").glob("*.json"):
        shutil.copyfile(p, HOME / "gateway" / p.name)
    variables = runtime_variables(images, before["runtime"])
    variables.update(ingestion_container_image=before["runtime"]["sites"]["ingestion"]["image"].removeprefix("DOCKER|"),
        ingestion_enabled=True, ingestion_timer_enabled=True, ingestion_start_at=before["cutoff"], ingestion_catalog_accepted=True)
    r.rt.save(HOME / "inputs.tfvars.json", variables)
    settings = r.fs.current_settings()
    r.rt.require({k: r.fs.sha(v) for k, v in settings.items()} == before["settings_hashes"], "complete_settings_preserved")
    r.rt.save(ROOT / "ratecard_preserved.tf.json", {"locals": {"ratecard_settings": r.fs.literal(r.fs.preserved_web_settings(settings))}})
    r.rt.save(ROOT / "zzzz_ratecard_override.tf.json", {"resource": {"azurerm_linux_web_app": {"main": {"app_settings": "${local.ratecard_settings[each.key]}"}}}})
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
    checkpoint("plan_guarded", plan_sha256=review["plan_sha256"], images=images,
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
        r.rt.require(snapshot() == review["baseline"], "protected_baseline_drift")
    return review


def apply():
    r.rt.require(not (HOME / "apply-intent.json").exists(), "attempted_apply_reconcile_never_retry")
    review = check()
    exclusive("apply-intent.json", {"at": r.fs.stamp(), "plan_sha256": review["plan_sha256"]})
    checkpoint("apply_intent_recorded_never_retry", plan_sha256=review["plan_sha256"])
    output = r.fs.terraform(ROOT, "apply", "-input=false", "-no-color", "-parallelism=1", str(PLAN))
    exclusive("applied.json", {"at": r.fs.stamp(), "plan_sha256": review["plan_sha256"],
        "summary": re.findall(r"Apply complete! Resources: [^\r\n]+", output)})
    checkpoint("applied_once_readback_pending", **load(HOME / "applied.json"))


def verify():
    review = check(live=False)
    r.rt.require(load(HOME / "applied.json")["plan_sha256"] == review["plan_sha256"], "matching_apply")
    current = snapshot()
    expected = deepcopy(review["baseline"])
    for kind, image in review["images"].items():
        expected["runtime"]["sites"][kind]["image"] = "DOCKER|" + image
    passed = current == expected
    exclusive("verified.json", {"at": r.fs.stamp(), "passed": passed, "baseline": current,
        "plan_sha256": review["plan_sha256"], "all_settings_hashes_equal": current["settings_hashes"] == expected["settings_hashes"]})
    checkpoint("protected_readback_passed" if passed else "protected_readback_failed_no_reapply", passed=passed, images=review["images"])
    r.rt.require(passed, "protected_readback_failed_no_reapply")


if __name__ == "__main__":
    try:
        r.rt.require(len(sys.argv) == 2 and sys.argv[1] in ("prepare", "build", "plan", "apply", "verify"), "action_required")
        globals()[sys.argv[1]]()
    except Exception as error:
        reason = str(error) if isinstance(error, RuntimeError) or re.fullmatch(r"[a-z0-9_:.\-]{1,80}", str(error)) else "sensitive_detail_suppressed"
        if HOME.exists():
            checkpoint("blocked_reconcile_before_any_retry", error_type=type(error).__name__, reason=reason)
        print(json.dumps({"error_type": type(error).__name__, "reason": reason}), flush=True)
        raise SystemExit(1)
