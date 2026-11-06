"""Offline successor11 only; explicit MOCK ports/authority, actual frozen XML."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.deployment import auto_resume11_parent as p
from tests.unit import test_auto_resume10 as prior


class Port(prior.Port):
    def __init__(self):
        super().__init__()
        self.state['sources'] = p.sources()
        self.root = {'etag': '"root130"', 'lease_state': 'available', 'lease_status': 'unlocked'}
        self.close_calls = 0
        self.close_effect = lambda: None

    def root_head(self):
        return deepcopy(self.root)

    def closing(self):
        self.close_calls += 1
        self.close_effect()
        return {'root': deepcopy(self.root), 'etags': deepcopy(self.state['etags']), 'values': {
            'api': deepcopy(self.state['owned']),
            'global': {'properties': {'value': self.state['policies']['global'].decode()}},
            'policy': {'properties': {'value': self.state['policies']['owned'].decode()}}}}


class StageTests(prior.StageTests):
    # Inherit ALL10 stage/cleanup tests except tests of deliberately superseded
    # handoff/serverproof semantics. Rebind that test module privately below.
    @classmethod
    def setUpClass(cls):
        cls.fixed = p.localcheck()

    def setUp(self):
        super().setUp()

    def activated(self):
        super().activated()
        p.checkpoint_score(self.folder, self.digest, self.port, lambda: self.clock)

    def accepted(self, phase, reference):
        if not (self.folder / 'check-score-verified.json').exists(): self.activated()
        request = p.emit(self.folder, self.digest, phase, lambda: self.clock)
        path = self.root / (phase + '-original.json')
        path.write_bytes(p.canonical({'binding': request,
            'dom': {'model': 'gpt-5.4-mini', 'system_empty': True, 'turns': 0,
                    'draft_matches': True, 'send_disabled': True}, 'auth_inspected': False}))
        return p.accept(self.folder, self.digest, phase, path, p.sha(path.read_bytes()), reference, lambda: self.clock)

    def test_prescore_full_guard_and_budget_intent_before_native_effect(self):
        self.activated()
        self.accepted('observe', 'MOCK_A'); self.accepted('inspect', 'MOCK_B')
        count = len(self.port.captures)
        request = p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.assertEqual(len(self.port.captures), count)
        self.assertEqual(request['phase'], 'score')
        self.assertTrue((self.folder / 'reserve-intent.json').exists())
        with self.assertRaises(FileExistsError):
            p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)

    def test_actual_split_stages_full_pre_post_and_final_protection(self):
        self.activated()
        self.assertEqual(len(self.port.captures), 8)  # initial+six+checkpoint
        result = p.cleanup(self.folder, self.digest, self.port)
        self.assertTrue(result['cleanup_verified'] and result['final_full_guard'])
        self.assertEqual(self.port.calls, ['install-global', 'install-revision', 'online', 'offline', 'restore-global'])

    def ready(self):
        self.activated()
        self.accepted('observe', 'MOCK_A'); self.accepted('inspect', 'MOCK_B')

    def assert_no_score(self):
        self.assertFalse((self.folder / 'score-request.json').exists())

    def test_closing_ETag_drift_blocks_score(self):
        self.ready(); self.port.state['etags']['policy'] = '"FOREIGN"'
        with self.assertRaisesRegex(ValueError, 'ETag_changed'):
            p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.assert_no_score()

    def test_root_lease_and_root_ETag_drift(self):
        self.ready(); self.port.root['lease_state'] = 'leased'
        with self.assertRaisesRegex(ValueError, 'lease_changed'):
            p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.port.root.update(lease_state='available', etag='"changed"')
        with self.assertRaisesRegex(ValueError, 'root_ETag'):
            p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.assert_no_score()

    def test_full_baseline_max90_includes_capture_duration(self):
        self.ready(); self.clock += timedelta(seconds=91)
        with self.assertRaisesRegex(ValueError, 'max90'):
            p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.assert_no_score()

    def test_slow_closing_does_not_relax_DOM30(self):
        self.ready()
        def slow():
            self.clock += timedelta(seconds=30)
            p.load(self.folder / 'worker-heartbeat.json')
        self.port.close_effect = slow
        with self.assertRaisesRegex(ValueError, 'fresh_independent_parent_inspection'):
            p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.assert_no_score()

    def test_nonce_source_and_checkpoint_tamper(self):
        self.ready()
        path = self.folder / 'check-score-verified.json'
        checkpoint = p.load(path); checkpoint['nonce'] = '0' * 32
        path.write_bytes(p.canonical(checkpoint))
        with self.assertRaisesRegex(ValueError, 'nonce_binding'):
            p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.assert_no_score()

    def test_exact_source_drift_blocks_before_closing(self):
        self.ready()
        with patch.object(p, 'sources', return_value={'FOREIGN': 'changed'}):
            with self.assertRaises(ValueError):
                p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        self.assert_no_score()

    def test_worker_stale_after_expensive_capture_stops(self):
        self.arm()
        self.clock += timedelta(seconds=5)
        with self.assertRaisesRegex(ValueError, 'worker_not_running'): self.advance('install-global')
        self.assertEqual(self.port.calls, [])

    def test_server_proof_requires_actual_correlated_trace_not_browser_counter(self):
        self.ready()
        checked_before = p.checked(self.folder, self.digest)
        request = p.reserve_score(self.folder, self.digest, self.port, lambda: self.clock)
        result = {'binding': request, 'server_correlation': 'MOCK_SERVER', 'http_status': 200,
            'observed_posts': 1, 'forwarded': True, 'guard_retained_closed': True,
            'diagnostic_schema_valid': True, 'auth_inspected': False, 'raw_body_logged': False,
            'request_started_at': self.clock.isoformat(), 'response_received_at': self.clock.isoformat()}
        p.put(self.folder, 'score-accepted.json', {'value': result, 'accepted_at': self.clock.isoformat()})
        compiler = p.ROOT / '.deployment/auto-resume06/highfix10/native/build-provenance.json'
        (self.folder / 'source-review-binding.json').write_bytes(p.canonical({'compiler': {
            'path': str(compiler), 'sha256': p.sha(compiler.read_bytes()), 'reference': 'MOCK_COMPILER'}}))
        # checked() must still enforce exact artifacts. Update ONLY explicit MOCK
        # checked dependency for testing proof after a fully exercised package.
        with patch.object(p, 'checked', return_value=checked_before):
            proof = p.serverproof(self.folder, self.digest)
        self.assertTrue(proof['structural_one_score_zero_completion'])
        self.assertEqual(proof['trace']['status'], 'UNVERIFIED_QUERY_NOT_AVAILABLE')
        self.assertTrue(proof['production_blocked'])
        self.assertNotIn('server_nonce', proof)

    def test_no_global_budget_reset_or_second_arm(self):
        self.arm()
        with self.assertRaises(ValueError): self.arm()
        self.assertEqual(p.arm.__defaults__[1], p.ten.six.LEDGER)


# Private copies of predecessor test methods (not mutation of predecessor tests).
# Their globals point at11 and the explicit MOCK Port, preserving regression
# coverage while original10 source/test bound bytes remain unchanged.
from types import FunctionType
_test_globals = {**vars(prior), 'p': p, 'Port': Port}
for _name, _fn in vars(prior.StageTests).items():
    if isinstance(_fn, FunctionType) and _name not in vars(StageTests):
        setattr(StageTests, _name, FunctionType(_fn.__code__, _test_globals, _name,
                                              _fn.__defaults__, _fn.__closure__))
_prior_setup = FunctionType(prior.StageTests.setUp.__code__, _test_globals, 'setUp')
def _setup(self):
    _prior_setup(self)
    self.manifest_before_proof = p.checked(self.folder, self.digest)
StageTests.setUp = _setup


class BindingTests(unittest.TestCase):
    def test_actual10_frozen_binding_no_glob(self):
        self.assertEqual(p.frozen10(), p.load(p.ROOT / '.deployment/auto-resume10/validation02/REPORT.json')['sources'])
        self.assertEqual(p.source_binding()['sources'], p.sources())

    def test_worker_real_source_hash_latency_is_not_assumed(self):
        from time import monotonic
        started = monotonic(); p.sources()
        elapsed = monotonic() - started
        print(json.dumps({'actual_source_hash_seconds': elapsed, 'worker_heartbeat_max_seconds': 5,
                          'live_worker_ack_verified': False}))
        # Do NOT relax5 or claim a live worker ack based on this timing test.

    def test_independent_review_rejects_author(self):
        with self.assertRaises(ValueError):
            p.review_binding('source11', {}, {'kind': 'source11', 'binding': {},
                'reviewer': 'successor11-author', 'original': {}, 'compiler': {}})


if __name__ == '__main__': unittest.main()