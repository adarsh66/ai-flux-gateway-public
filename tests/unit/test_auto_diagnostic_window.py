from datetime import UTC, datetime, timedelta
import inspect
import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.deployment import auto_diagnostic_window as w


def test_actual_retained_compile_and_whole_XML_regression():
    manifest = w.check_compilation()
    assert manifest["end"] == "2026-10-29T07:46:54+00:00"
    assert w.p.sha(w.DIAG / "diagnostic.xml") == "5a096d1094128dfa8d2fab1240b87de35d2fd97dad71342b4974986c99f8daaa"


@pytest.mark.parametrize("stage,value", [("online", True), ("offline", False)])
def test_literal_owned_PATCH_and_actual_ETag_only(stage, value):
    request = w.mutation_request(stage, '"opaque-actual"', "memory-only")
    assert request.method == "PATCH" and request.full_url == w.a.URL
    assert ";rev=2?" in request.full_url
    assert json.loads(request.data) == {"properties": {"isOnline": value}}
    assert request.headers["If-match"] == '"opaque-actual"'


@pytest.mark.parametrize("stage", ["policy-put", "send", "score", "promote", "delete", "create", "PATCH"])
def test_nonallowlisted_write_rejected(stage):
    with pytest.raises(RuntimeError):
        w.mutation_request(stage, '"opaque"', "memory-only")


@pytest.mark.parametrize("etag", [None, "*", "", "unquoted", '"bad\r\nheader"'])
def test_wildcard_or_invalid_ETag_rejected(etag):
    with pytest.raises(RuntimeError):
        w.mutation_request("online", etag, "memory-only")


def test_durable_exclusive_intent_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "OUT", tmp_path)
    w.exclusive("online-intent.json", {"attempt_budget": 1})
    before = (tmp_path / "online-intent.json").read_bytes()
    with pytest.raises(FileExistsError):
        w.exclusive("online-intent.json", {"attempt_budget": 2})
    assert (tmp_path / "online-intent.json").read_bytes() == before


@pytest.mark.parametrize("offset,ok", [(-1, False), (0, True), (1109, True), (1110, False), (1200, False)])
def test_fixed_window_boundary_and_cleanup_reserve(offset, ok):
    start = datetime(2026, 10, 29, 7, 26, 54, tzinfo=UTC)
    manifest = {"start": start.isoformat(), "end": (start + timedelta(minutes=20)).isoformat()}
    if ok:
        w.check_window(manifest, start + timedelta(seconds=offset))
    else:
        with pytest.raises(RuntimeError):
            w.check_window(manifest, start + timedelta(seconds=offset))


def review_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "OUT", tmp_path)
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "actual-native.txt").write_text("fixture independent review")
    old = datetime.now(UTC) - timedelta(days=1)
    receipt = {"approved": True, "independent_native_review": True,
               "stages": ["online", "reserve-browser", "offline"],
               "manifest_sha256": w.p.sha(tmp_path / "manifest.json"),
               "at_utc": old.isoformat(), "transcript": "actual-native.txt",
               "transcript_sha256": w.p.sha(tmp_path / "actual-native.txt")}
    (tmp_path / "parent-review.json").write_text(json.dumps(receipt))
    manifest = {"at_utc": (old - timedelta(minutes=1)).isoformat(),
                "start": old.isoformat(), "end": (old + timedelta(minutes=20)).isoformat()}
    monkeypatch.setattr(w, "check_package", lambda: manifest)
    return receipt


def test_cleanup_after_expiry_old_review_and_failed_online(tmp_path, monkeypatch):
    review_fixture(tmp_path, monkeypatch)
    (tmp_path / "online-intent.json").write_text("ambiguous outcome consumed")
    (tmp_path / "online-failure.json").write_text("failure fixture")
    w.review("offline")
    with pytest.raises(RuntimeError):
        w.review("online")
    with pytest.raises(RuntimeError):
        w.review("reserve-browser")


