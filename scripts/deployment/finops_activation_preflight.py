"""Read-only activation gate; never accepts a catalog merely because it has 11 rows.

No apply, configuration writes, host keys, provider named values, SQL, inference,
builds or runner provisioning. Failed acceptance cannot select a stale boundary.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError

from scripts.deployment import finops_function_stage as stage
from scripts.deployment import finops_release as release
from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt

TAG = "finops-20261027t040422z"
POLICY_SHA256 = "3f3ded3ec635482f4e8e61c46aa998dbb6a0d551efc8d2e47858741e423b1314"


def membership(catalog, routes, published):
    """Finite membership proof, not capability/runtime acceptance by itself."""
    expected = set(routes) | {"glm-5.3"}
    rt.require(len(routes) == 10 and "glm-5.3" not in routes, "approved_ten_plus_glm_required")
    rt.require(len(published) == len(set(published)) == 11 and set(published) == expected,
               "live_published_membership_not_approved")
    enabled = [m["id"] for m in catalog["models"] if m.get("enabled") is True]
    rt.require(len(enabled) == len(set(enabled)), "duplicate_packaged_alias")
    rt.require(not any(m.get("placeholder") and m.get("enabled") for m in catalog["models"]),
               "enabled_placeholder")
    return {"approved_aliases": sorted(expected), "packaged_aliases": sorted(enabled),
            "live_published_aliases": sorted(published),
            "missing_from_package": sorted(expected - set(enabled)),
            "package_not_live": sorted(set(enabled) - expected),
            "membership_matches": set(enabled) == expected,
            "catalog_accepted": False}


def published_aliases(policy):
    # APIM rawxml includes unescaped C# expression operators; XML parsing is not
    # valid for that representation. Extract only a literal JSON discovery body.
    found = []
    for text in re.findall(r"<set-body(?:\s[^>]*)?>(.*?)</set-body>", policy, re.S):
        try:
            body = json.loads(text.strip())
        except ValueError:
            continue
        if isinstance(body, dict) and isinstance(body.get("data"), list):
            found.append([m["id"] for m in body["data"]])
    rt.require(len(found) == 1, "single_literal_discovery_required")
    return found[0]


def collect():
    os.environ["REQUESTS_CA_BUNDLE"] = rt.CA
    from scripts.deployment.project_route_live import CandidateRun

    folder = rt.HOME / "finops" / TAG
    disabled = folder / stage.STAGE_NAME
    applied = json.loads((disabled / "applied.json").read_text())
    review = json.loads((disabled / "review.json").read_text())
    rt.require(applied["applied"] and applied["plan_sha256"] == review["plan_sha256"],
               "prior_disabled_stage_apply_required")
    images = stage.built(folder)  # Actual remote run/digest and current-source proof.
    rt.require(images == review["images"], "applied_images_changed")
    manifest = json.loads((folder / "source-manifest.json").read_text())
    name = "gateway/catalog/dev-models.json"
    packaged = folder / "context" / name
    entry = next(e for e in manifest["components"]["ingestion"]["entries"] if e["path"] == name)
    rt.require(release.digest(packaged.read_bytes()) == entry["sha256"] and
               packaged.read_bytes() == (rt.ROOT / name).read_bytes(), "packaged_catalog_source_binding")
    policy = CandidateRun().arm("/apis/aiflux-dev-unified/policies/policy?format=rawxml")["properties"]["value"]
    policy_hash = release.digest(policy.encode())
    rt.require(policy_hash == POLICY_SHA256, "observed_gateway_policy_drift")
    routes = json.loads((rt.ROOT / "gateway/catalog/project-routes.json").read_text())["routes"]
    catalog = membership(json.loads(packaged.read_text()), routes, published_aliases(policy))
    catalog.update(packaged_catalog_sha256=entry["sha256"], live_policy_sha256=policy_hash,
                   image_source_binding_verified=True, independent_running_filesystem_attested=False)
    current = portals.baseline()
    expected = json.loads((disabled / "baseline.json").read_text())
    for kind in release.COMPONENTS:
        expected["sites"][kind]["image"] = "DOCKER|" + images[kind]
    expected["sites"]["ingestion"]["protected"]["web"].update(
        acrUseManagedIdentityCreds=True, acrUserManagedIdentityID=review["client_id"])
    rt.require(current == expected, "protected_applied_baseline_drift")
    settings = stage.current_settings()
    hashes = json.loads((disabled / "settings-hashes.json").read_text())
    rt.require(all(stage.ingestion_settings_verified(settings[k], review["post_apply_expected_settings_hash"])
                   if k == "ingestion" else stage.sha(settings[k]) == hashes[k]
                   for k in release.COMPONENTS), "applied_settings_drift")
    storage = rt.cli(["storage", "account", "show", "--name", "projpoctokenex", "--resource-group",
                      "IDS-TOKEN-EXCHANGE-POC", "--subscription", rt.SUB])["networkRuleSet"]
    ips = sorted(r["ipAddressOrRange"] for r in storage["ipRules"])
    rt.require(storage["defaultAction"] == "Deny" and ips ==
               ["167.103.65.36", "167.103.66.248", "167.103.66.93"], "state_storage_acl_drift")
    rid = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-ingestion"
    host = rt.arm(rid)["properties"]
    try:
        functions = rt.arm(rid + "/functions")["value"]
        discovery = {"http_status": 200, "function_names": sorted(f["name"].split("/")[-1] for f in functions)}
    except HTTPError as exc:
        discovery = {"http_status": exc.code, "function_names": None}
    previous_path = rt.ROOT / "gateway/validation/finops-fresh-execution-b2b8ad1f981b.json"
    previous = json.loads(previous_path.read_text())
    probes = {}
    for kind in ("ingestion", "api"):
        p = previous["probes"][kind]
        snapshot = p["sanitized_result"]
        rt.require(p["probe_exit_code"] == 0 and snapshot["status"] == "verified_read_only_snapshot"
                   and snapshot["database_writes"] == 0 and snapshot["identity_role_matches"]
                   and snapshot["runtime_ddl_or_ownership"] is False, "retained_db_proof_invalid")
        probes[kind] = {"collected_at": snapshot["collected_at"], "historical_not_fresh_db_read": True,
                       "table_privileges": snapshot["table_privileges"], "checkpoint": snapshot["checkpoint"],
                       "all_time": snapshot["all_time"], "runtime_ddl_or_ownership": False}
    return {"at_utc": stage.stamp(), "status": "blocked_packaged_catalog_mismatch" if not catalog["membership_matches"]
            else "membership_only_remaining_runtime_gates", "tag": TAG, "images": images,
            "prior_apply_replayed": False, "prior_plan_sha256": applied["plan_sha256"],
            "catalog": catalog, "protected_baseline_verified": True, "all_settings_hashes_verified": True,
            "host": {"state": host["state"], "enabled": host["enabled"],
                     "public_network_access": host["publicNetworkAccess"],
                     "timer_disabled": settings["ingestion"].get("AzureWebJobs.ingest_usage.Disabled"),
                     "catalog_configured": settings["ingestion"].get("AIFLUX_CATALOG_CONFIGURED"),
                     "start_at": settings["ingestion"].get("AIFLUX_INGESTION_START_AT")},
            "functions_discovery": discovery, "state_storage": {"default_action": "Deny", "ips": ips},
            "postgres_public_network_access": current["postgres"]["network"]["publicNetworkAccess"],
            "postgres_firewall_rule_count": len(current["postgresRules"]), "retained_private_db_proofs": probes,
            "retained_db_evidence_sha256": release.digest(previous_path.read_bytes()),
            "intent": {"mode": "forward_only_delegated", "historical_cutoff_approved": False,
                       "historical_requests_deferred": 156, "historical_tokens_deferred": 11143,
                       "activation_start_at": None, "boundary_selection": "after_catalog_gate_before_host_start",
                       "existing_watermark_must_be_preserved": True},
            "cloud_writes": 0, "database_writes": 0, "new_builds": 0, "new_runners": 0,
            "scheduled_successes_verified": 0, "live_ingestion_accepted": False}


def main():
    report = collect()
    target = rt.ROOT / "gateway/validation" / ("finops-activation-preflight-" +
        datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    rt.require(not target.exists(), "evidence_collision")
    rt.save(target, report)
    print(json.dumps({"evidence": target.relative_to(rt.ROOT).as_posix(), **report}), flush=True)
    return 2 if report["status"].startswith("blocked") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "blocked", "exception_type": type(exc).__name__,
                          "reason": str(exc) if isinstance(exc, RuntimeError) else "protected_preflight_failed",
                          "cloud_writes": 0}), flush=True)
        raise SystemExit(2)