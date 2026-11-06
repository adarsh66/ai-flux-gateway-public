"""Fresh GET-only recovery evidence; never publish, reconcile, or replay a release."""
from contextlib import redirect_stdout
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
from uuid import UUID
import xml.etree.ElementTree as ET

from scripts.deployment import poc_publisher_recheck_oct29 as reads
from aiflux.poc_controls import render
from aiflux.gateway_settings import fingerprint
from aiflux.schemas import PocGatewayConfiguration

rt, fs = reads.rt, reads.fs
ORIGINAL = rt.HOME / "poc-publisher-recheck-20261029-0102114890616-21892"
PREFIX = '@{ var owners = JObject.Parse(@"'
SUFFIX = '"); return (string)owners[context.Subscription.Id] ?? ""; }'


def desired_configuration():
    safety = dict(profile="Custom", hate=1, violence=1, sexual=1, self_harm=1,
                  prompt_attack=True, protected_material=False,
                  input_filtering=True, output_filtering=True)
    return PocGatewayConfiguration.model_validate({
        "schema_version": 3,
        "defaults": dict(rpm=60, tpm=2048, token_quota=10000, request_quota=1000),
        "safety": safety,
        "overrides": [{"organization_id": "85d2748e-83b4-4349-a611-131742918afa",
                       "subscription_id": None, "limits": None,
                       "safety": {**safety, "self_harm": 0}}],
    })


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        rt.require(key not in result, "duplicate_owner_rejected")
        result[key] = value
    return result


def extract_bindings(raw):
    tree = ET.fromstring(raw)
    nodes = tree.findall('./set-variable[@name="aiflux-poc-organization"]')
    rt.require(len(nodes) == 1, "exact_one_ownership_variable_required")
    value = nodes[0].get("value", "")
    rt.require(value.startswith(PREFIX) and value.endswith(SUFFIX), "ownership_expression_shape")
    encoded = value[len(PREFIX):-len(SUFFIX)].replace('""', '"')
    mapping = json.loads(encoded, object_pairs_hook=unique_object)
    rt.require(isinstance(mapping, dict) and len(mapping) <= 200, "ownership_mapping_shape")
    for sid, oid in mapping.items():
        rt.require(isinstance(oid, str) and str(UUID(sid)) == sid and str(UUID(oid)) == oid,
                   "ownership_uuid_shape")
    # Preserve insertion order: the publisher canonicalizer does not sort JSON
    # inside the C# string. Equivalent mappings in another order can cause PUT.
    return [{"subscription_id": sid, "organization_id": oid} for sid, oid in mapping.items()]


def compare(raw):
    bindings = extract_bindings(raw)
    desired = desired_configuration()
    rendered = render(desired, bindings)
    exact = fingerprint(raw) == fingerprint(rendered)
    return bindings, rendered, {
        "current_publisher_canonical_sha256": fingerprint(raw),
        "rendered_parent_config_current_fragment_bindings_canonical_sha256": fingerprint(rendered),
        "canonical_match_using_extracted_current_bindings": exact,
        "strict_structure_match_using_extracted_current_bindings": reads.structure(raw) == reads.structure(rendered),
        "ownership_mapping_count": len(bindings),
        "ownership_mapping_sha256": fs.sha(bindings),
        "ownership_mapping_order_preserved": True,
        "config_source": "Parent GET at 2026-10-29T01:08:41Z; desired10 failed/published9; configurations reported identical",
        "revision10_stored_bindings_observed": False,
        "revision10_exact_ownership_match_proven": False,
        "reconcile_will_skip_put_proven": False,
        "limitation": "Roundtrip uses APIM's current bindings, not revision10 stored bindings. GET revision_output omits bindings; targets/current ownership cannot prove the historical stored revision map or JSON insertion order.",
        "recommendation": "Do not assert or rely on PUT being skipped. Obtain exact revision10 stored bindings/rendered fingerprint through an authorized read-only audited channel first. No direct fragment PUT or reconcile performed.",
    }


def original_hashes():
    return {p.name: reads.sha(p.read_bytes()) for p in ORIGINAL.iterdir() if p.is_file()}


