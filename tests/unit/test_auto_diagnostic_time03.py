import inspect

import pytest

from scripts.deployment import auto_diagnostic_time03 as t

START = "2026-10-29T08:00:00+00:00"
END = "2026-10-29T08:20:00+00:00"


def test_actual_compiled_policy_time_only_and_same_nonce_counters():
    before = (t.w.DIAG / "diagnostic.xml").read_bytes()
    after = t.time_only(START, END)
    assert before != after.encode()
    assert t.c.signature(t.c.tree(after).find("inbound")[2]) == t.c.signature(t.d.scope_guard(START, END))
    original = t.w.check_compilation()
    with t.d.bindings():
        assert t.c.guard(t.a.load(t.w.DIAG / "prepare-capture.json")["normalized_original"],
                         after, original["nonce"], START, END)
    assert (t.w.DIAG / "diagnostic.xml").read_bytes() == before
    assert t.d.expression_audit(after)["expression_count"] == 103


@pytest.mark.parametrize("start,end", [(START, START), (END, START),
    (START, "2026-10-29T08:21:00+00:00"), ("2026-10-29T08:00:00", END)])
def test_time_only_no_unbounded_or_naive_window(start, end):
    with pytest.raises(RuntimeError):
        t.time_only(start, end)


def test_new_source_never_exposes_online_or_browser_or_score():
    main = inspect.getsource(t.main)
    assert 'choices=("prepare-review", "policy-put")' in main
    assert 'method="PUT"' in inspect.getsource(t.wire_child)
    assert inspect.getsource(t.wire_child).count(".open(") == 1
    assert "safe_compilation_error" in inspect.getsource(t.wire_child)
    assert "rx.poll(60)" in inspect.getsource(t.once)


def test_prepare_is_offline_and_never_refreshes_existing_package():
    text = inspect.getsource(t.prepare)
    assert "existing_diagnostic03_never_refresh" in text
    for action in ("capture(", "once(", "execute(", "Reads("):
        assert action not in text
    assert '"nonce": old["nonce"]' in text


def test_literal_offline_pre_and_post_and_exclusive_before_wire():
    text = inspect.getsource(t.execute)
    assert '"policy-put-before", False)' in text
    assert '"policy-put-after", False, OUT / "diagnostic.xml")' in text
    assert text.index('w.exclusive("policy-put-intent.json"') < text.index('result = once(')
    assert "fresh_actual_policy_ETag" in text
    assert "post_PUT_source_history_state_exact" in text