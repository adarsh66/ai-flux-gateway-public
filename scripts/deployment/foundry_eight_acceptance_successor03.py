"""Three remaining, globally consumed probes; exact ARM canonical identity only.

Historical controllers and receipts are immutable. Terra is resolved from the
exact correlated LLM metadata, NOT a reconstruction of its lost response model.
Only this new controller has the corrected sanitizer and identity validator.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
from types import FunctionType
from uuid import uuid4

from scripts.deployment import foundry_eight_acceptance_successor02 as previous
from aiflux.display_pricing import catalog_price, manifest

a = previous.a
HOME = a.rt.HOME / "foundry-eight-acceptance-20261031-successor03"
LEDGER = a.rt.HOME / "foundry-eight-alias-global-ledger-20261031"
TELEMETRY = a.rt.HOME / "terra-existing-probe-readonly-20261031"
REMAINING = a.ALIASES[5:]


def historical_hashes():
    folders = list(a.rt.HOME.glob("foundry-eight-acceptance*")) + [TELEMETRY]
    return {p.relative_to(a.ROOT).as_posix(): a.sha(p.read_bytes())
            for folder in folders if folder != HOME for p in sorted(folder.rglob("*")) if p.is_file()}


def consumed_intents(base):
    result = {}
    for folder in sorted(base.glob("foundry-eight-acceptance*")):
        for path in sorted((folder / "probes").glob("*-intent.json")):
            row = a.load(path)
            alias = row["alias"]
            a.require(alias in a.ALIASES and alias not in result, "duplicate_or_unknown_consumed_alias_STOP")
            a.require(row["consumed_before_send"] and row["max_requests"] == 1
                      and row["retries"] == 0 and not row["fallback"], "prior_one_send_contract")
            result[alias] = {"intent_path": path.relative_to(base).as_posix(),
                             "intent_sha256": a.sha(path.read_bytes()), "client_request_id": row["client_request_id"]}
    return result


def seed_ledger(base, ledger):
    consumed = consumed_intents(base)
    a.require(set(consumed) == set(a.ALIASES[:5]), "exact_first_five_already_consumed_required")
    ledger.mkdir(exist_ok=False)
    for alias in a.ALIASES[:5]:
        a.write(ledger / (alias + ".json"), {"alias": alias, "consumed": True,
                "historical": True, **consumed[alias]})
    return consumed


def claim(base, ledger, alias, request_id):
    a.require(alias in REMAINING, "only_remaining_three_may_send")
    consumed = consumed_intents(base)
    a.require(alias not in consumed, "alias_already_consumed_no_replay")
    a.require(set(a.ALIASES[:5]) <= consumed.keys(), "historical_calls_must_remain_visible")
    a.require(all((ledger / (name + ".json")).is_file() for name in consumed), "global_ledger_missing_consumption")
    # Exclusive durable claim precedes intent and transport. UNKNOWN is consumed.
    return a.write(ledger / (alias + ".json"), {"at": a.now(), "alias": alias,
        "consumed": True, "historical": False, "client_request_id": request_id,
        "retry_permitted": False, "max_requests": 1})


def summary(alias, status, headers, raw):
    record = a.summary(alias, status, headers, raw)
    record["canonical_alias"] = alias
    if status == 200:
        try:
            record["response_model"] = a.clean_id(json.loads(raw).get("model"))
        except (ValueError, TypeError, AttributeError):
            record["parse_failed"] = True
    record["identity_source"] = "sanitized_raw_response_model"
    return record


def validate_probe(record, deployments):
    alias = record["alias"]
    rows = [d for d in deployments if d["name"] == alias]
    a.require(alias in a.ALIASES and len(rows) == 1, "unique_accepted_ARM_identity_required")
    d = rows[0]
    a.require(d["id"] == a.ACCOUNT + "/deployments/" + alias
              and d["provisioning_state"] == "Succeeded" and d["chat_completion"]
              and d["capacity"] > 0 and a.clean_id(d["model_name"])
              and a.clean_id(d["model_version"]), "exact_accepted_ARM_binding_required")
    identity = record.get("response_model")
    if record.get("identity_source") == "exact_correlated_LLM_metadata":
        a.require(alias == "gpt-6.1-terra" and identity is None
                  and record.get("raw_response_model_captured") is False, "metadata_not_raw_response")
        identity = record.get("identity_model")
        a.require(record.get("identity_resolution_verified") is True, "verified_telemetry_resolution_required")
    allowed = {alias}
    if d["model_format"] == "OpenAI":
        allowed.add(d["model_name"] + "-" + d["model_version"])
    a.require(identity in allowed, "exact_alias_or_OpenAI_ARM_name_version_only")
    a.require(record.get("canonical_alias", alias) == alias, "canonical_alias_mismatch")
    # Reuse every established content, usage, UUID and stop-condition guard.
    # Only the internal literal-alias comparison is replaced after exact proof.
    checked = {**record, "response_model": alias}
    a.validate_probe(checked)
    a.require(a.clean_id(record.get("response_id")), "safe_actual_response_id_required")


def bind_receipt(home, index, alias):
    stem = home / "probes" / f"{index:02d}-{alias}"
    intent_path, response_path = Path(str(stem) + "-intent.json"), Path(str(stem) + "-response.json")
    intent, row = a.load(intent_path), a.load(response_path)
    a.require(row["alias"] == intent["alias"] == alias
              and row["intent_sha256"] == a.sha(intent_path.read_bytes())
              and row["client_request_id"] == intent["client_request_id"]
              and row["policy_sha256"] == intent["policy_sha256"]
              and row["transport_invocations"] == 1, "actual_receipt_intent_binding")
    return row


def resolve_terra(row, metadata, evidence):
    llm, gateway = evidence["llm_row"], evidence["gateway_row"]
    a.require(evidence["llm_row_count_returned"] == evidence["gateway_row_count_returned"] == 1
              and evidence["original_receipt"] == (previous.HOME / "probes/05-gpt-6.1-terra-response.json").relative_to(a.ROOT).as_posix()
              and evidence["original_response_sha256"] == row["response_sha256"]
              and evidence["ids"]["response_id"] == llm["RequestId"] == row["response_id"]
              and evidence["ids"]["correlation_id"] == llm["CorrelationId"] == gateway["CorrelationId"] == row["correlation_id"]
              and llm["DeploymentName"] == row["alias"] == "gpt-6.1-terra"
              and gateway["ResponseCode"] == gateway["BackendResponseCode"] == row["status"] == 200
              and llm["TimeGenerated"] == gateway["TimeGenerated"]
              and not evidence["conclusions"]["raw_response_body_recovered"], "exact_correlated_terra_metadata_required")
    for key, field in (("prompt_tokens", "PromptTokens"), ("completion_tokens", "CompletionTokens"), ("total_tokens", "TotalTokens")):
        a.require(type(llm[field]) is int and llm[field] == row["usage"][key], "exact_correlated_usage_required")
    resolved = {**deepcopy(row), "canonical_alias": row["alias"], "identity_model": llm["ModelName"],
        "identity_source": "exact_correlated_LLM_metadata", "raw_response_model_captured": False,
        "identity_resolution_verified": True, "evidence_sha256": a.sha((TELEMETRY / "evidence.json").read_bytes()),
        "resolution": "Internal literal-alias validator corrected to exact accepted OpenAI ARM name/version; original failure and null response_model preserved"}
    validate_probe(resolved, metadata)
    return resolved


def predecessors():
    a.require(previous.inputs() == a.load(previous.HOME / "source-binding.json"), "all_original_bound_bytes_exact")
    integrity = a.load(TELEMETRY / "final-integrity.json")
    for item in integrity["files_sha256"]:
        a.require(a.sha((TELEMETRY / item["name"]).read_bytes()) == item["sha256"], "telemetry_integrity_changed")
    a.require(a.sha((previous.HOME / "probes/05-gpt-6.1-terra-response.json").read_bytes())
              == integrity["original_receipt_sha256"], "terra_original_receipt_changed")
    metadata = a.load(previous.HOME / "metadata.json")["additions"]
    results = []
    for i, alias in enumerate(a.ALIASES[:4], 1):
        row = bind_receipt(previous.HOME, i, alias)
        passed = a.load(previous.HOME / "probes" / f"{i:02d}-{alias}-passed.json")
        a.require(all(passed.get(k) == v for k, v in row.items()), "original_passed_response_binding")
        validate_probe(passed, metadata)
        results.append(passed)
    results.append(resolve_terra(bind_receipt(previous.HOME, 5, a.ALIASES[4]), metadata,
                                 a.load(TELEMETRY / "evidence.json")))
    binding = a.policy_binding({"properties": {"value": (a.applied.EVIDENCE / "postapply-policy.xml").read_bytes().decode("utf-8")}})
    a.require(all(r["policy_sha256"] == binding["policy_sha256"] for r in results), "prior_actual_policy_binding")
    fast = results[2]["fast_speed_proof"]
    a.require(fast["policy_sha256"] == binding["policy_sha256"]
              and fast["normalizer_sha256"] == binding["normalizer_sha256"]
              and fast["correlation_id"] == results[2]["correlation_id"]
              and fast["speed"] == "fast" and not fast["direct_native_trace_retained"], "actual_fast_policy_guard_proof")
    return results, metadata, binding


def probes(client, key, home, ledger, deployments, binding):
    results = []
    for i, alias in enumerate(REMAINING, 6):
        request_id = str(uuid4())
        claim_sha = claim(a.rt.HOME, ledger, alias, request_id)
        stem = home / "probes" / f"{i:02d}-{alias}"
        intent = {"at": a.now(), "pid": os.getpid(), "alias": alias, "client_request_id": request_id,
            "policy_sha256": binding["policy_sha256"], "max_completion_tokens": 128, "max_requests": 1,
            "retries": 0, "fallback": False, "consumed_before_send": True, "global_claim_sha256": claim_sha}
        intent_sha = a.write(str(stem) + "-intent.json", intent)
        started = time.monotonic()
        try:
            row = summary(alias, *client.send(alias, key, request_id))
            row.update(at_utc=intent["at"], received_at=a.now(), client_request_id=request_id,
                intent_sha256=intent_sha, elapsed_seconds=round(time.monotonic() - started, 3),
                policy_sha256=binding["policy_sha256"], transport_invocations=1)
            a.write(str(stem) + "-response.json", row)
            validate_probe(row, deployments)
            a.write(str(stem) + "-passed.json", row)
            results.append(row)
            print(json.dumps({"alias": alias, "passed": True, "response_model": row["response_model"], "usage": row["usage"]}), flush=True)
        except Exception as error:
            a.write(str(stem) + "-failure.json", {"at": a.now(), "alias": alias, "request_consumed": True,
                "retry_permitted": False, "error_type": type(error).__name__,
                "reason": str(error) if isinstance(error, a.AcceptanceError) else "sensitive_details_suppressed"})
            raise a.AcceptanceError("consumed_probe_failed_STOP:" + alias) from None
    return results


def promote(home, old, additions, results, candidate, bound):
    a.require(len({r["correlation_id"] for r in results}) == len({r["response_id"] for r in results}) == 8,
              "eight_distinct_actual_response_and_correlation_ids")
    for row in results:
        validate_probe(row, additions)
    scoped = {**a.promote.__globals__, "validate_probe": lambda r: validate_probe(r, additions)}
    artifacts = FunctionType(a.promote.__code__, scoped)(home, old, additions, results, candidate, bound)
    rates = manifest()
    loaded = []
    for d in additions:
        rate = catalog_price(d["name"], d["model_format"], "eastus")
        a.require(rate is not None and rate["model_version"] == d["model_version"], "all_eight_new_rates_load")
        loaded.append(rate)
    a.write(home / "rates-proof.json", {"at": a.now(), "manifest_sha256": rates["sha256"],
        "source_sha256": rates["source_sha256"], "rates": loaded})
    return artifacts


def run():
    a.require(not HOME.exists() and not LEDGER.exists(), "successor_or_global_ledger_consumed_NO_REPLAY")
    HOME.mkdir(exist_ok=False)
    a.write(HOME / "run-intent.json", {"at": a.now(), "pid": os.getpid(), "remaining_aliases": list(REMAINING),
        "prior_consumed": list(a.ALIASES[:5]), "max_new_calls": 3, "retry": 0, "fallback": False,
        "source_sha256": a.sha(Path(__file__).read_bytes())})
    client, key = None, None
    try:
        a.write(HOME / "worker-gate.json", a.applied.reader.worker_gate())
        results, prior_metadata, prior_binding = predecessors()
        bound = {**a.inputs(), **historical_hashes(),
            Path(__file__).relative_to(a.ROOT).as_posix(): a.sha(Path(__file__).read_bytes()),
            "tests/unit/test_foundry_eight_acceptance_successor03.py": a.sha((a.ROOT / "tests/unit/test_foundry_eight_acceptance_successor03.py").read_bytes()),
            "services/control-plane/src/aiflux/display_pricing.py": a.sha((a.ROOT / "services/control-plane/src/aiflux/display_pricing.py").read_bytes()),
            "services/control-plane/src/aiflux/pricing/rates-foundry-eight-20261030.json": a.sha((a.ROOT / "services/control-plane/src/aiflux/pricing/rates-foundry-eight-20261030.json").read_bytes())}
        a.write(HOME / "source-binding.json", bound)
        seed_ledger(a.rt.HOME, LEDGER)
        a.write(HOME / "terra-identity-resolution.json", results[4])
        client = previous.JSONClient()
        binding = a.policy_binding(client.arm(a.APIM + "/apis/aiflux-dev-unified/policies/policy?format=xml"))
        a.require(binding["policy_sha256"] == prior_binding["policy_sha256"], "same_actual_policy_for_all_eight")
        a.write(HOME / "policy-binding.json", binding)
        old, candidate = a.load(a.CATALOG / "foundry-inventory-20261026.json"), a.load(a.CATALOG / "foundry-eight-candidate-routes.json")
        additions, scope = a.metadata_guard(old, client.arm(a.ACCOUNT + "/deployments"), candidate)
        a.require(additions == prior_metadata, "accepted_ARM_model_metadata_unchanged")
        a.write(HOME / "metadata.json", {"at": a.now(), "additions": additions, "scope": scope})
        subscription = client.arm(a.APIM + "/subscriptions/" + a.SUBSCRIBER)
        a.require(subscription["name"] == a.SUBSCRIBER and subscription["properties"]["state"] == "active"
                  and subscription["properties"]["scope"].endswith("/products/aiflux"), "existing_product_auth_only")
        for rid in (a.ACCOUNT, a.PROJECT):
            parent = client.arm(rid)
            a.require(parent["id"].lower() == rid.lower() and parent["properties"]["provisioningState"] == "Succeeded", "exact_parent")
        a.require(client.arm(a.PROJECT + "/connections")["value"] == [], "no_connected_routes")
        backends = client.arm(a.APIM + "/backends")
        for _, (name, endpoint) in a.applied.reader.BACKENDS.items():
            row = next(r for r in backends["value"] if r["name"] == name)
            a.require(row["properties"]["url"] == endpoint and not row["properties"].get("credentials"), "backend_binding")
        a.require(all(a.sha((a.ROOT / p).read_bytes()) == h for p, h in bound.items()), "pre_send_source_drift")
        a.write(HOME / "pre-send-worker-gate.json", a.applied.reader.worker_gate())
        secret = client.arm(a.APIM + "/subscriptions/" + a.SUBSCRIBER + "/listSecrets", secret=True)
        key = secret.pop("primaryKey")
        secret.clear()
        a.require(isinstance(key, str) and bool(key), "existing_key_required")
        results.extend(probes(client, key, HOME, LEDGER, additions, binding))
        key = None
        after = a.policy_binding(client.arm(a.APIM + "/apis/aiflux-dev-unified/policies/policy?format=xml"))
        a.require(after["policy_sha256"] == binding["policy_sha256"], "post_probe_policy_drift")
        a.write(HOME / "post-probe-policy-binding.json", after)
        a.require(all(a.sha((a.ROOT / p).read_bytes()) == h for p, h in bound.items()), "post_probe_source_drift")
        a.require(set(consumed_intents(a.rt.HOME)) == set(a.ALIASES)
                  and {p.stem for p in LEDGER.glob("*.json")} == set(a.ALIASES), "exact_global_eight_consumed")
        artifacts = promote(HOME, old, additions, results, candidate, bound)
        result = {"at": a.now(), "passed": True, "successful_aliases": list(a.ALIASES), "actual_total_calls": 8,
            "new_calls": 3, "repeated_calls": 0, "usage": {r["alias"]: r["usage"] for r in results},
            "proofs": results, "historical_bytes_unchanged": True, "runtime_publish": False,
            "builds": 0, "database_mutations": 0, "APIM_mutations": 0, **artifacts}
        a.write(HOME / "result.json", result)
        print(json.dumps({k: v for k, v in result.items() if k != "proofs"}), flush=True)
        return 0
    except Exception as error:
        result = {"at": a.now(), "passed": False, "error_type": type(error).__name__,
            "reason": str(error) if isinstance(error, a.AcceptanceError) else "sensitive_details_suppressed",
            "consumed_aliases": sorted(p.stem for p in LEDGER.glob("*.json")), "retry_permitted": False}
        a.write(HOME / "failure.json", result)
        print(json.dumps(result), flush=True)
        return 2
    finally:
        key = None
        if client is not None:
            client.close()


if __name__ == "__main__":
    a.require(sys.argv[1:] == ["run"], "explicit_run_only")
    raise SystemExit(run())