"""Read retained activation evidence and existing ACR results; never submit work."""
import json
import xml.etree.ElementTree as ET

from scripts.deployment import poc_activation_prepare as p
from scripts.deployment import runtime_rollout as rt


def main():
    p.check_sources()
    account = rt.cli(["account", "show", "--subscription", rt.SUB])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    runs = rt.cli(["acr", "task", "list-runs", "-r", "pocidstokenexacr", "--subscription", rt.SUB, "--top", "5"])
    result = {"source_binding_verified": True, "account_scope_verified": True,
              "runs": [{k: r.get(k) for k in ("runId", "status", "createTime", "startTime", "finishTime", "outputImages")} for r in runs],
              "markers": sorted(x.name for x in p.HOME.iterdir() if x.is_file()), "tests": {}}
    for folder in (p.HOME, rt.HOME / "poc-activation-20261028"):
        for path in folder.glob("*.xml"):
            suites = list(ET.parse(path).getroot().iter("testsuite"))
            result["tests"][str(path.relative_to(rt.ROOT))] = {
                k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    proof = p.load(p.HOME / "permission-preflight.json")
    result["permission"] = {k: v for k, v in proof.items() if k in (
        "at_utc", "publisher_fragment_permission_verified", "publisher_identity", "publisher_permissions", "api_control_flags")}
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()