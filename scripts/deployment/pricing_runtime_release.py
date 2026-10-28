"""One-shot pricing release. Fresh exact three-image plan; never replay old plans.

Reuses existing native-Linux builders and exact-image delta guard, not historical
apply functions. Only hash protected settings in memory; no provider/key reads.
"""
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

from aiflux.display_pricing import manifest
from scripts.deployment import glm_runtime_release as glm
from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment.project_route_product_access import ProductRun, sha

HOME = rt.HOME / "pricing-runtime-20261027"
KINDS = ("api", "admin", "customer")


def sources():
    paths = set(glm.api_sources()) | set(portals.source_files())
    paths |= set((rt.ROOT / "services/control-plane/src/aiflux/pricing").glob("*.json"))
    paths |= {Path(__file__), rt.ROOT / "services/control-plane/src/aiflux/display_pricing.py"}
    return [{"path": p.relative_to(rt.ROOT).as_posix(), "sha256": sha(p.read_bytes())} for p in sorted(paths)]


def baseline():
    # Existing read-only protection includes four app settings hashes, all pins,
    # private PostgreSQL, state ACL, FinOps cutoff/timer/AlwaysOn, roles/identity.
    run = ProductRun()
    return {"protected": run.protected(), "apim_policy_sha256": sha(run.policy())}


def build_api():
    rt.require(not (HOME / "api-build-intent.json").exists(), "api_build_already_attempted_do_not_replay")
    entries = sources()
    source_hash = sha(json.dumps(entries, sort_keys=True))
    tag = "pricing-" + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz") + "-" + source_hash[:12]
    context = HOME / "api-context"
    for entry in entries:
        path = rt.ROOT / entry["path"]
        rt.require(not path.is_symlink(), "source_symlink")
        target = context / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    rt.save(HOME / "sources.json", entries)
    rt.save(HOME / "api-build-intent.json", {"tag": tag, "source_sha256": source_hash})
    p = subprocess.run(rt.CLI + ["acr", "build", "--registry", portals.REGISTRY, "--subscription", rt.SUB,
        "--platform", "linux/amd64", "--timeout", "1800", "--file", "services/control-plane/Dockerfile",
        "--image", "aiflux-api:" + tag, "."], cwd=context, env=rt.ENV,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1900)
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', "[signed-url-redacted]", p.stdout + p.stderr)
    (HOME / "api-build.log").write_text(text, encoding="utf-8")
    runs = re.findall(r"(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)", text)
    rt.require(p.returncode == 0 and runs, "api_remote_build_failed_private_log_retained")
    run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", runs[-1], "--subscription", rt.SUB])
    meta = rt.cli(["acr", "repository", "show", "-n", portals.REGISTRY, "--image", "aiflux-api:" + tag, "--subscription", rt.SUB])
    rt.require(run["status"] == "Succeeded" and re.fullmatch(r"sha256:[a-f0-9]{64}", meta["digest"]), "api_build_evidence")
    result = {"tag": tag, "runId": runs[-1], "status": run["status"], "finishedAt": run.get("finishTime"),
              "digest": meta["digest"], "image": portals.HOST + "/aiflux-api@" + meta["digest"]}
    rt.save(HOME / "api-result.json", result)
    print(json.dumps({"api": result}), flush=True)


def build_portals():
    rt.require(not (HOME / "portal-build-intent.json").exists(), "portal_build_already_attempted_do_not_replay")
    rt.save(HOME / "portal-build-intent.json", {"at": datetime.now(UTC).isoformat()})
    tag = portals.remote_build()
    rt.save(HOME / "portal-result.json", {"tag": tag})
    print(json.dumps({"portal_tag": tag}), flush=True)


def build_corrected_portals():
    # A new source-bound attempt, never erase or reuse the failed run marker.
    rt.require(not (HOME / "portal-correction-intent.json").exists(), "correction_already_attempted_do_not_replay")
    rt.require((HOME / "portal-build-intent.json").exists()
               and not (HOME / "portal-result.json").exists()
               and not (HOME / "apply-intent.json").exists(), "failed_validation_only")
    old = portals.HOME / "local-20261027t113450z-68cb39fc5d1d"
    log = (old / "validation-build.log").read_text(encoding="utf-8")
    rt.require("Tests  2 failed | 105 passed (107)" in log
               and not (old / "results.json").exists(), "failed_validation_evidence_required")
    run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY,
                  "--run-id", "cm1y", "--subscription", rt.SUB])
    rt.require(run["status"] == "Failed", "prior_validation_still_active_or_not_failed")
    rt.save(HOME / "portal-correction-intent.json", {"at": datetime.now(UTC).isoformat(),
            "predecessor_run": "cm1y", "reason": "correct stale disclosure assertion", "sources": sources()})
    tag = portals.remote_build()
    rt.save(HOME / "portal-result.json", {"tag": tag, "predecessor_run": "cm1y"})
    print(json.dumps({"portal_tag": tag}), flush=True)


def release():
    rt.require(json.loads((HOME / "sources.json").read_text()) == sources(), "release_source_changed")
    api = json.loads((HOME / "api-result.json").read_text())
    run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", api["runId"], "--subscription", rt.SUB])
    meta = rt.cli(["acr", "repository", "show", "-n", portals.REGISTRY, "--image", "aiflux-api:" + api["tag"], "--subscription", rt.SUB])
    rt.require(run["status"] == "Succeeded" and run.get("finishTime") == api["finishedAt"]
               and meta["digest"] == api["digest"], "api_build_or_pin_changed")
    portal_tag = json.loads((HOME / "portal-result.json").read_text())["tag"]
    built = portals.verify_release(portals.HOME / portal_tag)
    rt.require(portals.release_kinds(built) == ("admin", "customer"), "both_portals_required")
    return {"results": {"api": api, **{k: built["results"][k] for k in ("admin", "customer")}}}


