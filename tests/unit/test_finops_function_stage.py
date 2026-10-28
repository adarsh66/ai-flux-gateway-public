"""Disabled staging never implies authorization to select or change history."""
from copy import deepcopy

import pytest

from scripts.deployment import finops_function_stage as stage


def fixture():
    images = {k: stage.release.REGISTRY + "/aiflux-" + k + "@sha256:" + "a" * 64
              for k in stage.release.COMPONENTS}
    settings = {"AzureWebJobs.ingest_usage.Disabled": "true", "preserved": "exact"}
    target = {**settings, "AIFLUX_CATALOG_CONFIGURED": "true"}
    resources = []
    for address, kind in stage.release.ADDRESSES.items():
        before = {"enabled": False, "identity": [{"type": "UserAssigned", "identity_ids": ["original"]}],
            "public_network_access_enabled": False, "app_settings": deepcopy(settings),
            "site_config": [{"minimum_tls_version": "1.2", "application_stack": [{
                "docker_registry_url": "https://" + stage.release.REGISTRY,
                "docker_image_name": "old"}]}]}
        if kind == "ingestion":
            before["site_config"][0].update(application_stack=[{"python_version": "3.11"}],
                container_registry_use_managed_identity=False,
                container_registry_managed_identity_client_id=None)
        after = deepcopy(before)
        config = after["site_config"][0]
        if kind == "ingestion":
            after["app_settings"] = deepcopy(target)
            config.update(container_registry_use_managed_identity=True,
                container_registry_managed_identity_client_id="approved-client",
                application_stack=[{"python_version": None, "docker": [{
                    "registry_url": "https://" + stage.release.REGISTRY,
                    "image_name": "aiflux-ingestion@sha256", "image_tag": "a" * 64}]}])
        else:
            config["application_stack"][0]["docker_image_name"] = images[kind].split("/", 1)[1]
        resources.append({"mode": "managed", "address": address, "change": {
            "actions": ["update"], "before": before, "after": after, "after_unknown": {}}})
    return {"applyable": True, "resource_changes": resources}, images, target


def test_exact_stage_passes_without_mutating_the_plan():
    plan, images, settings = fixture()
    original = deepcopy(plan)
    stage.guard(plan, images, settings, "approved-client")
    assert plan == original


@pytest.mark.parametrize("mutation", ["timer", "cutoff", "host", "identity", "network", "tls",
    "storage", "extra_setting", "wrong_value", "registry", "credential", "pin", "acr_client",
    "api_setting", "unknown", "extra_resource", "missing", "duplicate", "create", "deferred"])
def test_unapproved_changes_fail_closed(mutation):
    plan, images, settings = fixture()
    function = plan["resource_changes"][-1]
    after = function["change"]["after"]
    config = after["site_config"][0]
    if mutation == "timer":
        settings["AzureWebJobs.ingest_usage.Disabled"] = "false"
        after["app_settings"] = deepcopy(settings)
    elif mutation == "cutoff":
        settings["AIFLUX_INGESTION_START_AT"] = "2026-10-26T01:18:34Z"
        after["app_settings"] = deepcopy(settings)
    elif mutation == "host":
        after["enabled"] = True
    elif mutation == "identity":
        after["identity"][0]["identity_ids"] = ["foreign"]
    elif mutation == "network":
        after["public_network_access_enabled"] = True
    elif mutation == "tls":
        config["minimum_tls_version"] = "1.0"
    elif mutation == "storage":
        settings["AzureWebJobsStorage__blobServiceUri"] = "https://foreign.invalid"
        after["app_settings"] = deepcopy(settings)
    elif mutation == "extra_setting":
        settings["AIFLUX_LOCAL_AUTH_ENABLED"] = "false"
        after["app_settings"] = deepcopy(settings)
    elif mutation == "wrong_value":
        after["app_settings"]["AIFLUX_CATALOG_CONFIGURED"] = "false"
    elif mutation == "registry":
        config["application_stack"][0]["docker"][0]["registry_url"] = "https://foreign.invalid"
    elif mutation == "credential":
        config["application_stack"][0]["docker"][0]["registry_password"] = "synthetic"
    elif mutation == "pin":
        config["application_stack"][0]["docker"][0]["image_tag"] = "b" * 64
    elif mutation == "acr_client":
        config["container_registry_managed_identity_client_id"] = "other"
    elif mutation == "api_setting":
        plan["resource_changes"][0]["change"]["after"]["app_settings"]["auth"] = "false"
    elif mutation == "unknown":
        function["change"]["after_unknown"] = {"app_settings": {"hidden": True}}
    elif mutation == "extra_resource":
        other = deepcopy(function)
        other["address"] = "azurerm_role_assignment.extra"
        plan["resource_changes"].append(other)
    elif mutation == "missing":
        plan["resource_changes"].pop()
    elif mutation == "duplicate":
        plan["resource_changes"].append(deepcopy(function))
    elif mutation == "create":
        function["change"]["actions"] = ["delete", "create"]
    else:
        plan["deferred_changes"] = [{"reason": "unknown"}]
    with pytest.raises(RuntimeError):
        stage.guard(plan, images, settings, "approved-client")


