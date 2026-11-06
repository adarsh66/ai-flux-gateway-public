"""Adversarial offline fixtures only; no fixture grants authority."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.deployment import auto_resume09_handoff as h

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.folder = self.home / 'mounted-MOCK'
        self.addCleanup(patch.stopall)
        patch.object(h, 'HOME', self.home).start()
        self.check = {'sources': {'mock': 'f' * 64}, 'retained': {'MOCK': 'e' * 64}}
        patch.object(h, 'localcheck', return_value=deepcopy(self.check)).start()

    def result(self, phase='mounted-observe', mutate=lambda _: None, handle='MOCK_NATIVE_1'):
        prefix = 'observe' if phase == 'mounted-observe' else 'inspect'
        request = h.load(self.folder / (prefix + '-request.json'))
        dom = {'model_names': sorted(h.MODEL_NAMES), 'selected_model': 'gpt-5.6-luna',
            'subscription': 'Caldova-AI', 'system_empty': True, 'draft_empty': True, 'turns': 0,
            'empty_conversation': True, 'send_enabled': True, 'customer': 'Caldova'}
        envelope = {'tool': 'run_playwright_code', 'tool_result_handle': handle, 'page_id': h.PAGE,
            'result': {'binding': request, 'observed_at': NOW.isoformat(), 'page_url': h.URL, 'dom': dom}}
        mutate(envelope)
        path = self.home / (prefix + '-MOCK-result.json')
        h.exclusive(path, envelope)
        return path, h.sha(path.read_bytes()), handle

    def accept(self, phase='mounted-observe', **kwargs):
        return h.accept_result(self.folder, phase, *self.result(phase, **kwargs), now=NOW)

    def test_external_await_across_fresh_loads_not_callable(self):
        h.begin(self.folder, NOW)
        first = self.accept()
        second = self.accept('mounted-inspect', handle='MOCK_NATIVE_2')
        self.assertNotEqual(first['request_id'], second['request_id'])
        self.assertEqual(second['dom'], first['dom'])
        self.assertIn('NO_LIVE_AUTHORITY', second['authority'])
        self.assertFalse((self.folder / 'reserve-intent.json').exists())

    def test_duplicate_accept_and_begin_exclusive(self):
        h.begin(self.folder, NOW)
        self.accept()
        with self.assertRaises(FileExistsError):
            h.accept_result(self.folder, 'mounted-observe', self.home / 'missing', 'x', 'x', NOW)
        with self.assertRaises(FileExistsError):
            h.begin(self.folder, NOW)

    def test_failed_pin_is_consumed_before_validation(self):
        h.begin(self.folder, NOW)
        path, _, handle = self.result()
        with self.assertRaisesRegex(ValueError, 'result_hash'):
            h.accept_result(self.folder, 'mounted-observe', path, '0' * 64, handle, NOW)
        with self.assertRaises(FileExistsError):
            h.accept_result(self.folder, 'mounted-observe', path, h.sha(path.read_bytes()), handle, NOW)

    def test_expiry_consumed(self):
        h.begin(self.folder, NOW)
        args = self.result()
        with self.assertRaisesRegex(ValueError, 'expired'):
            h.accept_result(self.folder, 'mounted-observe', *args, now=NOW + timedelta(minutes=5))
        self.assertTrue((self.folder / 'observe-accept-intent.json').exists())

    def test_foreign_page_phase_source_manifest_request_time(self):
        request = {'schema': 9, 'phase': 'mounted-observe', 'request_id': 'a' * 64,
            'page_id': h.PAGE, 'page_url': h.URL, 'manifest_sha256': 'b' * 64,
            'sources_sha256': 'c' * 64, 'issued_at': NOW.isoformat(),
            'expires_at': (NOW + timedelta(minutes=5)).isoformat()}
        h.begin(self.folder, NOW)
        args = self.result()
        envelope = h.load(args[0])
        for field in request:
            with self.subTest(field=field):
                changed = deepcopy(envelope)
                changed['result']['binding'][field] = 'FOREIGN'
                with self.assertRaisesRegex(ValueError, 'binding'):
                    h.validate_result(envelope['result']['binding'], changed, args[2])

    def test_secret_unknown_fields_and_self_counters_rejected(self):
        h.begin(self.folder, NOW)
        def mutate(value):
            value['result']['completion_request_count'] = 0
            value['result']['token'] = 'MOCK_FORBIDDEN'
        with self.assertRaisesRegex(ValueError, 'finite_probe_result'):
            self.accept(mutate=mutate)
        self.assertFalse((self.folder / 'observe-accepted.json').exists())

    def test_wrong_model_draft_history_and_boolean_turns(self):
        h.begin(self.folder, NOW)
        path, _, handle = self.result()
        envelope = h.load(path)
        for field, value in (('selected_model', 'gpt-5.4-mini'), ('draft_empty', False),
                ('system_empty', False), ('turns', True), ('turns', 1), ('customer', 'foreign'),
                ('subscription', 'foreign'), ('model_names', ['gpt-5.6-luna'] * 22)):
            with self.subTest(field=field):
                changed = deepcopy(envelope)
                changed['result']['dom'][field] = value
                with self.assertRaisesRegex(ValueError, 'DOM_mismatch'):
                    h.validate_result(envelope['result']['binding'], changed, handle)

    def test_source_drift_and_emitted_code_drift(self):
        h.begin(self.folder, NOW)
        args = self.result()
        (self.folder / 'observe-tool.js').write_bytes(b'return {fake:true}')
        with self.assertRaisesRegex(ValueError, 'tool_drift'):
            h.accept_result(self.folder, 'mounted-observe', *args, now=NOW)

    def test_retained_drift(self):
        h.begin(self.folder, NOW)
        args = self.result()
        self.check['retained'] = {}
        with patch.object(h, 'localcheck', return_value=self.check):
            with self.assertRaisesRegex(ValueError, 'retained_drift'):
                h.accept_result(self.folder, 'mounted-observe', *args, now=NOW)

    def test_same_tool_handle_cannot_corroborate_itself(self):
        h.begin(self.folder, NOW)
        self.accept()
        with self.assertRaisesRegex(ValueError, 'independent_inspection'):
            self.accept('mounted-inspect')

    def test_inspection_requires_prior_observe(self):
        h.begin(self.folder, NOW)
        with self.assertRaises(FileNotFoundError):
            self.accept('mounted-inspect')

    def test_closed_handoff_cannot_accept(self):
        h.begin(self.folder, NOW)
        args = self.result()
        receipt = h.cleanup(self.folder)
        self.assertIn('NOT_EXECUTED', receipt['remote_cleanup'])
        with self.assertRaisesRegex(ValueError, 'closed'):
            h.accept_result(self.folder, 'mounted-observe', *args, now=NOW)

    def test_every_live_stage_refuses_without_side_effects_even_forged_watchdog(self):
        h.begin(self.folder, NOW)
        h.exclusive(self.folder / 'watchdog.json', {'armed': True, 'decision': 'MOCK_NOT_APPROVAL'})
        before = sorted(p.name for p in self.folder.iterdir())
        for stage in h.LIVE:
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, 'off_laptop'):
                h.live_boundary(stage)
        self.assertEqual(before, sorted(p.name for p in self.folder.iterdir()))
        self.assertEqual(h.GLOBAL_SCORE_OWNER.name, 'auto-resume06-isolated-score-owner.json')

    def test_duplicate_JSON_and_nonfinite_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            path = self.home / 'duplicate.json'
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                h.load(path)

    def test_relative_path_and_naive_time_rejected(self):
        with self.assertRaisesRegex(ValueError, 'absolute'):
            h.safe(Path('relative'))
        with self.assertRaisesRegex(ValueError, 'UTC'):
            h.at('2026-10-31T12:00:00')

    def test_tool_has_no_secret_storage_or_action_calls(self):
        source = (h.ROOT / 'scripts/deployment/auto_resume09_probe.js').read_text()
        for forbidden in ('.fill(', '.press(', '.click(', '.route(', '.evaluate(', '.request.',
                'localStorage', 'sessionStorage', 'cookies(', 'fetch(', 'eval('):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()