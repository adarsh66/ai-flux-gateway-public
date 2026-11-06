"""SYNTHETIC unit fixtures ONLY. Never collect evidence or launch any runtime.

A positive parser/package test is NOT a native compile, MI or production proof.
All package files are pytest temporary files, never production release artifacts.
"""
import base64
import json
import os
import socket
import subprocess
from copy import deepcopy
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from aiflux import auto_snapshot
from aiflux.config import Settings
from scripts.deployment import auto_publication_artifact as a


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unit fixtures must never launch network/build/deployment/runtime")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


class SyntheticEvidence:
    """In-memory fixture collector format, intentionally NOT actual live proof."""

    def __init__(self, path):
        self.root = path / "synthetic-unit-fixtures-not-live-evidence"
        self.root.mkdir()
        self.package = path / "synthetic-unit-package"
        self.values = {}
        self.release = {"id": "SYNTHETIC-unit-release", "attempt_id": "SYNTHETIC-attempt-1",
            "stage": "production-auto", "actor": "SYNTHETIC-release-operator",
            "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:10:00Z"}
        self.put("sources.json", {p: a.digest((a.ROOT / p).read_bytes()) for p in a.source_paths()})
        settings = Settings(_env_file=None, environment="testing", local_auth_enabled=True,
            foundry_inventory_path=a.ROOT / "gateway/catalog/foundry-inventory-20261026.json")
        current = auto_snapshot.defaults(settings)
        snapshot = {"version": current["version"], "profiles": current["profiles"],
                    "candidates": {c["id"]: c for c in current["candidates"]}}
        self.put("snapshot.json", snapshot)
        encoded = base64.b64encode(a.encode(snapshot)).decode()
        fragment = (a.ROOT / "gateway/policies/auto-resolve.xml.tftpl").read_text(encoding="utf-8")
        # A synthetic render for parser testing, never a compiled policy claim.
        arguments = {"snapshot_base64": encoded, "gateway_client": a.CLIENT, "candidate_conditions": "true",
            "manifest_conditions": "true", "selected_limit_rules": "", "completion_limit": "1024",
            "provider_rules": "", "selected_limits": ""}
        for key, value in arguments.items():
            fragment = fragment.replace("${" + key + "}", value)
        policy = "<policies><inbound>" + fragment + "</inbound><backend/><outbound/><on-error/></policies>"
        self.put("rendered.xml", policy)
        self.binding = {"release_id": self.release["id"], "attempt_id": self.release["attempt_id"],
            "stage": self.release["stage"], "source_manifest_sha256": self.ref("sources.json")["sha256"],
            "snapshot_version": snapshot["version"], "policy_sha256": self.ref("rendered.xml")["sha256"]}
        role = "/providers/Microsoft.Authorization/roleDefinitions/SYNTHETIC-role"
        self.put("role-assignment.json", {"id": "SYNTHETIC-assignment", "properties": {
            "principalId": a.PRINCIPAL, "scope": a.ACCOUNT, "roleDefinitionId": role, "condition": None}})
        self.put("role-definition.json", {"id": role, "properties": {"permissions": [{
            "dataActions": ["Microsoft.CognitiveServices/*"], "notDataActions": []}]}})
        self.put("deny-assignments.json", {"value": []})
        self.put("authorization.json", self.record("platform-release-authorization", "00:00:01",
            authorized_stage="production-auto", authorized_attempt_id=self.release["attempt_id"],
            actor=self.release["actor"], role_assignment=self.ref("role-assignment.json"),
            role_definition=self.ref("role-definition.json"), deny_assignments=self.ref("deny-assignments.json"),
            budget={"auto_requests": 3, "score_requests": 3, "provider_requests": 3, "retries": 0,
                "max_completion_tokens": 1024, "score_timeout_ms": 5000, "score_response_bytes": 65536}))
        self.put("native.log", "SYNTHETIC fixture log, NOT native proof\nSYNTHETIC-native-run\n"
                 + "\n".join(self.binding.values()))
        self.put("render-output.json", {"renderer": "terraform-console", "binding": self.binding, "policy": policy})
        self.put("native.json", self.record("apim-native-production-validation", "00:00:02", exit_code=0,
            policy_resource_id=a.POLICY, run_id="SYNTHETIC-native-run", log=self.ref("native.log"),
            render_output=self.ref("render-output.json")))
        for fmt in ("rawxml", "xml"):
            self.put(fmt + "-response.json", {"id": a.POLICY, "properties": {"format": fmt, "value": policy}})
            self.put("readback-" + fmt + ".json", self.record("policy-readback", "00:00:03",
                method="GET", http_status=200, format=fmt, resource_id=a.POLICY,
                response=self.ref(fmt + "-response.json")))
        self.put("api.json", {"id": a.POLICY.removesuffix("/policies/policy"), "properties": {
            "path": "dev/llm/v1", "isCurrent": True, "isOnline": True}})
        event_refs = []
        for index, profile in enumerate(("balanced", "cost", "quality")):
            prefix = profile + "-"
            pool = snapshot["profiles"][profile]["candidate_models"]
            selected = min(pool)
            request = {"model": "auto", "messages": [{"role": "user", "content": "SYNTHETIC benign greeting"}],
                       "max_completion_tokens": 20}
            if profile != "balanced":
                request["routing_profile"] = profile
            self.put(prefix + "request.json", request)
            self.put(prefix + "redacted.json", request)
            self.put(prefix + "score-request.json", {"model": "Decision-1", "state": {
                "messages": request["messages"], "max_completion_tokens": 20}, "questions": {"route": {
                "type": "choice", "instructions": snapshot["profiles"][profile]["instructions"],
                "criteria": {alias: json.dumps(snapshot["candidates"][alias]) for alias in pool}}}})
            self.put(prefix + "score-response.json", {"answers": {"route": {"type": "choice", "choice": selected,
                "probabilities": {alias: 1 if alias == selected else 0 for alias in pool}}},
                "usage": {"input_tokens": 12, "output_tokens": 1}})
            provider = {"model": selected, "choices": [{"message": {"role": "assistant", "content": "Fixture"}}],
                        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}
            self.put(prefix + "provider.json", provider)
            self.put(prefix + "response.json", {**provider, "routing": {"selected_model": selected,
                "routing_profile": profile, "config_version": snapshot["version"], "fallback_used": False,
                "failure": None, "decision_overhead": {"latency_ms": 100, "cost_usd": None,
                    "usage": {"input_tokens": 12, "output_tokens": 1}}}})
            event = {"binding": self.binding, "native_run_id": "SYNTHETIC-native-run",
                "request_id": "SYNTHETIC-request-" + profile, "policy_resource_id": a.POLICY,
                "started_at": f"2026-01-01T00:00:{10 + index * 2:02}Z",
                "finished_at": f"2026-01-01T00:00:{11 + index * 2:02}Z", "method": "POST", "path": a.CHAT_PATH,
                "score_http_status": 200, "provider_http_status": 200, "http_status": 200,
                "score_requests": 1, "provider_requests": 1, "retries": 0, "score_endpoint": a.ENDPOINT,
                "score_identity": a.PRINCIPAL, "score_elapsed_ms": 100, "provider_selected_model": selected,
                "request": self.ref(prefix + "request.json"), "redacted_request": self.ref(prefix + "redacted.json"),
                "score_request": self.ref(prefix + "score-request.json"),
                "score_response": self.ref(prefix + "score-response.json"),
                "provider_response": self.ref(prefix + "provider.json"), "response": self.ref(prefix + "response.json")}
            self.put(prefix + "event.json", event)
            self.sync_trace(profile)
            event_refs.append(self.ref(prefix + "event.json"))
        self.put("runtime.json", self.record("production-auto-end-to-end", "00:01:00", native_run_id="SYNTHETIC-native-run",
            policy_resource_id=a.POLICY, gateway_principal=a.PRINCIPAL, gateway_client=a.CLIENT,
            api_readback=self.ref("api.json"), requests=event_refs))
        self.put("review.json", self.record("independent-native-release-review", "00:02:00", verdict="PASS",
            reviewer="SYNTHETIC-independent-reviewer", native_run_id="SYNTHETIC-native-run", reviewed={}, text={}))
        self.manifest = {"schema": 1, "kind": "auto-production-release-evaluation", "release": self.release,
            **{key: self.ref(name) for key, name in {
                "sources": "sources.json", "snapshot": "snapshot.json", "rendered_policy": "rendered.xml",
                "authorization": "authorization.json", "native": "native.json", "runtime": "runtime.json",
                "readback_rawxml": "readback-rawxml.json", "readback_xml": "readback-xml.json", "review": "review.json"
            }.items()}}
        self.seal()

    def record(self, kind, clock, **kwargs):
        return {"binding": self.binding, "origin": "deployment-collector", "kind": kind,
                "collected_at": "2026-01-01T" + clock + "Z", **kwargs}

    def put(self, name, value):
        self.values[name] = deepcopy(value)

    def raw(self, name):
        value = self.values[name]
        return value.encode() if isinstance(value, str) else a.encode(value)

    def ref(self, name):
        return {"path": name, "sha256": a.digest(self.raw(name))}

    def sync_trace(self, profile):
        prefix = profile + "-"
        event = self.values[prefix + "event.json"]
        observed = ("score_http_status", "provider_http_status", "http_status", "score_requests",
            "provider_requests", "retries", "score_endpoint", "score_identity", "score_elapsed_ms",
            "provider_selected_model", "method", "path")
        trace = {k: event[k] for k in ("binding", "request_id", "started_at", "finished_at", "policy_resource_id", "native_run_id")}
        trace.update(kind="apim-production-transaction", gateway_principal=a.PRINCIPAL,
            gateway_client=a.CLIENT, authentication="managed-identity", observed={k: event[k] for k in observed},
            payloads={k: event[k]["sha256"] for k in ("request", "redacted_request", "score_request",
                "score_response", "provider_response", "response")})
        self.put(prefix + "trace.json", trace)
        event["gateway_trace"] = self.ref(prefix + "trace.json")

    def seal(self):
        def refresh(value):
            if isinstance(value, dict):
                if set(value) == {"path", "sha256"} and value["path"] in self.values:
                    value.update(self.ref(value["path"]))
                else:
                    for child in value.values():
                        refresh(child)
            elif isinstance(value, list):
                for child in value:
                    refresh(child)
        # Fixture graph is acyclic. Rebind hashes to exercise semantic checks,
        # not merely fail every negative on the outermost checksum.
        for _ in range(8):
            for value in self.values.values():
                refresh(value)
            refresh(self.manifest)
        reviewed = {k: self.manifest[k]["sha256"] for k in ("sources", "snapshot", "rendered_policy", "authorization",
            "native", "readback_rawxml", "readback_xml", "runtime")}
        self.values["review.json"]["reviewed"] = reviewed
        self.put("review.txt", "SYNTHETIC independent fixture, NOT actual review\nSYNTHETIC-native-run\n"
                 + "\n".join([*self.binding.values(), *reviewed.values()]))
        self.values["review.json"]["text"] = self.ref("review.txt")
        self.manifest["review"] = self.ref("review.json")
        for name in self.values:
            (self.root / name).write_bytes(self.raw(name))
        (self.root / "manifest.json").write_bytes(a.encode(self.manifest))

    def create(self):
        return a.prepare_artifact(self.root, "manifest.json", self.package)


