"""Offline05 regressions. Real retained evidence; mocked writes NEVER Azure."""
from datetime import UTC, datetime, timedelta
import inspect
import json

import pytest

from scripts.deployment import auto_diagnostic_window05 as x


def test_actual04_complete_readonly_original_sources_unknown_browser_preserved():
    old = x.predecessor()
    assert old["IP"] == x.OLD_IP and old["nonce"]
    assert x.p.sha(x.PROOF / "result.json") == x.PROOF_SHA
    assert x.a.load(x.OLD / "browser-attempt-result.json")["scoring_request_count"] is None
    assert str(x.OUT).endswith("scoring-diagnostic05")


@pytest.mark.parametrize("field,value", [("full13_verified", False), ("cloud_mutations", 1),
    ("mutation_retries", 1), ("diagnostic_stages_invoked", ["offline"])])
def test_actual04_incomplete_or_mutating_proof_rejected(field, value, monkeypatch):
    load = x.a.load
    def altered(path):
        result = load(path)
        if path == x.PROOF / "result.json":
            result[field] = value
        return result
    monkeypatch.setattr(x.a, "load", altered)
    with pytest.raises(RuntimeError, match="actual04_full13_readonly_required"):
        x.predecessor()


@pytest.mark.parametrize("field,value", [("revision2_online", True), ("revision2_current", True),
    ("all13_supplemental_exact", False), ("inherited_exact", False), ("exact_both_formats", False),
    ("baseline_sha256", "drift"), ("supplemental_sha256", "drift"), ("revisions", [])])
def test_actual04_retained_protected_capture_drift_rejected(field, value, monkeypatch):
    load = x.a.load
    def altered(path):
        result = load(path)
        if path == x.PROOF / "fresh-capture.json":
            result[field] = value
        return result
    monkeypatch.setattr(x.a, "load", altered)
    with pytest.raises(RuntimeError, match="actual04_offline_current1_full13_state185"):
        x.predecessor()


@pytest.mark.parametrize("stage", ["policy-put", "online", "offline"])
def test_actual04_consumed_literal_wire_binding_rejected(stage, monkeypatch):
    load = x.a.load
    def altered(path):
        result = load(path)
        if path == x.OLD / (stage + "-intent.json"):
            result["body_sha256"] = "0" * 64
        return result
    monkeypatch.setattr(x.a, "load", altered)
    with pytest.raises(RuntimeError, match="actual04_original_consumed_wire_binding"):
        x.predecessor()


def test_actual04_wire_unknown_cannot_be_restated_zero(monkeypatch):
    load = x.a.load
    def altered(path):
        result = load(path)
        if path == x.OLD / "browser-attempt-result.json":
            result["scoring_request_count"] = 0
        return result
    monkeypatch.setattr(x.a, "load", altered)
    with pytest.raises(RuntimeError, match="historical04_wire_unknown_NOT_zero"):
        x.predecessor()


def test_literal_original04_evidence_hash_drift_rejected(monkeypatch):
    sha = x.p.sha
    monkeypatch.setattr(x.p, "sha", lambda path: "bad" if path == x.OLD / "offline-intent.json" else sha(path))
    with pytest.raises(RuntimeError, match="original04_intents_and_evidence_exact"):
        x.predecessor()


def test_source_history_includes_original_controllers_receipts_not_mutable_docs():
    sources, history = x.sources(), x.history()
    for path in (x.OLD / "manifest.json", x.OLD / "offline-intent.json", x.PROOF / "result.json"):
        assert history[path.relative_to(x.p.rt.ROOT).as_posix()] == x.p.sha(path)
    assert "docs/auto-diagnostic04-review-20261029.md" not in sources
    assert x.DOC.relative_to(x.p.rt.ROOT).as_posix() in sources
    for name in ("auto_diagnostic_window04.py", "auto_diagnostic_time03.py", "auto_diagnostic_browser.mjs", "auto_diagnostic_browser05.mjs"):
        assert "scripts/deployment/" + name in sources


