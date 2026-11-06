"""Offline platform release receipt packaging; never a publisher or live verifier.

Trust comes from the operator-protected deployment evidence directory, NOT SHA256
or assertions in JSON. No signature/crypto-attestation or tenant approval is implied.
See docs/auto-publication-artifact.md for the required collector contract.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import math
import os
import re
import stat
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from xml.sax.saxutils import unescape

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = "services/control-plane/src/aiflux/pricing/auto-routing-defaults.json"
ENDPOINT = "https://poc-ids-token-ex-foundry.services.ai.azure.com/providers/microsoft/v1/systemone"
PRINCIPAL = "bcf69911-f34e-4f33-acd8-a36f164db811"
CLIENT = "5792b72e-1605-4dce-a594-4c430a5af619"
ACCOUNT = ("/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/"
           "IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry")
POLICY = ACCOUNT.split("/providers/")[0] + (
    "/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim/apis/aiflux-dev-unified/policies/policy")
CHAT_PATH = "/dev/llm/v1/chat/completions"
CONTRACT = "systemone-choice-probabilities-v1"
LIMIT = 8 * 1024 * 1024
Json = dict[str, Any]


class EvidenceError(ValueError):
    """Evidence is missing, inconsistent, unsupported, or outside the trust root."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encode(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _pairs(items: list[tuple[str, Any]]) -> Json:
    result: Json = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def parse(raw: bytes) -> Json:
    def invalid(value: str) -> Any:
        raise EvidenceError("nonfinite JSON value: " + value)
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)
    require(isinstance(value, dict), "JSON object required")
    return value


def timestamp(value: Any) -> datetime:
    require(isinstance(value, str) and value.endswith(("Z", "+00:00")), "UTC timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result <= datetime.now(timezone.utc), "future evidence timestamp")
    return result


def _plain(path: Path) -> None:
    """Reject links/reparse points in every existing component, including root."""
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode)
                and not getattr(info, "st_file_attributes", 0) & 0x400, "linked/reparse path rejected")
    if path.is_file():
        require(path.stat().st_nlink == 1, "hardlinked evidence rejected")


class Boundary:
    """Read and retain exact bytes once; recheck all consumed files before write."""

    def __init__(self, root: Path):
        self.root = root.absolute()
        _plain(self.root)
        require(self.root.resolve(strict=True) == self.root, "canonical trusted directory required")
        require(self.root.is_dir(), "trusted deployment directory required")
        self.consumed: dict[Path, bytes] = {}

    def read(self, name: str) -> bytes:
        require(isinstance(name, str) and "\\" not in name and ":" not in name, "relative evidence path required")
        path = PurePosixPath(name)
        require(not path.is_absolute() and bool(path.parts)
                and all(p not in {".", ".."} for p in name.split("/")), "unsafe evidence path")
        target = self.root.joinpath(*path.parts)
        _plain(target)
        require(target.is_file() and target.stat().st_size <= LIMIT, "bounded regular evidence file required")
        raw = target.read_bytes()
        require(len(raw) <= LIMIT, "evidence too large")
        if target in self.consumed:
            require(self.consumed[target] == raw, "evidence changed during validation")
        self.consumed[target] = raw
        return raw

    def ref(self, reference: Json) -> bytes:
        require(set(reference) == {"path", "sha256"}, "file reference requires path and sha256")
        raw = self.read(reference["path"])
        require(digest(raw) == reference["sha256"], "file reference hash mismatch")
        return raw

    def recheck(self) -> None:
        for path, raw in list(self.consumed.items()):
            require(self.read(path.relative_to(self.root).as_posix()) == raw, "immutable evidence changed")


def source_paths() -> list[str]:
    """Fixed scope; a caller cannot omit a policy, pricing or render input."""
    paths = {DEFAULTS, "services/control-plane/src/aiflux/auto_snapshot.py",
             "services/control-plane/src/aiflux/config.py", "services/control-plane/src/aiflux/decision_router.py",
             "services/control-plane/src/aiflux/display_pricing.py",
             "services/control-plane/src/aiflux/foundry_inventory.py",
             "services/control-plane/src/aiflux/external_inventory.py",
             "scripts/deployment/auto_publication_artifact.py"}
    for folder, pattern in (("infra/project-route", "*.tf"), ("gateway/policies", "*"),
                            ("gateway/catalog", "*.json"), ("services/control-plane/src/aiflux/pricing", "*.json")):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob(pattern) if p.is_file())
    return sorted(paths)


