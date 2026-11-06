"""Focused stdlib boundaries; no predecessor prepare or live transport."""
import copy
from datetime import UTC, datetime, timedelta
import unittest

from scripts.deployment import auto_resume_current_adapter as a


class Boundaries(unittest.TestCase):
    def test_ttl_boundary(self):
        for remaining in (0, 599, 600):
            with self.assertRaises(ValueError):
                a.token_claims({'tid': a.TENANT, 'oid': a.OPERATOR, 'aud': a.STORAGE,
                                'exp': 1000 + remaining}, a.STORAGE, 1000)
        self.assertEqual(a.token_claims({'tid': a.TENANT, 'oid': a.OPERATOR,
                         'aud': a.STORAGE, 'exp': 1601}, a.STORAGE, 1000)['expiry'], 1601)

    def test_audience_not_relaxed(self):
        for key in ('tid', 'oid', 'aud'):
            v = dict(tid=a.TENANT, oid=a.OPERATOR, aud=a.STORAGE, exp=9999)
            v[key] = 'wrong'
            with self.assertRaises(ValueError):
                a.token_claims(v, a.STORAGE, 1000)

    def test_whole_checks_permutation_only(self):
        before = {'serial': 130, 'check_results': [dict(object_kind='check', config_addr='a', status='pass'),
                                                   dict(object_kind='check', config_addr='b', status='unknown')]}
        after = copy.deepcopy(before)
        after['check_results'].reverse()
        self.assertTrue(a.state_equal(before, after))
        after['check_results'][0]['status'] = 'pass'
        self.assertFalse(a.state_equal(before, after))

    def test_noncheck_not_ignored(self):
        self.assertFalse(a.state_equal({'serial': 130, 'check_results': []},
                                       {'serial': 131, 'check_results': []}))

    def test_duplicate_checks_rejected(self):
        row = dict(object_kind='check', config_addr='a')
        with self.assertRaises(ValueError):
            a.keyed_state({'check_results': [row, row]})

    def test_role_equality_retains_every_field(self):
        rows = [dict(id='x', condition=None), dict(id='y', condition='c')]
        self.assertTrue(a.roles_equal(rows, list(reversed(rows))))
        changed = copy.deepcopy(rows)
        changed[0]['condition'] = ''
        self.assertFalse(a.roles_equal(rows, changed))

    def test_duplicate_roles_rejected(self):
        with self.assertRaises(ValueError):
            a.roles_equal([{'id': 'x'}, {'id': 'x'}], [])

    def test_xml_csharp_not_normalized(self):
        first = '<policies><inbound><when condition="@(a &amp; b)" /></inbound></policies>'
        same = '<policies>\n<inbound><when condition="@(a &amp; b)"/></inbound>\n</policies>'
        self.assertEqual(a.xml_tree(first), a.xml_tree(same))
        self.assertNotEqual(a.xml_tree(first), a.xml_tree(first.replace('a &amp;', 'a  &amp;')))

    def test_xml_attribute_newline_not_normalized(self):
        self.assertNotEqual(a.xml_tree('<x v="@(a\nb)"/>'), a.xml_tree('<x v="@(a b)"/>'))

    def test_xml_entity_rejected(self):
        with self.assertRaises(ValueError):
            a.xml_tree('<!DOCTYPE x><x/>')

    def test_current_reference_scope(self):
        name = next(iter(a.ADDED))
        a.auto_references({'global_explicit_routes': name}, {'fragment': 'old pool'})
        with self.assertRaises(ValueError):
            a.auto_references({}, {'fragment': name})

    def test_window_boundaries(self):
        start = datetime(2026, 10, 31, tzinfo=UTC)
        self.assertEqual(a.window(start, start+timedelta(minutes=30), start), 1800)
        with self.assertRaises(ValueError):
            a.window(start, start+timedelta(minutes=30, seconds=1), start)
        with self.assertRaises(ValueError):
            a.window(start, start+timedelta(minutes=30), start+timedelta(minutes=9))

    def test_etags_no_wildcard(self):
        for value in (None, '', '*', 'W/"weak"'):
            with self.assertRaises(ValueError):
                a.etag(value)
        self.assertEqual(a.etag('"actual"'), '"actual"')

    def test_ip_unknown_not_offline_blocker(self):
        plan = a.contract()
        self.assertEqual(plan['admission_ip'], '167.103.66.248')
        self.assertFalse(plan['APIM_IP_preproof_required'])
        self.assertEqual(plan['scoring_budget'], 1)
        self.assertEqual(plan['completion_budget'], 0)
        self.assertEqual(len(plan['stages']), 6)


if __name__ == '__main__':
    unittest.main()