@pytest.fixture
def evidence(tmp_path):
    return SyntheticEvidence(tmp_path)


def test_synthetic_roundtrip_settings_bindings_no_autoenable_and_no_expiry(evidence):
    receipt = evidence.create()
    assert receipt == a.read_local_receipt(evidence.root, "manifest.json", evidence.package)
    assert receipt["runtime_verified"] is True
    assert "expires_at" not in receipt
    assert set(p.name for p in evidence.package.iterdir()) == {"receipt.json", "settings.json", "package.json"}
    settings_output = json.loads((evidence.package / "settings.json").read_bytes())
    assert settings_output["AIFLUX_AUTO_ROUTING_ENABLED"] == "false"
    assert settings_output["AIFLUX_AUTO_ROUTING_PUBLISHED_POLICY_SHA256"] == receipt["policy_sha256"]
    settings = Settings(_env_file=None, environment="testing", local_auth_enabled=True,
        foundry_inventory_path=a.ROOT / "gateway/catalog/foundry-inventory-20261026.json",
        auto_routing_publication_path=evidence.package / "receipt.json",
        auto_routing_published_policy_sha256=receipt["policy_sha256"])
    assert auto_snapshot.publication(settings, auto_snapshot.defaults(settings)) == receipt
    if os.name != "nt":
        assert evidence.package.stat().st_mode & 0o777 == 0o700
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in evidence.package.iterdir())
    with pytest.raises(a.EvidenceError, match="exclusive"):
        evidence.create()


