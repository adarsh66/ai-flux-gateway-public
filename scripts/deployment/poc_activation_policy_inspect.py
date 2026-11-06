"""Inspect an existing policy plan without replanning, applying or showing values."""
import json

from scripts.deployment import poc_activation_release as r


if __name__ == "__main__":
    folder, root, target = r.location("policy")
    data = r.parsed(root, target)
    result = {"at": r.fs.stamp(), "plan_sha256": r.sha(target.read_bytes()),
        "errored": data.get("errored"), "applyable": data.get("applyable"),
        "checks": [{"address": c["address"], "status": c["status"]} for c in data.get("checks", [])],
        "changes": [], "review_exists": (folder / "review.json").exists(),
        "apply_intent_exists": (folder / "apply-intent.json").exists()}
    def paths(before, after, prefix=""):
        if type(before) != type(after):
            return [prefix]
        if isinstance(before, dict):
            return [p for k in sorted(set(before) | set(after)) for p in paths(before.get(k), after.get(k), prefix + "/" + k)]
        if isinstance(before, list) and len(before) == len(after):
            return [p for i, (a, b) in enumerate(zip(before, after)) for p in paths(a, b, prefix + "/" + str(i))]
        return [] if before == after else [prefix]
    for item in data.get("resource_changes", []):
        c = item["change"]
        if c["actions"] != ["no-op"]:
            result["changes"].append({"address": item["address"], "actions": c["actions"],
                "paths": paths(c.get("before"), c.get("after"))})
    try:
        r.guard_activation_policy(data, (folder / "predecessor-policy.xml").read_bytes().decode(), r.prep.load(folder / "inputs.tfvars.json"))
        result["guard_passed"] = True
    except RuntimeError as error:
        result["guard_passed"] = False
        result["guard_error"] = str(error)
    r.exclusive(folder, "inspection.json", result)
    print(json.dumps(result, indent=2), flush=True)