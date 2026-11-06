"""Fresh GET-only Auto release gate. No scoring, build, plan or apply entrypoint.

Existing noncurrent revisions are discovery candidates, never permission to
commandeer them. Runtime proof and reviewed isolation must precede publication.
"""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import backend_connection_restore_oct29 as backend
from scripts.deployment import inventory_persistence_release as persistence
from scripts.deployment import poc_activation_release as release
from scripts.deployment.auto_identity_readback import collection
from scripts.deployment.apim_route_repair import APIM

API = "aiflux-dev-unified"
VERSION = "2024-05-01"


def now():
    return datetime.now(UTC).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_revision(item):
    # ApiRevisionContract is flat (unlike the ARM API resource envelope).
    p = item
    # APIM revisions enumerate apiId rather than the top-level resource id.
    revision = str(p.get("apiRevision", ""))
    identifier = p.get("apiId", item.get("id", ""))
    expected = APIM + "/apis/" + API + ";rev=" + revision
    relative = "/apis/" + API + ";rev=" + revision
    return {"revision": revision, "api_id": identifier,
            "is_current": p.get("isCurrent"), "is_online": p.get("isOnline"),
            "existing_noncurrent_candidate": bool(revision.isdecimal()
                and p.get("isCurrent") is False
                and identifier.lower() in {expected.lower(), relative.lower()})}


def isolation_gate(apis, revisions):
    """Current protected APIs are never test targets, even if named validation."""
    candidates = [r for r in revisions if r["existing_noncurrent_candidate"]]
    protected = [a["name"] for a in apis
                 if str(a.get("path", "")).strip("/") in {"v1", "dev/v1"}]
    return {"existing_noncurrent_revisions": candidates,
            "protected_paths_excluded": sorted(protected),
            "safe_existing_test_target_proven": False,
            "blockers": (["no_existing_noncurrent_development_revision"] if not candidates else [])
                + ["actual_gateway_MI_scoring_contract_unproven"],
            "metadata_is_runtime_proof": False}


def require_no_competing_workers(workers):
    competing = [w for w in workers if w["pid"] != os.getpid()
                 and (w["mutation_worker"] or w["name"].lower().startswith("terraform"))]
    rt.require(not competing, "competing_worker_reconcile_no_replay")


