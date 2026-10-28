"""Offline archive checks; no historical release or cloud credentials required."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts/verify_packaged_runtime.py"


@pytest.fixture
def release(tmp_path):
    directory = tmp_path / "release"
    target = directory / "context/services/control-plane"
    source = ROOT / "services/control-plane"
    target.mkdir(parents=True)
    for folder in ("src", "migrations"):
        shutil.copytree(source / folder, target / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "0003_portal_users.py"))
    shutil.copyfile(source / "alembic.ini", target / "alembic.ini")
    entries = [{"path": path.relative_to(directory / "context").as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for path in sorted(target.rglob("*")) if path.is_file()]
    (directory / "source-manifest.json").write_text(json.dumps({
        "tag": "synthetic-source-only", "entries": entries,
    }), encoding="utf-8")
    return directory


def verify(release):
    env = os.environ.copy()
    # Deliberately do NOT add the archive source: the verifier must select it.
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    env["AIFLUX_DATABASE_URL"] = "postgresql://must-not-connect.invalid/never"
    env["AIFLUX_ENVIRONMENT"] = "production"
    return subprocess.run([sys.executable, str(VERIFIER), str(release)], cwd=ROOT,
                          env=env, capture_output=True, text=True, check=False)


def update_manifest(release, mutate):
    path = release / "source-manifest.json"
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_source_archive_upgrades_twice_without_cloud_access(release):
    result = verify(release)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["tag"] == "synthetic-source-only"
    assert report["migration_head"] == "0003"
    assert report["empty_database_upgrade_and_repeat"] == "passed"
    assert report["azure_database_access"] is False


@pytest.mark.parametrize("name", ["../outside.py", "/outside.py", "C:/outside.py", "..\\outside.py"])
def test_manifest_rejects_unsafe_paths_before_read_or_import(release, name):
    outside = release / "outside.py"
    outside.write_text("# not part of the source release\n")
    update_manifest(release, lambda data: data["entries"].append({
        "path": name, "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }))
    result = verify(release)
    assert result.returncode != 0
    assert "unsafe_manifest_path" in result.stderr


def test_manifest_rejects_duplicate_paths(release):
    update_manifest(release, lambda data: data["entries"].append(data["entries"][0]))
    result = verify(release)
    assert result.returncode != 0
    assert "duplicate_manifest_path" in result.stderr


def test_manifest_rejects_unmanifested_migration(release):
    target = release / "context/services/control-plane/migrations/versions/injected.py"
    target.write_text("raise RuntimeError('unreviewed source must not execute')\n")
    result = verify(release)
    assert result.returncode != 0
    assert "unmanifested_python_source" in result.stderr
    assert "unreviewed source must not execute" not in result.stderr


def test_manifest_rejects_changed_source(release):
    target = release / "context/services/control-plane/src/aiflux/config.py"
    target.write_text("raise RuntimeError('unreviewed source must not execute')\n")
    result = verify(release)
    assert result.returncode != 0
    assert "packaged_source_hash_mismatch" in result.stderr
    assert "unreviewed source must not execute" not in result.stderr


def test_manifest_cannot_omit_alembic_configuration(release):
    update_manifest(release, lambda data: data.update(entries=[
        entry for entry in data["entries"] if not entry["path"].endswith("alembic.ini")]))
    result = verify(release)
    assert result.returncode != 0
    assert "missing_manifested_runtime_source" in result.stderr