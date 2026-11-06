"""Exclusive offline12 Python/Node validation. No prepare or policy compilation."""
import io
import json
import subprocess
import sys
import unittest

from scripts.deployment import auto_resume12_parent as p


def main():
    label = sys.argv[1]
    p.require(label.startswith('validation') and label.isalnum(), 'finite12_receipt')
    folder = p.HOME / label
    folder.mkdir(parents=True, exist_ok=False)
    def deny(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo'):
            raise RuntimeError('OFFLINE_NETWORK_DENIED')
        if event == 'subprocess.Popen':
            command = str(args[1]).replace('\\', '/').lower()
            p.require(str(args[0]).lower() == 'node' or (args[0] is None and command.startswith('node ')),
                      'OFFLINE_NON_NODE_CHILD_DENIED')
    sys.addaudithook(deny)
    before = p.localcheck()
    p.put(folder, 'before.json', before)
    suite = unittest.defaultTestLoader.discover(str(p.ROOT / 'tests/unit'), pattern='test_auto_resume12.py')
    suite.addTests(unittest.defaultTestLoader.discover(str(p.ROOT / 'tests/unit'), pattern='test_auto_resume11.py'))
    suite.addTests(unittest.defaultTestLoader.discover(str(p.ROOT / 'tests/unit'), pattern='test_auto_resume12_stages.py'))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    p.put(folder, 'python-tests.txt', stream.getvalue().encode())
    node = subprocess.run(['node', '--test', str(p.ROOT / 'tests/auto_resume11_browser.test.mjs')],
                          capture_output=True, timeout=60)
    p.put(folder, 'node.stdout.txt', node.stdout)
    p.put(folder, 'node.stderr.txt', node.stderr)
    node12 = subprocess.run(['node', '--test', str(p.ROOT / 'tests/auto_resume12_browser.test.mjs')],
                           capture_output=True, timeout=60)
    p.put(folder, 'node12.stdout.txt', node12.stdout)
    p.put(folder, 'node12.stderr.txt', node12.stderr)
    native_path = p.ROOT / '.deployment/auto-resume06/highfix10/native/build-provenance.json'
    native = p.compiler(native_path, p.sha(native_path.read_bytes()), 'retained/highfix10/native225')
    after = p.localcheck()
    p.put(folder, 'after.json', after)
    p.put(folder, 'source-binding.json', p.source_binding())
    report = {'status': 'OFFLINE_PASS' if result.wasSuccessful() and node.returncode == 0 and node12.returncode == 0 and before == after else 'OFFLINE_FAIL',
        'python': {'count': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors)},
        'node_exit': node.returncode, 'node12_exit': node12.returncode,
        'before_after_equal': before == after, 'sources': after['sources'],
        'native225_reused_not_recompiled': native, 'prepare_calls': 0, 'cloud_reads': 0,
        'cloud_mutations': 0, 'paid_calls': 0, 'actual_envelope_keys_retained': True,
        'independent_review_required': True, 'prepare_executed': False,
        'source_review_still_required': True,
        'authority': 'TEST_EVIDENCE_ONLY_NOT_APPROVAL'}
    p.put(folder, 'REPORT.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'sources'}, indent=2), flush=True)
    return 0 if report['status'] == 'OFFLINE_PASS' else 1


if __name__ == '__main__': raise SystemExit(main())