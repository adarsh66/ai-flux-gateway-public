"""Validate the retained offline revision only. No plan, build or apply path.

Native agent review is retained separately; this deterministic process does not
pretend to be another agent. All outputs are exclusive and ACL protected.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import fnmatch
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
from urllib.request import Request, urlopen
import zipfile
import xml.etree.ElementTree as ET

from scripts.deployment import auto_revision_prepare as p
from scripts.deployment.auto_identity_readback import collection
from scripts.deployment.inventory_persistence_apply_once import supplemental

HOME = p.rt.HOME / "auto-offline-revision-20261029T060302997824Z"
OUT = HOME / "validation01"
PLAN_SHA = "6675631640d48342ad5a55d38613e56c3393aaed67ae4889e98cdfbb1f400998"
REVIEW = Path("C:/Users/p4032099/AppData/Roaming/Code/User/workspaceStorage/c0077ec5e47287d6bf3fec331f95ec27/GitHub.copilot-chat/chat-session-resources/1fb13269-8028-40f5-82a2-14e156d03d63/call_u4mDvBfxDGjmpvBp7dS9Bp1B__vscode-1793145660724/content.txt")
COMMANDS = []


def load(name):
    return json.loads((HOME / name).read_bytes())


def save(name, value):
    p.backend.save(OUT, name, value)


def environment():
    env = {k: v for k, v in p.rt.ENV.items()
           if not k.startswith(("TF_CLI_ARGS", "TF_VAR_", "TF_LOG"))
           and k not in {"TF_WORKSPACE", "TF_DATA_DIR"}}
    env.update(TF_WORKSPACE="default", TF_INPUT="0", TF_IN_AUTOMATION="1", PYTHONUTF8="1")
    return env


def tf(*args):
    p.rt.require(args[0] in {"version", "init", "fmt", "validate", "workspace", "state", "show"}, "readonly_tf_only")
    p.rt.require(args[0] != "state" or args[1:] in (("list",), ("pull",)), "no_state_mutation")
    started = p.now()
    result = subprocess.run([p.rt.TF, "-chdir=" + str(p.ROOT), *args], cwd=p.rt.ROOT,
                            env=environment(), capture_output=True, encoding="utf-8", errors="replace", timeout=900)
    COMMANDS.append({"command": ["terraform", *args], "started_at_utc": started,
                     "finished_at_utc": p.now(), "exit_code": result.returncode})
    if args[0] not in {"state", "show"} or result.returncode:
        with (OUT / ("terraform-" + str(len(COMMANDS)) + ".private.log")).open("x", encoding="utf-8") as f:
            f.write(result.stdout + result.stderr)
    p.rt.require(result.returncode == 0, "terraform_failed:" + args[0])
    return result.stdout


def workflow(step):
    args = ["C:/Program Files/Git/bin/bash.exe", "C:/Users/p4032099/.agents/skills/azure-validate/references/scripts/workflow.sh",
            "--workspace-path", str(p.rt.ROOT)]
    if step != "None":
        args += ["--completed-step", step]
    result = subprocess.run(args, cwd=p.rt.ROOT, env=environment(), capture_output=True, encoding="utf-8", timeout=90)
    save("workflow-" + step + ".json", {"at_utc": p.now(), "completed_step": step,
         "exit_code": result.returncode, "output": result.stdout, "stderr": result.stderr})
    p.rt.require(result.returncode == 0, "workflow_failed:" + step)
    print(result.stdout, flush=True)


def bindings():
    result = load("result.json")
    p.rt.require(p.sha(HOME / "offline-revision.tfplan") == result["saved_plan_sha256"] == PLAN_SHA, "exact_target_bytes")
    p.rt.require(p.sha(HOME / "full-NEVER-APPLY.tfplan") == result["companion_sha256"], "exact_companion_bytes")
    p.rt.require(p.sources() == load("sources.json") and p.release.fs.sha(p.sources()) == result["source_sha256"], "source_freshness_drift_STOP")
    owner = load("state-owner.json")
    p.rt.require(p.sha(p.ROOT / "terraform.tfstate") == owner["sha256"], "state_bytes_drift_STOP")
    p.rt.require(not (p.ROOT / ".terraform.tfstate.lock.info").exists(), "state_lock_present")
    markers = p.backend.markers()
    old = load("historical-markers-before.json")
    prefix = HOME.relative_to(p.rt.ROOT).as_posix() + "/"
    p.rt.require(all(markers.get(k) == v for k, v in old.items())
                 and all(k.startswith(prefix) for k in markers.keys() - old.keys()), "foreign_intent_or_historical_drift")
    p.rt.require(not list(HOME.rglob("*apply-intent*")), "apply_attempt_exists_reconcile_only")
    p.require_no_competing_workers(p.backend.workers())
    return result


def fresh(name):
    bindings()
    baseline = p.release.snapshot()
    save(name + "-baseline.json", baseline)
    p.rt.require(len(baseline) == 13 and baseline == load("protected-before.json"), "all13_current_baseline_drift_STOP")
    supplement = supplemental(baseline)
    save(name + "-supplemental.json", supplement)
    p.rt.require(supplement == load("supplemental-before.json"), "supplemental_drift_STOP")
    rows = [p.summarize_revision(r) for r in collection("https://management.azure.com" + p.APIM
            + "/apis/" + p.API + "/revisions?api-version=" + p.VERSION)]
    save(name + "-revisions.json", rows)
    p.require_absent_revision(rows, load("result.json")["revision"])
    p.rt.require(rows == load("revisions-before.json"), "revision_list_changed_STOP")
    current = p.release.ProductRun().arm("/apis/" + p.API)["properties"]
    p.rt.require({k: current.get(k) for k in load("current-api-metadata.json")} == load("current-api-metadata.json"), "current_api_changed_STOP")
    head = p.backend.blob_head()
    save(name + "-remote-head.json", head)
    prior = load("remote-runtime-state-head.json")
    p.rt.require(all(head[k] == prior[k] for k in ("etag", "content_length", "last_modified", "lease_status", "lease_state")), "remote_runtime_state_changed_STOP")
    return baseline


def archive(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        p.rt.require(len(names) == len(set(names)), "unique_archive_members")
        files = {n.removeprefix("tfconfig/m-/"): z.read(n) for n in names if n.startswith("tfconfig/m-/")}
        expected = {f.name: f.read_bytes() for f in p.ROOT.iterdir() if f.is_file() and f.name.endswith((".tf", ".tf.json"))}
        p.rt.require(files == expected, "embedded_config_current_exact")
        p.rt.require(z.read(".terraform.lock.hcl") == (p.ROOT / ".terraform.lock.hcl").read_bytes().replace(b"\r\n", b"\n"), "embedded_lock_content")
        state = json.loads(z.read("tfstate"))
        return {k: state[k] for k in ("lineage", "serial")}


def policy_and_roles():
    token = p.rt.cli(["account", "get-access-token", "--subscription", p.rt.SUB, "--resource", "https://management.azure.com/"])["accessToken"]
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    p.rt.require(claims.get("oid") == p.rt.OPERATOR and claims.get("tid") == p.rt.TENANT, "operator_token_identity")
    tls = ssl.create_default_context(cafile=p.rt.CA)
    def get(rid, version):
        p.rt.require(rid.startswith(("/providers/Microsoft.Authorization/", "/subscriptions/" + p.rt.SUB)), "exact_arm_scope")
        with urlopen(Request("https://management.azure.com" + rid + "?api-version=" + version,
                     headers={"Authorization": "Bearer " + token}), context=tls, timeout=90) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            p.rt.require(len(raw) <= 8 * 1024 * 1024, "bounded_arm_response")
            return json.loads(raw)
    assignment_rows = collection("https://management.azure.com" + p.APIM + "/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01&$filter=atScope()")
    grants = []
    for a in assignment_rows:
        v = a["properties"]
        if v["principalId"] == p.rt.OPERATOR and not v.get("condition"):
            grants.extend(get(v["roleDefinitionId"], "2022-04-01")["properties"]["permissions"])
    actions = ["Microsoft.ApiManagement/service/apis/read", "Microsoft.ApiManagement/service/apis/write"]
    coverage = {a: any(any(fnmatch.fnmatchcase(a.lower(), pat.lower()) for pat in g.get("actions", []))
                and not any(fnmatch.fnmatchcase(a.lower(), pat.lower()) for pat in g.get("notActions", [])) for g in grants) for a in actions}
    p.rt.require(all(coverage.values()), "existing_operator_revision_coverage")
    denies = collection("https://management.azure.com" + p.APIM + "/providers/Microsoft.Authorization/denyAssignments?api-version=2022-04-01&$filter=atScope()")
    p.rt.require(not denies, "deny_assignment_requires_review")
    assignments = collection("https://management.azure.com/subscriptions/" + p.rt.SUB
                             + "/providers/Microsoft.Authorization/policyAssignments?api-version=2024-04-01")
    definitions = {}
    ids = {a["properties"]["policyDefinitionId"] for a in assignments}
    with ThreadPoolExecutor(max_workers=8) as pool:
        definitions.update(zip(sorted(ids), pool.map(lambda rid: get(rid, "2023-04-01"), sorted(ids))))
    children = {c["policyDefinitionId"] for d in definitions.values() for c in d["properties"].get("policyDefinitions", [])}
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = sorted(children - definitions.keys())
        definitions.update(zip(ids, pool.map(lambda rid: get(rid, "2023-04-01"), ids)))
    def expression(v, params):
        m = re.fullmatch(r"\[parameters\('([^']+)'\)\]", v) if isinstance(v, str) else None
        if m:
            p.rt.require(m[1] in params, "resolved_policy_parameter")
            return params[m[1]]
        p.rt.require(not isinstance(v, str) or not v.startswith("["), "unsupported_policy_expression")
        return v
    effects = []
    for a in assignments:
        ap = a["properties"]
        rid = ap["policyDefinitionId"]
        parent = definitions[rid]["properties"]
        params = {k: v.get("defaultValue") for k, v in parent.get("parameters", {}).items()}
        params.update({k: v["value"] for k, v in ap.get("parameters", {}).items()})
        for child in parent.get("policyDefinitions", [{"policyDefinitionId": rid, "parameters": {}}]):
            d = definitions[child["policyDefinitionId"]]["properties"]
            values = {k: v.get("defaultValue") for k, v in d.get("parameters", {}).items()}
            values.update({k: expression(v["value"], params) for k, v in child.get("parameters", {}).items()})
            if "policyDefinitions" not in parent:
                values = params
            effect = expression(d["policyRule"]["then"]["effect"], values)
            blocking = ap.get("enforcementMode", "Default") != "DoNotEnforce" and effect.lower() in {"deny", "denyaction", "modify", "deployifnotexists"}
            if blocking:
                p.rt.require(child["policyDefinitionId"].rsplit("/", 1)[-1] in {"54f51f64-eaa5-44cf-8674-830bcfd14d21", "f69cd8b8-9a6e-46b4-be84-244e8b127944"}, "unreviewed_blocking_policy")
                # Bind to previously fully inspected literal MFA definitions,
                # then evaluate current claims. Never save the token/claims.
                retained = p.rt.HOME / "inventory-persistence-20261029-urgent01/independent-validation01"
                old = json.loads((retained / ("actual-policy-" + child["policyDefinitionId"].rsplit("/", 1)[-1] + ".json")).read_bytes())
                p.rt.require(d == old["definition"]["properties"], "mfa_definition_changed_requires_review")
                p.rt.require("p1" in claims.get("acrs", []), "current_mfa_p1_required")
            effects.append({"assignment": a["id"], "definition": child["policyDefinitionId"], "effect": effect, "blocking_effect": blocking})
    texts = {f.name: f.read_text(encoding="utf-8") for f in p.ROOT.glob("*.tf")}
    p.rt.require(not any(re.search(r'^\s*resource\s+"(?:azurerm_role_assignment|azurerm_role_definition|azurerm_user_assigned_identity)"', t, re.M) for t in texts.values()), "no_role_or_identity_resources")
    proof = {"at_utc": p.now(), "passed": True, "coverage": coverage, "deny_count": len(denies),
             "assignment_count": len(assignments), "definition_count": len(definitions), "effects": effects,
             "definition_hashes": {k: p.release.fs.sha(v) for k, v in definitions.items()},
             "operator_matches": True, "tenant_matches": True, "current_p1": "p1" in claims.get("acrs", []),
             "static_role_or_identity_writes": 0, "runtime_inference_permission_proven": False,
             "policy_acceptance_is_static_not_write_probe": True}
    save("roles-policy.json", proof)
    return proof


def main():
    p.rt.require(sys.argv[1:] == ["validate-once"] and not OUT.exists(), "exclusive_validation_no_replay")
    p.release.fs.protect(OUT)
    stage = "retained_independent_review"
    try:
        review = REVIEW.read_text(encoding="utf-8")
        p.rt.require("CONDITIONAL PASS" in review and PLAN_SHA in review, "exact_native_review_binding")
        save("native-review.json", {"source": str(REVIEW), "sha256": p.sha(REVIEW), "text": review,
             "accepted_as_independent_agent_review": True, "new_agent_invocation_claimed": False,
             "corrections": ["prevent_destroy does not block state rm or removal of resource configuration",
                             "offline creation remains unproven until actual postapply GET"],
             "conditional_only_requires_actual_validation": True})
        bindings()
        p.persistence.transport()
        account = p.rt.cli(["account", "show"])
        p.rt.require(account["id"] == p.rt.SUB and account["tenantId"] == p.rt.TENANT, "account_context")
        save("account.json", {"subscription": account["id"], "tenant": account["tenantId"]})
        stage = "fresh_before"
        fresh("before")
        for step in ("None", "LoadPlan", "AddValidationSteps"):
            workflow(step)
        stage = "actual_recipe_preflight"
        tf("version", "-json")
        tf("init", "-input=false", "-lockfile=readonly", "-no-color")
        tf("fmt", "-check")
        validation = json.loads(tf("validate", "-json"))
        p.rt.require(validation["valid"] and not validation["error_count"], "actual_tf_validate")
        p.rt.require(tf("workspace", "show").strip() == "default", "default_workspace")
        addresses = tf("state", "list").splitlines()
        p.rt.require(p.ADDRESS not in addresses and p.POLICY in addresses, "state_owner_exact")
        owner = load("state-owner.json")
        state = json.loads(tf("state", "pull"))
        p.rt.require(all(state[k] == owner[k] for k in ("lineage", "serial")), "current_state_identity")
        target = json.loads(tf("show", "-json", str(HOME / "offline-revision.tfplan")))
        full = json.loads(tf("show", "-json", str(HOME / "full-NEVER-APPLY.tfplan")))
        for path in (HOME / "offline-revision.tfplan", HOME / "full-NEVER-APPLY.tfplan"):
            embedded = archive(path)
            p.rt.require(all(embedded[k] == owner[k] for k in ("lineage", "serial")), "embedded_state_identity")
        scope = p.guard_target(target, full, load("inputs.tfvars.json"))
        p.guard_companion(full, p.release.ProductRun().policy())
        p.rt.require(not any("{{ .Env." in f.read_text(encoding="utf-8") for f in p.ROOT.glob("*.tf*")), "no_unresolved_go_templates")
        save("preflight.json", {"at_utc": p.now(), "passed": True, "commands": COMMANDS, "scope": scope,
             "terraform_validation": validation, "state": owner, "saved_plan_sha256": PLAN_SHA,
             "adaptation": "Inspect exact retained plans; never run stock replan or build"})
        workflow("RunValidation")
        stage = "offline_tests"
        command = [sys.executable, "-X", "utf8", "-m", "pytest", "-q", "tests/unit/test_auto_revision_prepare.py",
                   "tests/unit/test_auto_live_gate.py", "--junitxml=" + str(OUT / "tests.xml")]
        test = subprocess.run(command, cwd=p.rt.ROOT, env=p.rt.ENV, capture_output=True, encoding="utf-8", errors="replace", timeout=300)
        with (OUT / "tests.private.log").open("x", encoding="utf-8") as f:
            f.write(test.stdout + test.stderr)
        p.rt.require(test.returncode == 0, "offline_guard_tests_failed")
        suites = list(ET.parse(OUT / "tests.xml").getroot().iter("testsuite"))
        counts = {k: sum(int(n.get(k, 0)) for n in suites) for k in ("tests", "errors", "failures", "skipped")}
        p.rt.require(counts["tests"] >= 45 and not any(counts[k] for k in ("errors", "failures", "skipped")), "actual_clean_tests")
        save("tests.json", {"at_utc": p.now(), "passed": True, "counts": counts, "no_application_build_required": True,
             "cm36_not_replayed": True, "reason": "API revision copy only; no application or UI deployment"})
        workflow("BuildVerification")
        stage = "actual_roles_policy"
        policy_and_roles()
        workflow("StaticRoleVerification")
        stage = "final_freshness"
        fresh("final")
        save("validation.json", {"at_utc": p.now(), "checks_passed": True, "pid": os.getpid(),
             "saved_plan_sha256": PLAN_SHA, "source_sha256": load("result.json")["source_sha256"],
             "protected_baseline_sha256": load("result.json")["protected_baseline_sha256"],
             "independent_native_review_retained": True, "deterministic_validator_not_agent": True,
             "tests": counts, "companion_never_apply": True, "actual_official_workflow_through": "StaticRoleVerification",
             "section7_parent_recording_required": True, "applies": 0, "scoring_requests": 0, "completion_requests": 0,
             "evidence": {f.name: p.sha(f) for f in OUT.iterdir() if f.is_file()}})
        print(json.dumps({"status": "actual_validation_passed_section7_recording_next", "evidence": str(OUT), "tests": counts}), flush=True)
        return 0
    except Exception as exc:
        failure = {"at_utc": p.now(), "stage": stage, "type": type(exc).__name__,
                   "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed", "applies": 0,
                   "http_status": getattr(exc, "code", None), "retry_authorized": False}
        save("failure.json", failure)
        print(json.dumps(failure), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())