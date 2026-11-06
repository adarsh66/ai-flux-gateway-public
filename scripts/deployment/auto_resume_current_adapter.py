"""Pure current-baseline boundaries. No imports of historical executors."""
from copy import deepcopy
from datetime import timedelta
from html import unescape
import hashlib
import json
import re
from urllib.parse import unquote
import xml.etree.ElementTree as ET

TENANT = 'beb276ac-6e9f-498e-8e31-019ee666decd'
OPERATOR = 'dd928302-055b-4516-9b8e-b06ae823057b'
STORAGE = 'https://storage.azure.com/'
ARM = 'https://management.azure.com/'
ADDED = frozenset(('Mistral-Large-3', 'claude-haiku-5-5', 'claude-opus-4-8',
    'claude-opus-5-5', 'claude-opus-5-5-fast', 'claude-sonnet-5-5',
    'gpt-6-luna', 'gpt-6.1-terra', 'mistral-medium-3-5'))


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def token_claims(claims, audience, now):
    require(claims.get('tid') == TENANT and claims.get('oid') == OPERATOR
            and claims.get('aud') == audience and claims.get('exp', 0)-now > 600,
            'exact_identity_audience_TTL600')
    return dict(tenant=TENANT, operator=OPERATOR, audience=audience,
                expiry=claims['exp'], token_persisted=False)


def keyed_state(state):
    result = deepcopy(state)
    rows = result['check_results']
    require(isinstance(rows, list), 'complete_check_list')
    keyed = {}
    for row in rows:
        key = (row['object_kind'], row['config_addr'])
        require(all(isinstance(k, str) and k for k in key) and key not in keyed, 'unique_whole_checks')
        keyed[key] = row
    result['check_results'] = keyed
    return result


def state_equal(before, after):
    return keyed_state(before) == keyed_state(after)


def roles_equal(before, after):
    def indexed(rows):
        result = {}
        for row in rows:
            key = row['id'].casefold()
            require(key not in result, 'duplicate_role_identity')
            result[key] = row
        return result
    return indexed(before) == indexed(after)


def xml_tree(text, exported=False):
    """Only XML decoding; never strip/rewrite any C# expression character."""
    require('<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(), 'DTD_entity')
    parts = re.split(r'(<!\[CDATA\[.*?\]\]>|<!--.*?-->)', text, flags=re.S)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'''(\s[\w:-]+=)("[^"]*"|'[^']*')''',
            lambda m: m[1]+m[2].replace('\r', '&#xD;').replace('\n', '&#xA;').replace('\t', '&#x9;'), parts[i])
    root = ET.fromstring(''.join(parts), parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))
    def decode(value):
        return unescape(value) if exported and value.startswith('@') else value
    def node(item):
        content = item.text or ''
        return [item.tag if isinstance(item.tag, str) else item.tag.__name__,
                sorted((k, decode(v)) for k, v in item.attrib.items()),
                '' if len(item) and not content.strip() else decode(content),
                [[node(c), c.tail if (c.tail or '').strip() else ''] for c in item]]
    return node(root)


def auto_references(explicit_routes, auto_only):
    """New9 explicit routes are legitimate. Only the Auto surface is restricted."""
    require(isinstance(explicit_routes, dict) and isinstance(auto_only, dict), 'separate_reference_namespaces')
    text = json.dumps(auto_only, sort_keys=True).casefold()
    for _ in range(3):
        text = unescape(unquote(text))
    require(not any(name.casefold() in text for name in ADDED), 'new9_in_original_Auto_pool_or_fragments')


def window(start, end, now):
    require(all(v.tzinfo is not None and v.utcoffset() == timedelta(0) for v in (start, end, now)), 'UTC_window')
    require(timedelta(0) < end-start <= timedelta(minutes=30)
            and start <= now and end-now >= timedelta(minutes=22), 'inclusive30_cleanup_reserve22')
    return (end-now).total_seconds()


def etag(value):
    require(isinstance(value, str) and len(value) > 2 and value.startswith('"')
            and value.endswith('"') and '\r' not in value and '\n' not in value, 'actual_strong_ETag')
    return value


def contract():
    return {'stages': ['install-global', 'install-revision', 'online', 'reserve', 'offline', 'restore-global'],
        'window_minutes_max_inclusive': 30, 'cleanup_reserve_minutes': 22,
        'scoring_budget': 1, 'completion_budget': 0, 'retries': 0,
        'admission_ip': '167.103.66.248', 'APIM_IP_preproof_required': False,
        'APIM_source_mismatch': 'fail_closed_during_one_budget_call_no_retry_no_firewall_change',
        'parent_finally': ['offline_exact_owned_revision', 'restore_exact_current_global_all22'],
        'parent_review_required': ['independent_native_exact_source', 'later_exact_package_audit'],
        'Auto': 'OFF_PENDING_VALIDATION', 'task_complete': False}