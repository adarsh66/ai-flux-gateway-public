"""Pure current-base diagnostic renderer; no historical executor or transport imports.

The caller supplies actual same-format current XML and its immutable binding.
Only four attribute paths may change. Current explicit22 is never rewritten.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import unescape

from scripts.deployment.auto_resume_current_adapter import auto_references, require

IP = '167.103.66.248'
SUBSCRIBER = 'e9f2abb0-930b-598a-b210-0ab0b279127f'
GLOBAL_PATH = '/policies/inbound[0]/choose[0]/when[0]/@condition'
SCOPE_PATH = '/policies/inbound[0]/choose[0]/when[0]/@condition'


def sha(raw):
    return hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest()


def tree(raw, exported=False):
    text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
    require('<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(), 'DTD_entity_forbidden')
    # XML attribute newlines must not become spaces. No C# whitespace folding.
    parts = re.split(r'(<!\[CDATA\[.*?\]\]>|<!--.*?-->)', text, flags=re.S)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'''(\s[\w:-]+=)("[^"]*"|'[^']*')''',
            lambda m: m[1] + m[2].replace('\r', '&#xD;').replace('\n', '&#xA;').replace('\t', '&#x9;'), parts[i])
    root = ET.fromstring(''.join(parts), parser=ET.XMLParser(
        target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))
    if exported:
        def decode(value):
            return unescape(value, {'&quot;': '"', '&apos;': "'"}) if value.startswith('@') else value
        for node in root.iter():
            node.attrib.update({k: decode(v) for k, v in node.attrib.items()})
            if node.text:
                node.text = decode(node.text)
    return root


def flatten(root):
    """Complete finite tree, including C# text, comments and significant tails."""
    result = {}
    def visit(node, path):
        result[path + '/tag'] = node.tag if isinstance(node.tag, str) else node.tag.__name__
        result[path + '/text'] = '' if len(node) and not (node.text or '').strip() else node.text or ''
        result[path + '/tail'] = node.tail if (node.tail or '').strip() else ''
        for key, value in node.attrib.items():
            result[path + '/@' + key] = value
        counts = {}
        for child in node:
            tag = child.tag if isinstance(child.tag, str) else child.tag.__name__
            index = counts.get(tag, 0)
            counts[tag] = index + 1
            visit(child, path + '/' + tag + '[' + str(index) + ']')
    visit(root, '/policies')
    return result


def delta(before, after):
    left, right = flatten(before), flatten(after)
    return {path: {'before': left.get(path), 'after': right.get(path)}
            for path in sorted(left.keys() | right.keys()) if left.get(path) != right.get(path)}


