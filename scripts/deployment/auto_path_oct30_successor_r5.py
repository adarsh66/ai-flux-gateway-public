"""Isolated r5: protected original13 plus exact known9; no action on import."""
from copy import deepcopy
from pathlib import Path

from scripts.deployment import auto_path_oct30_successor_r4 as r4
from scripts.deployment import auto_path_oct30_successor_r5_reads as reads

d, tools = r4.d, r4.tools
PREFIX = "auto-path-oct30-successor-r5-"
IP = "167.103.66.248"
BRIDGE = Path(__file__).with_name("auto_path_oct30_r5_bridge.mjs")
MINIMUM_REMAINING = r4.MINIMUM_REMAINING
FROZEN = d.ROOT / ".deployment/oct30-r4-authorized-current-pre-freeze-20261030.json"
FROZEN_SHA = "5f31c2f2745fa4d5ec2779aa8b74ad30390c3e46ea7f16ea92a1919555447ba0"
OWN_FILES = ("scripts/deployment/auto_path_oct30_successor_r5.py",
    "scripts/deployment/auto_path_oct30_successor_r5_reads.py",
    "tests/unit/test_auto_path_oct30_successor_r5.py", "docs/auto-path-oct30-successor-r5.md",
    "scripts/deployment/auto_path_oct30_r5_bridge.mjs")


def sources():
    # Never expand r4's old source glob to silently adopt new files into its proof.
    r4.r3.checked_file(d.ROOT, FROZEN.relative_to(d.ROOT), FROZEN_SHA)
    frozen = d.load(FROZEN)["sources"]
    d.require(len(frozen) == 268, "r5_preserve_all268_r4_bindings")
    for name, digest in frozen.items():
        r4.r3.checked_file(d.ROOT, name, digest)
    result = dict(frozen)
    historical, comparison = reads.evidence()
    for path in (FROZEN, reads.EVIDENCE / "deployment-comparison.json", reads.EVIDENCE / "analysis.md",
                 d.ROOT / comparison["historical_source"], d.ROOT / comparison["last_successful_frozen_capture"],
                 *(d.ROOT / name for name in (*OWN_FILES, *reads.REFERENCE_FILES))):
        r4.r3.checked_file(d.ROOT, path.relative_to(d.ROOT))
        result[path.relative_to(d.ROOT).as_posix()] = d.sha(path.read_bytes())
    return result


def account_proof(capture):
    value = capture.get("account_inventory_r5")
    d.require(isinstance(value, dict) and value.get("complete") is True
        and len(value.get("observations", [])) == 3, "r5_actual_complete_account_evidence_required")
    references = {"formats": capture["formats"], "inheritance": capture["inheritance"],
        "owned_api": capture["owned_api"], "baseline": capture["baseline"],
        "source_snapshots": {name: (d.ROOT / name).read_bytes().decode() for name in reads.REFERENCE_FILES}}
    reads.absent_references(references)
    d.require(value["references_sha256"] == d.r.fs.sha(references), "r5_reference_capture_binding")
    first = value["observations"][0]
    for item in value["observations"]:
        _, rebuilt = reads.protect(item["account"], item["pages"], references["source_snapshots"])
        d.require(rebuilt == item and item["account_sha256"] == first["account_sha256"],
                  "r5_full_account_proof_or_capture_drift")
    d.require(capture["baseline"]["model_metadata_sha256"] == reads.HISTORICAL_SHA
        and capture["supplemental"]["rai_bindings_sha256"] == d.r.fs.sha({
            row["name"]: row["properties"].get("raiPolicyName") for row in reads.evidence()[0]["value"]}),
        "r5_consistent_original13_metadata_and_RAI_projection")
    return first


def initial(capture):
    account_proof(capture)
    return r4.successor.initial(capture)


def guarded(before, current, folder, global_installed, revision_installed, online):
    previous, actual = account_proof(before), account_proof(current)
    d.require(actual["account_sha256"] == previous["account_sha256"]
        and actual["additions_sha256"] == previous["additions_sha256"], "r5_whole_account_drift_across_attempt")
    return r4.controller.guarded(before, current, folder, global_installed, revision_installed, online)


