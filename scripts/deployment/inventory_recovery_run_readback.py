"""Read an already-submitted ACR run in UTF8; never submit or retry a build."""
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys

from scripts.deployment import inventory_recovery_oct29 as r


def main(folder, run_id):
    r.rt.require(folder.parent == r.rt.HOME and folder.name.startswith("inventory-recovery-20261029-")
                 and re.fullmatch("cm[a-z0-9]+", run_id), "exact_retained_run")
    # Native az.cmd fixes neither isolated interpreter cp1252 nor Unicode build
    # logs. Its installed, identical CLI module supports an explicit UTF8 flag.
    r.rt.CLI = ["C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe", "-X", "utf8", "-IBm", "azure.cli"]
    run = r.rt.cli(["acr", "task", "show-run", "-r", "pocidstokenexacr", "--run-id", run_id, "--subscription", r.rt.SUB])
    log = r.rt.run(r.rt.CLI + ["acr", "task", "logs", "-r", "pocidstokenexacr", "--run-id", run_id, "--subscription", r.rt.SUB])
    log = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', log)
    name = "run-" + run_id + "-readback"
    with (folder / (name + ".log")).open("x", encoding="utf-8") as handle:
        handle.write(log)
    proof = {"at_utc": datetime.now(UTC).isoformat(), "run_id": run_id, "status": run["status"],
             "finishTime": run.get("finishTime"), "outputImages": run.get("outputImages"),
             "log_sha256": r.sha(log), "submissions": 0}
    r.write(folder, name + ".json", proof)
    print(json.dumps(proof), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), sys.argv[2])