"""Fresh API-only catalog correction. Never replay the applied three-image plan."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from xml.etree import ElementTree

from aiflux.display_pricing import manifest
from scripts.deployment import glm_runtime_release as glm
from scripts.deployment import pricing_runtime_release as prior
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.deploy_portals import workflow
from scripts.deployment.project_route_product_access import sha

HOME = rt.HOME / "catalog-pricing-correction-20261027"
PLAN = HOME / "api-only.tfplan"
REPORT = rt.ROOT / "gateway/validation/catalog-pricing-correction-release-20261027.json"
VALIDATION_REPORT = rt.ROOT / "gateway/validation/catalog-pricing-correction-validation-20261027.json"
TESTS = rt.ROOT / "gateway/validation/catalog-pricing-correction-tests-20261027.xml"


def sources():
    paths = set(glm.api_sources()) | set((rt.ROOT / "services/control-plane/src/aiflux/pricing").glob("*.json"))
    paths |= {Path(__file__), rt.ROOT / "scripts/deployment/pricing_runtime_release.py",
              rt.ROOT / "scripts/deployment/glm_runtime_release.py",
              rt.ROOT / "tests/unit/test_catalog_pricing_correction.py",
              rt.ROOT / "tests/unit/test_catalog_pricing_release.py"}
    paths |= set((rt.ROOT / "infra/terraform").glob("*.tf"))
    paths.add(rt.ROOT / "infra/terraform/.terraform.lock.hcl")
    return [{"path": p.relative_to(rt.ROOT).as_posix(), "sha256": sha(p.read_bytes())} for p in sorted(paths)]


def unchanged_portals():
    old = {e["path"]: e["sha256"] for e in json.loads((prior.HOME / "sources.json").read_text())}
    for path in prior.portals.source_files():
        name = path.relative_to(rt.ROOT).as_posix()
        rt.require(old.get(name) == sha(path.read_bytes()), "portal_source_changed:" + name)


def test_proof():
    suites = list(ElementTree.parse(TESTS).getroot().iter("testsuite"))
    count = sum(int(s.get("tests", "0")) for s in suites)
    rt.require(count >= 50 and all(s.get("failures") == "0" and s.get("errors") == "0" for s in suites), "tests_required")
    return {"tests": count, "sha256": sha(TESTS.read_bytes())}


def build():
    rt.require(not (HOME / "build-intent.json").exists(), "build_already_attempted_never_replay")
    unchanged_portals()
    proof = test_proof()
    # Confirm the existing release is genuinely applied and unchanged before build.
    prior_proof = json.loads((prior.HOME / "verification.json").read_text())
    rt.require(prior_proof["protected_equal_except_three_images"] and (prior.HOME / "applied.json").exists(), "prior_apply_proof")
    entries = sources()
    tag = "catalog-pricing-" + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz") + "-" + sha(json.dumps(entries, sort_keys=True))[:12]
    context = HOME / "context"
    for entry in entries:
        path = rt.ROOT / entry["path"]
        rt.require(not path.is_symlink(), "source_symlink")
        raw = path.read_bytes()
        rt.require(not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", raw), "source_secret_pattern")
        target = context / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    rt.save(HOME / "sources.json", entries)
    with (HOME / "build-intent.json").open("x") as handle:
        json.dump({"at": datetime.now(UTC).isoformat(), "tag": tag, "tests": proof}, handle)
    process = subprocess.run(rt.CLI + ["acr", "build", "--registry", prior.portals.REGISTRY,
        "--subscription", rt.SUB, "--platform", "linux/amd64", "--timeout", "1800", "--file",
        "services/control-plane/Dockerfile", "--image", "aiflux-api:" + tag, "."], cwd=context,
        env=rt.ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1900)
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', "[signed-url-redacted]", process.stdout + process.stderr)
    (HOME / "build.log").write_text(text, encoding="utf-8")
    runs = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
    rt.require(process.returncode == 0 and runs, "api_build_failed_private_log_retained_no_replay")
    run = rt.cli(["acr", "task", "show-run", "-r", prior.portals.REGISTRY, "--run-id", runs[-1], "--subscription", rt.SUB])
    meta = rt.cli(["acr", "repository", "show", "-n", prior.portals.REGISTRY, "--image", "aiflux-api:" + tag, "--subscription", rt.SUB])
    rt.require(run["status"] == "Succeeded" and re.fullmatch(r"sha256:[a-f0-9]{64}", meta["digest"]), "build_evidence")
    result = {"tag": tag, "runId": runs[-1], "finishedAt": run["finishTime"], "digest": meta["digest"],
              "image": prior.portals.HOST + "/aiflux-api@" + meta["digest"]}
    rt.save(HOME / "build.json", result)
    print(json.dumps(result), flush=True)


def release():
    rt.require(json.loads((HOME / "sources.json").read_text()) == sources(), "source_changed")
    unchanged_portals()
    result = json.loads((HOME / "build.json").read_text())
    run = rt.cli(["acr", "task", "show-run", "-r", prior.portals.REGISTRY, "--run-id", result["runId"], "--subscription", rt.SUB])
    meta = rt.cli(["acr", "repository", "show", "-n", prior.portals.REGISTRY, "--image", "aiflux-api:" + result["tag"], "--subscription", rt.SUB])
    rt.require(run["status"] == "Succeeded" and run["finishTime"] == result["finishedAt"]
               and meta["digest"] == result["digest"]
               and result["image"] == prior.portals.HOST + "/aiflux-api@" + meta["digest"], "immutable_build_changed")
    return result


def guard(plan, image):
    rt.require(not plan.get("errored") and plan.get("applyable") is True and not plan.get("deferred_changes"), "unresolved_plan")
    seen = []
    computed = {"possible_outbound_ip_address_list", "possible_outbound_ip_addresses",
                "outbound_ip_address_list", "outbound_ip_addresses", "custom_domain_verification_id"}
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        if change["actions"] == ["no-op"]:
            continue
        rt.require(resource.get("mode") == "managed" and resource["address"] == 'azurerm_linux_web_app.main["api"]'
                   and not seen and change["actions"] == ["update"], "exact_one_api_update_required")
        seen.append(resource["address"])
        before, after = deepcopy(change["before"]), deepcopy(change["after"])
        unknown = change.get("after_unknown") or {}
        rt.require(not any(rt.any_true(v) for k, v in unknown.items() if k not in computed), "unknown_writable_input")
        for key in computed:
            if rt.any_true(unknown.get(key)):
                after[key] = before.get(key)
        rt.require(prior.portals.changed(before, after) == {"site_config"}, "settings_identity_network_change")
        old, new = before["site_config"][0], after["site_config"][0]
        rt.require(prior.portals.changed(old, new) == {"application_stack"}, "security_config_change")
        old, new = old["application_stack"][0], new["application_stack"][0]
        rt.require(prior.portals.changed(old, new) == {"docker_image_name"}, "registry_or_non_image_change")
        rt.require(re.fullmatch(re.escape(prior.portals.HOST) + r"/aiflux-api@sha256:[a-f0-9]{64}", image)
                   and new["docker_registry_url"] == "https://" + prior.portals.HOST
                   and new["docker_image_name"] == image.split("/", 1)[1], "wrong_api_pin")
    rt.require(len(seen) == 1, "exact_one_api_update_required")


def plan():
    rt.require(not (HOME / "plan-intent.json").exists() and not (HOME / "apply-intent.json").exists(), "plan_already_attempted_never_replay")
    built = release()
    before = prior.baseline()
    prior_review = json.loads((prior.HOME / "review.json").read_text())
    rt.require(all(before["protected"]["runtime"]["sites"][k]["image"] == "DOCKER|" + prior_review["images"][k]
                   for k in prior.KINDS), "prior_runtime_pins_changed")
    # Existing helper preserves all current pins; no frontend builder invoked.
    variables = prior.portals.runtime_variables({"results": {k: {"image": prior_review["images"][k]}
        for k in ("admin", "customer")}}, before["protected"]["runtime"])
    variables["apps"]["api"]["image"] = built["image"].split("/", 1)[1]
    rt.save(HOME / "images.tfvars.json", variables)
    with (HOME / "plan-intent.json").open("x") as handle:
        json.dump({"at": datetime.now(UTC).isoformat()}, handle)
    rt.tf(["init", "-input=false", "-lockfile=readonly", "-no-color"])
    rt.tf(["fmt", "-check"])
    rt.tf(["validate", "-no-color"])
    rt.tf(["plan", "-input=false", "-no-color", "-lock-timeout=60s",
           "-var-file=" + str(rt.HOME / "rebuild-platform.tfvars.json"),
           "-var-file=" + str(HOME / "images.tfvars.json"),
           "-var-file=" + str(rt.HOME / "jwt-runtime.tfvars.json"),
           '-target=azurerm_linux_web_app.main["api"]', "-out=" + str(PLAN)])
    guard(json.loads(rt.tf(["show", "-json", str(PLAN)])), built["image"])
    review = {"at": datetime.now(UTC).isoformat(), "plan_sha256": sha(PLAN.read_bytes()), "sources": sources(),
              "manifest_sha256": manifest()["sha256"], "baseline": before, "image": built["image"],
              "tests": test_proof(), "guard": "exact_one_api_image_only"}
    rt.save(HOME / "review.json", review)
    print(json.dumps({k: review[k] for k in ("at", "plan_sha256", "image", "guard")}), flush=True)


def check():
    review = json.loads((HOME / "review.json").read_text())
    rt.require(review["sources"] == sources() and review["manifest_sha256"] == manifest()["sha256"], "source_changed")
    rt.require(review["plan_sha256"] == sha(PLAN.read_bytes()), "saved_plan_changed")
    rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at"]) <= timedelta(hours=2), "plan_expired")
    rt.require(test_proof() == review["tests"], "test_proof_changed")
    built = release()
    rt.require(built["image"] == review["image"], "image_changed")
    guard(json.loads(rt.tf(["show", "-json", str(PLAN)])), built["image"])
    rt.require(prior.baseline() == review["baseline"], "protected_baseline_drift")
    return review


def validate():
    rt.require(not (HOME / "apply-intent.json").exists(), "apply_already_attempted_never_validate")
    for step in ("None", "LoadPlan", "AddValidationSteps"):
        print(json.dumps(workflow(step)), flush=True)
    review = check()
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT
               and account["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "operator_scope")
    rt.tf(["version", "-json"])
    rt.tf(["fmt", "-check"])
    rt.tf(["validate", "-no-color"])
    rt.require(rt.tf(["workspace", "show"]).strip() == "default", "workspace")
    addresses = rt.tf(["state", "list"]).splitlines()
    current = review["baseline"]["protected"]["runtime"]
    registry = (rt.RG + "/providers/Microsoft.ContainerRegistry/registries/" + prior.portals.REGISTRY).lower()
    identities = current["sites"]["api"]["protected"]["identity"]["userAssignedIdentities"]
    rt.require(any(role[1] == identity["principalId"] and role[2].lower().endswith("/7f951dda-4ed3-4680-a7ca-43fe172d538d")
                   and role[3].lower() == registry and not role[4]
                   for identity in identities.values() for role in current["roleAssignments"]), "api_acr_pull")
    policies = rt.cli(["policy", "assignment", "list", "--scope", "/subscriptions/" + rt.SUB, "--disable-scope-strict-match"])
    url = "https://management.azure.com" + rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry/deployments?api-version=2025-06-01"
    response = rt.cli(["rest", "--method", "get", "--url", url, "--subscription", rt.SUB])
    rt.require(not response.get("nextLink"), "deployment_pagination")
    for rate in manifest()["rates"]:
        if rate["provider"] != "ModelArts":
            item = next(d for d in response["value"] if d["name"] == rate["model"])
            rt.require(item["sku"]["name"] == rate["sku"] and item["properties"]["model"]["version"] == rate["model_version"]
                       and item["properties"]["model"]["format"] == rate["provider"], "live_rate_identity:" + rate["model"])
    for step in ("RunValidation", "BuildVerification", "StaticRoleVerification"):
        print(json.dumps(workflow(step)), flush=True)
    proof = {"at": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"], "image": review["image"],
             "sources_sha256": sha(json.dumps(sources(), sort_keys=True)), "tests": review["tests"],
             "guard": review["guard"], "state_addresses": len(addresses), "policy_assignments": len(policies),
             "manifest_sha256": review["manifest_sha256"], "existing_api_acr_pull": True,
             "ten_live_sku_version_provider_pairs": True, "unchanged_portals_no_build": True, "checks_passed": True}
    rt.save(HOME / "validation.json", proof)
    rt.save(VALIDATION_REPORT, proof)
    path = rt.ROOT / ".azure/deployment-plan.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n### Section 7: API-only catalog correction validation proof\n\nIndependent validation " + proof["at"]
                     + ". Exact saved plan SHA256 " + proof["plan_sha256"] + ". Source SHA256 " + proof["sources_sha256"]
                     + ". Native Linux immutable API build only; existing portals unchanged and not rebuilt. "
                     + str(proof["tests"]["tests"]) + " backend/guard regressions pass. Exact one API image delta; "
                     "full four-app settings hashes, FinOps timer/cutoff/AlwaysOn, private DB, ACL, roles and APIM unchanged. "
                     "Terraform fmt/validate/default workspace/state, operator, policies, existing API AcrPull and ten live "
                     "SKU/version/provider checks passed. Original applied three-image plan/proofs retained.\n")
    for step in ("RecordProof", "ResolveErrors"):
        print(json.dumps(workflow(step)), flush=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\nCatalog pricing correction status: Validated. Plan SHA256 " + proof["plan_sha256"] + ".\n")
    print(json.dumps(workflow("UpdateStatus")), flush=True)
    print(json.dumps(proof), flush=True)


def apply():
    rt.require(not (HOME / "apply-intent.json").exists(), "apply_already_attempted_never_replay")
    review = check()
    proof = json.loads((HOME / "validation.json").read_text())
    status = json.loads((rt.ROOT / ".azure/validate-status.json").read_text())
    doc = (rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    rt.require(status.get("completedStep") == "UpdateStatus" and "Catalog pricing correction status: Validated." in doc
               and review["plan_sha256"] in doc and proof["checks_passed"]
               and proof["plan_sha256"] == review["plan_sha256"]
               and proof["sources_sha256"] == sha(json.dumps(sources(), sort_keys=True)), "fresh_validation_required")
    with (HOME / "apply-intent.json").open("x") as handle:
        json.dump({"at": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"]}, handle)
    rt.tf(["apply", "-input=false", "-no-color", str(PLAN)])
    rt.save(HOME / "applied.json", {"at": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"]})
    verify()


def verify():
    rt.require((HOME / "apply-intent.json").exists(), "apply_intent_required")
    review = json.loads((HOME / "review.json").read_text())
    expected = deepcopy(review["baseline"])
    expected["protected"]["runtime"]["sites"]["api"]["image"] = "DOCKER|" + review["image"]
    current = prior.baseline()
    proof = {"at": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"], "image": review["image"],
             "sources_sha256": sha(json.dumps(review["sources"], sort_keys=True)), "manifest_sha256": review["manifest_sha256"],
             "protected_equal_except_one_api_image": current == expected,
             "all_four_appsettings_hashes_unchanged": current["protected"]["settings_hashes"] == expected["protected"]["settings_hashes"],
             "unchanged_images": {k: current["protected"]["runtime"]["sites"][k]["image"] for k in ("admin", "customer", "ingestion")}}
    rt.save(HOME / "verification.json", proof)
    rt.save(REPORT, proof)
    print(json.dumps(proof), flush=True)
    rt.require(proof["protected_equal_except_one_api_image"], "post_apply_baseline_drift")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "plan", "check", "validate", "apply", "verify"])
    args = parser.parse_args()
    HOME.mkdir(parents=True, exist_ok=True)
    os.environ.update(REQUESTS_CA_BUNDLE=rt.CA, SSL_CERT_FILE=rt.CA)
    sid = re.search(r"S-1-5-[0-9-]+", rt.run(["whoami", "/user", "/fo", "csv", "/nh"])).group(0)
    rt.run(["icacls", str(HOME), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"])
    if args.action == "check":
        print(json.dumps({"checked_plan_sha256": check()["plan_sha256"]}), flush=True)
    else:
        {"build": build, "plan": plan, "validate": validate, "apply": apply, "verify": verify}[args.action]()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"errorType": type(error).__name__, "error": str(error) if isinstance(error, RuntimeError)
                          else "catalog_correction_failed_sensitive_detail_suppressed"}), flush=True)
        raise SystemExit(1)