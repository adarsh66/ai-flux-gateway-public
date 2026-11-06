"""Offline fixed03 binding regressions; no network, build, or mutation."""
from datetime import UTC, datetime
import inspect

import pytest

from scripts.deployment import auto_diagnostic_window03 as x
from tests.unit.test_auto_diagnostic_window import review_fixture


def test_actual_retained03_proof_and_unchanged02():
    assert x.check_compilation()["xml_sha256"] == x.XML_SHA
    assert x.w.DIAG.name == "scoring-diagnostic02"


@pytest.mark.parametrize("name", list(x.PROOF))
def test_any_pinned_proof_byte_drift_rejected(name, monkeypatch):
    sha = x.p.sha
    monkeypatch.setattr(x.p, "sha", lambda path: "0" * 64 if path == x.DIAG / name else sha(path))
    with pytest.raises(RuntimeError, match="literal_diagnostic03_actual_PUT_proof_exact"):
        x.check_compilation()


@pytest.mark.parametrize("field,value", [("start", "2026-10-29T07:44:19+00:00"),
                                        ("end", "2026-10-29T08:05:18+00:00"),
                                        ("xml_sha256", "0" * 64)])
def test_arbitrary_window_or_XML_not_accepted(field, value, monkeypatch):
    load = x.a.load
    def altered(path):
        result = load(path)
        if path == x.DIAG / "manifest.json":
            result[field] = value
        return result
    monkeypatch.setattr(x.a, "load", altered)
    with pytest.raises(RuntimeError, match="fixed03_XML_and_window_no_renewal"):
        x.check_compilation()


def test_only_narrow_bindings_and_restore_even_on_exception():
    names = ("OUT", "check_compilation", "history", "exports", "DIAG", "once", "capture", "review", "execute")
    prior = {key: getattr(x.w, key) for key in names}
    with pytest.raises(ValueError):
        with x.bindings():
            assert x.w.OUT == x.OUT and x.w.check_compilation is x.check_compilation
            for key in ("DIAG", "once", "capture", "review", "execute"):
                assert getattr(x.w, key) is prior[key]
            raise ValueError("fixture")
    assert all(getattr(x.w, key) is value for key, value in prior.items())


def test_exports_only_exact03(monkeypatch):
    seen = []
    monkeypatch.setattr(x, "_exports02", lambda formats, policy: seen.append(policy))
    x.exports({})
    assert seen == [x.DIAG / "diagnostic.xml"]
    with pytest.raises(RuntimeError, match="only_fixed03_export_policy"):
        x.exports({}, x.w.DIAG / "diagnostic.xml")


def test_exact03_deadline_keeps_cleanup_reserve():
    m = {"start": x.START, "end": x.END}
    x.w.check_window(m, datetime(2026, 10, 29, 8, 2, 47, tzinfo=UTC))
    with pytest.raises(RuntimeError):
        x.w.check_window(m, datetime(2026, 10, 29, 8, 2, 48, tzinfo=UTC))


def test_bound_adapter_cleanup_expired_review_and_exclusive_once(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    with x.bindings():
        review_fixture(tmp_path, monkeypatch)
        x.w.review("offline")
        with pytest.raises(RuntimeError):
            x.w.review("online")
        x.w.exclusive("offline-intent.json", {"outcome": "unknown_no_retry"})
        with pytest.raises(RuntimeError, match="existing_intent_NO_RETRY"):
            x.w.review("offline")


def test_offline_assembly_has_no_live_or_mutation_or_time_renewal():
    text = inspect.getsource(x.prepare_review)
    for forbidden in (".capture(", ".execute(", ".once(", "transport(", "workers(", "timedelta("):
        assert forbidden not in text
    assert "RETAINED_GET_EVIDENCE_NOT_FRESH_LIVE_PREPARE" in text
    assert "existing_window03_package_reconcile_only" in text
    assert '"policy-put"' not in inspect.getsource(x.main)