def test_literal_settings_escape_terraform_interpolation():
    assert stage.literal({"a": "${not_an_expression}", "b": "%{not_a_directive}"}) == {
        "a": "$${not_an_expression}", "b": "%%{not_a_directive}"}


def test_writable_block_preserves_inputs_not_computed_outputs():
    schema = {"attributes": {"enabled": {"optional": True}, "secret": {"optional": True},
                             "computed": {"computed": True}, "absent": {"optional": True},
                             "url": {"optional": True}, "health_check_eviction_time_in_min": {"optional": True}},
              "block_types": {"rule": {"block": {"attributes": {"action": {"required": True}}}}}}
    value = {"enabled": False, "secret": "${literal}", "computed": "ignored", "absent": None,
             "url": "", "health_check_eviction_time_in_min": 0,
             "rule": [{"action": "Deny", "output": "ignored"}]}
    assert stage.writable_block(value, schema) == {
        "enabled": False, "secret": "$${literal}", "rule": [{"action": "Deny"}]}


@pytest.mark.parametrize("mutation", [None, "url", "username", "password", "missing", "extra", "timer", "cutoff", "auth"])
def test_readback_accepts_only_exact_provider_injected_registry_fields(mutation):
    expected = {"AzureWebJobs.ingest_usage.Disabled": "true", "AIFLUX_CATALOG_CONFIGURED": "false",
                "AIFLUX_LOCAL_AUTH_ENABLED": "true", "preserved": "exact"}
    actual = {**expected, "DOCKER_REGISTRY_SERVER_URL": "https://" + stage.release.REGISTRY,
              "DOCKER_REGISTRY_SERVER_USERNAME": "", "DOCKER_REGISTRY_SERVER_PASSWORD": ""}
    if mutation in {"url", "username", "password"}:
        actual["DOCKER_REGISTRY_SERVER_" + {"url": "URL", "username": "USERNAME", "password": "PASSWORD"}[mutation]] = "foreign"
    elif mutation == "missing":
        del actual["DOCKER_REGISTRY_SERVER_PASSWORD"]
    elif mutation == "extra":
        actual["unapproved"] = "value"
    elif mutation == "timer":
        actual["AzureWebJobs.ingest_usage.Disabled"] = "false"
    elif mutation == "cutoff":
        actual["AIFLUX_INGESTION_START_AT"] = "2026-10-27T00:00:00Z"
    elif mutation == "auth":
        actual["AIFLUX_LOCAL_AUTH_ENABLED"] = "false"
    assert stage.ingestion_settings_verified(actual, stage.sha(expected)) is (mutation is None)
    assert stage.ingestion_settings_verified(expected, stage.sha(expected))


@pytest.mark.parametrize("foreign", [False, True])
def test_guard_normalizes_only_exact_provider_owned_host_settings(foreign):
    plan, images, settings = fixture()
    before = plan["resource_changes"][-1]["change"]["before"]
    before.update(storage_account_name="existing-host", functions_extension_version="~4")
    plan["resource_changes"][-1]["change"]["after"].update(
        storage_account_name="existing-host", functions_extension_version="~4")
    settings.update(AzureWebJobsStorage__accountName="foreign" if foreign else "existing-host",
                    FUNCTIONS_EXTENSION_VERSION="~4")
    if foreign:
        with pytest.raises(RuntimeError, match="provider_owned_function_setting_mismatch"):
            stage.guard(plan, images, settings, "approved-client")
    else:
        stage.guard(plan, images, settings, "approved-client")


