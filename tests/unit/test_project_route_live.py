"""Offline failure-path tests. Never attests any live service success."""
import json
from copy import deepcopy

import pytest

from scripts.deployment import project_route_live as live
from scripts.deployment.apim_route_repair import APIM, RepairBlocked, guard_candidate_rollback


def rollback_fixture():
    child = {"type": "Microsoft.ApiManagement/service/apis@2024-05-01", "parent_id": APIM,
             "name": "aiflux-project-validation", "body": {}}
    candidate = {"resource_changes": [{"address": 'azapi_resource.project_child["api"]',
                                      "change": {"actions": ["create"], "after": child}}]}
    baseline = {"format": "xml", "value": "protected-closed-baseline"}
    plan = {"applyable": True, "resource_changes": [
        {"address": 'azapi_resource.project_child["api"]', "change": {"actions": ["delete"], "before": child}},
        {"address": "azapi_resource.project_global_gate[0]", "change": {"actions": ["update"], "after": {
            "parent_id": APIM, "name": "policy", "body": {"properties": baseline}}}}]}
    return plan, candidate, baseline


def test_rollback_only_restores_global_and_deletes_owned_child():
    guard_candidate_rollback(*rollback_fixture())


@pytest.mark.parametrize("mutation", ["global_delete", "global_value", "foreign_child", "unowned", "errored", "unknown"])
def test_rollback_rejects_unsafe_changes(mutation):
    plan, candidate, baseline = deepcopy(rollback_fixture())
    if mutation == "global_delete": plan["resource_changes"][1]["change"]["actions"] = ["delete"]
    if mutation == "global_value": plan["resource_changes"][1]["change"]["after"]["body"] = {}
    if mutation == "foreign_child": plan["resource_changes"][0]["change"]["before"] = {"name": "legacy"}
    if mutation == "unowned": plan["resource_changes"][0]["address"] = "unrelated"
    if mutation == "errored": plan["errored"] = True
    if mutation == "unknown": plan["applyable"] = False
    with pytest.raises(RepairBlocked):
        guard_candidate_rollback(plan, candidate, baseline)


def test_failed_partial_apply_always_calls_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "WORK", tmp_path)
    monkeypatch.setattr(live, "ROOT", tmp_path)
    (tmp_path / ".azure").mkdir()
    (tmp_path / ".azure/validate-status.json").write_text(json.dumps({"completedStep": "UpdateStatus"}))
    (tmp_path / ".azure/deployment-plan.md").write_text("Candidate validation status: Validated")
    (tmp_path / "project-route-baseline.json").write_text(json.dumps({"snapshot": {}, "baseline": {"global_export": {"value": "baseline"}}}))
    (tmp_path / "project-candidate.tfplan").write_bytes(b"test saved plan")
    monkeypatch.setattr(live, "prepare", lambda *a, **k: {})
    monkeypatch.setattr(live, "conservative_defaults", lambda *a: {})
    monkeypatch.setattr(live, "guard_candidate_plan", lambda *a: None)
    run = object.__new__(live.CandidateRun)
    run.report = {}
    cleaned = []
    def tf(*args, **kwargs):
        if args[0] == "show": return "{}"
        if args[0] == "console": return json.dumps(json.dumps({}))
        if args[0] == "apply": raise RepairBlocked("actual simulated partial failure")
        raise AssertionError(args)
    run.tf = tf
    run.verify_baseline = lambda *a: None
    run.cleanup = lambda *a: cleaned.append(True)
    with pytest.raises(RepairBlocked, match="partial failure"):
        run.run()
    assert cleaned == [True]
    assert (tmp_path / "project-route-live-result.json").is_file()


def test_readiness_polls_models_only_without_retrying_inference(monkeypatch):
    run = object.__new__(live.CandidateRun)
    calls, waits = [], []
    results = iter([503, 404, 200])
    def probe(name, path, **kwargs):
        calls.append((path, kwargs))
        return {"status": next(results)}
    run.probe = probe
    monkeypatch.setattr(live.time, "sleep", waits.append)
    run.wait_for_candidate("/candidate", "memory-only")
    assert [path for path, _ in calls] == ["/candidate/models"] * 3
    assert all("body" not in kwargs for _, kwargs in calls)
    assert waits == [5, 5]


@pytest.mark.parametrize("status,count", [(503, 25), (401, 25), (403, 1)])
def test_readiness_failure_is_bounded_and_blocks_inference(monkeypatch, status, count):
    run = object.__new__(live.CandidateRun)
    calls = []
    def probe(*args, **kwargs):
        calls.append(args)
        return {"status": status}
    run.probe = probe
    monkeypatch.setattr(live.time, "sleep", lambda _: None)
    with pytest.raises(RepairBlocked):
        run.wait_for_candidate("/candidate", "memory-only")
    assert len(calls) == count


@pytest.mark.parametrize("elapsed,status,stage,expected", [
    (3, 200, None, "rejection_not_demonstrated"),
    (3, 429, "rpm", "rejection_observed"),
    (3, 429, "tokens", "rejection_not_demonstrated"),
    (3, 403, "tokens", "rejection_not_demonstrated"),
    (60, 200, None, "inconclusive_window"),
    (61, 429, "rpm", "inconclusive_window"),
    (-1, 429, "rpm", "inconclusive_window"),
])
def test_rpm_assessment_distinguishes_latency_and_token_limits(elapsed, status, stage, expected):
    first = {"started_monotonic": 100}
    second = {"started_monotonic": 100 + elapsed, "status": status, "failure_stage": stage}
    assert live.assess_rpm(first, second) == expected


def test_missing_historical_start_times_cannot_invent_window_acceptance():
    assert live.assess_rpm({}, {"status": 429, "error_code": "RateLimitExceeded"}) == "inconclusive_window"


def test_probe_records_only_numeric_counter_headers_and_no_content(monkeypatch):
    from email.message import Message
    headers = Message()
    headers["x-aiflux-rpm-remaining"] = "0"
    headers["x-aiflux-rpm-limit"] = "1"
    headers["x-aiflux-daily-tokens-remaining"] = "not-numeric-do-not-emit"
    headers["Authorization"] = "private-do-not-emit"
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return b'{"choices":[{"message":{"content":"private-text-do-not-emit"}}]}'
    response = Response()
    response.headers = headers
    monkeypatch.setattr(live.urllib.request, "urlopen", lambda *a, **k: response)
    clock = iter([100, 102.5])
    monkeypatch.setattr(live.time, "monotonic", lambda: next(clock))
    run = object.__new__(live.CandidateRun)
    run.tls = None
    run.report = {"checks": []}
    result = run.probe("bounded", "/test", key="memory-only-key")
    assert result["elapsed_seconds"] == 2.5
    assert result["started_monotonic"] == 100
    assert result["x-aiflux-rpm-remaining"] == 0
    assert result["x-aiflux-rpm-limit"] == 1
    assert result["assistant_text"] is True
    assert "do-not-emit" not in json.dumps(result)
    assert "memory-only-key" not in json.dumps(result)