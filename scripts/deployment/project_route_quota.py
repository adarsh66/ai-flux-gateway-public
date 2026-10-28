"""Authorized calls 8 -> 1000 on the existing demo; no destructive lifecycle.

Only a guarded saved policy update is applied. Keys stay in memory. No counter
reset, candidate apply, cleanup, global write, or automatic inference retry.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import xml.etree.ElementTree as ET

from scripts.deployment.apim_route_repair import RepairBlocked, SUBSCRIBER
from scripts.deployment.project_route_demo import guard_policy_update, policy_structure
from scripts.deployment.project_route_live import CandidateRun, ROOT, WORK

POLICY = "azapi_resource.project_policy[0]"
PROTECTED = (("global", "/policies/policy"),
             ("dev", "/apis/aiflux-dev-openai/policies/policy"),
             ("native", "/apis/aiflux-native-validation-pending/policies/policy"))


def guard_quota_update(plan, rendered, previous, baseline):
    """Only calls 8 -> 1000; unchanged counters, epoch, expiry and all gates."""
    original = next(x["change"]["after"] for x in previous["resource_changes"] if x["address"] == POLICY)
    old = original["body"]["properties"]["value"]
    old_node = ET.fromstring(old).find(".//quota-by-key")
    if old_node is None or old_node.get("calls") != "8":
        raise RepairBlocked("Expected the existing original eight-call demo")
    wanted = old.replace('<quota-by-key calls="8"', '<quota-by-key calls="1000"')
    if policy_structure(rendered["policy"]) != policy_structure(wanted):
        raise RepairBlocked("Quota increase must not change any other policy content")
    old_vars = {k: v["value"] for k, v in previous["variables"].items()}
    new_vars = {k: v["value"] for k, v in plan.get("variables", {}).items()}
    if new_vars != {**old_vars, "daily_call_allowance": 1000}:
        raise RepairBlocked("Quota update changed expiry, flags or other inputs")
    # Reconstruct the original full guard contract in memory. Never apply it.
    checked = deepcopy(previous)
    checked["variables"]["daily_call_allowance"] = {"value": 1000}
    guard_policy_update(plan, rendered, checked, baseline, authorized_daily_calls=1000)


class QuotaRun(CandidateRun):
    def protected_hashes(self):
        return {name: hashlib.sha256(self.arm(suffix + "?format=rawxml")["properties"]["value"].encode()).hexdigest()
                for name, suffix in PROTECTED}

    def update(self, *, apply=False):
        artifact = json.loads((WORK / "project-route-baseline.json").read_text())
        previous = json.loads(self.tf("show", "-json", str(WORK / "project-demo.tfplan")))
        final = json.loads((WORK / "project-route-final-result.json").read_text())
        if (not final.get("final_route_deployed") or final.get("plan_sha256") !=
                hashlib.sha256((WORK / "project-demo.tfplan").read_bytes()).hexdigest()):
            raise RepairBlocked("Verified deployed original demo predecessor required")
        values = json.loads((WORK / "project-route-demo.tfvars.json").read_text())
        values["daily_call_allowance"] = 1000
        variables = WORK / "project-route-quota.tfvars.json"
        saved = WORK / "project-demo-quota.tfplan"
        evidence = WORK / "project-route-quota-result.json"
        if not apply:
            variables.write_text(json.dumps(values, indent=2))
        elif json.loads(variables.read_text()) != values:
            raise RepairBlocked("Reviewed quota inputs changed")
        output = self.tf("console", "-no-color", "-var-file=" + str(variables), text=
                         "jsonencode({policy=local.policy,global=local.global_policy,global_format=var.global_policy_format,children=local.children})\n")
        rendered = json.loads(json.loads(output[output.find('"'):].strip()))
        if not apply:
            self.tf("validate", "-no-color")
            self.tf("plan", "-no-color", "-input=false", "-var-file=" + str(variables), "-out=" + str(saved))
        plan = json.loads(self.tf("show", "-json", str(saved)))
        guard_quota_update(plan, rendered, previous, artifact["baseline"]["global_export"]["value"])
        protected = self.protected_hashes()
        for name in ("dev", "native"):
            if protected[name] != artifact["baseline"][name]["sha256"]:
                raise RepairBlocked("Protected legacy policy drifted")
        expected_global = next(x["change"]["after"]["body"]["properties"] for x in previous["resource_changes"]
                               if x["address"] == "azapi_resource.project_global_gate[0]")
        if self.arm("/policies/policy?format=" + expected_global["format"])["properties"]["value"] != expected_global["value"]:
            raise RepairBlocked("Global policy drifted")
        current = self.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]
        before = next(x["change"]["before"]["body"]["properties"]["value"] for x in plan["resource_changes"]
                      if x["address"] == POLICY)
        if policy_structure(current) != policy_structure(before):
            raise RepairBlocked("Live policy no longer matches reviewed predecessor")
        subscriber = self.arm("/subscriptions/" + SUBSCRIBER)["properties"]
        if subscriber.get("state") != "active" or not subscriber.get("scope", "").endswith("/products/aiflux"):
            raise RepairBlocked("Exact existing active subscription required")
        sha = hashlib.sha256(saved.read_bytes()).hexdigest()
        self.report.update(plan_sha256=sha, quota_only_guard_verified=True,
                           daily_call_allowance=1000, previous_daily_call_allowance=8,
                           counter_identity_preserved=True, epoch_preserved=True,
                           demo_expires_at=values["demo_expires_at"], protected_hashes=protected,
                           changes=[{"address": POLICY, "actions": ["update"]}])
        if apply:
            reviewed = json.loads(evidence.read_text())
            document = (ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
            status = json.loads((ROOT / ".azure/validate-status.json").read_text())
            if (reviewed.get("plan_sha256") != sha or reviewed.get("protected_hashes") != protected
                    or "Quota validation status: Validated" not in document or sha not in document
                    or status.get("completedStep") != "UpdateStatus"):
                raise RepairBlocked("Current quota-only validation proof required")
            # No destructive cleanup, even on compiler/apply/readback failure.
            try:
                self.tf("apply", "-no-color", "-input=false", str(saved))
                self.report["quota_update_applied"] = True
                live = self.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]
                if policy_structure(live) != policy_structure(rendered["policy"]):
                    raise RepairBlocked("Applied policy readback mismatch")
                if self.protected_hashes() != protected:
                    raise RepairBlocked("Protected policy changed during quota update")
                self.report["readback_verified"] = True
            finally:
                self.report["finished_at"] = datetime.now(UTC).isoformat()
                evidence.write_text(json.dumps(self.report, indent=2))
        self.report["finished_at"] = datetime.now(UTC).isoformat()
        evidence.write_text(json.dumps(self.report, indent=2))
        print(json.dumps(self.report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    args = parser.parse_args()
    try:
        QuotaRun().update(apply=args.action == "apply")
        return 0
    except Exception as exc:
        # No arbitrary Terraform or service diagnostics in shared output.
        print(json.dumps({"failure_type": type(exc).__name__, "quota_update_verified": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())