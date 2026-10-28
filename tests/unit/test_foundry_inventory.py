import json
from datetime import UTC, datetime, timedelta

import pytest
from aiflux.foundry_inventory import FoundryInventory
from aiflux.models import ManagedModelEndpoint
from conftest import install_inventory
from gateway.tools.verify_foundry_inventory import InventoryReadError, collect
from sqlalchemy.orm import Session


def rewrite(env, mutate):
    path = env.settings.foundry_inventory_path
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data))


def test_exact_alias_to_deployment_mapping_and_limits(env):
    # This unit tests the inventory's own cap independently of the deployment's
    # lower 1024-token production environment cap (covered separately below).
    env.settings.gateway_max_completion_tokens = 4096
    response = env.client.get("/api/models", headers=env.customer)
    assert response.status_code == 200
    model = response.json()["items"][0]
    assert model["id"] == "test-alias"  # Not the provider name or deployment name.
    assert model["max_completion_tokens"] == 4096
    assert model["capabilities"] == ["chat", "stream"]
    rewrite(env, lambda d: d["routes"][0].update(capabilities=["chat"], max_completion_tokens=64))
    model = env.client.get("/api/models", headers=env.customer).json()["items"][0]
    assert model["capabilities"] == ["chat"]
    assert model["max_completion_tokens"] == 64


def test_published_poc_inventory_exact_routes_and_approved_limits():
    from pathlib import Path
    from aiflux.foundry_inventory import FoundryInventory

    root = Path(__file__).resolve().parents[2]
    inventory = FoundryInventory.model_validate_json(
        (root / "gateway/catalog/foundry-inventory-20261026.json").read_text()
    )
    manifest = json.loads((root / "gateway/catalog/project-routes.json").read_text())
    additive = json.loads((root / "gateway/catalog/fireworks-candidate-routes.json").read_text())
    assert set(manifest["routes"]) < set(additive["routes"])
    manifest = additive
    assert len(inventory.deployments) == 13
    assert {r.alias for r in inventory.routes} == set(manifest["routes"])
    for route in inventory.routes:
        assert inventory.route(route.alias) is not None
        assert route.max_completion_tokens == 1024
        assert route.capabilities == ["chat"]
        assert route.expires_at is None
        assert route.upstream_token_parameter == manifest["routes"][route.alias]["token_parameter"]
    decision = next(d for d in inventory.deployments if d.name == "Decision-1")
    assert decision.decision and not decision.chat_completion
    assert inventory.route("Decision-1") is None


@pytest.mark.parametrize("route_limit,expected", [(1024, 1024), (2048, 1024), (64, 64)])
def test_persistent_poc_catalog_keeps_lower_route_limit_without_deadline(env, route_limit, expected):
    env.settings.gateway_max_completion_tokens = 1024
    rewrite(env, lambda d: d["routes"][0].update(max_completion_tokens=route_limit, expires_at=None))
    response = env.client.get("/api/models", headers=env.customer)
    assert response.status_code == 200
    assert response.json()["items"][0]["max_completion_tokens"] == expected
    assert FoundryInventory.load(env.settings).route("test-alias").expires_at is None


def test_discovery_does_not_enable_decision_or_unvalidated_chat(env):
    rewrite(env, lambda d: d["deployments"].append({
        **d["deployments"][0], "id": d["account_resource_id"] + "/deployments/Decision-1",
        "name": "Decision-1", "model_name": "Microsoft-Decision-1", "chat_completion": False, "decision": True,
    }))
    result = env.client.get("/api/model-deployments", headers=env.customer)
    assert result.status_code == 200
    decision = next(m for m in result.json()["items"] if m["id"] == "Decision-1")
    assert decision["role"] == "routing-only" and decision["chat_selectable"] is False
    assert decision["status"] == "integration-unavailable"
    assert decision["pricing_status"] == "unknown"
    assert "Decision-1" not in [m["id"] for m in env.client.get("/api/models", headers=env.customer).json()["items"]]


