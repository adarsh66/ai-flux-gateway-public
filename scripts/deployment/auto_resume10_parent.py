"""Split finite parent CLI. Import/localcheck are offline; live stages are explicit.

Actual outer conversation owns native tool calls, original-result comparison,
independent review selection and try/finally. Hashes are integrity, not authority.
No opaque browser handle, remote supervisor, production release or paid retry.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from threading import Event
import time
from types import FunctionType

from scripts.deployment import auto_resume06_parent as six
from scripts.deployment import auto_resume09_handoff as nine
from scripts.deployment.auto_resume06_transport import Transport, canonical

ROOT = six.ROOT
HOME = ROOT / '.deployment/auto-resume10'
GLOBAL_SCORE_OWNER = six.LEDGER  # exact original path, across ALL packages
NEW = ('scripts/deployment/auto_resume10_parent.py', 'scripts/deployment/auto_resume10_browser.js',
       'scripts/deployment/auto_resume10_offline.py', 'tests/unit/test_auto_resume10.py',
       'tests/auto_resume10_browser.test.mjs', 'docs/auto-resume10-handoff.md')
TEXT = 'Please greet me in one short sentence.'
require, sha, load, at = nine.require, nine.sha, nine.load, nine.at


def now():
    return datetime.now(UTC)


def put(folder, name, value):
    return six.exclusive(folder / name, value)


def sources():
    """Own explicit corpus + immutable06 map; NEVER call06's expanding glob."""
    frozen = load(ROOT / '.deployment/auto-resume06/highfix10/full-source-hashes-after.json')
    for name, digest in frozen.items():
        nine.safe(ROOT / name)
        require(sha((ROOT / name).read_bytes()) == digest, 'frozen06_drift:' + name)
    result = dict(frozen)
    for name in (*nine.NEW, *NEW):
        nine.safe(ROOT / name)
        result[name] = sha((ROOT / name).read_bytes())
    return dict(sorted(result.items()))


