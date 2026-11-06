"""Finite read-only diagnosis of retained revision-seven publication failure.

No fragment PUT, reconciliation, inference, build, plan, apply or settings change.
Only fixed diagnostic stage/status fields are emitted from container logs.
"""
from copy import deepcopy
import json
import re

from aiflux.gateway_settings import fingerprint
from aiflux.poc_controls import render
from aiflux.schemas import PocGatewayConfiguration
from scripts.deployment import poc_reliability_release as release
from scripts.deployment.poc_fragment_readback import compare

r = release.r


def main():
    verified = r.prep.load(release.HOME / "verified.json")
    r.rt.require(verified["passed"], "applied_api_independent_verification_required")
    evidence = r.prep.load(r.HOME / "admin-initialization-before-reconcile.json")
    bindings = sorted([
        {"subscription_id": s["id"], "organization_id": s["organization_id"]}
        for s in evidence["subscriptions"]
    ], key=lambda b: b["subscription_id"])
    config = PocGatewayConfiguration().model_dump(mode="json")
    config["overrides"] = [{
        "organization_id": "00b30bd3-bf91-470d-b336-a192be32996e",
        "subscription_id": None,
        "limits": {**config["defaults"], "rpm": 59}, "safety": None,
    }]
    desired = render(PocGatewayConfiguration.model_validate(config), bindings)
    defaults = render(PocGatewayConfiguration(), bindings)
    run = r.ProductRun()
    raw = run.arm("/policyFragments/" + r.FRAGMENT + "?format=rawxml")
    xml = run.arm("/policyFragments/" + r.FRAGMENT + "?format=xml")
    logs = r.rt.arm(r.rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/containerlogs", "POST", raw=True)
    diagnostics = re.findall(
        r"POC fragment publication failed stage=(baseline_read|conditional_put_and_readiness|strict_readback) status=(None|[0-9]{3})",
        logs.decode("utf-8", errors="replace"),
    )
    current = r.snapshot()
    expected = deepcopy(verified["baseline"])
    expected["fragment_xml_sha256"] = current["fragment_xml_sha256"]
    r.rt.require(current == expected, "unrelated_protected_baseline_drift")
    proof = {
        "at": r.fs.stamp(), "revision": 7, "cloud_configuration_writes": 0,
        "inference_requests": 0, "fragment_provisioning_state": raw["properties"].get("provisioningState"),
        "fragment_identity_equal": raw["id"].lower() == xml["id"].lower() == r.ID.lower(),
        "desired_revision7_fingerprint_equal": fingerprint(desired) == fingerprint(raw["properties"]["value"]),
        "safe_defaults_fingerprint_equal": fingerprint(defaults) == fingerprint(raw["properties"]["value"]),
        "revision7_cross_export": compare(desired, raw["properties"]["value"], xml["properties"]["value"]),
        "sanitized_publication_diagnostics": [{"stage": stage, "status": None if status == "None" else int(status)}
                                              for stage, status in diagnostics],
        "complete_protected_equal_except_authorized_fragment_content": True,
        "baseline": current,
    }
    r.exclusive(release.native.HOME, "revision7-failure-readback.json", proof)
    print(json.dumps({k: v for k, v in proof.items() if k != "baseline"}), flush=True)


if __name__ == "__main__":
    main()