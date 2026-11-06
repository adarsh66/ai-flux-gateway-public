"""Independent offline preservation boundaries; no esbuild or native builds."""
import json
from pathlib import Path

import pytest

from scripts.deployment.apim_raw_auto_splice import compose, proof_tree
from scripts.deployment.auto_resume_current_adapter import xml_tree

R = Path(__file__).resolve().parents[2]
H = R / '.deployment/auto-shared-ratecard-20261101-01'


def inputs():
    original = (H / 'gateway18-raw-offline/predecessor.xml').read_bytes()
    template = (R / 'gateway/policies/auto-resolve.xml.tftpl').read_bytes()
    expected = (H / 'gateway-admin17/offline/candidate.xml').read_bytes()
    return original, template, expected


def test_independent_prefix_suffix_and_native():
    original, template, expected = inputs()
    actual, proof = compose(original, template, expected)
    assert actual == (H / 'gateway18-raw-offline/candidate.xml').read_bytes()
    assert actual[:54138] == original[:54138]
    assert actual[74509:] == original[65193:]
    for marker in (b'<outbound>', b'<on-error>'):
        assert actual[actual.index(marker):] == original[original.index(marker):]
    assert proof_tree(actual) == xml_tree(expected.decode())
    assert proof['whole_policy_reserialization'] is False


def test_literal_finops_quotes_and_newlines_unchanged():
    original, template, expected = inputs()
    actual, _ = compose(original, template, expected)
    marker = b'<set-variable name="aiflux-finops-usage"'
    old = original[original.index(marker):]
    new = actual[actual.index(marker):]
    assert old == new
    assert b'value="@{\n' in new and b'&#10;' not in new
    assert actual.count(b'\r') >= original.count(b'\r')


def test_missing_unique_auto_fails_closed():
    original, template, expected = inputs()
    with pytest.raises(AssertionError):
        compose(original.replace(b'name="aiflux-auto-result"', b'name="not-auto-result"'), template, expected)


def test_other_native_mutation_fails_closed():
    original, template, expected = inputs()
    with pytest.raises(AssertionError):
        compose(original, template, expected.replace(b'aiflux-finops-usage', b'changed-finops-usage'))