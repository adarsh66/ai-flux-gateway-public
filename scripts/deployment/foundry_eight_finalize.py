"""OFFLINE reconciliation only. No Azure client/HTTP/CLI invocation of any kind.

Preserve consumed receipts, explicitly reject empty appsettings GET projections
as proof, and report unknown comparisons rather than repeat a read or issue POST.
"""
import hashlib
import json
from pathlib import Path

from scripts.deployment import foundry_eight_continue as c


def text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def settings_evidence(value):
    if not value["setting_names"]:
        return {"status": "unavailable", "category": "get_appsettings_empty_projection",
                "settings_sha256": None, "safe_flags": None}
    return {"status": "observed", **value}


def retained_text_comparison(value, expected):
    text = value["properties"]["value"]
    if "[REDACTED]" in text:
        return {"equal": None, "category": "credential_redacted_projection_not_full_bytes"}
    return {"equal": text_hash(text) == expected, "observed_sha256": text_hash(text)}


def reconcile(home=c.HOME):
    first, tail = home / "continuation01", home / "continuation-tail01"
    previous = c.load(home / "continuation-intent.json")
    tail_intent = c.load(home / "continuation-tail-intent.json")
    c.require(previous["original_artifacts"] ==
        {name: c.sha((home / name).read_bytes()) for name in c.ORIGINAL_FILES}, "original_artifact_changed")
    c.require(tail_intent["previous_artifacts"] ==
        {name: c.sha((home / name).read_bytes()) for name in tail_intent["previous_artifacts"]}, "prior_artifact_changed")
    c.require(previous["continuation_source_sha256"] == c.sha(Path(c.__file__).read_bytes()), "consumed_source_changed")
    prior = c.load(c.rt.HOME / "ratecard-release-20261030/verified.json")["baseline"]
    runtime = c.load(tail / "runtime.json")
    sites = {kind: {key: value[key] for key in ("image", "protected")}
             for kind, value in runtime["sites"].items()}
    settings = {kind: settings_evidence(c.load(tail / (kind + "-settings.json"))) for kind in c.KINDS}
    summary = c.load(tail / "policy-summary.json")
    state = c.load(tail / "storage.json")
    comparisons = {"four_sites_images_and_protected_fields_equal": sites == prior["runtime"]["sites"],
                   "storage_approved_five_ip_projection_equal": state["approved_account_projection_equal"] and state["exact_five_ips"],
                   "fresh_settings_hashes_equal": None}
    policies = {}
    for name, oldhash in (("global", prior["apim"]["global"]), ("legacy-policy", prior["apim"]["legacy"]),
                           ("native-policy", prior["apim"]["native"]), ("policy-xml", prior["active_policy_sha256"])):
        policies[name] = retained_text_comparison(c.load(first / (name + ".json")), oldhash)
    policies["poc-fragment"] = retained_text_comparison(c.load(tail / "fragment-00-rawxml.json"), prior["fragment_xml_sha256"])
    for name in ("vault", "postgres"):
        observed = c.load(tail / (name + ".json"))
        comparisons[name + "_network_auth_equal"] = observed == prior["runtime"][name]
    comparisons["postgres_firewall_rules_equal"] = c.load(tail / "postgres-rules.json")["value"] == prior["runtime"]["postgresRules"]
    roles = c.load(tail / "role-assignments.json")
    rows = sorted([row["id"], row["properties"]["principalId"], row["properties"]["roleDefinitionId"],
                   row["properties"]["scope"], row["properties"].get("condition")] for row in roles["value"])
    comparisons["role_assignments_equal"] = rows == prior["runtime"]["roleAssignments"]
    comparisons["jwt_reference_metadata_equal"] = c.load(tail / "jwt-reference.json") == prior["runtime"]["jwt"]
    receipts, http_failures = [], []
    for folder in (first, tail):
        for path in sorted(folder.glob("read-*-result.json")):
            receipts.append({"path": path.relative_to(home).as_posix(), **c.load(path)})
        for path in sorted(folder.glob("read-*-failure.json")):
            http_failures.append({"path": path.relative_to(home).as_posix(), **c.load(path)})
    # Optional product/operation policy 404s were documented absence, not a
    # failed baseline call. Any other wire failure remains an explicit blocker.
    unexpected = [row for row in http_failures if row.get("http_status") != 404]
    c.require(not unexpected, "unexpected_http_failure_requires_review")
    collections = {name: c.load(first / (name + ".json")) for name in
                   ("backends", "fragments", "products", "subscriptions", "operations", "binding")}
    complete_collections = all(value["complete"] for value in collections.values())
    requested = c.load(home / "requested.json")
    c.require(set(requested) == c.original.ALIASES, "retained_requested_aliases_mismatch")
    guard = c.load(tail / "scope-guard.json")
    return {"at": c.stamp(), "status": "INCOMPLETE_FRESH_SETTINGS_UNAVAILABLE_GET_ONLY",
        "live_rollout_complete": False, "writes": 0, "inference": 0, "browser_actions": 0,
        "original_collector_rerun": False, "deployments_reread": False,
        "original_artifacts_unchanged": True, "previous_continuation_artifacts_unchanged": True,
        "fresh_scope_guard": guard,
        "original_stop": {"location": "first_apim_policy_get_or_validation_before_policy_artifact",
            "exception_category": "unknown_no_failure_handler_or_receipt",
            "constant_path_defect_proven": False, "same_exact_apim_get_now_succeeded": True},
        "continuation_stops": [{"artifact": "continuation01/failure.json", "category": "fragment_scope_rejected",
            "cause": "case_sensitive_resource_type_guard_rejected_ARM_policyfragments",
            "resolved_by": "exact_casefold_identity_check_then_canonical_type_in_separate_tail"},
            {"artifact": "continuation-tail01/failure.json", "category": "retained_policy_redacted_comparison_unavailable",
             "cause": "all_cloud_reads_finished_before_offline_full_policy_comparison_guard",
             "resolution": "preserve_redaction_and_report_full_byte_equality_unknown_without_reread"}],
        "cloud_read_summary": {"successful_gets": len(receipts), "optional_policy_absences": len(http_failures),
            "unexpected_cloud_failures": [], "all_apim_collections_complete": complete_collections,
            "collection_counts": {name: len(value["value"]) for name, value in collections.items()},
            "first_success_at": receipts[0]["at"], "last_success_at": receipts[-1]["at"]},
        "baseline_comparisons": comparisons, "policy_comparisons": policies,
        "settings": settings,
        "limitations": ["GET config/appsettings returned HTTP200 properties={} for all four sites; not actual configuration hashes",
            "Historical snapshot uses appsettings/list POST; prohibited here and not issued",
            "runtime.json empty-dictionary hashes and all_four_settings_fresh must NOT be used as live settings evidence",
            "Credential-redacted policy artifacts cannot establish whole-policy byte equality",
            "Original collector exception not retained; exact historical cause unknown"],
        "runtime_pins": {kind: {"site": runtime["sites"][kind]["name"], "image": runtime["sites"][kind]["image"]}
                         for kind in c.KINDS},
        "active_policy": summary,
        "poc_controls": {"fresh_runtime_flag": None, "fresh_v2_flag": None,
            "retained_ratecard_runtime_flag": c.load(tail / "retained-routing.json")["retained_api_runtime_config"]
                ["AIFLUX_GATEWAY_CONTROLS_POC_ENABLED"],
            "retained_ratecard_v2_flag": c.load(tail / "retained-routing.json")["retained_api_runtime_config"]
                ["AIFLUX_GATEWAY_CONTROLS_V2_ENABLED"],
            "live_fragment_exists": True, "live_fragment_attached_to_active_policy":
                "aiflux-dev-unified-poc-settings" in summary["fragment_references"],
            "fragment_content_equal_to_ratecard": policies["poc-fragment"]["equal"]},
        "storage": state,
        "retained_foundry": {"deployment_count": len(c.load(home / "deployments.json")["value"]),
            "requested_aliases": sorted(requested), "freshness": "original_retained_read_not_repeated"},
        "source_hashes": {Path(path).name: c.sha(Path(path).read_bytes()) for path in
            (c.original.__file__, c.__file__, __file__, str(c.rt.ROOT / "scripts/deployment/foundry_eight_recover_tail.py"))},
        "artifacts": {p.relative_to(home).as_posix(): c.sha(p.read_bytes()) for p in
            sorted(home.rglob("*.json"))}}


def main():
    # Exclusive even though offline; do not overwrite any historical receipt.
    c.exclusive(c.HOME, "baseline-finalize-intent.json", {"at": c.stamp(), "cloud_calls": 0,
        "source_sha256": c.sha(Path(__file__).read_bytes())})
    try:
        result = reconcile()
        c.exclusive(c.HOME, "baseline-recovery.json", result)
        print(json.dumps({key: result[key] for key in ("status", "baseline_comparisons", "poc_controls", "cloud_read_summary", "runtime_pins")}), flush=True)
        return 0
    except Exception as error:
        c.exclusive(c.HOME, "baseline-finalize-failure.json", {"at": c.stamp(), **c.failure(error), "cloud_calls": 0})
        print(json.dumps(c.failure(error)), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())