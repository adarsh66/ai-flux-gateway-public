"""Exact approved temporary ACI execution with a detached, hash-bound reaper.

No app configuration, state, RBAC, database write, recovery or alternate host.
ARM credentials remain in memory. All artifacts contain finite labels/aggregates.
The independent process survives controller exit, not workstation loss.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import json
import msvcrt
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_preflight as p
from scripts.deployment import finops_runner_prepare as prep
from scripts.deployment import finops_runner_build as build

OUT = p.ROOT / "gateway/validation/finops-runner-execution-20261027.json"
ERROR_CODES = {"RequestDisallowedByPolicy", "AuthorizationFailed", "InvalidResourceReference",
    "ServiceUnavailable", "InaccessibleImage", "ImagePullFailed", "RegistryErrorResponse",
    "DeploymentFailed", "InvalidTemplateDeployment", "SubnetMissingRequiredDelegation",
    "InvalidContainerGroupSubnet", "ResourceNotAvailable", "ContainerGroupQuotaReached",
    "AllocationFailed", "ResourceDeploymentFailure", "InternalServerError", "BadRequest",
    "InvalidRequestContent", "MissingSubscriptionRegistration", "SkuNotAvailable"}


def write(path, value):
    temp = path.with_suffix(path.suffix + ".tmp-" + str(os.getpid()))
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def bound_session(path, expected_hash):
    g.require(prep.digest(path) == expected_hash, "execution_session_changed")
    s = load(path)
    g.require(s["ids"] == g.owned_ids(s["owner_nonce"]), "execution_ids_changed")
    deadline = datetime.fromisoformat(s["deadline_utc"])
    started = datetime.fromisoformat(s["started_at_utc"])
    g.require(deadline - started == timedelta(minutes=60), "lifetime_changed")
    return s


@contextmanager
def lock(folder):
    with (folder / "operation.lock").open("a+b") as f:
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        end = time.monotonic() + 100
        while True:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                g.require(time.monotonic() < end, "controller_lock_timeout")
                threading.Event().wait(0.2)
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


class Arm:
    def __init__(self, session):
        self.s = session
        self.token = ""
        self.token_time = 0
        self.context = ssl.create_default_context(cafile=p.CA)
        self.events = []

    def request(self, method, rid, body=None, *, action=None):
        ids = self.s["ids"]
        g.require(rid in ids.values(), "foreign_arm_resource")
        key = next(k for k, v in ids.items() if v == rid)
        if action:
            g.require(method == "GET" and key in g.IDENTITIES and action == "/containers/probe/logs", "foreign_arm_action")
        if time.monotonic() - self.token_time > 900:
            account = p.cli(["account", "show"])
            g.require(account["id"] == g.SUB and account["tenantId"] == g.TENANT, "account_scope_mismatch")
            result = subprocess.run([p.AZ, "account", "get-access-token", "--subscription", g.SUB,
                "--resource", "https://management.azure.com/", "--query", "accessToken", "-o", "tsv", "--only-show-errors"],
                capture_output=True, text=True, env=p.ENV, timeout=60)
            g.require(result.returncode == 0 and result.stdout.strip(), "arm_authentication_failed")
            self.token, self.token_time = result.stdout.strip(), time.monotonic()
        version = "2023-05-01" if key in g.IDENTITIES else "2024-05-01"
        url = "https://management.azure.com" + rid + (action or "") + "?api-version=" + version
        if action:
            url += "&tail=1&timestamps=false"
        req = Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with urlopen(req, context=self.context, timeout=45) as response:
                raw = response.read(2_000_000)
                value = json.loads(raw) if raw else {}
                self.events.append({"at_utc": p.now(), "method": method, "resource_id": rid,
                    "http_status": response.status, "action": action})
                return value
        except HTTPError as exc:
            status = exc.code
            raw = exc.read(100_000).decode("utf-8", errors="replace")
            codes = sorted(code for code in ERROR_CODES if code in raw)
            exc.close()
            self.events.append({"at_utc": p.now(), "method": method, "resource_id": rid,
                "http_status": status, "error_codes": codes, "action": action})
            if status == 404 and method == "GET" and not action:
                return None
            raise g.GuardBlocked("arm_http_" + str(status)) from None

    def get(self, rid):
        return self.request("GET", rid)

    def delete(self, rid):
        self.request("DELETE", rid)
        end = time.monotonic() + 240
        while self.get(rid) is not None:
            g.require(time.monotonic() < end, "owned_delete_timeout")
            threading.Event().wait(3)


def verify_owned(resource, key, session):
    g.owned_resource(resource, nonce=session["owner_nonce"], key=key, journal=session)
    if key == "nsg":
        expected = prep.network_template(session["owner_nonce"], profile=session.get("network_profile", "postgres"))["resources"][1]["properties"]["securityRules"]
        actual = resource["properties"]["securityRules"]
        normalize = lambda rules: {r["name"]: {k: r["properties"].get(k) for k in expected[0]["properties"]} for r in rules}
        g.require(normalize(actual) == normalize(expected), "owned_nsg_rules_changed")
    if key == "nat":
        g.require(resource.get("sku", {}).get("name") == "Standard" and
            [x["id"].lower() for x in resource["properties"].get("publicIpAddresses", [])] == [session["ids"]["pip"].lower()], "owned_nat_changed")
    if key == "pip":
        g.require(resource.get("sku", {}).get("name") == "Standard" and
            resource["properties"].get("publicIPAllocationMethod") == "Static", "owned_pip_changed")
    if key in g.IDENTITIES:
        g.guard_probe_group(resource, nonce=session["owner_nonce"], phase=key,
            image=session["image"], source_hash=session["probe_hash"], prior_group_absent=True)


def cleanup(session, folder, arm):
    result = {"started_at_utc": p.now(), "deleted_resource_ids": [], "absence": []}
    try:
        # Delete only the two exact owned groups, then require their GET404
        # before considering the subnet. Never delete an adopted network object.
        for key in ("ingestion", "api", "subnet", "nsg", "nat", "pip"):
            with lock(folder):
                marker = folder / "cleanup-started.json"
                if not marker.exists():
                    write(marker, {"at_utc": p.now()})
                resource = arm.get(session["ids"][key])
                if resource is not None:
                    verify_owned(resource, key, session)
                    arm.delete(session["ids"][key])
                    result["deleted_resource_ids"].append(session["ids"][key])
        for rid in session["ids"].values():
            absent = arm.get(rid) is None
            result["absence"].append({"resource_id": rid, "http_status": 404 if absent else 200, "at_utc": p.now()})
            g.require(absent, "cleanup_final_get_failed")
        result["exit_code"] = 0
    except Exception as exc:
        result.update(exit_code=2, reason=str(exc) if isinstance(exc, g.GuardBlocked) else "sanitized_cleanup_failure")
    result["finished_at_utc"] = p.now()
    return result


def reconcile_cleanup(path, expected_hash):
    """Cleanup only: bind original session; never enter provisioning or probe paths."""
    s = bound_session(path, expected_hash)
    original = load(OUT)
    g.require(original.get("ids") == s["ids"] and original.get("owner_nonce") == s["owner_nonce"], "execution_evidence_mismatch")
    g.require(original["independent_watchdog_ready"]["session_sha256"] == expected_hash, "watchdog_session_mismatch")
    output = p.ROOT / "gateway/validation/finops-owned-cleanup-20261027.json"
    # A repeated verification must never erase the actual nonempty DELETE proof.
    if output.exists():
        output = output.with_name("finops-owned-cleanup-verification-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    report = {"started_at_utc": p.now(), "mode": "owned_cleanup_only", "owner_nonce": s["owner_nonce"],
        "session_sha256": expected_hash, "created_resource_ids": original["created_resource_ids"],
        "ids": s["ids"], "new_resources_created": [], "probe_retried": False,
        "original_execution_exit_code": original.get("exit_code"), "original_reason": original.get("reason"),
        "watchdog_pid": original["watchdog_pid"], "watchdog_stopped": False,
        "inbound_actually_applied": original["inbound"], "guard_sha256": prep.digest(Path(g.__file__)),
        "database_writes": 0, "timer_enabled": False, "app_release": False}
    arm = Arm(s)
    try:
        for phase in g.IDENTITIES:
            resource = arm.get(s["ids"][phase])
            if resource is not None:
                verify_owned(resource, phase, s)
                props = resource["properties"]
                instance = props["containers"][0]["properties"].get("instanceView", {})
                state = instance.get("currentState", {})
                report.setdefault("runtime_readback", {})[phase] = {
                    "at_utc": p.now(), "ownership_verified": True, "ipAddress": props.get("ipAddress"),
                    "state": state.get("state"), "os_exit_code": state.get("exitCode"),
                    "started_at_utc": state.get("startTime"), "finished_at_utc": state.get("finishTime"),
                    "restart_count": instance.get("restartCount"), "validated_probe_result": None}
        report["exit_code"] = 0
    except Exception as exc:
        report.update(exit_code=2, reason=str(exc) if isinstance(exc, g.GuardBlocked) else "sanitized_readback_failure")
    finally:
        # Even readback failure cannot skip the original strict owned cleanup.
        report["cleanup"] = cleanup(s, path.parent, arm)
        report["final_exact_id_readbacks"] = []
        for rid in s["ids"].values():
            try:
                absent = arm.get(rid) is None
                report["final_exact_id_readbacks"].append({"resource_id": rid,
                    "http_status": 404 if absent else 200, "at_utc": p.now()})
            except Exception:
                report["final_exact_id_readbacks"].append({"resource_id": rid, "http_status": None, "at_utc": p.now()})
        report["outstanding_resource_ids"] = [x["resource_id"] for x in report["final_exact_id_readbacks"] if x["http_status"] != 404]
        report["exit_code"] = 2 if report["outstanding_resource_ids"] or report["cleanup"]["exit_code"] else report["exit_code"]
        try:
            report["preservation_after"] = prep.preservation_readback()
        except Exception:
            report["preservation_after"] = {"verified": False}
        report.update(arm_events=arm.events, finished_at_utc=p.now())
        write(output, report)
        print(json.dumps(report), flush=True)
    return report["exit_code"]


def watchdog(path, expected_hash, *, synthetic=False):
    s = bound_session(path, expected_hash)
    folder = path.parent
    ready = {"pid": os.getpid(), "ready_at_utc": p.now(), "deadline_utc": s["deadline_utc"],
        "session_sha256": expected_hash, "synthetic": synthetic, "code_sha256": prep.digest(Path(__file__)),
        "guard_sha256": prep.digest(Path(g.__file__)), "ids": s["ids"]}
    write(folder / "watchdog-ready.json", ready)
    # Reserve eight minutes for dependency-safe DELETE + independent GET404.
    seconds = (datetime.fromisoformat(s["deadline_utc"]) - timedelta(minutes=8) - datetime.now(UTC)).total_seconds()
    if synthetic:
        seconds = 2
    threading.Event().wait(max(0, seconds))
    # This process does not depend on a controller finally, heartbeat or tokens
    # passed from the controller. Authenticate afresh at the deadline.
    if synthetic:
        class FakeArm:
            def __init__(self):
                self.items = {s["ids"][k]: {"id": s["ids"][k], "location": "southeastasia",
                    "tags": {"finops-owner": s["owner_nonce"]}, "properties": {"publicIPAllocationMethod": "Static"},
                    "sku": {"name": "Standard"}} for k in ("pip",)}
            def get(self, rid): return self.items.get(rid)
            def delete(self, rid): del self.items[rid]
        arm = FakeArm()
    else:
        arm = Arm(s)
    result = cleanup(s, folder, arm)
    result.update(worker_pid=os.getpid(), deadline_utc=s["deadline_utc"], triggered_at_utc=p.now(),
        survived_launcher_exit=True, synthetic=synthetic)
    if not synthetic:
        result["arm_events"] = arm.events
    write(folder / "watchdog-result.json", result)
    return result["exit_code"]


def launch_watchdog(path, expected_hash, *, synthetic=False):
    args = [sys.executable, "-m", "scripts.deployment.finops_runner_execute", "--watchdog", str(path), "--session-hash", expected_hash]
    if synthetic:
        args.append("--synthetic")
    child = subprocess.Popen(args, cwd=p.ROOT, env=p.ENV, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    return child.pid


def deadline_test():
    nonce = "deadbeef1234"
    folder = p.ROOT / ".deployment/finops-runner" / ("deadline-test-" + datetime.now(UTC).strftime("%H%M%S%f"))
    folder.mkdir(parents=True)
    start = datetime.now(UTC)
    s = {"owner_nonce": nonce, "ids": g.owned_ids(nonce), "started_at_utc": start.isoformat(),
        "deadline_utc": (start + timedelta(minutes=60)).isoformat(), "baseline_absent": {k: True for k in g.owned_ids(nonce)},
        "write_intents": list(g.owned_ids(nonce))}
    path = folder / "session.json"
    write(path, s)
    child = subprocess.run([sys.executable, "-m", "scripts.deployment.finops_runner_execute", "--launch-test",
        str(path), "--session-hash", prep.digest(path)], env=p.ENV, cwd=p.ROOT, capture_output=True, text=True, timeout=30)
    g.require(child.returncode == 0, "watchdog_test_launcher_failed")
    pid = json.loads(child.stdout)["worker_pid"]
    end = time.monotonic() + 30
    while not (folder / "watchdog-result.json").exists():
        g.require(time.monotonic() < end, "watchdog_test_deadline_failed")
        threading.Event().wait(0.2)
    report = load(folder / "watchdog-result.json")
    g.require(report["exit_code"] == 0 and report["worker_pid"] == pid and
        report["deleted_resource_ids"] == [s["ids"]["pip"]] and len(report["absence"]) == 6, "watchdog_cleanup_test_failed")
    report.update(launcher_exit_code=child.returncode, cloud_operations=0,
        limitations=["synthetic owned resource through real detached cleanup path, not populated Azure deletion",
            "workstation must remain powered, network-connected and authenticated"])
    write(p.ROOT / "gateway/validation/finops-runner-reaper-test-20261027.json", report)
    print(json.dumps(report))
    return 0


def live_put(arm, s, folder, key, body):
    with lock(folder):
        g.require(not (folder / "cleanup-started.json").exists() and
            datetime.now(UTC) < datetime.fromisoformat(s["deadline_utc"]) - timedelta(minutes=8), "resource_lifetime_gate")
        g.require(arm.get(s["ids"][key]) is None, "resource_collision")
        arm.request("PUT", s["ids"][key], body)


def wait_resource(arm, rid, deadline):
    while True:
        value = arm.get(rid)
        state = (value or {}).get("properties", {}).get("provisioningState")
        if state == "Succeeded":
            return value
        g.require(state not in {"Failed", "Canceled"}, "resource_provisioning_failed")
        g.require(time.monotonic() < deadline, "resource_deployment_deadline")
        threading.Event().wait(3)


def main(*, preparation=None, output=None, ingestion_dataplane=False):
    preparation = preparation or prep.OUT
    output = output or OUT
    report = {"started_at_utc": p.now(), "created_resource_ids": [], "probes": {}, "database_writes": 0,
        "timer_enabled": False, "app_release": False, "activation_cutoff": None, "replay_executed": False}
    s = folder = arm = None
    try:
        g.require(not output.exists(), "existing_execution_requires_read_only_reconciliation")
        e, image = load(preparation), load(build.OUT)
        nonce = e["owner_nonce"]
        profile = "ingestion_dataplane" if ingestion_dataplane else "postgres"
        probe_source = p.ROOT / ("scripts/deployment/finops_dataplane_probe.py" if ingestion_dataplane else "scripts/deployment/finops_private_probe.py")
        supervisor_source = p.ROOT / ("infra/finops-dataplane-probe/entrypoint.py" if ingestion_dataplane else "infra/finops-runner/entrypoint.py")
        g.require(image.get("exit_code") == 0 and image.get("status") == "Succeeded", "immutable_linux_image_required")
        g.require(e["security_scan"]["security_gate_passed"] and e["arm_network_preview"]["what-if"]["exact_create_only_guard_passed"], "fresh_preview_and_scan_required")
        g.require((datetime.now(UTC) - datetime.fromisoformat(e["updated_at_utc"])).total_seconds() < 1800, "preview_stale")
        g.require(load(p.ROOT / "gateway/validation/finops-runner-reaper-test-20261027.json")["exit_code"] == 0, "independent_reaper_test_required")
        report["preservation_before"] = prep.preservation_readback()
        report["network_capacity"] = g.network_capacity(p.get(g.VNET, "2024-05-01"))
        tags = p.get(f"/subscriptions/{g.SUB}/providers/Microsoft.Network/locations/southeastasia/serviceTags", "2024-05-01")
        required = {"AzureActiveDirectory", "AzureContainerRegistry.SoutheastAsia", "Storage.SoutheastAsia"}
        if ingestion_dataplane:
            required.add("AzureMonitor")
        names = {x["name"] for x in tags["values"]}
        g.require(required <= names, "regional_service_tags_unavailable")
        report["service_tags_verified"] = sorted(required)
        # Source content and checked IaC must still match, not only old booleans.
        template_path = p.ROOT / e["network_template"]["path"]
        template = load(template_path)
        prep.guard_network(template, nonce, profile=profile)
        g.require(prep.digest(template_path) == e["network_template"]["sha256"] == e["security_scan"]["artifacts_sha256"]["network.arm.json"], "network_artifact_changed")
        g.require(prep.digest(probe_source) == image["source_probe_sha256"] and
            prep.digest(supervisor_source) == image["source_entrypoint_sha256"], "reviewed_probe_changed")
        folder = p.ROOT / ".deployment/finops-runner" / nonce / "execution"
        folder.mkdir(exist_ok=False)
        start = datetime.now(UTC)
        s = {"owner_nonce": nonce, "ids": g.owned_ids(nonce), "started_at_utc": start.isoformat(),
            "deadline_utc": (start + timedelta(minutes=60)).isoformat(), "image": image["immutable_image"],
            "probe_hash": image["source_probe_sha256"], "baseline_absent": {}, "write_intents": list(g.owned_ids(nonce)),
            "controller_sha256": prep.digest(Path(__file__)), "guard_sha256": prep.digest(Path(g.__file__)),
            "preparation_sha256": prep.digest(preparation), "image_evidence_sha256": prep.digest(build.OUT),
            "network_profile": profile}
        arm = Arm(s)
        for key, rid in s["ids"].items():
            g.require(arm.get(rid) is None, "baseline_collision")
            s["baseline_absent"][key] = True
        report.update(owner_nonce=nonce, ids=s["ids"], deadline_utc=s["deadline_utc"], immutable_image=s["image"],
            build_run_id=image["run_id"], baseline_at_utc=p.now(), inbound=e["network_template"]["inbound"])
        session = folder / "session.json"
        write(session, s)
        session_hash = prep.digest(session)
        report["watchdog_pid"] = launch_watchdog(session, session_hash)
        end = time.monotonic() + 30
        while not (folder / "watchdog-ready.json").exists():
            g.require(time.monotonic() < end, "watchdog_not_ready")
            threading.Event().wait(0.2)
        ready = load(folder / "watchdog-ready.json")
        g.require(ready["pid"] == report["watchdog_pid"] and ready["session_sha256"] == session_hash and
            ready["code_sha256"] == s["controller_sha256"] and ready["guard_sha256"] == s["guard_sha256"] and
            ready["ids"] == s["ids"], "watchdog_attestation_failed")
        report["independent_watchdog_ready"] = ready
        write(output, report)
        # ARM direct PUTs use ONLY the exact four resources in the fresh preview;
        # never PUT the parent VNet or a complete-mode deployment.
        for key in ("pip", "nsg", "nat", "subnet"):
            resource = next(r for r in template["resources"] if r["type"].lower().endswith({"pip": "/publicipaddresses", "nsg": "/networksecuritygroups", "nat": "/natgateways", "subnet": "/subnets"}[key]))
            body = {k: v for k, v in resource.items() if k not in {"type", "apiVersion", "name", "dependsOn"}}
            live_put(arm, s, folder, key, body)
            report["created_resource_ids"].append(s["ids"][key])
            write(output, report)
            verify_owned(wait_resource(arm, s["ids"][key], time.monotonic() + 180), key, s)
        spec = importlib.util.spec_from_file_location("reviewed_probe_supervisor", supervisor_source)
        supervisor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(supervisor)
        for phase in (("ingestion",) if ingestion_dataplane else ("ingestion", "api")):
            other = "api" if phase == "ingestion" else "ingestion"
            g.require(arm.get(s["ids"][other]) is None, "other_identity_group_not_absent")
            group = prep.group_resource(nonce, phase, s["image"], s["probe_hash"])
            g.guard_probe_group(group, nonce=nonce, phase=phase, image=s["image"], source_hash=s["probe_hash"], prior_group_absent=True)
            path = folder / (phase + ".arm.json")
            write(path, prep.group_template(nonce, phase, s["image"], s["probe_hash"]))
            # Validate and exact create-only preview the bound single-MI group.
            preview = {}
            baseline = p.cli(["resource", "list", "--resource-group", "IDS-TOKEN-EXCHANGE-POC", "--query", "[].id"])
            for action in ("validate", "what-if"):
                args = [p.AZ, "deployment", "group", action, "--resource-group", "IDS-TOKEN-EXCHANGE-POC",
                    "--name", "finops-" + nonce + "-" + phase, "--mode", "Incremental", "--template-file", str(path),
                    "--subscription", g.SUB, "--only-show-errors", "-o", "json"]
                if action == "what-if": args += ["--no-pretty-print"]
                child = subprocess.run(args, capture_output=True, text=True, env=p.ENV, timeout=180)
                preview[action] = {"exit_code": child.returncode, "error_codes": sorted(c for c in ERROR_CODES if c in child.stdout or c in child.stderr)}
                if child.returncode == 0:
                    value = json.loads(child.stdout)
                    if action == "what-if": preview[action]["exact_create_only_guard_passed"] = g.guard_what_if(value, nonce, phase, baseline_ids=baseline)
            report.setdefault("group_previews", {})[phase] = preview
            write(output, report)
            g.require(all(x["exit_code"] == 0 for x in preview.values()), "bound_group_validation_failed")
            body = {k: v for k, v in group.items() if k not in {"id", "type", "apiVersion", "name"}}
            # Ten minutes includes group provisioning; supervisor separately bounds SQL.
            end = time.monotonic() + 600
            live_put(arm, s, folder, phase, body)
            report["created_resource_ids"].append(s["ids"][phase])
            write(output, report)
            value = wait_resource(arm, s["ids"][phase], end)
            verify_owned(value, phase, s)
            while True:
                instance = value["properties"]["containers"][0].get("properties", {}).get("instanceView", {})
                state = instance.get("currentState", {})
                g.require(instance.get("restartCount", 0) == 0, "unexpected_probe_restart")
                if state.get("state") == "Terminated": break
                g.require(time.monotonic() < end, "probe_ten_minute_deadline")
                threading.Event().wait(3)
                value = arm.get(s["ids"][phase])
            logs = arm.request("GET", s["ids"][phase], action="/containers/probe/logs")
            content = logs.get("content", "")
            result = supervisor.sanitize(content, state.get("exitCode"))
            report["probes"][phase] = {"os_exit_code": state.get("exitCode"), "sanitized_result": result,
                "probe_exit_code": 0 if result["status"] in {"verified_read_only_snapshot", "verified_data_plane"} else 2, "finished_at_utc": p.now(),
                "arm_logs_nonempty": bool(content.strip()), "arm_logs_bytes": len(content.encode()),
                "arm_logs_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "session_sha256": session_hash, "image": s["image"], "probe_sha256": s["probe_hash"],
                "state": state.get("state"), "restart_count": instance.get("restartCount", 0)}
            # Persist and show the bounded result BEFORE deletion, even on failure.
            write(output, report)
            print(json.dumps({"phase": phase, **report["probes"][phase]}), flush=True)
            g.require(bool(content.strip()), "probe_arm_logs_empty")
            verify_owned(arm.get(s["ids"][phase]), phase, s)
            arm.delete(s["ids"][phase])
            report["probes"][phase]["group_absent_http_404_at_utc"] = p.now()
            write(output, report)
        g.require(all(x["probe_exit_code"] == 0 for x in report["probes"].values()), "private_database_probe_blocked")
        report["exit_code"] = 0
    except Exception as exc:
        report.update(exit_code=2, reason=str(exc) if isinstance(exc, g.GuardBlocked) else "sanitized_execution_failure")
    finally:
        if arm is not None and s is not None and folder is not None:
            report["cleanup"] = cleanup(s, folder, arm)
            report["arm_events"] = arm.events
            if report["cleanup"]["exit_code"]:
                report["exit_code"] = 2
        try:
            report["preservation_after"] = prep.preservation_readback()
        except Exception:
            report["preservation_after"] = {"verified": False}
        report["finished_at_utc"] = p.now()
        # A guard on an existing execution must not overwrite its evidence.
        if report.get("reason") != "existing_execution_requires_read_only_reconciliation":
            write(output, report)
        print(json.dumps({k: report.get(k) for k in ("exit_code", "reason", "created_resource_ids", "probes", "cleanup", "finished_at_utc")}))
    return report["exit_code"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved", action="store_true")
    parser.add_argument("--test-detached-cleanup", action="store_true")
    parser.add_argument("--watchdog", type=Path)
    parser.add_argument("--launch-test", type=Path)
    parser.add_argument("--session-hash")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--cleanup-owned-session", type=Path)
    args = parser.parse_args()
    if args.cleanup_owned_session:
        raise SystemExit(reconcile_cleanup(args.cleanup_owned_session, args.session_hash))
    if args.watchdog:
        raise SystemExit(watchdog(args.watchdog, args.session_hash, synthetic=args.synthetic))
    if args.launch_test:
        print(json.dumps({"worker_pid": launch_watchdog(args.launch_test, args.session_hash, synthetic=True)}))
    elif args.test_detached_cleanup:
        raise SystemExit(deadline_test())
    elif args.execute_approved:
        raise SystemExit(main())
    else:
        parser.error("explicit execution or test mode required")