def localcheck():
    prior = nine.localcheck()
    # Freeze09 actual validated source map, not a new dynamically refreshed map.
    report = load(ROOT / '.deployment/auto-resume09/validation01/REPORT.json')
    require(report['status'] == 'OFFLINE_PASS', 'retained09_validation')
    require(prior['sources'] == report['sources'], 'frozen09_drift')
    retained = dict(prior['retained'])
    for path in sorted((ROOT / '.deployment/auto-resume09').rglob('*')):
        nine.safe(path)
        if path.is_file(): retained[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    return {'sources': sources(), 'frozen': prior['verified'], 'retained': retained,
            'authority': 'INTEGRITY_ONLY_NOT_APPROVAL'}


def bound(function):
    # Original guard's entire whole-state algorithm, private globals only.
    return FunctionType(function.__code__, {**function.__globals__, 'sources': sources},
                        function.__name__, function.__defaults__, function.__closure__)


def guard(before, actual, global_xml, revision_xml, online):
    return bound(six.guard_state)(before, actual, global_xml, revision_xml, online)


def initial(value):
    namespace = {**six.initial.__globals__, 'sources': sources, 'guard_state': guard}
    return FunctionType(six.initial.__code__, namespace)(value)


def compiler(path, digest, reference):
    require(bool(reference), 'actual_compiler_receipt_reference')
    nine.safe(path)
    require(sha(path.read_bytes()) == digest, 'compiler_original_bytes')
    value = load(path)
    require(value['compile_exit'] == value['semantic_exit'] == 0 and value['expressions'] == 225,
            'native225_compile_semantic_receipt')
    for group in ('inputs', 'outputs'):
        require(value[group], 'recursive_compiler_files')
        for name, pin in value[group].items():
            file = Path(name)
            nine.safe(file)
            require(sha(file.read_bytes()) == pin, 'recursive_compiler_drift')
    native = str(ROOT / 'scripts/deployment/auto_resume06_native.cs')
    require(value['inputs'].get(native) == sources()['scripts/deployment/auto_resume06_native.cs']
            and any(n.endswith('csc.dll') for n in value['inputs'])
            and any(n.endswith('Resume06Native.dll') for n in value['outputs']), 'actual_native_source_binding')
    return {'reference': reference, 'sha256': digest}


def original(path, digest, reference):
    """Parent supplies exact ORIGINAL result bytes + conversation reference.

    This validates integrity only. Parent MUST compare bytes with its original
    tool output, not believe a caller-authored disk file/reference string.
    """
    require(isinstance(reference, str) and reference.strip(), 'parent_conversation_result_reference')
    nine.safe(path)
    require(sha(path.read_bytes()) == digest, 'original_result_bytes_changed')
    return {'reference': reference, 'sha256': digest}


def review_binding(kind, expected, review):
    require(set(review) == {'kind', 'binding', 'reviewer', 'original', 'compiler'}, 'review_binding_fields')
    require(review['kind'] == kind and review['binding'] == expected
            and review['reviewer'] not in ('', 'successor10-author'), 'independent_exact_review_binding')
    for name in ('original', 'compiler'):
        pin = review[name]
        original(Path(pin['path']), pin['sha256'], pin['reference'])
    compiler_pin = review['compiler']
    compiler(Path(compiler_pin['path']), compiler_pin['sha256'], compiler_pin['reference'])
    # Original may be reviewer SUMMARY linked to transcript, not crypto/JSON APPROVED.
    return review


def source_binding():
    return {'sources': localcheck()['sources'], 'scope': 'ONE_SCORE_ZERO_COMPLETION_NO_RETRY',
            'stages': list(six.old.STAGES), 'native_source': 'scripts/deployment/auto_resume06_native.cs'}


def prepare(folder, port, review, clock=now):
    require(not folder.exists(), 'new_package_NO_REFRESH')
    review_binding('source10', source_binding(), review)
    folder.mkdir(parents=True, exist_ok=False)
    put(folder, 'prepare-intent.json', {'mutations': 0, 'paid_calls': 0})
    before = port.capture()
    initial(before)
    # Freeze only AFTER all fresh reads. No redundant pre-freeze freshening.
    start = clock().replace(microsecond=0)
    end = start + timedelta(minutes=30)
    begin, finish = (v.strftime('%Y-%m-%dT%H:%M:%SZ') for v in (start, end))
    nonce = secrets.token_hex(16)
    policy = before['policies']
    payloads = six.render.render(policy['global'], policy['owned'], policy['active'],
        {k: sha(policy[v]) for k, v in (('global', 'global'), ('owned', 'owned'), ('explicit', 'active'))},
        begin, finish, nonce, six.auto_inputs())
    artifacts = {'before.json': put(folder, 'before.json', six.pack(before)),
                 'payloads.json': put(folder, 'payloads.json', six.pack(payloads)),
                 'browser.js': put(folder, 'browser.js', (ROOT / NEW[1]).read_bytes()),
                 'source-review-binding.json': put(folder, 'source-review-binding.json', review)}
    manifest = {'schema': 10, 'start': begin, 'end': finish, 'nonce': nonce,
                'sources': sources(), 'artifacts': artifacts, 'budget': [1, 0, 0],
                'stages': list(six.old.STAGES), 'IP': six.render.IP}
    put(folder, 'manifest.json', manifest)
    return manifest


def checked(folder, digest):
    nine.safe(folder)
    require(sha((folder / 'manifest.json').read_bytes()) == digest, 'exact_manifest')
    m = load(folder / 'manifest.json')
    require(m['schema'] == 10 and m['sources'] == sources() and m['budget'] == [1, 0, 0]
            and m['stages'] == list(six.old.STAGES) and m['IP'] == six.render.IP, 'manifest_contract')
    require(set(m['artifacts']) == {'before.json', 'payloads.json', 'browser.js', 'source-review-binding.json'},
            'finite_artifacts')
    for name, pin in m['artifacts'].items():
        nine.safe(folder / name)
        require(sha((folder / name).read_bytes()) == pin, 'artifact_drift:' + name)
    require((folder / 'browser.js').read_bytes() == (ROOT / NEW[1]).read_bytes(), 'standalone_browser_binding')
    review_binding('source10', source_binding(), load(folder / 'source-review-binding.json'))
    before, payloads = (six.unpack(load(folder / name)) for name in ('before.json', 'payloads.json'))
    initial(before)
    policy = before['policies']
    six.render.prove(payloads, policy['global'], policy['owned'], policy['active'],
        {k: sha(policy[v]) for k, v in (('global', 'global'), ('owned', 'owned'), ('explicit', 'active'))},
        m['start'], m['end'], m['nonce'], six.auto_inputs())
    return m, before, payloads


def package_binding(folder, digest):
    m, _, _ = checked(folder, digest)
    return {'manifest_sha256': digest, 'sources': m['sources'], 'artifacts': m['artifacts']}


def emit(folder, digest, phase, clock=now):
    m, _, _ = checked(folder, digest)
    issued = clock()
    request = {'schema': 10, 'phase': phase, 'scope': 'ONE_SCORE_ZERO_COMPLETION_NO_RETRY',
        'manifest_sha256': digest, 'nonce': m['nonce'], 'challenge': secrets.token_hex(32),
        'issued_at': issued.isoformat(), 'expires_at': (issued + timedelta(seconds=30)).isoformat()}
    if phase == 'score':
        reserve = load(folder / 'reserve-intent.json')
        request.update(activation_manifest_sha256=digest, window_end=m['end'],
                       reservation_sha256=sha((folder / 'reserve-intent.json').read_bytes()))
        require(reserve['manifest_sha256'] == digest, 'reservation_binding')
    put(folder, phase + '-request.json', request)
    source = (ROOT / NEW[1]).read_text(encoding='utf-8').strip()
    put(folder, phase + '-tool.js', ('return await (' + source + ')(page, '
                                   + canonical(request).decode() + ');\n').encode())
    return request


def accept(folder, digest, phase, result_path, result_pin, reference, clock=now):
    checked(folder, digest)
    put(folder, phase + '-accept-intent.json', {'attempts': 1})
    pin = original(result_path, result_pin, reference)
    value = load(result_path)  # sanitized exact Result bytes, not browser snapshot
    request = load(folder / (phase + '-request.json'))
    require(value['binding'] == request and at(request['issued_at']) <= clock() < at(request['expires_at']),
            'challenge_or_freshness')
    if phase in ('observe', 'inspect'):
        require(value['dom'] == {'model': 'gpt-5.4-mini', 'system_empty': True, 'turns': 0,
                                'draft_matches': True, 'send_disabled': True}
                and value['auth_inspected'] is False, 'independent_mini_benign_DOM')
        if phase == 'inspect':
            first = load(folder / 'observe-accepted.json')
            require(first['original']['reference'] != reference, 'independent_parent_read_required')
    elif phase == 'score':
        require(value['observed_posts'] == 1 and value['forwarded'] is True
                and value['guard_retained_closed'] is True and value['http_status'] == 200
                and value['diagnostic_schema_valid'] is True and value['auth_inspected'] is False
                and value['raw_body_logged'] is False, 'actual_diagnostic_result')
    else:
        raise ValueError('finite_result_phase')
    put(folder, phase + '-accepted.json', {'original': pin, 'value': value, 'accepted_at': clock().isoformat()})
    return value


@contextmanager
def operation(folder):
    """Serialize stage effects with worker; never steal uncertain/crashed lock."""
    lock = folder / 'operation.lock'
    lock.mkdir(exist_ok=False)
    try:
        yield
    finally:
        lock.rmdir()


def reserve(m, clock=now):
    begin, end = six.render.times(m['start'], m['end'])
    six.a.window(begin, end, clock())  # inclusive22 and <=30 unchanged
    require((end - clock()).total_seconds() >= 22 * 60, 'inclusive22_reserve')


def expected(folder, before, payloads):
    g, p, online = before['policies']['global'], before['policies']['owned'], False
    for stage in ('install-global', 'install-revision', 'online'):
        if (folder / (stage + '-intent.json')).exists():
            require((folder / (stage + '-verified.json')).exists(), 'uncertain_stage_RECONCILE_NO_REPLAY')
            if stage == 'install-global': g = payloads['global.xml']
            elif stage == 'install-revision': p = payloads['revision.xml']
            else: online = True
    return g, p, online


def wire(folder, port, stage, current, payloads, cleanup=False):
    slot = 'api' if stage in ('online', 'offline') else 'global' if 'global' in stage else 'policy'
    etag = six.old.strong_etag(current['etags'][slot])
    body = six.stage_body(stage, payloads)
    put(folder, stage + '-intent.json', {'if_match': etag, 'body_sha256': sha(body), 'retry_budget': 0})
    result = port.send(stage, body, etag, 45, cleanup)
    require(result['http_status'] in (200, 201), 'HTTP200_201')
    six.old.strong_etag(result['etag'])
    put(folder, stage + '-result.json', result)
    return slot, result['etag']


def authorized(folder, digest):
    review_binding('package10', package_binding(folder, digest), load(folder / 'package-review-binding.json'))
    owner = load(GLOBAL_SCORE_OWNER)
    require(owner['manifest_sha256'] == digest and owner['package'] == str(folder)
        and owner['score_attempts'] == 1 and owner['completion_attempts'] == 0
        and owner['retry_budget'] == 0, 'original_global_owner_binding')
    parent = load(folder / 'parent-window-intent.json')
    require(parent['manifest_sha256'] == digest and parent['outer_parent_finally_required'] is True,
        'actual_parent_window_intent')


def arm(folder, digest, review, launch=True, ledger=GLOBAL_SCORE_OWNER, clock=now):
    m, _, _ = checked(folder, digest)
    reserve(m, clock)
    review_binding('package10', package_binding(folder, digest), review)
    require(not (folder / 'parent-window-intent.json').exists(), 'parent_NO_REPLAY')
    put(folder, 'package-review-binding.json', review)
    # Global intent BEFORE any effects; partial/old owner is consumed forever.
    six.exclusive(ledger, {'manifest_sha256': digest, 'score_attempts': 1, 'completion_attempts': 0,
                           'retry_budget': 0, 'package': str(folder)})
    put(folder, 'parent-window-intent.json', {'manifest_sha256': digest, 'outer_parent_finally_required': True})
    if launch:
        child = subprocess.Popen([sys.executable, '-B', '-m', 'scripts.deployment.auto_resume10_parent',
            'worker', '--package', str(folder), '--manifest-sha256', digest],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        put(folder, 'worker-launch.json', {'pid': child.pid, 'executable': sys.executable})
    return {'armed': True, 'global_owner': str(ledger), 'not_guaranteed': 'laptop_loss_or_outage'}


def worker_fresh(folder, clock=now):
    launched, heartbeat = (load(folder / name) for name in ('worker-launch.json', 'worker-heartbeat.json'))
    require(heartbeat['pid'] == launched['pid'] and 0 <= (clock() - at(heartbeat['at'])).total_seconds() < 5,
            'separate_finite_cleanup_worker_not_running')


def advance(folder, digest, stage, port, clock=now):
    """One reusable ARM stage with FULL pre/post guards, parent-finally on error."""
    try:
        with operation(folder):
            m, before, payloads = checked(folder, digest)
            authorized(folder, digest)
            worker_fresh(folder, clock)
            require(not (folder / 'cleanup-request.json').exists(), 'cleanup_started')
            require(stage in ('install-global', 'install-revision', 'online'), 'finite_ARM_stage')
            sequence = ['install-global', 'install-revision', 'online']
            for prior in sequence[:sequence.index(stage)]:
                require((folder / (prior + '-verified.json')).exists(), 'stage_order')
            reserve(m, clock)
            g, p, online = expected(folder, before, payloads)
            current = guard(before, port.capture(), g, p, online)
            reserve(m, clock)  # capture duration is charged, no reserve reduction
            worker_fresh(folder, clock)
            slot, etag = wire(folder, port, stage, current, payloads)
            if stage == 'install-global': g = payloads['global.xml']
            elif stage == 'install-revision': p = payloads['revision.xml']
            else: online = True
            actual = guard(before, port.capture(), g, p, online)
            require(actual['etags'][slot] == etag, 'response_readback_ETag_exact')
            put(folder, stage + '-verified.json', {'full_protected': True, 'etag': etag})
            return {'stage': stage, 'verified': True}
    except Exception:
        # This CLI's finally duty is immediate on errors; outer parent also has
        # mandatory finally across native-tool boundaries. Worker remains armed.
        request_cleanup(folder, 'stage_failure')
        cleanup(folder, digest, port)
        raise


def reserve_score(folder, digest, port, clock=now):
    with operation(folder):
        m, before, payloads = checked(folder, digest)
        authorized(folder, digest)
        worker_fresh(folder, clock)
        require(not (folder / 'cleanup-request.json').exists(), 'cleanup_started')
        require((folder / 'online-verified.json').exists(), 'audited_activation_required')
        reserve(m, clock)
        guard(before, port.capture(), *expected(folder, before, payloads))
        reserve(m, clock)
        inspected = load(folder / 'inspect-accepted.json')
        issued = at(inspected['value']['binding']['issued_at'])
        require(0 <= (clock() - issued).total_seconds() < 30, 'fresh_independent_parent_inspection')
        put(folder, 'reserve-intent.json', {'manifest_sha256': digest, 'score': 1, 'completion': 0,
            'retry_budget': 0, 'cleanup_due': (clock() + timedelta(seconds=45)).isoformat()})
        return emit(folder, digest, 'score', clock)


def request_cleanup(folder, reason):
    try:
        put(folder, 'cleanup-request.json', {'reason': reason})
    except FileExistsError:
        pass  # request reconciliation, never repeat a wire operation


def reconcile_slot(folder, before, payloads, current, stage):
    """Foreign OTHER slot cannot veto cleanup. Foreign TARGET never overwritten."""
    require(current['sources'] == before['sources'] == sources(), 'cleanup_source_binding')
    projected = deepcopy(before)
    key = 'owned' if stage == 'offline' else 'global'
    install = 'install-revision' if stage == 'offline' else 'install-global'
    candidates = [before['policies'][key]]
    if (folder / (install + '-intent.json')).exists():
        candidates.append(payloads['revision.xml' if key == 'owned' else 'global.xml'])
    matches = [v for v in candidates if six.policy_equal(current['policies'][key], v,
                                                        v == before['policies'][key])]
    require(bool(matches), 'foreign_target_policy_NO_OVERWRITE')
    if stage == 'offline':
        online = current['owned']['properties']['isOnline']
        require(type(online) is bool and (not online or (folder / 'online-intent.json').exists()), 'unowned_online')
        for name in ('owned', 'revisions'): projected[name] = deepcopy(current[name])
        projected['policies']['owned'] = current['policies']['owned']
        for slot in ('api', 'policy'): projected['etags'][slot] = current['etags'][slot]
        guard(before, projected, before['policies']['global'], matches[0], online)
    else:
        projected['policies']['global'] = current['policies']['global']
        projected['snapshot']['baseline']['apim']['global'] = current['snapshot']['baseline']['apim']['global']
        projected['etags']['global'] = current['etags']['global']
        guard(before, projected, matches[0], before['policies']['owned'], False)
    return matches[0]


def cleanup(folder, digest, port):
    # No reserve/expiry/auth-age launch gates. Transport obtains fresh cleanup
    # credentials BEFORE its sole HTTP attempt; 401/timeout is never resent.
    with operation(folder):
        _, before, payloads = checked(folder, digest)
        errors = []
        for stage in ('offline', 'restore-global'):
            if (folder / (stage + '-cleanup-claim.json')).exists():
                continue  # consumed original slot; caller reconciles its receipt
            put(folder, stage + '-cleanup-claim.json', {'attempts': 1})
            try:
                current = port.capture(cleanup=True)
                matched = reconcile_slot(folder, before, payloads, current, stage)
                unchanged = not current['owned']['properties']['isOnline'] if stage == 'offline' else matched == before['policies']['global']
                if not unchanged:
                    slot, etag = wire(folder, port, stage, current, payloads, cleanup=True)
                    actual = port.capture(cleanup=True)
                    matched = reconcile_slot(folder, before, payloads, actual, stage)
                    require(actual['etags'][slot] == etag, 'cleanup_response_ETag_exact')
                    require(not actual['owned']['properties']['isOnline'] if stage == 'offline'
                            else matched == before['policies']['global'], 'cleanup_target_exact')
                put(folder, stage + '-verified.json', {'owned_target': True, 'already_safe': unchanged})
            except Exception as error:
                errors.append({'stage': stage, 'type': type(error).__name__})
                put(folder, stage + '-unresolved.json', errors[-1])
        # Final FULL protected capture: report unrelated drift, do not repair it.
        if not (folder / 'cleanup-final-intent.json').exists():
            put(folder, 'cleanup-final-intent.json', {'attempts': 1})
            try:
                final = port.capture(cleanup=True)
                revision = payloads['revision.xml'] if (folder / 'install-revision-verified.json').exists() else before['policies']['owned']
                guard(before, final, before['policies']['global'], revision, False)
                put(folder, 'final-protected.json', {'full_guard': True})
            except Exception as error:
                put(folder, 'final-protected-unresolved.json', {'type': type(error).__name__})
        return {'cleanup_verified': all((folder / (s + '-verified.json')).exists()
                for s in ('offline', 'restore-global')), 'unresolved': errors,
                'final_full_guard': (folder / 'final-protected.json').exists(), 'retries': 0}


def worker(folder, digest, clock=now, wait=None):
    """SEPARATE local finite process, remains running during outer native call.

    Not a guarantee against laptop loss, credential failure or Azure outage.
    Lock contention is observed boundedly; it never replays a claimed stage.
    """
    m, _, _ = checked(folder, digest)
    authorized(folder, digest)
    deadline = at(m['end'])
    wait = wait or Event().wait
    put(folder, 'worker-start.json', {'pid': os.getpid(), 'end': m['end']})
    count = 0
    while clock() < deadline + timedelta(minutes=4) and count < 2040:
        count += 1
        heartbeat = folder / 'worker-heartbeat.json'
        temporary = folder / 'worker-heartbeat-next.json'
        put(folder, temporary.name, {'pid': os.getpid(), 'at': clock().isoformat()})
        os.replace(temporary, heartbeat)  # only this worker-owned liveness slot
        due = deadline
        if (folder / 'reserve-intent.json').exists():
            due = min(due, at(load(folder / 'reserve-intent.json')['cleanup_due']))
        if (folder / 'cleanup-request.json').exists() or clock() >= due:
            if not (folder / 'operation.lock').exists():
                port = transport(folder, 'cleanup-worker')
                try:
                    result = cleanup(folder, digest, port)
                except FileExistsError:  # another original stage owns lock
                    wait(1)
                    continue
                put(folder, 'worker-result.json', result)
                return result
        wait(1)
    put(folder, 'worker-expired-unresolved.json', {'no_retry': True, 'reason': 'finite_worker_or_lock_deadline'})
    return {'cleanup_verified': False}


def serverproof(folder, digest, path, pin, reference):
    checked(folder, digest)
    put(folder, 'serverproof-intent.json', {'attempts': 1})
    original_pin = original(path, pin, reference)
    proof = load(path)  # independent server trace query, not browser counters
    result = load(folder / 'score-accepted.json')['value']
    m = load(folder / 'manifest.json')
    require(proof['correlation'] == result['server_correlation'] and proof['nonce'] == m['nonce']
            and proof['manifest_sha256'] == digest and proof['complete_trace'] is True
            and len(proof['score_requests']) == 1 and proof['completion_requests'] == []
            and proof['score_requests'][0]['operation'] == 'auto-diagnostic-score'
            and proof['score_requests'][0]['status'] == 200, 'independent_server_1score_0completion_trace')
    put(folder, 'serverproof-verified.json', {'original': original_pin, 'correlation': proof['correlation']})
    return {'server_proof': True, 'later_Auto_chats_remaining': 2}


def transport(folder, label):
    prefix = label + '-' + secrets.token_hex(8)
    return Transport(lambda name, value: put(folder, prefix + '/' + name, value), sources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('localcheck', 'source-binding', 'prepare', 'package-binding',
        'arm', 'worker', 'install-global', 'install-revision', 'online', 'observe', 'inspect',
        'accept', 'reserve-score', 'serverproof', 'cleanup', 'close'))
    parser.add_argument('--package', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--phase', choices=('observe', 'inspect', 'score'))
    parser.add_argument('--result', type=Path)
    parser.add_argument('--result-sha256')
    parser.add_argument('--conversation-reference')
    args = parser.parse_args(argv)
    if args.stage == 'localcheck': return localcheck()
    if args.stage == 'source-binding': return source_binding()
    folder = args.package
    require(folder is not None and folder.is_absolute() and folder.parent == HOME / 'packages'
            and folder.name.startswith('successor10-'), 'new10_package_scope')
    nine.safe(folder)
    if args.stage == 'prepare':
        require(args.review is not None, 'source_review_binding_required')
        return prepare(folder, transport(folder, 'prepare'), load(args.review))
    digest = args.manifest_sha256
    require(bool(digest), 'manifest_pin_required')
    if args.stage == 'package-binding': return package_binding(folder, digest)
    if args.stage == 'arm': return arm(folder, digest, load(args.review))
    if args.stage == 'worker': return worker(folder, digest)
    if args.stage in ('observe', 'inspect', 'close'): return emit(folder, digest, args.stage)
    if args.stage == 'accept':
        return accept(folder, digest, args.phase, args.result, args.result_sha256, args.conversation_reference)
    if args.stage == 'serverproof':
        return serverproof(folder, digest, args.result, args.result_sha256, args.conversation_reference)
    if args.stage == 'reserve-score': return reserve_score(folder, digest, transport(folder, 'pre-score'))
    if args.stage == 'cleanup':
        request_cleanup(folder, 'outer_parent_finally')
        return cleanup(folder, digest, transport(folder, 'parent-finally'))
    return advance(folder, digest, args.stage, transport(folder, args.stage))


if __name__ == '__main__':
    try:
        print(json.dumps(main(), sort_keys=True))
    except Exception as error:
        print(json.dumps({'status': 'STOP_RECONCILE_NO_REPLAY', 'error_type': type(error).__name__,
                          'reason': str(error) if isinstance(error, ValueError) else 'inspect_original_receipts'}))
        raise SystemExit(2)