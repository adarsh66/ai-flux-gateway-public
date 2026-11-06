"""Synthetic/offline r5 tests. Saved evidence is NEVER a fresh prepare capture."""
from copy import deepcopy
from datetime import timedelta
import socket
from unittest.mock import Mock

import pytest

from scripts.deployment import auto_path_oct30_successor_r5 as r5

d, reads, r4 = r5.d, r5.reads, r5.r4


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    denied = Mock(side_effect=AssertionError("R5_OFFLINE_NETWORK_OR_SEND_FORBIDDEN"))
    original_send = r5.controller.send_once
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(r5.controller, "send_once", denied)
    yield original_send
    denied.assert_not_called()


@pytest.fixture
def data():
    historical, comparison = reads.evidence()
    # Construct ONLY a synthetic transport fixture from retained projections;
    # the original raw22 was NOT retained and is never claimed reconstructed.
    rows = deepcopy(historical["value"])
    for row in comparison["current_deployments"]:
        if row["name"] not in reads.ADDED:
            continue
        rows.append({"id": row["id"], "name": row["name"], "etag": row["etag"],
            "sku": deepcopy(row["sku"]), "systemData": {key: row[key] for key in ("createdAt", "lastModifiedAt")},
            "properties": {key: deepcopy(row[key]) for key in ("model", "currentCapacity", "raiPolicyName",
                "provisioningState", "deploymentState", "capabilities", "versionUpgradeOption", "rateLimits")}})
    return historical, comparison, {"value": rows}


def prove(data, references=None):
    historical, comparison, full = data
    return reads.protect(full, [deepcopy(full)], {} if references is None else references, historical, comparison)


def test_unchanged13_plus_exact_known9_passes_and_full_fields_retained(data):
    historical, _, full = data
    subset, proof = prove(data)
    assert subset == historical and d.r.fs.sha(subset) == reads.HISTORICAL_SHA
    assert proof["account_count"] == 22 and proof["protected_count"] == 13
    assert proof["addition_names"] == sorted(reads.ADDED)
    assert proof["account"] == full and set(proof["additions"]) == reads.ADDED
    assert "Decision-1" in reads.PROTECTED and "glm-5.3" not in reads.PROTECTED
    assert proof["protected_sha256"] != proof["account_sha256"]
    full["value"][0]["etag"] = "poison"
    assert proof["account"]["value"][0]["etag"] != "poison"


@pytest.mark.parametrize("name", ["Decision-1", "gpt-4o", "gpt-6.1-sol"])
def test_protected_missing_or_decision_missing_rejected(data, name):
    data[2]["value"] = [row for row in data[2]["value"] if row["name"] != name]
    with pytest.raises(RuntimeError, match="known_membership"):
        prove(data)


@pytest.mark.parametrize("field", ["model", "version", "sku", "capacity", "rai", "state", "etag", "unknown"])
def test_every_protected_field_including_unknown_raw_fields_fails(data, field):
    row = data[2]["value"][0]
    if field == "model":
        row["properties"]["model"]["name"] = "different"
    elif field == "version":
        row["properties"]["model"]["version"] = "different"
    elif field == "sku":
        row["sku"]["name"] = "different"
    elif field == "capacity":
        row["sku"]["capacity"] += 1
    elif field == "rai":
        row["properties"]["raiPolicyName"] = "Microsoft.Nil"
    elif field == "state":
        row["properties"]["provisioningState"] = "Failed"
    elif field == "etag":
        row["etag"] = '"changed"'
    else:
        row["unprojected_new_field"] = "must_not_ignore"
    with pytest.raises(RuntimeError, match="protected_full_metadata_hash"):
        prove(data)


@pytest.mark.parametrize("kind", ["new", "deleted", "changed", "duplicate", "foreign"])
def test_known_bad_account_membership_or_metadata_fails(data, kind):
    full = data[2]
    extra = next(row for row in full["value"] if row["name"] in reads.ADDED)
    if kind == "new":
        extra = deepcopy(extra)
        extra["name"] = "future-deployment"
        extra["id"] = reads.ACCOUNT + "/deployments/" + extra["name"]
        full["value"].append(extra)
    elif kind == "deleted":
        full["value"].remove(extra)
    elif kind == "changed":
        extra["etag"] = '"changed"'
    elif kind == "duplicate":
        full["value"].append(deepcopy(extra))
    else:
        extra["id"] = extra["id"].replace("poc-ids-token-ex-foundry", "foreign-account")
    with pytest.raises(RuntimeError):
        prove(data)


