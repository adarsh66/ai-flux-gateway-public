"""One exclusive, curated, no-push frontend validation; never a release launcher."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.deployment/decision1-visibility01/frontend-validation01'
DOCKER = 'infra/image-build/Decision1FrontendValidation.Dockerfile'
SUB = 'aa28274d-fea0-46d4-b9c8-30f3ef0a0e52'
TENANT = 'beb276ac-6e9f-498e-8e31-019ee666decd'
REGISTRY = 'pocidstokenexacr'
RG = 'IDS-TOKEN-EXCHANGE-POC'
PYTHON = Path('C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe')
CA = Path('C:/Users/p4032099/.azure/ca-bundle-zscaler.pem')
CLI = [str(PYTHON), '-X', 'utf8', '-IBm', 'azure.cli']


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, value):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def clean(text):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', text)
    return re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~-]+', r'\1[redacted]', text)


def env():
    assert CA.is_file(), 'corporate_ca_missing'
    assert os.environ.get('AZURE_CLI_DISABLE_CONNECTION_VERIFICATION', '').lower() not in {'1', 'true', 'yes'}
    return {**os.environ, 'REQUESTS_CA_BUNDLE': str(CA), 'SSL_CERT_FILE': str(CA),
            'AZURE_CORE_COLLECT_TELEMETRY': '0', 'AZURE_CORE_NO_COLOR': '1'}


def azure(args, label):
    proc = subprocess.run(CLI + args + ['--only-show-errors', '--output', 'json'],
                          env=env(), cwd=ROOT, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=240, check=False)
    (OUT / (label + '.log')).write_text(clean(proc.stdout + proc.stderr), encoding='utf-8')
    assert proc.returncode == 0, f'{label}_failed: {clean(proc.stderr)[-2000:]}'
    return json.loads(proc.stdout)


def constraints():
    expected = {
        'apps/admin-portal': {'build': 'tsc --noEmit -p tsconfig.json && vite build', 'typecheck': 'tsc --noEmit -p tsconfig.json'},
        'apps/customer-portal': {'build': 'tsc --noEmit -p tsconfig.json && vite build', 'typecheck': 'tsc --noEmit -p tsconfig.json'},
        'packages/ui': {'typecheck': 'tsc --noEmit -p tsconfig.json'},
    }
    for folder, scripts in expected.items():
        package = json.loads((ROOT / folder / 'package.json').read_text())
        assert all(package['scripts'].get(k) == v for k, v in scripts.items()), 'build_script_changed'
        assert not any(k in package['scripts'] for k in ('preinstall', 'install', 'postinstall', 'prebuild', 'postbuild', 'pretypecheck', 'posttypecheck'))
    scripts = json.loads((ROOT / 'package.json').read_text())['scripts']
    assert scripts['test'] == 'vitest run'
    assert scripts['typecheck'] == 'npm run typecheck --workspaces --if-present'
    assert not any(k in scripts for k in ('preinstall', 'install', 'postinstall', 'pretest', 'posttest', 'pretypecheck', 'posttypecheck'))


def prepare():
    if OUT.exists():
        assert {p.name for p in OUT.iterdir()} == {'started.json', 'prepare-failure.json'}, 'preparation_not_pristine'
        assert not (OUT / 'context').exists(), 'context_exists'
        save('prepare-continuation.json', {'at': now(), 'pid': os.getpid(), 'reason': 'allow bundled source font assets; no cloud attempt exists'})
    else:
        OUT.mkdir(parents=True, exist_ok=False)
        save('started.json', {'at': now(), 'pid': os.getpid(), 'max_cloud_runs': 1,
                              'no_push': True, 'deployed': False})
    constraints()
    paths = [ROOT / p for p in ('package.json', 'package-lock.json', 'tsconfig.base.json', 'vitest.config.ts', DOCKER)]
    for folder in ('apps/admin-portal', 'apps/customer-portal', 'packages/ui'):
        base = ROOT / folder
        for path in base.rglob('*'):
            parts = path.relative_to(base).parts
            if any(p.startswith('.') or p in {'node_modules', 'dist', 'build'} for p in parts):
                continue
            if path.is_file() and (parts[0] == 'src' or path.name in {'package.json', 'tsconfig.json', 'vite.config.ts', 'index.html'}):
                assert path.suffix.lower() in {'.ts', '.tsx', '.css', '.json', '.html', '.svg', '.woff2'}, f'unexpected_source:{path}'
                paths.append(path)
    entries = []
    for path in sorted(set(paths)):
        assert not any(p.is_symlink() for p in (path, *path.parents)), 'symlink'
        assert path.resolve().is_relative_to(ROOT.resolve()), 'outside_root'
        raw = path.read_bytes()
        assert not re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AccountKey=[A-Za-z0-9+/]{20}|SharedAccessSignature=', raw), 'secret_pattern'
        relative = path.relative_to(ROOT).as_posix()
        target = OUT / 'context' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
        entries.append({'path': relative, 'sha256': digest(raw)})
    assert any(e['path'].endswith('DecisionScoringUsage.test.tsx') for e in entries)
    if OUT.name in {'frontend-validation02', 'frontend-validation03', 'frontend-validation04'}:
        prior = ROOT / '.deployment/decision1-visibility01/frontend-validation01'
        original = json.loads((prior / 'sources.json').read_text())['entries']
        assert len(entries) == 80 and {e['path'] for e in entries} == {e['path'] for e in original}, 'same80files_required'
        predecessors = [prior]
        if OUT.name in {'frontend-validation03', 'frontend-validation04'}:
            predecessors.append(prior.parent / 'frontend-validation02')
        if OUT.name == 'frontend-validation04':
            predecessors.append(prior.parent / 'frontend-validation03')
        save('predecessor-artifacts.json', {'run_id': 'cm4h', 'entries': [
            {'path': p.relative_to(ROOT).as_posix(), 'sha256': digest(p.read_bytes())}
            for predecessor in predecessors for p in sorted(predecessor.rglob('*')) if p.is_file()]})
        if OUT.name in {'frontend-validation03', 'frontend-validation04'}:
            previous = json.loads((predecessors[-1] / 'sources.json').read_text())['entries']
            old_hashes = {e['path']: e['sha256'] for e in previous}
            save('source-changes.json', {'entries': [e for e in entries if e['sha256'] != old_hashes[e['path']]]})
    save('sources.json', {'entries': entries, 'source_sha256': digest(json.dumps(entries, sort_keys=True).encode()),
                         'constraints': 'explicit manifests/config, frontend src and index.html only; no env/public/cloud config'})
    save('launcher-sources.json', {str(Path(__file__).relative_to(ROOT)): digest(Path(__file__).read_bytes())})
    node = shutil.which('node')
    assert node, 'node_missing'
    results = {}
    for folder in ('apps/admin-portal', 'apps/customer-portal', 'packages/ui'):
        proc = subprocess.run([node, str(ROOT / 'node_modules/typescript/bin/tsc'), '--noEmit', '-p', str(ROOT / folder / 'tsconfig.json')],
                              cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180, check=False)
        label = folder.replace('/', '-')
        (OUT / (label + '-typecheck.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
        results[folder] = proc.returncode
    save('local-typecheck.json', {'at': now(), 'command': 'node node_modules/typescript/bin/tsc --noEmit -p <workspace>/tsconfig.json', 'exit_codes': results})
    print(json.dumps({'prepared': str(OUT), 'sources': len(entries), 'local_typecheck': results}), flush=True)


def unchanged():
    manifest = json.loads((OUT / 'sources.json').read_text())
    return all(digest((base / e['path']).read_bytes()) == e['sha256']
               for base in (ROOT, OUT / 'context') for e in manifest['entries'])


def cloud():
    assert not (OUT / 'cloud-intent.json').exists(), 'intent_exists_DO_NOT_REPLAY'
    assert unchanged(), 'sources_changed'
    account = azure(['account', 'show'], 'account')
    assert account['id'] == SUB and account['tenantId'] == TENANT and account['state'] == 'Enabled', 'account_scope'
    registry = azure(['acr', 'show', '--name', REGISTRY, '--subscription', SUB], 'registry')
    expected = f'/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.ContainerRegistry/registries/{REGISTRY}'
    assert registry['id'].lower() == expected.lower() and not registry['adminUserEnabled'], 'registry_scope_security'
    args = ['acr', 'build', '--registry', REGISTRY, '--subscription', SUB, '--platform', 'linux/amd64',
            '--timeout', '1800', '--no-push', '--no-wait', '--file', DOCKER, '.']
    save('cloud-intent.json', {'at': now(), 'args': args, 'cwd': 'context', 'no_push': True,
                              'source_sha256': json.loads((OUT / 'sources.json').read_text())['source_sha256'],
                              'max_runs': 1, 'no_deployment': True})
    proc = subprocess.run(CLI + args + ['--output', 'json', '--only-show-errors'], env=env(), cwd=OUT / 'context',
                          capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600, check=False)
    (OUT / 'submission.log').write_text(clean(proc.stdout + proc.stderr), encoding='utf-8')
    save('submission-result.json', {'at': now(), 'exit_code': proc.returncode})
    assert proc.returncode == 0, 'submission_ambiguous_DO_NOT_REPLAY'
    run = json.loads(proc.stdout)
    run_id = run.get('runId') or run.get('name')
    assert run_id and re.fullmatch('[a-z0-9]+', run_id), 'run_id_missing_DO_NOT_REPLAY'
    save('run.json', {'run_id': run_id, 'at': now(), 'submission': run})
    print('ORIGINAL_RUN_ID=' + run_id, flush=True)
    reconcile()


def reconcile():
    run_id = json.loads((OUT / 'run.json').read_text())['run_id']
    # This one stream attaches to the ORIGINAL run; it never queues a build.
    with (OUT / 'validation.log').open('x', encoding='utf-8') as stream:
        proc = subprocess.Popen(CLI + ['acr', 'task', 'logs', '--registry', REGISTRY, '--subscription', SUB, '--run-id', run_id],
                                env=env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding='utf-8', errors='replace')
        for line in proc.stdout:
            stream.write(clean(line))
            stream.flush()
        code = proc.wait(timeout=60)
    run = azure(['acr', 'task', 'show-run', '--registry', REGISTRY, '--subscription', SUB, '--run-id', run_id], 'original-run-status')
    text = (OUT / 'validation.log').read_text(encoding='utf-8')
    markers = {key: bool(re.search(rf'^D1_{key}_EXIT=0\s*$', text, re.M)) for key in ('TYPECHECK', 'TEST', 'ADMIN_BUILD', 'CUSTOMER_BUILD')}
    summaries = {key: re.findall(pattern, text) for key, pattern in {
        'tests': r'Tests\s+[^\r\n]+', 'test_files': r'Test Files\s+[^\r\n]+'}.items()}
    counts = {}
    for key, lines in summaries.items():
        summary = lines[-1] if lines else ''
        counts[key] = {state: int(match.group(1)) if (match := re.search(rf'(\d+)\s+{state}\b', summary)) else 0
                       for state in ('passed', 'failed', 'skipped', 'todo')}
        total = re.search(r'\((\d+)\)', summary)
        counts[key]['total'] = int(total.group(1)) if total else None
    predecessor_unchanged = None
    if (OUT / 'predecessor-artifacts.json').exists():
        predecessor_unchanged = all(digest((ROOT / e['path']).read_bytes()) == e['sha256']
                                    for e in json.loads((OUT / 'predecessor-artifacts.json').read_text())['entries'])
    images = run.get('outputImages')
    no_images = images is None or isinstance(images, list) and all(i is None for i in images)
    result = {'at': now(), 'run_id': run_id, 'status': run['status'], 'outputImages': images,
              'finishTime': run.get('finishTime'), 'logs_exit_code': code, 'proof_markers': markers,
              'summaries': summaries, 'counts': counts, 'predecessor_artifacts_unchanged': predecessor_unchanged,
              'sources_unchanged': unchanged(), 'validation_log_sha256': digest(text.encode()),
              'source_sha256': json.loads((OUT / 'sources.json').read_text())['source_sha256'],
              'passed': run['status'] == 'Succeeded' and no_images and all(markers.values()) and unchanged()
                        and predecessor_unchanged is not False and code == 0
                        and counts['tests'] == {'passed': 233, 'failed': 0, 'skipped': 0, 'todo': 0, 'total': 233}
                        and counts['test_files'] == {'passed': 22, 'failed': 0, 'skipped': 0, 'todo': 0, 'total': 22},
              'deployed': False, 'no_push': True}
    save('result.json', result)
    if OUT.name in {'frontend-validation02', 'frontend-validation03', 'frontend-validation04'}:
        save('completion.json', {**result, 'all233_tests_passed': counts['tests']['passed'] == 233 and counts['tests']['total'] == 233,
                                 'typecheck_workspaces': 3, 'portal_builds': 2,
                                 'production_deployment_approved': False})
    print(json.dumps(result, indent=2), flush=True)


def discover():
    """One read-only reconciliation of an ambiguous --no-wait response."""
    intent = json.loads((OUT / 'cloud-intent.json').read_text())
    assert not (OUT / 'run.json').exists(), 'original_already_bound'
    runs = azure(['acr', 'task', 'list-runs', '--registry', REGISTRY, '--subscription', SUB, '--top', '10'], 'original-run-discovery')
    candidates = [r for r in runs if r.get('createTime', '') >= intent['at']
                  and r.get('runType') == 'QuickRun'
                  and (r.get('sourceTrigger') or {}).get('sourceRepository') is None]
    save('discovery-summary.json', {'at': now(), 'candidates': candidates})
    print(json.dumps(candidates, indent=2), flush=True)


def bind_original():
    intent = json.loads((OUT / 'cloud-intent.json').read_text())
    runs = json.loads((OUT / 'original-run-discovery.log').read_text())
    candidates = [r for r in runs if r.get('createTime', '') >= intent['at']
                  and r.get('runType') == 'QuickRun' and r.get('task') is None
                  and r.get('platform', {}).get('os') == 'linux'
                  and r.get('outputImages') is None]
    assert len(candidates) == 1, 'ambiguous_original_run_DO_NOT_REPLAY'
    run = candidates[0]
    save('run.json', {'at': now(), 'run_id': run['runId'], 'binding': 'sole QuickRun after exclusive intent; retained list metadata', 'submission': run})
    print('ORIGINAL_RUN_ID=' + run['runId'], flush=True)
    reconcile()


def post_completion_local():
    """Retain post-run selector correction evidence without any Azure calls."""
    completion = json.loads((OUT / 'completion.json').read_text())
    entries = json.loads((OUT / 'sources.json').read_text())['entries']
    changed = [e['path'] for e in entries if digest((ROOT / e['path']).read_bytes()) != e['sha256']]
    assert changed == ['packages/ui/src/components.test.tsx'], 'unexpected_postrun_change'
    node = shutil.which('node')
    assert node, 'node_missing'
    proc = subprocess.run([node, str(ROOT / 'node_modules/typescript/bin/tsc'), '--noEmit', '-p', str(ROOT / 'packages/ui/tsconfig.json')],
                          cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180, check=False)
    with (OUT / 'post-run-ui-typecheck.log').open('x', encoding='utf-8') as stream:
        stream.write(proc.stdout + proc.stderr)
    predecessor = json.loads((OUT / 'predecessor-artifacts.json').read_text())['entries']
    evidence = {'at': now(), 'run_id': completion['run_id'], 'cloud_submissions': 1,
                'submitted_source_sha256': completion['source_sha256'],
                'submitted_context_unchanged': all(digest((OUT / 'context' / e['path']).read_bytes()) == e['sha256'] for e in entries),
                'predecessor_artifacts_unchanged': all(digest((ROOT / e['path']).read_bytes()) == e['sha256'] for e in predecessor),
                'changed_sources_after_run': [{'path': p, 'sha256': digest((ROOT / p).read_bytes())} for p in changed],
                'post_run_ui_typecheck_exit': proc.returncode, 'corrected_selector_test_executed': False,
                'no_push': True, 'deployed': False, 'production_deployment_approved': False}
    save('post-run-local-evidence.json', evidence)
    print(json.dumps(evidence, indent=2), flush=True)


def final_local():
    """Check corrected test sources locally; never invokes Azure or native tooling."""
    results = {}
    node = shutil.which('node')
    assert node, 'node_missing'
    for folder in ('packages/ui', 'apps/admin-portal', 'apps/customer-portal'):
        proc = subprocess.run([node, str(ROOT / 'node_modules/typescript/bin/tsc'), '--noEmit', '-p', str(ROOT / folder / 'tsconfig.json')],
                              cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180, check=False)
        (OUT / (folder.replace('/', '-') + '-corrected-typecheck.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
        results[folder] = proc.returncode
    entries = json.loads((OUT / 'sources.json').read_text())['entries']
    changed = [e['path'] for e in entries if digest((ROOT / e['path']).read_bytes()) != e['sha256']]
    retained = all(digest((OUT / 'context' / e['path']).read_bytes()) == e['sha256'] for e in entries)
    log = (OUT / 'validation.log').read_text(encoding='utf-8')
    failed = [line.strip() for line in log.splitlines() if line.startswith(' FAIL ')]
    result = {'at': now(), 'run_id': 'cm4h', 'status': 'Failed', 'tests_passed': 208, 'tests_failed': 25,
              'test_files_passed': 17, 'test_files_failed': 5, 'unhandled_errors': 24,
              'outputImages': None, 'submitted_context_hashes_unchanged': retained,
              'changed_sources_after_snapshot': changed, 'only_tests_changed': all('.test.' in p for p in changed),
              'corrected_source_local_typecheck': results, 'failed_tests': failed,
              'corrected_tests_executed': False, 'additional_cloud_runs': 0,
              'note': 'Original immutable snapshot failed; test-only fixes typechecked but require separately authorized Linux rerun.'}
    save('final-evidence.json', result)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'cloud', 'reconcile', 'discover', 'bind_original', 'final_local', 'post_completion_local'))
    parser.add_argument('--receipt', choices=('frontend-validation01', 'frontend-validation02', 'frontend-validation03', 'frontend-validation04'), default='frontend-validation01')
    parser.add_argument('--out', type=Path, help='Unique receipt path under .deployment/decision1-visibility01')
    options = parser.parse_args()
    receipt_root = ROOT / '.deployment/decision1-visibility01'
    OUT = options.out.resolve() if options.out else receipt_root / options.receipt
    assert OUT.parent == receipt_root.resolve() and OUT.name in {'frontend-validation01', 'frontend-validation02', 'frontend-validation03', 'frontend-validation04'}, 'invalid_receipt_path'
    assert options.action != 'final_local' or options.receipt == 'frontend-validation01', 'legacy_evidence_only'
    try:
        globals()[options.action]()
    except Exception as error:
        if OUT.is_dir():
            name = options.action + '-failure.json'
            if not (OUT / name).exists():
                save(name, {'at': now(), 'error': clean(str(error)), 'type': type(error).__name__, 'no_replay': True})
        raise