def _structure(raw: str, export_layer: bool = False) -> Any:
    require("<!DOCTYPE" not in raw.upper() and "<!ENTITY" not in raw.upper(), "DTD/entity rejected")
    root = ET.fromstring(raw)
    def decode(text: str) -> str:
        return unescape(text, {"&quot;": '"', "&apos;": "'"}) if export_layer else text
    def node(element: ET.Element) -> Any:
        children = list(element)
        text = element.text or ""
        return (element.tag, sorted((k, decode(v)) for k, v in element.attrib.items()),
                "" if children and not text.strip() else decode(text),
                [(node(c), decode(c.tail or "") if (c.tail or "").strip() else "") for c in children])
    return node(root)


def _snapshot(boundary: Boundary, reference: Json) -> Json:
    # This is the existing backend's source-bound defaults function, not a
    # caller-selected snapshot/version or an invocation of a runtime endpoint.
    from aiflux import auto_snapshot
    from aiflux.config import Settings
    require(Path(auto_snapshot.__file__).resolve() == (ROOT / "services/control-plane/src/aiflux/auto_snapshot.py").resolve(),
            "snapshot implementation must be the bound checkout source")
    current = auto_snapshot.defaults(Settings(_env_file=None, environment="testing", local_auth_enabled=True,
        foundry_inventory_path=ROOT / "gateway/catalog/foundry-inventory-20261026.json"))
    expected = {"version": current["version"], "profiles": current["profiles"],
                "candidates": {c["id"]: c for c in current["candidates"]}}
    require(parse(boundary.ref(reference)) == expected, "snapshot does not match platform defaults")
    return expected