@pytest.mark.parametrize("mutation", [None, "url", "username", "password"])
def test_provider_owned_registry_fields_are_not_application_settings(mutation):
    settings = {k: {"DOCKER_REGISTRY_SERVER_URL": "https://" + stage.release.REGISTRY,
                   "DOCKER_REGISTRY_SERVER_USERNAME": "", "DOCKER_REGISTRY_SERVER_PASSWORD": "",
                   "preserved": "${exact}", "AIFLUX_LOCAL_AUTH_ENABLED": "true"}
                for k in ("api", "admin", "customer")}
    original = deepcopy(settings)
    if mutation:
        name = {"url": "URL", "username": "USERNAME", "password": "PASSWORD"}[mutation]
        settings["api"]["DOCKER_REGISTRY_SERVER_" + name] = "foreign"
        with pytest.raises(RuntimeError, match="existing_mi_registry_required"):
            stage.preserved_web_settings(settings)
    else:
        assert stage.preserved_web_settings(settings) == {
            k: {"preserved": "${exact}", "AIFLUX_LOCAL_AUTH_ENABLED": "true"} for k in settings}
        assert settings == original


@pytest.mark.parametrize("marker", [None, "review.json", "apply-intent.json", "applied.json", "applyable", "unknown"])
def test_archive_only_proven_failed_unreviewed_preparation(tmp_path, monkeypatch, marker):
    folder = tmp_path / "disabled-stage"
    folder.mkdir()
    (folder / "disabled.tfplan").write_bytes(b"protected-test-plan")
    if marker and marker.endswith(".json"):
        (folder / marker).write_text("{}")
    parsed = {"errored": True, "applyable": False}
    if marker == "applyable":
        parsed = {"errored": False, "applyable": True}
    elif marker == "unknown":
        parsed = {}
    monkeypatch.setattr(stage, "terraform", lambda *args: stage.json.dumps(parsed))
    if marker:
        with pytest.raises(RuntimeError, match="existing_stage_do_not_overwrite"):
            stage.archive_failed_preparation(folder)
        assert folder.exists()
    else:
        stage.archive_failed_preparation(folder)
        archived = list(tmp_path.glob("disabled-stage-unplanned-*"))
        assert not folder.exists() and len(archived) == 1
        assert (archived[0] / "disabled.tfplan").read_bytes() == b"protected-test-plan"


@pytest.mark.parametrize("accepted", ["true", "false"])
@pytest.mark.parametrize("explicit_identity", [True, False])
def test_configured_preserves_cutoff_and_exact_host_storage(monkeypatch, accepted, explicit_identity):
    db = ("postgresql://poc-ids-token-ex-api-identity@"
          "poc-ids-token-ex-pg.postgres.database.azure.com:5432/turnstile?sslmode=require")
    api = {"AIFLUX_DATABASE_URL": db, "AIFLUX_CATALOG_CONFIGURED": accepted,
        "AIFLUX_APIM_PRODUCT_ID": "aiflux", "AIFLUX_LOG_WORKSPACE_ID": "workspace",
        "AIFLUX_APIM_RESOURCE_ID": stage.rt.RG + "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"}
    old = {"AZURE_CLIENT_ID": "client", "AzureWebJobsStorage__clientId": "client",
        "AzureWebJobsStorage__credential": "managedidentity", "AzureWebJobs.ingest_usage.Disabled": "true"}
    for service in ("blob", "queue", "table"):
        old["AzureWebJobsStorage__" + service + "ServiceUri"] = "https://pocidstokenexfunc." + service + ".core.windows.net"
    if not explicit_identity:
        del old["AZURE_CLIENT_ID"]
    monkeypatch.setattr(stage.rt, "cli", lambda args: {"customerId": "workspace"})
    target, client = stage.configured({"api": api, "ingestion": old})
    assert client == "client" and "AIFLUX_INGESTION_START_AT" not in target
    assert target["AzureWebJobs.ingest_usage.Disabled"] == "true"
    assert target["AIFLUX_CATALOG_CONFIGURED"] == accepted
    assert target["AZURE_CLIENT_ID"] == "client"
    assert target["AIFLUX_DATABASE_URL"] == db.replace("-api-identity@", "-ingestion-identity@")
    assert all(target[k] == v for k, v in old.items())
    old["AZURE_CLIENT_ID"] = "foreign"
    with pytest.raises(RuntimeError, match="host_storage_identity_required"):
        stage.configured({"api": api, "ingestion": old})