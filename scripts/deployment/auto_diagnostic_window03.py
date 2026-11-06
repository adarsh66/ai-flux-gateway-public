"""Fixed diagnostic03 adapter; offline review assembly, then reviewed PATCH stages.

No policy PUT, time renewal, arbitrary XML/window, build, or scoring entrypoint.
The original window controller remains unchanged. Its complete fresh execution
captures, exclusive intents, once callbacks, and expiry-independent cleanup run
under narrowly scoped bindings. Historical diagnostic02 baseline stays in use.
"""
import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path

from scripts.deployment import auto_diagnostic_window as w

c, d, p, a = w.c, w.d, w.p, w.a
require = w.require
DIAG = a.HOME / "scoring-diagnostic03"
OUT = a.HOME / "scoring-window03"
START = "2026-10-29T07:44:18+00:00"
END = "2026-10-29T08:04:18+00:00"
MANIFEST_SHA = "b3f46d3e4a68976f6b482c2468d01b3040fcfac13ae7f11bfc0572385c825496"
XML_SHA = "8b62af308a7d497f9844e6eb217cc3222afb7dd912b664edac8cbeaa6385bb20"
# Literal actual successful PUT and full protected readback, not a replacement
# verifier or fabricated supplemental receipt. Every byte remains immutable.
PROOF = {
    "manifest.json": MANIFEST_SHA,
    "diagnostic.xml": XML_SHA,
    "policy-put.json": "8ec7470023d040095965bd0f881ed884f196acb60207234d2ebe337a153d3a74",
    "policy-put-intent.json": "7e6acf25a395c9ba16f6df75aab006261f4dd2cea6c4668f195c7982bc2f33c8",
    "policy-put-result.json": "1c8bd22334c857dd8ecfaad9d4db2ff160110f1674d79a51338204453be1afc2",
    "policy-put-after-capture.json": "56e74653b37d1fcff92358b0dc8621aac445c4bfa72ea1f26e680675f0fb6f31",
    "policy-put-verification.json": "51c1ec6fa6d53700518b235516d6d4c5dd4bd3478b8e938620350d04d4a3ddad",
    "policy-put-parent-review.json": "6dd7b0e60919544715641e676f9558054f0d639320a8867eefb5df37f3760a58",
    "policy-put-native-review-summary.md": "578052321612483c1ff99dd1bfbedd5c261e10a96fbb2b96788417b8b7e178e6",
}
_compile02, _history02, _exports02 = w.check_compilation, w.history, w.exports


def check_compilation():
    require(all(p.sha(DIAG / name) == digest for name, digest in PROOF.items()),
            "literal_diagnostic03_actual_PUT_proof_exact")
    m = a.load(DIAG / "manifest.json")
    intent = a.load(DIAG / "policy-put-intent.json")
    result = a.load(DIAG / "policy-put-result.json")
    verified = a.load(DIAG / "policy-put-verification.json")
    after = a.load(DIAG / "policy-put-after-capture.json")
    require((m["start"], m["end"], m["xml_sha256"]) == (START, END, XML_SHA),
            "fixed03_XML_and_window_no_renewal")
    require(intent["method"] == "PUT" and intent["url"] == c.POLICY_URL
            and intent["attempt_budget"] == 1 and intent["retries"] == intent["redirects"] == 0
            and intent["manifest_sha256"] == MANIFEST_SHA
            and intent["body_sha256"] == m["put_sha256"] == PROOF["policy-put.json"]
            and intent["review_sha256"] == PROOF["policy-put-parent-review.json"]
            and result["http_status"] == verified["http_status"] == 200 and result["no_retry"] is True,
            "actual03_compiler_PUT_200_binding")
    require(all(after[key] is True for key in ("all13_supplemental_exact", "exact_both_formats", "inherited_exact"))
            and all(verified[key] is True for key in ("all13_supplemental_exact", "exact_both_formats"))
            and after["revision2_online"] is verified["revision2_online"] is False
            and after["revision2_current"] is verified["revision2_current"] is False
            and after["state_owner"] == m["state_owner"] == a.original_bindings()
            and after["state_owner"]["serial"] == 185
            and verified["controller_scoring_requests"] == verified["completion_requests"] == 0,
            "actual03_full13_policy_offline_noncurrent_state185")
    require(datetime.fromisoformat(intent["at_utc"]) < datetime.fromisoformat(result["at_utc"])
            <= datetime.fromisoformat(after["at_utc"]) <= datetime.fromisoformat(verified["at_utc"]),
            "actual03_PUT_then_readback_order")
    current = w.sources()
    require(all(current.get(name) == digest for name, digest in m["sources"].items()),
            "all_preexisting03_sources_unchanged_new_adapter_separately_bound")
    old = _compile02()
    require(m["nonce"] == old["nonce"], "original_nonce_and_counter_unchanged")
    with d.bindings():
        c.guard(a.load(w.DIAG / "prepare-capture.json")["normalized_original"],
                (DIAG / "diagnostic.xml").read_bytes(), m["nonce"], START, END)
    return m


