"""Offline proof that the portal-only plan guard fails closed."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.deployment import portal_fix as fix


class PortalFixGuardTests(unittest.TestCase):
    def setUp(self):
        self.release = {'results': {k: {'image': fix.HOST + '/aiflux-' + k + '@sha256:' + 'a' * 64}
                                    for k in fix.KINDS}}
        self.plan = {'resource_changes': []}
        for kind in fix.KINDS:
            before = {'app_settings': {'CONTROL_ORIGIN': 'https://existing'},
                      'identity': [{'type': 'UserAssigned'}],
                      'site_config': [{'scm_ip_restriction_default_action': 'Allow',
                          'application_stack': [{'docker_image_name': 'old@sha256:' + 'b' * 64,
                                                'docker_registry_url': 'https://' + fix.HOST}]}]}
            after = copy.deepcopy(before)
            after['site_config'][0]['application_stack'][0]['docker_image_name'] = self.release['results'][kind]['image'].split('/', 1)[1]
            self.plan['resource_changes'].append({'address': f'azurerm_linux_web_app.main["{kind}"]',
                'mode': 'managed', 'change': {'actions': ['update'], 'before': before,
                                            'after': after, 'after_unknown': {}}})

    def test_only_two_image_pins_pass_preserving_existing_allow(self):
        fix.guard(self.plan, self.release)

    def test_settings_change_rejected(self):
        self.plan['resource_changes'][0]['change']['after']['app_settings']['API_KEY'] = 'dummy'
        with self.assertRaisesRegex(RuntimeError, 'non_image_fields'):
            fix.guard(self.plan, self.release)

    def test_silent_admin_ingress_remediation_rejected(self):
        self.plan['resource_changes'][0]['change']['after']['site_config'][0]['scm_ip_restriction_default_action'] = 'Deny'
        with self.assertRaisesRegex(RuntimeError, 'non_image_site_config'):
            fix.guard(self.plan, self.release)

    def test_replacement_rejected(self):
        self.plan['resource_changes'][0]['change']['actions'] = ['delete', 'create']
        with self.assertRaisesRegex(RuntimeError, 'out_of_scope'):
            fix.guard(self.plan, self.release)

    def test_api_change_rejected(self):
        resource = copy.deepcopy(self.plan['resource_changes'][0])
        resource['address'] = 'azurerm_linux_web_app.main["api"]'
        self.plan['resource_changes'].append(resource)
        with self.assertRaisesRegex(RuntimeError, 'out_of_scope'):
            fix.guard(self.plan, self.release)

    def test_missing_portal_rejected(self):
        self.plan['resource_changes'].pop()
        with self.assertRaisesRegex(RuntimeError, 'expected_exactly_two_portals'):
            fix.guard(self.plan, self.release)

    def test_two_portal_variables_preserve_current_api_and_worker_pins(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder)
            (old / 'runtime-images.tfvars.json').write_text(json.dumps({
                'apps': {k: {'image': 'historical'} for k in ['api', 'admin', 'customer', 'ingestion']}
            }))
            fresh = {'sites': {k: {'image': 'DOCKER|' + fix.HOST + '/aiflux-' + k + '@sha256:' + 'e' * 64}
                                for k in ['api', 'admin', 'customer', 'ingestion']}}
            with patch.object(fix, 'OLD', old):
                values = fix.runtime_variables(self.release, fresh)
            for kind in ['api', 'ingestion']:
                self.assertEqual(values['apps'][kind]['image'], 'aiflux-' + kind + '@sha256:' + 'e' * 64)
            for kind in fix.KINDS:
                self.assertEqual(values['apps'][kind]['image'], self.release['results'][kind]['image'].split('/', 1)[1])

    def test_unknown_writable_field_rejected(self):
        self.plan['resource_changes'][0]['change']['after_unknown']['app_settings'] = True
        with self.assertRaisesRegex(RuntimeError, 'unknown_writable_values'):
            fix.guard(self.plan, self.release)

    def test_computed_output_unknown_allowed(self):
        c = self.plan['resource_changes'][0]['change']
        c['before']['outbound_ip_addresses'] = '192.0.2.1'
        c['after']['outbound_ip_addresses'] = None
        c['after_unknown']['outbound_ip_addresses'] = True
        fix.guard(self.plan, self.release)

    def test_identity_change_rejected(self):
        self.plan['resource_changes'][0]['change']['after']['identity'][0]['type'] = 'SystemAssigned'
        with self.assertRaisesRegex(RuntimeError, 'non_image_fields'):
            fix.guard(self.plan, self.release)

    def test_wrong_digest_rejected(self):
        self.release['results']['admin']['image'] = fix.HOST + '/aiflux-admin@sha256:' + 'c' * 64
        with self.assertRaisesRegex(RuntimeError, 'wrong_image_pin'):
            fix.guard(self.plan, self.release)

    def test_routing_change_still_rejected(self):
        self.plan['resource_changes'][0]['change']['after']['site_config'][0]['vnet_route_all_enabled'] = False
        with self.assertRaisesRegex(RuntimeError, 'non_image_site_config'):
            fix.guard(self.plan, self.release)


class PortalFixApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.tag = 'local-20261023t173114z-571d75366033'
        (self.home / self.tag).mkdir()
        old = self.home / 'old'
        old.mkdir()
        (old / 'runtime-images.tfvars.json').write_text(json.dumps({'apps': {k: {} for k in fix.KINDS}}))
        fixture = PortalFixGuardTests()
        fixture.setUp()
        self.parsed, self.release = fixture.plan, fixture.release
        self.calls = []
        self.plan_path = None
        for target, value in [('HOME', self.home), ('OLD', old)]:
            patcher = patch.object(fix, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target, options in [('verify_release', {'return_value': self.release}),
            ('require_validation', {}), ('baseline', {'return_value': {'protected': 'unchanged'}})]:
            patcher = patch.object(fix, target, **options)
            setattr(self, target, patcher.start())
            self.addCleanup(patcher.stop)
        patcher = patch.object(fix.rt, 'run', return_value='S-1-5-21-1234')
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(fix.rt, 'tf', side_effect=self.tf)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tf(self, args):
        self.calls.append(args)
        if args[0] == 'plan':
            self.plan_path = Path(next(a[5:] for a in args if a.startswith('-out=')))
            self.plan_path.write_bytes(b'exact-secret-plan-test-fixture')
        if args[0] == 'show':
            return json.dumps(self.parsed)
        if args[0] == 'apply':
            self.assertEqual(Path(args[-1]), self.plan_path)
            self.assertTrue(self.plan_path.exists())
            self.assertEqual(self.plan_path.read_bytes(), b'exact-secret-plan-test-fixture')
            return 'Apply complete! Resources: 0 added, 2 changed, 0 destroyed.'
        return ''

    def test_apply_exact_fresh_plan_inside_temporary_lifetime(self):
        fix.plan(self.tag, apply=True)
        self.assertEqual(sum(c[0] == 'plan' for c in self.calls), 1)
        self.assertEqual(sum(c[0] == 'apply' for c in self.calls), 1)
        self.assertFalse(self.plan_path.exists())
        self.assertEqual(self.require_validation.call_count, 2)
        self.assertEqual(self.verify_release.call_count, 2)

    def test_baseline_drift_blocks_apply_and_deletes_plan(self):
        self.baseline.side_effect = [{'protected': 'unchanged'}, {'protected': 'drift'}]
        with self.assertRaisesRegex(RuntimeError, 'live_baseline_drift'):
            fix.plan(self.tag, apply=True)
        self.assertFalse(any(c[0] == 'apply' for c in self.calls))
        self.assertFalse(self.plan_path.exists())

    def test_missing_validation_blocks_before_planning(self):
        self.require_validation.side_effect = RuntimeError('current_validation_missing')
        with self.assertRaisesRegex(RuntimeError, 'current_validation_missing'):
            fix.plan(self.tag, apply=True)
        self.assertFalse(self.calls)

    def test_changed_sources_after_plan_block_apply(self):
        self.verify_release.side_effect = [self.release, RuntimeError('source_changed')]
        with self.assertRaisesRegex(RuntimeError, 'source_changed'):
            fix.plan(self.tag, apply=True)
        self.assertFalse(any(c[0] == 'apply' for c in self.calls))

    def test_rejected_guard_never_applies(self):
        self.parsed['resource_changes'][0]['change']['after']['app_settings']['unsafe'] = 'change'
        with self.assertRaisesRegex(RuntimeError, 'non_image_fields'):
            fix.plan(self.tag, apply=True)
        self.assertFalse(any(c[0] == 'apply' for c in self.calls))

    def test_plan_only_never_applies(self):
        fix.plan(self.tag)
        self.assertFalse(any(c[0] == 'apply' for c in self.calls))

    def test_apply_failure_records_attempt_not_success_and_cleans(self):
        original = self.tf
        def fail(args):
            if args[0] == 'apply':
                raise RuntimeError('command_failed')
            return original(args)
        with patch.object(fix.rt, 'tf', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'command_failed'):
                fix.plan(self.tag, apply=True)
        proof = json.loads((self.home / self.tag / 'apply-result.json').read_text())
        self.assertTrue(proof['applyAttempted'])
        self.assertFalse(proof['applied'])
        self.assertFalse(self.plan_path.exists())


class AdminOnlyGuardTests(unittest.TestCase):
    def setUp(self):
        fixture = PortalFixGuardTests()
        fixture.setUp()
        self.release = fixture.release
        self.release['portals'] = ['admin']
        self.plan = fixture.plan
        self.customer_change = self.plan['resource_changes'].pop()

    def test_exact_admin_image_only_passes(self):
        fix.guard(self.plan, self.release)

    def test_customer_change_rejected_even_with_legacy_customer_result(self):
        self.plan['resource_changes'].append(self.customer_change)
        with self.assertRaisesRegex(RuntimeError, 'out_of_scope'):
            fix.guard(self.plan, self.release)

    def test_customer_only_scope_rejected(self):
        self.release['portals'] = ['customer']
        with self.assertRaisesRegex(RuntimeError, 'out_of_scope'):
            fix.guard(self.plan, self.release)

    def test_missing_admin_rejected(self):
        self.plan['resource_changes'] = []
        with self.assertRaisesRegex(RuntimeError, 'expected_exactly_admin'):
            fix.guard(self.plan, self.release)

    def test_settings_identity_scm_routing_replacement_unknown_rejected(self):
        for field in ('settings', 'identity', 'scm', 'routing', 'replacement', 'unknown', 'pin'):
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan)
                change = plan['resource_changes'][0]['change']
                after = change['after']
                if field == 'settings':
                    after['app_settings']['UNAUTHORIZED'] = 'change'
                elif field == 'identity':
                    after['identity'][0]['type'] = 'SystemAssigned'
                elif field == 'scm':
                    after['site_config'][0]['scm_ip_restriction_default_action'] = 'Deny'
                elif field == 'routing':
                    after['site_config'][0]['vnet_route_all_enabled'] = False
                elif field == 'replacement':
                    change['actions'] = ['delete', 'create']
                elif field == 'unknown':
                    change['after_unknown']['site_config'] = True
                else:
                    after['site_config'][0]['application_stack'][0]['docker_image_name'] = 'wrong'
                with self.assertRaises(RuntimeError):
                    fix.guard(plan, self.release)

    def test_duplicate_admin_rejected(self):
        self.plan['resource_changes'] *= 2
        with self.assertRaisesRegex(RuntimeError, 'out_of_scope'):
            fix.guard(self.plan, self.release)

    def test_legacy_scope_still_requires_both_portals(self):
        self.release.pop('portals')
        with self.assertRaisesRegex(RuntimeError, 'expected_exactly_two_portals'):
            fix.guard(self.plan, self.release)

    def test_api_change_rejected(self):
        self.plan['resource_changes'][0]['address'] = 'azurerm_linux_web_app.main["api"]'
        with self.assertRaisesRegex(RuntimeError, 'out_of_scope'):
            fix.guard(self.plan, self.release)

    def test_variables_use_fresh_customer_and_api_not_historical_pins(self):
        with tempfile.TemporaryDirectory() as temp:
            old = Path(temp)
            (old / 'runtime-images.tfvars.json').write_text(json.dumps({'apps': {
                k: {'image': 'historical'} for k in ('admin', 'customer', 'api')}}))
            fresh = {'sites': {k: {'image': 'DOCKER|' + fix.HOST + '/aiflux-' + k + '@sha256:' + 'd' * 64}
                               for k in ('admin', 'customer', 'api')}}
            with patch.object(fix, 'OLD', old):
                variables = fix.runtime_variables(self.release, fresh)
            for kind in ('customer', 'api'):
                self.assertEqual(variables['apps'][kind]['image'], 'aiflux-' + kind + '@sha256:' + 'd' * 64)
            self.assertEqual(variables['apps']['admin']['image'], self.release['results']['admin']['image'].split('/', 1)[1])

    def test_nonimmutable_live_pin_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            old = Path(temp)
            (old / 'runtime-images.tfvars.json').write_text(json.dumps({'apps': {'customer': {}}}))
            with patch.object(fix, 'OLD', old):
                with self.assertRaisesRegex(RuntimeError, 'baseline_image_not_immutable'):
                    fix.runtime_variables(self.release, {'sites': {'customer': {'image': 'DOCKER|latest'}}})


class AdminOnlyApplyTests(PortalFixApplyTests):
    def setUp(self):
        super().setUp()
        self.release['portals'] = ['admin']
        self.parsed['resource_changes'].pop()
        # Isolate the already separately-tested variable overlay in these apply-lifetime tests.
        patcher = patch.object(fix, 'runtime_variables', return_value={'apps': {}})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_admin_target_only(self):
        fix.plan(self.tag, apply=True)
        args = next(call for call in self.calls if call[0] == 'plan')
        self.assertEqual([a for a in args if a.startswith('-target=')],
                         ['-target=azurerm_linux_web_app.main["admin"]'])


if __name__ == '__main__':
    unittest.main()