"""Source-only successor of the exact latest consumed Oct30 attempt.

No collection, preparation, window, approval or mutation occurs on import.
Historical proof is checked by its frozen mapping, never a live source glob.
"""
from copy import deepcopy
from pathlib import Path
import sys

from scripts.deployment import auto_path_diagnostic_oct30 as old
from scripts.deployment import auto_path_oct30_collector as tools

d = old.d
ROOT = d.ROOT
PREDECESSOR = ROOT / ".deployment/auto-path-oct30-bounded-native-20261030T045805020273Z"
MANIFEST_SHA = "28878b99397dbd60a7c72c74dcbca2f262475ac6766f591bb22ec075ba162dfa"
SOURCE_SHA = "40cc80615cd230cbdc637b5cdde68fef8cfbdc7f317771007bb560d3ebdbba1f"
INVESTIGATION = ROOT / ".deployment/oct30-consumed-investigation-readonly-20261030"
AUDIT_SHA = "297dd72bab1795826889f53a76341b0b22c34ebcffde0d9cc162b123843b3073"
CAPTURE_SHA = "b0e7a728b0201b54b7bbc2c8f41ebd1a990cf9b6b8c720ddca4170aeb714dbc0"
RESULT_SHA = "ae7748bd1be5d13a8027cd5ca03ab610d7873743d8aa6dba8161fe2624c8e235"
PARENT_RESULT = ROOT / ".deployment/oct30-bounded-native-20261030/run-process-result.json"
PARENT_SHA = "c3977999e732180d0d3c984939b6760dc6509e1da015cead58b5fc6ef291a4f1"
PREFIX = "auto-path-oct30-successor-"
require = d.require


def checked_file(base, name, digest=None):
    relative = Path(name)
    require(not relative.is_absolute() and ".." not in relative.parts, "relative_evidence_only")
    path = base / relative
    require(path.is_file() and path.resolve().is_relative_to(base.resolve())
            and not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)),
            "no_link_or_escape_evidence")
    if digest is not None:
        require(d.sha(path.read_bytes()) == digest, "pinned_evidence_hash:" + relative.as_posix())
    return path


def at(value):
    result = d.datetime.fromisoformat(value)
    require(result.utcoffset() == d.timedelta(0), "evidence_UTC_only")
    return result


