"""Exclusive local-only reconciliation of stopped acceptance; no network."""
import json

from scripts.deployment import foundry_eight_acceptance_successor02 as s

a = s.a


def main():
    home = s.HOME
    gate = a.applied.reader.worker_gate()
    bound = a.load(home / "source-binding.json")
    a.require(s.inputs() == bound, "all_original_source_and_predecessor_bytes_exact")
    intents = sorted((home / "probes").glob("*-intent.json"))
    responses = sorted((home / "probes").glob("*-response.json"))
    passed = sorted((home / "probes").glob("*-passed.json"))
    a.require(len(intents) == len(responses) == 5 and len(passed) == 4, "exact_stopped_five")
    records = [a.load(p) for p in responses]
    a.require([r["alias"] for r in records] == list(a.ALIASES[:5]), "exact_order")
    a.require(len({r["correlation_id"] for r in records}) == 5, "unique_actual_correlations")
    for path in passed:
        a.validate_probe(a.load(path))
    a.require(not (home / "accepted-context").exists() and not (home / "accepted-provenance.json").exists(),
              "no_promotion_after_failure")
    result = {"at": a.now(), "local_only": True, "worker_gate": gate,
        "bound_sources_and_predecessors_unchanged": True,
        "inference_transport_invocations": 5, "passed_alias_count": 4,
        "failed_alias": records[-1]["alias"], "failed_http_status": records[-1]["status"],
        "failure": "response model did not equal requested alias; actual value not retained by sanitizer",
        "unattempted_aliases": list(a.ALIASES[5:]), "retries": 0, "fallbacks": 0,
        "actual_measured_usage_all_five": {k: sum(r["usage"][k] for r in records)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "accepted_artifacts_generated": False, "runtime_release_performed": False,
        "receipt_hashes": {p.relative_to(home).as_posix(): a.sha(p.read_bytes())
            for p in home.rglob("*") if p.is_file()}}
    a.write(home / "final-local-audit.json", result)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())