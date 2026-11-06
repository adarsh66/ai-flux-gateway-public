"""Network-denied r4 temporary fixtures; never real approvals or a prepare."""
from copy import deepcopy
from datetime import timedelta
import importlib.util
from pathlib import Path
import socket
from unittest.mock import Mock

import pytest

from scripts.deployment import auto_path_oct30_successor_r4 as r4

d, s = r4.d, r4.r3
spec = importlib.util.spec_from_file_location("r4_retained_fixture_helpers",
    d.ROOT / "tests/unit/test_auto_path_oct30_successor.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
START, END, AT = helpers.START, helpers.END, helpers.AT


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    denied = Mock(side_effect=AssertionError("OFFLINE_NETWORK_OR_WRITE_FORBIDDEN"))
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(d, "send_once", denied)
    monkeypatch.setattr(r4.controller, "send_once", denied)
    yield
    denied.assert_not_called()


@pytest.fixture(scope="module")
def actual():
    return s.investigation_baseline()


@pytest.fixture(scope="module")
def payloads(actual):
    return s.render(d.policy_values(actual["formats"]["global"])["xml"].encode(),
                    d.FIXTURE.read_bytes(), START, END, helpers.NONCE)


@pytest.fixture
def package(tmp_path, actual, payloads, monkeypatch):
    folder = helpers.package.__wrapped__(tmp_path, actual, payloads, monkeypatch)
    renamed = folder.with_name(r4.PREFIX + "TEST_ONLY")
    folder.rename(renamed)
    monkeypatch.setattr(r4.controller, "localcheck", lambda _: d.load(renamed / "manifest.json"))
    return renamed


def clock(package, remaining):
    at = d.datetime.fromisoformat(END) - timedelta(minutes=remaining)
    value = d.load(package / "fresh-before.json")
    value["at_utc"] = at.isoformat()
    (package / "fresh-before.json").write_bytes(d.encode(value))
    return lambda: at


def test_private_no_r3_rebinding_and_exact_22_not_27():
    assert r4.MINIMUM_REMAINING == timedelta(minutes=22)
    assert s.old.MINIMUM_REMAINING == timedelta(minutes=27)
    assert r4.controller is not s.controller
    assert r4.Stages is not s.Stages
    assert s.Stages._execute.__globals__ is vars(s.controller)
    assert r4.Stages._execute.__globals__ is vars(r4.controller)
    assert r4.successor._run_reviewed_window.__code__ is s.old.run_reviewed_window.__code__
    assert r4.parent_cli().s is r4.successor
    assert r4.parent_cli().main.__code__ is s.parent_cli().main.__code__
    assert r4.controller.review.__code__ == d.review.__code__
    assert r4.controller.claim.__code__ == d.claim.__code__


@pytest.mark.parametrize("remaining", [27, 23, 22])
def test_launch_passes_23_and_inclusive22_complete_all_six(package, remaining):
    now = clock(package, remaining)
    fake = helpers.legacy.Fake(package)
    callback = Mock(return_value="TEST_ONLY_NO_SEND")
    assert r4.run_reviewed_window(package, fake, callback, now) == "TEST_ONLY_NO_SEND"
    assert fake.captures == 18
    assert fake.calls == ["install-global", "install-revision", "online", "offline", "restore-global"]
    assert all((package / (stage + "-verified.json")).exists() for stage in d.STAGES)
    binding = callback.call_args.args[0]
    assert binding["reservation"]["scoring_budget"] == 1
    assert binding["reservation"]["completion_budget"] == binding["reservation"]["retry_budget"] == 0


@pytest.mark.parametrize("remaining", [21, 0, -1])
def test_late_or_expired_launch_has_no_intents_no_rollback(package, remaining):
    fake = helpers.legacy.Fake(package)
    callback = Mock()
    with pytest.raises(RuntimeError, match="insufficient_window|window_and_cleanup_reserve"):
        r4.run_reviewed_window(package, fake, callback, clock(package, remaining))
    assert fake.calls == [] and fake.captures == 0
    assert list(package.glob("*-intent.json")) == []
    callback.assert_not_called()


@pytest.mark.parametrize("stage", [x for x in d.STAGES if x not in d.CLEANUP])
@pytest.mark.parametrize("seconds", [90, 89, 0, -1])
def test_actual_stage_guard_fixed_end_minus90_no_intent(package, stage, seconds):
    now = lambda: d.datetime.fromisoformat(END) - timedelta(seconds=seconds)
    with pytest.raises(RuntimeError, match="window_and_cleanup_reserve"):
        r4.controller.review(package, stage, now)
    assert list(package.glob("*-intent.json")) == []


@pytest.mark.parametrize("stage", [x for x in d.STAGES if x not in d.CLEANUP])
def test_actual_stage_guard_91_seconds_still_allowed(package, stage):
    now = lambda: d.datetime.fromisoformat(END) - timedelta(seconds=91)
    r4.controller.review(package, stage, now)


@pytest.mark.parametrize("failure", ["install-global", "install-revision", "online", "reserve", "claim", "browser"])
def test_failure_each_stage_retains_finally_no_replay(package, monkeypatch, failure):
    now = clock(package, 23)
    fake = helpers.legacy.Fake(package)
    fake.fail = failure
    if failure == "claim":
        monkeypatch.setattr(r4.controller, "claim", Mock(side_effect=RuntimeError("fixture_claim")))
    browser = Mock(side_effect=RuntimeError("fixture_browser"))
    with pytest.raises(RuntimeError):
        r4.run_reviewed_window(package, fake, browser, now)
    if failure == "install-global":
        assert fake.calls == [] and not (package / "offline-intent.json").exists()
    else:
        assert fake.calls.count("restore-global") == 1
        assert fake.calls.count("offline") == (0 if failure in ("install-revision", "online") else 1)
        assert (package / "offline-verified.json").exists()
        assert (package / "restore-global-verified.json").exists()
        with pytest.raises((RuntimeError, FileExistsError)):
            r4.Stages(package, fake, lambda: AT).cleanup()


def test_cleanup_after_expiry_on_browser_failure(package):
    at = [d.datetime.fromisoformat(END) - timedelta(minutes=23)]
    clock(package, 23)
    fake = helpers.legacy.Fake(package)
    def browser(_):
        at[0] = d.datetime.fromisoformat(END) + timedelta(days=1)
        fake.value["at_utc"] = at[0].isoformat()
        raise RuntimeError("fixture_expired_browser")
    with pytest.raises(RuntimeError, match="fixture_expired_browser"):
        r4.run_reviewed_window(package, fake, browser, lambda: at[0])
    assert fake.calls[-2:] == ["offline", "restore-global"]
    assert all((package / (stage + "-verified.json")).exists() for stage in d.CLEANUP)


@pytest.mark.parametrize("target", ["install-global", "install-revision", "online", "reserve"])
def test_second_review_after_last_read_rejects_deadline_crossing(package, target):
    at = [clock(package, 23)()]
    class Crossing(helpers.legacy.Fake):
        def capture(self):
            self.latest_capture = super().capture()
            return self.latest_capture

        def last(self, stage):
            actual = self.latest_capture
            value, etag = super().last(stage)
            if stage == target:
                at[0] = d.datetime.fromisoformat(END) - timedelta(seconds=90)
                # Production last() updates the SAME captured object, not a
                # replacement. Preserve that contract while advancing UTC.
                self.value["at_utc"] = value["at_utc"] = actual["at_utc"] = at[0].isoformat()
            return value, etag
    fake = Crossing(package)
    with pytest.raises(RuntimeError, match="window_and_cleanup_reserve"):
        r4.run_reviewed_window(package, fake, Mock(), lambda: at[0])
    assert not (package / (target + "-intent.json")).exists()
    assert target not in fake.calls
    if target == "install-global":
        assert not (package / "offline-intent.json").exists()
    else:
        assert fake.calls[-1] == "restore-global"
        assert all((package / (stage + "-verified.json")).exists() for stage in d.CLEANUP)


def test_unchanged_30min_window_and_UTC():
    assert r4.controller.window(START, END)[1] - r4.controller.window(START, END)[0] == timedelta(minutes=30)
    with pytest.raises(RuntimeError):
        r4.controller.window(START, "2026-10-30T12:30:01Z")
    with pytest.raises(RuntimeError):
        r4.controller.window("2026-10-30T12:00:00+01:00", END)


def test_exact_input_memo_hits_and_mutable_copy(actual):
    pair = deepcopy(actual["formats"]["global"])
    r4._formats.cache_clear()
    first = r4.verify_formats(pair)
    first.set("TEST_ONLY_POISON", "true")
    second = r4.verify_formats(pair)
    assert second.get("TEST_ONLY_POISON") is None
    assert r4._formats.cache_info().hits == 1
    pair["xml"]["etag"] = '"changed"'
    r4.verify_formats(pair)
    assert r4._formats.cache_info().misses == 2
    pair["rawxml"]["body"]["properties"]["value"] += "<drift/>"
    for _ in range(2):
        with pytest.raises(Exception):
            r4.verify_formats(pair)
    assert r4._formats.cache_info().misses == 4


def test_wire_bytes_part_of_cache_key(actual):
    pair = actual["formats"]["global"]
    r4.verify_formats(pair)
    with pytest.raises(RuntimeError, match="both_policy_formats_match_wire"):
        r4.verify_formats(pair, b"<policies/>")


def test_real_localcheck_keeps_all_hashes_each_time(tmp_path, actual, payloads):
    folder = tmp_path / (r4.PREFIX + "REAL_LOCALCHECK_TEST_ONLY")
    folder.mkdir()
    for name, value in payloads.items():
        d.exclusive(folder / name, value)
    d.exclusive(folder / "fresh-before.json", actual)
    d.exclusive(folder / "browser-source.js", r4.controller.browser_source().encode())
    historical = d.load(s.PREDECESSOR / "manifest.json")
    manifest = {"at_utc": START, "start": START, "end": END, "sources": r4.sources(),
        "artifacts": {p.name: d.sha(p.read_bytes()) for p in folder.iterdir()},
        "tests": historical["tests"], "native_tests": historical["native_tests"],
        "stages": list(d.STAGES), "scope": d.SCOPE, "scoring_budget": 1,
        "retry_budget": 0, "completion_budget": 0, "historical_scoring_request_count": None}
    d.exclusive(folder / "manifest.json", manifest)
    assert r4.localcheck(folder) == manifest
    assert r4.localcheck(folder) == manifest
    (folder / "global.xml").write_bytes((folder / "global.xml").read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="artifact_drift"):
        r4.localcheck(folder)
    manifest["sources"]["scripts/deployment/auto_path_oct30_successor_r4.py"] = "0" * 64
    (folder / "manifest.json").write_bytes(d.encode(manifest))
    with pytest.raises(RuntimeError, match="source_drift"):
        r4.localcheck(folder)


def test_all_historical265_and_six_artifacts_unchanged():
    folder = d.ROOT / ".deployment/auto-path-oct30-successor-20261030T074052868393Z"
    manifest = d.load(folder / "manifest.json")
    assert d.sha((folder / "manifest.json").read_bytes()) == "7d54f350d05e6139dd5d1b871c97a925256a5533b2d7b298ddf7ac38601bb75a"
    assert len(manifest["sources"]) == 265
    assert all(d.sha((d.ROOT / name).read_bytes()) == digest for name, digest in manifest["sources"].items())
    assert all(d.sha((folder / name).read_bytes()) == digest for name, digest in manifest["artifacts"].items())
    assert not any((folder / name).exists() for name in ("parent-window-intent.json",
        "activation-intent.json", "browser-send-intent.json", "browser-claim-intent.json",
        *(stage + "-intent.json" for stage in d.STAGES)))