"""Exclusive after-restoration observation. No release entrypoint is invoked."""
from contextlib import redirect_stdout
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys

from scripts.deployment import poc_recovery_readonly_oct29 as pure

reads, rt, fs = pure.reads, pure.rt, pure.fs
PRIOR = rt.HOME / "poc-recovery-readonly-20261029-0110288510019-21404"
REV11 = rt.HOME / "poc-revision11-readonly-20261029-0115280360287-21404"
CANONICAL = "36af0cecf7ed9482ff8807f44474862c15dfa363918fc6d35e455b0ec6ae9edc"
RAW = "09c8c268d63490daeff42d8fbd414fd564743c325c32f72d7c553197f3b0896f"


def load(folder, name):
    return json.loads((folder / name).read_text(encoding="utf-8-sig"))


def hashes(folder):
    return {p.name: reads.sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()}


def differences(a, b, path=""):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return [p for k in sorted(a.keys() | b.keys()) for p in (
            [path + "/" + k] if k not in a or k not in b else differences(a[k], b[k], path + "/" + k))]
    if isinstance(a, list):
        if len(a) != len(b):
            return [path + "/length"]
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in differences(x, y, path + "/" + str(i))]
    return [] if a == b else [path]


def compare_fragment(folder):
    original = (PRIOR / "after-fragment-rawxml.xml").read_bytes()
    actual = (folder / "after-fragment-rawxml.xml").read_bytes()
    text, old = actual.decode("utf-8"), original.decode("utf-8")
    bindings = pure.extract_bindings(text)
    rendered = pure.render(pure.desired_configuration(), bindings)
    return {
        "baseline_raw_hash_matches_requested": reads.sha(original) == RAW,
        "baseline_canonical_hash_matches_requested": pure.fingerprint(old) == CANONICAL,
        "actual_raw_sha256": reads.sha(actual),
        "actual_canonical_sha256": pure.fingerprint(text),
        "raw_bytes_equal_original": actual == original,
        "canonical_equals_exact_original": pure.fingerprint(text) == CANONICAL,
        "strict_structure_equals_original": reads.structure(text) == reads.structure(old),
        "current_bindings_equal_original_exact_order": bindings == load(PRIOR, "current-fragment-extracted-bindings.json"),
        "binding_count": len(bindings),
        "exact_default60_original_override_render_match": reads.structure(text) == reads.structure(rendered),
        "rendered_canonical_equals_original": pure.fingerprint(rendered) == CANONICAL,
    }


