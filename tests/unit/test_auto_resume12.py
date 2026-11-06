"""Offline candidate envelope fixtures, NOT recorded Azure responses."""
import ast
from copy import deepcopy
import inspect
import textwrap
import unittest
from unittest.mock import patch

from scripts.deployment import auto_resume12_transport as t
from scripts.deployment import auto_resume12_parent as p

URL = t.a.ARM.rstrip('/') + t.old.APIM + '/backends?api-version=2024-05-01'


class CollectionTests(unittest.TestCase):
    def run_pages(self, pages, url=URL):
        calls, receipts = [], []
        class Reader:
            def get(self, target):
                calls.append(target)
                return deepcopy(pages[target])
        result = t.collection(Reader(), url, lambda name, value: receipts.append((name, value)))
        return result, calls, receipts

    def test_total_count_not_page_length_and_whole_rows(self):
        second = URL + '&$skip=1'
        rows = [{'id': '/resource/1', 'properties': {'critical': 'whole'}}, {'id': '/resource/2'}]
        result, calls, receipts = self.run_pages({URL: {'value': rows[:1], 'count': 99, 'nextLink': second},
            second: {'value': rows[1:], 'count': 99}})
        self.assertEqual(result, {'value': rows})
        self.assertEqual(calls, [URL, second])
        self.assertEqual(receipts[0][1]['metadata_sha256'], p.sha(p.canonical({'count': 99, 'nextLink': second})))
        self.assertEqual(receipts[0][1]['whole_rows_sha256'], p.sha(p.canonical(rows[:1])))
        self.assertNotIn('properties', str(receipts))

    def test_metadata_adversarial(self):
        for extra in ({'count': True}, {'count': -1}, {'count': 1.5}, {'count': 1.0},
                  {'count': 2147483648}, {'count': '2'},
                      {'count': float('nan')}, {'count': float('inf')}, {'id': '/anything'},
                      {'type': 'anything'}, {'name': 'anything'}, {'error': {}}, {'partial': True},
                      {'@odata.nextLink': URL}, {'nextLink': 5}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.run_pages({URL: {'value': [], **extra}})

    def test_count_is_not_globally_allowed(self):
        target = URL.replace('/backends?', '/products?')
        with self.assertRaises(ValueError):
            self.run_pages({target: {'value': [], 'count': 0}}, target)

    def test_foreign_pagination_and_version(self):
        for link in (URL.replace('management.azure.com', 'foreign.invalid'),
                     URL.replace('/backends?', '/products?'), URL.replace('https:', 'http:'),
                     URL + '#fragment', URL.replace('2024-05-01', '2020-01-01'), URL):
            with self.subTest(link=link), self.assertRaises(ValueError):
                self.run_pages({URL: {'value': [], 'nextLink': link}})

    def test_duplicates_casefold(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.run_pages({URL: {'value': [{'id': '/R/one'}, {'id': '/r/ONE'}]}})

    def test_finite30_pages(self):
        links = [URL] + [URL + '&$skip=' + str(i) for i in range(1, 31)]
        with self.assertRaisesRegex(ValueError, 'complete_scoped_pages'):
            self.run_pages({link: {'value': [], 'nextLink': links[i + 1]} for i, link in enumerate(links[:-1])})

    def test_other_envelopes_remain_strict(self):
        for kind in ('roles', 'deployments', 'postgres', 'apim'):
            t.validate_envelope({'value': [], 'nextLink': None}, kind)
            with self.assertRaises(ValueError): t.validate_envelope({'value': [], 'count': 0}, kind)

    def test_cached_collections_write_once_and_keep_critical_properties(self):
        receipts = []
        class Reader:
            def get(self, url):
                return {'value': [{'id': '/r/1', 'properties': {'critical': 'not_ignored'}}], 'count': 1}
        reader = Reader()
        first = t.collection(reader, URL, lambda *args: receipts.append(args))
        second = t.collection(reader, URL, lambda *args: receipts.append(args))
        self.assertEqual(first, second)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(first['value'][0]['properties']['critical'], 'not_ignored')


class GuardTests(unittest.TestCase):
    def test_capture_AST_only_collection_changed(self):
        def normalized(function):
            tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
            tree.body[0].returns = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    node.returns = None
                    for arg in node.args.args: arg.annotation = None
                    if node.name == 'collection': node.body = [ast.Pass()]
                if isinstance(node, ast.AnnAssign):
                    # Strip only local variable annotations for comparison.
                    node.__class__ = ast.Assign
                    node.targets = [node.target]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(normalized(t.six.Transport.capture), normalized(t.Transport.capture))

    def test_transport_parent_source_binding(self):
        self.assertIs(p.Transport, t.Transport)
        self.assertIs(p.transport.__globals__['Transport'], t.Transport)
        self.assertEqual(p.sources()['scripts/deployment/auto_resume12_transport.py'], p.sha(
            (p.ROOT / 'scripts/deployment/auto_resume12_transport.py').read_bytes()))
        self.assertEqual(p.frozen11(), p.load(p.ROOT / '.deployment/auto-resume11/validation04/REPORT.json')['sources'])

    def test_executable_dispatch_and_actual_unmocked_hashes(self):
        import hashlib
        from pathlib import Path
        import tempfile
        self.assertEqual(p.envelope_evidence()['path'], '.deployment/auto-resume12/envelope02/result.json')
        self.assertIs(p.prepare.__globals__, vars(p))
        self.assertIs(p._base_main.__globals__, vars(p))
        self.assertIs(p._candidate_main.__globals__, vars(p))
        self.assertIs(p.checkpoint_score.__globals__, vars(p))
        self.assertIs(p._base_main.__globals__['prepare'], p.prepare)
        # Native helpers, no mock or global rebinding: reproduce the exact
        # production receipt functions on complete critical properties.
        rows = [{'id': '/r/1', 'properties': {'url': 'https://example.invalid',
            'credentials': {'header': {'x-key': ['fixture-only']}}, 'tls': {'validateCertificateChain': True}}}]
        metadata = {'count': 1}
        result, _, receipts = self.run_native_collection(rows, metadata)
        self.assertEqual(result, {'value': rows})
        self.assertEqual(receipts[0][1]['whole_rows_sha256'], hashlib.sha256(p.canonical(rows)).hexdigest())
        self.assertEqual(receipts[0][1]['metadata_sha256'], hashlib.sha256(p.canonical(metadata)).hexdigest())
        self.assertEqual(p.source_binding()['manifest_schema'], 12)
        # Dispatcher exercised with only in-memory capabilities; no live port.
        with tempfile.TemporaryDirectory() as root:
            folder = p.HOME / 'packages/successor12-OFFLINE-DISPATCH'
            with patch.object(p, 'transport', return_value='OFFLINE_PORT'), \
                 patch.object(p, 'prepare', return_value={'offline_dispatch': True}) as prepare, \
                 patch.object(p, 'load', return_value={'offline_review': True}):
                self.assertEqual(p.main(['prepare', '--package', str(folder), '--review',
                    str(Path(root) / 'review.json')]), {'offline_dispatch': True})
                prepare.assert_called_once_with(folder, 'OFFLINE_PORT', {'offline_review': True})

    def run_native_collection(self, rows, metadata):
        receipts = []
        class Reader:
            def get(self, target):
                return {'value': rows, **metadata}
        return t.collection(Reader(), URL, lambda *args: receipts.append(args)), [], receipts

    def test_unchanged_send_closing_and_ledger(self):
        self.assertIs(t.Transport.send, t.six.Transport.send)
        self.assertIs(t.Transport.closing, p.eleven.Transport.closing)
        self.assertEqual(p.arm.__defaults__, p.eleven.arm.__defaults__)
        self.assertEqual(p.operation.__wrapped__.__code__, p.eleven.ten.operation.__wrapped__.__code__)


if __name__ == '__main__': unittest.main()