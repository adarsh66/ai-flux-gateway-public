"""Exact06 successor. Offline prepare/check only unless parent explicitly executes.

05b is permanently consumed (timer failure, no response, wire count UNKNOWN).
Never edit/replay historical executors or artifacts. Parent owns browser/claim.
"""
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from scripts.deployment import auto_diagnostic_window05b as previous

base = previous.base
p, a, w, c = previous.p, previous.a, previous.w, previous.c
require = previous.require
OLD = previous.OUT
OLD_OWNER = previous.OWNER
OUT = a.HOME / "scoring-diagnostic06"
OWNER = a.HOME / "diagnostic06-single-user-attempt-owner.json"
SCOPE = "DIAGNOSTIC06_CORRECTION_ONE_USER_ATTEMPT"
CORRECTION = "DIAGNOSTIC05B_TIMER_GLOBAL_FAILURE"
BROWSER = Path(__file__).with_name("auto_diagnostic_browser06.mjs")
DOC = p.rt.ROOT / "docs/auto-diagnostic06-review-20261029.md"
TEST = p.rt.ROOT / "tests/unit/test_auto_diagnostic_window06.py"
NODE_TEST = p.rt.ROOT / "tests/auto_diagnostic_browser06.test.mjs"
OLD_SHA = "486cfe89b51a6747783821cc81745fc09e2ac02a8824d6f2c1014ab1743bfab7"
RECEIPTS = {
    "offline-verification.json": "de26ab41b30999b5c63a805a8b57435d48085ebbd02de01dace89d95d19f3e5e",
    "offline-after-capture.json": "aca2519e5d38608a661fece44fd14fcc56506e9c61d534cd84c605322d94d6ac",
    "browser-send-result.json": "048571d21400d71ef7e195d3cfb9557ab0879fa2bb4abfcfe3ac3c3f43f42c4e",
}
ORIGINAL_SOURCE = previous.sources
ORIGINAL_CHECK = previous.check_package
ORIGINAL_CLAIM = previous.claim_send
PREFLIGHT = p.rt.ROOT / ".deployment/auto-diagnostic-browser06-offline-receipt.json"


def browser_preflight():
    receipt = a.load(PREFLIGHT)
    proof = receipt["browser_tool_preflight"]
    require(p.sha(BROWSER) == receipt["helper_file_sha256"]
            and p.sha(NODE_TEST) == receipt["tests_sha256"]
            and p.sha(p.rt.ROOT / receipt["junit"]) == receipt["junit_sha256"]
            and receipt["tests_passed"] == 50 and receipt["tests_failed"] == receipt["tests_skipped"] == 0
            and proof["status"] == "PASS_ABORT_ONLY_MOCK_NO_REAL_NETWORK"
            and proof["page_url"] == "about:blank" and proof["helper_function_lf_length"] == 8192
            and proof["helper_function_lf_fnv1a32"] == "5ac396b8"
            and all(value == "undefined" for value in proof["globals"].values())
            and proof["forwarded"] is proof["scorer_schema_proven"] is False
            and proof["guard_retained_closed"] is True,
            "actual_parent_browser_mock_preflight_exact_source_required")
    return p.sha(PREFLIGHT)


