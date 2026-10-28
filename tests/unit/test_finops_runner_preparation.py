"""Preparation regressions. Mock tests do not attest a deployed watchdog or probe."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_prepare as prep

NONCE = "012345abcdef"


def entrypoint():
    spec = importlib.util.spec_from_file_location("probe_entrypoint", prep.FOLDER / "entrypoint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_incremental_ignore_entries_require_explicit_baseline():
    plan = {"status": "Succeeded", "changes": [{"resourceId": g.owned_ids(NONCE)[key], "changeType": "Create"}
        for key in ("pip", "nsg", "nat", "subnet")] + [{"resourceId": g.VNET, "changeType": "Ignore"}]}
    assert g.guard_what_if(plan, NONCE, "network", baseline_ids=[g.VNET])
    with pytest.raises(g.GuardBlocked):
        g.guard_what_if(plan, NONCE, "network")
    for kind in ("Modify", "Delete", "Deploy", "Unsupported", "NoChange"):
        bad = deepcopy(plan)
        bad["changes"][-1]["changeType"] = kind
        with pytest.raises(g.GuardBlocked):
            g.guard_what_if(bad, NONCE, "network", baseline_ids=[g.VNET])


def test_ignore_cannot_conceal_planned_id_or_actual_delta():
    plan = {"status": "Succeeded", "changes": [{"resourceId": g.owned_ids(NONCE)["pip"], "changeType": "Ignore"}]}
    with pytest.raises(g.GuardBlocked):
        g.guard_what_if(plan, NONCE, "network", baseline_ids=list(g.owned_ids(NONCE).values()))


@pytest.mark.parametrize("mutation", ["ingress", "internet", "port", "vnet", "public_runner", "rbac", "existing_subnet"])
def test_network_exact_structural_guard_rejects_wider_design(mutation):
    template = prep.network_template(NONCE)
    nsg = template["resources"][1]["properties"]["securityRules"]
    if mutation == "ingress": nsg[1]["properties"]["access"] = "Allow"
    if mutation == "internet": nsg[-2]["properties"]["destinationAddressPrefix"] = "Internet"
    if mutation == "port": nsg[0]["properties"]["destinationPortRange"] = "*"
    if mutation == "vnet": nsg[1]["properties"]["destinationAddressPrefix"] = "VirtualNetwork"
    if mutation == "public_runner": template["resources"].append({"type": "Microsoft.ContainerInstance/containerGroups"})
    if mutation == "rbac": template["resources"].append({"type": "Microsoft.Authorization/roleAssignments"})
    if mutation == "existing_subnet": template["resources"][-1]["name"] = "poc-ids-token-ex-vnet/poc-ids-token-ex-private-endpoints"
    with pytest.raises(g.GuardBlocked): prep.guard_network(template, NONCE)


def test_network_plan_new_subnet_only_with_precise_egress_and_narrow_approved_management():
    template = prep.network_template(NONCE)
    assert prep.guard_network(template, NONCE)
    assert len(template["resources"]) == 4
    rules = template["resources"][1]["properties"]["securityRules"]
    inbound = [r["properties"] for r in rules if r["properties"]["direction"] == "Inbound"]
    assert [r["access"] for r in inbound] == ["Allow", "Deny"]
    assert inbound[0] == {"priority": 100, "direction": "Inbound", "access": "Allow", "protocol": "Tcp",
        "sourcePortRange": "*", "destinationPortRange": "19390", "sourceAddressPrefix": "10.240.0.0/16",
        "destinationAddressPrefix": "10.240.5.0/24"}
    assert inbound[1]["priority"] == 200 and inbound[1]["destinationPortRange"] == "*"
    assert template["resources"][-1]["properties"]["defaultOutboundAccess"] is False


@pytest.mark.parametrize("field,value", [("sourceAddressPrefix", "*"), ("sourceAddressPrefix", "Internet"),
    ("sourceAddressPrefix", "AzureCloud"), ("sourceAddressPrefix", "VirtualNetwork"),
    ("destinationAddressPrefix", "*"), ("destinationPortRange", "443"), ("protocol", "*")])
def test_management_exception_cannot_expand_source_destination_or_port(field, value):
    template = prep.network_template(NONCE)
    template["resources"][1]["properties"]["securityRules"][0]["properties"][field] = value
    with pytest.raises(g.GuardBlocked): prep.guard_network(template, NONCE)


@pytest.mark.parametrize("phase", ["ingestion", "api"])
def test_phase_template_uses_only_distinct_approved_mi_and_hash_bound_command(phase):
    image = "pocidstokenexacr.azurecr.io/aiflux-finops-probe@sha256:" + "a" * 64
    template = prep.group_template(NONCE, phase, image, "b" * 64)
    resource = template["resources"][0]
    assert set(resource["identity"]["userAssignedIdentities"]) == {g.IDENTITIES[phase]}
    assert resource["properties"]["containers"][0]["properties"]["command"][-1] == phase


@pytest.mark.parametrize("content", ["raw token", '{"status":"blocked","reason":"secret","exception_type":"secret"}', '{}', '[]'])
def test_entrypoint_cannot_echo_raw_child_errors_or_tokens(content):
    module = entrypoint()
    assert module.sanitize(content, 2) == module.failure("unverified_runtime_failure")


def test_entrypoint_uses_no_app_entrypoint_and_bounds_to_less_than_ten_minutes():
    source = (prep.FOLDER / "entrypoint.py").read_text()
    dockerfile = (prep.FOLDER / "Dockerfile").read_text()
    assert "timeout=590" in source and "os.O_EXCL" in source
    assert "return 0" in source and "--require-hashes" in dockerfile
    assert "USER 65532:65532" in dockerfile
    assert not any(x in dockerfile for x in ("uvicorn", "alembic", "COPY . ", "azure-cli"))


def test_validation_never_invokes_create_even_when_first_command_fails(monkeypatch, tmp_path):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout="", stderr="synthetic untrusted error")
    monkeypatch.setattr(prep.subprocess, "run", run)
    result = prep.validation(tmp_path / "template.json", NONCE, [])
    assert set(result) == {"validate", "what-if"}
    assert all(call[3] in {"validate", "what-if"} and "create" not in call and "Complete" not in call for call in calls)


def test_portal_websocket_requirement_does_not_prove_subnet_nsg_conflict():
    with pytest.raises(g.GuardBlocked, match="aci_nsg_platform_path_unresolved"):
        g.platform_gate(all_inbound_denied=True, documented_management_port_required=True)
    g.platform_gate(all_inbound_denied=True, documented_management_port_required=True,
                    requirement_applies_to_subnet_nsg=False)


def test_matching_top_level_fields_cannot_smuggle_nested_secrets():
    module = entrypoint()
    value = {key: None for key in module.SUCCESS_FIELDS}
    value.update(status="verified_read_only_snapshot", database_writes=0, replay_authorized=False,
                 database="turnstile", schema="public", identity_role_matches=True,
                 runtime_ddl_or_ownership=False, collected_at="2026-10-27T01:00:00+00:00",
                 table_privileges={"password": "hidden"})
    assert module.sanitize(json.dumps(value), 0) == module.failure("unverified_runtime_failure")


def test_real_reviewed_probe_aggregate_shape_survives_supervisor():
    # Real producer, synthetic cursor: no live DB, credentials or Azure call.
    spec = importlib.util.spec_from_file_location("probe_test_fixture", Path(__file__).with_name("test_finops_private_probe.py"))
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    value = fixture.probe.inspect_database(fixture.Database(), fixture.ROLE, now=fixture.NOW)
    rendered = json.dumps(value, default=str)
    module = entrypoint()
    assert module.sanitize(rendered, 0) == json.loads(rendered)
    value["all_time"]["first_request_at"] = "secret"
    assert module.sanitize(json.dumps(value, default=str), 0) == module.failure("unverified_runtime_failure")


@pytest.mark.parametrize("mode,reason", [("timeout", "deadline_exceeded"), ("already_started", "unverified_runtime_failure"), ("missing_source", "probe_source_changed")])
def test_supervisor_failure_os_exit_zero_never_means_snapshot_success(mode, reason, tmp_path, monkeypatch, capsys):
    import hashlib
    module = entrypoint()
    monkeypatch.setattr(module, "__file__", str(tmp_path / "entrypoint.py"))
    probe = tmp_path / "finops_private_probe.py"
    if mode != "missing_source": probe.write_bytes(b"reviewed source")
    monkeypatch.setattr(module.sys, "argv", ["entrypoint", "--probe-sha256", hashlib.sha256(b"reviewed source").hexdigest(), "--identity", "ingestion"])
    def open_marker(*args):
        if mode == "already_started": raise FileExistsError()
        return 777
    monkeypatch.setattr(module.os, "open", open_marker)
    monkeypatch.setattr(module.os, "close", lambda fd: None)
    def run(*args, **kwargs):
        assert kwargs["timeout"] == 590
        raise module.subprocess.TimeoutExpired("fixed", 590, output="DO-NOT-EXPORT", stderr="DO-NOT-EXPORT")
    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out) == module.failure(reason)


def test_exact_paid_acr_and_mgn_prices_exclude_existing_basic_baseline(tmp_path, monkeypatch):
    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps({"verified_same_session_price_observations": {
        "one_combined_hour_cpu_1_memory_gib_1_5_with_nat_and_ip_subtotal_usd": 0.108895,
        "additional_nat_data_usd_per_gb": 0.045}}))
    monkeypatch.setattr(prep.p, "OUT", prior)
    calls = []
    def prices(query):
        calls.append(query)
        if "Container Registry" in query:
            return [{"skuName": "Basic", "meterName": meter, "unitOfMeasure": unit, "retailPrice": rate}
                for meter, unit, rate in [("Task vCPU Duration", "1 Second", 0), ("Task vCPU Duration", "1 Second", 0.0001),
                    ("Data Stored", "1 GB/Month", 0.1), ("Basic Registry Unit", "1/Day", 0.1666)]]
        return [{"productName": "Rtn Preference: MGN", "meterName": "Standard Data Transfer Out", "unitOfMeasure": "1 GB", "retailPrice": 0.12},
                {"productName": "Bandwidth - Routing Preference: Internet", "meterName": "Standard Data Transfer Out", "unitOfMeasure": "1 GB", "retailPrice": 0.11}]
    monkeypatch.setattr(prep.p, "prices", prices)
    value = prep.collect_prices()
    assert len(calls) == 2
    assert value["all_in_scenario_estimate_usd"] == 0.778895
    assert value["planning_envelope_with_contingency_usd"] == 1.778895
    assert value["existing_basic_registry_sku_incremental_cost_usd"] == 0 and not value["hard_billing_cap"]


def test_unbound_group_templates_have_no_fake_digest_or_both_identities(tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "FOLDER", tmp_path)
    # Output paths need to remain relative to workspace for portable evidence.
    monkeypatch.setattr(prep, "ROOT", tmp_path)
    probe = tmp_path / "scripts/deployment/finops_private_probe.py"
    probe.parent.mkdir(parents=True)
    probe.write_text("reviewed probe fixture")
    result = prep.unbound_group_templates(NONCE)
    for phase in g.IDENTITIES:
        template = json.loads((tmp_path / (phase + ".unbound.arm.json")).read_text())
        assert "defaultValue" not in template["parameters"]["verifiedImageDigest"]
        assert result[phase]["image_digest"] is None and not result[phase]["what_if_run"]
        assert set(template["resources"][0]["identity"]["userAssignedIdentities"]) == {g.IDENTITIES[phase]}
        assert len(template["resources"]) == 1 and not result[phase]["apply_ready"]