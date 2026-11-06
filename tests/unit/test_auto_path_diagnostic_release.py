"""Offline only: actual retained XML fixtures; no Azure/CLI/TF/browser execution."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import pytest

from scripts.deployment import auto_path_diagnostic_release as m

START = "2026-10-29T14:00:00Z"
END = "2026-10-29T14:30:00Z"
AT = datetime(2026, 10, 29, 14, 1, tzinfo=UTC)
NONCE = "f" * 32


def exported(root):
    root = deepcopy(root)
    for node in root.iter():
        node.attrib.update({k: escape(v, {'"': "&quot;"}) for k, v in node.attrib.items()})
        if node.text:
            node.text = escape(node.text, {'"': "&quot;"})
    return ET.tostring(root, encoding="unicode")


def pair(root):
    # ARM rawxml emits literal C# quotes, not ElementTree's &quot; encoding.
    # This is intentionally not generally parseable XML; the established exact
    # raw-expression matcher verifies it without guessing delimiter repairs.
    raw = ET.tostring(root, encoding="unicode")
    for node in root.iter():
        for key, value in node.attrib.items():
            if value.startswith("@"):
                encoded = escape(value, {'"': "&quot;", "\t": "&#09;", "\n": "&#10;", "\r": "&#13;"})
                raw = raw.replace(key + '="' + encoded + '"', key + '="' + value + '"')
    return {fmt: {"status": 200, "etag": '"fixture"', "body": {"properties": {"value": text}}}
            for fmt, text in (("rawxml", raw), ("xml", exported(root)))}


@pytest.fixture(scope="module")
def retained():
    historical = m.load(m.a.HOME / "scoring-diagnostic01/prepare-capture.json")
    original = historical["inheritance"]["/policies/policy?format=xml"]["body"]["properties"]["value"].encode()
    candidate = m.render(original, m.FIXTURE.read_bytes(), START, END, NONCE)
    return original, candidate


@pytest.fixture
def capture(retained):
    original, _ = retained
    latest = m.load(m.ROOT / ".deployment/customer-send-cm38-independent-readonly-20261029T120345732391Z/protected-after.json")
    observation = m.load(m.ROOT / ".deployment/customer-send-cm38-independent-readonly-20261029T120345732391Z/revision-observation.json")
    history = m.load(m.a.HOME / "scoring-diagnostic01/prepare-capture.json")
    result = {"at_utc": AT.isoformat(), "baseline": latest["baseline"], "supplemental": latest["supplemental"],
        "project": observation["state_owner"], "runtime": {"serial": 111, "sha256": "fixture-current-runtime"},
        "storage_sha256": latest["storage_sha256"], "current_api_sha256": observation["current_api_sha256"],
        "owned_api": history["owned_api"], "revisions": observation["revisions"],
        "inheritance": history["inheritance"], "formats": {
            "global": pair(m.c.tree(original, exported=True)), "revision": pair(m.c.tree(m.FIXTURE.read_bytes()))}}
    # The proposal requires exact retained global EXPORT bytes, not reserialization.
    result["formats"]["global"]["xml"]["body"]["properties"]["value"] = original.decode()
    result["baseline"]["apim"]["global"] = m.sha(m.policy_values(result["formats"]["global"])["rawxml"].encode())
    return result


@pytest.fixture
def package(tmp_path, retained, capture, monkeypatch):
    folder = tmp_path / "auto-path-diagnostic-fixture"
    folder.mkdir()
    for name, value in retained[1].items():
        m.exclusive(folder / name, value)
    m.exclusive(folder / "fresh-before.json", capture)
    m.exclusive(folder / "manifest.json", {"at_utc": START, "start": START, "end": END})
    m.exclusive(folder / "transcript.txt", b"TEST FIXTURE, NOT NATIVE REVIEW")
    receipt = {"approved": True, "independent_native_review": True, "parent_says_cleanup": True, "stages": list(m.STAGES),
        "at_utc": AT.isoformat(), "manifest_sha256": m.sha((folder / "manifest.json").read_bytes()),
        "transcript": "transcript.txt", "transcript_sha256": m.sha((folder / "transcript.txt").read_bytes())}
    m.exclusive(folder / "parent-review.json", receipt)
    m.exclusive(folder / "browser-source.js", m.browser_source().encode())
    m.exclusive(folder / "safe-events.json", {"TEST_ONLY": True})
    m.exclusive(folder / "browser-preflight.json", {"evidence": "safe-events.json",
        "evidence_sha256": m.sha((folder / "safe-events.json").read_bytes()),
        "source_sha256": m.sha((folder / "browser-source.js").read_bytes()),
        "manifest_sha256": receipt["manifest_sha256"], "parent_observed": True,
        "safe_events_observed": True, "fixture": False, "send_invoked": False,
        "page_id": "00000000-0000-0000-0000-000000000000", "at_utc": AT.isoformat()})
    monkeypatch.setattr(m, "localcheck", lambda _: m.load(folder / "manifest.json"))
    return folder


def installed(capture, folder, global_policy=False, revision=False, online=False):
    result = deepcopy(capture)
    for kind, enabled in (("global", global_policy), ("revision", revision)):
        if enabled:
            result["formats"][kind] = pair(m.c.tree((folder / (kind + ".xml")).read_bytes()))
    result["baseline"]["apim"]["global"] = m.sha(m.policy_values(result["formats"]["global"])["rawxml"].encode())
    for row in result["revisions"]:
        if row["revision"] == "2":
            row["is_online"] = online
    return result


class Fake:
    def __init__(self, value, folder):
        self.value, self.folder, self.calls = deepcopy(value), folder, []
        self.fail = None

    def capture(self):
        return deepcopy(self.value)

    def last(self, stage):
        return self.capture(), '"fresh-etag"'

    def send(self, stage, body, etag):
        assert (self.folder / (stage + "-intent.json")).is_file()
        assert etag == '"fresh-etag"'
        self.calls.append(stage)
        if self.fail == stage:
            return {"http_status": 400, "raw_body": "SECRET_NOT_PERSISTED"}
        if stage in ("install-global", "install-revision", "restore-global"):
            kind = "revision" if stage == "install-revision" else "global"
            self.value["formats"][kind] = pair(m.c.tree(json.loads(body)["properties"]["value"]))
            if kind == "global":
                self.value["baseline"]["apim"]["global"] = m.sha(m.policy_values(self.value["formats"]["global"])["rawxml"].encode())
                # Simulated ARM export preserves exact original representations.
                if stage == "restore-global":
                    original = m.load(self.folder / "fresh-before.json")
                    self.value["formats"]["global"] = deepcopy(original["formats"]["global"])
                    self.value["baseline"]["apim"]["global"] = original["baseline"]["apim"]["global"]
        else:
            for row in self.value["revisions"]:
                if row["revision"] == "2":
                    row["is_online"] = stage == "online"
        return {"http_status": 200}


def test_wire_xml_is_single_encoded_and_exact_CSharp(retained):
    original, candidates = retained
    root = m.c.tree(candidates["global.xml"])
    condition = root.find("./inbound/choose/when").get("condition")
    assert m.expression(START, END) in condition
    assert "&amp;" not in condition and "&&" in condition
    assert m.c.signature(m.c.tree(candidates["restore-global.xml"])) == m.c.signature(m.c.tree(original, exported=True))
    assert b"&amp;amp;" not in candidates["global.xml"]


def test_revision_only_guard_and_new_one_budget_counter(retained):
    root = m.c.tree(retained[1]["revision.xml"])
    old = m.c.tree(m.FIXTURE.read_bytes())
    gate = m.c.post(root).find("limit-concurrency")
    old_gate = m.c.post(old).find("limit-concurrency")
    assert gate.get("key") != old_gate.get("key")
    assert gate[0].get("calls") == "1" and gate[0].get("renewal-period") == "3600"
    assert gate[0].get("counter-key") == gate.get("key")
    gate.set("key", old_gate.get("key"))
    gate[0].set("counter-key", old_gate[0].get("counter-key"))
    root.find("inbound")[2].find("when").set("condition", old.find("inbound")[2].find("when").get("condition"))
    assert m.c.signature(root) == m.c.signature(old)
    assert gate[-1].tag == "return-response"
    assert not gate.findall(".//retry") and not gate.findall(".//forward-request")


@pytest.mark.parametrize("start,end", [(START, START), (END, START), (START, "2026-10-29T14:30:01Z"),
    (START, "2026-10-29T14:30:00+00:00"), (START, "2026-02-30T14:30:00Z"), (START, END + '" || true')])
def test_window_fails_closed(start, end):
    with pytest.raises((RuntimeError, ValueError)):
        m.window(start, end)


@pytest.mark.parametrize("etag", [None, "*", "", "unquoted", '"x"\r\nInjected: true'])
def test_bad_etag_no_request(etag):
    with pytest.raises(RuntimeError):
        m.mutation_request("offline", m.encode({"properties": {"isOnline": False}}), etag, "not-a-real-token")


def test_request_exact_URI_and_literal_PATCH():
    request = m.mutation_request("offline", m.encode({"properties": {"isOnline": False}}), '"etag"', "fake")
    assert request.full_url == m.a.URL and request.method == "PATCH"
    assert request.get_header("If-match") == '"etag"'
    with pytest.raises(RuntimeError):
        m.mutation_request("offline", b'{"properties":{"isCurrent":true}}', '"etag"', "fake")
    with pytest.raises(RuntimeError):
        m.mutation_request("anything", b"{}", '"etag"', "fake")


def test_exclusive_fsync_and_permanent_consumption(tmp_path, monkeypatch):
    spy = Mock(wraps=m.os.fsync)
    monkeypatch.setattr(m.os, "fsync", spy)
    path = tmp_path / "intent.json"
    m.exclusive(path, {"attempts": 1})
    assert spy.call_count == 1
    with pytest.raises(FileExistsError):
        m.exclusive(path, {})
    assert m.load(path) == {"attempts": 1}


def test_initial_uses_current_cm38_not_oldbaseline(capture):
    m.initial(capture)
    assert capture["baseline"]["runtime"]["sites"]["customer"]["image"].endswith(m.CUSTOMER)
    assert capture["project"]["serial"] == 185 and capture["runtime"]["serial"] == 111
    bad = deepcopy(capture)
    next(row for row in bad["revisions"] if row["revision"] == "2")["is_online"] = True
    with pytest.raises(RuntimeError):
        m.initial(bad)


@pytest.mark.parametrize("key", ["baseline", "supplemental", "project", "runtime", "storage_sha256", "current_api_sha256"])
def test_every_protected_category_drift_stops(capture, package, key):
    current = deepcopy(capture)
    current[key] = {} if isinstance(current[key], dict) else "drift"
    with pytest.raises((RuntimeError, KeyError)):
        m.guarded(capture, current, package, False, False, False)


def test_global_only_exact_exception_not_broad_exclusion(capture, package):
    current = installed(capture, package, True, True)
    m.guarded(capture, current, package, True, True, False)
    current["baseline"]["apim"]["backends"] = "unexpected"
    with pytest.raises(RuntimeError):
        m.guarded(capture, current, package, True, True, False)


def test_global_hash_cannot_be_forged(capture, package):
    current = installed(capture, package, True)
    current["baseline"]["apim"]["global"] = "not-current-raw"
    with pytest.raises(RuntimeError):
        m.guarded(capture, current, package, True, False, False)


@pytest.mark.parametrize("kind,fmt", [("global", "rawxml"), ("global", "xml"), ("revision", "rawxml"), ("revision", "xml")])
def test_both_formats_reject_semantic_drift(capture, package, kind, fmt):
    current = installed(capture, package, True, True)
    current["formats"][kind][fmt]["body"]["properties"]["value"] += "<extra/>"
    with pytest.raises((RuntimeError, ET.ParseError)):
        m.guarded(capture, current, package, True, True, False)


def test_independent_expired_cleanup_after_failed_activation(package, capture):
    fake = Fake(capture, package)
    stages = m.Stages(package, fake, lambda: AT)
    stages.execute("install-global")
    fake.fail = "install-revision"
    with pytest.raises(RuntimeError):
        stages.execute("install-revision")
    assert m.load(package / "install-revision-cleanup-required.json")["offline_then_restore_global"] is True
    assert "SECRET" not in (package / "install-revision-result.json").read_text()
    # No success receipt needed for cleanup, no expired-window blocker.
    late = AT + timedelta(days=1)
    fake.value["at_utc"] = late.isoformat()
    cleanup = m.Stages(package, fake, lambda: late)
    cleanup.execute("offline")
    cleanup.execute("restore-global")
    assert fake.calls == ["install-global", "install-revision", "restore-global"]
    assert m.load(package / "offline-result.json")["no_wire"] is True
    assert m.policy_values(fake.value["formats"]["global"]) == m.policy_values(capture["formats"]["global"])
    for stage in ("install-revision", "offline", "restore-global"):
        with pytest.raises(RuntimeError):
            cleanup.execute(stage)
    assert len(fake.calls) == 3


def test_cleanup_handles_ambiguous_installed_write_without_success_receipt(package, capture):
    fake = Fake(installed(capture, package, True, True, True), package)
    stages = m.Stages(package, fake, lambda: AT)
    stages.execute("offline")
    stages.execute("restore-global")
    assert fake.calls == ["offline", "restore-global"]


def test_global_restore_requires_independent_offline(package, capture):
    fake = Fake(installed(capture, package, True), package)
    with pytest.raises(RuntimeError):
        m.Stages(package, fake, lambda: AT).execute("restore-global")
    assert not fake.calls


def test_unknown_cleanup_policy_drift_stops_without_intent(package, capture):
    fake = Fake(installed(capture, package, True), package)
    fake.value["formats"]["global"]["xml"]["body"]["properties"]["value"] += "<drift/>"
    with pytest.raises((RuntimeError, ET.ParseError)):
        m.Stages(package, fake, lambda: AT).execute("offline")
    assert not fake.calls and not (package / "offline-intent.json").exists()


def test_last_read_drift_and_stale_capture_stop(package, capture):
    fake = Fake(capture, package)
    fake.last = lambda _: (dict(fake.capture(), current_api_sha256="changed"), '"new"')
    with pytest.raises(RuntimeError):
        m.Stages(package, fake, lambda: AT).execute("install-global")
    assert not fake.calls
    fake.last = lambda _: (fake.capture(), '"new"')
    with pytest.raises(RuntimeError):
        m.Stages(package, fake, lambda: AT + timedelta(seconds=31)).execute("install-global")
    assert not fake.calls


def test_all_stages_review_required_even_cleanup(package):
    review = m.load(package / "parent-review.json")
    review["stages"] = ["offline"]
    (package / "parent-review.json").write_bytes(m.encode(review))
    with pytest.raises(RuntimeError):
        m.review(package, "offline", lambda: AT)


def test_foreign_transcript_rejected(package):
    review = m.load(package / "parent-review.json")
    review["transcript"] = "../outside.txt"
    (package / "parent-review.json").write_bytes(m.encode(review))
    with pytest.raises(RuntimeError):
        m.review(package, "offline", lambda: AT)


def test_timer_free_browser_source_only_binding_identity_changes():
    text = m.browser_source()
    assert m.SCOPE in text and "GLOBAL_ORIGINAL_PATH_CONJUNCTION" in text
    assert "setTimeout(" not in text and "clearTimeout(" not in text and "node:" not in text
    assert "Control+Enter" in text and 'completion_budget === 0' in text


def test_CLI_never_exposes_ungrouped_mutation_stages(monkeypatch, tmp_path):
    for stage in ("install-global", "install-revision", "online", "offline", "restore-global", "send"):
        monkeypatch.setattr(m.os.sys, "argv", ["helper", stage, "--package", str(tmp_path)])
        with pytest.raises(SystemExit) as exc:
            m.main()
        assert exc.value.code == 2


def test_failed_fresh_prepare_does_not_freeze_window(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "test_receipt", lambda _: {})
    monkeypatch.setattr(m, "sources", lambda: {})
    clock = Mock(side_effect=AssertionError("must not freeze before capture"))
    capture = Mock(side_effect=RuntimeError("fresh capture unavailable"))
    folder = tmp_path / "auto-path-diagnostic-no-freeze"
    with pytest.raises(RuntimeError):
        m.prepare(folder, Path("unused"), capture, clock)
    clock.assert_not_called()
    assert not folder.exists()


def test_activation_failure_supervisor_rolls_back_once(package, capture):
    fake = Fake(capture, package)
    fake.fail = "install-revision"
    stages = m.Stages(package, fake, lambda: AT)
    with pytest.raises(RuntimeError):
        stages.activate()
    assert fake.calls == ["install-global", "install-revision", "restore-global"]
    assert m.load(package / "activation-cleanup.json")["status"] == "OFFLINE_AND_ORIGINAL_GLOBAL_INDEPENDENTLY_VERIFIED"
    with pytest.raises(RuntimeError):
        stages.activate()
    assert len(fake.calls) == 3


def test_supervisor_does_not_replay_unresolved_cleanup(package, capture):
    fake = Fake(capture, package)
    original_send = fake.send
    def send(stage, body, etag):
        if stage == "online":
            for row in fake.value["revisions"]:
                if row["revision"] == "2":
                    row["is_online"] = True  # Remote success, lost response.
        fake.fail = stage if stage in ("online", "offline") else None
        return original_send(stage, body, etag)
    fake.send = send
    stages = m.Stages(package, fake, lambda: AT)
    with pytest.raises(RuntimeError):
        stages.activate()
    assert fake.calls == ["install-global", "install-revision", "online", "offline"]
    assert m.load(package / "activation-cleanup.json")["status"] == "UNRESOLVED_STOP_FRESH_READS_NO_REPLAY"
    with pytest.raises(RuntimeError):
        stages.execute("offline")
    assert len(fake.calls) == 4


def test_prepare_assembles_only_after_capture_then_localcheck_detects_drift(capture, tmp_path, monkeypatch):
    tests = {"path": "TEST_FIXTURE_NOT_AN_ACTUAL_RECEIPT", "sha256": "fixture", "counts": {"tests": 1}}
    monkeypatch.setattr(m, "test_receipt", lambda _: tests)
    monkeypatch.setattr(m, "sources", lambda: {"fixture-source": "fixture-hash"})
    monkeypatch.setattr(m.r.fs, "protect", lambda _: None)
    events = []
    def read():
        events.append("fresh-read-completed")
        return deepcopy(capture)
    def clock():
        assert events == ["fresh-read-completed"]
        return AT
    folder = tmp_path / "auto-path-diagnostic-preparation"
    result = m.prepare(folder, Path("unused"), read, clock)
    assert result["start"] == "2026-10-29T14:01:00Z" and result["end"] == "2026-10-29T14:31:00Z"
    assert result["historical_scoring_request_count"] is None and result["cloud_mutations"] == 0
    assert m.load(folder / "fresh-before.json")["baseline"] == capture["baseline"]
    assert not list(folder.glob("*-intent.json"))
    with pytest.raises(RuntimeError):
        m.prepare(folder, Path("unused"), read, clock)
    with (folder / "global.xml").open("ab") as stream:
        stream.write(b"drift")
    with pytest.raises(RuntimeError):
        m.localcheck(folder)


def adapter_reads(value):
    reads = Mock()
    def get(suffix):
        if suffix == "/revisions":
            return {"value": deepcopy(value["revisions"])}, '"list"'
        if suffix == ";rev=2":
            return deepcopy(value["owned_api"]), value["api_etag"]
        return {"current": True}, '"current"'
    reads.get.side_effect = get
    reads.arm.side_effect = lambda path: deepcopy(value["formats"]["global"][path.rsplit("=", 1)[1]])
    reads.policy.side_effect = lambda rev, fmt: deepcopy(value["formats"]["revision"][fmt])
    return reads


@pytest.mark.parametrize("stage", m.STAGES)
def test_actual_adapter_last_returns_same_capture_not_second_collect(package, capture, monkeypatch, stage):
    value = deepcopy(capture)
    value["api_etag"] = '"API"'
    value["current_api_sha256"] = m.r.fs.sha({"current": True})
    collector = Mock(return_value=value)
    monkeypatch.setattr(m, "collect", collector)
    reads = adapter_reads(value)
    monkeypatch.setattr(m.c, "Reads", lambda: reads)
    monkeypatch.setattr(m.p, "summarize_revision", lambda row: row)
    clock = AT + timedelta(seconds=10)
    adapter = m.ProductionAdapter(package, lambda: clock)
    actual = adapter.capture()
    latest, etag = adapter.last(stage)
    assert latest is actual and latest["at_utc"] == clock.isoformat()
    assert collector.call_count == 1
    assert etag == ('"fixture"' if stage in ("install-global", "restore-global", "install-revision") else '"API"')
    assert all(call.args[0].startswith("/policies/policy?format=") for call in reads.arm.call_args_list)


@pytest.mark.parametrize("kind,fmt", [(k, f) for k in ("global", "revision") for f in ("rawxml", "xml")])
def test_actual_adapter_last_both_formats_metadata_drift_stops(package, capture, monkeypatch, kind, fmt):
    value = deepcopy(capture)
    value["api_etag"] = '"API"'
    value["current_api_sha256"] = m.r.fs.sha({"current": True})
    remote = deepcopy(value)
    remote["formats"][kind][fmt]["etag"] = '"changed"'
    monkeypatch.setattr(m, "collect", lambda: value)
    monkeypatch.setattr(m.c, "Reads", lambda: adapter_reads(remote))
    monkeypatch.setattr(m.p, "summarize_revision", lambda row: row)
    adapter = m.ProductionAdapter(package, lambda: AT)
    adapter.capture()
    with pytest.raises(RuntimeError):
        adapter.last("install-global")
    assert adapter.ready is None


def test_actual_adapter_send_exact_global_body_not_API_mutation(package, monkeypatch):
    adapter = m.ProductionAdapter(package, lambda: AT)
    adapter.token = "SECRET_MEMORY_ONLY"
    body = m.stage_body(package, "install-global")
    adapter.ready = ("install-global", '"opaque"', AT.isoformat())
    m.exclusive(package / "install-global-intent.json", {"body_sha256": m.sha(body), "etag": '"opaque"',
        "manifest_sha256": m.sha((package / "manifest.json").read_bytes()),
        "review_sha256": m.sha((package / "parent-review.json").read_bytes())})
    token = Mock(return_value="SECRET_MEMORY_ONLY")
    sender = Mock(return_value={"http_status": 200})
    monkeypatch.setattr(m.p.backend, "token", token)
    monkeypatch.setattr(m, "send_once", sender)
    with pytest.raises(RuntimeError):
        adapter.send("install-global", body + b" ", '"opaque"')
    sender.assert_not_called()
    result = adapter.send("install-global", body, '"opaque"')
    assert result == {"http_status": 200} and sender.call_count == 1
    request = m.mutation_request(*sender.call_args.args)
    assert request.method == "PUT" and request.full_url == m.GLOBAL_URL
    assert "/apis/" not in request.full_url
    with pytest.raises(RuntimeError):
        adapter.send("install-global", body, '"opaque"')


@pytest.mark.parametrize("status", [200, 201, 204, 302, 400, 403, 412, 500])
def test_actual_writer_one_strict_open_status_only_no_body(package, monkeypatch, status):
    from urllib.error import HTTPError
    opener, conn = Mock(), Mock()
    response = Mock(status=status)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    if status >= 300:
        opener.open.side_effect = HTTPError(m.GLOBAL_URL, status, "SECRET", {}, None)
    else:
        opener.open.return_value = response
    factory = Mock(return_value=opener)
    monkeypatch.setattr(m.a, "opener", factory)
    body = m.stage_body(package, "install-global")
    m.wire_child(conn, "install-global", body, '"opaque"', "SECRET", "CORPORATE_CA")
    factory.assert_called_once_with("CORPORATE_CA")
    assert opener.open.call_count == 1 and opener.open.call_args.kwargs == {"timeout": 45}
    response.read.assert_not_called()
    conn.send.assert_called_once_with({"http_status": status})
    conn.close.assert_called_once()


def test_actual_writer_exception_is_fixed_not_exception_text(package, monkeypatch):
    opener, conn = Mock(), Mock()
    opener.open.side_effect = OSError("TOKEN SECRET")
    monkeypatch.setattr(m.a, "opener", lambda _: opener)
    m.wire_child(conn, "offline", m.stage_body(package, "offline"), '"opaque"', "SECRET", "CA")
    conn.send.assert_called_once_with({"transport_error": "TransportFailureUnknown"})


def test_noop_cleanup_both_stages_intents_results_and_independent_captures(package, capture):
    fake = Fake(capture, package)
    spy = Mock(wraps=fake.capture)
    fake.capture = spy
    m.Stages(package, fake, lambda: AT).cleanup()
    assert fake.calls == [] and spy.call_count == 6  # before/last/after each
    for stage in ("offline", "restore-global"):
        assert m.load(package / (stage + "-intent.json"))["no_wire"] is True
        assert m.load(package / (stage + "-result.json"))["no_wire"] is True
        assert m.load(package / (stage + "-verified.json"))["all13_exact"] is True
    with pytest.raises(RuntimeError):
        m.Stages(package, fake, lambda: AT).cleanup()


def test_unknown_global_install_response_runs_safe_fresh_noop_cleanup(package, capture):
    fake = Fake(capture, package)
    fake.fail = "install-global"
    with pytest.raises(RuntimeError):
        m.Stages(package, fake, lambda: AT).activate()
    assert fake.calls == ["install-global"]
    assert m.load(package / "activation-cleanup.json")["status"] == "OFFLINE_AND_ORIGINAL_GLOBAL_INDEPENDENTLY_VERIFIED"


def test_parent_cleanup_signal_required_before_any_stage(package):
    receipt = m.load(package / "parent-review.json")
    receipt.pop("parent_says_cleanup")
    (package / "parent-review.json").write_bytes(m.encode(receipt))
    for stage in m.STAGES:
        with pytest.raises(RuntimeError):
            m.review(package, stage, lambda: AT)


@pytest.mark.parametrize("field,value", [("parent_observed", False), ("safe_events_observed", False),
    ("fixture", True), ("send_invoked", True), ("source_sha256", "bad"), ("evidence_sha256", "bad")])
def test_real_preflight_cannot_be_substituted_by_fixture(package, field, value):
    receipt = m.load(package / "browser-preflight.json")
    receipt[field] = value
    (package / "browser-preflight.json").write_bytes(m.encode(receipt))
    with pytest.raises(RuntimeError):
        m.browser_preflight(package, lambda: AT)


def test_reserve_intent_precedes_fullcapture_then_fast_local_claim(package, capture):
    fake = Fake(capture, package)
    stages = m.Stages(package, fake, lambda: AT)
    stages.activate()
    original = fake.capture
    def capture_with_parent_intent():
        assert (package / "browser-send-intent.json").is_file()
        return original()
    fake.capture = capture_with_parent_intent
    reservation = m.reserve(package, fake, lambda: AT)
    assert not (package / "browser-claim-intent.json").exists()
    binding = m.claim(package, lambda: AT)
    assert reservation == binding["reservation"]
    assert fake.calls == ["install-global", "install-revision", "online"]
    assert binding["nonce"] == binding["reservation"]["nonce"]
    assert binding["review_sha256"] == binding["reservation"]["review_sha256"]
    assert binding["verified_at_utc"] == AT.isoformat()
    assert binding["parent_claim_durable"] is True
    with pytest.raises(FileExistsError):
        m.claim(package, lambda: AT)


def test_raw_text_expressions_compare_entire_tree():
    root = m.c.tree('<policies><inbound><set-body>@{ return "a" &amp; "b"; }</set-body></inbound></policies>')
    formats = pair(root)
    formats["rawxml"]["body"]["properties"]["value"] = '<policies><inbound><set-body>@{ return "a" & "b"; }</set-body></inbound></policies>'
    m.verify_formats(formats)
    formats["rawxml"]["body"]["properties"]["value"] = formats["rawxml"]["body"]["properties"]["value"].replace('"b"', '"c"')
    with pytest.raises(RuntimeError):
        m.verify_formats(formats)


def test_native_node_receipt_actual_leaf_counts_and_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "ROOT", tmp_path)
    path = tmp_path / "node.xml"
    path.write_text('<testsuites><testcase name="one"/><testcase name="two"/></testsuites>')
    assert m.test_receipt(path)["counts"] == {"tests": 2, "errors": 0, "failures": 0, "skipped": 0}
    path.write_text('<testsuites><testcase name="bad"><failure/></testcase></testsuites>')
    with pytest.raises(RuntimeError):
        m.test_receipt(path)


def test_fractional_capture_freezes_after_collection_not_before(capture, tmp_path, monkeypatch):
    tests = {"path": "unused", "counts": {"tests": 1}}
    monkeypatch.setattr(m, "test_receipt", lambda _: tests)
    monkeypatch.setattr(m, "sources", lambda: {})
    monkeypatch.setattr(m.r.fs, "protect", lambda _: None)
    value = deepcopy(capture)
    value["at_utc"] = (AT + timedelta(microseconds=500000)).isoformat()
    folder = tmp_path / "auto-path-diagnostic-fractional"
    result = m.prepare(folder, Path("unused"), lambda: value, lambda: AT + timedelta(microseconds=600000))
    assert result["start"] == AT.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_actual_native_proposal_core_excludes_separate_historical_binding():
    result = m.subprocess.run(["node", "--test", "--test-skip-pattern=^existing diagnostic06 source bindings",
        str(m.ROOT / "tests/auto_global_path_exception.test.mjs")], capture_output=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout[-3000:]


@pytest.mark.parametrize("drift", [None, "customer", "lease", "project", "runtime"])
def test_actual_collect_readonly_current_pins_state_and_no_old_baseline(capture, monkeypatch, drift):
    value = deepcopy(capture)
    value["api_etag"] = '"API"'
    reads = adapter_reads(value)
    baseline = deepcopy(value["baseline"])
    runtime = {"lineage": "b05cbf70-2d31-0e6e-34b7-c97e8f617ed6", "serial": 111,
        "sha256": "stable-runtime-bytes", "etag": '"runtime"', "length": 1234, "last_modified": "unchanged"}
    head = {"lease_state": "available", "lease_status": "unlocked", "etag": '"runtime"',
        "content_length": "1234", "last_modified": "unchanged"}
    if drift == "customer": baseline["runtime"]["sites"]["customer"]["image"] = "old-customer"
    if drift == "lease": head["lease_state"] = "leased"
    if drift == "project": value["project"]["serial"] = 184
    if drift == "runtime": runtime["serial"] = 110
    monkeypatch.setattr(m.a, "state_owner", lambda: value["project"])
    monkeypatch.setattr(m.c, "Reads", lambda: reads)
    monkeypatch.setattr(m.p, "summarize_revision", lambda row: row)
    monkeypatch.setattr(m.c, "inheritance", lambda _: (value["inheritance"], False))
    monkeypatch.setattr(m, "read_transport", nullcontext)
    monkeypatch.setattr(m.r.login, "account", Mock())
    monkeypatch.setattr(m.r.persistence.release, "snapshot", lambda: baseline)
    monkeypatch.setattr(m.r, "supplemental", lambda _: value["supplemental"])
    monkeypatch.setattr(m.r.persistence.backend, "arm_read", lambda: {"account": {"TEST": "storage"}})
    monkeypatch.setattr(m.r.persistence.backend, "blob_head", lambda: head)
    monkeypatch.setattr(m.r.persistence.backend, "workers", lambda: [])
    monkeypatch.setattr(m, "remote_state", lambda: runtime)
    if drift:
        with pytest.raises(RuntimeError): m.collect()
    else:
        actual = m.collect()
        assert actual["runtime"]["serial"] == 111 and actual["project"]["serial"] == 185
        assert actual["baseline"] == baseline
        assert [x.args[0] for x in reads.get.call_args_list] == ["/revisions", "", ";rev=2"]
        assert all(x.args[0].startswith("/policies/policy?format=") for x in reads.arm.call_args_list)


def test_strict_read_context_rejects_all_configuration_write_methods():
    before_arm, before_cli = m.r.rt.arm, m.r.rt.cli
    with m.read_transport():
        for method in ("PUT", "PATCH", "DELETE", "POST"):
            with pytest.raises(RuntimeError): m.r.rt.arm("/not-an-exact-settings-list", method)
        with pytest.raises(RuntimeError): m.r.rt.cli(["rest", "--method", "put", "--url", m.GLOBAL_URL])
    assert m.r.rt.arm is before_arm and m.r.rt.cli is before_cli