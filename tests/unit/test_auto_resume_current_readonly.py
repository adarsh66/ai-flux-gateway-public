"""New collector local mock tests only; no original r5 imports/prepare."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.deployment import auto_resume_current_adapter as a
from scripts.deployment import auto_resume_current_readonly as r
from scripts.deployment import auto_resume_current_successor as s


class LocalMocks(unittest.TestCase):
    def test_credential_single_acquisition(self):
        import base64
        import json
        claims = dict(tid=a.TENANT, oid=a.OPERATOR, aud=a.STORAGE, exp=9999999999)
        token = 'header.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.signature'
        with patch.object(r, 'command', return_value={'access_token': token}) as call, patch.object(r, 'write'):
            self.assertEqual(r.credential(a.STORAGE, 'mock')[0], token)
            call.assert_called_once()

    def test_short_token_no_second_acquisition(self):
        import base64
        import json
        claims = dict(tid=a.TENANT, oid=a.OPERATOR, aud=a.STORAGE, exp=1)
        token = 'h.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.s'
        with patch.object(r, 'command', return_value={'access_token': token}) as call:
            with self.assertRaises(ValueError):
                r.credential(a.STORAGE, 'mock')
            call.assert_called_once()

    def test_exclusive_receipt_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r, 'HOME', Path(folder)):
            r.write('intent.json', {'one': 1})
            with self.assertRaises(FileExistsError):
                r.write('intent.json', {'two': 2})

    def test_scope_and_mutation_rejected_pre_wire(self):
        reader = object.__new__(r.Reads)
        for url, method in [('https://evil.test/x', 'GET'),
                            (a.ARM.rstrip('/')+r.APIM+'?api-version=2024-05-01', 'PATCH')]:
            with self.assertRaises(ValueError):
                reader.request(url, method)

    def test_cached_reads_never_replay_transport(self):
        reader = object.__new__(r.Reads)
        url = a.ARM.rstrip('/')+r.APIM+'?api-version=2024-05-01'
        reader.cache = {('GET', url): {'actual': True}}
        self.assertEqual(reader.get(url), {'actual': True})

    def test_all22_separate_original_pool_freeze(self):
        value = self.fixture()
        self.assertEqual(len(value['full22_deployments']['value']), 22)
        self.assertEqual(value['original_Auto_candidates'], ['gpt-4o'])
        self.assertFalse(s.readiness(value)['diagnostic_ready'])

    @staticmethod
    def fixture():
        baseline = {str(n): n for n in range(12)}
        baseline['settings_hashes'] = {name: 'hash' for name in ('api', 'admin', 'customer', 'ingestion')}
        sources = {str(n): 'digest' for n in range(279)}
        sources['infra/project-route/main.tf'] = 'current'
        return s.freeze({'baseline': baseline}, {'value': [{'id': '/deployment/'+str(n)} for n in range(22)]},
            'explicit '+next(iter(a.ADDED)), '<global/>', {'candidates': ['gpt-4o']}, {'resolver': 'original'}, sources,
            [{'scope': scope, 'format': 'xml', 'etag': '"actual"', 'actual_wire': {'status': 200}}
             for scope in ('global', 'active', 'revision-2')])

    def test_full_metadata_drift_not_historical_projection(self):
        frozen = self.fixture()
        rows = deepcopy(frozen['full22_deployments'])
        rows['value'][-1]['new_field'] = 1
        with self.assertRaises(ValueError):
            s.unchanged(frozen, frozen['current_snapshot'], rows, frozen['current280_sources'])

    def test_cleanup_exact_current_global_not_historical(self):
        frozen = self.fixture()
        plan = s.cleanup_plan(frozen, r.APIM+'/apis/aiflux-dev-unified;rev=2', '"rev"', '"global"')
        self.assertEqual(plan['restore_global']['value'], '<global/>')
        self.assertEqual(plan['offline']['body'], {'properties': {'isOnline': False}})
        self.assertFalse(plan['execute_now'])


if __name__ == '__main__':
    unittest.main()