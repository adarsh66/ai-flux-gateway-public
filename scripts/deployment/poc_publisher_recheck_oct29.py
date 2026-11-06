"""One fresh read-only preflight; never invoke historical release entrypoints."""
from contextlib import redirect_stdout
from datetime import UTC, datetime
import base64
import json
from pathlib import Path
import re
import ssl
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import poc_activation_release as activation
from scripts.deployment import customer_login_release as customer
from scripts.deployment import glm_resume
from scripts.deployment.apim_route_repair import APIM
from scripts.deployment.poc_fragment_bootstrap import FRAGMENT, ID
from scripts.deployment.poc_fragment_readback import structure
from scripts.deployment.project_route_product_access import ProductRun, sha

READS = []
EXPECTED = {"api": "b489df", "admin": "2846f1", "customer": "a30d513", "ingestion": "fad3"}


def save(folder, name, data):
    with (folder / name).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def cli_read(args):
    allowed = (args[:2] in (["account", "show"], ["account", "get-access-token"])
               or args[:3] == ["role", "assignment", "list"]
               or (args[:3] == ["rest", "--method", "get"]
                   and args[3] == "--url"
                   and args[4].startswith("https://management.azure.com" + rt.RG + "/providers/")))
    rt.require(allowed, "nonread_cli_rejected")
    result = subprocess.run(rt.CLI + args + ["--only-show-errors", "-o", "json"],
                            cwd=rt.ROOT, env=rt.ENV, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120)
    READS.append({"kind": "cli_read", "command": args[:3], "exit_code": result.returncode})
    if result.returncode:
        expired = bool(re.search(r"AADSTS\d+|az login|expired|reauthenticat|interaction.required", result.stderr, re.I))
        raise RuntimeError("cli_login_needed" if expired else "cli_read_failed")
    return json.loads(result.stdout.lstrip("\ufeff"))


class ReadOnlyProductRun(ProductRun):
    """Use only GET against the exact APIM service, retaining HTTP metadata."""

    def __init__(self):
        # Do not initialize ProductRun: its historical isolated-state existence
        # check is irrelevant here. No Terraform or backend access is needed.
        self.tls = ssl.create_default_context(cafile=rt.CA)
        self.token = ""
        self.headers = {}

    def arm(self, suffix, method="GET"):
        rt.require(method == "GET" and (not suffix or suffix.startswith("/"))
                   and ".." not in suffix, "nonread_arm_rejected")
        if not self.token:
            self.token = rt.cli(["account", "get-access-token", "--subscription", rt.SUB,
                                 "--resource", "https://management.azure.com/"])["accessToken"]
            part = self.token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
            rt.require(claims.get("tid") == rt.TENANT and claims.get("oid") == rt.OPERATOR,
                       "token_identity")
        url = "https://management.azure.com" + APIM + suffix
        url += ("&" if "?" in suffix else "?") + "api-version=2024-05-01"
        req = Request(url, method="GET", headers={"Authorization": "Bearer " + self.token})
        with urlopen(req, context=self.tls, timeout=60) as response:
            body = response.read(8 * 1024 * 1024 + 1)
            rt.require(len(body) <= 8 * 1024 * 1024, "bounded_arm_response")
            self.headers[suffix] = {"status": response.status, "etag": response.headers.get("ETag"),
                                    "at_utc": datetime.now(UTC).isoformat()}
            READS.append({"kind": "apim_get", "suffix": suffix, "status": response.status})
            return json.loads(body)


