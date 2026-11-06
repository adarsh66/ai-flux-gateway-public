"""Offline regressions for actual03 successor and one-shot parent handoff."""
from datetime import UTC, datetime, timedelta
import inspect
import json

import pytest

from scripts.deployment import auto_diagnostic_window04 as x


def test_actual03_successor_includes_consumed_online_offline_zero_Send():
    m = x.predecessor()
    assert m["xml_sha256"] == x.prior.XML_SHA
    history = x.history()
    for folder, name in ((x.prior.DIAG, "policy-put-intent.json"),
                         (x.WINDOW03, "online-intent.json"),
                         (x.WINDOW03, "offline-intent.json"),
                         (x.WINDOW03, "offline-after-capture.json"),
                         (x.WINDOW03, "executor-sequence-report.json")):
        assert history[(folder / name).relative_to(x.p.rt.ROOT).as_posix()] == x.p.sha(folder / name)


@pytest.mark.parametrize("field,value", [("browser_send_count", 1), ("executor_scoring_requests", 1),
    ("executor_completion_requests", 1), ("reserve_browser_executed", True), ("online_wire_attempts", 2)])
def test_actual03_consumed_browser_budget_rejected(field, value, monkeypatch):
    load = x.a.load
    def altered(path):
        result = load(path)
        if path == x.WINDOW03 / "executor-sequence-report.json":
            result[field] = value
        return result
    monkeypatch.setattr(x.a, "load", altered)
    with pytest.raises(RuntimeError, match="actual03_consumed_stages_zero_Send"):
        x.predecessor()


def test_stale02_policy_predecessor_cannot_replace_actual03_readback(monkeypatch):
    load = x.a.load
    def altered(path):
        result = load(path)
        if path == x.WINDOW03 / "offline-after-capture.json":
            result["policy_format_hashes"] = {"rawxml": "stale02", "xml": "stale02"}
        return result
    monkeypatch.setattr(x.a, "load", altered)
    with pytest.raises(RuntimeError, match="actual03_successor_policy_predecessor_readback"):
        x.predecessor()


@pytest.mark.parametrize("stage", ["online", "offline"])
def test_actual03_consumed_wire_binding_drift_rejected(stage, monkeypatch):
    load = x.a.load
    def altered(path):
        result = load(path)
        if path == x.WINDOW03 / (stage + "-intent.json"):
            result["body_sha256"] = "0" * 64
        return result
    monkeypatch.setattr(x.a, "load", altered)
    with pytest.raises(RuntimeError, match="actual03_wire_and_full_readback_binding"):
        x.predecessor()


def test_time_only_delta_preserves_actual03_nonce_counters_safety_and_terminal():
    start, end = "2026-10-29T09:00:00+00:00", "2026-10-29T09:20:00+00:00"
    original = (x.prior.DIAG / "diagnostic.xml").read_bytes()
    candidate = x.time_only(start, end)
    assert candidate.encode() != original
    assert x.d.expression_audit(candidate)["expression_count"] == 103
    root = x.c.tree(candidate)
    assert x.c.signature(root.find("inbound")[2]) == x.c.signature(x.d.scope_guard(start, end))
    assert (x.prior.DIAG / "diagnostic.xml").read_bytes() == original


@pytest.mark.parametrize("start,end", [("2026-10-29T09:00:00", "2026-10-29T09:20:00+00:00"),
    ("2026-10-29T09:00:00+00:00", "2026-10-29T09:21:00+00:00"),
    ("2026-10-29T09:00:00+00:00", "2026-10-29T09:00:00+00:00")])
def test_unbounded_naive_or_zero_window_rejected(start, end):
    with pytest.raises(RuntimeError):
        x.time_only(start, end)


