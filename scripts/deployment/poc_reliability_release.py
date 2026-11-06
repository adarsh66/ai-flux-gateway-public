"""Fresh exact API-only release; never replay activation runtime or policy plans."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import sys

from scripts.deployment import poc_activation_release as r
from scripts.deployment import poc_reliability_native as native
from scripts.deployment.catalog_pricing_release import guard

HOME = native.HOME / "api-release"
ROOT = HOME / "infra/terraform"
PLAN = HOME / "api-only.tfplan"
ADDRESS = 'azurerm_linux_web_app.main["api"]'


def tooling():
    paths = {Path(__file__), Path(native.__file__), r.rt.ROOT / "scripts/deployment/poc_reliability_validation.py",
             r.rt.ROOT / "tests/unit/test_poc_reliability_release.py"}
    paths |= set((r.rt.ROOT / "infra/terraform").glob("*.tf")) | set((r.rt.ROOT / "infra/terraform").glob("*.tf.json"))
    paths |= {r.rt.ROOT / "infra/terraform/.terraform.lock.hcl", r.rt.ROOT / "infra/terraform/backend.hcl",
              r.rt.HOME / "rebuild-platform.tfvars.json", r.rt.HOME / "jwt-runtime.tfvars.json"}
    return {str(p): r.sha(p.read_bytes()) for p in paths}


def built():
    sources = native.check()
    item = r.prep.load(native.HOME / "api-build.json")
    r.rt.require(item["source_sha256"] == sources["sha256"], "build_source_binding")
    run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", item["run_id"], "--subscription", r.rt.SUB])
    meta = r.rt.cli(["acr", "manifest", "show-metadata", "--registry", r.portals.REGISTRY,
                    "--name", "aiflux-api:" + item["tag"], "--subscription", r.rt.SUB])
    r.rt.require(run["status"] == "Succeeded" and run["finishTime"] == item["finished_at"] and meta["digest"] == item["digest"]
        and run["outputImages"] == [{"digest": item["digest"], "registry": r.portals.HOST, "repository": "aiflux-api", "tag": item["tag"]}], "immutable_api_build")
    return item


def strict(plan, image, baseline):
    guard(plan, image)
    for item in plan["resource_changes"]:
        if item["address"] == ADDRESS:
            old = item["change"]["before"]["site_config"][0]["application_stack"][0]
            r.rt.require("DOCKER|" + r.portals.HOST + "/" + old["docker_image_name"] == baseline["runtime"]["sites"]["api"]["image"], "exact_current_api_predecessor")
    r.rt.require(all(c["status"] == "pass" for c in plan.get("checks", [])), "every_check_passed")


def data():
    result = r.parsed(ROOT, PLAN)
    companion = HOME / "validation-only-NEVER-APPLY.tfplan"
    if companion.exists():
        result = r.resolve(result, r.parsed(ROOT, companion), {ADDRESS})
    return result


def plan():
    r.rt.require(not HOME.exists(), "existing_release_reconcile_only")
    item = built()
    before = r.snapshot()
    r.rt.require(before == r.prep.load(native.HOME / "baseline.json"), "fresh_authorized_baseline_drift")
    r.require_publisher(r.collect())
    r.fs.protect(HOME)
    ROOT.mkdir(parents=True, exist_ok=False)
    for path in (r.rt.ROOT / "infra/terraform").iterdir():
        if path.is_file() and (path.name.endswith((".tf", ".tf.json")) or path.name == ".terraform.lock.hcl"):
            shutil.copyfile(path, ROOT / path.name)
    for path in ("infra/models", "gateway/catalog", "gateway/policies"):
        shutil.copytree(r.rt.ROOT / path, HOME / path, ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tfplan", "__pycache__"))
    for path in (r.rt.ROOT / "gateway").glob("*.json"):
        shutil.copyfile(path, HOME / "gateway" / path.name)
    current = before["runtime"]
    variables = r.portals.runtime_variables({"portals": ["admin", "customer"], "results": {
        k: {"image": current["sites"][k]["image"].removeprefix("DOCKER|")} for k in ("admin", "customer")}}, current)
    variables["apps"]["api"]["image"] = item["image"].split("/", 1)[1]
    variables.update(ingestion_container_image=current["sites"]["ingestion"]["image"].removeprefix("DOCKER|"),
                     ingestion_enabled=True, ingestion_timer_enabled=True, ingestion_start_at=before["cutoff"], ingestion_catalog_accepted=True)
    r.rt.save(HOME / "inputs.tfvars.json", variables)
    settings = r.fs.current_settings()
    r.rt.require({k: r.fs.sha(v) for k, v in settings.items()} == before["settings_hashes"], "all_settings_current_baseline")
    r.rt.save(ROOT / "poc_preserved.tf.json", {"locals": {"poc_release_settings": r.fs.literal(r.fs.preserved_web_settings(settings))}})
    r.rt.save(ROOT / "zzzz_poc_override.tf.json", {"resource": {"azurerm_linux_web_app": {"main": {"app_settings": "${local.poc_release_settings[each.key]}"}}}})
    r.exclusive(HOME, "baseline.json", before)
    args = ["-var-file=" + str(p) for p in (r.rt.HOME / "rebuild-platform.tfvars.json", HOME / "inputs.tfvars.json", r.rt.HOME / "jwt-runtime.tfvars.json")]
    r.fs.terraform(ROOT, "init", "-input=false", "-lockfile=readonly", "-no-color", "-backend-config=" + str(r.rt.ROOT / "infra/terraform/backend.hcl"))
    r.rt.require(r.fs.terraform(ROOT, "workspace", "show").strip() == "default", "default_workspace")
    r.fs.terraform(ROOT, "validate", "-no-color")
    r.exclusive(HOME, "plan-intent.json", {"at": r.fs.stamp(), "scope": "one_api_image_only", "max_applies": 1})
    r.fs.terraform(ROOT, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *args, "-target=" + ADDRESS, "-out=" + str(PLAN))
    target = r.parsed(ROOT, PLAN)
    if any(c["status"] != "pass" for c in target.get("checks", [])):
        r.exclusive(HOME, "companion-intent.json", {"at": r.fs.stamp(), "target_sha256": r.sha(PLAN.read_bytes()), "never_apply": True})
        r.fs.terraform(ROOT, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *args, "-out=" + str(HOME / "validation-only-NEVER-APPLY.tfplan"))
    strict(data(), item["image"], before)
    paths = [PLAN, HOME / "inputs.tfvars.json", *ROOT.glob("*.tf"), *ROOT.glob("*.tf.json"), ROOT / ".terraform.lock.hcl"]
    if (HOME / "validation-only-NEVER-APPLY.tfplan").exists():
        paths.append(HOME / "validation-only-NEVER-APPLY.tfplan")
    review = {"at": r.fs.stamp(), "plan_sha256": r.sha(PLAN.read_bytes()), "image": item["image"], "baseline": before,
              "tooling": tooling(), "source_sha256": native.check()["sha256"], "artifacts": {str(p): r.sha(p.read_bytes()) for p in paths}}
    r.exclusive(HOME, "review.json", review)
    print(json.dumps({k: review[k] for k in ("at", "plan_sha256", "image", "source_sha256")}), flush=True)


def check(live=True):
    review = r.prep.load(HOME / "review.json")
    r.rt.require(review["tooling"] == tooling() and review["source_sha256"] == native.check()["sha256"] and
                 review["plan_sha256"] == r.sha(PLAN.read_bytes()) and all(r.sha(Path(p).read_bytes()) == h for p, h in review["artifacts"].items()), "source_plan_input_binding")
    strict(data(), review["image"], review["baseline"])
    if live:
        r.rt.require(built()["image"] == review["image"], "current_build_binding")
        r.rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at"]) < timedelta(hours=2), "stale_plan")
        r.rt.require(r.snapshot() == review["baseline"], "complete_current_baseline_drift")
    return review


def apply():
    r.rt.require(not (HOME / "apply-intent.json").exists(), "existing_apply_intent_reconcile_only")
    review = check()
    proof = r.prep.load(HOME / "validation.json")
    doc = (r.rt.ROOT / ".azure/deployment-plan.md").read_text()
    r.rt.require(proof["checks_passed"] and proof["plan_sha256"] == review["plan_sha256"] and proof["tooling"] == tooling()
        and proof["at"] in doc and review["plan_sha256"] in doc and "Publisher reliability correction status: Validated." in doc
        and r.prep.load(r.rt.ROOT / ".azure/validate-status.json")["completedStep"] == "UpdateStatus", "actual_independent_validation_required")
    r.exclusive(HOME, "apply-intent.json", {"at": r.fs.stamp(), "plan_sha256": review["plan_sha256"]})
    output = r.fs.terraform(ROOT, "apply", "-input=false", "-no-color", str(PLAN))
    r.exclusive(HOME, "applied.json", {"at": r.fs.stamp(), "plan_sha256": review["plan_sha256"], "summary": re.findall(r"Apply complete! Resources: [^\r\n]+", output)})
    print(json.dumps(r.prep.load(HOME / "applied.json")), flush=True)


def verify():
    review = check(live=False)
    r.rt.require(r.prep.load(HOME / "applied.json")["plan_sha256"] == review["plan_sha256"], "matching_apply")
    current = r.snapshot()
    expected = deepcopy(review["baseline"])
    expected["runtime"]["sites"]["api"]["image"] = "DOCKER|" + review["image"]
    r.rt.require(current == expected, "complete_protected_baseline_api_image_only")
    r.exclusive(HOME, "verified.json", {"at": r.fs.stamp(), "passed": True, "baseline": current,
        "plan_sha256": review["plan_sha256"], "image": review["image"], "inference_requests": 0})
    print(json.dumps({"passed": True, "plan_sha256": review["plan_sha256"], "image": review["image"]}), flush=True)


if __name__ == "__main__":
    {"plan": plan, "apply": apply, "verify": verify}[sys.argv[1]]()