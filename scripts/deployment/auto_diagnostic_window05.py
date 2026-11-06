"""Offline successor05; retained transports, fresh parent review, no Send entrypoint.

Only a new 30-minute UTC scope and the explicitly authorized diagnostic IP differ
from actual04. Historical wire count is UNKNOWN. Never replay any predecessor.
"""
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from scripts.deployment import auto_diagnostic_window04 as prior

w, c, d, p, a = prior.w, prior.c, prior.d, prior.p, prior.a
require = w.require
OLD = prior.OUT
OUT = a.HOME / "scoring-diagnostic05"
PROOF = a.HOME / "diagnostic04-full-readonly-20261029T082900768569Z"
PROOF_SHA = "0a51675b6a203aeb5f7103dc0854f337c0728ebbf7d64c2155b3ff248761e262"
MANIFEST04 = "d838881109e50d4de139a7db16a8c362d2f0828b3e72a492b9658820a452b04e"
IP = "167.103.66.248"
OLD_IP = "167.103.63.12"
STAGES = prior.STAGES
DOC = p.rt.ROOT / "docs/auto-diagnostic05-review-20261029.md"
BROWSER = Path(__file__).with_name("auto_diagnostic_browser05.mjs")
NODE_TEST = p.rt.ROOT / "tests/auto_diagnostic_browser05.test.mjs"
_exports = prior._exports


def load(name):
    return a.load(OUT / name)


def sources():
    # Historical narrative docs are not executable guards. Their ORIGINAL
    # hashes remain in immutable manifests/history, never rewritten/restamped.
    current = {name: digest for name, digest in w.sources().items()
               if not (name.startswith("docs/") and name.endswith(".md"))}
    return {**current, **{f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
                         for f in (Path(__file__), BROWSER, BROWSER.with_name("auto_diagnostic_browser.mjs"), NODE_TEST, DOC,
                                   p.rt.ROOT / "packages/ui/src/pages/PlaygroundPage.tsx")}}


