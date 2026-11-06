"""Exclusive read-only revision11 observation; no historical entrypoint replay."""
from contextlib import redirect_stdout
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from scripts.deployment import poc_recovery_readonly_oct29 as pure

reads, rt, fs = pure.reads, pure.rt, pure.fs
PRIOR = rt.HOME / "poc-recovery-readonly-20261029-0110288510019-21404"


def main(folder):
    rt.require(folder.parent == rt.HOME and folder.name.startswith("poc-revision11-readonly-"), "exclusive_scope")
    rt.require(folder.is_dir() and not list(folder.iterdir()), "empty_exclusive_directory")
    report = {"started_at_utc": datetime.now(UTC).isoformat(), "evidence_directory": folder.relative_to(rt.ROOT).as_posix(),
              "cloud_configuration_writes": 0, "reconcile_requests": 0, "browser_actions": 0,
              "terraform_commands": 0, "inference_requests": 0, "status": "blocked",
              "ui_revision11_failed_published10": "parent-reported, not independently queried"}
    prior_hashes = {p.name: reads.sha(p.read_bytes()) for p in PRIOR.iterdir() if p.is_file()}
    try:
        with (folder / "azure-bestpractices.txt").open("x", encoding="utf-8") as handle, redirect_stdout(handle):
            reads.glm_resume.bestpractices()
        rt.cli = reads.cli_read
        reads.activation.ProductRun = reads.ReadOnlyProductRun
        reads.customer.account()
        run = reads.ReadOnlyProductRun()
        # Capture the transient fragment before the broader required baseline.
        before = reads.exports(run, folder, "before")
        reads.save(folder, "before-summary.json", before)
        raw = (folder / "before-fragment-rawxml.xml").read_bytes().decode("utf-8")
        bindings = pure.extract_bindings(raw)
        desired = pure.desired_configuration().model_dump(mode="json")
        desired["defaults"]["rpm"] = 59
        config = pure.PocGatewayConfiguration.model_validate(desired)
        rendered = pure.render(config, bindings)
        prior_raw = (PRIOR / "after-fragment-rawxml.xml").read_bytes().decode("utf-8")
        tree, old_tree = ET.fromstring(raw), ET.fromstring(prior_raw)
        rpm_nodes = tree.findall('./set-variable[@name="aiflux-poc-rpm"]')
        rt.require(len(rpm_nodes) == 1, "one_default_rpm_required")
        actual_rpm = rpm_nodes[0].get("value")
        rpm_nodes[0].set("value", "@(60)")
        safety_names = {"aiflux-" + n + "-threshold" for n in ("hate", "violence", "sexual", "self-harm")}
        safety = {n.get("name"): n.get("value") for n in tree.findall("./set-variable") if n.get("name") in safety_names}
        branches = tree.findall("./choose/when")
        old_branches = old_tree.findall("./choose/when")
        comparison = {
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "actual_raw_sha256": reads.sha(raw), "actual_canonical_sha256": pure.fingerprint(raw),
            "intended59_raw_sha256": reads.sha(rendered), "intended59_canonical_sha256": pure.fingerprint(rendered),
            "canonical_match_intended59": pure.fingerprint(raw) == pure.fingerprint(rendered),
            "strict_structure_match_intended59": reads.structure(raw) == reads.structure(rendered),
            "actual_default_rpm_expression": actual_rpm,
            "only_rpm60_to59_vs_prior_fragment": reads.structure(ET.tostring(tree, encoding="unicode")) == reads.structure(prior_raw),
            "current_bindings_equal_prior_exact_order": bindings == json.loads((PRIOR / "current-fragment-extracted-bindings.json").read_text(encoding="utf-8-sig")),
            "binding_count": len(bindings), "binding_sha256": fs.sha(bindings),
            "default_safety_four_ones": len(safety) == 4 and all(v == "@(1)" for v in safety.values()),
            "override_branches_exactly_preserved": [ET.tostring(n, encoding="unicode") for n in branches] == [ET.tostring(n, encoding="unicode") for n in old_branches],
            "override_organization": str(config.overrides[0].organization_id),
            "override_self_harm": config.overrides[0].safety.self_harm,
            "override_other_thresholds": [config.overrides[0].safety.hate, config.overrides[0].safety.violence, config.overrides[0].safety.sexual],
            "mandatory_scans_preserved_in_source_configuration": all(s.prompt_attack and s.input_filtering and s.output_filtering for s in [config.safety, config.overrides[0].safety]),
            "limitation": "Current APIM bindings extracted and insertion order retained; no claim about hidden revision11 stored binding order or whether recovery will skip PUT.",
        }
        reads.save(folder, "current-fragment-extracted-bindings.json", bindings)
        reads.save(folder, "parent-intended-revision11-configuration.json", desired)
        (folder / "intended59-current-bindings.xml").write_bytes(rendered.encode("utf-8"))
        reads.save(folder, "exact-fragment-comparison.json", comparison)
        print(json.dumps({"early_exact_fragment_evidence": report["evidence_directory"], **comparison}), flush=True)
        service = run.arm("")
        reads.save(folder, "apim-service.json", service)
        report["apim_provisioning_state"] = service.get("properties", {}).get("provisioningState")
        protected = reads.activation.snapshot()
        reads.save(folder, "protected-snapshot.json", protected)
        prior = json.loads((PRIOR / "protected-snapshot.json").read_text(encoding="utf-8-sig"))
        excluded = {"fragment_xml_sha256", "fragment_properties_sha256"}
        report["protected_except_fragment_equal"] = {key: protected.get(key) == prior.get(key) for key in set(prior) | set(protected) if key not in excluded}
        report["fragment_properties_equal_prior"] = protected["fragment_properties_sha256"] == prior["fragment_properties_sha256"]
        after = reads.exports(run, folder, "after")
        reads.save(folder, "after-summary.json", after)
        report["exports_stable_across_protected_read"] = before == after
        report["snapshot_binds_captured_fragment"] = protected["fragment_xml_sha256"] == before["fragment_rawxml_sha256"]
        report["fragment"] = before
        report["comparison"] = comparison
        # No logging settings changed, no historical log collector invoked.
        report["numeric_stage_logs"] = "Not collected: no readily available local revision11 numeric stage evidence established; no logging changes or cause inference."
        checks = [comparison[k] for k in ("canonical_match_intended59", "strict_structure_match_intended59", "only_rpm60_to59_vs_prior_fragment", "current_bindings_equal_prior_exact_order", "default_safety_four_ones", "override_branches_exactly_preserved", "mandatory_scans_preserved_in_source_configuration")]
        checks += [all(report["protected_except_fragment_equal"].values()), report["fragment_properties_equal_prior"], report["exports_stable_across_protected_read"], report["snapshot_binds_captured_fragment"], report["apim_provisioning_state"] == "Succeeded", before["fragment_provisioning_state"] == "Succeeded", before["fragment_etag_present"], before["fragment_export_etags_equal"], before["fragment_export_semantics_equal"], before["detached"]]
        report["status"] = "readonly_exact59_and_protected_baseline_verified" if all(checks) else "readonly_mismatch_observed"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["http_status"] = getattr(exc, "code", None)
    finally:
        report["prior_evidence_all_files_unchanged"] = prior_hashes == {p.name: reads.sha(p.read_bytes()) for p in PRIOR.iterdir() if p.is_file()}
        report["finished_at_utc"] = datetime.now(UTC).isoformat()
        reads.save(folder, "read-operations.json", reads.READS)
        report["evidence_sha256"] = {p.name: reads.sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()}
        reads.save(folder, "readiness.json", report)
        print(json.dumps(report), flush=True)
    return 0 if report["status"] == "readonly_exact59_and_protected_baseline_verified" else 2


