"""Read-only reconciliation of the ALREADY applied targeted01 fragment.

No Terraform execution, plan, apply, import, cloud mutation or inference path.
Original markers are hash-bound and retained. Only local evidence is appended.
"""
from datetime import UTC, datetime
import json
import xml.etree.ElementTree as ET

from scripts.deployment import poc_fragment_bootstrap as b
from scripts.deployment import poc_fragment_bootstrap_targeted as t
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.poc_fragment_readback import compare

PLAN_SHA = "1d35fbd135345241f7a4115aeb9ab16fa0d439360188595198e440e447545dcd"


class ReadOnly(b.Bootstrap):
    def arm(self, suffix, method="GET"):
        rt.require(method == "GET", "reconciliation_get_only")
        return super().arm(suffix, method)

    def terraform(self, *args, **kwargs):
        raise RuntimeError("reconciliation_terraform_prohibited")


def exports(reader):
    responses = {fmt: reader.arm("/policyFragments/" + b.FRAGMENT + "?format=" + fmt)
                 for fmt in ("rawxml", "xml")}
    expected_description = ("Runtime-owned bounded POC variables and literal-call quota; "
                            "stable counter identity and envelope.")
    for fmt, response in responses.items():
        rt.require(response["id"].lower() == b.ID.lower(), "exact_fragment_id:" + fmt)
        rt.require(response["name"] == b.FRAGMENT, "exact_fragment_name:" + fmt)
        rt.require(response["type"].lower() == "microsoft.apimanagement/service/policyfragments",
                   "exact_fragment_type:" + fmt)
        properties = response["properties"]
        rt.require(properties.get("provisioningState") == "Succeeded", "fragment_not_succeeded:" + fmt)
        rt.require(properties.get("description") == expected_description, "fragment_description_changed:" + fmt)
    return responses


