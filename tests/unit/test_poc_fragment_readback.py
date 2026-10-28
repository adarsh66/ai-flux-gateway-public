"""Offline strict readback regression tests; never call Azure."""
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import pytest

from scripts.deployment import poc_fragment_bootstrap as b
from scripts.deployment.poc_fragment_readback import compare, structure


def exported(raw):
    tree = ET.fromstring(raw)
    for node in tree.iter():
        for key, value in list(node.attrib.items()):
            node.set(key, escape(value, {'"': "&quot;", "'": "&apos;"}))
    return ET.tostring(tree, encoding="unicode")


def test_actual_apim_serialization_extra_entity_layer():
    expected = b.DEFAULTS.read_text()
    tree = ET.fromstring(expected)
    ET.indent(tree, space="\t")
    raw = ET.tostring(tree, encoding="unicode").replace("\n", "\r\n")
    result = compare(expected, raw, exported(raw))
    assert result["semantic_equal"]
    assert result["xml_export_extra_entity_layer"]
    assert not result["rawxml_expected_differences"]
    assert not result["xml_export_rawxml_differences"]


@pytest.mark.parametrize("old,new", [
    ('@(60)', '@(61)'), ('@(2048)', '@(2049)'), ('@(10000)', '@(10001)'),
    ('@(1000)', '@(1001)'), ('@(1)', '@(2)'), ('calls="1000"', 'calls="999"'),
    ('renewal-period="86400"', 'renewal-period="3600"'), ('project-demo:', 'project-demo:new:'),
    ('context.Subscription.Id', 'context.Product.Id'), (' ?? ', ' + '),
    ('@&quot;{}&quot;', '@&quot;{ }&quot;'), ('var owners', 'var  owners'),
    ('&quot;&quot;', '&quot; &quot;'),
])
def test_substantive_csharp_and_counter_changes_not_normalized(old, new):
    expected = b.DEFAULTS.read_text()
    raw = expected.replace(old, new)
    assert raw != expected
    result = compare(expected, raw, exported(raw))
    assert not result["semantic_equal"]
    assert result["rawxml_expected_differences"]


def test_child_order_is_significant():
    raw = '<fragment><b /><a /></fragment>'
    assert not compare('<fragment><a /><b /></fragment>', raw, exported(raw))["semantic_equal"]


@pytest.mark.parametrize("raw", ['<fragment><a> x </a></fragment>', '<fragment><a> </a></fragment>',
                                 '<fragment><a />changed<b /></fragment>'])
def test_significant_leaf_or_tail_text_is_preserved(raw):
    assert not compare('<fragment><a>x</a></fragment>', raw, exported(raw))["semantic_equal"]


def test_entity_spelling_and_attribute_order_are_serialization():
    expected = '<fragment><a x="&quot;" y="&amp;" /></fragment>'
    raw = '<fragment>\n<a y="&#38;" x="&#34;"/>\n</fragment>'
    assert compare(expected, raw, exported(raw))["semantic_equal"]


def test_no_recursive_unescape_or_rawxml_entity_waiver():
    expected = b.DEFAULTS.read_text()
    raw = expected.replace('&quot;', '&amp;quot;')
    assert not compare(expected, raw, exported(raw))["semantic_equal"]
    assert not compare(expected, expected, exported(exported(expected)))["semantic_equal"]


def test_cross_export_csharp_disagreement_rejected():
    expected = b.DEFAULTS.read_text()
    assert not compare(expected, expected, exported(expected.replace('project-demo:', 'other:')))["semantic_equal"]


@pytest.mark.parametrize("value", ['<fragment><!--comment--></fragment>', '<fragment><?pi test?></fragment>',
                                  '<fragment><a value="@("invalid")" /></fragment>'])
def test_invalid_or_unexpected_content_fails_closed(value):
    with pytest.raises((ValueError, ET.ParseError)):
        structure(value)


def test_reconciliation_reader_refuses_mutations_and_terraform():
    from scripts.deployment.poc_fragment_reconcile import ReadOnly
    reader = object.__new__(ReadOnly)
    for method in ('PUT', 'PATCH', 'POST', 'DELETE'):
        with pytest.raises(RuntimeError, match='get_only'):
            reader.arm('/policyFragments/' + b.FRAGMENT, method)
    with pytest.raises(RuntimeError, match='terraform_prohibited'):
        reader.terraform('apply')