def audit(folder):
    """Independent local verification; preserve all collector evidence unchanged."""
    load = lambda name: json.loads((folder / name).read_text(encoding="utf-8-sig"))
    report = load("readiness.json")
    before, after = load("before-summary.json"), load("after-summary.json")
    raw_bytes = (folder / "before-fragment-rawxml.xml").read_bytes()
    raw = raw_bytes.decode("utf-8")
    rendered = (folder / "intended59-current-bindings.xml").read_bytes().decode("utf-8")
    protected = load("protected-snapshot.json")
    prior = json.loads((PRIOR / "protected-snapshot.json").read_text(encoding="utf-8-sig"))
    excluded = {"fragment_xml_sha256", "fragment_properties_sha256"}
    result = {
        "at_utc": datetime.now(UTC).isoformat(), "offline_only": True,
        "evidence_hashes_verified": all(reads.sha((folder / name).read_bytes()) == digest for name, digest in report["evidence_sha256"].items()),
        "exact_raw_export_sha256": reads.sha(raw_bytes), "canonical_sha256": pure.fingerprint(raw),
        "raw_hash_matches_export_response_summary": reads.sha(raw_bytes) == before["fragment_rawxml_sha256"],
        "canonical_match_intended59": pure.fingerprint(raw) == pure.fingerprint(rendered),
        "strict_match_intended59": reads.structure(raw) == reads.structure(rendered),
        "protected_except_fragment_equal": all(protected.get(k) == prior.get(k) for k in set(prior) | set(protected) if k not in excluded),
        "protected_component_count_excluding_fragment": len((set(prior) | set(protected)) - excluded),
        "exports_stable": before == after,
        "prior_evidence_unchanged": report["prior_evidence_all_files_unchanged"],
        "raw_hash_correction": "Collector comparison read_text normalized CRLF. Authoritative raw hash is SHA256 of retained export bytes and matches before/after summary. Existing evidence retained, not overwritten.",
        "collector_status": report["status"], "cloud_configuration_writes": 0,
    }
    result["audit_passed"] = all(result[k] for k in ("evidence_hashes_verified", "raw_hash_matches_export_response_summary", "canonical_match_intended59", "strict_match_intended59", "protected_except_fragment_equal", "exports_stable", "prior_evidence_unchanged")) and report["status"] == "readonly_exact59_and_protected_baseline_verified"
    reads.save(folder, "independent-raw-byte-audit.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["audit_passed"] else 2


if __name__ == "__main__":
    if sys.argv[1] == "--audit":
        sys.exit(audit(Path(sys.argv[2]).resolve()))
    sys.exit(main(Path(sys.argv[1]).resolve()))