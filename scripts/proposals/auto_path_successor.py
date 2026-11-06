"""Fresh cm38-bound successor. Historical executors are NEVER invoked/rebound.

baseline: GET-only capture, no window. freeze: offline, AFTER parent readiness
review. Every subsequent wire stage requires a second exact-package independent
parent review. There is deliberately no command chaining activation or Send.
Cleanup is expiry-independent; ambiguous writes permanently consume their stage.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import json
import multiprocessing
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request
import uuid
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from scripts.deployment import auto_diagnostic_stage as core
from scripts.deployment import customer_send_release as customer

a, p = core.a, core.p
ROOT = p.rt.ROOT
NODE = "C:/Program Files/nodejs/node.exe"
OLD = a.HOME / "scoring-diagnostic06"
CUSTOMER = "DOCKER|pocidstokenexacr.azurecr.io/aiflux-customer@sha256:5f55df7d5fbc094f37011906c503e96b8c01e329978d6bca9ac9a7d8318eb589"
GLOBAL_SHA = "936a862488c18ea2f11d27bfbe99f653b26edead85546eda171cdb7229600d31"
DIAG_SHA = "1897a95092b04282ae75b30194a5c7f0915230235d35114fa03dd3c1464df930"
GLOBAL_URL = "https://management.azure.com" + p.APIM + "/policies/policy?api-version=" + p.VERSION
STAGES = ("diagnostic-put", "global-put", "online", "reserve-browser", "offline", "global-restore", "diagnostic-restore")
CLEANUP = STAGES[4:]
require = a.require


def now():
    return datetime.now(UTC)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write(folder, name, value):
    """Exclusive durable evidence: never overwrite even on failed/unknown outcome."""
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, indent=2).encode()
    with (folder / name).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def load(folder, name):
    return json.loads((folder / name).read_bytes())


def sources():
    paths = {* (ROOT / "scripts/deployment").glob("*.py"),
             * (ROOT / "scripts/proposals").glob("auto_path*"),
             ROOT / "scripts/proposals/auto_global_path_exception.mjs",
             ROOT / "tests/unit/test_auto_path_successor.py",
             ROOT / "tests/auto_path_browser.test.mjs",
             ROOT / "docs/auto-path-successor-20261029.md",
             OLD / "diagnostic.xml",
             a.HOME / "scoring-diagnostic02/read_only_export_audit.py"}
    # Bind current UI, not historical06's obsolete manifest source hashes.
    paths |= {ROOT / e["path"] for e in customer.retained()["entries"]}
    return {f.relative_to(ROOT).as_posix(): p.sha(f) for f in sorted(paths) if f.is_file()}


def expected_baseline():
    expected = deepcopy(a.load(a.HOME / "protected-before.json"))
    expected["runtime"]["sites"]["customer"]["image"] = CUSTOMER
    return expected


def guard_baseline(actual, extra):
    require(len(actual) == 13 and actual == expected_baseline(), "full13_ONLY_approved_cm38_customer_image")
    require(extra == a.load(a.HOME / "supplemental-before.json"), "all_supplemental_exact")


def verify_formats(formats, raw):
    """Known-expression exact raw verification plus independently exported XML."""
    spec = importlib.util.spec_from_file_location("successor_exact_export", a.HOME / "scoring-diagnostic02/read_only_export_audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # A raw candidate may have APIM's literal C# quote representation; use its
    # separately bound normal XML reference, never guess arbitrary delimiters.
    reference = core.tree(raw)
    module.verify(formats["rawxml"]["body"]["properties"]["value"], reference, core)
    require(core.signature(core.tree(formats["xml"]["body"]["properties"]["value"], exported=True))
            == core.signature(reference), "both_policy_formats_exact")


def policy_state(formats, folder, kind):
    """Finite known originals/candidates only; never adopt observed drift."""
    for state in ("original", "candidate"):
        reference = folder / (kind + "-" + state + "-reference.xml")
        if kind == "diagnostic" and state == "candidate":
            reference = folder / "diagnostic-candidate.xml"
        if not reference.exists():
            continue
        try:
            verify_formats(formats, reference.read_bytes())
            return state
        except (RuntimeError, ValueError, ET.ParseError):
            continue
    raise RuntimeError("unknown_" + kind + "_policy_STOP_NO_CLOBBER")


def normalize_baseline(actual, extra, formats, original, state):
    value = deepcopy(actual)
    observed = formats["rawxml"]["body"]["properties"]["value"].encode()
    require(value["apim"]["global"] == digest(observed), "full13_global_bound_to_verified_actual_raw")
    require(state in ("original", "candidate"), "finite_global_state")
    if state == "original":
        require(observed == original, "original_global_RAW_bytes_exact")
    value["apim"]["global"] = expected_baseline()["apim"]["global"]
    guard_baseline(value, extra)
    return value


def guard_owned_metadata(owned, saved, online):
    """Only the independently observed online boolean may change on API2."""
    require(type(online) is bool, "revision_list_online_boolean")
    actual, expected = deepcopy(owned), deepcopy(saved)
    if "isOnline" in expected["properties"]:
        require(type(expected["properties"]["isOnline"]) is bool
                and expected["properties"]["isOnline"] is False,
                "captured_owned_revision_offline_boolean")
        require(actual["properties"].get("isOnline") is online,
                "owned_online_matches_actual_revision_list")
        actual["properties"]["isOnline"] = False
    require(actual == expected, "owned_revision_metadata_exact_except_verified_online")


def stage_capture(folder, stage):
    """Fresh complete protected state, actual policy states and final ETags."""
    saved = load(folder, "baseline.json")
    require(a.original_bindings() == saved["state_owner"], "project_state185_exact")
    p.require_no_competing_workers(p.backend.workers())
    reads = core.Reads()
    with customer.read_transport():
        actual = p.release.snapshot()
        extra = a.v.supplemental(actual)
        head = p.backend.blob_head()
    require(all(head[k] == saved["remote_head"][k] for k in a.HEAD_KEYS)
            and head["status"] == 200 and head["lease_state"] == "available"
            and head["lease_status"] == "unlocked", "current_runtime111_remote_head_exact")
    inherited, _ = core.inheritance(reads)
    global_formats = {f: reads.arm("/policies/policy?format=" + f) for f in ("rawxml", "xml")}
    diagnostic_formats = {f: reads.policy(";rev=2", f) for f in ("rawxml", "xml")}
    global_state = policy_state(global_formats, folder, "global")
    diag_state = policy_state(diagnostic_formats, folder, "diagnostic")
    normalize_baseline(actual, extra, global_formats, (folder / "global-original.rawxml").read_bytes(), global_state)
    key = "/policies/policy?format=xml"
    # Only the independently verified exact temporary global policy may differ.
    normalized = deepcopy(inherited)
    require(normalized[key] == global_formats["xml"], "inherited_global_actual_read_stable")
    normalized[key] = saved["inheritance"][key]
    require(normalized == saved["inheritance"], "all_other_inherited_context_exact")
    current, _ = reads.get("")
    require(customer.fs.sha(current) == saved["current_api_sha256"], "all_current1_metadata_exact")
    owned, etag = reads.get(";rev=2")
    flat, _ = reads.get("/revisions")
    require(not flat.get("nextLink"), "complete_revisions")
    rows = [p.summarize_revision(r) for r in flat["value"]]
    expected = deepcopy(saved["revisions"])
    target = [r for r in rows if r["revision"] == "2"]
    require(len(target) == 1 and type(target[0]["is_online"]) is bool, "actual_online_boolean")
    online = target[0]["is_online"]
    for row in expected:
        if row["revision"] == "2":
            row["is_online"] = online
    require(rows == expected and target[0]["is_current"] is False, "current1_and_owned2_flags_exact")
    guard_owned_metadata(owned, saved["owned"], online)
    # Fetch mutation ETag LAST and reject any policy drift during collection.
    if stage.startswith("global-"):
        last = reads.arm("/policies/policy?format=rawxml")
        require(last == global_formats["rawxml"], "fresh_global_candidate_ETag_stable")
        etag = last["etag"]
    elif stage.startswith("diagnostic-"):
        last = reads.policy(";rev=2", "rawxml")
        require(last == diagnostic_formats["rawxml"], "fresh_diagnostic_ETag_stable")
        etag = last["etag"]
    else:
        last, etag = reads.get(";rev=2")
        require(last == owned, "fresh_owned_ETag_stable")
    a.valid_etag(etag)
    require(a.original_bindings() == saved["state_owner"], "stable_project_state")
    result = {"at_utc": now().isoformat(), "etag": etag, "online": online,
              "global_state": global_state, "diagnostic_state": diag_state,
              "all13_supplemental_exact_except_bound_temporary_global": True,
              "both_policy_formats_exact": True, "current1_exact": True,
              "global_raw_sha256": digest(global_formats["rawxml"]["body"]["properties"]["value"].encode()),
              "diagnostic_raw_sha256": digest(diagnostic_formats["rawxml"]["body"]["properties"]["value"].encode()),
              "state_owner": saved["state_owner"], "remote_head": head}
    return result, reads.token


def capture():
    """Original normal global/full13 + owned offline revision; GET-only."""
    p.require_no_competing_workers(p.backend.workers())
    customer.login.account()
    owner = a.original_bindings()
    reads = core.Reads()
    with customer.read_transport():
        baseline = p.release.snapshot()
        extra = a.v.supplemental(baseline)
        head = p.backend.blob_head()
    guard_baseline(baseline, extra)
    require(head["status"] == 200 and head["lease_state"] == "available"
            and head["lease_status"] == "unlocked", "remote_state_unlocked")
    flat, _ = reads.get("/revisions")
    require(not flat.get("nextLink"), "complete_revision_collection")
    rows = [p.summarize_revision(r) for r in flat["value"]]
    expected = deepcopy(a.load(a.HOME / "offline-correction02/revisions-before.json"))
    for row in expected:
        if row["revision"] == "2":
            row["is_online"] = False
    require(rows == expected, "owned2_offline_noncurrent_current1_unchanged")
    owned, _ = reads.get(";rev=2")
    require(owned["id"].lower() == a.RID.lower()
            and owned["properties"]["apiRevisionDescription"] == p.expected_body(a.SELECTION)["properties"]["apiRevisionDescription"]
            and owned["properties"]["subscriptionRequired"] is True, "same_owned_nonce_subscription_required")
    current, _ = reads.get("")
    prior = a.load(OLD / "offline-after-capture.json")
    require(customer.fs.sha(current) == prior["current_api_sha256"], "current1_full_metadata_exact")
    inherited, _ = core.inheritance(reads)
    old_inherited = a.load(a.HOME / "scoring-diagnostic01/prepare-capture.json")["inheritance"]
    require(inherited == old_inherited, "all_original_inheritance_exact")
    global_formats = {fmt: reads.arm("/policies/policy?format=" + fmt) for fmt in ("rawxml", "xml")}
    diag_formats = {fmt: reads.policy(";rev=2", fmt) for fmt in ("rawxml", "xml")}
    require(digest(global_formats["xml"]["body"]["properties"]["value"].encode()) == GLOBAL_SHA,
            "original_global_export_exact")
    require(p.sha(OLD / "diagnostic.xml") == DIAG_SHA, "frozen06_policy_fixture_exact_not_its_old_source_guards")
    verify_formats(diag_formats, (OLD / "diagnostic.xml").read_bytes())
    for formats in (global_formats, diag_formats):
        for item in formats.values():
            require(item["status"] == 200, "policy_exists")
            a.valid_etag(item["etag"])
    require(a.original_bindings() == owner, "stable_project185_owner")
    return {"at_utc": now().isoformat(), "baseline": baseline, "supplemental": extra,
            "state_owner": owner, "remote_head": head, "revisions": rows,
            "current_api_sha256": customer.fs.sha(current), "owned": owned,
            "inheritance": inherited, "global_formats": global_formats, "diagnostic_formats": diag_formats}


def raw_condition(raw, old, new):
    """Splice exactly one WHOLE known condition, preserving every other byte."""
    tokens = {"&": "(?:&amp;|&)", "<": "(?:&lt;|<)", ">": "(?:&gt;|>)"}
    pattern = 'condition="' + "".join(tokens.get(c, re.escape(c)) for c in old) + '"'
    matches = list(re.finditer(pattern, raw))
    require(len(matches) == 1, "one_known_global_raw_condition")
    match = matches[0]
    # rawxml wire representation uses valid XML; surrounding original raw is
    # untouched. Other C# expressions may use APIM's observed raw representation.
    replacement = 'condition="' + escape(new, {'"': "&quot;"}) + '"'
    return raw[:match.start()] + replacement + raw[match.end():]


def render(captured, start, end, nonce):
    require(re.fullmatch("[a-f0-9]{32}", nonce) is not None, "fresh_counter_nonce")
    old = a.load(OLD / "manifest.json")["nonce"]
    require(nonce != old, "NEVER_replenish_or_replay_consumed06_counter")
    body = {"globalOriginal": captured["global_formats"]["xml"]["body"]["properties"]["value"],
            "diagnosticOriginal": (OLD / "diagnostic.xml").read_bytes().decode(),
            "window": {"start": start, "end": end}}
    run = subprocess.run([NODE, str(Path(__file__).with_name("auto_path_render.mjs"))],
                         input=json.dumps(body), capture_output=True, text=True, encoding="utf-8", timeout=20)
    require(run.returncode == 0, "offline_renderer_failed")
    result = json.loads(run.stdout)
    global_root = core.tree(body["globalOriginal"], exported=True)
    before = global_root.find("./inbound/choose/when").attrib["condition"]
    candidate_root = core.tree(result["global"], exported=True)
    after = candidate_root.find("./inbound/choose/when").attrib["condition"]
    raw = captured["global_formats"]["rawxml"]["body"]["properties"]["value"]
    global_candidate = raw_condition(raw, before, after).encode()
    # A NEW, expressly approved single attempt gets its own quota identity.
    # Only the two exact diagnostic counter literals change; original explicit
    # subscription/model/project counter namespaces remain byte-identical.
    needle = "auto-diagnostic:" + old
    require(result["diagnostic"].count(needle) == 2, "exact_two_owned_diagnostic_counter_spans")
    diagnostic = result["diagnostic"].replace(needle, "auto-diagnostic:" + nonce).encode()
    return {"global-candidate.rawxml": global_candidate, "global-candidate-reference.xml": ET.tostring(candidate_root),
            "diagnostic-candidate.xml": diagnostic,
            "global-original.rawxml": raw.encode(),
            "global-original-reference.xml": ET.tostring(global_root),
            "diagnostic-original.rawxml": captured["diagnostic_formats"]["rawxml"]["body"]["properties"]["value"].encode(),
            "diagnostic-original-reference.xml": (OLD / "diagnostic.xml").read_bytes()}


def fresh_time(value, seconds):
    timestamp = datetime.fromisoformat(value)
    require(timestamp.tzinfo is not None and timedelta(0) <= now() - timestamp < timedelta(seconds=seconds), "fresh_aware_UTC_evidence")


def parent_review(folder, name, binding):
    review = load(folder, name)
    require(review.get("approved") is True and review.get("independent_native_review") is True
            and review.get("binding_sha256") == binding, "actual_independent_parent_review_required")
    path = (folder / review["transcript"]).resolve()
    require(path.is_relative_to(folder.resolve()) and path.is_file()
            and p.sha(path) == review["transcript_sha256"], "actual_review_transcript_exact")
    require(isinstance(review.get("reviewer_pid"), int) and review["reviewer_pid"] > 0
            and review["reviewer_pid"] != os.getpid(), "independent_reviewer_identity")
    return review


def baseline(folder):
    require(not folder.exists(), "existing_successor_NEVER_reprepare")
    folder.mkdir()
    write(folder, "read-intent.json", {"at_utc": now().isoformat(), "configuration_writes": 0})
    frozen = sources()
    result = capture()
    require(frozen == sources(), "stable_current_sources")
    write(folder, "baseline.json", result)
    write(folder, "sources.json", frozen)
    write(folder, "baseline-binding.json", {"baseline_sha256": p.sha(folder / "baseline.json"),
          "sources_sha256": p.sha(folder / "sources.json"), "window_frozen": False,
          "status": "FRESH_GET_ONLY_PARENT_READINESS_REVIEW_REQUIRED"})


def freeze(folder, tests):
    require(not (folder / "manifest.json").exists(), "existing_window_NEVER_refresh")
    binding = p.sha(folder / "baseline-binding.json")
    bound = load(folder, "baseline-binding.json")
    require(bound["baseline_sha256"] == p.sha(folder / "baseline.json")
            and bound["sources_sha256"] == p.sha(folder / "sources.json"), "readiness_baseline_binding_exact")
    readiness = parent_review(folder, "parent-readiness-review.json", binding)
    fresh_time(readiness["at_utc"], 1800)
    require(readiness.get("browser_actionability_proven") is True
            and readiness.get("crash_cleanup_supervisor_reviewed") is True,
            "actual_parent_browser_and_crash_cleanup_readiness_required")
    require(load(folder, "sources.json") == sources(), "source_bound_before_freeze")
    captured = load(folder, "baseline.json")
    fresh_time(captured["at_utc"], 1800)
    receipt = ET.parse(tests).getroot()
    cases = receipt.findall(".//testcase")
    require(len(cases) >= 20 and not receipt.findall(".//failure") and not receipt.findall(".//error")
            and not receipt.findall(".//skipped"), "actual_successor_test_receipt")
    browser_tests = ROOT / ".deployment/auto-path-browser-offline-final-20261029.xml"
    browser_root = ET.parse(browser_tests).getroot()
    require(len(browser_root.findall(".//testcase")) >= 13 and not browser_root.findall(".//failure")
            and not browser_root.findall(".//error") and not browser_root.findall(".//skipped"), "actual_browser_test_receipt")
    start = now().replace(microsecond=0)
    end = start + timedelta(minutes=30)
    window = {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")}
    nonce = uuid.uuid4().hex
    artifacts = render(captured, **window, nonce=nonce)
    for name, value in artifacts.items():
        write(folder, name, value)
    write(folder, "manifest.json", {"at_utc": now().isoformat(), **window, "nonce": nonce,
          "baseline_binding_sha256": binding, "baseline_sha256": p.sha(folder / "baseline.json"),
          "sources": sources(), "artifacts": {k: digest(v) for k, v in artifacts.items()},
          "tests": {"path": tests.resolve().relative_to(ROOT).as_posix(), "sha256": p.sha(tests)},
          "browser_tests": {"path": browser_tests.relative_to(ROOT).as_posix(), "sha256": p.sha(browser_tests)},
          "stages": list(STAGES), "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0,
          "historical_attempts_consumed": True, "cleanup_expiry_independent": True,
          "parent_exit_deadline_supervisor_implemented": True,
          "laptop_shutdown_or_network_loss_cleanup_guaranteed": False,
          "status": "EXACT_PACKAGE_PARENT_REVIEW_REQUIRED_NO_MUTATION"})


def check(folder, stage):
    require(stage in STAGES, "finite_stage")
    manifest = load(folder, "manifest.json")
    require(manifest["sources"] == sources(), "exact_current_source_binding")
    require(p.sha(folder / "baseline.json") == manifest["baseline_sha256"], "immutable_baseline")
    require(p.sha(folder / "baseline-binding.json") == manifest["baseline_binding_sha256"], "immutable_readiness_binding")
    require(all(p.sha(folder / name) == sha for name, sha in manifest["artifacts"].items()), "immutable_artifacts")
    require(p.sha(ROOT / manifest["tests"]["path"]) == manifest["tests"]["sha256"], "immutable_test_receipt")
    require(p.sha(ROOT / manifest["browser_tests"]["path"]) == manifest["browser_tests"]["sha256"], "immutable_browser_test_receipt")
    review = parent_review(folder, "parent-review.json", p.sha(folder / "manifest.json"))
    require(review.get("stages") == list(STAGES), "review_ALL_writes_reservation_AND_restorations")
    require(not (folder / (stage + "-intent.json")).exists(), "stage_consumed_NEVER_retry")
    if stage not in CLEANUP:
        fresh_time(review["at_utc"], 1800)
        require(datetime.fromisoformat(manifest["start"]) <= now()
                < datetime.fromisoformat(manifest["end"]) - timedelta(minutes=5), "fixed_window_cleanup_reserve")
        require(not any((folder / (s + "-intent.json")).exists() for s in CLEANUP), "cleanup_started_no_activation")
    return manifest


def stage_request(stage, etag, token, body):
    require(stage in STAGES and stage != "reserve-browser", "finite_wire_stage")
    url = GLOBAL_URL if stage.startswith("global-") else core.POLICY_URL if stage.startswith("diagnostic-") else a.URL
    return Request(url, method="PATCH" if stage in ("online", "offline") else "PUT", data=body,
                   headers={"Authorization": "Bearer " + token, "If-Match": a.valid_etag(etag),
                            "Content-Type": "application/json", "Accept": "application/json"})


def wire_child(connection, stage, etag, token, body):
    try:
        try:
            with a.opener(p.rt.CA).open(stage_request(stage, etag, token, body), timeout=45) as response:
                result = a.safe_http(response.status, response.headers)
        except HTTPError as exc:
            result = a.safe_http(exc.code, exc.headers)
            exc.close()
        connection.send(result)
    except Exception as exc:
        connection.send({"transport_error": type(exc).__name__, "outcome": "UNKNOWN_NO_RETRY"})
    finally:
        connection.close()


def once(stage, etag, token, body):
    ctx = multiprocessing.get_context("spawn")
    receive, send = ctx.Pipe(duplex=False)
    child = ctx.Process(target=wire_child, args=(send, stage, etag, token, body))
    try:
        child.start()
        send.close()
        return receive.recv() if receive.poll(60) else {"outcome": "UNKNOWN_TIMEOUT_NO_RETRY"}
    finally:
        if child.pid is not None:
            if child.is_alive():
                child.terminate()
            child.join(5)
            if child.is_alive():
                child.kill()
                child.join(5)
        receive.close()
        send.close()


@contextmanager
def stage_lock(folder):
    # Windows kernel lock releases on process crash; no stale lock deletion or
    # age-based ownership adoption. One wire/cleanup stage at a time.
    path = folder / "stage.lock"
    try:
        with path.open("xb") as stream:
            stream.write(b"0")
    except FileExistsError:
        pass
    with path.open("r+b") as stream:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def execute(folder, stage):
    with stage_lock(folder):
        return execute_locked(folder, stage)


def execute_locked(folder, stage):
    manifest = check(folder, stage)
    before, token = stage_capture(folder, stage)
    write(folder, stage + "-before.json", before)
    if stage not in CLEANUP:
        supervisor_live(folder)
        prior = {"global-put": "diagnostic-put", "online": "global-put", "reserve-browser": "online"}.get(stage)
        if prior:
            proof = load(folder, prior + "-verification.json")
            require(proof["manifest_sha256"] == p.sha(folder / "manifest.json"), "previous_stage_actual_verification")
    conditions = {
        "diagnostic-put": (False, "original", "original"),
        "global-put": (False, "original", "candidate"),
        "online": (False, "candidate", "candidate"),
        "reserve-browser": (True, "candidate", "candidate"),
    }
    if stage in conditions:
        require((before["online"], before["global_state"], before["diagnostic_state"]) == conditions[stage], "exact_stage_transition")
    elif stage != "offline":
        require(before["online"] is False, "restore_ONLY_while_owned_revision_offline")
    if stage == "diagnostic-restore":
        require(before["global_state"] == "original", "global_restored_BEFORE_diagnostic_restore")
    check(folder, stage)
    fresh_time(before["at_utc"], 30)
    body = body_for(folder, stage)
    intent = {"at_utc": now().isoformat(), "pid": os.getpid(), "stage": stage,
              "manifest_sha256": p.sha(folder / "manifest.json"), "review_sha256": p.sha(folder / "parent-review.json"),
              "etag": before["etag"], "body_sha256": digest(body), "attempt_budget": 1,
              "scoring_budget": 1, "completion_budget": 0, "retry_budget": 0,
              "fixed_text": core.TEXT, "subscription": core.SUBSCRIBER, "IP": "167.103.66.248",
              "model": "gpt-5.4-mini", "path": core.CHAT_PATH, "end": manifest["end"]}
    write(folder, stage + "-intent.json", intent)
    if stage == "reserve-browser":
        # Parent alone executes normal authenticated UI with URL-only routing.
        write(folder, "browser-reservation.json", {**intent, "send_executed": False,
              "scope": "AUTO_PATH_SUCCESSOR_ONE_ATTEMPT",
              "browser_source_sha256": p.sha(Path(__file__).with_name("auto_path_browser.mjs")),
              "auth": "NORMAL_UI_ONLY_NO_HEADERS_KEYS_OR_STORAGE_INSPECTION"})
        return
    already = ((stage == "offline" and not before["online"])
               or (stage == "global-restore" and before["global_state"] == "original")
               or (stage == "diagnostic-restore" and before["diagnostic_state"] == "original"))
    result = {"outcome": "ALREADY_ORIGINAL_READ_ONLY_NO_WIRE"} if already else once(stage, before["etag"], token, body)
    write(folder, stage + "-result.json", {"at_utc": now().isoformat(), **result, "no_retry": True})
    after, _ = stage_capture(folder, stage)
    write(folder, stage + "-after.json", after)
    # Ambiguous write can be reconciled by actual exact readback, NEVER replayed.
    wanted = {"diagnostic-put": ("diagnostic_state", "candidate"), "global-put": ("global_state", "candidate"),
              "online": ("online", True), "offline": ("online", False),
              "global-restore": ("global_state", "original"), "diagnostic-restore": ("diagnostic_state", "original")}[stage]
    require(after[wanted[0]] == wanted[1], "wire_outcome_not_verified_STOP_NO_RETRY")
    if stage == "diagnostic-restore":
        require(after["diagnostic_raw_sha256"] == digest((folder / "diagnostic-original.rawxml").read_bytes()),
                "restored_diagnostic_original_RAW_bytes_exact")
    write(folder, stage + "-verification.json", {**after, "manifest_sha256": p.sha(folder / "manifest.json"),
          "intent_sha256": p.sha(folder / (stage + "-intent.json")), "wire_result": result})


def body_for(folder, stage):
    if stage in ("online", "offline"):
        return b'{"properties":{"isOnline":true}}' if stage == "online" else a.BODY
    if stage == "reserve-browser":
        return b""
    name = {"diagnostic-put": "diagnostic-candidate.xml", "global-put": "global-candidate.rawxml",
            "global-restore": "global-original.rawxml", "diagnostic-restore": "diagnostic-original.rawxml"}[stage]
    return json.dumps({"properties": {"format": "xml" if name.endswith(".xml") else "rawxml",
                       "value": (folder / name).read_bytes().decode()}}, separators=(",", ":")).encode()


def process_identity(pid):
    require(type(pid) is int and pid > 0, "exact_process_pid")
    command = ("$p=Get-CimInstance Win32_Process -Filter 'ProcessId=" + str(pid)
               + "'; if($p){@{pid=$p.ProcessId;created=$p.CreationDate.ToUniversalTime().ToString('o');"
               "successor=([string]$p.CommandLine -match 'scripts.proposals.auto_path_successor.*supervise')} | ConvertTo-Json -Compress}")
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True,
                            text=True, timeout=20, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def supervisor_live(folder):
    proof = load(folder, "supervisor-ready.json")
    require(proof["manifest_sha256"] == p.sha(folder / "manifest.json")
            and process_identity(proof["identity"]["pid"]) == proof["identity"]
            and proof["identity"]["successor"] is True
            and not (folder / "supervisor-finished.json").exists(), "actual_bound_cleanup_supervisor_running")


def cleanup(folder):
    errors = []
    # Always try safe offline first. No retries, including supervisor/parent race.
    for stage in CLEANUP:
        try:
            if (folder / (stage + "-intent.json")).exists():
                with stage_lock(folder):
                    actual, _ = stage_capture(folder, stage)
                key, value = {"offline": ("online", False), "global-restore": ("global_state", "original"),
                              "diagnostic-restore": ("diagnostic_state", "original")}[stage]
                require(actual[key] == value, "consumed_cleanup_unknown_STOP_NO_RETRY")
            else:
                execute(folder, stage)
        except Exception as exc:
            errors.append({"stage": stage, "error_type": type(exc).__name__})
            # Further restores must never run while offline remains unproven.
            break
    return errors


def supervise(folder):
    # Independently running parent-started process; no activation, no inference.
    # It survives parent process exit, NOT laptop shutdown/network disappearance.
    manifest = check(folder, "diagnostic-put")
    require(not (folder / "supervisor-intent.json").exists(), "one_supervisor_no_relaunch")
    write(folder, "supervisor-intent.json", {"at_utc": now().isoformat(), "pid": os.getpid(),
          "manifest_sha256": p.sha(folder / "manifest.json")})
    identity = process_identity(os.getpid())
    require(identity is not None and identity["successor"] is True, "actual_supervisor_process_identity")
    write(folder, "supervisor-ready.json", {"at_utc": now().isoformat(), "identity": identity,
          "manifest_sha256": p.sha(folder / "manifest.json")})
    # Close at end-3min to leave time for bounded GETs and three one-shot writes.
    deadline = datetime.fromisoformat(manifest["end"]) - timedelta(minutes=3)
    while now() < deadline and not (folder / "cleanup-request.json").exists():
        if (folder / "diagnostic-restore-verification.json").exists():
            break
        time.sleep(1)
    errors = cleanup(folder)
    write(folder, "supervisor-finished.json", {"at_utc": now().isoformat(), "errors": errors,
          "status": "CLEANUP_VERIFIED" if not errors else "CLEANUP_BLOCKED_OWNER_RECONCILE_NO_RETRY"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("baseline", "freeze", "supervise", "cleanup", *STAGES))
    parser.add_argument("--name", required=True)
    parser.add_argument("--tests", type=Path)
    args = parser.parse_args()
    require(re.fullmatch(r"auto-path-successor-20261029T[0-9]{12}Z", args.name) is not None, "exclusive_successor_name")
    folder = ROOT / ".deployment" / args.name
    if args.stage == "baseline":
        baseline(folder)
    elif args.stage == "freeze":
        require(args.tests is not None, "tests_required")
        freeze(folder, args.tests)
    elif args.stage == "supervise":
        supervise(folder)
    elif args.stage == "cleanup":
        errors = cleanup(folder)
        require(not errors, "cleanup_blocked_owner_reconcile_NO_RETRY")
    else:
        execute(folder, args.stage)
    print(json.dumps({"package": folder.relative_to(ROOT).as_posix(), "stage": args.stage,
                      "inference_requests": 0}), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())