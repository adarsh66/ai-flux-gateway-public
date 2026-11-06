"""Synthetic direct-release receipts; never genuine live publication evidence."""
import json

import pytest

from aiflux import auto_snapshot, decision_router
from aiflux.display_pricing import manifest
from test_auto_snapshot import configured, receipt


def direct_receipt(tmp_path):
    settings = configured()
    snapshot, value = receipt(settings, tmp_path)
    value.update(schema=2, validation_mode="bounded-production-direct-v1", runtime_verified=False,
        gateway_runtime_evidence_sha256=None, independent_review_sha256="d" * 64,
        policy_readback_sha256="e" * 64, rollback_sha256="f" * 64,
        stop_on_explicit_regression=True,
        budget={"auto_attempts": 2, "scoring_calls": 2, "completion_calls": 2, "retries": 0, "fallback": False})
    settings.auto_routing_enabled = True
    settings.auto_routing_direct_validation_enabled = True
    settings.auto_routing_publication_path.write_text(json.dumps(value))
    return settings, snapshot, value


def test_frozen_auto_prices_match_tf_inputs_not_expanding_display_manifest():
    snapshot = auto_snapshot.defaults(configured())
    assert manifest()["sha256"] != manifest(False)["sha256"]
    assert len(snapshot["candidates"]) == 6
    assert all(c["price"] is None or c["price"]["manifest_sha256"] == manifest(False)["sha256"]
               for c in snapshot["candidates"])


def test_direct_release_is_explicit_pending_not_fake_runtime_proof(tmp_path):
    settings, snapshot, _ = direct_receipt(tmp_path)
    result = decision_router.availability(None, settings)
    assert result["ready"] is True and result["runtime_verified"] is False
    assert result["validation_mode"] == "bounded-production-direct-v1"
    assert result["config_version"] == snapshot["version"]
    settings.auto_routing_direct_validation_enabled = False
    assert decision_router.availability(None, settings) == {"ready": False, "profiles": []}


@pytest.mark.parametrize("field,value", [
    ("runtime_verified", True), ("gateway_runtime_evidence_sha256", "b" * 64),
    ("validation_mode", "diagnostic"), ("policy_readback_sha256", ""),
    ("independent_review_sha256", None), ("rollback_sha256", "fixture"),
    ("stop_on_explicit_regression", False), ("schema", True),
    ("budget", {"auto_attempts": 3, "scoring_calls": 3, "completion_calls": 3, "retries": 0, "fallback": False}),
    ("budget", {"auto_attempts": 2, "scoring_calls": 2, "completion_calls": 2, "retries": False, "fallback": 0}),
])
def test_direct_release_rejects_unbounded_or_fabricated_proof(tmp_path, field, value):
    settings, _, data = direct_receipt(tmp_path)
    data[field] = value
    settings.auto_routing_publication_path.write_text(json.dumps(data))
    assert decision_router.availability(None, settings) == {"ready": False, "profiles": []}


def test_publication_corruption_does_not_invoke_scorer_or_db(tmp_path, monkeypatch):
    settings, _, _ = direct_receipt(tmp_path)
    monkeypatch.setattr(decision_router.DecisionClient, "score", lambda *a, **k: pytest.fail("scorer invoked"))
    settings.auto_routing_publication_path.write_text('{"schema":2,"policy_sha256":[]}')
    assert decision_router.availability(None, settings)["ready"] is False