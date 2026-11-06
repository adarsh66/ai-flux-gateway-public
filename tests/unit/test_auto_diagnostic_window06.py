"""06 local evidence, exact adapters and real disk claim tests. No cloud calls."""
from datetime import UTC, datetime, timedelta
import inspect
import json

import pytest
from scripts.deployment import auto_diagnostic_window06 as x


def test_actual05b_cleanup_sources_history_no_replay():
    old = x.predecessor()
    assert old["nonce"] == x.base.predecessor()["nonce"]
    assert x.a.load(x.OLD / "offline-after-capture.json")["state_owner"]["serial"] == 185


@pytest.mark.parametrize("name", list(x.RECEIPTS))
def test_actual05b_receipt_drift_rejected(name, monkeypatch):
    sha = x.p.sha
    monkeypatch.setattr(x.p, "sha", lambda path: "bad" if path == x.OLD / name else sha(path))
    with pytest.raises(RuntimeError, match="cleanup_receipts_exact"):
        x.predecessor()


def test_all05b_original_sources_checked(monkeypatch):
    sha = x.p.sha
    monkeypatch.setattr(x.p, "sha", lambda path: "bad" if path == x.previous.BROWSER else sha(path))
    with pytest.raises(RuntimeError, match="original_sources_and_history_exact"):
        x.predecessor()


def test_history_preserves05b_every_file_and_all04():
    hashes = x.history()
    for path in x.OLD.iterdir():
        assert hashes[path.relative_to(x.p.rt.ROOT).as_posix()] == x.p.sha(path)
    assert not any(k.startswith(x.OUT.relative_to(x.p.rt.ROOT).as_posix() + "/") for k in hashes)


def test_bindings_restore_transport_and_expect_actual05b_before_put():
    original = x.previous.OUT, x.base.OUT, x.w.OUT, x.base.prior.prior.DIAG, x.w.exports
    transport = x.w.execute, x.w.once, x.w.capture, x.base.prior.policy_put
    with pytest.raises(ValueError):
        with x.bindings():
            assert x.previous.OUT == x.base.OUT == x.w.OUT == x.OUT
            assert x.base.prior.prior.DIAG == x.OLD
            assert x.w.exports is x.exports and x.w.BROWSER == x.BROWSER
            assert transport == (x.w.execute, x.w.once, x.w.capture, x.base.prior.policy_put)
            raise ValueError("fixture")
    assert original == (x.previous.OUT, x.base.OUT, x.w.OUT, x.base.prior.prior.DIAG, x.w.exports)


def test_exact_policy_nonce_quota_security_no_new_allowance():
    old = x.predecessor()
    before = x.c.tree((x.OLD / "diagnostic.xml").read_bytes())
    after = x.c.tree(x.base.candidate("2026-10-29T11:00:00+00:00", "2026-10-29T11:30:00+00:00"))
    after.find("inbound").remove(after.find("inbound")[2])
    after.find("inbound").insert(2, x.base.scope_guard(old["start"], old["end"]))
    assert x.c.signature(before) == x.c.signature(after)
    quota = x.c.post(before).find("limit-concurrency")[0]
    assert quota.get("calls") == "1" and quota.get("renewal-period") == "3600"


def test_prepare_no_cloud_and_no_refresh(tmp_path, monkeypatch):
    for fn in (x.prepare, x.predecessor, x.check_package):
        for forbidden in (".capture(", ".execute(", ".once(", "urlopen(", "get-access-token"):
            assert forbidden not in inspect.getsource(fn)
    monkeypatch.setattr(x, "OUT", tmp_path)
    with pytest.raises(RuntimeError, match="NEVER_refresh"):
        x.prepare(tmp_path / "missing", tmp_path / "missing2")


def test_inline_pure_no_timer_globals():
    text = x.inline_source()
    assert text.startswith("async function diagnostic06Attempt(page, binding) {") and text.endswith("}")
    for forbidden in ("setTimeout", "clearTimeout", "node:", "import(", ".click(", ".evaluate("):
        assert forbidden not in text