def predecessor():
    require(p.sha(OLD / "manifest.json") == OLD_SHA, "actual05b_manifest_exact")
    old = a.load(OLD / "manifest.json")
    for section in ("sources", "history"):
        require(all(p.sha(p.rt.ROOT / name) == digest for name, digest in old[section].items()),
                "all05b_original_sources_and_history_exact")
    for name, digest in RECEIPTS.items():
        require(p.sha(OLD / name) == digest, "actual05b_cleanup_receipts_exact")
    after, verified, attempt = [a.load(OLD / name) for name in
        ("offline-after-capture.json", "offline-verification.json", "browser-send-result.json")]
    intent, result = [a.load(OLD / ("offline-" + name + ".json")) for name in ("intent", "result")]
    require(verified["at_utc"] == "2026-10-29T10:04:48.073312+00:00"
            and verified["manifest_sha256"] == intent["manifest_sha256"] == OLD_SHA
            and verified["intent_sha256"] == p.sha(OLD / "offline-intent.json")
            and result["http_status"] == verified["http_status"] == 200 and result["no_retry"] is True
            and intent["method"] == "PATCH" and intent["url"] == a.URL
            and intent["body_sha256"] == c.sha_bytes(w.BODIES["offline"])
            and intent["attempt_budget"] == 1 and intent["retries"] == intent["redirects"] == 0,
            "actual05b_consumed_offline_wire")
    require(after["state_owner"] == old["state_owner"] == a.original_bindings()
            and after["state_owner"]["serial"] == 185
            and after["revision2_online"] is after["revision2_current"] is False
            and verified["revision2_online"] is verified["revision2_current"] is False
            and all(after[k] is True for k in ("all13_supplemental_exact", "exact_both_formats", "inherited_exact"))
            and verified["all13_supplemental_exact"] is verified["exact_both_formats"] is True
            and after["revisions"] == a.load(base.PROOF / "fresh-capture.json")["revisions"]
            and after["baseline_sha256"] == p.release.fs.sha(a.load(a.HOME / "protected-before.json"))
            and after["supplemental_sha256"] == p.release.fs.sha(a.load(a.HOME / "supplemental-before.json"))
            and after["current_api_sha256"] == a.load(base.PROOF / "fresh-capture.json")["current_api_sha256"]
            and after["policy_format_hashes"] == a.load(OLD / "policy-put-after-capture.json")["policy_format_hashes"],
            "actual05b_offline_all13_current1_state185_inheritance_bothformats")
    require(attempt["status"] == "BROWSER_SANDBOX_TIMER_GLOBAL_UNAVAILABLE_NO_RETRY"
            and attempt["new_scope_consumed"] is True and attempt["retry_authorized"] is False
            and attempt["keyboard_invocations"] == 1 and attempt["scoring_request_count"] is None
            and attempt["scorer_schema_proven"] is False, "05b_consumed_timerfailure_noresponse_UNKNOWN")
    owner = a.load(OLD_OWNER)
    require(p.sha(OLD_OWNER) == attempt["shared_owner_sha256"]
            and p.sha(OLD / "browser-send-intent.json") == attempt["parent_intent_sha256"]
            and owner["manifest_sha256"] == attempt["manifest_sha256"] == OLD_SHA
            and owner["parent_intent_sha256"] == attempt["parent_intent_sha256"]
            and owner["scope"] == "DIAGNOSTIC05_05B_ONE_USER_ATTEMPT",
            "actual05b_consumed_owner_and_send_intent_preserved")
    for name, digest in {"diagnostic.xml": old["xml_sha256"], "policy-put.json": old["put_sha256"],
                         "browser-inline-function.js": old["inline_sha256"], "prepare-capture.json": old["capture_sha256"],
                         **{s + "-patch.json": h for s, h in old["patches"].items()}}.items():
        require(p.sha(OLD / name) == digest, "actual05b_prepared_artifacts_exact")
    base.predecessor()
    return old


def sources():
    return {**ORIGINAL_SOURCE(), **{f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
        for f in (Path(__file__), BROWSER, DOC, TEST, NODE_TEST, PREFLIGHT)}}