def main(folder):
    rt.require(folder.parent == rt.HOME and folder.name.startswith("poc-recovery-readonly-20261029-"),
               "exclusive_recovery_directory_required")
    report = {"started_at_utc": datetime.now(UTC).isoformat(), "status": "blocked",
              "cloud_configuration_writes": 0, "publication_attempts": 0,
              "reconcile_requests": 0, "browser_actions": 0, "inference_requests": 0,
              "state_backend_access": False, "builds": 0, "terraform_commands": 0,
              "audit_deletions": 0, "tls_verification": True, "corporate_ca": rt.CA,
              "parent_reported_ip": "167.103.63.12", "ip_independently_verified": False,
              "blockers": [], "evidence_directory": folder.relative_to(rt.ROOT).as_posix()}
    stage = "azure_bestpractices"
    historical = original_hashes()
    reads.save(folder, "original-evidence-hashes-before.json", historical)
    try:
        with (folder / "azure-bestpractices.txt").open("x", encoding="utf-8") as handle, redirect_stdout(handle):
            reads.glm_resume.bestpractices()
        report["azure_bestpractices_invoked"] = True
        rt.cli = reads.cli_read
        reads.activation.ProductRun = reads.ReadOnlyProductRun
        stage = "account"
        reads.customer.account()
        report["account_tenant_subscription_verified"] = True
        stage = "fresh_apim_before"
        run = reads.ReadOnlyProductRun()
        service = run.arm("")
        reads.save(folder, "apim-service.json", service)
        report["apim_provisioning_state"] = service.get("properties", {}).get("provisioningState")
        before = reads.exports(run, folder, "before")
        reads.save(folder, "before-summary.json", before)
        stage = "complete_protected_baseline"
        protected = reads.activation.snapshot()
        reads.save(folder, "protected-snapshot.json", protected)
        report["protected_components"] = sorted(protected)
        report["protected_snapshot_object_sha256"] = fs.sha(protected)
        report["protected_snapshot_file_sha256"] = reads.sha((folder / "protected-snapshot.json").read_bytes())
        prior = json.loads((ORIGINAL / "protected-snapshot.json").read_text(encoding="utf-8-sig"))
        report["protected_component_equal_to_original"] = {key: value == prior.get(key) for key, value in protected.items()}
        stage = "fresh_apim_after"
        after = reads.exports(run, folder, "after")
        reads.save(folder, "after-summary.json", after)
        report.update(after)
        report["exports_stable_across_snapshot"] = before == after
        report["snapshot_binds_exact_policy_and_fragment"] = (
            protected["active_policy_sha256"] == after["policy_xml_sha256"]
            and protected["fragment_xml_sha256"] == after["fragment_rawxml_sha256"]
            and protected["fragment_properties_sha256"] == after["fragment_properties_sha256"])
        stage = "pure_render_comparison"
        raw = (folder / "after-fragment-rawxml.xml").read_bytes().decode("utf-8")
        bindings, rendered, comparison = compare(raw)
        reads.save(folder, "parent-reported-desired-revision10-configuration.json", desired_configuration().model_dump(mode="json"))
        reads.save(folder, "current-fragment-extracted-bindings.json", bindings)
        with (folder / "rendered-parent-config-current-bindings.xml").open("xb") as handle:
            handle.write(rendered.encode("utf-8"))
        reads.save(folder, "semantic-comparison.json", comparison)
        report["comparison"] = comparison
        report["runtime_image_pins"] = {key: value["image"].rsplit("@sha256:", 1)[-1]
                                        for key, value in protected["runtime"]["sites"].items()}
        checks = {
            "policy_not_detached": after["detached"],
            "apim_not_ready": report["apim_provisioning_state"] == "Succeeded",
            "fragment_not_ready": after["fragment_provisioning_state"] == "Succeeded",
            "fragment_etag_missing": after["fragment_etag_present"],
            "fragment_exports_differ": after["fragment_export_semantics_equal"] and after["fragment_export_etags_equal"],
            "exports_changed": report["exports_stable_across_snapshot"],
            "snapshot_xml_mismatch": report["snapshot_binds_exact_policy_and_fragment"],
            "parent_config_roundtrip_mismatch": comparison["canonical_match_using_extracted_current_bindings"]
                and comparison["strict_structure_match_using_extracted_current_bindings"],
            "unexpected_image_pin": all(report["runtime_image_pins"][key].startswith(pin) for key, pin in reads.EXPECTED.items()),
        }
        report["read_only_preflight_blockers"] = [key for key, value in checks.items() if not value]
        report["blockers"] = report["read_only_preflight_blockers"] + ["revision10_stored_bindings_not_exposed"]
        report["status"] = "readonly_baseline_passed_no_put_skip_unproven" if not report["read_only_preflight_blockers"] else "blocked"
    except Exception as exc:
        report.update(failed_stage=stage, error_type=type(exc).__name__)
        safe = str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[a-z_]+", str(exc)) else "read_only_collection_failed"
        report["blockers"].append(safe)
    finally:
        unchanged = historical == original_hashes()
        report["original_evidence_all_files_unchanged"] = unchanged
        if not unchanged:
            report["blockers"].append("original_evidence_changed")
        report["finished_at_utc"] = datetime.now(UTC).isoformat()
        reads.save(folder, "read-operations.json", reads.READS)
        report["evidence_sha256"] = {p.name: reads.sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()}
        reads.save(folder, "readiness.json", report)
        print(json.dumps(report), flush=True)
    return 0 if report["status"] == "readonly_baseline_passed_no_put_skip_unproven" else 2


