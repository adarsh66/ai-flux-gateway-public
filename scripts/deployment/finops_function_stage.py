"""Exact approved disabled-Function staging; never chooses an ingestion cutoff.

Separate from the image-only release guard. Produces a hash-bound saved Terraform
plan for four images and an explicit finite Function configuration map. The host
and timer remain disabled when the business/history boundary is unresolved.
No grants, replay, SQL, inference, resource creation or network writes exist here.
Sensitive settings and Terraform bodies stay in memory or an ACL-protected local
artifact directory; only hashes, names and immutable image pins are exported.
"""
from __future__ import annotations

import argparse
import copy
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import shutil

from scripts.deployment import finops_release as release
from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt

FUNCTION = 'azurerm_linux_function_app.ingestion[0]'
STAGE_NAME = "disabled-stage-preserved-config"
COMPUTED = {"possible_outbound_ip_address_list", "possible_outbound_ip_addresses",
            "outbound_ip_address_list", "outbound_ip_addresses", "custom_domain_verification_id"}
SETTING_NAMES = frozenset({"AIFLUX_ENVIRONMENT", "AIFLUX_DATABASE_URL", "AIFLUX_LOG_WORKSPACE_ID",
    "AIFLUX_APIM_RESOURCE_ID", "AIFLUX_APIM_PRODUCT_ID", "AIFLUX_CATALOG_PATH",
    "AIFLUX_CATALOG_CONFIGURED", "WEBSITES_ENABLE_APP_SERVICE_STORAGE", "AZURE_CLIENT_ID"})


def stamp():
    return datetime.now(UTC).isoformat()


def sha(value):
    return release.digest(json.dumps(value, sort_keys=True).encode())


def guard(plan, images, expected_settings, client_id):
    """No unknown writable fields; exact settings values, not just an allowlist."""
    rt.require(plan.get("applyable") is True and not plan.get("errored")
               and not plan.get("deferred_changes"), "unresolved_plan")
    rt.require(set(images) == set(release.COMPONENTS), "four_pins_required")
    for kind, image in images.items():
        rt.require(re.fullmatch(re.escape(release.REGISTRY + "/aiflux-" + kind + "@sha256:")
                               + "[a-f0-9]{64}", image), "immutable_pin")
    seen = set()
    for resource in plan.get("resource_changes", []):
        c = resource["change"]
        if c["actions"] == ["no-op"]:
            continue
        address = resource["address"]
        rt.require(resource.get("mode") == "managed" and address in release.ADDRESSES
                   and address not in seen and c["actions"] == ["update"], "out_of_scope_change")
        seen.add(address)
        before, after = copy.deepcopy(c["before"]), copy.deepcopy(c["after"])
        unknown = c.get("after_unknown") or {}
        rt.require(not any(release.any_unknown(v) for k, v in unknown.items() if k not in COMPUTED),
                   "unknown_writable_input")
        for key in COMPUTED:
            if release.any_unknown(unknown.get(key)):
                after[key] = before.get(key)
        kind = release.ADDRESSES[address]
        rt.require(len(before["site_config"]) == len(after["site_config"]) == 1, "site_config_shape")
        old, new = before["site_config"][0], after["site_config"][0]
        if address == FUNCTION:
            rt.require(before.get("enabled") is False and after.get("enabled") is False,
                       "host_must_remain_disabled_without_cutoff")
            provider_settings = {"AzureWebJobsStorage__accountName": before.get("storage_account_name"),
                                 "FUNCTIONS_EXTENSION_VERSION": before.get("functions_extension_version")}
            expected_hcl_settings = dict(expected_settings)
            for name, value in provider_settings.items():
                if name in expected_hcl_settings and name not in before.get("app_settings", {}):
                    rt.require(value and expected_hcl_settings[name] == value,
                               "provider_owned_function_setting_mismatch")
                    del expected_hcl_settings[name]
            rt.require(after["app_settings"] == expected_hcl_settings, "unexpected_function_settings")
            bsettings = before.get("app_settings") or {}
            changed = portals.changed(bsettings, expected_hcl_settings)
            rt.require(changed <= SETTING_NAMES, "unapproved_setting_name")
            rt.require(expected_settings.get("AzureWebJobs.ingest_usage.Disabled") == "true",
                       "timer_must_remain_disabled")
            rt.require(expected_settings.get("AIFLUX_INGESTION_START_AT") ==
                       bsettings.get("AIFLUX_INGESTION_START_AT"), "cutoff_must_be_preserved")
            after["app_settings"] = before["app_settings"]
            rt.require(new.get("container_registry_use_managed_identity") is True
                       and new.get("container_registry_managed_identity_client_id") == client_id,
                       "exact_acr_identity_required")
            for key in ("container_registry_use_managed_identity", "container_registry_managed_identity_client_id"):
                new[key] = old.get(key)
            rt.require(len(new["application_stack"]) == 1, "stack_shape")
            stack = new["application_stack"][0]
            rt.require(stack.get("python_version") in (None, ""), "native_stack_not_removed")
            docker = stack.get("docker") or []
            repo, pin = images[kind].split("@sha256:")
            rt.require(len(docker) == 1 and docker[0].get("registry_url") == "https://" + release.REGISTRY
                       and docker[0].get("image_name") == repo.split("/", 1)[1] + "@sha256"
                       and docker[0].get("image_tag") == pin
                       and docker[0].get("registry_username") in (None, "")
                       and docker[0].get("registry_password") in (None, ""), "wrong_function_container")
            new["application_stack"] = old["application_stack"]
        else:
            rt.require(len(new["application_stack"]) == len(old["application_stack"]) == 1, "stack_shape")
            stack = new["application_stack"][0]
            rt.require(stack.get("docker_registry_url") == "https://" + release.REGISTRY
                       and stack.get("docker_image_name") == images[kind].split("/", 1)[1], "wrong_app_image")
            stack["docker_image_name"] = old["application_stack"][0].get("docker_image_name")
        rt.require(before == after, "unapproved_configuration_change")
    rt.require(seen == set(release.ADDRESSES), "exact_four_updates_required")


