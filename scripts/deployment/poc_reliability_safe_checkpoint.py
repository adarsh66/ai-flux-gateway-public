"""Finite read-only checkpoint after audited revision-eight default recovery.

No build, Terraform, fragment write, inference, settings change or retry loop.
"""
from copy import deepcopy
import json
import xml.etree.ElementTree as ET

from aiflux.gateway_settings import fingerprint
from aiflux.poc_controls import render
from aiflux.schemas import PocGatewayConfiguration
from scripts.deployment import poc_reliability_release as release
from scripts.deployment.poc_fragment_readback import compare

r = release.r


def main():
    home = release.native.HOME
    r.rt.require(not (home / "default-restored-protected-readback-intent.json").exists(),
                 "existing_checkpoint_intent_reconcile_only")
    verified = r.prep.load(release.HOME / "verified.json")
    prior = r.prep.load(home / "revision8-default-before-reconcile.json")
    r.rt.require(verified["passed"] and prior["safe_defaults_fingerprint_equal"],
                 "verified_api_and_exact_defaults_required")
    preserved = [release.HOME / name for name in
                 ("apply-intent.json", "applied.json", "verified.json", "validation.json")]
    preserved += [home / "publisher-acceptance.json", home / "revision7-failure-readback.json"]
    hashes = {p.name: r.sha(p.read_bytes()) for p in preserved}
    r.exclusive(home, "default-restored-protected-readback-intent.json", {
        "at": r.fs.stamp(), "cloud_configuration_writes": 0, "preserved": hashes,
    })
    evidence = r.prep.load(r.HOME / "admin-initialization-before-reconcile.json")
    bindings = sorted([
        {"subscription_id": s["id"], "organization_id": s["organization_id"]}
        for s in evidence["subscriptions"]
    ], key=lambda b: b["subscription_id"])
    desired = render(PocGatewayConfiguration(), bindings)
    run = r.ProductRun()
    raw = run.arm("/policyFragments/" + r.FRAGMENT + "?format=rawxml")
    xml = run.arm("/policyFragments/" + r.FRAGMENT + "?format=xml")
    cross = compare(desired, raw["properties"]["value"], xml["properties"]["value"])
    r.rt.require(raw["id"].lower() == xml["id"].lower() == r.ID.lower()
                 and raw["properties"].get("provisioningState") == "Succeeded"
                 and fingerprint(desired) == fingerprint(raw["properties"]["value"])
                 and cross["semantic_equal"], "exact_safe_default_fragment_required")
    current = r.snapshot()
    expected = deepcopy(verified["baseline"])
    expected["fragment_xml_sha256"] = current["fragment_xml_sha256"]
    r.rt.require(current == expected, "unrelated_complete_protected_baseline_drift")
    policy = run.policy()
    tree = ET.fromstring(policy)
    r.rt.require(not any(n.get("fragment-id") == r.FRAGMENT
                         for n in tree.findall(".//include-fragment")), "policy_must_remain_detached")
    catalogs = [json.loads(n.text) for n in tree.findall(".//set-body")
                if (n.text or "").startswith('{"data":')]
    r.rt.require(len(catalogs) == 1 and {m["id"] for m in catalogs[0]["data"]} == r.MODELS,
                 "exact_thirteen_model_catalog_required")
    settings = r.fs.current_settings()
    flags = {k: settings["api"].get(k) for k in r.FLAGS}
    r.rt.require(flags == r.FLAGS and
                 {k: r.fs.sha(v) for k, v in settings.items()} == current["settings_hashes"],
                 "unchanged_settings_and_exact_live_flags_required")
    r.rt.require(hashes == {p.name: r.sha(p.read_bytes()) for p in preserved},
                 "historical_artifacts_must_remain_unchanged")
    proof = {
        "at": r.fs.stamp(), "passed": True, "cloud_configuration_writes": 0,
        "inference_requests": 0, "safe_defaults_fingerprint": fingerprint(desired),
        "fragment_provisioning_state": "Succeeded", "cross_export": cross,
        "complete_protected_equal_except_authorized_fragment_content": True,
        "byte_exact_original_default_fragment":
            current["fragment_xml_sha256"] == verified["baseline"]["fragment_xml_sha256"],
        "active_policy_sha256": current["active_policy_sha256"],
        "poc_fragment_in_active_policy": False, "api_control_flags": flags,
        "catalog_model_count": len(r.MODELS), "preserved_artifacts": hashes,
        "publisher_acceptance_passed": False, "baseline": current,
    }
    r.exclusive(home, "default-restored-protected-readback.json", proof)
    print(json.dumps({k: v for k, v in proof.items() if k != "baseline"}), flush=True)


if __name__ == "__main__":
    main()