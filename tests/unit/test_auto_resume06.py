"""Resume06 mocks only: new capabilities, never consumed live entrypoints."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.deployment import auto_resume06_parent as p
from scripts.deployment import auto_resume06_transport as t
from scripts.deployment import auto_resume06_review as review

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def baseline():
    folder, frozen = p.old.retained()
    policies = {key: (folder / name).read_bytes() for key, name in (
        ('global', 'global-actual.xml'), ('owned', 'revision-2-actual.xml'), ('active', 'active-actual.xml'))}
    snapshot = deepcopy(frozen['current_snapshot'])
    snapshot['baseline']['apim']['global'] = p.render.sha(policies['global'])
    return {'snapshot': snapshot, 'deployments': deepcopy(frozen['full22_deployments']),
        'root': p.old.load(p.ROOT / '.deployment/uv-apply01/remaining02/commands/state-after.stdout.txt'),
        'child': p.old.load(p.ROOT / 'infra/project-route/terraform.tfstate'),
        'roles': deepcopy(frozen['current_snapshot']['baseline']['runtime']['roleAssignments']),
        'inheritance': {'MOCK_ALL_INHERITANCE': 'full'},
        'revisions': p.old.load(folder / 'revisions-full.json')['value'],
        'owned': p.old.load(folder / 'revision-2-detail.json'), 'policies': policies,
        'etags': {'global': '"g0"', 'policy': '"p0"', 'api': '"a0"'}, 'sources': p.sources()}


class Port:
    def __init__(self):
        self.state = baseline()
        self.calls = []
        self.status = 200
        self.fail_stage = None
        self.apply_before_timeout = False
        self.response_etag_wrong = False
        self.cleanup_flags = []
        self.folder = None
        self.ledger = None

    def capture(self, cleanup=False):
        self.cleanup_flags.append(cleanup)
        return deepcopy(self.state)

    def send(self, stage, body, etag, timeout, cleanup=False):
        assert self.ledger.exists()  # ledger + intent must precede every effect
        assert (self.folder / (stage + '-intent.json')).exists()
        assert timeout == 45
        self.calls.append(stage)
        if self.fail_stage == stage and not self.apply_before_timeout:
            raise TimeoutError('MOCK uncertain wire')
        value = json.loads(body)
        if stage in ('online', 'offline'):
            assert value == {'properties': {'isOnline': stage == 'online'}}
            slot = 'api'
            self.state['owned']['properties']['isOnline'] = stage == 'online'
            for row in self.state['revisions']:
                if row['apiRevision'] == '2':
                    row['isOnline'] = stage == 'online'
        else:
            assert set(value['properties']) == {'format', 'value'}
            assert value['properties']['format'] == 'xml'
            slot = 'global' if 'global' in stage else 'policy'
            key = 'global' if slot == 'global' else 'owned'
            self.state['policies'][key] = value['properties']['value'].encode()
            if slot == 'global':
                self.state['snapshot']['baseline']['apim']['global'] = p.render.sha(self.state['policies'][key])
        self.state['etags'][slot] = '"' + slot + str(len(self.calls)) + '"'
        if self.fail_stage == stage:
            raise TimeoutError('MOCK applied but response lost')
        return {'http_status': self.status,
            'etag': '"WRONG"' if self.response_etag_wrong and not cleanup else self.state['etags'][slot]}


class CapabilitiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # All files are bound by the offline runner before executing this suite.
        cls.source_map = p.sources()

    def fixture(self, root):
        port = Port()
        folder = root / 'package'
        clock = [NOW]
        reviews = []
        def verify(kind, binding):
            reviews.append((kind, deepcopy(binding)))
        manifest = p.prepare(folder, port, verify, lambda: clock[0])
        digest = p.render.sha((folder / 'manifest.json').read_bytes())
        observation = {'manifest_sha256': digest, 'browser_source_sha256': manifest['artifacts']['browser-source.js'],
            'issued_at': NOW.isoformat(), 'page_url': 'https://poc-ids-token-ex-customer.azurewebsites.net/playground',
            'page_id': 'a' * 36, 'IP': p.render.IP, 'system_empty': True, 'history_empty': True,
            'safe_event': 'fill+End', 'fixture': False, 'send_invoked': False, 'auth_inspected': False}
        ledger = root / 'shared-owner.json'
        port.folder, port.ledger = folder, ledger
        def browser(binding, timeout):
            self.assertTrue((folder / 'reserve-intent.json').exists())
            self.assertEqual(binding['reservation']['completion_budget'], 0)
            return {'manifest_sha256': digest, 'keyboard_invocations': 1, 'observed_posts': 1,
                'forwarded': True, 'auth_inspected': False, 'raw_body_logged': False,
                'diagnostic': {'probabilities': {'greeting': .8, 'arithmetic': .2}}}
        class MockParentBrowser(review.ParentBrowser):
            def __init__(self): pass
            def validate_preflight(self, value):
                assert value == observation
            def score(self, binding, timeout): return browser(binding, timeout)
        return port, folder, clock, verify, manifest, digest, observation, ledger, MockParentBrowser(), reviews

    def execute(self, data, browser=None):
        port, folder, clock, verify, _, digest, observation, ledger, native, _ = data
        if browser:
            class MockParentBrowser(review.ParentBrowser):
                def __init__(self): pass
                def validate_preflight(self, value): pass
                def score(self, binding, timeout): return browser(binding, timeout)
            native = MockParentBrowser()
        return p.run_reviewed_window(folder, digest, port, verify, native,
            observation, ledger, lambda: clock[0], lambda: 10)

    def test_prepare_real_package_current22_and_four_attribute_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp))
            port, folder, _, _, manifest, digest, _, ledger, _, reviews = data
            self.assertFalse(ledger.exists())
            self.assertEqual(port.calls, [])
            self.assertEqual(reviews[0][0], 'nativeSourceReview')
            self.assertEqual(p.render.times(manifest['start'], manifest['end'])[1] -
                p.render.times(manifest['start'], manifest['end'])[0], timedelta(minutes=30))
            _, before, payloads = p.checked(folder, digest)
            self.assertEqual(len(before['roles']), 79)
            self.assertEqual(len(before['deployments']['value']), 22)
            self.assertEqual(len(payloads['proof']['global_delta']), 1)
            self.assertEqual(len(payloads['proof']['revision_delta']), 3)

    def test_source_review_failure_precedes_capture_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = Port()
            folder = Path(tmp) / 'not-created'
            def reject(*_):
                raise ValueError('independent source review rejected')
            with self.assertRaisesRegex(ValueError, 'review rejected'):
                p.prepare(folder, port, reject)
            self.assertFalse(folder.exists())
            self.assertEqual(port.cleanup_flags, [])

    def test_six_stages_200_and_201_response_ETags_and_exact_restore(self):
        for status in (200, 201):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                data = self.fixture(Path(tmp)); port = data[0]; port.status = status
                before = deepcopy(port.state)
                result = self.execute(data)
                self.assertEqual(port.calls, ['install-global', 'install-revision', 'online', 'offline', 'restore-global'])
                self.assertEqual(port.state['policies']['global'], before['policies']['global'])
                self.assertFalse(port.state['owned']['properties']['isOnline'])
                self.assertFalse(result['task_complete'])
                self.assertEqual(result['later_Auto_chats_remaining'], 2)

    def test_wrong_response_ETag_triggers_owned_cleanup_no_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp)); port = data[0]; port.response_etag_wrong = True
            with self.assertRaisesRegex(ValueError, 'response_readback_ETag'):
                self.execute(data)
            self.assertEqual(port.calls, ['install-global', 'restore-global'])
            self.assertFalse((data[1] / 'reserve-intent.json').exists())

    def test_timeout_unknown_success_reconciles_exact_target_no_resend(self):
        for applied in (False, True):
            with self.subTest(applied=applied), tempfile.TemporaryDirectory() as tmp:
                data = self.fixture(Path(tmp)); port = data[0]
                before = deepcopy(port.state)
                port.fail_stage = 'install-global'; port.apply_before_timeout = applied
                with self.assertRaises(TimeoutError):
                    self.execute(data)
                self.assertEqual(port.calls.count('install-global'), 1)
                self.assertEqual(port.state['policies']['global'], before['policies']['global'])
                self.assertFalse((data[1] / 'reserve-intent.json').exists())

    def test_online_timeout_unknown_success_still_offlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp)); port = data[0]
            port.fail_stage = 'online'; port.apply_before_timeout = True
            with self.assertRaises(TimeoutError):
                self.execute(data)
            self.assertEqual(port.calls[-2:], ['offline', 'restore-global'])
            self.assertFalse(port.state['owned']['properties']['isOnline'])

    def test_cleanup_after_expiry_does_not_use_launch_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp))
            def browser(binding, timeout):
                data[2][0] += timedelta(days=1)
                raise TimeoutError('MOCK browser timeout')
            with self.assertRaisesRegex(TimeoutError, 'browser timeout'):
                self.execute(data, browser)
            self.assertEqual(data[0].calls[-2:], ['offline', 'restore-global'])
            self.assertTrue(data[0].cleanup_flags[-1])

    def test_cleanup_failure_still_attempts_other_slot_and_retains_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp)); data[0].fail_stage = 'offline'
            with self.assertRaisesRegex(ValueError, 'cleanup_UNRESOLVED'):
                self.execute(data)
            self.assertEqual(data[0].calls[-2:], ['offline', 'restore-global'])
            self.assertEqual(data[0].calls.count('offline'), 1)
            self.assertTrue((data[1] / 'cleanup-RECONCILE.json').exists())

    def test_ownership_drift_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp))
            def browser(binding, timeout):
                data[0].state['owned']['properties']['apiRevisionDescription'] = 'FOREIGN'
                raise TimeoutError()
            with self.assertRaisesRegex(ValueError, 'cleanup_UNRESOLVED'):
                self.execute(data, browser)
            self.assertEqual(data[0].calls, ['install-global', 'install-revision', 'online', 'restore-global'])
            self.assertNotIn('offline', data[0].calls)

    def test_foreign_global_offlines_exact_owned_revision_ETag_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp))
            foreign = b'<policies><inbound><base/><set-header name="foreign" exists-action="delete"/></inbound></policies>'
            def browser(binding, timeout):
                data[0].state['policies']['global'] = foreign
                data[0].state['snapshot']['baseline']['apim']['global'] = p.render.sha(foreign)
                raise TimeoutError('original browser failure')
            with self.assertRaisesRegex(ValueError, 'cleanup_UNRESOLVED'):
                self.execute(data, browser)
            self.assertEqual(data[0].calls, ['install-global', 'install-revision', 'online', 'offline'])
            self.assertFalse(data[0].state['owned']['properties']['isOnline'])
            self.assertEqual(data[0].state['policies']['global'], foreign)
            intent = p.old.load(data[1] / 'offline-intent.json')
            self.assertEqual(intent['if_match'], '"api3"')
            self.assertEqual(intent['body_sha256'], p.render.sha(t.canonical({'properties': {'isOnline': False}})))
            self.assertEqual(p.old.load(data[1] / 'cleanup-RECONCILE.json')['unresolved'][0]['stage'], 'restore-global')

    def test_both_foreign_slots_aggregate_failures_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp))
            def browser(binding, timeout):
                data[0].state['policies']['global'] = b'<policies/>'
                data[0].state['owned']['properties']['apiRevisionDescription'] = 'FOREIGN'
                raise TimeoutError()
            with self.assertRaisesRegex(ValueError, 'cleanup_UNRESOLVED'):
                self.execute(data, browser)
            self.assertEqual(len(data[0].calls), 3)
            self.assertEqual([x['stage'] for x in p.old.load(data[1] / 'cleanup-RECONCILE.json')['unresolved']],
                ['offline', 'restore-global'])

    def test_global_ledger_blocks_second_package_and_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp))
            data[7].write_bytes(b'{')
            with self.assertRaises(FileExistsError):
                self.execute(data)
            self.assertEqual(data[0].calls, [])
            self.assertFalse((data[1] / 'parent-window-intent.json').exists())

    def test_inclusive22_positive_and_negative_launch(self):
        for seconds, allowed in ((8 * 60, True), (8 * 60 + .001, False)):
            with self.subTest(seconds=seconds), tempfile.TemporaryDirectory() as tmp:
                data = self.fixture(Path(tmp))
                data[2][0] += timedelta(seconds=seconds)
                data[6]['issued_at'] = data[2][0].isoformat()
                if allowed:
                    self.execute(data)
                    self.assertEqual(len(data[0].calls), 5)
                else:
                    with self.assertRaisesRegex(ValueError, 'reserve22'):
                        self.execute(data)
                    self.assertFalse(data[7].exists())

    def test_browser_manifest_issued_time_system_history_IP_bound(self):
        changes = {'manifest_sha256': '0' * 64, 'system_empty': False, 'history_empty': False,
            'fixture': True, 'IP': '167.103.67.80', 'issued_at': (NOW - timedelta(seconds=30)).isoformat()}
        for key, value in changes.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                data = self.fixture(Path(tmp)); data[6][key] = value
                with self.assertRaises(ValueError):
                    self.execute(data)
                self.assertEqual(data[0].calls, [])
                self.assertFalse(data[7].exists())

    def test_tampered_package_stops_before_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.fixture(Path(tmp)); (data[1] / 'payloads.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'artifact_hash'):
                self.execute(data)
            self.assertFalse(data[7].exists())

    def test_every_protected_field_drift_rejected(self):
        before = baseline()
        for key in ('roles', 'inheritance', 'deployments', 'child', 'sources'):
            with self.subTest(key=key):
                changed = deepcopy(before); changed[key] = {}
                with self.assertRaises(ValueError):
                    p.guard_state(before, changed, before['policies']['global'], before['policies']['owned'], False)


class TransportTests(unittest.TestCase):
    def transport(self, status=200, etag='"actual"', error=None):
        class Credentials:
            def get(self, audience, cleanup=False):
                return 'MOCK_TOKEN_NOT_REAL', {}
        class Response:
            headers = {'ETag': etag}
            def __init__(self, url): self.url, self.status = url, status
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def geturl(self): return self.url
        class HTTP:
            def __init__(self): self.requests = []
            def open(self, request, timeout):
                self.requests.append((request, timeout))
                if error: raise error
                return Response(request.full_url)
        value = object.__new__(t.Transport)
        value.credentials, value.http = Credentials(), HTTP()
        return value

    def test_real_wire_policy_PUT_and_API_PATCH_200_201(self):
        for status in (200, 201):
            value = self.transport(status)
            for stage in ('install-global', 'install-revision', 'online', 'offline', 'restore-global'):
                body = t.canonical({'properties': {'isOnline': stage == 'online'}}) if stage in ('online', 'offline') else t.canonical(
                    {'properties': {'format': 'xml', 'value': '<policies/>'}})
                result = value.send(stage, body, '"old"', 45, stage in ('offline', 'restore-global'))
                request = value.http.requests[-1][0]
                self.assertEqual(request.get_method(), 'PATCH' if stage in ('online', 'offline') else 'PUT')
                self.assertEqual(request.get_header('If-match'), '"old"')
                self.assertEqual(request.data, body)
                self.assertEqual(result, {'http_status': status, 'etag': '"actual"'})

    def test_wrong_status_weak_ETag_timeout_never_retried(self):
        for status, etag, error in ((202, '"x"', None), (200, 'W/"weak"', None), (200, '"x"', TimeoutError())):
            value = self.transport(status, etag, error)
            with self.assertRaises((ValueError, TimeoutError)):
                value.send('online', t.canonical({'properties': {'isOnline': True}}), '"old"', 45)
            self.assertEqual(len(value.http.requests), 1)

    def test_auth_cleanup_refresh_before_wire_not_mutation_retry(self):
        value = t.Credentials()
        value.tokens[audience := t.a.ARM] = ('old', {'exp': 1})
        with self.assertRaisesRegex(ValueError, 'launch_token_expiring'):
            value.get(audience)
        import base64
        claims = {'tid': t.a.TENANT, 'oid': t.a.OPERATOR, 'aud': audience, 'exp': 9999999999}
        part = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
        with patch.object(t.subprocess, 'run') as command:
            command.return_value.returncode = 0
            command.return_value.stdout = json.dumps({'access_token': 'x.' + part + '.x'}).encode()
            self.assertEqual(value.get(audience, cleanup=True)[1], claims)
            self.assertEqual(command.call_count, 1)

    def test_manual_parent_review_and_tampered_DLL_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / 'mock-review.json'; compiler = root / 'mock-build.json'
            dll = root / 'Resume06Native.dll'; csc = root / 'csc.dll'
            dll.write_bytes(b'MOCK_NOT_EXECUTABLE'); csc.write_bytes(b'MOCK_COMPILER')
            source = Path(review.__file__).with_name('auto_resume06_native.cs')
            expected = {'sources': {'scripts/deployment/auto_resume06_native.cs': review.sha(source.read_bytes())}}
            compiler.write_bytes(t.canonical({'schema': 1, 'inputs': {str(source): review.sha(source.read_bytes()),
                str(csc): review.sha(csc.read_bytes())}, 'outputs': {str(dll): review.sha(dll.read_bytes())},
                'compile_exit': 0, 'semantic_exit': 0, 'expressions': 225}))
            build_pin = review.sha(compiler.read_bytes())
            payload = {'schema': 1, 'reviewer': 'MOCK_INDEPENDENT', 'kind': 'nativeSourceReview', 'decision': 'APPROVED',
                'binding': expected, 'issued_at': NOW.isoformat(), 'expires_at': (NOW + timedelta(hours=1)).isoformat(),
                'compiler_receipt_sha256': build_pin, 'evidence': ['MOCK_TOOL_HANDLE_NOT_APPROVAL']}
            path.write_bytes(t.canonical(payload))
            capability = review.TrustedReview(path, review.sha(path.read_bytes()), 'MOCK_INDEPENDENT',
                frozenset({'MOCK_INDEPENDENT'}), compiler, build_pin)
            self.assertEqual(capability('nativeSourceReview', expected, NOW), payload)
            with self.assertRaisesRegex(ValueError, 'review_binding'):
                capability('nativeSourceReview', {}, NOW)
            dll.write_bytes(b'ARBITRARY_DLL_PRINTING_VERIFIED')
            with self.assertRaisesRegex(ValueError, 'DLL_hash_drift'):
                capability('nativeSourceReview', expected, NOW)
            path.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'pinned_review_hash'):
                capability('nativeSourceReview', expected, NOW)
            with self.assertRaisesRegex(ValueError, 'identity_allowlist'):
                review.TrustedReview(path, '0' * 64, 'attacker', frozenset({'INDEPENDENT'}), compiler, build_pin)


class BrowserTrustTests(unittest.TestCase):
    def fixture(self, transform=lambda x: x, inspection=True):
        seen = []
        def invoke(phase, binding, timeout):
            value = {'channel': binding['channel'], 'dom': deepcopy(review.DOM),
                'server_correlation': 'MOCK_SERVER_ID'}
            seen.append(deepcopy(value))
            return transform(value)
        def inspect(page_id, request_id, timeout):
            assert 0 < timeout <= 30
            return {'tool_result_handle': 'MOCK_NATIVE_TOOL_HANDLE' if inspection else '',
                'request_id': request_id, 'page_id': page_id, 'page_url': review.ORIGIN + '/playground',
                'dom': deepcopy(review.DOM), 'server_correlation': 'MOCK_SERVER_ID',
                'completion_request_count': 0, 'scoring_request_count': 1}
        cap = review.ParentBrowser(invoke, inspect, 'p' * 36, review.ORIGIN + '/playground', 'a' * 64)
        return cap, seen, {'manifest_sha256': 'b' * 64, 'browser_source_sha256': 'a' * 64}

    def test_real_capability_nonce_bound_single_attempt_not_persisted(self):
        cap, seen, binding = self.fixture()
        value = cap.observe(binding)
        result = cap.score({**binding, **value}, 30)
        self.assertNotIn('channel', result)
        self.assertEqual(len(seen[0]['channel']['capability']), 64)
        self.assertNotEqual(seen[0]['channel']['capability'], seen[1]['channel']['capability'])
        with self.assertRaisesRegex(ValueError, 'preflight_handle'):
            cap.score({**binding, **value}, 30)
        self.assertEqual(len(seen), 2)

    def test_forged_nonce_wrong_origin_replay_rejected(self):
        for field in ('capability', 'origin', 'request_id', 'manifest_sha256', 'page_url', 'issued_at'):
            def forge(value):
                value['channel'] = {**value['channel'], field: 'FORGED'}
                return value
            cap, _, binding = self.fixture(forge)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'capability_origin'):
                cap.observe(binding)
        cap, seen, binding = self.fixture()
        value = cap.observe(binding)
        cap.invoke = lambda *_: seen[0]
        with self.assertRaisesRegex(ValueError, 'capability_origin'):
            cap.score({**binding, **value}, 30)
        self.assertTrue(cap.used)

    def test_claimed_DOM_without_independent_handle_and_unknown_origin_rejected(self):
        cap, _, binding = self.fixture(inspection=False)
        with self.assertRaisesRegex(ValueError, 'independent_DOM'):
            cap.observe(binding)
        with self.assertRaisesRegex(ValueError, 'actual_parent_browser'):
            review.ParentBrowser(lambda *_: {}, lambda *_: {}, 'p', 'https://evil.invalid/playground', 'a' * 64)


if __name__ == '__main__':
    unittest.main()