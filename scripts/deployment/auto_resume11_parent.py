"""Successor11: immutable10 reuse, full checkpoint BEFORE independent browser reads.

No live action on import. Native parent owns original review/result authority and
outer try/finally. A recent full baseline is NOT a claim of atomic cloud state.
"""
from __future__ import annotations

from datetime import timedelta
from copy import deepcopy
from pathlib import Path
from types import FunctionType
import json
import secrets
import time
from urllib.request import Request

from scripts.deployment import auto_resume10_parent as ten
from scripts.deployment.auto_resume06_transport import Transport as BaseTransport
from scripts.deployment.auto_resume06_transport import old, a, p as five, OWNED, canonical

ROOT = ten.ROOT
HOME = ROOT / '.deployment/auto-resume11'
NEW = ('scripts/deployment/auto_resume11_parent.py', 'scripts/deployment/auto_resume11_browser.js',
       'scripts/deployment/auto_resume11_offline.py', 'tests/unit/test_auto_resume11.py',
       'tests/auto_resume11_browser.test.mjs', 'docs/auto-resume11-handoff.md')
require, sha, load, at, now = ten.require, ten.sha, ten.load, ten.at, ten.now


def frozen10():
    report = load(ROOT / '.deployment/auto-resume10/validation02/REPORT.json')
    require(report['status'] == 'OFFLINE_PASS', 'actual10_retained_validation')
    mapping = ten.sources()
    require(mapping == report['sources'], 'immutable10_bound_bytes')
    return mapping


def sources():
    result = frozen10()
    result.update({name: sha((ROOT / name).read_bytes()) for name in NEW})
    return dict(sorted(result.items()))


