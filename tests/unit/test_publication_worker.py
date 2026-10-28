"""Exercise the real publisher via the timer worker without Azure calls."""

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux.gateway_settings import BOOTSTRAP, fingerprint
from aiflux.models import GatewaySettings, GatewaySettingsRevision
from aiflux.publication_worker import reconcile_pending


class Fragments:
    def __init__(self):
        self.value = BOOTSTRAP.read_text()
        self.etag = '"1"'
        self.writes = 0

    def get_settings_fragment(self, scope):
        return self.value, self.etag

    def put_settings_fragment(self, scope, value, etag):
        assert etag == self.etag
        self.value = value
        self.etag = '"2"'
        self.writes += 1


def intent(env, db, apim):
    env.settings.gateway_settings_scopes = ["dev-openai"]
    db.add(GatewaySettings(scope="dev-openai", version=1))
    db.add(GatewaySettingsRevision(
        scope="dev-openai", version=1, object_id="33333333-3333-4333-8333-333333333333",
        reason="Previously approved request", base_hash=fingerprint(apim.value), base_etag=apim.etag,
        configuration=json.dumps({"safety_threshold": 1, "rpm": 2, "tpm": 1024,
                                  "token_quota": 10000, "quota_period": "Daily"}),
    ))
    db.commit()


def test_retries_current_intent_and_skips_published(env):
    apim = Fragments()
    with Session(env.db_engine) as db:
        intent(env, db, apim)
        assert reconcile_pending(db, env.settings, apim) == 1
        assert reconcile_pending(db, env.settings, apim) == 0
        assert db.scalar(select(GatewaySettingsRevision)).state == "published"
    assert apim.writes == 1


def test_drift_fails_without_overwriting_remote_policy(env):
    apim = Fragments()
    with Session(env.db_engine) as db:
        intent(env, db, apim)
        apim.value = '<fragment><set-variable name="external" value="true" /></fragment>'
        with pytest.raises(RuntimeError, match="incomplete"):
            reconcile_pending(db, env.settings, apim)
        assert db.scalar(select(GatewaySettingsRevision)).state == "failed"
    assert apim.writes == 0


def test_missing_home_organization_is_not_success(env):
    env.settings.home_tenant_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    with Session(env.db_engine) as db, pytest.raises(RuntimeError, match="bootstrapped"):
        reconcile_pending(db, env.settings, Fragments())


def test_timer_is_fail_closed_without_activation(monkeypatch):
    source = Path("services/control-plane/functions/handlers.py")
    spec = importlib.util.spec_from_file_location("publication_handlers", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv("GATEWAY_PUBLICATION_WORKER_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="not approved"):
        module.gateway_publication(None)


def test_function_binding_targets_real_handler():
    binding = json.loads(Path(
        "services/control-plane/functions/gateway_publication/function.json",
    ).read_text())
    assert binding["entryPoint"] == "gateway_publication"
    assert binding["bindings"][0]["runOnStartup"] is False