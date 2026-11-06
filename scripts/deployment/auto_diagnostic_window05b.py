"""Separate offline05b package. NEVER rewrite05; parent disk owns browser Send.

Preparation/check/claim-send are disk-only. Activation and cleanup are explicit
parent-only retained executors, never invoked by preparation or tests.
"""
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path

from scripts.deployment import auto_diagnostic_window05 as base

p, a, w, c = base.p, base.a, base.w, base.c
require = base.require
FROZEN05 = base.OUT
FROZEN05_SHA = "e7ee636aa01a625bdd249bbe507a742b051724c8f39e21908df7d1a26505e042"
OUT = a.HOME / "scoring-diagnostic05b"
OWNER = a.HOME / "diagnostic05-05b-single-user-attempt-owner.json"
SCOPE = "DIAGNOSTIC05_05B_ONE_USER_ATTEMPT"
BROWSER = Path(__file__).with_name("auto_diagnostic_browser05b.mjs")
DOC = p.rt.ROOT / "docs/auto-diagnostic05b-review-20261029.md"
NODE_TEST = p.rt.ROOT / "tests/auto_diagnostic_browser05b.test.mjs"
TEST = p.rt.ROOT / "tests/unit/test_auto_diagnostic_window05b.py"
ORIGINAL_SOURCES, ORIGINAL_REVIEW = base.sources, base.review


def frozen05():
    """Exactly the six original files, no activation/reservation/Send evidence."""
    require(p.sha(FROZEN05 / "manifest.json") == FROZEN05_SHA, "frozen05_manifest_exact")
    m = a.load(FROZEN05 / "manifest.json")
    names = {"manifest.json", "diagnostic.xml", "policy-put.json", "prepare-capture.json",
             "online-patch.json", "offline-patch.json"}
    require({f.name for f in FROZEN05.iterdir()} == names, "05_unreviewed_unactivated_unattempted_six_files_only")
    for name, digest in m["sources"].items():
        require(p.sha(p.rt.ROOT / name) == digest, "all_original05_bound_sources_exact")
    for name, digest in m["history"].items():
        require(p.sha(p.rt.ROOT / name) == digest, "all_original05_history_exact")
    expected = {"diagnostic.xml": m["xml_sha256"], "policy-put.json": m["put_sha256"],
                "prepare-capture.json": m["capture_sha256"],
                **{s + "-patch.json": digest for s, digest in m["patches"].items()}}
    require(all(p.sha(FROZEN05 / name) == digest for name, digest in expected.items()), "original05_artifacts_exact")
    return {f.name: p.sha(f) for f in sorted(FROZEN05.iterdir())}


def sources():
    return {**ORIGINAL_SOURCES(), **{f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
                                   for f in (Path(__file__), BROWSER, DOC, TEST, NODE_TEST)}}


