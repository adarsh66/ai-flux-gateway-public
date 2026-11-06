"""Finite file handoff for an OUTER native-tool parent, never a browser callback.

Disk hashes establish integrity, not tool origin or review authority. The parent
must pin original tool outputs independently. This CLI supports a read-only
mounted integration probe; it cannot grant live authority from JSON. In
particular no available off-laptop cleanup supervisor has been implemented.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / '.deployment/auto-resume09'
PAGE = '73973940-4718-42f8-8f59-4c5623ba1926'
URL = 'https://poc-ids-token-ex-customer.azurewebsites.net/playground'
MODEL_NAMES = frozenset(('gpt-5.6-luna', 'gpt-5.4-mini', 'claude-haiku-5-5',
    'claude-opus-4-8', 'claude-opus-5-5', 'claude-opus-5-5-fast', 'claude-sonnet-5-5',
    'DeepSeek-V4-Flash', 'DeepSeek-V4-Pro', 'FW-GLM-5.3', 'FW-MiniMax-M3', 'glm-5.3',
    'gpt-4o', 'gpt-6.1-sol', 'gpt-6.1-terra', 'gpt-6-luna', 'grok-4-1-fast-reasoning',
    'grok-4-20-reasoning', 'grok-4.3', 'Kimi-K2.7-Code', 'Mistral-Large-3', 'mistral-medium-3-5'))
NEW = ('scripts/deployment/auto_resume09_handoff.py',
    'scripts/deployment/auto_resume09_probe.js', 'scripts/deployment/auto_resume09_offline.py',
    'tests/unit/test_auto_resume09.py', 'tests/auto_resume09_probe.test.mjs',
    'docs/auto-resume09-handoff.md')
LIVE = ('prepare', 'install', 'activate', 'reserve-score')
# The old ledger remains the single diagnostic budget owner. NEVER reset or
# substitute a successor-only ledger when eventual live composition is reviewed.
GLOBAL_SCORE_OWNER = ROOT / '.deployment/auto-resume06-isolated-score-owner.json'
BLOCKERS = (
    'independent_source09_review_and_recursive_compiler_pins_not_registered',
    'off_laptop_expiry_cleanup_supervisor_not_implemented_or_verified',
    'native_one_POST_and_independent_server_correlation_handoff_not_implemented',
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe(path):
    require(path.is_absolute(), 'absolute_path_required')
    require(not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)), 'no_link_artifacts')


def exclusive(path, value):
    safe(path)
    raw = value if isinstance(value, bytes) else canonical(value)
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return sha(raw)


def load(path):
    safe(path)
    raw = path.read_bytes()
    require(len(raw) <= 1024 * 1024, 'bounded_receipt')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_JSON_key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: require(False, 'finite_JSON'))


def at(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    require(value.tzinfo is not None and value.utcoffset() == timedelta(0), 'UTC_required')
    return value


def sources():
    result = {}
    for name in NEW:
        safe(ROOT / name)
        result[name] = sha((ROOT / name).read_bytes())
    return result


def localcheck():
    """Rehash actual retained bytes; do not call source06's expanding glob map."""
    original = load(ROOT / '.deployment/auto-resume04/successor-offline-freeze.json')['current280_sources']
    highfix = load(ROOT / '.deployment/auto-resume06/highfix10/full-source-hashes-after.json')
    resume07 = load(ROOT / '.deployment/auto-resume07/validation01/source-hashes-before.json')
    six = load(ROOT / '.deployment/auto-resume06/highfix10/REPORT.json')
    require(six['tests'] == {'count': 23, 'failures': 0, 'errors': 0, 'skipped': 0, 'browser_exit': 0}
        and six['native']['compile_exit'] == six['native']['semantic_exit'] == 0
        and six['native']['expressions'] == 225, 'retained_highfix10_test_provenance')
    # Resume08 intentionally corrected these eight06 files after resume07.
    changed06 = frozenset((
        'scripts/deployment/auto_resume06_parent.py', 'scripts/deployment/auto_resume06_transport.py',
        'scripts/deployment/auto_resume06_review.py', 'scripts/deployment/auto_resume06_browser.mjs',
        'scripts/deployment/auto_resume06_native.cs', 'scripts/deployment/auto_resume06_offline.py',
        'tests/unit/test_auto_resume06.py', 'tests/auto_resume06_browser.test.mjs'))
    maps = {'original280': original, 'highfix10': highfix,
        'resume07_protected': {k: v for k, v in resume07.items() if k not in changed06}}
    verified = {}
    for label, mapping in maps.items():
        for name, digest in mapping.items():
            path = ROOT / name
            safe(path)
            require(sha(path.read_bytes()) == digest, 'frozen_drift:' + name)
        verified[label] = len(mapping)
    # Include every retained file in the frozen05/07/highfix10 trees in the new
    # evidence, even files not named by their historical source maps.
    retained = {}
    for tree in ('auto-resume05', 'auto-resume07', 'auto-resume06/highfix10', 'auto-live01'):
        for path in sorted((ROOT / '.deployment' / tree).rglob('*')):
            safe(path)
            if path.is_file():
                retained[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    return {'schema': 9, 'verified': verified, 'sources': sources(), 'retained': retained,
        'live_blockers': list(BLOCKERS), 'authority': 'integrity_only_not_approval'}


def request_source(request):
    """Emit the actual supported tool body; no imports, eval, listener or storage."""
    source = (ROOT / 'scripts/deployment/auto_resume09_probe.js').read_text(encoding='utf-8')
    return 'return await (' + source.strip() + ')(page, ' + canonical(request).decode() + ');\n'


def check_folder(folder):
    safe(folder)
    require(folder.parent == HOME and folder.name.startswith('mounted-'), 'finite_mounted_folder')


def begin(folder, now=None):
    """No prepare/window/budget side effects. An incomplete intent is consumed."""
    check_folder(folder)
    binding = localcheck()
    now = now or datetime.now(UTC)
    at(now.isoformat())
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': 9, 'kind': 'read_only_mounted_integration', 'page_id': PAGE,
        'page_url': URL, 'sources': binding['sources'], 'retained': binding['retained'],
        'issued_at': now.isoformat(), 'expires_at': (now + timedelta(minutes=5)).isoformat()}
    manifest_hash = exclusive(folder / 'manifest.json', manifest)
    request = {'schema': 9, 'phase': 'mounted-observe', 'request_id': secrets.token_hex(32),
        'page_id': PAGE, 'page_url': URL, 'manifest_sha256': manifest_hash,
        'sources_sha256': sha(canonical(binding['sources'])),
        'issued_at': now.isoformat(), 'expires_at': manifest['expires_at']}
    exclusive(folder / 'observe-request.json', request)
    exclusive(folder / 'observe-tool.js', request_source(request).encode())
    return request


