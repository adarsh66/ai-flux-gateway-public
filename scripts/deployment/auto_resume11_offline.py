"""Exclusive offline11 receipts. No installs/esbuild/cloud/live prepare."""
import io
import json
import subprocess
import sys
import time
import unittest

from scripts.deployment import auto_resume11_parent as p


def contract():
    folder, _ = p.ten.six.old.retained()  # resolve actual05.retained paths
    raw = (folder / 'revision-2-actual.xml').read_bytes()
    tree = p.ten.six.render.tree(raw, True)
    _, gate = p.ten.six.render.parts(tree)
    summary = next(n for n in tree.iter('set-variable') if n.get('name') == 'auto-diagnostic-summary').get('value')
    for literal in ('"scoring_status"', '"schema_valid"', '"body_within_bound"',
                    '"key_types"', '"probabilities"', '"usage"', '2147483647',
                    'new [] { "input_tokens", "output_tokens", "total_tokens" }',
                    'new [] { "greeting", "arithmetic" }'):
        p.require(literal in summary, 'actual_XML_summary_contract')
    metadata = [{'name': n.get('name'), 'value': n.get('value')}
                for trace in tree.iter('trace') for n in trace.findall('metadata')]
    return {'provenance': 'RETAINED_XML_CONTRACT_DERIVED_NOT_SERVER_RESPONSE',
        'path': str(folder / 'revision-2-actual.xml'), 'sha256': p.sha(raw),
        'summary_expression': summary, 'trace_metadata': metadata,
        'single_terminal_score': gate[-1].tag == 'return-response',
        'native225_expression_present': summary in p.load(p.ROOT / '.deployment/auto-resume06/highfix10/native/expressions.json'),
        'contract_success_fixture': {'scoring_status': 200, 'schema_valid': True, 'body_within_bound': True,
            'key_types': {'answers': 'Object'}, 'probabilities': {'greeting': .8, 'arithmetic': .2},
            'usage': {'input_tokens': None, 'output_tokens': None, 'total_tokens': None}}}


def main():
    label = sys.argv[1]
    p.require(label.startswith('validation') and label.isalnum(), 'finite11_receipt')
    folder = p.HOME / label
    folder.mkdir(parents=True, exist_ok=False)
    before = p.localcheck(); p.put(folder, 'before.json', before)
    def deny(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo'): raise RuntimeError('OFFLINE_NETWORK_DENIED')
        if event == 'subprocess.Popen':
            command = str(args[1]).replace('\\', '/').lower()
            p.require(str(args[0]).lower() == 'node' or (args[0] is None and command.startswith('node ')),
                      'OFFLINE_NON_NODE_CHILD_DENIED')
    sys.addaudithook(deny)
    fixture = contract()
    path = p.HOME / 'diagnostic-contract.json'
    if path.exists(): p.require(p.load(path) == fixture, 'immutable_contract_fixture')
    else: p.put(p.HOME, path.name, fixture)
    p.put(folder, 'diagnostic-contract.json', fixture)
    suite = unittest.defaultTestLoader.discover(str(p.ROOT / 'tests/unit'), pattern='test_auto_resume11.py')
    stream = io.StringIO(); started = time.monotonic()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    p.put(folder, 'python-tests.txt', stream.getvalue().encode())
    node = subprocess.run(['node', '--test', str(p.ROOT / 'tests/auto_resume11_browser.test.mjs')],
                          capture_output=True, timeout=60)
    p.put(folder, 'node.stdout.txt', node.stdout); p.put(folder, 'node.stderr.txt', node.stderr)
    native_path = p.ROOT / '.deployment/auto-resume06/highfix10/native/build-provenance.json'
    native = p.compiler(native_path, p.sha(native_path.read_bytes()), 'retained/highfix10/native225')
    after = p.localcheck(); p.put(folder, 'after.json', after)
    p.put(folder, 'source-binding.json', p.source_binding())
    report = {'status': 'OFFLINE_PASS' if result.wasSuccessful() and node.returncode == 0 and before == after else 'OFFLINE_FAIL',
        'python': {'count': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped)},
        'node_exit': node.returncode, 'seconds': time.monotonic() - started,
        'sources': after['sources'], 'before_after_equal': before == after, 'frozen': after['frozen'],
        'immutable10_bound_count': len(p.frozen10()), 'native_compiler': native,
        'XML_contract': {'path': fixture['path'], 'sha256': fixture['sha256'],
            'native225_expression_present': fixture['native225_expression_present'], 'not_actual_server_response': True},
        'live_prepare_calls': 0, 'cloud_reads': 0, 'cloud_mutations': 0, 'paid_calls': 0,
        'authority': 'TEST_EVIDENCE_ONLY_NOT_APPROVAL', 'performance_live_ready': False,
        'trace_status': 'UNVERIFIED_NO_QUERY_EXECUTED', 'production_blocked': True}
    p.put(folder, 'REPORT.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'sources'}, indent=2))
    return 0 if report['status'] == 'OFFLINE_PASS' else 1


if __name__ == '__main__': raise SystemExit(main())