def test_narrow_adapter_retains_full_capture_and_wire_and_restores(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    names = ("OUT", "exports", "review", "check_package", "DIAG", "capture", "execute", "once", "reserve_browser")
    before = {name: getattr(x.w, name) for name in names}
    with pytest.raises(ValueError):
        with x.bindings():
            assert x.w.OUT == tmp_path
            for name in ("DIAG", "capture", "execute", "once", "reserve_browser"):
                assert getattr(x.w, name) is before[name]
            raise ValueError("fixture")
    assert all(getattr(x.w, name) is value for name, value in before.items())


def test_exports_switch_from_actual03_only_after04_PUT_intent(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    seen = []
    monkeypatch.setattr(x, "_exports", lambda formats, policy: seen.append(policy))
    x.exports({})
    assert seen[-1] == x.prior.DIAG / "diagnostic.xml"
    (tmp_path / "policy-put-intent.json").write_text("consumed")
    x.exports({})
    assert seen[-1] == tmp_path / "diagnostic.xml"
    with pytest.raises(RuntimeError):
        x.exports({}, x.w.DIAG / "diagnostic.xml")


def setup_review(tmp_path, monkeypatch, expired=False):
    monkeypatch.setattr(x, "OUT", tmp_path)
    now = datetime.now(UTC)
    start = now - (timedelta(days=1) if expired else timedelta(minutes=1))
    manifest = {"at_utc": (start - timedelta(seconds=1)).isoformat(),
                "start": start.isoformat(), "end": (start + timedelta(minutes=20)).isoformat()}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "native.txt").write_text("fixture not a real parent approval")
    r = {"approved": True, "independent_native_review": True, "stages": x.STAGES,
         "manifest_sha256": x.p.sha(tmp_path / "manifest.json"), "at_utc": start.isoformat(),
         "transcript": "native.txt", "transcript_sha256": x.p.sha(tmp_path / "native.txt")}
    (tmp_path / "parent-review.json").write_text(json.dumps(r))
    monkeypatch.setattr(x, "check_package", lambda: manifest)
    return manifest


def cleanup_signal(tmp_path):
    signal = {"parent_says_cleanup": True, "at_utc": datetime.now(UTC).isoformat(),
              "manifest_sha256": x.p.sha(tmp_path / "manifest.json"),
              "review_sha256": x.p.sha(tmp_path / "parent-review.json")}
    (tmp_path / "cleanup-authorization.json").write_text(json.dumps(signal))


def test_expired_cleanup_requires_explicit_parent_signal_then_survives_expiry(tmp_path, monkeypatch):
    setup_review(tmp_path, monkeypatch, expired=True)
    with pytest.raises(FileNotFoundError):
        x.review("offline")
    cleanup_signal(tmp_path)
    x.review("offline")
    for stage in ("policy-put", "online", "reserve-browser"):
        with pytest.raises(RuntimeError, match="fresh04_native_review"):
            x.review(stage)
    with x.bindings():
        x.w.exclusive("offline-intent.json", {"outcome": "ambiguous_consumed"})
    with pytest.raises(RuntimeError, match="existing_intent_NO_RETRY"):
        x.review("offline")


@pytest.mark.parametrize("stages", [["policy-put"], ["online", "reserve-browser", "offline"], ["offline"]])
def test_one_native_review_must_bind_all_four_scopes(tmp_path, monkeypatch, stages):
    setup_review(tmp_path, monkeypatch)
    r = x.load("parent-review.json")
    r["stages"] = stages
    (tmp_path / "parent-review.json").write_text(json.dumps(r))
    with pytest.raises(RuntimeError, match="one_actual_parent_review_all_four_scopes"):
        x.review("policy-put")


def test_activation_one_each_then_return_online_ready_no_cleanup_or_Send(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"end": "fixed04"}))
    calls = []
    monkeypatch.setattr(x, "review", lambda stage: calls.append("review:" + stage))
    monkeypatch.setattr(x, "policy_put", lambda: calls.append("policy-put"))
    monkeypatch.setattr(x.w, "execute", lambda stage: calls.append(stage))
    def reserve():
        calls.append("reserve-browser")
        (tmp_path / "reserve-browser-intent.json").write_text("reserved_not_sent")
    monkeypatch.setattr(x.w, "reserve_browser", reserve)
    with x.bindings():
        result = x.activate()
        assert result["status"] == "ONLINE_READY" and result["send_count"] == 0
        assert calls == ["review:policy-put", "policy-put", "online", "reserve-browser"]
        before = list(calls)
        with pytest.raises(FileExistsError):
            x.activate()
        assert calls == before + ["review:policy-put"]
    assert not (tmp_path / "offline-intent.json").exists()


