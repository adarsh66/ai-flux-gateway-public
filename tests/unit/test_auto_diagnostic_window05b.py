"""05b offline tests: real immutable predecessor bytes; fake activation only."""
from datetime import UTC, datetime, timedelta
import inspect
import json

import pytest

from scripts.deployment import auto_diagnostic_window05b as x


def test_real05_exact_six_files_no_review_activation_reservation_Send():
    files = x.frozen05()
    assert len(files) == 6 and files["manifest.json"] == x.FROZEN05_SHA
    assert not x.OWNER.exists()


def test_real05_foreign_file_rejected(tmp_path, monkeypatch):
    original = x.FROZEN05
    for f in original.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    monkeypatch.setattr(x, "FROZEN05", tmp_path)
    (tmp_path / "browser-send-intent.json").write_text("{}")
    with pytest.raises(RuntimeError, match="six_files_only"):
        x.frozen05()


def test_real05_manifest_drift_rejected(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text("{}")
    monkeypatch.setattr(x, "FROZEN05", tmp_path)
    with pytest.raises(RuntimeError, match="frozen05_manifest_exact"):
        x.frozen05()


def test_frozen_sources_checked_individually_not_restamped(monkeypatch):
    sha = x.p.sha
    monkeypatch.setattr(x.p, "sha", lambda path: "bad" if path == x.base.BROWSER else sha(path))
    with pytest.raises(RuntimeError, match="all_original05_bound_sources_exact"):
        x.frozen05()


def test_history_includes05_but_excludes05b_and_all_original04_evidence():
    hashes = x.history()
    assert hashes[(x.FROZEN05 / "manifest.json").relative_to(x.p.rt.ROOT).as_posix()] == x.FROZEN05_SHA
    assert hashes[(x.base.PROOF / "result.json").relative_to(x.p.rt.ROOT).as_posix()] == x.base.PROOF_SHA
    assert not any(key.startswith(x.OUT.relative_to(x.p.rt.ROOT).as_posix() + "/") for key in hashes)


def test_scoped_adapter_restores_original_transports_and05_bindings():
    before = x.base.OUT, x.base.check_package, x.w.OUT, x.w.BROWSER, x.c.IP
    transport = x.w.execute, x.w.once, x.w.capture, x.base.prior.policy_put
    with pytest.raises(ValueError):
        with x.bindings():
            assert x.base.OUT == x.w.OUT == x.OUT
            assert x.w.BROWSER == x.BROWSER and x.c.IP == "167.103.66.248"
            assert x.base.check_package is x.check_package
            assert x.frozen05()["manifest.json"] == x.FROZEN05_SHA
            assert transport == (x.w.execute, x.w.once, x.w.capture, x.base.prior.policy_put)
            raise ValueError("fixture")
    assert before == (x.base.OUT, x.base.check_package, x.w.OUT, x.w.BROWSER, x.c.IP)


def test_exact_policy_delta_only_IP_30min_keeps_nonce_quota_security():
    before = (x.base.OLD / "diagnostic.xml").read_bytes()
    start, end = "2026-10-29T10:00:00+00:00", "2026-10-29T10:30:00+00:00"
    xml = x.base.candidate(start, end)
    root = x.c.tree(xml)
    assert x.c.signature(root.find("inbound")[2]) == x.c.signature(x.base.scope_guard(start, end))
    quota = x.c.post(root).find("limit-concurrency")[0]
    assert quota.get("calls") == "1" and quota.get("renewal-period") == "3600"
    assert x.base.d.expression_audit(xml)["expression_count"] == 103
    assert (x.base.OLD / "diagnostic.xml").read_bytes() == before


def test_prepare_and_claim_are_local_no_transport_or_network():
    for function in (x.prepare, x.claim_send, x.check_package, x.frozen05):
        text = inspect.getsource(function)
        for forbidden in (".capture(", ".execute(", ".once(", "transport(", "Reads(", "get-access-token", "urlopen("):
            assert forbidden not in text


def test_no_reprepare_or_consumed_owner_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    with pytest.raises(RuntimeError, match="NEVER_refresh"):
        x.prepare(tmp_path / "missing", tmp_path / "missing2")


def test_real_exclusive_fsynced_claim_cannot_overwrite(tmp_path):
    path = tmp_path / "owner.json"
    x.exclusive(path, {"real_disk": True})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        x.exclusive(path, {"real_disk": False})
    assert path.read_bytes() == before
    assert "os.fsync" in inspect.getsource(x.exclusive)


def setup_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(x, "OUT", tmp_path)
    monkeypatch.setattr(x, "OWNER", tmp_path / "shared-owner.json")
    now = datetime.now(UTC)
    start, end = (now - timedelta(minutes=1)).isoformat(), (now + timedelta(minutes=29)).isoformat()
    def save(name, value):
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    m = {"at_utc": start, "start": start, "end": end, "inline_sha256": "a" * 64}
    save("manifest.json", m)
    (tmp_path / "native.txt").write_text("TEST FIXTURE NOT ACTUAL APPROVAL")
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
        "reservation_sha256": x.p.sha(tmp_path / "reserve-browser-intent.json"),
        "review_sha256": x.p.sha(tmp_path / "parent-review.json"), "browser_source_sha256": x.p.sha(x.BROWSER),
        "inline_sha256": m["inline_sha256"], "attempt_budget": 1, "scoring_budget": 1,
        "retry_budget": 0, "completion_budget": 0, "new_scope_consumed": True,
        "parent_local_disk_review_verified": True, "at_utc": now.isoformat()})
    monkeypatch.setattr(x, "check_package", lambda: m)
    return save


