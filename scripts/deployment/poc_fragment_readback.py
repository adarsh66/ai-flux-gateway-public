"""Strict detached-fragment readback; never normalize C# or counter text.

APIM's xml export adds one XML entity layer to attribute/text values already
escaped in rawxml. Require BOTH exports to agree, not a permissive unescape of
the authoritative rawxml. Only whitespace between child elements is cosmetic.
"""
import xml.etree.ElementTree as ET
from xml.sax.saxutils import unescape


def structure(value, *, export_layer=False):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    root = ET.fromstring(value, parser=parser)

    def decode(text):
        return unescape(text, {"&quot;": '"', "&apos;": "'"}) if export_layer else text

    def node(element):
        if not isinstance(element.tag, str):
            raise ValueError("unexpected_comment_or_processing_instruction")
        children = list(element)
        text = element.text or ""
        if children and not text.strip():
            text = ""
        tails = []
        for child in children:
            tail = child.tail or ""
            tails.append(decode(tail) if tail.strip() else "")
        return (element.tag, tuple(sorted((k, decode(v)) for k, v in element.attrib.items())),
                decode(text), tuple((node(child), tail) for child, tail in zip(children, tails)))

    return node(root)


def differences(expected, actual, path="/fragment"):
    """Return exact differing semantic fields, including significant text."""
    result = []
    for index, field in ((0, "tag"), (1, "attributes"), (2, "text")):
        if expected[index] != actual[index]:
            result.append({"path": path + "/" + field,
                           "expected": expected[index], "actual": actual[index]})
    if len(expected[3]) != len(actual[3]):
        result.append({"path": path + "/child_count", "expected": len(expected[3]), "actual": len(actual[3])})
    for index, ((left, tail_left), (right, tail_right)) in enumerate(zip(expected[3], actual[3])):
        child_path = path + "/" + str(index) + ":" + str(left[0])
        result.extend(differences(left, right, child_path))
        if tail_left != tail_right:
            result.append({"path": child_path + "/tail", "expected": tail_left, "actual": tail_right})
    return result


def compare(expected, rawxml, xml_export):
    reference = structure(expected)
    raw = structure(rawxml)
    exported = structure(xml_export, export_layer=True)
    raw_diff = differences(reference, raw)
    export_diff = differences(raw, exported)
    return {"semantic_equal": not raw_diff and not export_diff,
            "rawxml_expected_differences": raw_diff,
            "xml_export_rawxml_differences": export_diff,
            "xml_export_extra_entity_layer": structure(xml_export) != raw,
            "normalization": "XML parsing; inter-element indentation only; exactly one XML-export entity layer"}