def collect(folder):
    rt.require(folder.parent == rt.HOME and folder.name.startswith("poc-restoration-readonly-20261029-"), "fresh_scope_required")
    rt.require(folder.is_dir() and {p.name for p in folder.iterdir()} == {"workers-before.json"}, "exclusive_directory_required")
    report = {"started_at_utc": datetime.now(UTC).isoformat(), "status": "blocked",
              "cloud_configuration_writes": 0, "reconcile_requests": 0,
              "publication_attempts": 0, "browser_actions": 0, "terraform_commands": 0,
              "inference_requests": 0, "tls_verification": True,
              "ui_revision12_failed_published11": "parent-reported; not independently queried",
              "reconcile_will_skip_put_proven": False,
              "evidence_directory": folder.relative_to(rt.ROOT).as_posix()}
    historical = {p.name: hashes(p) for p in (PRIOR, REV11)}
    reads.save(folder, "historical-evidence-hashes-before.json", historical)
    stage = "bestpractices"
    try:
        with (folder / "azure-bestpractices.txt").open("x", encoding="utf-8") as handle, redirect_stdout(handle):
            reads.glm_resume.bestpractices()
        rt.cli = reads.cli_read
        reads.activation.ProductRun = reads.ReadOnlyProductRun
        original_arm = rt.arm

        def guarded_arm(path, method="GET", raw=False):
            allowed_lists = {rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + k + "/config/appsettings/list"
                             for k in ("api", "admin", "customer", "ingestion")}
            log_path = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/containerlogs"
            rt.require(method == "GET" or (method == "POST" and path in allowed_lists | {log_path}), "nonread_arm_rejected")
            reads.READS.append({"kind": "arm_read", "path": path, "method": method,
                                "documented_read_only_post": method == "POST"})
            return original_arm(path, method, raw)

        rt.arm = guarded_arm
        stage = "account"
        reads.customer.account()
        stage = "fresh_before_exports"
        run = reads.ReadOnlyProductRun()
        service_before = run.arm("")
        reads.save(folder, "apim-service-before.json", service_before)
        before = reads.exports(run, folder, "before")
        reads.save(folder, "before-summary.json", before)
        # Early evidence is useful to the parent but is NOT full completion proof.
        stage = "complete_protected_snapshot"
        protected = reads.activation.snapshot()
        reads.save(folder, "protected-snapshot.json", protected)
        stage = "fresh_after_exports"
        after = reads.exports(run, folder, "after")
        reads.save(folder, "after-summary.json", after)
        service_after = run.arm("")
        reads.save(folder, "apim-service-after.json", service_after)
        comparison = compare_fragment(folder)
        reads.save(folder, "exact-fragment-comparison.json", comparison)
        prior = load(PRIOR, "protected-snapshot.json")
        paths = differences(prior, protected)
        report["protected_component_equal_original"] = {k: prior.get(k) == protected.get(k) for k in sorted(prior.keys() | protected.keys())}
        report["protected_delta_paths"] = paths
        report["protected_component_count"] = len(prior)
        report["protected_snapshot_object_sha256"] = fs.sha(protected)
        report["strict_no_ignored_protected_paths"] = not paths
        report["exports_stable_across_snapshot"] = before == after
        report["snapshot_binds_policy_and_fragment"] = (
            protected["active_policy_sha256"] == after["policy_xml_sha256"]
            and protected["fragment_xml_sha256"] == after["fragment_rawxml_sha256"]
            and protected["fragment_properties_sha256"] == after["fragment_properties_sha256"])
        report["apim_service_delta_paths_vs_original"] = differences(load(PRIOR, "apim-service.json"), service_after)
        report["apim_service_stable_during_collection"] = service_before == service_after
        report["apim_provisioning_state"] = service_after.get("properties", {}).get("provisioningState")
        report["fragment_provisioning_state"] = after["fragment_provisioning_state"]
        report["fragment_etag_changed_vs_original"] = after["fragment_etag_sha256"] != load(PRIOR, "after-summary.json")["fragment_etag_sha256"]
        report["policy_xml_sha256"] = after["policy_xml_sha256"]
        report["policy_rawxml_sha256"] = after["policy_rawxml_sha256"]
        report["detached_zero_includes"] = after["detached"] and after["policy_include_count"] == 0
        report["comparison"] = comparison
        stage = "optional_numeric_publication_logs"
        try:
            raw_logs = rt.arm(rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api/containerlogs", "POST", raw=True)
            text = raw_logs.decode("utf-8", errors="replace")
            # Retain only fixed stage names and numeric statuses, never raw lines.
            events = re.findall(r"POC fragment publication failed stage=(baseline_read|conditional_put_and_readiness|strict_readback) status=(\d{3}|None)", text)
            logs = {"at_utc": datetime.now(UTC).isoformat(), "read_only": True,
                    "matching_events": [{"stage": s, "status": int(n) if n.isdigit() else None} for s, n in events],
                    "response_bytes": len(raw_logs), "raw_logs_retained": False,
                    "revision12_event_attribution_proven": False,
                    "limitation": "No raw lines retained; absent exact timestamp correlation, events are not attributed to revision12."}
        except Exception as exc:
            logs = {"available": False, "error_type": type(exc).__name__, "http_status": getattr(exc, "code", None), "configuration_changed": False}
        reads.save(folder, "numeric-publication-log-summary.json", logs)
        checks = [all(v for k, v in comparison.items() if isinstance(v, bool)),
                  not paths, report["exports_stable_across_snapshot"], report["snapshot_binds_policy_and_fragment"],
                  report["apim_service_stable_during_collection"], report["detached_zero_includes"],
                  report["apim_provisioning_state"] == "Succeeded", after["fragment_provisioning_state"] == "Succeeded",
                  after["fragment_export_semantics_equal"], after["fragment_export_etags_equal"], after["fragment_etag_present"]]
        report["status"] = "readonly_exact_original_restoration_verified" if all(checks) else "readonly_mismatch_observed"
    except Exception as exc:
        report.update(failed_stage=stage, error_type=type(exc).__name__, http_status=getattr(exc, "code", None))
    finally:
        report["historical_evidence_all_files_unchanged"] = historical == {p.name: hashes(p) for p in (PRIOR, REV11)}
        report["finished_at_utc"] = datetime.now(UTC).isoformat()
        reads.save(folder, "read-operations.json", reads.READS)
        report["evidence_sha256"] = hashes(folder)
        reads.save(folder, "readiness.json", report)
        print(json.dumps(report), flush=True)
    return 0 if report["status"] == "readonly_exact_original_restoration_verified" else 2


def audit(folder):
    report = load(folder, "readiness.json")
    protected, prior = load(folder, "protected-snapshot.json"), load(PRIOR, "protected-snapshot.json")
    workers = load(folder, "workers-after.json")
    result = {"at_utc": datetime.now(UTC).isoformat(), "offline_only": True,
              "evidence_hashes_verified": all(reads.sha((folder / n).read_bytes()) == h for n, h in report["evidence_sha256"].items()),
              "historical_evidence_unchanged": load(folder, "historical-evidence-hashes-before.json") == {p.name: hashes(p) for p in (PRIOR, REV11)},
              "exact_fragment_comparison_reproduced": compare_fragment(folder) == load(folder, "exact-fragment-comparison.json"),
              "all_protected_components_exact_equal": protected == prior,
              "protected_delta_paths": differences(prior, protected),
              "before_after_exports_stable": load(folder, "before-summary.json") == load(folder, "after-summary.json"),
              "python_or_terraform_workers_after": sum(bool(re.search("python|terraform", w["name"], re.I)) for w in workers),
              "mutation_workers_after": sum(w["mutation_worker"] and not w["this_collector"] for w in workers),
              "collector_status": report["status"], "cloud_configuration_writes": 0,
              "readiness_file_sha256": reads.sha((folder / "readiness.json").read_bytes()),
              "collector_source_sha256": reads.sha(Path(__file__).read_bytes())}
    result["audit_passed"] = all(result[k] for k in ("evidence_hashes_verified", "historical_evidence_unchanged", "exact_fragment_comparison_reproduced", "all_protected_components_exact_equal", "before_after_exports_stable")) and not result["python_or_terraform_workers_after"] and not result["mutation_workers_after"] and report["status"] == "readonly_exact_original_restoration_verified"
    reads.save(folder, "independent-completion-audit.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["audit_passed"] else 2


if __name__ == "__main__":
    sys.exit(audit(Path(sys.argv[2]).resolve()) if sys.argv[1] == "--audit" else collect(Path(sys.argv[1]).resolve()))