def audit(folder, current=False):
    """Offline post-worker audit; no reads from Azure and no historical changes."""
    rt.require(folder.parent == rt.HOME and folder.name.startswith("poc-recovery-readonly-20261029-"),
               "recovery_scope_required")
    load = lambda name: json.loads((folder / name).read_text(encoding="utf-8-sig"))
    readiness = load("readiness.json")
    hashes = {name: reads.sha((folder / name).read_bytes()) == digest
              for name, digest in readiness["evidence_sha256"].items()}
    before = load("workers-before.json")
    after = load("workers-current.json" if current else "workers-after.json")
    conflicts = [item for item in before + after if item["mutation_worker"] and not item["this_collector"]]
    original = load("original-evidence-hashes-before.json") == original_hashes()
    raw = (folder / "after-fragment-rawxml.xml").read_bytes().decode("utf-8")
    comparison = compare(raw)[2]
    stable = comparison == load("semantic-comparison.json")
    result = {
        "at_utc": datetime.now(UTC).isoformat(), "offline_only": True,
        "evidence_hashes_verified": all(hashes.values()),
        "original_evidence_all_files_unchanged": original,
        "mutation_workers_observed": len(conflicts),
        "python_or_terraform_workers_after": sum(bool(re.search("python|terraform", item["name"], re.I)) for item in after),
        "workers_before_after_identical": before == after,
        "pure_comparison_reproduced": stable,
        "fragment_rawxml_restore_target_sha256": reads.sha(raw),
        "publisher_canonical_sha256": fingerprint(raw),
        "readiness_file_sha256": reads.sha((folder / "readiness.json").read_bytes()),
        "source_sha256": reads.sha(Path(__file__).read_bytes()),
        "cloud_configuration_writes": 0, "reconcile_requests": 0,
        "status": readiness["status"],
        "reconcile_will_skip_put_proven": False,
    }
    result["audit_passed"] = all(hashes.values()) and original and stable and not conflicts and not result["python_or_terraform_workers_after"]
    if current:
        result["prior_completion_audit_sha256"] = reads.sha((folder / "completion-audit.json").read_bytes())
        result["prior_after_python_worker_count"] = sum(bool(re.search("python|terraform", item["name"], re.I)) for item in load("workers-after.json"))
        result["prior_worker_review"] = "Original after-capture overlapped focused offline tests; retained unchanged. Current independent process capture is authoritative only for current quiescence."
    reads.save(folder, "completion-current-workers-audit.json" if current else "completion-audit.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["audit_passed"] else 2


if __name__ == "__main__":
    if sys.argv[1] == "--audit-current":
        sys.exit(audit(Path(sys.argv[2]).resolve(), current=True))
    if sys.argv[1] == "--audit":
        sys.exit(audit(Path(sys.argv[2]).resolve()))
    sys.exit(main(Path(sys.argv[1]).resolve()))