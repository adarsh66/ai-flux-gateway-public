"""Fresh API-only source-bound validation/build; no runtime or policy apply."""
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from scripts.deployment import poc_activation_release as r
from scripts.deployment.poc_reliability_review import HOME
from scripts.deployment.fireworks_runtime import remote_build

ALLOWED = {"services/control-plane/src/aiflux/apim.py", "services/control-plane/src/aiflux/gateway_settings.py"}
TESTS = [*r.prep.BACKEND_TESTS, "test_poc_publisher_reliability.py"]


def manifest():
    original = r.prep.load(r.HOME / "sources.json")
    prior = {e["path"]: e["sha256"] for e in original["entries"]}
    paths = set(original["api_paths"])
    changed = {p for p in paths if r.sha((r.rt.ROOT / p).read_bytes()) != prior[p]}
    r.rt.require(changed == ALLOWED, "exact_two_api_source_fixes_only:" + ",".join(sorted(changed)))
    paths |= {"tests/unit/" + p for p in ["conftest.py", *TESTS]}
    paths |= {"gateway/policies/poc-settings-defaults.xml", "services/usage-ingestion/ingestion-approved.json"}
    paths |= {p.relative_to(r.rt.ROOT).as_posix() for p in (r.rt.ROOT / "gateway/tools").glob("*.py")}
    entries = [{"path": p, "sha256": r.sha((r.rt.ROOT / p).read_bytes())} for p in sorted(paths)]
    return {"entries": entries, "sha256": r.fs.sha(entries), "changed_api_paths": sorted(changed),
            "predecessor_source_sha256": original["source_sha256"]}


def check():
    value = manifest()
    r.rt.require(value == r.prep.load(HOME / "api-sources.json"), "fresh_api_source_drift")
    review = r.prep.load(HOME / "offline-review.json")
    r.rt.require(review["passed"] and all(r.sha((r.rt.ROOT / p).read_bytes()) == h for p, h in review["sources"].items()), "offline_review_source_binding")
    return value


def context(name):
    sources = check()
    folder = HOME / name / "context"
    for entry in sources["entries"]:
        path = r.rt.ROOT / entry["path"]
        r.rt.require(not path.is_symlink(), "source_symlink")
        target = folder / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(path.read_bytes())
    return folder


def native():
    r.rt.require(not (HOME / "api-native-intent.json").exists(), "existing_native_intent_reconcile_only")
    sources = manifest()
    r.exclusive(HOME, "api-sources.json", sources)
    check()
    before = r.snapshot()
    current = r.prep.load(r.HOME / "current_result.json")
    r.rt.require(before == current["baseline"], "fresh_baseline_drift_requires_review")
    r.exclusive(HOME, "baseline.json", before)
    r.exclusive(HOME, "api-native-intent.json", {"at": r.fs.stamp(), "source_sha256": sources["sha256"], "no_push": True})
    folder = context("api-native")
    docker = (folder / "services/control-plane/Dockerfile").read_text()
    docker += ('\nRUN python -m pip install --user --no-cache-dir pytest==8.4.0\n'
               'COPY tests/unit /app/tests/unit\nCOPY gateway/tools /app/gateway/tools\n'
               'COPY services/usage-ingestion/ingestion-approved.json /app/services/usage-ingestion/ingestion-approved.json\n'
               'COPY gateway/policies/poc-settings-defaults.xml /app/gateway/policies/poc-settings-defaults.xml\n'
               'RUN python -m pytest -q ' + " ".join("tests/unit/" + p for p in TESTS) + ' -k "not migration"\n')
    (folder / "PocReliabilityNative.Dockerfile").write_text(docker, encoding="utf-8")
    result = remote_build(folder, "PocReliabilityNative.Dockerfile")
    run = r.rt.cli(["acr", "task", "show-run", "-r", r.portals.REGISTRY, "--run-id", result["run_id"], "--subscription", r.rt.SUB])
    r.rt.require(r.prep.ui_native.no_published_images(run.get("outputImages")), "native_no_push_required")
    check()
    r.exclusive(HOME, "api-native.json", {**result, "source_sha256": sources["sha256"], "passed": True})
    print(json.dumps(r.prep.load(HOME / "api-native.json")), flush=True)


def build():
    sources = check()
    proof = r.prep.load(HOME / "api-native.json")
    r.rt.require(proof["passed"] and proof["source_sha256"] == sources["sha256"], "native_required")
    r.rt.require(r.snapshot() == r.prep.load(HOME / "baseline.json"), "prebuild_baseline_drift")
    tag = "poc-publisher-fix-" + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz")
    r.exclusive(HOME, "api-build-intent.json", {"at": r.fs.stamp(), "tag": tag, "source_sha256": sources["sha256"]})
    result = remote_build(context("api-build"), "services/control-plane/Dockerfile", "api", tag)
    check()
    r.exclusive(HOME, "api-build.json", {**result, "source_sha256": sources["sha256"]})
    print(json.dumps(r.prep.load(HOME / "api-build.json")), flush=True)


if __name__ == "__main__":
    {"native": native, "build": build}[sys.argv[1]]()