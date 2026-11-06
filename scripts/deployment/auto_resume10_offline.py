"""New10 receipts only. Offline focused Python+Node; no live prepare/paid calls."""
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.deployment import auto_resume10_parent as p


def main():
    label = sys.argv[1]
    p.require(label.startswith('validation') and label.isalnum(), 'finite_new10_receipt')
    folder = p.HOME / label
    folder.mkdir(parents=True, exist_ok=False)
    before = p.localcheck()
    p.put(folder, 'before.json', before)
    def deny(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo'):
            raise RuntimeError('OFFLINE_NETWORK_DENIED')
        if event == 'subprocess.Popen':
            command = str(args[1]).replace('\\', '/').lower()
            p.require(str(args[0]).lower() == 'node' or (args[0] is None and command.startswith('node ')),
                      'OFFLINE_NON_NODE_CHILD_DENIED')
    sys.addaudithook(deny)
    suite = unittest.defaultTestLoader.discover(str(p.ROOT / 'tests/unit'), pattern='test_auto_resume10.py')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    p.put(folder, 'python-tests.txt', stream.getvalue().encode())
    node = subprocess.run(['node', '--test', str(p.ROOT / 'tests/auto_resume10_browser.test.mjs')],
                          capture_output=True, timeout=60)
    p.put(folder, 'node.stdout.txt', node.stdout)
    p.put(folder, 'node.stderr.txt', node.stderr)
    compiler_path = p.ROOT / '.deployment/auto-resume06/highfix10/native/build-provenance.json'
    native = p.compiler(compiler_path, p.sha(compiler_path.read_bytes()),
                        'retained06/highfix10/native/build-provenance.json')
    p.put(folder, 'native-compiler-reference.json', native)
    started = p.load(p.ROOT / '.deployment/auto-resume04/protected-intent.json')['at']
    finished = p.load(p.ROOT / '.deployment/auto-resume04/protected-result.json')['at']
    timing = {'provenance': 'RETAINED04_NOT_LIVE10', 'protected_reads': 39,
              'seconds': (p.at(finished) - p.at(started)).total_seconds(),
              'not_full06_capture_latency': True, 'reserve_minutes': 22,
              'performance_live_ready': False}
    p.put(folder, 'retained04-timing.json', timing)
    after = p.localcheck()
    p.put(folder, 'after.json', after)
    ok = result.wasSuccessful() and node.returncode == 0 and before == after
    report = {'status': 'OFFLINE_PASS' if ok else 'OFFLINE_FAIL',
        'python': {'count': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                   'skips': len(result.skipped)}, 'node_exit': node.returncode,
        'sources': after['sources'], 'before_after_equal': before == after,
        'frozen': after['frozen'], 'retained_count': len(after['retained']),
        'native_compiler': native, 'timing': timing, 'live_prepare_calls': 0,
        'cloud_reads': 0, 'cloud_mutations': 0, 'paid_calls': 0,
        'authority': 'TEST_EVIDENCE_ONLY_NOT_APPROVAL', 'performance_live_ready': False}
    p.put(folder, 'REPORT.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'sources'}, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())