def history():
    folders = [f for f in a.HOME.glob("scoring-*") if f.is_dir() and f != OUT]
    return {OLD_OWNER.relative_to(p.rt.ROOT).as_posix(): p.sha(OLD_OWNER), **{f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
        for folder in sorted([*folders, base.PROOF]) for f in sorted(folder.rglob("*"))
        if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"}}


def inline_source():
    text = BROWSER.read_text(encoding="utf-8")
    return text[text.index("export async function ") + len("export "):text.index("\n\nexport const SOURCE")]


def exports(formats, policy=None):
    expected = OUT / "diagnostic.xml" if (OUT / "policy-put-intent.json").exists() else OLD / "diagnostic.xml"
    require(policy is None or policy in (OLD / "diagnostic.xml", OUT / "diagnostic.xml"), "only05b_or06_policy")
    return base._exports(formats, policy or expected)


def check_package():
    predecessor()
    preflight = browser_preflight()
    m = ORIGINAL_CHECK()
    require(m["predecessor05b"] == RECEIPTS and m["predecessor_manifest_sha256"] == OLD_SHA
            and m["attempt_budget"] == 1 and m["cleanup_expiry_independent"] is True
            and m["predecessor05b_consumed"] is True and m["correction_of"] == CORRECTION
            and m["browser_preflight_sha256"] == preflight, "exact06_predecessor_and_budget")
    return m


def claim_send():
    # Original real-disk exclusive ownership and full review/activation gate.
    intent = a.load(OUT / "browser-send-intent.json")
    require(intent.get("correction_of") == CORRECTION and intent.get("cleanup_complete") is True,
            "06_parent_intent_correction_cleanup_required")
    original = previous.exclusive
    def exclusive(path, value):
        if path == OUT / "browser-binding.json":
            value = {**value, "correction_of": CORRECTION, "cleanup_complete": True,
                     "parent_claim_durable": True}
        original(path, value)
    previous.exclusive = exclusive
    try:
        ORIGINAL_CLAIM()
        return a.load(OUT / "browser-binding.json")
    finally:
        previous.exclusive = original


@contextmanager
def bindings():
    edits = [(previous, key, value) for key, value in {
        "OUT": OUT, "OWNER": OWNER, "SCOPE": SCOPE, "BROWSER": BROWSER,
        "sources": sources, "history": history, "inline_source": inline_source,
        "check_package": check_package}.items()]
    saved = [(obj, key, getattr(obj, key)) for obj, key, _ in edits]
    try:
        for obj, key, value in edits:
            setattr(obj, key, value)
        with previous.bindings():
            # Before06 PUT the installed policy is actual05b, not historical04.
            old_exports, old_diag = base.exports, base.prior.prior.DIAG
            base.exports, base.prior.prior.DIAG = exports, OLD
            try:
                w.exports = base.prior.exports = exports
                yield
            finally:
                base.exports, base.prior.prior.DIAG = old_exports, old_diag
    finally:
        for obj, key, value in reversed(saved):
            setattr(obj, key, value)


def prepare(receipt, browser_receipt):
    require(not OUT.exists() and not OWNER.exists(), "existing06_package_or_claim_NEVER_refresh")
    old = predecessor()
    preflight = browser_preflight()
    frozen05 = previous.frozen05()
    receipts = [f.resolve() for f in (receipt, browser_receipt)]
    require(all(f.is_relative_to(p.rt.ROOT) for f in receipts), "workspace_test_receipts_required")
    tests = [{"path": f.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(f), "kind": kind,
              "counts": base.test_counts(f, kind)} for f, kind in zip(receipts, ("python", "node"), strict=True)]
    src, retained, markers = sources(), history(), p.backend.markers()
    p.require_no_competing_workers(p.backend.workers())
    # Freeze only after all implementation/tests/predecessor checks are complete.
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(minutes=30)
    xml = base.candidate(start.isoformat(), end.isoformat()).encode()
    body = json.dumps({"properties": {"format": "xml", "value": xml.decode()}}, separators=(",", ":")).encode()
    require(sources() == src and history() == retained, "stable06_offline_preparation")
    p.release.fs.protect(OUT)
    for name, value in {"diagnostic.xml": xml, "policy-put.json": body,
        "browser-inline-function.js": inline_source().encode(),
        **{s + "-patch.json": b for s, b in w.BODIES.items()}}.items():
        with (OUT / name).open("xb") as stream:
            stream.write(value)
    p.backend.save(OUT, "prepare-capture.json", {"mode": "RETAINED_ACTUAL05B_OFFLINE_NOT_FRESH_LIVE_READ",
        "receipt": a.load(OLD / "offline-after-capture.json"), "verification_sha256": RECEIPTS["offline-verification.json"],
        "parent_reported_guard_removal": "2026-10-29T10:08:49Z page.unrouteAll AFTER verified offline; not independently observed here",
        "fresh_before_every_mutation": "MANDATORY_full13_state185_current1_ETag_policy_inheritance"})
    p.backend.save(OUT, "manifest.json", {"at_utc": p.now(), "status": "READY_FOR_PARENT_INDEPENDENT_NATIVE_REVIEW",
        "sources": src, "source_sha256": p.release.fs.sha(src), "history": retained, "markers": markers,
        "frozen05": frozen05, "state_owner": a.original_bindings(), "start": start.isoformat(), "end": end.isoformat(),
        "nonce": old["nonce"], "xml_sha256": p.sha(OUT / "diagnostic.xml"), "put_sha256": p.sha(OUT / "policy-put.json"),
        "inline_sha256": p.sha(OUT / "browser-inline-function.js"), "capture_sha256": p.sha(OUT / "prepare-capture.json"),
        "tests": tests, "stages": base.STAGES, "url": a.URL, "policy_url": c.POLICY_URL,
        "patches": {s: c.sha_bytes(b) for s, b in w.BODIES.items()}, "fixed_text": c.TEXT,
        "subscription": c.SUBSCRIBER, "IP": base.IP, "chat_path": c.CHAT_PATH,
        "budget_scope": SCOPE, "attempt_budget": 1, "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0,
        "historical_scoring_request_count": None, "historical_total_at_most_one_proven": False,
        "predecessor05b_consumed": True, "predecessor05b": RECEIPTS, "predecessor_manifest_sha256": OLD_SHA,
        "correction_of": CORRECTION, "browser_preflight_sha256": preflight,
        "controller_scoring_requests": 0, "fresh_live_prepare": False, "cleanup_expiry_independent": True,
        "cleanup_requires_parent_signal": True, "automatic_cleanup": False, "activation_returns": "ONLINE_READY",
        "nonce_and_counter_unchanged": True})
    check_package()
    print(json.dumps({"status": "REVIEW_READY_NO_ACTIVATION", "manifest_sha256": p.sha(OUT / "manifest.json"),
        "package": OUT.relative_to(p.rt.ROOT).as_posix(), "start": start.isoformat(), "end": end.isoformat(),
        "inline_path": (OUT / "browser-inline-function.js").relative_to(p.rt.ROOT).as_posix(), "cloud_calls": 0}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare-review", "check", "claim-send", "activate", "offline"))
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--browser-tests", type=Path)
    args = parser.parse_args()
    with bindings():
        if args.stage == "prepare-review":
            require(args.tests is not None and args.browser_tests is not None, "actual_receipts_required")
            prepare(args.tests, args.browser_tests)
        elif args.stage == "check":
            check_package()
            print(json.dumps({"status": "LOCAL_EXACT_NO_LIVE_STATE_CLAIM", "manifest_sha256": p.sha(OUT / "manifest.json")}))
        elif args.stage == "claim-send":
            print(json.dumps(claim_send()), flush=True)
        elif args.stage == "activate":
            require(not OWNER.exists(), "attempt_consumed_NO_RETRY")
            base.prior.activate()
        else:
            w.execute("offline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())