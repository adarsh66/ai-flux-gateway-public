"""Existing admin endpoint: strict CAS defaults-only migration, offline."""
from copy import deepcopy
import json

from sqlalchemy.orm import Session

from aiflux.default_limits import POC_DEFAULT_LIMITS, global_defaults_status
from aiflux.models import GatewaySettingsRevision
from aiflux.schemas import PocGatewayConfiguration, PocLimits
from test_poc_controls import URL, poc, save


def test_status_rejects_bool_string_and_pending_defaults():
    stored = {"configuration": {"schema_version": 3, "defaults": dict(POC_DEFAULT_LIMITS)}}
    assert global_defaults_status(stored, 2, 2)["published_match"]
    assert not global_defaults_status(stored, 2, 1)["published_match"]
    for bad in (True, "60", 60.0):
        broken = deepcopy(stored)
        broken["configuration"]["defaults"]["rpm"] = bad
        assert not global_defaults_status(broken, 2, 2)["strict_match"]


def test_existing_put_migrates_only_defaults_and_preserves_pricing_attempts(env, poc):
    config = PocGatewayConfiguration(defaults=PocLimits(tpm=2048, token_quota=10000, request_quota=1000))
    assert save(env, config.model_dump(mode="json")).status_code == 200
    with Session(env.db_engine) as db:
        row = db.query(GatewaySettingsRevision).filter_by(scope="dev-unified", version=1).one()
        stored = json.loads(row.configuration)
        stored["auto_pricing"] = {"attempted_hash": "retained", "attempt_predecessor_hash": "exact", "applied": None}
        stored["unknown"] = [True, None, {"preserved": 1}]
        row.configuration = json.dumps(stored)
        db.commit()
        original = row.configuration
    payload = {"expected_version": 1, "configuration": config.model_dump(mode="json"),
               "reason": "User-authorized four quota defaults", "defaults_only": True}
    payload["configuration"]["defaults"].update(POC_DEFAULT_LIMITS)
    before = env.client.get("/api/admin/gateway-settings", headers=env.admin).json()["items"][0]
    assert not before["global_defaults_status"]["strict_match"]
    response = env.client.put(URL, headers=env.admin, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["global_defaults_status"]["published_match"]
    assert response.json()["global_defaults_status"]["completion_allowance"] == 1024
    assert not response.json()["global_defaults_status"]["inline_enforcement_verified"]
    with Session(env.db_engine) as db:
        old = db.query(GatewaySettingsRevision).filter_by(scope="dev-unified", version=1).one()
        new = db.query(GatewaySettingsRevision).filter_by(scope="dev-unified", version=2).one()
        assert old.configuration == original
        changed = json.loads(new.configuration)
        changed["configuration"]["defaults"] = stored["configuration"]["defaults"]
        assert changed == stored
    assert env.client.put(URL, headers=env.admin, json=payload).status_code == 409
    assert env.client.put(URL, headers=env.customer, json=payload).status_code == 403


def test_defaults_only_rejects_override_or_safety_edits_and_boolean_flag(env, poc):
    assert save(env).status_code == 200
    config = PocGatewayConfiguration().model_dump(mode="json")
    payload = {"expected_version": 1, "configuration": config,
               "reason": "Defaults only", "defaults_only": True}
    payload["configuration"]["safety"]["hate"] = 0
    assert env.client.put(URL, headers=env.admin, json=payload).status_code == 409
    payload["defaults_only"] = "true"
    assert env.client.put(URL, headers=env.admin, json=payload).status_code == 422
    with Session(env.db_engine) as db:
        assert db.query(GatewaySettingsRevision).count() == 1