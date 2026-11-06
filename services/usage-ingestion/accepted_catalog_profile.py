"""Portable OFFLINE proof-required profile for this exact eight-response release.

No inference/client/credentials imports. The historical builder stays byte-exact.
Anchors identify actual retained evidence, not synthetic gateway_validated flags.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import UUID

PROFILE = "foundry-eight-accepted"
INTEGRITY_SHA256 = "29a08c4f0435f227078c62c18310e74f9c9c5d8b4a4fd58fd148eef1c3de702c"
MISTRAL_EVIDENCE_SHA256 = "026143c5f3d9ced7773b4a88e706fc28e9e281a35a6ff68d07cc1ad5c305e985"
MISTRAL_RAW_SHA256 = "73d5e006a344f1fa72aa569f5043ff4495b04d79054fec7a0f7c1a853d116d6f"
S03 = ".deployment/foundry-eight-acceptance-20261031-successor03/"
S02 = ".deployment/foundry-eight-acceptance-20261031-successor02/"
TERRA = ".deployment/terra-existing-probe-readonly-20261031/"
MISTRAL = ".deployment/mistral-existing-probe-resolution-20261031/"
LEDGER = ".deployment/foundry-eight-alias-global-ledger-20261031/"
ALIASES = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5-fast", "claude-haiku-5-5",
           "gpt-6.1-terra", "gpt-6-luna", "claude-opus-4-8", "Mistral-Large-3")


def require(ok, label):
    if not ok:
        raise ValueError(label)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def legacy_builder(root):
    path = root / "services/usage-ingestion/approved_catalog.py"
    spec = importlib.util.spec_from_file_location("accepted_profile_historical_builder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_identity(row, deployment, correlated=None):
    """No global case folding; only this EXACT Mistral pair with exact log proof."""
    alias = row["alias"]
    require(alias in ALIASES and row.get("canonical_alias", alias) == alias, "exact canonical alias")
    require(deployment["name"] == alias and deployment["model_name"] == alias
            and deployment["id"].endswith("/deployments/" + alias)
            and deployment["provisioning_state"] == "Succeeded" and deployment["capacity"] > 0
            and deployment["chat_completion"], "accepted ARM deployment binding")
    identity = row.get("response_model")
    if alias == "gpt-6.1-terra":
        require(identity is None and correlated is not None, "Terra original null preserved")
        identity = correlated["llm_row"]["ModelName"]
    allowed = {alias}
    if deployment["model_format"] == "OpenAI":
        allowed.add(deployment["model_name"] + "-" + deployment["model_version"])
    if alias == "Mistral-Large-3":
        require(deployment["model_format"] == "Mistral AI" and deployment["model_version"] == "1"
                and correlated is not None, "Mistral exact provider and correlated proof")
        allowed.add("mistral-large-3")
    require(identity in allowed, "exact identity mapping only")
    if correlated is not None:
        llm, gateway = correlated["llm_row"], correlated["gateway_row"]
        require(correlated["llm_row_count_returned"] == correlated["gateway_row_count_returned"] == 1
                and correlated["original_response_sha256"] == row["response_sha256"]
                and llm["RequestId"] == row["response_id"]
                and llm["DeploymentName"] == alias and llm["ModelName"] == identity
                and llm["CorrelationId"] == gateway["CorrelationId"] == row["correlation_id"]
                and llm["TimeGenerated"] == gateway["TimeGenerated"]
                and gateway["ResponseCode"] == gateway["BackendResponseCode"] == row["status"] == 200,
                "exact correlated deployment/model/response proof")
        for key, field in (("prompt_tokens", "PromptTokens"), ("completion_tokens", "CompletionTokens"),
                           ("total_tokens", "TotalTokens")):
            require(type(llm[field]) is int and llm[field] == row["usage"][key], "exact correlated usage")
    require(row["status"] == 200 and row["assistant_nonempty"] is True and row["finish_reason"] == "stop"
            and not row.get("usage_invalid") and not row.get("parse_failed")
            and isinstance(row["response_id"], str) and bool(row["response_id"]), "actual successful response")
    UUID(row["correlation_id"])
    usage = row["usage"]
    require(type(usage["prompt_tokens"]) is int and usage["prompt_tokens"] > 0
            and type(usage["completion_tokens"]) is int and 1 <= usage["completion_tokens"] <= 128
            and type(usage["total_tokens"]) is int
            and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"], "actual measured usage")
    require(all(v is None or type(v) is int and 0 <= v <= usage["prompt_tokens"]
                for v in (usage.get("cached_input_tokens"), usage.get("cache_write_tokens"))), "cache subsets")


def validate_proof(root, selected):
    """Re-read original hash-anchored receipts, not user-editable success booleans."""
    proof_root = root / "gateway/catalog/acceptance-evidence"

    def raw(path):
        require(not Path(path).is_absolute() and ".." not in Path(path).parts, "proof path escape")
        return (proof_root / path).read_bytes()

    def read(path):
        return json.loads(raw(path))

    require(digest(raw(S03 + "final-local-integrity.json")) == INTEGRITY_SHA256, "genuine final integrity required")
    final = read(S03 + "final-local-integrity.json")
    anchors = dict(final["receipt_hashes"])
    require(digest(raw(S03 + "source-binding.json")) == anchors[S03 + "source-binding.json"], "bound source manifest")
    anchors.update(read(S03 + "source-binding.json"))

    def anchored(path):
        require(digest(raw(path)) == anchors[path], "historical evidence changed:" + path)
        return read(path)

    require(final["remaining_call_budget"] == 0 and final["total_consumed_calls"] == 8
            and not final["retry_permitted"] and final["accepted_success_count"] == 7,
            "retain original failure and consumed budget")
    deployments = anchored(S03 + "metadata.json")["additions"]
    require([d["name"] for d in deployments] == list(ALIASES), "exact eight additions no ninth")
    rows = []
    for i, alias in enumerate(ALIASES, 1):
        stem = (S02 if i <= 5 else S03) + f"probes/{i:02d}-{alias}"
        row, intent = anchored(stem + "-response.json"), anchored(stem + "-intent.json")
        ledger = anchored(LEDGER + alias + ".json")
        require(row["alias"] == intent["alias"] == ledger["alias"] == alias
                and ledger["consumed"] is True and row["transport_invocations"] == 1
                and row["client_request_id"] == intent["client_request_id"] == ledger["client_request_id"]
                and row["intent_sha256"] == digest(raw(stem + "-intent.json"))
                and row["policy_sha256"] == intent["policy_sha256"]
                and intent["consumed_before_send"] is True and intent["max_requests"] == 1
                and intent["retries"] == 0 and intent["fallback"] is False, "original one-shot receipt/intent/ledger")
        evidence = None
        if i <= 4 or i in (6, 7):
            passed = anchored(stem + "-passed.json")
            require(all(passed.get(k) == v for k, v in row.items()), "original passed receipt binding")
            row = passed
        if alias == "gpt-6.1-terra":
            evidence = anchored(TERRA + "evidence.json")
        if alias == "Mistral-Large-3":
            require(digest(raw(MISTRAL + "evidence.json")) == MISTRAL_EVIDENCE_SHA256
                    and digest(raw(MISTRAL + "joined-response.json")) == MISTRAL_RAW_SHA256, "genuine Mistral observation")
            evidence = read(MISTRAL + "evidence.json")
            failure = anchored(stem + "-failure.json")
            require(failure["request_consumed"] and not failure["retry_permitted"]
                    and failure["reason"] == "exact_alias_or_OpenAI_ARM_name_version_only", "original failure retained")
        validate_identity(row, deployments[i - 1], evidence)
        rows.append(row)
    require(len({r["response_id"] for r in rows}) == len({r["correlation_id"] for r in rows}) == 8,
            "eight distinct genuine responses")
    policy = anchored(S03 + "policy-binding.json")
    fast = rows[2]["fast_speed_proof"]
    require(all(r["policy_sha256"] == policy["policy_sha256"] for r in rows)
            and fast["speed"] == "fast" and fast["policy_sha256"] == policy["policy_sha256"]
            and fast["normalizer_sha256"] == policy["normalizer_sha256"]
            and fast["correlation_id"] == rows[2]["correlation_id"]
            and not fast["direct_native_trace_retained"], "exact guard-based Claude fast proof")
    old = anchored("gateway/catalog/foundry-inventory-20261026.json")
    candidate = anchored("gateway/catalog/foundry-eight-candidate-routes.json")
    anchored("gateway/catalog/external-inventory.json")
    require((root / "gateway/catalog/external-inventory.json").read_bytes()
            == raw("gateway/catalog/external-inventory.json"), "external byte identity")
    # Execute the historically bound builder, never a permissive replacement.
    for path in ("services/usage-ingestion/approved_catalog.py", "services/usage-ingestion/catalog-bindings.json",
                 "gateway/catalog/foundry-eight-candidate-routes.json", "gateway/catalog/fireworks-candidate-routes.json",
                 "gateway/catalog/project-routes.json"):
        require(digest((root / path).read_bytes()) == anchors[path], "packaged historical builder/input drift")
    expected = deepcopy(old)
    for route in expected["routes"]:
        route["endpoint_url"] = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"
    expected["deployments"].extend(deployments)
    for deployment in deployments:
        alias = deployment["name"]
        expected["routes"].append({"alias": alias, "deployment_id": deployment["id"], "backend_model": alias,
            "model_name": deployment["model_name"], "model_version": deployment["model_version"],
            "endpoint_url": "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1",
            "api_format": "openai-chat-completions", "capabilities": ["chat"], "max_completion_tokens": 1024,
            "gateway_validated": True, "upstream_token_parameter": candidate["routes"][alias]["token_parameter"],
            "expires_at": None})
    require(json.loads(selected.read_bytes()) == expected, "selected inventory must derive exactly from genuine proof")
    return rows


def build(root, *, profile=PROFILE, inventory_path=None, proof_path=None, proof_sha256=None):
    if profile == 'foundry-successor22-accepted':
        spec = importlib.util.spec_from_file_location('explicit_successor22_catalog',
            root / 'services/usage-ingestion/successor22_catalog.py')
        successor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(successor)
        return successor.build(root, inventory_path=inventory_path, proof_path=proof_path, proof_sha256=proof_sha256)
    require(profile == PROFILE, "explicit proof-required profile")
    selected = inventory_path or root / "gateway/catalog/foundry-inventory-20261026.json"
    if not selected.is_absolute():
        selected = root / selected
    validate_proof(root, selected)
    return legacy_builder(root).build(root, profile="foundry-eight", inventory_path=selected)


def verify_packaged(root, *, profile=PROFILE, inventory_path=None, proof_path=None, proof_sha256=None):
    expected = build(root, profile=profile, inventory_path=inventory_path, proof_path=proof_path, proof_sha256=proof_sha256)
    for path in ("gateway/catalog/ingestion-approved.json", "gateway/catalog/dev-models.json",
                 "services/usage-ingestion/ingestion-approved.json"):
        require(json.loads((root / path).read_bytes()) == expected, "packaged catalog differs from genuine proof")
    if profile == PROFILE:
        legacy_builder(root).verify_packaged(root, profile="foundry-eight", inventory_path=inventory_path)
    else:
        require(json.loads((root / 'gateway/catalog/models.json').read_bytes()) == expected, 'effective API catalog path exact22')


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=(PROFILE,), required=True)
    args = parser.parse_args()
    verify_packaged(Path.cwd(), profile=args.profile)