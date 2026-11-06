"""Scorer presentation never confers chat eligibility or writes economics."""
import hashlib
from decimal import Decimal
from importlib.resources import files

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_catalog_pricing_correction import accepted  # noqa: F401

from aiflux import scoring_catalog
from aiflux.display_pricing import manifest
from aiflux.external_inventory import AcceptedInventory
from aiflux.models import ManagedModelEndpoint
from aiflux.schemas import ModelGardenItemOutput, ModelGardenUpsert
from aiflux.turnstile_exchange import list_model_garden, upsert_model_garden_item


def decision(inventory):
    return next(d for d in inventory.foundry.deployments if d.name == "Decision-1")


def test_sourced_tariff_is_separate_from_historical_chat_manifests():
    old = manifest(False)
    current = manifest()
    hashes = (old["sha256"], dict(old["source_sha256"]), current["sha256"], dict(current["source_sha256"]))
    data = scoring_catalog.scoring_manifest()
    raw = files("aiflux").joinpath("pricing/decision1-scoring-20261031.json").read_bytes()
    assert data["sha256"] == hashlib.sha256(raw).hexdigest()
    rate = scoring_catalog.scoring_descriptor()
    assert (rate["model"], rate["display_name"]) == ("Decision-1", "Microsoft Decision-1")
    assert rate["input"] == "0.042" and rate["billing_dimensions"] == ["input"]
    assert not {"output", "cached", "write"} & rate.keys()
    assert data["provenance"]["pricing_table"] == {
        "section": "Microsoft", "model": "Microsoft-Decision-1", "input": "$0.042",
        "cached": "N/A", "output": "N/A",
    }
    retail = data["provenance"]["retail"]
    assert retail["meterId"] == "3340205e-23e1-59c4-9be6-0e158131ec64"
    assert retail["currencyCode"] == "USD" and retail["unitOfMeasure"] == "1M"
    assert Decimal(str(retail["retailPrice"])) == Decimal("0.042")
    assert retail["effectiveStartDate"] == data["applicable_from"] == "2026-10-01T00:00:00Z"
    assert not any(r["model"] == "Decision-1" for r in current["rates"])
    assert hashes == (manifest(False)["sha256"], manifest(False)["source_sha256"],
                      manifest()["sha256"], manifest()["source_sha256"])


def test_verified_scorer_is_not_accepted_chat_and_is_not_coming_soon(accepted):
    env, inventory = accepted
    before = inventory.accepted_aliases(env.settings)
    metadata = scoring_catalog.scoring_metadata(env.settings, inventory)
    assert metadata["scoring_available"] is True
    assert metadata["deployment_state"] == decision(inventory).deployment_state  # null is not invented Active
    assert scoring_catalog.scoring_scope(env.settings, inventory) is not None
    item = scoring_catalog.scoring_item(env.settings, inventory)
    assert item.id == "Decision-1" and item.display_name == "Microsoft Decision-1"
    assert item.model_kind == "scoring" and item.scoring_available is True
    assert not item.enabled and not item.coming_soon and item.capabilities == ["scoring"]
    assert item.output_per_million is None and item.cached_input_per_million is None
    assert item.context_window is None and item.region == "unknown"
    assert inventory.route(item.id) is None and item.id not in before
    assert inventory.accepted_aliases(env.settings) == before
    assert ModelGardenItemOutput.model_validate(item.model_dump()) == item


@pytest.mark.parametrize("field,value,available", [
    ("decision", False, None), ("chat_completion", True, None),
    ("model_name", "other", None), ("model_name", "Decision-1", None),
    ("model_name", "synthetic-Decision-1", None), ("model_version", "future", None),
    ("model_format", "other", None), ("capacity", 0, False),
    ("provisioning_state", "Failed", False), ("deployment_state", "Inactive", False),
    ("provisioning_state", "Unknown", None), ("deployment_state", "Unknown", None),
])
def test_incompatible_inactive_and_unknown_evidence_never_fabricates_availability(
    accepted, field, value, available,
):
    env, inventory = accepted
    setattr(decision(inventory), field, value)
    item = scoring_catalog.scoring_item(env.settings, inventory)
    assert item.scoring_available is available and not item.enabled
    assert scoring_catalog.scoring_scope(env.settings, inventory) is None


