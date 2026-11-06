"""Exclusive offline cm45/cm4f composition. No cloud, build, install or inference.

Creates NEW packaging outputs only; never edits retained inputs or workspace app.
Run once. Partial outputs are evidence and must not be overwritten/replayed.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".deployment/auto-additive-clean01"
DEP = ROOT / ".deployment"
API_PROD = DEP / "sgt-production-release-20261031-01"
API_FULL = DEP / "sgt-f05/api"
CUSTOMER = DEP / "usage-visuals-partial-release-20261031-01/contexts/customer"
PREFIX = "services/control-plane/src/aiflux/"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_bytes())


def emit(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def text(path: Path, value: str) -> None:
    emit(path, value.encode("utf-8"))


def record(path: Path, value: object) -> None:
    text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def replace_once(value: str, old: str, new: str) -> str:
    assert value.count(old) == 1, old
    return value.replace(old, new, 1)


def tree(path: Path) -> dict[str, str]:
    return {p.relative_to(path).as_posix(): sha(p.read_bytes())
            for p in sorted(path.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def verify_files(root: Path, expected: dict[str, str]) -> None:
    for name, digest in expected.items():
        assert sha((root / name).read_bytes()) == digest, str(root / name)


def compose() -> None:
    OUT.mkdir(exist_ok=False)
    record(OUT / "intent.json", {"scope": "offline clean composition only", "replay": False})
    frozen = tree(DEP / "auto-additive01")
    production = load(API_PROD / "source-manifest.json")
    api_base = API_PROD / "contexts/api"
    verify_files(api_base, production["contexts"]["api"]["files"])
    customer_files = load(DEP / "uv-final02/source-manifest.json")["contexts"]["customer"]["files"]
    assert tree(CUSTOMER) == customer_files, "cm4f upload source mismatch"
    api_run = load(API_PROD / "api-build-result.json")
    customer_run = load(DEP / "uv-final02/customer-build-result.json")
    assert api_run["run_id"] == "cm45" and api_run["status"] == "Succeeded"
    assert customer_run["run_id"] == "cm4f" and customer_run["status"] == "Succeeded"
    assert sha((API_PROD / "source-manifest.json").read_bytes()) == api_run["source_manifest_sha256"]
    assert sha((DEP / "uv-final02/source-manifest.json").read_bytes()) == customer_run["source_manifest_sha256"]
    api = OUT / "contexts/api"
    customer = OUT / "contexts/customer"
    # Exact retained cm4f source; no dirty UI sources and no need for a new image.
    for name in customer_files:
        emit(customer / name, (CUSTOMER / name).read_bytes())
    app_base = (api_base / "modules/app.py").read_text(encoding="utf-8")
    app = replace_once(app_base, "from aiflux.config import Settings, get_settings\n",
                       "from aiflux.config import Settings, get_settings\nfrom aiflux.auto_availability import availability\n")
    anchor = '    @app.get("/api/admin/model-router", response_model=ModelRouterConfigOutput)\n'
    endpoint = ('    @app.get("/api/auto-routing/availability")\n'
                '    def auto_routing_availability(principal: User, db: Db) -> dict:\n'
                '        return availability(settings)\n\n')
    app = replace_once(app, anchor, endpoint + anchor)
    config_base = (API_FULL / PREFIX / "config.py").read_text(encoding="utf-8")
    fields = ('    # Direct gateway publication only. No private resolver or profile writes.\n'
              '    auto_routing_enabled: bool = False\n'
              '    auto_routing_direct_validation_enabled: bool = False\n'
              '    auto_routing_publication_path: Path | None = None\n'
              '    auto_routing_published_policy_sha256: str = ""\n'
              '    auto_routing_snapshot_inventory_path: Path | None = None\n')
    config = replace_once(config_base, '    local_auth_enabled: bool = False\n', fields + '    local_auth_enabled: bool = False\n')
    snapshot_base = (ROOT / PREFIX / "auto_snapshot.py").read_text(encoding="utf-8")
    snapshot = replace_once(snapshot_base,
        '    if (settings.foundry_inventory_path is None or spec["schema"] != 1 or spec["catalog_sha256"] != hashlib.sha256(\n            settings.foundry_inventory_path.read_bytes()).hexdigest()\n',
        '    frozen_path = settings.auto_routing_snapshot_inventory_path or settings.foundry_inventory_path\n'
        '    if (frozen_path is None or spec["schema"] != 1 or spec["catalog_sha256"] != hashlib.sha256(\n            frozen_path.read_bytes()).hexdigest()\n')
    snapshot = replace_once(snapshot, '        inv = AcceptedInventory.load(settings)\n        accepted = inv.accepted_aliases(settings)\n',
        '        current = AcceptedInventory.load(settings)\n'
        '        accepted = current.accepted_aliases(settings)\n'
        '        inv = AcceptedInventory.load(settings.model_copy(update={"foundry_inventory_path": frozen_path}))\n')
    snapshot = replace_once(snapshot, '        if route is None or alias not in accepted or "chat" not in route.capabilities:\n',
        '        live_route = current.foundry.route(alias)\n'
        '        binding = ("backend_model", "model_name", "model_version",\n'
        '                   "api_format", "capabilities", "max_completion_tokens", "upstream_token_parameter", "reasoning_effort")\n'
        '        if (route is None or live_route is None or alias not in accepted or "chat" not in route.capabilities\n'
        '                or any(getattr(route, key) != getattr(live_route, key) for key in binding)\n'
        '                or inv.provider(alias) != current.provider(alias)\n'
        '                or (route.endpoint_url, live_route.endpoint_url) != (\n'
        '                    "https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1",\n'
        '                    "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1")):\n')
    snapshot = replace_once(snapshot,
        '        price = accepted_catalog_price(inv, alias, route.backend_model, route.endpoint_url)\n',
        '        price = accepted_catalog_price(current, alias, live_route.backend_model, live_route.endpoint_url)\n')
    availability = '''"""Authenticated read-only publication readiness; no DB writes or scorer dependency."""
from aiflux import auto_snapshot
from aiflux.config import Settings


def availability(settings: Settings) -> dict:
    if not settings.auto_routing_enabled:
        return {"ready": False, "profiles": []}
    try:
        snapshot = auto_snapshot.defaults(settings)
        published = auto_snapshot.publication(settings, snapshot)
        if published is not None:
            result = {"ready": True, "profiles": ["balanced", "cost", "quality"],
                      "config_version": snapshot["version"], "architecture": "gateway-direct"}
            if published["schema"] == 2:
                result.update(validation_mode=published["validation_mode"], runtime_verified=False)
            return result
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return {"ready": False, "profiles": []}
'''
    modules = {"app.py": app, "config.py": config, "auto_snapshot.py": snapshot,
               "auto_availability.py": availability}
    original = {"app.py": app_base, "config.py": config_base,
                "auto_snapshot.py": snapshot_base, "auto_availability.py": ""}
    expected = load(api_base / "expected-files.json")
    copy_lines = []
    for name, source in modules.items():
        ast.parse(source, feature_version=(3, 11))
        text(api / "modules" / name, source)
        text(OUT / "deltas" / (name + ".diff"), "".join(difflib.unified_diff(
            original[name].splitlines(True), source.splitlines(True), fromfile="retained/" + name, tofile="clean/" + name)))
        for prefix in ("/app/" + PREFIX, "/usr/local/lib/python3.11/site-packages/aiflux/"):
            expected[prefix + name] = sha(source.encode())
            copy_lines.append(f"COPY --chown=10001:10001 modules/{name} {prefix}{name}")
    frozen_inventory = API_FULL / "gateway/catalog/acceptance-evidence/gateway/catalog/foundry-inventory-20261026.json"
    spec_path = ROOT / PREFIX / "pricing/auto-routing-defaults.json"
    assert sha(frozen_inventory.read_bytes()) == load(spec_path)["catalog_sha256"]
    resources = {"pricing/auto-routing-defaults.json": spec_path.read_bytes(),
                 "pricing/auto-routing-inventory.json": frozen_inventory.read_bytes(),
                 "queries/decision-overhead.kql": (ROOT / PREFIX / "queries/decision-overhead.kql").read_bytes()}
    for name, raw in resources.items():
        emit(api / "resources" / name, raw)
        for prefix in ("/app/" + PREFIX, "/usr/local/lib/python3.11/site-packages/aiflux/"):
            expected[prefix + name] = sha(raw)
            copy_lines.append(f"COPY --chown=10001:10001 resources/{name} {prefix}{name}")
    record(api / "expected-files.json", expected)
    # cm45 carries unchanged all22, SGT/granularity and financial dependencies.
    # Existing verification is inherited; no broad app, catalog or ingestion copy.
    text(api / "Production.Dockerfile", f"FROM {api_run['image']}\nWORKDIR /app\n" + "\n".join(copy_lines) +
         "\nCOPY expected-files.json /tmp/auto-expected.json\nCOPY verify.py /tmp/auto-verify.py\nRUN python /tmp/auto-verify.py\n")
    verifier = '''import hashlib, importlib, json, runpy, socket
from pathlib import Path
def deny(*args, **kwargs):
    raise RuntimeError("network prohibited during image verification")
socket.create_connection = deny
socket.socket.connect = deny
expected = json.loads(Path("/tmp/auto-expected.json").read_bytes())
for path, digest in expected.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
runpy.run_path("/app/verify22.py", run_name="__main__")
for name in ("app", "config", "auto_snapshot", "auto_availability"):
    module = importlib.import_module("aiflux." + name)
    assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == expected[module.__file__]
print("AUTO_CLEAN_DUAL_PATH_ALL22_HASHES_AND_IMPORTS_PASS")
'''
    text(api / "verify.py", verifier)
    # Effective local source tree is validation-only, never an upload/build context.
    effective = OUT / "checks/effective"
    shutil.copytree(API_FULL, effective, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("app.py", "finops.py", "schemas.py"):
        emit_path = effective / PREFIX / name
        emit_path.unlink()
        emit(emit_path, (api_base / "modules" / name).read_bytes())
    for name, source in modules.items():
        p = effective / PREFIX / name
        if p.exists():
            p.unlink()
        text(p, source)
    for name, raw in resources.items():
        p = effective / PREFIX / name
        if p.exists():
            p.unlink()
        emit(p, raw)
    # Each uploaded member is explicit, hashed, and included exactly once.
    manifests = {"api": tree(api), "customer": tree(customer)}
    assert manifests["customer"] == customer_files
    for kind in ("api", "customer"):
        with tarfile.open(OUT / (kind + ".tar.gz"), "x:gz") as archive:
            for name in manifests[kind]:
                archive.add(OUT / "contexts" / kind / name, arcname=name, recursive=False)
        with tarfile.open(OUT / (kind + ".tar.gz"), "r:gz") as archive:
            assert {m.name: sha(archive.extractfile(m).read()) for m in archive.getmembers()} == manifests[kind]
    assert tree(DEP / "auto-additive01") == frozen
    record(OUT / "source-manifest.json", {
        "contexts": manifests, "archives": {k: sha((OUT / (k + ".tar.gz")).read_bytes()) for k in manifests},
        "baseline": {"api": api_run, "customer": customer_run},
        "retained_additive01": frozen,
        "retained_production_api": production["contexts"]["api"]["files"],
        "minimal_runtime_delta": list(modules) + list(resources),
        "customer_delta": [], "customer_rebuild_required": False,
        "admin_rebuild_required": False, "ingestion_rebuild_required": False,
        "publication_artifact_created": False, "cloud_reads": 0, "cloud_writes": 0, "paid_calls": 0,
    })
    print("CLEAN_CONTEXTS_CREATED", OUT, flush=True)


if __name__ == "__main__":
    compose()