def reconcile():
    t.configure()
    home = t.HOME
    at = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    old_bytes = (home / "result.json").read_bytes()
    old = json.loads(old_bytes)
    with (home / ("result-before-readonly-" + at + ".json")).open("xb") as handle:
        handle.write(old_bytes)
    immutable_paths = [home / n for n in ("apply-intent.json", "applied.json", "review.json", "validation.json",
                                          "fragment-targeted.tfplan", "full-validation-NEVER-APPLY.tfplan")]
    immutable_paths += [p for p in t.ORIGINAL.iterdir() if p.is_file()]
    hashes = {str(p.relative_to(rt.ROOT)): b.sha(p.read_bytes()) for p in immutable_paths}
    review = b.load(home / "review.json")
    rt.require(review["plan_sha256"] == PLAN_SHA == b.sha(b.PLAN.read_bytes()), "exact_applied_plan_hash")
    for name in ("apply-intent.json", "applied.json"):
        rt.require(b.load(home / name)["plan_sha256"] == PLAN_SHA, "applied_marker_plan_mismatch")
    rt.require(old["apply_attempts"] == 1 and old["cloud_writes"] == 1, "one_original_apply_required")
    rt.require(all(b.sha((rt.ROOT / path).read_bytes()) == digest for path, digest in review["sources"].items()),
               "historical_reviewed_source_changed")
    junit = home / "readonly-semantic-tests.xml"
    suites = list(ET.parse(junit).getroot())
    test_count = sum(int(s.get("tests", 0)) for s in suites)
    rt.require(test_count >= 131 and not any(int(s.get(k, 0)) for s in suites
                                           for k in ("errors", "failures", "skipped")), "focused_test_proof_required")
    first = exports(ReadOnly())
    comparison = compare(b.DEFAULTS.read_text(encoding="utf-8"), first["rawxml"]["properties"]["value"],
                         first["xml"]["properties"]["value"])
    # Always preserve precise XML differences before reporting failure.
    rt.save(home / ("readback-diagnosis-" + at + ".json"), comparison)
    rt.require(comparison["semantic_equal"], "substantive_xml_diff:readback-diagnosis-" + at + ".json")
    baseline = ReadOnly().protected_complete()
    expected_baseline = b.load(home / "baseline.json")
    rt.save(home / ("protected-readonly-" + at + ".json"), baseline)
    rt.require(baseline == expected_baseline, "full_protected_baseline_changed")
    # A new reader/token and fresh exact GETs, independent of the failed verifier
    # and initial diagnosis. No Terraform source-binding waiver or reapply.
    final = exports(ReadOnly())
    final_comparison = compare(b.DEFAULTS.read_text(encoding="utf-8"), final["rawxml"]["properties"]["value"],
                               final["xml"]["properties"]["value"])
    rt.require(final_comparison["semantic_equal"] and final == first, "fragment_changed_during_reconciliation")
    state = b.load(b.TFROOT / "terraform.tfstate")
    before = b.load(home / "state-before-summary.json")
    rt.require(state["lineage"] == before["lineage"], "state_lineage_changed")
    matches = [i for r in state["resources"] if r["mode"] == "managed" and r["type"] == "azapi_resource"
               and r["name"] == "poc_settings" for i in r["instances"]
               if i["attributes"]["id"].lower() == b.ID.lower()]
    rt.require(len(matches) == 1, "single_existing_owner_state_binding_required")
    rt.require(hashes == {str(p.relative_to(rt.ROOT)): b.sha(p.read_bytes()) for p in immutable_paths},
               "historical_marker_or_plan_changed")
    proof = {"at_utc": datetime.now(UTC).isoformat(), "fragment_exists": True,
             "resource_id": final["rawxml"]["id"], "portal_url": "https://portal.azure.com/#resource" + b.ID + "/overview",
             "created_at_utc": b.load(home / "applied.json")["at_utc"], "plan_sha256": PLAN_SHA,
             "provisioning_state": "Succeeded", "xml_readback": final_comparison,
             "rawxml_sha256": b.sha(final["rawxml"]["properties"]["value"]),
             "xml_export_sha256": b.sha(final["xml"]["properties"]["value"]),
             "properties": {k: v for k, v in final["rawxml"]["properties"].items() if k != "value"},
             "protected_baseline_equal_except_new_fragment": True, "protected_baseline_sha256": fs.sha(baseline),
             "active_policy_sha256": baseline["active_policy_sha256"], "all_four_images_and_settings_unchanged": True,
             "controls_remain_off": True, "publisher_permission_verified": False,
             "state_lineage": state["lineage"], "state_serial": state["serial"],
             "historical_artifact_sha256": hashes, "previous_result_sha256": b.sha(old_bytes),
             "focused_tests": {"passed": test_count, "failures": 0, "junit_sha256": b.sha(junit.read_bytes())},
             "verifier_sources": {p: b.sha((rt.ROOT / p).read_bytes()) for p in
                                  ("scripts/deployment/poc_fragment_readback.py", "scripts/deployment/poc_fragment_reconcile.py",
                                   "tests/unit/test_poc_fragment_readback.py")},
             "cloud_writes_this_reconciliation": 0, "apply_attempts": 1, "cloud_writes": 1,
             "role_writes": 0, "activation_writes": 0, "inference_requests": 0,
             "next_step": "Central Entra team: grant existing API principal fragment-scoped read/write only; no activation."}
    path = home / ("read-only-verified-" + at + ".json")
    rt.save(path, proof)
    b.checkpoint("created_and_readonly_semantically_verified", **proof,
                 verification_evidence=path.name, previous_failure_retained=True,
                 failed_stage=None, error_type=None, reason=None, existing_xml_matches_defaults=True)
    return proof


if __name__ == "__main__":
    try:
        reconcile()
    except Exception as error:
        print(json.dumps({"status": "reconciliation_failed_no_retry_or_writes", "error_type": type(error).__name__,
                          "reason": str(error) if isinstance(error, RuntimeError) else "diagnostic_suppressed"}), flush=True)
        raise SystemExit(1) from None