"""Read exact-fragment operation status after failed publication; no retry/write."""
import json

from scripts.deployment import poc_activation_release as r


def main():
    raw = r.ProductRun().arm("/policyFragments/" + r.FRAGMENT + "?format=rawxml")
    events = r.rt.cli(["monitor", "activity-log", "list", "--resource-id", r.ID,
        "--start-time", "2026-10-28T08:48:00Z", "--end-time", r.fs.stamp(),
        "--subscription", r.rt.SUB, "--max-events", "30"])
    value = raw["properties"]["value"]
    result = {"at": r.fs.stamp(), "fragment_sha256": r.sha(value),
        "fragment_properties": {k: v for k, v in raw["properties"].items() if k != "value"},
        "original_fragment_sha256": r.prep.load(r.location("runtime")[0] / "baseline.json")["fragment_xml_sha256"],
        "policy_unchanged": r.sha(r.ProductRun().policy()) == r.prep.load(r.location("runtime")[0] / "baseline.json")["active_policy_sha256"],
        "events": [{k: e.get(k) for k in ("eventTimestamp", "operationName", "status", "subStatus", "correlationId", "caller")}
                   for e in events], "cloud_writes": 0}
    r.exclusive(r.HOME, "initialization-failure-diagnosis.json", result)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()