@pytest.mark.parametrize("missing", ["manifest.json", "authorization.json", "native.log", "review.txt",
    "rawxml-response.json", "xml-response.json", "balanced-trace.json", "quality-provider.json"])
def test_missing_actual_evidence_never_creates_directory(evidence, missing):
    (evidence.root / missing).unlink()
    with pytest.raises((OSError, ValueError)):
        evidence.create()
    assert not evidence.package.exists()


@pytest.mark.parametrize("name,field,value", [
    ("native.json", "exit_code", 1), ("native.json", "run_id", "unrelated-run"),
    ("native.json", "runtime_verified", True), ("runtime.json", "kind", "diagnostic-probability-probe"),
    ("runtime.json", "gateway_principal", "operator-not-gateway"),
    ("runtime.json", "collected_at", "2026-01-01T00:00:00Z"),
    ("authorization.json", "authorized_attempt_id", "unapproved-attempt"),
    ("authorization.json", "actor", "unrelated-actor"),
    ("review.json", "reviewer", "SYNTHETIC-release-operator"), ("review.json", "verdict", "CONDITIONAL PASS"),
    ("review.json", "collected_at", "2026-01-01T00:00:05Z"),
    ("balanced-trace.json", "authentication", "operator-bearer"),
    ("balanced-trace.json", "request_id", "unconnected-transaction"),
])
def test_structured_evidence_cannot_be_replaced_by_flags_or_unbound_records(evidence, name, field, value):
    evidence.values[name][field] = value
    evidence.seal()
    with pytest.raises(a.EvidenceError):
        evidence.create()
    assert not evidence.package.exists()