def history():
    folders = [folder for folder in a.HOME.glob("scoring-*")
               if folder.is_dir() and folder != OUT]
    folders.append(PROOF)
    return {f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
            for folder in sorted(folders) for f in sorted(folder.rglob("*"))
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"}


def predecessor():
    """Use actual complete04 reconciliation, NOT stale04.check_package()."""
    require(p.sha(PROOF / "result.json") == PROOF_SHA
            and p.sha(OLD / "manifest.json") == MANIFEST04, "actual04_proof_manifest_exact")
    proof, old = a.load(PROOF / "result.json"), a.load(OLD / "manifest.json")
    require(proof["status"] == "COMPLETE_PROTECTED13_READONLY_VERIFIED"
            and proof["full13_verified"] is True and all(v is True for v in proof["checks"].values())
            and proof["cloud_mutations"] == proof["mutation_retries"] == 0
            and proof["diagnostic_stages_invoked"] == [], "actual04_full13_readonly_required")
    for name, digest in proof["evidence"].items():
        require(p.sha(PROOF / name) == digest, "actual04_reconciliation_evidence_exact")
    for name, digest in a.load(PROOF / "original-evidence-hashes-before.json").items():
        require(p.sha(p.rt.ROOT / name) == digest, "original04_intents_and_evidence_exact")
    current = sources()
    require(all(current.get(name) == digest for name, digest in old["sources"].items()
                if not (name.startswith("docs/") and name.endswith(".md"))),
            "all04_executable_source_evidence_preserved")
    owner = a.original_bindings()
    after = a.load(PROOF / "fresh-capture.json")
    expected_revisions = a.load(a.HOME / "offline-correction02/revisions-before.json")
    # Original capture also normalizes ONLY owned revision2's observed flag;
    # the original pre-correction list predates its offline PATCH.
    require(len([row for row in expected_revisions if row["revision"] == "2"]) == 1,
            "one_original_owned_revision2")
    for row in expected_revisions:
        if row["revision"] == "2":
            row["is_online"] = False
    require(owner == old["state_owner"] == proof["state_owner"] == after["state_owner"]
            and owner["serial"] == 185
            and after["revision2_online"] is after["revision2_current"] is False
            and all(after[k] is True for k in ("all13_supplemental_exact", "exact_both_formats", "inherited_exact"))
            and after["baseline_sha256"] == proof["baseline_sha256"] == p.release.fs.sha(a.load(a.HOME / "protected-before.json"))
            and after["supplemental_sha256"] == proof["supplemental_sha256"] == p.release.fs.sha(a.load(a.HOME / "supplemental-before.json"))
            and after["revisions"] == expected_revisions,
            "actual04_offline_current1_full13_state185")
    for stage, method, url, body in (("policy-put", "PUT", c.POLICY_URL, (OLD / "policy-put.json").read_bytes()),
                                    ("online", "PATCH", a.URL, w.BODIES["online"]),
                                    ("offline", "PATCH", a.URL, w.BODIES["offline"])):
        intent, result = a.load(OLD / (stage + "-intent.json")), a.load(OLD / (stage + "-result.json"))
        require(intent["method"] == method and intent["url"] == url
                and intent["manifest_sha256"] == MANIFEST04
                and intent["review_sha256"] == p.sha(OLD / "parent-review.json")
                and intent["attempt_budget"] == 1 and intent["retries"] == intent["redirects"] == 0
                and intent["body_sha256"] == c.sha_bytes(body)
                and result["http_status"] == 200 and result["no_retry"] is True
                and datetime.fromisoformat(intent["at_utc"]) < datetime.fromisoformat(result["at_utc"])
                < datetime.fromisoformat(after["at_utc"]), "actual04_original_consumed_wire_binding")
    require(after["policy_format_hashes"] == a.load(OLD / "policy-put-after-capture.json")["policy_format_hashes"],
            "actual04_final_policy_exact")
    attempt = a.load(OLD / "browser-attempt-result.json")
    require(attempt["browser_click_invocations"] == 1 and attempt["scoring_request_count"] is None
            and attempt["completion_request_count"] is None and attempt["retry_count"] == 0,
            "historical04_wire_unknown_NOT_zero")
    # Validate original XML under its ORIGINAL IP/time scope, never substitute
    # the current IP into historical evidence checks.
    with scope_binding(d.scope_guard, OLD_IP):
        c.guard(a.load(w.DIAG / "prepare-capture.json")["normalized_original"],
                (OLD / "diagnostic.xml").read_bytes(), old["nonce"], old["start"], old["end"])
    return old


@contextmanager
def scope_binding(scope, ip):
    previous = c.scope_guard, c.IP
    try:
        c.scope_guard, c.IP = scope, ip
        yield
    finally:
        c.scope_guard, c.IP = previous


def scope_guard(start, end):
    begin, finish = d.utc_ticks(start), d.utc_ticks(end)
    require(finish - begin == 30 * 60 * 10_000_000, "exact05_thirty_minute_window")
    # Reuse the reviewed ticks-expression producer with a permitted 20-minute
    # interval, then replace ONLY its single literal finish tick. No broadening
    # of product/subscription/path/method/revision/IP comparisons.
    interim = (datetime.fromisoformat(start) + timedelta(minutes=20)).isoformat()
    with scope_binding(d.scope_guard, IP):
        node = d.scope_guard(start, interim)
    when = node.find("when")
    text = when.get("condition")
    suffix = str(d.utc_ticks(interim)) + "L)"
    require(text.endswith(suffix), "literal05_scope_finish_suffix")
    when.set("condition", text[:-len(suffix)] + str(finish) + "L)")
    return node


def candidate(start, end):
    old = predecessor()
    root = c.tree((OLD / "diagnostic.xml").read_bytes())
    inbound = root.find("inbound")
    with scope_binding(d.scope_guard, OLD_IP):
        original_scope = d.scope_guard(old["start"], old["end"])
    require(c.signature(inbound[2]) == c.signature(original_scope), "literal04_scope_exact")
    inbound.remove(inbound[2])
    inbound.insert(2, scope_guard(start, end))
    xml = c.ET.tostring(root, encoding="unicode", short_empty_elements=True)
    with scope_binding(scope_guard, IP):
        c.guard(a.load(w.DIAG / "prepare-capture.json")["normalized_original"], xml, old["nonce"], start, end)
    inbound.remove(inbound[2])
    inbound.insert(2, original_scope)
    require(c.signature(root) == c.signature(c.tree((OLD / "diagnostic.xml").read_bytes())),
            "ONLY_time_IP_changed_nonce_quota_safety_terminal_exact")
    return xml


def exports(formats, policy=None):
    expected = OUT / "diagnostic.xml" if (OUT / "policy-put-intent.json").exists() else OLD / "diagnostic.xml"
    require(policy is None or policy in (OLD / "diagnostic.xml", OUT / "diagnostic.xml"), "only04_or05_policy")
    return _exports(formats, policy or expected)


@contextmanager
def bindings():
    # Reuse04 activation/PUT, original w capture/PATCH/reservation and original
    # PUT/PATCH transports, TLS, no-redirect, exclusive intents and ETag guards.
    edits = [(w, "OUT", OUT), (w, "exports", exports), (w, "review", review),
             (w, "check_package", check_package), (w, "BROWSER", BROWSER),
             (c, "IP", IP), (prior, "OUT", OUT), (prior, "exports", exports),
             (prior, "review", review), (prior, "check_package", check_package),
             (prior.prior, "DIAG", OLD)]
    previous = [(obj, key, getattr(obj, key)) for obj, key, _ in edits]
    try:
        for obj, key, value in edits:
            setattr(obj, key, value)
        yield
    finally:
        for obj, key, value in reversed(previous):
            setattr(obj, key, value)


def prepare(receipt, browser_receipt):
    require(not OUT.exists(), "existing05_package_NEVER_refresh")
    receipts = [f.resolve() for f in (receipt, browser_receipt)]
    require(all(f.is_relative_to(p.rt.ROOT) for f in receipts), "workspace_test_receipts_required")
    tests = [{"path": f.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(f), "kind": kind,
              "counts": test_counts(f, kind)} for f, kind in zip(receipts, ("python", "node"), strict=True)]
    old = predecessor()
    frozen, retained, markers = sources(), history(), p.backend.markers()
    p.require_no_competing_workers(p.backend.workers())
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(minutes=30)
    xml = candidate(start.isoformat(), end.isoformat()).encode()
    body = json.dumps({"properties": {"format": "xml", "value": xml.decode()}}, separators=(",", ":")).encode()
    require(sources() == frozen and history() == retained, "prepare_sources_history_stable")
    p.release.fs.protect(OUT)
    for name, value in {"diagnostic.xml": xml, "policy-put.json": body,
                        **{stage + "-patch.json": value for stage, value in w.BODIES.items()}}.items():
        with (OUT / name).open("xb") as stream:
            stream.write(value)
    p.backend.save(OUT, "prepare-capture.json", {"mode": "RETAINED_ACTUAL04_FULL13_NOT_FRESH_LIVE_READ",
                   "receipt": a.load(PROOF / "fresh-capture.json"),
                   "fresh_before_every_mutation": "MANDATORY_full13_state185_ETag_policy_inheritance"})
    p.backend.save(OUT, "manifest.json", {"at_utc": p.now(), "status": "READY_FOR_PARENT_INDEPENDENT_NATIVE_REVIEW",
        "sources": frozen, "source_sha256": p.release.fs.sha(frozen), "history": retained, "markers": markers,
        "historical_document_bindings": {k: v for k, v in old["sources"].items() if k.startswith("docs/") and k.endswith(".md")},
        "state_owner": a.original_bindings(), "start": start.isoformat(), "end": end.isoformat(), "nonce": old["nonce"],
        "xml_sha256": p.sha(OUT / "diagnostic.xml"), "put_sha256": p.sha(OUT / "policy-put.json"),
        "capture_sha256": p.sha(OUT / "prepare-capture.json"), "tests": tests, "stages": STAGES,
        "url": a.URL, "policy_url": c.POLICY_URL, "patches": {s: c.sha_bytes(b) for s, b in w.BODIES.items()},
        "fixed_text": c.TEXT, "subscription": c.SUBSCRIBER, "IP": IP, "chat_path": c.CHAT_PATH,
        "budget_scope": "NEW_USER_AUTHORIZED_DIAGNOSTIC05_SINGLE_ATTEMPT",
        "historical_scoring_request_count": None, "historical_total_at_most_one_proven": False,
        "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0, "controller_scoring_requests": 0,
        "fresh_live_prepare": False, "cleanup_expiry_independent": True, "cleanup_requires_parent_signal": True,
        "automatic_cleanup": False, "activation_returns": "ONLINE_READY", "nonce_and_counter_unchanged": True,
        "old_quota_warning": "retained3600s_quota_may_have_expired_NO_historical_total_claim",
        "predecessor_full_readonly_sha256": PROOF_SHA, "predecessor_manifest_sha256": MANIFEST04})
    check_package()
    print(json.dumps({"status": "REVIEW_READY_NO_ACTIVATION", "package": OUT.relative_to(p.rt.ROOT).as_posix(),
          "manifest_sha256": p.sha(OUT / "manifest.json"), "start": start.isoformat(), "end": end.isoformat(),
          "tests": tests, "cloud_calls": 0}), flush=True)


def test_counts(path, kind):
    if kind == "python":
        return c.test_counts(path)
    require(kind == "node", "known_test_reporter_only")
    # Node's native JUnit reporter emits testcase children directly, WITHOUT
    # testsuite count attributes. Parse the actual receipt, do not manufacture
    # a wrapper or treat a missing testsuite as zero successful tests.
    root = c.ET.parse(path).getroot()
    counts = {"tests": len(list(root.iter("testcase"))),
              **{key: len(list(root.iter(tag))) for key, tag in
                 (("errors", "error"), ("failures", "failure"), ("skipped", "skipped"))}}
    require(root.tag == "testsuites" and counts["tests"] > 0
            and not any(counts[key] for key in ("errors", "failures", "skipped")), "clean_actual_node_tests")
    return counts


def check_package():
    m = load("manifest.json")
    require(m["sources"] == sources() and m["source_sha256"] == p.release.fs.sha(m["sources"])
            and m["history"] == history(), "immutable05_source_actual_history")
    require(m["state_owner"] == a.original_bindings() and m["state_owner"]["serial"] == 185, "original_state185_exact")
    require(m["stages"] == STAGES and m["IP"] == IP and m["fixed_text"] == c.TEXT
            and m["subscription"] == c.SUBSCRIBER and m["chat_path"] == c.CHAT_PATH
            and m["scoring_budget"] == 1 and m["completion_budget"] == m["retry_budget"] == 0
            and m["historical_scoring_request_count"] is None and m["historical_total_at_most_one_proven"] is False
            and m["budget_scope"] == "NEW_USER_AUTHORIZED_DIAGNOSTIC05_SINGLE_ATTEMPT"
            and m["nonce"] == predecessor()["nonce"], "new05_budget_NOT_unused_historical_budget")
    require([r["kind"] for r in m["tests"]] == ["python", "node"], "both_python_and_browser_tests_required")
    for receipt in m["tests"]:
        path = (p.rt.ROOT / receipt["path"]).resolve()
        require(path.is_relative_to(p.rt.ROOT) and p.sha(path) == receipt["sha256"]
                and test_counts(path, receipt["kind"]) == receipt["counts"], "actual05_tests_exact")
    require(p.sha(OUT / "prepare-capture.json") == m["capture_sha256"], "actual04_retained_capture_exact")
    xml = candidate(m["start"], m["end"]).encode()
    require((OUT / "diagnostic.xml").read_bytes() == xml and c.sha_bytes(xml) == m["xml_sha256"], "fixed05_time_IP_XML_exact")
    body = json.dumps({"properties": {"format": "xml", "value": xml.decode()}}, separators=(",", ":")).encode()
    require((OUT / "policy-put.json").read_bytes() == body and c.sha_bytes(body) == m["put_sha256"], "literal05_PUT_exact")
    for stage, value in w.BODIES.items():
        require((OUT / (stage + "-patch.json")).read_bytes() == value and m["patches"][stage] == c.sha_bytes(value), "literal05_PATCH_exact")
    markers = p.backend.markers()
    require(all(markers.get(k) == v for k, v in m["markers"].items())
            and all(k.startswith(OUT.relative_to(p.rt.ROOT).as_posix() + "/") for k in markers.keys() - m["markers"].keys()),
            "foreign_intent_or_history_drift")
    p.require_no_competing_workers(p.backend.workers())
    return m


def review(stage):
    require(stage in STAGES, "allowlisted05_stage")
    m = check_package()
    r = load("parent-review.json")
    require(r.get("approved") is True and r.get("independent_native_review") is True
            and r.get("stages") == STAGES and r.get("manifest_sha256") == p.sha(OUT / "manifest.json"),
            "actual_parent_review_all_four_scopes")
    transcript = (OUT / r["transcript"]).resolve()
    require(transcript.is_relative_to(OUT.resolve()) and transcript.is_file()
            and p.sha(transcript) == r["transcript_sha256"], "actual_native_transcript_exact")
    at = datetime.fromisoformat(r["at_utc"])
    require(datetime.fromisoformat(m["at_utc"]) <= at <= datetime.now(UTC), "actual05_review_timestamp")
    require(not (OUT / (stage + "-intent.json")).exists(), "existing_intent_NO_RETRY")
    if stage == "offline":
        signal = load("cleanup-authorization.json")
        require(signal.get("parent_says_cleanup") is True
                and signal.get("manifest_sha256") == p.sha(OUT / "manifest.json")
                and signal.get("review_sha256") == p.sha(OUT / "parent-review.json")
                and at <= datetime.fromisoformat(signal["at_utc"]) <= datetime.now(UTC), "explicit_parent_cleanup_signal")
        # NO expiry/review-age/browser-success requirement for cleanup.
    else:
        require(datetime.now(UTC) - at < timedelta(minutes=30), "fresh05_native_review")
        w.check_window(m)
        require(not (OUT / "offline-intent.json").exists(), "cleanup_started_no_activation")
        if stage in ("online", "reserve-browser"):
            prior.compiled04()
    return m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare-review", "activate", "offline", "status", "check"))
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--browser-tests", type=Path)
    args = parser.parse_args()
    try:
        with bindings():
            if args.stage == "prepare-review":
                require(args.tests is not None and args.browser_tests is not None, "actual05_test_receipts_required")
                prepare(args.tests, args.browser_tests)
            elif args.stage == "activate":
                prior.activate()
            elif args.stage == "offline":
                w.execute("offline")
            elif args.stage == "check":
                check_package()
                print(json.dumps({"status": "LOCAL_PACKAGE_EXACT_NOT_REVIEWED_NOT_ACTIVATED", "manifest_sha256": p.sha(OUT / "manifest.json")}))
            else:
                print(json.dumps(prior.status()), flush=True)
        return 0
    except Exception as exc:
        # Never persist arbitrary exception text (could contain HTTP/body/auth).
        result = {"at_utc": p.now(), "stage": args.stage, "type": type(exc).__name__,
                  "details_suppressed": True, "retry_authorized": False, "automatic_cleanup": False}
        if OUT.exists() and args.stage not in ("status", "check"):
            p.backend.save(OUT, args.stage + "-failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", result)
        print(json.dumps(result), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())