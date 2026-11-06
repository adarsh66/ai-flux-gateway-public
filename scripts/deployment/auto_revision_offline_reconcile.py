"""Read-only reconciliation of correction02. Never replan, apply or replay create.

Keep the bound preparer/tests unchanged. Only derived, unconfigured name and
parent_id unknowns are reconciled in a copy passed to the original exact guard.
Provider schema and embedded expressions must establish that derivation first.
Independent review and actual postapply flat-list offline proof remain required.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from scripts.deployment import auto_revision_offline_correct as c

p, v = c.p, c.v
PACKAGE = c.e.HOME / "offline-correction02"
OUT = PACKAGE / "reconciliation01"
TARGET_SHA = "5dbef5da261a633ad32702b7cc1ec037ea610c424daa8a06d3e704be7e7a0046"
FULL_SHA = "a9bc71358482aeb4d7fb85394f28f185399c021cc120e4c6a25ca3202df4a2ad"
DERIVED = {"name", "parent_id"}


def load(name):
    return json.loads((PACKAGE / name).read_bytes())


def guard(plan, selection, attributes):
    """Allow only omitted computed identity outputs, not writable unknowns."""
    rows = [r for r in plan["resource_changes"] if r["address"] == c.ADDRESS]
    p.rt.require(len(rows) == 1, "one_exact_patch")
    row = rows[0]
    expressions = next(r for r in plan["configuration"]["root_module"]["resources"]
                       if r["address"] == c.ADDRESS.split("[")[0])["expressions"]
    p.rt.require(not DERIVED.intersection(expressions), "derived_identity_must_be_unconfigured")
    p.rt.require(expressions.get("body") == {"constant_value": {"properties": {"isOnline": False}}},
                 "embedded_body_constant_locked")
    unknown = row["change"].get("after_unknown", {})
    for key in DERIVED:
        p.rt.require(attributes.get(key, {}).get("computed") is True
                     and attributes[key].get("type") == "string", "provider_computed_identity_required")
        p.rt.require(unknown.get(key, False) is False or unknown.get(key) is True,
                     "derived_unknown_shape")
        p.rt.require(row["change"]["after"].get(key) is None, "no_alternative_identity_input")
    # Do NOT clear any other unknown. The original guard still checks exact
    # resource_id, fully known false body, one write, and all activation flags.
    checked = deepcopy(plan)
    checked_row = next(r for r in checked["resource_changes"] if r["address"] == c.ADDRESS)
    for key in DERIVED:
        checked_row["change"].get("after_unknown", {}).pop(key, None)
    return c.guard(checked, selection)


def artifacts():
    p.rt.require(p.sha(PACKAGE / "take-offline.tfplan") == TARGET_SHA
                 and p.sha(PACKAGE / "full-NEVER-APPLY.tfplan") == FULL_SHA, "retained_plan_bytes")
    frozen = load("sources.json")
    p.rt.require(all(p.sha(p.rt.ROOT / name) == digest for name, digest in frozen.items()),
                 "original_source_binding_drift")
    owner = load("state-owner.json")
    state = json.loads((p.ROOT / "terraform.tfstate").read_bytes())
    p.rt.require(owner["serial"] == state["serial"] == 185
                 and owner["lineage"] == state["lineage"] == p.LINEAGE
                 and p.sha(p.ROOT / "terraform.tfstate") == owner["sha256"]
                 and not (p.ROOT / ".terraform.tfstate.lock.info").exists(), "existing_state_185_exact")
    p.rt.require(not any(r["type"] == "azapi_update_resource" and r["name"] == "auto_stage_offline"
                         for r in state["resources"]), "patch_already_owned_reconcile_only")
    p.rt.require(not list(PACKAGE.rglob("*apply-intent*")), "patch_apply_intent_exists")
    receipt = v.load("execution01/apply-result.json")
    p.rt.require(receipt["attempts"] == 1 and receipt["exit_code"] == 0
                 and receipt["saved_plan_sha256"] == v.PLAN_SHA, "original_create_receipt")
    return owner


def fresh(name):
    artifacts()
    workers = p.backend.workers()
    v.save(name + "-workers.json", workers)
    p.require_no_competing_workers(workers)
    baseline = p.release.snapshot()
    supplement = v.supplemental(baseline)
    v.save(name + "-protected.json", baseline)
    v.save(name + "-supplemental.json", supplement)
    p.rt.require(len(baseline) == 13 and baseline == load("protected-before.json")
                 == v.load("protected-before.json")
                 and supplement == load("supplemental-before.json")
                 == v.load("supplemental-before.json"), "all13_supplemental_exact")
    selection = v.load("result.json")["reservation"]
    rows = [p.summarize_revision(r) for r in p.collection("https://management.azure.com" + p.APIM
            + "/apis/" + p.API + "/revisions?api-version=" + p.VERSION)]
    v.save(name + "-flat-revisions.json", rows)
    p.rt.require(rows == load("revisions-before.json"), "actual_flat_revision_drift")
    owned = [r for r in rows if r["revision"] == selection["revision"]]
    current = [r for r in rows if r["is_current"] is True]
    p.rt.require(len(owned) == 1 and owned[0]["is_current"] is False
                 and owned[0]["is_online"] is True and len(current) == 1
                 and current[0]["revision"] == "1" and current[0]["is_online"] is True,
                 "explicit_current1_owned2_online_before_patch")
    run = p.release.ProductRun()
    api = run.arm("/apis/" + p.API + ";rev=" + selection["revision"])
    props = api["properties"]
    p.rt.require(api["id"].lower() == (p.APIM + "/apis/" + p.API + ";rev=" + selection["revision"]).lower()
                 and props["apiRevisionDescription"] == p.expected_body(selection)["properties"]["apiRevisionDescription"]
                 and props["path"] == "dev/llm/v1" and props["subscriptionRequired"] is True,
                 "exact_revision_nonce_metadata")
    current_props = run.arm("/apis/" + p.API)["properties"]
    original = v.load("current-api-metadata.json")
    p.rt.require({k: current_props.get(k) for k in original} == original, "current_revision1_exact")
    head = p.backend.blob_head()
    v.save(name + "-remote-head.json", head)
    prior = load("remote-head-before.json")
    p.rt.require(all(head[k] == prior[k] for k in ("etag", "content_length", "last_modified", "lease_status", "lease_state")),
                 "remote_runtime_state_unchanged")
    markers = p.backend.markers()
    old = load("historical-markers-before.json")
    prefix = PACKAGE.relative_to(p.rt.ROOT).as_posix() + "/"
    p.rt.require(all(markers.get(k) == value for k, value in old.items())
                 and all(k.startswith(prefix) for k in markers.keys() - old.keys()), "foreign_intent_or_history_drift")
    v.save(name + "-markers.json", markers)
    return baseline


def main():
    p.rt.require(sys.argv[1:] == ["validate-retained-once"] and not OUT.exists(), "exclusive_no_replay")
    p.release.fs.protect(OUT)
    v.OUT = OUT
    stage = "bindings"
    try:
        # A separate manifest binds this new code, all prior evidence and inputs.
        retained = {f.name: p.sha(f) for f in PACKAGE.iterdir() if f.is_file()}
        tooling = {str(f.relative_to(p.rt.ROOT)): p.sha(f) for f in
                   (Path(__file__), p.rt.ROOT / "tests/unit/test_auto_revision_offline_reconcile.py")}
        v.save("binding.json", {"at_utc": p.now(), "retained": retained, "new_tooling": tooling,
               "original_sources_unchanged": True, "original_failed_guard_preserved": True})
        artifacts()
        p.persistence.transport()
        account = p.rt.cli(["account", "show"])
        p.rt.require(account["id"] == p.rt.SUB and account["tenantId"] == p.rt.TENANT, "exact_account")
        stage = "fresh_before"
        before = fresh("before")
        for step in ("None", "LoadPlan", "AddValidationSteps"):
            v.workflow(step)
        stage = "actual_recipe_preflight"
        v.tf("version", "-json")
        v.tf("init", "-input=false", "-lockfile=readonly", "-no-color")
        v.tf("fmt", "-check")
        validation = json.loads(v.tf("validate", "-json"))
        p.rt.require(validation["valid"] and not validation["error_count"], "actual_tf_validate")
        p.rt.require(v.tf("workspace", "show").strip() == "default", "existing_default_workspace")
        addresses = v.tf("state", "list").splitlines()
        p.rt.require(p.ADDRESS in addresses and p.POLICY in addresses and c.ADDRESS not in addresses, "state_addresses")
        state = json.loads(v.tf("state", "pull"))
        owner = artifacts()
        p.rt.require(all(state[k] == owner[k] for k in ("lineage", "serial")), "actual_state_identity")
        schema_run = subprocess.run([p.rt.TF, "-chdir=" + str(p.ROOT), "providers", "schema", "-json"],
                                    env=v.environment(), capture_output=True, encoding="utf-8", timeout=120)
        p.rt.require(schema_run.returncode == 0, "actual_provider_schema")
        attrs = json.loads(schema_run.stdout)["provider_schemas"]["registry.terraform.io/azure/azapi"]["resource_schemas"]["azapi_update_resource"]["block"]["attributes"]
        v.save("identity-schema.json", {k: attrs[k] for k in DERIVED})
        target = json.loads(v.tf("show", "-json", str(PACKAGE / "take-offline.tfplan")))
        full = json.loads(v.tf("show", "-json", str(PACKAGE / "full-NEVER-APPLY.tfplan")))
        inputs = load("inputs.tfvars.json")
        p.rt.require(target["configuration"] == full["configuration"] and target["variables"] == full["variables"]
                     and all(target["variables"][k]["value"] == value for k, value in inputs.items()), "exact_companion_inputs")
        selection = v.load("result.json")["reservation"]
        scope = guard(target, selection, attrs)
        p.rt.require(next(r for r in target["resource_changes"] if r["address"] == c.ADDRESS)["change"]
                     == next(r for r in full["resource_changes"] if r["address"] == c.ADDRESS)["change"], "exact_companion_patch")
        p.rt.require(full.get("checks") and all(x["status"] == "pass" for x in full["checks"])
                     and not full.get("errored") and not full.get("deferred_changes"), "full_checks_resolved")
        for path in (PACKAGE / "take-offline.tfplan", PACKAGE / "full-NEVER-APPLY.tfplan"):
            p.rt.require(v.archive(path) == {k: owner[k] for k in ("lineage", "serial")}, "embedded_state_config_exact")
        p.rt.require(not any("{{ .Env." in f.read_text(encoding="utf-8") for f in p.ROOT.glob("*.tf*")), "no_go_templates")
        v.save("preflight.json", {"at_utc": p.now(), "passed": True, "scope": scope, "commands": v.COMMANDS,
               "terraform_validation": validation, "state": owner, "saved_plan_sha256": TARGET_SHA,
               "companion_never_apply": True, "plans_created": 0})
        v.workflow("RunValidation")
        stage = "offline_tests"
        tests = ["tests/unit/test_auto_revision_" + name + ".py" for name in
                 ("prepare", "validate", "execute", "offline_correct", "offline_reconcile")]
        tests.append("tests/unit/test_auto_live_gate.py")
        result = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "-q", *tests,
                                 "--junitxml=" + str(OUT / "tests.xml")], cwd=p.rt.ROOT, env=p.rt.ENV,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=300)
        with (OUT / "tests.private.log").open("x", encoding="utf-8") as handle:
            handle.write(result.stdout + result.stderr)
        p.rt.require(result.returncode == 0, "actual_tests_failed")
        counts = {k: sum(int(n.get(k, 0)) for n in ET.parse(OUT / "tests.xml").getroot().iter("testsuite"))
                  for k in ("tests", "failures", "errors", "skipped")}
        p.rt.require(counts["tests"] > 0 and not any(counts[k] for k in ("failures", "errors", "skipped")), "clean_tests")
        v.save("tests.json", {"counts": counts, "no_application_build_required": True, "no_images": True})
        v.workflow("BuildVerification")
        stage = "actual_roles_policy"
        v.policy_and_roles()
        v.workflow("StaticRoleVerification")
        stage = "final_readback"
        fresh("final")
        p.rt.require(all(p.sha(PACKAGE / name) == digest for name, digest in retained.items())
                     and all(p.sha(p.rt.ROOT / name) == digest for name, digest in tooling.items()), "retained_or_tooling_changed")
        v.save("validation.json", {"at_utc": p.now(), "read_checks_passed": True, "saved_plan_sha256": TARGET_SHA,
               "companion_sha256": FULL_SHA, "all13_protected_equal": True,
               "protected_baseline_sha256": p.release.fs.sha(before), "supplemental_equal": True,
               "tests": counts, "actual_official_workflow_through": "StaticRoleVerification",
               "independent_agent_review": False, "parent_native_review_required": True,
               "api_patch_contract_requires_review": True, "section7_ready_to_record": True,
               "status": "READ_CHECKS_PASS_NOT_Validated_NO_APPLY",
               "original_create_never_replay": True, "flat_offline_postapply_proof_required": True,
               "cloud_configuration_writes": 0, "plans_created": 0, "applies": 0,
               "scoring_requests": 0, "completion_requests": 0,
               "evidence": {f.name: p.sha(f) for f in OUT.iterdir() if f.is_file()}})
        print((OUT / "validation.json").read_text(encoding="utf-8"), flush=True)
        return 0
    except Exception as exc:
        failure = {"at_utc": p.now(), "stage": stage, "type": type(exc).__name__,
                   "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed",
                   "http_status": getattr(exc, "code", None), "retry_authorized": False, "applies": 0}
        v.save("failure.json", failure)
        print(json.dumps(failure), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())