def test_missing_duplicate_and_wrong_settings_evidence(accepted):
    env, inventory = accepted
    deployment = decision(inventory)
    inventory.foundry.deployments.remove(deployment)
    assert scoring_catalog.scoring_item(env.settings, inventory).scoring_available is None
    inventory.foundry.deployments.extend([deployment, deployment])
    assert scoring_catalog.scoring_scope(env.settings, inventory) is None
    inventory.foundry.deployments.pop()
    env.settings.decision_router_endpoint = "https://unrelated.test/providers/microsoft/v1/systemone"
    assert scoring_catalog.scoring_item(env.settings, inventory).scoring_available is False
    env.settings.decision_router_endpoint = "/providers/microsoft/v1/systemone"
    env.settings.foundry_project_resource_id += "-wrong"
    assert scoring_catalog.scoring_item(env.settings, inventory).scoring_available is None


@pytest.mark.parametrize("seeded", [False, True])
def test_catalog_adds_or_overlays_only_a_dto_without_dml_or_ddl(accepted, seeded):
    env, _ = accepted
    with Session(env.db_engine) as db:
        if seeded:
            db.add(ManagedModelEndpoint(
                id="Decision-1", display_name="Legacy", provider="legacy", vendor="legacy",
                backend_model="Decision-1", enabled=True, capabilities_json='["chat"]',
                input_per_million=Decimal("8"), output_per_million=Decimal("9"),
            ))
            db.commit()
        before = list(db.execute(select(
            ManagedModelEndpoint.id, ManagedModelEndpoint.input_per_million,
            ManagedModelEndpoint.output_per_million, ManagedModelEndpoint.enabled,
        )))
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(env.db_engine, "before_cursor_execute", capture)
        try:
            for include_disabled in (True, False):
                items = list_model_garden(db, env.settings, include_disabled=include_disabled)
                scorers = [i for i in items if i.id == "Decision-1"]
                assert len(scorers) == 1
                item = scorers[0]
                assert not item.enabled and item.scoring_available is True and not item.coming_soon
                assert item.input_per_million is None and item.output_per_million is None
                assert item.display_price["input"] == "0.042"
                assert "output" not in item.display_price
            assert before == list(db.execute(select(
                ManagedModelEndpoint.id, ManagedModelEndpoint.input_per_million,
                ManagedModelEndpoint.output_per_million, ManagedModelEndpoint.enabled,
            )))
            assert not db.new and not db.dirty
            assert not any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER"))
                           for s in statements)
        finally:
            event.remove(env.db_engine, "before_cursor_execute", capture)


def test_unknown_scorer_remains_disabled_and_unpriced_in_presentation(accepted, monkeypatch):
    env, inventory = accepted
    inventory.foundry.deployments.remove(decision(inventory))
    monkeypatch.setattr(AcceptedInventory, "load", classmethod(lambda cls, settings: inventory))
    with Session(env.db_engine) as db:
        item = next(i for i in list_model_garden(db, env.settings) if i.id == "Decision-1")
        assert item.scoring_available is None and not item.enabled and item.display_price is None
        visible = list_model_garden(db, env.settings, include_disabled=False)
        scorer = next(i for i in visible if i.id == "Decision-1")
        assert scorer.scoring_available is None and not scorer.enabled


@pytest.mark.parametrize("identity", ["Decision-1", "decision-1", "Microsoft-Decision-1"])
def test_upsert_cannot_promote_or_seed_a_scorer(identity):
    payload = ModelGardenUpsert(
        id=identity, display_name="Wrong chat", provider="Microsoft", vendor="Microsoft",
        backend_model=identity, enabled=True, capabilities=["chat"],
    )
    # None deliberately proves rejection occurs before any database/economic work.
    with pytest.raises(HTTPException) as error:
        upsert_model_garden_item(None, None, payload)
    assert error.value.status_code == 422


def test_other_chat_alias_cannot_be_bound_to_scoring_backend():
    payload = ModelGardenUpsert(id="disguised-chat", display_name="Wrong", provider="Microsoft",
                               vendor="Microsoft", backend_model="Decision-1")
    with pytest.raises(HTTPException):
        upsert_model_garden_item(None, None, payload)