@pytest.mark.parametrize("field,value", [("score_http_status", 403), ("provider_http_status", 502),
    ("http_status", 503), ("score_requests", 2), ("provider_requests", 0), ("retries", 1),
    ("score_elapsed_ms", 5001), ("score_identity", "operator"), ("path", "/diagnostic"),
    ("method", "GET"), ("score_endpoint", "https://unrelated.invalid")])
def test_runtime_budgets_and_production_path_are_proven_not_diagnostic(evidence, field, value):
    evidence.values["balanced-event.json"][field] = value
    evidence.sync_trace("balanced")
    evidence.seal()
    with pytest.raises(a.EvidenceError):
        evidence.create()
    assert not evidence.package.exists()


@pytest.mark.parametrize("mutation", ["choice_missing", "probabilities_only", "unconnected_choices", "bool_probability",
    "wrong_snapshot", "fallback", "provider_response_unconnected", "completion_budget", "descriptor", "no_completion"])
def test_end_to_end_production_schema_selection_and_full_response_required(evidence, mutation):
    score = evidence.values["balanced-score-response.json"]["answers"]["route"]
    response = evidence.values["balanced-response.json"]
    if mutation == "choice_missing":
        del score["choice"]
    elif mutation == "probabilities_only":
        del score["type"]
    elif mutation == "unconnected_choices":
        score["probabilities"] = {"greeting": 0.9, "arithmetic": 0.1}
    elif mutation == "bool_probability":
        score["probabilities"][score["choice"]] = True
    elif mutation == "wrong_snapshot":
        response["routing"]["config_version"] = "0" * 64
    elif mutation == "fallback":
        response["routing"]["fallback_used"] = True
    elif mutation == "provider_response_unconnected":
        response["choices"][0]["message"]["content"] = "unrelated-response"
    elif mutation == "completion_budget":
        evidence.values["balanced-request.json"]["max_completion_tokens"] = 1025
    elif mutation == "descriptor":
        criteria = evidence.values["balanced-score-request.json"]["questions"]["route"]["criteria"]
        criteria[next(iter(criteria))] = '{"id":"unrelated"}'
    elif mutation == "no_completion":
        evidence.values["balanced-provider.json"]["choices"] = []
        response["choices"] = []
    evidence.seal()
    # Keep trace payloads correlated so semantic production checks are exercised.
    evidence.sync_trace("balanced")
    evidence.seal()
    with pytest.raises((a.EvidenceError, KeyError)):
        evidence.create()
    assert not evidence.package.exists()


def test_both_policy_formats_must_match_exact_rendered_expressions(evidence):
    evidence.values["xml-response.json"]["properties"]["value"] = evidence.values["rendered.xml"].replace(
        "response.StatusCode != 200", "response.StatusCode != 201")
    evidence.seal()
    with pytest.raises(a.EvidenceError, match="deployed policy"):
        evidence.create()
    assert not evidence.package.exists()