def built(folder):
    manifest = json.loads((folder / "source-manifest.json").read_text())
    result = json.loads((folder / "results.json").read_text())
    rt.require(manifest == release.source_manifest(), "current_source_mismatch")
    rt.require(result.get("exit_code") == 0 and set(result["components"]) == set(release.COMPONENTS)
               and result["source_manifest_sha256"] == release.digest((folder / "source-manifest.json").read_bytes()),
               "completed_four_image_build_required")
    images = {}
    for kind in release.COMPONENTS:
        item = result["components"][kind]
        rt.require(item.get("status") == "Succeeded" and item.get("submissions") == 1,
                   "single_successful_build_required")
        run = rt.cli(["acr", "task", "show-run", "--registry", "pocidstokenexacr", "--subscription", rt.SUB,
                      "--run-id", item["run_id"]])
        meta = rt.cli(["acr", "manifest", "show-metadata", "--registry", "pocidstokenexacr", "--subscription", rt.SUB,
                       "--name", "aiflux-" + kind + ":" + result["tag"]])
        rt.require(run["status"] == "Succeeded" and run["finishTime"] == item["finished_at_utc"]
                   and item["image"] == release.REGISTRY + "/aiflux-" + kind + "@" + meta["digest"]
                   and any(x and x.get("digest") == meta["digest"] and x.get("repository") == "aiflux-" + kind
                           for x in run.get("outputImages") or []), "remote_build_binding")
        images[kind] = item["image"]
    return images


def current_settings():
    return {k: rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + k
                       + "/config/appsettings/list", "POST")["properties"] for k in release.COMPONENTS}


