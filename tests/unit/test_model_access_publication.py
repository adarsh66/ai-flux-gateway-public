"""In-memory remote fragment faults; no network, SQL service or credentials."""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from aiflux import model_access as access
from aiflux import model_access_publisher as publisher
from aiflux import auto_pricing
from aiflux.models import Organization, TeamSubscription, ModelAccessPublication, GatewaySettingsRevision
from aiflux.settings_envelope import parse
from tests.unit.test_auto_shared_pricing import env


def prepare(p, monkeypatch):
    p.settings.model_access_enabled = True
    oid, sid = str(uuid4()), str(uuid4())
    p.db.add(Organization(id=oid, name="test", tenant_id=str(uuid4())))
    p.db.flush()
    p.db.add(TeamSubscription(id=sid, organization_id=oid, name="test", team="t", state="pending",
        desired_state="active", idempotency_key=str(uuid4())))
    access.queue(p.db)
    p.db.commit()
    monkeypatch.setattr(access, "catalog", lambda *_: [{"id": a, "model_kind": "chat", "globally_enabled": True} for a in "abcdef"])
    return oid, sid


def test_price_access_price_preserves_all_siblings(env, monkeypatch):
    p = env
    oid, sid = prepare(p, monkeypatch)
    assert auto_pricing.reconcile(p.db, p.settings, p.apim)
    assert publisher.reconcile(p.db, p.settings, p.apim)
    controls, price, entitlements = parse(p.apim.value)
    assert entitlements["bindings"] == {sid: oid}
    assert p.db.get(TeamSubscription, sid).state == "active"
    p.rates["a"]["input"] = "9"
    assert auto_pricing.reconcile(p.db, p.settings, p.apim, immediate=True)
    controls2, price2, entitlements2 = parse(p.apim.value)
    assert entitlements2 == entitlements and controls == controls2
    assert price2["prices"]["a"]["input"] == "9"
    assert json.loads(p.db.scalar(select(GatewaySettingsRevision)).configuration)["unrelated"] == {"keep": 42}


@pytest.mark.parametrize("fault", ["read", "put", "ambiguous"])
def test_fault_backoff_lastgood_and_readback(env, monkeypatch, fault):
    p = env
    prepare(p, monkeypatch)
    p.apim.fault = fault
    before = p.apim.value
    result = publisher.reconcile(p.db, p.settings, p.apim)
    job = p.db.get(ModelAccessPublication, "default")
    if fault == "ambiguous":
        assert result and job.state == "applied" and p.apim.puts == 1
        assert not publisher.reconcile(p.db, p.settings, p.apim)
        assert p.apim.puts == 1
    else:
        assert not result and job.state == "error" and job.next_attempt_at
        assert p.apim.value == before and not job.applied_json
        reads = p.apim.reads
        assert not publisher.reconcile(p.db, p.settings, p.apim)
        assert p.apim.reads == reads
        p.apim.fault = None
        assert publisher.reconcile(p.db, p.settings, p.apim, immediate=True)


def test_foreign_fragment_never_overwritten(env, monkeypatch):
    p = env
    prepare(p, monkeypatch)
    p.apim.value = '<fragment><set-variable name="foreign" value="data" /></fragment>'
    assert not publisher.reconcile(p.db, p.settings, p.apim)
    assert p.apim.puts == 0
    assert p.db.get(ModelAccessPublication, "default").error == "publication_conflict"


def test_worker_applied_catalog_future_default_disable_remove_and_noop(env, monkeypatch):
    p = env
    oid, sid = prepare(p, monkeypatch)
    models = [{"id": "a", "model_kind": "chat", "globally_enabled": True}]
    monkeypatch.setattr(access, "catalog", lambda *_: models)
    assert publisher.reconcile(p.db, p.settings, p.apim)
    assert access.preference(p.db, oid)["version"] == 0
    models.append({"id": "future", "model_kind": "chat", "globally_enabled": True})
    assert publisher.reconcile(p.db, p.settings, p.apim)
    projection = parse(p.apim.value)[2]
    assert access.authorize_projection(projection, sid, "future")
    assert access.filter_items(p.db, oid, [{"id": "future"}]) == [{"id": "future"}]
    assert projection["generation"] == 2
    models[1]["globally_enabled"] = False
    assert publisher.reconcile(p.db, p.settings, p.apim)
    assert parse(p.apim.value)[2]["catalog"] == ["a"]
    models.clear()  # inventory removal/refresh to zero candidates
    assert publisher.reconcile(p.db, p.settings, p.apim)
    assert parse(p.apim.value)[2]["catalog"] == []
    reads, puts = p.apim.reads, p.apim.puts
    assert not publisher.reconcile(p.db, p.settings, p.apim)
    assert (p.apim.reads, p.apim.puts) == (reads, puts)


def test_new_job_between_intent_and_reacquire_is_not_lost(env, monkeypatch):
    p = env
    prepare(p, monkeypatch)
    assert not publisher.reconcile(p.db, p.settings, p.apim, prepared=True)
    old_generation = p.db.get(ModelAccessPublication, "default").generation
    access.queue(p.db)
    p.db.commit()
    assert publisher.reconcile(p.db, p.settings, p.apim)
    job = p.db.get(ModelAccessPublication, "default", populate_existing=True)
    assert job.generation == job.applied_generation == old_generation + 1
    assert parse(p.apim.value)[2]["generation"] == job.generation


def test_generation_cas_never_marks_concurrent_queue_applied(env, monkeypatch):
    p = env
    prepare(p, monkeypatch)
    original = p.apim.put_settings_fragment
    def competing(scope, value, etag):
        original(scope, value, etag)
        # Deliberately break the fixture's single transaction lock to exercise
        # the defensive CAS. Not a real PostgreSQL concurrency claim.
        access.queue(p.db)
        p.db.commit()
    monkeypatch.setattr(p.apim, "put_settings_fragment", competing)
    assert not publisher.reconcile(p.db, p.settings, p.apim)
    job = p.db.get(ModelAccessPublication, "default", populate_existing=True)
    assert job.state == "pending" and job.generation > job.applied_generation
    monkeypatch.setattr(p.apim, "put_settings_fragment", original)
    assert publisher.reconcile(p.db, p.settings, p.apim)


def test_catalog_republish_etag_conflict_keeps_job_and_lastgood(env, monkeypatch):
    from aiflux.apim import ApimError
    p = env
    prepare(p, monkeypatch)
    assert publisher.reconcile(p.db, p.settings, p.apim)
    lastgood = p.db.get(ModelAccessPublication, "default").applied_json
    monkeypatch.setattr(access, "catalog", lambda *_: [{"id": "future", "model_kind": "chat", "globally_enabled": True}])
    original = p.apim.put_settings_fragment
    def reject(scope, value, etag):
        assert etag != "*"
        raise ApimError(412)
    monkeypatch.setattr(p.apim, "put_settings_fragment", reject)
    assert not publisher.reconcile(p.db, p.settings, p.apim)
    job = p.db.get(ModelAccessPublication, "default")
    assert job.state == "error" and job.applied_json == lastgood
    monkeypatch.setattr(p.apim, "put_settings_fragment", original)
    assert publisher.reconcile(p.db, p.settings, p.apim, immediate=True)