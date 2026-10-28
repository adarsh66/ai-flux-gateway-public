"""Independent deadline process; current entrypoint tests real ARM absence only.

This does NOT authorize/provide cloud DELETE, install a production watchdog, or
attest live populated-resource cleanup. Its actual subprocess test is distinct
from mocked cleanup unit tests. Fail closed if any reserved ID is not HTTP 404.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_preflight as p

OUT = p.ROOT / "gateway/validation/finops-runner-watchdog-deadline-20261027.json"


def at_deadline(deadline, output):
    report = {"mode": "read_only_external_process_deadline_test", "worker_pid": os.getpid(),
        "deadline_utc": deadline.isoformat(), "started_at_utc": p.now(),
        "cloud_deletes": 0, "cloud_creates": 0, "production_watchdog_installed": False,
        "populated_resource_cleanup_tested": False, "results": []}
    try:
        seconds = (deadline - datetime.now(UTC)).total_seconds()
        g.require(-60 <= seconds <= 15, "test_deadline_outside_bound")
        threading.Event().wait(max(seconds, 0))
        report["triggered_at_utc"] = p.now()
        account = p.cli(["account", "show"])
        g.require(account["id"] == g.SUB and account["tenantId"] == g.TENANT, "account_scope_mismatch")
        prior = json.loads(p.OUT.read_text(encoding="utf-8"))
        ids = g.owned_ids(prior["owner_nonce"])
        token = subprocess.run([p.AZ, "account", "get-access-token", "--subscription", g.SUB,
            "--resource", "https://management.azure.com/", "--query", "accessToken", "-o", "tsv", "--only-show-errors"],
            capture_output=True, text=True, env=p.ENV, timeout=70)
        g.require(token.returncode == 0 and token.stdout.strip(), "arm_authentication_failed")
        tls = ssl.create_default_context(cafile=p.CA)
        for key, rid in ids.items():
            version = "2023-05-01" if key in g.IDENTITIES else "2024-05-01"
            request = Request("https://management.azure.com" + rid + "?api-version=" + version,
                headers={"Authorization": "Bearer " + token.stdout.strip()})
            try:
                with urlopen(request, context=tls, timeout=20) as response:
                    code = response.status
            except HTTPError as exc:
                code = exc.code
                exc.close()
            report["results"].append({"resource_id": rid, "http_status": code, "at_utc": p.now()})
            g.require(code == 404, "test_refuses_existing_or_unverified_resource")
        report["all_six_exact_ids_absent"] = True
        report["exit_code"] = 0
    except Exception as exc:
        report["exit_code"] = 2
        report["reason"] = str(exc) if isinstance(exc, g.GuardBlocked) else "deadline_test_failed"
    finally:
        report["finished_at_utc"] = p.now()
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report["exit_code"]


def launch_detached(deadline, output):
    g.require(os.name == "nt", "windows_process_isolation_required")
    child = subprocess.Popen([sys.executable, "-m", "scripts.deployment.finops_runner_watchdog",
        "--deadline", deadline, "--output", str(output)], cwd=p.ROOT, env=p.ENV,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    print(json.dumps({"worker_pid": child.pid, "launcher_pid": os.getpid()}), flush=True)


def external_process_test():
    deadline = datetime.now(UTC) + timedelta(seconds=8)
    # The disposable launcher actually exits. A different detached process later
    # reaches its deadline and obtains fresh credentials, then checks real ARM.
    child = subprocess.run([sys.executable, "-m", "scripts.deployment.finops_runner_watchdog",
        "--launch", "--deadline", deadline.isoformat(), "--output", str(OUT)],
        cwd=p.ROOT, env=p.ENV, capture_output=True, text=True, timeout=20)
    g.require(child.returncode == 0, "detached_launcher_failed")
    ids = json.loads(child.stdout)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, ids["worker_pid"])
    g.require(bool(handle), "cannot_observe_independent_worker")
    try:
        g.require(kernel.WaitForSingleObject(handle, 160000) == 0, "independent_worker_deadline_failed")
    finally:
        kernel.CloseHandle(handle)
    report = json.loads(OUT.read_text(encoding="utf-8"))
    g.require(report["worker_pid"] == ids["worker_pid"] and report["deadline_utc"] == deadline.isoformat(), "stale_deadline_evidence")
    report["launcher_pid"] = ids["launcher_pid"]
    report["launcher_exit_code_before_worker_completion"] = child.returncode
    report["actual_independent_process_survived_launcher_exit"] = True
    report["limitations"] = ["not a production cleanup controller installation", "no DELETE path or populated live resource cleanup exercised",
        "depends on this workstation remaining awake, connected and authorized; not proof against host loss"]
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report), flush=True)
    return report["exit_code"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-external-process", action="store_true")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--deadline")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    if args.test_external_process:
        raise SystemExit(external_process_test())
    deadline = datetime.fromisoformat(args.deadline)
    g.require(deadline.tzinfo is not None, "explicit_utc_required")
    if args.launch:
        launch_detached(args.deadline, args.output)
    else:
        raise SystemExit(at_deadline(deadline, args.output))