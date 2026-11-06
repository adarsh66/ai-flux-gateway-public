"""Offline private-collector regressions; no actual prepare/transport/Send."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import ssl
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from scripts.deployment import auto_path_diagnostic_oct30 as s
from scripts.deployment import auto_path_oct30_collector as a
from scripts.deployment import poc_publisher_recheck_oct29 as reads
from scripts.deployment import project_route_product_access as product

d = s.d


@pytest.fixture
def environment(monkeypatch):
    before, after = s.storage_transition()
    value = {"account": deepcopy(after)}
    runtime = {"sites": {"ingestion": {"protected": {"web": {"alwaysOn": True}}}}}
    settings = {"api": {"AIFLUX_APIM_PRODUCT_ID": "aiflux"}, "customer": {}, "admin": {},
                "ingestion": {"AzureWebJobs.ingest_usage.Disabled": "false",
                              "AIFLUX_INGESTION_START_AT": "2026-10-27T06:06:02.045288+00:00"}}
    monkeypatch.setattr(product.portals, "baseline", lambda: deepcopy(runtime))
    monkeypatch.setattr(product.fs, "current_settings", lambda: deepcopy(settings))
    def cli(args):
        assert args[:3] == ["rest", "--method", "get"]
        if "/storageAccounts/projpoctokenex?" in args[-1]:
            return value["account"]  # Intentionally same object: must not mutate it.
        return {"value": []}
    monkeypatch.setattr(d.r.rt, "cli", cli)
    def arm(self, suffix, method="GET"):
        assert method == "GET"
        if suffix.startswith("/policyFragments/"):
            return {"id": d.r.persistence.release.ID,
                    "properties": {"value": "<fragment/>", "provisioningState": "Succeeded"}}
        if "/policies/policy?format=rawxml" in suffix:
            return {"properties": {"value": "<policies/>"}}
        return {"value": [], "identity": {"type": "SystemAssigned"}}
    monkeypatch.setattr(reads.ReadOnlyProductRun, "arm", arm)
    monkeypatch.setattr(reads.ReadOnlyProductRun, "policy", lambda self: "<policies/>")
    monkeypatch.setattr(reads.ReadOnlyProductRun, "metadata", lambda self: {"TEST_ONLY": True})
    monkeypatch.setattr(reads.ReadOnlyProductRun, "__init__", lambda self: None)
    monkeypatch.setattr(d.r.persistence.release, "without_created_fragment", lambda v: v)
    monkeypatch.setattr(d.a, "opener", Mock(side_effect=AssertionError("offline: no HTTP")))
    return before, after, value


@contextmanager
def offline_context():
    yield


def snapshot(environment):
    private, klass = a.private_controller({})
    private.read_transport = offline_context
    with a.strict_read_context(private, klass, {}):
        return private.r.persistence.release.snapshot()


def test_original_four_guard_unchanged_and_five_still_rejected_outside_context(environment):
    before, after, current = environment
    current["account"] = before
    run = reads.ReadOnlyProductRun()
    assert run.protected()["state_network"] == s.state_network(before)
    current["account"] = after
    with pytest.raises(product.RepairBlocked, match="Preserve exact approved state ACL"):
        run.protected()
    result = snapshot(environment)
    assert len(result) == 13
    assert result["state_network"] == s.state_network(after)
    assert len(result["state_network"]["networkAcls"]["ipRules"]) == 5
    assert current["account"] == after
    with pytest.raises(product.RepairBlocked, match="Preserve exact approved state ACL"):
        run.protected()


@pytest.mark.parametrize("change", [
    "other_IP", "sixth_IP", "missing_added", "duplicate", "order", "action", "CIDR",
    "VNet", "bypass", "defaultAction", "publicNetworkAccess", "allowSharedKeyAccess",
    "ipv6", "resourceAccessRules", "allowBlobPublicAccess", "minimumTlsVersion", "tags", "unknown_property"])
def test_full_account_drift_rejected_before_historical_guard(environment, change, monkeypatch):
    _, _, current = environment
    account = current["account"]
    p = account["properties"]
    acl = p["networkAcls"]
    rules = acl["ipRules"]
    if change == "other_IP":
        rules[-1]["value"] = "192.0.2.1"
    elif change == "sixth_IP":
        rules.append({"value": "192.0.2.1", "action": "Allow"})
    elif change == "missing_added":
        rules.pop()
    elif change == "duplicate":
        rules[-1] = deepcopy(rules[0])
    elif change == "order":
        rules.reverse()
    elif change == "action":
        rules[-1]["action"] = "Deny"
    elif change == "CIDR":
        rules[-1]["value"] += "/32"
    elif change == "VNet":
        acl["virtualNetworkRules"] = [{"id": "TEST_ONLY", "action": "Allow"}]
    elif change in ("bypass", "defaultAction"):
        acl[change] = "None" if change == "bypass" else "Allow"
    elif change == "ipv6":
        acl["ipv6Rules"] = [{"value": "2001:db8::1", "action": "Allow"}]
    elif change == "resourceAccessRules":
        acl[change] = [{"resourceId": "TEST_ONLY", "tenantId": "TEST_ONLY"}]
    elif change == "tags":
        account["tags"] = {"TEST_ONLY": "changed"}
    else:
        p[change] = "TEST_ONLY_CHANGED"
    # Prove the old require is not globally disabled, and is never reached for
    # unverified storage. Earlier FinOps require remains real and passes.
    original = product.require
    calls = []
    def require(ok, message):
        calls.append(message)
        return original(ok, message)
    monkeypatch.setattr(product, "require", require)
    with pytest.raises(RuntimeError, match="whole_account_exact_approved_after"):
        snapshot(environment)
    assert "Preserve exact approved state ACL" not in calls
    assert "Current working product and FinOps baseline required" in calls


def test_private_graph_and_original_bindings_restore_on_exception(environment):
    original_class = d.r.persistence.release.ProductRun
    original_snapshot = d.r.persistence.release.snapshot
    original_protected = product.ProductRun.protected
    original_cli = d.r.rt.cli
    private, klass = a.private_controller({})
    release = private.r.persistence.release
    assert private is not d and private.r is not d.r
    assert private.r.persistence is not d.r.persistence and release is not d.r.persistence.release
    assert private.collect.__globals__ is vars(private)
    assert release.snapshot.__globals__ is vars(release)
    private.read_transport = offline_context
    with pytest.raises(ValueError):
        with a.strict_read_context(private, klass, {}):
            assert release.ProductRun is klass
            assert d.r.persistence.release.ProductRun is original_class
            raise ValueError("TEST_ONLY_secret_not_retained")
    assert release.ProductRun is original_class
    assert d.r.persistence.release.snapshot is original_snapshot
    assert product.ProductRun.protected is original_protected
    assert d.r.rt.cli is original_cli


def test_original_other_security_guards_still_run(environment, monkeypatch):
    monkeypatch.setattr(product.fs, "current_settings", lambda: {
        "api": {"AIFLUX_APIM_PRODUCT_ID": "wrong"}, "ingestion": {}})
    with pytest.raises(product.RepairBlocked, match="Current working product"):
        snapshot(environment)


def test_actual_collect_retains_five_and_checks_second_account_read(environment, monkeypatch):
    _, after, _ = environment
    # Execute the real snapshot and guard through the cloned collect globals.
    def fake_collect():
        with read_transport():
            baseline = r.persistence.release.snapshot()
        return {"baseline": baseline, "storage_sha256": r.fs.sha(r.persistence.backend.arm_read()["account"])}
    second_read = {"account": after}
    monkeypatch.setattr(d.r.persistence.backend, "arm_read", lambda: second_read)
    monkeypatch.setattr(d, "collect", fake_collect)
    monkeypatch.setattr(d, "read_transport", offline_context)
    capture = a.collect()
    assert capture["storage_sha256"] == d.r.fs.sha(after)
    assert capture["baseline"]["state_network"] == s.state_network(after)
    second_read["account"] = s.storage_transition()[0]
    with pytest.raises(RuntimeError, match="retained_full13_actual_five_pinned_account"):
        a.collect()


def test_real_collect_calls_real_private_snapshot_full13_with_offline_reads(environment, monkeypatch):
    actual = d.load(s.ROOT / ".deployment/auto-path-diagnostic-20261029T145153223109Z-actual-capture.json")
    monkeypatch.setattr(product.portals, "baseline", lambda: deepcopy(actual["baseline"]["runtime"]))
    class Reads:
        def get(self, suffix):
            if suffix == "/revisions":
                return {"value": [{"apiRevision": row["revision"], "apiId": row["api_id"],
                    "isCurrent": row["is_current"], "isOnline": row["is_online"]}
                    for row in actual["revisions"]]}, None
            if suffix == ";rev=2":
                return deepcopy(actual["owned_api"]), actual["api_etag"]
            assert suffix == ""
            return {"TEST_ONLY_CURRENT_API": True}, None
        def arm(self, suffix):
            return deepcopy(actual["formats"]["global"][suffix.rsplit("=", 1)[-1]])
        def policy(self, revision, fmt):
            assert revision == ";rev=2"
            return deepcopy(actual["formats"]["revision"][fmt])
    monkeypatch.setattr(d.c, "Reads", Reads)
    monkeypatch.setattr(d.c, "inheritance", lambda _: (actual["inheritance"], None))
    monkeypatch.setattr(d.a, "state_owner", lambda: deepcopy(actual["project"]))
    monkeypatch.setattr(d.r.login, "account", lambda: None)
    monkeypatch.setattr(d.r.persistence.backend, "workers", lambda: [])
    monkeypatch.setattr(d.r, "supplemental", lambda _: {"TEST_ONLY": True})
    monkeypatch.setattr(d, "read_transport", offline_context)
    monkeypatch.setattr(d, "remote_state", lambda: deepcopy(actual["runtime"]))
    monkeypatch.setattr(d.r.persistence.backend, "arm_read", lambda: {"account": environment[1]})
    runtime = actual["runtime"]
    monkeypatch.setattr(d.r.persistence.backend, "blob_head", lambda: {
        "lease_state": "available", "lease_status": "unlocked", "etag": runtime["etag"],
        "content_length": runtime["length"], "last_modified": runtime["last_modified"]})
    result = a.collect()
    assert len(result["baseline"]) == 13
    assert result["baseline"]["state_network"] == s.state_network(environment[1])
    assert result["storage_sha256"] == d.r.fs.sha(environment[1])
    assert result["project"] == actual["project"] and result["runtime"] == actual["runtime"]


@pytest.mark.parametrize("failure_at", ["body", "entry"])
def test_strict_transport_restores_real_bindings_even_on_exception(monkeypatch, failure_at):
    from scripts.deployment import auto_path_oct30_parent as parent
    private, klass = a.private_controller({})
    rt = d.r.rt
    monkeypatch.setattr(rt, "CA", str(parent.TRUSTED_CA))
    modules = (reads, d.r.persistence.old, d.r.persistence.backend, rt)
    saved = [module.urlopen for module in modules]
    original = (rt.cli, rt.CLI, rt.arm, d.r.persistence.release.ProductRun)
    private_class = private.r.persistence.release.ProductRun
    if failure_at == "entry":
        monkeypatch.setattr(ssl, "create_default_context", Mock(side_effect=ssl.SSLError("TEST_ONLY")))
    with pytest.raises((ValueError, ssl.SSLError)):
        with a.strict_read_context(private, klass, {}):
            # Existing strict method guard rejects writes BEFORE token or HTTP.
            for method in ("PUT", "PATCH", "DELETE", "POST"):
                with pytest.raises(RuntimeError):
                    rt.arm(rt.RG + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex", method)
            raise ValueError("TEST_ONLY")
    assert [module.urlopen for module in modules] == saved
    assert (rt.cli, rt.CLI, rt.arm, d.r.persistence.release.ProductRun) == original
    assert private.r.persistence.release.ProductRun is private_class


@pytest.mark.parametrize("error,code", [
    (RuntimeError("SECRET_TEST_ONLY"), "GUARD_OR_RUNTIME_FAILURE"),
    (ValueError("SECRET_TEST_ONLY"), "UNCLASSIFIED_FAILURE"),
    (ssl.SSLError("SECRET_TEST_ONLY"), "TLS_FAILURE"),
    (TimeoutError("SECRET_TEST_ONLY"), "READ_TIMEOUT"),
    (HTTPError("https://SECRET_TEST_ONLY", 403, "SECRET_TEST_ONLY", {}, None), "HTTP_READ_FAILURE"),
    (product.RepairBlocked("SECRET_TEST_ONLY"), "GUARD_REJECTED")])
def test_durable_prepare_failure_finite_sanitized_and_no_replay(tmp_path, monkeypatch, error, code):
    folder = tmp_path / "auto-path-oct30-TEST_FAILURE"
    def fail(*args, **kwargs):
        kwargs["capture_fn"]()
    monkeypatch.setattr(s.controller, "prepare", fail)
    capture = Mock(side_effect=error)
    with pytest.raises(type(error)) as caught:
        s.prepare(folder, Path("TEST_ONLY"), capture_fn=capture)
    assert caught.value is error
    path = folder.with_name(folder.name + "-prepare-failure.json")
    data = d.load(path)
    assert data["error_code"] == code and "SECRET_TEST_ONLY" not in path.read_text()
    assert data["original_PID27864_exception"] == "UNKNOWN_NOT_RECOVERED"
    assert data["phase"] == "PREPARE_VALIDATION"
    with pytest.raises(RuntimeError, match="failed_prepare_reconcile_never_replay"):
        s.prepare(folder, Path("TEST_ONLY"), capture_fn=capture)
    assert capture.call_count == 1 and not folder.exists()


def test_wiring_sources_all_old173_unchanged():
    assert s.controller.collect is a.collect
    assert s.ProductionAdapter.capture.__globals__["collect"] is a.collect
    sources = s.sources()
    for path in (Path(a.__file__), Path(__file__), s.COLLECTOR_DOC):
        assert sources[path.relative_to(s.ROOT).as_posix()] == d.sha(path.read_bytes())
    old = d.load(s.prior.PREDECESSOR / "manifest.json")["sources"]
    assert len(old) == 173 and all(sources[name] == digest for name, digest in old.items())


def test_failure_frames_retained_without_messages_locals_or_chains(tmp_path):
    secret = "SECRET_TOKEN_HEADERS_LOCALS_TEST_ONLY"
    class SecretError(RuntimeError):
        def __str__(self):
            raise AssertionError("must never format exception")
    try:
        try:
            raise ValueError(secret)
        except ValueError as cause:
            raise SecretError(secret, {"Authorization": secret}) from cause
    except SecretError as error:
        a.retain_prepare_failure(tmp_path / "diagnostic", error, {"phase": "STRICT_READ_CONTEXT"})
    text = (tmp_path / "diagnostic-prepare-failure.json").read_text()
    data = d.json.loads(text)
    assert data["exception_type"] == "UNKNOWN_EXCEPTION_TYPE"
    assert secret not in text and "Authorization" not in text and "SecretError" not in text
    assert data["frames"][-1]["function"] == "test_failure_frames_retained_without_messages_locals_or_chains"
    for frame in data["frames"]:
        assert set(frame) == {"file", "function", "line"}
        assert not Path(frame["file"]).is_absolute() and ".." not in Path(frame["file"]).parts
        assert (s.ROOT / frame["file"]).resolve().is_relative_to(s.ROOT.resolve())
        assert isinstance(frame["line"], int) and frame["line"] > 0


@pytest.mark.parametrize("filename", [
    "C:/outside/SECRET_TEST_ONLY.py",
    "C:/LocalWorkspace/ai-flux-gateway-public-OUTSIDER/SECRET_TEST_ONLY.py",
    "C:/LocalWorkspace/ai-flux-gateway-public/../SECRET_TEST_ONLY.py",
    "<SECRET_TEST_ONLY>", "relative/SECRET_TEST_ONLY.py"])
def test_failure_frames_omit_outsider_and_synthetic_paths(filename):
    try:
        exec(compile("raise RuntimeError('SECRET_TEST_ONLY')", filename, "exec"), {})
    except RuntimeError as error:
        frames = a.safe_failure_frames(error)
    assert len(frames) == 1 and frames[0]["file"] == Path(__file__).relative_to(s.ROOT).as_posix()
    assert "SECRET_TEST_ONLY" not in d.json.dumps(frames)


def test_failure_frames_bounded_and_keep_innermost():
    def recurse(depth):
        if depth:
            recurse(depth - 1)
        else:
            raise RuntimeError("SECRET_TEST_ONLY")
    try:
        recurse(40)
    except RuntimeError as error:
        frames = a.safe_failure_frames(error)
    assert len(frames) == 16 and all(frame["function"] == "recurse" for frame in frames)


@pytest.mark.parametrize("error,name", [
    (RuntimeError("SECRET_TEST_ONLY"), "RuntimeError"),
    (ValueError("SECRET_TEST_ONLY"), "ValueError"),
    (FileNotFoundError("SECRET_TEST_ONLY"), "FileNotFoundError"),
    (ssl.SSLCertVerificationError("SECRET_TEST_ONLY"), "SSLCertVerificationError"),
    (Exception("SECRET_TEST_ONLY"), "UNKNOWN_EXCEPTION_TYPE")])
def test_exception_type_finite_mapping(error, name):
    assert a.safe_exception_type(error) == name


def test_exact_storage_version_only_rewrite_and_other_args_unchanged(environment, monkeypatch):
    original = d.r.rt.cli
    observed = []
    def cli(args):
        observed.append(deepcopy(args))
        return original(args)
    monkeypatch.setattr(d.r.rt, "cli", cli)
    snapshot(environment)
    storage = [args for args in observed if "/storageAccounts/" in args[-1]]
    assert storage == [["rest", "--method", "get", "--url", d.r.persistence.backend.URL]]
    assert storage[0][-1].endswith("projpoctokenex?api-version=2025-06-01")
    assert a.HISTORICAL_STORAGE_API == "2023-05-01"
    assert a.APPROVED_STORAGE_API == "2025-06-01"
    # Every non-storage request is passed through byte-for-byte, not rebuilt.
    assert observed and all(args[:4] == ["rest", "--method", "get", "--url"] for args in observed)


@pytest.mark.parametrize("value", [None, True, "false", 0, "ABSENT"])
def test_delegation_false_is_not_absent_or_coerced(environment, value):
    props = environment[2]["account"]["properties"]
    if value == "ABSENT":
        del props["allowCrossTenantDelegationSas"]
    else:
        props["allowCrossTenantDelegationSas"] = value
    with pytest.raises(RuntimeError, match="whole_account_exact_approved_after"):
        snapshot(environment)


def test_separate_arm_read_API_drift_fails_closed(environment, monkeypatch):
    monkeypatch.setattr(d.r.persistence.backend, "URL", d.r.persistence.backend.URL.replace("2025-06-01", "2023-05-01"))
    with pytest.raises(RuntimeError, match="separate_storage_read_exact_approved_API"):
        snapshot(environment)


def test_finite_exact_args_only_no_near_match_rewrite(environment, monkeypatch):
    approved = d.r.persistence.backend.URL
    old = approved.replace("2025-06-01", "2023-05-01")
    variants = [
        ["rest", "--method", "get", "--url", old.replace("projpoctokenex?", "other? ")],
        ["rest", "--method", "get", "--url", old + "&extra=1"],
        ["rest", "--method", "get", "--url", old, "--only-show-errors"],
        ["rest", "--method", "GET", "--url", old],
        ["rest", "--method", "get", "--url", approved],
    ]
    observed = []
    def cli(args):
        observed.append(args)
        return deepcopy(environment[1])
    historical_network = s.state_network(environment[0])
    def protected(self):
        for args in variants:
            rt.cli(args)
        rt.cli(["rest", "--method", "get", "--url", old])
        return {"state_network": historical_network}
    monkeypatch.setattr(d.r.rt, "cli", cli)
    monkeypatch.setattr(product.ProductRun, "protected", protected)
    _, klass = a.private_controller({})
    klass().protected()
    assert observed[:-1] == variants
    assert all(actual is expected for actual, expected in zip(observed, variants))
    assert observed[-1] == ["rest", "--method", "get", "--url", approved]