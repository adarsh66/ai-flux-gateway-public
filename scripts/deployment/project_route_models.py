"""Exact existing dev-policy update only. No grants, networks, counters or models.

The public token field remains max_completion_tokens; the reviewed manifest
normalizes provider fields inside APIM. Discovery does not grant acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from scripts.deployment.apim_route_repair import RepairBlocked, SUBSCRIBER
from scripts.deployment.project_route_demo import policy_structure
from scripts.deployment.project_route_live import CandidateRun, ROOT, WORK
from scripts.deployment.project_route_quota import PROTECTED

POLICY = "azapi_resource.project_policy[0]"
MANIFEST = ROOT / "gateway/catalog/project-routes.json"
EXPIRY = "2026-10-27T05:41:01Z"
BLOCKED = ["Kimi-K2.7-Code", "grok-4.3", "grok-4-20-reasoning", "grok-4-1-fast-reasoning"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard_model_update(plan, rendered, before_policy, manifest):
    if plan.get("errored") or plan.get("applyable") is not True or plan.get("deferred_changes"):
        raise RepairBlocked("Resolved applyable model policy plan required")
    writes = [r for r in plan.get("resource_changes", [])
              if r["change"]["actions"] not in (["read"], ["no-op"])]
    if len(writes) != 1 or writes[0]["address"] != POLICY or writes[0]["change"]["actions"] != ["update"]:
        raise RepairBlocked("Only the existing owned dev API policy may update")
    change = writes[0]["change"]
    old, new = change["before"], change["after"]
    for field in ("type", "parent_id", "name"):
        if old.get(field) != new.get(field):
            raise RepairBlocked("Policy target changed")
    if (new.get("parent_id", "").endswith("/apis/aiflux-dev-unified") is not True
            or new.get("name") != "policy"):
        raise RepairBlocked("Wrong existing dev API target")
    if policy_structure(old["body"]["properties"]["value"]) != policy_structure(before_policy):
        raise RepairBlocked("Live policy drifted")
    policy = rendered["policy"]
    if new["body"] != {"properties": {"format": "rawxml", "value": policy}}:
        raise RepairBlocked("Plan differs from exact render")
    def unknown(value):
        if isinstance(value, dict):
            return any(unknown(v) for v in value.values())
        if isinstance(value, list):
            return any(unknown(v) for v in value)
        return value is True
    if unknown(change.get("after_unknown", {}).get("body")):
        raise RepairBlocked("Unknown policy body")
    tree, prior = ET.fromstring(policy), ET.fromstring(before_policy)
    for tag in ("cors", "quota-by-key", "rate-limit-by-key", "llm-token-limit", "llm-content-safety", "send-request", "authentication-managed-identity", "forward-request"):
        nodes = tree.findall(".//" + tag)
        previous = prior.findall(".//" + tag)
        if [policy_structure(ET.tostring(n, encoding="unicode")) for n in nodes] != [
                policy_structure(ET.tostring(n, encoding="unicode")) for n in previous]:
            raise RepairBlocked("Protected security policy changed: " + tag)
    if tree.findall(".//retry") or len(list(tree.find("backend"))) != 1:
        raise RepairBlocked("Exactly one backend child and no retries required")
    variables = {k: v["value"] for k, v in plan["variables"].items()}
    fixed = {"rpm_limit": 60, "tpm_limit": 1000, "daily_token_quota": 10000,
             "daily_call_allowance": 1000, "completion_token_limit": 32,
             "backend_retries": 0, "safety_threshold": 1, "demo_expires_at": EXPIRY,
             "demo_authorized": True, "candidate_validation": False, "acceptance_verified": False}
    if any(variables.get(k) != v for k, v in fixed.items()):
        raise RepairBlocked("Approved demo limits, expiry and flags must not change")
    if datetime.now(UTC) >= datetime.fromisoformat(EXPIRY.replace("Z", "+00:00")):
        raise RepairBlocked("Demo expired; explicit new expiry required")
    if (SUBSCRIBER not in policy or policy.count('DateTime.Parse("' + EXPIRY + '")') != 1
            or "pii_inspection_unavailable" not in policy):
        raise RepairBlocked("Subscriber, expiry or fail-closed PII missing")
    routes = set(manifest["routes"]) - set(variables.get("excluded_routes", []))
    if "gpt-5.6-luna" not in routes or "Decision-1" in routes:
        raise RepairBlocked("Preserve Luna; Decision-1 is not a chat route")
    lists = [json.loads(n.text) for n in tree.findall(".//set-body")
             if (n.text or "").startswith('{"data":') or (n.text or "").startswith('{"object":"list"')]
    if len(lists) != 1 or {m["id"] for m in lists[0]["data"]} != routes:
        raise RepairBlocked("Exact manifest /models equality required")
    dispatch = [n for n in tree.findall(".//when") if n.find("set-backend-service") is not None]
    expected = {f'@((string)context.Variables["aiflux-model"] == "{alias}")' for alias in routes}
    if {n.get("condition") for n in dispatch} != expected or len(dispatch) != len(routes):
        raise RepairBlocked("Exact deployment dispatch required")
    if any(n.find("set-backend-service").get("backend-id") != "aiflux-project-gpt-5-6-luna" for n in dispatch):
        raise RepairBlocked("Only the existing exact-account backend is authorized")
    if manifest.get("upstream_url") != "https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1":
        raise RepairBlocked("Wrong upstream account or dialect")


class ModelsRun(CandidateRun):
    def hashes(self):
        return {name: hashlib.sha256(self.arm(suffix + "?format=rawxml")["properties"]["value"].encode()).hexdigest()
                for name, suffix in PROTECTED}

    def update(self, apply=False):
        variables = WORK / "project-route-models.tfvars.json"
        saved = WORK / "project-models.tfplan"
        proof = WORK / "project-models-review.json"
        manifest = json.loads(MANIFEST.read_text())
        before = self.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]
        protected = self.hashes()
        if not apply:
            values = json.loads((WORK / "project-route-quota.tfvars.json").read_text())
            values["route_manifest_path"] = MANIFEST.as_posix()
            values["excluded_routes"] = BLOCKED
            variables.write_text(json.dumps(values, indent=2))
            self.tf("validate", "-no-color")
            self.tf("plan", "-no-color", "-input=false", "-var-file=" + str(variables), "-out=" + str(saved))
        output = self.tf("console", "-no-color", "-var-file=" + str(variables),
                         text="jsonencode({policy=local.policy})\n")
        rendered = json.loads(json.loads(output[output.find('"'):].strip()))
        plan = json.loads(self.tf("show", "-json", str(saved)))
        guard_model_update(plan, rendered, before, manifest)
        sources = {p.relative_to(ROOT).as_posix(): sha(p) for p in [MANIFEST,
                   ROOT / "infra/project-route/main.tf", ROOT / "gateway/policies/dev-openai.xml.tftpl",
                   ROOT / "scripts/deployment/project_route_models.py"]}
        record = {"plan_sha256": sha(saved), "sources": sources, "protected": protected,
                  "before_policy_sha256": hashlib.sha256(before.encode()).hexdigest(),
                  "models": sorted(manifest["routes"]), "demo_expires_at": EXPIRY,
                  "scope": [{"address": POLICY, "actions": ["update"]}], "guard_verified": True}
        if not apply:
            # Protected rollback is local only; no key/credential material.
            rollback = WORK / "project-models-original-rollback-policy.xml"
            if not rollback.exists():
                rollback.write_text(before)
            (WORK / "project-models-predecessor-policy.xml").write_text(before)
            proof.write_text(json.dumps(record, indent=2))
        else:
            if json.loads(proof.read_text()) != record:
                raise RepairBlocked("Saved plan, sources or protected baselines changed after review")
            sub = self.arm("/subscriptions/" + SUBSCRIBER)["properties"]
            if sub.get("state") != "active" or not sub.get("scope", "").endswith("/products/aiflux"):
                raise RepairBlocked("Exact existing active subscriber required")
            self.tf("apply", "-no-color", "-input=false", str(saved))
            live = self.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]
            if policy_structure(live) != policy_structure(rendered["policy"]) or self.hashes() != protected:
                raise RepairBlocked("Applied policy or protected baseline readback mismatch")
            record["applied"] = True
            (WORK / "project-models-apply.json").write_text(json.dumps(record, indent=2))
        print(json.dumps(record, indent=2))

    def probes(self, models=None):
        manifest = json.loads(MANIFEST.read_text())
        key = self.arm("/subscriptions/" + SUBSCRIBER + "/listSecrets", "POST")["primaryKey"]
        base = "/dev/llm/v1"
        selected = models or list(manifest["routes"])
        if not set(selected) <= set(manifest["routes"]):
            raise RepairBlocked("Only exact manifest deployments may be probed")
        for alias in selected:
            self.probe(alias, base + "/chat/completions", key=key,
                       body={"model": alias, "messages": [{"role": "user", "content": "Reply with Hello."}],
                             "max_completion_tokens": 32, "stream": False},
                       origin="https://poc-ids-token-ex-customer.azurewebsites.net")
        for name, supplied in (("missing-key", None), ("invalid-key", "invalid-model-test-key")):
            self.probe(name, base + "/models", key=supplied)
        for alias in ("Decision-1", "unknown-model"):
            self.probe("reject-" + alias, base + "/chat/completions", key=key,
                       body={"model": alias, "messages": [{"role": "user", "content": "Hello"}], "max_completion_tokens": 32})
        for origin in ("https://poc-ids-token-ex-customer.azurewebsites.net", "https://poc-ids-token-ex-admin.azurewebsites.net", "https://untrusted.invalid"):
            self.probe("cors", base + "/chat/completions", method="OPTIONS", origin=origin)
        self.report.update(strict_rpm_verified=False, pricing_verified=False, output_limit=32,
                           demo_expires_at=EXPIRY, browser_verified=False)
        path = WORK / ("project-models-probes-selected.json" if models else "project-models-probes.json")
        path.write_text(json.dumps(self.report, indent=2))
        print(json.dumps(self.report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "apply", "probe"])
    parser.add_argument("--models", help="Comma-separated exact deployments; each is sent once without retries")
    args = parser.parse_args()
    run = ModelsRun()
    try:
        if args.action == "probe":
            run.probes(args.models.split(",") if args.models else None)
        else:
            run.update(apply=args.action == "apply")
        return 0
    except Exception as exc:
        print(json.dumps({"blocked": type(exc).__name__, "reason": str(exc) if isinstance(exc, RepairBlocked) else "See protected local diagnostics"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())