def test_candidate_changes_ONLY_IP_time_preserves_nonce_quota_safety_terminal():
    original = (x.OLD / "diagnostic.xml").read_bytes()
    old = x.predecessor()
    start, end = "2026-10-29T10:00:00+00:00", "2026-10-29T10:30:00+00:00"
    candidate = x.candidate(start, end)
    root = x.c.tree(candidate)
    scope = root.find("inbound")[2]
    assert x.c.signature(scope) == x.c.signature(x.scope_guard(start, end))
    assert x.IP in scope.find("when").get("condition")
    assert x.OLD_IP not in scope.find("when").get("condition")
    assert x.d.expression_audit(candidate)["expression_count"] == 103
    gate = x.c.post(root).find("limit-concurrency")
    assert gate.get("key") == '@("auto-diagnostic:' + old["nonce"] + '")'
    assert gate[0].get("calls") == "1" and gate[0].get("renewal-period") == "3600"
    assert gate[-1].tag == "return-response"
    assert (x.OLD / "diagnostic.xml").read_bytes() == original


@pytest.mark.parametrize("start,end", [("2026-10-29T10:00:00", "2026-10-29T10:30:00+00:00"),
    ("2026-10-29T10:00:00+00:00", "2026-10-29T10:20:00+00:00"),
    ("2026-10-29T10:00:00+00:00", "2026-10-29T10:31:00+00:00"),
    ("2026-10-29T10:00:00+00:00", "2026-10-29T10:00:00+00:00"),
    ("2026-10-29T10:00:00+01:00", "2026-10-29T10:30:00+01:00")])
def test_exact_bounded_UTC_window_required(start, end):
    with pytest.raises(RuntimeError):
        x.scope_guard(start, end)


def test_adapter_reuses_and_restores_all_original_transport_capture_guards(monkeypatch, tmp_path):
    monkeypatch.setattr(x, "OUT", tmp_path)
    preserved = {name: getattr(x.w, name) for name in ("capture", "execute", "once", "wire_child", "reserve_browser", "check_window", "mutation_request", "DIAG")}
    previous = x.prior.OUT, x.prior.prior.DIAG, x.c.IP, x.w.OUT, x.w.BROWSER
    source_before = x.sources()
    with pytest.raises(ValueError):
        with x.bindings():
            assert all(getattr(x.w, key) is value for key, value in preserved.items())
            assert x.c.IP == x.IP and x.prior.OUT == tmp_path
            assert x.prior.prior.DIAG == x.OLD and x.w.DIAG != x.OLD
            assert x.sources() == source_before
            assert x.predecessor()["IP"] == x.OLD_IP
            raise ValueError("fixture")
    assert previous == (x.prior.OUT, x.prior.prior.DIAG, x.c.IP, x.w.OUT, x.w.BROWSER)
    assert all(getattr(x.w, key) is value for key, value in preserved.items())


def setup_review(tmp_path, monkeypatch, expired=False):
    monkeypatch.setattr(x, "OUT", tmp_path)
    at = datetime.now(UTC) - (timedelta(days=1) if expired else timedelta(minutes=1))
    m = {"at_utc": (at - timedelta(seconds=1)).isoformat(), "start": at.isoformat(), "end": (at + timedelta(minutes=30)).isoformat()}
    (tmp_path / "manifest.json").write_text(json.dumps(m))
    (tmp_path / "native.txt").write_text("FIXTURE NOT REAL APPROVAL")
    r = {"approved": True, "independent_native_review": True, "stages": x.STAGES,
         "manifest_sha256": x.p.sha(tmp_path / "manifest.json"), "at_utc": at.isoformat(),
         "transcript": "native.txt", "transcript_sha256": x.p.sha(tmp_path / "native.txt")}
    (tmp_path / "parent-review.json").write_text(json.dumps(r))
    monkeypatch.setattr(x, "check_package", lambda: m)
    return m


def test_expired_cleanup_independent_of_window_and_review_age_but_requires_parent(tmp_path, monkeypatch):
    setup_review(tmp_path, monkeypatch, expired=True)
    with pytest.raises(FileNotFoundError):
        x.review("offline")
    (tmp_path / "cleanup-authorization.json").write_text(json.dumps({"parent_says_cleanup": True,
        "manifest_sha256": x.p.sha(tmp_path / "manifest.json"), "review_sha256": x.p.sha(tmp_path / "parent-review.json"),
        "at_utc": datetime.now(UTC).isoformat()}))
    x.review("offline")
    for stage in x.STAGES[:-1]:
        with pytest.raises(RuntimeError, match="fresh05_native_review"):
            x.review(stage)
    (tmp_path / "offline-intent.json").write_text("consumed_ambiguous")
    with pytest.raises(RuntimeError, match="existing_intent_NO_RETRY"):
        x.review("offline")