@pytest.mark.parametrize("target", ["protected_route", "scorer", "safety_policy", "candidate_snapshot", "auth_binding"])
def test_added_model_reference_in_any_protected_target_rejected(data, target):
    with pytest.raises(RuntimeError, match="added_deployment_referenced"):
        prove(data, {target: "https://example/deployments/claude-opus-5-5"})


@pytest.mark.parametrize("text", ["CLAUDE-OPUS-5-5", "claude%2dopus%2d5%2d5", "claude&#45;opus&#45;5&#45;5"])
def test_reference_encoding_never_bypasses_check(text):
    with pytest.raises(RuntimeError, match="added_deployment_referenced"):
        reads.absent_references(text)


def test_complete_two_page_collection_accepted_without_dropping_fields(data):
    full = data[2]
    link = reads.URL + "&$skiptoken=second"
    pages = [{"value": full["value"][:13], "nextLink": link}, {"value": full["value"][13:]}]
    fetched = Mock(side_effect=deepcopy(pages))
    actual, retained = reads.complete_collection(fetched)
    assert actual == full and retained == pages
    assert [call.args[0] for call in fetched.call_args_list] == [reads.URL, link]
    assert reads.protect(actual, retained, {}, *data[:2])[0] == data[0]


@pytest.mark.parametrize("kind", ["partial", "missing_page", "cycle", "foreign_link", "wrong_version",
    "duplicate_page", "empty_continuation", "unknown_envelope", "extra_page", "bad_link"])
def test_partial_or_malicious_pagination_fails(data, kind):
    first = deepcopy(data[2])
    if kind == "partial":
        first["partial"] = True
    elif kind == "unknown_envelope":
        first["ignored"] = "not allowed"
    elif kind == "bad_link":
        first["nextLink"] = 1
    elif kind == "extra_page":
        with pytest.raises(RuntimeError, match="exact_complete_page_chain"):
            reads.protect(first, [first, first], {}, *data[:2])
        return
    else:
        first["nextLink"] = reads.URL + "&$skiptoken=next"
        if kind == "cycle":
            first["nextLink"] = reads.URL
        elif kind == "foreign_link":
            first["nextLink"] = first["nextLink"].replace("management.azure.com", "foreign.example")
        elif kind == "wrong_version":
            first["nextLink"] = first["nextLink"].replace("2025-06-01", "2024-01-01")
        elif kind == "empty_continuation":
            first["value"] = []
    following = {"value": deepcopy(first["value"])} if kind == "duplicate_page" else None
    with pytest.raises((RuntimeError, StopIteration)):
        reads.complete_collection(Mock(side_effect=[first] if following is None else [first, following]))


def test_full_unknown_addition_metadata_is_bound_and_drift_rejected(data, monkeypatch):
    monkeypatch.setattr(reads, "evidence", lambda: data[:2])
    first, second = deepcopy(data[2]), deepcopy(data[2])
    extra = next(row for row in second["value"] if row["name"] in reads.ADDED)
    extra["unprojected_field"] = "changed"
    ledger = reads.InventoryReads(Mock(side_effect=[first, second]), {})
    assert ledger.read() == data[0]
    with pytest.raises(RuntimeError, match="account_drift_during_capture"):
        ledger.read()
    assert len(ledger.observations) == 1


def test_consistent_metadata_and_supplement_projection_use_same_reader(data, monkeypatch):
    monkeypatch.setattr(reads, "evidence", lambda: data[:2])
    ledger = reads.InventoryReads(Mock(side_effect=[deepcopy(data[2]), deepcopy(data[2])]), {})
    snapshot, supplement = ledger.read(), ledger.read()
    assert d.r.fs.sha(snapshot) == reads.HISTORICAL_SHA
    assert len(supplement["value"]) == 13
    assert d.r.fs.sha({r["name"]: r["properties"].get("raiPolicyName") for r in supplement["value"]}) == (
        "9c1f27b849d2698ffde96f5925e76ab686f6623daf5c94ffc248aba2141ab5a1")
    assert len(ledger.observations) == 2