def predecessor():
    """Four verified stages; online HTTP200/postread UNKNOWN, NOT verified.

    Exact directory inventory pins every actual before/intent/result/after,
    transcript and failure marker. Extra online/reserve proof cannot be adopted.
    This never invokes an old entrypoint/localcheck or collects cloud state.
    """
    checked_file(INVESTIGATION, "retained-audit.json", AUDIT_SHA)
    audit = d.load(INVESTIGATION / "retained-audit.json")
    inventory = audit["consumed_package_file_sha256"]
    require({p.name for p in PREDECESSOR.iterdir()} == set(inventory), "exact_consumed_inventory")
    for name, digest in inventory.items():
        checked_file(PREDECESSOR, name, digest)
    checked_file(PREDECESSOR, "manifest.json", MANIFEST_SHA)
    manifest = d.load(PREDECESSOR / "manifest.json")
    require(len(manifest["sources"]) == 210 and d.sha(d.encode(manifest["sources"])) == SOURCE_SHA,
            "exact_frozen_210_mapping")
    for name, digest in manifest["sources"].items():
        checked_file(ROOT, name, digest)
    require(len(manifest["artifacts"]) == 6, "six_original_artifacts")
    for name, digest in manifest["artifacts"].items():
        checked_file(PREDECESSOR, name, digest)
    for receipt in (manifest["tests"], *manifest["native_tests"]):
        require(d.test_receipt(checked_file(ROOT, receipt["path"], receipt["sha256"])) == receipt,
                "actual_retained_receipt")
    require(manifest["stages"] == list(d.STAGES) and manifest["scope"] == d.SCOPE
            and manifest["scoring_budget"] == 1 and manifest["historical_scoring_request_count"] is None
            and manifest["retry_budget"] == manifest["completion_budget"] == 0
            and manifest["cleanup_expiry_independent"] is True, "unchanged_budgets")
    start, end = d.window(manifest["start"], manifest["end"])
    review = d.load(PREDECESSOR / "parent-review.json")
    review_sha = inventory["parent-review.json"]
    require(review["approved"] is review["independent_native_review"] is review["parent_says_cleanup"] is True
            and review["manifest_sha256"] == MANIFEST_SHA and review["stages"] == list(d.STAGES),
            "actual_all_six_review")
    checked_file(PREDECESSOR, review["transcript"], review["transcript_sha256"])
    preflight = d.load(PREDECESSOR / "browser-preflight.json")
    checked_file(PREDECESSOR, preflight["evidence"], preflight["evidence_sha256"])
    require(preflight["parent_observed"] is preflight["safe_events_observed"] is True
            and preflight["fixture"] is preflight["send_invoked"] is False
            and preflight["manifest_sha256"] == MANIFEST_SHA
            and preflight["source_sha256"] == inventory["browser-source.js"], "actual_old_safe_preflight")
    parent = d.load(PREDECESSOR / "parent-window-intent.json")
    activation = d.load(PREDECESSOR / "activation-intent.json")
    for item in (parent, activation):
        require(item["manifest_sha256"] == MANIFEST_SHA and item["review_sha256"] == review_sha
                and item["attempts"] == 1, "actual_parent_activation_binding")
    require(parent["finally_armed_before_online"] is True
            and at(manifest["at_utc"]) <= at(review["at_utc"]) <= at(parent["at_utc"])
            <= at(activation["at_utc"]) <= end - old.MINIMUM_REMAINING,
            "actual_review_parent_budget_order")
    before = d.load(PREDECESSOR / "fresh-before.json")
    old.initial(before)  # The old guard remains correct for ITS original before.
    reference = d.c.tree((PREDECESSOR / "restore-global.xml").read_bytes())
    d.verify_formats(before["formats"]["global"], (PREDECESSOR / "restore-global.xml").read_bytes())
    require((PREDECESSOR / "restore-global.xml").read_bytes() ==
            old.prior.render(d.policy_values(before["formats"]["global"])["xml"].encode(),
                d.FIXTURE.read_bytes(), manifest["start"], manifest["end"], "0" * 32)["restore-global.xml"],
            "independent_original_global_wire")
    nonce = counter((PREDECESSOR / "revision.xml").read_bytes())
    expected = old.render(d.policy_values(before["formats"]["global"])["xml"].encode(),
                          d.FIXTURE.read_bytes(), manifest["start"], manifest["end"], nonce)
    require(all((PREDECESSOR / name).read_bytes() == value for name, value in expected.items()),
            "latest_candidate_exact_original_fixture_delta")
    states = {"install-global": (True, False, False), "install-revision": (True, True, False),
              "online": (True, True, False), "offline": (True, True, True),
              "restore-global": (True, True, False)}
    after_states = {"install-global": (True, False, False), "install-revision": (True, True, False),
                    "offline": (True, True, False), "restore-global": (False, True, False)}
    previous = at(activation["at_utc"])
    for stage, before_state in states.items():
        observed = d.load(PREDECESSOR / (stage + "-before.json"))
        # install-global's before has no installed new policy yet.
        state = (False, False, False) if stage == "install-global" else before_state
        if stage == "install-revision":
            state = (True, False, False)
        d.guarded(before, observed, PREDECESSOR, *state)
        intent = d.load(PREDECESSOR / (stage + "-intent.json"))
        require(previous <= at(observed["started_at_utc"]) <= at(observed["at_utc"])
                <= at(intent["at_utc"])
                and at(intent["at_utc"]) - at(observed["at_utc"]) < d.timedelta(seconds=30),
                "actual_before_intent_order:" + stage)
        require(intent["manifest_sha256"] == MANIFEST_SHA and intent["review_sha256"] == review_sha
                and intent["stage"] == stage and intent["no_wire"] is False
                and intent["retries"] == intent["redirects"] == 0
                and intent["body_sha256"] == d.sha(d.stage_body(PREDECESSOR, stage))
                and d.load(PREDECESSOR / (stage + "-result.json")) == {"http_status": 200},
                "actual_HTTP200_intent_body:" + stage)
        d.a.valid_etag(intent["etag"])
        if stage not in d.CLEANUP:
            require(start <= at(intent["at_utc"]) < end - d.timedelta(seconds=90), "actual_window_budget")
        if stage == "online":
            previous = at(intent["at_utc"])
            continue  # NEVER create or infer the missing online proof.
        proof = d.load(PREDECESSOR / (stage + "-verified.json"))
        after = d.load(PREDECESSOR / (stage + "-after.json"))
        require(proof["manifest_sha256"] == MANIFEST_SHA and proof["all13_exact"] is True
                and proof["no_wire"] is False
                and proof["intent_sha256"] == inventory[stage + "-intent.json"]
                and proof["after_sha256"] == inventory[stage + "-after.json"]
                and at(intent["at_utc"]) <= at(after["started_at_utc"]) <= at(after["at_utc"])
                <= at(proof["at_utc"]), "actual_verified_hash_time_chain:" + stage)
        d.guarded(before, after, PREDECESSOR, *after_states[stage])
        previous = at(proof["at_utc"])
    checked_file(ROOT, PARENT_RESULT.relative_to(ROOT), PARENT_SHA)
    failure = d.load(PARENT_RESULT)
    require(failure == audit["original_parent_result"] and failure["pid"] == 29564
            and failure["manifest_sha256"] == MANIFEST_SHA and failure["exception_type"] == "TimeoutError"
            and failure["attempts"] == 1 and at(failure["at_utc"]) >= previous,
            "actual_online_postread_TimeoutError_UNKNOWN")
    marker = d.load(PREDECESSOR / "online-cleanup-required.json")
    require(marker == {"automatic_replay": False, "independent_cleanup_after_expiry": True,
            "offline_then_restore_global": True, "outcome": "UNKNOWN_UNTIL_FRESH_READ"}, "actual_unknown_marker")
    cleanup = d.load(PREDECESSOR / "activation-cleanup.json")
    require(cleanup["status"] == "OFFLINE_AND_ORIGINAL_GLOBAL_INDEPENDENTLY_VERIFIED"
            and cleanup["automatic_replay"] is False
            and at(d.load(PREDECESSOR / "online-intent.json")["at_utc"]) <= at(cleanup["at_utc"])
            <= at(d.load(PREDECESSOR / "offline-before.json")["started_at_utc"]), "actual_cleanup_not_replayed")
    return before, d.load(PREDECESSOR / "restore-global-after.json"), reference


