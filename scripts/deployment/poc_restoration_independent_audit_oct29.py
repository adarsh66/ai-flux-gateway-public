"""Offline independent verification of retained after-restoration response bytes."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def load(folder, name):
    return json.loads((folder / name).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def delta(a, b, path=""):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return [p for k in sorted(a.keys() | b.keys()) for p in (
            [path + "/" + k] if k not in a or k not in b else delta(a[k], b[k], path + "/" + k))]
    if isinstance(a, list):
        return [path + "/length"] if len(a) != len(b) else [
            p for i, (x, y) in enumerate(zip(a, b)) for p in delta(x, y, path + "/" + str(i))]
    return [] if a == b else [path]


def main(folder):
    root = Path(__file__).resolve().parents[2]
    home = root / ".deployment"
    assert folder.parent == home and folder.name.startswith("poc-restoration-readonly-20261029-")
    prior = home / "poc-recovery-readonly-20261029-0110288510019-21404"
    # Restoration proof does not depend on the optional bounded log download.
    readiness = load(folder, "readiness.json") if (folder / "readiness.json").exists() else None
    completion = load(folder, "independent-completion-audit.json") if (folder / "independent-completion-audit.json").exists() else None
    before = load(folder, "before-summary.json")
    after = load(folder, "after-summary.json")
    raw = (folder / "after-fragment-rawxml.xml").read_bytes()
    canonical = hashlib.sha256(ET.canonicalize(raw.decode("utf-8"), strip_text=True).encode("utf-8")).hexdigest()
    response_deltas = {}
    unexpected = {}
    for kind in ("fragment", "policy"):
        for fmt in ("rawxml", "xml"):
            name = "after-" + kind + "-" + fmt + "-response.json"
            paths = delta(load(prior, name), load(folder, name))
            response_deltas[kind + "_" + fmt] = paths
            # Only exact HTTP observation timestamp and fragment HTTP ETag
            # may differ. No writable/body/runtime/APIM metadata is discarded.
            allowed = {"/http/at_utc"} | ({"/http/etag"} if kind == "fragment" else set())
            unexpected[kind + "_" + fmt] = [p for p in paths if p not in allowed]
    historical = load(folder, "historical-evidence-hashes-before.json")
    current_historical = {name: {p.name: digest(p) for p in (home / name).iterdir() if p.is_file()} for name in historical}
    operations = load(folder, "read-operations.json") if (folder / "read-operations.json").exists() else None
    approved_posts = {"/config/appsettings/list", "/containerlogs"}
    post_paths = [r["path"] for r in operations if r.get("method") == "POST"] if operations is not None else None
    checks = {
        "all_13_protected_components_exact_equal": len(load(folder, "protected-snapshot.json")) == 13 and load(folder, "protected-snapshot.json") == load(prior, "protected-snapshot.json"),
        "historical_evidence_unchanged": current_historical == historical,
        "fragment_raw_exact_original_bytes": raw == (prior / "after-fragment-rawxml.xml").read_bytes(),
        "fragment_raw_requested_hash": hashlib.sha256(raw).hexdigest() == "09c8c268d63490daeff42d8fbd414fd564743c325c32f72d7c553197f3b0896f",
        "fragment_canonical_requested_hash": canonical == "36af0cecf7ed9482ff8807f44474862c15dfa363918fc6d35e455b0ec6ae9edc",
        "export_stability": before == after,
        "apim_service_exact_original_without_ignored_paths": load(folder, "apim-service-before.json") == load(folder, "apim-service-after.json") == load(prior, "apim-service.json"),
        "apim_and_fragment_succeeded": load(folder, "apim-service-after.json")["properties"]["provisioningState"] == after["fragment_provisioning_state"] == "Succeeded",
        "no_unexpected_response_metadata_delta": not any(unexpected.values()),
        "policy_exact_original_bytes_both_exports": all((folder / ("after-policy-" + fmt + ".xml")).read_bytes() == (prior / ("after-policy-" + fmt + ".xml")).read_bytes() for fmt in ("xml", "rawxml")),
        "policy_detached_zero_includes": after["detached"] and after["policy_include_count"] == after["target_fragment_include_count"] == 0,
    }
    if readiness is not None:
        checks["collector_passed"] = readiness["status"] == "readonly_exact_original_restoration_verified"
        checks["all_manifest_hashes_verified"] = all(digest(folder / n) == h for n, h in readiness["evidence_sha256"].items())
    if completion is not None:
        checks["completion_passed"] = completion["audit_passed"]
    if post_paths is not None:
        checks["no_unapproved_post"] = all(any(p.endswith(suffix) for suffix in approved_posts) for p in post_paths)
    result = {"at_utc": datetime.now(UTC).isoformat(), "offline_only": True,
              "checks": checks, "audit_passed": all(checks.values()),
              "scope": "Independent complete restoration proof from retained original and fresh protected snapshots and exact exports; optional logs are not a prerequisite.",
              "collector_readiness_available": readiness is not None,
              "collector_worker_completion_available": completion is not None,
              "input_file_sha256": {p.name: digest(p) for p in folder.iterdir() if p.is_file()},
              "exact_response_delta_paths_vs_original": response_deltas,
              "unexpected_response_delta_paths": unexpected,
              "protected_delta_paths": delta(load(prior, "protected-snapshot.json"), load(folder, "protected-snapshot.json")),
              "canonical_sha256": canonical, "raw_sha256": hashlib.sha256(raw).hexdigest(),
              "documented_read_only_post_count": len(post_paths) if post_paths is not None else None,
              "observed_read_operation_count": len(operations) if operations is not None else None,
              "worker_after_capture": load(folder, "workers-after.json") if (folder / "workers-after.json").exists() else None,
              "completion_audit_sha256": digest(folder / "independent-completion-audit.json") if completion is not None else None,
              "readiness_sha256": digest(folder / "readiness.json") if readiness is not None else None,
              "source_sha256": digest(Path(__file__)), "cloud_configuration_writes": 0}
    with (folder / "independent-exact-response-audit.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result), flush=True)
    return 0 if result["audit_passed"] else 2


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]).resolve()))