"""Offline only: no Azure, Terraform, image build or browser Send."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import os

import pytest

from scripts.deployment import customer_send_release as r


NAME = "customer-send-20261029T105900000000Z"
IMAGE = r.portals.HOST + "/aiflux-customer@sha256:" + "b" * 64


def plan_fixture():
    old = {"app_settings": {"complete": "preserved"}, "identity": {"type": "UserAssigned"},
        "site_config": [{"always_on": True, "application_stack": [{"docker_image_name":
            "aiflux-customer@sha256:" + r.PINS["customer"], "docker_registry_url": "https://" + r.portals.HOST}]}]}
    new = deepcopy(old)
    new["site_config"][0]["application_stack"][0]["docker_image_name"] = IMAGE.split("/", 1)[1]
    plan = {"applyable": True, "checks": [{"status": "pass"}], "resource_changes": [{
        "address": r.ADDRESS, "mode": "managed", "change": {"actions": ["update"], "before": old,
            "after": new, "after_unknown": {}}}]}
    before = {"runtime": {"sites": {"customer": {"image": "DOCKER|" + r.portals.HOST + "/aiflux-customer@sha256:" + r.PINS["customer"]}}}}
    return plan, before


def test_image_only_plan():
    plan, before = plan_fixture()
    r.guard(plan, IMAGE, before, {"complete": "preserved"})


@pytest.mark.parametrize("mutation", ["api", "admin", "ingestion", "settings", "flag", "network", "identity", "always_on",
    "create", "destroy", "unknown", "check", "extra", "nochange", "mutable", "predecessor", "missing_setting"])
def test_plan_rejects_every_other_delta(mutation):
    plan, before = plan_fixture()
    resource = plan["resource_changes"][0]
    c = resource["change"]
    settings = {"complete": "preserved"}
    image = IMAGE
    if mutation in {"api", "admin", "ingestion"}: resource["address"] = f'azurerm_linux_web_app.main["{mutation}"]'
    if mutation == "settings": c["after"]["app_settings"]["complete"] = "changed"
    if mutation == "flag": c["after"]["app_settings"]["AIFLUX_AUTO_ROUTING_ENABLED"] = "true"
    if mutation == "network": c["after"]["public_network_access_enabled"] = True
    if mutation == "identity": c["after"]["identity"] = {}
    if mutation == "always_on": c["after"]["site_config"][0]["always_on"] = False
    if mutation in {"create", "destroy"}: c["actions"] = [mutation]
    if mutation == "unknown": c["after_unknown"] = {"site_config": True}
    if mutation == "check": plan["checks"][0]["status"] = "unknown"
    if mutation == "extra": plan["resource_changes"].append(deepcopy(resource))
    if mutation == "nochange": plan["resource_changes"] = []
    if mutation == "mutable": image = r.portals.HOST + "/aiflux-customer:latest"
    if mutation == "predecessor": before["runtime"]["sites"]["customer"]["image"] = "DOCKER|other"
    if mutation == "missing_setting": settings = {}
    with pytest.raises(RuntimeError): r.guard(plan, image, before, settings)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "C:/escape", "a\\escape", ".env", "a/.secret", "a//b", ""])
def test_safe_paths(path):
    with pytest.raises(RuntimeError): r.safe_path(path)


def test_subset_matches_only_customer_docker_copy_inputs():
    names = ["package.json", "package-lock.json", "tsconfig.base.json", "packages/ui/src/chat.ts",
             r.DOCKER, "apps/customer-portal/src/main.tsx", "apps/admin-portal/src/main.tsx",
             "services/control-plane/src/aiflux/app.py", "infra/image-build/FinOpsValidation.Dockerfile"]
    selected = r.subset([{"path": n} for n in names])
    assert {e["path"] for e in selected} == set(names[:6])


def test_context_extra_or_modified_file_fails(tmp_path):
    (tmp_path / "only.txt").write_bytes(b"expected")
    entries = [{"path": "only.txt", "sha256": r.sha(tmp_path / "only.txt")}]
    r.context_guard(tmp_path, entries)
    (tmp_path / "only.txt").write_bytes(b"drift")
    with pytest.raises(RuntimeError): r.context_guard(tmp_path, entries)
    (tmp_path / "only.txt").write_bytes(b"expected")
    (tmp_path / "extra.txt").write_bytes(b"extra")
    with pytest.raises(RuntimeError): r.context_guard(tmp_path, entries)


def test_retained_actual_cm37_no_cloud(monkeypatch):
    monkeypatch.setattr(r.rt, "cli", lambda *_: pytest.fail("cloud called"))
    assert len(r.retained()["entries"]) == 77


def test_exclusive_receipt_no_overwrite(tmp_path):
    r.write(tmp_path, "intent.json", {"once": True})
    with pytest.raises(FileExistsError): r.write(tmp_path, "intent.json", {"once": False})
    assert r.load(tmp_path / "intent.json") == {"once": True}


def test_review_missing_stops_before_cloud_or_build(tmp_path, monkeypatch):
    monkeypatch.setattr(r.rt, "HOME", tmp_path)
    rel = r.Release(NAME)
    rel.home.mkdir()
    monkeypatch.setattr(rel, "check", lambda: None)
    monkeypatch.setattr(r, "collect", lambda: pytest.fail("cloud before review"))
    with pytest.raises(FileNotFoundError): rel.build()
    assert not (rel.home / "build-intent.json").exists()


@pytest.mark.parametrize("mutation", ["scope", "package", "self", "not_actual", "stale", "summary"])
def test_parent_review_is_exact(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(r.rt, "HOME", tmp_path)
    rel = r.Release(NAME)
    rel.home.mkdir()
    r.write(rel.home, "package.json", {"exact": True})
    (rel.home / "native-review.md").write_text("Actual parent review summary", encoding="utf-8")
    review = {"scope": "CUSTOMER_SEND_IMAGE_BUILD_ONLY", "decision": "PASS", "actual_independent_review": True,
        "package_sha256": r.sha(rel.home / "package.json"), "reviewer_pid": os.getpid() + 1,
        "summary_file": "native-review.md", "summary_sha256": r.sha(rel.home / "native-review.md"),
        "at_utc": datetime.now(UTC).isoformat()}
    if mutation == "scope": review["scope"] = "AUTO_ENABLE"
    if mutation == "package": review["package_sha256"] = "0" * 64
    if mutation == "self": review["reviewer_pid"] = os.getpid()
    if mutation == "not_actual": review["actual_independent_review"] = False
    if mutation == "stale": review["at_utc"] = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    if mutation == "summary": review["summary_sha256"] = "0" * 64
    r.write(rel.home, "parent-build-review.json", review)
    monkeypatch.setattr(rel, "check", lambda: None)
    with pytest.raises(RuntimeError): rel.reviewed()


def test_consumed_build_never_reenters_review(tmp_path, monkeypatch):
    monkeypatch.setattr(r.rt, "HOME", tmp_path)
    rel = r.Release(NAME)
    rel.home.mkdir()
    r.write(rel.home, "build-intent.json", {"outcome": "UNKNOWN"})
    monkeypatch.setattr(rel, "reviewed", lambda: pytest.fail("replayed"))
    with pytest.raises(RuntimeError, match="consumed"): rel.build()


def test_no_apply_or_auto_entrypoint():
    rel = r.Release(NAME)
    assert not hasattr(rel, "apply")
    args = rel.build_args()
    assert args[:2] == ["acr", "build"] and args.count("--image") == 1
    assert args[args.index("--file") + 1] == r.DOCKER
    assert not any("aiflux-api" in x or "aiflux-admin:" in x or "AUTO" in x for x in args)
    assert "--no-push" not in args  # Future production build, NOT cm37 replay.


def test_environment_cannot_inject_other_workspace_or_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(r.rt, "ENV", {"TF_CLI_ARGS_plan": "-destroy", "TF_VAR_enabled": "true",
        "TF_LOG": "TRACE", "TF_WORKSPACE": "foreign", "TF_DATA_DIR": "foreign",
        "ARM_ACCESS_KEY": "synthetic", "ARM_CLIENT_SECRET": "synthetic", "REQUESTS_CA_BUNDLE": "trusted"})
    original = r.rt.ENV
    with r.terraform_environment(tmp_path):
        assert r.rt.ENV["TF_WORKSPACE"] == "default"
        assert r.rt.ENV["TF_DATA_DIR"] == str(tmp_path / ".terraform")
        assert not any(k.startswith(("TF_CLI_ARGS", "TF_VAR_", "TF_LOG")) or k in {"ARM_ACCESS_KEY", "ARM_CLIENT_SECRET"} for k in r.rt.ENV)
        assert r.rt.ENV["REQUESTS_CA_BUNDLE"] == "trusted"
    assert r.rt.ENV is original


def test_read_transport_restored_even_on_failure(monkeypatch):
    original = r.rt.cli
    command = r.rt.CLI
    product = r.persistence.release.ProductRun
    def install():
        r.rt.cli = lambda *_: None
        r.rt.CLI = ["temporary"]
        r.persistence.release.ProductRun = object
    monkeypatch.setattr(r.persistence, "transport", install)
    with pytest.raises(ValueError):
        with r.read_transport(): raise ValueError("synthetic")
    assert r.rt.cli is original and r.rt.CLI is command and r.persistence.release.ProductRun is product


def test_prepare_never_invokes_build_plan_or_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(r.rt, "HOME", tmp_path)
    monkeypatch.setattr(r.rt, "ROOT", tmp_path)
    # Exact retained file copying is independently tested above; this tests orchestration.
    source = tmp_path / "source"
    (source / "context").mkdir(parents=True)
    monkeypatch.setattr(r, "UI", source)
    monkeypatch.setattr(r, "retained", lambda: {"entries": []})
    monkeypatch.setattr(r, "subset", lambda _: [])
    monkeypatch.setattr(r, "collect", lambda: {"baseline": {"fixture": True}})
    monkeypatch.setattr(r.fs, "protect", lambda _: None)
    monkeypatch.setattr(r, "context_guard", lambda *_: None)
    monkeypatch.setattr(r, "tooling", lambda: {})
    monkeypatch.setattr(r, "sha", lambda _: "f" * 64)
    monkeypatch.setattr(r, "read_transport", nullcontext)
    monkeypatch.setattr(r.persistence.release, "snapshot", lambda: {"fixture": True})
    monkeypatch.setattr(r, "load", lambda _: {"entries": []})
    monkeypatch.setattr(r.Release, "build", lambda _: pytest.fail("build from prepare"))
    monkeypatch.setattr(r.Release, "plan", lambda _: pytest.fail("plan from prepare"))
    p = r.Release(NAME).prepare()
    assert p["max_builds"] == 1 and p["max_applies"] == 0
    assert p["requires_parent_review"] and p["auto_enablement"] is False