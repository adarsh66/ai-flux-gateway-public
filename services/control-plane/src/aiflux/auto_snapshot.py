"""Shared, source-bound platform defaults. No tenant membership, DB writes or leases.

APIM consumes these same immutable inputs during an ordinary platform release.
An optional desired DB row is NOT a published gateway override.
"""
import hashlib
import json
from importlib.resources import files

from fastapi import HTTPException

from aiflux.config import Settings
from aiflux import completion_limits
from aiflux.display_pricing import accepted_catalog_price, manifest
from aiflux.external_inventory import AcceptedInventory

ENDPOINT = "https://poc-ids-token-ex-foundry.services.ai.azure.com/providers/microsoft/v1/systemone"
GATEWAY_PRINCIPAL = "bcf69911-f34e-4f33-acd8-a36f164db811"
GATEWAY_CLIENT = "5792b72e-1605-4dce-a594-4c430a5af619"


def defaults(settings: Settings) -> dict:
    raw = files("aiflux").joinpath("pricing/auto-routing-defaults.json").read_bytes()
    spec = json.loads(raw)
    # Auto owns a frozen six-option price snapshot, not the expanding display
    # rate-card manifest. Preserve its bytes/version as explicit models grow.
    prices = manifest(False)
    frozen_path = settings.auto_routing_snapshot_inventory_path or settings.foundry_inventory_path
    if (frozen_path is None or spec["schema"] != 1 or spec["catalog_sha256"] != hashlib.sha256(
            frozen_path.read_bytes()).hexdigest()
            or spec["pricing_sha256"] != prices["sha256"]):
        raise ValueError("Platform Auto snapshot inputs changed; release a validated successor")
    try:
        current = AcceptedInventory.load(settings)
        accepted = current.accepted_aliases(settings)
        inv = AcceptedInventory.load(settings.model_copy(update={"foundry_inventory_path": frozen_path}))
    except HTTPException as exc:
        raise ValueError("Invalid platform inventory") from exc
    candidates = []
    limits = completion_limits.load(settings, accepted)
    # Stable pool/capability admission remains bound to the original release.
    # With shared pricing enabled, defaults use the SAME catalog rate source,
    # never an independently editable or newer frozen Auto price manifest.
    shared_scopes = None
    if settings.auto_pricing_sync_enabled:
        from aiflux import rate_card
        shared_scopes = dict(rate_card.accepted_scopes(settings, inventory=current))
    for alias in spec["candidates"]:
        route = inv.foundry.route(alias)
        live_route = current.foundry.route(alias)
        binding = ("backend_model", "model_name", "model_version", "api_format", "capabilities",
                   "max_completion_tokens", "upstream_token_parameter", "reasoning_effort")
        if (route is None or live_route is None or alias not in accepted or "chat" not in route.capabilities
                or any(getattr(route, key) != getattr(live_route, key) for key in binding)
                or inv.provider(alias) != current.provider(alias)
                or (frozen_path != settings.foundry_inventory_path and
                    (route.endpoint_url, live_route.endpoint_url) != (
                        "https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1",
                        "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"))):
            raise ValueError("Unaccepted platform Auto candidate")
        price = accepted_catalog_price(current, alias, live_route.backend_model, live_route.endpoint_url)
        if price is not None:
            rates = [r for r in prices["rates"] if r["model"] == alias
                     and r["provider"] == inv.provider(alias) and r["model_version"] == route.model_version]
            if len(rates) != 1:
                raise ValueError("Invalid frozen Auto price binding")
            rate = rates[0]
            price = None if rate["status"] == "unknown" else {
                **rate, "revision": prices["revision"], "manifest_sha256": prices["sha256"],
                "currency": "USD", "unit": prices["unit"], "checked_at": prices["checked_at"],
                "source_url": prices["sources"][rate["source"]], "basis": prices["basis"],
                "assumptions": prices["assumptions"], "applicable_from": prices["applicable_from"],
            }
        if shared_scopes is not None:
            price = rate_card.display_price(0, [], shared_scopes.get(alias))
        candidates.append({"id": alias, "provider": inv.provider(alias),
            "model_name": route.model_name, "model_version": route.model_version,
            "capabilities": sorted(route.capabilities), "max_completion_tokens": (
                min(1024, route.max_completion_tokens) if limits is None else
                completion_limits.effective(settings, alias, route.max_completion_tokens, limits)),
            "context_window": None, "capability_source": "accepted-foundry-route-inventory",
            "capability_checked_at": inv.verified_at.isoformat(), "price": price,
            "price_status": "unknown" if price is None else (
                "published" if price["status"] == "public_list" else "provisional"),
            "operator_preference": "general text option; no benchmark quality ranking",
            "descriptor_version": spec["descriptor_version"]})
    profiles = {}
    for name, rubric in spec["profiles"].items():
        pool = [c["id"] for c in candidates if name != "cost" or c["price"] is not None]
        suitability_fallback = shared_scopes is not None and name == "cost" and len(pool) < 2
        if suitability_fallback:
            pool = [c["id"] for c in candidates]
        if not 2 <= len(pool) <= 10 or (shared_scopes is None and spec["fallback_model"] not in pool):
            raise ValueError("Invalid platform default pool")
        if suitability_fallback:
            rubric = "Comparable pricing is unavailable. Select the option most suitable for this text task; do not invent prices or claim a cheapest option."
        profiles[name] = {"candidate_models": pool, "fallback_model": spec["fallback_model"],
                          "instructions": rubric + spec["instructions_suffix"]}
    return {"version": completion_limits.snapshot_version(hashlib.sha256(raw).hexdigest(), limits), "profiles": profiles,
            "candidates": candidates, "descriptor_version": spec["descriptor_version"]}


