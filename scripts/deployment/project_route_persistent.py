"""Authorized existing-policy output1024/TPM2048/no-expiry POC. No cleanup.

Compare the ENTIRE predecessor policy after only three exact transformations.
This preserves all ten routes, authentication, stable counters, safety and PII.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import xml.etree.ElementTree as ET

from scripts.deployment.apim_route_repair import APIM, RepairBlocked, SUBSCRIBER
from scripts.deployment.project_route_demo import policy_structure
from scripts.deployment.project_route_live import ROOT, WORK
from scripts.deployment.project_route_models import ModelsRun, POLICY, sha

APPROVED = {
    "enabled": True, "demo_authorized": True, "persistent_poc_authorized": True,
    "acceptance_verified": False, "candidate_validation": False,
    "completion_token_limit": 1024, "tpm_limit": 2048, "rpm_limit": 60,
    "daily_token_quota": 10000, "daily_call_allowance": 1000,
    "backend_retries": 0, "safety_threshold": 1, "demo_expires_at": "",
}


def expected_policy(before):
    """Only remove the existing expiry choose, raise output and minute tokens."""
    tree = ET.fromstring(before)
    inbound = tree.find("inbound")
    expires = [n for n in list(inbound) if n.tag == "choose" and "demo_expired" in ET.tostring(n, encoding="unicode")]
    if len(expires) != 1:
        raise RepairBlocked("Exactly one predecessor expiry gate required")
    inbound.remove(expires[0])
    limits = tree.findall(".//llm-token-limit")
    if len(limits) != 1 or limits[0].get("tokens-per-minute") != "1000":
        raise RepairBlocked("Expected existing TPM1000 counter")
    limits[0].set("tokens-per-minute", "2048")
    text = ET.tostring(tree, encoding="unicode")
    if 'modelMaximum = 32;' not in text or 'max_completion_tokens up to 32' not in text:
        raise RepairBlocked("Expected bounded output32 predecessor")
    def output_limit(value):
        return value.replace('modelMaximum = 32;', 'modelMaximum = 1024;').replace(
            'body["max_completion_tokens"] > 32', 'body["max_completion_tokens"] > 1024').replace(
            'max_completion_tokens up to 32', 'max_completion_tokens up to 1024')
    # Work on decoded XML: expression quotes in attributes serialize as &quot;.
    for node in tree.iter():
        for name, value in node.attrib.items():
            node.set(name, output_limit(value))
        if node.text:
            node.text = output_limit(node.text)
    return ET.tostring(tree, encoding="unicode")


def guard_persistent_update(plan, rendered, before_policy, previous_variables):
    if plan.get("errored") or plan.get("applyable") is not True or plan.get("deferred_changes"):
        raise RepairBlocked("Resolved applyable saved plan required")
    writes = [r for r in plan.get("resource_changes", []) if r["change"]["actions"] not in (["read"], ["no-op"])]
    if len(writes) != 1 or writes[0]["address"] != POLICY or writes[0]["change"]["actions"] != ["update"]:
        raise RepairBlocked("Only one existing policy update, zero creates/deletes allowed")
    change = writes[0]["change"]
    old, new = change["before"], change["after"]
    target = {"type": "Microsoft.ApiManagement/service/apis/policies@2024-05-01",
              "parent_id": APIM + "/apis/aiflux-dev-unified", "name": "policy"}
    if any(old.get(k) != v or new.get(k) != v for k, v in target.items()):
        raise RepairBlocked("Exact existing dev API policy target required")
    def unknown(v):
        return any(unknown(x) for x in v.values()) if isinstance(v, dict) else (
            any(unknown(x) for x in v) if isinstance(v, list) else v is True)
    if unknown(change.get("after_unknown", {}).get("body")):
        raise RepairBlocked("Unknown policy body")
    if policy_structure(old["body"]["properties"]["value"]) != policy_structure(before_policy):
        raise RepairBlocked("Live predecessor changed")
    if new["body"] != {"properties": {"format": "rawxml", "value": rendered["policy"]}}:
        raise RepairBlocked("Saved plan and render differ")
    if policy_structure(rendered["policy"]) != policy_structure(expected_policy(before_policy)):
        raise RepairBlocked("Unapproved policy content change")
    values = {k: v["value"] for k, v in plan["variables"].items()}
    # Includes route_manifest_path/exclusions and global baseline, not just limits.
    expected = {**previous_variables, **APPROVED}
    if values != expected:
        raise RepairBlocked("Unapproved input, quota, expiry or route change")
    tree = ET.fromstring(rendered["policy"])
    if ("demo_expired" in rendered["policy"] or "DateTime.Parse" in rendered["policy"]
            or tree.findall(".//retry") or len(tree.findall(".//forward-request")) != 1
            or len(tree.findall(".//llm-content-safety")) != 3
            or SUBSCRIBER not in rendered["policy"] or "pii_inspection_unavailable" not in rendered["policy"]):
        raise RepairBlocked("Persistent POC security contract violated")


class PersistentRun(ModelsRun):
    def update(self, apply=False):
        saved = WORK / "project-persistent.tfplan"
        variables = WORK / "project-route-persistent.tfvars.json"
        proof = WORK / "project-persistent-review.json"
        previous = {k: v["value"] for k, v in json.loads(self.tf("show", "-json", str(WORK / "project-models.tfplan")))["variables"].items()}
        before = self.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]
        protected = self.hashes()
        if not apply:
            variables.write_text(json.dumps({**previous, **APPROVED}, indent=2))
            (WORK / "project-persistent-rollback-policy.xml").write_text(before)
            self.tf("validate", "-no-color")
            self.tf("plan", "-no-color", "-input=false", "-var-file=" + str(variables), "-out=" + str(saved))
        output = self.tf("console", "-no-color", "-var-file=" + str(variables), text="jsonencode({policy=local.policy})\n")
        rendered = json.loads(json.loads(output[output.find('"'):].strip()))
        plan = json.loads(self.tf("show", "-json", str(saved)))
        guard_persistent_update(plan, rendered, before, previous)
        paths = [ROOT / "infra/project-route/main.tf", ROOT / "gateway/policies/dev-openai.xml.tftpl",
                 ROOT / "gateway/catalog/project-routes.json", ROOT / "scripts/deployment/project_route_persistent.py"]
        record = {"plan_sha256": sha(saved), "sources": {p.relative_to(ROOT).as_posix(): sha(p) for p in paths},
                  "protected": protected, "before_policy_sha256": hashlib.sha256(before.encode()).hexdigest(),
                  "scope": [{"address": POLICY, "actions": ["update"]}], "limits": APPROVED,
                  "counter_identity_and_epoch_preserved": True, "guard_verified": True}
        if not apply:
            proof.write_text(json.dumps(record, indent=2))
        else:
            document = (ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
            status = json.loads((ROOT / ".azure/validate-status.json").read_text())
            if (json.loads(proof.read_text()) != record or status.get("completedStep") != "UpdateStatus"
                    or "Persistent POC validation status: Validated" not in document or record["plan_sha256"] not in document):
                raise RepairBlocked("Current exact-plan validation proof required")
            sub = self.arm("/subscriptions/" + SUBSCRIBER)["properties"]
            if sub.get("state") != "active" or not sub.get("scope", "").endswith("/products/aiflux"):
                raise RepairBlocked("Exact active product subscriber required")
            # No candidate workflow, broad apply, or destructive finally cleanup.
            self.tf("apply", "-no-color", "-input=false", str(saved))
            live = self.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]
            if policy_structure(live) != policy_structure(rendered["policy"]) or self.hashes() != protected:
                raise RepairBlocked("Applied readback or protected hashes differ")
            record.update(applied=True, readback_verified=True, finished_at=datetime.now(UTC).isoformat())
            (WORK / "project-persistent-apply.json").write_text(json.dumps(record, indent=2))
        print(json.dumps(record, indent=2))

    def probes(self):
        key = self.arm("/subscriptions/" + SUBSCRIBER + "/listSecrets", "POST")["primaryKey"]
        base = "/dev/llm/v1"
        body = {"model": "gpt-5.6-luna", "messages": [{"role": "user", "content":
                "Explain how a rainbow forms in approximately 80 words, using plain language."}],
                "max_completion_tokens": 256, "stream": False}
        result = self.probe("output_over32", base + "/chat/completions", key=key, body=body,
                            origin="https://poc-ids-token-ex-customer.azurewebsites.net")
        self.probe("reject_output1025", base + "/chat/completions", key=key, body={**body, "max_completion_tokens": 1025})
        self.probe("missing_key", base + "/models")
        self.probe("invalid_key", base + "/models", key="invalid-persistent-poc-key")
        key = None
        self.report["output_over32_verified"] = bool(result["status"] == 200 and result["assistant_text"]
            and (result.get("usage") or {}).get("completion_tokens", 0) > 32)
        (WORK / "project-persistent-probes.json").write_text(json.dumps(self.report, indent=2))
        print(json.dumps(self.report, indent=2))
        if not self.report["output_over32_verified"]:
            raise RepairBlocked("Actual output greater than32 not demonstrated")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "apply", "probe"])
    args = parser.parse_args()
    try:
        run = PersistentRun()
        run.probes() if args.action == "probe" else run.update(args.action == "apply")
        return 0
    except Exception as exc:
        print(json.dumps({"blocked": type(exc).__name__, "reason": str(exc) if isinstance(exc, RepairBlocked) else "Protected diagnostics only"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())