def counter(wire):
    gate = d.c.post(d.c.tree(wire)).find("limit-concurrency")
    match = d.re.fullmatch(r'@\("auto-diagnostic:([a-f0-9]{32})"\)', gate.get("key"))
    require(match is not None and gate[0].get("counter-key") == gate.get("key"), "exact_counter_shape")
    return match[1]


def counter_files():
    home = ROOT / ".deployment"
    # A new own candidate is not a consumed counter or a source dependency of
    # itself. It is independently reconstructed by localcheck instead.
    return sorted(path for path in set(home.glob("**/revision.xml")) | set(home.glob("**/diagnostic.xml"))
                  if not any(part.startswith(PREFIX) for part in path.relative_to(home).parts))


def initial(capture):
    before, final, reference = predecessor()
    d.guarded(before, capture, PREDECESSOR, False, True, False)
    require(len(capture["baseline"]) == 13 and len(capture["baseline"]["settings_hashes"]) == 4
            and capture["baseline"] == final["baseline"] and capture["project"]["serial"] == 185
            and capture["runtime"]["serial"] == 111, "exact_latest_cleanup_full13")
    for kind, name in (("global", "restore-global.xml"), ("revision", "revision.xml")):
        d.verify_formats(capture["formats"][kind], (PREDECESSOR / name).read_bytes())
        for item in capture["formats"][kind].values():
            require(item["status"] == 200, "actual_policy_HTTP200")
            d.a.valid_etag(item["etag"])
    require(d.c.signature(d.verify_formats(capture["formats"]["global"])) == d.c.signature(reference),
            "original_global_both_formats_independent_rawhash")
    d.a.valid_etag(capture["api_etag"])
    _, approved = old.storage_transition()
    require(capture["storage_sha256"] == d.r.fs.sha(approved)
            and capture["baseline"]["state_network"] == old.state_network(approved), "exact_approved_five_IP")


def investigation_baseline():
    """Offline regression input only; NOT a future preparation capture."""
    checked_file(INVESTIGATION, "capture.json", CAPTURE_SHA)
    checked_file(INVESTIGATION, "result.json", RESULT_SHA)
    capture = d.load(INVESTIGATION / "capture.json")
    result = d.load(INVESTIGATION / "result.json")
    require(result["capture_sha256"] == CAPTURE_SHA and result["full13_exact"] is True
            and result["shared_owner_absent"] is True, "actual_investigation_PASS")
    initial(capture)
    return capture


def render(global_export, revision, start, end, nonce):
    predecessor()
    for path in counter_files():
        checked_file(ROOT, path.relative_to(ROOT))
        require(nonce.encode() not in path.read_bytes(), "no_consumed_counter_reuse")
    return old.render(global_export, revision, start, end, nonce)


controller = old.prior._isolated()
controller.IP, controller.BRIDGE, controller.PATH_BROWSER = old.IP, old.BRIDGE, old.BROWSER
_localcheck = controller.localcheck


