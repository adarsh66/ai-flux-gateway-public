"""Actual retained evidence, offline only; fixture package never means live publish."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from scripts.deployment import foundry_eight_offline_promotion as f

a = f.a
p = f.profile_module()


@pytest.fixture(scope="module")
def retained():
    before = f.historical_hashes()
    # A mistaken cloud call must fail even during tests of real evidence.
    with patch.object(a, "cli", side_effect=AssertionError("offline only")), \
            patch("requests.sessions.Session.request", side_effect=AssertionError("offline only")):
        rows, additions, policy = f.existing()
    assert f.historical_hashes() == before
    return rows, additions, policy


@pytest.fixture(scope="module")
def packaged(tmp_path_factory, retained):
    home = tmp_path_factory.mktemp("genuine-eight-offline")
    before = f.historical_hashes()
    with patch.object(a, "cli", side_effect=AssertionError("offline only")), \
            patch("requests.sessions.Session.request", side_effect=AssertionError("offline only")):
        context = f.package(home, *retained)
    assert f.historical_hashes() == before
    return home, context


def test_actual_eight_identity_usage_and_global_zero_budget(retained):
    rows, additions, _ = retained
    assert [r["alias"] for r in rows] == list(a.ALIASES)
    assert [d["name"] for d in additions] == list(a.ALIASES)
    assert len({r["response_id"] for r in rows}) == len({r["correlation_id"] for r in rows}) == 8
    assert [sum(r["usage"][key] for r in rows) for key in ("prompt_tokens", "completion_tokens", "total_tokens")] == [121, 80, 201]
    final = a.load(f.s.HOME / "final-local-integrity.json")
    assert final["remaining_call_budget"] == 0 and final["accepted_success_count"] == 7
    assert {q.stem for q in f.s.LEDGER.glob("*.json")} == set(a.ALIASES)


@pytest.mark.parametrize("model", ["mistral-large-3", "Mistral-Large-3"])
def test_only_exact_authorized_mistral_identity_pair(retained, model):
    rows, additions, _ = retained
    row = {**rows[7], "response_model": model}
    evidence = a.load(f.m.HOME / "evidence.json")
    if model == "mistral-large-3":
        p.validate_identity(row, additions[7], evidence)
    else:
        # A claimed alias cannot replace the actual correlated provider spelling.
        with pytest.raises(ValueError):
            p.validate_identity(row, additions[7], evidence)


@pytest.mark.parametrize("model", ["MISTRAL-LARGE-3", "Mistral-large-3", "mistral-Large-3", "mistral-large-3-1", "other", None])
def test_casefold_dated_other_missing_identity_rejected(retained, model):
    rows, additions, _ = retained
    with pytest.raises(ValueError):
        p.validate_identity({**rows[7], "response_model": model}, additions[7], a.load(f.m.HOME / "evidence.json"))


@pytest.mark.parametrize("field,value", [("DeploymentName", "mistral-large-3"), ("ModelName", "Mistral-Large-3"),
    ("RequestId", "different-response"), ("CorrelationId", "different-correlation"), ("PromptTokens", 10), ("TotalTokens", 17)])
def test_mistral_exact_llm_deployment_response_usage_required(retained, field, value):
    rows, additions, _ = retained
    evidence = a.load(f.m.HOME / "evidence.json")
    evidence["llm_row"][field] = value
    with pytest.raises(ValueError):
        p.validate_identity(rows[7], additions[7], evidence)


def test_canonical_openai_and_terra_not_faked_raw(retained):
    rows, additions, _ = retained
    for i in (4, 5):
        evidence = a.load(f.s.TELEMETRY / "evidence.json") if i == 4 else None
        p.validate_identity(rows[i], additions[i], evidence)
        wrong = deepcopy(additions[i])
        wrong["model_version"] += "-wrong"
        with pytest.raises(ValueError):
            p.validate_identity(rows[i], wrong, evidence)
    assert rows[4]["response_model"] is None and rows[4]["raw_response_model_captured"] is False
    for i in (0, 1, 2, 3, 6):
        for spelling in (rows[i]["alias"].upper(), rows[i]["alias"] + "-2", "mistral-large-3"):
            with pytest.raises(ValueError):
                p.validate_identity({**rows[i], "response_model": spelling}, additions[i])


def test_genuine_proof_packaged_actual_builder_schema_and_membership(packaged):
    home, context = packaged
    builder = f.profile_module(context / "services/usage-ingestion/accepted_catalog_profile.py")
    builder.verify_packaged(context)
    actual = builder.build(context)
    assert sum(m["enabled"] for m in actual["models"]) == 21 and len(actual["models"]) == 22
    assert next(m for m in actual["models"] if m["id"] == "Decision-1")["enabled"] is False
    selected = a.load(context / "gateway/catalog/foundry-inventory-20261026.json")
    inventory = a.FoundryInventory.model_validate(selected)
    assert len(inventory.routes) == 20 and all(inventory.route(r.alias) for r in inventory.routes)
    # RouteEvidence deliberately has no 'provider' field: prove actual strict schema.
    wrong = deepcopy(selected)
    wrong["routes"][-1]["provider"] = "bogusprovider???"
    with pytest.raises(ValueError):
        a.FoundryInventory.model_validate(wrong)
    provenance = a.load(home / "accepted-provenance.json")
    old = a.load(a.CATALOG / "foundry-inventory-20261026.json")
    assert selected["verified_at"] == old["verified_at"]
    assert selected["deployments"][:13] == old["deployments"]
    for original, converted in zip(old["routes"], selected["routes"]):
        assert converted == {**original, "endpoint_url": a.GATEWAY}
    assert len(provenance["old_twelve_endpoint_conversions"]) == 12
    assert all(not c["new_probe"] and c["grandfather_route_sha256"] for c in provenance["old_twelve_endpoint_conversions"])
    assert (context / "gateway/catalog/external-inventory.json").read_bytes() == (a.CATALOG / "external-inventory.json").read_bytes()


@pytest.mark.parametrize("defect", ["missing_proof", "fake_integrity", "fake_usage", "fake_mistral_log", "no_fast_guard", "extra_provider", "stale_ingester", "external_drift", "provider_drift"])
def test_packaging_rejects_flags_or_synthetic_or_missing_actual_proof(packaged, tmp_path, defect):
    _, original = packaged
    # Only public catalog/builder inputs needed; no runtime or cloud execution.
    context = tmp_path / "context"
    shutil.copytree(original / "gateway/catalog", context / "gateway/catalog")
    shutil.copytree(original / "services/usage-ingestion", context / "services/usage-ingestion")
    proof = context / "gateway/catalog/acceptance-evidence"
    if defect == "missing_proof":
        (proof / (p.S03 + "final-local-integrity.json")).unlink()
    elif defect == "fake_integrity":
        target = proof / (p.S03 + "final-local-integrity.json")
        data = a.load(target)
        data["accepted_success_count"] = 8
        target.write_text(json.dumps(data))
    elif defect in ("fake_usage", "no_fast_guard"):
        i = 3 if defect == "no_fast_guard" else 8
        alias = a.ALIASES[i - 1]
        target = proof / ((p.S02 if i == 3 else p.S03) + f"probes/{i:02d}-{alias}-" + ("passed.json" if i == 3 else "response.json"))
        data = a.load(target)
        if i == 3:
            data.pop("fast_speed_proof")
        else:
            data["usage"]["total_tokens"] = 99
        target.write_text(json.dumps(data))
    elif defect == "fake_mistral_log":
        target = proof / (p.MISTRAL + "evidence.json")
        data = a.load(target)
        data["llm_row"]["DeploymentName"] = "other"
        target.write_text(json.dumps(data))
    elif defect == "stale_ingester":
        target = context / "services/usage-ingestion/ingestion-approved.json"
        target.write_text('{"models": []}')
    elif defect == "external_drift":
        target = context / "gateway/catalog/external-inventory.json"
        target.write_bytes(target.read_bytes() + b"\n")
    else:
        target = context / "gateway/catalog/foundry-inventory-20261026.json"
        data = a.load(target)
        if defect == "extra_provider":
            data["routes"][-1]["provider"] = "bogusprovider???"
        else:
            data["deployments"][-1]["model_format"] = "bogusprovider???"
        target.write_text(json.dumps(data))
    with pytest.raises((ValueError, OSError)):
        p.verify_packaged(context)


def test_separate_pricing_freeze_exact_and_no_auto_or_build(packaged):
    home, context = packaged
    manifest = a.load(home / "pricing-freeze/manifest.json")
    assert not manifest["acceptance_identity_source"] and not manifest["fresh_pricing_fetch"]
    for relative, expected in manifest["files"].items():
        assert a.sha((home / "pricing-freeze" / relative).read_bytes()) == a.sha((a.ROOT / relative).read_bytes()) == expected
    for docker in ("services/control-plane/Dockerfile", "services/usage-ingestion/Dockerfile"):
        text = (context / docker).read_text()
        assert "accepted_catalog_profile.py --profile" in text
    assert not (context / ".env").exists() and not (context / "node_modules").exists()
    with pytest.raises(ValueError):
        p.build(context, profile="foundry-eight")


def test_collector_fixed_existing_ids_metadata_only_and_remaining_query():
    row = a.load(f.m.prior.RECEIPT)
    text = f.m.query(row)
    assert row["response_id"] in text and row["correlation_id"] in text
    assert "DeploymentName" in text and "ModelName" in text and "take 2" in text
    assert "RequestMessages" not in text and "ResponseMessages" not in text and "Body" not in text
    assert "_ResourceId =~" in text and "CorrelationId ==" in text and "RequestId ==" in text