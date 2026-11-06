"""Oct30 fixed-IP successor; import/localcheck are offline, no implicit stages.

All live stages require a later explicit authorization. Parent browser handoff
must run inside run_reviewed_window, whose finally is armed before activation.
"""
import argparse
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import time

from scripts.deployment import auto_path_diagnostic_successor as prior
from scripts.deployment import auto_path_oct30_collector as collector

d = prior.original
ROOT = d.ROOT
IP = "167.103.67.80"
OLD_IP = "167.103.66.248"
DOC = ROOT / "docs/auto-path-diagnostic-oct30.md"
TEST = ROOT / "tests/unit/test_auto_path_diagnostic_oct30.py"
NATIVE = ROOT / "tests/auto_path_oct30.test.mjs"
BROWSER = ROOT / "scripts/deployment/auto_path_oct30_browser.mjs"
BRIDGE = ROOT / "scripts/deployment/auto_path_oct30_render.mjs"
PROPOSAL = ROOT / "scripts/proposals/auto_path_oct30.mjs"
COLLECTOR_TEST = ROOT / "tests/unit/test_auto_path_oct30_collector.py"
COLLECTOR_DOC = ROOT / "docs/auto-path-oct30-collector-adaptation-20261030.md"
MINIMUM_REMAINING = timedelta(minutes=27)
STORAGE = ROOT / ".deployment/storage-firewall-167-103-67-80-20261030"
STORAGE_AUDIT_SHA = "92f2b40369ce793e6f6b3f490e6bf244b1c2415f90f36d332fc16bfc22d777d8"
require = d.require
controller = prior._isolated()
_render = controller.render
_localcheck = controller.localcheck
controller.IP = IP
controller.BRIDGE = BRIDGE
controller.PATH_BROWSER = BROWSER


def storage_transition():
    """Offline pinned whole-account proof; never adopt arbitrary current drift."""
    audit_path = STORAGE / "final-offline-audit.json"
    require(d.sha(audit_path.read_bytes()) == STORAGE_AUDIT_SHA, "approved_storage_audit_hash")
    audit = d.load(audit_path)
    for name, digest in audit["evidence_sha256"].items():
        require(Path(name).name == name and not (STORAGE / name).is_symlink()
            and d.sha((STORAGE / name).read_bytes()) == digest, "approved_storage_evidence:" + name)
    authorization = d.load(STORAGE / "authorization.json")
    result = d.load(STORAGE / "result.json")
    intent = d.load(STORAGE / "wire-intent.json")
    head = d.load(STORAGE / "blob-head.json")
    require(authorization["source"] == "explicit_current_user_message"
        and authorization["scope"] == "one_IP_addition_only_not_Auto_or_deployment"
        and authorization["ip"] == intent["single_ip"] == IP
        and authorization["resource_id"] == intent["resource_id"]
        and intent["method"] == "PATCH" and intent["retry_budget"] == 0
        and intent["durably_exclusive_before_send"] is True
        and result["success"] is audit["success"] is True
        and result["all_other_account_properties_exact"] is True
        and result["metadata_changes"] == {}
        and audit["actual_wire_mutations"] == 1
        and d.load(STORAGE / "wire-response.json")["http_status"] == 200
        and head["method"] == "HEAD" and head["http_status"] == 200,
        "approved_exact_storage_addition_only")
    before = d.load(STORAGE / "before.json")["account"]
    after = deepcopy(before)
    rule = {"value": IP, "action": "Allow"}
    rules = after["properties"]["networkAcls"]["ipRules"]
    require(not any(item["value"] == IP for item in rules), "new_storage_IP_absent_before")
    rules.append(rule)
    require(result["expected_added_rule"] == [rule] and result["actual_ip_rules"] == rules,
        "approved_exact_storage_rule")
    for name in ("independent-after.json", "final-account.json"):
        require(d.load(STORAGE / name)["account"] == after, "whole_account_exact_one_appended_IP")
    return before, after