def times(start, end):
    require(all(isinstance(x, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', x)
                for x in (start, end)), 'literal_UTC_seconds')
    begin, finish = (datetime.fromisoformat(x) for x in (start, end))
    require(timedelta(0) < finish - begin <= timedelta(minutes=30), 'inclusive30_no_extension')
    return begin, finish


def expression(start, end):
    begin, finish = times(start, end)
    def ticks(at):
        difference = at - datetime(1, 1, 1, tzinfo=UTC)
        return str((difference.days * 86400 + difference.seconds) * 10_000_000) + 'L'
    return ('context.Api != null && (context.Api.Id == "aiflux-dev-unified"'
        ' || context.Api.Id == "aiflux-dev-unified;rev=2") && context.Api.Revision == "2"'
        ' && context.Subscription != null && context.Product != null'
        ' && context.Product.Id == "aiflux" && context.Subscription.Id == "' + SUBSCRIBER + '"'
        ' && context.Request.Method == "POST" && context.Request.IpAddress == "' + IP + '"'
        ' && (context.Request.OriginalUrl.Path == "/dev/llm/v1/chat/completions"'
        ' || context.Request.OriginalUrl.Path == "/dev/llm/v1;rev=2/chat/completions")'
        ' && DateTime.UtcNow.Ticks >= ' + ticks(begin) + ' && DateTime.UtcNow.Ticks < ' + ticks(finish))


def parts(revision):
    inbound = revision.find('inbound')
    require(inbound is not None and inbound[0].tag == 'cors' and inbound[1].tag == 'base', 'CORS_base_order')
    scope = inbound[2].find('when')
    require(scope is not None and 'diagnostic_scope_closed' in ET.tostring(scope, encoding='unicode'), 'owned_scope_guard')
    branches = inbound.findall('./choose/when[@condition=\'@(context.Request.Method == "POST")\']')
    require(len(branches) == 1, 'single_POST_branch')
    branch = branches[0]
    gates = branch.findall('limit-concurrency')
    require(len(gates) == 1, 'single_diagnostic_gate')
    gate = gates[0]
    safety = [i for i, n in enumerate(branch) if n.tag == 'llm-content-safety']
    require(len(safety) == 2 and list(branch).index(gate) == safety[-1] + 1,
            'scoring_after_redaction_safety_before_dispatch')
    require(gate.get('max-count') == '1' and gate[0].tag == 'quota-by-key'
        and gate[0].attrib == {'calls': '1', 'renewal-period': '3600', 'counter-key': gate.get('key')}, 'quota_one')
    require(len(gate) == 5 and gate[-1].tag == 'return-response'
        and len(gate.findall('.//send-request')) == 1
        and gate.find('send-request').get('id') == 'auto-diagnostic-score'
        and gate.find('send-request/set-url').text ==
            'https://poc-ids-token-ex-foundry.services.ai.azure.com/providers/microsoft/v1/systemone'
        and not gate.findall('.//retry') and not gate.findall('.//forward-request'), 'one_score_terminal_no_completion')
    require('Please greet me in one short sentence.' in ET.tostring(branch, encoding='unicode'), 'fixed_synthetic_input')
    return scope, gate


def render(global_xml, owned_xml, explicit_xml, binding, start, end, nonce, auto_only):
    """Binding comes from a new current fixture/package, never old13 substitutions."""
    require(binding == {'global': sha(global_xml), 'owned': sha(owned_xml), 'explicit': sha(explicit_xml)}, 'actual_current_XML_binding')
    require(re.fullmatch('[a-f0-9]{32}', nonce) is not None, 'fresh_nonce_shape')
    auto_references({'explicit': explicit_xml}, auto_only)
    original_global, original_owned = tree(global_xml, True), tree(owned_xml, True)
    global_tree, revision = deepcopy(original_global), deepcopy(original_owned)
    guard = global_tree.find('./inbound/choose/when')
    require(guard is not None, 'global_guard_required')
    old = guard.get('condition')
    require(old.startswith('@(') and old.endswith(')'), 'global_expression_wrapper')
    expected = expression(start, end)
    guard.set('condition', '@((' + old[2:-1] + ') && !(' + expected + '))')
    scope, gate = parts(revision)
    key = '@("auto-diagnostic:' + nonce + '")'
    require(key != gate.get('key'), 'counter_not_historical_reuse')
    scope.set('condition', '@(!(' + expected + '))')
    gate.set('key', key)
    gate[0].set('counter-key', key)
    global_delta = delta(original_global, global_tree)
    revision_delta = delta(original_owned, revision)
    expected_revision = {path for path in flatten(original_owned) if
        path == SCOPE_PATH or path.endswith('/limit-concurrency[0]/@key')
        or path.endswith('/limit-concurrency[0]/quota-by-key[0]/@counter-key')}
    require(set(global_delta) == {GLOBAL_PATH} and set(revision_delta) == expected_revision
        and len(expected_revision) == 3, 'finite_attribute_delta_only')
    def wire(value):
        raw = ET.tostring(value, encoding='utf-8')
        require(flatten(tree(raw)) == flatten(value), 'serialized_XML_all_CSharp_characters_exact')
        return raw
    return {'global.xml': wire(global_tree), 'revision.xml': wire(revision),
        'restore-global.xml': global_xml.encode() if isinstance(global_xml, str) else global_xml,
        'explicit.xml': explicit_xml.encode() if isinstance(explicit_xml, str) else explicit_xml,
        'proof': {'global_delta': global_delta, 'revision_delta': revision_delta,
            'input_sha256': dict(binding), 'explicit22_unchanged': True,
            'scoring_budget': 1, 'completion_budget': 0, 'retry_budget': 0}}


def prove(candidate, *args, **kwargs):
    expected = render(*args, **kwargs)
    require(candidate == expected, 'candidate_exact_finite_delta_and_serialized_bytes')
    return expected['proof']