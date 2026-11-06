"""OFFLINE promotion of eight consumed responses. No client, send or cloud call.

New contexts/receipts only. Historical timestamps, failures, sources and ledgers
are immutable. Identity policy is exactly the user's technical mapping, not a
change to the public capability contract or an authorization for a ninth send.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import sys

from scripts.deployment import foundry_eight_acceptance_successor03 as s
from scripts.deployment import foundry_eight_mistral_metadata_resolution as m

a = s.a
HOME = a.rt.HOME / "foundry-eight-offline-promotion-20261031"
PROFILE_SOURCE = a.ROOT / "services/usage-ingestion/accepted_catalog_profile.py"


def profile_module(path=PROFILE_SOURCE):
    spec = importlib.util.spec_from_file_location("proof_required_accepted_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def historical_hashes():
    folders = list(a.rt.HOME.glob("foundry-eight-acceptance*")) + [s.TELEMETRY, s.LEDGER, m.HOME, m.prior.HOME]
    return {p.relative_to(a.ROOT).as_posix(): a.sha(p.read_bytes())
            for folder in folders for p in sorted(folder.rglob("*")) if p.is_file()}


def existing():
    profile = profile_module()
    final = a.load(s.HOME / "final-local-integrity.json")
    a.require(a.sha((s.HOME / "final-local-integrity.json").read_bytes()) == profile.INTEGRITY_SHA256,
              "genuine_original_final_integrity_required")
    bound = a.load(s.HOME / "source-binding.json")
    a.require(all(a.sha((a.ROOT / p).read_bytes()) == h for p, h in bound.items()), "all_frozen_source_and_historical_bytes")
    a.require(all(a.sha((a.ROOT / p).read_bytes()) == h for p, h in final["receipt_hashes"].items()), "original_receipts_unchanged")
    integrity = a.load(m.HOME / "integrity.json")
    a.require(integrity["passed"] and integrity["queries_total"] == 2 and integrity["inference_sends"] == 0
              and all(a.sha((m.HOME / p).read_bytes()) == h for p, h in integrity["files"].items())
              and all(a.sha((a.ROOT / p).read_bytes()) == h for p, h in integrity["prior_failed_capture_files"].items()),
              "actual_metadata_capture_and_failed_capture_preserved")
    rows, deployments, policy = s.predecessors()
    for i, alias in enumerate(s.REMAINING, 6):
        row = s.bind_receipt(s.HOME, i, alias)
        if i < 8:
            s.validate_probe(row, deployments)
            a.require(row == a.load(s.HOME / "probes" / f"{i:02d}-{alias}-passed.json"), "passed_receipt_identity")
        rows.append(row)
    evidence = a.load(m.HOME / "evidence.json")
    m.prior.validate(rows[7], evidence)
    for row, deployment in zip(rows, deployments):
        correlated = evidence if row["alias"] == "Mistral-Large-3" else (
            a.load(s.TELEMETRY / "evidence.json") if row["alias"] == "gpt-6.1-terra" else None)
        profile.validate_identity(row, deployment, correlated)
    a.require(set(s.consumed_intents(a.rt.HOME)) == {p.stem for p in s.LEDGER.glob("*.json")} == set(a.ALIASES)
              and all(a.load(p)["consumed"] for p in s.LEDGER.glob("*.json"))
              and final["remaining_call_budget"] == 0, "global_budget_fully_consumed_zero_available")
    a.require(len({r["response_id"] for r in rows}) == len({r["correlation_id"] for r in rows}) == 8,
              "eight_distinct_actual_usage_proofs")
    return rows, deployments, policy


def public_source_files():
    """Curated source allowlist, never .deployment, credentials, output or venv."""
    roots = ("services/control-plane", "services/usage-ingestion", "packages/ui", "apps/admin-portal", "apps/customer-portal")
    suffixes = {".py", ".json", ".kql", ".ini", ".mako", ".ts", ".tsx", ".css", ".html", ".template"}
    skip_parts = {"node_modules", "__pycache__", ".venv", "dist", "build", ".pytest_cache", ".git", "aiflux_control_plane.egg-info"}
    paths = [a.ROOT / name for name in ("pyproject.toml", "package.json", "package-lock.json", "tsconfig.base.json")]
    for directory in roots:
        paths.extend(p for p in (a.ROOT / directory).rglob("*") if p.is_file()
                     and not skip_parts.intersection(p.parts) and not p.name.startswith(".env")
                     and (p.suffix in suffixes or p.name.endswith("Dockerfile")))
    paths += [a.ROOT / "gateway/policies/settings-unconfigured.xml"]
    return sorted(set(paths))


def package(home, rows, additions, policy):
    """Writes exclusively; also exercised offline in temporary directories."""
    profile = profile_module()
    context = home / "accepted-context"
    old_path = a.CATALOG / "foundry-inventory-20261026.json"
    old = a.load(old_path)
    candidate = a.load(a.CATALOG / "foundry-eight-candidate-routes.json")
    accepted = deepcopy(old)
    conversions = []
    for old_route, route in zip(old["routes"], accepted["routes"]):
        conversions.append({"alias": route["alias"], "old_endpoint_url": route["endpoint_url"], "new_endpoint_url": a.GATEWAY,
            "grandfather_route_sha256": a.sha(old_route), "original_inventory_sha256": a.sha(old_path.read_bytes()),
            "original_verified_at": old["verified_at"], "new_probe": False,
            "reason": "public endpoint metadata conversion only; original acceptance fields retained verbatim"})
        route["endpoint_url"] = a.GATEWAY
    accepted["deployments"].extend(additions)
    for deployment in additions:
        alias = deployment["name"]
        accepted["routes"].append({"alias": alias, "deployment_id": deployment["id"], "backend_model": alias,
            "model_name": deployment["model_name"], "model_version": deployment["model_version"],
            "endpoint_url": a.GATEWAY, "api_format": "openai-chat-completions", "capabilities": ["chat"],
            "max_completion_tokens": 1024, "gateway_validated": True,
            "upstream_token_parameter": candidate["routes"][alias]["token_parameter"], "expires_at": None})
    parsed = a.FoundryInventory.model_validate(accepted)
    a.require(len(parsed.routes) == 20 and len(parsed.deployments) == 21
              and all(parsed.route(r.alias) for r in parsed.routes), "actual_inventory_schema_and_route_validation")
    replacements = {"gateway/catalog/foundry-inventory-20261026.json", "gateway/catalog/ingestion-approved.json",
                    "gateway/catalog/dev-models.json", "services/usage-ingestion/ingestion-approved.json",
                    "services/control-plane/Dockerfile", "services/usage-ingestion/Dockerfile"}
    source_hashes = {}
    for path in public_source_files():
        relative = path.relative_to(a.ROOT).as_posix()
        raw = path.read_bytes()
        a.require(not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}", raw),
                  "no_secrets_in_curated_source")
        source_hashes[relative] = a.sha(raw)
        if relative not in replacements:
            a.write(context / relative, raw)
    for name in ("project-routes.json", "fireworks-candidate-routes.json", "foundry-eight-candidate-routes.json", "external-inventory.json"):
        a.write(context / "gateway/catalog" / name, (a.CATALOG / name).read_bytes())
    selected = context / "gateway/catalog/foundry-inventory-20261026.json"
    a.write(selected, accepted)
    proof_paths = {profile.S03 + name for name in ("final-local-integrity.json", "source-binding.json", "metadata.json", "policy-binding.json")}
    proof_paths |= {profile.TERRA + "evidence.json", profile.MISTRAL + "evidence.json", profile.MISTRAL + "joined-response.json"}
    proof_paths |= {"gateway/catalog/" + name for name in ("foundry-inventory-20261026.json", "external-inventory.json")}
    for i, alias in enumerate(a.ALIASES, 1):
        stem = (profile.S02 if i <= 5 else profile.S03) + f"probes/{i:02d}-{alias}"
        proof_paths |= {stem + "-response.json", stem + "-intent.json", profile.LEDGER + alias + ".json"}
        if i <= 4 or i in (6, 7):
            proof_paths.add(stem + "-passed.json")
        elif i == 8:
            proof_paths.add(stem + "-failure.json")
    # Native manifests are validated against the historical source binding.
    proof_paths |= {"gateway/catalog/foundry-eight-candidate-routes.json"}
    proof_root = context / "gateway/catalog/acceptance-evidence"
    for path in sorted(proof_paths):
        a.write(proof_root / path, (a.ROOT / path).read_bytes())
    # Execute both the actual historical builder and the new proof-required profile.
    builder = profile_module(context / "services/usage-ingestion/accepted_catalog_profile.py")
    catalog = builder.build(context, profile=profile.PROFILE)
    for path in ("gateway/catalog/ingestion-approved.json", "gateway/catalog/dev-models.json", "services/usage-ingestion/ingestion-approved.json"):
        a.write(context / path, catalog)
    builder.verify_packaged(context, profile=profile.PROFILE)
    enabled = sorted(model["id"] for model in catalog["models"] if model["enabled"])
    a.require(set(enabled) == {r["alias"] for r in accepted["routes"]} | {"glm-5.3"}
              and len(enabled) == 21 and len(catalog["models"]) == 22, "exact_twenty_Foundry_plus_external_and_disabled_Decision")
    # Only NEW Dockerfile copies change; original frozen Dockerfiles are untouched.
    api = (a.ROOT / "services/control-plane/Dockerfile").read_text(encoding="utf-8")
    validation = ('COPY services/usage-ingestion/approved_catalog.py services/usage-ingestion/accepted_catalog_profile.py '
                  'services/usage-ingestion/catalog-bindings.json services/usage-ingestion/ingestion-approved.json ./services/usage-ingestion/\n'
                  'RUN python services/usage-ingestion/accepted_catalog_profile.py --profile foundry-eight-accepted\n')
    a.require(api.count("USER aiflux") == 1, "exact_API_Dockerfile_validation_hook")
    a.write(context / "services/control-plane/Dockerfile", api.replace("USER aiflux", validation + "USER aiflux").encode())
    ingestion = (a.ROOT / "services/usage-ingestion/Dockerfile").read_text(encoding="utf-8")
    a.require(ingestion.count("ARG APPROVED_CATALOG_PROFILE=historical") == 1
              and ingestion.count('RUN python services/usage-ingestion/approved_catalog.py --profile') == 1, "exact_ingestion_Dockerfile_validation_hook")
    ingestion = ingestion.replace("ARG APPROVED_CATALOG_PROFILE=historical", "ARG APPROVED_CATALOG_PROFILE=foundry-eight-accepted")
    ingestion = ingestion.replace("RUN python services/usage-ingestion/approved_catalog.py --profile", (
        'COPY services/usage-ingestion/accepted_catalog_profile.py services/usage-ingestion/ingestion-approved.json ./services/usage-ingestion/\n'
        'COPY gateway/catalog/acceptance-evidence ./gateway/catalog/acceptance-evidence\n'
        'RUN python services/usage-ingestion/accepted_catalog_profile.py --profile'))
    a.write(context / "services/usage-ingestion/Dockerfile", ingestion.encode())
    # Pricing remains its own exact source freeze, not part of acceptance identity.
    rates_path = "services/control-plane/src/aiflux/pricing/rates-foundry-eight-20261030.json"
    pricing = {path: a.sha((a.ROOT / path).read_bytes()) for path in (
        rates_path, "services/control-plane/src/aiflux/pricing/rates-20261027.json", "services/control-plane/src/aiflux/display_pricing.py")}
    for path in pricing:
        a.write(home / "pricing-freeze" / path, (a.ROOT / path).read_bytes())
    rates = a.load(a.ROOT / rates_path)
    a.require({r["model"] for r in rates["rates"]} == set(a.ALIASES) and len(rates["rates"]) == 8, "eight_exact_separate_frozen_rates")
    a.write(home / "pricing-freeze/manifest.json", {"files": pricing, "acceptance_identity_source": False,
        "fresh_pricing_fetch": False, "rates_revision": rates["revision"]})
    a.write(home / "accepted-provenance.json", {"at": a.now(), "profile": profile.PROFILE,
        "technical_identity_mapping": {"deployment": "Mistral-Large-3", "provider_model": "mistral-large-3",
            "match": "exact_case_sensitive_with_correlated_existing_LLM_response_and_usage", "generic_casefold": False,
            "capability_contract_changed": False},
        "original_failed_integrity_sha256": profile.INTEGRITY_SHA256,
        "old_twelve_verified_at_preserved": old["verified_at"], "old_twelve_endpoint_conversions": conversions,
        "grandfather_original_inventory_sha256": a.sha(old_path.read_bytes()), "old_twelve_new_probes": 0,
        "external_bytes_sha256": a.sha((a.CATALOG / "external-inventory.json").read_bytes()), "external_new_probes": 0,
        "new_eight_actual_proofs": rows, "policy_binding": policy,
        "post_probe_policy_read_performed": False, "post_probe_policy_unchanged_claimed": False,
        "fast_evidence": "exact guard-based policy proof, not a retained direct native trace",
        "selected_deployments": 21, "enabled_chat_aliases": enabled, "disabled_routing_only": ["Decision-1"],
        "new_inference_sends": 0, "remaining_inference_budget": 0, "retry_permitted": False,
        "new_builds": 0, "runtime_publish": False, "database_mutations": 0, "APIM_mutations": 0,
        "pricing_freeze": pricing, "curated_source_hashes": source_hashes,
        "files": {p.relative_to(home).as_posix(): a.sha(p.read_bytes()) for p in sorted(context.rglob("*")) if p.is_file()}})
    return context


def run():
    a.require(not HOME.exists(), "offline_promotion_exists_reconcile_no_overwrite")
    gate = a.applied.reader.worker_gate()
    before = historical_hashes()
    validation_home = a.rt.HOME / "foundry-eight-offline-validation-20261031"
    validation = a.load(validation_home / "result.json")
    a.require(validation["passed"] and validation["returncode"] == 0
              and all(a.sha((a.ROOT / p).read_bytes()) == h for p, h in validation["sources"].items())
              and all(a.sha((validation_home / p).read_bytes()) == h for p, h in validation["files"].items()),
              "actual_durable_offline_validation_of_exact_sources_required")
    rows, additions, policy = existing()
    a.write(HOME / "intent.json", {"at": a.now(), "worker_gate": gate, "cloud_calls": 0, "inference_sends": 0,
        "source_sha256": a.sha(Path(__file__).read_bytes()), "profile_sha256": a.sha(PROFILE_SOURCE.read_bytes())})
    try:
        context = package(HOME, rows, additions, policy)
        a.require(historical_hashes() == before, "historical_bytes_unchanged_after_packaging")
        resolved = {**rows[7], "identity_model": "mistral-large-3", "identity_resolution_verified": True,
            "identity_source": "exact_correlated_existing_LLM_metadata_and_retained_raw_model",
            "evidence_sha256": a.sha((m.HOME / "evidence.json").read_bytes()),
            "original_failure_preserved": True, "resolution": "explicit technical identity mapping; no casefold or capability change"}
        a.write(HOME / "mistral-identity-resolution.json", resolved)
        proof_rows = [{**r, "acceptance_identity_validated": True} for r in rows]
        proof_rows[7] = {**resolved, "acceptance_identity_validated": True}
        a.write(HOME / "all-eight-usage-proofs.json", {"proofs": proof_rows,
            "totals": {key: sum(r["usage"][key] for r in rows) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}})
        result = {"at": a.now(), "passed": True, "accepted_identity_successes": 8, "http_200_count": 8,
            "enabled_chat_count": 21, "disabled_Decision_1": True, "new_inference_sends": 0,
            "total_consumed_inference_calls": 8, "remaining_call_budget": 0, "new_builds": 0,
            "cloudbuild_ready_context": context.relative_to(a.ROOT).as_posix(), "profile": profile_module().PROFILE,
            "offline_validation": validation["counts"], "offline_validation_sha256": a.sha((validation_home / "result.json").read_bytes()),
            "historical_bytes_unchanged": True, "historical_hashes": before,
            "files": {p.relative_to(HOME).as_posix(): a.sha(p.read_bytes()) for p in sorted(HOME.rglob("*")) if p.is_file()}}
        a.write(HOME / "result.json", result)
        print(json.dumps({k: v for k, v in result.items() if k not in ("historical_hashes", "files")}))
        return 0
    except Exception as error:
        a.write(HOME / "failure.json", {"at": a.now(), "error_type": type(error).__name__,
            "reason": str(error) if isinstance(error, (a.AcceptanceError, ValueError)) else "details_suppressed",
            "cloud_calls": 0, "inference_sends": 0, "historical_bytes_unchanged": historical_hashes() == before})
        raise


if __name__ == "__main__":
    a.require(sys.argv[1:] == ["promote"], "explicit_offline_promotion_only")
    raise SystemExit(run())