"""One consumed request per exact new alias. No retry/resume/deployment path.

Existing APIM product subscription listSecrets is an explicitly authorized READ;
its primary key and CLI ARM bearer live only in memory. All artifacts are NEW.
An interrupted request is UNKNOWN and consumed forever, never a retry ticket.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import UUID, uuid4

import requests
from requests.adapters import HTTPAdapter

from aiflux.foundry_inventory import FoundryInventory
from scripts.deployment import runtime_rollout as rt
from scripts.deployment import foundry_eight_gateway_apply as applied
from scripts.deployment.apim_route_repair import SUBSCRIBER

ROOT = rt.ROOT
HOME = rt.HOME / "foundry-eight-acceptance-20261031"
ALIASES = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5-fast",
           "claude-haiku-5-5", "gpt-6.1-terra", "gpt-6-luna", "claude-opus-4-8", "Mistral-Large-3")
APIM = applied.APIM
ACCOUNT = rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
PROJECT = ACCOUNT + "/projects/poc-ids-token-ex-foundry-project"
GATEWAY = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"
CATALOG = ROOT / "gateway/catalog"


class AcceptanceError(RuntimeError):
    """Only fixed controller-generated labels may be retained."""


def require(ok, code):
    if not ok:
        raise AcceptanceError(code)


def now():
    return datetime.now(UTC).isoformat()


def sha(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return sha(raw)


def inputs():
    paths = [CATALOG / p for p in ("foundry-inventory-20261026.json", "external-inventory.json",
             "project-routes.json", "fireworks-candidate-routes.json", "foundry-eight-candidate-routes.json")]
    paths += [ROOT / "services/usage-ingestion/approved_catalog.py",
              ROOT / "services/usage-ingestion/catalog-bindings.json", Path(__file__),
              ROOT / "tests/unit/test_foundry_eight_acceptance.py",
              Path(applied.__file__), Path(applied.reader.__file__), Path(rt.__file__),
              ROOT / "services/control-plane/src/aiflux/foundry_inventory.py",
              ROOT / "services/control-plane/src/aiflux/external_inventory.py",
              applied.EVIDENCE / "verified.json", applied.EVIDENCE / "apply-result.json",
              applied.EVIDENCE / "postapply-policy.xml", applied.EVIDENCE / "preapply-policy.xml",
              applied.reader.HOME / "candidate-policy.xml"]
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in paths}


def cli(args):
    # Never persist stdout/stderr: token output must stay ephemeral.
    env = {**rt.ENV, "AZURE_CORE_COLLECT_TELEMETRY": "false"}
    result = subprocess.run(rt.CLI + args + ["--only-show-errors", "-o", "json"], cwd=ROOT,
                            env=env, capture_output=True, timeout=90)
    require(result.returncode == 0, "existing_cli_auth_failed_sensitive_details_suppressed")
    return json.loads(result.stdout)


class Client:
    def __init__(self):
        require(Path(rt.CA).is_file(), "existing_trusted_ca_required")
        account = cli(["account", "show"])
        require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT
                and account["state"] == "Enabled", "current_account_scope")
        token = cli(["account", "get-access-token", "--subscription", rt.SUB,
                     "--resource", "https://management.azure.com/"])["accessToken"]
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        require(claims["tid"] == rt.TENANT and claims["oid"] == rt.OPERATOR
                and claims["exp"] > datetime.now(UTC).timestamp() + 900, "current_arm_identity_expiry")
        self.token = token
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=0))
        self.session.verify = rt.CA

    def close(self):
        self.token = None
        self.session.close()

    def wire(self, method, url, *, headers, body=None, limit=8 * 1024 * 1024):
        # A Session adapter configured with max_retries=0, redirects disabled,
        # no SDK, no second send, bounded connect/read and response size.
        with self.session.request(method, url, headers=headers, json=body, timeout=(10, 90),
                                  allow_redirects=False, stream=True) as response:
            raw = bytearray()
            for block in response.iter_content(chunk_size=8192):
                raw.extend(block)
                require(len(raw) <= limit, "bounded_response_exceeded")
            return response.status_code, dict(response.headers), bytes(raw)

    def arm(self, path, *, secret=False):
        allowed = {APIM + "/apis/aiflux-dev-unified/policies/policy?format=xml",
                   APIM + "/subscriptions/" + SUBSCRIBER,
                   APIM + "/subscriptions/" + SUBSCRIBER + "/listSecrets",
                   APIM + "/backends", ACCOUNT, PROJECT, PROJECT + "/connections", ACCOUNT + "/deployments"}
        require(path in allowed and secret == path.endswith("/listSecrets"), "exact_read_scope_only")
        version = "2024-05-01" if path.startswith(APIM) else "2025-06-01"
        url = "https://management.azure.com" + path + ("&" if "?" in path else "?") + "api-version=" + version
        status, _, raw = self.wire("POST" if secret else "GET", url,
                                  headers={"Authorization": "Bearer " + self.token})
        require(status == 200, "arm_read_http_" + str(status))
        value = json.loads(raw)
        # Fail closed on pagination instead of mistaking one page for all rows.
        require(not value.get("nextLink"), "additional_page_requires_separate_review_no_inference")
        return value

    def send(self, alias, key, request_id):
        return self.wire("POST", GATEWAY + "/chat/completions", limit=65536,
            headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json",
                     "x-ms-client-request-id": request_id},
            body={"model": alias, "messages": [{"role": "user", "content": "Reply with a short greeting."}],
                  "max_completion_tokens": 128, "stream": False})


def policy_binding(value):
    current = value["properties"]["value"]
    verified = load(applied.EVIDENCE / "verified.json")
    desired = (applied.reader.HOME / "candidate-policy.xml").read_bytes().decode()
    previous = (applied.EVIDENCE / "preapply-policy.xml").read_bytes().decode()
    require(verified["passed"] and verified["plan_sha256"] == applied.APPROVED
            and verified["current_policy_matches_saved_candidate"], "applied_exact_gateway_required")
    require(sha(current.encode()) == verified["current_policy_sha256"], "live_policy_byte_drift")
    node = applied.reader.xml_node(current, exported=True)
    require(applied.reader.structural(node) == applied.reader.structural(applied.reader.xml_node(desired)),
            "live_policy_semantic_drift")
    proof = applied.semantic_policy(previous, desired)
    guard = node.find('./outbound//set-body[@id="aiflux-anthropic-normalization"]')
    require(guard is not None, "normalizer_required")
    return {"at": now(), "policy_sha256": sha(current.encode()), "plan_sha256": applied.APPROVED,
            "normalizer_sha256": sha((guard.text or "").encode()), "semantic_guard": proof,
            "fast_proof_method": "HTTP200 normalized fast alias under exact live policy requires native usage.speed=fast",
            "speed_exposed_in_public_usage": False, "speed_inferred_from_latency": False}


def metadata_guard(old, live, candidate):
    require(not live.get("nextLink"), "complete_deployments_required")
    rows = {r["name"]: r for r in live["value"]}
    require(len(rows) == len(live["value"]), "unique_live_deployments")
    old_names = {d["name"] for d in old["deployments"]}
    selected = old_names | set(ALIASES)
    require(len(old_names) == 13 and len(selected) == 21 and selected <= rows.keys(), "exact_selected_twentyone")
    require(set(rows) - selected <= {"mistral-medium-3-5"}, "unreviewed_extra_deployment")
    for saved in old["deployments"]:
        row = rows[saved["name"]]
        p = row["properties"]
        require(row["id"].lower() == saved["id"].lower()
                and p["model"] == {"name": saved["model_name"], "version": saved["model_version"], "format": saved["model_format"]}
                and p["provisioningState"] == saved["provisioning_state"] == "Succeeded"
                and row["sku"]["capacity"] == saved["capacity"]
                and (saved.get("sku") is None or saved["sku"] == row["sku"]["name"]), "old_deployment_changed")
    additions = []
    for alias in ALIASES:
        row, expected = rows[alias], candidate["routes"][alias]
        p = row["properties"]
        require(row["id"] == ACCOUNT + "/deployments/" + alias
                and p["model"] == {"name": expected["model_name"], "version": expected["version"], "format": expected["provider"]}
                and p["provisioningState"] == "Succeeded" and p["capabilities"]["chatCompletion"] == "true"
                and row["sku"] == {"name": expected["sku"], "capacity": expected["capacity"]}
                and p.get("raiPolicyName") == "Microsoft.DefaultV2", "new_deployment_contract:" + alias)
        additions.append({"id": row["id"], "name": alias, "model_name": p["model"]["name"],
            "model_version": p["model"]["version"], "model_format": p["model"]["format"],
            "provisioning_state": "Succeeded", "deployment_state": None,
            "capacity": row["sku"]["capacity"], "chat_completion": True, "decision": False, "sku": row["sku"]["name"]})
    return additions, {"actual_count": len(rows), "selected_count": len(selected),
                       "excluded_names": sorted(set(rows) - selected), "complete": True}


def clean_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", value) else None


def summary(alias, status, headers, raw):
    headers = {k.lower(): v for k, v in headers.items()}
    record = {"alias": alias, "status": status, "response_sha256": sha(raw),
              "correlation_id": clean_id(headers.get("x-aiflux-request-id")),
              "apim_request_id": clean_id(headers.get("apim-request-id")),
              "provider_request_id": clean_id(headers.get("x-request-id")),
              "assistant_nonempty": False, "response_model": None, "usage": None, "finish_reason": None}
    try:
        body = json.loads(raw)
        if status != 200:
            # Never keep arbitrary error text (may contain provider content).
            record["error_code"] = next((code for code in ("invalid_provider_response", "provider_unavailable",
                "pii_inspection_unavailable", "RateLimitReached", "PermissionDenied", "InternalServerError")
                if code in raw.decode("utf-8", errors="replace")), "unclassified_error_body_suppressed")
            return record
        record["response_model"] = body.get("model") if body.get("model") == alias else None
        record["response_id"] = clean_id(body.get("id"))
        choices = body.get("choices")
        if isinstance(choices, list) and len(choices) == 1:
            choice = choices[0]
            message = choice.get("message", {})
            text = message.get("content")
            record["assistant_nonempty"] = (message.get("role") == "assistant" and isinstance(text, str) and bool(text.strip()))
            record["finish_reason"] = choice.get("finish_reason") if choice.get("finish_reason") in ("stop", "length") else None
        usage = body.get("usage")
        if isinstance(usage, dict):
            details = usage.get("prompt_tokens_details")
            details = details if isinstance(details, dict) else {}
            # Invalid values stay null plus an invalid flag, never coerced to 0.
            fields = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
            fields.update(cached_input_tokens=details.get("cached_tokens"), cache_write_tokens=details.get("cache_write_tokens"))
            record["usage_invalid"] = any(v is not None and (type(v) is not int or v < 0 or v > 2147483647) for v in fields.values())
            record["usage"] = {k: v if type(v) is int and 0 <= v <= 2147483647 else None for k, v in fields.items()}
    except (ValueError, TypeError, AttributeError, KeyError):
        record["parse_failed"] = True
    return record


def validate_probe(record):
    require(record["status"] == 200 and record["response_model"] == record["alias"]
            and record["assistant_nonempty"] and record["finish_reason"] == "stop"
            and record.get("response_id") and record["correlation_id"]
            and not record.get("usage_invalid") and not record.get("parse_failed"), "gateway_response_contract_failed")
    UUID(record["correlation_id"])
    u = record["usage"] or {}
    require(type(u.get("completion_tokens")) is int and 1 <= u["completion_tokens"] <= 128, "measured_output_required")
    if u.get("prompt_tokens") is None:
        require(record["alias"].startswith("claude-") and u.get("total_tokens") is None
                and (u.get("cached_input_tokens") is None or u.get("cache_write_tokens") is None), "unknown_native_cache_only")
    else:
        require(type(u.get("total_tokens")) is int and u["total_tokens"] == u["prompt_tokens"] + u["completion_tokens"], "measured_usage_total")
        require(all(v is None or v <= u["prompt_tokens"] for v in (u.get("cached_input_tokens"), u.get("cache_write_tokens"))), "cache_subset")


def probes(client, key, home, binding):
    results = []
    for index, alias in enumerate(ALIASES):
        stem = home / "probes" / f"{index + 1:02d}-{alias}"
        request_id = str(uuid4())
        intent = {"at": now(), "pid": os.getpid(), "alias": alias, "client_request_id": request_id,
                  "policy_sha256": binding["policy_sha256"], "max_completion_tokens": 128,
                  "max_requests": 1, "retries": 0, "fallback": False, "consumed_before_send": True}
        intent_sha = write(str(stem) + "-intent.json", intent)
        started = time.monotonic()
        try:
            status, headers, raw = client.send(alias, key, request_id)
            record = summary(alias, status, headers, raw)
            record.update(at_utc=intent["at"], received_at=now(), client_request_id=request_id,
                          intent_sha256=intent_sha, elapsed_seconds=round(time.monotonic() - started, 3),
                          policy_sha256=binding["policy_sha256"], transport_invocations=1)
            # Retain actual sanitized response even when it fails validation.
            write(str(stem) + "-response.json", record)
            validate_probe(record)
            if alias == "claude-opus-5-5-fast":
                record["fast_speed_proof"] = {"speed": "fast", "method": binding["fast_proof_method"],
                    "normalizer_sha256": binding["normalizer_sha256"], "policy_sha256": binding["policy_sha256"],
                    "correlation_id": record["correlation_id"], "direct_native_trace_retained": False}
            write(str(stem) + "-passed.json", record)
            results.append(record)
            print(json.dumps({"alias": alias, "status": status, "passed": True, "usage": record["usage"]}), flush=True)
        except Exception as error:
            write(str(stem) + "-failure.json", {"at": now(), "alias": alias,
                "error_type": type(error).__name__, "reason": str(error) if isinstance(error, AcceptanceError) else "sensitive_details_suppressed",
                "request_consumed": True, "transport_invocations": 1, "retry_permitted": False})
            raise AcceptanceError("consumed_probe_failed_STOP:" + alias) from None
    require(len(results) == 8 and len({r["correlation_id"] for r in results}) == 8, "eight_unique_actual_probes")
    return results


def promote(home, old, additions, results, candidate, bound):
    require(len(results) == 8 and [r["alias"] for r in results] == list(ALIASES), "all_eight_success_required")
    for row in results:
        validate_probe(row)
    require(next(r for r in results if r["alias"] == "claude-opus-5-5-fast").get("fast_speed_proof"), "actual_fast_proof_required")
    accepted = deepcopy(old)
    conversions = []
    for route in accepted["routes"]:
        conversions.append({"alias": route["alias"], "old_endpoint_url": route["endpoint_url"], "new_endpoint_url": GATEWAY,
                            "reason": "public gateway metadata conversion only; original inference evidence grandfathered; no new probe"})
        route["endpoint_url"] = GATEWAY
    accepted["deployments"].extend(additions)
    for d in additions:
        accepted["routes"].append({"alias": d["name"], "deployment_id": d["id"], "backend_model": d["name"],
            "model_name": d["model_name"], "model_version": d["model_version"], "endpoint_url": GATEWAY,
            "api_format": "openai-chat-completions", "capabilities": ["chat"], "max_completion_tokens": 1024,
            "gateway_validated": True, "upstream_token_parameter": candidate["routes"][d["name"]]["token_parameter"], "expires_at": None})
    parsed = FoundryInventory.model_validate(accepted)
    require(len(parsed.deployments) == 21 and len(parsed.routes) == 20
            and all(parsed.route(r.alias) for r in parsed.routes), "official_inventory_schema_and_routes")
    context = home / "accepted-context"
    # New context only: never rewrite historical source JSON or bound artifacts.
    for name in ("project-routes.json", "fireworks-candidate-routes.json", "foundry-eight-candidate-routes.json", "external-inventory.json"):
        write(context / "gateway/catalog" / name, (CATALOG / name).read_bytes())
    selected = context / "gateway/catalog/foundry-inventory-20261026.json"
    write(selected, accepted)
    for name in ("approved_catalog.py", "catalog-bindings.json"):
        write(context / "services/usage-ingestion" / name, (ROOT / "services/usage-ingestion" / name).read_bytes())
    spec = importlib.util.spec_from_file_location("eight_acceptance_packaged_builder", context / "services/usage-ingestion/approved_catalog.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    catalog = builder.build(context, profile="foundry-eight", inventory_path=selected)
    for path in ("gateway/catalog/ingestion-approved.json", "gateway/catalog/dev-models.json", "services/usage-ingestion/ingestion-approved.json"):
        write(context / path, catalog)
    builder.verify_packaged(context, profile="foundry-eight", inventory_path=selected)
    enabled = sorted(m["id"] for m in catalog["models"] if m["enabled"])
    require(len(enabled) == 21 and "Decision-1" not in enabled and "mistral-medium-3-5" not in enabled, "exact_enabled_membership")
    provenance = {"at": now(), "profile": "foundry-eight", "source_hashes": bound,
        "grandfather_foundry_source_sha256": sha((CATALOG / "foundry-inventory-20261026.json").read_bytes()),
        "grandfather_verified_at_preserved": old["verified_at"], "old_twelve_new_probes": 0,
        "old_twelve_endpoint_conversions": conversions, "external_bytes_and_timestamps_preserved": True,
        "external_new_probes": 0, "new_eight_actual_probes": results, "enabled_chat_aliases": enabled,
        "selected_deployment_count": 21, "runtime_builds": 0, "applies": 0, "catalog_database_writes": 0,
        "files": {p.relative_to(home).as_posix(): sha(p.read_bytes()) for p in context.rglob("*") if p.is_file()}}
    write(home / "accepted-provenance.json", provenance)
    return {"accepted_inventory": selected.relative_to(ROOT).as_posix(),
            "accepted_catalog": (context / "gateway/catalog/ingestion-approved.json").relative_to(ROOT).as_posix(),
            "provenance": (home / "accepted-provenance.json").relative_to(ROOT).as_posix(), "enabled_chat_count": 21}


def run():
    require(not HOME.exists(), "acceptance_scope_consumed_reconcile_original_NO_REPLAY")
    HOME.mkdir(exist_ok=False)
    write(HOME / "run-intent.json", {"at": now(), "pid": os.getpid(), "aliases": list(ALIASES),
        "total_max_requests": 8, "per_alias_max_requests": 1, "output_cap": 128,
        "retry": 0, "fallback": False, "resume_permitted": False, "source_sha256": sha(Path(__file__).read_bytes())})
    client, key = None, None
    try:
        write(HOME / "worker-gate.json", applied.reader.worker_gate())
        bound = inputs()
        write(HOME / "source-binding.json", bound)
        client = Client()
        binding = policy_binding(client.arm(APIM + "/apis/aiflux-dev-unified/policies/policy?format=xml"))
        write(HOME / "policy-binding.json", binding)
        subscription = client.arm(APIM + "/subscriptions/" + SUBSCRIBER)
        require(subscription["name"] == SUBSCRIBER and subscription["properties"]["state"] == "active"
                and subscription["properties"]["scope"].endswith("/products/aiflux"), "existing_active_product_subscription_required")
        write(HOME / "subscription-metadata.json", {"at": now(), "id": subscription["id"],
            "state": "active", "scope": subscription["properties"]["scope"], "new_gate_added": False})
        for rid in (ACCOUNT, PROJECT):
            parent = client.arm(rid)
            require(parent["id"].lower() == rid.lower() and parent["properties"]["provisioningState"] == "Succeeded", "exact_foundry_parent")
        connections = client.arm(PROJECT + "/connections")
        require(connections["value"] == [], "no_connected_account_routes")
        old = load(CATALOG / "foundry-inventory-20261026.json")
        candidate = load(CATALOG / "foundry-eight-candidate-routes.json")
        live = client.arm(ACCOUNT + "/deployments")
        additions, scope = metadata_guard(old, live, candidate)
        write(HOME / "metadata.json", {"at": now(), "scope": scope, "additions": additions,
            "whole_deployment_collection_sha256": sha(live), "old_deployments_match": True})
        backends = client.arm(APIM + "/backends")
        for address, (name, endpoint) in applied.reader.BACKENDS.items():
            row = next(r for r in backends["value"] if r["name"] == name)
            require(row["properties"]["url"] == endpoint and not row["properties"].get("credentials"), "new_backend_binding")
        require(inputs() == bound, "source_binding_drift_before_send")
        write(HOME / "pre-send-worker-gate.json", applied.reader.worker_gate())
        # The ONLY credential read is the legitimate existing product auth path.
        secret = client.arm(APIM + "/subscriptions/" + SUBSCRIBER + "/listSecrets", secret=True)
        key = secret.pop("primaryKey")
        secret.clear()
        require(isinstance(key, str) and bool(key), "existing_subscription_key_unavailable")
        results = probes(client, key, HOME, binding)
        key = None
        after = policy_binding(client.arm(APIM + "/apis/aiflux-dev-unified/policies/policy?format=xml"))
        require(after["policy_sha256"] == binding["policy_sha256"] and inputs() == bound, "policy_or_source_changed_during_acceptance")
        write(HOME / "post-probe-policy-binding.json", after)
        artifacts = promote(HOME, old, additions, results, candidate, bound)
        result = {"at": now(), "passed": True, "inference_transport_invocations": 8,
                  "successful_aliases": list(ALIASES), "retries": 0, "fallbacks": 0, **artifacts}
        write(HOME / "result.json", result)
        print(json.dumps(result), flush=True)
        return 0
    except Exception as error:
        intents = sorted((HOME / "probes").glob("*-intent.json"))
        passed = sorted((HOME / "probes").glob("*-passed.json"))
        result = {"at": now(), "passed": False, "consumed_alias_count": len(intents),
            "successful_aliases": [load(p)["alias"] for p in passed], "reason": str(error) if isinstance(error, AcceptanceError) else "sensitive_details_suppressed",
            "error_type": type(error).__name__, "retry_permitted": False, "acceptance_generated": False}
        write(HOME / "failure.json", result)
        print(json.dumps(result), flush=True)
        return 2
    finally:
        key = None
        if client is not None:
            client.close()


if __name__ == "__main__":
    require(sys.argv[1:] == ["run"], "only_explicit_run_action")
    raise SystemExit(run())