def main():
    rt.require(len(sys.argv) == 1, "read_only_no_arguments")
    folder = rt.HOME / ("auto-live-gate-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    release.fs.protect(folder)
    report = {"started_at_utc": now(), "pid": os.getpid(),
              "cloud_configuration_writes": 0, "scoring_requests": 0,
              "completion_requests": 0, "image_builds": 0, "image_pushes": 0,
              "plans": 0, "applies": 0, "runtime_mi_access_proven": False,
              "auto_enabled_by_this_run": False, "release_validated": False,
              "evidence": folder.relative_to(rt.ROOT).as_posix()}

    def save(name, value):
        backend.save(folder, name, value)

    stage = "ownership"
    try:
        save("read-intent.json", {"at_utc": now(), "read_only": True,
             "scoring_budget": 0, "completion_budget": 0,
             "historical_replay_authorized": False})
        workers = backend.workers()
        save("workers-before.json", workers)
        require_no_competing_workers(workers)
        markers = backend.markers()
        save("historical-intents-before.json", markers)
        persistence.transport()
        rt.require(Path(rt.CA).is_file() and rt.ENV.get(
            "AZURE_CLI_DISABLE_CONNECTION_VERIFICATION", "").lower()
            not in {"true", "1", "yes"}, "strict_tls_required")
        account = rt.cli(["account", "show"])
        rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT,
                   "existing_account_context")
        stage = "existing_isolation_discovery"
        url = "https://management.azure.com" + APIM
        revisions = collection(url + "/apis/" + API + "/revisions?api-version=" + VERSION)
        save("revision-response-metadata.json", revisions)
        summarized = [summarize_revision(r) for r in revisions]
        save("existing-revisions.json", summarized)
        apis = collection(url + "/apis?api-version=" + VERSION)
        api_metadata = [{"id": a["id"], "name": a["name"],
                         **{k: a["properties"].get(k) for k in (
                             "path", "apiRevision", "isCurrent", "subscriptionRequired")}}
                        for a in apis]
        save("existing-apis.json", api_metadata)
        isolation_review = isolation_gate(api_metadata, summarized)
        save("isolation-gate.json", isolation_review)
        report["activation_blockers"] = isolation_review["blockers"]
        isolation = []
        # Inspect existing validation resources only; never create an API/revision.
        names = {API} | {a["name"] for a in apis
                        if "validation" in a["name"].lower() and ";" not in a["name"]}
        names |= {API + ";rev=" + r["revision"] for r in summarized
                  if r["existing_noncurrent_candidate"]}
        for name in sorted(names):
            ops = collection(url + "/apis/" + name + "/operations?api-version=" + VERSION)
            isolation.append({"api": name, "operations": [
                {"id": o["id"], "name": o["name"],
                 "method": o["properties"].get("method"),
                 "url_template": o["properties"].get("urlTemplate")}
                for o in ops]})
        save("existing-operations.json", isolation)
        report["noncurrent_revision_candidates"] = sum(
            r["existing_noncurrent_candidate"] for r in summarized)
        report["existing_validation_api_names"] = sorted(names - {API})
        stage = "protected_baseline"
        baseline = release.snapshot()
        save("protected-baseline.json", baseline)
        rt.require(len(baseline) == 13, "complete13_baseline")
        report["protected_components"] = len(baseline)
        report["protected_baseline_sha256"] = release.fs.sha(baseline)
        report["live_images"] = {k: v["image"] for k, v in baseline["runtime"]["sites"].items()}
        report["all_four_settings_hashed"] = sorted(baseline["settings_hashes"])
        stage = "supplemental_roles_rai_networks"
        from scripts.deployment.inventory_persistence_apply_once import supplemental
        supplement = supplemental(baseline)
        save("supplemental-baseline.json", supplement)
        report["supplemental_role_definitions"] = supplement["role_definition_count"]
        report["supplemental_rai_policies"] = supplement["rai_policy_count"]
        policy = release.ProductRun().policy()
        tree = ET.fromstring(policy)
        catalogs = [json.loads(n.text) for n in tree.findall(".//set-body")
                    if (n.text or "").startswith('{"data":')]
        aliases = sorted(m["id"] for m in catalogs[0]["data"]) if len(catalogs) == 1 else []
        rt.require(set(aliases) == release.MODELS and len(aliases) == 13, "exact13_live_aliases")
        auto_nodes = [n for n in tree.iter() if (n.get("id") or "").startswith("aiflux-auto")
                      or (n.get("name") or "").startswith("aiflux-auto")]
        report["live_auto_policy_nodes"] = len(auto_nodes)
        report["live_explicit_aliases"] = aliases
        report["live_auto_scoring_policy_present"] = bool(auto_nodes)
        rt.require(not auto_nodes, "unexpected_live_auto_policy_reconcile_before_release")
        settings = release.fs.current_settings()["api"]
        report["live_auto_feature_settings"] = {key: settings.get(key) for key in (
            "AIFLUX_AUTO_ROUTING_ENABLED", "AIFLUX_AUTO_ROUTING_GATEWAY_READY",
            "AIFLUX_AUTO_ROUTING_CONTRACT_VERIFIED")}
        stage = "state_owner_read"
        save("remote-state-head.json", backend.blob_head())
        local = rt.ROOT / "infra/project-route/terraform.tfstate"
        state = json.loads(local.read_bytes())
        save("project-state-owner.json", {"sha256": sha(local),
             "lineage": state["lineage"], "serial": state["serial"],
             "resource_addresses": sorted(r["type"] + "." + r["name"]
                                          for r in state["resources"] if r["mode"] == "managed")})
        stage = "protected_readback_comparison"
        readback = release.snapshot()
        save("protected-after.json", readback)
        rt.require(readback == baseline, "protected_drift_during_get_only_preflight")
        report["all13_protected_equal_before_after"] = True
        stage = "final_ownership"
        after = backend.markers()
        rt.require(all(after.get(k) == v for k, v in markers.items()), "historical_marker_drift")
        own = folder.relative_to(rt.ROOT).as_posix() + "/"
        rt.require(all(k.startswith(own) for k in set(after) - set(markers)), "foreign_release_intent")
        workers = backend.workers()
        save("workers-after.json", workers)
        require_no_competing_workers(workers)
        report.update(status="metadata_collected_actual_gateway_scoring_and_isolation_review_required",
                      failed_stage=None, finished_at_utc=now())
    except Exception as exc:
        report.update(status="blocked_no_release", failed_stage=stage,
                      error_type=type(exc).__name__, http_status=getattr(exc, "code", None),
                      guard=str(exc) if isinstance(exc, RuntimeError) else "details_suppressed",
                      finished_at_utc=now())
    save("result.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["status"].startswith("metadata_collected") else 2


if __name__ == "__main__":
    raise SystemExit(main())