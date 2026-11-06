"""Final independent read-only checkpoint after rejected activation plan. No apply."""
from copy import deepcopy
import json

from aiflux.gateway_settings import fingerprint
from aiflux.poc_controls import render
from aiflux.schemas import PocGatewayConfiguration
from scripts.deployment import poc_activation_release as r
from scripts.deployment.poc_fragment_readback import compare


if __name__ == "__main__":
    r.prep.check_sources()
    folder, root, target = r.location("policy")
    plan = r.parsed(root, target)
    r.rt.require(plan.get("errored") is True and plan.get("applyable") is False
                 and not (folder / "apply-intent.json").exists(), "rejected_plan_must_remain_unapplied")
    failed = [c["address"]["to_display"] for c in plan["checks"] if c["status"] == "fail"]
    r.rt.require(failed == ["azapi_resource.fireworks_backend"], "unexpected_plan_failure")
    r.rt.require(not any(c["change"]["actions"] not in (["no-op"], ["read"])
                        for c in plan.get("resource_changes", [])), "unexpected_partial_plan_write")
    run = r.ProductRun()
    raw = run.arm("/policyFragments/" + r.FRAGMENT + "?format=rawxml")
    xml = run.arm("/policyFragments/" + r.FRAGMENT + "?format=xml")
    bindings = [{"subscription_id": s["id"], "organization_id": s["organization_id"]}
                for s in r.prep.load(r.HOME / "admin-initialization-before-reconcile.json")["subscriptions"]]
    desired = render(PocGatewayConfiguration(), sorted(bindings, key=lambda x: x["subscription_id"]))
    exact = compare(desired, raw["properties"]["value"], xml["properties"]["value"])
    r.rt.require(exact["semantic_equal"] and raw["properties"]["provisioningState"] == "Succeeded",
                 "unexpected_final_fragment_drift")
    r.rt.require(fingerprint(desired) == fingerprint(raw["properties"]["value"]), "fingerprint_not_bypassed")
    original = r.prep.load(r.location("runtime")[0] / "verified.json")["baseline"]
    current = r.snapshot()
    expected = deepcopy(original)
    for key in ("fragment_xml_sha256", "fragment_properties_sha256"):
        expected[key] = current[key]
    r.rt.require(expected == current, "unrelated_final_protected_drift")
    r.rt.require(current == r.prep.load(folder / "baseline.json"), "post_plan_baseline_drift")
    settings = r.fs.current_settings()
    r.rt.require(all(settings["api"].get(k) == v for k, v in r.FLAGS.items()), "runtime_flags_changed")
    runtime = r.prep.load(r.location("runtime")[0] / "applied.json")
    result = {"at": r.fs.stamp(), "status": "blocked_policy_activation_guard",
        "runtime_applied_once_and_verified": True, "runtime_plan_sha256": runtime["plan_sha256"],
        "rebuilds_this_continuation": 0, "runtime_reapplies_this_continuation": 0,
        "fragment_recreated": False, "fragment_canonical_sha256": fingerprint(desired),
        "fragment_exact_restored_safe_defaults": exact["semantic_equal"],
        "admin_acceptance": r.prep.load(r.HOME / "admin-save-restore-acceptance.json"),
        "rejected_policy_plan_sha256": r.sha(target.read_bytes()), "policy_apply_attempts": 0,
        "blocker": {"address": failed[0], "source": "infra/project-route/fireworks.tf",
            "condition": "var.persistent_poc_authorized && !var.poc_controls_enabled && var.glm_enabled && var.allow_product_subscriptions",
            "error": "Fireworks addition requires the unchanged product-authenticated POC with external GLM and optional controls OFF.",
            "resolution": "Requires separately reviewed Fireworks/POC compatibility invariant and tests, then a fresh exclusive successor plan and actual independent validation. Never apply the rejected plan or weaken the guard as a deployment workaround."},
        "full_protected_baseline_matches_verified_runtime_except_authorized_fragment": True,
        "full_protected_baseline_matches_policy_preparation": True,
        "active_policy_sha256": current["active_policy_sha256"], "active_policy_unchanged": True,
        "api_flags": r.FLAGS, "images": {k: v["image"] for k, v in current["runtime"]["sites"].items()},
        "baseline": current, "inference_requests": 0, "cloud_writes_in_final_readback": 0,
        "no_secret_values_emitted": True}
    r.exclusive(r.HOME, "current_result.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "baseline"}, indent=2), flush=True)