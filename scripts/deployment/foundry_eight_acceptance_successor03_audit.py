"""Local-only final reconciliation; cannot create clients or send inference."""
import json
from pathlib import Path

from scripts.deployment import foundry_eight_acceptance_successor03 as s

a = s.a


def main():
    # This file is new and not part of any consumed controller's frozen sources.
    gate = a.applied.reader.worker_gate()
    bound = a.load(s.HOME / "source-binding.json")
    a.require(all(a.sha((a.ROOT / p).read_bytes()) == h for p, h in bound.items()), "frozen_source_or_historical_evidence_drift")
    results, additions, _ = s.predecessors()
    for i, alias in enumerate(s.REMAINING, 6):
        row = s.bind_receipt(s.HOME, i, alias)
        if i < 8:
            s.validate_probe(row, additions)
            passed = a.load(s.HOME / "probes" / f"{i:02d}-{alias}-passed.json")
            a.require(row == passed, "passed_receipt_changed")
        results.append(row)
    failure = a.load(s.HOME / "probes/08-Mistral-Large-3-failure.json")
    a.require(failure["reason"] == "exact_alias_or_OpenAI_ARM_name_version_only"
              and failure["request_consumed"] and not failure["retry_permitted"], "precise_retained_stop")
    mistral = results[7]
    a.require(mistral["status"] == 200 and mistral["response_model"] == "mistral-large-3"
              and mistral["canonical_alias"] == "Mistral-Large-3", "actual_case_sensitive_identity_mismatch")
    try:
        s.validate_probe(mistral, additions)
    except a.AcceptanceError as error:
        a.require(str(error) == failure["reason"], "offline_failure_differs")
    else:
        raise a.AcceptanceError("failed_identity_must_not_be_accepted")
    consumed = s.consumed_intents(a.rt.HOME)
    a.require(set(consumed) == {p.stem for p in s.LEDGER.glob("*.json")} == set(a.ALIASES), "exact_eight_global_exhaustion")
    a.require(len({r["correlation_id"] for r in results}) == len({r["response_id"] for r in results}) == 8,
              "eight_distinct_actual_response_ids")
    for name in ("accepted-context", "accepted-provenance.json", "result.json", "rates-proof.json"):
        a.require(not (s.HOME / name).exists(), "no_acceptance_or_packaging_after_failure")
    proof = {"at": a.now(), "local_only": True, "worker_gate": gate,
        "passed": False, "accepted_success_count": 7, "http_200_count": 8,
        "total_consumed_calls": 8, "new_calls": 3, "repeated_calls": 0,
        "remaining_call_budget": 0, "retry_permitted": False,
        "successful_aliases": [r["alias"] for r in results[:7]],
        "blocker": {"alias": mistral["alias"], "captured_response_model": mistral["response_model"],
            "expected_alias": "Mistral-Large-3", "reason": failure["reason"],
            "contract": "Only OpenAI may additionally use exact ARM model_name-model_version; no case-fold equivalence authorized"},
        "usage": {r["alias"]: r["usage"] for r in results},
        "measured_usage_total_all_eight": {k: sum(r["usage"][k] for r in results)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "proofs": results, "historical_bytes_unchanged": True, "all_frozen_source_hashes_match": True,
        "original_terra_response_model_still_null": a.load(s.previous.HOME / "probes/05-gpt-6.1-terra-response.json")["response_model"] is None,
        "accepted_context_generated": False, "packaged_catalogs_generated": False,
        "post_probe_policy_read_performed": False, "post_probe_policy_unchanged_claimed": False,
        "APIM_mutations": 0, "builds": 0, "runtime_publish": False, "database_mutations": 0,
        "offline_validation": {"passed": 195, "existing_deprecation_warnings": 1},
        "source_hashes": {Path(path).relative_to(a.ROOT).as_posix(): a.sha(Path(path).read_bytes())
            for path in (s.__file__, __file__, a.ROOT / "tests/unit/test_foundry_eight_acceptance_successor03.py")},
        "receipt_hashes": {p.relative_to(a.ROOT).as_posix(): a.sha(p.read_bytes())
            for folder in (s.HOME, s.LEDGER) for p in sorted(folder.rglob("*")) if p.is_file()}}
    a.write(s.HOME / "final-local-integrity.json", proof)
    print(json.dumps({k: v for k, v in proof.items() if k not in ("proofs", "receipt_hashes", "source_hashes")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())