def history():
    # Original05 remains part of history,05b output excluded. No old file writes.
    folders = [f for f in a.HOME.glob("scoring-*") if f.is_dir() and f != OUT]
    return {f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
            for folder in sorted([*folders, base.PROOF]) for f in sorted(folder.rglob("*"))
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"}


def inline_source():
    text = BROWSER.read_text(encoding="utf-8")
    return text[text.index("export async function ") + len("export "):text.index("\n\nexport const SOURCE")]


def load(name):
    return a.load(OUT / name)


def exclusive(path, value):
    # Atomic O_EXCL and fsync on REAL parent disk, never simulated in browser.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def ownership():
    if OWNER.exists():
        owner = a.load(OWNER)
        require(owner["scope"] == SCOPE and owner["manifest_sha256"] == p.sha(OUT / "manifest.json")
                and owner["parent_intent_sha256"] == p.sha(OUT / "browser-send-intent.json")
            and owner["attempt_budget"] == owner["scoring_budget"] == 1
            and owner["retry_budget"] == owner["completion_budget"] == 0,
                "shared_budget_owned_by_this_exact05b_NO_RETRY")


def prepare(receipt, browser_receipt):
    require(not OUT.exists() and not OWNER.exists(), "existing_package_or_consumed_shared_budget_NEVER_refresh")
    frozen = frozen05()
    receipts = [f.resolve() for f in (receipt, browser_receipt)]
    require(all(f.is_relative_to(p.rt.ROOT) for f in receipts), "workspace_test_receipts_required")
    tests = [{"path": f.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(f), "kind": kind,
              "counts": base.test_counts(f, kind)} for f, kind in zip(receipts, ("python", "node"), strict=True)]
    old = base.predecessor()
    src, retained, markers = sources(), history(), p.backend.markers()
    p.require_no_competing_workers(p.backend.workers())
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(minutes=30)
    xml = base.candidate(start.isoformat(), end.isoformat()).encode()
    body = json.dumps({"properties": {"format": "xml", "value": xml.decode()}}, separators=(",", ":")).encode()
    require(sources() == src and history() == retained and frozen05() == frozen, "stable_offline_preparation")
    p.release.fs.protect(OUT)
    files = {"diagnostic.xml": xml, "policy-put.json": body,
             "browser-inline-function.js": inline_source().encode(),
             **{stage + "-patch.json": value for stage, value in w.BODIES.items()}}
    for name, value in files.items():
        with (OUT / name).open("xb") as stream:
            stream.write(value)
    p.backend.save(OUT, "prepare-capture.json", {"mode": "RETAINED_ACTUAL04_FULL13_NOT_FRESH_LIVE_READ",
        "receipt": a.load(base.PROOF / "fresh-capture.json"), "fresh_before_every_mutation": "MANDATORY_full13_state185_ETag_policy_inheritance"})
    p.backend.save(OUT, "manifest.json", {"at_utc": p.now(), "status": "READY_FOR_PARENT_INDEPENDENT_NATIVE_REVIEW",
        "sources": src, "source_sha256": p.release.fs.sha(src), "history": retained, "markers": markers,
        "frozen05": frozen, "frozen05_unactivated_unattempted": True,
        "state_owner": a.original_bindings(), "start": start.isoformat(), "end": end.isoformat(), "nonce": old["nonce"],
        "xml_sha256": p.sha(OUT / "diagnostic.xml"), "put_sha256": p.sha(OUT / "policy-put.json"),
        "inline_sha256": p.sha(OUT / "browser-inline-function.js"),
        "capture_sha256": p.sha(OUT / "prepare-capture.json"), "tests": tests, "stages": base.STAGES,
        "url": a.URL, "policy_url": c.POLICY_URL, "patches": {s: c.sha_bytes(b) for s, b in w.BODIES.items()},
        "fixed_text": c.TEXT, "subscription": c.SUBSCRIBER, "IP": base.IP, "chat_path": c.CHAT_PATH,
        "budget_scope": SCOPE, "historical_scoring_request_count": None, "historical_total_at_most_one_proven": False,
        "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0, "controller_scoring_requests": 0,
        "fresh_live_prepare": False, "cleanup_expiry_independent": True, "cleanup_requires_parent_signal": True,
        "automatic_cleanup": False, "activation_returns": "ONLINE_READY", "nonce_and_counter_unchanged": True,
        "predecessor_full_readonly_sha256": base.PROOF_SHA, "predecessor_manifest_sha256": base.MANIFEST04})
    check_package()
    print(json.dumps({"status": "REVIEW_READY_NO_ACTIVATION", "manifest_sha256": p.sha(OUT / "manifest.json"),
        "package": OUT.relative_to(p.rt.ROOT).as_posix(), "start": start.isoformat(), "end": end.isoformat(),
        "cloud_calls": 0, "shared_budget_claimed": False}), flush=True)


def check_package():
    m = load("manifest.json")
    require(m["sources"] == sources() and m["source_sha256"] == p.release.fs.sha(m["sources"])
            and m["history"] == history() and m["frozen05"] == frozen05(), "immutable05b_sources_history_frozen05")
    require(m["state_owner"] == a.original_bindings() and m["state_owner"]["serial"] == 185, "original_state185_exact")
    require(m["IP"] == base.IP and m["stages"] == base.STAGES and m["budget_scope"] == SCOPE
            and m["scoring_budget"] == 1 and m["completion_budget"] == m["retry_budget"] == 0
            and m["fixed_text"] == c.TEXT and m["subscription"] == c.SUBSCRIBER and m["chat_path"] == c.CHAT_PATH
            and m["nonce"] == base.predecessor()["nonce"]
            and m["historical_scoring_request_count"] is None and m["historical_total_at_most_one_proven"] is False,
            "one_shared05_05b_attempt_not_new_budget")
    require([r["kind"] for r in m["tests"]] == ["python", "node"], "both_test_receipts_required")
    for receipt in m["tests"]:
        path = (p.rt.ROOT / receipt["path"]).resolve()
        require(path.is_relative_to(p.rt.ROOT) and p.sha(path) == receipt["sha256"]
                and base.test_counts(path, receipt["kind"]) == receipt["counts"], "actual05b_tests_exact")
    xml = base.candidate(m["start"], m["end"]).encode()
    body = json.dumps({"properties": {"format": "xml", "value": xml.decode()}}, separators=(",", ":")).encode()
    require((OUT / "diagnostic.xml").read_bytes() == xml and c.sha_bytes(xml) == m["xml_sha256"]
            and (OUT / "policy-put.json").read_bytes() == body and c.sha_bytes(body) == m["put_sha256"], "exact05b_literal_policy")
    require((OUT / "browser-inline-function.js").read_text(encoding="utf-8") == inline_source()
            and p.sha(OUT / "browser-inline-function.js") == m["inline_sha256"]
            and p.sha(OUT / "prepare-capture.json") == m["capture_sha256"], "inline_and_capture_exact")
    for stage, value in w.BODIES.items():
        require((OUT / (stage + "-patch.json")).read_bytes() == value and m["patches"][stage] == c.sha_bytes(value), "literal_PATCH_exact")
    markers = p.backend.markers()
    allowed = OUT.relative_to(p.rt.ROOT).as_posix() + "/"
    owner_path = OWNER.relative_to(p.rt.ROOT).as_posix()
    require(all(markers.get(k) == v for k, v in m["markers"].items())
            and all(k.startswith(allowed) or k == owner_path for k in markers.keys() - m["markers"].keys()), "no_foreign_intents")
    ownership()
    p.require_no_competing_workers(p.backend.workers())
    return m


def review(stage):
    frozen05()
    ownership()
    return ORIGINAL_REVIEW(stage)


@contextmanager
def bindings():
    changes = [(base, "OUT", OUT), (base, "BROWSER", BROWSER), (base, "check_package", check_package),
               (base, "review", review)]
    previous = [(obj, key, getattr(obj, key)) for obj, key, _ in changes]
    try:
        for obj, key, value in changes:
            setattr(obj, key, value)
        with base.bindings():
            yield
    finally:
        for obj, key, value in reversed(previous):
            setattr(obj, key, value)


def claim_send():
    """Parent ONLY after real review/activation + apply_patch intent, before tool.

    Atomic shared claim is the durable exclusivity guarantee, NOT apply_patch
    semantics and NOT a pretend browser filesystem. Any failure consumes claim.
    """
    require(not OWNER.exists() and not (OUT / "browser-binding.json").exists()
            and not (OUT / "browser-send-result.json").exists(), "shared_attempt_already_claimed_NO_RETRY")
    m = check_package()
    r, activation, parent = load("reserve-browser-intent.json"), load("activate-result.json"), load("parent-review.json")
    sha, intent = p.sha(OUT / "manifest.json"), load("browser-send-intent.json")
    # Reuse actual review gate without the reserve stage's already-consumed check.
    require(parent.get("approved") is True and parent.get("independent_native_review") is True
            and parent.get("manifest_sha256") == sha and parent.get("stages") == base.STAGES, "real_parent_review_required")
    transcript = (OUT / parent["transcript"]).resolve()
    require(transcript.is_relative_to(OUT.resolve()) and p.sha(transcript) == parent["transcript_sha256"], "native_review_transcript_exact")
    now = datetime.now(UTC)
    require(datetime.fromisoformat(m["at_utc"]) <= datetime.fromisoformat(parent["at_utc"]) <= now
            and now - datetime.fromisoformat(parent["at_utc"]) < timedelta(minutes=30)
            and datetime.fromisoformat(m["start"]) <= now < datetime.fromisoformat(m["end"]) - timedelta(seconds=90), "fresh_parent_review_and_window")
    require(activation["status"] == "ONLINE_READY" and activation["manifest_sha256"] == sha
            and activation["reservation_sha256"] == p.sha(OUT / "reserve-browser-intent.json")
            and r["manifest_sha256"] == sha and r["review_sha256"] == p.sha(OUT / "parent-review.json")
            and r["browser_source_sha256"] == p.sha(BROWSER) and r["IP"] == base.IP
            and r["fixed_text"] == c.TEXT and r["model"] == "gpt-5.4-mini" and r["path"] == c.CHAT_PATH
            and r["end"] == m["end"] and r["attempt_budget"] == r["scoring_budget"] == 1
            and r["completion_budget"] == r["retry_budget"] == 0
            and not (OUT / "offline-intent.json").exists(), "actual_activation_reservation_no_cleanup")
    expected = {"scope": SCOPE, "manifest_sha256": sha, "reservation_sha256": p.sha(OUT / "reserve-browser-intent.json"),
        "review_sha256": p.sha(OUT / "parent-review.json"), "browser_source_sha256": p.sha(BROWSER),
        "inline_sha256": m["inline_sha256"], "attempt_budget": 1, "scoring_budget": 1, "retry_budget": 0,
        "completion_budget": 0, "new_scope_consumed": True, "parent_local_disk_review_verified": True}
    require(all(intent.get(k) == v for k, v in expected.items())
            and datetime.fromisoformat(parent["at_utc"]) <= datetime.fromisoformat(intent["at_utc"]) <= now,
            "actual_parent_apply_patch_intent_exact")
    exclusive(OWNER, {**expected, "parent_intent_sha256": p.sha(OUT / "browser-send-intent.json"), "at_utc": p.now()})
    binding = {"scope": SCOPE, "parent_disk_verified": True, "verified_at_utc": p.now(), "manifest_sha256": sha,
        "parent_intent_sha256": p.sha(OUT / "browser-send-intent.json"), "shared_owner_sha256": p.sha(OWNER),
        "reservation_sha256": p.sha(OUT / "reserve-browser-intent.json"), "browser_source_sha256": p.sha(BROWSER),
        "end": m["end"], "reservation": r}
    exclusive(OUT / "browser-binding.json", binding)
    return binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare-review", "check", "claim-send", "activate", "offline"))
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--browser-tests", type=Path)
    args = parser.parse_args()
    try:
        with bindings():
            if args.stage == "prepare-review":
                require(args.tests is not None and args.browser_tests is not None, "actual_receipts_required")
                prepare(args.tests, args.browser_tests)
            elif args.stage == "check":
                check_package()
                print(json.dumps({"status": "LOCAL_PACKAGE_EXACT_NOT_LIVE_STATE_PROOF", "manifest_sha256": p.sha(OUT / "manifest.json")}))
            elif args.stage == "claim-send":
                print(json.dumps(claim_send()), flush=True)
            elif args.stage == "activate":
                require(not OWNER.exists(), "shared_attempt_consumed_no_activation")
                base.prior.activate()
            else:
                w.execute("offline")
        return 0
    except Exception as exc:
        print(json.dumps({"stage": args.stage, "type": type(exc).__name__, "details_suppressed": True,
                          "retry_authorized": False, "automatic_cleanup": False}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())