def configured(settings):
    """Derive only canonical non-secret settings; preserve the absent cutoff."""
    api, old = settings["api"], settings["ingestion"]
    rt.require(old.get("AzureWebJobs.ingest_usage.Disabled") == "true", "timer_not_disabled")
    rt.require(not old.get("AIFLUX_INGESTION_START_AT"), "unexpected_existing_cutoff_review_required")
    expected_api_db = ("postgresql://poc-ids-token-ex-api-identity@"
                       "poc-ids-token-ex-pg.postgres.database.azure.com:5432/turnstile?sslmode=require")
    rt.require(api.get("AIFLUX_DATABASE_URL") == expected_api_db, "canonical_database_required")
    rt.require(api.get("AIFLUX_APIM_PRODUCT_ID") == "aiflux"
               and api.get("AIFLUX_CATALOG_CONFIGURED") in {"true", "false"}, "canonical_api_source_required")
    apim = rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"
    rt.require(api.get("AIFLUX_APIM_RESOURCE_ID", "").lower() == apim.lower(), "canonical_apim_required")
    workspace = rt.cli(["monitor", "log-analytics", "workspace", "show", "--subscription", rt.SUB,
                        "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--workspace-name", "poc-ids-token-ex-logs"])
    rt.require(api.get("AIFLUX_LOG_WORKSPACE_ID") == workspace["customerId"], "canonical_workspace_required")
    client = old.get("AzureWebJobsStorage__clientId")
    rt.require(client and old.get("AZURE_CLIENT_ID") in (None, client)
               and old.get("AzureWebJobsStorage__credential") == "managedidentity", "host_storage_identity_required")
    for service in ("blob", "queue", "table"):
        rt.require(old.get("AzureWebJobsStorage__" + service + "ServiceUri") ==
                   "https://pocidstokenexfunc." + service + ".core.windows.net", "existing_host_storage_required")
    target = {**old, "AZURE_CLIENT_ID": client, "AIFLUX_ENVIRONMENT": "production",
              "AIFLUX_DATABASE_URL": expected_api_db.replace("-api-identity@", "-ingestion-identity@"),
              "AIFLUX_LOG_WORKSPACE_ID": workspace["customerId"], "AIFLUX_APIM_RESOURCE_ID": api["AIFLUX_APIM_RESOURCE_ID"],
              "AIFLUX_APIM_PRODUCT_ID": "aiflux",
              # Disabled staging is not catalog acceptance. Preserve the actual
              # API acceptance flag rather than turning a source build into proof.
              "AIFLUX_CATALOG_CONFIGURED": api["AIFLUX_CATALOG_CONFIGURED"],
              "AIFLUX_CATALOG_PATH": "/home/site/wwwroot/gateway/catalog/dev-models.json",
              "WEBSITES_ENABLE_APP_SERVICE_STORAGE": "false"}
    rt.require(portals.changed(old, target) <= SETTING_NAMES, "finite_settings_only")
    return target, client


def terraform(root, *args):
    return rt.run([rt.TF, "-chdir=" + str(root), *args])


