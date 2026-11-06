"""One versioned fragment envelope; each data-only inclusion skips controls.

Recognize the prior two-branch envelope exactly. Reject unknown branch layouts
rather than accidentally executing dormant controls or dropping sibling data.
"""
from copy import deepcopy
import json
import xml.etree.ElementTree as ET

PRICE_MODE = "aiflux-auto-price-only"
PRICE_VARIABLE = "aiflux-auto-price-projection"
ACCESS_MODE = "aiflux-model-access-only"
ACCESS_VARIABLE = "aiflux-model-access-projection"
MARKER = "aiflux-settings-envelope-v2"


def condition(mode):
    return '@(context.Variables.GetValueOrDefault<bool>("' + mode + '", false))'


def parse(value):
    if len(value.encode()) > 65536:
        raise ValueError("Shared fragment exceeds 64KiB")
    root = ET.fromstring(value)
    if root.tag != "fragment" or root.attrib:
        raise ValueError("Expected bounded settings fragment")
    children = list(root)
    versioned = bool(children and children[0].tag == "set-variable" and children[0].get("name") == MARKER)
    if versioned:
        if children[0].attrib != {"name": MARKER, "value": "2"} or len(children) != 2:
            raise ValueError("Unknown settings envelope version")
        children = children[1:]
    price = access = None
    if len(children) == 1 and children[0].tag == "choose":
        choose = children[0]
        expected = [(ACCESS_MODE, ACCESS_VARIABLE), (PRICE_MODE, PRICE_VARIABLE)] if versioned else [(PRICE_MODE, PRICE_VARIABLE)]
        if len(choose) != len(expected) + 1 or choose.attrib or choose[-1].tag != "otherwise" or choose[-1].attrib:
            if versioned:
                raise ValueError("Unknown settings envelope branches")
            return value, None, None
        data = {}
        for branch, (mode, variable) in zip(list(choose)[:-1], expected):
            if (branch.tag != "when" or branch.attrib != {"condition": condition(mode)} or len(branch) != 1
                    or branch[0].tag != "set-variable" or branch[0].get("name") != variable
                    or set(branch[0].attrib) != {"name", "value"} or len(branch[0])):
                raise ValueError("Unknown settings envelope branch")
            encoded = branch[0].get("value", "")
            if not encoded.startswith('@(@"') or not encoded.endswith('")'):
                raise ValueError("Invalid projection literal")
            literal = encoded[4:-2].replace('""', '"')
            data[variable] = json.loads(literal) if literal else None
        out = ET.Element("fragment")
        out.extend(deepcopy(list(choose[-1])))
        return ET.tostring(out, encoding="unicode"), data.get(PRICE_VARIABLE), data.get(ACCESS_VARIABLE)
    if versioned:
        raise ValueError("Missing settings envelope branches")
    return value, price, access


def render(controls, price=None, access=None):
    original = ET.fromstring(controls)
    if original.tag != "fragment" or original.attrib:
        raise ValueError("Expected controls fragment")
    if price is None and access is None:
        return controls
    root = ET.Element("fragment")
    if access is not None:
        ET.SubElement(root, "set-variable", name=MARKER, value="2")
    choose = ET.SubElement(root, "choose")
    branches = [(ACCESS_MODE, ACCESS_VARIABLE, access)] if access is not None else []
    branches.append((PRICE_MODE, PRICE_VARIABLE, price))
    for mode, variable, data in branches:
        when = ET.SubElement(choose, "when", condition=condition(mode))
        literal = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) if data is not None else ""
        ET.SubElement(when, "set-variable", name=variable, value='@(@"' + literal.replace('"', '""') + '")')
    otherwise = ET.SubElement(choose, "otherwise")
    otherwise.extend(deepcopy(list(original)))
    result = ET.tostring(root, encoding="unicode")
    if len(result.encode()) > 65536:
        raise ValueError("Shared settings fragment exceeds 64KiB")
    return result