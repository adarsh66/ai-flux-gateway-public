"""Read-only attribution and exact render proof; never publishes or applies."""
import json

from aiflux.gateway_settings import fingerprint
from aiflux.poc_controls import render
from aiflux.schemas import PocGatewayConfiguration
from scripts.deployment import poc_activation_release as r
from scripts.deployment.poc_fragment_readback import compare


def main():
    r.prep.check_sources()
    evidence = r.prep.load(r.HOME / "admin-initialization-before-reconcile.json")
    head = evidence["head"]
    r.rt.require(head["version"] == 1 and head["published_version"] is None
                 and head["desired"]["state"] == "failed", "retained_failed_revision_required")
    config = PocGatewayConfiguration.model_validate(head["desired"]["configuration"])
    r.rt.require(config == PocGatewayConfiguration(), "safe_defaults_only")
    bindings = [{"subscription_id": s["id"], "organization_id": s["organization_id"]}
                for s in evidence["subscriptions"]]
    bindings.sort(key=lambda b: b["subscription_id"])
    desired = render(config, bindings)
    run = r.ProductRun()
    raw = run.arm("/policyFragments/" + r.FRAGMENT + "?format=rawxml")
    exported = run.arm("/policyFragments/" + r.FRAGMENT + "?format=xml")
    exact = compare(desired, raw["properties"]["value"], exported["properties"]["value"])
    r.rt.require(exact["semantic_equal"] and fingerprint(desired) == fingerprint(raw["properties"]["value"]),
                 "unexpected_fragment_drift_stop")
    events = r.rt.cli(["monitor", "activity-log", "list", "--resource-group", "IDS-TOKEN-EXCHANGE-POC",
        "--start-time", "2026-10-28T08:48:00Z", "--end-time", r.fs.stamp(),
        "--subscription", r.rt.SUB, "--max-events", "1000"])
    writes = [e for e in events if str(e.get("operationName", {}).get("value", "")).lower()
              == "microsoft.apimanagement/service/policyfragments/write"]
    caller = "4e7b70ed-9868-47ba-9b61-304f1e1fdd89"
    exact_writes = [e for e in writes if str(e.get("resourceId", "")).lower() == r.ID.lower()]
    r.rt.require(exact_writes and all(e.get("caller") == caller for e in exact_writes)
                 and {e["correlationId"] for e in exact_writes} == {"b42cc360-1a18-4794-82a4-807c8665ec22"},
                 "unexpected_or_unattributed_fragment_writer")
    r.rt.require(any(e.get("correlationId") == exact_writes[0]["correlationId"]
                     and e.get("status", {}).get("value") == "Succeeded" for e in writes),
                 "successful_write_event_required")
    baseline = r.prep.load(r.location("runtime")[0] / "verified.json")["baseline"]
    current = r.snapshot()
    expected = dict(baseline)
    for key in ("fragment_xml_sha256", "fragment_properties_sha256"):
        expected[key] = current[key]
    r.rt.require(current == expected, "unrelated_protected_baseline_drift")
    result = {"at": r.fs.stamp(), "passed": True, "revision": 1,
        "desired_canonical_sha256": fingerprint(desired), "exact_cross_export_comparison": exact,
        "writer_principal": caller, "write_correlation_id": exact_writes[0]["correlationId"],
        "write_events": [{k: e.get(k) for k in ("eventTimestamp", "resourceId", "operationName", "status", "caller", "correlationId")}
                         for e in writes], "full_protected_baseline_unchanged_except_authorized_fragment": True,
        "baseline": current, "cloud_writes": 0, "inference_requests": 0,
        "recovery": "Existing revision reconcile can adopt only the already exact desired fingerprint; no drift bypass."}
    r.exclusive(r.HOME, "publication-attribution-readback.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "baseline"}, indent=2), flush=True)


if __name__ == "__main__":
    main()