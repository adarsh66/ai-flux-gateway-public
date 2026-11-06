"""Time-only successor to compiled diagnostic02; prepare-review / policy-put.

No online, browser, scoring or completion entrypoint. Parent native review must
bind the exact new manifest before one offline compiler PUT. No silent refresh.
"""
import argparse
from datetime import UTC, datetime, timedelta
import json
import multiprocessing
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

from scripts.deployment import auto_diagnostic_window as w

c, d, p, a = w.c, w.d, w.p, w.a
require = w.require
OUT = a.HOME / "scoring-diagnostic03"


def save(name, value):
    p.backend.save(OUT, name, value)


def time_only(start, end):
    old = w.check_compilation()
    root = c.tree((w.DIAG / "diagnostic.xml").read_bytes())
    inbound = root.find("inbound")
    require(c.signature(inbound[2]) == c.signature(d.scope_guard(old["start"], old["end"])), "exact_old_scope")
    inbound.remove(inbound[2])
    inbound.insert(2, d.scope_guard(start, end))
    xml = c.ET.tostring(root, encoding="unicode", short_empty_elements=True)
    with d.bindings():
        c.guard(a.load(w.DIAG / "prepare-capture.json")["normalized_original"], xml, old["nonce"], start, end)
    # Reverse ONLY the scope delta; all other nodes, original counters/nonce,
    # safety, input, IP/subscription and scorer terminal remain exactly equal.
    inbound.remove(inbound[2])
    inbound.insert(2, d.scope_guard(old["start"], old["end"]))
    require(c.signature(root) == c.signature(c.tree((w.DIAG / "diagnostic.xml").read_bytes())), "time_only_complete_structure")
    return xml


def prepare(receipt):
    require(not OUT.exists(), "existing_diagnostic03_never_refresh")
    receipt = receipt.resolve()
    require(receipt.is_relative_to(p.rt.ROOT), "workspace_test_receipt")
    counts = c.test_counts(receipt)
    old = w.check_compilation()
    frozen, retained = w.sources(), w.history()
    owner = a.original_bindings()
    p.require_no_competing_workers(p.backend.workers())
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(minutes=20)
    xml = time_only(start.isoformat(), end.isoformat())
    body = json.dumps({"properties": {"format": "xml", "value": xml}}, separators=(",", ":")).encode()
    p.release.fs.protect(OUT)
    for name, value in (("diagnostic.xml", xml.encode()), ("policy-put.json", body)):
        with (OUT / name).open("xb") as stream:
            stream.write(value)
    save("manifest.json", {"at_utc": p.now(), "status": "TIME_ONLY_REVIEW_READY_NO_PUT_NO_FRESH_LIVE_READ_CLAIM",
         "sources": frozen, "source_sha256": p.release.fs.sha(frozen), "diagnostic02": retained,
         "state_owner": owner, "start": start.isoformat(), "end": end.isoformat(), "nonce": old["nonce"],
         "xml_sha256": p.sha(OUT / "diagnostic.xml"), "put_sha256": c.sha_bytes(body),
         "markers": p.backend.markers(), "tests": {"path": receipt.relative_to(p.rt.ROOT).as_posix(),
         "sha256": p.sha(receipt), "counts": counts}, "scoring_budget": 1, "completion_budget": 0,
         "retry_budget": 0, "nonce_and_counter_unchanged": True, "allowed_stages": ["policy-put"],
         "fresh_before_and_after": "mandatory_all13_fullstate_exactpolicy_ETag_offline_noncurrent"})
    print(json.dumps({"package": OUT.relative_to(p.rt.ROOT).as_posix(), "manifest_sha256": p.sha(OUT / "manifest.json"),
         "source_sha256": p.release.fs.sha(frozen), "xml_sha256": p.sha(OUT / "diagnostic.xml"),
         "start": start.isoformat(), "end": end.isoformat(), "no_mutation": True}), flush=True)