def test_actual_parent_claim_before_binding_exclusive_across_scope(tmp_path, monkeypatch):
    setup_claim(tmp_path, monkeypatch)
    binding = x.claim_send()
    assert binding["shared_owner_sha256"] == x.p.sha(x.OWNER)
    assert binding["parent_intent_sha256"] == x.p.sha(tmp_path / "browser-send-intent.json")
    assert binding["parent_disk_verified"] is True
    assert x.a.load(tmp_path / "browser-binding.json") == binding
    owner = x.OWNER.read_bytes()
    with pytest.raises(RuntimeError, match="already_claimed_NO_RETRY"):
        x.claim_send()
    assert x.OWNER.read_bytes() == owner


def test_crash_after_owner_before_binding_permanently_consumes(tmp_path, monkeypatch):
    setup_claim(tmp_path, monkeypatch)
    original = x.exclusive
    def interrupted(path, value):
        if path.name == "browser-binding.json":
            raise OSError("fixture disk failure")
        original(path, value)
    monkeypatch.setattr(x, "exclusive", interrupted)
    with pytest.raises(OSError):
        x.claim_send()
    assert x.OWNER.exists() and not (tmp_path / "browser-binding.json").exists()
    with pytest.raises(RuntimeError, match="already_claimed_NO_RETRY"):
        x.claim_send()


@pytest.mark.parametrize("field,value", [("attempt_budget", 2), ("scope", "NEW_BUDGET"),
    ("parent_local_disk_review_verified", False), ("inline_sha256", "bad"),
    ("reservation_sha256", "bad"), ("review_sha256", "bad"), ("retry_budget", 1), ("completion_budget", 1)])
def test_actual_parent_intent_invalid_no_claim(field, value, tmp_path, monkeypatch):
    save = setup_claim(tmp_path, monkeypatch)
    intent = x.load("browser-send-intent.json")
    intent[field] = value
    save("browser-send-intent.json", intent)
    with pytest.raises(RuntimeError, match="actual_parent_apply_patch_intent_exact"):
        x.claim_send()
    assert not x.OWNER.exists()


@pytest.mark.parametrize("name", ["browser-send-intent.json", "reserve-browser-intent.json", "activate-result.json", "parent-review.json"])
def test_missing_actual_parent_prerequisite_never_claims(name, tmp_path, monkeypatch):
    setup_claim(tmp_path, monkeypatch)
    (tmp_path / name).unlink()
    with pytest.raises(FileNotFoundError):
        x.claim_send()
    assert not x.OWNER.exists()


def test_offline_cleanup_intent_forbids_Send_claim(tmp_path, monkeypatch):
    setup_claim(tmp_path, monkeypatch)
    (tmp_path / "offline-intent.json").write_text("{}")
    with pytest.raises(RuntimeError, match="actual_activation_reservation_no_cleanup"):
        x.claim_send()
    assert not x.OWNER.exists()


def test_inline_file_exact_function_no_dependencies():
    source = x.inline_source()
    assert source.startswith("async function diagnostic05bAttempt(page, binding) {")
    assert source.endswith("}") and "export " not in source
    for bad in ("node:", "readFileSync", "writeFileSync", "import(", ".click(", ".evaluate("):
        assert bad not in source


def test_05b_cleanup_expiry_independent_with_actual_shared_claim(tmp_path, monkeypatch):
    setup_claim(tmp_path, monkeypatch)
    x.claim_send()
    old = datetime.now(UTC) - timedelta(days=1)
    m = {"at_utc": (old - timedelta(seconds=1)).isoformat(), "start": old.isoformat(),
         "end": (old + timedelta(minutes=30)).isoformat()}
    # Expire the review without altering the manifest/claim identity fixture.
    parent = x.load("parent-review.json")
    parent["at_utc"] = old.isoformat()
    (tmp_path / "parent-review.json").write_text(json.dumps(parent))
    monkeypatch.setattr(x, "check_package", lambda: m)
    (tmp_path / "cleanup-authorization.json").write_text(json.dumps({"parent_says_cleanup": True,
        "manifest_sha256": x.p.sha(tmp_path / "manifest.json"),
        "review_sha256": x.p.sha(tmp_path / "parent-review.json"), "at_utc": datetime.now(UTC).isoformat()}))
    with x.bindings():
        x.review("offline")
        with pytest.raises(RuntimeError, match="fresh05_native_review"):
            x.review("online")
    (tmp_path / "offline-intent.json").write_text("{}")
    with x.bindings():
        with pytest.raises(RuntimeError, match="existing_intent_NO_RETRY"):
            x.review("offline")


def test_ownership_foreign_claim_blocks_but_own_claim_allows_cleanup(tmp_path, monkeypatch):
    setup_claim(tmp_path, monkeypatch)
    x.claim_send()
    x.ownership()
    owner = x.a.load(x.OWNER)
    owner["manifest_sha256"] = "foreign"
    x.OWNER.write_text(json.dumps(owner))
    with pytest.raises(RuntimeError, match="shared_budget_owned_by_this_exact05b_NO_RETRY"):
        x.ownership()