def _number(value: Any, maximum: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum


def evaluate(trusted_root: Path, manifest_name: str) -> tuple[Json, Boundary]:
    """Validate trusted collector records. Missing real proof has no fallback."""
    b = Boundary(trusted_root)
    manifest_raw = b.read(manifest_name)
    m = parse(manifest_raw)
    require(set(m) == {"schema", "kind", "release", "sources", "snapshot", "rendered_policy", "authorization",
                       "native", "readback_rawxml", "readback_xml", "runtime", "review"}, "manifest fields unsupported")
    require(type(m["schema"]) is int and m["schema"] == 1
            and m["kind"] == "auto-production-release-evaluation", "production manifest required")
    release = m["release"]
    require(set(release) == {"id", "attempt_id", "stage", "actor", "started_at", "finished_at"}, "release identity required")
    require(all(isinstance(release[k], str) and release[k].strip() for k in release), "release fields required")
    require(release["stage"] == "production-auto", "diagnostic stages cannot publish")
    start, finish = timestamp(release["started_at"]), timestamp(release["finished_at"])
    require(start < finish, "release time order")
    sources = parse(b.ref(m["sources"]))
    require(set(sources) == set(source_paths()), "complete source manifest required")
    for name in source_paths():
        path = ROOT / name
        _plain(path)
        require(digest(path.read_bytes()) == sources[name], "current release source mismatch: " + name)
    snapshot = _snapshot(b, m["snapshot"])
    policy_raw = b.ref(m["rendered_policy"])
    policy_hash = digest(policy_raw)
    binding = {"release_id": release["id"], "attempt_id": release["attempt_id"], "stage": release["stage"],
               "source_manifest_sha256": m["sources"]["sha256"], "snapshot_version": snapshot["version"],
               "policy_sha256": policy_hash}

    def record(name: str) -> Json:
        value = parse(b.ref(m[name]))
        require("runtime_verified" not in value, "runtime_verified is derived, never an input flag")
        require(value["binding"] == binding and value["origin"] == "deployment-collector", "release evidence binding")
        require(start <= timestamp(value["collected_at"]) <= finish, "evidence outside authorized attempt")
        return value

    auth = record("authorization")
    require(auth["kind"] == "platform-release-authorization" and auth["authorized_stage"] == release["stage"]
            and auth["authorized_attempt_id"] == release["attempt_id"]
            and auth["actor"] == release["actor"], "platform release authorization required")
    intent_at = timestamp(auth["collected_at"])
    grant = parse(b.ref(auth["role_assignment"]))
    definition = parse(b.ref(auth["role_definition"]))
    gp, dp = grant["properties"], definition["properties"]
    require(gp["principalId"] == PRINCIPAL and gp["scope"] == ACCOUNT and not gp.get("condition")
            and gp["roleDefinitionId"] == definition["id"], "exact gateway role binding required")
    require(any("Microsoft.CognitiveServices/*" in p.get("dataActions", [])
                and not p.get("notDataActions") for p in dp["permissions"]), "inference role metadata required")
    require(parse(b.ref(auth["deny_assignments"])) == {"value": []}, "unresolved deny assignments")
    budget = auth["budget"]
    require(all(type(v) is int for v in budget.values())
            and budget == {"auto_requests": 3, "score_requests": 3, "provider_requests": 3,
                       "retries": 0, "max_completion_tokens": 1024, "score_timeout_ms": 5000,
                       "score_response_bytes": 65536}, "reviewed bounded production budget required")
    native = record("native")
    require(native["kind"] == "apim-native-production-validation" and type(native["exit_code"]) is int
            and native["exit_code"] == 0
            and native["policy_resource_id"] == POLICY and native["run_id"], "actual native validation required")
    rendering = parse(b.ref(native["render_output"]))
    require(rendering["renderer"] == "terraform-console" and rendering["binding"] == binding
            and rendering["policy"].encode("utf-8") == policy_raw, "native exact source rendering required")
    native_log = b.ref(native["log"]).decode("utf-8")
    require(all(str(v) in native_log for v in (native["run_id"], *binding.values())), "native log release binding")
    read_times = []
    for name, fmt in (("readback_rawxml", "rawxml"), ("readback_xml", "xml")):
        readback = record(name)
        require(readback["method"] == "GET" and readback["http_status"] == 200
                and readback["format"] == fmt and readback["resource_id"] == POLICY, "policy readback scope/format")
        response = parse(b.ref(readback["response"]))
        require(response["id"] == POLICY and response["properties"]["format"] == fmt, "policy response identity")
        actual = response["properties"]["value"]
        if fmt == "rawxml":
            require(digest(actual.encode("utf-8")) == policy_hash, "deployed raw policy hash differs from rendering")
        reference = _structure(policy_raw.decode("utf-8"))
        require(_structure(actual) == reference or (fmt == "xml" and _structure(actual, True) == reference),
                "deployed policy differs from exact rendering")
        read_times.append(timestamp(readback["collected_at"]))
    tree = ET.fromstring(policy_raw)
    require(tree.tag == "policies" and [c.tag for c in tree] == ["inbound", "backend", "outbound", "on-error"],
            "complete production policy required, not a diagnostic fragment")
    variables = tree.findall('.//set-variable[@name="aiflux-auto-snapshot"]')
    require(len(variables) == 1, "one source-bound snapshot required")
    encoded = re.fullmatch(r'@\(System.Text.Encoding.UTF8.GetString\(Convert.FromBase64String\("([A-Za-z0-9+/=]+)"\)\)\)',
                           variables[0].get("value", ""))
    require(encoded and parse(base64.b64decode(encoded[1], validate=True)) == snapshot, "rendered snapshot mismatch")
    mi = tree.findall('.//authentication-managed-identity[@id="aiflux-auto-auth"]')
    require(len(mi) == 1 and mi[0].get("client-id") == CLIENT
            and mi[0].get("resource") == "https://cognitiveservices.azure.com", "rendered gateway MI mismatch")
    scoring = tree.findall('.//send-request[@id="aiflux-auto-resolver"]')
    require(len(scoring) == 1 and scoring[0].findtext("set-url") == ENDPOINT
            and scoring[0].get("timeout") == "5", "rendered endpoint/budget mismatch")
    runtime = record("runtime")
    require(runtime["kind"] == "production-auto-end-to-end" and runtime["native_run_id"] == native["run_id"]
            and runtime["policy_resource_id"] == POLICY and runtime["gateway_principal"] == PRINCIPAL
            and runtime["gateway_client"] == CLIENT, "production gateway runtime required")
    api = parse(b.ref(runtime["api_readback"]))
    require(api["id"] == POLICY.removesuffix("/policies/policy")
            and api["properties"]["path"] == "dev/llm/v1" and api["properties"]["isCurrent"] is True
            and api["properties"]["isOnline"] is True, "current online production API required")
    require(len(runtime["requests"]) == 3, "all three production profiles required")
    profiles, ids = set(), set()
    last_request = intent_at
    for ref in runtime["requests"]:
        event = parse(b.ref(ref))
        require(event["binding"] == binding and event["native_run_id"] == native["run_id"], "request release binding")
        request_at, response_at = timestamp(event["started_at"]), timestamp(event["finished_at"])
        require(intent_at <= min(read_times) <= max(read_times) <= request_at < response_at <=
                timestamp(runtime["collected_at"]), "production request timestamp order")
        last_request = max(last_request, response_at)
        request = parse(b.ref(event["request"]))
        redacted = parse(b.ref(event["redacted_request"]))
        score_request = parse(b.ref(event["score_request"]))
        score_raw = b.ref(event["score_response"])
        score = parse(score_raw)
        provider = parse(b.ref(event["provider_response"]))
        response = parse(b.ref(event["response"]))
        trace = parse(b.ref(event["gateway_trace"]))
        require(trace["kind"] == "apim-production-transaction" and trace["binding"] == binding
            and trace["request_id"] == event["request_id"]
            and trace["started_at"] == event["started_at"] and trace["finished_at"] == event["finished_at"]
            and trace["gateway_principal"] == PRINCIPAL and trace["gateway_client"] == CLIENT
            and trace["authentication"] == "managed-identity" and trace["policy_resource_id"] == POLICY
            and trace["native_run_id"] == native["run_id"], "actual correlated gateway transaction required")
        payload_keys = ("request", "redacted_request", "score_request", "score_response", "provider_response", "response")
        require(trace["payloads"] == {k: event[k]["sha256"] for k in payload_keys}, "gateway trace payload binding")
        observed_keys = ("score_http_status", "provider_http_status", "http_status", "score_requests",
                 "provider_requests", "retries", "score_endpoint", "score_identity", "score_elapsed_ms",
                 "provider_selected_model", "method", "path")
        require(trace["observed"] == {k: event[k] for k in observed_keys}, "gateway trace observations mismatch")
        profile = request.get("routing_profile", "balanced")
        require(profile in snapshot["profiles"] and profile not in profiles, "unique production profiles required")
        profiles.add(profile)
        require(isinstance(event["request_id"], str) and event["request_id"] and event["request_id"] not in ids,
                "unique correlated request id required")
        ids.add(event["request_id"])
        require(request["model"] == "auto" and event["method"] == "POST"
            and event["path"] == CHAT_PATH and event["policy_resource_id"] == POLICY,
                "actual production Auto request required")
        maximum = request["max_completion_tokens"]
        require(type(maximum) is int and 1 <= maximum <= budget["max_completion_tokens"], "completion budget exceeded")
        pool = snapshot["profiles"][profile]["candidate_models"]
        expected_score = {"model": "Decision-1", "state": {"messages": redacted["messages"],
            "max_completion_tokens": maximum}, "questions": {"route": {"type": "choice",
            "instructions": snapshot["profiles"][profile]["instructions"],
            "criteria": {alias: json.dumps(snapshot["candidates"][alias], ensure_ascii=False) for alias in pool}}}}
        # Criteria are JSON strings produced by JObject.ToString(); ignore JSON
        # indentation/key order only, never descriptor content or instructions.
        actual_score = json.loads(json.dumps(score_request))
        actual_criteria = actual_score["questions"]["route"]["criteria"]
        require(set(actual_criteria) == set(pool), "diagnostic/unconnected candidate pool")
        require({k: parse(v.encode()) for k, v in actual_criteria.items()} ==
                {k: snapshot["candidates"][k] for k in pool}, "production descriptor mismatch")
        actual_score["questions"]["route"]["criteria"] = expected_score["questions"]["route"]["criteria"]
        require(actual_score == expected_score, "production score request mismatch")
        messages = redacted["messages"]
        require(1 <= len(messages) <= 25 and all(isinstance(v["content"], str) and
                1 <= len(v["content"]) <= 4800 for v in messages)
                and sum(len(v["content"]) for v in messages) <= 8000, "redacted request budget")
        counters = ("score_http_status", "provider_http_status", "http_status", "score_requests", "provider_requests", "retries")
        require(all(type(event[k]) is int for k in counters)
            and event["score_http_status"] == event["provider_http_status"] == event["http_status"] == 200
                and event["score_requests"] == event["provider_requests"] == 1 and event["retries"] == 0
                and event["score_endpoint"] == ENDPOINT and event["score_identity"] == PRINCIPAL
                and _number(event["score_elapsed_ms"], budget["score_timeout_ms"])
                and len(score_raw) <= budget["score_response_bytes"], "runtime identity/status/budget proof")
        answer = score["answers"]["route"]
        probabilities = answer["probabilities"]
        require(answer["type"] == "choice" and answer.get("choice") in pool
                and set(probabilities) == set(pool) and all(_number(v, 1) for v in probabilities.values())
                and abs(sum(probabilities.values()) - 1) <= 0.02, "production choice schema unproven")
        selected = min(pool, key=lambda a: (-probabilities[a], a))
        require(probabilities[answer["choice"]] == probabilities[selected], "choice is not maximal")
        routing = response["routing"]
        overhead = routing["decision_overhead"]
        require(routing["selected_model"] == event["provider_selected_model"] == selected
                and routing["routing_profile"] == profile and routing["config_version"] == snapshot["version"]
                and routing["fallback_used"] is False and routing["failure"] is None
                and _number(overhead["latency_ms"], 120000) and overhead["cost_usd"] is None,
                "production routing/overhead proof")
        expected_usage = {k: v if type(v := score.get("usage", {}).get(k)) is int and 0 <= v <= 2147483647
                          else None for k in ("input_tokens", "output_tokens")}
        require(overhead["usage"] == expected_usage, "score usage mismatch")
        require({k: v for k, v in response.items() if k != "routing"} == provider
                and isinstance(provider.get("choices"), list) and bool(provider["choices"])
                and isinstance(provider.get("usage"), dict), "full provider completion required")
    review = record("review")
    require(review["kind"] == "independent-native-release-review" and review["verdict"] == "PASS"
            and review["reviewer"] != release["actor"] and review["reviewer"]
            and review["native_run_id"] == native["run_id"]
            and timestamp(review["collected_at"]) >= last_request, "independent actual release review required")
    expected_reviewed = {k: m[k]["sha256"] for k in ("sources", "snapshot", "rendered_policy", "authorization",
                         "native", "readback_rawxml", "readback_xml", "runtime")}
    require(review["reviewed"] == expected_reviewed, "review does not match exact release evidence")
    require(timestamp(review["collected_at"]) >= timestamp(runtime["collected_at"]), "review predates runtime collection")
    review_text = b.ref(review["text"]).decode("utf-8")
    require(all(str(v) in review_text for v in (*binding.values(), *expected_reviewed.values(), native["run_id"])),
            "retained actual review text binding")
    require(intent_at <= timestamp(native["collected_at"]) <= min(read_times), "authorized native stage order")
    b.recheck()
    for name, sha in sources.items():
        require(digest((ROOT / name).read_bytes()) == sha, "source changed during evaluation")
    receipt = {"schema": 1, "snapshot_version": snapshot["version"], "policy_sha256": policy_hash,
        "gateway_runtime_evidence_sha256": m["runtime"]["sha256"],
        "authorization_evidence_sha256": m["authorization"]["sha256"],
        "endpoint": ENDPOINT, "deployment": "Decision-1", "gateway_principal": PRINCIPAL,
        "gateway_client": CLIENT, "response_contract": CONTRACT, "runtime_verified": True,
        "verified_at": runtime["collected_at"], "release": release,
        "release_manifest_sha256": digest(manifest_raw), "review_sha256": m["review"]["sha256"]}
    return receipt, b


def _private_directory(path: Path) -> None:
    _plain(path.parent)
    os.mkdir(path, 0o700)  # exclusive; never reuse an existing release package
    if os.name == "nt":
        # Protected DACL: owner rights only, no inherited broad grants. No shell,
        # icacls, network, or external dependency. Fail before writing any file.
        from ctypes import wintypes
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
                            ctypes.POINTER(wintypes.DWORD)]
        convert.restype = wintypes.BOOL
        set_security = advapi.SetFileSecurityW
        set_security.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
        set_security.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        descriptor = ctypes.c_void_p()
        try:
            require(convert("D:P(A;OICI;FA;;;OW)", 1, ctypes.byref(descriptor), None), "owner DACL conversion failed")
            require(set_security(str(path), 0x80000004, descriptor), "owner DACL application failed")
        except BaseException:
            path.rmdir()
            raise
        finally:
            if descriptor:
                kernel.LocalFree(descriptor)