def test_private_namespaces_originals_unchanged_without_opening_network(monkeypatch):
    # Building a strict opener is local. Use the existing OS-root evidence bundle
    # ONLY for this offline constructor test, never change a shared CA setting.
    monkeypatch.setattr(reads.RUNTIME, "CA", str(reads.EVIDENCE / "os-trusted-roots.pem"))
    original = (d.r.rt.cli, d.r.rt.arm, d.r.rt.urlopen, d.r.persistence.release.ProductRun,
        d.r.persistence.release.snapshot, d.r.supplemental, product_rt_cli())
    private, ledger = reads.private_controller({})
    assert private.r.rt is not d.r.rt and private.r.persistence.release is not d.r.persistence.release
    assert private.r.persistence.release.snapshot.__globals__ is vars(private.r.persistence.release)
    assert private.r.supplemental.__globals__["r"].rt is private.r.rt
    assert private.r.persistence.release.rt is private.r.rt
    assert ledger.observations == []
    assert original == (d.r.rt.cli, d.r.rt.arm, d.r.rt.urlopen, d.r.persistence.release.ProductRun,
        d.r.persistence.release.snapshot, d.r.supplemental, product_rt_cli())


def product_rt_cli():
    return reads.product.rt.cli


def test_all268_and_original_six_artifacts_unchanged():
    assert all(d.sha((d.ROOT / name).read_bytes()) == digest for name, digest in d.load(r5.FROZEN)["sources"].items())
    assert len(d.load(r5.FROZEN)["sources"]) == 268
    prior = d.ROOT / ".deployment/auto-path-oct30-successor-20261030T074052868393Z"
    manifest = d.load(prior / "manifest.json")
    assert all(d.sha((prior / name).read_bytes()) == digest for name, digest in manifest["artifacts"].items())
    assert set(r5.OWN_FILES) <= set(r5.sources())


def test_same_six_stages_timing_cleanup_and_parent_without_shared_rebinding(offline):
    assert r5.MINIMUM_REMAINING == timedelta(minutes=22)
    assert r5.controller.STAGES == d.STAGES and len(d.STAGES) == 6
    assert r5.controller.window("2026-10-30T12:00:00Z", "2026-10-30T12:30:00Z")[1] - (
        r5.controller.window("2026-10-30T12:00:00Z", "2026-10-30T12:30:00Z")[0]) == timedelta(minutes=30)
    assert r5.Stages.activate.__code__ is d.Stages.activate.__code__
    assert r5.Stages.cleanup.__code__ is d.Stages.cleanup.__code__
    assert r5.Stages._execute.__globals__ is vars(r5.controller)
    # The inherited controller is compiled in an isolated module. Equal code,
    # not object identity, proves inheritance; its globals must remain private.
    assert r5.controller.review.__code__ == d.review.__code__
    assert r5.controller.claim.__code__ == d.claim.__code__
    assert r5.controller.review.__globals__ is vars(r5.controller)
    assert r5.controller.claim.__globals__ is vars(r5.controller)
    assert offline.__code__ is d.send_once.__code__
    assert offline.__globals__ is vars(r5.controller)
    assert r5.controller.wire_child is d.wire_child
    assert r5.successor._run_reviewed_window.__globals__["MINIMUM_REMAINING"] == timedelta(minutes=22)
    assert r5.parent_cli().s is r5.successor and r5.parent_cli().d is r5.controller
    assert r5.controller.r.rt is reads.RUNTIME and reads.RUNTIME is not d.r.rt


def test_no_account_proof_cannot_be_accepted_as_r5_capture():
    with pytest.raises(RuntimeError, match="actual_complete_account_evidence_required"):
        r5.account_proof({})