def plan():
    rt.require(not (HOME / "apply-intent.json").exists(), "apply_already_attempted_never_replan_or_replay")
    built = release()
    before = baseline()
    rt.save(HOME / "baseline.json", before)
    current = before["protected"]["runtime"]
    variables = portals.runtime_variables({"results": built["results"]}, current)
    variables["apps"]["api"]["image"] = built["results"]["api"]["image"].split("/", 1)[1]
    rt.save(HOME / "images.tfvars.json", variables)
    rt.tf(["init", "-input=false", "-lockfile=readonly", "-no-color"])
    rt.tf(["fmt", "-check"])
    rt.tf(["validate", "-no-color"])
    rt.tf(["plan", "-input=false", "-no-color", "-lock-timeout=60s",
           "-var-file=" + str(rt.HOME / "rebuild-platform.tfvars.json"),
           "-var-file=" + str(HOME / "images.tfvars.json"),
           "-var-file=" + str(rt.HOME / "jwt-runtime.tfvars.json"),
           *['-target=azurerm_linux_web_app.main["' + k + '"]' for k in KINDS],
           "-out=" + str(HOME / "pricing.tfplan")])
    parsed = json.loads(rt.tf(["show", "-json", str(HOME / "pricing.tfplan")]))
    glm.guard(parsed, built)
    review = {"at": datetime.now(UTC).isoformat(), "plan_sha256": sha((HOME / "pricing.tfplan").read_bytes()),
              "sources": sources(), "manifest_sha256": manifest()["sha256"], "baseline": before,
              "images": {k: built["results"][k]["image"] for k in KINDS}, "guard": "exact_three_images_only"}
    rt.save(HOME / "review.json", review)
    print(json.dumps({k: review[k] for k in ("at", "plan_sha256", "manifest_sha256", "images", "guard")}), flush=True)


def check():
    review = json.loads((HOME / "review.json").read_text())
    rt.require(review["sources"] == sources() and review["manifest_sha256"] == manifest()["sha256"], "source_changed")
    rt.require(review["plan_sha256"] == sha((HOME / "pricing.tfplan").read_bytes()), "saved_plan_changed")
    age = datetime.now(UTC) - datetime.fromisoformat(review["at"])
    rt.require(timedelta(0) <= age <= timedelta(hours=2), "plan_expired")
    built = release()
    glm.guard(json.loads(rt.tf(["show", "-json", str(HOME / "pricing.tfplan")])), built)
    rt.require(baseline() == review["baseline"], "protected_live_baseline_drift")
    return review


def apply():
    rt.require(not (HOME / "apply-intent.json").exists(), "apply_already_attempted_do_not_replay")
    review = check()
    status = json.loads((rt.ROOT / ".azure/validate-status.json").read_text())
    doc = (rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    rt.require(status.get("completedStep") == "UpdateStatus" and "Pricing runtime status: Validated" in doc
               and review["plan_sha256"] in doc, "fresh_pricing_validation_required")
    # Exclusive durable marker BEFORE any apply. A failed/partial apply is never replayed.
    with (HOME / "apply-intent.json").open("x") as handle:
        json.dump({"at": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"]}, handle)
    rt.tf(["apply", "-input=false", "-no-color", str(HOME / "pricing.tfplan")])
    rt.save(HOME / "applied.json", {"at": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"]})
    verify()


def verify():
    review = json.loads((HOME / "review.json").read_text())
    current = baseline()
    expected = deepcopy(review["baseline"])
    for kind in KINDS:
        expected["protected"]["runtime"]["sites"][kind]["image"] = "DOCKER|" + review["images"][kind]
    same = current == expected
    result = {"at": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"],
              "protected_equal_except_three_images": same, "images": review["images"],
              "manifest_sha256": manifest()["sha256"], "ingester_unchanged": current["protected"]["runtime"]["sites"]["ingestion"] == expected["protected"]["runtime"]["sites"]["ingestion"]}
    rt.save(HOME / "verification.json", result)
    rt.save(rt.ROOT / "gateway/validation/pricing-runtime-release-20261027.json", result)
    print(json.dumps(result), flush=True)
    rt.require(same, "post_apply_baseline_drift")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build-api", "build-portals", "build-corrected-portals", "plan", "check", "apply", "verify", "baseline"])
    args = parser.parse_args()
    HOME.mkdir(parents=True, exist_ok=True)
    os.environ.update(REQUESTS_CA_BUNDLE=rt.CA, SSL_CERT_FILE=rt.CA)
    # Private plan/settings-bearing artifacts must retain existing operator-only ACL.
    sid = re.search(r"S-1-5-[0-9-]+", rt.run(["whoami", "/user", "/fo", "csv", "/nh"])).group(0)
    rt.run(["icacls", str(HOME), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"])
    if args.action == "baseline":
        data = baseline()
        rt.save(HOME / "initial-baseline.json", data)
        print(json.dumps({"protected_sha256": sha(json.dumps(data, sort_keys=True)), "images": {
            k: v["image"] for k, v in data["protected"]["runtime"]["sites"].items()}, "at": datetime.now(UTC).isoformat()}), flush=True)
    elif args.action == "check":
        print(json.dumps({"checked_plan_sha256": check()["plan_sha256"]}), flush=True)
    else:
        {"build-api": build_api, "build-portals": build_portals, "build-corrected-portals": build_corrected_portals,
         "plan": plan, "apply": apply, "verify": verify}[args.action]()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"errorType": type(error).__name__, "error": str(error) if isinstance(error, RuntimeError)
                          else "pricing_release_failed_sensitive_detail_suppressed"}), flush=True)
        raise SystemExit(1)