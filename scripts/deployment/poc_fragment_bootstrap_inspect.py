"""Read-only field-path diagnostic for the rejected, never-applied plan."""
import json

from scripts.deployment.poc_fragment_bootstrap import Bootstrap, PLAN, HOME, TFROOT, checkpoint, load, sha
from scripts.deployment.project_route_demo import policy_structure
from scripts.deployment import runtime_rollout as rt


def paths(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        return [p for k in a.keys() | b.keys() for p in paths(a.get(k), b.get(k), path + "/" + k)]
    return [] if a == b else [path]


if __name__ == "__main__":
    parsed = json.loads(Bootstrap().terraform("show", "-json", str(PLAN)))
    result = {"changes": [{"address": r["address"], "actions": r["change"]["actions"],
                           "paths": paths(r["change"].get("before"), r["change"].get("after"))}
                          for r in parsed["resource_changes"] if r["change"]["actions"] not in (["no-op"], ["read"])],
              "checks": [{"address": c["address"].get("to_display"), "status": c["status"]} for c in parsed.get("checks", [])]}
    change = next(r["change"] for r in parsed["resource_changes"] if r["address"] == "azapi_resource.project_policy[0]")
    before, after = [change[k]["body"]["properties"] for k in ("before", "after")]
    state = json.loads(Bootstrap().terraform("show", "-json"))
    stored = next(r["values"]["body"]["properties"] for r in state["values"]["root_module"]["resources"] if r["name"] == "project_policy")
    result["policy_representation"] = {"plan_before_format": before["format"], "plan_after_format": after["format"],
        "stored_state_format": stored["format"], "plan_semantics_equal": policy_structure(before["value"]) == policy_structure(after["value"]),
        "stored_matches_desired_bytes": stored == after, "stored_sha256": sha(stored["value"]), "desired_sha256": sha(after["value"])}
    rt.save(HOME / "plan-path-diagnostic.json", result)
    checkpoint("rejected_plan_inspected_no_apply", **result, cloud_writes=0)