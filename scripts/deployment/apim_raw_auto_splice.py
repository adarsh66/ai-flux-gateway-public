"""Splice the bounded Auto pricing delta; never serialize protected policy XML.

APIM rawxml is Razor input and may contain literal C# quotes inside double
quoted XML attributes. XML parsing is used only on a disposable proof view.
"""
import hashlib
import re

from scripts.deployment.auto_resume_current_adapter import xml_tree

FIELDS = ('pricing_revision', 'pricing_sha256', 'pricing_source',
          'pricing_stale', 'cost_suitability_fallback')


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def proof_tree(raw: bytes):
    """Decode a proof-only XML view without altering supplied wire bytes."""
    text = raw.decode('utf-8')
    parts = re.split(r'(<!\[CDATA\[.*?\]\]>|<!--.*?-->)', text, flags=re.S)
    for index in range(0, len(parts), 2):
        parts[index] = re.sub(
            r'(\s[\w:-]+=)"(@.*?)"(?=\s*/?>|\s+[\w:-]+=)',
            lambda match: match[1] + "'" + match[2].replace("'", '&apos;') + "'",
            parts[index], flags=re.S)
    return xml_tree(''.join(parts))


def element_span(raw: bytes, tag: bytes, name: bytes, start: int = 0, end: int | None = None):
    pattern = rb'<' + tag + rb'\s+name="' + re.escape(name) + rb'"\s+value=".*?"\s*/>'
    matches = list(re.finditer(pattern, raw[start:end], flags=re.S))
    assert len(matches) == 1, 'exact_unique_element_required:' + name.decode()
    match = matches[0]
    return start + match.start(), start + match.end()


def compose(predecessor: bytes, template: bytes, expected_native: bytes):
    snapshot_start, insertion_at = element_span(predecessor, b'set-variable', b'aiflux-auto-snapshot')
    result_start, result_end = element_span(predecessor, b'set-variable', b'aiflux-auto-result')
    inbound_end = predecessor.index(b'</inbound>')
    trace_start, trace_end = element_span(predecessor, b'metadata', b'payload', result_end, inbound_end)
    assert snapshot_start < insertion_at < result_start < result_end < trace_start < trace_end < inbound_end
    reset = b'<set-variable name="aiflux-auto-price-only" value="@(true)" />'
    begin = template.index(reset)
    finish = template.index(b'<set-variable name="aiflux-auto-started"', begin)
    addition = b'\r\n\t\t\t\t\t\t' + template[begin:finish].rstrip().replace(
        b'${pricing_fragment}', b'aiflux-dev-unified-poc-settings')
    assert b'${' not in addition and addition.count(b'<include-fragment') == 1
    old = b'if (profileName == "cost" &amp;&amp; snapshot["candidates"][selected]["price"].Type == JTokenType.Null)'
    new = b'if (profileName == "cost" &amp;&amp; !(bool)snapshot["cost_suitability_fallback"] &amp;&amp; snapshot["candidates"][selected]["price"].Type == JTokenType.Null)'
    result = predecessor[result_start:result_end]
    assert result.count(old) == 1
    result = result.replace(old, new)
    for owner, original, label in [(b'snapshot', result, 'result'),
                                   (b'route', predecessor[trace_start:trace_end], 'trace')]:
        anchor = b'["config_version"] = (string)' + owner + b'["version"],' if owner == b'snapshot' else b'["config_version"] = (string)route["config_version"],'
        assert original.count(anchor) == 1, 'exact_metadata_anchor_required'
        added = b'\n' + b'\n'.join(b'                ["' + field.encode() + b'"] = ' + owner + b'["' + field.encode() + b'"],' for field in FIELDS)
        value = original.replace(anchor, anchor + added)
        if label == 'result':
            result = value
        else:
            trace = value
    edits = [(insertion_at, insertion_at, addition),
             (result_start, result_end, result), (trace_start, trace_end, trace)]
    candidate = predecessor
    for start, end, replacement in reversed(edits):
        candidate = candidate[:start] + replacement + candidate[end:]
    # Independent cursor comparison proves every untouched interval byte-exact.
    intervals, old_cursor, new_cursor = [], 0, 0
    for start, end, replacement in edits:
        untouched = predecessor[old_cursor:start]
        assert candidate[new_cursor:new_cursor + len(untouched)] == untouched
        intervals.append({'predecessor_start': old_cursor, 'predecessor_end': start,
                          'candidate_start': new_cursor, 'length': len(untouched),
                          'sha256': digest(untouched), 'exact': True})
        new_cursor += len(untouched)
        assert candidate[new_cursor:new_cursor + len(replacement)] == replacement
        new_cursor += len(replacement)
        old_cursor = end
    suffix = predecessor[old_cursor:]
    assert candidate[new_cursor:] == suffix
    intervals.append({'predecessor_start': old_cursor, 'predecessor_end': len(predecessor),
                      'candidate_start': new_cursor, 'length': len(suffix),
                      'sha256': digest(suffix), 'exact': True})
    # A second, independent inverse operation must recover the original bytes.
    recovered = candidate
    offset = 0
    inverse = []
    for start, end, replacement in edits:
        inverse.append((start + offset, start + offset + len(replacement), predecessor[start:end]))
        offset += len(replacement) - (end - start)
    for start, end, replacement in reversed(inverse):
        recovered = recovered[:start] + replacement + recovered[end:]
    assert recovered == predecessor, 'inverse_raw_byte_reconstruction_failed'
    assert proof_tree(candidate) == xml_tree(expected_native.decode('utf-8')), 'reviewed_native_delta_changed'
    assert proof_tree(recovered) == proof_tree(predecessor), 'protected_decoded_native_changed'
    assert predecessor[predecessor.index(b'<outbound>'):] == candidate[candidate.index(b'<outbound>'):]
    return candidate, {'passed': True, 'predecessor_sha256': digest(predecessor),
        'candidate_sha256': digest(candidate), 'edits': 3,
        'untouched_intervals': intervals, 'inverse_raw_exact': True,
        'decoded_native_equals_reviewed_candidate': True, 'protected_decoded_native_exact': True,
        'outbound_onerror_suffix_bytes_exact': True, 'whole_policy_reserialization': False,
        'APIM_acceptance': 'NOT_PROVEN_OFFLINE'}