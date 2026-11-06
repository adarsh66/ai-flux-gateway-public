"""The live preflight cannot promote metadata into runtime authorization."""
import pytest

from scripts.deployment import auto_live_gate as gate


@pytest.mark.parametrize("revision,current,identifier,accepted", [
    ("2", False, gate.APIM + "/apis/" + gate.API + ";rev=2", True),
    ("2", False, "/apis/" + gate.API + ";rev=2", True),
    ("1", True, gate.APIM + "/apis/" + gate.API + ";rev=1", False),
    ("2", None, gate.APIM + "/apis/" + gate.API + ";rev=2", False),
    ("2", False, gate.APIM + "/apis/other;rev=2", False),
    ("../2", False, gate.APIM + "/apis/" + gate.API + ";rev=../2", False),
])
def test_noncurrent_identity_must_be_exact(revision, current, identifier, accepted):
    item = {"apiRevision": revision, "isCurrent": current, "apiId": identifier}
    assert gate.summarize_revision(item)["existing_noncurrent_candidate"] is accepted


def test_worker_guard_rejects_even_readonly_competing_terraform():
    with pytest.raises(RuntimeError, match="competing_worker"):
        gate.require_no_competing_workers([
            {"pid": -1, "name": "terraform.exe", "mutation_worker": False}])


def test_worker_guard_accepts_no_workers():
    gate.require_no_competing_workers([])


def test_current_production_validation_name_does_not_authorize_test():
    result = gate.isolation_gate([
        {"name": "aiflux-native-validation-pending", "path": "v1"},
        {"name": "aiflux-dev-openai", "path": "dev/v1"},
    ], [])
    assert result["protected_paths_excluded"] == [
        "aiflux-dev-openai", "aiflux-native-validation-pending"]
    assert "no_existing_noncurrent_development_revision" in result["blockers"]
    assert result["safe_existing_test_target_proven"] is False


def test_noncurrent_revision_discovery_is_not_runtime_or_isolation_proof():
    result = gate.isolation_gate([], [{"existing_noncurrent_candidate": True}])
    assert result["existing_noncurrent_revisions"]
    assert result["safe_existing_test_target_proven"] is False
    assert result["metadata_is_runtime_proof"] is False
    assert result["blockers"] == ["actual_gateway_MI_scoring_contract_unproven"]