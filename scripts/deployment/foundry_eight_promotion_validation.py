"""Durable, exclusive offline validation of the new evidence promotion sources."""
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from scripts.deployment import foundry_eight_offline_promotion as f

a = f.a
HOME = a.rt.HOME / "foundry-eight-offline-validation-20261031"
TESTS = (
    "tests/unit/test_foundry_eight_offline_promotion.py",
    "tests/unit/test_foundry_eight_acceptance.py",
    "tests/unit/test_foundry_eight_acceptance_successor.py",
    "tests/unit/test_foundry_eight_acceptance_successor02.py",
    "tests/unit/test_foundry_eight_acceptance_successor03.py",
    "tests/unit/test_foundry_eight_catalog.py",
    "tests/unit/test_foundry_inventory.py",
    "tests/unit/test_external_inventory.py",
    "tests/unit/test_display_pricing.py",
    "tests/unit/test_catalog_pricing_correction.py",
)


def sources():
    paths = [a.ROOT / name for name in TESTS] + [Path(__file__), Path(f.__file__),
        f.PROFILE_SOURCE, Path(f.m.__file__), Path(f.m.prior.__file__)]
    return {p.relative_to(a.ROOT).as_posix(): a.sha(p.read_bytes()) for p in paths}


def run():
    a.require(not HOME.exists(), "validation_exists_read_retained_result")
    before, bound = f.historical_hashes(), sources()
    a.write(HOME / "intent.json", {"at": a.now(), "sources": bound, "cloud_calls": 0, "inference_sends": 0})
    result = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider",
        *TESTS, "--junitxml=" + str(HOME / "tests.xml")], cwd=a.ROOT,
        capture_output=True, timeout=300)
    a.write(HOME / "stdout.log", result.stdout)
    a.write(HOME / "stderr.log", result.stderr)
    report = ET.parse(HOME / "tests.xml").getroot()
    suites = list(report.iter("testsuite"))
    counts = {key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    passed = result.returncode == 0 and counts["tests"] > 0 and not any(counts[k] for k in ("failures", "errors", "skipped"))
    a.require(sources() == bound and f.historical_hashes() == before, "validation_input_or_history_drift")
    proof = {"at": a.now(), "passed": passed, "returncode": result.returncode, "counts": counts,
        "sources": bound, "historical_bytes_unchanged": True, "cloud_calls": 0, "inference_sends": 0,
        "files": {p.name: a.sha(p.read_bytes()) for p in HOME.iterdir() if p.is_file()}}
    a.write(HOME / "result.json", proof)
    print(result.stdout.decode("utf-8", errors="replace"), flush=True)
    print({k: v for k, v in proof.items() if k not in ("sources", "files")}, flush=True)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(run())