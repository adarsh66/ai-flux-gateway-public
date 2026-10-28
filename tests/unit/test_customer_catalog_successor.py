from copy import deepcopy
import unittest
from scripts.deployment import customer_catalog_successor as s


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.role = [s.facts.ASSIGNMENT, s.facts.PRINCIPAL,
            '/subscriptions/' + s.r.rt.SUB + '/providers/Microsoft.Authorization/roleDefinitions/' + s.facts.ROLE,
            s.facts.APIM, None]
        self.before = {'runtime': {'roleAssignments': [self.role, ['preserved']]}, 'settings': 'preserved'}
        self.current = deepcopy(self.before)
        self.current['runtime']['roleAssignments'].remove(self.role)
        self.proof = {'assignment_http_status': 404, 'actual_role_definition_http_status': 200,
            'actual_role': {'id': self.role[2], 'name': 'poc-ids-scoped-APIM-read-write-role',
                'permissions': [{'actions': s.facts.ACTIONS[7:], 'notActions': [], 'dataActions': [], 'notDataActions': []}]},
            'subscription_management_actions_covered': True,
            'action_grant_coverage': {a: ['grant'] for a in s.facts.ACTIONS[:7]},
            'removed_roles': [self.role], 'added_roles': [], 'all_other_protected_fields_equal': True,
            'original_baseline_sha256': s.r.fs.sha(self.before), 'current_baseline_sha256': s.r.fs.sha(self.current)}

    def test_exact_metadata_bound_removal_only(self):
        original = deepcopy(self.before)
        self.assertEqual(s.reconcile(self.before, self.current, self.proof), self.current)
        self.assertEqual(self.before, original)

    def test_rejects_any_other_change(self):
        for field in ('settings', 'added_role', 'different_removal'):
            with self.subTest(field=field):
                current = deepcopy(self.current)
                if field == 'settings':
                    current['settings'] = 'changed'
                elif field == 'added_role':
                    current['runtime']['roleAssignments'].append(['new'])
                else:
                    current['runtime']['roleAssignments'] = []
                with self.assertRaises(RuntimeError):
                    s.reconcile(self.before, current, self.proof)

    def test_rejects_unproven_coverage_role_or_snapshot(self):
        for field in ('coverage', 'role', 'actions', 'hash', 'status'):
            with self.subTest(field=field):
                proof = deepcopy(self.proof)
                if field == 'coverage':
                    proof['action_grant_coverage'][s.facts.ACTIONS[0]] = []
                elif field == 'role':
                    proof['actual_role']['name'] = 'subscription-manager'
                elif field == 'actions':
                    proof['actual_role']['permissions'][0]['actions'] = ['*']
                elif field == 'hash':
                    proof['current_baseline_sha256'] = 'wrong'
                else:
                    proof['assignment_http_status'] = 200
                with self.assertRaises(RuntimeError):
                    s.reconcile(self.before, self.current, proof)