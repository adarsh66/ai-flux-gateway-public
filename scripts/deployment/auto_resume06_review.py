"""Parent-owned review authority and direct browser tool capabilities.

Hashes provide integrity, not authority. The actual independent parent supplies
pins and its fixed identity allowlist from original tool results, never CLI JSON.
No approvals, identities, certificates, keys or executable verifiers are created.
"""
from __future__ import annotations
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit
from scripts.deployment import auto_resume_current_adapter as a
from scripts.deployment.auto_resume06_transport import canonical

ORIGIN = 'https://poc-ids-token-ex-customer.azurewebsites.net'
DOM = {'selected_model': 'gpt-5.4-mini', 'system': '', 'turns': 0,
    'draft': 'Please greet me in one short sentence.', 'send_disabled_until_route': True}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def at(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    a.require(result.utcoffset().total_seconds() == 0, 'review_UTC')
    return result


def page_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (parsed.scheme + '://' + parsed.netloc == ORIGIN and not parsed.query
        and not parsed.fragment and not parsed.username and parsed.path == '/playground')


class TrustedReview:
    """Only the independently reviewing parent constructs this capability.

    Parent selects identity from its fixed allowlist, and pins the exact original
    review tool result. Neither identity nor receipt digest is a root CLI option.
    """
    def __init__(self, path: Path, receipt_sha256: str, approved_identity: str,
                 parent_allowlist: frozenset[str], compiler_receipt: Path,
                 compiler_receipt_sha256: str):
        a.require(approved_identity in parent_allowlist and approved_identity != 'resume06-author',
            'parent_independent_identity_allowlist')
        self.path, self.pin, self.identity = path, receipt_sha256, approved_identity
        self.compiler, self.compiler_pin = compiler_receipt, compiler_receipt_sha256

    def __call__(self, kind: str, expected: dict, now=None):
        raw = self.path.read_bytes()
        a.require(sha(raw) == self.pin, 'parent_pinned_review_hash')
        value = json.loads(raw)
        a.require(set(value) == {'schema', 'reviewer', 'kind', 'decision', 'binding',
            'issued_at', 'expires_at', 'compiler_receipt_sha256', 'evidence'}, 'manual_review_schema')
        a.require(value['schema'] == 1 and value['reviewer'] == self.identity
            and value['kind'] == kind and value['decision'] == 'APPROVED'
            and value['binding'] == expected and isinstance(value['evidence'], list)
            and len(value['evidence']) > 0, 'exact_parent_independent_review_binding')
        now = now or datetime.now(UTC)
        a.require(at(value['issued_at']) <= now <= at(value['expires_at']), 'review_issued_expiry')
        raw_build = self.compiler.read_bytes()
        a.require(sha(raw_build) == self.compiler_pin == value['compiler_receipt_sha256'],
            'parent_pinned_compiler_receipt')
        build = json.loads(raw_build)
        a.require(set(build) == {'schema', 'inputs', 'outputs', 'compile_exit', 'semantic_exit', 'expressions'}
            and build['schema'] == 1 and build['compile_exit'] == build['semantic_exit'] == 0
            and build['expressions'] == 225, 'reviewed_native_compile_receipt')
        for group in ('inputs', 'outputs'):
            a.require(isinstance(build[group], dict) and build[group], 'compiler_files_required')
            for name, digest in build[group].items():
                path = Path(name)
                a.require(path.is_absolute() and not any(p.is_symlink() or p.is_junction()
                    for p in (path, *path.parents)), 'compiler_no_link')
                a.require(sha(path.read_bytes()) == digest, 'compiler_or_DLL_hash_drift')
        source = str(Path(__file__).with_name('auto_resume06_native.cs'))
        a.require(source in build['inputs'] and any(name.endswith('csc.dll') for name in build['inputs'])
            and any(name.endswith('Resume06Native.dll') for name in build['outputs']), 'recursive_native_binding')
        a.require(expected.get('sources', {}).get('scripts/deployment/auto_resume06_native.cs')
            == build['inputs'][source], 'fixed_reviewed_native_source_hash')
        return value


class ParentBrowser:
    """Parent-owned existing-tool invoke/inspect, not configurable IPC.

    invoke(export, binding, timeout) uses the trusted native browser channel.
    inspect(page_id, request_id) independently inspects mounted DOM/response and
    returns its actual tool handle. Capability is ephemeral, never logged or sent
    in a URL. Hashes and self-reported browser metrics alone grant no authority.
    """
    def __init__(self, invoke, inspect, page_id: str, url: str, source_sha256: str):
        a.require(callable(invoke) and callable(inspect) and page_url(url), 'actual_parent_browser_required')
        self.invoke, self.inspect = invoke, inspect
        self.page_id, self.url, self.source = page_id, url, source_sha256
        self.used, self.preflight_hash, self.preflight_keys = False, None, frozenset()

    def _call(self, phase, binding, timeout):
        a.require(0 < timeout <= 30, 'single_browser_deadline')
        a.require(binding.get('browser_source_sha256') == self.source, 'parent_reviewed_browser_source')
        challenge = {'phase': phase, 'capability': secrets.token_hex(32),
            'request_id': secrets.token_hex(32), 'page_id': self.page_id,
            'page_url': self.url, 'origin': ORIGIN, 'manifest_sha256': binding['manifest_sha256'],
            'browser_source_sha256': self.source, 'issued_at': datetime.now(UTC).isoformat()}
        start = time.monotonic()
        # Do not let an adapter mutate the expected challenge by aliasing it.
        result = self.invoke(phase, {**binding, 'channel': dict(challenge)}, timeout)
        a.require(time.monotonic() - start < timeout, 'browser_deadline_expired')
        a.require(isinstance(result, dict) and result.get('channel') == challenge,
            'browser_capability_origin_request_binding')
        evidence = self.inspect(self.page_id, challenge['request_id'], timeout - (time.monotonic() - start))
        a.require(time.monotonic() - start < timeout, 'inspection_deadline_expired')
        a.require(isinstance(evidence.get('tool_result_handle'), str) and evidence['tool_result_handle']
            and evidence.get('request_id') == challenge['request_id']
            and evidence.get('page_id') == self.page_id and evidence.get('page_url') == self.url
            and evidence.get('dom') == result.get('dom') == DOM,
            'actual_parent_independent_DOM_inspection')
        if phase == 'score':
            a.require(isinstance(result.get('server_correlation'), str) and result['server_correlation']
                and evidence.get('server_correlation') == result['server_correlation']
                and evidence.get('completion_request_count') == 0
                and evidence.get('scoring_request_count') == 1, 'actual_server_correlation_zero_completion')
        result = dict(result)
        result.pop('channel')
        result['parent_inspection_handle'] = evidence['tool_result_handle']
        result['request_id'] = challenge['request_id']
        if phase == 'score':
            result['completion_request_count'] = 0
            result['scoring_request_count'] = 1
        return result

    def observe(self, binding, timeout=30):
        a.require(not self.used and self.preflight_hash is None, 'browser_preflight_no_replay')
        # Reserve even a failed preflight: no second original attempt.
        self.preflight_hash = 'RESERVED'
        value = self._call('observe', binding, timeout)
        self.preflight_hash, self.preflight_keys = sha(canonical(value)), frozenset(value)
        return value

    def validate_preflight(self, value):
        a.require(not self.used and self.preflight_hash == sha(canonical(value)),
            'parent_actual_preflight_handle_required')

    def score(self, binding, timeout):
        self.validate_preflight({key: value for key, value in binding.items() if key in self.preflight_keys})
        self.used = True
        return self._call('score', binding, timeout)