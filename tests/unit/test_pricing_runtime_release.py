import json

import pytest

from scripts.deployment import pricing_runtime_release as pricing


def test_manifest_json_is_source_bound_and_packaged():
    paths = {e["path"] for e in pricing.sources()}
    assert "services/control-plane/src/aiflux/pricing/rates-20261027.json" in paths
    assert "services/control-plane/src/aiflux/display_pricing.py" in paths
    assert "packages/ui/src/components/DisplayPrice.tsx" in paths
    assert not any(".deployment" in p or "node_modules" in p for p in paths)


@pytest.mark.parametrize("action,marker", [("apply", "apply-intent.json"), ("plan", "apply-intent.json"),
    ("build_api", "api-build-intent.json"), ("build_portals", "portal-build-intent.json"),
    ("build_corrected_portals", "portal-correction-intent.json")])
def test_existing_attempt_never_replayed(tmp_path, monkeypatch, action, marker):
    monkeypatch.setattr(pricing, "HOME", tmp_path)
    (tmp_path / marker).write_text(json.dumps({"already_attempted": True}))
    monkeypatch.setattr(pricing, "baseline", lambda: pytest.fail("must not access cloud"))
    monkeypatch.setattr(pricing, "release", lambda: pytest.fail("must not access cloud"))
    with pytest.raises(RuntimeError, match="already_attempted"):
        getattr(pricing, action)()


def test_correction_requires_failed_unpublished_unapplied_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(pricing, "HOME", tmp_path)
    monkeypatch.setattr(pricing.rt, "cli", lambda *a: pytest.fail("must not access cloud"))
    with pytest.raises(RuntimeError, match="failed_validation_only"):
        pricing.build_corrected_portals()
    (tmp_path / "portal-build-intent.json").write_text("{}")
    (tmp_path / "apply-intent.json").write_text("{}")
    with pytest.raises(RuntimeError, match="failed_validation_only"):
        pricing.build_corrected_portals()