"""Offline final source/evidence binding. No cloud requests or release operations."""
from datetime import UTC, datetime
import json
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment import portal_fix as portals


def main():
    source_paths = ["services/control-plane/src/aiflux/" + p + ".py" for p in
                    ("decision_auth", "decision_client", "decision_router", "foundry_inventory", "external_inventory")]
    source_paths += ["tests/unit/test_decision_auto.py", "tests/contract/test_auto_gateway_policy.py",
        "tests/unit/test_auto_validation_runner.py", "scripts/validate_auto_routing.py",
        "scripts/deployment/auto_identity_readback.py", "gateway/policies/dev-openai.xml.tftpl",
        "gateway/policies/auto-resolve.xml.tftpl", "gateway/policies/auto-metadata.xml", "gateway/policies/auto-error.xml",
        "infra/project-route/auto-routing.tf", "packages/ui/src/token-exchange.test.tsx"]
    native = rt.HOME / "auto-routing-native-20261029T042445894316Z"
    evidence = [".deployment/auto-implementation-corrected-backend-20261029.xml",
        ".deployment/auto-full-thirteen-render-20261029.xml", ".deployment/auto-validation-runner-20261029.xml",
        ".deployment/auto-identity-readback-20261029T042927919100Z/readback.json"]
    evidence += [(native / p).relative_to(rt.ROOT).as_posix() for p in
                 ("result.json", "validation.log", "sources.json", "build-intent.json", "launcher-sources.json")]
    results = {}
    for path in evidence[:3]:
        suites = ET.parse(rt.ROOT / path).getroot().findall("testsuite")
        results[path] = {key: sum(int(s.get(key, "0")) for s in suites)
                         for key in ("tests", "failures", "errors", "skipped")}
    manifest = json.loads((native / "sources.json").read_text(encoding="utf-8"))
    unchanged = all(portals.digest((base / e["path"]).read_bytes()) == e["sha256"]
                    for e in manifest["entries"] for base in (rt.ROOT, native / "context"))
    rt.require(unchanged, "validated_ui_sources_changed")
    native_result = json.loads((native / "result.json").read_text(encoding="utf-8"))
    rt.require(native_result["passed"] and native_result["run_id"] == "cm35", "native_not_passed")
    report = {"at_utc": datetime.now(UTC).isoformat(), "offline_only": True,
        "source_hashes": {p: portals.digest((rt.ROOT / p).read_bytes()) for p in source_paths},
        "evidence_hashes": {p: portals.digest((rt.ROOT / p).read_bytes()) for p in evidence},
        "junit": results, "native": native_result, "ui_source_and_context_rechecked": unchanged,
        "cloud_writes_other_than_two_no_push_validation_runs": 0, "inference_requests": 0,
        "excluded": ["full backend suite", "historical .NET harness", "browser E2E", "live MI or scoring", "APIM C# runtime"]}
    folder = rt.HOME / ("auto-implementation-audit-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(exist_ok=False)
    rt.save(folder / "audit.json", report)
    print(json.dumps({"evidence": folder.relative_to(rt.ROOT).as_posix(), **report}, indent=2), flush=True)


if __name__ == "__main__":
    main()