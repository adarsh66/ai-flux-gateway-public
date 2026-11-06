"""Independent post-apply process: GET/state reads only, never retries a write."""
from copy import deepcopy
from datetime import UTC, datetime
import json
import os
import ssl
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler

from scripts.deployment import inventory_persistence_apply_once as a

r = a.r


def now():
    return datetime.now(UTC).isoformat()


def differences(left, right, prefix=""):
    """Only structural paths are persisted; never configuration values."""
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            path = prefix + "/" + key
            if key not in left or key not in right:
                result.append(path)
            else:
                result.extend(differences(left[key], right[key], path))
        return result
    return [] if left == right else [prefix]


def verify():
    out = a.HOME / "independent-live-verification01"
    a.require(not out.exists(), "existing_verification_reconcile_saved_evidence")
    r.fs.protect(out)

    def save(name, value):
        r.backend.save(out, name, value)

    report = {"started_at_utc": now(), "verification_pid": os.getpid(), "passed": False,
              "plan_sha256": a.PLAN_SHA, "source_sha256": a.SOURCE_SHA, "image": a.IMAGE,
              "mutation_commands": 0, "inference_requests": 0, "browser_verified": False,
              "parent_browser_confirmation_required": True}
    try:
        intent = r.old.load(a.HOME / "live-apply-intent.json")
        a.require(intent["plan_sha256"] == a.PLAN_SHA and intent["pid"] != os.getpid(), "independent_process_binding")
        save("artifact-integrity.json", a.integrity())
        r.transport()
        workers = r.backend.workers()
        save("workers-before.json", {"at_utc": now(), "workers": workers})
        a.require(not any(w["mutation_worker"] or w["name"].lower().startswith("terraform") for w in workers if w["pid"] != os.getpid()), "apply_worker_still_active_NO_RETRY")
        # Compare whole independent management-plane snapshot, normalizing ONLY
        # the separately authorized exact API image field.
        baseline = r.old.load(a.HOME / "baseline.json")
        live = r.release.snapshot()
        save("baseline-after.json", live)
        normalized = deepcopy(live)
        a.require(live["runtime"]["sites"]["api"]["image"] == "DOCKER|" + a.IMAGE, "exact_live_api_image_not_observed")
        normalized["runtime"]["sites"]["api"]["image"] = baseline["runtime"]["sites"]["api"]["image"]
        drift = differences(baseline, normalized)
        save("protected-comparison.json", {"at_utc": now(), "protected_components": len(live),
             "expected_image_only": True, "other_drift_paths": drift,
             "baseline_sha256": r.fs.sha(baseline), "normalized_after_sha256": r.fs.sha(normalized),
             "settings_equal": live["settings_hashes"] == baseline["settings_hashes"],
             "all_four_settings": sorted(live["settings_hashes"]),
             "other_images_equal": all(live["runtime"]["sites"][k]["image"] == baseline["runtime"]["sites"][k]["image"]
                                       for k in ("admin", "customer", "ingestion"))})
        a.require(len(live) == 13 and not drift, "STOP_postapply_protected_drift")
        supplement = a.supplemental(live)
        save("supplemental-after.json", supplement)
        a.require(supplement == r.old.load(a.HOME / "independent-validation01/supplemental-baseline.json")["protected"], "STOP_postapply_supplemental_drift")
        state = json.loads(a.tf_read("state", "pull"))
        save("state-after-private.json", state)
        before = r.old.load(a.OUT / "state-before-private.json")
        a.require(state["lineage"] == before["lineage"] and state["serial"] > before["serial"], "new_state_serial_same_lineage")
        api = [instance for resource in state["resources"] if resource["mode"] == "managed" and
               resource["type"] == "azurerm_linux_web_app" and resource["name"] == "main"
               for instance in resource["instances"] if instance.get("index_key") == "api"]
        a.require(len(api) == 1, "exact_api_state_owner")
        attrs = api[0]["attributes"]
        a.require(attrs["site_config"][0]["application_stack"][0]["docker_image_name"] == a.IMAGE.split("/", 1)[1], "exact_state_api_digest")
        head = r.backend.blob_head()
        save("state-head-after.json", head)
        a.require(head["lease_state"] == "available" and head["lease_status"] == "unlocked", "state_lock_released")
        a.require(head["etag"] != r.old.load(a.OUT / "state-head-before.json")["etag"], "state_write_observed")
        report.update(protected_components=13, all_other_protected_equal=True, supplemental_equal=True,
                      all_four_settings_equal=True, other_three_images_equal=True,
                      state_lineage=state["lineage"], state_serial_before=before["serial"], state_serial_after=state["serial"],
                      state_api_digest_verified=True, backend_lock_released=True)
        # Existing healthz only, unauthenticated, no redirects and no response body output.
        site = r.rt.arm(r.rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-api")
        hostname = site["properties"]["defaultHostName"]
        a.require(hostname.endswith(".azurewebsites.net") and "/" not in hostname, "existing_api_hostname")
        url = "https://" + hostname + "/healthz"

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=r.rt.CA)), NoRedirect())
        try:
            with opener.open(Request(url, method="GET"), timeout=90) as response:
                health = {"at_utc": now(), "url": url, "status": response.status, "authenticated": False,
                          "inference": False, "response_body_persisted": False}
        except HTTPError as exc:
            health = {"at_utc": now(), "url": url, "status": exc.code, "authenticated": False,
                      "inference": False, "response_body_persisted": False}
        except Exception as exc:
            health = {"at_utc": now(), "url": url, "status": None, "error_type": type(exc).__name__,
                      "authenticated": False, "inference": False, "response_body_persisted": False}
        save("http-health.json", health)
        report["http_health"] = health
        result_path = a.OUT / "apply-result.json"
        result = r.old.load(result_path) if result_path.exists() else None
        report["apply_result_present"] = result is not None
        report["apply_exit_code"] = result["exit_code"] if result else None
        report["apply_summary"] = result["summary"] if result else None
        report["live_and_state_image_applied"] = True
        a.require(result and result["exit_code"] == 0 and result["summary"] == [0, 1, 0], "live_state_reconciled_but_wrapper_not_confirmed_NO_RETRY")
        a.require(health["status"] == 200, "http_health_not_200_parent_must_review_NO_WRITE_RETRY")
        save("artifact-integrity-after.json", a.integrity())
        workers = r.backend.workers()
        report["active_workers"] = workers
        report["competing_mutation_workers"] = sum(w["mutation_worker"] for w in workers if w["pid"] != os.getpid())
        a.require(report["competing_mutation_workers"] == 0, "postverification_mutation_worker")
        report.update(passed=True, finished_at_utc=now(), status="applied_and_independently_verified_parent_browser_pending")
        save("verification.json", report)
        print(json.dumps(report), flush=True)
    except Exception as exc:
        report.update(finished_at_utc=now(), error_type=type(exc).__name__, http_status=getattr(exc, "code", None),
                      guard=str(exc) if isinstance(exc, RuntimeError) else "details_suppressed", retry_authorized=False)
        save("verification-failure.json", report)
        print(json.dumps(report), flush=True)
        raise SystemExit(2)


if __name__ == "__main__":
    verify()