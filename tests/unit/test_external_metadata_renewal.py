"""Synthetic renewal contracts; never current external inference acceptance."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aiflux.config import Settings
from aiflux.external_inventory import ExternalRoute, historical_acceptance_sha256

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    data = json.loads((ROOT / 'gateway/catalog/external-inventory.json').read_text())['routes'][0]
    data.pop('metadata_renewal', None)
    data['verified_at'] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    old = ExternalRoute.model_validate(data)
    data['metadata_renewal'] = {
        'kind': 'unchanged_apim_metadata', 'observed_at': datetime.now(UTC).isoformat(),
        'historical_acceptance_sha256': historical_acceptance_sha256(old),
        'policy_sha256': 'a' * 64, 'backend_sha256': 'b' * 64,
        'reference_metadata_sha256': 'c' * 64,
        'named_value_resource_id': '/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/'
        'IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.ApiManagement/service/'
        'poc-ids-token-ex-apim/namedValues/aiflux-glm-5-3-api-key',
        'secret_storage': 'apim_internal_secret',
        'fresh_credential_health_verified': False, 'smoke_repeated': False,
    }
    return data


def test_real_metadata_freshness_separate_from_historical_smoke():
    data = fixture()
    route = ExternalRoute.model_validate(data)
    settings = Settings(_env_file=None, environment='development')
    assert route.accepted(settings)
    assert route.verified_at < datetime.now(UTC) - timedelta(days=1)
    assert not route.metadata_renewal.fresh_credential_health_verified
    old = deepcopy(data)
    old.pop('metadata_renewal')
    assert not ExternalRoute.model_validate(old).accepted(settings)


@pytest.mark.parametrize('field,value', [
    ('verified_at', '2026-10-25T01:00:00Z'), ('probe_prompt_tokens', 26),
    ('probe_total_tokens', 78), ('assistant_nonempty', False),
    ('credential_healthy', False), ('gateway_validated', False),
    ('max_completion_tokens', 512), ('probe_status', None),
])
def test_renewal_cannot_restamp_or_change_historical_acceptance(field, value):
    data = fixture()
    data[field] = value
    with pytest.raises(ValidationError):
        ExternalRoute.model_validate(data)


@pytest.mark.parametrize('field,value', [
    ('kind', 'fresh_smoke'), ('historical_acceptance_sha256', 'd' * 64),
    ('named_value_resource_id', '/foreign'), ('policy_sha256', ''),
    ('secret_storage', 'key_vault'), ('fresh_credential_health_verified', True),
    ('smoke_repeated', True), ('observed_at', '2020-01-01T00:00:00Z'),
])
def test_renewal_rejects_unbound_or_misrepresented_proof(field, value):
    data = fixture()
    data['metadata_renewal'][field] = value
    with pytest.raises(ValidationError):
        ExternalRoute.model_validate(data)


@pytest.mark.parametrize('delta', [timedelta(days=-2), timedelta(minutes=5)])
def test_metadata_freshness_still_failclosed_for_expired_or_future(delta):
    data = fixture()
    data['verified_at'] = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    old = deepcopy(data)
    old.pop('metadata_renewal')
    data['metadata_renewal']['historical_acceptance_sha256'] = historical_acceptance_sha256(
        ExternalRoute.model_validate(old))
    data['metadata_renewal']['observed_at'] = (datetime.now(UTC) + delta).isoformat()
    assert not ExternalRoute.model_validate(data).accepted(Settings(_env_file=None, environment='development'))