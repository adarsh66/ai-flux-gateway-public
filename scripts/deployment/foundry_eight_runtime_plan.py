"""One new FOUR-image saved plan; NO apply/build/DB/inference entrypoint.

Compose from the actual applied rate-card archive, not the dirty working root.
Retain the remote main-state owner, every runtime setting and existing Function
configuration. Historical controllers are read-only helpers; private transport
bindings retain strict TLS and permit only documented settings-list POST reads.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time
from urllib.request import build_opener, HTTPSHandler
import zipfile

from scripts.deployment import foundry_eight_gateway_release as gateway
from scripts.deployment import foundry_eight_gateway_apply as gateway_apply
from scripts.deployment import foundry_eight_runtime_release as builds

rt = gateway.rt
rate = gateway.rate
fs = rate.r.fs
require = rt.require
sha = gateway.digest
load = gateway.load
now = gateway.now
HOME = rt.HOME / "foundry-eight-runtime-plan-20261031"
ROOT = HOME / "infra/terraform"
PLAN = HOME / "four-images.tfplan"
BUILD = builds.HOME
RATE = rate.HOME
GATEWAY = gateway.HOME / "attempts/apply01"
KINDS = ("api", "admin", "customer", "ingestion")
ADDRESSES = {**{f'azurerm_linux_web_app.main["{k}"]': k for k in KINDS[:3]},
             fs.FUNCTION: "ingestion"}
RUNS = dict(zip(KINDS, ("cm3s", "cm3t", "cm3u", "cm3v")))
DIGESTS = dict(zip(KINDS, (
    "f82fd47eb54f1e331ebf5ae7d9305d3238e78f50bd0d2a6c15b74216ba69b663",
    "0d5bc4e60af8d003c786c0b511f4d4bb7a8926ae8883a4fbffe8aff0139b5ca5",
    "cb12513df262891762d6c59017ee8bc8aad3879ddc78b0eccfd318f1eec92e53",
    "d60816f38b399f3e9f925b4dacf998ca3df08e393f884406a91cbf113cc2798e")))
SOURCE = "da7b3dcfed9e586db5f3ccfe2c1a01af384147ed877948a4bc48d966c09fccac"
WORKFLOW = Path("C:/Users/p4032099/.agents/skills/azure-validate/references/scripts/workflow.sh")
WORKFLOW_SHA = "699defd6489930070d5330432dbf257b9f89d6752caef69e0cf47e47edc2c620"
BASH = Path("C:/Program Files/Git/bin/bash.exe")


def write(name, value):
    path = HOME / name
    require(path.resolve().is_relative_to(HOME.resolve()), "owned_output_only")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return sha(raw)


def hashes(paths):
    return {p.relative_to(rt.ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(set(paths))}


def history():
    # Entire frozen build stage, accepted infrastructure dependencies, existing
    # controllers and shared status are immutable inputs to this NEW release.
    paths = [p for p in BUILD.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += list((rt.ROOT / "scripts/deployment").glob("*.py"))
    paths += [p for p in (RATE / "infra/terraform").iterdir() if p.is_file()]
    paths += [p for p in (RATE / "gateway").rglob("*") if p.is_file()]
    paths += [p for p in (RATE / "infra/models").rglob("*") if p.is_file()]
    paths += [RATE / n for n in ("rate-card.tfplan", "review.json", "verified.json", "applied.json", "inputs.tfvars.json")]
    paths += [GATEWAY / n for n in ("verified.json", "postapply-snapshot.json", "postapply-policy.xml", "postapply-backend-hashes.json")]
    paths += [gateway.OWNER, rt.ROOT / "infra/terraform/backend.hcl", rt.HOME / "terraform.rc",
              rt.ROOT / ".azure/deployment-plan.md", rt.ROOT / ".azure/validate-status.json", WORKFLOW,
              rt.ROOT / "tests/unit/test_foundry_eight_runtime_plan.py"]
    # The installed workflow lives outside the repository and is bound separately.
    return hashes(p for p in paths if p.is_relative_to(rt.ROOT))


def check_history():
    expected = load(HOME / "historical-inputs.json")
    require(history() == expected, "historical_sources_or_receipts_changed")
    return expected


def command(label, argv, *, cwd=None, stdin=None, timeout=1800):
    write("commands/" + label + "-intent.json", {"at": now(), "pid": os.getpid(), "argv": argv,
          "timeout_seconds": timeout, "stdin_sha256": sha(stdin.encode()) if stdin is not None else None})
    try:
        child = subprocess.run(argv, cwd=cwd or rt.ROOT, env=rt.ENV, input=stdin,
            capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        write("commands/" + label + "-result.json", {"at": now(), "error": "TimeoutExpired", "replay": False})
        raise RuntimeError("bounded_command_timeout:" + label) from None
    out, err = child.stdout.encode(), child.stderr.encode()
    write("commands/" + label + ".stdout.txt", out)
    write("commands/" + label + ".stderr.txt", err)
    write("commands/" + label + "-result.json", {"at": now(), "exit_code": child.returncode,
          "stdout_sha256": sha(out), "stderr_sha256": sha(err)})
    require(child.returncode == 0, "command_failed_private_diagnostic:" + label)
    print(json.dumps({"at": now(), "command": label, "exit_code": 0}), flush=True)
    return child.stdout


def terraform(label, *args, stdin=None):
    require(args and args[0] in ("init", "workspace", "validate", "fmt", "version", "show", "state", "providers", "plan", "console"),
            "no_apply_or_other_terraform_command")
    require(args[0] != "state" or args[1:] in (("pull",), ("list",)), "read_only_state")
    require(args[0] != "workspace" or args[1:] == ("show",), "existing_workspace_only")
    if args[0] == "plan":
        require(label == "plan-once" and not PLAN.exists() and load(HOME / "plan-intent.json")["max_plan_invocations"] == 1,
                "sole_new_plan_only")
    return command(label, [rt.TF, "-chdir=" + str(ROOT), *args], stdin=stdin)


def cli(label, args):
    require(args == ["account", "show"] or args == ["account", "get-access-token", "--subscription", rt.SUB,
             "--resource", "https://management.azure.com/"] or
            args[:3] in (["acr", "task", "show-run"], ["acr", "manifest", "show-metadata"]), "readonly_cli")
    # Tokens never enter an on-disk command stream.
    if args[:2] == ["account", "get-access-token"]:
        child = subprocess.run(rt.CLI + args + ["--only-show-errors", "-o", "json"], env=rt.ENV,
            capture_output=True, encoding="utf-8", timeout=240)
        require(child.returncode == 0, "token_read_failed")
        return json.loads(child.stdout)
    return json.loads(command(label, rt.CLI + args + ["--only-show-errors", "-o", "json"], timeout=240))


class ReadOnly(gateway.AttemptReader):
    request = gateway.rebound(gateway.AttemptReader.request, exclusive=write)
    cli = gateway.rebound(gateway.AttemptReader.cli, exclusive=write)

    def __init__(self, label):
        token = cli(label + "-token", ["account", "get-access-token", "--subscription", rt.SUB,
                    "--resource", "https://management.azure.com/"])["accessToken"]
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        require(claims["tid"] == rt.TENANT and claims["oid"] == rt.OPERATOR and
                claims["exp"] > datetime.now(UTC).timestamp() + 600, "strict_token_scope_lifetime")
        self.token, self.count, self.label, self.cache = token, 0, label, {}
        self.deadline = time.monotonic() + 2400
        self.tls = ssl.create_default_context(cafile=rt.CA)
        require(self.tls.check_hostname and self.tls.verify_mode == ssl.CERT_REQUIRED, "strict_tls")
        self.opener = build_opener(HTTPSHandler(context=self.tls), gateway.NoRedirect())


def capture(label):
    # Same complete protected projection as the accepted gateway postapply,
    # including actual five-IP storage. Never compare to obsolete 13-route policy.
    operation = gateway.rebound(gateway_apply.capture, ReadOnly=ReadOnly, write=write)
    snapshot, active, backends = operation(label)
    expected = load(GATEWAY / "postapply-snapshot.json")
    require(snapshot == expected, "current_post_gateway_full_protected_baseline_drift")
    proof = load(GATEWAY / "verified.json")
    require(proof["passed"] and proof["all_four_settings_equal"] and proof["runtime_unchanged"] and
            proof["actual_advertised_count"] == 21 and sha(active.encode()) == proof["current_policy_sha256"],
            "actual_accepted_gateway_proof")
    require(sha(gateway.OWNER.read_bytes()) == proof["state"]["sha256"], "separate_gateway_state_unchanged")
    require(set(gateway.advertised(gateway.xml_node(active, exported=True))) == set(proof["actual_advertised_aliases"]),
            "exact_twentyone_routes")
    for kind in KINDS:
        require(snapshot["baseline"]["runtime"]["sites"][kind]["image"] ==
                "DOCKER|" + builds.HOST + "/aiflux-" + kind + "@sha256:" + builds.PINS[kind], "old_runtime_pin:" + kind)
    write(label + "-protected-proof.json", {"at": now(), "full_post_gateway_baseline_equal": True,
          "snapshot_sha256": sha(snapshot), "gateway_receipt_sha256": sha((GATEWAY / "verified.json").read_bytes()),
          "route_count": 21, "runtime_flags": snapshot["runtime_flags"], "four_current_old_pins_exact": True})
    return snapshot


def build_binding(remote):
    require(sha((BUILD / "result.json").read_bytes()) == "e4bdd1321c34a20376e42418e70a620218b8230dfd47a6632f3cbc82903c0a9c",
            "completed_build_receipt")
    result = load(BUILD / "result.json")
    require(result["runtime_unchanged"] and not result["runtime_apply"] and result["source_sha256"] == SOURCE,
            "frozen_source_result")
    freeze = load(BUILD / "context-freeze.json")
    require(set(freeze) == {*KINDS, "api-native", "ingestion-native"}, "exact_six_frozen_build_and_native_contexts")
    for kind, entries in freeze.items():
        require(builds.files(BUILD / "contexts" / kind) == entries, "frozen_build_context:" + kind)
    images = {}
    for kind in KINDS:
        receipt = load(BUILD / ("build-" + kind + "-result.json"))
        require(receipt["status"] == "Succeeded" and receipt["run_id"] == RUNS[kind] and
                receipt["source_sha256"] == SOURCE and receipt["digest"] == "sha256:" + DIGESTS[kind] and not receipt["no_push"],
                "exact_green_original_build:" + kind)
        image = builds.HOST + "/aiflux-" + kind + "@sha256:" + DIGESTS[kind]
        require(receipt["image"] == image, "exact_receipt_digest_image")
        if remote:
            run = cli("acr-" + kind + "-run", ["acr", "task", "show-run", "--registry", builds.REGISTRY,
                      "--subscription", rt.SUB, "--run-id", RUNS[kind]])
            meta = cli("acr-" + kind + "-digest", ["acr", "manifest", "show-metadata", "--registry", builds.REGISTRY,
                       "--subscription", rt.SUB, "--name", "aiflux-" + kind + "@sha256:" + DIGESTS[kind]])
            require(run["status"] == "Succeeded" and run["finishTime"] == receipt["finished_at"] and
                    run["outputImages"] == receipt["outputs"] and meta["digest"] == receipt["digest"], "actual_registry_digest_binding")
        images[kind] = image
    return images


def guard(plan, images, baseline, validation=None):
    """Independent exact FOUR-resource, image-leaves-only semantic guard."""
    require(set(images) == set(KINDS) and plan.get("applyable") is True and not plan.get("errored") and
            not plan.get("deferred_changes"), "resolved_four_image_plan_required")
    seen, changes = set(), []
    for row in plan.get("resource_changes", []):
        c = row["change"]
        if c["actions"] == ["no-op"] or (c["actions"] == ["read"] and row.get("mode") == "data"):
            continue
        address = row["address"]
        require(row.get("mode") == "managed" and address in ADDRESSES and address not in seen and
                c["actions"] == ["update"] and not row.get("deposed") and not c.get("importing") and
                not c.get("generated_config"), "exact_four_existing_updates_only")
        seen.add(address)
        old, new = deepcopy(c["before"]), deepcopy(c["after"])
        unknown = c.get("after_unknown") or {}
        require(not any(gateway.rate.r.any_unknown(v) for k, v in unknown.items() if k not in fs.COMPUTED), "unknown_writable")
        for key in fs.COMPUTED:
            if gateway.rate.r.any_unknown(unknown.get(key)):
                new[key] = old.get(key)
        kind = ADDRESSES[address]
        require(re.fullmatch(re.escape(builds.HOST + "/aiflux-" + kind + "@sha256:") + "[a-f0-9]{64}", images[kind]), "immutable_digest_only")
        rid = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind
        require(old["id"] == new["id"] == rid and old["name"] == new["name"] == "poc-ids-token-ex-" + kind,
                "existing_exact_microsoft_web_site_id")
        require(len(old["site_config"]) == len(new["site_config"]) == 1, "single_site_config")
        a, b = old["site_config"][0]["application_stack"], new["site_config"][0]["application_stack"]
        require(len(a) == len(b) == 1, "single_stack")
        previous = baseline["runtime"]["sites"][kind]["image"]
        if kind == "ingestion":
            x, y = a[0]["docker"], b[0]["docker"]
            require(len(x) == len(y) == 1 and x[0]["image_name"] == y[0]["image_name"] == "aiflux-ingestion@sha256" and
                    x[0]["registry_url"] == y[0]["registry_url"] == "https://" + builds.HOST and
                    previous == "DOCKER|" + builds.HOST + "/" + x[0]["image_name"] + ":" + x[0]["image_tag"] and
                    y[0]["image_tag"] == images[kind].split("@sha256:")[1], "exact_function_predecessor_target")
            y[0]["image_tag"] = x[0]["image_tag"]
            path = "site_config[0].application_stack[0].docker[0].image_tag"
        else:
            require("DOCKER|" + builds.HOST + "/" + a[0]["docker_image_name"] == previous and
                    b[0]["docker_image_name"] == images[kind].split("/", 1)[1] and
                    b[0]["docker_registry_url"] == "https://" + builds.HOST, "exact_web_predecessor_target")
            b[0]["docker_image_name"] = a[0]["docker_image_name"]
            path = "site_config[0].application_stack[0].docker_image_name"
        require(old == new and c["before"] != c["after"], "nonimage_delta_rejected")
        changes.append({"address": address, "id": rid, "actions": ["update"], "only_changed_leaf": path,
                        "before_image": previous, "after_image": "DOCKER|" + images[kind]})
    require(seen == set(ADDRESSES), "exact_four_updates_required")
    checks = plan.get("checks")
    require(checks and all(c["status"] in ("pass", "unknown") for c in checks), "no_failed_plan_checks")
    for c in checks:
        if c["status"] == "unknown":
            require(c["address"].get("kind") == "var" and validation and validation["all_conditions_true"] and
                    validation["plan_json_sha256"] == sha((HOME / "plan.json").read_bytes()), "unknown_resource_or_unproven_input_check")
    require(not plan.get("resource_drift"), "unreviewed_refresh_drift")
    return changes


def compose():
    review = load(RATE / "review.json")
    require(sha((RATE / "rate-card.tfplan").read_bytes()) == review["plan_sha256"] and
            load(RATE / "applied.json")["plan_sha256"] == review["plan_sha256"] and
            load(RATE / "verified.json")["passed"], "accepted_applied_ratecard_source")
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(RATE / "rate-card.tfplan") as archive:
        for name in archive.namelist():
            if not name.startswith("tfconfig/m-/"):
                continue
            leaf = name.removeprefix("tfconfig/m-/")
            require("/" not in leaf and leaf.endswith((".tf", ".tf.json")) and "auto" not in leaf.lower(), "accepted_root_source_only")
            raw = archive.read(name)
            require(raw == (RATE / "infra/terraform" / leaf).read_bytes() and
                    review["artifacts"].get(str(RATE / "infra/terraform" / leaf)) == sha(raw), "actual_applied_source_bytes")
            write("infra/terraform/" + leaf, raw)
        lock = archive.read(".terraform.lock.hcl")
        require(lock == (RATE / "infra/terraform/.terraform.lock.hcl").read_bytes(), "accepted_provider_lock")
        write("infra/terraform/.terraform.lock.hcl", lock)
    for base in ("infra/models", "gateway"):
        for path in (RATE / base).rglob("*"):
            if path.is_file():
                require(path.suffix not in (".tfplan", ".tfstate") and ".terraform" not in path.parts, "source_dependency_only")
                write(path.relative_to(RATE).as_posix(), path.read_bytes())
    write("source-composition.json", {"at": now(), "origin": str(RATE / "rate-card.tfplan"),
          "applied_plan_sha256": review["plan_sha256"], "dirty_root_copied": False,
          "files": hashes(p for p in HOME.rglob("*") if p.is_file() and p.suffix in (".tf", ".json", ".tftpl", ".xml"))})


def varargs():
    return ["-var-file=" + str(HOME / "inputs.tfvars.json")]


def preserved_function(state, schema, settings, image):
    row = next(r for r in state["values"]["root_module"]["resources"] if r["address"] == fs.FUNCTION)
    before = row["values"]
    block = schema["provider_schemas"]["registry.terraform.io/hashicorp/azurerm"]["resource_schemas"]["azurerm_linux_function_app"]["block"]["block_types"]["site_config"]["block"]
    config = fs.writable_block(before["site_config"][0], block)
    stack = config["application_stack"][0]["docker"][0]
    require(stack["image_name"] == "aiflux-ingestion@sha256" and stack["image_tag"] == builds.PINS["ingestion"], "actual_function_state_old_pin")
    stack["image_tag"] = image.split("@sha256:")[1]
    expected = dict(settings)
    for name, field in {"AzureWebJobsStorage__accountName": "storage_account_name", "FUNCTIONS_EXTENSION_VERSION": "functions_extension_version"}.items():
        require(expected.get(name) == before.get(field), "provider_owned_function_setting_exact")
        expected.pop(name)
    require(expected == before["app_settings"], "all_function_settings_exact_state")
    return {"app_settings": fs.literal(expected), "site_config": [config],
            **{k: before[k] for k in ("enabled", "content_share_force_disabled", "public_network_access_enabled")}}


def input_checks(plan):
    conditions = []
    for path in sorted(ROOT.glob("*.tf")):
        text = path.read_text()
        conditions += re.findall(r'validation\s*\{\s*condition\s*=\s*(.*?)\s*\n\s*error_message\s*=', text, re.S)
    require(conditions, "actual_source_validation_conditions")
    expression = "jsonencode([" + ",\n".join("(" + c + ")" for c in conditions) + "])"
    raw = terraform("input-validation-console", "console", "-no-color", *varargs(), stdin=expression + "\n")
    values = json.loads(json.loads(raw))
    require(len(values) == len(conditions) and all(v is True for v in values), "every_actual_input_predicate_true")
    result = {"at": now(), "all_conditions_true": True, "condition_count": len(values),
              "condition_expressions_sha256": sha(expression.encode()), "plan_json_sha256": sha((HOME / "plan.json").read_bytes()),
              "raw_saved_checks_unchanged": True, "source": "actual archived validation conditions evaluated against exact plan var files"}
    write("input-check-proof.json", result)
    return result


def run_plan():
    require(not HOME.exists(), "existing_new_release_reconcile_only_never_replay")
    require(Path(rt.CA).is_file() and Path(rt.TF).is_file() and BASH.is_file() and
            sha(WORKFLOW.read_bytes()) == WORKFLOW_SHA, "existing_strict_ca_tools_workflow")
    require(not any(k.startswith("TF_CLI_ARGS") for k in rt.ENV), "no_hidden_terraform_arguments")
    fs.protect(HOME)
    write("run-intent.json", {"at": now(), "pid": os.getpid(), "controller_sha256": sha(Path(__file__).read_bytes()),
          "authorization": "explicit_new_four_images_saved_plan_only", "max_plan_invocations": 1, "applies": 0,
          "builds": 0, "DB_operations": 0, "inference": 0, "Auto": "HOLD", "replay_permitted": False})
    write("workers-before.json", gateway.worker_gate())
    write("historical-inputs.json", history())
    a = cli("account", ["account", "show"])
    require(a["id"] == rt.SUB and a["tenantId"] == rt.TENANT and a["state"] == "Enabled" and
            a["user"]["name"].lower() == "xv.puneet.devadiga@singtel.com", "exact_account")
    images = build_binding(remote=True)
    write("images.json", images)
    before = capture("preplan")
    compose()
    # Input values come from the actually applied plan, never current defaults.
    # Terraform show runs against the isolated root only after backend init.
    variables = load(RATE / "inputs.tfvars.json")
    for source in (rt.HOME / "rebuild-platform.tfvars.json", rt.HOME / "jwt-runtime.tfvars.json"):
        require(sha(source.read_bytes()) == load(RATE / "review.json")["tooling"][str(source)], "accepted_variable_file_binding")
    variables = {**load(rt.HOME / "rebuild-platform.tfvars.json"), **variables, **load(rt.HOME / "jwt-runtime.tfvars.json")}
    for kind in KINDS[:3]:
        variables["apps"][kind]["image"] = images[kind].split("/", 1)[1]
    variables["ingestion_container_image"] = images["ingestion"]
    write("inputs.tfvars.json", variables)
    terraform("init", "init", "-input=false", "-lockfile=readonly", "-no-color",
              "-backend-config=" + str(rt.ROOT / "infra/terraform/backend.hcl"))
    require(terraform("workspace", "workspace", "show").strip() == "default", "existing_main_default_workspace")
    metadata = load(ROOT / ".terraform/terraform.tfstate")["backend"]
    config = metadata["config"]
    require(metadata["type"] == "azurerm" and config["storage_account_name"] == "projpoctokenex" and
            config["container_name"] == "tfstate" and config["key"] == "poc-ids-token-ex/main.tfstate" and
            config["use_azuread_auth"] is True, "exact_existing_remote_main_owner")
    write("backend-proof.json", {"at": now(), "type": metadata["type"], "key": config["key"],
          "container": config["container_name"], "account": config["storage_account_name"], "entra_auth": True})
    state_raw = terraform("state-before", "state", "pull")
    state_id = json.loads(state_raw)
    require(state_id["lineage"] == "b05cbf70-2d31-0e6e-34b7-c97e8f617ed6", "main_state_lineage")
    state = json.loads(terraform("state-show", "show", "-json"))
    schema = json.loads(terraform("provider-schema", "providers", "schema", "-json"))
    settings = gateway.continuation_settings(ReadOnly("preserved-settings"))
    require({k: fs.sha(v) for k, v in settings.items()} == before["baseline"]["settings_hashes"], "all_current_settings_exact")
    preserved = preserved_function(state, schema, settings["ingestion"], images["ingestion"])
    write("infra/terraform/four_preserved.tf.json", {"locals": {"four_web_settings": fs.literal(fs.preserved_web_settings(settings))}})
    write("infra/terraform/zzzzz_four_images_override.tf.json", {"resource": {
        "azurerm_linux_web_app": {"main": {"app_settings": "${local.four_web_settings[each.key]}"}},
        "azurerm_linux_function_app": {"ingestion": preserved}}})
    del settings
    terraform("fmt", "fmt", "-check", "-no-color")
    valid = json.loads(terraform("validate", "validate", "-json"))
    require(valid["valid"] and not valid["error_count"], "actual_terraform_validate")
    context = hashes(p for p in HOME.rglob("*") if p.is_file() and ".terraform" not in p.parts and
                     p.suffix in (".tf", ".json", ".tftpl", ".xml", ".hcl") and
                     (p.is_relative_to(HOME / "infra") or p.is_relative_to(HOME / "gateway") or p.name == "inputs.tfvars.json"))
    write("plan-context.json", context)
    check_history()
    write("plan-intent.json", {"at": now(), "pid": os.getpid(), "targets": list(ADDRESSES),
          "max_plan_invocations": 1, "max_applies": 0, "context_sha256": sha(context), "images": images,
          "state_serial": state_id["serial"], "state_lineage": state_id["lineage"], "state_sha256": sha(state_raw.encode())})
    terraform("plan-once", "plan", "-input=false", "-no-color", "-lock-timeout=60s", "-parallelism=1", *varargs(),
              *["-target=" + a for a in ADDRESSES], "-out=" + str(PLAN))
    actual = terraform("show-plan", "show", "-json", str(PLAN))
    write("plan.json", actual.encode())
    data = json.loads(actual)
    validation = input_checks(data)
    changes = guard(data, images, before["baseline"], validation)
    after_state = terraform("state-after", "state", "pull")
    require(after_state == state_raw, "remote_main_state_bytes_changed")
    after = capture("postplan")
    require(after == before, "protected_state_changed_during_plan")
    check_history()
    write("review.json", {"at": now(), "status": "SAVED_FOUR_IMAGE_ONLY_NO_APPLY_PARENT_AUDIT_PENDING",
        "plan_sha256": sha(PLAN.read_bytes()), "plan_json_sha256": sha((HOME / "plan.json").read_bytes()),
        "source_sha256": SOURCE, "controller_sha256": sha(Path(__file__).read_bytes()), "context_sha256": sha(context),
        "changes": changes, "change_counts": {"create": 0, "update": 4, "delete": 0, "replace": 0},
        "images": images, "full_protected_snapshot_unchanged": True, "baseline_sha256": sha(before),
        "remote_state_unchanged": True, "state_serial": state_id["serial"], "state_lineage": state_id["lineage"],
        "input_validation": validation, "saved_check_counts": {s: sum(c["status"] == s for c in data["checks"]) for s in ("pass", "unknown", "fail")},
        "applies": 0, "builds": 0, "database_operations": 0, "inference": 0, "Auto": "HOLD"})
    print(json.dumps(load(HOME / "review.json")), flush=True)


def audit():
    review = load(HOME / "review.json")
    require(sha(PLAN.read_bytes()) == review["plan_sha256"] and sha((HOME / "plan.json").read_bytes()) == review["plan_json_sha256"], "actual_saved_plan_bytes")
    require(review["controller_sha256"] == sha(Path(__file__).read_bytes()), "frozen_controller_source")
    check_history()
    context = load(HOME / "plan-context.json")
    require(all(sha((rt.ROOT / p).read_bytes()) == h for p, h in context.items()) and sha(context) == review["context_sha256"], "exact_context_bytes")
    data = load(HOME / "plan.json")
    require(data == json.loads((HOME / "commands/show-plan.stdout.txt").read_bytes()), "native_show_actual_json")
    changes = guard(data, build_binding(remote=False), load(HOME / "preplan-snapshot.json")["baseline"], load(HOME / "input-check-proof.json"))
    require(changes == review["changes"] and load(HOME / "preplan-snapshot.json") == load(HOME / "postplan-snapshot.json"), "actual_changes_and_protected_receipts")
    with zipfile.ZipFile(PLAN) as archive:
        files = {"tfconfig/m-/" + p.name: p.read_bytes() for p in ROOT.iterdir() if p.is_file() and p.name.endswith((".tf", ".tf.json"))}
        require({n for n in archive.namelist() if n.startswith("tfconfig/m-/")} == set(files) and
                all(archive.read(k) == v for k, v in files.items()) and
                archive.read(".terraform.lock.hcl") == (ROOT / ".terraform.lock.hcl").read_bytes(), "actual_saved_configuration_not_sidecar_only")
        state = json.loads(archive.read("tfstate"))
        require(state["lineage"] == review["state_lineage"] and state["serial"] == review["state_serial"], "saved_main_state_owner")
    return review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "audit"))
    args = parser.parse_args()
    try:
        if args.action == "plan":
            run_plan()
        else:
            print(json.dumps(audit()), flush=True)
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Za-z0-9_:.\-]+", str(exc)) else "private_sensitive_diagnostic_retained"
        if HOME.exists():
            write("failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", {"at": now(), "pid": os.getpid(),
                  "error_type": type(exc).__name__, "reason": reason, "replay_permitted": False, "applies": 0})
        print(json.dumps({"error_type": type(exc).__name__, "reason": reason, "replay": False, "applies": 0}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())