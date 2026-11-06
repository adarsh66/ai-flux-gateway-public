"""Review-gated emergency ARM correction. Never invokes Terraform or inference.

prepare-review is entirely offline. execute-reviewed-once belongs to the parent
AFTER independent review; an intent survives failures, timeouts and crashes.
"""
from datetime import UTC, datetime, timedelta
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import xml.etree.ElementTree as ET

from scripts.deployment import auto_revision_validate as v

p = v.p
HOME = v.HOME
OUT = HOME / "arm-offline-correction01"
INTENT = HOME / "arm-take-offline-intent.json"
RID = p.APIM + "/apis/" + p.API + ";rev=2"
URL = "https://management.azure.com" + RID + "?api-version=" + p.VERSION
BODY = b'{"properties":{"isOnline":false}}'
SELECTION = {"revision": "2", "owner_nonce": "a74c955500c9c14b4c8ffe6e9b1da913",
             "baseline_sha256": "90c0e4a501cd5d2c3256b4777e7699d517cb5d8ec5c47186973858001e32e9b7"}
ORIGINAL_SOURCE = "9c678b621b3ae289d7ca9906560a3ee59b0dcacd24b1661391cd3b03b78246c1"
HEAD_KEYS = ("etag", "content_length", "last_modified", "lease_status", "lease_state")
TEST = "tests/unit/test_auto_revision_arm_once.py"
HANDOFF = "docs/auto-revision-arm-once-handoff-20261029.md"
require = p.rt.require


def load(path):
    return json.loads(path.read_bytes())


def save(name, value):
    p.backend.save(OUT, name, value)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def opener(ca):
    tls = ssl.create_default_context(cafile=ca)
    require(tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED, "verified_tls")
    return build_opener(HTTPSHandler(context=tls), NoRedirect())


def valid_etag(etag):
    require(isinstance(etag, str) and 2 < len(etag) <= 1024
            and re.fullmatch(r'(?:W/)?"[\x21\x23-\x7e]+"', etag) is not None,
            "actual_opaque_etag_required")
    return etag


def patch_request(url, etag, token):
    require(url == URL, "revision2_uri_only")
    return Request(url, method="PATCH", data=BODY, headers={
        "Authorization": "Bearer " + token, "If-Match": valid_etag(etag),
        "Content-Type": "application/json", "Accept": "application/json"})


