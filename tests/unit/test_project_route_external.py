"""Render real Terraform policy offline; never resolve or provision a secret."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest

from scripts.deployment.apim_route_repair import APIM, RepairBlocked
from scripts.deployment.project_route_external import BACKEND, NAMED_VALUE, guard_external_update
from scripts.deployment.project_route_models import POLICY
from scripts.deployment.project_route_persistent import APPROVED

ROOT = Path(__file__).resolve().parents[2]
URI = "https://pocidstokenexkv.vault.azure.net/secrets/glm-5-3-api-key"


@pytest.fixture(scope="module")
def external_plan():
    def render(enabled):
        args = ["terraform", "-chdir=" + str(ROOT / "infra/project-route"), "console", "-no-color",
                "-var=enabled=false", "-var=demo_authorized=true", "-var=persistent_poc_authorized=true",
                "-var=rpm_limit=60", "-var=tpm_limit=2048", "-var=completion_token_limit=1024",
                "-var=daily_call_allowance=1000", "-var=route_manifest_path=" + (ROOT / "gateway/catalog/project-routes.json").as_posix(),
                "-var=glm_enabled=" + str(enabled).lower()]
        proc = subprocess.run(args, input="jsonencode({policy=local.policy})\n", capture_output=True, text=True,
            env={**os.environ, "TF_CLI_CONFIG_FILE": str(ROOT / ".deployment/terraform.rc")}, timeout=90)
        assert proc.returncode == 0, proc.stderr
        return json.loads(json.loads(proc.stdout[proc.stdout.find('"'):]))["policy"]
    before, after = render(False), render(True)
    previous = {**APPROVED, "route_manifest_path": "preserved", "excluded_routes": [],
                "glm_enabled": False, "glm_resolver_verified": False, "glm_secret_identifier": "",
                "glm_credential_storage": "apim-internal", "glm_internal_secret_verified": False}
    variables = {**previous, "glm_enabled": True, "glm_resolver_verified": True, "glm_secret_identifier": URI,
                 "glm_credential_storage": "key-vault"}
    def policy(value):
        return {"type": "Microsoft.ApiManagement/service/apis/policies@2024-05-01", "parent_id": APIM + "/apis/aiflux-dev-unified",
                "name": "policy", "body": {"properties": {"format": "rawxml", "value": value}}}
    resources = [
        {"address": POLICY, "change": {"actions": ["update"], "before": policy(before), "after": policy(after)}},
        {"address": NAMED_VALUE, "change": {"actions": ["create"], "after": {
            "type": "Microsoft.ApiManagement/service/namedValues@2024-05-01", "parent_id": APIM, "name": "aiflux-glm-5-3-api-key",
            "body": {"properties": {"displayName": "aiflux-glm-5-3-api-key", "secret": True, "keyVault": {"secretIdentifier": URI}}}}}},
        {"address": BACKEND, "change": {"actions": ["create"], "after": {
            "type": "Microsoft.ApiManagement/service/backends@2024-05-01", "parent_id": APIM, "name": "aiflux-external-glm-5-3",
            "body": {"properties": {"protocol": "http", "url": "https://api-ap-southeast-1.modelarts-maas.com/v1",
                                    "tls": {"validateCertificateChain": True, "validateCertificateName": True}}}}}},
    ]
    return {"applyable": True, "variables": {k: {"value": v} for k, v in variables.items()},
            "resource_changes": resources}, before, after, previous, URI


def test_external_saved_plan_and_credential_isolation(external_plan):
    guard_external_update(*external_plan, storage_mode="key-vault")
    _, baseline, rendered, _, _ = external_plan
    tree = ET.fromstring(rendered)
    assert "glm-5.3" not in baseline
    assert len(tree.findall(".//llm-content-safety")) == 3
    assert len(tree.findall(".//send-request")) == 5
    assert len(tree.findall(".//forward-request")) == 1
    assert not tree.findall(".//retry")
    assert len(list(tree.find("backend"))) == 1
    assert rendered.rindex("</send-request>") < rendered.index("Bearer {{")
    assert rendered.index("Bearer {{") > rendered.index('name="Ocp-Apim-Subscription-Key" exists-action="delete"')
    branch = next(n for n in tree.findall(".//when") if n.find("rewrite-uri") is not None and 'glm-5.3' in n.get('condition', ''))
    assert branch.find("authentication-managed-identity") is None
    assert branch.find("rewrite-uri").get("template") == "/chat/completions"
    for call in tree.findall(".//send-request"):
        assert "Bearer {{" not in ET.tostring(call, encoding="unicode")
    for name in ("Authorization", "api-key", "Ocp-Apim-Subscription-Key", "x-api-key", "Ocp-Apim-Trace", "Apim-Debug-Authorization"):
        assert tree.find(f'.//set-header[@name="{name}"][@exists-action="delete"]') is not None
    assert '"max_completion_tokens"' in rendered
    assert "aiflux-external-response" in rendered and "Invalid external response" in rendered
    assert 'finishReason != "stop" && finishReason != "length"' in rendered
    assert '["finish_reason"] = finishReason' in rendered
    assert 'completion == maximum ? "length" : "stop"' not in rendered


@pytest.mark.parametrize("mutation", ["foreign", "tls", "inline", "unknown", "delete", "quota", "network", "foundry"])
def test_reject_out_of_scope_or_unsafe_external_plans(external_plan, mutation):
    plan, before, after, previous, uri = deepcopy(external_plan)
    if mutation in ("foreign", "network"):
        plan["resource_changes"].append({"address": "azapi_resource.network", "change": {"actions": ["update"]}})
    elif mutation == "tls":
        plan["resource_changes"][2]["change"]["after"]["body"]["properties"]["tls"]["validateCertificateName"] = False
    elif mutation == "inline":
        plan["resource_changes"][1]["change"]["after"]["body"]["properties"]["value"] = "synthetic-placeholder"
    elif mutation == "unknown":
        plan["resource_changes"][1]["change"]["after_unknown"] = {"body": True}
    elif mutation == "delete":
        plan["resource_changes"][2]["change"]["actions"] = ["delete", "create"]
    else:
        after = after.replace('token-quota="10000"', 'token-quota="10001"') if mutation == "quota" else after.replace("gpt-4o", "unapproved")
        plan["resource_changes"][0]["change"]["after"]["body"]["properties"]["value"] = after
    with pytest.raises(RepairBlocked):
        guard_external_update(plan, before, after, previous, uri, storage_mode="key-vault")


def internal_candidate(external_plan):
    from datetime import UTC, datetime
    from scripts.deployment.glm_apim_secret import NAME, RESOURCE_ID
    plan, before, after, previous, _ = deepcopy(external_plan)
    plan["resource_changes"] = [r for r in plan["resource_changes"] if r["address"] != NAMED_VALUE]
    for key, value in {"glm_credential_storage": "apim-internal", "glm_internal_secret_verified": True,
                       "glm_resolver_verified": False, "glm_secret_identifier": ""}.items():
        plan["variables"][key] = {"value": value}
    evidence = {"resource_id": RESOURCE_ID, "display_name": NAME, "secret": True,
                "key_vault": False, "checked_at": datetime.now(UTC).isoformat()}
    return plan, before, after, previous, evidence


def test_internal_existing_secret_allows_only_backend_and_policy(external_plan):
    plan, before, after, previous, evidence = internal_candidate(external_plan)
    guard_external_update(plan, before, after, previous, "", storage_mode="apim-internal", internal_metadata=evidence)


@pytest.mark.parametrize("mutation", ["missing", "public", "vault", "foreign", "stale", "future", "value", "owned", "data-source", "mode", "quota", "network"])
def test_internal_guard_fails_closed(external_plan, mutation):
    plan, before, after, previous, evidence = internal_candidate(external_plan)
    if mutation == "missing":
        evidence = None
    elif mutation == "public":
        evidence["secret"] = False
    elif mutation == "vault":
        evidence["key_vault"] = True
    elif mutation == "foreign":
        evidence["resource_id"] += "-wrong"
    elif mutation in ("stale", "future"):
        evidence["checked_at"] = "2000-01-01T00:00:00+00:00" if mutation == "stale" else "2099-01-01T00:00:00+00:00"
    elif mutation == "value":
        evidence["value"] = "synthetic-never-a-real-key"
    elif mutation == "owned":
        plan["resource_changes"].append({"address": NAMED_VALUE, "change": {"actions": ["no-op"]}})
    elif mutation == "data-source":
        plan["resource_changes"].append({"address": "data.azapi_resource.unapproved", "change": {
            "actions": ["read"], "after": {"type": "Microsoft.ApiManagement/service/namedValues@2024-05-01"}}})
    elif mutation == "mode":
        plan["variables"]["glm_credential_storage"]["value"] = "key-vault"
    elif mutation == "quota":
        plan["variables"]["daily_call_allowance"]["value"] = 1001
    elif mutation == "network":
        plan["resource_changes"].append({"address": "azapi_resource.network", "change": {"actions": ["update"]}})
    with pytest.raises(RepairBlocked):
        guard_external_update(plan, before, after, previous, "", storage_mode="apim-internal", internal_metadata=evidence)