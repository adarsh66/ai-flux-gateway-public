"""UNBOUND r4: private 22-minute launch reserve; no implicit release action."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from scripts.deployment import auto_path_oct30_successor as r3
from scripts.deployment import auto_path_oct30_successor_reads as reads

d, tools = r3.d, r3.tools
MINIMUM_REMAINING = d.timedelta(minutes=22)
PREFIX = "auto-path-oct30-successor-r4-"


def _copy(module, **overrides):
    """Rebind module-owned functions only; never patch imported r3 globals."""
    result = tools.copy_module(module)
    result.__dict__.update(overrides)
    for name, value in vars(module).items():
        if getattr(value, "__globals__", None) is vars(module) and name not in overrides:
            setattr(result, name, tools.bind(value, vars(result)))
    return result


@lru_cache(maxsize=256)
def _formats(encoded, wire):
    # Exact complete values, NOT filename/mtime/ETag-only cache keys. Exceptions
    # aren't cached; callers receive copies so they cannot poison later proofs.
    return d.verify_formats(d.json.loads(encoded), wire)


def verify_formats(value, wire=None):
    return deepcopy(_formats(d.encode(value), wire))


# The old predecessor chain repeatedly verifies identical format pairs. Only
# that pure proof is memoized. File reads, full SHA mappings, inventories,
# rendering, reviews, clocks, intents, owner and live captures are NEVER cached.
proof = _copy(d, verify_formats=verify_formats)
prior = _copy(r3.old.prior, original=proof, _sources=proof.sources, _guarded=proof.guarded)
controller = r3.old.prior._isolated()
controller.IP, controller.BRIDGE, controller.PATH_BROWSER = r3.old.IP, r3.old.BRIDGE, r3.old.BROWSER
old = _copy(r3.old, d=proof, prior=prior, _render=tools.bind(d.render, vars(controller)))
successor = _copy(r3, d=proof, old=old, controller=controller, PREFIX=PREFIX,
                  _localcheck=controller.localcheck, counter_files=r3.counter_files)
_sources = successor.sources


def sources():
    frozen = _sources()
    for path in (Path(__file__), d.ROOT / "tests/unit/test_auto_path_oct30_successor_r4.py",
                 d.ROOT / "docs/auto-path-oct30-successor-r4.md"):
        frozen[path.relative_to(d.ROOT).as_posix()] = d.sha(path.read_bytes())
    return frozen


successor.sources = sources
controller.initial, controller.render = successor.initial, successor.render
controller.sources, controller.localcheck = sources, successor.localcheck
controller.verify_formats = verify_formats
controller.send_once, controller.collect = d.send_once, reads.collect


class Stages(reads.Stages):
    activate = tools.bind(d.Stages.activate, vars(controller))
    cleanup = tools.bind(d.Stages.cleanup, vars(controller))
    _execute = tools.bind(d.Stages.execute, vars(controller))


successor.Stages = controller.Stages = Stages
successor.ProductionAdapter = controller.ProductionAdapter = reads.ProductionAdapter
successor.namespace = {**vars(old), "controller": controller, "localcheck": successor.localcheck,
                       "Stages": Stages, "ProductionAdapter": reads.ProductionAdapter,
                       "collector": reads, "MINIMUM_REMAINING": MINIMUM_REMAINING}
successor._run_reviewed_window = tools.bind(r3.old.run_reviewed_window, successor.namespace)
localcheck, prepare = successor.localcheck, successor.prepare
run_reviewed_window = successor.run_reviewed_window


def parent_cli():
    from scripts.deployment import auto_path_oct30_parent as parent
    return _copy(parent, s=successor)


if __name__ == "__main__":
    try:
        parent_cli().main()
    except Exception:
        print('{"status":"STOP_RECONCILE_DURABLE_EVIDENCE_NO_RETRY"}', flush=True)
        raise SystemExit(2)