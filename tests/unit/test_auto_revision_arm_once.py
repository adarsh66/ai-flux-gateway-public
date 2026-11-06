"""Offline fixtures only: no CLI auth, Azure, Terraform, inference or images."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
from pathlib import Path
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from scripts.deployment import auto_revision_arm_once as c


@pytest.fixture(autouse=True)
def no_cloud(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline_test_external_operation_forbidden")
    monkeypatch.setattr(c.p.rt, "cli", forbidden)
    monkeypatch.setattr(c.p.backend, "token", forbidden)
    monkeypatch.setattr(c.p.backend, "blob_head", forbidden)
    monkeypatch.setattr(c.p.backend, "workers", forbidden)
    monkeypatch.setattr(c.p.release, "snapshot", forbidden)
    monkeypatch.setattr(c.p.persistence, "transport", forbidden)


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "HOME", tmp_path)
    monkeypatch.setattr(c, "OUT", tmp_path / "package")
    monkeypatch.setattr(c, "INTENT", tmp_path / "arm-take-offline-intent.json")
    c.OUT.mkdir()
    return c.OUT


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_exact_false_only_request_and_opaque_etag():
    request = c.patch_request(c.URL, 'W/"actual-server-etag"', "fixture-not-a-token")
    assert request.method == "PATCH" and request.full_url == c.URL
    assert request.data == b'{"properties":{"isOnline":false}}'
    assert request.get_header("If-match") == 'W/"actual-server-etag"'
    assert json.loads(request.data)["properties"]["isOnline"] is False
    assert set(dict(request.header_items())) == {"Authorization", "If-match", "Content-type", "Accept"}


@pytest.mark.parametrize("etag", [None, "", "*", '""', "unquoted", '"x"\r\nInjected: yes', '"x y"', 42, '"' + "x" * 1024 + '"'])
def test_missing_wildcard_or_injected_etag_rejected(etag):
    with pytest.raises(RuntimeError, match="actual_opaque_etag"):
        c.patch_request(c.URL, etag, "fixture")


@pytest.mark.parametrize("url", [c.URL.replace(";rev=2", ""), c.URL.replace(";rev=2", ";rev=1"),
    c.URL.replace(";rev=2", ";rev=3"), c.URL + "&x=1", c.URL.replace("https:", "http:"),
    c.URL.replace("management.azure.com", "example.invalid")])
def test_only_exact_revision2_uri(url):
    with pytest.raises(RuntimeError, match="revision2_uri_only"):
        c.patch_request(url, '"etag"', "fixture")


def test_tls_context_is_verified(monkeypatch):
    seen = []
    original = ssl.create_default_context
    def context(*args, **kwargs):
        value = original(*args, **kwargs)
        seen.append((value.check_hostname, value.verify_mode))
        return value
    monkeypatch.setattr(c.ssl, "create_default_context", context)
    c.opener(None)
    assert seen == [(True, ssl.CERT_REQUIRED)]


class Response:
    status = 200
    headers = {"x-ms-request-id": "fixture-123", "Authorization": "do-not-retain"}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, *args):
        raise AssertionError("PATCH_success_body_must_not_be_read")


@pytest.mark.parametrize("status", [200, 201, 202, 204, 301, 302, 303, 307, 308, 401, 403, 412, 429, 500, 503])
def test_exact_one_open_on_every_http_outcome(monkeypatch, status):
    calls = []
    class HTTP:
        def open(self, request, timeout):
            calls.append((request, timeout))
            if status >= 300:
                raise HTTPError(c.URL, status, "private secret message", {"x-ms-request-id": "safe-id"},
                                BytesIO(b'{"error":{"code":"PolicyViolation","message":"private secret"}}'))
            response = Response()
            response.status = status
            return response
    monkeypatch.setattr(c, "opener", lambda ca: HTTP())
    result = c.patch_wire(c.URL, '"etag"', "private fixture token", "fixture-ca")
    assert len(calls) == 1 and calls[0][1] == 60 and calls[0][0].method == "PATCH"
    assert result["http_status"] == status
    assert "private" not in json.dumps(result) and "secret" not in json.dumps(result)


@pytest.mark.parametrize("code", ["Bearer secret token", "x\r\ny", {"arbitrary": "payload"}, "x" * 129])
def test_error_code_allowlist(code):
    assert c.safe_http(403, {"Location": "private", "x-ms-request-id": "x\r\ny"}, code) == {"http_status": 403}


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_real_urllib_never_follows_redirect_on_loopback(status):
    # Local fixture server proves installed handlers, not merely a mocked flag.
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_PATCH(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(status)
            self.send_header("Location", "/must-not-follow")
            self.send_header("Content-Length", "0")
            self.end_headers()
        do_GET = do_PATCH
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(f"http://127.0.0.1:{server.server_port}/original", data=c.BODY, method="PATCH")
        with pytest.raises(HTTPError) as failure:
            c.opener(None).open(request, timeout=5)
        assert failure.value.code == status and calls == ["/original"]
        failure.value.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize("ready", [True, False])
def test_watchdog_single_process_budget_and_no_replay(monkeypatch, ready):
    calls = []
    class Pipe:
        def close(self):
            pass
        def poll(self, timeout):
            calls.append(("poll", timeout))
            return ready
        def recv(self):
            return {"http_status": 204}
    class Child:
        pid = None
        alive = True
        def start(self):
            calls.append("start")
            self.pid = 1
        def is_alive(self):
            return self.alive
        def terminate(self):
            calls.append("terminate")
            self.alive = False
        def join(self, seconds):
            pass
    class Context:
        def Pipe(self, duplex):
            assert duplex is False
            return Pipe(), Pipe()
        def Process(self, target, args):
            assert target is c.patch_child and args[1:4] == (c.URL, '"etag"', "fixture")
            return Child()
    monkeypatch.setattr(c.multiprocessing, "get_context", lambda method: Context() if method == "spawn" else None)
    result = c.patch_once('"etag"', "fixture")
    assert calls.count("start") == 1 and ("poll", 60) in calls and "terminate" in calls
    assert result == ({"http_status": 204} if ready else {"transport_error": "WallClockTimeout", "outcome": "unknown_no_retry"})


def setup_review(monkeypatch, package):
    manifest = {"sources": {"fixture": "hash"}, "state_owner": {"serial": 185}, "markers": {},
                "tests": {"path": "test.xml", "sha256": "testhash"}}
    write(package / "manifest.json", manifest)
    (package / "native-review.txt").write_text("Fixture independent review", encoding="utf-8")
    review = {"approved": True, "independent_native_review": True,
              "manifest_sha256": c.p.sha(package / "manifest.json"), "at_utc": datetime.now(UTC).isoformat(),
              "transcript": "native-review.txt", "transcript_sha256": c.p.sha(package / "native-review.txt")}
    write(package / "parent-review.json", review)
    monkeypatch.setattr(c, "sources", lambda: manifest["sources"])
    monkeypatch.setattr(c, "original_bindings", lambda: manifest["state_owner"])
    monkeypatch.setattr(c, "check_markers", lambda markers: None)
    real_sha = c.p.sha
    monkeypatch.setattr(c.p, "sha", lambda path: "testhash" if path.name == "test.xml" else real_sha(path))
    return manifest, review


def test_bound_parent_review_accepted_fixture_only(monkeypatch, package):
    manifest, _ = setup_review(monkeypatch, package)
    c.check_review(manifest)


@pytest.mark.parametrize("change", ["missing", "notapproved", "notindependent", "wrongmanifest", "stale", "future", "traversal", "wrongtranscript", "intent", "source", "state"])
def test_review_failure_blocks_write(monkeypatch, package, change):
    manifest, review = setup_review(monkeypatch, package)
    if change == "missing":
        (package / "parent-review.json").unlink()
    else:
        if change == "notapproved": review["approved"] = False
        if change == "notindependent": review["independent_native_review"] = False
        if change == "wrongmanifest": review["manifest_sha256"] = "wrong"
        if change == "stale": review["at_utc"] = (datetime.now(UTC) - timedelta(minutes=31)).isoformat()
        if change == "future": review["at_utc"] = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
        if change == "traversal": review["transcript"] = "../outside.txt"
        if change == "wrongtranscript": review["transcript_sha256"] = "wrong"
        if change == "intent": c.INTENT.touch()
        if change == "source": monkeypatch.setattr(c, "sources", lambda: {})
        if change == "state": monkeypatch.setattr(c, "original_bindings", lambda: {})
        write(package / "parent-review.json", review)
    with pytest.raises((RuntimeError, FileNotFoundError)):
        c.check_review(manifest)


def state_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(c.p, "ROOT", tmp_path / "infra")
    state = {"lineage": c.p.LINEAGE, "serial": 185, "resources": [{"mode": "managed", "type": "azapi_resource",
        "name": "auto_stage_revision", "instances": [{"index_key": 0, "attributes": {"id": c.RID,
        "body": json.dumps(c.p.expected_body(c.SELECTION))}}]}]}
    def commit():
        write(c.p.ROOT / "terraform.tfstate", state)
        write(c.HOME / "offline-correction02/state-owner.json", {"lineage": state["lineage"], "serial": state["serial"],
            "sha256": c.p.sha(c.p.ROOT / "terraform.tfstate")})
    commit()
    return state, commit


def test_state_owner_readonly_does_not_rewrite(package, tmp_path, monkeypatch):
    state_fixture(tmp_path, monkeypatch)
    path = c.p.ROOT / "terraform.tfstate"
    before = path.read_bytes()
    assert c.state_owner()["serial"] == 185 and path.read_bytes() == before


def test_actual_azapi_dynamic_state_body_wrapper(package, tmp_path, monkeypatch):
    state, commit = state_fixture(tmp_path, monkeypatch)
    state["resources"][0]["instances"][0]["attributes"]["body"] = {
        "type": ["object", {"properties": ["object", {}]}], "value": c.p.expected_body(c.SELECTION)}
    commit()
    before = (c.p.ROOT / "terraform.tfstate").read_bytes()
    assert c.state_owner()["serial"] == 185
    assert (c.p.ROOT / "terraform.tfstate").read_bytes() == before


@pytest.mark.parametrize("change", ["lineage", "serial", "hash", "lock", "id", "body", "duplicate", "newowner", "index"])
def test_state_owner_negatives(package, tmp_path, monkeypatch, change):
    state, commit = state_fixture(tmp_path, monkeypatch)
    if change == "lineage": state["lineage"] = "foreign"
    if change == "serial": state["serial"] = 186
    if change == "id": state["resources"][0]["instances"][0]["attributes"]["id"] = c.RID.replace("rev=2", "rev=1")
    if change == "body": state["resources"][0]["instances"][0]["attributes"]["body"] = {"properties": {"isOnline": True}}
    if change == "duplicate": state["resources"].append(deepcopy(state["resources"][0]))
    if change == "newowner": state["resources"].append({"name": "auto_stage_offline", "type": "azapi_update_resource"})
    if change == "index": state["resources"][0]["instances"][0]["index_key"] = 1
    commit()
    if change == "hash": (c.p.ROOT / "terraform.tfstate").write_bytes(b" " + (c.p.ROOT / "terraform.tfstate").read_bytes())
    if change == "lock": (c.p.ROOT / ".terraform.tfstate.lock.info").touch()
    with pytest.raises(RuntimeError): c.state_owner()


def execution_fixture(monkeypatch, package):
    write(package / "manifest.json", {"sources": {}, "markers": {}})
    write(package / "parent-review.json", {"fixture": True})
    monkeypatch.setattr(c, "check_review", lambda manifest: c.require(not c.INTENT.exists(), "existing_arm_intent"))
    monkeypatch.setattr(c.p.persistence, "transport", lambda: None)
    monkeypatch.setattr(c.p.rt, "cli", lambda args: {"id": c.p.rt.SUB, "tenantId": c.p.rt.TENANT})
    monkeypatch.setattr(c, "Reads", lambda: type("Reads", (), {"token": "private fixture"})())
    monkeypatch.setattr(c, "sources", lambda: {})
    monkeypatch.setattr(c, "state_owner", lambda: {"serial": 185})
    monkeypatch.setattr(c, "check_markers", lambda markers: None)
    calls = []
    def fresh(reads, label, online):
        calls.append(label)
        return {"at_utc": datetime.now(UTC).isoformat(), "etag": '"real-fixture-etag"',
                "current_api_sha256": "same", "state_owner": {"serial": 185}}
    monkeypatch.setattr(c, "fresh", fresh)
    def patch(etag, token):
        assert c.INTENT.exists() and etag == '"real-fixture-etag"'
        calls.append("PATCH")
        return {"http_status": 204}
    monkeypatch.setattr(c, "patch_once", patch)
    return calls


def test_orchestration_intent_before_one_patch_after_proofs_no_terraform(monkeypatch, package):
    calls = execution_fixture(monkeypatch, package)
    result = c.execute_reviewed_once()
    assert result["status"] == "ARM_offline_readback_verified" and calls == ["before", "PATCH", "after"]
    assert c.load(package / "verification.json")["terraform_executed"] is False
    assert c.load(c.INTENT)["attempt_budget"] == 1
    assert "private fixture" not in "".join(f.read_text() for f in package.glob("*.json"))


@pytest.mark.parametrize("result", [{"http_status": 403}, {"http_status": 412}, {"http_status": 429},
    {"http_status": 503}, {"http_status": 307}, {"transport_error": "WallClockTimeout"}])
def test_http_failure_timeout_no_retry_no_success(monkeypatch, package, result):
    calls = execution_fixture(monkeypatch, package)
    def patch(*args):
        calls.append("PATCH")
        return result
    monkeypatch.setattr(c, "patch_once", patch)
    assert c.execute_reviewed_once()["status"] == "STOP_no_retry"
    assert calls == ["before", "PATCH"] and c.INTENT.exists() and not (package / "verification.json").exists()
    assert c.load(package / "patch-result.json")["retry_authorized"] is False


def test_service_ignores_flag_stops_no_retry(monkeypatch, package):
    calls = execution_fixture(monkeypatch, package)
    original = c.fresh
    def fresh(reads, label, online):
        result = original(reads, label, online)
        if label == "after": raise RuntimeError("explicit_revision2_flag_current1_unchanged")
        return result
    monkeypatch.setattr(c, "fresh", fresh)
    assert c.execute_reviewed_once()["status"] == "STOP_no_retry"
    assert calls == ["before", "PATCH", "after"] and c.INTENT.exists()
    assert not (package / "verification.json").exists()


def test_prebaseline_failure_never_consumes_write_intent(monkeypatch, package):
    calls = execution_fixture(monkeypatch, package)
    def fail(*args): raise RuntimeError("all13_supplemental_exact")
    monkeypatch.setattr(c, "fresh", fail)
    assert c.execute_reviewed_once()["stage"] == "fresh_before"
    assert not c.INTENT.exists() and calls == []


def test_existing_intent_prevents_patch(monkeypatch, package):
    calls = execution_fixture(monkeypatch, package)
    c.INTENT.touch()
    assert c.execute_reviewed_once()["stage"] == "review" and calls == []


@pytest.mark.parametrize("change", ["changed", "new"])
def test_foreign_intent_blocks(monkeypatch, change):
    monkeypatch.setattr(c.p.backend, "markers", lambda: {"old": "changed"} if change == "changed" else {"old": "hash", "foreign": "hash"})
    with pytest.raises(RuntimeError, match="foreign_intent"):
        c.check_markers({"old": "hash"})


def test_no_terraform_or_inference_entrypoint_in_new_module():
    text = Path(c.__file__).read_text()
    assert "subprocess" not in text and "v.tf(" not in text and ".workflow(" not in text
    assert 'method="PATCH"' in text and 'method="PUT"' not in text and 'method="POST"' not in text


def fresh_fixture(monkeypatch, package):
    baseline = {str(n): "hash" for n in range(13)}
    supplement = {"supplement": "hash"}
    rows = [{"revision": "2", "api_id": "/apis/" + c.p.API + ";rev=2", "is_current": False,
             "is_online": True, "existing_noncurrent_candidate": True},
            {"revision": "1", "api_id": "/apis/" + c.p.API + ";rev=1", "is_current": True,
             "is_online": True, "existing_noncurrent_candidate": False}]
    current = {"id": c.p.APIM + "/apis/" + c.p.API,
               "properties": {"apiRevision": "1", "isCurrent": True, "isOnline": True,
                              "path": "dev/llm/v1", "subscriptionRequired": True}}
    api = {"id": c.RID, "properties": {**c.p.expected_body(c.SELECTION)["properties"], "subscriptionRequired": True}}
    head = {k: "fixture" for k in c.HEAD_KEYS}
    for name, value in (("protected-before.json", baseline), ("supplemental-before.json", supplement),
        ("current-api-metadata.json", current["properties"]), ("offline-correction02/remote-head-before.json", head),
        ("offline-correction02/revisions-before.json", rows)):
        write(c.HOME / name, value)
    monkeypatch.setattr(c, "original_bindings", lambda: {"serial": 185})
    monkeypatch.setattr(c, "state_owner", lambda: {"serial": 185})
    monkeypatch.setattr(c.p.release, "snapshot", lambda: baseline)
    monkeypatch.setattr(c.v, "supplemental", lambda base: supplement)
    monkeypatch.setattr(c.p.backend, "blob_head", lambda: head)
    flat = {"value": [{"apiRevision": r["revision"], "apiId": r["api_id"],
                       "isCurrent": r["is_current"], "isOnline": r["is_online"]} for r in rows]}
    class Reads:
        etag = '"actual-fixture-etag"'
        def get(self, suffix):
            return ({"/revisions": flat, ";rev=2": api, "": current}[suffix], self.etag)
    return baseline, supplement, flat, api, current, head, Reads()


@pytest.mark.parametrize("online", [True, False])
def test_fresh_complete_before_and_after_readback(monkeypatch, package, online):
    _, _, flat, _, _, _, reads = fresh_fixture(monkeypatch, package)
    flat["value"][0]["isOnline"] = online
    result = c.fresh(reads, "actual", online)
    assert result["all13_supplemental_exact"] is True
    assert c.load(package / "actual-flat-revisions.json")[0]["is_online"] is online


@pytest.mark.parametrize("change", ["baseline", "supplement", "paginated", "missingflag", "numericflag", "online_ignored",
    "madecurrent", "current1flag", "current1metadata", "nonce", "path", "subscription", "apiid", "remotehead", "etag", "state"])
def test_fresh_guard_negatives_save_actual_not_inferred(monkeypatch, package, change):
    baseline, supplement, flat, api, current, head, reads = fresh_fixture(monkeypatch, package)
    online = True
    if change == "baseline": baseline["0"] = "changed"
    if change == "supplement": supplement["supplement"] = "changed"
    if change == "paginated": flat["nextLink"] = "https://example.invalid/next"
    if change == "missingflag": del flat["value"][0]["isOnline"]
    if change == "numericflag":
        online = False
        flat["value"][0]["isOnline"] = 0
    if change == "online_ignored": online = False
    if change == "madecurrent": flat["value"][0]["isCurrent"] = True
    if change == "current1flag": flat["value"][1]["isOnline"] = False
    if change == "current1metadata": current["properties"]["path"] = "changed"
    if change == "nonce": api["properties"]["apiRevisionDescription"] = "foreign"
    if change == "path": api["properties"]["path"] = "changed"
    if change == "subscription": api["properties"]["subscriptionRequired"] = False
    if change == "apiid": api["id"] = c.RID.replace("rev=2", "rev=3")
    if change == "remotehead": head["etag"] = "changed"
    if change == "etag": reads.etag = "*"
    if change == "state": monkeypatch.setattr(c, "state_owner", lambda: {"serial": 186})
    with pytest.raises(RuntimeError): c.fresh(reads, "actual", online)
    assert (package / "actual-protected.json").exists()