"""Independent read-only handoff audit. Never builds, plans, applies or publishes."""
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys

from scripts.deployment import inventory_persistence_release as r


def audit(folder):
    review = r.old.load(folder / "review.json")
    manifest = r.package(folder)
    source = r.fs.sha(manifest)
    r.rt.require(review["source_sha256"] == source, "review_source_binding")
    for name in ("native-intent.json", "native02-intent.json", "build-intent.json", "plan-intent.json", "native.json", "build.json"):
        proof = r.old.load(folder / name)
        r.rt.require(proof["source_sha256"] == source, "immutable_intent_source_binding")
    for name, value in review["artifacts"].items():
        path = folder / name
        r.rt.require(path.resolve().is_relative_to(folder) and r.old.sha(path.read_bytes()) == value, "exact_saved_artifact_changed")
    for attempt in ("native", "native02"):
        r.rt.require(r.source_entries(folder / attempt / "context") == r.old.load(folder / (attempt + "-inputs.json")), "preserved_native_inputs")
    historical = r.old.load(folder / "historical-intents.json")
    current = r.backend.markers()
    r.rt.require(all(current.get(p) == h for p, h in historical.items()), "historical_intents_changed")
    new = {p for p in current if p not in historical}
    r.rt.require(all(p.startswith(folder.relative_to(r.rt.ROOT).as_posix() + "/") for p in new), "foreign_release_intent_created")
    r.transport()
    baseline = r.unchanged(folder, "final-independent-baseline")
    r.rt.require(r.fs.sha(baseline) == review["baseline_sha256"], "baseline_review_binding")
    root = folder / "plan/infra/terraform"
    plan = r.release.parsed(root, folder / "api-only.tfplan")
    companion = folder / "validation-only-NEVER-APPLY.tfplan"
    if companion.exists():
        plan = r.release.resolve(plan, r.release.parsed(root, companion), {r.ADDRESS})
    r.strict(plan, review["image"], baseline)
    r.fresh(folder)
    build = r.old.load(folder / "build.json")
    native = r.old.load(folder / "native.json")
    for proof in (native, build):
        run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", proof["run_id"], "--subscription", r.rt.SUB])
        r.rt.require(run["status"] == "Succeeded" and run["finishTime"] == proof["finished_at"], "remote_finished_run_binding")
        if proof is native:
            r.rt.require(r.no_published_images(run.get("outputImages")), "no_push_native")
        else:
            r.rt.require(run["outputImages"] == [{"digest": build["digest"], "registry": r.portals.HOST, "repository": "aiflux-api", "tag": build["tag"]}], "one_api_output_only")
    meta = r.rt.cli(["acr", "manifest", "show-metadata", "--registry", r.portals.REGISTRY,
        "--name", "aiflux-api:" + build["tag"], "--subscription", r.rt.SUB])
    r.rt.require(meta["digest"] == build["digest"] and review["image"] == build["image"], "immutable_remote_digest")
    log = (folder / "native02/native-validation-build.log").read_text(encoding="utf-8")
    r.rt.require('"persistence_attestation": "before"' in log and '"persistence_attestation": "after"' in log
        and "342 passed, 2 deselected" in log, "actual_native_log_evidence")
    r.rt.require(not list(folder.rglob("*apply-intent*")) and not (folder / "applied.json").exists(), "no_apply_allowed")
    workers = r.backend.workers()
    r.rt.require(not any(w["mutation_worker"] for w in workers), "current_mutation_worker_present")
    tooling = {p.relative_to(r.rt.ROOT).as_posix(): r.old.sha(p.read_bytes()) for p in (
        *[Path(m.__file__) for m in (r, r.old, r.release, r.fs, r.rt)], Path(__file__),
        r.rt.ROOT / "scripts/deployment/inventory_persistence_attestation.py",
        r.rt.ROOT / "scripts/deployment/project_route_product_access.py",
        r.rt.ROOT / "tests/unit/test_inventory_persistence_release.py",
        r.rt.ROOT / "tests/unit/test_inventory_persistent_acceptance.py")}
    result = {"at_utc": datetime.now(UTC).isoformat(), "status": "ready_for_parent_independent_validation_NOT_APPLIED",
        "source_sha256": source, "plan_sha256": review["plan_sha256"], "image": review["image"],
        "companion_sha256": r.old.sha(companion.read_bytes()) if companion.exists() else None,
        "full_current_protected_components": len(baseline), "all_settings_and_other_pins_preserved": True,
        "native_tests": native["tests_passed"], "historical_intents_unchanged": True,
        "mutation_workers": 0, "workers": workers, "tooling": tooling,
        "azure_validate_and_section7_completed": False, "applies": 0, "inference_requests": 0}
    r.save(folder, "handoff.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("workers", "tooling")}), flush=True)


if __name__ == "__main__":
    audit(Path(sys.argv[1]).resolve())