# Same memoized exact format proofs, six stages and fixed budgets.
# Rebinding is private; the original268 and all imported module bindings survive.
controller = r4._copy(r4.controller, initial=initial, guarded=guarded, sources=sources, collect=reads.collect,
    r=r4._copy(d.r, rt=reads.RUNTIME), IP=IP, BRIDGE=BRIDGE, PATH_BROWSER=BRIDGE)


def render(global_export, revision, start, end, nonce):
    # First execute every inherited predecessor/counter/finite-delta proof.
    # Do NOT rebind old.IP: that literal authenticates the historical storage ADD.
    previous = r4.successor.render(global_export, revision, start, end, nonce)
    before, _, _ = r4.r3.old.prior.predecessor()
    fresh = tools.bind(d.render, vars(controller))(
        d.policy_values(before["formats"]["global"])["xml"].encode(), revision, start, end, nonce)
    # Compare serialized wire bytes (XML attributes escape quotes), not raw C#.
    old_literal = ('context.Request.IpAddress == &quot;' + r4.r3.old.IP + '&quot;').encode()
    new_literal = ('context.Request.IpAddress == &quot;' + IP + '&quot;').encode()
    for name in ("global.xml", "revision.xml"):
        d.require(previous[name].count(old_literal) == 1 and new_literal not in previous[name]
            and fresh[name].count(new_literal) == 1 and old_literal not in fresh[name]
            and fresh[name] == previous[name].replace(old_literal, new_literal, 1),
            "r5_exact_candidate_admission_IP_only:" + name)
    d.require(fresh["restore-global.xml"] == previous["restore-global.xml"], "r5_restore_bytes_unchanged")
    prior_diffs, new_diffs = (d.json.loads(value["proposal-diffs.json"]) for value in (previous, fresh))
    for kind in ("global", "diagnostic"):
        d.require(new_diffs[kind]["before"] == prior_diffs[kind]["before"], "r5_original_before_provenance")
    return fresh


successor = r4._copy(r4.successor, controller=controller, PREFIX=PREFIX,
    sources=sources, initial=initial, render=render, _localcheck=tools.bind(d.localcheck, vars(controller)))
controller.render = render
controller.localcheck = successor.localcheck
controller.wire_child = d.wire_child  # Spawn target must remain original/importable on Windows.
controller.send_once = tools.bind(d.send_once, vars(controller))


class ProductionAdapter(d.ProductionAdapter):
    def capture(self):
        self.ready = None
        self.value = reads.collect()
        account_proof(self.value)
        self.captured = deepcopy(self.value)
        return self.value

    def last(self, stage):
        private, _ = reads.private_controller({})
        return tools.bind(d.ProductionAdapter.last, {**vars(controller), "c": private.c})(self, stage)

    send = tools.bind(d.ProductionAdapter.send, vars(controller))


class Stages(r4.reads.Stages):
    activate = tools.bind(d.Stages.activate, vars(controller))
    cleanup = tools.bind(d.Stages.cleanup, vars(controller))
    _execute = tools.bind(d.Stages.execute, vars(controller))


successor.Stages = controller.Stages = Stages
successor.ProductionAdapter = controller.ProductionAdapter = ProductionAdapter
successor.namespace = {**vars(r4.old), "controller": controller, "localcheck": successor.localcheck,
    "Stages": Stages, "ProductionAdapter": ProductionAdapter, "collector": reads,
    "MINIMUM_REMAINING": MINIMUM_REMAINING}
successor._run_reviewed_window = tools.bind(r4.r3.old.run_reviewed_window, successor.namespace)
successor.file_browser_handoff = tools.bind(r4.r3.old.file_browser_handoff, successor.namespace)
localcheck, prepare = successor.localcheck, successor.prepare
run_reviewed_window = successor.run_reviewed_window


def parent_cli():
    from scripts.deployment import auto_path_oct30_parent as parent
    # Existing parent and review/preflight/finally integration, never a new executor.
    return r4._copy(parent, s=successor, d=controller)


if __name__ == "__main__":
    try:
        parent_cli().main()
    except Exception:
        print('{"status":"STOP_RECONCILE_DURABLE_EVIDENCE_NO_RETRY"}', flush=True)
        raise SystemExit(2)