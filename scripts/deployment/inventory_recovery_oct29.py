"""Fresh metadata-only recovery, never a historical release entrypoint.

Preparation is GET-only (appsettings/list is a documented read). The candidate
inherits the exact deployed immutable image; no dirty workspace API/UI/Auto
source can enter it. This module deliberately has no apply entrypoint.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import fnmatch
import json
from pathlib import Path
import re
import ssl
import subprocess
import sys
from urllib.request import Request, urlopen

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import poc_activation_release as activation
from scripts.deployment import poc_publisher_recheck_oct29 as reads
from scripts.deployment.glm_apim_secret import NAME, metadata, internal_ready
from scripts.deployment.project_route_product_access import sha

PRIOR = rt.HOME / "admin-showback-release-20261028"
BASE = PRIOR / "build-api/context"
FOUNDRY = "gateway/catalog/foundry-inventory-20261026.json"
EXTERNAL = "gateway/catalog/external-inventory.json"
PINS = {
    "api": "b489df53815f0d0242eda4c28b2c471bca2ce53344abc6733220c67c87bc0e09",
    "admin": "2846f1ff04244f20cb6612cca62c348b6a79a2fff7245dfc609347564becbfe5",
    "customer": "a30d513ce0dd7c529491689a49ce311f7794f4785e1dd5c5577ae62da9f1b975",
    "ingestion": "fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90",
}
IMAGE = "pocidstokenexacr.azurecr.io/aiflux-api@sha256:" + PINS["api"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(folder, name, data):
    reads.save(folder, name, data)


def retained_sources():
    manifest = load(PRIOR / "sources.json")
    rt.require(fs.sha(manifest["entries"]) == manifest["sha256"], "retained_manifest_integrity")
    for entry in manifest["entries"]:
        path = BASE / entry["path"]
        rt.require(path.resolve().is_relative_to(BASE.resolve()) and not path.is_symlink()
                   and sha(path.read_bytes()) == entry["sha256"], "retained_source_integrity")
    built = load(PRIOR / "api-build.json")
    rt.require(built["image"] == IMAGE and built["source_sha256"] == manifest["sha256"], "retained_image_binding")
    rt.require(not any((BASE / "services/control-plane/src/aiflux" / name).exists()
                       for name in ("decision_auth.py", "decision_router.py", "decision_client.py")), "auto_excluded")
    return manifest, built


def renew_foundry(old, live, observed_at):
    """Only a complete successful joined ARM read can renew the old timestamp."""
    from aiflux.foundry_inventory import FoundryInventory
    FoundryInventory.model_validate(old)
    rt.require(live["account"]["id"].lower() == old["account_resource_id"].lower()
               and live["project"]["id"].lower() == old["project_resource_id"].lower()
               and all(live[k]["properties"]["provisioningState"] == "Succeeded" for k in ("account", "project")),
               "matching_successful_parent_required")
    rt.require(live["connections"]["value"] == [] and not live["connections"].get("nextLink")
               and not live["deployments"].get("nextLink"), "complete_unconnected_scope_required")
    rows = live["deployments"]["value"]
    by_name = {d["name"]: d for d in rows}
    rt.require(len(rows) == len(by_name) == len(old["deployments"]) == 13
               and set(by_name) == {d["name"] for d in old["deployments"]}, "exact_deployment_membership")
    for saved in old["deployments"]:
        item = by_name[saved["name"]]
        props = item["properties"]
        rt.require(item["id"].lower() == saved["id"].lower()
                   and props["model"] == {"name": saved["model_name"], "version": saved["model_version"], "format": saved["model_format"]}
                   and props["provisioningState"] == saved["provisioning_state"] == "Succeeded"
                   and props.get("deploymentState") == saved.get("deployment_state")
                   and item["sku"]["capacity"] == saved["capacity"]
                   and (not saved.get("sku") or item["sku"]["name"] == saved["sku"])
                   and (not saved["chat_completion"] or str(props.get("capabilities", {}).get("chatCompletion")).lower() == "true"),
                   "deployment_contract_changed:" + saved["name"])
    observed = datetime.fromisoformat(observed_at)
    rt.require(observed.tzinfo is not None and timedelta(0) <= datetime.now(UTC) - observed < timedelta(hours=2), "fresh_observation_required")
    result = deepcopy(old)
    result["verified_at"] = observed_at
    FoundryInventory.model_validate(result)
    return result


def renew_external(old, policy, backend, reference, observed_at):
    from aiflux.external_inventory import ExternalInventory, historical_acceptance_sha256
    parsed = ExternalInventory.model_validate(old)
    rt.require(len(parsed.routes) == 1 and internal_ready(reference), "exact_external_reference_required")
    previous = old["routes"][0]["metadata_renewal"]
    rt.require(previous["policy_sha256"] == sha(policy)
               and previous["backend_sha256"] == sha(json.dumps(backend, sort_keys=True))
               and previous["historical_acceptance_sha256"] == historical_acceptance_sha256(parsed.routes[0]),
               "unchanged_external_route_backend_acceptance_required")
    result = deepcopy(old)
    renewal = result["routes"][0]["metadata_renewal"]
    renewal.update(observed_at=observed_at, reference_metadata_sha256=sha(json.dumps(reference, sort_keys=True)))
    rt.require(renewal["fresh_credential_health_verified"] is False and renewal["smoke_repeated"] is False,
               "never_claim_fresh_inference")
    ExternalInventory.model_validate(result)
    return result


def install_read_transport():
    """Cache one operator token, strict TLS and bounded GETs; no raw errors."""
    rt.CLI = ["C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"]
    original = rt.cli
    cache = {}
    tls = ssl.create_default_context(cafile=rt.CA)

    def cli(args):
        if args[:2] == ["account", "get-access-token"]:
            key = tuple(args)
            if key not in cache:
                cache[key] = original(args)
            return cache[key]
        if args[:3] == ["rest", "--method", "get"]:
            url = args[args.index("--url") + 1]
            rt.require(url.startswith("https://management.azure.com/subscriptions/" + rt.SUB + "/")
                       or url.startswith("https://management.azure.com/providers/Microsoft.Authorization/roleDefinitions/"), "read_scope")
            token = cli(["account", "get-access-token", "--subscription", rt.SUB, "--resource", "https://management.azure.com/"])["accessToken"]
            with urlopen(Request(url, headers={"Authorization": "Bearer " + token}), context=tls, timeout=90) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                rt.require(len(body) <= 8 * 1024 * 1024, "bounded_metadata_response")
                return json.loads(body)
        allowed = args[:2] == ["account", "show"] or args[:3] == ["role", "assignment", "list"] or args[:3] in (
            ["acr", "task", "show-run"], ["acr", "manifest", "show-metadata"])
        rt.require(allowed, "preflight_nonread_cli_rejected")
        return original(args)

    rt.cli = cli
    activation.ProductRun = reads.ReadOnlyProductRun
    return cli


def role_coverage(assignments, principal, account_id):
    required = ("Microsoft.CognitiveServices/accounts/read", "Microsoft.CognitiveServices/accounts/projects/read",
                "Microsoft.CognitiveServices/accounts/projects/connections/read", "Microsoft.CognitiveServices/accounts/deployments/read")
    relevant = [a for a in assignments if a.get("principalId", "").lower() == principal.lower()
                and not a.get("condition") and (account_id.lower() == a["scope"].lower()
                or account_id.lower().startswith(a["scope"].lower().rstrip("/") + "/"))]
    grants = []
    for assignment in relevant:
        rid = assignment["roleDefinitionId"]
        definition = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + rid + "?api-version=2022-04-01"])
        grants.extend(definition["properties"]["permissions"])
    covered = {action: any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("actions", []))
                    and not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get("notActions", [])) for g in grants) for action in required}
    return {"direct_unconditional_assignment_count": len(relevant), "actions": covered,
            "all_required_direct_actions_covered": all(covered.values()), "runtime_identity_live_read_proven": False,
            "group_membership_and_deny_assignments_evaluated": False,
            "automatic_refresh_authorized": False}


def prepare(folder):
    rt.require(folder.parent == rt.HOME and folder.name.startswith("inventory-recovery-20261029-"), "fresh_recovery_scope")
    rt.require(not folder.exists(), "existing_recovery_reconcile_only")
    fs.protect(folder)
    report = {"started_at_utc": datetime.now(UTC).isoformat(), "status": "blocked", "stage": "local_reconciliation",
              "configuration_writes": 0, "inference_requests": 0, "permission_changes": 0, "network_changes": 0,
              "historical_entrypoint_replays": 0, "ttl_seconds": 86400, "auto_source_included": False}
    try:
        workers = subprocess.run(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|terraform|bash' } | ForEach-Object { @{ pid=$_.ProcessId; name=$_.Name; conflict=([string]$_.CommandLine -match 'terraform.+(plan|apply)|scripts.deployment.+ (apply|plan|build|native|publish|reconcile)') } } | ConvertTo-Json -Compress"],
            capture_output=True, text=True, env=rt.ENV, check=True)
        observed_workers = json.loads(workers.stdout) if workers.stdout.strip() else []
        if isinstance(observed_workers, dict):
            observed_workers = [observed_workers]
        write(folder, "workers-before.json", observed_workers)
        rt.require(not any(w["conflict"] for w in observed_workers), "conflicting_worker_reconcile_required")
        markers = {p.relative_to(rt.ROOT).as_posix(): sha(p.read_bytes()) for p in rt.HOME.rglob("*intent*.json") if p.is_file()}
        write(folder, "retained-intent-hashes.json", markers)
        manifest, built = retained_sources()
        write(folder, "retained-source-binding.json", {"manifest_sha256": manifest["sha256"], "build": built})
        report["stage"] = "account_and_live_image"
        install_read_transport()
        account = rt.cli(["account", "show"])
        rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
        run = reads.ReadOnlyProductRun()
        site_id = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api"
        site = rt.arm(site_id)
        web = rt.arm(site_id + "/config/web")["properties"]
        settings = fs.current_settings()
        allowed = {"AIFLUX_FOUNDRY_INVENTORY_PATH", "AIFLUX_EXTERNAL_INVENTORY_PATH", "AIFLUX_FOUNDRY_INVENTORY_MAX_AGE_SECONDS",
                   "AIFLUX_FOUNDRY_PROJECT_ENDPOINT", "AIFLUX_FOUNDRY_PROJECT_RESOURCE_ID", "AIFLUX_CATALOG_PATH", "AIFLUX_CATALOG_CONFIGURED"}
        safe = {k: v for k, v in settings["api"].items() if k in allowed}
        write(folder, "live-inventory-config.json", safe)
        rt.require(web["linuxFxVersion"] == "DOCKER|" + IMAGE, "unexpected_current_api_image")
        docker = (BASE / "services/control-plane/Dockerfile").read_text(encoding="utf-8")
        rt.require("AIFLUX_FOUNDRY_INVENTORY_MAX_AGE_SECONDS=86400" in docker
                   and settings["api"].get("AIFLUX_FOUNDRY_INVENTORY_MAX_AGE_SECONDS", "86400") == "86400", "ttl_must_remain_86400")
        for key, value in (("AIFLUX_FOUNDRY_INVENTORY_PATH", "/app/" + FOUNDRY), ("AIFLUX_EXTERNAL_INVENTORY_PATH", "/app/" + EXTERNAL)):
            rt.require(settings["api"].get(key, value) == value, "inventory_path_override")
        remote = rt.cli(["acr", "task", "show-run", "-r", "pocidstokenexacr", "--run-id", built["run_id"], "--subscription", rt.SUB])
        rt.require(remote["status"] == "Succeeded" and remote["finishTime"] == built["finished_at"]
                   and remote["outputImages"] == [{"digest": built["digest"], "registry": "pocidstokenexacr.azurecr.io", "repository": "aiflux-api", "tag": built["tag"]}], "deployed_build_provenance")
        report["stage"] = "complete_current_protected_baseline"
        before_exports = reads.exports(run, folder, "before")
        before = activation.snapshot()
        write(folder, "baseline.json", before)
        rt.require(all(before["runtime"]["sites"][k]["image"].endswith("@sha256:" + v) for k, v in PINS.items()), "current_all_four_pins")
        report["stage"] = "fresh_foundry_metadata"
        old = load(BASE / FOUNDRY)
        rt.require(settings["api"].get("AIFLUX_FOUNDRY_PROJECT_ENDPOINT", old["project_endpoint"]) == old["project_endpoint"]
                   and settings["api"].get("AIFLUX_FOUNDRY_PROJECT_RESOURCE_ID", old["project_resource_id"]).lower() == old["project_resource_id"].lower(), "live_project_config_mismatch")
        live = {}
        for kind, suffix in (("account", ""), ("project", "/projects/poc-ids-token-ex-foundry-project"),
                             ("connections", "/projects/poc-ids-token-ex-foundry-project/connections"), ("deployments", "/deployments")):
            live[kind] = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + old["account_resource_id"] + suffix + "?api-version=2025-06-01"])
        write(folder, "foundry-live-metadata.json", live)
        at = datetime.now(UTC).isoformat()
        renewed = renew_foundry(old, live, at)
        report["stage"] = "external_route_readback"
        policy = run.policy()
        backends = run.arm("/backends")
        rt.require(not backends.get("nextLink"), "complete_backend_collection")
        external_backend = [b for b in backends["value"] if "glm" in b["name"].lower()]
        rt.require(len(external_backend) == 1, "unique_external_backend")
        reference = metadata(run.arm("/namedValues/" + NAME))
        write(folder, "external-reference-metadata.json", reference)
        write(folder, "external-backend.json", external_backend[0])
        external = renew_external(load(BASE / EXTERNAL), policy, external_backend[0], reference, at)
        report["stage"] = "existing_api_identity_read_coverage"
        identities = site["identity"].get("userAssignedIdentities", {})
        selected = settings["api"].get("AZURE_CLIENT_ID")
        matching = [v for v in identities.values() if v.get("clientId") == selected]
        rt.require(len(matching) == 1, "exact_runtime_api_identity_required")
        assignments = rt.cli(["role", "assignment", "list", "--scope", old["account_resource_id"], "--include-inherited", "--subscription", rt.SUB])
        coverage = role_coverage(assignments, matching[0]["principalId"], old["account_resource_id"])
        write(folder, "api-mi-arm-read-coverage.json", coverage)
        report["runtime_automatic_refresh"] = "not_enabled_existing_runtime_read_not_proven"
        report["api_mi_direct_arm_read_actions_covered"] = coverage["all_required_direct_actions_covered"]
        report["stage"] = "stable_route_and_fragment_binding"
        after_exports = reads.exports(run, folder, "after")
        rt.require(before_exports == after_exports and after_exports["detached"] and after_exports["policy_include_count"] == 0
                   and before["active_policy_sha256"] == sha(policy) == after_exports["policy_xml_sha256"]
                   and before["fragment_xml_sha256"] == after_exports["fragment_rawxml_sha256"], "route_or_fragment_changed")
        # Candidate is image-derived, not rebuilt from any dirty current source.
        context = folder / "context"
        (context / "gateway/catalog").mkdir(parents=True)
        write(context / "gateway/catalog", Path(FOUNDRY).name, renewed)
        write(context / "gateway/catalog", Path(EXTERNAL).name, external)
        candidate = ("FROM " + IMAGE + "\n"
                     "COPY --chown=10001:10001 gateway/catalog/foundry-inventory-20261026.json /app/gateway/catalog/foundry-inventory-20261026.json\n"
                     "COPY --chown=10001:10001 gateway/catalog/external-inventory.json /app/gateway/catalog/external-inventory.json\n")
        (context / "InventoryRecovery.Dockerfile").write_text(candidate, encoding="utf-8")
        write(folder, "package-manifest.json", {"base_image": IMAGE, "retained_sources_sha256": manifest["sha256"],
            "observed_at_utc": at, "entries": [{"path": p.relative_to(context).as_posix(), "sha256": sha(p.read_bytes())}
                                                for p in sorted(context.rglob("*")) if p.is_file()],
            "source_changes": [], "foundry_delta": ["verified_at"],
            "external_delta": ["routes[0].metadata_renewal.observed_at", "routes[0].metadata_renewal.reference_metadata_sha256"],
            "new_inference_or_credential_health_proof": False, "auto_excluded": True})
        stamp = datetime.fromisoformat(old["verified_at"])
        report.update(status="verified_metadata_package_prepared_not_deployed", stage="prepared", observed_at_utc=at,
            existing_verified_at_utc=old["verified_at"], expired_at_utc=(stamp + timedelta(seconds=86400)).isoformat(),
            existing_age_seconds=(datetime.now(UTC) - stamp).total_seconds(),
            current_images={k: v["image"] for k, v in before["runtime"]["sites"].items()},
            accepted_explicit_route_count=len(renewed["routes"]) + 1,
            deployed_file_proof="Retained source hashes bound to exact live image and successful ACR build; container filesystem attestation pending native no-push",
            sustainable_refresh_blocker="Runtime MI ARM read is not proven; no permission grant or automatic refresh introduced")
    except Exception as exc:
        report.update(error_type=type(exc).__name__, http_status=getattr(exc, "code", None),
                      safe_error=str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[a-zA-Z0-9_:.-]+", str(exc)) else "details_suppressed")
    finally:
        report["finished_at_utc"] = datetime.now(UTC).isoformat()
        write(folder, "result.json", report)
        print(json.dumps({"evidence_directory": folder.relative_to(rt.ROOT).as_posix(), **report}), flush=True)
    return 0 if report["status"] == "verified_metadata_package_prepared_not_deployed" else 2


def complete_retained(folder):
    """New exclusive continuation; original failed collector evidence is immutable."""
    rt.require(folder.parent == rt.HOME and folder.name.startswith("inventory-recovery-20261029-"), "fresh_recovery_scope")
    prior = load(folder / "result.json")
    rt.require(prior["stage"] == "existing_api_identity_read_coverage" and prior["status"] == "blocked"
               and not (folder / "complete-intent.json").exists(), "only_exact_unattempted_continuation")
    write(folder, "complete-intent.json", {"at_utc": datetime.now(UTC).isoformat(), "original_result_sha256": sha((folder / "result.json").read_bytes()), "cloud_writes": 0})
    report = {"status": "blocked", "stage": "retained_baseline_recheck", "configuration_writes": 0, "inference_requests": 0}
    try:
        manifest, built = retained_sources()
        install_read_transport()
        rt.require(rt.cli(["account", "show"])["id"] == rt.SUB, "account_scope")
        baseline = load(folder / "baseline.json")
        current = activation.snapshot()
        rt.require(current == baseline, "complete_current_baseline_changed")
        write(folder, "completion-protected-baseline.json", current)
        old = load(BASE / FOUNDRY)
        live = {}
        for kind, suffix in (("account", ""), ("project", "/projects/poc-ids-token-ex-foundry-project"),
                             ("connections", "/projects/poc-ids-token-ex-foundry-project/connections"), ("deployments", "/deployments")):
            live[kind] = rt.cli(["rest", "--method", "get", "--url", "https://management.azure.com" + old["account_resource_id"] + suffix + "?api-version=2025-06-01"])
        at = datetime.now(UTC).isoformat()
        write(folder, "completion-foundry-live-metadata.json", {"observed_at_utc": at, "metadata": live})
        renewed = renew_foundry(old, live, at)
        report["stage"] = "stable_external_and_routes"
        run = reads.ReadOnlyProductRun()
        policy = run.policy()
        rt.require(sha(policy) == baseline["active_policy_sha256"], "unchanged_active_routes")
        backends = run.arm("/backends")
        rt.require(not backends.get("nextLink"), "complete_backends")
        selected = [b for b in backends["value"] if "glm" in b["name"].lower()]
        rt.require(len(selected) == 1, "exact_external_backend")
        reference = metadata(run.arm("/namedValues/" + NAME))
        external = renew_external(load(BASE / EXTERNAL), policy, selected[0], reference, at)
        write(folder, "completion-external-reference-metadata.json", reference)
        identities = baseline["runtime"]["sites"]["api"]["protected"]["identity"]["userAssignedIdentities"]
        rt.require(len(identities) == 1, "exact_api_identity")
        principal = next(iter(identities.values()))["principalId"]
        assignments = [dict(principalId=a[1], roleDefinitionId=a[2], scope=a[3], condition=a[4])
                       for a in baseline["runtime"]["roleAssignments"]]
        coverage = role_coverage(assignments, principal, old["account_resource_id"])
        write(folder, "api-mi-arm-read-coverage.json", coverage)
        exports = reads.exports(run, folder, "completion")
        rt.require(exports["detached"] and exports["policy_include_count"] == 0
                   and exports["policy_xml_sha256"] == baseline["active_policy_sha256"]
                   and exports["fragment_rawxml_sha256"] == baseline["fragment_xml_sha256"]
                   and exports["fragment_properties_sha256"] == baseline["fragment_properties_sha256"], "unchanged_detached_fragment_and_policy")
        context = folder / "context"
        (context / "gateway/catalog").mkdir(parents=True, exist_ok=False)
        write(context / "gateway/catalog", Path(FOUNDRY).name, renewed)
        write(context / "gateway/catalog", Path(EXTERNAL).name, external)
        (context / "InventoryRecovery.Dockerfile").write_text(
            "FROM " + IMAGE + "\n"
            "COPY --chown=10001:10001 gateway/catalog/foundry-inventory-20261026.json /app/gateway/catalog/foundry-inventory-20261026.json\n"
            "COPY --chown=10001:10001 gateway/catalog/external-inventory.json /app/gateway/catalog/external-inventory.json\n", encoding="utf-8")
        package = {"base_image": IMAGE, "retained_sources_sha256": manifest["sha256"], "observed_at_utc": at,
                   "entries": [{"path": p.relative_to(context).as_posix(), "sha256": sha(p.read_bytes())} for p in sorted(context.rglob("*")) if p.is_file()],
                   "source_changes": [], "foundry_delta": ["verified_at"],
                   "external_delta": ["routes[0].metadata_renewal.observed_at", "routes[0].metadata_renewal.reference_metadata_sha256"],
                   "new_inference_or_credential_health_proof": False, "auto_excluded": True}
        write(folder, "package-manifest.json", package)
        stamp = datetime.fromisoformat(old["verified_at"])
        report.update(status="verified_metadata_package_prepared_not_deployed", stage="prepared", observed_at_utc=at,
            existing_verified_at_utc=old["verified_at"], expired_at_utc=(stamp + timedelta(seconds=86400)).isoformat(),
            existing_age_seconds=(datetime.now(UTC) - stamp).total_seconds(), ttl_seconds=86400,
            all_four_runtime_pins_reverified=True, complete_protected_baseline_unchanged=True,
            explicit_routes_preserved=13, auto_source_included=False, api_mi_arm_read_coverage=coverage,
            native_image_filesystem_attestation="pending", runtime_automatic_refresh="not_enabled_no_proven_runtime_read")
    except Exception as exc:
        report.update(error_type=type(exc).__name__, http_status=getattr(exc, "code", None),
                      safe_error=str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[a-zA-Z0-9_:.-]+", str(exc)) else "details_suppressed")
    report["finished_at_utc"] = datetime.now(UTC).isoformat()
    write(folder, "complete-result.json", report)
    print(json.dumps({"evidence_directory": folder.relative_to(rt.ROOT).as_posix(), **report}), flush=True)
    return 0 if report["status"] == "verified_metadata_package_prepared_not_deployed" else 2


if __name__ == "__main__":
    raise SystemExit(complete_retained(Path(sys.argv[2]).resolve()) if sys.argv[1] == "--complete-retained" else prepare(Path(sys.argv[1]).resolve()))