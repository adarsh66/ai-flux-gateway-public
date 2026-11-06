"""Retained local evidence only. No tests, network, Azure, database or deployment."""
import ast
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".validation/admin-archival-20261104/FINAL.json"
if OUT.exists():
    raise SystemExit("Final report already exists; do not replay this evidence stage")

paths = [
    "services/control-plane/src/aiflux/archival.py",
    "services/control-plane/src/aiflux/models.py",
    "services/control-plane/src/aiflux/schemas.py",
    "services/control-plane/src/aiflux/app.py",
    "services/control-plane/src/aiflux/apim.py",
    "services/control-plane/src/aiflux/subscriptions.py",
    "services/control-plane/src/aiflux/auth.py",
    "services/control-plane/src/aiflux/turnstile_exchange.py",
    "services/control-plane/src/aiflux/gateway_settings.py",
    "services/control-plane/src/aiflux/managed_controls.py",
    "services/control-plane/src/aiflux/poc_controls.py",
    "services/control-plane/src/aiflux/model_access.py",
    "services/control-plane/src/aiflux/model_access_publisher.py",
    "services/control-plane/migrations/versions/0007_admin_archival.py",
    "packages/ui/src/components/DeletionDialog.tsx",
    "packages/ui/src/client.ts",
    "packages/ui/src/types.ts",
    "packages/ui/src/styles.css",
    "packages/ui/src/pages/SubscriptionsPage.tsx",
    "packages/ui/src/pages/admin.tsx",
    "packages/ui/src/pages/TokenExchangePages.tsx",
    "packages/ui/src/admin-deletion.test.tsx",
    "tests/unit/test_admin_archival.py",
    "tests/unit/test_admin_archival_postgres.py",
    "scripts/validate_admin_archival.py",
    "scripts/validate_admin_archival_types.mjs",
]
hashes = {}
for name in paths:
    raw = (ROOT / name).read_bytes()
    if name.endswith(".py"):
        ast.parse(raw, filename=name)
    hashes[name] = hashlib.sha256(raw).hexdigest()

suite = ET.parse(ROOT / ".validation/admin-archival-20261104/backend-final03.xml").getroot().find("testsuite")
counts = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
by_file = {}
for case in suite.findall("testcase"):
    key = case.attrib["classname"]
    item = by_file.setdefault(key, {"passed": 0, "skipped": 0, "failed": 0})
    item["skipped" if case.find("skipped") is not None else "failed"
         if case.find("failure") is not None or case.find("error") is not None else "passed"] += 1

types = json.loads((ROOT / ".validation/admin-archival-20261104/typecheck03.json").read_text())
if counts["failures"] or counts["errors"] or any(p["exit"] != 0 for p in types["results"]):
    raise SystemExit("Validation failed; do not produce a successful final status")

report = {
    "at": datetime.now(UTC).isoformat(),
    "status": "source_implemented_release_gated",
    "scope": "terminal archive and access revocation; history retained; no hard deletion",
    "cloud_network_deployment_production_operations": 0,
    "public_ip_needed": False,
    "feature2_activation": False,
    "backend": counts,
    "backend_by_file": by_file,
    "typescript": types["results"],
    "frontend_authored_tests": len(re.findall(r"\bit\(", (ROOT / "packages/ui/src/admin-deletion.test.tsx").read_text())),
    "frontend_runtime_tests_run": False,
    "migration_target": "0007_admin_archival",
    "migration_parent": "0006_monthly_advisory_budgets",
    "paused_0005_in_migration_path": False,
    "migration_applied_to_production": False,
    "release_gates": [
        "Approved Linux frontend runtime tests/accessibility acceptance; local esbuild/Vitest remain prohibited",
        "Real PostgreSQL multisession lifecycle/concurrency, migration and runtime DML grants",
        "Approved APIM suspend/readback/async operation behavior and existing least-privilege access; no new grants assumed",
        "Unknown APIM write outcomes require operator reconciliation, never a state-only waiver",
        "Separate clean-parent release approval excluding paused Feature2 and preserving monthly budgets/APIM4096",
        "Separate selected disposable-entity approval before any real archive acceptance",
    ],
    "raw_source_sha256": hashes,
}
with OUT.open("x", encoding="utf-8") as output:
    json.dump(report, output, indent=2)
    output.write("\n")
print(json.dumps({key: report[key] for key in ("status", "backend", "frontend_authored_tests", "typescript")}))