def publication(settings: Settings, snapshot: dict) -> dict | None:
    """Immutable release readback receipt, not a feature flag or tenant approval.

    Schema 1 requires actual MI/response proof. Schema 2 explicitly advertises
    bounded direct production validation with runtime proof STILL PENDING; it
    additionally requires a separate default-off setting. Both require actual
    policy readback and independent review. No GET creates either. Hashes
    bind that reviewed evidence; parsing a fixture does not establish live proof.
    No expiry is used: a new release supersedes the exact policy/snapshot binding.
    """
    inline = settings.auto_routing_publication_json
    path = settings.auto_routing_publication_path
    # Exactly one operator-controlled transport. Never silently prefer stale
    # file evidence over new settings (or vice versa). Receipt is not a secret.
    if (inline is None) == (path is None):
        return None
    try:
        raw = inline if inline is not None else path.read_text(encoding="utf-8")
        if len(raw.encode("utf-8")) > 8192:
            return None
        def unique_keys(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("Duplicate publication key")
                value[key] = item
            return value
        receipt = json.loads(raw, object_pairs_hook=unique_keys)
        if not isinstance(receipt, dict):
            return None
        import re
        hashes = ("policy_sha256", "authorization_evidence_sha256")
        if (type(receipt.get("schema")) is not int or receipt.get("schema") not in (1, 2)
            or receipt.get("snapshot_version") != snapshot["version"]
                or receipt.get("policy_sha256") != settings.auto_routing_published_policy_sha256
                or receipt.get("endpoint") != ENDPOINT or receipt.get("deployment") != "Decision-1"
                or receipt.get("gateway_principal") != GATEWAY_PRINCIPAL
                or receipt.get("gateway_client") != GATEWAY_CLIENT
                or receipt.get("response_contract") != "systemone-choice-probabilities-v1"
                or any(not isinstance(receipt.get(k), str)
                       or not re.fullmatch(r"[0-9a-f]{64}", receipt[k]) for k in hashes)):
            return None
        if receipt["schema"] == 1:
            evidence = receipt.get("gateway_runtime_evidence_sha256")
            if (receipt.get("runtime_verified") is not True or not isinstance(evidence, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", evidence)):
                return None
        else:
            if (not settings.auto_routing_direct_validation_enabled
                    or receipt.get("validation_mode") != "bounded-production-direct-v1"
                    or receipt.get("runtime_verified") is not False
                    or receipt.get("gateway_runtime_evidence_sha256") is not None
                    or receipt.get("budget") != {"auto_attempts": 2, "scoring_calls": 2,
                        "completion_calls": 2, "retries": 0, "fallback": False}
                    or any(type(receipt.get("budget", {}).get(k)) is not int
                           for k in ("auto_attempts", "scoring_calls", "completion_calls", "retries"))
                    or receipt["budget"]["fallback"] is not False
                    or receipt.get("stop_on_explicit_regression") is not True):
                return None
            for key in ("independent_review_sha256", "policy_readback_sha256", "rollback_sha256"):
                if not isinstance(receipt.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", receipt[key]):
                    return None
        # This version implements published platform defaults only. Desired DB
        # overrides are deliberately excluded until a reviewed successor release.
        return receipt
    except (OSError, ValueError, TypeError):
        return None