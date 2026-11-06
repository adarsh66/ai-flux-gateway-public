"""Independent successor: prepare, online, reserve-browser, offline. NEVER scores.

Only literal owned-revision PATCHes; inherited OriginalUrl uncertainty is a
functional fail-closed risk, not a reason to bypass any inherited policy.
One parent native receipt approves BOTH online and expiry-independent cleanup.
"""
import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

from scripts.deployment import auto_diagnostic02 as d

c = d.core
a = c.a
p = c.p
require = c.require
DIAG = d.OUT
OUT = a.HOME / "scoring-window01"
TEST = p.rt.ROOT / "tests/unit/test_auto_diagnostic_window.py"
DOC = p.rt.ROOT / "docs/auto-diagnostic-window-review-20261029.md"
BROWSER = Path(__file__).with_name("auto_diagnostic_browser.mjs")
VERIFY = DIAG / "read_only_export_audit.py"
BODIES = {"online": b'{"properties":{"isOnline":true}}', "offline": a.BODY}


def load(name):
    return a.load(OUT / name)


def save(name, value):
    p.backend.save(OUT, name, value)


def exclusive(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def history():
    return {f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
            for f in sorted(DIAG.iterdir()) if f.is_file()}


def sources():
    paths = {* (p.rt.ROOT / "scripts/deployment").glob("*.py"), TEST, DOC, BROWSER, VERIFY,
             p.rt.ROOT / "tests/auto_diagnostic_browser.test.mjs",
             * (p.rt.ROOT / "tests/unit").glob("test_auto_diagnostic*.py")}
    paths |= {p.rt.ROOT / name for name in p.sources()}
    return {f.relative_to(p.rt.ROOT).as_posix(): p.sha(f) for f in sorted(paths)}


def check_compilation():
    manifest = a.load(DIAG / "manifest.json")
    receipt = a.load(DIAG / "policy-put-supplemental-verification.json")
    result = a.load(DIAG / "policy-put-result.json")
    require(result["http_status"] == receipt["http_status"] == 200
            and receipt["exact_both_formats"] is True
            and receipt["manifest_sha256"] == p.sha(DIAG / "manifest.json")
            and receipt["candidate_xml_sha256"] == p.sha(DIAG / "diagnostic.xml") == manifest["xml_sha256"]
            and receipt["intent_sha256"] == p.sha(DIAG / "policy-put-intent.json")
            and receipt["result_sha256"] == p.sha(DIAG / "policy-put-result.json")
            and receipt["supplemental_verifier_sha256"] == p.sha(VERIFY), "actual_compilation_and_reconciliation_binding")
    with d.bindings():
        c.guard(a.load(DIAG / "prepare-capture.json")["normalized_original"],
                (DIAG / "diagnostic.xml").read_bytes(), manifest["nonce"], manifest["start"], manifest["end"])
    return manifest


def exports(formats, policy=None):
    spec = importlib.util.spec_from_file_location("exact_retained_export", VERIFY)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    expected = c.tree((policy or DIAG / "diagnostic.xml").read_bytes())
    verifier.verify(formats["rawxml"]["body"]["properties"]["value"], expected, c)
    require(c.signature(c.tree(formats["xml"]["body"]["properties"]["value"], exported=True))
            == c.signature(expected), "XML_exact_approved_policy")


def capture(reads, label, wanted, policy=None):
    """No parent-controller rebinding; full original13/state/inheritance checks."""
    started = p.now()
    owner = a.original_bindings()
    baseline = p.release.snapshot()
    supplement = a.v.supplemental(baseline)
    require(len(baseline) == 13 and baseline == a.load(a.HOME / "protected-before.json")
            and supplement == a.load(a.HOME / "supplemental-before.json"), "all13_supplemental_exact")
    flat, _ = reads.get("/revisions")
    require(not flat.get("nextLink"), "complete_revision_list")
    rows = [p.summarize_revision(row) for row in flat["value"]]
    expected = deepcopy(a.load(a.HOME / "offline-correction02/revisions-before.json"))
    owned = [row for row in rows if row["revision"] == "2"]
    require(len(owned) == 1 and type(owned[0]["is_online"]) is bool, "explicit_owned_online_boolean")
    online = owned[0]["is_online"]
    if wanted is not None:
        require(online is wanted, "expected_owned_online_flag")
    for row in expected:
        if row["revision"] == "2":
            row["is_online"] = online
    require(rows == expected and owned[0]["is_current"] is False, "all_revision_flags_current1_unchanged")
    api, _ = reads.get(";rev=2")
    props = api["properties"]
    require(api["id"].lower() == a.RID.lower() and props["apiRevision"] == "2"
            and props["path"] == "dev/llm/v1" and props["subscriptionRequired"] is True
            and props["apiRevisionDescription"] == p.expected_body(a.SELECTION)["properties"]["apiRevisionDescription"], "owned_nonce_path_subscription_exact")
    current, _ = reads.get("")
    prior = a.load(DIAG / "prepare-capture.json")
    require(p.release.fs.sha(current) == prior["current_api_sha256"], "current1_full_metadata_exact")
    inherited, path_proven = c.inheritance(reads)
    require(inherited == prior["inheritance"], "all_inherited_policies_operations_diagnostics_exact")
    formats = {fmt: reads.policy(";rev=2", fmt) for fmt in ("rawxml", "xml")}
    exports(formats, policy)
    head = p.backend.blob_head()
    old_head = a.load(a.HOME / "offline-correction02/remote-head-before.json")
    require(all(head[key] == old_head[key] for key in a.HEAD_KEYS)
            and a.original_bindings() == owner, "state_owner_and_remote_head_exact")
    # Fetch the ETag LAST, after the expensive protected reads. Never wildcard.
    last_api, etag = reads.get(";rev=2")
    require(last_api == api, "owned_metadata_stable_during_capture")
    a.valid_etag(etag)
    result = {"started_at_utc": started, "at_utc": p.now(), "etag": etag,
              "revision2_online": online, "revision2_current": False, "revisions": rows,
              "state_owner": owner, "baseline_sha256": p.release.fs.sha(baseline),
              "supplemental_sha256": p.release.fs.sha(supplement), "current_api_sha256": p.release.fs.sha(current),
              "all13_supplemental_exact": True, "exact_both_formats": True,
              "inherited_exact": True, "path_semantics_proven": path_proven,
              "policy_format_hashes": {fmt: c.sha_bytes(formats[fmt]["body"]["properties"]["value"].encode()) for fmt in formats}}
    save(label + "-capture.json", result)
    return result


def check_window(manifest, now=None):
    now = now or datetime.now(UTC)
    require(datetime.fromisoformat(manifest["start"]) <= now
            < datetime.fromisoformat(manifest["end"]) - timedelta(seconds=90), "fixed_window_90_seconds_cleanup_reserve")


def check_package():
    manifest = load("manifest.json")
    require(manifest["sources"] == sources() and manifest["diagnostic02"] == history(), "immutable_source_and_diag02_history")
    require(manifest["state_owner"] == a.original_bindings(), "original_owned_state_exact")
    tests = p.rt.ROOT / manifest["tests"]["path"]
    require(p.sha(tests) == manifest["tests"]["sha256"] and c.test_counts(tests) == manifest["tests"]["counts"], "actual_tests_bound")
    require(p.sha(OUT / "prepare-capture.json") == manifest["capture_sha256"], "prepare_capture_exact")
    for stage, body in BODIES.items():
        require((OUT / (stage + "-patch.json")).read_bytes() == body
                and c.sha_bytes(body) == manifest["patches"][stage], "literal_PATCH_body_exact")
    check_compilation()
    markers = p.backend.markers()
    require(all(markers.get(key) == value for key, value in manifest["markers"].items())
            and all(key.startswith(OUT.relative_to(p.rt.ROOT).as_posix() + "/") for key in markers.keys() - manifest["markers"].keys()), "foreign_intent_or_history_drift")
    p.require_no_competing_workers(p.backend.workers())
    return manifest


def review(stage):
    require(stage in BODIES or stage == "reserve-browser", "allowlisted_stage")
    manifest = check_package()
    receipt = load("parent-review.json")
    require(receipt.get("approved") is True and receipt.get("independent_native_review") is True
            and receipt.get("stages") == ["online", "reserve-browser", "offline"]
            and receipt.get("manifest_sha256") == p.sha(OUT / "manifest.json"), "actual_parent_review_binds_online_browser_AND_cleanup")
    transcript = (OUT / receipt["transcript"]).resolve()
    require(transcript.is_relative_to(OUT.resolve()) and transcript.is_file()
            and p.sha(transcript) == receipt["transcript_sha256"], "native_transcript_binding")
    approved_at = datetime.fromisoformat(receipt["at_utc"])
    require(approved_at.tzinfo is not None and datetime.fromisoformat(manifest["at_utc"]) <= approved_at <= datetime.now(UTC), "actual_review_timestamp")
    # Cleanup authorization deliberately survives expiry, failed online/browser,
    # and old review age. Source/ownership/protected baseline still mandatory.
    if stage != "offline":
        require(datetime.now(UTC) - approved_at < timedelta(minutes=20), "fresh_online_review")
        check_window(manifest)
        require(not (OUT / "offline-intent.json").exists(), "cleanup_started_no_further_online_or_browser")
    require(not (OUT / (stage + "-intent.json")).exists(), "existing_intent_NO_RETRY")
    return manifest


def mutation_request(stage, etag, token):
    require(stage in BODIES, "PATCH_only_online_or_offline")
    return Request(a.URL, method="PATCH", data=BODIES[stage], headers={
        "Authorization": "Bearer " + token, "If-Match": a.valid_etag(etag),
        "Content-Type": "application/json", "Accept": "application/json"})


def wire_child(connection, stage, etag, token):
    try:
        request = mutation_request(stage, etag, token)
        try:
            with a.opener(p.rt.CA).open(request, timeout=45) as response:
                result = a.safe_http(response.status, response.headers)
        except HTTPError as exc:
            result = a.safe_http(exc.code, exc.headers)
            exc.close()
        connection.send(result)
    except Exception as exc:
        connection.send({"transport_error": type(exc).__name__})
    finally:
        connection.close()


def once(stage, etag, token):
    context = multiprocessing.get_context("spawn")
    rx, tx = context.Pipe(duplex=False)
    child = context.Process(target=wire_child, args=(tx, stage, etag, token))
    try:
        child.start()
        tx.close()
        return rx.recv() if rx.poll(60) else {"transport_error": "WallClockTimeout", "outcome": "unknown_no_retry"}
    finally:
        if child.pid is not None:
            if child.is_alive():
                child.terminate()
            child.join(5)
            if child.is_alive():
                child.kill()
                child.join(5)
        rx.close()
        tx.close()


def prepare(receipt):
    require(not OUT.exists(), "existing_package_reconcile_only")
    receipt = receipt.resolve()
    require(receipt.is_relative_to(p.rt.ROOT), "workspace_test_receipt")
    counts = c.test_counts(receipt)
    diagnostic = check_compilation()
    frozen, retained = sources(), history()
    p.require_no_competing_workers(p.backend.workers())
    p.release.fs.protect(OUT)
    # Both immutable cleanup and online bodies exist BEFORE any online stage.
    for stage, body in BODIES.items():
        with (OUT / (stage + "-patch.json")).open("xb") as stream:
            stream.write(body)
    p.persistence.transport()
    before = capture(c.Reads(), "prepare", False)
    require(sources() == frozen and history() == retained, "prepare_source_history_stable")
    save("manifest.json", {"at_utc": p.now(), "status": "READY_FOR_PARENT_NATIVE_REVIEW_NO_MUTATION",
         "sources": frozen, "source_sha256": p.release.fs.sha(frozen), "diagnostic02": retained,
         "state_owner": before["state_owner"], "start": diagnostic["start"], "end": diagnostic["end"],
         "url": a.URL, "patches": {stage: c.sha_bytes(body) for stage, body in BODIES.items()},
         "capture_sha256": p.sha(OUT / "prepare-capture.json"), "markers": p.backend.markers(),
         "tests": {"path": receipt.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(receipt), "counts": counts},
         "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0, "controller_scoring_requests": 0,
         "fixed_text": c.TEXT, "subscription": c.SUBSCRIBER, "IP": c.IP, "chat_path": c.CHAT_PATH,
         "cleanup_expiry_independent": True, "path_uncertainty": "may_403_safe_no_global_or_base_bypass"})
    print(json.dumps({"package": OUT.relative_to(p.rt.ROOT).as_posix(), "manifest_sha256": p.sha(OUT / "manifest.json"),
                      "source_sha256": p.release.fs.sha(frozen), "end": diagnostic["end"], "tests": counts}), flush=True)


def prepare_review(receipt):
    """Offline assembly, NOT a retry/freshness claim; preserves failed reads."""
    require(not (OUT / "manifest.json").exists(), "existing_manifest_reconcile_only")
    require(not any((OUT / (stage + "-intent.json")).exists() for stage in BODIES), "no_existing_mutation")
    receipt = receipt.resolve()
    require(receipt.is_relative_to(p.rt.ROOT), "workspace_receipt")
    counts = c.test_counts(receipt)
    diagnostic = check_compilation()
    p.release.fs.protect(OUT)
    for stage, body in BODIES.items():
        path = OUT / (stage + "-patch.json")
        if path.exists():
            require(path.read_bytes() == body, "existing_literal_body_unchanged")
        else:
            with path.open("xb") as stream:
                stream.write(body)
    retained = a.load(DIAG / "policy-put-supplemental-verification.json")
    save("prepare-capture.json", {"mode": "RETAINED_GET_EVIDENCE_NOT_FRESH_LIVE_PREPARE",
         "receipt": retained, "fresh_before_every_mutation": "MANDATORY_full13_state_ETag_policy_inheritance"})
    frozen = sources()
    save("manifest.json", {"at_utc": p.now(), "status": "REVIEW_READY_RETAINED_PROOF_FRESH_EXECUTION_GATES_REQUIRED",
         "sources": frozen, "source_sha256": p.release.fs.sha(frozen), "diagnostic02": history(),
         "state_owner": a.original_bindings(), "start": diagnostic["start"], "end": diagnostic["end"],
         "url": a.URL, "patches": {stage: c.sha_bytes(body) for stage, body in BODIES.items()},
         "capture_sha256": p.sha(OUT / "prepare-capture.json"), "markers": p.backend.markers(),
         "tests": {"path": receipt.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(receipt), "counts": counts},
         "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0, "controller_scoring_requests": 0,
         "fixed_text": c.TEXT, "subscription": c.SUBSCRIBER, "IP": c.IP, "chat_path": c.CHAT_PATH,
         "cleanup_expiry_independent": True, "fresh_live_prepare": False,
         "path_uncertainty": "may_403_safe_no_global_or_base_bypass"})
    print(json.dumps({"package": OUT.relative_to(p.rt.ROOT).as_posix(), "manifest_sha256": p.sha(OUT / "manifest.json"),
         "source_sha256": p.release.fs.sha(frozen), "tests": counts, "fresh_live_prepare": False}), flush=True)


def execute(stage):
    require(stage in BODIES, "literal_PATCH_only")
    review(stage)
    p.persistence.transport()
    reads = c.Reads()
    # Cleanup accepts either actual flag, including ambiguous failed online.
    before = capture(reads, stage + "-before", False if stage == "online" else None)
    review(stage)
    require(datetime.now(UTC) - datetime.fromisoformat(before["at_utc"]) < timedelta(seconds=60), "fresh_actual_etag")
    exclusive(stage + "-intent.json", {"at_utc": p.now(), "pid": os.getpid(), "stage": stage,
              "manifest_sha256": p.sha(OUT / "manifest.json"), "review_sha256": p.sha(OUT / "parent-review.json"),
              "url": a.URL, "method": "PATCH", "body_sha256": c.sha_bytes(BODIES[stage]),
              "etag": before["etag"], "attempt_budget": 1, "retries": 0, "redirects": 0, "wall_clock_seconds": 60})
    result = once(stage, before["etag"], reads.token)
    save(stage + "-result.json", {"at_utc": p.now(), **result, "no_retry": True})
    # Read back even a failed/ambiguous wire outcome; never repeat the write.
    after = capture(reads, stage + "-after", None)
    require(result.get("http_status") in (200, 201, 202, 204)
            and after["revision2_online"] is (stage == "online"), "mutation_or_readback_failed_NO_RETRY_cleanup_separate")
    check_package()
    save(stage + "-verification.json", {"at_utc": p.now(), "http_status": result["http_status"],
         "revision2_online": after["revision2_online"], "revision2_current": False,
         "exact_both_formats": True, "all13_supplemental_exact": True, "controller_scoring_requests": 0,
         "manifest_sha256": p.sha(OUT / "manifest.json"), "intent_sha256": p.sha(OUT / (stage + "-intent.json"))})


def reserve_browser():
    manifest = review("reserve-browser")
    online = load("online-verification.json")
    require(online["revision2_online"] is True and online["revision2_current"] is False
            and online["manifest_sha256"] == p.sha(OUT / "manifest.json")
            and online["intent_sha256"] == p.sha(OUT / "online-intent.json")
            and not (OUT / "offline-intent.json").exists(), "verified_online_no_cleanup_started")
    p.persistence.transport()
    capture(c.Reads(), "browser-before", True)
    review("reserve-browser")
    exclusive("reserve-browser-intent.json", {"at_utc": p.now(), "pid": os.getpid(),
        "manifest_sha256": p.sha(OUT / "manifest.json"), "review_sha256": p.sha(OUT / "parent-review.json"),
        "fixed_text": c.TEXT, "model": "gpt-5.4-mini", "subscription": c.SUBSCRIBER, "IP": c.IP,
        "path": c.CHAT_PATH, "end": manifest["end"], "max_completion_tokens": 1024,
        "attempt_budget": 1, "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0,
        "browser_source_sha256": p.sha(BROWSER), "auth": "unchanged_URL_only_no_header_or_storage_inspection"})
    print(json.dumps({"browser_intent_sha256": p.sha(OUT / "reserve-browser-intent.json"), "send_not_executed": True}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "prepare-review", "online", "reserve-browser", "offline"))
    parser.add_argument("--tests", type=Path)
    args = parser.parse_args()
    try:
        if args.stage in ("prepare", "prepare-review"):
            require(args.tests is not None, "actual_tests_required")
            (prepare if args.stage == "prepare" else prepare_review)(args.tests)
        elif args.stage == "reserve-browser":
            reserve_browser()
        else:
            execute(args.stage)
        return 0
    except Exception as exc:
        result = {"at_utc": p.now(), "stage": args.stage, "type": type(exc).__name__,
                  "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed", "retry_authorized": False}
        if OUT.exists():
            save(args.stage + "-failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", result)
        print(json.dumps(result), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())