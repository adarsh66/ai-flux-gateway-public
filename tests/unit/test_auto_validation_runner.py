"""Offline safety contracts for the new runner; no subprocess or Azure calls."""
import json

import pytest

from scripts import validate_auto_routing as runner


def test_fixed_native_validation_cannot_push_or_deploy():
    args = runner.native.build_args()
    assert args[:2] == ["acr", "build"]
    assert args.count("--no-push") == 1
    assert "--image" not in args and "deploy" not in args
    assert "pocidstokenexacr" in args and "linux/amd64" in args


@pytest.mark.parametrize("images", [None, [], [None]])
def test_native_no_push_image_representations(images):
    assert runner.native.no_published_images(images)


def test_published_image_is_not_no_push():
    assert not runner.native.no_published_images([{"name": "unapproved"}])


def test_curation_includes_auto_and_excludes_private_runtime_inputs(tmp_path):
    manifest = runner.native.stage(tmp_path)
    paths = {e["path"] for e in manifest["entries"]}
    assert runner.REQUIRED <= paths
    assert all(p.startswith(("apps/", "packages/")) or p in {
        "package.json", "package-lock.json", "tsconfig.base.json", "vitest.config.ts", runner.native.DOCKERFILE}
        for p in paths)
    assert all(not p.startswith((".deployment/", ".azure/", "services/", "infra/terraform/")) for p in paths)
    for entry in manifest["entries"]:
        assert runner.native.portals.digest((tmp_path / "context" / entry["path"]).read_bytes()) == entry["sha256"]


def test_reconcile_missing_run_id_never_submits_or_queries_cloud(tmp_path, monkeypatch):
    (tmp_path / "build-intent.json").write_text(json.dumps({"args": runner.native.build_args(), "no_push": True}))
    (tmp_path / "sources.json").write_text('{}')
    (tmp_path / "validation.log").write_text("wrapper failed before returning run identity")
    monkeypatch.setattr(runner.native.rt, "cli", lambda *a: pytest.fail("must not query or submit without run identity"))
    with pytest.raises(RuntimeError, match="run_id_unknown_do_not_resubmit"):
        runner.reconcile(tmp_path)