def test_explicit_inventory_sync_is_idempotent_and_preserves_operator_overrides(env):
    from aiflux.models import ModelRouterConfig
    with Session(env.db_engine) as db:
        row = ManagedModelEndpoint(id="test-alias", display_name="Operator label", provider="operator", vendor="operator",
            backend_model="stale", endpoint_url="", enabled=False, priority=7, description="Keep me")
        db.add(row)
        db.add(ModelRouterConfig(id="default", enabled=True, default_model="stale", candidate_models_json='["stale"]'))
        db.commit()
    first = env.client.post("/api/admin/model-deployments/sync", headers=env.admin)
    assert first.status_code == 200, first.text
    assert first.json()["gateway_published"] is False
    second = env.client.post("/api/admin/model-deployments/sync", headers=env.admin)
    assert second.json()["changed"] == []
    with Session(env.db_engine) as db:
        row = db.get(ManagedModelEndpoint, "test-alias")
        assert row.display_name == "Operator label" and row.description == "Keep me"
        assert row.enabled is False and row.priority == 7
        assert row.backend_model == FoundryInventory.load(env.settings).route("test-alias").backend_model
        assert db.get(ModelRouterConfig, "default").enabled is False


@pytest.mark.parametrize("change", [
    lambda d: d.update(verified_at=(datetime.now(UTC) - timedelta(days=2)).isoformat()),
    lambda d: d.update(verified_at=(datetime.now(UTC) + timedelta(minutes=2)).isoformat()),
    lambda d: d.update(verified_at="2026-10-26T00:00:00"),
    lambda d: d.update(project_endpoint="https://other.services.ai.azure.com/api/projects/other"),
    lambda d: d.update(account_resource_id=d["account_resource_id"] + "-other"),
    lambda d: d.update(project_resource_id=d["project_resource_id"] + "-other"),
    lambda d: d.update(account_read="Failed"),
    lambda d: d.update(project_read="Failed"),
    lambda d: d.update(connections_read="Failed"),
    lambda d: d.update(project_deployments_read="Unknown"),
    lambda d: d.update(connection_ids=["unverified-connected-account"]),
    lambda d: d["deployments"].append(d["deployments"][0]),
    lambda d: d["routes"].append(d["routes"][0]),
    lambda d: d["deployments"][0].update(id=d["deployments"][0]["id"].replace("poc-ids-token-ex-foundry/", "Other/")),
])
def test_bad_inventory_fails_closed_for_every_customer_path(env, change):
    rewrite(env, change)
    for path in ("/api/models", "/api/model-garden", "/api/model-router"):
        response = env.client.get(path, headers=env.customer)
        assert response.status_code == 503
        assert "inventory" in response.json()["detail"]
    chat = env.client.post("/api/playground/chat", headers=env.customer,
                           json={"model": "test-alias", "messages": [{"role": "user", "content": "Hello"}]})
    assert chat.status_code == 503


@pytest.mark.parametrize("mode", ["unset", "missing", "malformed"])
def test_missing_inventory_never_falls_back_to_seeded_postgres_rows(env, mode):
    env.settings.local_auth_enabled = True
    env.settings.catalog_configured = False
    path = env.settings.foundry_inventory_path
    if mode == "unset":
        env.settings.foundry_inventory_path = None
    elif mode == "missing":
        path.unlink()
    else:
        path.write_text("not JSON")
    assert env.client.get("/api/models", headers=env.customer).status_code == 503


@pytest.mark.parametrize("change", [
    lambda d: d["deployments"][0].update(provisioning_state="Failed"),
    lambda d: d["deployments"][0].update(provisioning_state="Creating"),
    lambda d: d["deployments"][0].update(deployment_state="Disabled"),
    lambda d: d["deployments"][0].update(capacity=0),
    lambda d: d["deployments"][0].update(chat_completion=False),
    lambda d: d["routes"][0].update(gateway_validated=False),
    lambda d: d["routes"][0].update(deployment_id="unknown"),
    lambda d: d["routes"][0].update(backend_model="provider-name-not-deployment-alias"),
    lambda d: d["routes"][0].update(model_name="different-provider-model"),
    lambda d: d["routes"][0].update(model_version="different-version"),
    lambda d: d["routes"][0].update(capabilities=["embeddings"]),
    lambda d: d["routes"][0].update(endpoint_url="http://gateway.test/v1"),
    lambda d: d["routes"][0].update(endpoint_url="https://user:secret@gateway.test/v1"),
    lambda d: d.update(routes=[]),
])
def test_only_active_successful_chat_deployments_with_exact_accepted_routes_are_listed(env, change):
    rewrite(env, change)
    response = env.client.get("/api/models", headers=env.customer)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_all_endpoint_pool_members_must_match_verified_route(env):
    data = json.loads(env.settings.catalog_path.read_text())
    data["models"][0]["backends"] = [
        {"id": "valid", "region": "test-region", "url": "https://gateway.test/v1"},
        {"id": "wrong", "region": "other", "url": "https://other.test/v1"},
    ]
    env.settings.catalog_path.write_text(json.dumps(data))
    assert env.client.get("/api/models", headers=env.customer).json()["items"] == []


