"""Recovery dry-run regressions. All data is synthetic; no production writes."""
from datetime import UTC, datetime, timedelta
import json

import pytest

from scripts.deployment.finops_replay import dry_run, recovery_windows

NOW = datetime(2026, 10, 27, 0, 0, tzinfo=UTC)
START = NOW - timedelta(hours=2)
END = NOW - timedelta(hours=1)


def source(**changes):
    return {"resource_id": "/resource", "correlation_id": "synthetic-id", "subscription_id": "owned",
            "occurred_at": START, "input_tokens": 11, "output_tokens": 7, **changes}


@pytest.mark.parametrize("start,end,cutoff", [
    (START.replace(tzinfo=None), END, START),
    (START, END, START + timedelta(seconds=1)),
    (NOW - timedelta(days=31), END, NOW - timedelta(days=40)),
    (START, NOW, START), (END, START, START),
])
def test_recovery_refuses_unapproved_time_boundaries(start, end, cutoff):
    with pytest.raises(ValueError):
        recovery_windows(start, end, cutoff, now=NOW)


def test_dry_run_dedup_neutral_trace_and_unknown_ownership():
    trace = [{"source": "aiflux", "metadata": {"category": "usage", "payload": json.dumps({
        "schema": "finops-v1", "model": "glm-5.3", "attempts": 1,
        "input_tokens": 15, "output_tokens": 4})}}]
    rows = [source(trace_records=trace), source(trace_records=trace),
            source(correlation_id="second", output_tokens=None)]
    result = dry_run(START, END, START, lambda *_: rows, now=NOW)
    assert result["requests"] == 2 and result["duplicate_source_rows"] == 1
    assert result["measured_requests"] == 1 and result["complete_total_tokens"] == 19
    assert result["known_input_tokens"] == 26 and result["missing_token_requests"] == 1
    assert result["ownership_verified"] is False and result["unresolved_owners"] is None
    assert result["writes"] == 0 and result["forward_watermark_changed"] is False
    assert "synthetic-id" not in str(result) and "owned" not in str(result)


def test_unresolved_owner_is_not_assigned_to_a_default_customer():
    result = dry_run(START, END, START, lambda *_: [source()], now=NOW, owned={"other"})
    assert result["unresolved_owners"] == 1 and result["write_authorized"] is False


def test_overflow_subdivides_but_partial_failure_aborts():
    attempts = []

    def query(left, right):
        attempts.append((left, right))
        if right - left > timedelta(minutes=30):
            raise RuntimeError("Usage window exceeds row limit; reduce ingestion_batch_minutes")
        return [source(occurred_at=left, correlation_id=left.isoformat())]

    result = dry_run(START, END, START, query, now=NOW, owned={"owned"})
    assert len(attempts) == 3 and result["requests"] == 2
    assert len(result["windows"]) == 2 and result["unresolved_owners"] == 0

    def partial(*_):
        raise RuntimeError("Azure Monitor returned partial usage data; watermark was not advanced")

    with pytest.raises(RuntimeError, match="partial"):
        dry_run(START, END, START, partial, now=NOW)


def test_recovery_rejects_end_inclusive_rows_and_invalid_counters():
    with pytest.raises(ValueError, match="outside"):
        dry_run(START, END, START, lambda *_: [source(occurred_at=END)], now=NOW)
    with pytest.raises(ValueError, match="Invalid native"):
        dry_run(START, END, START, lambda *_: [source(input_tokens=True)], now=NOW)


def test_repeated_dry_runs_are_deterministic_without_a_forward_cursor():
    collect = lambda: dry_run(START, END, START, lambda *_: [source()], now=NOW, owned={"owned"})
    assert collect() == collect()