def exports(run, folder, label):
    result = {}
    for kind, path in (("policy", "/apis/aiflux-dev-unified/policies/policy"),
                       ("fragment", "/policyFragments/" + FRAGMENT)):
        for fmt in ("rawxml", "xml"):
            suffix = path + "?format=" + fmt
            data = run.arm(suffix)
            if kind == "fragment":
                rt.require(data["id"].lower() == ID.lower(), "fragment_exact_identity")
            value = data["properties"]["value"]
            rt.require(isinstance(value, str) and bool(value), "empty_xml_export")
            (folder / (label + "-" + kind + "-" + fmt + ".xml")).write_bytes(value.encode("utf-8"))
            save(folder, label + "-" + kind + "-" + fmt + "-response.json",
                 {"body": data, "http": run.headers[suffix]})
            result[kind + "_" + fmt] = {"body": data, "http": run.headers[suffix], "value": value}
    raw, xml = result["fragment_rawxml"], result["fragment_xml"]
    raw_semantics = structure(raw["value"])
    xml_semantics = structure(xml["value"], export_layer=True)
    tree = ET.fromstring(result["policy_xml"]["value"])
    includes = tree.findall(".//include-fragment")
    target_includes = [n for n in includes if n.get("fragment-id") == FRAGMENT]
    properties = raw["body"]["properties"]
    etag = raw["http"]["etag"]
    return {
        "policy_xml_sha256": sha(result["policy_xml"]["value"]),
        "policy_rawxml_sha256": sha(result["policy_rawxml"]["value"]),
        "policy_etag_sha256": sha(result["policy_xml"]["http"]["etag"] or ""),
        "policy_include_count": len(includes), "target_fragment_include_count": len(target_includes),
        "detached": not target_includes and FRAGMENT not in result["policy_rawxml"]["value"],
        "fragment_rawxml_sha256": sha(raw["value"]), "fragment_xml_sha256": sha(xml["value"]),
        "fragment_semantic_sha256": fs.sha(raw_semantics),
        "publisher_canonical_sha256": sha(ET.canonicalize(raw["value"], strip_text=True)),
        "fragment_export_semantics_equal": raw_semantics == xml_semantics,
        "fragment_properties_sha256": fs.sha({k: v for k, v in properties.items() if k != "value"}),
        "fragment_provisioning_state": properties.get("provisioningState"),
        "fragment_etag_present": isinstance(etag, str) and bool(etag) and etag != "*" and len(etag) <= 200,
        "fragment_etag_sha256": sha(etag or ""),
        "fragment_export_etags_equal": etag == xml["http"]["etag"],
        "fragment_exact_identity": True,
        "normalization": "Strict parsed structure; only inter-element indentation ignored; xml export decoded exactly one entity layer",
    }