def state_network(account):
    properties = account["properties"]
    return {key: deepcopy(properties[key]) for key in
        ("allowSharedKeyAccess", "networkAcls", "publicNetworkAccess")}


def initial(capture):
    # Normalize ONLY two proven storage projections in a private COPY, solely
    # for old predecessor validation. The actual new capture is never rewritten.
    before, after = storage_transition()
    _, final, _ = prior.predecessor()
    require(final["storage_sha256"] == d.r.fs.sha(before)
        and final["baseline"]["state_network"] == state_network(before),
        "storage_before_bound_to_consumed_cleanup")
    require(capture["storage_sha256"] == d.r.fs.sha(after)
        and capture["baseline"]["state_network"] == state_network(after),
        "fresh_storage_exact_approved_after")
    normalized = deepcopy(capture)
    normalized["storage_sha256"] = d.r.fs.sha(before)
    normalized["baseline"]["state_network"] = state_network(before)
    prior.initial(normalized)


def render(global_export, revision, start, end, nonce):
    before, _, reference = prior.predecessor()
    require(d.c.signature(d.c.tree(global_export, exported=True)) == d.c.signature(reference),
            "render_original_global_semantics")
    require(revision == d.FIXTURE.read_bytes() and d.sha(revision) == d.REVISION_SHA,
            "render_original_diagnostic06_only")
    old = prior.render(global_export, revision, start, end, nonce)
    fresh = _render(d.policy_values(before["formats"]["global"])["xml"].encode(),
                    revision, start, end, nonce)
    # Independent byte-level proof AFTER the native renderer and Python's full
    # structural/predicate/quota proof. No header/body/safety/restore edits.
    for name in ("global.xml", "revision.xml"):
        require(old[name].count(OLD_IP.encode()) == 1 and IP.encode() not in old[name]
                and fresh[name].count(IP.encode()) == 1 and OLD_IP.encode() not in fresh[name]
                and fresh[name].replace(IP.encode(), OLD_IP.encode(), 1) == old[name],
                "oct30_exact_one_IP_only:" + name)
    require(fresh["restore-global.xml"] == old["restore-global.xml"], "oct30_restore_bytes_unchanged")
    return fresh


def sources():
    # Keep original browser/bridge bindings as well as their new successors.
    frozen = prior.sources()
    for path in (Path(__file__), TEST, DOC, NATIVE, BROWSER, BRIDGE, PROPOSAL,
                 prior.TEST, prior.DOC, prior.RECEIPT, COLLECTOR_TEST, COLLECTOR_DOC):
        frozen[path.relative_to(ROOT).as_posix()] = d.sha(path.read_bytes())
    storage_transition()
    for name in ("final-offline-audit.json", *d.load(STORAGE / "final-offline-audit.json")["evidence_sha256"]):
        path = STORAGE / name
        frozen[path.relative_to(ROOT).as_posix()] = d.sha(path.read_bytes())
    return frozen


def localcheck(folder):
    manifest = _localcheck(folder)
    require(manifest["historical_scoring_request_count"] is None, "historical_count_unknown")
    owner_path = folder.parent / "auto-path-diagnostic-attempt-owner.json"
    if owner_path.exists():
        owner = d.load(owner_path)
        require(owner["manifest_sha256"] == d.sha((folder / "manifest.json").read_bytes())
                and owner["parent_intent_sha256"] == d.sha((folder / "browser-send-intent.json").read_bytes())
                and owner["scope"] == d.SCOPE, "oct30_only_own_shared_owner")
    revision = d.c.tree((folder / "revision.xml").read_bytes())
    key = d.c.post(revision).find("limit-concurrency").get("key")
    match = d.re.fullmatch(r'@\("auto-diagnostic:([a-f0-9]{32})"\)', key)
    require(match is not None, "oct30_counter_shape")
    before = d.load(folder / "fresh-before.json")
    expected = render(d.policy_values(before["formats"]["global"])["xml"].encode(),
                      d.FIXTURE.read_bytes(), manifest["start"], manifest["end"], match[1])
    require(all((folder / name).read_bytes() == value for name, value in expected.items()),
            "oct30_exact_finite_fixture_delta")
    require((folder / "browser-source.js").read_bytes() == controller.browser_source().encode(),
            "oct30_exact_browser_source")
    return manifest