def test_real_private_snapshot_and_supplemental_share_full_inventory_projection(data, monkeypatch):
    """Real inherited consumers, with only external read boundaries synthetic."""
    import base64
    from io import BytesIO
    monkeypatch.setattr(reads.RUNTIME, "CA", str(reads.EVIDENCE / "os-trusted-roots.pem"))
    claims = base64.urlsafe_b64encode(d.encode({"tid": reads.RUNTIME.TENANT,
        "oid": reads.RUNTIME.OPERATOR})).decode().rstrip("=")
    token = "TEST_ONLY." + claims + ".TEST_ONLY"
    monkeypatch.setattr(reads.RUNTIME, "cli", lambda args: {"accessToken": token})
    settings = {"api": {"AIFLUX_APIM_PRODUCT_ID": "aiflux"}, "customer": {}, "admin": {},
        "ingestion": {"AzureWebJobs.ingest_usage.Disabled": "false",
            "AIFLUX_INGESTION_START_AT": "2026-10-27T06:06:02.045288+00:00"}}
    monkeypatch.setattr(reads.product.fs, "current_settings", lambda: deepcopy(settings))
    monkeypatch.setattr(reads.product.portals, "baseline", lambda: {"sites": {
        "ingestion": {"protected": {"web": {"alwaysOn": True}}}}, "roleAssignments": []})
    monkeypatch.setattr(reads.product_reads.ReadOnlyProductRun, "__init__", lambda self: None)
    fragment_id = d.r.persistence.release.ID
    def arm(self, suffix, method="GET"):
        assert method == "GET"
        if suffix.startswith("/policyFragments/"):
            return {"id": fragment_id, "properties": {"value": "<fragment/>"}}
        if "policies/policy?format=" in suffix:
            return {"properties": {"value": "<policies/>"}}
        return {"value": [], "identity": {"type": "SystemAssigned"}}
    monkeypatch.setattr(reads.product_reads.ReadOnlyProductRun, "arm", arm)
    monkeypatch.setattr(reads.product_reads.ReadOnlyProductRun, "metadata", lambda self: {})
    monkeypatch.setattr(d.r.persistence.release, "without_created_fragment", lambda value: value)
    _, storage = r4.r3.old.storage_transition()
    calls = []
    class Response(BytesIO):
        status = 200
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            assert request.get_method() == "GET" and timeout == 90
            value = (data[2] if request.full_url == reads.URL else storage
                if request.full_url == d.r.persistence.backend.URL else {"value": []})
            return Response(d.encode(value))
    monkeypatch.setattr(d.a, "opener", lambda _: Opener())
    # Bypass diagnostic persistence ONLY in this synthetic test; URL/method
    # labeling and the real bounded read remain exercised.
    from contextlib import contextmanager
    @contextmanager
    def opened(self, request, *, timeout):
        r4.reads.label(request)
        with self.opener.open(request, timeout=timeout) as response:
            yield response
    monkeypatch.setattr(r4.reads.TimedOpen, "open", opened)
    private, ledger = reads.private_controller({})
    snapshot = private.r.persistence.release.snapshot()
    supplemental = private.r.supplemental(snapshot)
    ledger.read()
    assert len(snapshot) == 13 and snapshot["model_metadata_sha256"] == reads.HISTORICAL_SHA
    assert snapshot["state_network"] == r4.r3.old.state_network(storage)
    assert supplemental["rai_bindings_sha256"] == "9c1f27b849d2698ffde96f5925e76ab686f6623daf5c94ffc248aba2141ab5a1"
    assert calls.count(reads.URL) == 3 and len(ledger.observations) == 3
    assert calls.count(d.r.persistence.backend.URL) == 1


def capture_fixture(data):
    comparison = data[1]
    capture = d.load(d.ROOT / comparison["last_successful_frozen_capture"])
    references = {"formats": capture["formats"], "inheritance": capture["inheritance"],
        "owned_api": capture["owned_api"], "baseline": capture["baseline"],
        "source_snapshots": {name: (d.ROOT / name).read_bytes().decode() for name in reads.REFERENCE_FILES}}
    _, proof = prove(data, references["source_snapshots"])
    capture["account_inventory_r5"] = {"complete": True, "observations": [deepcopy(proof) for _ in range(3)],
        "references_sha256": d.r.fs.sha(references)}
    return capture


def test_actual_account_proof_and_guard_call_existing_guard_only_after_whole_account_check(data, monkeypatch):
    capture = capture_fixture(data)
    assert r5.account_proof(capture)["account_count"] == 22
    inherited = Mock(return_value="INHERITED_GUARD_TEST_ONLY")
    monkeypatch.setattr(r4.controller, "guarded", inherited)
    assert r5.guarded(capture, deepcopy(capture), None, False, False, False) == "INHERITED_GUARD_TEST_ONLY"
    inherited.assert_called_once()
    changed = deepcopy(data)
    extra = next(row for row in changed[2]["value"] if row["name"] in reads.ADDED)
    extra["new_raw_field"] = "different_within_attempt"
    current = capture_fixture(changed)
    r5.account_proof(current)  # Self-consistent later raw proof cannot override the attempt's first hash.
    with pytest.raises(RuntimeError, match="whole_account_drift_across_attempt"):
        r5.guarded(capture, current, None, False, False, False)
    assert inherited.call_count == 1


