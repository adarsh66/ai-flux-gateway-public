"""Quota task tests: offline, no pricing workflow or provider traffic."""
from copy import deepcopy
import json
from uuid import uuid4
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from aiflux.default_limits import POC_DEFAULT_LIMITS, defaults_only_envelope
from aiflux.gateway_settings import migrate_poc_defaults, render_revision
from aiflux.models import GatewaySettings, GatewaySettingsRevision
from aiflux.poc_controls import effective, render
from aiflux.schemas import PocGatewayConfiguration, PocLimits, PocOverride
from test_poc_controls import poc, save


@pytest.mark.parametrize("field,ceiling", list(POC_DEFAULT_LIMITS.items()))
def test_strict_defaults_and_bounds(field, ceiling):
    assert PocLimits().model_dump()[field] == ceiling
    assert PocLimits.model_validate({field: ceiling}).model_dump()[field] == ceiling
    for invalid in (True, False, 0, -1, 1.0, str(ceiling), ceiling + 1, 2**63):
        with pytest.raises(ValidationError):
            PocLimits.model_validate({field: invalid})


def test_migration_preserves_every_other_json_field_and_input():
    stored = {"configuration": {"schema_version": 3,
        "defaults": {"rpm": 60, "tpm": 2048, "token_quota": 10000, "request_quota": 1000, "future": [1]},
        "safety": {"retain": True}, "overrides": [{"explicit": "old"}], "future": {"keep": None}},
        "bindings": [{"retain": "exact"}], "auto_pricing": {"applied": {"sha256": "exact"}, "pending": True},
        "future": ["metadata"]}
    original = deepcopy(stored)
    migrated = defaults_only_envelope(stored)
    assert stored == original
    assert migrated["configuration"]["defaults"] == {**POC_DEFAULT_LIMITS, "future": [1]}
    migrated["configuration"]["defaults"] = original["configuration"]["defaults"]
    assert migrated == original


@pytest.mark.parametrize("schema", [True, 1, 2, "3", None])
def test_no_implicit_legacy_migration(schema):
    with pytest.raises(ValueError):
        defaults_only_envelope({"configuration": {"schema_version": schema, "defaults": {}}})


def test_old_explicit_overrides_still_parse_and_unknown_sub_inherits():
    old = PocLimits(rpm=20, tpm=2048, token_quota=10000, request_quota=1000)
    org, sub = uuid4(), uuid4()
    config = PocGatewayConfiguration(overrides=[PocOverride(organization_id=org, subscription_id=sub, limits=old)])
    assert effective(config, str(org), str(sub))[0] == old
    assert effective(config, str(uuid4()), str(uuid4()))[0].model_dump() == POC_DEFAULT_LIMITS
    root = ET.fromstring(render(config, []))
    for branch in root.findall("choose")[-1]:
        assert len(branch) == 1
        quota = branch[0]
        assert quota.attrib == {"calls": quota.get("calls"), "renewal-period": "86400",
            "counter-key": '@("project-demo:" + context.Subscription.Id)'}
    assert {q.get("calls") for q in root.findall(".//quota-by-key")} == {"1000", "50000"}


def test_raw_quota_delta_preserves_every_other_byte():
    from aiflux.quota_policy_delta import inline_quota_delta
    raw = ('<policies>\r\n\t<quota-by-key calls="1000" renewal-period="86400" '
        'counter-key="@(project-demo:sub)" />\r\n'
        + '<llm-token-limit tokens-per-minute="2048" token-quota="10000" token-quota-period="Daily" />' * 2
        + '<set-variable name="finops" value="@{&#xD;&#xA;\"retain\";}" /></policies>')
    changed = inline_quota_delta(raw)
    assert 'calls="50000"' in changed and changed.count('tokens-per-minute="300000"') == 2
    assert changed.replace('calls="50000"', 'calls="1000"').replace(
        'tokens-per-minute="300000" token-quota="20000000"',
        'tokens-per-minute="2048" token-quota="10000"') == raw
    for invalid in (raw.replace('calls="1000"', 'calls="8"'), raw + raw):
        with pytest.raises(ValueError):
            inline_quota_delta(invalid)


def test_append_only_cas_migration_preserves_history_bindings_and_metadata(env, poc):
    from aiflux.auth import Principal
    from fastapi import HTTPException
    legacy = PocGatewayConfiguration(defaults=PocLimits(tpm=2048, token_quota=10000, request_quota=1000))
    assert save(env, legacy.model_dump(mode="json")).status_code == 200
    with Session(env.db_engine) as db:
        old = db.query(GatewaySettingsRevision).filter_by(scope="dev-unified", version=1).one()
        stored = json.loads(old.configuration)
        stored["unknown"] = {"opaque": [1, None, True]}
        old.configuration = json.dumps(stored)
        db.commit()
        original = old.configuration
        principal = Principal(organization_id=env.orgs["admin"], organization_name="IDS", tenant_id="test", object_id="test", role="ids_admin")
        result = migrate_poc_defaults(db, env.settings, poc, principal, "dev-unified", 1, "Approved default quota release")
        assert result.version == result.published_version == 2
        db.expire_all()
        assert db.query(GatewaySettingsRevision).filter_by(scope="dev-unified", version=1).one().configuration == original
        new = db.query(GatewaySettingsRevision).filter_by(scope="dev-unified", version=2).one()
        changed = json.loads(new.configuration)
        assert changed["unknown"] == stored["unknown"] and changed["bindings"] == stored["bindings"]
        changed["configuration"]["defaults"] = stored["configuration"]["defaults"]
        assert changed == stored
        assert render_revision("dev-unified", new) == poc.values["dev-unified"]
        with pytest.raises(HTTPException) as exc:
            migrate_poc_defaults(db, env.settings, poc, principal, "dev-unified", 1, "Stale attempt")
        assert exc.value.status_code == 409
        assert db.get(GatewaySettings, "dev-unified").version == 2