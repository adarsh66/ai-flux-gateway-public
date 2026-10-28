"""Fresh-session isolation and actual supervisor CLI output; no live SQL/Azure."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import subprocess
import sys

import pytest

from scripts.deployment import finops_runner_execute as ex
from scripts.deployment import finops_runner_fresh as fresh
from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_prepare as prep

NONCE = "f00df00df00d"


def test_all_six_ids_including_subnet_are_disjoint_from_active_legacy_watchdog():
    old, new = g.owned_ids(fresh.LEGACY), g.owned_ids(NONCE)
    assert old["subnet"] == g.SUBNET
    assert not set(old.values()) & set(new.values())
    assert all(NONCE in rid for rid in new.values())
    assert len(set(new.values())) == 6
    assert prep.network_template(NONCE)["resources"][-1]["name"].endswith(NONCE + "-subnet")
    for phase in g.IDENTITIES:
        group = prep.group_resource(NONCE, phase, "pocidstokenexacr.azurecr.io/aiflux-finops-probe@sha256:" + "a" * 64, "b" * 64)
        assert group["properties"]["subnetIds"] == [{"id": new["subnet"]}]
        bad = deepcopy(group)
        bad["properties"]["subnetIds"] = [{"id": old["subnet"]}]
        with pytest.raises(g.GuardBlocked, match="wrong_subnet"):
            g.guard_probe_group(bad, nonce=NONCE, phase=phase,
                image=group["properties"]["containers"][0]["properties"]["image"], source_hash="b" * 64, prior_group_absent=True)


def test_old_hash_bound_reaper_cannot_touch_any_fresh_resource(tmp_path):
    start = datetime.now(UTC)
    ids = g.owned_ids(fresh.LEGACY)
    session = {"owner_nonce": fresh.LEGACY, "ids": ids, "started_at_utc": start.isoformat(),
        "deadline_utc": (start + timedelta(minutes=60)).isoformat()}
    path = tmp_path / "session.json"
    ex.write(path, session)
    assert ex.bound_session(path, prep.digest(path)) == session
    calls = []
    class OldArm:
        def get(self, rid):
            calls.append(rid)
            assert rid in ids.values() and rid not in g.owned_ids(NONCE).values()
            return None
        def delete(self, rid): pytest.fail("no old resource exists")
    assert ex.cleanup(session, tmp_path, OldArm())["exit_code"] == 0
    assert set(calls) == set(ids.values())


def test_actual_isolated_entrypoint_cli_prints_parseable_sanitized_json():
    child = subprocess.run([sys.executable, "-I", str(prep.FOLDER / "entrypoint.py"),
        "--probe-sha256", "0" * 64, "--identity", "ingestion"], capture_output=True, text=True, timeout=15)
    assert child.returncode == 0 and not child.stderr
    assert json.loads(child.stdout) == {"status": "blocked", "reason": "probe_source_changed", "sqlstate": None,
        "database_writes": 0, "replay_authorized": False}


def test_supervisor_success_main_prints_real_producer_shape(monkeypatch, tmp_path, capsys):
    from tests.unit.test_finops_runner_preparation import entrypoint
    from tests.unit.test_finops_private_probe import Database, ROLE, NOW, probe
    module = entrypoint()
    source = prep.FOLDER / "finops_private_probe.py"
    # Actual source sits beside the supervisor only inside the isolated image.
    monkeypatch.setattr(module, "__file__", str(tmp_path / "entrypoint.py"))
    copied = tmp_path / source.name
    copied.write_bytes((prep.ROOT / "scripts/deployment/finops_private_probe.py").read_bytes())
    monkeypatch.setattr(module.sys, "argv", ["entrypoint", "--probe-sha256", prep.digest(copied), "--identity", "ingestion"])
    monkeypatch.setattr(module.os, "open", lambda *_: 999)
    monkeypatch.setattr(module.os, "close", lambda *_: None)
    expected = json.loads(json.dumps(probe.inspect_database(Database(), ROLE, now=NOW), default=str))
    def run(*args, **kwargs):
        assert kwargs["timeout"] == 590 and kwargs["capture_output"] is True
        return type("Child", (), {"returncode": 0, "stdout": json.dumps(expected)})()
    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main() == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_fresh_execute_rejects_legacy_before_any_creation(tmp_path):
    path = tmp_path / "prep.json"
    ex.write(path, {"owner_nonce": fresh.LEGACY, "exit_code": 0, "ids": g.owned_ids(fresh.LEGACY)})
    with pytest.raises(g.GuardBlocked, match="invalid_fresh_preparation"):
        fresh.execute(path, prep.digest(path))


def test_fresh_execute_rejects_preparation_tampering(tmp_path):
    path = tmp_path / "prep.json"
    ex.write(path, {})
    with pytest.raises(g.GuardBlocked, match="fresh_preparation_hash_mismatch"):
        fresh.execute(path, "a" * 64)


def test_controller_persists_result_before_deletion_and_no_probe_retry():
    source = (prep.ROOT / "scripts/deployment/finops_runner_execute.py").read_text()
    start = source.index('content = logs.get("content", "")')
    end = source.index('report["probes"][phase]["group_absent_http_404_at_utc"]', start)
    section = source[start:end]
    assert section.index("write(output, report)") < section.index('arm.delete(s["ids"][phase])')
    assert 'g.require(bool(content.strip()), "probe_arm_logs_empty")' in section
    assert 'supervisor.sanitize(content, state.get("exitCode"))' in section