def review():
    m = a.load(OUT / "manifest.json")
    require(m["sources"] == w.sources() and m["diagnostic02"] == w.history()
            and m["state_owner"] == a.original_bindings(), "source_history_state_exact")
    require(p.sha(OUT / "diagnostic.xml") == m["xml_sha256"] and p.sha(OUT / "policy-put.json") == m["put_sha256"]
            and (OUT / "diagnostic.xml").read_bytes() == time_only(m["start"], m["end"]).encode(), "time_only_artifacts_exact")
    expected_body = json.dumps({"properties": {"format": "xml", "value": (OUT / "diagnostic.xml").read_text(encoding="utf-8")}}, separators=(",", ":")).encode()
    require((OUT / "policy-put.json").read_bytes() == expected_body, "literal_policy_body_exact")
    tests = p.rt.ROOT / m["tests"]["path"]
    require(p.sha(tests) == m["tests"]["sha256"] and c.test_counts(tests) == m["tests"]["counts"], "tests_exact")
    r = a.load(OUT / "policy-put-parent-review.json")
    require(r.get("approved") is True and r.get("independent_native_review") is True and r.get("stage") == "policy-put"
            and r.get("manifest_sha256") == p.sha(OUT / "manifest.json"), "actual_parent_offline_PUT_review")
    at = datetime.fromisoformat(r["at_utc"])
    require(datetime.fromisoformat(m["at_utc"]) <= at <= datetime.now(UTC)
            and datetime.now(UTC) - at < timedelta(minutes=20), "fresh_actual_review")
    transcript = (OUT / r["transcript"]).resolve()
    require(transcript.is_relative_to(OUT.resolve()) and transcript.is_file() and p.sha(transcript) == r["transcript_sha256"], "actual_review_transcript")
    require(not (OUT / "policy-put-intent.json").exists(), "existing_intent_NO_RETRY")
    markers = p.backend.markers()
    require(all(markers.get(k) == v for k, v in m["markers"].items())
            and all(k.startswith(OUT.relative_to(p.rt.ROOT).as_posix() + "/") for k in markers.keys() - m["markers"].keys()), "foreign_intent_or_history_drift")
    p.require_no_competing_workers(p.backend.workers())
    w.check_window(m)
    return m


def wire_child(connection, etag, token, body):
    try:
        request = Request(c.POLICY_URL, method="PUT", data=body, headers={"Authorization": "Bearer " + token,
                          "If-Match": a.valid_etag(etag), "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with a.opener(p.rt.CA).open(request, timeout=45) as response:
                result = a.safe_http(response.status, response.headers)
        except HTTPError as exc:
            result = a.safe_http(exc.code, exc.headers)
            try:
                result.update(d.safe_compilation_error(exc.read(65537)))
            finally:
                exc.close()
        connection.send(result)
    except Exception as exc:
        connection.send({"transport_error": type(exc).__name__})
    finally:
        connection.close()


def once(etag, token, body):
    ctx = multiprocessing.get_context("spawn")
    rx, tx = ctx.Pipe(duplex=False)
    child = ctx.Process(target=wire_child, args=(tx, etag, token, body))
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


def execute():
    review()
    p.persistence.transport()
    reads = c.Reads()
    # New controller output only; the old diagnostic02 files are never written.
    previous = w.OUT
    w.OUT = OUT
    try:
        w.capture(reads, "policy-put-before", False)
        actual = reads.policy(";rev=2", "rawxml")
        w.exports({"rawxml": actual, "xml": reads.policy(";rev=2", "xml")})
        etag = a.valid_etag(actual["etag"])
        fetched_at = datetime.now(UTC)
        review()
        body = (OUT / "policy-put.json").read_bytes()
        require(datetime.now(UTC) - fetched_at < timedelta(seconds=60), "fresh_actual_policy_ETag")
        w.exclusive("policy-put-intent.json", {"at_utc": p.now(), "pid": os.getpid(), "method": "PUT", "url": c.POLICY_URL,
             "etag": etag, "body_sha256": c.sha_bytes(body), "manifest_sha256": p.sha(OUT / "manifest.json"),
             "review_sha256": p.sha(OUT / "policy-put-parent-review.json"), "attempt_budget": 1, "retries": 0, "redirects": 0})
        result = once(etag, reads.token, body)
        save("policy-put-result.json", {"at_utc": p.now(), **result, "no_retry": True})
        require(result.get("http_status") == 200, "compiler_failure_or_ambiguous_NO_RETRY")
        w.capture(reads, "policy-put-after", False, OUT / "diagnostic.xml")
        manifest = a.load(OUT / "manifest.json")
        require(manifest["sources"] == w.sources() and manifest["diagnostic02"] == w.history()
            and manifest["state_owner"] == a.original_bindings(), "post_PUT_source_history_state_exact")
        save("policy-put-verification.json", {"at_utc": p.now(), "http_status": 200, "exact_both_formats": True,
             "revision2_online": False, "revision2_current": False, "all13_supplemental_exact": True,
             "controller_scoring_requests": 0, "completion_requests": 0})
    finally:
        w.OUT = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare-review", "policy-put"))
    parser.add_argument("--tests", type=Path)
    args = parser.parse_args()
    try:
        if args.stage == "prepare-review":
            require(args.tests is not None, "actual_test_receipt_required")
            prepare(args.tests)
        else:
            execute()
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