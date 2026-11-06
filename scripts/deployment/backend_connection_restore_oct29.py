"""Exclusive storage-only approval; no release, plan, apply or state-write path."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt

IP = "167.103.63.12"
PRIOR = {"167.103.66.93", "167.103.66.248", "167.103.65.36"}
RID = rt.RG + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex"
URL = "https://management.azure.com" + RID + "?api-version=2025-06-01"
PREFIX = "backend-connection-restoration-20261029-"


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save(folder, name, value):
    with (folder / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def load(folder, name):
    return json.loads((folder / name).read_text(encoding="utf-8"))


def markers():
    result = {}
    for base, directories, files in os.walk(rt.HOME):
        directories[:] = [d for d in directories if d not in {
            "node_modules", ".terraform", "context", "security-tools", "dataplane-sdk-tools", "__pycache__"
        } and not d.startswith(PREFIX)]
        for name in files:
            if "intent" in name and name.endswith(".json"):
                path = Path(base) / name
                result[path.relative_to(rt.ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def workers():
    # Command lines are inspected locally but never returned or persisted.
    code = r"""Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|terraform|bash|azmcp' } | ForEach-Object { @{ pid=$_.ProcessId; name=$_.Name; current_restore=([string]$_.CommandLine -match 'scripts.deployment.backend_connection_restore_oct29'); mutation_worker=([string]$_.CommandLine -match 'terraform.+(plan|apply)|scripts.deployment.+ (apply|plan|build|native|publish|reconcile)|storage account network-rule (add|remove)|inventory_recovery_backend') } } | ConvertTo-Json -Compress"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", code], env=rt.ENV,
                            capture_output=True, text=True, check=True, timeout=30)
    values = json.loads(result.stdout) if result.stdout.strip() else []
    return [values] if isinstance(values, dict) else values


def check_workers(folder, name):
    values = workers()
    save(folder, name, {"at_utc": now(), "workers": values})
    rt.require(not any(w["mutation_worker"] and not w["current_restore"] for w in values),
               "competing_mutation_worker_present")
    rt.require(sum(w["current_restore"] for w in values) <= 1, "duplicate_restore_worker")
    return values


def token(resource):
    value = rt.cli(["account", "get-access-token", "--subscription", rt.SUB, "--resource", resource])
    text = value["accessToken"]
    part = text.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    rt.require(claims.get("tid") == rt.TENANT and claims.get("oid") == rt.OPERATOR, "token_identity")
    return text


def arm_read():
    request = Request(URL, headers={"Authorization": "Bearer " + token("https://management.azure.com/")})
    with urlopen(request, context=ssl.create_default_context(cafile=rt.CA), timeout=90) as response:
        value = json.load(response)
        return {"at_utc": now(), "http_status": response.status,
                "etag_header": response.headers.get("ETag"), "etag_body": value.get("etag"),
                "request_id": response.headers.get("x-ms-request-id"), "account": value}


def validate_before(account):
    rt.require(account["id"].lower() == RID.lower(), "storage_scope")
    props = account["properties"]
    acl = props["networkAcls"]
    rt.require(props["provisioningState"] == "Succeeded", "storage_not_quiescent")
    rt.require(acl["defaultAction"] == "Deny", "default_deny_required")
    rt.require(PRIOR <= {x["value"] for x in acl["ipRules"] if x["action"] == "Allow"}, "prior_rules_missing")
    matches = [x for x in acl["ipRules"] if x["value"] == IP]
    rt.require(not matches or matches == [{"value": IP, "action": "Allow"}], "approved_rule_ambiguous")
    return bool(matches)


def expected_account(before):
    value = deepcopy(before)
    if not validate_before(value):
        value["properties"]["networkAcls"]["ipRules"].append({"value": IP, "action": "Allow"})
    return value


def assert_only_approved(before, after):
    # Compare every returned account field, not just the named network controls.
    expected = expected_account(before)
    for value in (expected, after := deepcopy(after)):
        value.pop("etag", None)
        # ARM bookkeeping may advance on an account update; retain it in raw evidence.
        value.pop("systemData", None)
        value["properties"]["networkAcls"]["ipRules"].sort(key=lambda x: json.dumps(x, sort_keys=True))
    rt.require(expected == after, "unapproved_account_delta")
    return True