def safe_http(status, headers, error_code=None):
    # Never retain response bodies, Location, tokens, messages or arbitrary headers.
    result = {"http_status": int(status)}
    request_id = headers.get("x-ms-request-id", "")
    if re.fullmatch(r"[a-zA-Z0-9-]{1,128}", request_id):
        result["request_id"] = request_id
    if isinstance(error_code, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", error_code):
        result["arm_error_code"] = error_code
    return result


def patch_wire(url, etag, token, ca):
    """Exactly one opener.open; no SDK pipeline, redirects, polling or retry."""
    request = patch_request(url, etag, token)
    try:
        with opener(ca).open(request, timeout=60) as response:
            return safe_http(response.status, response.headers)
    except HTTPError as exc:
        code = None
        try:
            raw = exc.read(65537)
            if len(raw) <= 65536:
                code = json.loads(raw).get("error", {}).get("code")
        except Exception:
            pass
        finally:
            exc.close()
        return safe_http(exc.code, exc.headers, code)


def patch_child(connection, url, etag, token, ca):
    try:
        connection.send(patch_wire(url, etag, token, ca))
    except Exception as exc:
        connection.send({"transport_error": type(exc).__name__})
    finally:
        connection.close()


def patch_once(etag, token):
    """Spawn isolates the write with a 60-second parent wall-clock watchdog.

    Token travels only in process memory, never command arguments/files/logs.
    Timeout is an ambiguous outcome, NEVER permission to retry.
    """
    valid_etag(etag)
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(target=patch_child, args=(send, URL, etag, token, p.rt.CA))
    try:
        child.start()
        send.close()
        if receive.poll(60):
            return receive.recv()
        return {"transport_error": "WallClockTimeout", "outcome": "unknown_no_retry"}
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


class Reads:
    def __init__(self):
        self.token = p.backend.token("https://management.azure.com/")
        self.http = opener(p.rt.CA)

    def get(self, suffix):
        require(suffix in {"", ";rev=2", "/revisions"}, "exact_read_scope")
        url = "https://management.azure.com" + p.APIM + "/apis/" + p.API + suffix + "?api-version=" + p.VERSION
        with self.http.open(Request(url, headers={"Authorization": "Bearer " + self.token}), timeout=60) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            require(len(raw) <= 8 * 1024 * 1024, "bounded_read")
            return json.loads(raw), response.headers.get("ETag")


def state_owner():
    path = p.ROOT / "terraform.tfstate"
    state = load(path)
    owner = load(HOME / "offline-correction02/state-owner.json")
    require({"lineage": state["lineage"], "serial": state["serial"], "sha256": p.sha(path)} == owner
            and state["lineage"] == p.LINEAGE and state["serial"] == 185
            and not (p.ROOT / ".terraform.tfstate.lock.info").exists(), "state185_bytes_identity_lock")
    resources = [r for r in state["resources"] if r["type"] == "azapi_resource" and r["name"] == "auto_stage_revision"]
    require(len(resources) == 1 and len(resources[0]["instances"]) == 1, "single_existing_state_owner")
    resource = resources[0]
    instance = resource["instances"][0]
    attrs = instance["attributes"]
    require(resource.get("mode") == "managed" and instance.get("index_key") == 0
            and attrs["id"].lower() == RID.lower(), "state_owned_revision2")
    body = attrs["body"]
    if isinstance(body, str):
        body = json.loads(body)
    if isinstance(body, dict) and set(body) == {"type", "value"}:
        require(isinstance(body["type"], list) and body["type"][0] == "object", "azapi_dynamic_object_body")
        body = body["value"]
    require(body == p.expected_body(SELECTION) and body["properties"]["isOnline"] is False
            and body["properties"]["isCurrent"] is False,
            "same_terraform_owner_desired_offline")
    require(not any(r["name"] == "auto_stage_offline" for r in state["resources"]), "no_correction_state_owner")
    return owner


def original_bindings():
    original = load(HOME / "result.json")
    receipt = load(HOME / "execution01/apply-result.json")
    require(original["reservation"] == SELECTION and original["source_sha256"] == ORIGINAL_SOURCE
            and p.release.fs.sha(load(HOME / "sources.json")) == ORIGINAL_SOURCE,
            "original_reservation_source")
    require(receipt["attempts"] == 1 and receipt["exit_code"] == 0
            and receipt["saved_plan_sha256"] == v.PLAN_SHA
            and p.sha(HOME / "offline-revision.tfplan") == v.PLAN_SHA, "original_create_receipt")
    original = load(HOME / "sources.json")
    current = p.sources()
    correction = load(HOME / "offline-correction02/sources.json")
    # The retained correction added a separate default-off Terraform resource.
    # Never misrepresent that reviewed historical delta as original-create bytes.
    require(set(current) == set(original)
            and {name for name in current if current[name] != original[name]} <= {"infra/project-route/auto-staging.tf"}
            and all(current[name] == correction[name] for name in current), "retained_correction_source_binding")
    return state_owner()


def sources():
    # Bind transitive local helper implementations as well as Terraform intent.
    paths = {* (p.rt.ROOT / "scripts/deployment").glob("*.py"),
             p.rt.ROOT / TEST, p.rt.ROOT / HANDOFF}
    paths |= {p.rt.ROOT / name for name in load(HOME / "sources.json")}
    paths |= {HOME / name for name in ("result.json", "sources.json", "execution01/apply-result.json",
        "protected-before.json", "supplemental-before.json", "current-api-metadata.json",
        "offline-correction02/state-owner.json", "offline-correction02/sources.json", "offline-correction02/remote-head-before.json",
        "offline-correction02/revisions-before.json")}
    return {f.relative_to(p.rt.ROOT).as_posix(): p.sha(f) for f in sorted(paths)}


def check_markers(expected):
    actual = p.backend.markers()
    own = INTENT.relative_to(p.rt.ROOT).as_posix()
    require(all(actual.get(k) == digest for k, digest in expected.items())
            and set(actual) - set(expected) <= {own}, "foreign_intent_or_history_drift")
    p.require_no_competing_workers(p.backend.workers())


def check_review(manifest):
    require(manifest["sources"] == sources() and manifest["state_owner"] == original_bindings(), "review_source_state_binding")
    require(not INTENT.exists(), "existing_arm_intent_reconcile_only")
    review = load(OUT / "parent-review.json")
    require(review.get("approved") is True and review.get("independent_native_review") is True
            and review.get("manifest_sha256") == p.sha(OUT / "manifest.json"), "independent_parent_review_required")
    age = datetime.now(UTC) - datetime.fromisoformat(review["at_utc"])
    require(timedelta(0) <= age < timedelta(minutes=30), "fresh_parent_review")
    transcript = OUT / review["transcript"]
    require(transcript.resolve().is_relative_to(OUT.resolve()) and transcript.is_file()
            and p.sha(transcript) == review["transcript_sha256"], "actual_review_transcript_binding")
    test = p.rt.ROOT / manifest["tests"]["path"]
    require(test.resolve().is_relative_to(p.rt.ROOT) and p.sha(test) == manifest["tests"]["sha256"], "test_receipt_changed")
    check_markers(manifest["markers"])


def fresh(reads, label, online):
    started = p.now()
    owner = original_bindings()
    baseline = p.release.snapshot()
    supplement = v.supplemental(baseline)
    save(label + "-protected.json", baseline)
    save(label + "-supplemental.json", supplement)
    require(len(baseline) == 13 and baseline == load(HOME / "protected-before.json")
            and supplement == load(HOME / "supplemental-before.json"), "all13_supplemental_exact")
    flat, _ = reads.get("/revisions")
    require(not flat.get("nextLink") and isinstance(flat.get("value"), list), "complete_flat_revision_list")
    rows = [p.summarize_revision(r) for r in flat["value"]]
    save(label + "-flat-revisions.json", rows)
    expected = load(HOME / "offline-correction02/revisions-before.json")
    # Compare ALL revision rows; only the owned row's online flag may differ.
    expected = json.loads(json.dumps(expected))
    targets = [r for r in expected if r["revision"] == "2"]
    require(len(targets) == 1, "one_owned_revision")
    targets[0]["is_online"] = online
    actual_owned = [r for r in rows if r["revision"] == "2"]
    require(rows == expected and len(actual_owned) == 1 and actual_owned[0]["is_current"] is False
            and actual_owned[0]["is_online"] is online
            and sum(r["revision"] == "1" and r["is_current"] is True and r["is_online"] is True for r in rows) == 1,
            "explicit_revision2_flag_current1_unchanged")
    api, etag = reads.get(";rev=2")
    props = api["properties"]
    require(api["id"].lower() == RID.lower() and props["apiRevision"] == "2"
            and props["apiRevisionDescription"] == p.expected_body(SELECTION)["properties"]["apiRevisionDescription"]
            and props["path"] == "dev/llm/v1" and props["subscriptionRequired"] is True, "live_exact_owned_nonce")
    if online:
        valid_etag(etag)
    current, _ = reads.get("")
    prior = load(HOME / "current-api-metadata.json")
    require({k: current["properties"].get(k) for k in prior} == prior, "current1_metadata_exact")
    head = p.backend.blob_head()
    require({k: head[k] for k in HEAD_KEYS} == {k: load(HOME / "offline-correction02/remote-head-before.json")[k]
            for k in HEAD_KEYS}, "remote_state_head_unchanged")
    require(state_owner() == owner, "state_changed_during_reads")
    evidence = {"at_utc": started, "finished_at_utc": p.now(), "state_owner": owner, "remote_head": head,
                "current_api_sha256": p.release.fs.sha(current), "owned_revision": "2",
                "owner_nonce_matches": True, "etag": etag, "all13_supplemental_exact": True}
    save(label + "-metadata.json", evidence)
    return evidence


def prepare_review(test_path):
    require(not OUT.exists() and not INTENT.exists(), "existing_package_or_intent_no_replay")
    owner = original_bindings()
    path = test_path.resolve()
    require(path.is_relative_to(p.rt.ROOT) and path.is_file(), "workspace_test_receipt")
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    counts = {k: sum(int(n.get(k, 0)) for n in suites) for k in ("tests", "errors", "failures", "skipped")}
    require(counts["tests"] > 0 and not any(counts[k] for k in ("errors", "failures", "skipped")), "clean_actual_fixture_tests")
    p.release.fs.protect(OUT)
    save("manifest.json", {"at_utc": p.now(), "status": "PREPARED_NOT_REVIEWED_NOT_EXECUTED",
         "operation": "direct_ARM_PATCH_NOT_Terraform", "url": URL, "body_sha256": hashlib.sha256(BODY).hexdigest(),
         "sources": sources(), "state_owner": owner, "markers": p.backend.markers(),
         "tests": {"path": path.relative_to(p.rt.ROOT).as_posix(), "sha256": p.sha(path), "counts": counts},
         "live_freshness": "required_after_review_immediately_before_PATCH_not_claimed",
         "cloud_writes": 0, "terraform_applies": 0, "independent_review": False})
    return {"status": "review_ready_NO_PATCH", "manifest_sha256": p.sha(OUT / "manifest.json"),
            "evidence": OUT.relative_to(p.rt.ROOT).as_posix(), "tests": counts}


def execute_reviewed_once():
    manifest = load(OUT / "manifest.json")
    stage, attempted = "review", False
    try:
        check_review(manifest)
        p.persistence.transport()  # Existing strict-TLS READ helper only; not the PATCH transport.
        account = p.rt.cli(["account", "show"])
        require(account["id"] == p.rt.SUB and account["tenantId"] == p.rt.TENANT, "exact_existing_context")
        reads = Reads()
        stage = "fresh_before"
        before = fresh(reads, "before", True)
        check_review(manifest)
        require(datetime.now(UTC) - datetime.fromisoformat(before["at_utc"]) < timedelta(minutes=2), "prepatch_freshness")
        # Exclusive, durable global intent precedes process creation; never removed.
        with INTENT.open("x", encoding="utf-8") as handle:
            json.dump({"at_utc": p.now(), "pid": os.getpid(), "url": URL, "method": "PATCH",
                "manifest_sha256": p.sha(OUT / "manifest.json"), "review_sha256": p.sha(OUT / "parent-review.json"),
                "body_sha256": hashlib.sha256(BODY).hexdigest(), "etag": before["etag"], "attempt_budget": 1,
                "no_retry": True, "no_redirect": True, "wall_clock_seconds": 60,
                "operation": "direct_ARM_NOT_Terraform", "terraform_applies": 0}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        intent_sha = p.sha(INTENT)
        stage, attempted = "patch", True
        result = patch_once(before["etag"], reads.token)
        save("patch-result.json", {"at_utc": p.now(), "attempt_budget_consumed": True, **result, "retry_authorized": False})
        require(result.get("http_status") in {200, 201, 202, 204}, "patch_http_or_transport_failure_STOP_no_retry")
        stage = "fresh_after"
        after = fresh(reads, "after", False)
        require(after["current_api_sha256"] == before["current_api_sha256"], "current1_full_response_changed")
        require(manifest["sources"] == sources() and state_owner() == before["state_owner"]
            and p.sha(INTENT) == intent_sha, "postpatch_source_state_intent_drift")
        check_markers(manifest["markers"])
        save("verification.json", {"at_utc": p.now(), "status": "ARM_offline_readback_verified",
             "revision2_online": False, "revision2_current": False, "current1_unchanged": True,
             "all13_supplemental_exact": True, "state_bytes_unchanged": True,
             "state_reconciliation": "read_only_desired_false_actual_false_no_state_rewrite",
             "terraform_executed": False, "terraform_applies": 0, "patch_attempts": 1,
             "scoring_requests": 0, "completion_requests": 0, "auto_enabled": False})
    except Exception as exc:
        save("failure.json", {"at_utc": p.now(), "stage": stage, "type": type(exc).__name__,
             "guard": str(exc) if type(exc) is RuntimeError else "details_suppressed",
             "http_status": getattr(exc, "code", None), "patch_attempted": attempted,
             "intent_exists": INTENT.exists(), "retry_authorized": False, "terraform_executed": False})
        return {"status": "STOP_no_retry", "stage": stage}
    return {"status": "ARM_offline_readback_verified", "terraform_executed": False}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "prepare-review":
        result = prepare_review(Path(sys.argv[2]))
    elif sys.argv[1:] == ["execute-reviewed-once"]:
        result = execute_reviewed_once()
    else:
        raise SystemExit("explicit prepare-review TEST_XML or execute-reviewed-once required")
    print(json.dumps(result), flush=True)
    return 2 if result["status"] == "STOP_no_retry" else 0


if __name__ == "__main__":
    raise SystemExit(main())