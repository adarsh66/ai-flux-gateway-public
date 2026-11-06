"""One authorized plan02 APIM apply, then read-only reconciliation; never replan.

Only this new controller and attempts/apply01 are owned here. Historical reader
functions are imported/rebound privately, not monkeypatched or rewritten. An
exclusive fsynced intent precedes the ONLY Terraform apply invocation. Failure,
empty output or interrupted observation NEVER authorizes another invocation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.deployment import foundry_eight_gateway_release as reader

rt = reader.rt
require = reader.require
load = reader.load
digest = reader.digest
now = reader.now
PLAN_HOME = reader.HOME / "attempts/plan02"
EVIDENCE = reader.HOME / "attempts/apply01"
PLAN = PLAN_HOME / "gateway.tfplan"
APPROVED = "bb8aba49c135a58e1a84e25b8c28b36cab640bb4299bc6054f48f4e4bf33b433"
OWN = Path(__file__).resolve().relative_to(rt.ROOT).as_posix()
APIM = rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"
POLICY_ID = APIM + "/apis/aiflux-dev-unified/policies/policy"
CLAUDE = {a for a in reader.NEW if a.startswith("claude-")}
CLIENT = "5792b72e-1605-4dce-a594-4c430a5af619"


def write(name, value):
    """All output inherits the existing private release ACL; no ACL changes."""
    path = EVIDENCE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return digest(raw)


class ReadOnly(reader.AttemptReader):
    # Private globals retain strict TLS, GET/semantic settings-list POST
    # allowlists, bounded read retries and token-free endpoint journals.
    request = reader.rebound(reader.AttemptReader.request, exclusive=write)
    cli = reader.rebound(reader.AttemptReader.cli, exclusive=write)


def expected_ids():
    return {reader.POLICY: POLICY_ID, **{a: APIM + "/backends/" + v[0]
                                      for a, v in reader.BACKENDS.items()}}


def identities(plan):
    result = {}
    for row in plan["resource_changes"]:
        change = row["change"]
        if change["actions"] in (["no-op"], ["read"]):
            continue
        address = row["address"]
        require(address in expected_ids(), "changed_address_not_authorized")
        after = change["after"]
        if address == reader.POLICY:
            require(after["type"] == "Microsoft.ApiManagement/service/apis/policies@2024-05-01"
                    and after["name"] == "policy" and after["parent_id"] == APIM + "/apis/aiflux-dev-unified"
                    and after["id"] == change["before"]["id"] == POLICY_ID, "exact_existing_policy_id")
            target = after["id"]
        else:
            require(after["parent_id"] == APIM and change["actions"] == ["create"], "exact_backend_parent")
            target = after["parent_id"] + "/backends/" + after["name"]
        require(target == expected_ids()[address], "exact_changed_resource_id")
        result[address] = {"id": target, "actions": change["actions"]}
    require(set(result) == set(expected_ids()), "exact_three_resource_ids")
    return result


def semantic_policy(previous, desired):
    """Independently inspect actual rendered routing, not a format-only claim."""
    guards = reader.policy_guard(previous, desired)
    old, node = reader.xml_node(previous, exported=True), reader.xml_node(desired)
    catalogs = [json.loads(n.text)["data"] for n in node.findall("./inbound//set-body")
                if (n.text or "").startswith('{"data":')]
    require(len(catalogs) == 1 and len(catalogs[0]) == len(reader.advertised(node)) == 21,
            "exact_twentyone_unique_advertised_aliases")
    require(reader.structural(old) != reader.structural(node), "format_only_policy_is_not_rollout")
    for alias in reader.NEW:
        condition = '@((string)context.Variables["aiflux-model"] == "' + alias + '")'
        branches = [n for n in node.findall("./inbound//when") if n.get("condition") == condition
                    and n.find("set-backend-service") is not None and n.find("set-body") is not None]
        if alias in CLAUDE:
            require(len(branches) == 1, "one_native_dispatch:" + alias)
            branch = branches[0]
            require(branch.find("set-backend-service").attrib ==
                    {"backend-id": "aiflux-project-foundry-eight-anthropic"}, "native_backend:" + alias)
            require(branch.find("rewrite-uri").attrib ==
                    {"template": "/messages", "copy-unmatched-params": "false"}, "native_messages_path:" + alias)
            require(any(n.get("name") == "anthropic-version" and n.get("exists-action") == "override"
                        and n.findtext("value") == "2023-06-01" for n in branch.findall("set-header")),
                    "native_version:" + alias)
            body = branch.findtext("set-body") or ""
            require(all(x in body for x in ('["max_tokens"] = (int)request["max_completion_tokens"]',
                    '["model"] = (string)context.Variables["aiflux-model"]', '["stream"] = false',
                    'role == "system" || role == "developer"', 'converted["system"]')),
                    "native_request_conversion:" + alias)
            require(('converted["speed"] = "fast";' in body) == (alias == "claude-opus-5-5-fast"),
                    "exact_fast_speed_branch:" + alias)
        else:
            dispatches = [n for n in node.findall("./inbound//when") if n.get("condition") == condition
                          and n.find("set-backend-service") is not None]
            require(dispatches, "new_non_native_dispatch:" + alias)
            if alias == "Mistral-Large-3":
                require(any(n.find("set-backend-service").get("backend-id") ==
                    "aiflux-project-foundry-eight-mistral" for n in dispatches)
                    and any(n.attrib == {"template": "/chat/completions", "copy-unmatched-params": "false"}
                        for n in node.findall("./inbound//rewrite-uri"))
                    and any('if ((string)request["model"] == "Mistral-Large-3") { request["max_tokens"] = request["max_completion_tokens"]; request.Remove("max_completion_tokens"); }'
                        in (n.text or "") for n in node.findall("./inbound//set-body")),
                    "mistral_native_token_conversion")
    native_auth = [n for n in node.findall("./inbound//when")
                   if n.find("authentication-managed-identity") is not None and "claude-" in n.get("condition", "")]
    # One shared Claude auth branch follows routing/header deletion. The other
    # ai.azure.com node belongs to the unchanged Fireworks branch, NOT Claude.
    require(len(native_auth) == 1, "single_shared_native_auth_branch")
    for branch in native_auth:
        aliases = set(re.findall(r'context\.Variables\["aiflux-model"\] == "([^"]+)"', branch.get("condition", "")))
        require(aliases == CLAUDE and branch.find("authentication-managed-identity").attrib ==
                {"resource": "https://ai.azure.com", "client-id": CLIENT, "ignore-error": "false"},
                "all_five_claude_exact_audience_and_identity")
    require(all(n.get("client-id") == CLIENT and n.get("ignore-error") == "false"
                and n.get("resource") in ("https://ai.azure.com", "https://cognitiveservices.azure.com/")
                for n in node.findall(".//authentication-managed-identity")), "existing_mi_bindings_retained")
    normalization = node.findall('./outbound//set-body[@id="aiflux-anthropic-normalization"]')
    require(len(normalization) == 1, "single_native_response_normalization")
    text = normalization[0].text or ""
    require(all(x in text for x in ('response["content"] as JArray', 'response["usage"] as JObject',
        '"cache_read_input_tokens"', '"cache_creation_input_tokens"', 'Invalid provider cache usage',
        'Invalid provider usage total', 'Invalid provider speed', '"claude-opus-5-5-fast"',
        'usage["speed"] != "fast"', '"standard"', 'type == "thinking"', '"max_tokens" ? "length" : "stop"',
        '["object"] = "chat.completion"', '["prompt_tokens"] = promptTokens')),
        "strict_native_response_usage_speed_normalization")
    require('pii_inspection_unavailable' in desired and 'no answer was released' in desired
            and 'aiflux-native-answer' in desired, "native_answer_must_pass_output_safety")
    return {**guards, "advertised_aliases": sorted(reader.advertised(node)), "advertised_count": 21,
            "claude_count": 5, "claude_audience": "https://ai.azure.com", "gateway_client_id": CLIENT,
            "exact_fast_only_request_branch": True, "strict_native_response_normalization": True,
            "format_only_claim_rejected": True}


def check_hashes(mapping, code):
    require(all(digest((rt.ROOT / path).read_bytes()) == sha for path, sha in mapping.items()), code)


def bound():
    review = load(PLAN_HOME / "review.json")
    require(digest(PLAN.read_bytes()) == review["plan_sha256"] == APPROVED, "exact_parent_approved_saved_plan")
    require(digest((PLAN_HOME / "plan.json").read_bytes()) == review["plan_json_sha256"], "exact_plan_json_bytes")
    # The NEW apply controller is expressly excluded from the historical glob
    # binding, and separately bound in our intent. No historical receipt changes.
    sources = reader.inputs_bound()
    require(OWN not in review["sources"] and sources.pop(OWN, None) == digest(Path(__file__).read_bytes()),
            "only_new_owned_apply_source_excluded")
    require(sources == review["sources"], "all_reviewed_sources_exact")
    require(reader.digest(reader.context_hashes()) == review["context_sha256"], "exact_private_context")
    require(reader.state_identity() == review["state"], "original_state185_bytes_lineage_path")
    check_hashes(review["artifacts"], "retained_plan_artifact_integrity")
    launch = load(PLAN_HOME / "attempt-intent.json")
    check_hashes(launch["consumed_receipts_preserved"], "consumed_receipt_integrity")
    require(digest((reader.HOME / "prepared.json").read_bytes()) == reader.ORIGINAL_PREPARED ==
            review["original_prepared_receipt_sha256"], "original_prepared_integrity")
    correction = load(reader.HOME / "plan02-guard-correction-review.json")
    require(correction["corrected_controller_sha256"] == review["guard_controller_sha256"] ==
            digest(Path(reader.__file__).read_bytes()) and correction["plan_sha256"] == APPROVED
            and correction["plan_generator_controller_sha256"] == review["plan_generator_controller_sha256"],
            "reviewed_controller_provenance")
    data = load(PLAN_HOME / "plan.json")
    require(data == json.loads((PLAN_HOME / "commands/show.stdout.txt").read_bytes()), "actual_plan_json_equals_native_show")
    previous = (PLAN_HOME / "preplan-policy.xml").read_bytes().decode()
    desired = (reader.HOME / "candidate-policy.xml").read_bytes().decode()
    require(digest(desired.encode()) == review["candidate_policy_sha256"], "candidate_policy_binding")
    proof = load(PLAN_HOME / "format-input-check.json")
    require(digest((PLAN_HOME / "commands/format-input-check-result.json").read_bytes()) == proof["console_result_sha256"],
            "separate_input_predicate_receipt")
    require(reader.guard(data, previous, desired, load(reader.HOME / "inputs.tfvars.json"), proof) == review["changes"],
            "actual_saved_plan_strict_scope_guard")
    with zipfile.ZipFile(PLAN) as archive:
        config = {"tfconfig/m-/" + p.name: p.read_bytes() for p in reader.TFROOT.glob("*.tf")}
        require({n for n in archive.namelist() if n.startswith("tfconfig/m-/")} == set(config)
                and all(archive.read(k) == v for k, v in config.items())
                and archive.read(".terraform.lock.hcl") == (reader.TFROOT / ".terraform.lock.hcl").read_bytes(),
                "actual_saved_config_and_lock_bytes")
        require(not any(re.search(rb'backend\s+"', raw) for raw in config.values())
                and not (reader.TFROOT / "terraform.tfstate").exists(), "existing_local_backend_exact_owner_only")
        state = json.loads(archive.read("tfstate"))
        require(state["serial"] == 185 and state["lineage"] == review["state"]["lineage"], "saved_state185_lineage")
        def ids(value):
            return {(r["mode"], r["type"], r["name"], str(i.get("index_key"))): i["attributes"].get("id")
                    for r in value["resources"] for i in r["instances"] if r["mode"] == "managed"}
        require(ids(state) == ids(load(reader.OWNER)), "saved_existing_managed_state_ownership")
    require(load(PLAN_HOME / "preplan-snapshot.json") == load(PLAN_HOME / "postplan-snapshot.json") ==
            load(reader.HOME / "prepare-snapshot.json"), "all_retained_full_snapshots_equal")
    completion = load(PLAN_HOME / "official-validation-completion.json")
    require(completion["status"] == "VALIDATED_READONLY_NO_APPLY_PARENT_AUDIT_PENDING"
            and completion["plan_sha256"] == APPROVED and completion["final_step"]["step"] == "UpdateStatus"
            and load(PLAN_HOME / ".azure/validate-status.json")["completedStep"] == "UpdateStatus"
            and (PLAN_HOME / ".azure/deployment-plan.md").read_text().splitlines()[2] == "Status: Validated",
            "official_validation_must_be_green")
    workflow = Path("C:/Users/p4032099/.agents/skills/azure-validate/references/scripts/workflow.sh")
    require(digest(workflow.read_bytes()) == completion["workflow_sha256"], "unchanged_official_workflow")
    require([r["step"] for r in completion["all_steps"]] == ["None", "LoadPlan", "AddValidationSteps",
            "RunValidation", "BuildVerification", "StaticRoleVerification", "RecordProof", "ResolveErrors", "UpdateStatus"],
            "actual_official_sequential_completion")
    for row in completion["all_steps"]:
        require(row["exit_code"] == 0 and row == load(PLAN_HOME / ("official-" + row["step"] + "-result.json")),
                "official_step_exit_zero")
        for stream in ("stdout", "stderr"):
            require(digest((PLAN_HOME / ("official-" + row["step"] + "." + stream + ".txt")).read_bytes()) ==
                    row[stream + "_sha256"], "official_step_output_integrity")
    return {"plan_sha256": APPROVED, "changed_ids": identities(data), "state": review["state"],
            "policy_review": semantic_policy(previous, desired), "sources": sources,
            "official_validation_completion_sha256": digest((PLAN_HOME / "official-validation-completion.json").read_bytes())}


def capture(label):
    write(label + "-intent.json", {"at": now(), "pid": os.getpid(), "methods": ["GET", "settings-list-POST-read"]})
    transport = ReadOnly(label)
    baseline = reader.continuation_snapshot(transport)
    settings = reader.continuation_settings(transport)
    require(set(settings) == set(reader.PINS) and all(settings[k] for k in reader.PINS)
            and {k: reader.rate.r.fs.sha(v) for k, v in settings.items()} == baseline["settings_hashes"],
            "actual_complete_four_settings_hashes")
    flags = {k: settings["api"].get(k) for k in reader.rate.r.FLAGS}
    del settings
    require(flags == reader.rate.r.FLAGS, "runtime_flags_preserved")
    def url(suffix):
        return "https://management.azure.com" + APIM + suffix + ("&" if "?" in suffix else "?") + "api-version=2024-05-01"
    supplemental, counts, collections = {}, {}, {}
    for key, suffix in (("backends", "/backends"), ("subscriptions", "/subscriptions"), ("products", "/products"),
                        ("operations", "/apis/aiflux-dev-unified/operations"), ("bindings", "/apis/aiflux-dev-unified/products")):
        value = transport.collection(url(suffix))
        collections[key] = value
        supplemental[key], counts[key] = digest(value), len(value["value"])
        policy_prefix = "/products/" if key == "products" else "/apis/aiflux-dev-unified/operations/"
        if key in ("products", "operations"):
            for row in value["value"]:
                name = row["name"]
                supplemental[("product_policy:" if key == "products" else "operation_policy:") + name] = digest(
                    transport.get(url(policy_prefix + name + "/policies/policy?format=xml"), optional=True))
    active = transport.get(url("/apis/aiflux-dev-unified/policies/policy?format=xml"))["properties"]["value"]
    write(label + "-policy.xml", active.encode())
    account_url = "https://management.azure.com" + rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
    deployments = transport.collection(account_url + "/deployments?api-version=2025-06-01")
    supplemental.update(deployments=digest(deployments), active_policy=digest(active.encode()))
    snapshot = {"baseline": baseline, "supplemental": supplemental, "counts": counts, "runtime_flags": flags}
    write(label + "-snapshot.json", snapshot)
    # Backend bodies contain no credentials for the two new resources. Retain
    # old bodies only as hashes; compare complete actual collections in memory.
    write(label + "-backend-hashes.json", {r["name"]: digest(r) for r in collections["backends"]["value"]})
    write(label + "-result.json", {"at": now(), "snapshot_sha256": digest(snapshot), "reads": transport.count,
                                  "advertised_count": len(reader.advertised(reader.xml_node(active, exported=True)))})
    return snapshot, active, collections["backends"]


def projected_snapshot(snapshot, before):
    """Only exact API policy content and backend collection/count may differ."""
    value = deepcopy(snapshot)
    for path in (("baseline", "active_policy_sha256"), ("baseline", "apim", "backends"),
                 ("supplemental", "active_policy"), ("supplemental", "backends"), ("counts", "backends")):
        target, original = value, before
        for part in path[:-1]:
            target, original = target[part], original[part]
        target[path[-1]] = original[path[-1]]
    return value


def backend_delta(before, after):
    old = {r["name"]: r for r in before["value"]}
    new = {r["name"]: r for r in after["value"]}
    require(len(old) == len(before["value"]) and len(new) == len(after["value"]), "unique_backend_names")
    require(all(new.get(name) == row for name, row in old.items()), "all_existing_backend_objects_unchanged")
    added = set(new) - set(old)
    require(added <= {v[0] for v in reader.BACKENDS.values()}, "no_unapproved_backend_added")
    data = load(PLAN_HOME / "plan.json")
    for address, (name, endpoint) in reader.BACKENDS.items():
        if name not in added:
            continue
        row = new[name]
        expected = next(r["change"]["after"]["body"]["properties"] for r in data["resource_changes"] if r["address"] == address)
        require(row["id"].lower() == expected_ids()[address].lower() and row["name"] == name
                and row["properties"] == expected and row["properties"]["url"] == endpoint,
                "new_backend_exact_saved_properties:" + name)
    return sorted(added)


def sanitized(text):
    text = re.sub(r"(?i)Bearer\s+\S+|eyJ[A-Za-z0-9_.-]{30,}", "[redacted-token]", text)
    text = re.sub(r"\{\{[^}]+\}\}|https?://[^\s\"<>]+", "[redacted-reference]", text)
    text = re.sub(r"(?i)(api[-_]?key|authorization|password|secret|connectionstring)\s*[:=]\s*[^\s,;]+",
                  "[redacted-sensitive-field]", text)
    return text[:5000]


def apply_once(binding):
    require(not (EVIDENCE / "apply-intent.json").exists(), "apply_consumed_reconcile_original_only")
    argv = [rt.TF, "-chdir=" + str(reader.TFROOT), "apply", "-input=false", "-no-color", "-json",
            "-lock-timeout=30s", "-state=" + str(reader.OWNER), str(PLAN)]
    env = {k: v for k, v in rt.ENV.items() if not k.startswith(("TF_CLI_ARGS", "TF_LOG", "ARM_")) and k != "TF_DATA_DIR"}
    env.update(TF_IN_AUTOMATION="1", CHECKPOINT_DISABLE="1")
    write("apply-intent.json", {"at": now(), "pid": os.getpid(), "plan_sha256": APPROVED, "argv": argv,
        "state": binding["state"], "changed_ids": binding["changed_ids"], "max_command_invocations": 1,
        "source_sha256": digest(Path(__file__).read_bytes()), "authorization": "parent_explicit_exact_saved_plan_user_full_rollout",
        "replans": 0, "builds": 0, "inference": 0, "automatic_retry": False})
    # No timeout/kill/relaunch. Original child PID and private output files allow
    # reconciliation even when the observer or terminal returns empty output.
    with (EVIDENCE / "apply.stdout.jsonl").open("xb") as stdout, (EVIDENCE / "apply.stderr.txt").open("xb") as stderr:
        child = subprocess.Popen(argv, cwd=rt.ROOT, env=env, stdout=stdout, stderr=stderr)
        write("apply-started.json", {"at": now(), "controller_pid": os.getpid(), "terraform_pid": child.pid,
                                    "plan_sha256": APPROVED})
        exit_code = child.wait()
        for handle in (stdout, stderr):
            handle.flush()
            os.fsync(handle.fileno())
    events = []
    for line in (EVIDENCE / "apply.stdout.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    changes = [r["changes"] for r in events if r.get("type") == "change_summary" and r.get("changes", {}).get("operation") == "apply"]
    completed = [{"address": r["hook"]["resource"]["addr"], "action": r["hook"].get("action")}
                 for r in events if r.get("type") == "apply_complete"]
    errors = [{"summary": sanitized(r["diagnostic"].get("summary", "")),
               "detail": sanitized(r["diagnostic"].get("detail", ""))}
              for r in events if r.get("type") == "diagnostic" and r["diagnostic"].get("severity") == "error"]
    result = {"at": now(), "plan_sha256": APPROVED, "terraform_pid": child.pid, "exit_code": exit_code,
              "actual_apply_summary": changes[-1] if changes else None, "actual_completed_resources": completed,
              "sanitized_errors": errors, "stdout_sha256": digest((EVIDENCE / "apply.stdout.jsonl").read_bytes()),
              "stderr_sha256": digest((EVIDENCE / "apply.stderr.txt").read_bytes()), "command_invocations": 1,
              "retry_permitted": False}
    write("apply-result.json", result)
    print(json.dumps(result), flush=True)
    return result


def run():
    require(not EVIDENCE.exists(), "apply01_consumed_reconcile_original_only")
    EVIDENCE.mkdir(parents=False, exist_ok=False)
    write("run-intent.json", {"at": now(), "pid": os.getpid(), "approved_plan_sha256": APPROVED,
          "source_sha256": digest(Path(__file__).read_bytes()), "scope": "saved_apim_plan_only_then_protected_readback"})
    reader.worker_gate()
    binding = bound()
    frozen = reader.hashes([p for p in reader.HOME.rglob("*") if p.is_file()
                           and ".terraform" not in p.parts and EVIDENCE not in p.parents])
    write("independent-review.json", binding)
    write("historical-preservation.json", frozen)
    reader.account()
    before, previous, backends_before = capture("preapply")
    require(before == load(PLAN_HOME / "postplan-snapshot.json"), "fresh_full_protected_predecessor_must_match")
    require(previous == (PLAN_HOME / "preplan-policy.xml").read_bytes().decode(), "fresh_policy_exact_saved_predecessor")
    require(not ({r["name"] for r in backends_before["value"]} & {v[0] for v in reader.BACKENDS.values()}),
            "new_backend_already_present")
    require(bound() == binding, "final_binding_race")
    check_hashes(frozen, "frozen_history_changed_before_apply")
    reader.worker_gate()
    write("preapply-passed.json", {"at": now(), "plan_sha256": APPROVED, "fresh_snapshot_sha256": digest(before),
                                   "exact_changed_ids": binding["changed_ids"], "all_predicates_true": True})
    applied = apply_once(binding)
    # ALWAYS attempt full protected readback after an actual command return,
    # including a compilation failure/partial backend creation. No more writes.
    after, current_policy, backends_after = capture("postapply")
    added = backend_delta(backends_before, backends_after)
    protected_equal = projected_snapshot(after, before) == before
    policy_matches = reader.structural(reader.xml_node(current_policy, exported=True)) == reader.structural(
        reader.xml_node((reader.HOME / "candidate-policy.xml").read_bytes().decode()))
    old_policy_matches = current_policy == previous
    advertised = sorted(reader.advertised(reader.xml_node(current_policy, exported=True)))
    state = load(reader.OWNER)
    readback = {"at": now(), "plan_sha256": APPROVED, "apply_exit_code": applied["exit_code"],
        "actual_added_backend_names": added, "protected_except_exact_policy_and_backends_equal": protected_equal,
        "current_policy_matches_saved_candidate": policy_matches, "current_policy_matches_predecessor": old_policy_matches,
        "current_policy_sha256": digest(current_policy.encode()), "actual_advertised_aliases": advertised,
        "actual_advertised_count": len(advertised), "all_four_settings_equal": after["baseline"]["settings_hashes"] == before["baseline"]["settings_hashes"],
        "runtime_unchanged": after["baseline"]["runtime"] == before["baseline"]["runtime"],
        "state": {"path": reader.OWNER.as_posix(), "sha256": digest(reader.OWNER.read_bytes()), "serial": state["serial"], "lineage": state["lineage"]},
        "builds": 0, "inference": 0, "replans": 0, "retries": 0, "further_writes": False}
    check_hashes(frozen, "frozen_history_changed_after_apply")
    readback["historical_artifacts_unchanged"] = True
    success = (applied["exit_code"] == 0 and protected_equal and policy_matches and len(advertised) == 21
               and len(added) == 2 and state["lineage"] == binding["state"]["lineage"])
    readback.update(passed=success, status="APPLIED_AND_PROTECTED_READBACK_PASSED" if success else "STOP_NO_RETRY_RECONCILED_ACTUAL_STATE")
    write("verified.json", readback)
    write("handoff.md", ("# One-shot eight-model APIM apply01 — actual result\n\n"
        + "Status: " + readback["status"] + "\n\nSaved plan SHA256: " + APPROVED + "\n\n"
        + "Terraform apply command invoked exactly once; exit " + str(applied["exit_code"]) + ". Never replay.\n\n"
        + "Actual apply summary: " + json.dumps(applied["actual_apply_summary"]) + "\n\n"
        + "Actual completed resources: " + json.dumps(applied["actual_completed_resources"]) + "\n\n"
        + "Sanitized actual errors: " + json.dumps(applied["sanitized_errors"]) + "\n\n"
        + "Added backends observed: " + json.dumps(added) + ". Actual advertised aliases: " + str(len(advertised)) + ".\n\n"
        + "Policy equals saved candidate: " + str(policy_matches) + "; equals predecessor: " + str(old_policy_matches) + ".\n\n"
        + "Full protected comparison (only exact API policy/two backends excepted): " + str(protected_equal) + ".\n\n"
        + "No inference, build, runtime/settings/roles/identity/network changes, Auto, replan, state edits or retry.\n"
        + "Independent review verified substantive eight-route addition and Claude normalization, not format-only.\n"
        + "See apply-result.json, verified.json, original PID receipt and protected snapshot hashes.\n").encode())
    print(json.dumps(readback), flush=True)
    return 0 if success else 1


def reconcile_readonly():
    """Consume completed original artifacts; GET only, never enter apply/run.

    ARM returns exactly title:null in addition to the requested backend body.
    Preserve the original strict failure and original source digest; this
    additive reconciliation accepts no other extra field or non-null title.
    """
    require(not (EVIDENCE / "verified.json").exists(), "already_reconciled_no_replay")
    reader.worker_gate()
    result = load(EVIDENCE / "apply-result.json")
    original = load(EVIDENCE / "apply-intent.json")
    failure = load(EVIDENCE / "failure-164636210276.json")
    require(result["exit_code"] == 0 and result["command_invocations"] == 1
            and result["actual_apply_summary"] == {"add": 2, "change": 1, "import": 0, "remove": 0, "operation": "apply"}
            and failure["reason"] == "new_backend_exact_saved_properties:aiflux-project-foundry-eight-anthropic"
            and result["plan_sha256"] == original["plan_sha256"] == APPROVED == digest(PLAN.read_bytes()),
            "only_actual_successful_apply_null_title_readback_stop")
    write("reconcile-readonly-intent.json", {"at": now(), "pid": os.getpid(), "plan_sha256": APPROVED,
          "original_apply_source_sha256": original["source_sha256"], "current_source_sha256": digest(Path(__file__).read_bytes()),
          "scope": "retained_full_snapshot_plus_exact_two_backend_GETs", "cloud_writes": 0, "apply_commands": 0})
    for stream, filename in (("stdout", "apply.stdout.jsonl"), ("stderr", "apply.stderr.txt")):
        require(digest((EVIDENCE / filename).read_bytes()) == result[stream + "_sha256"], "original_apply_output_integrity")
    check_hashes(load(EVIDENCE / "historical-preservation.json"), "all_historical_artifacts_unchanged")
    before, after = load(EVIDENCE / "preapply-snapshot.json"), load(EVIDENCE / "postapply-snapshot.json")
    require(before == load(PLAN_HOME / "postplan-snapshot.json") and projected_snapshot(after, before) == before,
            "full_actual_protected_snapshot_only_authorized_delta")
    for label, snapshot in (("preapply", before), ("postapply", after)):
        require(load(EVIDENCE / (label + "-result.json"))["snapshot_sha256"] == digest(snapshot), "snapshot_receipt_integrity")
    current = (EVIDENCE / "postapply-policy.xml").read_bytes().decode()
    require(digest(current.encode()) == after["supplemental"]["active_policy"] == after["baseline"]["active_policy_sha256"],
            "actual_live_policy_capture_integrity")
    require(reader.structural(reader.xml_node(current, exported=True)) == reader.structural(
        reader.xml_node((reader.HOME / "candidate-policy.xml").read_bytes().decode())), "whole_live_policy_matches_candidate")
    aliases = sorted(reader.advertised(reader.xml_node(current, exported=True)))
    require(aliases == load(EVIDENCE / "independent-review.json")["policy_review"]["advertised_aliases"]
            and len(aliases) == 21, "actual_advertised_exact_twentyone")
    old, new = load(EVIDENCE / "preapply-backend-hashes.json"), load(EVIDENCE / "postapply-backend-hashes.json")
    names = {v[0] for v in reader.BACKENDS.values()}
    require(set(new) - set(old) == names and all(new.get(k) == v for k, v in old.items())
            and after["counts"]["backends"] == before["counts"]["backends"] + 2, "only_two_new_backends_all_old_exact")
    transport = ReadOnly("reconcile-final")
    evidence = {}
    plan = load(PLAN_HOME / "plan.json")
    for address, (name, _) in reader.BACKENDS.items():
        row = transport.get("https://management.azure.com" + expected_ids()[address] + "?api-version=2024-05-01")
        expected = next(r["change"]["after"]["body"]["properties"] for r in plan["resource_changes"] if r["address"] == address)
        require(row["id"].lower() == expected_ids()[address].lower() and row["name"] == name
                and row["type"].lower() == "microsoft.apimanagement/service/backends"
                and row["properties"] == {**expected, "title": None}, "only_exact_actual_null_title_default:" + name)
        require(digest(row) == new[name], "fresh_backend_GET_equals_original_full_capture")
        evidence[name] = {"id": row["id"], "properties": row["properties"], "whole_object_sha256": digest(row)}
    write("backend-readonly-reconciliation.json", {"at": now(), "actual_two_backends": evidence,
          "only_additional_ARM_property": {"title": None}, "original_strict_failure_preserved": True,
          "cloud_writes": 0, "apply_commands": 0})
    state = load(reader.OWNER)
    require(state["lineage"] == original["state"]["lineage"] and state["serial"] > 185, "same_actual_state_owner_after_apply")
    verification = {"at": now(), "status": "APPLIED_ONCE_PROTECTED_READBACK_PASSED_NULL_TITLE_RECONCILED",
        "passed": True, "plan_sha256": APPROVED, "apply_exit_code": 0, "actual_resource_changes": result["actual_apply_summary"],
        "command_invocations": 1, "protected_except_exact_policy_and_backends_equal": True,
        "all_four_settings_equal": True, "runtime_unchanged": True, "all_existing_backends_unchanged": True,
        "current_policy_matches_saved_candidate": True, "current_policy_sha256": digest(current.encode()),
        "actual_advertised_count": 21, "actual_advertised_aliases": aliases, "actual_added_backend_names": sorted(names),
        "observed_ARM_extra_properties": {"title": None}, "original_failure_preserved": True,
        "historical_artifacts_unchanged": True, "source_at_apply_sha256": original["source_sha256"],
        "read_only_reconciliation_source_sha256": digest(Path(__file__).read_bytes()),
        "state": {"path": reader.OWNER.as_posix(), "sha256": digest(reader.OWNER.read_bytes()),
                  "lineage": state["lineage"], "serial": state["serial"]},
        "builds": 0, "inference": 0, "replans": 0, "apply_retries": 0, "further_cloud_writes": False}
    write("verified.json", verification)
    write("handoff.md", ("# apply01 — completed once; readback reconciled\n\n"
        + "Saved plan SHA256: " + APPROVED + "\n\n"
        + "Original controller PID21112 / Terraform PID30788. Apply exit0; actual 2 added, 1 changed, 0 removed. Never replay.\n\n"
        + "Current API policy equals the exact saved candidate structurally (ARM export decoding only); actual21 advertised aliases.\n"
        + "Independent substantive review verified eight-route addition, five-Claude MI audience/client, exact fast-speed branch and response normalization; not formatting-only.\n\n"
        + "Full protected pre/post snapshots match except exact policy and two backend additions. All four settings maps, runtime images/configuration, identities/roles/network, ingestion, Foundry deployments, subscriptions, existing backends, global/legacy/native policies and detached fragment remain unchanged.\n\n"
        + "Original final strict guard stopped on Azure-returned title:null. Original failure and source hash are preserved. Additive GET-only reconciliation requires exact planned backend properties plus only title:null and hashes equal the original full postapply capture. No retry, reapply or cloud write occurred.\n\n"
        + "State owner/lineage unchanged; actual serial " + str(state["serial"]) + ". No state edits/import/force-unlock.\n\n"
        + "No inference, build, runtime/settings/permissions/roles/network changes or Auto activation. This proves configuration readback, not inference acceptance.\n\n"
        + "Evidence: apply-result.json, original failure-164636210276.json, backend-readonly-reconciliation.json, verified.json, protected snapshots and independent-review.json.\n").encode())
    print(json.dumps(verification), flush=True)
    return 0


class OfflineTests(unittest.TestCase):
    def policies(self):
        return ((PLAN_HOME / "preplan-policy.xml").read_bytes().decode(),
                (reader.HOME / "candidate-policy.xml").read_bytes().decode())

    def test_exact_saved_plan_sources_state_validation_and_semantics(self):
        self.assertEqual(bound()["policy_review"]["advertised_count"], 21)

    def test_format_only_rejected(self):
        previous, _ = self.policies()
        with self.assertRaises(RuntimeError):
            semantic_policy(previous, previous)

    def test_wrong_native_identity_rejected(self):
        previous, desired = self.policies()
        with self.assertRaises(RuntimeError):
            semantic_policy(previous, desired.replace('resource="https://ai.azure.com"', 'resource="https://wrong.example"'))

    def test_fast_branch_required(self):
        previous, desired = self.policies()
        with self.assertRaises(RuntimeError):
            semantic_policy(previous, desired.replace('converted["speed"] = "fast";', 'converted["speed"] = "standard";'))

    def test_wrong_policy_resource_rejected(self):
        plan = load(PLAN_HOME / "plan.json")
        for row in plan["resource_changes"]:
            if row["address"] == reader.POLICY:
                row["change"]["after"]["id"] += "/other"
        with self.assertRaises(RuntimeError):
            identities(plan)

    def test_projection_does_not_hide_runtime_changes(self):
        before = load(PLAN_HOME / "postplan-snapshot.json")
        changed = deepcopy(before)
        changed["baseline"]["active_policy_sha256"] = "expected-policy-delta"
        self.assertEqual(projected_snapshot(changed, before), before)
        changed["baseline"]["settings_hashes"]["api"] = "unapproved"
        self.assertNotEqual(projected_snapshot(changed, before), before)

    def test_exclusive_intent_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(globals(), EVIDENCE=Path(folder)):
            write("apply-intent.json", {"plan_sha256": APPROVED})
            with self.assertRaises(FileExistsError):
                write("apply-intent.json", {"plan_sha256": "wrong"})

    def test_sensitive_diagnostic_redaction(self):
        self.assertNotIn("do-not-emit", sanitized("Authorization=do-not-emit {{private-name}} Bearer do-not-emit"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("localcheck", "apply", "reconcile-readonly"))
    args = parser.parse_args()
    if args.action == "localcheck":
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OfflineTests))
        return 0 if result.wasSuccessful() else 1
    try:
        return reconcile_readonly() if args.action == "reconcile-readonly" else run()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[a-zA-Z0-9_:./\-]{1,160}", str(exc)) else "protected_detail_suppressed"
        failure = {"at": now(), "pid": os.getpid(), "status": "STOP_NO_MORE_WRITES_NO_REPLAY",
                   "error_type": type(exc).__name__, "reason": reason,
                   "apply_intent_exists": (EVIDENCE / "apply-intent.json").exists(), "plan_sha256": APPROVED}
        if EVIDENCE.exists():
            write("failure-" + reader.datetime.now(reader.UTC).strftime("%H%M%S%f") + ".json", failure)
        print(json.dumps(failure), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())