"""Offline fault fixtures: no cloud, inference, financial records or new tables."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import threading
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from aiflux import auto_pricing as pricing
from aiflux.apim import ApimError
from aiflux.config import Settings
from aiflux.gateway_settings import fingerprint, render_revision
from aiflux.models import Base, GatewaySettings, GatewaySettingsRevision
from aiflux.poc_controls import render
from aiflux.schemas import PocGatewayConfiguration

POOL = ["a", "b", "c", "d", "e", "f"]


@pytest.fixture
def env(monkeypatch):
    settings = Settings(_env_file=None, auto_pricing_sync_enabled=True, auto_routing_enabled=True,
        gateway_controls_poc_enabled=True, gateway_controls_v2_enabled=False,
        gateway_settings_scopes=["dev-unified"])
    snapshot = {"version": "a" * 64, "candidates": [{"id": x} for x in POOL]}
    monkeypatch.setattr(pricing.auto_snapshot, "defaults", lambda _: snapshot)
    monkeypatch.setattr(pricing.rate_card, "accepted_scopes", lambda _: [(x, {"model": x}) for x in POOL])
    rates = {x: {"input": "1", "output": "2", "status": "configured",
                 "revision": "rate-card-v1"} for x in POOL}
    monkeypatch.setattr(pricing.rate_card, "display_price", lambda v, e, scope: rates[scope["model"]])
    monkeypatch.setattr(pricing.rate_card, "revision_label", lambda v: "rate-card-v" + str(v))
    monkeypatch.setattr(pricing.rate_card, "load_state", lambda db: (1, []))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    controls = render(PocGatewayConfiguration(), [])
    db.add_all([GatewaySettings(scope="rate-card", version=1),
                GatewaySettings(scope="dev-unified", version=12, published_version=12),
                GatewaySettingsRevision(scope="dev-unified", version=12, reason="existing",
                    object_id="original", state="published", base_hash=fingerprint(controls), base_etag="e1",
                    configuration=json.dumps({"configuration": PocGatewayConfiguration().model_dump(mode="json"),
                                              "bindings": [], "unrelated": {"keep": 42}}))])
    db.commit()
    class Apim:
        value = controls
        etag = "e1"
        puts = 0
        fault = None
        reads = 0

        def get_settings_fragment(self, scope):
            assert scope == "dev-unified"
            self.reads += 1
            if self.fault == "read":
                raise ApimError(503)
            return self.value, self.etag

        def put_settings_fragment(self, scope, value, etag):
            assert scope == "dev-unified" and etag == self.etag and etag != "*"
            self.puts += 1
            if self.fault == "put":
                raise ApimError(503)
            self.value, self.etag = value, "e" + str(self.puts + 1)
            if self.fault == "ambiguous":
                raise ApimError(504)
    apim = Apim()
    yield SimpleNamespace(db=db, settings=settings, apim=apim, rates=rates, controls=controls)
    db.close()
    engine.dispose()


def test_price_only_branch_cannot_execute_detached_quota_or_safety(env):
    p = pricing.projection(env.settings, 1, [])
    xml = pricing.envelope(env.controls, p)
    root = ET.fromstring(xml)
    assert len(root) == 1 and len(root[0]) == 2
    assert root[0][0][0].tag == "set-variable" and len(root[0][0]) == 1
    assert len(root[0][0].findall(".//quota-by-key")) == 0
    assert fingerprint(pricing.controls_only(xml)) == fingerprint(env.controls)
    assert len(xml.encode()) <= 65536
    assert pricing.envelope(env.controls, None) == env.controls


def test_projection_zero_null_optional_and_scorer_exclusion(env):
    env.rates["a"].update(input="0", cached="0.00000001")
    env.rates["b"] = None
    p = pricing.projection(env.settings, 1, [])
    assert set(p["prices"]) == set(POOL) and "Decision-1" not in p["prices"]
    assert p["prices"]["a"]["input"] == "0"
    assert p["prices"]["a"]["cached"] == "0.00000001"
    assert "write" not in p["prices"]["a"] and p["prices"]["b"] is None
    assert p == pricing.projection(env.settings, 1, [])
    assert pricing.projection(env.settings, 0, [])["source"] == "packaged-default"


def test_publish_initial_noop_and_preserve_other_json_fields(env):
    assert pricing.reconcile(env.db, env.settings, env.apim)
    assert env.apim.puts == 1
    assert pricing.reconcile(env.db, env.settings, env.apim)
    assert env.apim.puts == 1
    row = env.db.scalar(select(GatewaySettingsRevision))
    assert json.loads(row.configuration)["unrelated"] == {"keep": 42}
    assert row.version == 12 and row.state == "published"
    assert fingerprint(env.apim.value) == fingerprint(render_revision("dev-unified", row))
    assert pricing.status(env.db, env.settings)["state"] == "applied"


@pytest.mark.parametrize("fault", ["read", "put"])
def test_failed_sync_lastgood_bounded_backoff_and_automatic_recovery(env, fault):
    assert pricing.reconcile(env.db, env.settings, env.apim)
    old = env.apim.value
    env.rates["a"]["input"] = "9"
    env.apim.fault = fault
    assert not pricing.reconcile(env.db, env.settings, env.apim, immediate=True)
    assert env.apim.value == old
    assert pricing.status(env.db, env.settings)["state"] == "pending"
    reads = env.apim.reads
    assert not pricing.reconcile(env.db, env.settings, env.apim)
    assert env.apim.reads == reads
    env.apim.fault = None
    row = env.db.scalar(select(GatewaySettingsRevision))
    state = pricing.metadata(row)
    state["next_attempt_at"] = None
    pricing.store(row, state)
    env.db.commit()
    assert pricing.reconcile(env.db, env.settings, env.apim)
    assert pricing.metadata(row)["applied"]["prices"]["a"]["input"] == "9"


def test_ambiguous_completed_put_readback_no_duplicate_put(env):
    env.apim.fault = "ambiguous"
    assert pricing.reconcile(env.db, env.settings, env.apim)
    assert env.apim.puts == 1
    assert pricing.reconcile(env.db, env.settings, env.apim)
    assert env.apim.puts == 1


def test_foreign_drift_never_overwritten(env):
    env.apim.value = '<fragment><set-variable name="foreign" value="x" /></fragment>'
    old = env.apim.value
    assert not pricing.reconcile(env.db, env.settings, env.apim)
    assert env.apim.puts == 0 and env.apim.value == old


def test_unreadable_saved_card_cannot_publish_defaults_over_lastgood(env, monkeypatch):
    assert pricing.reconcile(env.db, env.settings, env.apim)
    monkeypatch.setattr(pricing.rate_card, "load_state", lambda db: (0, []))
    old = env.apim.value
    assert not pricing.reconcile(env.db, env.settings, env.apim)
    assert env.apim.value == old and env.apim.puts == 1


def test_actual_worker_tick_and_clean_shutdown(monkeypatch):
    from aiflux import auto_pricing_worker as worker
    calls = []
    stop = asyncio.Event()
    def tick(settings, apim):
        calls.append(True)
        stop.set()
    monkeypatch.setattr(worker, "reconcile_once", tick)
    asyncio.run(worker.run_worker(SimpleNamespace(auto_pricing_reconcile_seconds=5), None, stop))
    assert calls == [True]


def test_crash_completed_old_intent_superseded_without_stale_overwrite(env):
    assert pricing.reconcile(env.db, env.settings, env.apim)
    row = env.db.scalar(select(GatewaySettingsRevision))
    env.rates["a"]["input"] = "3"
    old_intent = pricing.projection(env.settings, 1, [])
    remote = pricing.envelope(env.controls, old_intent)
    state = pricing.metadata(row)
    state["attempted_hash"] = fingerprint(remote)
    pricing.store(row, state)
    env.db.commit()
    env.apim.value, env.apim.etag = remote, "external-etag"
    env.rates["a"]["input"] = "4"
    assert pricing.reconcile(env.db, env.settings, env.apim)
    assert pricing.metadata(row)["applied"]["prices"]["a"]["input"] == "4"


def test_pending_controls_rebased_not_published_or_erased(env):
    assert pricing.reconcile(env.db, env.settings, env.apim)
    row = env.db.scalar(select(GatewaySettingsRevision))
    config = json.loads(row.configuration)
    config["configuration"]["defaults"]["rpm"] = 59
    row.configuration = json.dumps(config)
    row.state = "failed"
    row.base_hash, row.base_etag = fingerprint(env.apim.value), env.apim.etag
    env.db.commit()
    env.rates["b"]["input"] = "5"
    assert pricing.reconcile(env.db, env.settings, env.apim)
    assert row.state == "failed"
    assert fingerprint(pricing.controls_only(env.apim.value)) == fingerprint(env.controls)
    assert row.base_hash == fingerprint(env.apim.value)
    assert json.loads(row.configuration)["configuration"]["defaults"]["rpm"] == 59


def test_unknown_envelope_condition_rejected(env):
    p = pricing.projection(env.settings, 1, [])
    value = pricing.envelope(env.controls, p).replace('aiflux-auto-price-only', 'foreign-mode')
    with pytest.raises(ValueError):
        pricing.controls_only(value)


@pytest.mark.parametrize("change", ["schema", "hash", "extra", "pool", "dimension", "numeric", "alias"])
def test_closed_typed_projection_rejects_invalid_transport(env, change):
    value = pricing.projection(env.settings, 1, [])
    if change == "schema":
        value["schema"] = True
    elif change == "hash":
        value["sha256"] = "0" * 64
    elif change == "extra":
        value["xml"] = "untrusted"
    elif change == "pool":
        value["prices"].pop("f")
    elif change == "dimension":
        value["prices"]["a"]["output"] = None
    elif change == "numeric":
        value["prices"]["a"]["input"] = 0
    else:
        value["prices"]["Decision-1"] = value["prices"].pop("f")
    with pytest.raises(ValueError):
        pricing.envelope(env.controls, value)


def test_transport_roundtrip_verbatim_escaping_and_hash(env):
    env.rates["a"].update(source_url='https://example.test/?a=1&b="2"', source_model='Line\n"quoted"')
    # Fixture projection preserves normal provenance from the actual producer.
    value = pricing.projection(env.settings, 1, [])
    value["prices"]["a"]["source_model"] = 'Line\n"quoted"'
    value["sha256"] = hashlib.sha256(pricing.compact({k: v for k, v in value.items() if k != "sha256"}).encode()).hexdigest()
    expression = ET.fromstring(pricing.envelope(env.controls, value))[0][0][0].get("value")
    assert expression.startswith('@(@"') and expression.endswith('")')
    decoded = json.loads(expression[4:-2].replace('""', '"'))
    assert pricing.validate_projection(decoded) == value


def test_projection_actual_six_catalog_parity_defaults_configured_reset_unknown(monkeypatch):
    from test_auto_snapshot import configured
    from aiflux import auto_snapshot, rate_card
    settings = configured()
    settings.auto_pricing_sync_enabled = True
    scopes = dict(rate_card.accepted_scopes(settings))
    first = pricing.projection(settings, 0, [])
    alias = "gpt-5.4-mini"
    key = rate_card.key_of(scopes[alias])
    entries = [{"model": key[0], "provider": key[1], "region": key[2],
                "origin": "configured", "valid_from": datetime.now(UTC),
                "input": "0", "output": "0.00000001", "cached": "0"}]
    changed = pricing.projection(settings, 1, entries)
    for candidate, price in changed["prices"].items():
        catalog = rate_card.display_price(1, entries, scopes[candidate])
        assert {f: price.get(f) for f in rate_card.FIELDS} == {
            f: rate_card.fmt(rate_card.parse_rate(catalog[f])) if catalog.get(f) is not None else None
            for f in rate_card.FIELDS}
        assert price["status"] == catalog["status"] and price["revision"] == catalog["revision"]
    assert changed["prices"][alias]["input"] == "0"
    reset = pricing.projection(settings, 2, [])
    assert {f: reset["prices"][alias].get(f) for f in rate_card.FIELDS} == {
        f: first["prices"][alias].get(f) for f in rate_card.FIELDS}
    assert first["pool_version"] == changed["pool_version"] == reset["pool_version"]
    original = rate_card.display_price
    monkeypatch.setattr(rate_card, "display_price", lambda v, e, s: None if s["model"] == alias else original(v, e, s))
    assert pricing.projection(settings, 3, entries)["prices"][alias] is None
    monkeypatch.setattr(rate_card, "display_price", lambda *a: None)
    unknown = auto_snapshot.defaults(settings)
    assert all(c["price"] is None for c in unknown["candidates"])
    assert set(unknown["profiles"]) == {"balanced", "cost", "quality"}
    for profile in unknown["profiles"].values():
        assert len(profile["candidate_models"]) == 6
    assert "do not invent prices" in unknown["profiles"]["cost"]["instructions"]


def test_cas_failure_retains_old_then_automatic_retry(env):
    assert pricing.reconcile(env.db, env.settings, env.apim)
    old = env.apim.value
    env.rates["a"]["input"] = "8"
    original = env.apim.put_settings_fragment
    def stale(scope, value, etag):
        env.apim.etag = "new-etag"
        raise ApimError(412)
    env.apim.put_settings_fragment = stale
    assert not pricing.reconcile(env.db, env.settings, env.apim, immediate=True)
    assert env.apim.value == old
    assert pricing.metadata(env.db.scalar(select(GatewaySettingsRevision)))["applied"]["prices"]["a"]["input"] == "1"
    env.apim.put_settings_fragment = original
    assert pricing.reconcile(env.db, env.settings, env.apim, immediate=True)
    assert pricing.metadata(env.db.scalar(select(GatewaySettingsRevision)))["applied"]["prices"]["a"]["input"] == "8"


def test_two_real_sessions_serialize_put_and_refresh_stale_json(env, tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "replicas.db").as_posix(),
                           connect_args={"check_same_thread": False, "timeout": 10})
    Base.metadata.create_all(engine)
    original = env.db.scalar(select(GatewaySettingsRevision))
    with Session(engine) as seed:
        seed.add_all([GatewaySettings(scope="rate-card", version=1),
                      GatewaySettings(scope="dev-unified", version=12, published_version=12),
                      GatewaySettingsRevision(scope="dev-unified", version=12, reason="existing",
                          object_id="original", state="published", base_hash=original.base_hash,
                          base_etag="e1", configuration=original.configuration)])
        seed.commit()
    barrier = threading.Barrier(2)
    def replica():
        with Session(engine, expire_on_commit=False) as db:
            # Both replicas cache OLD JSON before either publishes.
            stale = db.scalar(select(GatewaySettingsRevision))
            db.commit()
            barrier.wait(timeout=10)
            result = pricing.reconcile(db, env.settings, env.apim, immediate=True)
            return result, pricing.metadata(stale)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(replica) for _ in range(2)]
            results = [f.result(timeout=20) for f in futures]
        assert all(ok for ok, _ in results) and env.apim.puts == 1
        assert all(state["state"] == "applied" for _, state in results)
        with Session(engine) as check:
            row = check.scalar(select(GatewaySettingsRevision))
            assert json.loads(row.configuration)["unrelated"] == {"keep": 42}
            assert fingerprint(env.apim.value) == fingerprint(render_revision("dev-unified", row))
    finally:
        engine.dispose()


def test_controls_save_preserves_applied_prices_and_unknown_metadata(env):
    from aiflux.gateway_settings import save_poc
    from aiflux.schemas import GatewaySettingsUpdate
    assert pricing.reconcile(env.db, env.settings, env.apim)
    old_price = deepcopy(pricing.metadata(env.db.scalar(select(GatewaySettingsRevision)))["applied"])
    config = PocGatewayConfiguration()
    config.defaults.rpm = 59
    result = save_poc(env.db, env.settings, env.apim, SimpleNamespace(object_id="admin", organization_id="org"),
                     "dev-unified", GatewaySettingsUpdate(expected_version=12, configuration=config, reason="offline test"))
    assert result.version == 13 and result.published_version == 13
    row = env.db.scalar(select(GatewaySettingsRevision).where(GatewaySettingsRevision.version == 13))
    assert pricing.metadata(row)["applied"] == old_price
    assert json.loads(row.configuration)["unrelated"] == {"keep": 42}
    assert fingerprint(pricing.controls_only(env.apim.value)) == fingerprint(render(config, []))


def test_postcommit_unexpected_sync_failure_is_pending_not_save_failure(env, monkeypatch):
    monkeypatch.setattr(pricing, "reconcile", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("private")))
    state = pricing.after_save(env.db, env.settings, env.apim)
    assert state["state"] == "pending" and state["access_gated"] is False
    assert "private" not in json.dumps(state)
    assert env.db.get(GatewaySettings, "rate-card").version == 1


def test_worker_survives_failed_tick_and_starts_without_publication_receipt(monkeypatch):
    from aiflux import auto_pricing_worker as worker
    stop = asyncio.Event()
    calls = []
    def tick(*a):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("private")
        stop.set()
    monkeypatch.setattr(worker, "reconcile_once", tick)
    asyncio.run(worker.run_worker(SimpleNamespace(auto_pricing_reconcile_seconds=0), None, stop))
    assert calls == [True, True]


def test_no_rate_head_uses_packaged_fallback_without_remote_write(env):
    env.db.delete(env.db.get(GatewaySettings, "rate-card"))
    env.db.commit()
    assert not pricing.reconcile(env.db, env.settings, env.apim)
    assert env.apim.reads == env.apim.puts == 0
    assert pricing.status(env.db, env.settings)["source"] == "packaged-default"


@pytest.mark.parametrize("scope", ["rate-card", "dev-unified"])
def test_stale_head_compare_and_swap_never_downgrades_new_version(env, monkeypatch, scope):
    from aiflux import gateway_settings
    original = gateway_settings.locked_head
    def stale(db, requested):
        head = original(db, requested)
        if requested == scope:
            # Simulate a writer committing after a SELECT on a dialect without
            # FOR UPDATE. The subsequent conditional no-op must not reset it.
            from sqlalchemy import update
            db.execute(update(GatewaySettings).where(GatewaySettings.scope == scope)
                       .values(version=head.version + 1).execution_options(synchronize_session=False))
            db.commit()
        return head
    monkeypatch.setattr(gateway_settings, "locked_head", stale)
    before = env.db.get(GatewaySettings, scope).version
    assert not pricing.reconcile(env.db, env.settings, env.apim)
    env.db.expire_all()
    assert env.db.get(GatewaySettings, scope).version == before + 1
    assert env.apim.reads == env.apim.puts == 0


def test_controls_writer_between_intent_and_reacquisition_never_restores_old_controls(env, monkeypatch):
    from aiflux.gateway_settings import save_poc
    from aiflux.schemas import GatewaySettingsUpdate
    assert pricing.reconcile(env.db, env.settings, env.apim)
    env.rates["a"]["input"] = "6"
    commit = env.db.commit
    interleaved = []
    config = PocGatewayConfiguration()
    config.defaults.rpm = 59
    def commit_with_controls_writer():
        commit()
        if not interleaved:
            interleaved.append(True)
            save_poc(env.db, env.settings, env.apim, SimpleNamespace(object_id="admin", organization_id="org"),
                     "dev-unified", GatewaySettingsUpdate(expected_version=12, configuration=config,
                                                         reason="offline interleave"))
    monkeypatch.setattr(env.db, "commit", commit_with_controls_writer)
    # First bounded attempt may only prepare a NEW intent after controls changed.
    pricing.reconcile(env.db, env.settings, env.apim, immediate=True)
    assert pricing.reconcile(env.db, env.settings, env.apim, immediate=True)
    row = env.db.scalar(select(GatewaySettingsRevision).where(GatewaySettingsRevision.version == 13))
    assert fingerprint(pricing.controls_only(env.apim.value)) == fingerprint(render(config, []))
    assert pricing.metadata(row)["applied"]["prices"]["a"]["input"] == "6"
    assert pricing.metadata(row)["attempt_predecessor_hash"] is None