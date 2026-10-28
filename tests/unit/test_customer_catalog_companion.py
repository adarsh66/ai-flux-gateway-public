from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.deployment import customer_catalog_companion as c


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.target = {'configuration': {'references': ['b', 'a']}, 'variables': {'x': {'value': 1}},
                       'checks': [{'address': {'kind': 'var', 'name': 'x'}, 'status': 'unknown'}],
                       'resource_changes': [{'address': c.r.ADDRESS, 'change': {'actions': ['update']}}]}
        self.full = deepcopy(self.target)
        self.full['configuration']['references'].reverse()
        self.full['checks'][0]['status'] = 'pass'

    def test_identical_input_resolution_retains_original(self):
        before = deepcopy(self.target)
        with patch.object(c.r, 'guard') as guard:
            result = c.resolve(self.target, self.full, 'image')
        self.assertEqual(self.target, before)
        self.assertEqual(result['checks'][0]['status'], 'pass')
        guard.assert_called_once_with(result, 'image')

    def test_rejects_input_change_failure_missing_or_target_delta(self):
        for field in ('variables', 'configuration', 'failed', 'missing', 'change', 'errored', 'deferred'):
            with self.subTest(field=field):
                f = deepcopy(self.full)
                if field in ('variables', 'configuration'):
                    f[field] = {}
                elif field == 'failed':
                    f['checks'][0]['status'] = 'fail'
                elif field == 'missing':
                    f['checks'][0]['address']['name'] = 'other'
                elif field == 'change':
                    f['resource_changes'][0]['change']['actions'] = ['delete']
                elif field == 'errored':
                    f['errored'] = True
                else:
                    f['deferred_changes'] = [{}]
                with self.assertRaises(RuntimeError):
                    c.resolve(self.target, f, 'image')

    def test_does_not_override_target_failure(self):
        self.target['checks'][0]['status'] = 'fail'
        with self.assertRaises(RuntimeError):
            c.resolve(self.target, self.full, 'image')

    def test_original_strict_guard_cannot_be_bypassed(self):
        with self.assertRaises(RuntimeError):
            c.resolve(self.target, self.full, 'image')

    def test_existing_apply_intent_blocks_before_check(self):
        with patch.object(c.r, 'HOME') as home, patch.object(c, 'check') as check:
            (home / 'apply-intent.json').exists.return_value = True
            with self.assertRaisesRegex(RuntimeError, 'never_replay'):
                c.apply()
            check.assert_not_called()