def localcheck():
    prior = ten.localcheck()
    retained = dict(prior['retained'])
    for path in sorted((ROOT / '.deployment/auto-resume10').rglob('*')):
        ten.nine.safe(path)
        if path.is_file(): retained[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    return {'sources': sources(), 'frozen': prior['frozen'], 'retained': retained,
            'authority': 'INTEGRITY_ONLY_NOT_APPROVAL'}


# Copy10 executable functions into a PRIVATE namespace. Never mutate10 globals.
# This preserves its complete stages, cleanup reconciliation, lock, owner ledger,
# independent original receipt review and all whole-state guard algorithms.
_ns = dict(ten.__dict__)
_ns.update(HOME=HOME, NEW=NEW, sources=sources, localcheck=localcheck)
for _name, _fn in vars(ten).items():
    if isinstance(_fn, FunctionType) and _fn.__module__ == ten.__name__:
        if _name not in ('sources', 'localcheck'):
            _ns[_name] = FunctionType(_fn.__code__, _ns, _name, _fn.__defaults__, _fn.__closure__)
globals().update({name: value for name, value in _ns.items()
                  if isinstance(value, FunctionType) and value.__globals__ is _ns})

# Only schema/review/module literals differ in these copied functions; rewriting
# code constants is forbidden. These small wrappers map the exact10 contract
# through a private cloned code object's constants, recursively and explicitly.
def _literal_copy(function, replacements):
    from types import CodeType
    def constant(value):
        if isinstance(value, CodeType): return rewrite(value)
        if isinstance(value, tuple): return tuple(constant(v) for v in value)
        if isinstance(value, frozenset): return frozenset(constant(v) for v in value)
        return replacements.get(value, value) if isinstance(value, (str, int)) else value
    def rewrite(code):
        return code.replace(co_consts=tuple(constant(v) for v in code.co_consts))
    return FunctionType(rewrite(function.__code__), _ns, function.__name__,
                        function.__defaults__, function.__closure__)


for _name in ('prepare', 'checked', 'authorized', 'arm', 'main', 'review_binding'):
    _ns[_name] = _literal_copy(_ns[_name], {
        'source10': 'source11', 'package10': 'package11', 'successor10-author': 'successor11-author',
        'scripts.deployment.auto_resume10_parent': 'scripts.deployment.auto_resume11_parent',
        'successor10-': 'successor11-', 'new10_package_scope': 'new11_package_scope', 10: 11})
    globals()[_name] = _ns[_name]


class Transport(BaseTransport):
    """Closing reads only: exactly three strong-ETag GETs and unlocked root HEAD.

    No credential refresh/retry, policy mutation, omitted full projection, or lock
    bypass. A slow request fails timing gates rather than relaxing freshness.
    """
    def closing(self):
        token, _ = self.credentials.get(a.ARM)
        values, etags = {}, {}
        for key, suffix in (('global', '/policies/policy?format=xml&api-version=2024-05-01'),
                            ('policy', five.OWNED + '/policies/policy?format=xml&api-version=2024-05-01'),
                            ('api', five.OWNED + '?api-version=2024-05-01')):
            url = a.ARM.rstrip('/') + old.APIM + suffix
            with self.http.open(Request(url, headers={'Authorization': 'Bearer ' + token,
                    'Accept': 'application/json'}), timeout=8) as response:
                require(response.status == 200 and response.geturl() == url, 'closing_exact_HTTP200')
                etags[key] = five.strong_etag(response.headers.get('ETag'))
                raw = response.read(1024 * 1024 + 1)
                require(len(raw) <= 1024 * 1024, 'closing_bounded_body')
                values[key] = json.loads(raw)
        return {'etags': etags, 'values': values, 'root': self.root_head()}

    def root_head(self):
        token, claims = self.credentials.get(a.STORAGE)
        a.token_claims(claims, a.STORAGE, time.time())
        headers = {'Authorization': 'Bearer ' + token, 'x-ms-version': '2023-11-03',
                   'x-ms-date': now().strftime('%a, %d %b %Y %H:%M:%S GMT')}
        with self.http.open(Request(old.BLOB, method='HEAD', headers=headers), timeout=8) as response:
            require(response.status == 200 and response.geturl() == old.BLOB, 'closing_root_HTTP200')
            result = {'etag': five.strong_etag(response.headers.get('ETag')),
                      'lease_state': response.headers.get('x-ms-lease-state'),
                      'lease_status': response.headers.get('x-ms-lease-status')}
        root_available(result)
        return result


def root_available(root):
    five.strong_etag(root['etag'])
    require(root['lease_state'] == 'available' and root['lease_status'] == 'unlocked', 'root_lease_changed')


def closing_equal(full, closing, root):
    root_available(closing['root'])
    require(closing['root'] == root, 'root_ETag_or_lease_changed')
    require(closing['etags'] == full['etags'], 'closing_strong_ETag_changed')
    for value in closing['etags'].values(): five.strong_etag(value)
    require(closing['values']['api'] == full['owned'], 'closing_owned_metadata_changed')
    for slot, name in (('global', 'global'), ('policy', 'owned')):
        require(closing['values'][slot]['properties']['value'].encode() == full['policies'][name],
                'closing_exact_policy_readback_changed')


def checkpoint_score(folder, digest, port, clock=now):
    with operation(folder):
        m, before, payloads = checked(folder, digest)
        authorized(folder, digest)
        require(not (folder / 'observe-request.json').exists(), 'full_checkpoint_BEFORE_observe')
        require(not (folder / 'cleanup-request.json').exists(), 'cleanup_started')
        require((folder / 'online-verified.json').exists(), 'audited_activation_required')
        worker_fresh(folder, clock)
        reserve(m, clock)
        put(folder, 'check-score-intent.json', {'manifest_sha256': digest, 'attempts': 1})
        started = clock()  # age of ALL full projections, not just last HTTP read
        root = port.root_head()
        root_available(root)
        actual = guard(before, port.capture(), *expected(folder, before, payloads))
        closing = port.closing()
        closing_equal(actual, closing, root)
        require(0 <= (clock() - started).total_seconds() <= 90, 'full_checkpoint_max90')
        reserve(m, clock)
        worker_fresh(folder, clock)  # check AFTER expensive source/capture work
        pin = put(folder, 'check-score-full.json', ten.six.pack(actual))
        checkpoint = {'manifest_sha256': digest, 'nonce': m['nonce'],
            'started_at': started.isoformat(), 'finished_at': clock().isoformat(),
            'full_sha256': pin, 'root': root, 'closing': closing,
            'max_full_age_seconds': 90, 'full_guard': True}
        put(folder, 'check-score-verified.json', checkpoint)
        return checkpoint


def checkpoint_bound(folder, digest, m, clock):
    checkpoint = load(folder / 'check-score-verified.json')
    require(checkpoint['manifest_sha256'] == digest and checkpoint['nonce'] == m['nonce']
            and checkpoint['full_guard'] is True and checkpoint['max_full_age_seconds'] == 90,
            'checkpoint_manifest_nonce_binding')
    require(sha((folder / 'check-score-full.json').read_bytes()) == checkpoint['full_sha256'],
            'full_checkpoint_bytes_changed')
    require(at(checkpoint['started_at']) <= at(checkpoint['finished_at']) <= clock()
            and (clock() - at(checkpoint['started_at'])).total_seconds() <= 90, 'full_checkpoint_max90')
    actual = ten.six.unpack(load(folder / 'check-score-full.json'))
    require(actual['sources'] == m['sources'] == sources(), 'checkpoint_exact_source_changed')
    return checkpoint, actual


def emit(folder, digest, phase, clock=now):
    m, _, _ = checked(folder, digest)
    checkpoint = None
    if phase in ('observe', 'inspect', 'score'):
        checkpoint, _ = checkpoint_bound(folder, digest, m, clock)
    issued = clock()
    request = {'schema': 11, 'phase': phase, 'scope': 'ONE_SCORE_ZERO_COMPLETION_NO_RETRY',
        'manifest_sha256': digest, 'nonce': m['nonce'], 'challenge': secrets.token_hex(32),
        'issued_at': issued.isoformat(), 'expires_at': (issued + timedelta(seconds=30)).isoformat()}
    if checkpoint:
        request.update(checkpoint_sha256=sha((folder / 'check-score-verified.json').read_bytes()),
                       full_started_at=checkpoint['started_at'])
    if phase == 'score':
        reservation = load(folder / 'reserve-intent.json')
        require(reservation['manifest_sha256'] == digest, 'reservation_binding')
        request.update(activation_manifest_sha256=digest, window_end=m['end'],
            reservation_sha256=sha((folder / 'reserve-intent.json').read_bytes()),
            inspection_issued_at=load(folder / 'inspect-accepted.json')['value']['binding']['issued_at'])
        require(0 <= (clock() - at(request['inspection_issued_at'])).total_seconds() < 30,
                'fresh_independent_parent_inspection')
        reserve(m, clock)
        worker_fresh(folder, clock)
    put(folder, phase + '-request.json', request)
    source = (ROOT / NEW[1]).read_text(encoding='utf-8').strip()
    put(folder, phase + '-tool.js', ('return await (' + source + ')(page, '
                                   + canonical(request).decode() + ');\n').encode())
    return request


def reserve_score(folder, digest, port, clock=now):
    with operation(folder):
        m, before, payloads = checked(folder, digest)
        authorized(folder, digest)
        require(not (folder / 'cleanup-request.json').exists(), 'cleanup_started')
        checkpoint, full = checkpoint_bound(folder, digest, m, clock)
        guard(before, full, *expected(folder, before, payloads))
        inspected = load(folder / 'inspect-accepted.json')
        binding = inspected['value']['binding']
        require(binding['checkpoint_sha256'] == sha((folder / 'check-score-verified.json').read_bytes())
                and binding['nonce'] == m['nonce'] and binding['manifest_sha256'] == digest,
                'inspection_checkpoint_binding')
        require(at(binding['issued_at']) >= at(checkpoint['finished_at']), 'inspection_AFTER_full_capture')
        reserve(m, clock)
        worker_fresh(folder, clock)
        # NO full capture here. Three exact GETs + HEAD close the critical roots.
        closing = port.closing()
        closing_equal(full, closing, checkpoint['root'])
        put(folder, 'reserve-closing.json', {'at': clock().isoformat(), 'closing': closing})
        checkpoint_bound(folder, digest, m, clock)  # includes exact sources again
        require(0 <= (clock() - at(binding['issued_at'])).total_seconds() < 30,
                'fresh_independent_parent_inspection')
        reserve(m, clock)
        worker_fresh(folder, clock)
        put(folder, 'reserve-intent.json', {'manifest_sha256': digest, 'score': 1, 'completion': 0,
            'retry_budget': 0, 'checkpoint_sha256': sha((folder / 'check-score-verified.json').read_bytes()),
            'cleanup_due': (clock() + timedelta(seconds=45)).isoformat()})
        return emit(folder, digest, 'score', clock)


def serverproof(folder, digest, path=None, pin=None, reference=None):
    """Structural corroboration is distinct from an independently queried trace.

    No server nonce/manifest fields are assumed: they are linked locally through
    exact audited policy/quota-key, revision2 readback, window and correlation.
    Production remains blocked even when structural one-score proof succeeds.
    """
    m, before, payloads = checked(folder, digest)
    put(folder, 'serverproof-intent.json', {'attempts': 1})
    checkpoint = load(folder / 'check-score-verified.json')
    require(checkpoint['manifest_sha256'] == digest and checkpoint['nonce'] == m['nonce'], 'proof_nonce_binding')
    require(sha((folder / 'check-score-full.json').read_bytes()) == checkpoint['full_sha256'], 'proof_full_bytes')
    full = ten.six.unpack(load(folder / 'check-score-full.json'))
    guard(before, full, payloads['global.xml'], payloads['revision.xml'], True)
    ten.six.render.parts(ten.six.render.tree(payloads['revision.xml']))
    accepted = load(folder / 'score-accepted.json')
    result = accepted['value']
    request = load(folder / 'score-request.json')
    require(result['binding'] == request and request['nonce'] == m['nonce']
        and request['manifest_sha256'] == digest and request['activation_manifest_sha256'] == digest
        and request['reservation_sha256'] == sha((folder / 'reserve-intent.json').read_bytes())
        and request['checkpoint_sha256'] == sha((folder / 'check-score-verified.json').read_bytes()), 'proof_request_binding')
    require(result['observed_posts'] == 1 and result['forwarded'] is True
        and result['guard_retained_closed'] is True and result['http_status'] == 200
        and result['diagnostic_schema_valid'] is True and result['auth_inspected'] is False
        and result['raw_body_logged'] is False and bool(result['server_correlation']), 'structural_success_required')
    require(at(m['start']) <= at(result['request_started_at']) <= at(result['response_received_at']) < at(m['end'])
        and at(request['issued_at']) <= at(result['request_started_at']) < at(request['expires_at'])
        and at(result['response_received_at']) <= at(accepted['accepted_at']), 'actual_request_window')
    compiler_pin = load(folder / 'source-review-binding.json')['compiler']
    compiler(Path(compiler_pin['path']), compiler_pin['sha256'], compiler_pin['reference'])
    traces = {'status': 'UNVERIFIED_QUERY_NOT_AVAILABLE', 'production_blocked': True}
    if path is not None:
        original_pin = original(path, pin, reference)
        trace = load(path)
        # Original native trace query, parent establishes completeness. These are
        # evidence projection fields, NOT claimed emitted APIM metadata fields.
        require(trace['correlation'] == result['server_correlation'] and trace['complete_trace'] is True
            and trace['api_revision'] == '2' and trace['completion_requests'] == []
            and len(trace['score_requests']) == 1
            and trace['score_requests'][0]['operation'] == 'auto-diagnostic-score'
            and trace['score_requests'][0]['status'] == 200, 'actual_correlated_complete_trace')
        traces = {'status': 'VERIFIED_PARENT_ORIGINAL_QUERY', 'original': original_pin, 'production_blocked': True}
    proof = {'structural_one_score_zero_completion': True, 'not_trace_counter_proof': True,
        'manifest_sha256': digest, 'nonce_policy_link': m['nonce'], 'correlation': result['server_correlation'],
        'policy_sha256': sha(payloads['revision.xml']), 'full_readback_sha256': checkpoint['full_sha256'],
        'trace': traces, 'production_blocked': True, 'later_Auto_chats_remaining': 2}
    put(folder, 'serverproof-verified.json', proof)
    return proof


def transport(folder, label):
    prefix = label + '-' + secrets.token_hex(8)
    return Transport(lambda name, value: put(folder, prefix + '/' + name, value), sources)


_base_main = main
def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'check-score':
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('stage')
        parser.add_argument('--package', type=Path, required=True)
        parser.add_argument('--manifest-sha256', required=True)
        args = parser.parse_args(argv)
        require(args.package.is_absolute() and args.package.parent == HOME / 'packages'
                and args.package.name.startswith('successor11-'), 'new11_package_scope')
        return checkpoint_score(args.package, args.manifest_sha256, transport(args.package, 'check-score'))
    return _base_main(argv)


# Resolve inherited functions through the actual successor module namespace,
# including test patching. Never modify a function or global in predecessor10.
for _name, _value in _ns.items():
    if not _name.startswith('_'):
        globals().setdefault(_name, _value)
for _name, _value in list(globals().items()):
    if isinstance(_value, FunctionType) and _value.__globals__ is _ns:
        globals()[_name] = FunctionType(_value.__code__, globals(), _value.__name__,
                                      _value.__defaults__, _value.__closure__)
# contextmanager's wrapper executes contextlib globals, NOT deployment globals.
# Rewrap the actual original generator so lock acquisition/release is unchanged.
operation = ten.contextmanager(FunctionType(ten.operation.__wrapped__.__code__, globals(), 'operation'))

if __name__ == '__main__':
    try:
        print(json.dumps(main(), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'STOP_RECONCILE_NO_REPLAY', 'error_type': type(error).__name__,
                          'reason': str(error) if isinstance(error, ValueError) else 'inspect_original_receipts'}))
        raise SystemExit(2)