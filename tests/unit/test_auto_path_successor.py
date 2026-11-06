from datetime import timedelta
import pytest

from scripts.proposals import auto_path_successor as s


def test_current_customer_is_only_baseline_delta():
    old = s.a.load(s.a.HOME / "protected-before.json")
    new = s.expected_baseline()
    assert new["runtime"]["sites"]["customer"]["image"] == s.CUSTOMER
    new["runtime"]["sites"]["customer"]["image"] = old["runtime"]["sites"]["customer"]["image"]
    assert new == old


@pytest.mark.parametrize("component", list(s.expected_baseline()))
def test_every_protected_component_rejects_drift(component):
    value = s.expected_baseline()
    value[component] = None
    with pytest.raises(RuntimeError):
        s.guard_baseline(value, s.a.load(s.a.HOME / "supplemental-before.json"))


def test_exact_current_baseline_passes():
    s.guard_baseline(s.expected_baseline(), s.a.load(s.a.HOME / "supplemental-before.json"))


def test_supplemental_drift_rejected():
    with pytest.raises(RuntimeError):
        s.guard_baseline(s.expected_baseline(), {})


@pytest.mark.parametrize("etag", [None, "*", "", "old", '"x"\r\nX: bad'])
def test_wire_rejects_bad_etag(etag):
    with pytest.raises(RuntimeError):
        s.stage_request("global-put", etag, "synthetic", b"{}")


@pytest.mark.parametrize("stage", ["global-put", "global-restore", "diagnostic-put", "diagnostic-restore", "online", "offline"])
def test_exact_wire_scope(stage):
    request = s.stage_request(stage, '"opaque"', "synthetic", b"{}")
    assert request.get_method() == ("PATCH" if stage in ("online", "offline") else "PUT")
    assert request.full_url == (s.GLOBAL_URL if stage.startswith("global-") else s.core.POLICY_URL if stage.startswith("diagnostic-") else s.a.URL)
    assert request.get_header("If-match") == '"opaque"'


@pytest.mark.parametrize("stage", ["delete", "apply", "reserve-browser", "current1"])
def test_unknown_wire_stage_rejected(stage):
    with pytest.raises(RuntimeError):
        s.stage_request(stage, '"opaque"', "synthetic", b"{}")


def test_durable_evidence_never_overwrites(tmp_path):
    s.write(tmp_path, "intent.json", {"one": 1})
    with pytest.raises(FileExistsError):
        s.write(tmp_path, "intent.json", {"one": 2})
    assert s.load(tmp_path, "intent.json") == {"one": 1}


def test_raw_global_splice_preserves_surrounding_bytes():
    raw = '<policies>\r\n<when condition="@(!(a &amp;&amp; b))">keep</when></policies>'
    result = s.raw_condition(raw, "@(!(a && b))", "@((!(a && b)) && !(c))")
    assert result.startswith('<policies>\r\n<when ')
    assert result.endswith('>keep</when></policies>')
    assert s.raw_condition(result, "@((!(a && b)) && !(c))", "@(!(a && b))") == raw


@pytest.mark.parametrize("raw", ["<policies/>", '<when condition="@(a)"/><when condition="@(a)"/>'])
def test_raw_global_unknown_or_duplicate_span_rejected(raw):
    with pytest.raises(RuntimeError):
        s.raw_condition(raw, "@(a)", "@(b)")


@pytest.mark.parametrize("age", [-1, 61])
def test_future_or_stale_evidence_rejected(age):
    with pytest.raises(RuntimeError):
        s.fresh_time((s.now() - timedelta(seconds=age)).isoformat(), 60)


def test_missing_fresh_capture_never_wires(monkeypatch, tmp_path):
    monkeypatch.setattr(s, "check", lambda *args: {})
    def rejected(*args):
        raise RuntimeError("actual_capture_required")
    monkeypatch.setattr(s, "stage_capture", rejected)
    monkeypatch.setattr(s, "once", lambda *args: pytest.fail("must never wire"))
    with pytest.raises(RuntimeError, match="actual_capture_required"):
        s.execute(tmp_path, "global-put")


