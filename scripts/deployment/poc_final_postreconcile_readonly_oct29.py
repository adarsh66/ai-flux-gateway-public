"""Fresh post-reconcile proof using existing pure read functions, never entrypoints."""
from contextlib import redirect_stdout
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys

from scripts.deployment import poc_restoration_readonly_oct29 as pure

reads, rt, fs = pure.reads, pure.rt, pure.fs
ORIGINAL = pure.pure.ORIGINAL
RESTORATION = rt.HOME / "poc-restoration-readonly-20261029-0119418708893-21404"
AFTER = "2026-10-29T01:24:14.008+00:00"


def historical():
    return {p.name: pure.hashes(p) for p in (ORIGINAL, pure.PRIOR, pure.REV11, RESTORATION)}


def compare(folder):
    results = {}
    for kind in ("policy", "fragment"):
        for fmt in ("rawxml", "xml"):
            name = f"after-{kind}-{fmt}.xml"
            results[name] = (folder / name).read_bytes() == (ORIGINAL / name).read_bytes()
    return results


def collect(folder):
    rt.require(folder.parent == rt.HOME and folder.name.startswith("poc-final-postreconcile-readonly-20261029-"), "fresh_scope_required")
    rt.require({p.name for p in folder.iterdir()} == {"workers-before.json"}, "exclusive_directory_required")
    started = datetime.now(UTC).isoformat()
    rt.require(started > AFTER, "must_be_after_successful_reconcile_and_portal_get")
    report = dict(started_at_utc=started, status="blocked", evidence_directory=folder.relative_to(rt.ROOT).as_posix(),
                  cloud_configuration_writes=0, reconcile_requests=0, publication_attempts=0,
                  browser_actions=0, inference_requests=0, terraform_commands=0, builds=0,
                  network_changes=0, role_changes=0, optional_log_reads=0, state_backend_access=False,
                  tls_verification=True, historical_entrypoint_replays=0,
                  parent_portal_state="parent-reported: GET01:24:14.008Z 200 desired=published=12 exact original config error=null enforcement=false",
                  portal_state_independently_queried=False, http504_cause_established=False)
    prior_hashes = historical()
    reads.save(folder, "historical-evidence-hashes-before.json", prior_hashes)
    stage = "bestpractices"
    try:
        with (folder / "azure-bestpractices.txt").open("x", encoding="utf-8") as handle, redirect_stdout(handle):
            reads.glm_resume.bestpractices()
        rt.cli = reads.cli_read
        reads.activation.ProductRun = reads.ReadOnlyProductRun
        original_arm = rt.arm
        allowed = {rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + k + "/config/appsettings/list"
                   for k in ("api", "admin", "customer", "ingestion")}

        def guarded_arm(path, method="GET", raw=False):
            rt.require(method == "GET" or (method == "POST" and path in allowed), "nonread_or_log_operation_rejected")
            reads.READS.append(dict(kind="arm_read", path=path, method=method, documented_read_only_post=method == "POST"))
            return original_arm(path, method, raw)

        rt.arm = guarded_arm
        stage = "account"
        reads.customer.account()
        run = reads.ReadOnlyProductRun()
        stage = "before_exports"
        service_before = run.arm("")
        reads.save(folder, "apim-service-before.json", service_before)
        before = reads.exports(run, folder, "before")
        reads.save(folder, "before-summary.json", before)
        stage = "complete_protected_snapshot"
        protected = reads.activation.snapshot()
        reads.save(folder, "protected-snapshot.json", protected)
        stage = "after_exports"
        after = reads.exports(run, folder, "after")
        reads.save(folder, "after-summary.json", after)
        service_after = run.arm("")
        reads.save(folder, "apim-service-after.json", service_after)
        baseline = pure.load(ORIGINAL, "protected-snapshot.json")
        fragment = pure.compare_fragment(folder)
        reads.save(folder, "exact-fragment-comparison.json", fragment)
        paths = pure.differences(baseline, protected)
        checks = dict(
            exact_fragment_all_checks=all(v for v in fragment.values() if isinstance(v, bool)),
            all_four_export_bytes_equal_original=all(compare(folder).values()),
            all13_protected_equal_original=len(baseline) == len(protected) == 13 and protected == baseline,
            no_protected_exceptions=not paths,
            exports_stable=before == after,
            snapshot_binds_exports=protected["active_policy_sha256"] == after["policy_xml_sha256"]
                and protected["fragment_xml_sha256"] == after["fragment_rawxml_sha256"]
                and protected["fragment_properties_sha256"] == after["fragment_properties_sha256"],
            apim_service_stable=service_before == service_after,
            apim_service_equal_original=service_after == pure.load(ORIGINAL, "apim-service.json"),
            apim_succeeded=service_after.get("properties", {}).get("provisioningState") == "Succeeded",
            fragment_succeeded=after["fragment_provisioning_state"] == "Succeeded",
            detached_zero_includes=after["detached"] and after["policy_include_count"] == 0,
            fragment_exports_equal=after["fragment_export_semantics_equal"] and after["fragment_export_etags_equal"] and after["fragment_etag_present"])
        report.update(checks=checks, comparison=fragment, export_bytes_equal_original=compare(folder),
                      protected_delta_paths=paths, ignored_protected_paths=[],
                      protected_component_equal_original={k: baseline[k] == protected.get(k) for k in baseline},
                      protected_snapshot_file_sha256=reads.sha((folder / "protected-snapshot.json").read_bytes()),
                      protected_snapshot_object_sha256=fs.sha(protected))
        report["status"] = "readonly_postreconcile_exact_original_verified" if all(checks.values()) else "readonly_mismatch_observed"
    except Exception as exc:
        report.update(failed_stage=stage, error_type=type(exc).__name__, http_status=getattr(exc, "code", None))
    finally:
        report["historical_evidence_unchanged"] = prior_hashes == historical()
        if not report["historical_evidence_unchanged"]:
            report["status"] = "blocked"
        report["finished_at_utc"] = datetime.now(UTC).isoformat()
        reads.save(folder, "read-operations.json", reads.READS)
        report["evidence_sha256"] = pure.hashes(folder)
        reads.save(folder, "readiness.json", report)
        print(json.dumps(report), flush=True)
    return 0 if report["status"] == "readonly_postreconcile_exact_original_verified" else 2


