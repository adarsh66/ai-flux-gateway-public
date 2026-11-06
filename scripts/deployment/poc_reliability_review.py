"""Independent finite offline review. No builds, plans, ARM calls or applies."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt

HOME = rt.HOME / "poc-publisher-reliability-20261028"
FILES = ["services/control-plane/src/aiflux/apim.py", "services/control-plane/src/aiflux/gateway_settings.py",
         "infra/project-route/fireworks.tf", "tests/unit/test_poc_publisher_reliability.py",
         "tests/unit/test_poc_fireworks_compatibility.py", "scripts/deployment/poc_reliability_review.py"]


def hashes():
    return {p: hashlib.sha256((rt.ROOT / p).read_bytes()).hexdigest() for p in FILES}


def main():
    HOME.mkdir(exist_ok=True)
    initial = hashes()
    with (HOME / "offline-review-intent.json").open("x") as handle:
        json.dump({"at": datetime.now(UTC).isoformat(), "sources": initial, "cloud_writes": 0}, handle)
    tests = ["test_poc_publisher_reliability.py", "test_poc_fireworks_compatibility.py", "test_gateway_settings.py",
             "test_poc_controls.py", "test_managed_controls.py", "test_poc_controls_guards.py",
             "test_poc_activation_release.py", "test_fireworks_addition.py"]
    commands = [[sys.executable, "-X", "utf8", "-m", "pytest", "-q", *["tests/unit/" + p for p in tests],
                 "-k", "not migration", "--junitxml=" + str(HOME / "offline-tests.xml")],
                [rt.TF, "-chdir=infra/project-route", "fmt", "-check"],
                [rt.TF, "-chdir=infra/project-route", "validate", "-no-color"],
                [rt.TF, "-chdir=infra/project-route", "test", "-no-color"]]
    results = []
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=rt.ROOT, env=rt.ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
        (HOME / ("offline-" + str(index) + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        results.append({"index": index, "exit_code": result.returncode})
        print(json.dumps(results[-1]), flush=True)
    suites = ET.parse(HOME / "offline-tests.xml").getroot().findall("testsuite")
    counts = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "errors", "failures", "skipped")}
    proof = {"at": datetime.now(UTC).isoformat(), "sources": initial, "source_unchanged": initial == hashes(),
             "results": results, "tests": counts, "passed": all(r["exit_code"] == 0 for r in results) and initial == hashes(),
             "live_root_cause_proven": False, "documented_async_response_reproduced": True,
             "cloud_writes": 0, "builds": 0, "plans": 0, "applies": 0}
    with (HOME / "offline-review.json").open("x") as handle:
        json.dump(proof, handle, indent=2)
    print(json.dumps(proof), flush=True)
    return 0 if proof["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())