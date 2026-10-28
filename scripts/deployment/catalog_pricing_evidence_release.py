"""Separate post-expiry API-only promotion; first correction is never replayed.

Refresh only deployment-read evidence after actual live parent/connections/model
verification and unchanged accepted route policy. No expiry relaxation/inference.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from scripts.deployment import catalog_pricing_release as controller
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.project_route_product_access import sha

FIRST = controller.HOME
HOME = rt.HOME / "catalog-pricing-evidence-renewal-20261027"
READBACK = rt.ROOT / "gateway/validation/catalog-inventory-renewal-readback-20261027.json"
SNAPSHOT = "gateway/catalog/foundry-inventory-20261026.json"
BASE_SOURCES = controller.sources


def renewal_guard(old, current, proof):
    expected = deepcopy(old)
    expected["verified_at"] = proof["at"]
    rt.require(current == expected and proof["snapshot_sha256"] == sha(
        (FIRST / "context" / SNAPSHOT).read_bytes()), "only_live_verified_timestamp_may_change")
    rt.require(proof["all_live_metadata_matches"] and proof["account_and_project_succeeded"]
               and proof["connections"] == 0 and proof["no_inference_no_writes"]
               and proof["freshness_limit_seconds_unchanged"] == 86400, "fresh_live_read_evidence_required")
    rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(proof["at"]) < timedelta(hours=2), "renewal_evidence_expired")


def sources():
    values = BASE_SOURCES()
    for path in (Path(__file__), rt.ROOT / "scripts/deployment/catalog_inventory_readback.py", READBACK,
                 rt.ROOT / "tests/unit/test_catalog_inventory_renewal.py"):
        values.append({"path": path.relative_to(rt.ROOT).as_posix(), "sha256": sha(path.read_bytes())})
    return sorted(values, key=lambda e: e["path"])


def plan():
    rt.require(not (HOME / "plan-intent.json").exists() and not (HOME / "apply-intent.json").exists(), "plan_already_attempted_never_replay")
    built = controller.release()
    before = controller.prior.baseline()
    first = json.loads((FIRST / "review.json").read_text())
    expected = deepcopy(first["baseline"])
    expected["protected"]["runtime"]["sites"]["api"]["image"] = "DOCKER|" + first["image"]
    rt.require(before == expected and (FIRST / "applied.json").exists(), "first_correction_protected_baseline_changed")
    pins = before["protected"]["runtime"]["sites"]
    variables = controller.prior.portals.runtime_variables({"results": {k: {"image": pins[k]["image"].removeprefix("DOCKER|")}
        for k in ("admin", "customer")}}, before["protected"]["runtime"])
    variables["apps"]["api"]["image"] = built["image"].split("/", 1)[1]
    rt.save(HOME / "images.tfvars.json", variables)
    with (HOME / "plan-intent.json").open("x") as handle:
        json.dump({"at": datetime.now(UTC).isoformat()}, handle)
    rt.tf(["init", "-input=false", "-lockfile=readonly", "-no-color"])
    rt.tf(["fmt", "-check"])
    rt.tf(["validate", "-no-color"])
    rt.tf(["plan", "-input=false", "-no-color", "-lock-timeout=60s",
           "-var-file=" + str(rt.HOME / "rebuild-platform.tfvars.json"),
           "-var-file=" + str(HOME / "images.tfvars.json"),
           "-var-file=" + str(rt.HOME / "jwt-runtime.tfvars.json"),
           '-target=azurerm_linux_web_app.main["api"]', "-out=" + str(controller.PLAN)])
    controller.guard(json.loads(rt.tf(["show", "-json", str(controller.PLAN)])), built["image"])
    review = {"at": datetime.now(UTC).isoformat(), "plan_sha256": sha(controller.PLAN.read_bytes()), "sources": sources(),
              "manifest_sha256": controller.manifest()["sha256"], "baseline": before, "image": built["image"],
              "tests": controller.test_proof(), "guard": "exact_one_api_image_only", "predecessor_plan_sha256": first["plan_sha256"],
              "renewal_evidence_at": json.loads(READBACK.read_text())["at"]}
    rt.save(HOME / "review.json", review)
    print(json.dumps({k: review[k] for k in ("at", "plan_sha256", "image", "guard", "predecessor_plan_sha256")}), flush=True)


def main():
    renewal_guard(json.loads((FIRST / "context" / SNAPSHOT).read_text()),
                  json.loads((rt.ROOT / SNAPSHOT).read_text()), json.loads(READBACK.read_text()))
    # Explicit, fixed separate run context. Exact-one guard and all protected
    # checks are shared unchanged, not modified to accept the old three-image plan.
    controller.HOME = HOME
    controller.PLAN = HOME / "api-only.tfplan"
    controller.REPORT = rt.ROOT / "gateway/validation/catalog-pricing-evidence-release-20261027.json"
    controller.VALIDATION_REPORT = rt.ROOT / "gateway/validation/catalog-pricing-evidence-validation-20261027.json"
    controller.TESTS = rt.ROOT / "gateway/validation/catalog-pricing-evidence-tests-20261027.xml"
    controller.sources = sources
    controller.plan = plan
    controller.main()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"errorType": type(error).__name__, "error": str(error) if isinstance(error, RuntimeError)
                          else "evidence_renewal_failed_sensitive_detail_suppressed"}), flush=True)
        raise SystemExit(1)