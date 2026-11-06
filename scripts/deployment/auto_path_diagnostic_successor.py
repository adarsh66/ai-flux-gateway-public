"""Narrow rollover of the consumed 141022 window; no work occurs on import.

The frozen controller is loaded into a private module namespace. Its functions
retain that namespace, so neither the imported original nor its package changes.
Only prepare's predecessor/render and the local provenance/source checks differ.
"""
import argparse
from datetime import datetime
import importlib.util
from pathlib import Path

from scripts.deployment import auto_path_diagnostic_release as original

ROOT = original.ROOT
PREDECESSOR = ROOT / ".deployment/auto-path-diagnostic-20261029T1410225944396Z"
MANIFEST_SHA = "04c09dfb6c64b50a87f5a1e0ffebeeec01e1ec7232e2bcd82ba27318cc6eef91"
REVIEW_SHA = "abe39e736101942864c162c7bcf9c38f3314145290be3798721b16628d2bc920"
RECEIPT = ROOT / "docs/auto-path-diagnostic-successor-predecessor.json"
TEST = ROOT / "tests/unit/test_auto_path_diagnostic_successor.py"
DOC = ROOT / "docs/auto-path-diagnostic-successor.md"
require = original.require


def _isolated():
    spec = importlib.util.spec_from_file_location(
        "scripts.deployment._auto_path_successor_controller", original.__file__)
    require(spec is not None and spec.loader is not None, "isolated_controller_loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


controller = _isolated()
_sources = controller.sources
_localcheck = controller.localcheck
_guarded = controller.guarded


def _digest(path, expected):
    require(path.is_file() and not path.is_symlink()
            and original.sha(path.read_bytes()) == expected, "consumed_predecessor_hash:" + path.name)


def _time(value):
    at = datetime.fromisoformat(value)
    require(at.utcoffset() == original.timedelta(0), "predecessor_UTC")
    return at


def predecessor():
    """Local-only proof, not an old release/localcheck invocation or replan.

    Pinned verified receipts transitively bind the actual intents and captures.
    The manifest binds all old artifacts/sources. No unknown outcome is adopted.
    """
    d = original
    require(not PREDECESSOR.is_symlink(), "predecessor_not_symlink")
    _digest(PREDECESSOR / "manifest.json", MANIFEST_SHA)
    _digest(PREDECESSOR / "parent-review.json", REVIEW_SHA)
    receipt = d.load(RECEIPT)
    require(receipt["manifest_sha256"] == MANIFEST_SHA
            and receipt["package"] == PREDECESSOR.relative_to(ROOT).as_posix(), "only_actual_consumed_predecessor")
    manifest = d.load(PREDECESSOR / "manifest.json")
    require(manifest["stages"] == list(d.STAGES) and manifest["scope"] == d.SCOPE
            and manifest["historical_scoring_request_count"] is None
            and manifest["scoring_budget"] == 1
            and manifest["retry_budget"] == manifest["completion_budget"] == 0, "old_budget_not_reinterpreted")
    for collection, base in ((manifest["sources"], ROOT), (manifest["artifacts"], PREDECESSOR)):
        for name, digest in collection.items():
            path = (base / name).resolve()
            require(path.is_relative_to(base.resolve()), "predecessor_relative_binding")
            _digest(path, digest)
    for item in (manifest["tests"], *manifest["native_tests"]):
        require(d.test_receipt(ROOT / item["path"]) == item, "retained_actual_test_receipt")
    before = d.load(PREDECESSOR / "fresh-before.json")
    d.initial(before)
    reference = d.c.tree((PREDECESSOR / "restore-global.xml").read_bytes())
    require(d.c.signature(reference) == d.c.signature(d.verify_formats(before["formats"]["global"])),
            "original_global_wire_reference")
    # Prove the entire old candidate is solely the permitted finite guard/key
    # delta of diagnostic06, not merely a matching scope/counter substring.
    prior_revision = d.c.tree((PREDECESSOR / "revision.xml").read_bytes())
    key = d.c.post(prior_revision).find("limit-concurrency").get("key")
    match = d.re.fullmatch(r'@\("auto-diagnostic:([a-f0-9]{32})"\)', key)
    require(match is not None, "known_old_counter")
    expected = d.render(d.policy_values(before["formats"]["global"])["xml"].encode(),
                        d.FIXTURE.read_bytes(), manifest["start"], manifest["end"], match[1])
    require(all((PREDECESSOR / name).read_bytes() == value for name, value in expected.items()),
            "old_candidate_exact_finite_fixture_delta")
    flags = {"install-global": (True, False, False), "install-revision": (True, True, False),
             "online": (True, True, True), "offline": (True, True, False),
             "restore-global": (False, True, False)}
    require(set(receipt["verified_sha256"]) == set(flags), "five_actual_HTTP_stages_not_six")
    previous_time = _time(manifest["at_utc"])
    for stage, state in flags.items():
        _digest(PREDECESSOR / (stage + "-verified.json"), receipt["verified_sha256"][stage])
        verified = d.load(PREDECESSOR / (stage + "-verified.json"))
        intent = d.load(PREDECESSOR / (stage + "-intent.json"))
        after_path = PREDECESSOR / (stage + "-after.json")
        _digest(after_path, verified["after_sha256"])
        _digest(PREDECESSOR / (stage + "-intent.json"), verified["intent_sha256"])
        require(verified["manifest_sha256"] == intent["manifest_sha256"] == MANIFEST_SHA
                and intent["review_sha256"] == REVIEW_SHA and intent["stage"] == stage
                and verified["all13_exact"] is True
                and verified["no_wire"] is intent["no_wire"] is False
                and intent["retries"] == intent["redirects"] == 0
                and intent["body_sha256"] == d.sha(d.stage_body(PREDECESSOR, stage))
                and d.load(PREDECESSOR / (stage + "-result.json")) == {"http_status": 200},
                "actual_HTTP200_verified_no_unknown:" + stage)
        d.a.valid_etag(intent["etag"])
        after = d.load(after_path)
        times = [_time(after["started_at_utc"]), _time(after["at_utc"]), _time(verified["at_utc"])]
        require(previous_time <= _time(intent["at_utc"]) <= times[0] <= times[1] <= times[2],
                "actual_stage_time_order:" + stage)
        if stage not in d.CLEANUP:
            require(d.window(manifest["start"], manifest["end"])[0] <= _time(intent["at_utc"])
                    < d.window(manifest["start"], manifest["end"])[1], "old_activation_in_original_window")
        d.guarded(before, after, PREDECESSOR, *state)
        previous_time = times[-1]
    # Reserve began but failed before its intent. This proves no browser claim,
    # NOT that historical scorer traffic globally was zero.
    for name in ("browser-send-intent.json", "reserve-before.json"):
        _digest(PREDECESSOR / name, receipt["reserve_failure_sha256"][name])
    reserve_before = d.load(PREDECESSOR / "reserve-before.json")
    parent_intent = d.load(PREDECESSOR / "browser-send-intent.json")
    d.guarded(before, reserve_before, PREDECESSOR, True, True, True)
    require(parent_intent["manifest_sha256"] == MANIFEST_SHA
            and parent_intent["review_sha256"] == REVIEW_SHA and parent_intent["scope"] == d.SCOPE
            and _time(d.load(PREDECESSOR / "online-verified.json")["at_utc"])
            <= _time(parent_intent["at_utc"]) <= _time(reserve_before["started_at_utc"])
            <= _time(reserve_before["at_utc"])
            <= _time(d.load(PREDECESSOR / "offline-intent.json")["at_utc"]),
            "actual_failed_reserve_full13_time_binding")
    forbidden = ("reserve-intent.json", "reserve-result.json", "reserve-verified.json",
                 "browser-reservation.json", "browser-claim-intent.json", "browser-binding.json")
    require(not any((PREDECESSOR / name).exists() for name in forbidden),
            "known_no_reservation_or_browser_claim_only")
    final = d.load(PREDECESSOR / "restore-global-after.json")
    return before, final, reference


def initial(capture):
    """Accept ONLY this consumed cleanup, never arbitrary semantically safe drift."""
    before, final, reference = predecessor()
    _guarded(before, capture, PREDECESSOR, False, True, False)
    require(capture["baseline"] == final["baseline"], "fresh_exact_completed_cleanup_baseline")
    require(original.c.signature(original.verify_formats(capture["formats"]["global"]))
            == original.c.signature(reference), "fresh_original_global_both_formats")
    for pair in capture["formats"].values():
        for item in pair.values():
            require(item["status"] == 200, "fresh_policy_HTTP200")
            original.a.valid_etag(item["etag"])
    original.a.valid_etag(capture["api_etag"])


def render(global_export, revision, start, end, nonce):
    """Serialize the verified original wire, not a restamped current raw hash."""
    before, _, reference = predecessor()
    require(original.c.signature(original.c.tree(global_export, exported=True))
            == original.c.signature(reference), "render_original_global_semantics")
    require(revision == original.FIXTURE.read_bytes()
            and original.sha(revision) == original.REVISION_SHA, "render_original_diagnostic06_only")
    old_key = original.c.post(original.c.tree((PREDECESSOR / "revision.xml").read_bytes())).find("limit-concurrency").get("key")
    require(old_key != '@("auto-diagnostic:' + nonce + '")', "no_old_counter_reuse")
    # The existing renderer still receives its immutable known export. The
    # current differently serialized export never acquires the old hash.
    payloads = original.render(original.policy_values(before["formats"]["global"])["xml"].encode(),
                               revision, start, end, nonce)
    canonical = original.ET.tostring(reference, encoding="utf-8")
    require(payloads["restore-global.xml"] == canonical, "canonical_original_wire_exact")
    return payloads


def sources():
    frozen = _sources()
    for path in (Path(__file__), TEST, DOC, RECEIPT):
        frozen[path.relative_to(ROOT).as_posix()] = original.sha(path.read_bytes())
    return frozen


def guarded(before, current, folder, global_installed, revision_installed, online):
    # Inherited controller compares revision=false with fresh-before: the OLD
    # installed candidate. Cleanup accepts only that or the NEW exact candidate.
    _guarded(before, current, folder, global_installed, revision_installed, online)


def localcheck(folder):
    manifest = _localcheck(folder)
    require(manifest["historical_scoring_request_count"] is None, "historical_count_unknown")
    owner_path = folder.parent / "auto-path-diagnostic-attempt-owner.json"
    if owner_path.exists():
        owner = original.load(owner_path)
        require(owner["manifest_sha256"] == original.sha((folder / "manifest.json").read_bytes())
                and owner["parent_intent_sha256"] == original.sha((folder / "browser-send-intent.json").read_bytes())
                and owner["scope"] == original.SCOPE, "successor_only_own_shared_owner")
    # Reconstruct and verify artifacts on every localcheck; do not broaden the
    # finite delta merely because somebody could hash an altered artifact.
    revision = original.c.tree((folder / "revision.xml").read_bytes())
    key = original.c.post(revision).find("limit-concurrency").get("key")
    match = original.re.fullmatch(r'@\("auto-diagnostic:([a-f0-9]{32})"\)', key)
    require(match is not None, "successor_counter_shape")
    before = original.load(folder / "fresh-before.json")
    expected = render(original.policy_values(before["formats"]["global"])["xml"].encode(),
                      original.FIXTURE.read_bytes(), manifest["start"], manifest["end"], match[1])
    require(all((folder / name).read_bytes() == value for name, value in expected.items()),
            "successor_exact_finite_fixture_delta")
    return manifest


# Only this private namespace is adapted. All other state-machine, wire,
# last-target ETag, review, preflight, reserve/claim and cleanup code is inherited.
controller.initial = initial
controller.render = render
controller.sources = sources
controller.guarded = guarded
controller.localcheck = localcheck
# Windows spawn must pickle the public, importable frozen wire_child, not a
# function in this intentionally unregistered private module. The writer itself
# is unchanged: exact URLs/bodies, If-Match, one strict open, no retry/redirect.
controller.send_once = original.send_once


def prepare(folder, receipt, capture_fn=controller.collect, clock=controller.now, node_receipts=()):
    # A successor owner is allowed during ITS own reserve/cleanup localchecks,
    # never as a prerequisite to another preparation or a historical zero claim.
    require(not (folder.parent / "auto-path-diagnostic-attempt-owner.json").exists(),
            "attempt_already_consumed")
    return controller.prepare(folder, receipt, capture_fn=capture_fn, clock=clock, node_receipts=node_receipts)


Stages = controller.Stages
ProductionAdapter = controller.ProductionAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "localcheck", "activate", "reserve", "claim", "cleanup"))
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--browser-tests", type=Path)
    parser.add_argument("--proposal-tests", type=Path)
    args = parser.parse_args()
    folder = args.package.resolve()
    require(folder.parent == original.r.rt.HOME.resolve()
            and folder.name.startswith("auto-path-successor-") and folder != PREDECESSOR,
            "separate_new_successor_package_only")
    if args.stage == "prepare":
        require(all(x is not None for x in (args.tests, args.browser_tests, args.proposal_tests)),
                "actual_test_receipts_required")
        prepare(folder, args.tests, node_receipts=(args.browser_tests, args.proposal_tests))
    elif args.stage == "localcheck":
        localcheck(folder)
    elif args.stage in ("activate", "cleanup"):
        getattr(Stages(folder, ProductionAdapter(folder)), args.stage)()
    elif args.stage == "reserve":
        controller.reserve(folder, ProductionAdapter(folder))
    else:
        controller.claim(folder)
    print(original.json.dumps({"status": "COMPLETED_" + args.stage.upper(),
          "manifest_sha256": original.sha((folder / "manifest.json").read_bytes())}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"status":"STOP_RECONCILE_DURABLE_EVIDENCE_NO_RETRY"}', flush=True)
        raise SystemExit(2)