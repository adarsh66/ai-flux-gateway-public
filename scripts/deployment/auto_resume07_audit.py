"""Independent offline audit receipts; never calls live prepare or transport.

This reviewer fixed compilation infrastructure and cannot approve that fix.
No certificate, signing key, synthetic signature or approval is produced.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.deployment import auto_resume06_parent as p
from scripts.deployment import auto_resume06_offline as offline

HOME = p.ROOT / '.deployment/auto-resume07'


def main():
    folder = HOME / 'validation01'
    p.safe(folder)
    folder.mkdir(parents=True, exist_ok=False)
    before = p.sources()
    retained = p.old.load(p.ROOT / '.deployment/auto-resume06/stage03/full-source-hashes-before.json')
    protected = {k: v for k, v in retained.items() if k not in p.NEW}
    p.exclusive(folder / 'source-hashes-before.json', before)

    def deny(event, args):
        if event == 'socket.connect':
            address = args[1]
            if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1'):
                raise RuntimeError('OFFLINE_EXTERNAL_NETWORK_DENIED')
        if event == 'socket.getaddrinfo' and args[0] not in ('127.0.0.1', '::1', None):
            raise RuntimeError('OFFLINE_EXTERNAL_DNS_DENIED')
        if event == 'subprocess.Popen':
            command = str(args[1]).lower().replace('\\', '/')
            executable = str(args[0]).lower().replace('\\', '/')
            allowed = executable in ('node', 'c:/program files/dotnet/dotnet.exe')
            allowed |= args[0] is None and (command.startswith('node ')
                or command.startswith('"c:/program files/dotnet/dotnet.exe" '))
            p.a.require(allowed, 'OFFLINE_SUBPROCESS_DENIED')
    sys.addaudithook(deny)

    suite = unittest.defaultTestLoader.discover(str(p.ROOT / 'tests/unit'), pattern='test_auto_resume06.py')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    p.exclusive(folder / 'python-tests.txt', stream.getvalue().encode())
    browser = subprocess.run(['node', '--test', str(p.ROOT / 'tests/auto_resume06_browser.test.mjs')],
        capture_output=True, timeout=60)
    p.exclusive(folder / 'browser-tests.stdout.txt', browser.stdout)
    p.exclusive(folder / 'browser-tests.stderr.txt', browser.stderr)
    native = offline.native(folder / 'native')

    # Executable regression evidence for the cleanup isolation HIGH finding.
    # Everything below is an in-memory fake port, never the real transport.
    test_module = sys.modules['test_auto_resume06']
    case = test_module.CapabilitiesTests()
    with tempfile.TemporaryDirectory() as tmp:
        data = case.fixture(Path(tmp))
        def foreign_global(binding, timeout):
            state = data[0].state
            state['policies']['global'] = b'<policies><inbound><base /></inbound></policies>'
            state['snapshot']['baseline']['apim']['global'] = p.render.sha(state['policies']['global'])
            raise TimeoutError('MOCK foreign global after activation')
        error = None
        try:
            case.execute(data, foreign_global)
        except ValueError as exc:
            error = str(exc)
        probe = {'error': error, 'calls': data[0].calls,
            'owned_revision_left_online': data[0].state['owned']['properties']['isOnline'],
            'offline_attempted': 'offline' in data[0].calls,
            'foreign_global_not_overwritten': 'restore-global' not in data[0].calls}
        p.a.require(probe['owned_revision_left_online'] and not probe['offline_attempted'],
            'HIGH_cleanup_defect_reproduction_changed')
        p.exclusive(folder / 'HIGH-cleanup-reproduction.json', probe)

    after = p.sources()
    changed = [name for name, digest in protected.items() if after.get(name) != digest]
    p.exclusive(folder / 'source-hashes-after.json', after)
    p.exclusive(folder / 'nativeSourceReview-binding.json', p.source_binding())
    evidence = {path.relative_to(folder).as_posix(): p.render.sha(path.read_bytes())
        for path in folder.rglob('*') if path.is_file()}
    report = {'status': 'FAIL_UNSAFE_NOT_READY_FOR_FRESH_PREPARE', 'task_complete': False,
        'review_gate': 'REJECTED_NO_SIGNED_APPROVAL',
        'independence': 'independent review of prior implementation; compiler fix now requires another reviewer',
        'source_count': len(after), 'source_hashes': after,
        'protected_count': len(protected), 'protected_changed': changed,
        'original280_count': len(p.old.retained()[1]['current280_sources']),
        'prior_stage03': {'python_count': 18, 'browser_count': 4, 'compile_exit': 1,
            'semantic_exit': None, 'actual_error': 'CS2012 missing native output directory'},
        'tests': {'python_count': result.testsRun, 'failures': len(result.failures),
            'errors': len(result.errors), 'skipped': len(result.skipped), 'browser_exit': browser.returncode},
        'native': native, 'cleanup_reproduction': probe,
        'findings': [
            {'id': 'H1', 'severity': 'HIGH', 'status': 'OPEN_REPRODUCED',
             'issue': 'Whole-state reconciliation couples independent cleanup slots; foreign global prevents offlining an exactly owned online diagnostic revision.'},
            {'id': 'H2', 'severity': 'HIGH', 'status': 'OPEN_SOURCE_VERIFIED',
             'issue': 'CLI accepts arbitrary verifier DLL; review.verify trusts exit0/VERIFIED without pinning compiled verifier bytes. A substitute helper bypasses RSA verification.'},
            {'id': 'H3', 'severity': 'HIGH', 'status': 'OPEN_SOURCE_VERIFIED',
             'issue': 'Loopback native_handoff accepts first unauthenticated connection and caller-supplied JSON metrics; no challenge, peer binding, or durable parent result authentication.'}],
        'evidence_sha256': evidence, 'live_prepare_calls': 0, 'cloud_reads': 0,
        'cloud_mutations': 0, 'paid_calls': 0, 'signed_review_created': False,
        'budget_remaining': {'isolated_score': 1, 'completion': 0, 'later_Auto_chats': 2, 'retries': 0},
        'window': {'minutes_max': 30, 'inclusive_launch_reserve_minutes': 22},
        'compiler_validation_pass': result.wasSuccessful() and browser.returncode == 0
            and native['compile_exit'] == 0 and native['semantic_exit'] == 0 and not changed,
        'next': 'Resolve H1-H3, independently audit exact new source hashes and verifier provenance, then obtain genuine out-of-band pinned reviewer signature. No prepare authorized.'}
    p.exclusive(HOME / 'REPORT.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('source_hashes', 'evidence_sha256')}, indent=2))
    return 2  # Safety review fails even if the compilation/tests pass.


if __name__ == '__main__':
    raise SystemExit(main())