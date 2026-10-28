from copy import deepcopy
from datetime import UTC, datetime
import json

import pytest
from scripts.deployment import catalog_pricing_evidence_release as renewal


@pytest.mark.parametrize("bad", [None, "route", "deployment", "expiry", "proof", "timestamp"])
def test_renewal_only_after_real_matching_read_and_no_route_changes(tmp_path, monkeypatch, bad):
    old = {"verified_at": "2026-10-26T12:44:49.521995+00:00", "routes": [{"backend": "same"}], "deployments": [{"model": "same"}]}
    path = tmp_path / "context" / renewal.SNAPSHOT
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(old))
    monkeypatch.setattr(renewal, "FIRST", tmp_path)
    proof = {"at": datetime.now(UTC).isoformat(), "snapshot_sha256": renewal.sha(path.read_bytes()),
             "all_live_metadata_matches": True, "account_and_project_succeeded": True,
             "connections": 0, "no_inference_no_writes": True, "freshness_limit_seconds_unchanged": 86400}
    current = deepcopy(old)
    current["verified_at"] = proof["at"]
    if bad == "route":
        current["routes"][0]["backend"] = "wrong"
    elif bad == "deployment":
        current["deployments"][0]["model"] = "wrong"
    elif bad == "expiry":
        proof["freshness_limit_seconds_unchanged"] = 172800
    elif bad == "proof":
        proof["all_live_metadata_matches"] = False
    elif bad == "timestamp":
        current["verified_at"] = "2026-10-28T13:00:00+00:00"
    if bad:
        with pytest.raises(RuntimeError):
            renewal.renewal_guard(old, current, proof)
    else:
        renewal.renewal_guard(old, current, proof)