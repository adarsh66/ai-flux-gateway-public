"""New current-fixture boundaries; no historical goldens or cloud execution."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from scripts.deployment import auto_resume05_render as r
from scripts.deployment import auto_resume05_parent as p

START = '2026-10-31T12:00:00Z'
END = '2026-10-31T12:30:00Z'
NONCE = 'b' * 32


def inputs():
    folder, frozen = p.retained()
    global_xml, owned_xml, explicit = [(folder / name).read_bytes() for name in
        ('global-actual.xml', 'revision-2-actual.xml', 'active-actual.xml')]
    binding = {'global': r.sha(global_xml), 'owned': r.sha(owned_xml), 'explicit': r.sha(explicit)}
    auto = {'defaults': frozen['original_Auto_defaults'], 'fragments': {
        name: (p.ROOT / name).read_text(encoding='utf-8') for name in frozen['original_Auto_fragments_sha256']}}
    return global_xml, owned_xml, explicit, binding, START, END, NONCE, auto


def capture():
    folder, frozen = p.retained()
    snapshot = deepcopy(frozen['current_snapshot'])
    policies = {key: (folder / name).read_bytes() for key, name in (
        ('global', 'global-actual.xml'), ('owned', 'revision-2-actual.xml'), ('active', 'active-actual.xml'))}
    snapshot['baseline']['apim']['global'] = r.sha(policies['global'])
    root = {'serial': 130, 'lineage': 'MOCK_ROOT_NOT_LIVE', 'check_results': [
        {'object_kind': 'check', 'config_addr': str(i), 'status': 'pass'} for i in range(49)]}
    return {'snapshot': snapshot, 'deployments': frozen['full22_deployments'], 'root': root,
        'child': {'serial': 191, 'local_only': True}, 'roles': snapshot['baseline']['runtime']['roleAssignments'],
        'inheritance': {'MOCK': 'unchanged'}, 'revisions': p.load(folder / 'revisions-full.json')['value'],
        'owned': p.load(folder / 'revision-2-detail.json'), 'policies': policies,
        'etags': {'global': '"global0"', 'policy': '"policy0"', 'api': '"api0"'}, 'sources': p.sources()}


class RendererTests(unittest.TestCase):
    def test_exact_four_delta_paths_and_22_explicit(self):
        args = inputs()
        result = r.render(*args)
        self.assertEqual(len(result['proof']['global_delta']), 1)
        self.assertEqual(len(result['proof']['revision_delta']), 3)
        self.assertEqual(result['explicit.xml'], args[2])
        self.assertEqual(result['restore-global.xml'], args[0])
        self.assertEqual(r.prove(result, *args), result['proof'])
        # Foundry inventory includes scoring-only Decision-1; explicit chat IDs
        # are the actual GET list, not guessed from deployment inventory names.
        explicit_tree = r.tree(args[2], True)
        listing = next(n.text for n in explicit_tree.iter('set-body') if (n.text or '').startswith('{"data":'))
        aliases = {row['id'] for row in json.loads(listing)['data']}
        self.assertEqual(len(aliases), 22)
        self.assertTrue(r.auto_references is not None)
        self.assertNotIn('Decision-1', aliases)

    def test_mutation_hidden_in_CSharp_rejected(self):
        args = inputs()
        candidate = r.render(*args)
        candidate['revision.xml'] = candidate['revision.xml'].replace(b'loggingOptOut', b'loggingOptIn')
        with self.assertRaisesRegex(ValueError, 'candidate_exact'):
            r.prove(candidate, *args)

    def test_new9_candidate_leak_encoded_rejected(self):
        for name in ('gpt-6%2Dluna', 'mistral-medium-3-5', 'claude-opus-5-5'):
            args = list(inputs())
            args[-1] = {'hidden': name}
            with self.assertRaisesRegex(ValueError, 'new9'):
                r.render(*args)

    def test_profiles_original_pool_and_Decision1_not_chat(self):
        frozen = p.retained()[1]
        self.assertEqual(frozen['original_Auto_candidates'],
            ['DeepSeek-V4-Flash', 'Kimi-K2.7-Code', 'gpt-5.4-mini', 'gpt-5.6-luna', 'gpt-6.1-sol', 'grok-4-1-fast-reasoning'])
        self.assertNotIn('microsoft-decision-1', frozen['original_Auto_candidates'])
        result = r.render(*inputs())
        # Full decoded equality except allowlisted paths proves every profile,
        # fixed body, safety and redaction character is inherited, not regenerated.
        _, gate = r.parts(r.tree(result['revision.xml']))
        self.assertEqual(len(gate.findall('.//send-request')), 1)
        self.assertEqual(gate[-1].tag, 'return-response')

    def test_current_binding_not_substitutable(self):
        args = list(inputs())
        args[3] = {**args[3], 'explicit': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'actual_current_XML_binding'):
            r.render(*args)

    def test_all_serialized_CSharp_text_exact(self):
        result = r.render(*inputs())
        original = r.flatten(r.tree(inputs()[1], True))
        actual = r.flatten(r.tree(result['revision.xml']))
        allowed = set(result['proof']['revision_delta'])
        self.assertGreater(len(original), 300)
        self.assertEqual({k: v for k, v in original.items() if k not in allowed},
                         {k: v for k, v in actual.items() if k not in allowed})

    def test_bad_windows_nonce_and_DTD(self):
        for index, value in ((5, '2026-10-31T12:30:01Z'), (5, START), (6, 'not-a-nonce')):
            args = list(inputs()); args[index] = value
            with self.assertRaises(ValueError):
                r.render(*args)
        with self.assertRaisesRegex(ValueError, 'DTD'):
            r.tree('<!DOCTYPE policies><policies/>')

    def test_expected_legitimate_diagnostic06_source_changes_preserved(self):
        fixture = p.load(p.ROOT / '.deployment/auto-resume05/current-fixture.json')
        changes = fixture['historical_diagnostic06']['expected_current_source_changes']
        self.assertTrue(changes)
        self.assertTrue(fixture['historical_diagnostic06']['goldens_untouched'])
        for name, hashes in changes.items():
            self.assertNotEqual(hashes['historical'], hashes['current'])
            self.assertEqual(r.sha((p.ROOT / name).read_bytes()), hashes['current'])


class ParentTests(unittest.TestCase):
    def test_cli_prepare_and_run_missing_capabilities_no_package(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'not-created'
            for stage in ('prepare', 'run-reviewed-window'):
                with self.assertRaisesRegex(ValueError, 'missing_actual_capabilities'):
                    p.main([stage, '--package', str(path)])
                self.assertFalse(path.exists())

    def test_strong_ETag_malformed_and_injection_rejected(self):
        for value in (None, '', '*', 'W/"weak"', '"*"', '"a\r\nb"', '"a"junk"'):
            with self.assertRaises(ValueError):
                p.strong_etag(value)
        self.assertEqual(p.strong_etag('"actual"'), '"actual"')

    def test_whole_guard_rejects_all_protected_mutations(self):
        before = capture()
        self.assertEqual(p.guard(before, deepcopy(before), before['policies']['global'], before['policies']['owned'], False), before)
        for key in ('roles', 'inheritance', 'child', 'deployments', 'sources'):
            changed = deepcopy(before); changed[key] = {}
            with self.assertRaises(ValueError):
                p.guard(before, changed, before['policies']['global'], before['policies']['owned'], False)
        changed = deepcopy(before); changed['revisions'][0]['isCurrent'] = True
        with self.assertRaises(ValueError):
            p.guard(before, changed, before['policies']['global'], before['policies']['owned'], False)

    def exercise(self, folder, browser_error=False, expiry=False, fail_stage=None, ambiguous=False):
        before = capture(); state = deepcopy(before)
        payloads = r.render(*inputs())
        now = [datetime(2026, 10, 31, 12, 0, tzinfo=UTC)]
        calls = []
        def send(stage, body, etag, timeout):
            self.assertTrue((folder / (stage + '-intent.json')).exists())
            calls.append((stage, etag))
            if stage == fail_stage:
                if ambiguous:
                    state['policies']['global'] = b'UNKNOWN_REMOTE_POLICY'
                raise OSError('MOCK uncertain transport')
            if stage in ('install-global', 'restore-global'):
                state['policies']['global'] = body
                state['snapshot']['baseline']['apim']['global'] = r.sha(body)
                state['etags']['global'] = '"global' + str(len(calls)) + '"'
            elif stage == 'install-revision':
                state['policies']['owned'] = body
                state['etags']['policy'] = '"policy' + str(len(calls)) + '"'
            else:
                online = stage == 'online'
                state['owned']['properties']['isOnline'] = online
                state['revisions'][0]['isOnline'] = online
                state['etags']['api'] = '"api' + str(len(calls)) + '"'
            return {'http_status': 200}
        def browser(binding, timeout):
            self.assertEqual(binding['stages'], list(p.STAGES))
            if expiry:
                now[0] += timedelta(days=1)
            if browser_error:
                raise RuntimeError('MOCK browser failure')
            return {'MOCK_ONLY': True, 'paid_calls': 0}
        cap = p.Capabilities(lambda: deepcopy(state), lambda stage, binding: binding, browser, send)
        return before, state, payloads, now, calls, cap

    def test_six_stage_success_exact_restore_ETag_ownership_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            before, state, payloads, now, calls, cap = self.exercise(folder)
            result = p.run_reviewed_window(folder, before, payloads, START, END, cap, lambda: now[0], lambda: 10)
            self.assertTrue(result['MOCK_ONLY'])
            self.assertEqual([x[0] for x in calls], ['install-global', 'install-revision', 'online', 'offline', 'restore-global'])
            self.assertEqual(state['policies']['global'], before['policies']['global'])
            self.assertFalse(state['revisions'][0]['isOnline'])
            self.assertFalse(state['revisions'][0]['isCurrent'])
            self.assertEqual(calls[-1][1], '"global1"')
            self.assertTrue((folder / 'reserve-intent.json').exists())
            with self.assertRaisesRegex(ValueError, 'existing_intent'):
                p.run_reviewed_window(folder, before, payloads, START, END, cap, lambda: now[0], lambda: 10)

    def test_failure_after_expiry_still_offline_then_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            before, state, payloads, now, calls, cap = self.exercise(folder, True, True)
            with self.assertRaisesRegex(RuntimeError, 'MOCK browser failure'):
                p.run_reviewed_window(folder, before, payloads, START, END, cap, lambda: now[0], lambda: 10)
            self.assertEqual([c[0] for c in calls][-2:], ['offline', 'restore-global'])
            self.assertEqual(state['policies']['global'], before['policies']['global'])

    def test_failed_activation_finally_and_consumed_ambiguous_cleanup(self):
        for ambiguous in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                before, state, payloads, now, calls, cap = self.exercise(folder, fail_stage='install-global', ambiguous=ambiguous)
                with self.assertRaises((ValueError, OSError)):
                    p.run_reviewed_window(folder, before, payloads, START, END, cap, lambda: now[0], lambda: 10)
                self.assertTrue((folder / 'install-global-intent.json').exists())
                if ambiguous:
                    self.assertEqual(len(calls), 1)
                    self.assertTrue((folder / 'cleanup-RECONCILE.json').exists())
                else:
                    self.assertEqual([c[0] for c in calls][-2:], ['offline', 'restore-global'])

    def test_late_or_monotonic_expired_launch_no_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            before, state, payloads, now, calls, cap = self.exercise(folder)
            now[0] += timedelta(minutes=9)
            with self.assertRaises(ValueError):
                p.run_reviewed_window(folder, before, payloads, START, END, cap, lambda: now[0])
            self.assertEqual(calls, [])
            now[0] -= timedelta(minutes=9)
            ticks = iter((0, 1000))
            with self.assertRaisesRegex(ValueError, 'monotonic'):
                p.run_reviewed_window(folder, before, payloads, START, END, cap, lambda: now[0], lambda: next(ticks))
            self.assertEqual(calls, [])

    def test_exclusive_crash_partial_file_blocks_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'intent.json'
            path.write_bytes(b'{')
            with self.assertRaises(FileExistsError):
                p.exclusive(path, {})

    def test_cleanup_wire_failure_attempts_other_stage_once_retains_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            before, state, payloads, now, calls, cap = self.exercise(folder, fail_stage='offline')
            with self.assertRaisesRegex(ValueError, 'cleanup_UNRESOLVED'):
                p.run_reviewed_window(folder, before, payloads, START, END, cap, lambda: now[0], lambda: 10)
            self.assertEqual([x[0] for x in calls][-2:], ['offline', 'restore-global'])
            self.assertEqual(sum(x[0] == 'offline' for x in calls), 1)
            self.assertTrue((folder / 'cleanup-RECONCILE.json').exists())
            self.assertEqual(state['policies']['global'], before['policies']['global'])

    def test_payload_tampering_stops_before_parent_intent_and_wire(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            before, state, payloads, now, calls, cap = self.exercise(folder)
            payloads['global.xml'] += b'<!-- hidden mutation -->'
            with self.assertRaisesRegex(ValueError, 'candidate_exact'):
                p.run_reviewed_window(folder, before, payloads, START, END, cap, lambda: now[0], lambda: 10)
            self.assertEqual(calls, [])
            self.assertFalse((folder / 'parent-window-intent.json').exists())


if __name__ == '__main__':
    unittest.main()