def test_postgres_seed_flags_are_not_active_inventory(env):
    env.settings.local_auth_enabled = True
    env.settings.catalog_configured = False
    assert env.client.get("/api/models", headers=env.customer).json() == {"items": [], "total": 0}
    garden = env.client.get("/api/model-garden", headers=env.customer)
    assert garden.json()["items"] == []
    admin = env.client.get("/api/admin/model-garden", headers=env.admin)
    assert admin.json()["items"]
    assert all(not item["enabled"] for item in admin.json()["items"])
    router = env.client.get("/api/model-router", headers=env.customer).json()
    assert router["enabled"] is False and router["candidate_models"] == []
    decision = env.client.post("/api/model-router/decide", headers=env.customer, json={"prompt": "Hello"})
    assert decision.status_code == 503
    chat = env.client.post("/api/playground/chat", headers=env.customer,
                          json={"model": "gpt-5.4-mini", "messages": [{"role": "user", "content": "Hello"}]})
    assert chat.status_code == 422


def test_local_models_and_garden_share_validated_availability(env, tmp_path, monkeypatch):
    from aiflux.turnstile_exchange import ensure_model_garden_seeded

    env.settings.local_auth_enabled = True
    env.settings.catalog_configured = False
    with Session(env.db_engine) as db:
        ensure_model_garden_seeded(db)
        row = db.get(ManagedModelEndpoint, "gpt-5.4-mini")
        row.backend_model = "actual-mini-deployment"
        row.endpoint_url = "https://gateway.test/v1"
        db.commit()
    install_inventory(env.settings, tmp_path / "verified.json", [
        ("gpt-5.4-mini", "actual-mini-deployment", "https://gateway.test/v1", ["chat"], 64),
    ])
    models = env.client.get("/api/models", headers=env.customer).json()["items"]
    garden = env.client.get("/api/model-garden", headers=env.customer).json()["items"]
    assert [m["id"] for m in models] == [m["id"] for m in garden] == ["gpt-5.4-mini"]
    assert models[0]["max_completion_tokens"] == 64
    assert "auto" not in [m["id"] for m in models]

    import httpx

    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Actual test response"}}]})

    monkeypatch.setattr("aiflux.turnstile_exchange.httpx.post", post)
    env.settings.environment = "development"
    env.settings.upstream_apim_url = "https://unused-wrong-gateway.test"
    env.settings.upstream_apim_key = "synthetic-test-only-key"
    body = {"model": "gpt-5.4-mini", "max_completion_tokens": 512,
            "messages": [{"role": "user", "content": "Hello"}]}
    chat = env.client.post("/api/playground/chat", headers=env.customer, json=body)
    assert chat.status_code == 200
    assert chat.json()["reply"] == "Actual test response"
    assert calls == [("https://gateway.test/v1/chat/completions", {
        "model": "actual-mini-deployment", "max_completion_tokens": 64,
        "messages": [{"role": "user", "content": "Hello"}],
    })]
    monkeypatch.setattr("aiflux.turnstile_exchange.httpx.post", lambda *a, **k: httpx.Response(503))
    failed = env.client.post("/api/playground/chat", headers=env.customer, json=body)
    assert failed.status_code == 503
    assert "no completion was generated" in failed.json()["detail"]


def test_catalog_flags_cannot_enable_models_not_accepted_by_catalog_source(env, tmp_path):
    from aiflux.turnstile_exchange import ensure_model_garden_seeded

    with Session(env.db_engine) as db:
        ensure_model_garden_seeded(db)
        row = db.get(ManagedModelEndpoint, "gpt-5.4-mini")
        row.endpoint_url = "https://gateway.test/v1"
        db.commit()
    install_inventory(env.settings, tmp_path / "verified.json", [
        ("gpt-5.4-mini", "gpt-5.4-mini", "https://gateway.test/v1", ["chat"], 64),
    ])
    assert env.settings.catalog_configured  # Its accepted source contains only test-alias.
    assert env.client.get("/api/models", headers=env.customer).json()["items"] == []
    assert env.client.get("/api/model-garden", headers=env.customer).json()["items"] == []
    chat = env.client.post("/api/playground/chat", headers=env.customer, json={
        "model": "gpt-5.4-mini", "messages": [{"role": "user", "content": "Hello"}],
    })
    assert chat.status_code == 422


