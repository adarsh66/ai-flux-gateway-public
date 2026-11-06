"""Finite offline backend test groups with exclusive, durable result receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".deployment/decision1-visibility01"
GROUPS = {
    "scoring": ["test_scoring_catalog", "test_scoring_rate_card"],
    "telemetry": ["test_decision_telemetry", "test_decision_overhead_accounting"],
    "pricing": ["test_rate_card", "test_display_pricing", "test_catalog_pricing_correction"],
    "portal": ["test_turnstile_exchange", "test_portal_fix", "test_portal_auth"],
    "turnstile": ["test_turnstile_exchange"],
    "catalog": ["test_foundry_inventory", "test_external_inventory", "test_inventory_persistent_acceptance"],
}


def offline(event, args):
    if event == "subprocess.Popen" or event == "os.system":
        raise RuntimeError("Offline validation forbids child commands")
    if event == "socket.getaddrinfo" and args[0] not in ("localhost", "127.0.0.1", "::1", None):
        raise RuntimeError("Offline validation forbids external DNS")
    if event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("Offline validation forbids external connections")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=GROUPS)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if not args.receipt.replace("-", "").isalnum():
        parser.error("receipt must be an alphanumeric label")
    OUT.mkdir(parents=True, exist_ok=True)
    prefix = OUT / args.receipt
    tests = [f"tests/unit/{name}.py" for name in GROUPS[args.group]]
    pytest_args = ["-q", "-ra", "--tb=short", "-o", "addopts=", "--junitxml=" + str(prefix) + ".xml", *tests]
    if args.worker:
        sys.addaudithook(offline)
        import pytest
        return int(pytest.main(pytest_args))
    command = [sys.executable, str(Path(__file__).resolve()), args.group,
               "--receipt", args.receipt, "--worker"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for directory in (ROOT / "services/control-plane/src/aiflux", ROOT / "tests/unit")
              for p in directory.rglob("*") if p.is_file() and p.suffix in (".py", ".json")}
    started = time.time()
    with prefix.with_suffix(".started.json").open("x", encoding="utf-8") as handle:
        json.dump({"command": command, "pytest_args": pytest_args, "source_sha256": hashes}, handle, indent=2)
    timed_out = False
    with prefix.with_suffix(".log").open("x", encoding="utf-8") as log:
        environment = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONUTF8": "1"}
        try:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=240, check=False)
            code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out, code = True, None
    counts = None
    xml = prefix.with_suffix(".xml")
    if xml.exists():
        suites = ET.parse(xml).getroot().findall("testsuite")
        counts = {key: sum(int(s.get(key, "0")) for s in suites)
                  for key in ("tests", "failures", "errors", "skipped")}
    changed = [p for p, digest in hashes.items()
               if not (ROOT / p).exists() or hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != digest]
    receipt = {"command": command, "pytest_args": pytest_args, "exit_code": code,
               "timed_out": timed_out, "counts": counts, "elapsed_seconds": round(time.time() - started, 3),
               "changed_during_run": changed}
    with prefix.with_suffix(".result.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt, indent=2), flush=True)
    print(prefix.with_suffix(".log").read_text(encoding="utf-8"), flush=True)
    return code if code is not None else 124


if __name__ == "__main__":
    raise SystemExit(main())