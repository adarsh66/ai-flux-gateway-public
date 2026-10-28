"""Offline verification of the exact source archive used by a published release.

Runs migrations only against a disposable local SQLite database, never Azure.
"""

import ast
import argparse
import hashlib
import json
import sys
import tempfile
import warnings
from pathlib import Path, PurePosixPath

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL, create_engine, inspect


def verify_manifest(directory: Path) -> tuple[dict, Path]:
    """Check the complete Python source boundary before loading release modules.

    A manifest is integrity evidence, not a signature or deployment approval.
    Only use source from a separately reviewed, trusted release.
    """
    manifest = json.loads((directory / "source-manifest.json").read_text())
    context = (directory / "context").resolve()
    paths = set()
    for entry in manifest["entries"]:
        name = entry["path"]
        relative = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or relative.is_absolute()
                or ".." in relative.parts or relative.as_posix() != name):
            raise RuntimeError("unsafe_manifest_path")
        source = (context / name).resolve()
        if not source.is_relative_to(context):
            raise RuntimeError("unsafe_manifest_path")
        if name in paths:
            raise RuntimeError("duplicate_manifest_path")
        paths.add(name)
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise RuntimeError("packaged_source_hash_mismatch")
        if source.suffix == ".py":
            ast.parse(data, filename=name)
    root = context / "services/control-plane"
    required = {"services/control-plane/alembic.ini",
                "services/control-plane/src/aiflux/__init__.py",
                "services/control-plane/migrations/env.py"}
    if not required <= paths:
        raise RuntimeError("missing_manifested_runtime_source")
    for folder in (root / "src", root / "migrations"):
        for source in folder.rglob("*.py"):
            if source.relative_to(context).as_posix() not in paths:
                raise RuntimeError("unmanifested_python_source")
    return manifest, root


def verify_release(directory: Path) -> dict:
    manifest, root = verify_manifest(directory.resolve())
    source_root = root / "src"
    # Never accidentally test an old installed copy. Reject already-loaded copies
    # rather than deleting modules or silently mixing two model registries.
    for name, module in list(sys.modules.items()):
        if name == "aiflux" or name.startswith("aiflux."):
            location = getattr(module, "__file__", None)
            if not location or not Path(location).resolve().is_relative_to(source_root):
                raise RuntimeError("start_fresh_process_for_release_source")
    sys.path.insert(0, str(source_root))
    import aiflux.config
    from aiflux.config import Settings

    config = Config(str(root / "alembic.ini"))
    config.set_main_option("prepend_sys_path", str(source_root))
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        graph = ScriptDirectory.from_config(config)
        revisions = list(graph.walk_revisions())
        if graph.get_heads() != ["0003"] or sorted(item.revision for item in revisions) != ["0001", "0002", "0003"]:
            raise RuntimeError("unexpected_packaged_migration_graph")
    with tempfile.TemporaryDirectory(prefix="aiflux-release-check-") as temp:
        url = URL.create("sqlite", database=str(Path(temp) / "verify.db"))
        settings = Settings(_env_file=None, environment="testing", database_url=url.render_as_string(),
                            local_auth_enabled=False)
        engine = create_engine(url)
        original = aiflux.config.get_settings
        aiflux.config.get_settings = lambda: settings
        try:
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                command.upgrade(config, "head")
                from aiflux.models import Base

                if set(inspect(connection).get_table_names()) != set(Base.metadata.tables) | {"alembic_version"}:
                    raise RuntimeError("packaged_migration_schema_incomplete")
        finally:
            config.attributes.pop("connection", None)
            engine.dispose()
            aiflux.config.get_settings = original
    return {"tag": manifest["tag"], "hashed_files": len(manifest["entries"]),
            "python_syntax": "passed", "migration_head": "0003",
            "empty_database_upgrade_and_repeat": "passed", "azure_database_access": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path, help="Reviewed manifest plus extracted context directory")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_release(args.release_dir)))
    except Exception as error:
        # Driver/parser errors can contain file contents or environment data.
        # Only our fixed internal error codes are safe to print.
        code = str(error) if type(error) is RuntimeError else "verification_failed"
        allowed = {"unsafe_manifest_path", "duplicate_manifest_path", "packaged_source_hash_mismatch",
                   "missing_manifested_runtime_source", "unmanifested_python_source",
                   "start_fresh_process_for_release_source", "unexpected_packaged_migration_graph",
                   "packaged_migration_schema_incomplete"}
        print(json.dumps({"status": "failed", "code": code if code in allowed else "verification_failed"}),
              file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()