def _write(path: Path, value: Json) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encode(value))
        handle.flush()
        os.fsync(handle.fileno())


def _settings(package: Path, receipt: Json) -> Json:
    return {"AIFLUX_AUTO_ROUTING_PUBLICATION_PATH": str(package / "receipt.json"),
            "AIFLUX_AUTO_ROUTING_PUBLISHED_POLICY_SHA256": receipt["policy_sha256"],
            "AIFLUX_AUTO_ROUTING_ENABLED": "false"}


def prepare_artifact(trusted_root: Path, manifest_name: str, package_path: Path) -> Json:
    """Write a local receipt only after complete evaluation; never enable Auto."""
    receipt, boundary = evaluate(trusted_root, manifest_name)
    package = package_path.absolute()
    require(not package.exists(), "exclusive new package required")
    require(package.parent.resolve(strict=True) == package.parent, "canonical output parent required")
    require(not package.is_relative_to(boundary.root) and not boundary.root.is_relative_to(package),
            "output must be separate from immutable deployment evidence")
    boundary.recheck()
    _private_directory(package)
    try:
        _write(package / "receipt.json", receipt)
        _write(package / "settings.json", _settings(package, receipt))
        _write(package / "package.json", {"schema": 1, "receipt_sha256": digest(encode(receipt)),
            "settings_sha256": digest(encode(_settings(package, receipt))),
            "release_manifest_sha256": receipt["release_manifest_sha256"], "auto_enabled": False})
        if os.name != "nt":
            fd = os.open(package, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    except BaseException:
        # Never leave a partial receipt available for release packaging.
        for name in ("receipt.json", "settings.json", "package.json"):
            (package / name).unlink(missing_ok=True)
        package.rmdir()
        raise
    return receipt


def read_local_receipt(trusted_root: Path, manifest_name: str, package_path: Path) -> Json:
    """Re-evaluate retained evidence; this is not the lightweight runtime reader."""
    expected, _ = evaluate(trusted_root, manifest_name)
    b = Boundary(package_path)
    receipt_raw, settings_raw = b.read("receipt.json"), b.read("settings.json")
    require(parse(receipt_raw) == expected, "local receipt mismatch")
    require(parse(settings_raw) == _settings(package_path.absolute(), expected), "settings binding mismatch")
    require(parse(b.read("package.json")) == {"schema": 1, "receipt_sha256": digest(receipt_raw),
        "settings_sha256": digest(settings_raw), "release_manifest_sha256": expected["release_manifest_sha256"],
        "auto_enabled": False}, "package integrity mismatch")
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("create", "read"))
    parser.add_argument("--trusted-root", type=Path, required=True)
    parser.add_argument("--manifest", required=True, help="Relative manifest inside the trusted root")
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        operation = prepare_artifact if args.operation == "create" else read_local_receipt
        receipt = operation(args.trusted_root, args.manifest, args.package)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, OverflowError, ET.ParseError) as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "local_receipt_validated", "policy_sha256": receipt["policy_sha256"],
                      "auto_enabled": False, "cloud_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())