@pytest.mark.parametrize("field,value", [("approved", False), ("independent_native_review", False),
    ("stages", ["online", "offline"]), ("manifest_sha256", "bad")])
def test_parent_review_all_four_scopes_required(field, value, tmp_path, monkeypatch):
    setup_review(tmp_path, monkeypatch)
    r = x.load("parent-review.json")
    r[field] = value
    (tmp_path / "parent-review.json").write_text(json.dumps(r))
    with pytest.raises(RuntimeError, match="actual_parent_review_all_four_scopes"):
        x.review("policy-put")


def test_online_requires_actual_offline_compilation(tmp_path, monkeypatch):
    setup_review(tmp_path, monkeypatch)
    with x.bindings():
        with pytest.raises(FileNotFoundError):
            x.review("online")
    assert not (tmp_path / "online-intent.json").exists()


def test_actual_original_executor_reservation_sequence_one_wire_new_IP_no_Send(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"end": "fixed05"}))
    (tmp_path / "parent-review.json").write_text("{}")
    calls = []
    monkeypatch.setattr(x, "review", lambda stage: {"end": "fixed05"})
    monkeypatch.setattr(x, "check_package", lambda: {})
    monkeypatch.setattr(x.p.persistence, "transport", lambda: None)
    monkeypatch.setattr(x.c, "Reads", lambda: type("Reads", (), {"token": "memory_only_fixture"})())
    def capture(reads, label, wanted, policy=None):
        calls.append(label)
        return {"at_utc": datetime.now(UTC).isoformat(), "etag": '"fixture"', "revision2_online": label != "online-before"}
    monkeypatch.setattr(x.w, "capture", capture)
    def once(stage, etag, token):
        assert stage == "online" and (tmp_path / "online-intent.json").is_file()
        calls.append("one_wire")
        return {"http_status": 200}
    monkeypatch.setattr(x.w, "once", once)
    monkeypatch.setattr(x.prior, "policy_put", lambda: calls.append("offline_PUT_verified"))
    with x.bindings():
        result = x.prior.activate()
        assert result["status"] == "ONLINE_READY"
        reservation = x.load("reserve-browser-intent.json")
        assert reservation["IP"] == x.IP and reservation["browser_source_sha256"] == x.p.sha(x.BROWSER)
        assert reservation["scoring_budget"] == 1 and reservation["completion_budget"] == 0
        before = list(calls)
        with pytest.raises(FileExistsError):
            x.prior.activate()
        assert calls == before
    assert calls == ["offline_PUT_verified", "online-before", "one_wire", "online-after", "browser-before"]
    assert not (tmp_path / "offline-intent.json").exists() and not (tmp_path / "browser-send-intent.json").exists()


