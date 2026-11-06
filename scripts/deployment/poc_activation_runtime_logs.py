"""Read retained API container logs; emit categories and counts, never raw lines."""
import json
import re

from scripts.deployment import poc_activation_release as r


if __name__ == "__main__":
    raw = r.rt.arm(r.rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/containerlogs", "POST", raw=True)
    text = raw.decode("utf-8", errors="replace")
    result = {"at": r.fs.stamp(), "summary": r.rt.log_summary(raw),
        "poc_publish_502_mentions": len(re.findall(r"gateway-settings.*502", text)),
        "poc_reconcile_200_mentions": len(re.findall(r"gateway-settings.*reconcile.*200", text)),
        "apim_async_exception_detail_available": False,
        "limitation": "publish_poc catches ApimError without logging its status/cause; this collector cannot prove which async/readback branch failed.",
        "cloud_writes": 0}
    r.exclusive(r.HOME, "runtime-publication-log-summary.json", result)
    print(json.dumps(result, indent=2), flush=True)