def checked(folder, now):
    check_folder(folder)
    require(not (folder / 'closed.json').exists(), 'handoff_closed')
    manifest = load(folder / 'manifest.json')
    require(set(manifest) == {'schema', 'kind', 'page_id', 'page_url', 'sources', 'retained',
        'issued_at', 'expires_at'}, 'finite_manifest')
    require(manifest['schema'] == 9 and manifest['kind'] == 'read_only_mounted_integration'
        and manifest['page_id'] == PAGE and manifest['page_url'] == URL, 'manifest_scope')
    actual = localcheck()
    require(manifest['sources'] == actual['sources'] and manifest['retained'] == actual['retained'],
        'source_or_retained_drift')
    require(at(manifest['issued_at']) <= now < at(manifest['expires_at']), 'handoff_expired')
    return manifest


def validate_result(request, envelope, expected_tool_handle):
    # The handle comes from the parent's ORIGINAL tool output. Merely putting a
    # plausible handle in this file does not establish authority (see receipt).
    require(set(envelope) == {'tool', 'tool_result_handle', 'page_id', 'result'}, 'finite_tool_envelope')
    require(envelope['tool'] == 'run_playwright_code' and expected_tool_handle
        and envelope['tool_result_handle'] == expected_tool_handle
        and envelope['page_id'] == PAGE, 'original_parent_tool_pin')
    value = envelope['result']
    require(set(value) == {'binding', 'observed_at', 'page_url', 'dom'}, 'finite_probe_result')
    require(value['binding'] == request and value['page_url'] == URL, 'phase_page_request_manifest_binding')
    require(at(request['issued_at']) <= at(value['observed_at']) < at(request['expires_at']), 'probe_time_binding')
    dom = value['dom']
    require(set(dom) == {'model_names', 'selected_model', 'subscription', 'system_empty',
        'draft_empty', 'turns', 'empty_conversation', 'send_enabled', 'customer'}, 'finite_DOM_projection')
    require(isinstance(dom['model_names'], list) and len(dom['model_names']) == 22
        and frozenset(dom['model_names']) == MODEL_NAMES and dom['selected_model'] == 'gpt-5.6-luna'
        and dom['subscription'] == 'Caldova-AI' and dom['customer'] == 'Caldova'
        and dom['system_empty'] is True and dom['draft_empty'] is True
        and type(dom['turns']) is int and dom['turns'] == 0
        and dom['empty_conversation'] is True and dom['send_enabled'] is True, 'mounted_DOM_mismatch')
    return value


