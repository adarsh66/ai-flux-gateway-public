from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import patch
import xml.etree.ElementTree as ET

import pytest

from scripts.deployment import auto_diagnostic_stage as d

NONCE = "a" * 32
START = "2026-10-29T08:00:00+00:00"
END = "2026-10-29T08:20:00+00:00"


@pytest.fixture
def original():
    # Original copied policy export is bound only after actual preparation. This
    # fixture exercises structure; the real-policy guard runs during preparation.
    return '''<policies><inbound><cors><allowed-origins><origin>https://existing.example</origin></allowed-origins></cors><base />
    <choose><when condition='@(context.Subscription == null || context.Product == null || context.Product.Id != "aiflux")'><return-response><set-status code="403" reason="closed" /></return-response></when></choose>
    <choose><when condition='@(context.Request.Method == "POST")'>
    <set-variable name="aiflux-request-json" value="@(fixed)" />
    <set-variable name="aiflux-model" value="@(model)" />
    <quota-by-key calls="1000" renewal-period="86400" counter-key="project-demo:original" />
    <rate-limit-by-key calls="60" renewal-period="60" counter-key="rpm:original" />
    <llm-token-limit counter-key="tpm:original" tokens-per-minute="2048" token-quota="10000" />
    <llm-content-safety backend-id="original"><categories><category name="Hate" threshold="1" /></categories></llm-content-safety>
    <send-request response-variable-name="original-pii"><set-url>https://existing.example/pii</set-url></send-request>
    <set-body>@(redacted)</set-body>
    <llm-content-safety backend-id="original"><categories><category name="Hate" threshold="1" /></categories></llm-content-safety>
    <set-backend-service backend-id="original" />
    </when></choose></inbound><backend><forward-request /></backend><outbound><base /><llm-content-safety backend-id="original" /></outbound><on-error><base /></on-error></policies>'''


def candidate(original):
    return d.render(original, NONCE, START, END)


def test_original_retained_terminal_score_after_two_scans(original):
    value = candidate(original)
    assert d.guard(original, value, NONCE, START, END)
    root = d.tree(value)
    branch = d.post(root)
    gate = branch.find("limit-concurrency")
    assert list(branch).index(gate) < next(i for i, n in enumerate(branch) if n.tag == "set-backend-service")
    assert gate[-1].tag == "return-response"
    assert len(root.findall(".//llm-content-safety")) == 3
    assert len(root.findall(".//forward-request")) == 1  # Retained, unreachable.
    assert len(root.findall(".//quota-by-key")) == 2  # Original identity never reset.


@pytest.mark.parametrize("before,after", [
    ('calls="1000"', 'calls="1001"'), ('threshold="1"', 'threshold="7"'),
    ('tokens-per-minute="2048"', 'tokens-per-minute="2049"'),
    ('counter-key="rpm:original"', 'counter-key="rpm:new"'),
    ('counter-key="project-demo:original"', 'counter-key="reset"'),
    ('https://existing.example/pii', 'https://other.example/pii'),
    ('https://existing.example</origin>', 'https://other.example</origin>'),
    ('context.Subscription == null', 'false'), ('context.Product == null', 'false'),
    ('context.Product.Id != &quot;aiflux&quot;', 'false'),
    (d.IP, '127.0.0.1'), (d.SUBSCRIBER, 'other-sub'),
    ('messages.Count != 1', 'messages.Count != 2'), (d.TEXT, 'customer prompt'),
    ('https://cognitiveservices.azure.com/', 'https://ai.azure.com/'),
    ('5792b72e-1605-4dce-a594-4c430a5af619', 'new-identity'),
    ('/providers/microsoft/v1/systemone', '/openai/v1/chat/completions'),
    ('timeout="15"', 'timeout="60"'), ('calls="1"', 'calls="2"'),
    ('max-count="1"', 'max-count="2"'), ('65536', '6553600'),
    ('preserveContent: false', 'preserveContent: true'),
    ('DateTime.UtcNow &gt;=', 'DateTime.UtcNow &gt;'),
])
def test_exact_guard_rejects_mutation(original, before, after):
    xml = candidate(original)
    assert before in xml
    with pytest.raises(RuntimeError):
        d.guard(original, xml.replace(before, after), NONCE, START, END)


@pytest.mark.parametrize("tag", ["base", "cors"])
def test_no_base_or_cors_removal(original, tag):
    root = d.tree(candidate(original))
    parent = root.find("inbound")
    parent.remove(parent.find(tag))
    with pytest.raises(RuntimeError):
        d.guard(original, ET.tostring(root), NONCE, START, END)


@pytest.mark.parametrize("kind", ["trace", "retry", "forward-request", "set-backend-service"])
def test_no_extra_diagnostic_actions(original, kind):
    root = d.tree(candidate(original))
    d.post(root).find("limit-concurrency").insert(2, ET.Element(kind))
    with pytest.raises(RuntimeError):
        d.guard(original, ET.tostring(root), NONCE, START, END)