def sources():
    predecessor()
    frozen = old.sources()
    for path in (Path(__file__), ROOT / "scripts/deployment/auto_path_oct30_successor_reads.py",
                 ROOT / "tests/unit/test_auto_path_oct30_successor.py",
                 ROOT / "docs/auto-path-oct30-successor.md", *counter_files()):
        frozen[path.relative_to(ROOT).as_posix()] = d.sha(path.read_bytes())
    for base, names in ((PREDECESSOR, d.load(INVESTIGATION / "retained-audit.json")["consumed_package_file_sha256"]),
                        (INVESTIGATION, ("retained-audit.json", "capture.json", "result.json"))):
        for name in names:
            path = base / name
            frozen[path.relative_to(ROOT).as_posix()] = d.sha(path.read_bytes())
    frozen[PARENT_RESULT.relative_to(ROOT).as_posix()] = PARENT_SHA
    return frozen


def localcheck(folder):
    manifest = _localcheck(folder)
    require(folder.name.startswith(PREFIX) and folder != PREDECESSOR, "separate_latest_successor_only")
    require(manifest["historical_scoring_request_count"] is None, "historical_count_UNKNOWN")
    owner_path = folder.parent / "auto-path-diagnostic-attempt-owner.json"
    if owner_path.exists():
        owner = d.load(owner_path)
        require(owner["manifest_sha256"] == d.sha((folder / "manifest.json").read_bytes())
                and owner["parent_intent_sha256"] == d.sha((folder / "browser-send-intent.json").read_bytes())
                and owner["scope"] == d.SCOPE, "only_own_exact_owner")
    nonce = counter((folder / "revision.xml").read_bytes())
    before = d.load(folder / "fresh-before.json")
    expected = render(d.policy_values(before["formats"]["global"])["xml"].encode(),
                      d.FIXTURE.read_bytes(), manifest["start"], manifest["end"], nonce)
    require(all((folder / name).read_bytes() == data for name, data in expected.items()), "exact_new_fixture_delta")
    require((folder / "browser-source.js").read_bytes() == controller.browser_source().encode(), "exact_browser_source")
    return manifest


controller.initial, controller.render = initial, render
controller.sources, controller.localcheck = sources, localcheck
controller.send_once = d.send_once  # Unchanged importable Windows one-open writer.

# Private copies of the EXISTING bounded parent and handoff, not a second CLI.
namespace = {**vars(old), "controller": controller, "localcheck": localcheck}
file_browser_handoff = tools.bind(old.file_browser_handoff, namespace)


def _wire_private_runtime():
    from scripts.deployment import auto_path_oct30_successor_reads as reads
    global Stages, ProductionAdapter
    Stages, ProductionAdapter = reads.Stages, reads.ProductionAdapter
    controller.Stages, controller.ProductionAdapter = Stages, ProductionAdapter
    for name in ("activate", "cleanup"):
        setattr(Stages, name, tools.bind(getattr(d.Stages, name), vars(controller)))
    Stages._execute = tools.bind(d.Stages.execute, vars(controller))
    controller.collect = reads.collect
    namespace.update(Stages=Stages, ProductionAdapter=ProductionAdapter, collector=reads)


_wire_private_runtime()
_run_reviewed_window = tools.bind(old.run_reviewed_window, namespace)


def run_reviewed_window(folder, adapter, parent_browser, clock=controller.now):
    from scripts.deployment import auto_path_oct30_successor_reads as reads
    with reads.diagnostics(folder, "install-global"):
        return _run_reviewed_window(folder, adapter, parent_browser, clock)


def prepare(folder, receipt, capture_fn=None, clock=controller.now, node_receipts=()):
    """LATER explicit gate only; source tests do not call this function."""
    from scripts.deployment import auto_path_oct30_successor_reads as reads
    require(folder.name.startswith(PREFIX) and folder.parent == d.r.rt.HOME.resolve()
            and not folder.exists() and not folder.is_symlink(), "fresh_separate_successor_package")
    require(not (folder.parent / "auto-path-diagnostic-attempt-owner.json").exists(), "attempt_already_consumed")
    predecessor()
    d.r.gate.require_no_competing_workers(d.r.persistence.backend.workers())
    with reads.diagnostics(folder, "prepare"):
        return tools.bind(old.prepare, namespace)(folder, receipt, capture_fn, clock, node_receipts)


def parent_cli():
    """Bind the unchanged bounded parent CLI to this successor privately."""
    from scripts.deployment import auto_path_oct30_parent as parent
    private = tools.copy_module(parent)
    private.s = sys.modules[__name__]
    for name in ("checked_package", "run_parent", "main"):
        setattr(private, name, tools.bind(getattr(parent, name), vars(private)))
    return private


if __name__ == "__main__":
    try:
        parent_cli().main()
    except Exception:
        print('{"status":"STOP_RECONCILE_DURABLE_EVIDENCE_NO_RETRY"}', flush=True)
        raise SystemExit(2)