def protect(folder):
    folder.mkdir(parents=True, exist_ok=True)
    sid = re.search(r"S-1-5-[0-9-]+", rt.run(["whoami", "/user", "/fo", "csv", "/nh"])).group(0)
    rt.run(["icacls", str(folder), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"])


def literal(value):
    if isinstance(value, dict):
        return {k: literal(v) for k, v in value.items()}
    if isinstance(value, str):
        return value.replace("${", "$${").replace("%{", "%%{")
    return value


def preserved_web_settings(settings):
    """Registry fields belong to application_stack, not provider app_settings.

    Only the existing exact registry URL and empty MI credentials may be omitted
    from generated HCL. Full ARM settings hashes still bind pre/post readback.
    """
    reserved = {"DOCKER_REGISTRY_SERVER_URL", "DOCKER_REGISTRY_SERVER_USERNAME",
                "DOCKER_REGISTRY_SERVER_PASSWORD"}
    result = {}
    for kind in ("api", "admin", "customer"):
        current = settings[kind]
        rt.require(current.get("DOCKER_REGISTRY_SERVER_URL") == "https://" + release.REGISTRY
                   and not current.get("DOCKER_REGISTRY_SERVER_USERNAME")
                   and not current.get("DOCKER_REGISTRY_SERVER_PASSWORD"), "existing_mi_registry_required")
        result[kind] = {k: v for k, v in current.items() if k not in reserved}
    return result


def archive_failed_preparation(stage):
    """Retain errored non-applyable plans; never archive reviewed/apply intent."""
    rt.require(not any((stage / name).exists() for name in
                       ("review.json", "apply-intent.json", "applied.json")),
               "existing_stage_do_not_overwrite")
    plan = stage / "disabled.tfplan"
    if plan.exists():
        parsed = json.loads(terraform(stage / "infra/terraform", "show", "-json", str(plan)))
        rt.require(parsed.get("errored") is True and parsed.get("applyable") is False,
                   "existing_stage_do_not_overwrite")
    stage.rename(stage.parent / ("disabled-stage-unplanned-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")))


def writable_block(value, schema):
    """Preserve known provider state inputs, excluding computed-only outputs."""
    result = {k: literal(value[k]) for k, spec in schema.get("attributes", {}).items()
              if (spec.get("optional") or spec.get("required")) and k in value
              and value[k] is not None and value[k] != ""}
    # The provider reads an unconfigured health-check eviction as zero, but
    # validates explicit input as 2..10. Omission retains that existing default.
    if result.get("health_check_eviction_time_in_min") == 0 and not value.get("health_check_path"):
        result.pop("health_check_eviction_time_in_min")
    for key, spec in schema.get("block_types", {}).items():
        if key in value:
            result[key] = [writable_block(item, spec["block"]) for item in value[key]]
    return result


def preserved_function(root, target, image, client):
    state = json.loads(terraform(root, "show", "-json"))
    resources = state["values"]["root_module"]["resources"]
    before = next(item["values"] for item in resources if item["address"] == FUNCTION)
    schema = json.loads(terraform(root, "providers", "schema", "-json"))
    block = schema["provider_schemas"]["registry.terraform.io/hashicorp/azurerm"]["resource_schemas"][
        "azurerm_linux_function_app"]["block"]["block_types"]["site_config"]["block"]
    config = writable_block(before["site_config"][0], block)
    repository, pin = image.split("@sha256:")
    config.update(container_registry_use_managed_identity=True,
                  container_registry_managed_identity_client_id=client,
                  application_stack=[{"docker": [{"registry_url": "https://" + release.REGISTRY,
                      "image_name": repository.split("/", 1)[1] + "@sha256", "image_tag": pin}]}])
    settings = dict(target)
    for name, field in {"AzureWebJobsStorage__accountName": "storage_account_name",
                        "FUNCTIONS_EXTENSION_VERSION": "functions_extension_version"}.items():
        rt.require(settings.get(name) == before.get(field), "provider_owned_function_setting_mismatch")
        settings.pop(name)
    return {"app_settings": literal(settings), "site_config": [config],
            "content_share_force_disabled": before["content_share_force_disabled"],
            "public_network_access_enabled": before["public_network_access_enabled"]}


def prepare(tag):
    rt.require(re.fullmatch(r"finops-[0-9]{8}t[0-9]{6}z", tag), "invalid_tag")
    folder = rt.HOME / "finops" / tag
    images = built(folder)
    stage = folder / STAGE_NAME
    if stage.exists() and any(stage.iterdir()):
        # Preserve failed preparation, but never regenerate a saved plan or
        # replay an apply. No production write is possible during preparation.
        archive_failed_preparation(stage)
    protect(stage)
    baseline = portals.baseline()
    rt.require(baseline["sites"]["ingestion"]["protected"]["enabled"] is False, "disabled_host_required")
    settings = current_settings()
    target, client = configured(settings)
    identities = baseline["sites"]["ingestion"]["protected"]["identity"]["userAssignedIdentities"]
    rt.require(len(identities) == 1 and next(iter(identities.values())).get("clientId") == client,
               "exact_existing_ingestion_identity_required")
    # These are generated, ACL-protected deployment artifacts, not shared source edits.
    root = stage / "infra/terraform"
    root.mkdir(parents=True)
    for path in (rt.ROOT / "infra/terraform").iterdir():
        if path.is_file() and (path.name.endswith((".tf", ".tf.json")) or path.name == ".terraform.lock.hcl"):
            shutil.copyfile(path, root / path.name)
    for name in ("infra/models", "gateway/policies"):
        shutil.copytree(rt.ROOT / name, stage / name)
    for path in (rt.ROOT / "gateway").glob("*.json"):
        shutil.copyfile(path, stage / "gateway" / path.name)
    # Preserve all web settings byte-for-byte; only the nine declared ingester
    # settings may change. The existing Terraform preconditions stay in force.
    # Terraform override files may replace existing locals but cannot introduce
    # a new local. Put that declaration in an ordinary generated configuration.
    rt.save(root / "finops_preserved.tf.json", {"locals": {
        "finops_preserved_web_settings": literal(preserved_web_settings(settings))}})
    variables = portals.runtime_variables({"results": {k: {"image": images[k]} for k in ("admin", "customer")}}, baseline)
    for kind in ("api", "admin", "customer"):
        variables["apps"][kind]["image"] = images[kind].split("/", 1)[1]
    variables.update(ingestion_container_image=images["ingestion"], ingestion_enabled=False,
                     ingestion_timer_enabled=False, ingestion_start_at="")
    rt.save(stage / "runtime.tfvars.json", variables)
    terraform(root, "init", "-input=false", "-lockfile=readonly", "-no-color",
              "-backend-config=" + str(rt.ROOT / "infra/terraform/backend.hcl"))
    override = {"resource": {"azurerm_linux_web_app": {"main": {
            "app_settings": "${local.finops_preserved_web_settings[each.key]}"}},
        "azurerm_linux_function_app": {"ingestion": preserved_function(root, target, images["ingestion"], client)}}}
    rt.save(root / "zzzz_finops_disabled_override.tf.json", override)
    terraform(root, "validate", "-no-color")
    rt.require(terraform(root, "workspace", "show").strip() == "default", "wrong_workspace")
    plan = stage / "disabled.tfplan"
    terraform(root, "plan", "-input=false", "-no-color", "-lock-timeout=60s",
              "-var-file=" + str(rt.HOME / "rebuild-platform.tfvars.json"),
              "-var-file=" + str(stage / "runtime.tfvars.json"),
              "-var-file=" + str(rt.HOME / "jwt-runtime.tfvars.json"),
              *["-target=" + address for address in release.ADDRESSES], "-out=" + str(plan))
    parsed = json.loads(terraform(root, "show", "-json", str(plan)))
    guard(parsed, images, target, client)
    rt.save(stage / "baseline.json", baseline)
    rt.save(stage / "settings-hashes.json", {k: sha(v) for k, v in settings.items()})
    proof = {"at_utc": stamp(), "tag": tag, "plan_sha256": release.digest(plan.read_bytes()),
        "images": images, "configuration_stage": "host_disabled_timer_disabled_no_cutoff_selected",
        "changed_setting_names": sorted(portals.changed(settings["ingestion"], target)),
        "guard": "passed", "applied": False, "timer_enabled": False, "cutoff_selected": False,
        "source_manifest_sha256": release.digest((folder / "source-manifest.json").read_bytes()),
        "controller_sha256": release.digest(Path(__file__).read_bytes()),
        "artifact_hashes": {p.relative_to(stage).as_posix(): release.digest(p.read_bytes())
                            for p in stage.rglob("*") if p.is_file() and ".terraform" not in p.parts
                            and p.name not in {"baseline.json", "settings-hashes.json"}},
        "post_apply_expected_settings_hash": sha(target), "client_id": client}
    rt.save(stage / "review.json", proof)
    print(json.dumps({k: v for k, v in proof.items() if k not in {"artifact_hashes", "client_id"}}), flush=True)


def apply(tag):
    folder = rt.HOME / "finops" / tag
    stage = folder / STAGE_NAME
    proof = json.loads((stage / "review.json").read_text())
    rt.require(not (stage / "apply-intent.json").exists(), "prior_apply_reconcile_do_not_replay")
    rt.require(proof["controller_sha256"] == release.digest(Path(__file__).read_bytes()), "controller_changed")
    rt.require(built(folder) == proof["images"], "build_changed")
    for name, expected in proof["artifact_hashes"].items():
        rt.require(release.digest((stage / name).read_bytes()) == expected, "artifact_changed")
    rt.require(0 <= (datetime.now(UTC) - datetime.fromisoformat(proof["at_utc"])).total_seconds() <= 7200,
               "plan_expired")
    status = json.loads((rt.ROOT / ".azure/validate-status.json").read_text())
    doc = (rt.ROOT / ".azure/deployment-plan.md").read_text(encoding="utf-8")
    rt.require(status.get("completedStep") == "UpdateStatus" and proof["plan_sha256"] in doc
               and "FinOps disabled staging status: Validated" in doc, "fresh_validation_required")
    baseline = json.loads((stage / "baseline.json").read_text())
    rt.require(portals.baseline() == baseline, "live_baseline_drift")
    settings = current_settings()
    rt.require({k: sha(v) for k, v in settings.items()} == json.loads((stage / "settings-hashes.json").read_text()),
               "settings_changed")
    target, client = configured(settings)
    root, plan = stage / "infra/terraform", stage / "disabled.tfplan"
    rt.require(release.digest(plan.read_bytes()) == proof["plan_sha256"], "saved_plan_changed")
    guard(json.loads(terraform(root, "show", "-json", str(plan))), proof["images"], target, client)
    rt.save(stage / "apply-intent.json", {"at_utc": stamp(), "plan_sha256": proof["plan_sha256"]})
    terraform(root, "apply", "-input=false", "-no-color", str(plan))
    rt.save(stage / "applied.json", {"at_utc": stamp(), "plan_sha256": proof["plan_sha256"], "applied": True})
    verify(tag)


def ingestion_settings_verified(settings, expected_hash):
    """Container conversion injects only these exact provider-owned ARM fields.

    This does not widen the configurable settings allowlist: validate all three
    values, then compare every remaining setting to the pre-apply target hash.
    """
    if sha(settings) == expected_hash:
        return True
    registry = {"DOCKER_REGISTRY_SERVER_URL": "https://" + release.REGISTRY,
                "DOCKER_REGISTRY_SERVER_USERNAME": "", "DOCKER_REGISTRY_SERVER_PASSWORD": ""}
    if any(settings.get(k) != v for k, v in registry.items()):
        return False
    return sha({k: v for k, v in settings.items() if k not in registry}) == expected_hash


def verify(tag):
    stage = rt.HOME / "finops" / tag / STAGE_NAME
    proof = json.loads((stage / "review.json").read_text())
    baseline = json.loads((stage / "baseline.json").read_text())
    current = portals.baseline()
    for kind in release.COMPONENTS:
        baseline["sites"][kind]["image"] = "DOCKER|" + proof["images"][kind]
    web = baseline["sites"]["ingestion"]["protected"]["web"]
    web.update(acrUseManagedIdentityCreds=True, acrUserManagedIdentityID=proof["client_id"])
    settings = current_settings()
    original = json.loads((stage / "settings-hashes.json").read_text())
    settings_ok = all(ingestion_settings_verified(settings[k], proof["post_apply_expected_settings_hash"])
                      if k == "ingestion" else sha(settings[k]) == original[k] for k in release.COMPONENTS)
    result = {"at_utc": stamp(), "images": proof["images"], "settings_verified": settings_ok,
        "protected_baseline_verified": current == baseline,
        "function_enabled": current["sites"]["ingestion"]["protected"]["enabled"],
        "timer_disabled": settings["ingestion"].get("AzureWebJobs.ingest_usage.Disabled") == "true",
        "activation_cutoff_present": bool(settings["ingestion"].get("AIFLUX_INGESTION_START_AT")),
        "live_ingestion_accepted": False, "next_gate": "exact_business_cutoff_before_host_and_timer_activation"}
    rt.save(stage / ("verification-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json"), result)
    print(json.dumps(result), flush=True)
    rt.require(settings_ok and current == baseline and result["timer_disabled"] and not result["function_enabled"],
               "post_apply_readback_mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply", "verify"))
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    rt.require(re.fullmatch(r"finops-[0-9]{8}t[0-9]{6}z", args.tag), "invalid_tag")
    {"plan": prepare, "apply": apply, "verify": verify}[args.action](args.tag)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Terraform/provider response bodies and settings are never echoed.
        print(json.dumps({"status": "blocked", "exception_type": type(exc).__name__,
                          "reason": str(exc) if isinstance(exc, RuntimeError) else "protected_operation_failed"}), flush=True)
        raise SystemExit(2)