controller.initial = initial
controller.render = render
controller.sources = sources
controller.localcheck = localcheck
controller.send_once = d.send_once  # Public importable unchanged Windows spawn writer.
controller.collect = collector.collect
Stages = controller.Stages
ProductionAdapter = controller.ProductionAdapter


def prepare(folder, receipt, capture_fn=None, clock=controller.now, node_receipts=()):
    require(not (folder.parent / "auto-path-diagnostic-attempt-owner.json").exists(), "attempt_already_consumed")
    require(folder.name.startswith("auto-path-oct30-") and folder != prior.PREDECESSOR,
            "separate_oct30_package_only")
    failure = folder.with_name(folder.name + "-prepare-failure.json")
    require(not failure.exists() and not failure.is_symlink(), "failed_prepare_reconcile_never_replay")
    require(not folder.exists(), "existing_package_never_refresh")
    progress = {"phase": "PREPARE_VALIDATION"}
    def capture():
        value = collector.collect(progress) if capture_fn is None else capture_fn()
        progress["phase"] = "CAPTURE_RETURNED"
        return value
    try:
        return controller.prepare(folder, receipt, capture_fn=capture, clock=clock, node_receipts=node_receipts)
    except Exception as error:
        collector.retain_prepare_failure(folder, error, progress)
        raise


def run_reviewed_window(folder, adapter, parent_browser, clock=controller.now):
    """Explicit parent integration API, NOT called by import/prepare/CLI.

    Source/native/browser readiness must precede freeze. Keep the inherited
    30-minute cap and all full reads. Refuse a late start; never extend a window.
    The callback receives the real durable binding, never a fixture/approval.
    """
    require(callable(parent_browser), "explicit_parent_browser_handoff_required")
    manifest = controller.review(folder, "install-global", clock)
    controller.browser_preflight(folder, clock)
    require(controller.window(manifest["start"], manifest["end"])[1] - clock() >= MINIMUM_REMAINING,
            "insufficient_window_for_full_reads_NO_ACTIVATION")
    d.exclusive(folder / "parent-window-intent.json", {
        "at_utc": clock().isoformat(), "manifest_sha256": d.sha((folder / "manifest.json").read_bytes()),
        "review_sha256": d.sha((folder / "parent-review.json").read_bytes()),
        "finally_armed_before_online": True, "attempts": 1})
    stages = Stages(folder, adapter, clock)
    try:
        stages.activate()
        controller.reserve(folder, adapter, clock)
        return parent_browser(controller.claim(folder, clock))
    finally:
        if (folder / "install-global-intent.json").exists():
            consumed = any((folder / (s + "-intent.json")).exists() for s in d.CLEANUP)
            if not consumed:
                stages.cleanup()
            else:
                # Inherited activation supervisor may already have cleaned up.
                # Never replay a partial/ambiguous cleanup, even after expiry.
                require(all((folder / (s + "-verified.json")).exists() for s in d.CLEANUP),
                        "UNRESOLVED_STOP_FRESH_READS_NO_REPLAY")
                for stage in d.CLEANUP:
                    verified = d.load(folder / (stage + "-verified.json"))
                    require(verified["all13_exact"] is True
                            and verified["manifest_sha256"] == d.sha((folder / "manifest.json").read_bytes())
                            and verified["intent_sha256"] == d.sha((folder / (stage + "-intent.json")).read_bytes())
                            and verified["after_sha256"] == d.sha((folder / (stage + "-after.json")).read_bytes()),
                            "UNRESOLVED_STOP_FRESH_READS_NO_REPLAY")


