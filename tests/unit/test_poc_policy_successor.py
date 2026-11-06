"""No live operations: require publisher evidence before planning and no replay."""
import pytest

from scripts.deployment import poc_policy_successor as release


def test_existing_policy_directory_is_never_replanned(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "HOME", tmp_path)
    monkeypatch.setattr(release, "acceptance", lambda: pytest.fail("must stop before reads"))
    with pytest.raises(RuntimeError, match="reconcile_only"):
        release.plan()


def test_existing_apply_intent_blocks_before_any_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "HOME", tmp_path)
    (tmp_path / "apply-intent.json").write_text("preserved")
    monkeypatch.setattr(release, "check", lambda: pytest.fail("must stop before reads"))
    with pytest.raises(RuntimeError, match="reconcile_only"):
        release.apply()
    assert (tmp_path / "apply-intent.json").read_text() == "preserved"


@pytest.mark.parametrize("defect", ["failed", "502", "reconcile", "not_restored", "unpublished"])
def test_unreliable_publisher_cannot_satisfy_activation_gate(monkeypatch, defect):
    from aiflux.schemas import PocGatewayConfiguration
    evidence = {"passed": defect != "failed", "http502_count": int(defect == "502"), "reconciles": int(defect == "reconcile"),
                "operations": [{"http_status": 200, "published": True}] * 4,
                "head": {"version": 10, "published_version": 9 if defect == "unpublished" else 10,
                         "state": "published", "configuration": PocGatewayConfiguration().model_dump(mode="json")}}
    if defect == "not_restored":
        evidence["head"]["configuration"]["defaults"]["rpm"] = 59
    monkeypatch.setattr(release.r.prep, "load", lambda path: {"passed": True} if path.name == "verified.json" else evidence)
    with pytest.raises(RuntimeError, match="reliable_live_publisher"):
        release.acceptance()