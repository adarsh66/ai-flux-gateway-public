"""Offline FinOps source manifest and exact image-only saved-plan rejection guard.

No Azure calls, builds, Terraform execution or apply mode. This is NOT a release
approval. Native Functions conversion/configuration needs its own reviewed plan.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = "pocidstokenexacr.azurecr.io"
COMPONENTS = ("api", "ingestion", "admin", "customer")
ADDRESSES = {**{f'azurerm_linux_web_app.main["{kind}"]': kind for kind in ("api", "admin", "customer")},
             "azurerm_linux_function_app.ingestion[0]": "ingestion"}


def require(value, label):
    if not value:
        raise ValueError(label)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def source_manifest(root=ROOT):
    """Shared control-plane changes affect BOTH API and ingester container inputs."""
    shared = {"pyproject.toml"}
    for folder in ("services/control-plane/src", "gateway/catalog"):
        shared.update(p.relative_to(root).as_posix() for p in (root / folder).rglob("*")
                      if p.is_file() and p.suffix in {".py", ".kql", ".json"} and "__pycache__" not in p.parts)
    backend = shared | {"services/control-plane/Dockerfile", "services/control-plane/alembic.ini",
                        "gateway/policies/settings-unconfigured.xml"}
    backend.update(p.relative_to(root).as_posix() for p in (root / "services/control-plane/migrations").rglob("*")
                   if p.is_file() and p.suffix in {".py", ".mako"} and "__pycache__" not in p.parts
                   and p.name != "0003_portal_users.py")
    ingester = (backend - {"services/control-plane/Dockerfile", "gateway/policies/settings-unconfigured.xml"}) | {
        "services/usage-ingestion/Dockerfile", "services/usage-ingestion/requirements.txt"}
    ingester.update(p.relative_to(root).as_posix() for p in (root / "services/usage-ingestion").rglob("*")
                    if p.is_file() and p.suffix in {".py", ".json"} and "__pycache__" not in p.parts)
    ui_shared = {"package.json", "package-lock.json", "tsconfig.base.json", "vitest.config.ts"}
    ui_shared.update(p.relative_to(root).as_posix() for p in (root / "packages/ui").rglob("*")
                     if p.is_file() and not any(part in {"node_modules", "dist", "build"} or part.startswith(".")
                                               for part in p.relative_to(root / "packages/ui").parts))
    groups = {"api": backend, "ingestion": ingester}
    for kind in ("admin", "customer"):
        app = root / "apps" / (kind + "-portal")
        groups[kind] = ui_shared | {p.relative_to(root).as_posix() for p in app.rglob("*") if p.is_file()
            and not any(part in {"node_modules", "dist", "build"} or part.startswith(".") for part in p.relative_to(app).parts)}
    results = {}
    for kind, paths in groups.items():
        entries = []
        for name in sorted(paths):
            path = root / name
            require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), "source_path")
            require(path.suffix.lower() not in {".key", ".pem", ".pfx", ".env"}, "source_secret_file")
            entries.append({"path": name, "sha256": digest(path.read_bytes())})
        results[kind] = {"entries": entries, "source_sha256": digest(json.dumps(entries, sort_keys=True).encode())}
    return {"components": results, "required_changed_components": list(COMPONENTS), "release_authorized": False,
            "exclusions": ["legacy duplicate 0003_portal_users.py; active LocalUser migration is 0003_stable_teams.py"],
            "scope": "offline_manifest_and_image_only_guard_not_build_or_deployment_proof"}


def any_unknown(value):
    if isinstance(value, dict):
        return any(any_unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(any_unknown(v) for v in value)
    return bool(value)


def guard_image_plan(plan, images):
    """Exactly four immutable image updates, no settings/network/identity activation.

    Reject Python-to-container conversion, timer/catalog/cutoff edits and unknowns.
    A passing offline structural guard does not authorize applying a plan.
    """
    require(set(images) == set(COMPONENTS), "exact_four_component_pins_required")
    for kind, image in images.items():
        require(re.fullmatch(re.escape(REGISTRY + "/aiflux-" + kind + "@sha256:") + "[a-f0-9]{64}", image), "immutable_registry_pin")
    require(plan.get("applyable") is True and not plan.get("errored") and not plan.get("deferred_changes"), "unresolved_plan")
    seen = set()
    for resource in plan.get("resource_changes", []):
        change = resource["change"]
        if change["actions"] == ["no-op"]:
            continue
        address = resource["address"]
        require(address in ADDRESSES and address not in seen and resource.get("mode") == "managed"
                and change["actions"] == ["update"], "non_image_resource")
        require(not any_unknown(change.get("after_unknown", {})), "unknown_plan_value")
        seen.add(address)
        kind = ADDRESSES[address]
        old, new = copy.deepcopy(change["before"]), copy.deepcopy(change["after"])
        require(len(old["site_config"]) == len(new["site_config"]) == 1, "site_config_shape")
        old_stack, new_stack = old["site_config"][0]["application_stack"], new["site_config"][0]["application_stack"]
        require(len(old_stack) == len(new_stack) == 1, "application_stack_shape")
        if kind == "ingestion":
            require(len(old_stack[0].get("docker", [])) == len(new_stack[0].get("docker", [])) == 1,
                    "function_configuration_requires_separate_review")
            docker = new_stack[0]["docker"][0]
            repository, pin = images[kind].split("@sha256:")
            require(docker.get("registry_url") == "https://" + REGISTRY and
                    docker.get("image_name") == repository.split("/", 1)[1] + "@sha256" and
                    docker.get("image_tag") == pin, "wrong_ingester_pin")
            for key in ("image_name", "image_tag"):
                docker[key] = old_stack[0]["docker"][0].get(key)
        else:
            require(new_stack[0].get("docker_registry_url") == "https://" + REGISTRY and
                    new_stack[0].get("docker_image_name") == images[kind].split("/", 1)[1], "wrong_app_pin")
            new_stack[0]["docker_image_name"] = old_stack[0].get("docker_image_name")
        require(old != change["after"] and old == new, "non_image_or_unchanged_input")
    require(seen == set(ADDRESSES), "exact_four_image_updates_required")
    return {"structural_guard": "passed", "release_authorized": False, "apply_executed": False}


if __name__ == "__main__":
    try:
        manifest = source_manifest()
        manifest["collected_at"] = datetime.now(UTC).isoformat()
        target = ROOT / ".deployment/finops/source-manifest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"components": {k: v["source_sha256"] for k, v in manifest["components"].items()},
                          "release_authorized": False, "cloud_writes": 0}), flush=True)
    except Exception as exc:
        print(json.dumps({"status": "blocked", "exception_type": type(exc).__name__}), flush=True)
        raise SystemExit(2)