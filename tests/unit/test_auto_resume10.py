"""Offline mocks only. Never invoke live prepare, transport or original runner."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.deployment import auto_resume10_parent as p

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def baseline():
    folder, frozen = p.six.old.retained()
    policies = {k: (folder / n).read_bytes() for k, n in (
        ('global', 'global-actual.xml'), ('owned', 'revision-2-actual.xml'), ('active', 'active-actual.xml'))}
    snapshot = deepcopy(frozen['current_snapshot'])
    snapshot['baseline']['apim']['global'] = p.sha(policies['global'])
    return {'snapshot': snapshot, 'deployments': deepcopy(frozen['full22_deployments']),
        'root': p.load(p.ROOT / '.deployment/uv-apply01/remaining02/commands/state-after.stdout.txt'),
        'child': p.load(p.ROOT / 'infra/project-route/terraform.tfstate'),
        'roles': deepcopy(snapshot['baseline']['runtime']['roleAssignments']),
        'inheritance': {'MOCK_COMPLETE_INHERITANCE': []},
        'revisions': p.load(folder / 'revisions-full.json')['value'],
        'owned': p.load(folder / 'revision-2-detail.json'), 'policies': policies,
        'etags': {'global': '"g0"', 'policy': '"p0"', 'api': '"a0"'}, 'sources': p.sources()}


class Port:
    def __init__(self):
        self.state = baseline()
        self.calls, self.captures = [], []
        self.fail, self.applied, self.wrong = None, False, False

    def capture(self, cleanup=False):
        self.captures.append(cleanup)
        return deepcopy(self.state)

    def send(self, stage, body, etag, timeout, cleanup=False):
        assert self.ledger.exists() and (self.folder / (stage + '-intent.json')).exists()
        assert timeout == 45
        self.calls.append(stage)
        if self.fail == stage and not self.applied: raise TimeoutError('MOCK_NOT_SENT')
        value = json.loads(body)['properties']
        slot = 'api' if stage in ('online', 'offline') else 'global' if 'global' in stage else 'policy'
        assert etag == self.state['etags'][slot]
        if slot == 'api':
            self.state['owned']['properties']['isOnline'] = value['isOnline']
            for row in self.state['revisions']:
                if row['apiRevision'] == '2': row['isOnline'] = value['isOnline']
        else:
            key = 'global' if slot == 'global' else 'owned'
            self.state['policies'][key] = value['value'].encode()
            if slot == 'global':
                self.state['snapshot']['baseline']['apim']['global'] = p.sha(self.state['policies'][key])
        self.state['etags'][slot] = '"' + slot + str(len(self.calls)) + '"'
        if self.fail == stage: raise TimeoutError('MOCK_RESPONSE_UNKNOWN')
        return {'http_status': 201, 'etag': '"wrong"' if self.wrong and not cleanup else self.state['etags'][slot]}


class StageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Fixed verified bytes for mocks only; avoid rehashing compiler/retained
        # corpus on every synthetic capture. Runner still hashes real before/after.
        cls.fixed = p.localcheck()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clock = NOW
        # Explicit MOCK independent capability, not a production approval receipt.
        self.review = patch.object(p, 'review_binding', lambda *args: args[-1])
        self.review.start()
        self.addCleanup(self.review.stop)
        self.fixed_sources = patch.object(p, 'sources', lambda: self.fixed['sources'])
        self.fixed_check = patch.object(p, 'localcheck', lambda: deepcopy(self.fixed))
        self.fixed_sources.start(); self.fixed_check.start()
        self.addCleanup(self.fixed_sources.stop); self.addCleanup(self.fixed_check.stop)
        self.addCleanup(self.tmp.cleanup)
        self.port = Port()
        self.folder = self.root / 'package'
        self.port.folder, self.port.ledger = self.folder, self.root / 'MOCK_OWNER'
        self.owner = patch.object(p, 'GLOBAL_SCORE_OWNER', self.port.ledger)
        self.owner.start()
        self.addCleanup(self.owner.stop)
        p.prepare(self.folder, self.port, {'MOCK': 'source_review'}, lambda: self.clock)
        self.digest = p.sha((self.folder / 'manifest.json').read_bytes())

    def arm(self):
        p.arm(self.folder, self.digest, {'MOCK': 'package_review'}, launch=False,
              ledger=self.port.ledger, clock=lambda: self.clock)
        p.put(self.folder, 'worker-launch.json', {'pid': 123})
        p.put(self.folder, 'worker-heartbeat.json', {'pid': 123, 'at': self.clock.isoformat()})

    def advance(self, stage):
        return p.advance(self.folder, self.digest, stage, self.port, lambda: self.clock)

    def activated(self):
        self.arm()
        for stage in ('install-global', 'install-revision', 'online'): self.advance(stage)

    def test_prepare_freezes_after_complete_reads_no_budget_effect(self):
        self.assertEqual(self.port.captures, [False])
        self.assertFalse(self.port.ledger.exists())
        m = p.load(self.folder / 'manifest.json')
        self.assertEqual(p.at(m['end']) - p.at(m['start']), timedelta(minutes=30))
        self.assertEqual(m['start'], '2026-10-31T12:00:00Z')
        self.assertEqual(self.port.calls, [])

    def test_actual_split_stages_full_pre_post_and_final_protection(self):
        self.activated()
        self.assertEqual(len(self.port.captures), 7)  # initial + SIX full captures
        result = p.cleanup(self.folder, self.digest, self.port)
        self.assertTrue(result['cleanup_verified'] and result['final_full_guard'])
        self.assertEqual(self.port.calls, ['install-global', 'install-revision', 'online', 'offline', 'restore-global'])
        self.assertFalse(self.port.state['owned']['properties']['isOnline'])
        calls = self.port.calls[:]
        p.cleanup(self.folder, self.digest, self.port)
        self.assertEqual(self.port.calls, calls)

    def test_unknown_applied_write_reconciles_no_resend(self):
        self.arm(); self.port.fail = 'install-global'; self.port.applied = True
        with self.assertRaises(TimeoutError): self.advance('install-global')
        self.assertEqual(self.port.calls, ['install-global', 'restore-global'])
        self.assertTrue((self.folder / 'cleanup-request.json').exists())
        with self.assertRaises(ValueError): self.advance('install-global')
        self.assertEqual(self.port.calls.count('install-global'), 1)

    def test_wrong_response_ETag_cleanup_before_return(self):
        self.arm(); self.port.wrong = True
        with self.assertRaisesRegex(ValueError, 'ETag_exact'): self.advance('install-global')
        self.assertEqual(self.port.calls, ['install-global', 'restore-global'])

    def test_no_global_budget_reset_or_second_arm(self):
        self.arm()
        with self.assertRaises(ValueError): self.arm()
        self.assertEqual(p.arm.__defaults__[1], p.six.LEDGER)
        self.assertEqual(self.port.calls, [])

    def test_partial_original_owner_never_replaced(self):
        self.port.ledger.write_bytes(b'{')
        with self.assertRaises(FileExistsError): self.arm()
        self.assertFalse((self.folder / 'parent-window-intent.json').exists())
        self.assertEqual(self.port.ledger.read_bytes(), b'{')

    def test_exact_inclusive22_and_capture_elapsed_is_charged(self):
        self.clock += timedelta(minutes=8)
        self.arm()
        original_capture = self.port.capture
        def capture(cleanup=False):
            result = original_capture(cleanup)
            if not cleanup: self.clock += timedelta(microseconds=1)
            return result
        self.port.capture = capture
        with self.assertRaises(ValueError): self.advance('install-global')
        self.assertEqual(self.port.calls, [])

    def test_foreign_global_does_not_veto_owned_offline(self):
        self.activated()
        self.port.state['policies']['global'] = b'<policies/>'
        self.port.state['snapshot']['baseline']['apim']['global'] = p.sha(b'<policies/>')
        result = p.cleanup(self.folder, self.digest, self.port)
        self.assertEqual(self.port.calls[-1], 'offline')
        self.assertFalse(self.port.state['owned']['properties']['isOnline'])
        self.assertFalse(result['cleanup_verified'] or result['final_full_guard'])
        self.assertTrue((self.folder / 'restore-global-unresolved.json').exists())

    def test_foreign_owned_does_not_veto_global_restore(self):
        self.activated()
        self.port.state['owned']['properties']['apiRevisionDescription'] = 'FOREIGN'
        result = p.cleanup(self.folder, self.digest, self.port)
        self.assertEqual(self.port.calls[-1], 'restore-global')
        self.assertNotIn('offline', self.port.calls)
        self.assertFalse(result['cleanup_verified'])

    def test_cleanup_expiry_independent_other_stage_after_timeout(self):
        self.activated()
        self.clock += timedelta(days=1)
        self.port.fail = 'offline'
        p.cleanup(self.folder, self.digest, self.port)
        self.assertEqual(self.port.calls[-2:], ['offline', 'restore-global'])
        p.cleanup(self.folder, self.digest, self.port)
        self.assertEqual(self.port.calls.count('offline'), 1)

    def test_every_whole_protected_guard_not_narrowed(self):
        before = deepcopy(self.port.state)
        for name in ('snapshot', 'deployments', 'root', 'child', 'roles', 'inheritance',
                     'revisions', 'owned', 'policies', 'etags', 'sources'):
            with self.subTest(name=name):
                changed = deepcopy(before); changed[name] = {}
                with self.assertRaises((ValueError, KeyError)):
                    p.guard(before, changed, before['policies']['global'], before['policies']['owned'], False)

    def test_tamper_fails_before_mutation(self):
        self.arm(); (self.folder / 'payloads.json').write_bytes(b'{}')
        with self.assertRaises(ValueError): self.advance('install-global')
        self.assertEqual(self.port.calls, [])

    def accepted(self, phase, reference):
        request = p.emit(self.folder, self.digest, phase, lambda: self.clock)
        path = self.root / (phase + '-original.json')
        path.write_bytes(p.canonical({'binding': request,
            'dom': {'model': 'gpt-5.4-mini', 'system_empty': True, 'turns': 0,
                    'draft_matches': True, 'send_disabled': True}, 'auth_inspected': False}))
        return p.accept(self.folder, self.digest, phase, path, p.sha(path.read_bytes()), reference, lambda: self.clock)

    def test_conversation_original_bytes_no_opaque_handle_and_independent_read(self):
        self.accepted('observe', 'MOCK_CONVERSATION/tool-result-A')
        self.accepted('inspect', 'MOCK_CONVERSATION/tool-result-B')
        with self.assertRaises(FileExistsError): self.accepted('inspect', 'MOCK_C')

    def test_same_conversation_result_not_independent(self):
        self.accepted('observe', 'MOCK_SAME')
        with self.assertRaisesRegex(ValueError, 'independent_parent_read'):
            self.accepted('inspect', 'MOCK_SAME')

    def test_prescore_full_guard_and_budget_intent_before_native_effect(self):
        self.activated()
        self.accepted('observe', 'MOCK_A'); self.accepted('inspect', 'MOCK_B')
        count = len(self.port.captures)
        request = p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.assertEqual(len(self.port.captures), count + 1)
        self.assertEqual(request['phase'], 'score')
        self.assertTrue((self.folder / 'reserve-intent.json').exists())
        with self.assertRaises(FileExistsError):
            p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)

    def test_worker_stale_blocks_effect_not_new_remote_infrastructure_gate(self):
        self.arm(); self.clock += timedelta(seconds=5)
        with self.assertRaisesRegex(ValueError, 'worker_not_running'): self.advance('install-global')
        self.assertEqual(self.port.calls, [])

    def test_real_worker_function_runs_cleanup_independently_on_due_request(self):
        self.activated()
        p.request_cleanup(self.folder, 'MOCK_outer_tool_outstanding')
        with patch.object(p, 'transport', return_value=self.port):
            result = p.worker(self.folder, self.digest, clock=lambda: self.clock, wait=lambda _: None)
        self.assertTrue(result['cleanup_verified'])
        self.assertTrue((self.folder / 'worker-result.json').exists())

    def test_server_proof_requires_actual_correlated_trace_not_browser_counter(self):
        self.activated()
        p.put(self.folder, 'score-accepted.json', {'value': {'server_correlation': 'MOCK_SERVER'}})
        path = self.root / 'MOCK_TRACE.json'
        path.write_bytes(p.canonical({'correlation': 'MOCK_SERVER',
            'nonce': p.load(self.folder / 'manifest.json')['nonce'], 'manifest_sha256': self.digest,
            'complete_trace': True, 'score_requests': [{'operation': 'auto-diagnostic-score', 'status': 200}],
            'completion_requests': []}))
        result = p.serverproof(self.folder, self.digest, path, p.sha(path.read_bytes()), 'MOCK_QUERY_RESULT')
        self.assertEqual(result['later_Auto_chats_remaining'], 2)


class BindingTests(unittest.TestCase):
    def test_frozen_sources_no_inherited_dynamic_glob(self):
        with patch.object(p.six, 'sources', side_effect=AssertionError('EXPANDING_GLOB_FORBIDDEN')):
            binding = p.source_binding()
        self.assertIn(p.NEW[0], binding['sources'])
        self.assertEqual(p.localcheck()['frozen']['original280'], 280)

    def test_recursive_actual_native_compiler_receipt(self):
        path = p.ROOT / '.deployment/auto-resume06/highfix10/native/build-provenance.json'
        result = p.compiler(path, p.sha(path.read_bytes()), 'retained/highfix10/native/compiler-result')
        self.assertEqual(result['sha256'], p.sha(path.read_bytes()))
        with self.assertRaisesRegex(ValueError, 'compiler_original_bytes'):
            p.compiler(path, '0' * 64, 'MOCK_BAD_PIN')

    def test_independent_summary_transcript_binding_not_self_APPROVED(self):
        path = p.ROOT / '.deployment/auto-resume06/highfix10/native/build-provenance.json'
        pin = {'path': str(path), 'sha256': p.sha(path.read_bytes()), 'reference': 'MOCK_ORIGINAL_TRANSCRIPT'}
        review = {'kind': 'source10', 'binding': {'sources': 'MOCK_EXACT'},
                  'reviewer': 'MOCK_INDEPENDENT_REVIEWER', 'original': pin, 'compiler': pin}
        self.assertEqual(p.review_binding('source10', review['binding'], review), review)
        with self.assertRaisesRegex(ValueError, 'exact_review_binding'):
            p.review_binding('source10', {}, review)
        review['reviewer'] = 'successor10-author'
        with self.assertRaises(ValueError): p.review_binding('source10', review['binding'], review)


if __name__ == '__main__':
    unittest.main()