@pytest.mark.parametrize("start,end", [(START, START), (START, "2026-10-29T08:21:00+00:00"),
                                       ("2026-10-29T08:00:00", "2026-10-29T08:20:00")])
def test_window_fails_closed(original, start, end):
    with pytest.raises(RuntimeError):
        d.render(original, NONCE, start, end)


def test_scope_only_diagnostic_not_general_auto(original):
    root = d.tree(candidate(original))
    gate = root.find("./inbound")[2].find("when").get("condition")
    for text in (d.IP, d.SUBSCRIBER, d.CHAT_PATH, START, END, 'context.Api.Revision != "2"', 'context.Product.Id != "aiflux"'):
        assert text in gate
    assert '"auto"' not in candidate(original)


def test_fixed_wire_no_customer_body_or_completion():
    root = d.tree(d.TEMPLATE.read_bytes())
    req = root.find("send-request")
    body = json.loads(req.findtext("set-body"))
    assert body["state"] == d.TEXT and body["model"] == "Decision-1"
    assert set(body["questions"]["route"]["criteria"]) == {"greeting", "arithmetic"}
    assert not req.findall(".//forward-request") and not req.findall(".//retry")
    assert "context.Request" not in req.findtext("set-body")


@pytest.mark.parametrize("etag", [None, "*", "", "invented", '"x"\r\nAuthorization: other'])
def test_actual_etag_required(etag):
    with pytest.raises(RuntimeError):
        d.mutation_request("offline", etag, "memory-only-test-token")


@pytest.mark.parametrize("stage,method,body", [
    ("online", "PATCH", b'{"properties":{"isOnline":true}}'),
    ("offline", "PATCH", b'{"properties":{"isOnline":false}}')])
def test_literal_patch_scope_and_body(stage, method, body):
    request = d.mutation_request(stage, '"actual-fixture-etag"', "memory-only-fixture-token")
    assert request.method == method and request.data == body and request.full_url == d.a.URL
    assert request.headers["If-match"] == '"actual-fixture-etag"'


def test_unknown_stage_no_request():
    with pytest.raises(RuntimeError):
        d.mutation_request("create", '"etag"', "unused")


def test_exact_expression_spaces_entities_not_folded():
    one = '<policies><set-body>@{ return "a &amp;amp; b"; }</set-body></policies>'
    decoded = d.tree(one, exported=True)
    assert decoded.findtext("set-body") == '@{ return "a & b"; }'
    assert d.signature(d.tree('<p value="a  b" />')) != d.signature(d.tree('<p value="a b" />'))
    assert d.signature(d.tree('<p>@{ return "&amp;amp;"; }</p>')) != d.signature(d.tree('<p>@{ return "&amp;"; }</p>'))


def test_template_never_returns_auth_or_raw():
    root = d.tree(d.TEMPLATE.read_bytes())
    expr = root.find("set-variable").get("value")
    assert 'summary["usage"]' in expr and 'JValue.CreateNull()' in expr
    assert 'Content-Length' in expr and '65536' in expr
    assert 'return raw' not in expr and 'return result' not in expr
    assert '"Authorization"' not in expr
    assert root[-1].findtext("set-body") == '@((string)context.Variables["auto-diagnostic-summary"])'


def test_prepare_is_read_only_source_contract():
    import inspect
    source = inspect.getsource(d.prepare)
    assert "execute(" not in source and "once(" not in source
    assert "capture(reads" in source


def test_no_mutation_without_actual_review(monkeypatch, tmp_path):
    monkeypatch.setattr(d, "OUT", tmp_path)
    with pytest.raises(FileNotFoundError):
        d.execute("policy-put")


def test_stage_intents_exclusive_no_unlink():
    import inspect
    source = inspect.getsource(d.execute)
    assert '.open("x"' in source and "os.fsync" in source
    assert source.index('os.fsync') < source.index('result = once(')
    assert 'unlink' not in source


@pytest.mark.parametrize("raw", ['<p value="@(x == "a")" />', '<p value="@(x == &quot;a&quot;)" />'])
def test_raw_export_complete_known_expression(raw):
    expected = d.tree('<p value="@(x == &quot;a&quot;)" />')
    if '&quot;' in raw:
        with pytest.raises(RuntimeError):
            d.raw_signature(raw, expected)  # Not an observed raw quote representation.
    else:
        assert d.raw_signature(raw, expected) == d.signature(expected)


@pytest.mark.parametrize("raw", ['<p value="@(x == "b")" />', '<p value="@(x == "a")" extra="yes" />'])
def test_raw_expression_or_structure_drift_rejected(raw):
    with pytest.raises(RuntimeError):
        d.raw_signature(raw, d.tree('<p value="@(x == &quot;a&quot;)" />'))