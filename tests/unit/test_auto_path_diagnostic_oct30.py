"""Offline Oct30 tests. Temporary fixtures are not actual release evidence."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from unittest.mock import Mock
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import pytest

from scripts.deployment import auto_path_diagnostic_oct30 as s

d = s.d
START, END = "2026-10-30T01:00:00Z", "2026-10-30T01:30:00Z"
AT = datetime(2026, 10, 30, 1, 1, tzinfo=UTC)
NONCE = "e" * 32


@pytest.fixture(autouse=True)
def oct30_offline_write_guard_ssl_context(request, monkeypatch):
    """Load this module as a pytest plugin for the unchanged bound guard test.

    Only that test's context construction is mocked: it exercises the real
    configuration-write guards, not certificate loading or a network request.
    Production TLS and its missing-CA failure path are never changed.
    """
    target = "tests/unit/test_auto_path_diagnostic_release.py::test_strict_read_context_rejects_all_configuration_write_methods"
    if request.node.nodeid.replace("\\", "/") != target:
        yield
        return
    ssl_module = d.r.persistence.old.ssl
    context = Mock(spec=ssl_module.SSLContext)
    factory = Mock(return_value=context)
    network = Mock(side_effect=AssertionError("offline guard test must not open a transport"))
    cli = Mock(side_effect=AssertionError("offline guard test must not invoke a CLI"))
    monkeypatch.setattr(ssl_module, "create_default_context", factory)
    monkeypatch.setattr(d.a, "opener", network)
    monkeypatch.setattr(d.r.rt, "cli", cli)
    yield
    factory.assert_called_once_with(cafile=d.r.rt.CA)
    network.assert_not_called()
    cli.assert_not_called()
    assert context.mock_calls == []


def pair(root):
    raw = ET.tostring(root, encoding="unicode")
    exported = deepcopy(root)
    for node in root.iter():
        for key, value in node.attrib.items():
            if value.startswith("@"):
                encoded = escape(value, {'"': "&quot;", "\t": "&#09;", "\n": "&#10;", "\r": "&#13;"})
                raw = raw.replace(key + '="' + encoded + '"', key + '="' + value + '"')
    for node in exported.iter():
        node.attrib.update({key: escape(value, {'"': "&quot;"}) for key, value in node.attrib.items()})
        if node.text:
            node.text = escape(node.text, {'"': "&quot;"})
    return {fmt: {"status": 200, "etag": '"test-etag"', "body": {"properties": {"value": text}}}
            for fmt, text in (("rawxml", raw), ("xml", ET.tostring(exported, encoding="unicode")))}


@pytest.fixture(scope="module")
def actual():
    # Explicit fixture projection, NOT a new actual capture or live evidence.
    value = d.load(d.ROOT / ".deployment/auto-path-diagnostic-20261029T145153223109Z-actual-capture.json")
    _, after = s.storage_transition()
    value["storage_sha256"] = d.r.fs.sha(after)
    value["baseline"]["state_network"] = s.state_network(after)
    return value


@pytest.fixture(scope="module")
def payloads(actual):
    return s.render(d.policy_values(actual["formats"]["global"])["xml"].encode(),
                    d.FIXTURE.read_bytes(), START, END, NONCE)


@pytest.fixture
def package(tmp_path, actual, payloads, monkeypatch):
    folder = tmp_path / "auto-path-oct30-TEST_ONLY"
    folder.mkdir()
    for name, value in payloads.items():
        d.exclusive(folder / name, value)
    before = deepcopy(actual)
    before["at_utc"] = AT.isoformat()
    d.exclusive(folder / "fresh-before.json", before)
    d.exclusive(folder / "manifest.json", {"at_utc": START, "start": START, "end": END})
    d.exclusive(folder / "transcript.txt", b"TEST_ONLY_NOT_ACTUAL_REVIEW")
    d.exclusive(folder / "parent-review.json", {"approved": True, "independent_native_review": True,
        "parent_says_cleanup": True, "stages": list(d.STAGES), "at_utc": AT.isoformat(),
        "manifest_sha256": d.sha((folder / "manifest.json").read_bytes()),
        "transcript": "transcript.txt", "transcript_sha256": d.sha((folder / "transcript.txt").read_bytes())})
    d.exclusive(folder / "browser-source.js", s.controller.browser_source().encode())
    d.exclusive(folder / "safe-events.json", {"TEST_ONLY": True})
    d.exclusive(folder / "browser-preflight.json", {"evidence": "safe-events.json",
        "evidence_sha256": d.sha((folder / "safe-events.json").read_bytes()),
        "source_sha256": d.sha((folder / "browser-source.js").read_bytes()),
        "manifest_sha256": d.sha((folder / "manifest.json").read_bytes()), "parent_observed": True,
        "safe_events_observed": True, "fixture": False, "send_invoked": False,
        "page_id": "00000000-0000-0000-0000-000000000000", "at_utc": AT.isoformat()})
    monkeypatch.setattr(s.controller, "localcheck", lambda _: d.load(folder / "manifest.json"))
    return folder


class Fake:
    def __init__(self, folder):
        self.folder = folder
        self.value = d.load(folder / "fresh-before.json")
        self.calls = []
        self.fail = None
        self.captures = 0

    def capture(self):
        self.captures += 1
        return deepcopy(self.value)

    def last(self, stage):
        if stage == self.fail:
            raise RuntimeError("TEST_ONLY_last_failed")
        return self.capture(), '"test-etag"'

    def send(self, stage, body, etag):
        assert etag == '"test-etag"'
        assert (self.folder / "parent-window-intent.json").exists()
        assert (self.folder / (stage + "-intent.json")).exists()
        self.calls.append(stage)
        if stage in ("install-global", "install-revision", "restore-global"):
            kind = "revision" if stage == "install-revision" else "global"
            self.value["formats"][kind] = pair(d.c.tree(json.loads(body)["properties"]["value"]))
            if kind == "global":
                self.value["baseline"]["apim"]["global"] = d.sha(d.policy_values(self.value["formats"][kind])["rawxml"].encode())
        else:
            for row in self.value["revisions"]:
                if row["revision"] == "2":
                    row["is_online"] = stage == "online"
        return {"http_status": 200}


def test_isolated_namespace_and_old173():
    s.prior.predecessor()
    assert s.controller is not s.prior.controller and s.controller is not d
    assert d.IP == s.prior.controller.IP == s.OLD_IP and s.controller.IP == s.IP
    assert s.controller.Stages.execute.__globals__ is s.controller.__dict__
    assert s.controller.send_once is d.send_once
    assert len(d.load(s.prior.PREDECESSOR / "manifest.json")["sources"]) == 173


def test_exact_one_IP_each_and_no_other_wire_change(actual, payloads):
    old = s.prior.render(d.policy_values(actual["formats"]["global"])["xml"].encode(),
                         d.FIXTURE.read_bytes(), START, END, NONCE)
    for name in ("global.xml", "revision.xml"):
        assert old[name].count(s.OLD_IP.encode()) == payloads[name].count(s.IP.encode()) == 1
        assert s.OLD_IP.encode() not in payloads[name]
        assert payloads[name].replace(s.IP.encode(), s.OLD_IP.encode(), 1) == old[name]
    assert payloads["restore-global.xml"] == old["restore-global.xml"]
    predicate = s.controller.expression(START, END)
    assert predicate.replace(s.IP, s.OLD_IP) == d.expression(START, END)
    assert d.c.tree(payloads["revision.xml"]).find("inbound")[2].find("when").get("condition") == "@(!(" + predicate + "))"


@pytest.mark.parametrize("kind,fmt", [(k, f) for k in ("global", "revision") for f in ("rawxml", "xml")])
def test_actual_predecessor_cannot_be_rebased_to_new_IP(actual, kind, fmt):
    bad = deepcopy(actual)
    text = bad["formats"][kind][fmt]["body"]["properties"]["value"]
    bad["formats"][kind][fmt]["body"]["properties"]["value"] = text + "<drift/>"
    with pytest.raises((RuntimeError, ET.ParseError)):
        s.initial(bad)


@pytest.mark.parametrize("field", ["baseline", "supplemental", "project", "runtime", "storage_sha256",
                                   "current_api_sha256", "inheritance", "owned_api", "revisions"])
def test_all_protected_categories_still_fail_closed(actual, field):
    bad = deepcopy(actual)
    bad[field] = {} if isinstance(bad[field], dict) else "drift"
    with pytest.raises((RuntimeError, KeyError, TypeError)):
        s.initial(bad)


def test_sources_bind_all_new_files_and_do_not_rewrite_old173():
    sources = s.sources()
    for path in (Path(s.__file__), s.TEST, s.DOC, s.NATIVE, s.BROWSER, s.BRIDGE, s.PROPOSAL):
        assert sources[path.relative_to(s.ROOT).as_posix()] == d.sha(path.read_bytes())
    for name, digest in d.load(s.prior.PREDECESSOR / "manifest.json")["sources"].items():
        assert sources[name] == digest


def test_supervised_all_six_stages_new_reservation_and_cleanup(package):
    fake = Fake(package)
    def browser(binding):
        assert binding["reservation"]["IP"] == s.IP
        assert binding["reservation"]["scoring_budget"] == 1
        assert binding["reservation"]["completion_budget"] == binding["reservation"]["retry_budget"] == 0
        assert (package / "browser-claim-intent.json").exists()
        assert not (package / "offline-intent.json").exists()
        return "TEST_ONLY_NO_SEND"
    assert s.run_reviewed_window(package, fake, browser, lambda: AT) == "TEST_ONLY_NO_SEND"
    assert fake.calls == ["install-global", "install-revision", "online", "offline", "restore-global"]
    assert fake.captures == 18  # Every stage retains before/last/after full guards.
    assert all((package / (name + "-verified.json")).exists() for name in d.STAGES)
    with pytest.raises((RuntimeError, FileExistsError)):
        s.run_reviewed_window(package, fake, browser, lambda: AT)


@pytest.mark.parametrize("failure", ["install-revision", "online", "reserve", "browser"])
def test_parent_finally_covers_activation_reserve_and_browser_failure(package, failure):
    fake = Fake(package)
    fake.fail = failure
    callback = Mock(side_effect=RuntimeError("TEST_ONLY_browser"))
    with pytest.raises(RuntimeError):
        s.run_reviewed_window(package, fake, callback, lambda: AT)
    if failure != "browser":
        callback.assert_not_called()
    assert (package / "offline-verified.json").exists()
    assert (package / "restore-global-verified.json").exists()
    assert fake.calls.count("restore-global") == 1


def test_cleanup_after_expiry_without_window_extension(package):
    fake = Fake(package)
    current = [AT]
    def callback(_):
        current[0] += timedelta(hours=1)
        # A fresh collector timestamps the expired-window cleanup read NOW;
        # an hour-old final-target timestamp must remain rejected.
        fake.value["at_utc"] = current[0].isoformat()
    s.run_reviewed_window(package, fake, callback, lambda: current[0])
    assert d.load(package / "manifest.json")["end"] == END
    assert (package / "restore-global-verified.json").exists()


def test_parent_finally_covers_local_claim_failure(package, monkeypatch):
    fake = Fake(package)
    monkeypatch.setattr(s.controller, "claim", Mock(side_effect=RuntimeError("TEST_ONLY_claim_failed")))
    callback = Mock()
    with pytest.raises(RuntimeError, match="TEST_ONLY_claim_failed"):
        s.run_reviewed_window(package, fake, callback, lambda: AT)
    callback.assert_not_called()
    assert (package / "reserve-verified.json").exists()
    assert (package / "offline-verified.json").exists()
    assert (package / "restore-global-verified.json").exists()


def test_parent_does_not_replay_partial_cleanup(package):
    fake = Fake(package)
    def callback(_):
        fake.fail = "restore-global"
    with pytest.raises(RuntimeError):
        s.run_reviewed_window(package, fake, callback, lambda: AT)
    assert (package / "offline-verified.json").exists()
    count = len(fake.calls)
    with pytest.raises(RuntimeError):
        s.run_reviewed_window(package, fake, callback, lambda: AT)
    assert len(fake.calls) == count


def test_late_start_refuses_before_any_online_or_intent(package):
    fake = Fake(package)
    with pytest.raises(RuntimeError, match="insufficient_window"):
        s.run_reviewed_window(package, fake, Mock(), lambda: AT + timedelta(minutes=3))
    assert fake.calls == [] and fake.captures == 0
    assert not (package / "parent-window-intent.json").exists()


def test_no_review_or_fixture_preflight_never_arms(package):
    value = d.load(package / "parent-review.json")
    value["stages"] = ["offline"]
    (package / "parent-review.json").write_bytes(d.encode(value))
    with pytest.raises(RuntimeError, match="actual_review_all_stages_required"):
        s.run_reviewed_window(package, Fake(package), Mock(), lambda: AT)
    assert not (package / "parent-window-intent.json").exists()


def test_prepare_injected_capture_only_then_rehash_drift_stops(actual, tmp_path, monkeypatch):
    before = deepcopy(actual)
    before["at_utc"] = AT.isoformat()
    capture = Mock(return_value=before)
    monkeypatch.setattr(s.controller.r.fs, "protect", lambda _: None)
    old_manifest = d.load(s.prior.PREDECESSOR / "manifest.json")
    folder = tmp_path / "auto-path-oct30-TEST_PREPARE_ONLY"
    manifest = s.prepare(folder, d.ROOT / old_manifest["tests"]["path"], capture, lambda: AT)
    assert capture.call_count == 1 and manifest["historical_scoring_request_count"] is None
    assert s.localcheck(folder) == manifest
    assert manifest["cloud_mutations"] == 0 and manifest["completion_budget"] == 0
    assert (folder / "browser-source.js").read_bytes().count(s.IP.encode()) == 1
    for mutation in ("body", "quota", "safety", "IP"):
        old = (folder / "revision.xml").read_bytes()
        tree = d.c.tree(old)
        if mutation == "body":
            tree.find(".//set-body").text = "drift"
        elif mutation == "quota":
            d.c.post(tree).find("limit-concurrency")[0].set("calls", "2")
        elif mutation == "safety":
            ET.SubElement(d.c.post(tree), "forward-request")
        else:
            node = tree.find("inbound")[2].find("when")
            node.set("condition", node.get("condition").replace(s.IP, s.OLD_IP))
        (folder / "revision.xml").write_bytes(ET.tostring(tree, encoding="utf-8"))
        changed = deepcopy(manifest)
        changed["artifacts"]["revision.xml"] = d.sha((folder / "revision.xml").read_bytes())
        (folder / "manifest.json").write_bytes(d.encode(changed))
        with pytest.raises(RuntimeError, match="oct30_exact_finite_fixture_delta"):
            s.localcheck(folder)
        (folder / "revision.xml").write_bytes(old)
        (folder / "manifest.json").write_bytes(d.encode(manifest))
    with pytest.raises(RuntimeError, match="existing_package_never_refresh"):
        s.prepare(folder, d.ROOT / old_manifest["tests"]["path"], capture, lambda: AT)
    assert capture.call_count == 1


def test_storage_exact_transition_preserves_capture_and_all173(actual):
    before, after = s.storage_transition()
    normalized = deepcopy(after)
    assert normalized["properties"]["networkAcls"]["ipRules"].pop() == {"value": s.IP, "action": "Allow"}
    assert normalized == before
    original = deepcopy(actual)
    s.initial(actual)
    assert actual == original
    assert len(actual["baseline"]) == 13
    assert actual["storage_sha256"] != s.prior.predecessor()[1]["storage_sha256"]
    assert actual["supplemental"] == s.prior.predecessor()[1]["supplemental"]


@pytest.mark.parametrize("field", ["allowSharedKeyAccess", "publicNetworkAccess", "networkAcls"])
def test_storage_projection_cannot_hide_other_property_drift(actual, field):
    bad = deepcopy(actual)
    bad["baseline"]["state_network"][field] = "drift"
    with pytest.raises(RuntimeError, match="fresh_storage_exact_approved_after"):
        s.initial(bad)


@pytest.mark.parametrize("field", list(d.load(s.prior.PREDECESSOR / "restore-global-after.json")["baseline"]))
def test_each_full13_field_remains_guarded_after_storage_transition(actual, field):
    bad = deepcopy(actual)
    bad["baseline"][field] = "drift"
    with pytest.raises((RuntimeError, KeyError, TypeError)):
        s.initial(bad)


def test_historical_storage_baseline_not_silently_accepted():
    old = d.load(s.prior.PREDECESSOR / "restore-global-after.json")
    with pytest.raises(RuntimeError, match="fresh_storage_exact_approved_after"):
        s.initial(old)


def test_evidence_tampering_cannot_be_blessed_by_changing_after_hash(monkeypatch, tmp_path):
    storage = tmp_path / "TEST_ONLY_STORAGE"
    storage.mkdir()
    for path in s.STORAGE.glob("*.json"):
        (storage / path.name).write_bytes(path.read_bytes())
    monkeypatch.setattr(s, "STORAGE", storage)
    value = d.load(storage / "final-account.json")
    value["account"]["properties"]["networkAcls"]["defaultAction"] = "Allow"
    (storage / "final-account.json").write_bytes(d.encode(value))
    with pytest.raises(RuntimeError, match="approved_storage_evidence"):
        s.storage_transition()
    audit = d.load(storage / "final-offline-audit.json")
    audit["evidence_sha256"]["final-account.json"] = d.sha((storage / "final-account.json").read_bytes())
    (storage / "final-offline-audit.json").write_bytes(d.encode(audit))
    with pytest.raises(RuntimeError, match="approved_storage_audit_hash"):
        s.storage_transition()


def handoff_callback(folder, *, change=None, fail=False, respond=True):
    """Simulated file parent; all evidence explicitly TEST_ONLY, never live."""
    def callback(binding):
        ticks = [0.0]
        def clock():
            return AT + timedelta(seconds=ticks[0])
        def wait(seconds):
            ticks[0] += seconds
            if respond and not (folder / "parent-browser-response.json").exists():
                assert (folder / "parent-browser-request.json").exists()
                evidence = {"TEST_ONLY": True, "send_invoked": False}
                d.exclusive(folder / "parent-browser-TEST_ONLY.json", evidence)
                value = {"at_utc": clock().isoformat(), "manifest_sha256": binding["manifest_sha256"],
                         "binding_sha256": d.sha((folder / "browser-binding.json").read_bytes()),
                         "nonce": binding["nonce"], "parent_observed": True, "fixture": False,
                         "status": "FAILED" if fail else "COMPLETED", "evidence": "parent-browser-TEST_ONLY.json",
                         "evidence_sha256": d.sha((folder / "parent-browser-TEST_ONLY.json").read_bytes())}
                if change:
                    value.update(change)
                d.exclusive(folder / "parent-browser-response.json", value)
        return s.file_browser_handoff(folder, binding, clock, lambda: ticks[0], wait)
    return callback


def test_file_handoff_actual_durable_binding_and_parent_finally(package):
    fake = Fake(package)
    value = s.run_reviewed_window(package, fake, handoff_callback(package), lambda: AT)
    assert value["status"] == "COMPLETED"
    assert d.load(package / "parent-browser-request.json")["coordination_only_not_browser_evidence"] is True
    assert (package / "offline-verified.json").exists() and (package / "restore-global-verified.json").exists()
    with pytest.raises((RuntimeError, FileExistsError)):
        s.file_browser_handoff(package, d.load(package / "browser-binding.json"), lambda: AT)


@pytest.mark.parametrize("change", [{"manifest_sha256": "a" * 64}, {"binding_sha256": "b" * 64},
    {"nonce": "c" * 32}, {"parent_observed": False}, {"fixture": True},
    {"at_utc": "2026-10-30T01:02:00Z"}, {"evidence_sha256": "d" * 64},
    {"evidence": "../outside.json"}])
def test_handoff_invalid_response_raises_into_parent_cleanup(package, change):
    fake = Fake(package)
    with pytest.raises(RuntimeError):
        s.run_reviewed_window(package, fake, handoff_callback(package, change=change), lambda: AT)
    assert (package / "offline-verified.json").exists() and (package / "restore-global-verified.json").exists()
    assert fake.calls.count("restore-global") == 1


@pytest.mark.parametrize("fail,respond", [(True, True), (False, False)])
def test_handoff_failure_or_bounded_timeout_cleans_without_retry(package, fail, respond):
    fake = Fake(package)
    with pytest.raises(RuntimeError, match="handoff_browser_failed|handoff_timeout"):
        s.run_reviewed_window(package, fake, handoff_callback(package, fail=fail, respond=respond), lambda: AT)
    assert (package / "offline-verified.json").exists() and (package / "restore-global-verified.json").exists()
    assert fake.calls.count("restore-global") == 1


def test_parent_entrypoint_pinned_existing_CA_is_verified_and_source_bound(monkeypatch):
    from scripts.deployment import auto_path_oct30_parent as parent
    monkeypatch.setattr(d.r.rt, "CA", d.r.rt.CA)
    monkeypatch.setattr(d.r.rt, "ENV", dict(d.r.rt.ENV))
    parent.configure_trusted_transport()
    assert d.r.rt.CA == str(parent.TRUSTED_CA)
    assert d.r.rt.ENV["REQUESTS_CA_BUNDLE"] == d.r.rt.ENV["SSL_CERT_FILE"] == d.r.rt.CA
    assert s.sources()[Path(parent.__file__).relative_to(s.ROOT).as_posix()] == d.sha(Path(parent.__file__).read_bytes())


def test_parent_entrypoint_CA_tamper_fails_before_configuration(monkeypatch, tmp_path):
    from scripts.deployment import auto_path_oct30_parent as parent
    fake = tmp_path / "TEST_ONLY_CA.pem"
    fake.write_bytes(b"not the pinned bundle")
    monkeypatch.setattr(parent, "TRUSTED_CA", fake)
    original = d.r.rt.CA, dict(d.r.rt.ENV)
    with pytest.raises(RuntimeError, match="exact_existing_trusted_CA"):
        parent.configure_trusted_transport()
    assert (d.r.rt.CA, d.r.rt.ENV) == original


def test_parent_entrypoint_does_not_run_on_localcheck(monkeypatch):
    from scripts.deployment import auto_path_oct30_parent as parent
    folder = d.r.rt.HOME / "auto-path-oct30-TEST_ONLY_ENTRYPOINT"
    monkeypatch.setattr(parent, "checked_package", Mock(return_value={}))
    run = Mock(side_effect=AssertionError("no activation from localcheck"))
    monkeypatch.setattr(parent, "run_parent", run)
    monkeypatch.setattr(parent.d, "sha", lambda _: "a" * 64)
    monkeypatch.setattr(Path, "read_bytes", lambda _: b"TEST_ONLY")
    parent.main(["localcheck", "--package", str(folder), "--manifest-sha256", "a" * 64])
    run.assert_not_called()


def test_parent_entrypoint_wrong_page_never_configures_or_runs(package, monkeypatch):
    from scripts.deployment import auto_path_oct30_parent as parent
    monkeypatch.setattr(parent, "checked_package", Mock(return_value={}))
    monkeypatch.setattr(s.controller, "review", Mock(return_value={}))
    monkeypatch.setattr(s.controller, "browser_preflight", Mock(return_value="TEST_ONLY"))
    configure = Mock(side_effect=AssertionError("wrong page must stop locally"))
    run = Mock(side_effect=AssertionError("wrong page must not activate"))
    monkeypatch.setattr(parent, "configure_trusted_transport", configure)
    monkeypatch.setattr(s, "run_reviewed_window", run)
    with pytest.raises(RuntimeError, match="actual_parent_page_binding"):
        parent.run_parent(package, "a" * 64, "11111111-1111-1111-1111-111111111111")
    configure.assert_not_called()
    run.assert_not_called()


def test_parent_entrypoint_existing_intent_never_runs(package, monkeypatch):
    from scripts.deployment import auto_path_oct30_parent as parent
    monkeypatch.setattr(parent, "checked_package", Mock(return_value={}))
    monkeypatch.setattr(s.controller, "review", Mock(return_value={}))
    monkeypatch.setattr(s.controller, "browser_preflight", Mock(return_value="TEST_ONLY"))
    d.exclusive(package / "activation-intent.json", {"TEST_ONLY": True})
    run = Mock(side_effect=AssertionError("no replay"))
    monkeypatch.setattr(s, "run_reviewed_window", run)
    with pytest.raises(RuntimeError, match="existing_intent_RECONCILE_NEVER_REPLAY"):
        parent.run_parent(package, "a" * 64, "00000000-0000-0000-0000-000000000000")
    run.assert_not_called()