def main(folder):
    rt.require(folder.parent == rt.HOME and folder.name.startswith("poc-publisher-recheck-20261029-"),
               "fresh_evidence_scope")
    rt.require(folder.is_dir() and not (folder / "readiness.json").exists(), "exclusive_evidence_required")
    report = {"started_at_utc": datetime.now(UTC).isoformat(), "status": "blocked",
              "cloud_configuration_writes": 0, "settings_list_operations_are_read_only": True,
              "state_backend_access": False, "user_ip_is_network_approval": False,
              "publication_attempts": 0, "reconcile_requests": 0, "inference_requests": 0,
              "browser_actions": 0, "blockers": [], "evidence_directory": folder.relative_to(rt.ROOT).as_posix()}
    stage = "azure_bestpractices"
    try:
        with (folder / "azure-bestpractices.txt").open("x", encoding="utf-8") as handle, redirect_stdout(handle):
            glm_resume.bestpractices()
        report["azure_bestpractices_invoked"] = True
        rt.cli = cli_read
        activation.ProductRun = ReadOnlyProductRun
        stage = "account"
        customer.account()
        report["correct_subscription_tenant_account_verified"] = True
        stage = "apim_exports_before"
        run = ReadOnlyProductRun()
        service = run.arm("")
        report["apim_provisioning_state"] = service.get("properties", {}).get("provisioningState")
        report["apim_service_sha256"] = fs.sha(service)
        save(folder, "apim-service.json", service)
        before = exports(run, folder, "before")
        save(folder, "before-summary.json", before)
        stage = "fresh_complete_protected_snapshot"
        protected = activation.snapshot()
        save(folder, "protected-snapshot.json", protected)
        report["protected_snapshot_sha256"] = fs.sha(protected)
        report["settings_hash_components"] = sorted(protected["settings_hashes"])
        report["runtime_image_pins"] = {k: v["image"].rsplit("@sha256:", 1)[-1]
                                         for k, v in protected["runtime"]["sites"].items()}
        report["expected_image_prefix_matches"] = {k: report["runtime_image_pins"][k].startswith(v)
                                                     for k, v in EXPECTED.items()}
        report["protected_components"] = sorted(protected)
        report["active_product_subscription_count"] = len(protected["product_subscriptions"])
        stage = "apim_exports_after"
        after = exports(run, folder, "after")
        save(folder, "after-summary.json", after)
        report.update(after)
        report["exports_stable_across_snapshot"] = before == after
        report["snapshot_binds_exact_policy_and_fragment"] = (
            protected["active_policy_sha256"] == after["policy_xml_sha256"]
            and protected["fragment_xml_sha256"] == after["fragment_rawxml_sha256"]
            and protected["fragment_properties_sha256"] == after["fragment_properties_sha256"])
        checks = {
            "fragment_not_detached": after["detached"],
            "fragment_not_ready": after["fragment_provisioning_state"] == "Succeeded",
            "fragment_etag_missing": after["fragment_etag_present"],
            "fragment_export_semantic_mismatch": after["fragment_export_semantics_equal"],
            "fragment_export_etag_changed": after["fragment_export_etags_equal"],
            "apim_not_succeeded": report["apim_provisioning_state"] == "Succeeded",
            "apim_changed_during_collection": report["exports_stable_across_snapshot"],
            "snapshot_xml_binding_mismatch": report["snapshot_binds_exact_policy_and_fragment"],
            "unexpected_runtime_image_pin": all(report["expected_image_prefix_matches"].values()),
        }
        report["blockers"] = [name for name, passed in checks.items() if not passed]
        report["status"] = "arm_preflight_passed_ui_state_pending" if not report["blockers"] else "blocked"
        report["limitations"] = ["Normal-UI settings version/state/history and authorization remain parent-owned",
                                  "HTTP502 persistence cannot be established by reads",
                                  "Preserve actual current XML; no historical defaults or revision assumed",
                                  "Snapshot is a fresh baseline, not a comparison proving equality to a historical release"]
    except Exception as exc:
        report["failed_stage"] = stage
        report["error_type"] = type(exc).__name__
        report["http_status"] = exc.code if isinstance(exc, HTTPError) else None
        safe = str(exc) if isinstance(exc, RuntimeError) and re.fullmatch(r"[a-z_]+", str(exc)) else "read_only_collection_failed"
        report["blockers"].append(safe)
    finally:
        report["finished_at_utc"] = datetime.now(UTC).isoformat()
        save(folder, "read-operations.json", READS)
        report["evidence_sha256"] = {p.name: sha(p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()}
        save(folder, "readiness.json", report)
        print(json.dumps(report), flush=True)
    return 0 if not report["blockers"] else 2


def audit(folder):
    """Offline completion audit, including worker-after proof; no Azure calls."""
    rt.require(folder.parent == rt.HOME and folder.name.startswith("poc-publisher-recheck-20261029-"),
               "evidence_scope")
    load = lambda name: json.loads((folder / name).read_text(encoding="utf-8-sig"))
    report = load("readiness.json")
    artifact_checks = {name: sha((folder / name).read_bytes()) == digest
                       for name, digest in report["evidence_sha256"].items()}
    markers = load("historical-marker-metadata.json")
    marker_checks = [sha((rt.ROOT / row["path"]).read_bytes()) == row["sha256"] for row in markers]
    workers = load("workers-before.json") + load("workers-after.json")
    conflicts = [w for w in workers if w["mutation_worker"] and not w["this_collector"]]
    executors = [w for w in load("workers-after.json")
                 if re.search(r"python|terraform", w["name"], re.I)]
    raw = (folder / "after-fragment-rawxml.xml").read_bytes().decode("utf-8")
    tree = ET.fromstring(raw)
    safety_names = {"aiflux-" + n + "-threshold" for n in ("hate", "violence", "sexual", "self-harm")}
    defaults = [n for n in tree.findall("./set-variable") if n.get("name") in safety_names]
    overrides = [n for n in tree.findall("./choose/when/set-variable") if n.get("name") in safety_names]
    summary = {
        "at_utc": datetime.now(UTC).isoformat(), "offline_only": True,
        "status": report["status"], "blockers": list(report["blockers"]),
        "evidence_hashes_verified": all(artifact_checks.values()),
        "historical_marker_count": len(markers), "historical_marker_hashes_unchanged": all(marker_checks),
        "mutation_workers_observed": len(conflicts), "python_or_terraform_workers_after": len(executors),
        "workers_before_after_identical": load("workers-before.json") == load("workers-after.json"),
        "actual_default_safety_is_four_ones": len(defaults) == 4 and all(n.get("value") == "@(1)" for n in defaults),
        "actual_safety_override_assignments_present": bool(overrides),
        "actual_zero_self_harm_override_present": any(n.get("name") == "aiflux-self-harm-threshold"
                                                       and n.get("value") == "@(0)" for n in overrides),
        "actual_fragment_preserved_without_modification": True,
        "restore_target": "Use exact fresh pre-test UI configuration and private fragment exports, not historical revision8 defaults",
        "fragment_rawxml_sha256": report["fragment_rawxml_sha256"],
        "protected_snapshot_file_sha256": sha((folder / "protected-snapshot.json").read_bytes()),
        "protected_snapshot_object_sha256": report["protected_snapshot_sha256"],
        "readiness_file_sha256": sha((folder / "readiness.json").read_bytes()),
        "worker_after_file_sha256": sha((folder / "workers-after.json").read_bytes()),
        "collector_source_sha256": sha(Path(__file__).read_bytes()),
        "cloud_configuration_writes": 0,
    }
    if not all(artifact_checks.values()) or not all(marker_checks):
        summary["blockers"].append("local_evidence_changed")
    if conflicts or executors:
        summary["blockers"].append("worker_review_required")
    if summary["blockers"]:
        summary["status"] = "blocked"
    save(folder, "completion-audit.json", summary)
    print(json.dumps(summary), flush=True)
    return 0 if not summary["blockers"] else 2


if __name__ == "__main__":
    if sys.argv[1] == "--audit":
        sys.exit(audit(Path(sys.argv[2]).resolve()))
    sys.exit(main(Path(sys.argv[1]).resolve()))