def test_actual_browser_preflight_source_receipt_exact():
    assert x.browser_preflight() == x.p.sha(x.PREFLIGHT)


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    monkeypatch.setattr(x, "OWNER", tmp_path / "owner.json")
    now = datetime.now(UTC)
    start, end = (now - timedelta(minutes=1)).isoformat(), (now + timedelta(minutes=29)).isoformat()
    def save(name, value):
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    m = {"at_utc": start, "start": start, "end": end, "inline_sha256": "a" * 64}
    save("manifest.json", m)
    (tmp_path / "native.txt").write_text("FIXTURE NOT ACTUAL REVIEW")
    save("parent-review.json", {"approved": True, "independent_native_review": True,
        "manifest_sha256": x.p.sha(tmp_path / "manifest.json"), "stages": x.base.STAGES,
        "at_utc": start, "transcript": "native.txt", "transcript_sha256": x.p.sha(tmp_path / "native.txt")})
    save("reserve-browser-intent.json", {"manifest_sha256": x.p.sha(tmp_path / "manifest.json"),
        "review_sha256": x.p.sha(tmp_path / "parent-review.json"), "browser_source_sha256": x.p.sha(x.BROWSER),
        "IP": x.base.IP, "fixed_text": x.c.TEXT, "model": "gpt-5.4-mini", "path": x.c.CHAT_PATH,
        "end": end, "attempt_budget": 1, "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0})
    save("activate-result.json", {"status": "ONLINE_READY", "manifest_sha256": x.p.sha(tmp_path / "manifest.json"),
        "reservation_sha256": x.p.sha(tmp_path / "reserve-browser-intent.json")})
    save("browser-send-intent.json", {"scope": x.SCOPE, "manifest_sha256": x.p.sha(tmp_path / "manifest.json"),
        "correction_of": x.CORRECTION, "cleanup_complete": True,
        "reservation_sha256": x.p.sha(tmp_path / "reserve-browser-intent.json"),
        "review_sha256": x.p.sha(tmp_path / "parent-review.json"), "browser_source_sha256": x.p.sha(x.BROWSER),
        "inline_sha256": m["inline_sha256"], "attempt_budget": 1, "scoring_budget": 1,
        "retry_budget": 0, "completion_budget": 0, "new_scope_consumed": True,
        "parent_local_disk_review_verified": True, "at_utc": now.isoformat()})
    monkeypatch.setattr(x, "check_package", lambda: m)
    return save


def test_parent_claim_real_exclusive_no_reclaim(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    with x.bindings():
        binding = x.claim_send()
        assert binding["scope"] == x.SCOPE and binding["shared_owner_sha256"] == x.p.sha(x.OWNER)
        assert binding["cleanup_complete"] is binding["parent_claim_durable"] is True
        assert binding == x.a.load(tmp_path / "browser-binding.json")
        with pytest.raises(RuntimeError, match="NO_RETRY"):
            x.claim_send()


@pytest.mark.parametrize("field,value", [("attempt_budget", 2), ("scope", "DIAGNOSTIC05_05B_ONE_USER_ATTEMPT"),
    ("retry_budget", 1), ("completion_budget", 1), ("inline_sha256", "bad"), ("parent_local_disk_review_verified", False)])
def test_parent_claim_invalid_no_owner(field, value, tmp_path, monkeypatch):
    save = fixture(tmp_path, monkeypatch)
    intent = x.a.load(tmp_path / "browser-send-intent.json")
    intent[field] = value
    save("browser-send-intent.json", intent)
    with x.bindings(), pytest.raises(RuntimeError, match="intent_exact"):
        x.claim_send()
    assert not x.OWNER.exists()


def test_cleanup_starts_blocks_claim(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    (tmp_path / "offline-intent.json").write_text("{}")
    with x.bindings(), pytest.raises(RuntimeError, match="no_cleanup"):
        x.claim_send()


def test_claim_crash_consumed_no_retry(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    original = x.previous.exclusive
    def fail(path, value):
        if path.name == "browser-binding.json":
            raise OSError("fixture")
        original(path, value)
    monkeypatch.setattr(x.previous, "exclusive", fail)
    with x.bindings():
        with pytest.raises(OSError):
            x.claim_send()
        assert x.OWNER.exists()
        with pytest.raises(RuntimeError, match="NO_RETRY"):
            x.claim_send()


def test_actual_review_allfour_not_generic_approval(tmp_path, monkeypatch):
    save = fixture(tmp_path, monkeypatch)
    parent = x.a.load(tmp_path / "parent-review.json")
    parent["stages"] = ["online"]
    save("parent-review.json", parent)
    with x.bindings(), pytest.raises(RuntimeError, match="all_four_scopes"):
        x.previous.review("policy-put")


def test_cleanup_after_expiry_independent_and_no_repeat(tmp_path, monkeypatch):
    save = fixture(tmp_path, monkeypatch)
    with x.bindings():
        x.claim_send()
    expired = datetime.now(UTC) - timedelta(days=1)
    manifest = {"at_utc": (expired - timedelta(seconds=1)).isoformat(), "start": expired.isoformat(),
                "end": (expired + timedelta(minutes=30)).isoformat()}
    monkeypatch.setattr(x, "check_package", lambda: manifest)
    parent = x.a.load(tmp_path / "parent-review.json")
    parent["at_utc"] = expired.isoformat()
    save("parent-review.json", parent)
    save("cleanup-authorization.json", {"parent_says_cleanup": True,
        "manifest_sha256": x.p.sha(tmp_path / "manifest.json"),
        "review_sha256": x.p.sha(tmp_path / "parent-review.json"), "at_utc": datetime.now(UTC).isoformat()})
    with x.bindings():
        x.previous.review("offline")
        with pytest.raises(RuntimeError, match="fresh05_native_review"):
            x.previous.review("online")
        save("offline-intent.json", {})
        with pytest.raises(RuntimeError, match="existing_intent_NO_RETRY"):
            x.previous.review("offline")


def test_exports_actual05b_before_put_then06_after_no04_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    monkeypatch.setattr(x.base, "_exports", lambda formats, policy: policy)
    assert x.exports({}) == x.OLD / "diagnostic.xml"
    (tmp_path / "policy-put-intent.json").write_text("{}")
    assert x.exports({}) == tmp_path / "diagnostic.xml"
    with pytest.raises(RuntimeError, match="only05b_or06_policy"):
        x.exports({}, x.base.OLD / "diagnostic.xml")


@pytest.mark.parametrize("field,value", [("correction_of", "retry05b"), ("cleanup_complete", False)])
def test_parent_correction_attestations_required(field, value, tmp_path, monkeypatch):
    save = fixture(tmp_path, monkeypatch)
    intent = x.a.load(tmp_path / "browser-send-intent.json")
    intent[field] = value
    save("browser-send-intent.json", intent)
    with x.bindings(), pytest.raises(RuntimeError, match="correction_cleanup_required"):
        x.claim_send()
    assert not x.OWNER.exists()