"""One fixed diagnostic04 package. Offline prepare; parent-reviewed activate ONCE.

activate = offline policy PUT -> online PATCH -> browser reservation -> RETURN.
It never sends, retries, or calls cleanup. Only a separate parent-authorized
offline command cleans up, including after server-side expiry. No TF writes.
The retained controller supplies the unchanged full13/state/inheritance capture,
exclusive wire intents, literal PATCHes, TLS/no-redirect transport and time gate.
"""
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path

from scripts.deployment import auto_diagnostic_window03 as prior
from scripts.deployment import auto_diagnostic_time03 as put_transport

w, c, d, p, a = prior.w, prior.c, prior.d, prior.p, prior.a
require = w.require
OUT = a.HOME / "scoring-diagnostic04"
WINDOW03 = prior.OUT
STAGES = ["policy-put", "online", "reserve-browser", "offline"]
WINDOW03_MANIFEST = "c97856e68a952b9a7b090654a97918ec2228c910bc78438df71a5224a6534f41"
DOC = p.rt.ROOT / "docs/auto-diagnostic04-review-20261029.md"
_exports = w.exports


def load(name):
    return a.load(OUT / name)


def save(name, value):
    p.backend.save(OUT, name, value)


def historical_folders():
    return sorted(folder for folder in a.HOME.glob("scoring-*")
                  if folder.is_dir() and folder != OUT)