def file_browser_handoff(folder, binding, clock=controller.now, monotonic=time.monotonic,
                         wait=None):
    """Signal the real parent without pretending that a browser ran.

    Use a separately launched reviewed controller process, not a blocking parent
    tool call. Parent reads this request and executes the real browser tool while
    this bounded callback is alive. Missing/late/error results raise into finally.
    No CLI activation entrypoint is exposed. No approval/result is manufactured.
    """
    require(wait is None or callable(wait), "handoff_wait_callable")
    wait = wait or __import__("threading").Event().wait
    binding_path = folder / "browser-binding.json"
    require(d.load(binding_path) == binding, "handoff_actual_durable_binding")
    manifest_sha = d.sha((folder / "manifest.json").read_bytes())
    binding_sha = d.sha(binding_path.read_bytes())
    require(binding["manifest_sha256"] == manifest_sha, "handoff_manifest_binding")
    response = folder / "parent-browser-response.json"
    require(not response.exists() and not response.is_symlink(), "handoff_no_preexisting_response")
    # The binding expires in 30 seconds; retain time for the actual 20s browser
    # operation. This request is coordination only, never browser/preflight proof.
    deadline = min(controller.window(d.load(folder / "manifest.json")["start"],
                                    d.load(folder / "manifest.json")["end"])[1],
                   d.datetime.fromisoformat(binding["verified_at_utc"]) + timedelta(seconds=30))
    remaining = (deadline - clock()).total_seconds()
    require(20 <= remaining <= 30, "handoff_binding_fresh_before_signal")
    requested_at = clock()
    d.exclusive(folder / "parent-browser-request.json", {
        "at_utc": requested_at.isoformat(), "deadline_utc": deadline.isoformat(),
        "manifest_sha256": manifest_sha, "binding_sha256": binding_sha,
        "nonce": binding["nonce"], "coordination_only_not_browser_evidence": True})
    stop = monotonic() + remaining
    while monotonic() < stop and clock() < deadline:
        if response.exists():
            require(not response.is_symlink(), "handoff_response_not_symlink")
            value = d.load(response)
            require(value["manifest_sha256"] == manifest_sha
                    and value["binding_sha256"] == binding_sha
                    and value["nonce"] == binding["nonce"]
                    and value["parent_observed"] is True
                    and value["fixture"] is False, "handoff_parent_response_binding")
            at = d.datetime.fromisoformat(value["at_utc"])
            require(requested_at <= at <= clock() < deadline,
                    "handoff_response_time")
            evidence = (folder / value["evidence"]).resolve()
            require(evidence.is_relative_to(folder.resolve()) and evidence.is_file()
                    and not (folder / value["evidence"]).is_symlink()
                    and d.sha(evidence.read_bytes()) == value["evidence_sha256"],
                    "handoff_actual_parent_evidence")
            require(value["status"] == "COMPLETED", "handoff_browser_failed_cleanup_required")
            return value  # Attestation only; caller/reviewer still inspects actual evidence.
        wait(min(0.1, max(0, stop - monotonic())))
    raise RuntimeError("handoff_timeout_NO_RETRY_PARENT_FINALLY_CLEANUP")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "localcheck", "cleanup"))
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--browser-tests", type=Path)
    parser.add_argument("--proposal-tests", type=Path)
    args = parser.parse_args()
    folder = args.package.resolve()
    require(folder.parent == d.r.rt.HOME.resolve() and folder.name.startswith("auto-path-oct30-"),
            "separate_oct30_package_only")
    if args.stage == "prepare":
        require(all(x is not None for x in (args.tests, args.browser_tests, args.proposal_tests)),
                "actual_test_receipts_required")
        prepare(folder, args.tests, node_receipts=(args.browser_tests, args.proposal_tests))
    elif args.stage == "localcheck":
        localcheck(folder)
    else:
        Stages(folder, ProductionAdapter(folder)).cleanup()
    print(d.json.dumps({"status": "COMPLETED_" + args.stage.upper(),
                        "manifest_sha256": d.sha((folder / "manifest.json").read_bytes())}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"status":"STOP_RECONCILE_DURABLE_EVIDENCE_NO_RETRY"}', flush=True)
        raise SystemExit(2)