@pytest.mark.parametrize("field", ["complete", "observations", "references_sha256", "account_sha256", "pages", "rai"])
def test_forged_account_proofs_cannot_bless_capture(data, field):
    capture = capture_fixture(data)
    proof = capture["account_inventory_r5"]
    if field == "complete":
        proof[field] = False
    elif field == "observations":
        proof[field].pop()
    elif field == "references_sha256":
        proof[field] = "0" * 64
    elif field == "rai":
        capture["supplemental"]["rai_bindings_sha256"] = "0" * 64
    elif field == "pages":
        proof["observations"][0][field] = []
    else:
        proof["observations"][0][field] = "0" * 64
    with pytest.raises((RuntimeError, StopIteration)):
        r5.account_proof(capture)


@pytest.fixture(scope="module")
def ip_payloads():
    actual = r4.r3.investigation_baseline()
    args = (d.policy_values(actual["formats"]["global"])["xml"].encode(),
        d.FIXTURE.read_bytes(), "2026-10-30T12:00:00Z", "2026-10-30T12:30:00Z", "e" * 32)
    return args, r5.render(*args), r4.successor.render(*args)


def test_r5_private_IP_binding_does_not_reauthorize_historical_storage():
    assert r5.IP == r5.controller.IP == "167.103.66.248"
    assert r5.Stages._execute.__globals__["IP"] == r5.IP
    assert r5.controller.expression.__globals__ is vars(r5.controller)
    assert r5.controller.PATH_BROWSER == r5.controller.BRIDGE == r5.BRIDGE
    assert r4.controller.IP == r4.r3.old.IP == "167.103.67.80"
    before, after = r4.r3.old.storage_transition()
    assert after["properties"]["networkAcls"]["ipRules"][-1] == {
        "value": "167.103.67.80", "action": "Allow"}
    assert len(before["properties"]["networkAcls"]["ipRules"]) == 4
    assert len(after["properties"]["networkAcls"]["ipRules"]) == 5


@pytest.mark.parametrize("name", ["global.xml", "revision.xml"])
def test_candidate_wire_exact_one_IP_delta_native_predicate_and_before_provenance(ip_payloads, name):
    args, fresh, previous = ip_payloads
    old = b'context.Request.IpAddress == &quot;167.103.67.80&quot;'
    new = b'context.Request.IpAddress == &quot;167.103.66.248&quot;'
    assert fresh[name] == previous[name].replace(old, new, 1)
    assert fresh[name].count(new) == 1 and old not in fresh[name]
    assert fresh["restore-global.xml"] == previous["restore-global.xml"]
    for kind, delta in d.json.loads(fresh["proposal-diffs.json"]).items():
        assert delta["before"] == d.json.loads(previous["proposal-diffs.json"])[kind]["before"]
        assert delta["after_sha256"] == d.sha(delta["after"].encode())
    if name == "revision.xml":
        tree = d.c.tree(fresh[name])
        assert tree.find("./inbound")[2].find("when").get("condition") == (
            "@(!(" + r5.controller.expression(args[2], args[3]) + "))")
    stage = "install-global" if name == "global.xml" else "install-revision"
    body = d.encode({"properties": {"format": "xml", "value": fresh[name].decode()}})
    request = r5.controller.mutation_request(stage, body, '"test-etag"', "TEST_ONLY")
    assert request.data == body and request.full_url == d.URLS[stage]
    assert request.get_method() == "PUT" and request.get_header("If-match") == '"test-etag"'


@pytest.mark.parametrize("kind", ["global", "revision", "counter", "window"])
def test_r5_renderer_retains_predecessor_nonce_and_UTC_guards(ip_payloads, kind):
    args = list(ip_payloads[0])
    if kind == "global":
        args[0] = args[0].replace(b"<policies>", b'<policies TEST_ONLY="drift">', 1)
    elif kind == "revision":
        args[1] += b" "
    elif kind == "counter":
        args[4] = "not-a-counter"
    else:
        args[3] = "2026-10-30T12:30:01Z"
    with pytest.raises(RuntimeError):
        r5.render(*args)


