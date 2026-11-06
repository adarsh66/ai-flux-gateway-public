from datetime import UTC, datetime, timedelta
import inspect
import json
from unittest.mock import patch

import pytest

from scripts.deployment import auto_diagnostic02 as d
from tests.unit import test_auto_diagnostic_stage as old
from tests.unit.test_auto_diagnostic_stage import original

START = old.START
END = old.END
NONCE = old.NONCE


def candidate(original):
    with d.bindings():
        return d.core.render(original, NONCE, START, END)


def test_tick_epoch_and_known_unix_epoch_exact():
    assert d.utc_ticks("0001-01-01T00:00:00+00:00") == 0
    assert d.utc_ticks("1970-01-01T00:00:00+00:00") == 621355968000000000
    assert d.utc_ticks("1970-01-01T00:00:00.000001+00:00") == 621355968000000010


@pytest.mark.parametrize("value", ["2026-10-29T08:00:00", "2026-10-29T09:00:00+01:00", "2026-10-29T07:00:00-01:00"])
def test_no_naive_or_nonUTC(value):
    with pytest.raises(RuntimeError):
        d.utc_ticks(value)


def test_fixed_window_boundary_and_no_runtime_parse(original):
    xml = candidate(original)
    condition = d.core.tree(xml).find("./inbound")[2].find("when").get("condition")
    low, high = d.utc_ticks(START), d.utc_ticks(END)
    assert high-low == 1200*10_000_000
    assert f"DateTime.UtcNow.Ticks < {low}L" in condition
    assert f"DateTime.UtcNow.Ticks >= {high}L" in condition
    for now, closed in [(low-1, True), (low, False), (high-1, False), (high, True)]:
        assert (now < low or now >= high) is closed
    assert "Parse" not in condition and "ToUniversalTime" not in xml


def test_bindings_restore_historical_module_on_error():
    original_out, original_scope, original_once = d.core.OUT, d.core.scope_guard, d.core.once
    with pytest.raises(ValueError):
        with d.bindings():
            assert d.core.OUT == d.OUT != d.OLD
            assert d.core.scope_guard is d.scope_guard and d.core.once is d.once
            raise ValueError()
    assert (d.core.OUT, d.core.scope_guard, d.core.once) == (original_out, original_scope, original_once)


MUTATIONS = old.test_exact_guard_rejects_mutation.pytestmark[0].args[1]


@pytest.mark.parametrize("before,after", [pair for pair in MUTATIONS if not pair[0].startswith("DateTime.")]
                         + [("DateTime.UtcNow.Ticks &gt;=", "DateTime.UtcNow.Ticks &gt;"),
                            (str(d.utc_ticks(START))+"L", str(d.utc_ticks(START)+1)+"L"),
                            (str(d.utc_ticks(END))+"L", str(d.utc_ticks(END)+1)+"L")])
def test_exact_same_original_mutation_guards(original, before, after):
    with d.bindings():
        old.test_exact_guard_rejects_mutation(original, before, after)


@pytest.mark.parametrize("start,end", [(START, START), (END, START),
    (START, "2026-10-29T08:20:00.000001+00:00"),
    ("2026-10-29T08:00:00", "2026-10-29T08:20:00")])
def test_same_window_guards(original, start, end):
    with d.bindings(), pytest.raises(RuntimeError):
        d.core.render(original, NONCE, start, end)


def test_all_original_safety_and_terminal_contracts(original):
    with d.bindings():
        old.test_original_retained_terminal_score_after_two_scans(original)
        for tag in ("base", "cors"):
            old.test_no_base_or_cors_removal(original, tag)
        for action in ("trace", "retry", "forward-request", "set-backend-service"):
            old.test_no_extra_diagnostic_actions(original, action)
    assert len(d.expression_audit(candidate(original))["expressions"]) > 0


