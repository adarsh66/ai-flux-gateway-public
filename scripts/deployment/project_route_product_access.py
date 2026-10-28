"""One-shot, exact-delta persistent POC product-access release. Never reads keys.

Historical subscriber-only controllers deliberately remain unchanged. This
controller owns only one in-place existing API policy update, with a durable
attempt marker, fresh source/input/baseline binding and independent readback.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import portal_fix as portals
from scripts.deployment import finops_function_stage as fs
from scripts.deployment.apim_route_repair import APIM, RepairBlocked, SUBSCRIBER
from scripts.deployment.project_route_demo import policy_structure
from scripts.deployment.project_route_live import CandidateRun
from scripts.deployment.project_route_models import POLICY
from scripts.deployment.project_route_persistent import APPROVED

HOME = rt.HOME / "product-subscription-access-20261027"
TFROOT = rt.ROOT / "infra/project-route"
CONTOSO = "d9768b6a-415c-5b2c-9c4e-fccaf92db250"
PREDICATE = f' || context.Subscription.Id != "{SUBSCRIBER}"'
PRODUCT_GATE = '@(context.Subscription == null || context.Product == null || context.Product.Id != "aiflux")'


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def require(value, message):
    if not value:
        raise RepairBlocked(message)


def expected_policy(before):
    """Change exactly one parsed eligibility expression; no other normalization."""
    tree = ET.fromstring(before)
    gates = [n for n in tree.findall("./inbound/choose/when")
             if n.get("condition") == PRODUCT_GATE[:-1] + PREDICATE + ")"]
    require(len(gates) == 1, "Exactly one original product/subscriber eligibility gate required")
    gates[0].set("condition", PRODUCT_GATE)
    return ET.tostring(tree, encoding="unicode")


def any_unknown(value):
    return any(any_unknown(v) for v in value.values()) if isinstance(value, dict) else (
        any(any_unknown(v) for v in value) if isinstance(value, list) else value is True)


def guard_product_update(plan, before_policy, previous_variables):
    require(plan.get("applyable") is True and not plan.get("errored")
            and not plan.get("deferred_changes"), "Resolved applyable saved plan required")
    values = {k: v["value"] for k, v in plan.get("variables", {}).items()}
    expected = {**previous_variables, "allow_product_subscriptions": True}
    require(values == expected and all(values.get(k) == v for k, v in APPROVED.items()),
            "Only explicit product-access opt-in may change; exact persistent POC required")
    require(values.get("glm_enabled") is True and values.get("glm_credential_storage") == "apim-internal"
            and values.get("excluded_routes") == [], "Preserve all current GLM-inclusive routes")
    writes = []
    for r in plan.get("resource_changes", []):
        require("/namedValues@" not in str((r["change"].get("after") or {}).get("type", "")),
                "Terraform must not own or read the internal provider secret")
        actions = r["change"]["actions"]
        if actions not in (["no-op"], ["read"]):
            writes.append(r)
    require(len(writes) == 1 and writes[0]["address"] == POLICY
            and writes[0]["change"]["actions"] == ["update"], "Exactly one existing API policy update only")
    c = writes[0]["change"]
    old, new = deepcopy(c["before"]), deepcopy(c["after"])
    target = {"type": "Microsoft.ApiManagement/service/apis/policies@2024-05-01",
              "parent_id": APIM + "/apis/aiflux-dev-unified", "name": "policy"}
    require(all(old.get(k) == v and new.get(k) == v for k, v in target.items()), "Exact existing target required")
    require(not any(any_unknown(v) for k, v in c.get("after_unknown", {}).items() if k != "output"),
            "Unknown writable inputs prohibited")
    require(policy_structure(old["body"]["properties"]["value"]) == policy_structure(before_policy),
            "Fresh live predecessor must equal plan predecessor")
    policy = new["body"]["properties"]["value"]
    require(new["body"] == {"properties": {"format": "rawxml", "value": policy}}, "Exact rawxml body required")
    require(policy_structure(policy) == policy_structure(expected_policy(before_policy)),
            "Unapproved XML delta outside the single eligibility predicate")
    # The provider's computed response may change, but no other writable field.
    new["body"] = old["body"]
    new["output"] = old.get("output")
    require(new == old, "Non-policy resource attributes changed")
    tree = ET.fromstring(policy)
    catalogs = [json.loads(n.text) for n in tree.findall(".//set-body")
                if (n.text or "").startswith('{"data":')]
    require(len(catalogs) == 1 and len(catalogs[0]["data"]) == 11
            and "glm-5.3" in {m["id"] for m in catalogs[0]["data"]}, "Exact eleven-model catalog required")
    require(len(tree.findall(".//forward-request")) == 1 and not tree.findall(".//retry")
            and len(tree.findall(".//llm-content-safety")) == 3
            and "pii_inspection_unavailable" in policy, "Mandatory forwarding and safety contracts required")
    return policy


class ProductRun(CandidateRun):
    def __init__(self):
        os.environ.update(REQUESTS_CA_BUNDLE=rt.CA, SSL_CERT_FILE=rt.CA)
        super().__init__()
        # Existing isolated state only; no init against the main-stack backend.
        require((TFROOT / "terraform.tfstate").is_file(), "Existing isolated state required")

    def terraform(self, *args, text=None):
        import subprocess
        p = subprocess.run([rt.TF, "-chdir=" + str(TFROOT), *args], input=text,
                           env=rt.ENV, capture_output=True, text=True, encoding="utf-8", timeout=600)
        if p.returncode:
            # Keep full Terraform diagnostics private, never stream policy/state.
            (HOME / ("terraform-" + args[0] + "-failure.log")).write_text(p.stdout + p.stderr)
            raise RepairBlocked("Terraform " + args[0] + " failed; private diagnostic retained")
        return p.stdout

    def policy(self):
        # APIM rawxml export may contain unescaped expression attributes and is
        # not parseable XML. The xml export escapes those same expressions;
        # compare decoded structures, never regex-repair an invalid export.
        return self.arm("/apis/aiflux-dev-unified/policies/policy?format=xml")["properties"]["value"]

    def metadata(self):
        rows = {}
        for sid in (SUBSCRIBER, CONTOSO):
            p = self.arm("/subscriptions/" + sid)["properties"]
            require(p.get("state") == "active" and p.get("scope", "").lower() == (APIM + "/products/aiflux").lower(),
                    "Existing active product subscriptions required; use existing admin Reconcile if needed")
            rows[sid] = {k: p.get(k) for k in ("state", "scope", "displayName")}
        require(any(i["name"] == "aiflux-dev-unified" for i in self.arm("/products/aiflux/apis")["value"]),
                "Exact product/API association required")
        return rows

    def protected(self):
        result = {"runtime": portals.baseline(), "settings_hashes": {}}
        settings = fs.current_settings()
        result["settings_hashes"] = {k: fs.sha(v) for k, v in settings.items()}
        result["configured_product"] = settings["api"].get("AIFLUX_APIM_PRODUCT_ID")
        ing = settings["ingestion"]
        result["timer_disabled"] = ing.get("AzureWebJobs.ingest_usage.Disabled")
        result["cutoff"] = ing.get("AIFLUX_INGESTION_START_AT")
        require(result["configured_product"] == "aiflux" and result["timer_disabled"] == "false"
                and result["cutoff"] == "2026-10-27T06:06:02.045288+00:00"
                and result["runtime"]["sites"]["ingestion"]["protected"]["web"]["alwaysOn"] is True,
                "Current working product and FinOps baseline required")
        state = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + rt.RG
                + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex?api-version=2023-05-01"])["properties"]
        acl = state["networkAcls"]
        require(acl["defaultAction"] == "Deny" and {r["value"] for r in acl["ipRules"]}
                == {"167.103.66.248", "167.103.66.93", "167.103.65.36"}, "Preserve exact approved state ACL")
        result["state_network"] = {k: state.get(k) for k in ("networkAcls", "publicNetworkAccess", "allowSharedKeyAccess")}
        result["apim"] = {}
        for name, suffix in (("global", "/policies/policy"), ("legacy", "/apis/aiflux-dev-openai/policies/policy"),
                             ("native", "/apis/aiflux-native-validation-pending/policies/policy")):
            result["apim"][name] = sha(self.arm(suffix + "?format=rawxml")["properties"]["value"])
        for name, suffix in (("backends", "/backends"), ("product", "/products/aiflux"),
                             ("binding", "/products/aiflux/apis"), ("fragments", "/policyFragments"),
                             ("api", "/apis/aiflux-dev-unified"), ("operations", "/apis/aiflux-dev-unified/operations")):
            result["apim"][name] = fs.sha(self.arm(suffix))
        return result

    def sources(self):
        paths = [*TFROOT.glob("*.tf"), TFROOT / ".terraform.lock.hcl",
                 * (rt.ROOT / "gateway/policies").glob("*.tftpl"),
                 rt.ROOT / "gateway/catalog/project-routes.json", Path(__file__), HOME / "inputs.tfvars.json"]
        return {p.relative_to(rt.ROOT).as_posix(): sha(p.read_bytes()) for p in paths}

    def prepare(self):
        from scripts.deployment.run_private_sql import protect_directory
        protect_directory(HOME)
        require(not (HOME / "apply-intent.json").exists(), "Never replay an attempted release")
        previous = json.loads((rt.HOME / "project-route-glm.tfvars.json").read_text())
        require("allow_product_subscriptions" not in previous or previous["allow_product_subscriptions"] is False,
                "Original input profile required")
        before = self.policy()
        expected_policy(before)
        rt.save(HOME / "subscriptions.json", self.metadata())
        baseline = self.protected()
        (HOME / "rollback-policy.xml").write_bytes(before.encode("utf-8"))
        rt.save(HOME / "baseline.json", baseline)
        rt.save(HOME / "inputs.tfvars.json", {**previous, "allow_product_subscriptions": True})
        # Full untargeted plan of the existing narrow root. No imports/refresh-only
        # apply, resource replacement or unrelated drift exemption is authorized.
        self.terraform("init", "-input=false", "-lockfile=readonly", "-no-color")
        require(self.terraform("workspace", "show").strip() == "default", "Existing default workspace only")
        self.terraform("validate", "-no-color")
        self.terraform("plan", "-input=false", "-lock-timeout=30s", "-no-color",
                       "-var-file=" + str(HOME / "inputs.tfvars.json"), "-out=" + str(HOME / "policy.tfplan"))
        plan = json.loads(self.terraform("show", "-json", str(HOME / "policy.tfplan")))
        variables = {k: v["value"] for k, v in plan["variables"].items()}
        # Bind the complete default-expanded predecessor profile, not only the
        # explicitly supplied subset. The sole new variable was default false.
        oldplan = json.loads(self.terraform("show", "-json", str(rt.HOME / "project-glm.tfplan")))
        prior = {k: v["value"] for k, v in oldplan["variables"].items()}
        prior["allow_product_subscriptions"] = False
        policy = guard_product_update(plan, before, prior)
        require(variables == {**prior, "allow_product_subscriptions": True}, "Complete profile must match current GLM inputs")
        rt.save(HOME / "previous-variables.json", prior)
        review = {"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": sha((HOME / "policy.tfplan").read_bytes()),
                  "sources": self.sources(), "baseline_sha256": fs.sha(baseline), "before_policy_sha256": sha(before),
                  "after_policy_sha256": sha(policy), "scope": [{"address": POLICY, "actions": ["update"]}],
                  "guard_verified": True, "builds": 0, "resource_creates": 0, "limits": APPROVED}
        rt.save(HOME / "review.json", review)
        print(json.dumps({k: v for k, v in review.items() if k != "sources"}), flush=True)

    def check(self, baseline=True):
        review = json.loads((HOME / "review.json").read_text())
        require(review["sources"] == self.sources(), "Source/input bytes changed since review")
        require(review["plan_sha256"] == sha((HOME / "policy.tfplan").read_bytes()), "Saved plan bytes changed")
        require(datetime.now(UTC) - datetime.fromisoformat(review["at_utc"]) < timedelta(hours=1), "Fresh plan required")
        before = (HOME / "rollback-policy.xml").read_bytes().decode("utf-8")
        require(sha(before) == review["before_policy_sha256"], "Protected rollback changed")
        prior = json.loads((HOME / "previous-variables.json").read_text())
        plan = json.loads(self.terraform("show", "-json", str(HOME / "policy.tfplan")))
        policy = guard_product_update(plan, before, prior)
        require(sha(policy) == review["after_policy_sha256"], "Target policy hash changed")
        if baseline:
            require(fs.sha(self.protected()) == review["baseline_sha256"], "Live security/runtime baseline drifted")
            require(policy_structure(self.policy()) == policy_structure(before), "Live API policy drifted")
            self.metadata()
        return review, policy

    def apply(self):
        require(not (HOME / "apply-intent.json").exists(), "Apply already attempted; reconcile only, never replay")
        review, _ = self.check()
        proof = json.loads((HOME / "validation.json").read_text())
        require(proof["plan_sha256"] == review["plan_sha256"] and proof["sources"] == review["sources"], "Exact validation required")
        require(json.loads((rt.ROOT / ".azure/validate-status.json").read_text())["completedStep"] == "UpdateStatus",
                "Complete current azure-validate workflow required")
        doc = (rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
        require("Product subscription access status: Validated" in doc and review["plan_sha256"] in doc,
                "Current policy-only Section 7 validation proof required")
        with (HOME / "apply-intent.json").open("x", encoding="utf-8") as f:
            json.dump({"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"]}, f)
        self.terraform("apply", "-input=false", "-no-color", str(HOME / "policy.tfplan"))
        rt.save(HOME / "applied.json", {"applied": True, "at_utc": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"]})
        self.verify()

    def verify(self):
        review, policy = self.check(baseline=False)
        live = self.policy()
        require(policy_structure(live) == policy_structure(policy), "Live target policy readback differs")
        require(fs.sha(self.protected()) == review["baseline_sha256"], "Other protected configuration changed")
        rows = self.metadata()
        result = {"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"],
                  "readback_verified": True, "live_policy_sha256": sha(live), "target_policy_sha256": sha(policy),
                  "normalized_policy_equal": True, "protected_baseline_equal": True,
                  "active_product_subscriptions": rows, "builds": 0, "policy_apply_attempts": 1,
                  "key_reads": 0, "network_writes": 0, "rbac_writes": 0}
        rt.save(HOME / "verified.json", result)
        rt.save(rt.ROOT / "gateway/validation/product-subscription-access-20261027.json", result)
        print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "validate", "apply", "verify"])
    args = parser.parse_args()
    try:
        run = ProductRun()
        if args.action == "plan":
            run.prepare()
        elif args.action == "validate":
            run.terraform("validate", "-no-color")
            review, _ = run.check()
            proof = {**review, "validated_at_utc": datetime.now(UTC).isoformat()}
            rt.save(HOME / "validation.json", proof)
            print(json.dumps(proof), flush=True)
        else:
            getattr(run, args.action)()
        return 0
    except Exception as exc:
        print(json.dumps({"blocked": type(exc).__name__, "reason": str(exc) if isinstance(exc, RepairBlocked)
                          else "Protected diagnostic; no raw Azure/settings output"}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())