def prepare():
    folder = rt.HOME / (PREFIX + datetime.now(UTC).strftime("%H%M%S%fZ"))
    folder.mkdir(exist_ok=False)
    save(folder, "approval.json", {"recorded_at_utc": now(), "source": "explicit_user_message_2026-10-29",
         "resource_id": RID, "only_allowed_addition": {"value": IP, "action": "Allow"},
         "prior_ips_must_remain": sorted(PRIOR), "all_concurrent_rules_preserved": True,
         "no_other_acl_rbac_identity_infrastructure_or_release_change": True})
    check_workers(folder, "workers-before.json")
    save(folder, "retained-marker-hashes.json", markers())
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    save(folder, "account-context.json", {"subscription_id": account["id"], "tenant_id": account["tenantId"],
         "operator_oid": rt.OPERATOR, "token_identity_verified": True})
    before = arm_read()
    validate_before(before["account"])
    save(folder, "arm-before.json", before)
    print(json.dumps({"status": "prepared_no_cloud_write", "evidence": folder.relative_to(rt.ROOT).as_posix(),
                      "etag_header": before["etag_header"], "etag_body": before["etag_body"],
                      "ip_rules": before["account"]["properties"]["networkAcls"]["ipRules"]}), flush=True)


def restore(folder):
    rt.require(not (folder / "write-intent.json").exists(), "existing_write_intent_never_replay")
    rt.require(markers() == load(folder, "retained-marker-hashes.json"), "retained_markers_changed")
    check_workers(folder, "workers-prewrite.json")
    original = load(folder, "arm-before.json")["account"]
    fresh = arm_read()
    save(folder, "arm-immediately-before.json", fresh)
    rt.require(original == fresh["account"], "concurrent_account_change_stop_without_write")
    present = validate_before(fresh["account"])
    save(folder, "write-intent.json", {"at_utc": now(), "single_ip": IP, "already_present": present,
         "method": "native_cli_single_ip_add", "etag_header": fresh["etag_header"], "etag_body": fresh["etag_body"],
         "concurrency": "fresh_full_comparison_then_cli_own_fresh_merge_no_atomic_etag_available",
         "no_automatic_retry": True})
    if not present:
        # CLI performs its own fresh account GET and merges only this single IP.
        # No cached ACL document, account update, broad rule, or default-action flag is passed.
        result = subprocess.run(rt.CLI + ["storage", "account", "network-rule", "add", "--subscription", rt.SUB,
            "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--account-name", "projpoctokenex",
            "--ip-address", IP, "--action", "Allow", "--only-show-errors", "--output", "none"],
            cwd=rt.ROOT, env=rt.ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        save(folder, "write-result.json", {"at_utc": now(), "exit_code": result.returncode,
             "stdout_sha256": digest(result.stdout), "stderr_sha256": digest(result.stderr),
             "error_categories": categories(result.stdout + result.stderr), "attempts": 1})
        rt.require(result.returncode == 0, "single_ip_cli_failed_inspect_readback_no_retry")
    else:
        save(folder, "write-result.json", {"at_utc": now(), "exit_code": 0, "attempts": 0, "already_present": True})
    print(json.dumps({"status": "single_ip_operation_completed_requires_independent_verify", "ip": IP}), flush=True)


def categories(text):
    return sorted(set(re.findall(r"AuthorizationFailure|AuthorizationFailed|ForbiddenByRbac|ForbiddenByFirewall|AADSTS\d+|CERTIFICATE_VERIFY_FAILED", text)))


def blob_head():
    request = Request("https://projpoctokenex.blob.core.windows.net/tfstate/poc-ids-token-ex/main.tfstate",
        method="HEAD", headers={"Authorization": "Bearer " + token("https://storage.azure.com/"),
                                "x-ms-version": "2023-11-03"})
    with urlopen(request, context=ssl.create_default_context(cafile=rt.CA), timeout=90) as response:
        return {"at_utc": now(), "status": response.status, "etag": response.headers.get("ETag"),
                "content_length": response.headers.get("Content-Length"),
                "lease_status": response.headers.get("x-ms-lease-status"),
                "lease_state": response.headers.get("x-ms-lease-state"),
                "last_modified": response.headers.get("Last-Modified"),
                "request_id": response.headers.get("x-ms-request-id")}


def verify(folder):
    rt.require(load(folder, "write-result.json")["exit_code"] == 0, "write_result_unverified")
    check_workers(folder, "workers-verify.json")
    before = load(folder, "arm-immediately-before.json")["account"]
    after = arm_read()
    save(folder, "arm-independent-readback.json", after)
    assert_only_approved(before, after["account"])
    # Separate native CLI read verifies management-plane transport/model agreement.
    cli_account = rt.cli(["storage", "account", "show", "--subscription", rt.SUB,
        "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--name", "projpoctokenex"])
    rules = cli_account["networkRuleSet"]
    arm_rules = after["account"]["properties"]["networkAcls"]
    rt.require(sorted((x["ipAddressOrRange"], x["action"]) for x in rules["ipRules"]) ==
               sorted((x["value"], x["action"]) for x in arm_rules["ipRules"]), "cli_arm_ip_mismatch")
    rt.require(rules["defaultAction"] == arm_rules["defaultAction"] and rules["bypass"] == arm_rules["bypass"], "cli_arm_acl_mismatch")
    save(folder, "network-verification.json", {"at_utc": now(), "all_account_configuration_equal_except_single_ip": True,
         "arm_and_native_cli_agree": True, "ip_rules": arm_rules["ipRules"],
         "etag_available": bool(after["etag_header"] or after["etag_body"]),
         "atomic_concurrency_guarantee": False, "concurrent_change_observed": False,
         "default_action": arm_rules["defaultAction"], "bypass": arm_rules["bypass"],
         "public_network_access": after["account"]["properties"].get("publicNetworkAccess"),
         "allow_shared_key_access": after["account"]["properties"].get("allowSharedKeyAccess"),
         "ipv6_vnet_resource_access_and_all_other_settings_unchanged": True})
    exists = rt.cli(["storage", "container", "exists", "--subscription", rt.SUB,
                    "--account-name", "projpoctokenex", "--name", "tfstate", "--auth-mode", "login"])
    rt.require(exists.get("exists") is True, "entra_container_probe_failed")
    save(folder, "entra-container-probe.json", {"at_utc": now(), "exists": True, "auth_mode": "login_entra", "exit_code": 0})
    head = blob_head()
    save(folder, "blob-metadata-before-init.json", head)
    rt.require(head["lease_status"] == "unlocked" and head["lease_state"] == "available", "existing_state_lease_held_no_break")
    root = folder / "isolated-init"
    root.mkdir(exist_ok=False)
    (root / "main.tf").write_text('terraform {\n  backend "azurerm" {}\n}\n', encoding="utf-8")
    for name in ("backend.hcl", ".terraform.lock.hcl"):
        shutil.copyfile(rt.ROOT / "infra/terraform" / name, root / name)
    lock_hash = hashlib.sha256((root / ".terraform.lock.hcl").read_bytes()).hexdigest()
    env = {k: v for k, v in rt.ENV.items() if not k.startswith("TF_CLI_ARGS") and k not in {
        "ARM_ACCESS_KEY", "ARM_SAS_TOKEN", "ARM_CLIENT_SECRET", "ARM_OIDC_TOKEN", "TF_DATA_DIR"}}
    env.update({"TF_WORKSPACE": "default", "TF_IN_AUTOMATION": "1", "TF_INPUT": "0", "TF_DATA_DIR": str(root / ".terraform")})
    save(folder, "isolated-init-intent.json", {"at_utc": now(), "workspace": "default", "no_migration_no_reconfigure": True,
         "source_lock_sha256": lock_hash, "backend_hcl_sha256": hashlib.sha256((root / "backend.hcl").read_bytes()).hexdigest()})
    result = subprocess.run([rt.TF, "-chdir=" + str(root), "init", "-input=false", "-lockfile=readonly", "-no-color",
        "-backend-config=" + str(root / "backend.hcl")], cwd=rt.ROOT, env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=240)
    text = result.stdout + result.stderr
    save(folder, "isolated-init-result.json", {"at_utc": now(), "exit_code": result.returncode, "workspace": "default",
         "error_categories": categories(text), "output_sha256": digest(text),
         "request_ids": re.findall(r"RequestId:([a-fA-F0-9-]+)", text),
         "azure_error_timestamps": re.findall(r"Time:([^\r\n]+)", text),
         "backend_initialized": 'Successfully configured the backend "azurerm"' in text,
         "raw_output_not_saved_or_printed": True})
    rt.require(result.returncode == 0, "isolated_init_failed_no_retry")
    rt.require(hashlib.sha256((root / ".terraform.lock.hcl").read_bytes()).hexdigest() == lock_hash, "provider_lock_changed")
    head_after = blob_head()
    save(folder, "blob-metadata-after-init.json", head_after)
    rt.require(all(head[k] == head_after[k] for k in ("etag", "content_length", "lease_status", "lease_state", "last_modified")), "remote_blob_metadata_changed")
    final = arm_read()
    save(folder, "arm-final.json", final)
    assert_only_approved(before, final["account"])
    rt.require(markers() == load(folder, "retained-marker-hashes.json"), "historical_markers_changed")
    final_workers = check_workers(folder, "workers-final.json")
    report = {"at_utc": now(), "status": "backend_ready", "evidence": folder.relative_to(rt.ROOT).as_posix(),
         "approved_ip": IP, "allowed_ips": sorted(x["value"] for x in arm_rules["ipRules"]),
         "cloud_configuration_writes": load(folder, "write-result.json")["attempts"],
         "only_storage_single_ip_changed": True, "default_deny_preserved": True,
         "all_other_account_settings_preserved": True, "entra_container_probe": True, "state_blob_head": 200,
         "isolated_terraform_init_exit": result.returncode, "workspace": "default", "provider_lock_unchanged": True,
         "remote_state_etag_length_lastmodified_lease_unchanged": True, "retained_intents_unchanged": True,
         "other_mutation_workers": sum(w["mutation_worker"] and not w["current_restore"] for w in final_workers),
         "builds": 0, "pushes": 0, "plans": 0, "applies": 0, "state_writes": 0,
         "state_body_printed_or_saved": False, "roles_identities_or_other_acl_changes": 0,
         "live_application_fixed": False}
    save(folder, "result.json", report)
    print(json.dumps(report), flush=True)


def audit(folder):
    """Offline final audit only: never initializes Terraform or calls Azure."""
    report = load(folder, "result.json")
    rt.require(report["status"] == "backend_ready", "ready_result_required")
    before = load(folder, "arm-immediately-before.json")["account"]
    for name in ("arm-independent-readback.json", "arm-final.json"):
        assert_only_approved(before, load(folder, name)["account"])
    retained = load(folder, "retained-marker-hashes.json")
    rt.require(markers() == retained, "retained_marker_integrity")
    root = folder / "isolated-init"
    cache = json.loads((root / ".terraform/terraform.tfstate").read_text(encoding="utf-8"))
    config = cache["backend"]["config"]
    rt.require(cache["backend"]["type"] == "azurerm", "existing_backend_type")
    for key, value in {"storage_account_name": "projpoctokenex", "container_name": "tfstate",
                       "key": "poc-ids-token-ex/main.tfstate", "subscription_id": rt.SUB,
                       "tenant_id": rt.TENANT, "use_cli": True, "use_azuread_auth": True}.items():
        rt.require(config.get(key) == value, "isolated_backend_config_mismatch_" + key)
    rt.require(not cache.get("resources") and not cache.get("outputs"), "unexpected_cached_state_payload")
    source_lock = rt.ROOT / "infra/terraform/.terraform.lock.hcl"
    rt.require(source_lock.read_bytes() == (root / ".terraform.lock.hcl").read_bytes(), "original_provider_lock_mismatch")
    suites = list(ET.parse(folder / "guard-tests.xml").getroot().iter("testsuite"))
    rt.require(suites and all(int(s.get("errors", 0)) == int(s.get("failures", 0)) == 0 for s in suites), "offline_tests_failed")
    current = check_workers(folder, "workers-postcompletion-audit.json")
    proof = {"at_utc": now(), "status": "backend_ready_offline_audit_passed", "cloud_calls_this_audit": 0,
             "retained_intent_count": len(retained), "retained_intents_unchanged": True,
             "whole_account_readbacks_match_exact_approved_delta": True,
             "original_and_copied_provider_locks_equal": True,
             "isolated_cached_backend_exact_cli_entra_config": True, "state_payload_in_cache": False,
             "tests_passed": sum(int(s.get("tests", 0)) for s in suites),
             "current_workers": current, "no_release_or_historical_backend_replay": True}
    save(folder, "offline-final-audit.json", proof)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    hashes["source_module"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    hashes["source_tests"] = hashlib.sha256((rt.ROOT / "tests/unit/test_backend_connection_restore_oct29.py").read_bytes()).hexdigest()
    save(folder, "evidence-sha256.json", hashes)
    print(json.dumps(proof), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "restore", "verify", "audit"))
    parser.add_argument("folder", nargs="?")
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
        return
    folder = Path(args.folder).resolve()
    rt.require(folder.parent == rt.HOME and folder.name.startswith(PREFIX), "exclusive_evidence_scope")
    try:
        {"restore": restore, "verify": verify, "audit": audit}[args.stage](folder)
    except Exception as error:
        report = {"at_utc": now(), "stage": args.stage, "status": "blocked_no_automatic_retry",
                  "error_type": type(error).__name__, "http_status": getattr(error, "code", None)}
        if isinstance(error, RuntimeError):
            report["guard"] = str(error)
        if isinstance(error, HTTPError):
            report["request_id"] = error.headers.get("x-ms-request-id")
            report["service_error_code"] = error.headers.get("x-ms-error-code")
        save(folder, args.stage + "-blocked.json", report)
        print(json.dumps(report), flush=True)
        raise SystemExit(2)


if __name__ == "__main__":
    main()