def history():
    return {**_history02(), **{f.relative_to(p.rt.ROOT).as_posix(): p.sha(f)
            for f in sorted(DIAG.iterdir()) if f.is_file()}}


def exports(formats, policy=None):
    require(policy is None or policy == DIAG / "diagnostic.xml", "only_fixed03_export_policy")
    return _exports02(formats, DIAG / "diagnostic.xml")


@contextmanager
def bindings():
    # Do NOT rebind w.DIAG: capture needs its original baseline/inheritance;
    # do NOT rebind wire/once/review/capture or the cleanup/window guards.
    replacement = {"OUT": OUT, "check_compilation": check_compilation,
                   "history": history, "exports": exports}
    previous = {key: getattr(w, key) for key in replacement}
    try:
        for key, value in replacement.items():
            setattr(w, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(w, key, value)


def prepare_review(receipt):
    """Retained proof only. Fresh complete live gates remain in w.execute."""
    require(not OUT.exists(), "existing_window03_package_reconcile_only")
    receipt = receipt.resolve()
    require(receipt.is_relative_to(p.rt.ROOT), "workspace_test_receipt")
    counts = c.test_counts(receipt)
    diagnostic = check_compilation()
    frozen, retained = w.sources(), history()
    owner = a.original_bindings()
    p.release.fs.protect(OUT)
    for stage, body in w.BODIES.items():
        with (OUT / (stage + "-patch.json")).open("xb") as stream:
            stream.write(body)
    w.save("prepare-capture.json", {"mode": "RETAINED_GET_EVIDENCE_NOT_FRESH_LIVE_PREPARE",
           "receipt": a.load(DIAG / "policy-put-after-capture.json"),
           "fresh_before_every_mutation": "MANDATORY_full13_state_ETag_policy_inheritance"})
    require(w.sources() == frozen and history() == retained, "assembly_sources_and_history_stable")
    w.save("manifest.json", {"at_utc": p.now(),
        "status": "REVIEW_READY_RETAINED_PROOF_FRESH_EXECUTION_GATES_REQUIRED",
        "sources": frozen, "source_sha256": p.release.fs.sha(frozen),
        # Legacy field name is required by unchanged w.check_package; contains
        # BOTH immutable diagnostic02 AND actual diagnostic03 histories.
        "diagnostic02": retained, "diagnostic03_manifest_sha256": MANIFEST_SHA,
        "diagnostic03_xml_sha256": XML_SHA, "diagnostic03_proof": PROOF,
        "state_owner": owner, "start": diagnostic["start"], "end": diagnostic["end"],
        "url": a.URL, "patches": {stage: c.sha_bytes(body) for stage, body in w.BODIES.items()},
        "capture_sha256": p.sha(OUT / "prepare-capture.json"), "markers": p.backend.markers(),
        "tests": {"path": receipt.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(receipt), "counts": counts},
        "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0, "controller_scoring_requests": 0,
        "fixed_text": c.TEXT, "subscription": c.SUBSCRIBER, "IP": c.IP, "chat_path": c.CHAT_PATH,
        "cleanup_expiry_independent": True, "fresh_live_prepare": False,
        "path_uncertainty": "may_403_safe_no_global_or_base_bypass"})
    print(json.dumps({"package": OUT.relative_to(p.rt.ROOT).as_posix(),
          "manifest_sha256": p.sha(OUT / "manifest.json"), "adapter_sha256": p.sha(Path(__file__)),
          "start": START, "end": END, "tests": counts, "fresh_live_prepare": False}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare-review", "online", "reserve-browser", "offline"))
    parser.add_argument("--tests", type=Path)
    args = parser.parse_args()
    try:
        with bindings():
            if args.stage == "prepare-review":
                require(args.tests is not None, "actual_tests_required")
                prepare_review(args.tests)
            elif args.stage == "reserve-browser":
                w.reserve_browser()
            else:
                w.execute(args.stage)
        return 0
    except Exception as exc:
        result = {"at_utc": p.now(), "stage": args.stage, "type": type(exc).__name__,
                  "guard": str(exc) if isinstance(exc, RuntimeError) else "details_suppressed", "retry_authorized": False}
        if OUT.exists():
            p.backend.save(OUT, args.stage + "-failure-" + datetime.now(UTC).strftime("%H%M%S%f") + ".json", result)
        print(json.dumps(result), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())