"""One focused offline composition/import/typecheck pass; never replay outputs."""
import ast
import hashlib
import importlib
import json
from pathlib import Path
import socket
import subprocess
import sys

from scripts.deployment.auto_additive_clean import (
    API_FULL, API_PROD, DEP, OUT, PREFIX, ROOT, load, record, sha, text, tree,
)


def deny(*args, **kwargs):
    raise RuntimeError("network prohibited in clean composition checks")


def main():
    record(OUT / "checks/intent.json", {"focused": True, "replay": False})
    report = {"cloud_reads": 0, "cloud_writes": 0, "builds": 0, "paid_calls": 0}
    try:
        socket.create_connection = deny
        socket.socket.connect = deny
        sys.dont_write_bytecode = True
        effective = OUT / "checks/effective"
        sys.path.insert(0, str(ROOT / ".venv/Lib/site-packages"))
        sys.path.insert(0, str(effective / "services/control-plane/src"))
        manifest = load(OUT / "source-manifest.json")
        for kind, files in manifest["contexts"].items():
            assert tree(OUT / "contexts" / kind) == files
        assert tree(DEP / "auto-additive01") == manifest["retained_additive01"]
        package = effective / PREFIX
        parsed = 0
        for file in package.rglob("*.py"):
            ast.parse(file.read_text(encoding="utf-8"), feature_version=(3, 11))
            parsed += 1
        baseline = ast.parse((API_PROD / "contexts/api/modules/app.py").read_text())
        composed = ast.parse((package / "app.py").read_text())
        composed.body = [node for node in composed.body if not (
            isinstance(node, ast.ImportFrom) and node.module == "aiflux.auto_availability")]
        create = next(n for n in composed.body if isinstance(n, ast.FunctionDef) and n.name == "create_app")
        new_endpoint = next(n for n in create.body if isinstance(n, ast.FunctionDef) and n.name == "auto_routing_availability")
        assert [a.arg for a in new_endpoint.args.args] == ["principal", "db"]
        assert ast.unparse(new_endpoint.args.args[0].annotation) == "User"
        assert ast.unparse(new_endpoint.args.args[1].annotation) == "Db"
        create.body.remove(new_endpoint)
        assert ast.dump(composed) == ast.dump(baseline), "unrelated entrypoint delta"
        config = importlib.import_module("aiflux.config")
        snap = importlib.import_module("aiflux.auto_snapshot")
        ready = importlib.import_module("aiflux.auto_availability")
        settings = config.Settings(_env_file=None, environment="testing", local_auth_enabled=True,
            foundry_inventory_path=effective / "gateway/catalog/foundry-inventory-20261026.json",
            external_inventory_path=effective / "gateway/catalog/external-inventory.json",
            catalog_path=effective / "gateway/catalog/models.json",
            auto_routing_snapshot_inventory_path=package / "pricing/auto-routing-inventory.json")
        assert ready.availability(settings) == {"ready": False, "profiles": []}
        settings.auto_routing_enabled = True
        snapshot = snap.defaults(settings)
        assert snapshot["version"] == sha((package / "pricing/auto-routing-defaults.json").read_bytes())
        assert set(snapshot["profiles"]) == {"balanced", "cost", "quality"}
        assert len(snapshot["candidates"]) == 6
        assert ready.availability(settings) == {"ready": False, "profiles": []}, "no publication must stay closed"
        # Negative compatibility check: preserve current full inventory, reject
        # a genuine candidate semantic delta, without writing any evidence receipt.
        inv_module = importlib.import_module("aiflux.external_inventory")
        original_load = inv_module.AcceptedInventory.load
        def altered(value):
            inv = original_load(value)
            if value.foundry_inventory_path == settings.foundry_inventory_path:
                inv.foundry.routes[0].model_version = "unreviewed-drift"
                for route in inv.foundry.routes:
                    if route.alias == snapshot["candidates"][0]["id"]:
                        route.model_version = "unreviewed-drift"
            return inv
        inv_module.AcceptedInventory.load = altered
        try:
            try:
                snap.defaults(settings)
            except ValueError:
                pass
            else:
                raise AssertionError("candidate drift accepted")
        finally:
            inv_module.AcceptedInventory.load = original_load
        app = importlib.import_module("aiflux.app")
        assert Path(app.__file__).resolve() == (package / "app.py").resolve()
        routes = {route.path for route in app.app.routes}
        assert "/api/auto-routing/availability" in routes
        assert "/internal/auto-routing/resolve" not in routes
        assert "/api/admin/auto-routing/initialize" not in routes
        # All existing non-overlay dependency bytes must remain production-bound.
        for name in ("display_pricing.py", "external_inventory.py", "foundry_inventory.py",
                     "auth.py", "runtime_catalog22.py", "models.py"):
            assert (package / name).read_bytes() == (API_FULL / PREFIX / name).read_bytes()
        report.update(python311_syntax_files=parsed, import_pass=True,
                      authenticated_endpoint_only=True, snapshot_six_current_candidates=True,
                      missing_publication_fail_closed=True, drift_rejected=True)
        commands = {
            "terraform-fmt": ["C:/Program Files/Terraform/terraform.exe", "fmt", "-check",
                "infra/project-route/auto-routing.tf", "infra/project-route/foundry-successor22.tf",
                "infra/project-route/tests/auto-routing.tftest.hcl"],
            "ui-typecheck": ["node", str(ROOT / "node_modules/typescript/bin/tsc"), "--noEmit", "-p",
                str(OUT / "contexts/customer/packages/ui/tsconfig.json")],
            "customer-typecheck": ["node", str(ROOT / "node_modules/typescript/bin/tsc"), "--noEmit", "-p",
                str(OUT / "contexts/customer/apps/customer-portal/tsconfig.json")],
        }
        for name, argv in commands.items():
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=180)
            text(OUT / "checks" / (name + ".txt"), result.stdout.decode("utf-8", errors="replace") +
                 result.stderr.decode("utf-8", errors="replace"))
            report[name] = {"argv": argv, "exit_code": result.returncode}
            assert result.returncode == 0, f"{name} exact failure retained in checks/{name}.txt"
        assert tree(DEP / "auto-additive01") == manifest["retained_additive01"]
        report["status"] = "OFFLINE_COMPOSITION_CHECKS_PASS_PENDING_INDEPENDENT_REVIEW"
    except Exception as exc:
        report.update(status="STOPPED_NO_REPLAY", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        record(OUT / "checks/result.json", report)
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()