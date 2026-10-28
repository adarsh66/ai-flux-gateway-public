"""One detached fragment, existing state/owner, durable stages; never activate."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import ssl
import subprocess
import sys
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment.project_route_product_access import ProductRun, sha, any_unknown
from scripts.deployment.apim_route_repair import APIM

HOME = rt.HOME / "poc-fragment-bootstrap-20261028"
TFROOT = rt.ROOT / "infra/project-route"
FRAGMENT = "aiflux-dev-unified-poc-settings"
ID = APIM + "/policyFragments/" + FRAGMENT
ADDRESS = "azapi_resource.poc_settings[0]"
DEFAULTS = rt.ROOT / "gateway/policies/poc-settings-defaults.xml"
INPUT = HOME / "inputs.tfvars.json"
PLAN = HOME / "fragment.tfplan"
ACTIVE_INPUT = rt.HOME / "fireworks-models-20261028-formatted/inputs.tfvars.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def checkpoint(stage, **values):
    HOME.mkdir(parents=True, exist_ok=True)
    path = HOME / "result.json"
    result = load(path) if path.exists() else {"cloud_writes": 0}
    event = {"at_utc": datetime.now(UTC).isoformat(), "stage": stage, **values}
    result.update(event)
    result.setdefault("history", []).append(event)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(json.dumps(event), flush=True)


def xml(value):
    return ET.canonicalize(value.strip(), strip_text=True)


def without_created_fragment(response):
    """Remove only the exact allowed new object and its measured list count."""
    result = deepcopy(response)
    rt.require(not result.get("nextLink"), "fragment_pagination")
    rows = result["value"]
    matches = [r for r in rows if r["name"] == FRAGMENT]
    rt.require(len(matches) <= 1 and all(r["id"].lower() == ID.lower() for r in matches),
               "fragment_collection_exact_identity")
    if "count" in result:
        rt.require(type(result["count"]) is int and result["count"] == len(rows), "fragment_collection_count_contract")
        result["count"] -= len(matches)
    result["value"] = [r for r in rows if r["name"] != FRAGMENT]
    return result


def guard(plan):
    rt.require(plan.get("applyable") is True and not plan.get("errored")
               and not plan.get("deferred_changes"), "resolved_applyable_plan_required")
    rt.require(all(c.get("status") == "pass" for c in plan.get("checks", [])), "all_preconditions_pass_required")
    writes = [r for r in plan.get("resource_changes", [])
              if r["change"]["actions"] not in (["no-op"], ["read"])]
    rt.require(len(writes) == 1 and writes[0]["address"] == ADDRESS, "exactly_one_fragment_write")
    change = writes[0]["change"]
    rt.require(change["actions"] == ["create"] and change.get("before") is None, "fragment_create_only")
    after = change["after"]
    rt.require(after["name"] == FRAGMENT and after["parent_id"] == APIM
               and after["type"] == "Microsoft.ApiManagement/service/policyFragments@2024-05-01",
               "exact_fragment_target")
    rt.require(after["body"] == {"properties": {
        "description": "Runtime-owned bounded POC variables and literal-call quota; stable counter identity and envelope.",
        "format": "rawxml", "value": DEFAULTS.read_text(encoding="utf-8")}}, "exact_safe_default_body")
    rt.require(not any(any_unknown(v) for k, v in change.get("after_unknown", {}).items()
                       if k not in ("id", "output")), "unknown_writable_input")
    values = {k: v["value"] for k, v in plan["variables"].items()}
    rt.require(values["enabled"] is True and values["poc_settings_bootstrap_enabled"] is True
               and values["poc_controls_enabled"] is False
               and values["poc_publisher_permissions_verified"] is False, "creation_not_activation")
    supplied = load(INPUT)
    rt.require(all(values.get(k) == v for k, v in supplied.items()), "exact_supplied_inputs")
    from scripts.deployment.project_route_persistent import APPROVED
    rt.require(all(values.get(k) == v for k, v in APPROVED.items())
               and values["allow_product_subscriptions"] is True
               and values["glm_enabled"] is True and values["excluded_routes"] == [], "protected_profile")
    # All preexisting managed resources must actually be present and no-op.
    state = load(HOME / "state-before-summary.json")
    for address in state["managed_addresses"]:
        matches = [r for r in plan["resource_changes"] if r["address"] == address]
        rt.require(len(matches) == 1 and matches[0]["change"]["actions"] == ["no-op"],
                   "existing_resource_not_noop:" + address)
    policies = [r for r in plan["resource_changes"] if r["address"] == "azapi_resource.project_policy[0]"]
    rt.require(len(policies) == 1, "existing_live_policy_required")
    value = policies[0]["change"]["after"]["body"]["properties"]["value"]
    rt.require("<include-fragment" not in value, "no_policy_include")
    tree = ET.fromstring(value)
    catalogs = [json.loads(n.text) for n in tree.findall(".//set-body") if (n.text or "").startswith('{"data":')]
    rt.require(len(catalogs) == 1 and len(catalogs[0]["data"]) == 13
               and {"FW-GLM-5.3", "FW-MiniMax-M3", "glm-5.3"}
               <= {m["id"] for m in catalogs[0]["data"]}, "preserve_live_thirteen_models")
    return {"address": ADDRESS, "actions": ["create"], "existing_managed_noops": len(state["managed_addresses"])}


class Bootstrap(ProductRun):
    def terraform(self, *args, text=None):
        p = subprocess.run([rt.TF, "-chdir=" + str(TFROOT), *args], input=text,
                           cwd=rt.ROOT, env=rt.ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
        # Never publish plan/state/settings bodies. Diagnostics remain local.
        if p.returncode:
            (HOME / ("terraform-" + args[0] + "-failure.log")).write_text(p.stdout + p.stderr, encoding="utf-8")
            errors = re.findall(r"^Error: ([^\r\n]+)", p.stdout + p.stderr, re.M)
            raise RuntimeError("terraform_" + args[0] + "_failed:" + ",".join(errors))
        if args[0] in ("init", "fmt", "validate", "test", "plan", "apply"):
            (HOME / ("terraform-" + args[0] + ".log")).write_text(p.stdout + p.stderr, encoding="utf-8")
        return p.stdout

    def exact(self):
        try:
            # XML export preserves escaped C# attribute values for structural
            # comparison; rawxml exports can contain unescaped expression quotes.
            result = self.arm("/policyFragments/" + FRAGMENT + "?format=xml")
            rt.require(result["id"].lower() == ID.lower(), "exact_get_id_mismatch")
            return result
        except HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError("exact_fragment_get_http_" + str(error.code)) from None

    def protected_complete(self):
        result = self.protected()
        # Creation is the only allowed collection difference. Preserve every old
        # fragment and independently hash the active policy (not in old helper).
        fragments = without_created_fragment(self.arm("/policyFragments"))
        result["apim"]["fragments"] = fs.sha(fragments)
        result["active_policy_sha256"] = sha(self.policy())
        result["gateway_identity"] = self.arm("").get("identity")
        account = rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
        deployments = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + account + "/deployments?api-version=2025-06-01"])
        rt.require(not deployments.get("nextLink"), "deployment_pagination")
        result["model_metadata_sha256"] = fs.sha(deployments)
        settings = fs.current_settings()["api"]
        rt.require(settings.get("AIFLUX_GATEWAY_CONTROLS_POC_ENABLED", "false").lower() == "false"
                   and settings.get("AIFLUX_GATEWAY_CONTROLS_V2_ENABLED", "false").lower() == "false"
                   and json.loads(settings.get("AIFLUX_GATEWAY_SETTINGS_SCOPES", "[]")) == [], "controls_must_remain_off")
        return result

    def sources(self):
        paths = [*TFROOT.glob("*.tf"), *TFROOT.glob("*.tfvars*"), TFROOT / ".terraform.lock.hcl",
                 *TFROOT.glob("tests/*.tftest.hcl"), DEFAULTS, Path(__file__),
                 rt.ROOT / "scripts/deployment/poc_fragment_bootstrap_validation.py",
                 rt.ROOT / "scripts/deployment/poc_fragment_bootstrap_exact.py",
                 rt.ROOT / "tests/unit/test_poc_fragment_bootstrap.py",
                 rt.ROOT / "gateway/policies/dev-openai.xml.tftpl", INPUT, ACTIVE_INPUT,
                 rt.ROOT / "gateway/catalog/fireworks-candidate-routes.json",
                 rt.ROOT / "gateway/catalog/project-routes.json"]
        return {p.relative_to(rt.ROOT).as_posix(): sha(p.read_bytes()) for p in paths}

    def preflight(self):
        from scripts.deployment.run_private_sql import protect_directory
        protect_directory(HOME)
        checkpoint("preflight_started", cloud_writes=0)
        rt.require(not (HOME / "apply-intent.json").exists(), "apply_intent_exists_reconcile_only")
        ssl.create_default_context(cafile=rt.CA)
        a = rt.cli(["account", "show"])
        rt.require(a["id"] == rt.SUB and a["tenantId"] == rt.TENANT
                   and a["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "account_scope")
        existing = self.exact()  # FIRST resource request: never overwrite existing.
        checkpoint("exact_get_complete", fragment_exists=existing is not None, resource_id=ID,
                   existing_xml_matches_defaults=(xml(existing["properties"]["value"]) == xml(DEFAULTS.read_text())) if existing else None)
        if existing:
            checkpoint("existing_fragment_reconciled_no_overwrite", cloud_writes=0,
                       provisioning_state=existing["properties"].get("provisioningState"))
            return
        rt.require(not (TFROOT / ".terraform.tfstate.lock.info").exists(), "existing_state_lock")
        state = load(TFROOT / "terraform.tfstate")
        addresses = []
        for resource in state["resources"]:
            if resource["mode"] != "managed":
                continue
            for instance in resource["instances"]:
                index = instance.get("index_key")
                addresses.append(resource["type"] + "." + resource["name"] +
                                 ("[" + json.dumps(index) + "]" if index is not None else ""))
        rt.require(ADDRESS not in addresses, "state_fragment_without_live_resource")
        rt.save(HOME / "state-before-summary.json", {"serial": state["serial"], "lineage": state["lineage"],
                "sha256": sha((TFROOT / "terraform.tfstate").read_bytes()), "managed_addresses": sorted(addresses)})
        inputs = load(ACTIVE_INPUT)
        rt.save(HOME / "predecessor-inputs.tfvars.json", inputs)
        rt.require(inputs["route_manifest_path"].endswith("fireworks-candidate-routes.json") and inputs["enabled"] is True, "current_thirteen_model_inputs")
        markers = {}
        for name in ("fireworks-models-20261028-formatted", "fireworks-live-20261028/preserved-image-plan"):
            directory = rt.HOME / name
            markers[name] = {n: (directory / n).exists() for n in ("apply-intent.json", "applied.json", "verified.json", "independently-verified.json", "verification.json")}
            rt.require(markers[name]["applied.json"] and any(markers[name][n] for n in ("verified.json", "independently-verified.json", "verification.json")), "historical_release_must_be_applied_verified")
        checkpoint("state_inputs_markers_reconciled", state_serial=state["serial"], state_lineage=state["lineage"], markers=markers)
        baseline = self.protected_complete()
        rt.save(HOME / "baseline.json", baseline)
        rt.save(HOME / "preflight.json", {"at_utc": datetime.now(UTC).isoformat(), "baseline_sha256": fs.sha(baseline), "cloud_writes": 0})
        checkpoint("preflight_complete", protected_baseline_sha256=fs.sha(baseline), active_policy_sha256=baseline["active_policy_sha256"], cloud_writes=0)

    def tests(self):
        checkpoint("offline_tests_started")
        rt.require(self.terraform("workspace", "show").strip() == "default", "default_workspace_required")
        self.terraform("fmt", "-check", "poc-controls.tf", "tests/poc-controls.tftest.hcl")
        self.terraform("validate", "-no-color")
        output = self.terraform("test", "-no-color", "-filter=tests\\defaults.tftest.hcl",
                                "-filter=tests\\external.tftest.hcl", "-filter=tests\\poc-controls.tftest.hcl")
        rt.require(re.search(r"Success! \d+ passed, 0 failed", output), "actual_terraform_tests_required")
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/unit/test_poc_fragment_bootstrap.py",
                            "tests/unit/test_poc_controls.py", "tests/unit/test_fireworks_addition.py",
                            "tests/contract/test_gateway_dev_policy.py", "--junitxml=" + str(HOME / "tests.xml")],
                           cwd=rt.ROOT, env=rt.ENV, capture_output=True, text=True, encoding="utf-8")
        (HOME / "pytest.log").write_text(p.stdout + p.stderr, encoding="utf-8")
        rt.require(p.returncode == 0, "focused_tests_failed")
        root = ET.parse(HOME / "tests.xml").getroot()
        suites = [root] if root.tag == "testsuite" else list(root)
        passed = sum(int(s.get("tests", 0)) for s in suites)
        rt.require(passed > 0 and not any(int(s.get(k, 0)) for s in suites for k in ("errors", "failures")), "test_proof_required")
        rt.save(HOME / "tests.json", {"at_utc": datetime.now(UTC).isoformat(), "python_tests": passed,
                "terraform_summary": re.search(r"Success! \d+ passed, 0 failed", output).group(),
                "junit_sha256": sha((HOME / "tests.xml").read_bytes())})
        checkpoint("offline_tests_complete", **load(HOME / "tests.json"))

    def prepare(self):
        checkpoint("plan_preparation_started")
        rt.require(not (HOME / "plan-intent.json").exists() and not (HOME / "apply-intent.json").exists(), "plan_attempt_exists_inspect_only")
        rt.require(self.exact() is None, "fragment_now_exists_no_overwrite")
        preflight = load(HOME / "preflight.json")
        rt.require(datetime.now(UTC) - datetime.fromisoformat(preflight["at_utc"]) < timedelta(hours=2), "preflight_expired")
        rt.require(self.protected_complete() == load(HOME / "baseline.json"), "fresh_baseline_drift")
        inputs = load(HOME / "predecessor-inputs.tfvars.json")
        inputs.update(poc_settings_bootstrap_enabled=True, poc_controls_enabled=False, poc_publisher_permissions_verified=False)
        rt.save(INPUT, inputs)
        rt.require(self.terraform("workspace", "show").strip() == "default", "workspace")
        self.terraform("init", "-input=false", "-lockfile=readonly", "-no-color")
        self.terraform("validate", "-no-color")
        with (HOME / "plan-intent.json").open("x") as handle:
            json.dump({"at_utc": datetime.now(UTC).isoformat(), "source_state": str(TFROOT / "terraform.tfstate")}, handle)
        checkpoint("saved_plan_started")
        self.terraform("plan", "-input=false", "-no-color", "-lock-timeout=30s", "-var-file=" + str(INPUT), "-out=" + str(PLAN))
        plan = json.loads(self.terraform("show", "-json", str(PLAN)))
        summary = guard(plan)
        review = {"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": sha(PLAN.read_bytes()),
                  "sources": self.sources(), "baseline_sha256": fs.sha(load(HOME / "baseline.json")),
                  "scope": summary, "tests": load(HOME / "tests.json")}
        rt.save(HOME / "review.json", review)
        checkpoint("saved_plan_guard_passed", plan_sha256=review["plan_sha256"], scope=summary, cloud_writes=0)

    def check(self, live=True):
        review = load(HOME / "review.json")
        rt.require(review["sources"] == self.sources(), "source_or_input_drift")
        rt.require(review["plan_sha256"] == sha(PLAN.read_bytes()), "saved_plan_bytes_drift")
        guard(json.loads(self.terraform("show", "-json", str(PLAN))))
        if live:
            rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at_utc"]) < timedelta(hours=2), "plan_expired")
            rt.require(self.exact() is None, "fragment_exists_no_overwrite")
            rt.require(self.protected_complete() == load(HOME / "baseline.json"), "live_protected_baseline_drift")
        return review

    def apply(self):
        rt.require(not (HOME / "apply-intent.json").exists(), "attempt_exists_reconcile_before_any_retry")
        checkpoint("preapply_recheck_started")
        review = self.check()
        proof = load(HOME / "validation.json")
        rt.require(proof["checks_passed"] and proof["plan_sha256"] == review["plan_sha256"]
                   and proof["sources"] == review["sources"], "independent_exact_validation_required")
        rt.require(load(rt.ROOT / ".azure/validate-status.json")["completedStep"] == "UpdateStatus", "workflow_incomplete")
        doc = (rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
        rt.require("Fragment bootstrap status: Validated" in doc and review["plan_sha256"] in doc, "section7_exact_proof_required")
        # Persist creation in the same root for future ordinary plans. Do not edit
        # historical reviewed Fireworks input artifacts or invent a second owner.
        rt.require(load(TFROOT / "poc-settings-bootstrap.auto.tfvars.json") == {"poc_settings_bootstrap_enabled": True}, "persistent_bootstrap_required")
        with (HOME / "apply-intent.json").open("x") as handle:
            json.dump({"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"]}, handle)
        checkpoint("exclusive_apply_started", apply_attempts=1, plan_sha256=review["plan_sha256"], cloud_writes="pending_reconciliation")
        self.terraform("apply", "-input=false", "-no-color", str(PLAN))
        rt.save(HOME / "applied.json", {"at_utc": datetime.now(UTC).isoformat(), "plan_sha256": review["plan_sha256"]})
        checkpoint("fragment_created_pending_independent_verification", cloud_writes=1, resource_id=ID)

    def verify(self):
        checkpoint("independent_readback_started")
        rt.require((HOME / "apply-intent.json").exists(), "no_apply_attempt_to_reconcile")
        review = self.check(live=False)
        actual = self.exact()
        rt.require(actual is not None, "fragment_not_found_after_attempt_no_automatic_retry")
        properties = actual["properties"]
        expected = DEFAULTS.read_text(encoding="utf-8")
        rt.require(xml(properties["value"]) == xml(expected), "fragment_xml_readback_mismatch")
        rt.require(properties.get("provisioningState") == "Succeeded", "fragment_provisioning_not_succeeded")
        baseline = self.protected_complete()
        rt.require(baseline == load(HOME / "baseline.json"), "protected_postapply_mismatch")
        state = load(TFROOT / "terraform.tfstate")
        rt.require(state["lineage"] == load(HOME / "state-before-summary.json")["lineage"], "state_lineage_changed")
        matches = [v for r in state["resources"] if r["mode"] == "managed" and r["name"] == "poc_settings"
                   for v in r["instances"] if v["attributes"]["id"].lower() == ID.lower()]
        rt.require(len(matches) == 1, "existing_owner_state_binding_required")
        proof = {"at_utc": datetime.now(UTC).isoformat(), "resource_id": actual["id"],
                 "portal_url": "https://portal.azure.com/#resource" + actual["id"] + "/overview",
                 "plan_sha256": review["plan_sha256"], "xml_sha256": sha(properties["value"]),
                 "xml_canonical_sha256": sha(xml(properties["value"])), "provisioning_state": properties["provisioningState"],
                 "protected_baseline_equal_except_new_fragment": True, "active_policy_sha256": baseline["active_policy_sha256"],
                 "all_four_settings_hashes_equal": True, "all_four_images_equal": True,
                 "same_state_lineage": state["lineage"], "state_serial": state["serial"],
                 "cloud_writes": 1, "role_writes": 0, "activation_writes": 0, "inference_requests": 0,
                 "apply_attempts": 1, "publisher_permission_verified": False}
        rt.save(HOME / "verified.json", proof)
        checkpoint("created_and_independently_verified", **proof)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("preflight", "tests", "plan", "validate", "apply", "verify"))
    stage = parser.parse_args().stage
    try:
        run = Bootstrap()
        if stage == "validate":
            from scripts.deployment.poc_fragment_bootstrap_validation import validate
            validate(run)
        else:
            getattr(run, "prepare" if stage == "plan" else stage)()
    except Exception as error:
        safe = str(error) if isinstance(error, RuntimeError) else "sensitive_diagnostic_suppressed"
        checkpoint("stage_failed", failed_stage=stage, error_type=type(error).__name__, reason=safe,
                   apply_intent_exists=(HOME / "apply-intent.json").exists())
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()