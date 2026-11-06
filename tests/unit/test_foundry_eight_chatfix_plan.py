"""Offline exact one-image guard tests; no command or cloud execution."""
from copy import deepcopy
import unittest

from scripts.deployment import foundry_eight_chatfix_plan as p


class OnePinGuardTests(unittest.TestCase):
    def fixture(self):
        image = p.fix.b.HOST + '/aiflux-api@sha256:' + 'a' * 64
        old = {'id': p.rt_id if hasattr(p, 'rt_id') else p.p.rt.RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-api',
               'name': 'poc-ids-token-ex-api', 'app_settings': {'keep': 'exact'}, 'identity': {'keep': True},
               'public_network_access_enabled': False,
               'site_config': [{'application_stack': [{'docker_image_name': 'aiflux-api@sha256:' + p.fix.PIN,
                   'docker_registry_url': 'https://' + p.fix.b.HOST}]}]}
        new = deepcopy(old)
        new['site_config'][0]['application_stack'][0]['docker_image_name'] = image.split('/', 1)[1]
        plan = {'applyable': True, 'errored': False, 'resource_changes': [
            {'address': p.TARGET, 'mode': 'managed', 'change': {'actions': ['update'], 'before': old, 'after': new, 'after_unknown': {}}}],
            'checks': [{'address': {'kind': 'var', 'to_display': 'var.apps'}, 'status': 'unknown'}]}
        return plan, image, {'all_conditions_true': True, 'inactive_counts': {}}

    def test_exact_one_pin(self):
        report = p.guard(*self.fixture())
        self.assertEqual(report['counts']['update'], 1)

    def test_reject_all_nonimage_deltas(self):
        for field in ('app_settings', 'identity', 'public_network_access_enabled', 'tags', 'https_only'):
            plan, image, proof = self.fixture()
            plan['resource_changes'][0]['change']['after'][field] = 'unauthorized'
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                p.guard(plan, image, proof)

    def test_reject_extra_writes_replacements_unknowns_and_drift(self):
        for mode in ('extra', 'replace', 'unknown', 'drift', 'output', 'check'):
            plan, image, proof = self.fixture()
            row = plan['resource_changes'][0]
            if mode == 'extra':
                extra = deepcopy(row)
                extra['address'] = 'azurerm_linux_web_app.main["admin"]'
                plan['resource_changes'].append(extra)
            elif mode == 'replace':
                row['change']['actions'] = ['delete', 'create']
            elif mode == 'unknown':
                row['change']['after_unknown'] = {'app_settings': True}
            elif mode == 'drift':
                plan['resource_drift'] = [row]
            elif mode == 'output':
                plan['output_changes'] = {'sneak': {'actions': ['update'], 'before': 1, 'after': 2}}
            else:
                plan['checks'][0]['status'] = 'fail'
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                p.guard(plan, image, proof)


if __name__ == '__main__':
    unittest.main()