@pytest.mark.parametrize("fail_stage", ["policy-put", "online", "reserve-browser"])
def test_failure_never_automatically_cleans_up_or_repeats_scope(tmp_path, monkeypatch, fail_stage):
    monkeypatch.setattr(x, "OUT", tmp_path)
    (tmp_path / "manifest.json").write_text("{}")
    monkeypatch.setattr(x, "review", lambda stage: {})
    calls = []
    def run(stage):
        calls.append(stage)
        if stage == fail_stage:
            raise RuntimeError("actual stage failed or silent")
    monkeypatch.setattr(x, "policy_put", lambda: run("policy-put"))
    monkeypatch.setattr(x.w, "execute", run)
    monkeypatch.setattr(x.w, "reserve_browser", lambda: run("reserve-browser"))
    with x.bindings():
        with pytest.raises(RuntimeError):
            x.activate()
        before = list(calls)
        with pytest.raises(FileExistsError):
            x.activate()
        assert calls == before
    assert "offline" not in calls and len(calls) == len(set(calls))


def test_offline_prepare_and_status_never_call_cloud_or_stage():
    for function in (x.prepare, x.status):
        text = inspect.getsource(function)
        for forbidden in (".capture(", ".execute(", ".once(", "transport(", "Reads("):
            assert forbidden not in text
    assert "existing04_package_NEVER_refresh" in inspect.getsource(x.prepare)
    assert 'choices=("prepare-review", "activate", "offline", "status")' in inspect.getsource(x.main)
    assert "finally" not in inspect.getsource(x.activate)


def test_PUT_literal03_before04_after_and_intent_before_single_wire():
    text = inspect.getsource(x.policy_put)
    assert '"policy-put-before", False, prior.DIAG / "diagnostic.xml"' in text
    assert '"policy-put-after", False, OUT / "diagnostic.xml"' in text
    assert text.index('exclusive("policy-put-intent.json"') < text.index("put_transport.once(")
    assert text.count("put_transport.once(") == 1
    assert 'review("policy-put")' in text and 'fetched < timedelta(seconds=60)' in text


def test_online_cannot_use_actual03_instead_of_compiled04(tmp_path, monkeypatch):
    setup_review(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError):
        x.review("online")
    assert not (tmp_path / "online-intent.json").exists()


def test_real_retained_PATCH_and_reservation_executor_in_single04_sequence(tmp_path, monkeypatch):
    """Exercise actual w.execute/reserve, not a copied/fabricated controller."""
    monkeypatch.setattr(x, "OUT", tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"end": "fixed04"}))
    (tmp_path / "parent-review.json").write_text("{}")
    calls = []
    monkeypatch.setattr(x, "review", lambda stage: {"end": "fixed04"})
    monkeypatch.setattr(x, "check_package", lambda: {})
    monkeypatch.setattr(x.p.persistence, "transport", lambda: None)
    monkeypatch.setattr(x.c, "Reads", lambda: type("Reads", (), {"token": "memory_only_fixture"})())
    def capture(reads, label, wanted, policy=None):
        calls.append(label)
        return {"at_utc": datetime.now(UTC).isoformat(), "etag": '"actual-fixture-etag"',
                "revision2_online": label != "online-before"}
    monkeypatch.setattr(x.w, "capture", capture)
    def wire(stage, etag, token):
        assert stage == "online" and (tmp_path / "online-intent.json").is_file()
        calls.append("online-wire")
        return {"http_status": 200}
    monkeypatch.setattr(x.w, "once", wire)
    monkeypatch.setattr(x, "policy_put", lambda: calls.append("offline-PUT-verified"))
    with x.bindings():
        result = x.activate()
    assert calls == ["offline-PUT-verified", "online-before", "online-wire", "online-after", "browser-before"]
    assert x.load("online-verification.json")["revision2_online"] is True
    assert x.load("reserve-browser-intent.json")["scoring_budget"] == 1
    assert result["status"] == "ONLINE_READY"
    assert not (tmp_path / "offline-intent.json").exists()