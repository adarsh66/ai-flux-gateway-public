"""Local-only reconciliation of existing one-shot workers and structural logs."""
import json
import re

from scripts.deployment import inventory_persistence_apply_once as a


if __name__ == "__main__":
    result = a.OUT / "apply-result.json"
    text = (a.OUT / "apply.stdout.private.log").read_text(encoding="utf-8", errors="replace")
    errors = (a.OUT / "apply.stderr.private.log").read_text(encoding="utf-8", errors="replace")
    print(json.dumps({
        "at_utc": a.now(),
        "apply_result": a.r.old.load(result) if result.exists() else None,
        "workers": a.r.backend.workers(),
        "structural_progress": re.findall(
            r"Still modifying\.\.\.|Modifications complete after|Apply complete! Resources: \d+ added, \d+ changed, \d+ destroyed\.", text)[-5:],
        "fixed_error_categories": a.r.rt.diagnostic_categories(errors),
        "apply_intent_exists": (a.HOME / "live-apply-intent.json").exists(),
        "writes": 0, "retry_authorized": False,
    }), flush=True)