def audit(folder):
    report = pure.load(folder, "readiness.json")
    protected = pure.load(folder, "protected-snapshot.json")
    baseline = pure.load(ORIGINAL, "protected-snapshot.json")
    workers = pure.load(folder, "workers-after.json")
    result = dict(at_utc=datetime.now(UTC).isoformat(), offline_only=True,
                  evidence_hashes_verified=all(reads.sha((folder / n).read_bytes()) == h for n, h in report["evidence_sha256"].items()),
                  historical_evidence_unchanged=pure.load(folder, "historical-evidence-hashes-before.json") == historical(),
                  fragment_comparison_reproduced=pure.compare_fragment(folder) == pure.load(folder, "exact-fragment-comparison.json"),
                  all_four_export_bytes_equal_original=all(compare(folder).values()),
                  all13_protected_equal_original=len(protected) == len(baseline) == 13 and protected == baseline,
                  no_protected_exceptions=not pure.differences(baseline, protected),
                  python_or_terraform_workers_after=sum(bool(re.search("python|terraform", w["name"], re.I)) for w in workers),
                  mutation_workers_after=sum(w["mutation_worker"] and not w["this_collector"] for w in workers),
                  readonly_operation_contract=all(r.get("method", "GET") == "GET" or r.get("documented_read_only_post") for r in pure.load(folder, "read-operations.json")),
                  no_optional_log_reads=not any("containerlogs" in r.get("path", "") for r in pure.load(folder, "read-operations.json")),
                  collector_verified=report["status"] == "readonly_postreconcile_exact_original_verified",
                  readiness_file_sha256=reads.sha((folder / "readiness.json").read_bytes()),
                  collector_source_sha256=reads.sha(Path(__file__).read_bytes()))
    result["audit_passed"] = all(v for v in result.values() if isinstance(v, bool)) and not result["python_or_terraform_workers_after"] and not result["mutation_workers_after"]
    reads.save(folder, "independent-completion-audit.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["audit_passed"] else 2


if __name__ == "__main__":
    sys.exit(audit(Path(sys.argv[2]).resolve()) if sys.argv[1] == "--audit" else collect(Path(sys.argv[1]).resolve()))