@pytest.mark.parametrize("member", ["ToUniversalTime", "ToLocalTime", "ParseExact", "SpecifyKind", "ToBinary", "ToFileTime", "InventedMember"])
def test_member_audit_all_branches_rejects(original, member):
    xml = candidate(original).replace("</on-error>", f'<set-body>@(DateTime.UtcNow.{member}())</set-body></on-error>')
    with pytest.raises(RuntimeError):
        d.expression_audit(xml)


def test_production_date_members_are_already_supported():
    audit = d.production_audit()
    assert audit["date_expressions"] == ["DateTime.UtcNow.Ticks"]*2
    assert audit["change_required"] is False and audit["APIM_compile_proven"] is False


def test_predecessor_and_real_entire_candidate_audited_offline():
    # Actual retained XML, not just synthetic fixtures. Replace only the rejected
    # scope node to exercise the exact real copied expressions offline.
    history = d.predecessor()
    root = d.core.tree((d.OLD / "diagnostic.xml").read_bytes())
    inbound = root.find("inbound")
    inbound.remove(inbound[2]); inbound.insert(2, d.scope_guard(START, END))
    audit = d.expression_audit(d.core.ET.tostring(root))
    assert audit["expression_count"] == 103
    assert history == d.predecessor()


def test_actual_failure_reproduced_offline_audit_rejects_old_XML():
    with pytest.raises(RuntimeError):
        d.expression_audit((d.OLD / "diagnostic.xml").read_bytes())


def test_sanitized_compiler_error_no_raw_expression_or_secret():
    secret = "Bearer NEVER_SAVE subscription-key=NEVER_SAVE"
    raw = json.dumps({"error": {"code": "ValidationError", "message": secret,
        "details": [{"message": "Error in choose: Usage of member 'ToUniversalTime()' of type 'System.DateTime' is not supported within expressions. " + secret}]}}).encode()
    result = d.safe_compilation_error(raw)
    assert result["arm_error_code"] == "ValidationError"
    assert result["unsupported_members"] == [{"member": "ToUniversalTime()", "type": "System.DateTime"}]
    assert "NEVER_SAVE" not in json.dumps(result) and result["error_body_retained"] is False


@pytest.mark.parametrize("raw", [b"not json", b"x"*65537, b"null", b"[]", b'{"error":{"code":"Bearer secret","message":"arbitrary"}}'],
                         ids=["malformed", "oversized", "null", "array", "untrusted-code"])
def test_unknown_errors_suppressed(raw):
    assert d.safe_compilation_error(raw) == {"error_body_retained": False}


@pytest.mark.parametrize("stage", ["online", "offline", "create", "send"])
def test_no_other_stage_can_mutate(stage):
    with patch.object(d.core, "execute") as called, pytest.raises(RuntimeError):
        d.execute(stage)
    called.assert_not_called()


def test_spawn_target_rebinds_new_package(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "OUT", tmp_path)
    (tmp_path / "policy-put.json").write_bytes(b'{"fixture":"diagnostic02"}')
    with d.bindings():
        req = d.core.mutation_request("policy-put", '"fresh-etag"', "memory-only-fixture")
    assert req.data == b'{"fixture":"diagnostic02"}'
    assert req.method == "PUT" and req.full_url == d.core.POLICY_URL
    assert req.headers["If-match"] == '"fresh-etag"'
    assert "with bindings()" in inspect.getsource(d.wire_child)


def test_inherited_one_shot_review_guards_unchanged():
    execute = inspect.getsource(d.core.execute)
    assert execute.index('os.fsync') < execute.index('result = once(')
    assert '.open("x"' in execute and "unlink" not in execute
    for text in ("review(stage)", 'candidate=stage != "policy-put"', 'stage == "offline"', 'fresh_actual_etag_and_baseline'):
        assert text in execute
    assert "existing_intent_NO_RETRY" in inspect.getsource(d.core.review)
    assert "guard(original, candidate" in inspect.getsource(d.core.render)


def test_prepare_no_mutation_and_exclusive_output():
    text = inspect.getsource(d.prepare)
    assert "execute(" not in text and "once(" not in text
    assert "existing_package_reconcile_only" in text and 'open("xb")' in text
    assert "start + timedelta(minutes=20)" in text