@pytest.mark.parametrize("fail_stage", ["policy-put", "online", "reserve-browser"])
def test_stage_failure_consumed_no_automatic_cleanup_no_reinvoke(fail_stage, tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    (tmp_path / "manifest.json").write_text("{}")
    monkeypatch.setattr(x, "review", lambda stage: {})
    calls = []
    def run(stage):
        calls.append(stage)
        if stage == fail_stage:
            raise RuntimeError("fixture")
    monkeypatch.setattr(x.prior, "policy_put", lambda: run("policy-put"))
    monkeypatch.setattr(x.w, "execute", run)
    monkeypatch.setattr(x.w, "reserve_browser", lambda: run("reserve-browser"))
    with x.bindings():
        with pytest.raises(RuntimeError):
            x.prior.activate()
        before = list(calls)
        with pytest.raises(FileExistsError):
            x.prior.activate()
        assert calls == before and "offline" not in calls


def test_offline_prepare_no_cloud_and_existing_package_never_refresh(tmp_path, monkeypatch):
    text = inspect.getsource(x.prepare)
    for forbidden in (".capture(", ".execute(", ".once(", "transport(", "Reads("):
        assert forbidden not in text
    monkeypatch.setattr(x, "OUT", tmp_path)
    with pytest.raises(RuntimeError, match="existing05_package_NEVER_refresh"):
        x.prepare(tmp_path / "not_used.xml", tmp_path / "not_used2.xml")


def test_existing_PUT_runs_actual04_before05_after_and_intent_before_retained_transport():
    text = inspect.getsource(x.prior.policy_put)
    assert '"policy-put-before", False, prior.DIAG / "diagnostic.xml"' in text
    assert '"policy-put-after", False, OUT / "diagnostic.xml"' in text
    assert text.index('exclusive("policy-put-intent.json"') < text.index("put_transport.once(")
    assert text.count("put_transport.once(") == 1
    transport = inspect.getsource(x.prior.put_transport.once)
    assert "rx.poll(60)" in transport and "child.terminate()" in transport and "child.kill()" in transport


def test_actual_retained_PUT_executor_uses04_before05_after_exclusive_wire(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "parent-review.json").write_text("{}")
    body = b'fixed_fixture_body_NOT_a_real_policy'
    (tmp_path / "policy-put.json").write_bytes(body)
    calls = []
    monkeypatch.setattr(x, "review", lambda stage: calls.append("review:" + stage))
    monkeypatch.setattr(x, "check_package", lambda: {})
    monkeypatch.setattr(x.p.persistence, "transport", lambda: None)
    class Reads:
        token = "fixture_memory_only"
        def policy(self, revision, fmt):
            assert revision == ";rev=2" and fmt in ("rawxml", "xml")
            return {"etag": '"fixture_ETag"'}
    monkeypatch.setattr(x.c, "Reads", Reads)
    monkeypatch.setattr(x.prior, "exports", lambda formats, policy: calls.append(("exports", policy)))
    def capture(reads, label, online, policy):
        calls.append((label, online, policy))
        if label == "policy-put-after":
            (tmp_path / "policy-put-after-capture.json").write_text("fixture")
        return {"state_owner": {"serial": 185}}
    monkeypatch.setattr(x.w, "capture", capture)
    def once(etag, token, actual_body):
        assert etag == '"fixture_ETag"' and actual_body == body
        assert (tmp_path / "policy-put-intent.json").exists()
        calls.append("one_PUT_wire")
        return {"http_status": 200}
    monkeypatch.setattr(x.prior.put_transport, "once", once)
    with x.bindings():
        # bindings deliberately installs the real export adapter. Only its
        # verifier is mocked here; real export negatives run in original tests.
        monkeypatch.setattr(x.prior, "exports", lambda formats, policy: calls.append(("exports", policy)))
        x.prior.policy_put()
    assert ("policy-put-before", False, x.OLD / "diagnostic.xml") in calls
    assert ("policy-put-after", False, tmp_path / "diagnostic.xml") in calls
    assert calls.count("one_PUT_wire") == 1
    intent = x.load("policy-put-intent.json")
    assert intent["attempt_budget"] == 1 and intent["retries"] == intent["redirects"] == 0
    assert x.load("policy-put-verification.json")["revision2_online"] is False


def test_native_node_receipt_actual_shape_and_failure_rejection(tmp_path):
    receipt = tmp_path / "node.xml"
    receipt.write_text('<testsuites><testcase name="fixture"/></testsuites>')
    assert x.test_counts(receipt, "node") == {"tests": 1, "errors": 0, "failures": 0, "skipped": 0}
    for node in ("failure", "error", "skipped"):
        receipt.write_text('<testsuites><testcase name="fixture"><' + node + '/></testcase></testsuites>')
        with pytest.raises(RuntimeError, match="clean_actual_node_tests"):
            x.test_counts(receipt, "node")
    receipt.write_text("<testsuites/>")
    with pytest.raises(RuntimeError, match="clean_actual_node_tests"):
        x.test_counts(receipt, "node")


def test_keyboard_handler_verified_in_current_UI_source():
    source = (x.p.rt.ROOT / "packages/ui/src/pages/PlaygroundPage.tsx").read_text(encoding="utf-8")
    assert 'e.key === "Enter" && (e.ctrlKey || e.metaKey) && !busy' in source
    assert "e.preventDefault(); void send();" in source