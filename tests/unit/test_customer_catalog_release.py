"""Synthetic offline mutation tests: no Azure calls."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.deployment import customer_catalog_release as release


class CustomerOnlyTests(unittest.TestCase):
    def setUp(self):
        self.image = release.portals.HOST + '/aiflux-customer@sha256:' + 'a' * 64
        before = {'app_settings': {'example': 'preserve'}, 'identity': [{'type': 'UserAssigned'}],
                  'site_config': [{'always_on': True, 'application_stack': [{
                      'docker_image_name': 'aiflux-customer@sha256:' + release.PINS['customer'],
                      'docker_registry_url': 'https://' + release.portals.HOST}]}]}
        after = deepcopy(before)
        after['site_config'][0]['application_stack'][0]['docker_image_name'] = self.image.split('/', 1)[1]
        self.plan = {'applyable': True, 'checks': [{'status': 'pass'}], 'resource_changes': [{
            'mode': 'managed', 'address': release.ADDRESS,
            'change': {'actions': ['update'], 'before': before, 'after': after, 'after_unknown': {}}}]}

    def test_exact_customer_image_passes(self):
        release.guard(self.plan, self.image)

    def test_predecessor_drift_rejected(self):
        self.plan['resource_changes'][0]['change']['before']['site_config'][0]['application_stack'][0]['docker_image_name'] = 'another'
        with self.assertRaises(RuntimeError):
            release.guard(self.plan, self.image)

    def test_other_components_and_resources_rejected(self):
        for address in ('azurerm_linux_web_app.main["api"]', 'azurerm_linux_web_app.main["admin"]',
                        'azurerm_linux_function_app.ingestion[0]', 'azapi_resource.poc_settings[0]', 'azurerm_role_assignment.extra'):
            with self.subTest(address=address):
                plan = deepcopy(self.plan)
                row = deepcopy(plan['resource_changes'][0])
                row['address'] = address
                plan['resource_changes'].append(row)
                with self.assertRaises(RuntimeError):
                    release.guard(plan, self.image)

    def test_settings_identity_always_on_changes_rejected(self):
        for field in ('settings', 'identity', 'always_on', 'registry'):
            with self.subTest(field=field):
                plan = deepcopy(self.plan)
                after = plan['resource_changes'][0]['change']['after']
                if field == 'settings':
                    after['app_settings']['example'] = 'changed'
                elif field == 'identity':
                    after['identity'] = []
                elif field == 'always_on':
                    after['site_config'][0]['always_on'] = False
                else:
                    after['site_config'][0]['application_stack'][0]['docker_registry_url'] = 'https://other.invalid'
                with self.assertRaises(RuntimeError):
                    release.guard(plan, self.image)

    def test_failed_unknown_deferred_and_nonapplyable_rejected(self):
        for key, value in (('checks', [{'status': 'unknown'}]), ('checks', [{'status': 'fail'}]),
                           ('applyable', False), ('errored', True), ('deferred_changes', [{}])):
            plan = deepcopy(self.plan)
            plan[key] = value
            with self.assertRaises(RuntimeError):
                release.guard(plan, self.image)

    def test_unknown_writable_and_replace_rejected(self):
        for key, value in (('after_unknown', {'app_settings': True}), ('actions', ['delete', 'create'])):
            plan = deepcopy(self.plan)
            plan['resource_changes'][0]['change'][key] = value
            with self.assertRaises(RuntimeError):
                release.guard(plan, self.image)

    def test_wrong_repository_tag_and_digest_rejected(self):
        for image in (self.image.replace('customer', 'admin'), 'aiflux-customer:latest', self.image[:-1]):
            with self.assertRaises(RuntimeError):
                release.guard(self.plan, image)

    def test_exclusive_intent_never_overwritten(self):
        with tempfile.TemporaryDirectory() as name, patch.object(release, 'HOME', Path(name)):
            release.exclusive('apply-intent.json', {'once': True})
            with self.assertRaises(FileExistsError):
                release.exclusive('apply-intent.json', {'twice': True})

    def test_apply_marker_blocks_before_any_check_or_apply(self):
        with tempfile.TemporaryDirectory() as name, patch.object(release, 'HOME', Path(name)), patch.object(release, 'check') as check:
            (Path(name) / 'apply-intent.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'never_replay'):
                release.apply()
            check.assert_not_called()

    def test_build_marker_blocks_before_any_build(self):
        with tempfile.TemporaryDirectory() as name, patch.object(release, 'HOME', Path(name)), \
                patch.object(release, 'account'), patch.object(release, 'source_check'), \
                patch.object(release.subprocess, 'run') as run:
            (Path(name) / 'build-intent.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'never_replay'):
                release.build()
            run.assert_not_called()