def test_exactly_one_xml_export_entity_layer_and_cosmetic_indentation(evidence):
    evidence.values["xml-response.json"]["properties"]["value"] = escape(evidence.values["rendered.xml"],
        {'"': "&quot;", "'": "&apos;"})
    # APIM export escapes values, not the XML markup itself.
    import xml.etree.ElementTree as ET
    tree = ET.fromstring(evidence.values["rendered.xml"])
    for node in tree.iter():
        node.attrib.update({k: escape(v, {'"': "&quot;", "'": "&apos;"}) for k, v in node.attrib.items()})
        if node.text:
            node.text = escape(node.text, {'"': "&quot;", "'": "&apos;"})
    evidence.values["xml-response.json"]["properties"]["value"] = ET.tostring(tree, encoding="unicode")
    evidence.seal()
    assert evidence.create()["runtime_verified"] is True


@pytest.mark.parametrize("mutation", ["sources_omitted", "snapshot_changed", "role_principal", "deny",
    "review_binding", "stage", "timestamp", "api_revision", "hashes_only", "flag"])
def test_release_source_authz_review_and_snapshot_guards(evidence, mutation):
    if mutation == "sources_omitted":
        evidence.values["sources.json"].pop(a.DEFAULTS)
    elif mutation == "snapshot_changed":
        evidence.values["snapshot.json"]["profiles"]["balanced"]["instructions"] = "changed"
    elif mutation == "role_principal":
        evidence.values["role-assignment.json"]["properties"]["principalId"] = "api-identity"
    elif mutation == "deny":
        evidence.values["deny-assignments.json"]["value"] = [{"id": "unresolved-deny"}]
    elif mutation == "review_binding":
        evidence.values["review.json"]["binding"]["policy_sha256"] = "0" * 64
    elif mutation == "stage":
        evidence.manifest["release"]["stage"] = "diagnostic02"
    elif mutation == "timestamp":
        evidence.values["runtime.json"]["collected_at"] = "2099-01-01T00:00:00Z"
    elif mutation == "api_revision":
        evidence.values["api.json"]["properties"]["isCurrent"] = False
    elif mutation == "hashes_only":
        evidence.values["runtime.json"] = {"sha256": "a" * 64}
    elif mutation == "flag":
        evidence.manifest["runtime_verified"] = True
    evidence.seal()
    with pytest.raises((a.EvidenceError, KeyError)):
        evidence.create()
    assert not evidence.package.exists()


def test_stale_review_hash_rejected_even_when_review_file_is_rehashed(evidence):
    evidence.values["review.json"]["reviewed"]["runtime"] = "0" * 64
    (evidence.root / "review.json").write_bytes(evidence.raw("review.json"))
    evidence.manifest["review"] = evidence.ref("review.json")
    (evidence.root / "manifest.json").write_bytes(a.encode(evidence.manifest))
    with pytest.raises(a.EvidenceError, match="review does not match"):
        evidence.create()


