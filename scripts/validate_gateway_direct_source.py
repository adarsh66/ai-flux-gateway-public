"""Offline gateway-direct verification only; never deploy, initialize or infer."""
import argparse
from datetime import UTC, datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FOCUSED = ["tests/unit/test_decision_auto.py", "tests/unit/test_auto_snapshot.py",
    "tests/contract/test_auto_gateway_policy.py", "tests/contract/test_auto_gateway_expressions.py",
    "tests/unit/test_auto_validation_runner.py"]
REGRESSION = FOCUSED + ["tests/unit/test_control_plane.py", "tests/unit/test_admin_subscriptions.py",
    "tests/unit/test_turnstile_exchange.py", "tests/unit/test_foundry_inventory.py",
    "tests/unit/test_external_inventory.py", "tests/unit/test_external_metadata_renewal.py",
    "tests/unit/test_inventory_persistent_acceptance.py", "tests/unit/test_display_pricing.py",
    "tests/unit/test_gateway_settings.py", "tests/unit/test_managed_controls.py", "tests/unit/test_poc_controls.py",
    "tests/unit/test_portal_auth.py", "tests/unit/test_production_local_auth.py",
    "tests/unit/test_finops_ingestion.py", "tests/unit/test_model_tokens.py", "tests/unit/test_usage_filters.py",
    "tests/unit/test_usage_series.py", "tests/unit/test_usage_rankings.py", "tests/unit/test_config.py"]


def main(stage):
    folder = ROOT / ".deployment" / ("gateway-direct-" + stage + "-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, "CHECKPOINT_DISABLE": "1", "TF_INPUT": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    records = []
    def run(args, cwd=ROOT, stdin=None):
        result = subprocess.run(args, cwd=cwd, input=stdin, env=env, text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=600)
        text = result.stdout + result.stderr
        (folder / f"command-{len(records)+1}.log").write_text(text, encoding="utf-8")
        record = {"args": [str(a) for a in args], "cwd": str(cwd), "exit_code": result.returncode,
                  "log_sha256": hashlib.sha256(text.encode()).hexdigest()}
        records.append(record)
        print(text, flush=True)
        return result
    passed = True
    if stage in ("focused", "regression"):
        # Preserve collection failures in the result while allowing independent
        # suites to run; never turn a legacy import error into a green report.
        result = run([sys.executable, "-X", "utf8", "-m", "pytest", "-q",
            *(["--continue-on-collection-errors"] if stage == "regression" else []),
            *(FOCUSED if stage == "focused" else REGRESSION), f"--junitxml={folder / 'tests.xml'}"])
        passed = result.returncode == 0
    else:
        binary = shutil.which("terraform") or "C:/Program Files/Terraform/terraform.exe"
        module = ROOT / "infra/project-route"
        passed = run([binary, "validate", "-no-color"], cwd=module).returncode == 0
        # Windows Terraform records test paths with backslashes. A forward-slash
        # filter silently reports zero tests: require the actual seven passes.
        test = run([binary, "test", "-filter=" + str(Path("tests") / "auto-routing.tftest.hcl"), "-no-color"], cwd=module)
        passed &= test.returncode == 0 and bool(re.search(r"7 passed, 0 failed", test.stdout))
        for path in (module / "auto-routing.tf", module / "tests/auto-routing.tftest.hcl"):
            before = path.read_text(encoding="utf-8")
            formatted = run([binary, "fmt", "-"], cwd=module, stdin=before)
            equal = formatted.returncode == 0 and formatted.stdout == before
            passed &= equal
            if not equal:
                diff = "".join(difflib.unified_diff(before.splitlines(True), formatted.stdout.splitlines(True),
                    fromfile=path.name, tofile="formatted"))
                print(diff, flush=True)
                (folder / (path.name + ".diff")).write_text(diff, encoding="utf-8")
    report = {"at_utc": datetime.now(UTC).isoformat(), "stage": stage, "passed": bool(passed),
        "commands": records, "evidence": folder.relative_to(ROOT).as_posix(),
        "live_changes": False, "inference": False, "actual_apim_runtime_compilation": False}
    (folder / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("focused", "regression", "terraform"))
    raise SystemExit(main(parser.parse_args().stage))