def history():
    # Actual current receipts/intents, NOT the stale history inside manifest03.
    return {f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
            for folder in historical_folders() for f in sorted(folder.rglob("*"))
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"}


def sources():
    return {**w.sources(), DOC.relative_to(p.rt.ROOT).as_posix(): p.sha(DOC)}


def predecessor():
    """Prove actual03 PUT and consumed online/offline, with no browser Send."""
    old = prior.check_compilation()
    require(p.sha(WINDOW03 / "manifest.json") == WINDOW03_MANIFEST,
            "actual_window03_manifest_exact")
    report = a.load(WINDOW03 / "executor-sequence-report.json")
    require(report["status"] == "OFFLINE_VERIFIED_BROWSER_NOT_ATTEMPTED_EXECUTION_DEVIATION"
            and report["manifest_sha256"] == WINDOW03_MANIFEST
            and report["adapter_sha256"] == p.sha(Path(prior.__file__))
            and report["browser_send_count"] == report["executor_scoring_requests"]
            == report["executor_completion_requests"] == 0
            and report["reserve_browser_executed"] is False
            and report["online_controller_invocations"] == 2
            and report["online_wire_attempts"] == report["offline_wire_attempts"] == 1,
            "actual03_consumed_stages_zero_Send")
    for folder in historical_folders():
        require(not (folder / "reserve-browser-intent.json").exists()
                and not (folder / "browser-send-intent.json").exists(),
                "historical_browser_budget_not_consumed")
    for stage, online in (("online", True), ("offline", False)):
        intent = a.load(WINDOW03 / (stage + "-intent.json"))
        result = a.load(WINDOW03 / (stage + "-result.json"))
        verified = a.load(WINDOW03 / (stage + "-verification.json"))
        capture = a.load(WINDOW03 / (stage + "-after-capture.json"))
        require(intent["method"] == "PATCH" and intent["url"] == a.URL
                and intent["stage"] == stage and intent["attempt_budget"] == 1
                and intent["retries"] == intent["redirects"] == 0
                and intent["manifest_sha256"] == verified["manifest_sha256"] == WINDOW03_MANIFEST
                and intent["review_sha256"] == p.sha(WINDOW03 / "parent-review.json")
                and intent["body_sha256"] == c.sha_bytes(w.BODIES[stage])
                and verified["intent_sha256"] == p.sha(WINDOW03 / (stage + "-intent.json"))
                and result["http_status"] == verified["http_status"] == 200
                and result["no_retry"] is True
                and capture["revision2_online"] is verified["revision2_online"] is online
                and capture["revision2_current"] is verified["revision2_current"] is False
                and all(capture[k] is True for k in
                        ("all13_supplemental_exact", "exact_both_formats", "inherited_exact"))
                and capture["state_owner"] == a.original_bindings()
                and capture["state_owner"]["serial"] == 185,
                "actual03_wire_and_full_readback_binding")
        require(datetime.fromisoformat(intent["at_utc"]) < datetime.fromisoformat(result["at_utc"])
                <= datetime.fromisoformat(capture["at_utc"]) <= datetime.fromisoformat(verified["at_utc"]),
                "actual03_intent_result_readback_order")
    after = a.load(WINDOW03 / "offline-after-capture.json")
    original_put = a.load(prior.DIAG / "policy-put-after-capture.json")
    require(after["policy_format_hashes"] == original_put["policy_format_hashes"],
            "actual03_successor_policy_predecessor_readback")
    require(datetime.fromisoformat(a.load(WINDOW03 / "online-verification.json")["at_utc"])
            < datetime.fromisoformat(a.load(WINDOW03 / "offline-intent.json")["at_utc"]),
            "actual03_online_then_cleanup_not_replayed")
    return old


def time_only(start, end):
    old = predecessor()
    root = c.tree((prior.DIAG / "diagnostic.xml").read_bytes())
    inbound = root.find("inbound")
    require(c.signature(inbound[2]) == c.signature(d.scope_guard(old["start"], old["end"])),
            "actual03_scope_predecessor")
    inbound.remove(inbound[2])
    inbound.insert(2, d.scope_guard(start, end))
    xml = c.ET.tostring(root, encoding="unicode", short_empty_elements=True)
    with d.bindings():
        c.guard(a.load(w.DIAG / "prepare-capture.json")["normalized_original"],
                xml, old["nonce"], start, end)
    inbound.remove(inbound[2])
    inbound.insert(2, d.scope_guard(old["start"], old["end"]))
    require(c.signature(root) == c.signature(c.tree((prior.DIAG / "diagnostic.xml").read_bytes())),
            "only_time_changed_fixed_nonce_counter1_score0completions")
    return xml


def exports(formats, policy=None):
    # Before PUT the actual03 successor is expected, not diagnostic02.
    expected = (OUT / "diagnostic.xml" if (OUT / "policy-put-intent.json").exists()
                else prior.DIAG / "diagnostic.xml")
    require(policy is None or policy in (prior.DIAG / "diagnostic.xml", OUT / "diagnostic.xml"),
            "only_actual03_or_fixed04_policy")
    return _exports(formats, policy or expected)


@contextmanager
def bindings():
    # No clone or replacement of capture/execute/once/transport/revision guards.
    changes = {"OUT": OUT, "exports": exports, "check_package": check_package, "review": review}
    previous = {key: getattr(w, key) for key in changes}
    try:
        for key, value in changes.items():
            setattr(w, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(w, key, value)


def prepare(receipt):
    require(not OUT.exists(), "existing04_package_NEVER_refresh")
    receipt = receipt.resolve()
    require(receipt.is_relative_to(p.rt.ROOT), "workspace_tests_required")
    counts = c.test_counts(receipt)
    old = predecessor()
    frozen, retained, markers = sources(), history(), p.backend.markers()
    # Freeze this 20-minute window once, near the end of local preparation.
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(minutes=20)
    xml = time_only(start.isoformat(), end.isoformat()).encode()
    body = json.dumps({"properties": {"format": "xml", "value": xml.decode()}}, separators=(",", ":")).encode()
    require(sources() == frozen and history() == retained, "prepare_sources_history_stable")
    p.release.fs.protect(OUT)
    for name, value in {"diagnostic.xml": xml, "policy-put.json": body,
                        **{stage + "-patch.json": value for stage, value in w.BODIES.items()}}.items():
        with (OUT / name).open("xb") as stream:
            stream.write(value)
    save("prepare-capture.json", {"mode": "RETAINED_ACTUAL03_SUCCESSOR_NOT_FRESH_LIVE_READ",
         "receipt": a.load(WINDOW03 / "offline-after-capture.json"),
         "fresh_before_every_mutation": "MANDATORY_full13_state185_ETag_policy_inheritance"})
    save("manifest.json", {"at_utc": p.now(), "status": "READY_FOR_INDEPENDENT_REVIEW_NO_CLOUD_MUTATION",
         "sources": frozen, "source_sha256": p.release.fs.sha(frozen), "history": retained,
         "state_owner": a.original_bindings(), "start": start.isoformat(), "end": end.isoformat(),
         "nonce": old["nonce"], "xml_sha256": p.sha(OUT / "diagnostic.xml"),
         "put_sha256": p.sha(OUT / "policy-put.json"), "url": a.URL, "policy_url": c.POLICY_URL,
         "patches": {stage: c.sha_bytes(value) for stage, value in w.BODIES.items()},
         "capture_sha256": p.sha(OUT / "prepare-capture.json"), "markers": markers,
         "tests": {"path": receipt.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(receipt), "counts": counts},
         "stages": STAGES, "historical_send_count": 0, "scoring_budget": 1,
         "completion_budget": 0, "retry_budget": 0, "controller_scoring_requests": 0,
         "fixed_text": c.TEXT, "subscription": c.SUBSCRIBER, "IP": c.IP, "chat_path": c.CHAT_PATH,
         "cleanup_expiry_independent": True, "cleanup_requires_parent_signal": True,
         "activation_returns": "ONLINE_READY", "automatic_cleanup": False,
         "fresh_live_prepare": False, "predecessor_window03_manifest_sha256": WINDOW03_MANIFEST,
         "predecessor_offline_readback_sha256": p.sha(WINDOW03 / "offline-after-capture.json"),
         "nonce_and_counter_unchanged": True})
    print(json.dumps({"status": "REVIEW_READY", "package": OUT.relative_to(p.rt.ROOT).as_posix(),
          "manifest_sha256": p.sha(OUT / "manifest.json"), "start": start.isoformat(),
          "end": end.isoformat(), "tests": counts, "cloud_mutations": 0}), flush=True)


def check_package():
    m = load("manifest.json")
    require(m["sources"] == sources() and m["history"] == history(), "immutable04_sources_actual_history")
    require(datetime.fromisoformat(m["end"]) - datetime.fromisoformat(m["start"]) == timedelta(minutes=20),
            "exact04_twenty_minute_window")
    require(m["state_owner"] == a.original_bindings() and m["state_owner"]["serial"] == 185,
            "original_state185_exact")
    tests = p.rt.ROOT / m["tests"]["path"]
    require(p.sha(tests) == m["tests"]["sha256"] and c.test_counts(tests) == m["tests"]["counts"], "actual04_tests_exact")
    require(p.sha(OUT / "prepare-capture.json") == m["capture_sha256"], "retained_capture_exact")
    require(p.sha(OUT / "diagnostic.xml") == m["xml_sha256"]
            and (OUT / "diagnostic.xml").read_bytes() == time_only(m["start"], m["end"]).encode(),
            "fixed04_time_only_XML_exact")
    body = json.dumps({"properties": {"format": "xml", "value": (OUT / "diagnostic.xml").read_text(encoding="utf-8")}},
                      separators=(",", ":")).encode()
    require((OUT / "policy-put.json").read_bytes() == body and c.sha_bytes(body) == m["put_sha256"], "literal04_PUT_exact")
    for stage, value in w.BODIES.items():
        require((OUT / (stage + "-patch.json")).read_bytes() == value
                and m["patches"][stage] == c.sha_bytes(value), "literal04_PATCH_exact")
    require(m["stages"] == STAGES and m["historical_send_count"] == 0
            and m["scoring_budget"] == 1 and m["completion_budget"] == m["retry_budget"] == 0
            and m["nonce"] == predecessor()["nonce"], "one_overall_browser_budget_no_new_nonce")
    current = p.backend.markers()
    require(all(current.get(key) == value for key, value in m["markers"].items())
            and all(key.startswith(OUT.relative_to(p.rt.ROOT).as_posix() + "/")
                    for key in current.keys() - m["markers"].keys()), "foreign_intent_or_history_drift")
    p.require_no_competing_workers(p.backend.workers())
    return m


def compiled04():
    """Never online a reviewed04 window while actual03 is still installed."""
    verified = load("policy-put-verification.json")
    result = load("policy-put-result.json")
    after = load("policy-put-after-capture.json")
    require(result["http_status"] == verified["http_status"] == 200 and result["no_retry"] is True
            and verified["manifest_sha256"] == p.sha(OUT / "manifest.json")
            and verified["intent_sha256"] == p.sha(OUT / "policy-put-intent.json")
            and verified["capture_sha256"] == p.sha(OUT / "policy-put-after-capture.json")
            and after["revision2_online"] is after["revision2_current"] is False
            and after["state_owner"] == load("manifest.json")["state_owner"]
            and all(after[key] is True for key in ("all13_supplemental_exact", "exact_both_formats", "inherited_exact")),
            "actual04_PUT_and_full_offline_readback_required_before_online")


def review(stage):
    require(stage in STAGES, "allowlisted04_stage")
    m = check_package()
    r = load("parent-review.json")
    require(r.get("approved") is True and r.get("independent_native_review") is True
            and r.get("stages") == STAGES and r.get("manifest_sha256") == p.sha(OUT / "manifest.json"),
            "one_actual_parent_review_all_four_scopes")
    transcript = (OUT / r["transcript"]).resolve()
    require(transcript.is_relative_to(OUT.resolve()) and transcript.is_file()
            and p.sha(transcript) == r["transcript_sha256"], "actual_native_transcript_exact")
    at = datetime.fromisoformat(r["at_utc"])
    require(datetime.fromisoformat(m["at_utc"]) <= at <= datetime.now(UTC), "actual04_review_timestamp")
    require(not (OUT / (stage + "-intent.json")).exists(), "existing_intent_NO_RETRY")
    if stage == "offline":
        signal = load("cleanup-authorization.json")
        require(signal.get("parent_says_cleanup") is True
                and signal.get("manifest_sha256") == p.sha(OUT / "manifest.json")
                and signal.get("review_sha256") == p.sha(OUT / "parent-review.json")
                and at <= datetime.fromisoformat(signal["at_utc"]) <= datetime.now(UTC),
                "explicit_parent_cleanup_signal_required")
        # Deliberately NO expiry or review-age guard for cleanup.
    else:
        require(datetime.now(UTC) - at < timedelta(minutes=20), "fresh04_native_review")
        w.check_window(m)
        require(not (OUT / "offline-intent.json").exists(), "cleanup_started_no_activation")
        if stage in ("online", "reserve-browser"):
            compiled04()
    return m


def policy_put():
    review("policy-put")
    p.persistence.transport()
    reads = c.Reads()
    w.capture(reads, "policy-put-before", False, prior.DIAG / "diagnostic.xml")
    actual = reads.policy(";rev=2", "rawxml")
    exports({"rawxml": actual, "xml": reads.policy(";rev=2", "xml")}, prior.DIAG / "diagnostic.xml")
    etag, fetched = a.valid_etag(actual["etag"]), datetime.now(UTC)
    review("policy-put")
    body = (OUT / "policy-put.json").read_bytes()
    require(datetime.now(UTC) - fetched < timedelta(seconds=60), "fresh04_policy_ETag")
    w.exclusive("policy-put-intent.json", {"at_utc": p.now(), "pid": os.getpid(), "method": "PUT",
        "url": c.POLICY_URL, "etag": etag, "manifest_sha256": p.sha(OUT / "manifest.json"),
        "review_sha256": p.sha(OUT / "parent-review.json"), "body_sha256": c.sha_bytes(body),
        "attempt_budget": 1, "retries": 0, "redirects": 0})
    result = put_transport.once(etag, reads.token, body)
    save("policy-put-result.json", {"at_utc": p.now(), **result, "no_retry": True})
    require(result.get("http_status") == 200, "PUT_failure_or_ambiguous_NO_RETRY_parent_decides_cleanup")
    after = w.capture(reads, "policy-put-after", False, OUT / "diagnostic.xml")
    check_package()
    save("policy-put-verification.json", {"at_utc": p.now(), "http_status": 200,
         "manifest_sha256": p.sha(OUT / "manifest.json"), "intent_sha256": p.sha(OUT / "policy-put-intent.json"),
         "capture_sha256": p.sha(OUT / "policy-put-after-capture.json"), "state_owner": after["state_owner"],
         "revision2_online": False, "revision2_current": False, "all13_supplemental_exact": True,
         "exact_both_formats": True, "controller_scoring_requests": 0, "completion_requests": 0})


def activate():
    review("policy-put")
    # Controller ownership exists BEFORE any expensive read or wire request.
    # A silent terminal is never permission to invoke this controller again.
    w.exclusive("activate-intent.json", {"at_utc": p.now(), "pid": os.getpid(),
        "manifest_sha256": p.sha(OUT / "manifest.json"), "attempt_budget": 1,
        "sequence": ["policy-put", "online", "reserve-browser"], "automatic_cleanup": False})
    policy_put()
    w.execute("online")
    w.reserve_browser()
    result = {"at_utc": p.now(), "status": "ONLINE_READY", "parent_owns_browser_Send": True,
              "manifest_sha256": p.sha(OUT / "manifest.json"),
              "reservation_sha256": p.sha(OUT / "reserve-browser-intent.json"),
              "end": load("manifest.json")["end"], "send_count": 0, "scoring_requests": 0,
              "completion_requests": 0, "cleanup_requires_parent_signal": True}
    save("activate-result.json", result)
    print(json.dumps(result), flush=True)
    return result


def status():
    # Local-only reconciliation: never invokes a stage, transport or cleanup.
    names = ("activate-intent.json", "policy-put-result.json", "online-result.json",
             "online-verification.json", "reserve-browser-intent.json", "activate-result.json",
             "offline-intent.json", "offline-result.json", "offline-verification.json")
    return {"at_utc": p.now(), "mode": "LOCAL_READ_ONLY_NO_RETRY",
            "artifacts": {name: {"sha256": p.sha(OUT / name), "receipt": load(name)}
                  for name in (*names, *(path.name for path in sorted(OUT.glob("*-failure-*.json"))))
                  if (OUT / name).is_file()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare-review", "activate", "offline", "status"))
    parser.add_argument("--tests", type=Path)
    args = parser.parse_args()
    try:
        with bindings():
            if args.stage == "prepare-review":
                require(args.tests is not None, "actual04_tests_required")
                prepare(args.tests)
            elif args.stage == "activate":
                activate()
            elif args.stage == "offline":
                w.execute("offline")
            else:
                print(json.dumps(status()), flush=True)
        return 0
    except Exception as exc:
        result = {"at_utc": p.now(), "stage": args.stage, "type": type(exc).__name__,
                  "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed",
                  "retry_authorized": False, "automatic_cleanup": False}
        if OUT.exists() and args.stage != "status":
            save(args.stage + "-failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", result)
        print(json.dumps(result), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())