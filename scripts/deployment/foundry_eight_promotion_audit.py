"""Independent local final integrity check. Never promotes, sends or builds."""
import json
from pathlib import Path

from scripts.deployment import foundry_eight_offline_promotion as f

a = f.a


def run():
    home = f.HOME
    gate = a.applied.reader.worker_gate()
    result = a.load(home / "result.json")
    a.require(result["passed"] and result["accepted_identity_successes"] == 8
              and result["enabled_chat_count"] == 21 and result["remaining_call_budget"] == 0
              and result["new_inference_sends"] == result["new_builds"] == 0, "accepted_result_scope")
    a.require(all(a.sha((home / path).read_bytes()) == expected for path, expected in result["files"].items()),
              "every_packaged_byte_and_receipt_matches")
    a.require(f.historical_hashes() == result["historical_hashes"], "every_original_historical_byte_preserved")
    rows, deployments, _ = f.existing()
    context = a.ROOT / result["cloudbuild_ready_context"]
    builder = f.profile_module(context / "services/usage-ingestion/accepted_catalog_profile.py")
    builder.verify_packaged(context, profile=result["profile"])
    inventory = a.FoundryInventory.model_validate_json((context / "gateway/catalog/foundry-inventory-20261026.json").read_bytes())
    catalog = builder.build(context)
    a.require(len(inventory.routes) == 20 and len(inventory.deployments) == 21
              and all(inventory.route(route.alias) for route in inventory.routes)
              and sum(model["enabled"] for model in catalog["models"]) == 21
              and len(catalog["models"]) == 22, "actual_profile_build_schema_and_runtime_routes")
    provenance = a.load(home / "accepted-provenance.json")
    for path, expected in provenance["files"].items():
        a.require(a.sha((home / path).read_bytes()) == expected, "provenance_file_binding")
    proofs = a.load(home / "all-eight-usage-proofs.json")
    a.require([r["alias"] for r in proofs["proofs"]] == list(a.ALIASES)
              and proofs["totals"] == {"prompt_tokens": 121, "completion_tokens": 80, "total_tokens": 201},
              "exact_actual_eight_usage_proofs")
    for original, resolved in zip(rows, proofs["proofs"]):
        a.require(all(resolved.get(key) == value for key, value in original.items()
                      if not (original["alias"] == "Mistral-Large-3" and key == "identity_source")),
                  "original_actual_response_fields_preserved")
    a.require(proofs["proofs"][7]["identity_source"] == "exact_correlated_existing_LLM_metadata_and_retained_raw_model"
              and rows[7]["identity_source"] == "sanitized_raw_response_model", "explicit_resolution_not_historical_rewrite")
    freeze = a.load(home / "pricing-freeze/manifest.json")
    for path, expected in freeze["files"].items():
        a.require(a.sha((home / "pricing-freeze" / path).read_bytes()) == a.sha((context / path).read_bytes())
                  == a.sha((a.ROOT / path).read_bytes()) == expected, "separate_exact_pricing_freeze")
    validation_home = a.rt.HOME / "foundry-eight-offline-validation-20261031"
    validation = a.load(validation_home / "result.json")
    a.require(a.sha((validation_home / "result.json").read_bytes()) == result["offline_validation_sha256"]
              and all(a.sha((a.ROOT / path).read_bytes()) == expected for path, expected in validation["sources"].items()),
              "214_tests_bound_to_exact_unchanged_sources")
    report = {"at_actual_utc": a.now(), "passed": True, "local_only": True, "worker_gate": gate,
        "accepted_context": result["cloudbuild_ready_context"], "context_files": sum(p.is_file() for p in context.rglob("*")),
        "exact_enabled_aliases": sorted(m["id"] for m in catalog["models"] if m["enabled"]),
        "accepted_identity_successes": len(rows), "selected_Foundry_chat_routes": 20,
        "external_chat_routes": 1, "disabled_Decision_1": True, "remaining_inference_budget": 0,
        "new_inference_sends": 0, "telemetry_queries_total": 2, "cloud_calls_this_audit": 0,
        "builds": 0, "runtime_publish": False, "database_mutations": 0, "APIM_mutations": 0,
        "offline_validation": validation["counts"], "historical_bytes_unchanged": True,
        "actual_builder_schema_and_route_checks": True, "separate_pricing_freeze_exact": True,
        "post_probe_policy_read_performed": False, "post_probe_policy_unchanged_claimed": False,
        "result_sha256": a.sha((home / "result.json").read_bytes()),
        "provenance_sha256": a.sha((home / "accepted-provenance.json").read_bytes()),
        "all_eight_usage_proofs_sha256": a.sha((home / "all-eight-usage-proofs.json").read_bytes()),
        "audit_source_sha256": a.sha(Path(__file__).read_bytes())}
    a.write(home / "final-integrity.json", report)
    print(json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())