def test_no_evidence_no_creation_cli_returns_blocked(tmp_path, capsys):
    missing = tmp_path / "absent-evidence"
    package = tmp_path / "not-created"
    assert a.main(["create", "--trusted-root", str(missing), "--manifest", "manifest.json",
                   "--package", str(package)]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not package.exists()


@pytest.mark.parametrize("name", ["../escape.json", "/absolute.json", "C:/outside.json", "dir\\file.json", "./manifest.json"])
def test_evidence_path_traversal_rejected(evidence, name):
    with pytest.raises(a.EvidenceError):
        a.prepare_artifact(evidence.root, name, evidence.package)
    assert not evidence.package.exists()


def test_checksum_tampering_and_duplicate_json_keys_rejected(evidence):
    (evidence.root / "native.log").write_text("tampered", encoding="utf-8")
    with pytest.raises(a.EvidenceError, match="hash mismatch"):
        evidence.create()
    (evidence.root / "manifest.json").write_text('{"schema":1,"schema":1}', encoding="utf-8")
    with pytest.raises(a.EvidenceError, match="duplicate"):
        evidence.create()
    assert not evidence.package.exists()


def test_hardlinked_evidence_rejected(evidence, tmp_path):
    os.link(evidence.root / "native.log", tmp_path / "hardlink.log")
    with pytest.raises(a.EvidenceError, match="hardlinked"):
        evidence.create()
    assert not evidence.package.exists()


def test_output_cannot_be_inside_immutable_evidence(evidence):
    with pytest.raises(a.EvidenceError, match="separate"):
        a.prepare_artifact(evidence.root, "manifest.json", evidence.root / "output")
    assert not (evidence.root / "output").exists()


def test_partial_write_failure_removes_receipt_and_package(evidence, monkeypatch):
    real = a._write
    def fail_settings(path, value):
        if path.name == "settings.json":
            raise OSError("synthetic disk failure")
        return real(path, value)
    monkeypatch.setattr(a, "_write", fail_settings)
    with pytest.raises(OSError, match="disk failure"):
        evidence.create()
    assert not evidence.package.exists()


def test_local_read_detects_settings_tampering(evidence):
    evidence.create()
    path = evidence.package / "settings.json"
    data = json.loads(path.read_bytes())
    data["AIFLUX_AUTO_ROUTING_ENABLED"] = "true"
    path.write_bytes(a.encode(data))
    with pytest.raises(a.EvidenceError, match="settings binding"):
        a.read_local_receipt(evidence.root, "manifest.json", evidence.package)


def test_builder_has_no_cloud_sql_publish_or_runtime_launch_imports():
    import ast
    tree = ast.parse(Path(a.__file__).read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    modules |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert not any(name and name.split(".")[0] in {
        "subprocess", "socket", "urllib", "httpx", "requests", "azure", "sqlalchemy"} for name in modules)


def test_deployed_raw_policy_hash_is_exact_not_just_semantically_equal(evidence):
    value = evidence.values["rawxml-response.json"]["properties"]["value"]
    evidence.values["rawxml-response.json"]["properties"]["value"] = value.replace(
        "<backend/>", "\n<backend/>\n")
    evidence.seal()
    with pytest.raises(a.EvidenceError, match="deployed raw policy hash"):
        evidence.create()
    assert not evidence.package.exists()


def test_boolean_request_count_is_not_an_actual_integer_measurement(evidence):
    evidence.values["balanced-event.json"]["score_requests"] = True
    evidence.sync_trace("balanced")
    evidence.seal()
    with pytest.raises(a.EvidenceError, match="runtime identity/status/budget"):
        evidence.create()
    assert not evidence.package.exists()


def test_snapshot_must_import_the_hash_bound_source_not_an_installed_copy(evidence, monkeypatch):
    monkeypatch.setattr(auto_snapshot, "__file__", str(evidence.root / "unbound-installed-copy.py"))
    with pytest.raises(a.EvidenceError, match="bound checkout source"):
        evidence.create()
    assert not evidence.package.exists()


def test_changed_evidence_is_rechecked_before_any_package_creation(evidence, monkeypatch):
    real = a.Boundary.recheck
    def mutate_then_recheck(boundary):
        path = evidence.root / "native.log"
        path.write_bytes(path.read_bytes() + b"\nSYNTHETIC concurrent mutation")
        real(boundary)
    monkeypatch.setattr(a.Boundary, "recheck", mutate_then_recheck)
    with pytest.raises(a.EvidenceError, match="changed"):
        evidence.create()
    assert not evidence.package.exists()


def test_each_local_package_file_is_fsynced(evidence, monkeypatch):
    real = os.fsync
    descriptors = []
    def track(descriptor):
        descriptors.append(descriptor)
        real(descriptor)
    monkeypatch.setattr(os, "fsync", track)
    evidence.create()
    assert len(descriptors) == (3 if os.name == "nt" else 4)


@pytest.mark.skipif(os.name != "nt", reason="Windows owner-only DACL inspection")
def test_windows_package_has_protected_owner_only_dacl(evidence):
    import ctypes
    from ctypes import wintypes
    evidence.create()
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_security = advapi.GetFileSecurityW
    get_security.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p,
                            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    get_security.restype = wintypes.BOOL
    convert = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                       ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(wintypes.DWORD)]
    convert.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(8192)
    needed = wintypes.DWORD()
    assert get_security(str(evidence.package), 4, buffer, len(buffer), ctypes.byref(needed))
    text = wintypes.LPWSTR()
    assert convert(buffer, 1, 4, ctypes.byref(text), None)
    try:
        sddl = text.value
        assert "D:P" in sddl and sddl.count("(A;") == 1 and ";;;OW)" in sddl
    finally:
        kernel.LocalFree(text)