@pytest.mark.parametrize("change", ["scope", "manifest", "transcript", "approved", "independent"])
def test_cleanup_must_have_actual_review_covering_both_scopes(tmp_path, monkeypatch, change):
    receipt = review_fixture(tmp_path, monkeypatch)
    if change == "scope":
        receipt["stages"] = ["offline"]
    elif change == "manifest":
        receipt["manifest_sha256"] = "0" * 64
    elif change == "transcript":
        receipt["transcript"] = "../outside.txt"
    elif change == "approved":
        receipt["approved"] = False
    else:
        receipt["independent_native_review"] = False
    (tmp_path / "parent-review.json").write_text(json.dumps(receipt))
    with pytest.raises(RuntimeError):
        w.review("offline")


def test_cleanup_one_attempt_even_when_first_failed(tmp_path, monkeypatch):
    review_fixture(tmp_path, monkeypatch)
    w.exclusive("offline-intent.json", {"outcome": "unknown_no_retry"})
    with pytest.raises(RuntimeError, match="existing_intent_NO_RETRY"):
        w.review("offline")


def test_no_functional_path_gate_or_base_bypass_and_ETag_last():
    text = inspect.getsource(w.capture)
    assert 'c.inheritance(reads)' in text
    assert 'inherited == prior["inheritance"]' in text
    assert "path_semantics_proven" in text
    assert "require(path_proven" not in text
    assert text.index('exports(formats, policy)') < text.index('last_api, etag')
    assert text.index('blob_head()') < text.index('last_api, etag')
    assert "len(baseline) == 13" in text and 'owned[0]["is_current"] is False' in text


def test_wire_one_open_no_retry_no_body_capture():
    text = inspect.getsource(w.wire_child)
    assert text.count(".open(") == 1 and "timeout=45" in text
    assert ".read(" not in text and "safe_http" in text
    watchdog = inspect.getsource(w.once)
    assert "rx.poll(60)" in watchdog and "unknown_no_retry" in watchdog
    assert "child.terminate()" in watchdog and "child.kill()" in watchdog


def test_execution_intent_before_wire_and_postread_even_on_failure():
    text = inspect.getsource(w.execute)
    assert text.index('exclusive(stage + "-intent.json"') < text.index('result = once(')
    assert text.index('after = capture(') < text.index('require(result.get(')
    assert 'False if stage == "online" else None' in text
    assert "check_window" not in text  # review enforces only online window


def test_prepare_both_cleanup_and_online_bodies_before_GETs_no_mutation():
    text = inspect.getsource(w.prepare)
    assert text.index('for stage, body in BODIES.items()') < text.index('before = capture(')
    assert "execute(" not in text and "once(" not in text
    assert "existing_package_reconcile_only" in text


def test_browser_reservation_durable_before_parent_Send_no_controller_score():
    text = inspect.getsource(w.reserve_browser)
    assert 'exclusive("reserve-browser-intent.json"' in text
    assert '"completion_budget": 0' in text and '"retry_budget": 0' in text
    assert 'online["intent_sha256"]' in text and 'capture(c.Reads()' in text
    source = inspect.getsource(w)
    assert '"send-request"' not in source and 'method="POST"' not in source


def test_browser_helper_URL_only_no_header_or_storage_reads():
    text = w.BROWSER.read_text()
    assert "route.continue({ url: REVISION })" in text
    assert "consumed = true" in text and "route.abort" in text
    for forbidden in (".headers(", ".allHeaders(", "localStorage", "sessionStorage", "storageState(", "route.fetch(", ".click("):
        assert forbidden not in text


def test_exact_actual_exports_and_mutations_rejected():
    # Pure verifier runs against synthetic whole expressions; actual retained
    # XML compile binding above is checked without cloud access.
    spec = w.importlib.util.spec_from_file_location("fixture_verifier", w.VERIFY)
    verifier = w.importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    assert verifier.regression(w.c) == {"positive_cases": 2, "negative_cases": 8, "failures": 0}


def test_native_node_browser_helper_without_esbuild_or_network():
    result = subprocess.run(["C:/Program Files/nodejs/node.exe", "--test", "tests/auto_diagnostic_browser.test.mjs"],
                            cwd=w.p.rt.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests 3" in result.stdout and "fail 0" in result.stdout


def test_offline_review_assembly_does_not_repeat_failed_GET_or_mutate():
    text = inspect.getsource(w.prepare_review)
    assert "capture(" not in text and "once(" not in text and "execute(" not in text
    assert "RETAINED_GET_EVIDENCE_NOT_FRESH_LIVE_PREPARE" in text
    assert "existing_manifest_reconcile_only" in text