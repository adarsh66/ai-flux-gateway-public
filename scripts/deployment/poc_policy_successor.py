"""Fresh single-policy successor, blocked on independently verified reliable publisher."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import sys

from aiflux.gateway_settings import fingerprint
from aiflux.poc_controls import render
from aiflux.schemas import PocGatewayConfiguration
from scripts.deployment import poc_reliability_release as api
from scripts.deployment.poc_fragment_readback import compare

r = api.r
HOME = api.native.HOME / "policy-successor01"
ROOT = r.rt.ROOT / "infra/project-route"
PLAN = HOME / "policy.tfplan"
REJECTED = "7d200ba93b01e2fa9d969c86a333751008e93bb26a202dea77be5555871aeab6"


def tooling():
    paths = {Path(__file__), r.rt.ROOT / "scripts/deployment/poc_policy_successor_validation.py",
             r.rt.ROOT / "tests/unit/test_poc_fireworks_compatibility.py", r.rt.ROOT / "tests/unit/test_poc_policy_successor.py",
             r.rt.ROOT / "scripts/deployment/poc_controls_guards.py"}
    paths |= set(ROOT.glob("*.tf")) | {ROOT / ".terraform.lock.hcl"}
    return {str(p): r.sha(p.read_bytes()) for p in paths}


def acceptance():
    verified = r.prep.load(api.HOME / "verified.json")
    r.rt.require(verified["passed"], "new_api_independent_readback_required")
    evidence = r.prep.load(api.native.HOME / "publisher-acceptance.json")
    r.rt.require(evidence["passed"] and evidence["http502_count"] == 0 and evidence["reconciles"] == 0
                 and len(evidence["operations"]) >= 4 and all(x["http_status"] == 200 and x["published"] for x in evidence["operations"])
                 and evidence["head"]["version"] == evidence["head"]["published_version"] and evidence["head"]["state"] == "published"
                 and evidence["head"]["configuration"] == PocGatewayConfiguration().model_dump(mode="json"), "reliable_live_publisher_restored_defaults_required")
    r.rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(evidence["at"]) < timedelta(hours=2), "stale_publisher_acceptance")
    old = r.prep.load(r.HOME / "admin-initialization-before-reconcile.json")
    bindings = sorted([{"subscription_id": s["id"], "organization_id": s["organization_id"]} for s in old["subscriptions"]], key=lambda b: b["subscription_id"])
    desired = render(PocGatewayConfiguration(), bindings)
    run = r.ProductRun()
    raw = run.arm("/policyFragments/" + r.FRAGMENT + "?format=rawxml")
    xml = run.arm("/policyFragments/" + r.FRAGMENT + "?format=xml")
    r.rt.require(raw["id"].lower() == xml["id"].lower() == r.ID.lower() and raw["properties"]["provisioningState"] == "Succeeded"
        and compare(desired, raw["properties"]["value"], xml["properties"]["value"])["semantic_equal"] and
        fingerprint(desired) == fingerprint(raw["properties"]["value"]), "published_exact_safe_defaults_readback")
    r.rt.require(r.sha((r.HOME / "policy/policy.tfplan").read_bytes()) == REJECTED, "original_rejected_plan_preserved")
    return evidence


def plan():
    r.rt.require(not HOME.exists(), "existing_successor_reconcile_only")
    acceptance()
    r.require_publisher(r.collect())
    baseline = r.snapshot()
    previous = r.prep.load(api.HOME / "verified.json")["baseline"]
    expected = deepcopy(previous)
    expected["fragment_xml_sha256"] = baseline["fragment_xml_sha256"]
    r.rt.require(baseline == expected, "prepolicy_full_protected_baseline")
    r.fs.protect(HOME)
    r.exclusive(HOME, "baseline.json", baseline)
    variables = r.prep.load(r.rt.HOME / "poc-fragment-bootstrap-20261028/inputs.tfvars.json")
    variables.update(poc_controls_enabled=True, poc_publisher_permissions_verified=True, poc_settings_bootstrap_enabled=True)
    r.rt.save(HOME / "inputs.tfvars.json", variables)
    predecessor = r.ProductRun().policy()
    (HOME / "predecessor-policy.xml").write_bytes(predecessor.encode())
    r.fs.terraform(ROOT, "init", "-input=false", "-lockfile=readonly", "-no-color")
    r.rt.require(r.fs.terraform(ROOT, "workspace", "show").strip() == "default", "default_workspace")
    r.fs.terraform(ROOT, "validate", "-no-color")
    r.exclusive(HOME, "plan-intent.json", {"at": r.fs.stamp(), "scope": "one_existing_policy_update", "max_applies": 1,
        "rejected_plan_sha256": REJECTED, "never_apply_rejected": True})
    r.fs.terraform(ROOT, "plan", "-input=false", "-no-color", "-lock-timeout=60s", "-var-file=" + str(HOME / "inputs.tfvars.json"), "-out=" + str(PLAN))
    data = r.parsed(ROOT, PLAN)
    r.rt.require(data.get("checks") and all(c["status"] == "pass" for c in data["checks"]), "every_real_policy_check_pass")
    desired = r.guard_activation_policy(data, predecessor, variables)
    (HOME / "desired-policy.xml").write_bytes(desired.encode())
    paths = [PLAN, HOME / "inputs.tfvars.json", HOME / "predecessor-policy.xml", HOME / "desired-policy.xml", *ROOT.glob("*.tf"), ROOT / ".terraform.lock.hcl"]
    review = {"at": r.fs.stamp(), "plan_sha256": r.sha(PLAN.read_bytes()), "tooling": tooling(), "baseline": baseline,
              "artifacts": {str(p): r.sha(p.read_bytes()) for p in paths}, "api_plan_sha256": r.prep.load(api.HOME / "verified.json")["plan_sha256"],
              "publisher_acceptance_sha256": r.sha((api.native.HOME / "publisher-acceptance.json").read_bytes())}
    r.exclusive(HOME, "review.json", review)
    print(json.dumps({"at": review["at"], "plan_sha256": review["plan_sha256"], "exact_one_policy_update": True}), flush=True)


def check(live=True):
    review = r.prep.load(HOME / "review.json")
    r.rt.require(review["tooling"] == tooling() and review["plan_sha256"] == r.sha(PLAN.read_bytes()) and
        all(r.sha(Path(p).read_bytes()) == h for p, h in review["artifacts"].items()) and
        review["publisher_acceptance_sha256"] == r.sha((api.native.HOME / "publisher-acceptance.json").read_bytes()), "current_policy_source_input_evidence_binding")
    data = r.parsed(ROOT, PLAN)
    r.rt.require(data.get("checks") and all(c["status"] == "pass" for c in data["checks"]), "every_real_check_pass")
    r.guard_activation_policy(data, (HOME / "predecessor-policy.xml").read_bytes().decode(), r.prep.load(HOME / "inputs.tfvars.json"))
    if live:
        acceptance()
        r.require_publisher(r.collect())
        r.rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at"]) < timedelta(hours=2), "stale_policy_plan")
        r.rt.require(r.snapshot() == review["baseline"], "complete_current_policy_baseline")
    return review


def apply():
    r.rt.require(not (HOME / "apply-intent.json").exists(), "existing_policy_apply_intent_reconcile_only")
    review = check()
    proof = r.prep.load(HOME / "validation.json")
    doc = (r.rt.ROOT / ".azure/deployment-plan.md").read_text()
    r.rt.require(proof["checks_passed"] and proof["plan_sha256"] == review["plan_sha256"] and proof["tooling"] == tooling()
        and proof["at"] in doc and review["plan_sha256"] in doc and "POC policy successor status: Validated." in doc and
        r.prep.load(r.rt.ROOT / ".azure/validate-status.json")["completedStep"] == "UpdateStatus", "independent_actual_policy_validation_required")
    r.exclusive(HOME, "apply-intent.json", {"at": r.fs.stamp(), "plan_sha256": review["plan_sha256"]})
    result = r.fs.terraform(ROOT, "apply", "-input=false", "-no-color", str(PLAN))
    r.exclusive(HOME, "applied.json", {"at": r.fs.stamp(), "plan_sha256": review["plan_sha256"], "summary": re.findall(r"Apply complete! Resources: [^\r\n]+", result)})
    print(json.dumps(r.prep.load(HOME / "applied.json")), flush=True)


def verify():
    review = check(live=False)
    r.rt.require(r.prep.load(HOME / "applied.json")["plan_sha256"] == review["plan_sha256"], "matching_policy_apply")
    current = r.snapshot()
    desired = (HOME / "desired-policy.xml").read_bytes().decode()
    r.rt.require(r.policy_structure(r.ProductRun().policy()) == r.policy_structure(desired), "exact_live_policy_readback")
    expected = deepcopy(review["baseline"])
    expected["active_policy_sha256"] = current["active_policy_sha256"]
    r.rt.require(current == expected, "policy_only_complete_protected_delta")
    r.exclusive(HOME, "verified.json", {"at": r.fs.stamp(), "passed": True, "plan_sha256": review["plan_sha256"],
        "baseline": current, "inference_requests": 0})
    print(json.dumps({"passed": True, "plan_sha256": review["plan_sha256"], "policy_sha256": current["active_policy_sha256"]}), flush=True)


if __name__ == "__main__":
    {"plan": plan, "apply": apply, "verify": verify}[sys.argv[1]]()