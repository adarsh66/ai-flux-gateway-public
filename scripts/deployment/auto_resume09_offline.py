"""Exclusive09 focused test evidence; no installs, credentials, Azure or prepare."""
from __future__ import annotations
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.deployment import auto_resume09_handoff as h


def main():
    # Fixed receipt directory, never overwrite/rerun this original validation.
    folder = h.HOME / 'validation01'
    h.safe(folder)
    folder.mkdir(parents=True, exist_ok=False)
    before = h.localcheck()
    h.exclusive(folder / 'before.json', before)
    def deny(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo'):
            raise RuntimeError('OFFLINE_NETWORK_DENIED')
        if event == 'subprocess.Popen':
            command = str(args[1]).replace('\\', '/').lower()
            executable = str(args[0]).lower()
            h.require(executable == 'node' or (args[0] is None and command.startswith('node ')),
                'OFFLINE_NON_NODE_CHILD_DENIED')
    sys.addaudithook(deny)
    suite = unittest.defaultTestLoader.discover(str(h.ROOT / 'tests/unit'), pattern='test_auto_resume09.py')
    stream = io.StringIO()
    tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    h.exclusive(folder / 'python-tests.txt', stream.getvalue().encode())
    node = subprocess.run(['node', '--test', str(h.ROOT / 'tests/auto_resume09_probe.test.mjs')],
        capture_output=True, timeout=60)
    h.exclusive(folder / 'node.stdout.txt', node.stdout)
    h.exclusive(folder / 'node.stderr.txt', node.stderr)
    after = h.localcheck()
    h.exclusive(folder / 'after.json', after)
    ok = tests.wasSuccessful() and node.returncode == 0 and before == after
    report = {'schema': 9, 'status': 'OFFLINE_PASS' if ok else 'OFFLINE_FAIL',
        'python': {'count': tests.testsRun, 'failures': len(tests.failures), 'errors': len(tests.errors),
            'skips': len(tests.skipped)}, 'node_exit': node.returncode,
        'frozen_checks': after['verified'], 'all_before_after_equal': before == after,
        'sources': after['sources'], 'retained_files': len(after['retained']),
        'authority': 'TEST_EVIDENCE_ONLY_NOT_APPROVAL', 'live_boundaries': list(h.BLOCKERS)}
    h.exclusive(folder / 'REPORT.json', report)
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())