def test_no_window_before_actual_readiness(tmp_path):
    with pytest.raises(FileNotFoundError):
        s.freeze(tmp_path, tmp_path / "absent.xml")
    assert not (tmp_path / "manifest.json").exists()


def test_render_actual_retained_policies_offline_only():
    retained = s.a.load(s.a.HOME / "scoring-diagnostic01/prepare-capture.json")
    # Expired fixed fixture, no freeze, no manifest or cloud operation.
    captured = {"global_formats": {"xml": retained["inheritance"]["/policies/policy?format=xml"],
                "rawxml": {"body": {"properties": {"value": s.core.ET.tostring(
                    s.core.tree(retained["inheritance"]["/policies/policy?format=xml"]["body"]["properties"]["value"], exported=True)).decode()
                    .replace("&quot;", '"')}}}},
                "diagnostic_formats": {"rawxml": {"body": {"properties": {"value": s.OLD.joinpath("diagnostic.xml").read_bytes().decode()}}}}}
    artifacts = s.render(captured, "2026-10-29T10:16:50Z", "2026-10-29T10:46:50Z", "1" * 32)
    assert artifacts["diagnostic-candidate.xml"].count(b"auto-diagnostic:" + b"1" * 32) == 2
    assert b"<base" in artifacts["diagnostic-candidate.xml"]
    assert b"167.103.66.248" in artifacts["global-candidate-reference.xml"]
    assert artifacts["global-original.rawxml"] == captured["global_formats"]["rawxml"]["body"]["properties"]["value"].encode()


def test_kernel_stage_lock_released_after_exception(tmp_path):
    with pytest.raises(ValueError):
        with s.stage_lock(tmp_path):
            raise ValueError()
    with s.stage_lock(tmp_path):
        pass


@pytest.mark.parametrize("stage", s.CLEANUP)
def test_cleanup_review_not_blocked_by_expiry(stage, monkeypatch, tmp_path):
    # Focused real check() with mocked disk contents, no transport.
    manifest = {"sources": {}, "baseline_sha256": "h", "baseline_binding_sha256": "h",
                "artifacts": {}, "tests": {"path": "receipt", "sha256": "h"},
                "browser_tests": {"path": "browser-receipt", "sha256": "h"},
                "start": "2000-01-01T00:00:00Z", "end": "2000-01-01T00:30:00Z"}
    monkeypatch.setattr(s, "load", lambda *args: manifest)
    monkeypatch.setattr(s, "sources", lambda: {})
    monkeypatch.setattr(s.p, "sha", lambda *args: "h")
    monkeypatch.setattr(s, "parent_review", lambda *args: {"stages": list(s.STAGES), "at_utc": "2000-01-01T00:00:00Z"})
    assert s.check(tmp_path, stage) == manifest


@pytest.mark.parametrize("stage", s.STAGES[:4])
def test_activation_blocked_after_expiry(stage, monkeypatch, tmp_path):
    manifest = {"sources": {}, "baseline_sha256": "h", "baseline_binding_sha256": "h",
                "artifacts": {}, "tests": {"path": "receipt", "sha256": "h"},
                "browser_tests": {"path": "browser-receipt", "sha256": "h"},
                "start": "2000-01-01T00:00:00Z", "end": "2000-01-01T00:30:00Z"}
    monkeypatch.setattr(s, "load", lambda *args: manifest)
    monkeypatch.setattr(s, "sources", lambda: {})
    monkeypatch.setattr(s.p, "sha", lambda *args: "h")
    monkeypatch.setattr(s, "parent_review", lambda *args: {"stages": list(s.STAGES), "at_utc": "2000-01-01T00:00:00Z"})
    with pytest.raises(RuntimeError):
        s.check(tmp_path, stage)


