"""Offline rollover regressions using the actual retained consumed evidence.

No collect, APIM transport, Azure CLI, browser Send, build or TF is invoked.
Fixture stage receipts are explicitly NOT actual review/browser evidence.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from unittest.mock import Mock
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import pytest

from scripts.deployment import auto_path_diagnostic_successor as s

d = s.original
START, END = "2026-10-29T16:00:00Z", "2026-10-29T16:30:00Z"
AT = datetime(2026, 10, 29, 16, 1, tzinfo=UTC)
NONCE = "c" * 32


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
    return d.load(d.ROOT / ".deployment/auto-path-diagnostic-20261029T145153223109Z-actual-capture.json")


@pytest.fixture(scope="module")
def payloads(actual):
    return s.render(d.policy_values(actual["formats"]["global"])["xml"].encode(),
                    d.FIXTURE.read_bytes(), START, END, NONCE)


@pytest.fixture
def package(tmp_path, actual, payloads, monkeypatch):
    folder = tmp_path / "auto-path-successor-TEST_ONLY"
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
    d.exclusive(folder / "browser-source.js", b"TEST_ONLY")
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
        self.unknown = None

    def capture(self):
        return deepcopy(self.value)

    def last(self, stage):
        return self.capture(), '"test-etag"'

    def send(self, stage, body, etag):
        assert etag == '"test-etag"'
        assert (self.folder / (stage + "-intent.json")).is_file()
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
        if stage == self.unknown:
            return {"transport_error": "TransportFailureUnknown"}
        return {"http_status": 200}


def test_source_path_and_private_namespace():
    assert Path(s.__file__).resolve() == d.ROOT / "scripts/deployment/auto_path_diagnostic_successor.py"
    assert sys.modules["scripts.deployment.auto_path_diagnostic_release"] is d
    assert s.controller is not d and s.controller.initial is s.initial
    assert s.controller.Stages.execute.__globals__ is s.controller.__dict__
    assert d.Stages.execute.__globals__ is d.__dict__
    assert d.initial is not s.initial and d.sources is not s.sources
    assert s.controller.collect is not d.collect
    assert s.controller.send_once is d.send_once
    assert s.controller.send_once.__globals__["wire_child"] is d.wire_child


def test_actual_consumed_provenance_and_serialization_blocker(actual):
    _, final, reference = s.predecessor()
    assert d.sha((s.PREDECESSOR / "manifest.json").read_bytes()) == s.MANIFEST_SHA
    assert actual["baseline"] == final["baseline"]
    assert d.sha(d.policy_values(actual["formats"]["global"])["xml"].encode()) != d.GLOBAL_SHA
    assert d.c.signature(d.verify_formats(actual["formats"]["global"])) == d.c.signature(reference)
    s.initial(actual)
    with pytest.raises(RuntimeError, match="fresh_global_original_not_adopted"):
        d.initial(actual)


def test_sources_freeze_successor_and_receipt():
    frozen = s.sources()
    for path in (Path(s.__file__), s.TEST, s.DOC, s.RECEIPT):
        assert frozen[path.relative_to(d.ROOT).as_posix()] == d.sha(path.read_bytes())
    assert frozen["scripts/deployment/auto_path_diagnostic_release.py"] == d.load(s.PREDECESSOR / "manifest.json")["sources"]["scripts/deployment/auto_path_diagnostic_release.py"]


@pytest.mark.parametrize("name", ["manifest.json", "offline-after.json", "restore-global-after.json",
    "offline-verified.json", "restore-global-verified.json", "revision.xml"])
def test_changed_predecessor_bytes_fail_closed(tmp_path, monkeypatch, name):
    target = tmp_path / "corrupt"
    target.write_bytes((s.PREDECESSOR / name).read_bytes() + b" ")
    real = s._digest
    monkeypatch.setattr(s, "_digest", lambda path, digest: real(target if path.name == name else path, digest))
    with pytest.raises(RuntimeError, match="consumed_predecessor_hash"):
        s.predecessor()


@pytest.mark.parametrize("name", ["reserve-intent.json", "browser-reservation.json", "browser-claim-intent.json",
                                  "browser-binding.json"])
def test_claim_or_unknown_reservation_outcome_blocks_rollover(monkeypatch, name):
    exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda path: path.name == name or exists(path))
    with pytest.raises(RuntimeError, match="known_no_reservation_or_browser_claim_only"):
        s.predecessor()


def test_fresh_render_uses_original_fixture_and_new_window_counter(actual, payloads):
    root = d.c.tree(payloads["revision.xml"])
    old = d.c.tree((s.PREDECESSOR / "revision.xml").read_bytes())
    fixture = d.c.tree(d.FIXTURE.read_bytes())
    assert root.find("inbound")[2].find("when").get("condition") == "@(!(" + d.expression(START, END) + "))"
    gate = d.c.post(root).find("limit-concurrency")
    assert gate.get("key") != d.c.post(old).find("limit-concurrency").get("key")
    gate.set("key", d.c.post(fixture).find("limit-concurrency").get("key"))
    gate[0].set("counter-key", gate.get("key"))
    root.find("inbound")[2].find("when").set("condition", fixture.find("inbound")[2].find("when").get("condition"))
    assert d.c.signature(root) == d.c.signature(fixture)
    assert payloads["restore-global.xml"] == (s.PREDECESSOR / "restore-global.xml").read_bytes()
    with pytest.raises(RuntimeError, match="render_original_diagnostic06_only"):
        s.render(d.policy_values(actual["formats"]["global"])["xml"].encode(),
                 (s.PREDECESSOR / "revision.xml").read_bytes(), START, END, NONCE)


@pytest.mark.parametrize("kind,fmt", [(k, f) for k in ("global", "revision") for f in ("xml", "rawxml")])
def test_initial_both_formats_reject_altered_content(actual, kind, fmt):
    bad = deepcopy(actual)
    bad["formats"][kind][fmt]["body"]["properties"]["value"] += "<extra/>"
    with pytest.raises((RuntimeError, ET.ParseError)):
        s.initial(bad)


@pytest.mark.parametrize("mutation", ["body", "time", "quota", "counter", "safety"])
def test_revision_full_structure_not_just_guard(actual, mutation):
    bad = deepcopy(actual)
    root = d.c.tree((s.PREDECESSOR / "revision.xml").read_bytes())
    gate = d.c.post(root).find("limit-concurrency")
    if mutation == "body":
        root.find(".//set-body").text = "changed"
    elif mutation == "time":
        node = root.find("inbound")[2].find("when")
        node.set("condition", node.get("condition").replace("639288817290000000", "639288817290000001"))
    elif mutation == "quota":
        gate[0].set("calls", "2")
    elif mutation == "counter":
        gate[0].set("counter-key", '@("different")')
    else:
        ET.SubElement(gate, "forward-request")
    bad["formats"]["revision"] = pair(root)
    with pytest.raises(RuntimeError):
        s.initial(bad)


@pytest.mark.parametrize("key", ["baseline", "supplemental", "project", "runtime", "storage_sha256",
                                 "current_api_sha256", "inheritance", "owned_api", "revisions"])
def test_protected_state_rejects_all_categories(actual, key):
    bad = deepcopy(actual)
    bad[key] = {} if isinstance(bad[key], dict) else "drift"
    with pytest.raises((RuntimeError, KeyError, TypeError)):
        s.initial(bad)


def test_fresh_raw_hash_cannot_be_restamped(actual):
    bad = deepcopy(actual)
    bad["baseline"]["apim"]["global"] = d.GLOBAL_SHA
    with pytest.raises(RuntimeError, match="full13_global_raw_hash_binding"):
        s.initial(bad)


def test_install_from_oldcandidate_cleanup_retains_newcandidate_offline(package):
    adapter = Fake(package)
    before = deepcopy(adapter.value)
    s.guarded(before, adapter.value, package, False, False, False)
    stages = s.Stages(package, adapter, lambda: AT)
    stages.activate()
    stages.cleanup()
    assert adapter.calls == ["install-global", "install-revision", "online", "offline", "restore-global"]
    assert d.c.signature(d.verify_formats(adapter.value["formats"]["revision"])) == d.c.signature(d.c.tree((package / "revision.xml").read_bytes()))
    assert next(row for row in adapter.value["revisions"] if row["revision"] == "2")["is_online"] is False
    s.guarded(before, adapter.value, package, False, True, False)
    with pytest.raises(RuntimeError, match="existing_intent_NO_RETRY"):
        stages.cleanup()


@pytest.mark.parametrize("unknown", ["install-global", "install-revision", "online"])
def test_unknown_activation_no_replay_and_original_global_cleanup(package, unknown):
    adapter = Fake(package)
    adapter.unknown = unknown
    stages = s.Stages(package, adapter, lambda: AT)
    with pytest.raises(RuntimeError):
        stages.activate()
    assert d.load(package / "activation-cleanup.json")["status"] == "OFFLINE_AND_ORIGINAL_GLOBAL_INDEPENDENTLY_VERIFIED"
    count = len(adapter.calls)
    with pytest.raises((RuntimeError, FileExistsError)):
        stages.activate()
    assert len(adapter.calls) == count


@pytest.mark.parametrize("unknown", ["offline", "restore-global"])
def test_cleanup_unknown_stops_no_replay_even_after_expiry(package, unknown):
    adapter = Fake(package)
    s.Stages(package, adapter, lambda: AT).activate()
    adapter.unknown = unknown
    adapter.value["at_utc"] = (AT + timedelta(days=1)).isoformat()
    stages = s.Stages(package, adapter, lambda: AT + timedelta(days=1))
    with pytest.raises(RuntimeError):
        stages.cleanup()
    assert (package / "restore-global-intent.json").exists() is (unknown == "restore-global")
    count = len(adapter.calls)
    with pytest.raises(RuntimeError, match="existing_intent_NO_RETRY"):
        stages.cleanup()
    assert len(adapter.calls) == count


def test_original_fixture_not_adoptable_as_fresh_revision(actual):
    bad = deepcopy(actual)
    bad["formats"]["revision"] = pair(d.c.tree(d.FIXTURE.read_bytes()))
    with pytest.raises(RuntimeError):
        s.initial(bad)


def test_prepare_uses_one_injected_capture_and_freezes_fresh_actual(actual, tmp_path, monkeypatch):
    before = deepcopy(actual)
    before["at_utc"] = AT.isoformat()
    capture = Mock(return_value=before)
    monkeypatch.setattr(s.controller.r.fs, "protect", lambda _: None)
    old_manifest = d.load(s.PREDECESSOR / "manifest.json")
    receipt = d.ROOT / old_manifest["tests"]["path"]
    folder = tmp_path / "auto-path-successor-TEST_PREPARE_ONLY"
    manifest = s.prepare(folder, receipt, capture_fn=capture, clock=lambda: AT)
    assert capture.call_count == 1
    assert d.load(folder / "fresh-before.json") == before
    assert manifest["start"] == AT.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert manifest["historical_scoring_request_count"] is None
    assert manifest["scoring_budget"] == 1 and manifest["cloud_mutations"] == 0
    assert s.localcheck(folder) == manifest
    # A new owner must not invalidate predecessor provenance or its own cleanup.
    d.exclusive(folder / "browser-send-intent.json", {"TEST_ONLY": True})
    owner = {"manifest_sha256": d.sha((folder / "manifest.json").read_bytes()),
             "parent_intent_sha256": d.sha((folder / "browser-send-intent.json").read_bytes()), "scope": d.SCOPE}
    d.exclusive(folder.parent / "auto-path-diagnostic-attempt-owner.json", owner)
    assert s.localcheck(folder) == manifest
    capture.reset_mock()
    with pytest.raises(RuntimeError, match="attempt_already_consumed"):
        s.prepare(tmp_path / "auto-path-successor-ANOTHER", receipt, capture_fn=capture, clock=lambda: AT)
    capture.assert_not_called()
    (folder.parent / "auto-path-diagnostic-attempt-owner.json").unlink()
    with pytest.raises(RuntimeError, match="existing_package_never_refresh"):
        s.prepare(folder, receipt, capture_fn=capture, clock=lambda: AT)
    capture.assert_not_called()
    # Rehashing an altered candidate is not enough: the finite fixture delta is
    # independently reconstructed by localcheck, including body/quota/safety.
    for mutation in ("body", "time", "quota", "counter", "safety"):
        root = d.c.tree((folder / "revision.xml").read_bytes())
        gate = d.c.post(root).find("limit-concurrency")
        if mutation == "body":
            root.find(".//set-body").text = "changed"
        elif mutation == "time":
            node = root.find("inbound")[2].find("when")
            node.set("condition", node.get("condition") + " || true")
        elif mutation == "quota":
            gate[0].set("calls", "2")
        elif mutation == "counter":
            gate[0].set("counter-key", '@("different")')
        else:
            ET.SubElement(gate, "forward-request")
        prior = (folder / "revision.xml").read_bytes()
        (folder / "revision.xml").write_bytes(ET.tostring(root, encoding="utf-8"))
        changed = deepcopy(manifest)
        changed["artifacts"]["revision.xml"] = d.sha((folder / "revision.xml").read_bytes())
        (folder / "manifest.json").write_bytes(d.encode(changed))
        with pytest.raises(RuntimeError, match="successor_exact_finite_fixture_delta"):
            s.localcheck(folder)
        (folder / "revision.xml").write_bytes(prior)
        (folder / "manifest.json").write_bytes(d.encode(manifest))


def test_fixture_preflight_not_reused_for_real_activation(package):
    value = d.load(package / "browser-preflight.json")
    value["fixture"] = True
    (package / "browser-preflight.json").write_bytes(d.encode(value))
    with pytest.raises(RuntimeError, match="actual_safe_browser_events_required_NOT_fixture"):
        s.Stages(package, Fake(package), lambda: AT).activate()
    assert not (package / "activation-intent.json").exists()