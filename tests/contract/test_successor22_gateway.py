"""Clean applied-context offline tests. No pending Auto files or tests copied."""
from datetime import UTC, datetime
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from scripts.deployment import restore22_successor as s

ROOT = s.rt.ROOT
HOME = ROOT / '.deployment' / ('r22t-' + datetime.now(UTC).strftime('%H%M%S%f'))


def historical():
    spec = importlib.util.spec_from_file_location('successor22_historical_contract', ROOT / 'tests/contract/test_foundry_eight_gateway.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    value.HOME = HOME
    return value


class Contracts(unittest.TestCase):
    summaries = []
    @classmethod
    def setUpClass(cls):
        HOME.mkdir(parents=True, exist_ok=False)
        cls.before = s.protected_sources()
        cls.old = historical()
        cls.route = HOME / 'context/infra/project-route'
        shutil.copytree(s.CONTEXT, HOME / 'context')
        tests = cls.route / 'tests'
        tests.mkdir()
        original = (ROOT / 'infra/project-route/tests/foundry-eight.tftest.hcl').read_text()
        # Test-only substitution matches actual APIM21 composition (Auto absent).
        (tests / 'foundry-eight.tftest.hcl').write_text(original.replace('local.auto_policy', 'local.glm_policy'), encoding='utf-8')
        successor = (ROOT / 'infra/project-route/tests/foundry-successor22.tftest.hcl').read_text()
        overrides = original[original.index('override_data {'):original.index('run "default_render')]
        (tests / 'foundry-successor22.tftest.hcl').write_text(successor.replace('run "explicit_successor', overrides + '\nrun "explicit_successor', 1), encoding='utf-8')
        cls.renders = {}
        cls.summaries = []
        for name in ('foundry-eight', 'foundry-successor22'):
            child = cls.old.run(name, [cls.old.TF, 'test', '-json', '-verbose', '-no-color', '-filter=tests\\' + name + '.tftest.hcl'], cwd=cls.route)
            events = [json.loads(line) for line in child.stdout.splitlines() if line.strip()]
            summaries = [v['test_summary'] for v in events if v.get('type') == 'test_summary']
            if len(summaries) != 1 or summaries[0]['passed'] < 1:
                raise AssertionError('No actual mocked Terraform tests selected: ' + name)
            cls.summaries += summaries
            for value in events:
                if value.get('type') == 'test_plan':
                    policy = value['test_plan'].get('output_changes', {}).get('candidate_policy', {}).get('after')
                    if policy:
                        cls.renders[value['@testrun']] = policy
            if child.returncode:
                raise AssertionError('Mock test failed; retained log ' + name)

    def test_exact_profiles_and_historical_tests(self):
        self.assertEqual(len(self.summaries), 2)
        self.assertTrue(all(v['failed'] == 0 and v['errored'] == 0 for v in self.summaries))
        candidate = (s.HOME / 'candidate-policy.xml').read_bytes().decode()
        self.assertEqual(self.renders['explicit_successor_exact22_old21_contracts'], candidate)
        self.assertTrue(s.policy_guard((s.HOME / 'current-policy.xml').read_bytes().decode(), candidate)['old21_preserved'])

    def test_actual_historical_77_csharp_fixtures(self):
        instance = self.old.GatewayOffline('test_06_actual_rendered_csharp_contracts')
        instance.renders = self.renders
        instance.test_06_actual_rendered_csharp_contracts()

    def test_ninth_actual_csharp_usage_and_shape(self):
        # Compile the actual successor expressions, not Python imitations.
        stage = HOME / 'ninth'
        stage.mkdir()
        self.old.HOME = stage
        try:
            policy = self.renders['explicit_successor_exact22_old21_contracts']
            harness = self.old.compile_csharp(policy)
            request = {'model': s.NINTH, 'max_completion_tokens': 128, 'stream': False,
                       'messages': [{'role': 'user', 'content': 'Synthetic fixture only.'}]}
            usage = {'prompt_tokens': 18, 'completion_tokens': 13, 'total_tokens': 31}
            cases = {'shape': {'_kind': 'shape', '_request': request},
                     'usage': {'_kind': 'usage', '_alias': s.NINTH, 'usage': usage},
                     'cached': {'_kind': 'usage', '_alias': s.NINTH, 'usage': usage | {'prompt_tokens_details': {'cached_tokens': 4, 'cache_write_tokens': 0}}}}
            for name, value in {'cap': request | {'max_completion_tokens': 1025}, 'stream': request | {'stream': True},
                                'foreign': request | {'model': 'MISTRAL-MEDIUM-3-5'}, 'speed': request | {'speed': 'fast'}}.items():
                cases[name] = {'_kind': 'shape', '_request': value}
            for value in (None, -1, True, '18', 0.5, 2**31):
                cases['bad-' + str(value)] = {'_kind': 'usage', '_alias': s.NINTH, 'usage': usage | {'prompt_tokens': value}}
            child = self.old.run('ninth-execution', [self.old.DOTNET, harness / 'Harness.dll'], stdin=json.dumps(cases))
            self.assertEqual(child.returncode, 0)
            actual = json.loads(child.stdout)
            self.assertEqual(actual['shape'], {'rejected': False})
            self.assertEqual(actual['usage']['model'], s.NINTH)
            self.assertEqual(actual['usage']['input_tokens'], 18)
            self.assertEqual(actual['usage']['output_tokens'], 13)
            self.assertIsNone(actual['usage']['cached_input_tokens'])
            self.assertIsNone(actual['usage']['cache_write_tokens'])
            self.assertEqual(actual['cached']['cached_input_tokens'], 4)
            for name in ('cap', 'stream', 'foreign', 'speed'):
                self.assertEqual(actual[name], {'rejected': True})
            for name in cases:
                if name.startswith('bad-'):
                    self.assertIsNone(actual[name]['input_tokens'])
            self.old.save('fixtures.json', cases)
            self.old.save('actual.json', actual)
            self.old.save('summary.json', {'fixtures': len(cases), 'all_assertions_passed': True,
                'missing_cache_remains_unknown': True, 'actual_rendered_CSharp': True})
        finally:
            self.old.HOME = HOME

    def test_guard_rejects_nonadditive_changes(self):
        previous = (s.HOME / 'current-policy.xml').read_bytes().decode()
        desired = (s.HOME / 'candidate-policy.xml').read_bytes().decode()
        for altered in (desired.replace('calls="60"', 'calls="59"'), desired.replace('timeout="45"', 'timeout="46"'),
                        desired.replace('backend-id="aiflux-project-foundry-eight-mistral"', 'backend-id="foreign"'),
                        desired.replace('resource="https://cognitiveservices.azure.com/"', 'resource="https://ai.azure.com"')):
            with self.assertRaises(RuntimeError):
                s.policy_guard(previous, altered)


def main():
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / 'unittest.txt').write_text(stream.getvalue(), encoding='utf-8')
    after = s.protected_sources()
    report = {'at': s.now(), 'passed': result.wasSuccessful() and after == Contracts.before,
        'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'protected_unchanged': after == Contracts.before, 'terraform_summaries': Contracts.summaries,
        'source_sha256': s.source_hashes(), 'context': s.context_hashes(), 'Auto_prepared_or_tested': False,
        'cloud_calls': 0, 'applies': 0, 'inference': 0}
    (HOME / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(stream.getvalue(), flush=True)
    print('RESULT=' + str(HOME / 'result.json'), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())