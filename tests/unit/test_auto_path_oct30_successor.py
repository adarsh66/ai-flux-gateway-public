"""Offline only. Retained actual evidence is never overwritten or replayed."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import shutil
from unittest.mock import Mock
from urllib.request import Request
import xml.etree.ElementTree as ET

import pytest

from scripts.deployment import auto_path_oct30_successor as s
from scripts.deployment import auto_path_oct30_successor_reads as reads

d = s.d
START, END = "2026-10-30T12:00:00Z", "2026-10-30T12:30:00Z"
AT = datetime(2026, 10, 30, 12, 1, tzinfo=UTC)
NONCE = "1234567890abcdef1234567890abcdef"
spec = importlib.util.spec_from_file_location("oct30_old_test_helpers", d.ROOT / "tests/unit/test_auto_path_diagnostic_oct30.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import socket
    denied = Mock(side_effect=AssertionError("offline network forbidden"))
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(d.a, "opener", denied)
    monkeypatch.setattr(d, "send_once", denied)
    yield
    denied.assert_not_called()


@pytest.fixture(scope="module")
def actual():
    return s.investigation_baseline()


@pytest.fixture(scope="module")
def payloads(actual):
    return s.render(d.policy_values(actual["formats"]["global"])["xml"].encode(),
                    d.FIXTURE.read_bytes(), START, END, NONCE)


@pytest.fixture
def package(tmp_path, actual, payloads, monkeypatch):
    folder = legacy.package.__wrapped__(tmp_path, actual, payloads, monkeypatch)
    renamed = folder.with_name(s.PREFIX + "TEST_ONLY")
    folder.rename(renamed)
    manifest = d.load(renamed / "manifest.json")
    manifest.update(at_utc=START, start=START, end=END)
    (renamed / "manifest.json").write_bytes(d.encode(manifest))
    for name in ("parent-review.json", "browser-preflight.json"):
        value = d.load(renamed / name)
        value.update(at_utc=AT.isoformat(), manifest_sha256=d.sha((renamed / "manifest.json").read_bytes()))
        (renamed / name).write_bytes(d.encode(value))
    before = d.load(renamed / "fresh-before.json")
    before["at_utc"] = AT.isoformat()
    (renamed / "fresh-before.json").write_bytes(d.encode(before))
    # Actual source/receipt validation is exercised independently. These
    # deliberately marked fixtures test the inherited state machine ONLY.
    monkeypatch.setattr(s.controller, "localcheck", lambda _: d.load(renamed / "manifest.json"))
    return renamed


def test_actual_latest_chain_and_old_guard_rejection(actual):
    before, final, _ = s.predecessor()
    assert actual["baseline"] == final["baseline"]
    assert len(actual["baseline"]) == 13
    s.initial(actual)
    with pytest.raises(RuntimeError, match="both_policy_formats_match_wire"):
        s.old.initial(actual)
    assert not (s.PREDECESSOR / "online-verified.json").exists()
    assert d.load(s.PREDECESSOR / "online-result.json") == {"http_status": 200}
    assert before != actual


def test_all_210_sources_and_consumed_files_immutable():
    s.predecessor()
    manifest = d.load(s.PREDECESSOR / "manifest.json")
    assert len(manifest["sources"]) == 210
    assert d.sha(d.encode(manifest["sources"])) == s.SOURCE_SHA
    assert all(d.sha((d.ROOT / name).read_bytes()) == digest for name, digest in manifest["sources"].items())
    assert s.controller is not s.old.controller and s.controller is not d
    assert s.controller.IP == s.old.IP != d.IP
    assert s.Stages._execute.__globals__ is vars(s.controller)
    assert s.Stages.activate.__globals__ is vars(s.controller)
    assert s.controller.send_once is not d.send_once  # autouse denies only public alias in this test


@pytest.mark.parametrize("name", list(d.load(s.INVESTIGATION / "retained-audit.json")["consumed_package_file_sha256"]))
def test_each_consumed_file_change_rejected(tmp_path, monkeypatch, name):
    clone = tmp_path / "consumed_TEST_ONLY"
    shutil.copytree(s.PREDECESSOR, clone)
    monkeypatch.setattr(s, "PREDECESSOR", clone)
    (clone / name).write_bytes((clone / name).read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="pinned_evidence_hash"):
        s.predecessor()


@pytest.mark.parametrize("name", ["online-after.json", "online-verified.json", "reserve-before.json",
    "reserve-intent.json", "reserve-result.json", "reserve-verified.json", "browser-send-intent.json",
    "browser-reservation.json", "browser-claim-intent.json", "browser-binding.json",
    "parent-browser-request.json", "parent-browser-response.json"])
def test_no_fabricated_online_reserve_or_browser_evidence(tmp_path, monkeypatch, name):
    clone = tmp_path / "consumed_TEST_ONLY"
    shutil.copytree(s.PREDECESSOR, clone)
    monkeypatch.setattr(s, "PREDECESSOR", clone)
    (clone / name).write_text("{}")
    with pytest.raises(RuntimeError, match="exact_consumed_inventory"):
        s.predecessor()


@pytest.mark.parametrize("field", list(d.load(s.INVESTIGATION / "capture.json")["baseline"]))
def test_every_full13_component_drift_rejected(actual, field):
    bad = deepcopy(actual)
    bad["baseline"][field] = "drift"
    with pytest.raises((RuntimeError, KeyError, TypeError)):
        s.initial(bad)


@pytest.mark.parametrize("field", ["supplemental", "project", "runtime", "storage_sha256", "current_api_sha256",
                                   "owned_api", "inheritance", "revisions", "api_etag"])
def test_all_other_protected_state(actual, field):
    bad = deepcopy(actual)
    bad[field] = {} if isinstance(bad[field], dict) else "drift"
    with pytest.raises((RuntimeError, KeyError, TypeError, ValueError)):
        s.initial(bad)


@pytest.mark.parametrize("kind,fmt", [(k, f) for k in ("global", "revision") for f in ("xml", "rawxml")])
def test_each_format_drift_cannot_be_adopted(actual, kind, fmt):
    bad = deepcopy(actual)
    bad["formats"][kind][fmt]["body"]["properties"]["value"] += "<drift/>"
    with pytest.raises((RuntimeError, ET.ParseError)):
        s.initial(bad)


def test_independent_raw_hash_cannot_be_hidden(actual):
    bad = deepcopy(actual)
    bad["baseline"]["apim"]["global"] = "0" * 64
    with pytest.raises(RuntimeError, match="full13_global_raw_hash_binding"):
        s.initial(bad)


def test_candidate_from_original_fixture_only(actual, payloads):
    for name in ("global.xml", "revision.xml"):
        assert payloads[name].count(s.old.IP.encode()) == 1
        assert s.old.OLD_IP.encode() not in payloads[name]
    assert s.counter(payloads["revision.xml"]) == NONCE
    predicate = s.controller.expression(START, END)
    assert s.old.IP in predicate and s.old.OLD_IP not in predicate
    with pytest.raises(RuntimeError, match="render_original_diagnostic06_only"):
        s.render(d.policy_values(actual["formats"]["global"])["xml"].encode(),
                 (s.PREDECESSOR / "revision.xml").read_bytes(), START, END, NONCE)
    with pytest.raises(RuntimeError, match="window_at_most_30_minutes|offline_proposal_renderer_failed"):
        s.render(d.policy_values(actual["formats"]["global"])["xml"].encode(), d.FIXTURE.read_bytes(),
                 START, "2026-10-30T12:30:01Z", NONCE)


@pytest.mark.parametrize("package", [s.PREDECESSOR, s.old.prior.PREDECESSOR])
def test_latest_and_older_counter_reuse_rejected(actual, package):
    nonce = s.counter((package / "revision.xml").read_bytes())
    with pytest.raises(RuntimeError, match="no_consumed_counter_reuse"):
        s.render(d.policy_values(actual["formats"]["global"])["xml"].encode(), d.FIXTURE.read_bytes(), START, END, nonce)


def test_new_source_set_retains_all210_and_new_files():
    frozen = s.sources()
    for name, digest in d.load(s.PREDECESSOR / "manifest.json")["sources"].items():
        assert frozen[name] == digest
    for name in ("scripts/deployment/auto_path_oct30_successor.py", "scripts/deployment/auto_path_oct30_successor_reads.py",
                 "tests/unit/test_auto_path_oct30_successor.py", "docs/auto-path-oct30-successor.md"):
        assert frozen[name] == d.sha((d.ROOT / name).read_bytes())


def test_real_localcheck_offline_fixture_and_exact_own_owner(tmp_path, actual, payloads):
    # Construct an explicitly offline fixture, NOT prepare() or a live window.
    folder = tmp_path / (s.PREFIX + "LOCALCHECK_TEST_ONLY")
    folder.mkdir()
    for name, value in payloads.items():
        d.exclusive(folder / name, value)
    d.exclusive(folder / "fresh-before.json", actual)
    d.exclusive(folder / "browser-source.js", s.controller.browser_source().encode())
    historical = d.load(s.PREDECESSOR / "manifest.json")
    manifest = {"at_utc": START, "start": START, "end": END, "sources": s.sources(),
        "artifacts": {p.name: d.sha(p.read_bytes()) for p in folder.iterdir()},
        "tests": historical["tests"], "native_tests": historical["native_tests"],
        "stages": list(d.STAGES), "scope": d.SCOPE, "scoring_budget": 1,
        "retry_budget": 0, "completion_budget": 0, "historical_scoring_request_count": None}
    d.exclusive(folder / "manifest.json", manifest)
    assert s.localcheck(folder) == manifest
    d.exclusive(folder / "browser-send-intent.json", {"TEST_ONLY": True})
    owner = {"manifest_sha256": d.sha((folder / "manifest.json").read_bytes()),
        "parent_intent_sha256": d.sha((folder / "browser-send-intent.json").read_bytes()), "scope": d.SCOPE}
    owner_path = tmp_path / "auto-path-diagnostic-attempt-owner.json"
    d.exclusive(owner_path, owner)
    assert s.localcheck(folder) == manifest
    owner["manifest_sha256"] = "0" * 64
    owner_path.write_bytes(d.encode(owner))
    with pytest.raises(RuntimeError, match="only_own_exact_owner"):
        s.localcheck(folder)
    owner_path.unlink()
    wire = d.c.tree((folder / "revision.xml").read_bytes())
    d.c.post(wire).find("limit-concurrency")[0].set("calls", "2")
    (folder / "revision.xml").write_bytes(ET.tostring(wire, encoding="utf-8"))
    manifest["artifacts"]["revision.xml"] = d.sha((folder / "revision.xml").read_bytes())
    (folder / "manifest.json").write_bytes(d.encode(manifest))
    with pytest.raises(RuntimeError, match="exact_new_fixture_delta"):
        s.localcheck(folder)


def test_parent_cli_is_actual_existing_private_bounded_parent():
    from scripts.deployment import auto_path_oct30_parent as original
    parent = s.parent_cli()
    assert parent.s is s and original.s is s.old
    assert parent.main.__code__ is original.main.__code__
    assert parent.run_parent.__globals__ is vars(parent)
    assert parent.checked_package.__globals__ is vars(parent)
    assert s.file_browser_handoff.__code__ is s.old.file_browser_handoff.__code__


def test_full_inherited_parent_reserve_claim_cleanup(package):
    fake = legacy.Fake(package)
    seen = []
    def browser(binding):
        seen.append(binding)
        assert binding["reservation"]["IP"] == s.old.IP
        return "TEST_ONLY_NO_SEND"
    assert s.run_reviewed_window(package, fake, browser, lambda: AT) == "TEST_ONLY_NO_SEND"
    assert len(seen) == 1 and fake.captures == 18
    assert fake.calls == ["install-global", "install-revision", "online", "offline", "restore-global"]
    assert all((package / (stage + "-verified.json")).exists() for stage in d.STAGES)
    with pytest.raises((RuntimeError, FileExistsError)):
        s.run_reviewed_window(package, fake, browser, lambda: AT)


def test_online_HTTP200_postread_timeout_cleans_once_never_fakes_proof(package):
    class TimeoutFake(legacy.Fake):
        def capture(self):
            if self.calls and self.calls[-1] == "online" and not getattr(self, "timed_out", False):
                self.timed_out = True
                raise TimeoutError("SECRET_NOT_FOR_LOGGING")
            return super().capture()
    fake = TimeoutFake(package)
    callback = Mock()
    with pytest.raises(TimeoutError):
        s.run_reviewed_window(package, fake, callback, lambda: AT)
    callback.assert_not_called()
    assert d.load(package / "online-result.json") == {"http_status": 200}
    assert not (package / "online-after.json").exists() and not (package / "online-verified.json").exists()
    assert fake.calls.count("offline") == fake.calls.count("restore-global") == 1
    assert (package / "restore-global-verified.json").exists()


@pytest.mark.parametrize("failure", ["install-revision", "online", "reserve", "browser", "claim"])
def test_inherited_finally_and_no_replay(package, monkeypatch, failure):
    fake = legacy.Fake(package)
    fake.fail = failure
    callback = Mock(side_effect=RuntimeError("fixture_browser"))
    if failure == "claim":
        monkeypatch.setattr(s.controller, "claim", Mock(side_effect=RuntimeError("fixture_claim")))
    with pytest.raises(RuntimeError):
        s.run_reviewed_window(package, fake, callback, lambda: AT)
    assert (package / "offline-verified.json").exists() and (package / "restore-global-verified.json").exists()
    assert fake.calls.count("restore-global") == 1


def test_late_budget_stops_before_intent(package):
    fake = legacy.Fake(package)
    with pytest.raises(RuntimeError, match="insufficient_window"):
        s.run_reviewed_window(package, fake, Mock(), lambda: AT + timedelta(minutes=3))
    assert fake.calls == [] and not (package / "parent-window-intent.json").exists()


@pytest.mark.parametrize("corruption", ["review", "preflight"])
def test_review_and_genuine_preflight_still_required(package, corruption):
    name = "parent-review.json" if corruption == "review" else "browser-preflight.json"
    value = d.load(package / name)
    if corruption == "review":
        value["stages"] = ["offline"]
    else:
        value["fixture"] = True
    (package / name).write_bytes(d.encode(value))
    fake = legacy.Fake(package)
    with pytest.raises(RuntimeError):
        s.run_reviewed_window(package, fake, Mock(), lambda: AT)
    assert fake.calls == []


@pytest.mark.parametrize("kind", ["success", "open_timeout", "body_timeout"])
@pytest.mark.parametrize("timeout", [45, 60, 90])
def test_timing_one_open_includes_body_sanitizes_and_preserves_timeout(tmp_path, kind, timeout):
    response = Mock()
    response.status = 200
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    if kind == "open_timeout":
        opener.open.side_effect = TimeoutError("BEARER_SECRET_url_header_body")
    req = Request(d.GLOBAL_URL + "&format=rawxml", headers={"Authorization": "Bearer SECRET"})
    folder = tmp_path / "TEST_ONLY_TIMING"
    with reads.diagnostics(folder, "online"):
        if kind == "success":
            with reads.TimedOpen(opener).open(req, timeout=timeout) as result:
                assert result is response
        else:
            with pytest.raises(TimeoutError):
                with reads.TimedOpen(opener).open(req, timeout=timeout):
                    raise TimeoutError("BODY_SECRET")
    opener.open.assert_called_once_with(req, timeout=timeout)
    target = tmp_path / (folder.name + "-online-read-diagnostics")
    start = d.load(target / "000001-start.json")
    end = d.load(target / "000001-end.json")
    assert end["monotonic_end_ns"] >= start["monotonic_start_ns"]
    assert end["elapsed_ns"] >= 0 and end["timeout_seconds"] == timeout
    assert end["failure_type"] == (None if kind == "success" else "TimeoutError")
    assert end["http_status"] == (None if kind == "open_timeout" else 200)
    assert end["format"] == "rawxml" and end["stage"] == "online"
    serialized = b"".join(p.read_bytes() for p in target.iterdir())
    assert all(word not in serialized for word in (b"SECRET", b"Bearer", b"https:", b"Authorization"))
    assert reads._context.get() is None


@pytest.mark.parametrize("url,method", [("https://evil.invalid/x", "GET"), (d.GLOBAL_URL, "PUT"),
    (d.GLOBAL_URL, "PATCH"), (d.GLOBAL_URL, "DELETE"), (d.GLOBAL_URL, "POST"),
    (d.GLOBAL_URL.replace("https:", "http:"), "GET"), (d.GLOBAL_URL + "#secret", "GET")])
def test_transport_rejects_nonread_and_arbitrary_destination(tmp_path, url, method):
    opener = Mock()
    with reads.diagnostics(tmp_path / "TEST_ONLY_DENY", "offline"):
        with pytest.raises(RuntimeError):
            with reads.TimedOpen(opener).open(Request(url, method=method), timeout=45):
                pytest.fail("must not open")
    opener.open.assert_not_called()


def test_private_reader_restores_bindings_on_failure(monkeypatch):
    original = d.c.Reads
    private, product = reads.private_controller({})
    assert d.c.Reads is original and private.c is not d.c and private.c.Reads is not original
    assert private.a is not d.a
    assert private.collect.__globals__ is vars(private)
    assert private.remote_state.__globals__ is vars(private)
    release = private.r.persistence.release
    prior = release.ProductRun
    from contextlib import contextmanager
    @contextmanager
    def local_transport():
        yield
    private.read_transport = local_transport
    with pytest.raises(TimeoutError):
        with s.tools.strict_read_context(private, product, {}):
            assert release.ProductRun is product
            raise TimeoutError()
    assert release.ProductRun is prior and d.c.Reads is original


@pytest.mark.parametrize("name", ["../escape", "/absolute", "missing"])
def test_pinned_paths_no_escape_or_missing(tmp_path, name):
    with pytest.raises(RuntimeError):
        s.checked_file(tmp_path, name)