def test_parent_inventory_denial_provenance_is_not_successful_project_read(env):
    inventory = FoundryInventory.load(env.settings)
    assert inventory.project_deployments_read == "PermissionDenied"
    assert inventory.route("test-alias") is not None  # Verified ARM parent, zero connections.


def test_collector_exact_scope_pagination_and_permission_denial(env):
    settings = env.settings
    project = settings.foundry_project_resource_id
    account = project.rsplit("/projects/", 1)[0]
    endpoint = settings.foundry_project_endpoint
    calls = []

    def read(url, stage, audience):
        calls.append((url, stage, audience))
        if stage == "account":
            return {"id": account, "properties": {"provisioningState": "Succeeded"}}
        if stage == "project":
            return {"id": project, "properties": {"provisioningState": "Succeeded", "endpoints": {"AI Foundry API": endpoint}}}
        if stage == "connections":
            return {"value": []}
        if stage == "project deployments":
            raise InventoryReadError(stage, permission_denied=True)
        if "page=2" in url:
            return {"value": []}
        return {"value": [{
            "id": account + "/deployments/actual-name", "name": "actual-name",
            "properties": {"model": {"name": "provider-name", "version": "1", "format": "OpenAI"},
                           "provisioningState": "Succeeded", "currentCapacity": 1,
                           "capabilities": {"chatCompletion": "true"}},
        }], "nextLink": url + "&page=2"}

    evidence = collect(endpoint, project, read)
    assert evidence["project_deployments_read"] == "PermissionDenied"
    assert evidence["deployments"][0]["name"] == "actual-name"
    assert evidence["deployments"][0]["model_name"] == "provider-name"
    assert evidence["routes"] == []
    assert calls[-1] == (endpoint + "/deployments?api-version=v1", "project deployments", "https://ai.azure.com")
    assert any("page=2" in url for url, _, _ in calls)

    def failed(url, stage, audience):
        if stage == "project deployments":
            raise InventoryReadError(stage)
        return read(url, stage, audience)

    with pytest.raises(InventoryReadError):
        collect(endpoint, project, failed)


def test_collector_does_not_follow_cross_resource_pagination(env):
    project = env.settings.foundry_project_resource_id
    account = project.rsplit("/projects/", 1)[0]
    endpoint = env.settings.foundry_project_endpoint

    def read(url, stage, audience):
        if stage == "account":
            return {"id": account, "properties": {"provisioningState": "Succeeded"}}
        if stage == "project":
            return {"id": project, "properties": {"provisioningState": "Succeeded", "endpoints": {"AI Foundry API": endpoint}}}
        return {"value": [], "nextLink": "https://untrusted.test/deployments"}

    with pytest.raises(InventoryReadError, match="pagination scope"):
        collect(endpoint, project, read)


@pytest.mark.parametrize("error, expected", [
    ('ERROR: {"error":{"code":"PermissionDenied","message":""}}', True),
    ('ERROR: {"error":{"code":"AuthorizationFailed"}}', False),
    ('ERROR: network timeout', False),
    ('ERROR: PermissionDenied mentioned without a structured service code', False),
])
def test_cli_permission_fallback_requires_structured_project_error(monkeypatch, capsys, error, expected):
    from types import SimpleNamespace
    from gateway.tools import verify_foundry_inventory as collector

    monkeypatch.setattr(collector.sys, "argv", ["verify", "--project-endpoint", "https://example.test",
                                               "--project-resource-id", "unused"])
    monkeypatch.setattr(collector.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1, stdout="", stderr=error))
    observed = []

    def exercise_read(endpoint, resource_id, read):
        for stage in ("project deployments", "account"):
            with pytest.raises(InventoryReadError) as exc:
                read("https://example.test/deployments", stage, "https://ai.azure.com")
            observed.append(exc.value.permission_denied)
        return {"routes": []}

    monkeypatch.setattr(collector, "collect", exercise_read)
    assert collector.main() == 0
    assert observed == [expected, False]
    captured = capsys.readouterr()
    assert error not in captured.out and error not in captured.err