def accept_result(folder, phase, result_file, result_pin, original_tool_handle, now=None):
    """External tool await boundary: no resident Python or callable tool adapter.

    At-most-once acceptance is consumed BEFORE parsing/checking the input. Failed
    and expired handoffs cannot be revived with replacement JSON. No raw browser
    snapshot, message content, credential or token is persisted by this API.
    """
    check_folder(folder)
    require(phase in ('mounted-observe', 'mounted-inspect'), 'finite_readonly_phase')
    now = now or datetime.now(UTC)
    prefix = 'observe' if phase == 'mounted-observe' else 'inspect'
    exclusive(folder / (prefix + '-accept-intent.json'), {'phase': phase, 'attempts': 1})
    manifest = checked(folder, now)
    request = load(folder / (prefix + '-request.json'))
    require(request['phase'] == phase and request['page_id'] == manifest['page_id']
        and request['page_url'] == manifest['page_url']
        and request['manifest_sha256'] == sha((folder / 'manifest.json').read_bytes())
        and request['sources_sha256'] == sha(canonical(manifest['sources']))
        and request['issued_at'] == manifest['issued_at']
        and request['expires_at'] == manifest['expires_at']
        and len(request['request_id']) == 64, 'request_file_binding')
    require((folder / (prefix + '-tool.js')).read_bytes() == request_source(request).encode(), 'emitted_tool_drift')
    safe(result_file)
    require(sha(result_file.read_bytes()) == result_pin, 'original_parent_result_hash')
    value = validate_result(request, load(result_file), original_tool_handle)
    require(at(value['observed_at']) <= now and (now - at(value['observed_at'])).total_seconds() < 60,
        'fresh_tool_result')
    if phase == 'mounted-inspect':
        first = load(folder / 'observe-accepted.json')
        require(first['dom'] == value['dom'] and first['tool_result_handle'] != original_tool_handle,
            'independent_inspection_required')
    receipt = {'schema': 9, 'phase': phase, 'request_id': request['request_id'],
        'tool_result_handle': original_tool_handle, 'result_sha256': result_pin,
        'manifest_sha256': request['manifest_sha256'], 'accepted_at': now.isoformat(), 'dom': value['dom'],
        'authority': 'parent_must_independently_pin_original_tool_output_NO_LIVE_AUTHORITY'}
    exclusive(folder / (prefix + '-accepted.json'), receipt)
    if phase == 'mounted-observe':
        follow = {**request, 'phase': 'mounted-inspect', 'request_id': secrets.token_hex(32)}
        exclusive(folder / 'inspect-request.json', follow)
        exclusive(folder / 'inspect-tool.js', request_source(follow).encode())
    return receipt


def live_boundary(stage):
    """A writable JSON 'watchdog_armed' or 'APPROVED' never enables a stage.

    No live adapter is shipped: cannot prove independent cleanup survives parent
    suspension, laptop loss, token expiry or transport failure. Refusal precedes
    prepare, captures, windows, ledger claims and mutation intents.
    """
    require(stage in LIVE, 'finite_live_stage')
    raise ValueError(stage + '_BLOCKED:' + ';'.join(BLOCKERS))


def cleanup(folder):
    """Read-only close. Do not equate this with remote offline/restore cleanup."""
    check_folder(folder)
    receipt = {'schema': 9, 'phase': 'close-readonly-handoff',
        'remote_cleanup': 'NOT_EXECUTED_NO_REMOTE_WRITES_PERMITTED',
        'remote_obligations_if_ever_enabled': ['offline_owned_revision_independent_fresh_ETag',
            'restore_owned_global_independent_fresh_ETag'], 'live_blockers': list(BLOCKERS)}
    exclusive(folder / 'closed.json', receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('localcheck', 'mounted-begin', 'accept-result', 'cleanup', *LIVE))
    parser.add_argument('--folder', type=Path)
    parser.add_argument('--phase', choices=('mounted-observe', 'mounted-inspect'))
    parser.add_argument('--result', type=Path)
    parser.add_argument('--result-sha256')
    parser.add_argument('--original-tool-handle')
    args = parser.parse_args(argv)
    if args.stage in LIVE:
        return live_boundary(args.stage)
    if args.stage == 'localcheck':
        return localcheck()
    require(args.folder is not None, 'folder_required')
    if args.stage == 'mounted-begin':
        return begin(args.folder)
    if args.stage == 'cleanup':
        return cleanup(args.folder)
    require(all((args.phase, args.result, args.result_sha256, args.original_tool_handle)), 'actual_parent_pins_required')
    return accept_result(args.folder, args.phase, args.result, args.result_sha256, args.original_tool_handle)


if __name__ == '__main__':
    try:
        print(json.dumps(main(), sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'STOP_NO_REPLAY', 'reason': str(error)}))
        raise SystemExit(2)