def test_r5_browser_export_exact_finite_guard_and_timer_free_VM():
    import subprocess
    source = r5.controller.browser_source()
    original = d.browser_source()
    assert source == original
    assert 'r.IP === "167.103.66.248"' in source and 'r.IP === "167.103.67.80"' not in source
    # Execute the existing complete path-browser fixtures against the ACTUAL r5
    # export in memory. No file rewrite, timers, auth, live page or network.
    script = (d.ROOT / "tests/auto_path_diagnostic_browser.test.mjs").read_text()
    script = script.replace('import { SOURCE } from "../scripts/deployment/auto_path_diagnostic_browser.mjs";',
        'import { SOURCE } from "./scripts/deployment/auto_path_oct30_r5_bridge.mjs";')
    script = script.replace('["IP", "167.103.63.12"]', '["IP", "167.103.67.80"]')
    result = subprocess.run(["node", "--input-type=module", "-"], input=script.encode(),
        cwd=d.ROOT, capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()


def test_r5_real_localcheck_rejects_rehashed_wrong_IP_and_browser(data, tmp_path, ip_payloads):
    folder = tmp_path / (r5.PREFIX + "TEST_ONLY")
    folder.mkdir()
    for name, value in ip_payloads[1].items():
        d.exclusive(folder / name, value)
    d.exclusive(folder / "fresh-before.json", capture_fixture(data))
    d.exclusive(folder / "browser-source.js", r5.controller.browser_source().encode())
    historical = d.load(r4.r3.PREDECESSOR / "manifest.json")
    manifest = {"at_utc": ip_payloads[0][2], "start": ip_payloads[0][2], "end": ip_payloads[0][3],
        "sources": r5.sources(), "artifacts": {p.name: d.sha(p.read_bytes()) for p in folder.iterdir()},
        "tests": historical["tests"], "native_tests": historical["native_tests"],
        "stages": list(d.STAGES), "scope": d.SCOPE, "scoring_budget": 1,
        "retry_budget": 0, "completion_budget": 0, "historical_scoring_request_count": None}
    d.exclusive(folder / "manifest.json", manifest)
    assert r5.localcheck(folder) == manifest
    for name, bad in (("global.xml", ip_payloads[2]["global.xml"]),
                      ("browser-source.js", r4.controller.browser_source().encode())):
        original = (folder / name).read_bytes()
        (folder / name).write_bytes(bad)
        manifest["artifacts"][name] = d.sha(bad)
        (folder / "manifest.json").write_bytes(d.encode(manifest))
        with pytest.raises(RuntimeError, match="exact_new_fixture_delta|exact_browser_source"):
            r5.localcheck(folder)
        (folder / name).write_bytes(original)
        manifest["artifacts"][name] = d.sha(original)
        (folder / "manifest.json").write_bytes(d.encode(manifest))


def test_r5_actual_reservation_claim_IP_and_finally_cleanup(data, tmp_path, ip_payloads, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("r5_state_machine_fixtures",
        d.ROOT / "tests/unit/test_auto_path_oct30_successor.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    folder = helpers.package.__wrapped__(tmp_path, capture_fixture(data), ip_payloads[1], monkeypatch)
    source = r5.controller.browser_source().encode()
    (folder / "browser-source.js").write_bytes(source)
    preflight = d.load(folder / "browser-preflight.json")
    preflight["source_sha256"] = d.sha(source)
    (folder / "browser-preflight.json").write_bytes(d.encode(preflight))
    # State-machine fixtures ONLY; real manifest/artifact checks tested above.
    monkeypatch.setattr(r5.controller, "localcheck", lambda _: d.load(folder / "manifest.json"))
    class Fake(helpers.legacy.Fake):
        def capture(self):
            value = super().capture()
            references = {key: value[key] for key in ("formats", "inheritance", "owned_api", "baseline")}
            references["source_snapshots"] = {name: (d.ROOT / name).read_bytes().decode()
                for name in reads.REFERENCE_FILES}
            value["account_inventory_r5"]["references_sha256"] = d.r.fs.sha(references)
            return value
    fake = Fake(folder)
    def browser(binding):
        assert binding["reservation"]["IP"] == r5.IP
        assert binding["reservation"]["browser_source_sha256"] == d.sha(source)
        assert binding["reservation"]["scoring_budget"] == 1
        assert binding["reservation"]["completion_budget"] == binding["reservation"]["retry_budget"] == 0
        return "TEST_ONLY_NO_SEND"
    assert r5.run_reviewed_window(folder, fake, browser, lambda: helpers.AT) == "TEST_ONLY_NO_SEND"
    assert fake.calls == ["install-global", "install-revision", "online", "offline", "restore-global"]
    assert all((folder / (stage + "-verified.json")).exists() for stage in d.STAGES)