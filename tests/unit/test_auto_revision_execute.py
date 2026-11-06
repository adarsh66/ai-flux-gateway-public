"""No-cloud execution intent and evidence gates."""
import json

import pytest

from scripts.deployment import auto_revision_execute as e


@pytest.mark.parametrize("marker", ["live-apply-intent.json", "nested/old-apply-intent.json"])
def test_existing_intent_prevents_any_execute(tmp_path, monkeypatch, marker):
    monkeypatch.setattr(e, "HOME", tmp_path)
    path = tmp_path / marker
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    with pytest.raises(RuntimeError, match="existing_execution_reconcile_ONLY"):
        e.apply_once()


def test_existing_execution_prevents_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(e, "HOME", tmp_path)
    (tmp_path / "execution01").mkdir()
    with pytest.raises(RuntimeError, match="existing_execution_reconcile_ONLY"):
        e.apply_once()


def test_existing_readback_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(e, "HOME", tmp_path)
    (tmp_path / "readback01").mkdir()
    with pytest.raises(RuntimeError, match="existing_readback_reconcile_no_replay"):
        e.verify_once()


def test_validation_false_rejected(monkeypatch):
    monkeypatch.setattr(e.v, "load", lambda _: {"checks_passed": False})
    with pytest.raises(RuntimeError, match="actual_review_validation_required"):
        e.integrity()


def test_validation_wrong_target_rejected(monkeypatch):
    monkeypatch.setattr(e.v, "load", lambda _: {"checks_passed": True, "saved_plan_sha256": "0" * 64})
    with pytest.raises(RuntimeError, match="actual_review_validation_required"):
        e.integrity()