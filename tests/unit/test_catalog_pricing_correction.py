"""Real accepted inventory shapes, stale SQL metadata, and fail-closed display."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from aiflux.external_inventory import AcceptedInventory
from aiflux.display_pricing import accepted_catalog_price, manifest
from aiflux.models import ManagedModelEndpoint
from aiflux.schemas import ModelGardenItemOutput
from aiflux.turnstile_exchange import ensure_model_garden_seeded, list_model_garden


@pytest.fixture
def accepted(env, tmp_path):
    root = Path("gateway/catalog")
    foundry = json.loads((root / "foundry-inventory-20261026.json").read_text())
    foundry["verified_at"] = datetime.now(UTC).isoformat()
    external = json.loads((root / "external-inventory.json").read_text())
    for route in external["routes"]:
        route["verified_at"] = datetime.now(UTC).isoformat()
    settings = env.settings
    settings.foundry_project_endpoint = foundry["project_endpoint"]
    settings.foundry_project_resource_id = foundry["project_resource_id"]
    settings.foundry_inventory_path.write_text(json.dumps(foundry))
    settings.external_inventory_path = tmp_path / "external.json"
    settings.external_inventory_path.write_text(json.dumps(external))
    routes = foundry["routes"] + external["routes"]
    settings.catalog_path.write_text(json.dumps({"models": [
        {"id": r["alias"], "provider": "ModelArts" if r["alias"] == "glm-5.3" else "Foundry",
         "backend_model": r["backend_model"], "enabled": True, "capabilities": ["chat"]}
        for r in routes]}))
    inventory = AcceptedInventory.load(settings)
    with Session(env.db_engine) as db:
        ensure_model_garden_seeded(db)
        for rate in manifest()["rates"]:
            if db.get(ManagedModelEndpoint, rate["model"]) is None:
                db.add(ManagedModelEndpoint(id=rate["model"], display_name=rate["model"],
                       provider="legacy-provider", vendor="legacy-provider", backend_model=rate["model"]))
        db.flush()
        for row in db.scalars(select(ManagedModelEndpoint)):
            route = inventory.route(row.id)
            if route:
                row.backend_model, row.endpoint_url = route.backend_model, route.endpoint_url
                row.provider = row.vendor = "legacy-provider"
                row.region = "eastus2" if row.id == "gpt-5.4-mini" else "unknown" if row.id == "glm-5.3" else "southeastasia"
        db.commit()
    return env, inventory


def test_all_eleven_catalog_prices_with_legacy_provider_region_and_no_writes(accepted):
    env, inventory = accepted
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(env.db_engine, "before_cursor_execute", capture)
    try:
        with Session(env.db_engine) as db:
            before = {r.id: (r.provider, r.vendor, r.region, r.input_per_million)
                      for r in db.scalars(select(ManagedModelEndpoint))}
            items = {i.id: i for i in list_model_garden(db, env.settings)}
            for rate in manifest()["rates"]:
                item = items[rate["model"]]
                price = item.display_price
                assert price is not None
                assert (price["provider"], price["region"]) == (rate["provider"], rate["region"])
                assert price["input"] == rate["input"] and price["output"] == rate["output"]
                assert price["source_url"].startswith("https://")
                assert ModelGardenItemOutput.model_validate(item.model_dump()).display_price == price
            glm = items["glm-5.3"].display_price
            assert glm["status"] == "tbc" and glm["source_url"] == "https://bigmodel.cn/pricing"
            assert glm["cny_per_usd_assumption"] == "7" and "NOT ModelArts" in glm["assumption"]
            assert before == {r.id: (r.provider, r.vendor, r.region, r.input_per_million)
                              for r in db.scalars(select(ManagedModelEndpoint))}
            assert not db.dirty
        assert not any(s.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for s in statements)
    finally:
        event.remove(env.db_engine, "before_cursor_execute", capture)


@pytest.mark.parametrize("bad", ["endpoint", "backend", "unaccepted", "version", "provider", "sku", "ambiguous", "external_expired"])
def test_wrong_or_unaccepted_binding_never_alias_falls_back(accepted, monkeypatch, bad):
    env, inventory = accepted
    alias = "glm-5.3" if bad == "external_expired" else "gpt-5.4-mini"
    route = inventory.route(alias)
    backend, endpoint = route.backend_model, route.endpoint_url
    if bad == "endpoint":
        endpoint = "https://wrong.test/v1"
    elif bad == "backend":
        backend = "wrong"
    elif bad == "unaccepted":
        route.gateway_validated = False
    elif bad == "external_expired":
        route.verified_at = datetime.now(UTC) - timedelta(days=365)
    elif bad == "ambiguous":
        data = deepcopy(manifest())
        data["rates"].append(dict(next(r for r in data["rates"] if r["model"] == alias), region="wrong"))
        monkeypatch.setattr("aiflux.display_pricing.manifest", lambda: data)
    else:
        deployment = next(d for d in inventory.foundry.deployments if d.id == route.deployment_id)
        if bad == "version":
            deployment.model_version = route.model_version = "wrong"
        elif bad == "provider":
            deployment.model_format = "wrong"
        else:
            deployment.sku = "wrong"
    assert accepted_catalog_price(inventory, alias, backend, endpoint) is None