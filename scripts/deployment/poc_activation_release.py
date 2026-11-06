"""Two separately reviewed stages, saved-plan-only exclusive apply, no role writes."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import sys

from scripts.deployment import runtime_rollout as rt, portal_fix as portals
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import poc_activation_prepare as prep
from scripts.deployment.poc_controls_guards import guard_policy, guard_protected, require_publisher
from scripts.deployment.poc_controls_preflight import collect
from scripts.deployment.project_route_product_access import ProductRun, sha, any_unknown
from scripts.deployment.poc_fragment_bootstrap import ID, FRAGMENT, DEFAULTS, without_created_fragment
from scripts.deployment.poc_fragment_readback import compare
from scripts.deployment.customer_catalog_companion import normalized
from scripts.deployment.project_route_demo import policy_structure

HOME = prep.HOME
POLICY = "azapi_resource.project_policy[0]"
RUNTIME = {f'azurerm_linux_web_app.main["{k}"]': k for k in ("api", "admin")}
FLAGS = {"AIFLUX_GATEWAY_CONTROLS_POC_ENABLED": "true", "AIFLUX_GATEWAY_CONTROLS_V2_ENABLED": "false",
         "AIFLUX_GATEWAY_SETTINGS_SCOPES": '["dev-unified"]'}
MODELS = {"gpt-5.6-luna", "gpt-6.1-sol", "gpt-5.4-mini", "gpt-4o", "DeepSeek-V4-Flash", "DeepSeek-V4-Pro",
          "Kimi-K2.7-Code", "grok-4.3", "grok-4-20-reasoning", "grok-4-1-fast-reasoning", "FW-GLM-5.3", "FW-MiniMax-M3", "glm-5.3"}
PINS = {"api": "dd8b048b8a189061d870ca9011c3d8e0152ff63712ee6d61fe3f2a37af3b0a33",
        "admin": "8950baf1fa8c5e8b0762c3b1069251706fe043dbca9c060b31c77092ba9f6ca0",
        "customer": "d9d8b4b21283801feb2aff3ad12707155f5c38c59b6fc09091a4c22c35e71ea3",
        "ingestion": "fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90"}


def location(stage):
    rt.require(stage in ("runtime", "policy"), "stage_required")
    # Original runtime preparation stopped before plan-intent (invalid portal
    # scope); retain it untouched and use a fresh, exclusive successor.
    folder = HOME / ("runtime-successor01" if stage == "runtime" else stage)
    root = folder / "infra/terraform" if stage == "runtime" else rt.ROOT / "infra/project-route"
    return folder, root, folder / (stage + ".tfplan")


def exclusive(folder, name, value):
    with (folder / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)


def tooling():
    paths = {Path(__file__), rt.ROOT / "scripts/deployment/poc_activation_validation.py",
             rt.ROOT / "scripts/deployment/poc_activation_prepare.py",
             rt.ROOT / "tests/unit/test_poc_activation_release.py"}
    paths |= set((rt.ROOT / "scripts/deployment").glob("poc_controls*.py"))
    for folder in ("infra/terraform", "infra/project-route"):
        paths |= set((rt.ROOT / folder).glob("*.tf")) | set((rt.ROOT / folder).glob("*.tf.json"))
        paths.add(rt.ROOT / folder / ".terraform.lock.hcl")
    paths |= {rt.HOME / "rebuild-platform.tfvars.json", rt.HOME / "jwt-runtime.tfvars.json",
              rt.ROOT / "infra/terraform/backend.hcl"}
    return {p.relative_to(rt.ROOT).as_posix(): sha(p.read_bytes()) for p in paths}


def snapshot():
    run = ProductRun()
    result = run.protected()
    fragments = run.arm("/policyFragments")
    rt.require(not fragments.get("nextLink"), "fragment_pagination")
    result["apim"]["fragments"] = fs.sha(without_created_fragment(fragments))
    result["active_policy_sha256"] = sha(run.policy())
    raw = run.arm("/policyFragments/" + FRAGMENT + "?format=rawxml")
    exported = run.arm("/policyFragments/" + FRAGMENT + "?format=xml")
    rt.require(raw["id"].lower() == exported["id"].lower() == ID.lower(), "fragment_identity")
    result["fragment_xml_sha256"] = sha(raw["properties"]["value"])
    result["fragment_properties_sha256"] = fs.sha({k: v for k, v in raw["properties"].items() if k != "value"})
    result["gateway_identity"] = run.arm("").get("identity")
    account = rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
    deployments = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + account + "/deployments?api-version=2025-06-01"])
    rt.require(not deployments.get("nextLink"), "model_pagination")
    result["model_metadata_sha256"] = fs.sha(deployments)
    result["product_subscriptions"] = run.metadata()
    return result


def built(remote=True):
    prep.check_sources()
    rt.require(prep.load(HOME / "native.json")["passed"], "native_required")
    data = prep.load(HOME / "build.json")
    rt.require(set(data) == {"api", "admin"}, "exact_required_images")
    for kind, item in data.items():
        rt.require(re.fullmatch(re.escape(portals.HOST + "/aiflux-" + kind + "@sha256:") + "[a-f0-9]{64}", item["image"]), "immutable_pin")
        if remote:
            run = rt.cli(["acr", "task", "show-run", "-r", portals.REGISTRY, "--run-id", item["run_id"], "--subscription", rt.SUB])
            meta = rt.cli(["acr", "repository", "show", "-n", portals.REGISTRY, "--image", "aiflux-" + kind + ":" + item["tag"], "--subscription", rt.SUB])
            rt.require(run["status"] == "Succeeded" and run["finishTime"] == item["finished_at"] and meta["digest"] == item["digest"], "remote_image_binding")
    return {k: v["image"] for k, v in data.items()}


def guard_runtime(plan, images):
    rt.require(set(images) == {"api", "admin"} and plan.get("applyable") is True and not plan.get("errored")
               and not plan.get("deferred_changes"), "resolved_runtime_plan")
    seen = set()
    for item in plan.get("resource_changes", []):
        c = item["change"]
        if c["actions"] in (["no-op"], ["read"]):
            rt.require(c["actions"] == ["no-op"] or item.get("mode") == "data", "managed_read")
            continue
        address = item["address"]
        rt.require(address in RUNTIME and address not in seen and item.get("mode") == "managed" and c["actions"] == ["update"], "exact_runtime_targets")
        seen.add(address)
        before, after = deepcopy(c["before"]), deepcopy(c["after"])
        unknown = c.get("after_unknown") or {}
        rt.require(not any(any_unknown(v) for k, v in unknown.items() if k not in fs.COMPUTED), "runtime_unknown_writable")
        for key in fs.COMPUTED:
            if any_unknown(unknown.get(key)):
                after[key] = before.get(key)
        kind = RUNTIME[address]
        rt.require(re.fullmatch(re.escape(portals.HOST + "/aiflux-" + kind + "@sha256:") + "[a-f0-9]{64}", images[kind]), "immutable_image")
        rt.require(len(before["site_config"]) == len(after["site_config"]) == 1, "site_shape")
        old, new = before["site_config"][0]["application_stack"], after["site_config"][0]["application_stack"]
        rt.require(len(old) == len(new) == 1 and old[0]["docker_image_name"] == "aiflux-" + kind + "@sha256:" + PINS[kind]
                   and new[0]["docker_image_name"] == images[kind].split("/", 1)[1]
                   and new[0]["docker_registry_url"] == "https://" + portals.HOST, "exact_image_predecessor_target")
        new[0]["docker_image_name"] = old[0]["docker_image_name"]
        if kind == "api":
            rt.require(after["app_settings"] == {**before["app_settings"], **FLAGS}, "exact_three_flags_only")
            after["app_settings"] = before["app_settings"]
        rt.require(after == before and c["before"] != c["after"], "runtime_unapproved_delta")
    rt.require(seen == set(RUNTIME), "two_runtime_updates_required")


def guard_activation_policy(plan, previous, inputs):
    rt.require(plan.get("applyable") is True and not plan.get("errored") and not plan.get("deferred_changes"), "resolved_policy_plan")
    variables = {k: v["value"] for k, v in plan["variables"].items()}
    rt.require(all(variables.get(k) == v for k, v in inputs.items()) and variables["poc_controls_enabled"] is True
               and variables["poc_publisher_permissions_verified"] is True and variables["poc_settings_bootstrap_enabled"] is True,
               "exact_approved_activation_inputs")
    writes = [c for c in plan["resource_changes"] if c["change"]["actions"] not in (["no-op"], ["read"])]
    rt.require(len(writes) == 1 and writes[0]["address"] == POLICY and writes[0]["change"]["actions"] == ["update"], "one_existing_policy_update_only")
    c = writes[0]["change"]
    before, after = deepcopy(c["before"]), deepcopy(c["after"])
    rt.require(not any(any_unknown(v) for k, v in c.get("after_unknown", {}).items() if k == "body" or k not in ("output",)), "policy_unknown_writable")
    rt.require(policy_structure(before["body"]["properties"]["value"]) == policy_structure(previous), "fresh_policy_predecessor")
    desired = after["body"]["properties"]["value"]
    guard_policy(previous, desired)
    tree = __import__("xml.etree.ElementTree", fromlist=["ElementTree"]).fromstring(desired)
    catalogs = [json.loads(n.text) for n in tree.findall(".//set-body") if (n.text or "").startswith('{"data":')]
    rt.require(len(catalogs) == 1 and {m["id"] for m in catalogs[0]["data"]} == MODELS, "exact_thirteen_model_membership")
    after["body"] = before["body"]
    after["output"] = before.get("output")
    rt.require(after == before, "nonpolicy_attribute_delta")
    fragment = [c for c in plan["resource_changes"] if c["address"] == "azapi_resource.poc_settings[0]"]
    rt.require(len(fragment) == 1 and fragment[0]["change"]["actions"] == ["no-op"], "existing_fragment_must_be_noop")
    return desired


def parsed(root, path):
    return json.loads(fs.terraform(root, "show", "-json", str(path)))


def runtime_variables(images, current):
    rt.require(set(images) == {"api", "admin"}, "exact_runtime_variable_images")
    # Portal helper deliberately only accepts portal kinds. Seed admin while
    # preserving ALL current pins, then set the separately authorized API pin.
    variables = portals.runtime_variables({"portals": ["admin"], "results": {
        "admin": {"image": images["admin"]}}}, current)
    variables["apps"]["api"]["image"] = images["api"].split("/", 1)[1]
    return variables


def resolve(target, full, addresses):
    rt.require(normalized(target.get("configuration")) == normalized(full.get("configuration"))
               and target.get("variables") == full.get("variables") and not full.get("errored")
               and not full.get("deferred_changes"), "identical_full_companion_inputs")
    rt.require(full.get("checks") and all(c["status"] == "pass" for c in full["checks"]), "full_checks_required")
    lookup = {c["address"]: c["change"] for c in full["resource_changes"]}
    for item in target["resource_changes"]:
        if item["address"] in addresses:
            rt.require(item["change"] == lookup.get(item["address"]), "companion_exact_target_binding")
    checks = {json.dumps(c["address"], sort_keys=True): c for c in full["checks"]}
    result = deepcopy(target)
    result["checks"] = []
    for c in target.get("checks", []):
        key = json.dumps(c["address"], sort_keys=True)
        rt.require(c["status"] in ("pass", "unknown") and key in checks, "target_check_failed_or_missing")
        result["checks"].append(checks[key])
    return result


def plan(stage):
    folder, root, target = location(stage)
    rt.require(not folder.exists(), "existing_stage_reconcile_never_replay")
    images = built()
    permissions = collect()
    require_publisher(permissions)
    before = snapshot()
    if stage == "runtime":
        for kind, pin in PINS.items():
            rt.require(before["runtime"]["sites"][kind]["image"] == "DOCKER|" + portals.HOST + "/aiflux-" + kind + "@sha256:" + pin, "current_predecessor:" + kind)
        raw = ProductRun().arm("/policyFragments/" + FRAGMENT + "?format=rawxml")["properties"]["value"]
        exported = ProductRun().arm("/policyFragments/" + FRAGMENT + "?format=xml")["properties"]["value"]
        rt.require(compare(DEFAULTS.read_text(), raw, exported)["semantic_equal"], "safe_default_fragment_required")
    else:
        rt.require(prep.load(location("runtime")[0] / "verified.json")["passed"] and (HOME / "initialization.json").exists(), "published_schema3_before_policy_required")
    fs.protect(folder)
    exclusive(folder, "baseline.json", before)
    settings = fs.current_settings()
    exclusive(folder, "settings-hashes.json", {k: fs.sha(v) for k, v in settings.items()})
    if stage == "runtime":
        root.mkdir(parents=True, exist_ok=False)
        for p in (rt.ROOT / "infra/terraform").iterdir():
            if p.is_file() and (p.name.endswith((".tf", ".tf.json")) or p.name == ".terraform.lock.hcl"):
                shutil.copyfile(p, root / p.name)
        for path in ("infra/models", "gateway/catalog", "gateway/policies"):
            shutil.copytree(rt.ROOT / path, folder / path, ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tfplan", "__pycache__"))
        for p in (rt.ROOT / "gateway").glob("*.json"):
            shutil.copyfile(p, folder / "gateway" / p.name)
        variables = runtime_variables(images, before["runtime"])
        variables.update(ingestion_container_image=before["runtime"]["sites"]["ingestion"]["image"].removeprefix("DOCKER|"),
            ingestion_enabled=True, ingestion_timer_enabled=True, ingestion_start_at=before["cutoff"], ingestion_catalog_accepted=True)
        rt.save(folder / "inputs.tfvars.json", variables)
        settings["api"].update(FLAGS)
        rt.save(root / "poc_preserved.tf.json", {"locals": {"poc_release_settings": fs.literal(fs.preserved_web_settings(settings))}})
        rt.save(root / "zzzz_poc_override.tf.json", {"resource": {"azurerm_linux_web_app": {"main": {"app_settings": "${local.poc_release_settings[each.key]}"}}}})
        varargs = ["-var-file=" + str(p) for p in (rt.HOME / "rebuild-platform.tfvars.json", folder / "inputs.tfvars.json", rt.HOME / "jwt-runtime.tfvars.json")]
        fs.terraform(root, "init", "-input=false", "-lockfile=readonly", "-no-color", "-backend-config=" + str(rt.ROOT / "infra/terraform/backend.hcl"))
        targets = ["-target=" + a for a in RUNTIME]
    else:
        variables = prep.load(rt.HOME / "poc-fragment-bootstrap-20261028/inputs.tfvars.json")
        variables.update(poc_controls_enabled=True, poc_publisher_permissions_verified=True, poc_settings_bootstrap_enabled=True)
        rt.save(folder / "inputs.tfvars.json", variables)
        varargs = ["-var-file=" + str(folder / "inputs.tfvars.json")]
        fs.terraform(root, "init", "-input=false", "-lockfile=readonly", "-no-color")
        targets = []
        (folder / "predecessor-policy.xml").write_bytes(ProductRun().policy().encode())
    rt.require(fs.terraform(root, "workspace", "show").strip() == "default", "default_workspace")
    fs.terraform(root, "validate", "-no-color")
    exclusive(folder, "plan-intent.json", {"at": fs.stamp(), "targets": targets, "max_applies": 1})
    fs.terraform(root, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *varargs, *targets, "-out=" + str(target))
    data = parsed(root, target)
    if stage == "runtime" and any(c["status"] != "pass" for c in data.get("checks", [])):
        full = folder / "validation-only-NEVER-APPLY.tfplan"
        exclusive(folder, "companion-intent.json", {"at": fs.stamp(), "target_sha256": sha(target.read_bytes()), "never_apply": True})
        fs.terraform(root, "plan", "-input=false", "-no-color", "-lock-timeout=60s", *varargs, "-out=" + str(full))
        data = resolve(data, parsed(root, full), set(RUNTIME))
    rt.require(all(c["status"] == "pass" for c in data.get("checks", [])), "every_plan_check_pass")
    if stage == "runtime":
        guard_runtime(data, images)
    else:
        desired = guard_activation_policy(data, (folder / "predecessor-policy.xml").read_bytes().decode(), variables)
        (folder / "desired-policy.xml").write_bytes(desired.encode())
    artifacts = [folder / "inputs.tfvars.json", target, *root.glob("*.tf"), *root.glob("*.tf.json"), root / ".terraform.lock.hcl"]
    if (folder / "validation-only-NEVER-APPLY.tfplan").exists():
        artifacts.append(folder / "validation-only-NEVER-APPLY.tfplan")
    review = {"at": fs.stamp(), "stage": stage, "plan_sha256": sha(target.read_bytes()), "images": images,
              "tooling": tooling(), "source_sha256": prep.manifest()["source_sha256"], "baseline": before,
              "artifacts": {str(p): sha(p.read_bytes()) for p in artifacts}, "permission_proof": permissions["at_utc"]}
    exclusive(folder, "review.json", review)
    print(json.dumps({"stage": stage, "plan_sha256": review["plan_sha256"], "images": images, "guard_passed": True}), flush=True)


def check(stage, live=True):
    folder, root, target = location(stage)
    review = prep.load(folder / "review.json")
    rt.require(review["tooling"] == tooling() and review["images"] == built(remote=live)
               and review["plan_sha256"] == sha(target.read_bytes())
               and all(sha(Path(p).read_bytes()) == h for p, h in review["artifacts"].items()), "review_source_plan_input_binding")
    data = parsed(root, target)
    full = folder / "validation-only-NEVER-APPLY.tfplan"
    if full.exists():
        data = resolve(data, parsed(root, full), set(RUNTIME))
    rt.require(all(c["status"] == "pass" for c in data.get("checks", [])), "every_check_pass")
    if stage == "runtime":
        guard_runtime(data, review["images"])
    else:
        guard_activation_policy(data, (folder / "predecessor-policy.xml").read_bytes().decode(), prep.load(folder / "inputs.tfvars.json"))
    if live:
        rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review["at"]) < timedelta(hours=2), "stale_plan")
        rt.require(snapshot() == review["baseline"], "current_full_baseline_drift")
    return review


def apply(stage):
    folder, root, target = location(stage)
    rt.require(not (folder / "apply-intent.json").exists(), "already_attempted_reconcile_no_replay")
    review = check(stage)
    proof = prep.load(folder / "validation.json")
    doc = (rt.ROOT / ".azure/deployment-plan.md").read_text()
    rt.require(proof["checks_passed"] and proof["plan_sha256"] == review["plan_sha256"] and proof["tooling"] == tooling()
        and proof["at"] in doc and review["plan_sha256"] in doc and "POC activation " + stage + " status: Validated." in doc
        and prep.load(rt.ROOT / ".azure/validate-status.json")["completedStep"] == "UpdateStatus", "independent_current_validation_required")
    exclusive(folder, "apply-intent.json", {"at": fs.stamp(), "plan_sha256": review["plan_sha256"]})
    output = fs.terraform(root, "apply", "-input=false", "-no-color", str(target))
    exclusive(folder, "applied.json", {"at": fs.stamp(), "plan_sha256": review["plan_sha256"], "summary": re.findall(r"Apply complete! Resources: [^\r\n]+", output)})
    print(json.dumps(prep.load(folder / "applied.json")), flush=True)


def verify(stage):
    folder, _, _ = location(stage)
    review = check(stage, live=False)
    rt.require(prep.load(folder / "applied.json")["plan_sha256"] == review["plan_sha256"], "matching_apply")
    current = snapshot()
    expected = deepcopy(review["baseline"])
    if stage == "runtime":
        settings = fs.current_settings()
        previous = deepcopy(settings)
        preflight_flags = prep.load(HOME / "permission-preflight.json")["api_control_flags"]
        for k, v in preflight_flags.items():
            if v is None:
                previous["api"].pop(k, None)
            else:
                previous["api"][k] = v
        guard_protected(expected, current, previous, settings, review["images"])
    else:
        desired = (folder / "desired-policy.xml").read_bytes().decode()
        rt.require(policy_structure(ProductRun().policy()) == policy_structure(desired), "exact_policy_readback")
        expected["active_policy_sha256"] = current["active_policy_sha256"]
        rt.require(current == expected, "policy_protected_baseline_drift")
    proof = {"at": fs.stamp(), "stage": stage, "plan_sha256": review["plan_sha256"], "passed": True,
        "baseline": current, "images": {k: v["image"] for k, v in current["runtime"]["sites"].items()}, "inference_requests": 0}
    exclusive(folder, "verified.json", proof)
    print(json.dumps({k: v for k, v in proof.items() if k != "baseline"}), flush=True)


if __name__ == "__main__":
    try:
        globals()[sys.argv[1]](sys.argv[2])
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__, "reason": str(error) if isinstance(error, RuntimeError)
                          else "activation_failed_sensitive_detail_suppressed"}), flush=True)
        raise SystemExit(1)