def test_finite_policy_state_candidate_and_original(tmp_path):
    for state, expression in (("original", "@(true)"), ("candidate", "@(false)")):
        reference = '<policies><inbound><when condition="' + expression + '"/></inbound></policies>'
        s.write(tmp_path, "global-" + state + "-reference.xml", reference.encode())
    for wanted, expression in (("original", "@(true)"), ("candidate", "@(false)")):
        raw = '<policies><inbound><when condition="' + expression + '"/></inbound></policies>'
        formats = {f: {"body": {"properties": {"value": raw}}} for f in ("rawxml", "xml")}
        assert s.policy_state(formats, tmp_path, "global") == wanted
    raw = '<policies><inbound><when condition="@(null)"/></inbound></policies>'
    with pytest.raises(RuntimeError, match="STOP_NO_CLOBBER"):
        s.policy_state({f: {"body": {"properties": {"value": raw}}} for f in ("rawxml", "xml")}, tmp_path, "global")


@pytest.mark.parametrize("component", list(s.expected_baseline()))
def test_temporary_global_exception_never_waives_other_components(component):
    value = s.expected_baseline()
    raw = b"verified-candidate-fixture"
    value["apim"]["global"] = s.digest(raw)
    if component == "apim":
        value["apim"]["legacy"] = "bad"
    else:
        value[component] = None
    with pytest.raises(RuntimeError):
        s.normalize_baseline(value, s.a.load(s.a.HOME / "supplemental-before.json"),
            {"rawxml": {"body": {"properties": {"value": raw.decode()}}}}, b"original", "candidate")


def test_temporary_global_normalization_only_verified_hash():
    value = s.expected_baseline()
    raw = b"verified-candidate-fixture"
    value["apim"]["global"] = s.digest(raw)
    formats = {"rawxml": {"body": {"properties": {"value": raw.decode()}}}}
    assert s.normalize_baseline(value, s.a.load(s.a.HOME / "supplemental-before.json"), formats, b"original", "candidate") == s.expected_baseline()
    with pytest.raises(RuntimeError):
        s.normalize_baseline(value, s.a.load(s.a.HOME / "supplemental-before.json"), formats, b"original", "original")


def test_cleanup_stops_on_unknown_offline_no_restore(monkeypatch, tmp_path):
    calls = []
    def rejected(folder, stage):
        calls.append(stage)
        raise RuntimeError("unknown")
    monkeypatch.setattr(s, "execute", rejected)
    errors = s.cleanup(tmp_path)
    assert calls == ["offline"] and len(errors) == 1


def test_consumed_cleanup_reconciles_without_wire(monkeypatch, tmp_path):
    for stage in s.CLEANUP:
        s.write(tmp_path, stage + "-intent.json", {})
    monkeypatch.setattr(s, "stage_capture", lambda *args: ({"online": False, "global_state": "original", "diagnostic_state": "original"}, None))
    monkeypatch.setattr(s, "execute", lambda *args: pytest.fail("must never retry consumed stage"))
    assert s.cleanup(tmp_path) == []


@pytest.mark.parametrize("online", [False, True])
def test_owned_online_only_matches_independent_revision_list(online):
    saved = {"id": "owned2", "properties": {"isOnline": False, "subscriptionRequired": True}}
    actual = s.deepcopy(saved)
    actual["properties"]["isOnline"] = online
    s.guard_owned_metadata(actual, saved, online)
    assert saved["properties"]["isOnline"] is False
    assert actual["properties"]["isOnline"] is online


@pytest.mark.parametrize("bad", [None, "true", 1, False])
def test_owned_online_conflict_or_nonboolean_rejected(bad):
    saved = {"properties": {"isOnline": False, "subscriptionRequired": True}}
    actual = s.deepcopy(saved)
    actual["properties"]["isOnline"] = bad
    with pytest.raises(RuntimeError):
        s.guard_owned_metadata(actual, saved, True)


def test_owned_online_never_waives_other_metadata():
    saved = {"properties": {"isOnline": False, "subscriptionRequired": True}}
    actual = {"properties": {"isOnline": True, "subscriptionRequired": False}}
    with pytest.raises(RuntimeError):
        s.guard_owned_metadata(actual, saved, True)


def test_owned_absent_online_cannot_be_invented():
    saved = {"properties": {"subscriptionRequired": True}}
    s.guard_owned_metadata(saved, saved, True)
    with pytest.raises(RuntimeError):
        s.guard_owned_metadata({"properties": {"subscriptionRequired": True, "isOnline": True}}, saved, True)