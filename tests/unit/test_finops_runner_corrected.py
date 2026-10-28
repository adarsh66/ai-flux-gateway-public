"""Corrected coordinator isolation; no cloud operations."""
from pathlib import Path

import pytest

from scripts.deployment import finops_runner_corrected as corrected
from scripts.deployment import finops_runner_guards as g


@pytest.mark.parametrize("nonce", ["2f75015b55d1", "9461fb0c1a35", "3788be5dd201", "05a9ff859f48", "../bad", "", "0" * 13])
def test_prior_and_invalid_sessions_cannot_be_bound(nonce):
    with pytest.raises(g.GuardBlocked, match="new_nonce_required"):
        corrected.bind(nonce)


def test_new_evidence_paths_do_not_overwrite_historical_proof(monkeypatch):
    monkeypatch.setattr(corrected.build, "OUT", corrected.build.OUT)
    monkeypatch.setattr(corrected.prep, "OUT", corrected.prep.OUT)
    path = corrected.bind("abcdef012345")
    assert corrected.build.OUT != corrected.HISTORICAL_IMAGE
    assert corrected.prep.OUT != corrected.HISTORICAL_PREPARATION
    assert "abcdef012345" in path.name
    for old in corrected.PREVIOUS:
        assert not set(g.owned_ids(old).values()) & set(g.owned_ids("abcdef012345").values())


def test_linux_validation_is_executed_as_nonroot_without_dependency_upgrade():
    root = Path(__file__).resolve().parents[2]
    docker = (root / "infra/finops-runner/Dockerfile").read_text()
    contract = (root / "infra/finops-runner/linux_contract.py").read_text()
    assert docker.index("USER 65532:65532") < docker.index("RUN python -I /probe/linux_contract.py")
    assert "--require-hashes" in docker and "--no-index" in docker
    assert "socket.socket.connect = forbidden" in contract
    assert "socket.getaddrinfo = forbidden" in contract
    assert "NumericLoader(1700).load" in contract and "psycopg.pq.__impl__" in contract
    assert "psycopg.connect(" not in contract
    assert "supervisor.sanitize(json.dumps(first), 0) == first" in contract