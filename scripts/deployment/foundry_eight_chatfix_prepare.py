"""Fresh API-only preparation. No apply, SQL, sync, inference or role/network writes."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from datetime import UTC, datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from scripts.deployment import foundry_eight_runtime_release as b

ROOT = b.ROOT
HOME = ROOT / '.deployment/foundry-eight-chatfix-20261031-r2'
OLD = b.HOME
API = 'services/control-plane/src/aiflux/'
MODULES = ('app.py', 'model_inventory_sync.py', 'display_pricing.py', 'rate_card.py', 'db.py')
PIN = 'f82fd47eb54f1e331ebf5ae7d9305d3238e78f50bd0d2a6c15b74216ba69b663'
require = b.require
sha = b.sha
load = b.load


def write(name, value):
    path = HOME / name
    require(path.resolve().is_relative_to(HOME.resolve()), 'owned_output_only')
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (value.encode() if isinstance(value, str) else
        (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
    with path.open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def replace_once(text, old, new):
    require(text.count(old) == 1, 'unique_reviewed_hunk:' + old[:60])
    return text.replace(old, new, 1)


def function(text, name):
    tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return ''.join(text.splitlines(True)[node.lineno-1:node.end_lineno])


def compose():
    require(not (HOME / 'composition.json').exists(), 'composition_already_exists')
    frozen = load(OLD / 'context-freeze.json')
    require(b.files(OLD / 'contexts/api') == frozen['api'], 'actual_cm3s_overlay_exact')
    native = OLD / 'contexts/api-native'
    # Native profile execution changed catalog output only. Bind source modules
    # independently against the original frozen file entries.
    for name in MODULES:
        if API + name in frozen['api-native']:
            require(sha((native / API / name).read_bytes()) == frozen['api-native'][API + name], 'frozen_native_module:' + name)
    write('intent.json', {'at': b.now(), 'pid': os.getpid(), 'scope': 'API_build_and_ONE_saved_plan_NOT_APPLY',
        'base_run': 'cm3s', 'base_digest': PIN, 'apply': 0, 'DB_sync': 0, 'inference': 0, 'Auto': 'HOLD'})
    shutil.copytree(OLD / 'contexts/api', HOME / 'context')
    # Tests start with clean cm3s native source + retained corrected fixtures.
    shutil.copytree(native, HOME / 'native', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    fixture = OLD / 'validation/api/validation'
    shutil.copytree(fixture, HOME / 'native', dirs_exist_ok=True)
    # Historical fixtures stay old13; the production context remains accepted21.
    transforms = {}
    for name in MODULES:
        old = (native / API / name).read_text()
        current = (ROOT / API / name).read_text()
        if name == 'app.py':
            new = replace_once(old,
                'def sync_model_deployments(principal: Admin, db: Db) -> dict:',
                'def sync_model_deployments(principal: Admin, db: Db, reconcile_router: bool = True) -> dict:')
            new = replace_once(new, 'return sync_verified_models(db, settings, principal)',
                'return sync_verified_models(db, settings, principal, reconcile_router=reconcile_router)')
        elif name == 'model_inventory_sync.py':
            new = replace_once(old, 'from aiflux.auth import Principal\n', 'from aiflux.auth import Principal\nfrom aiflux.catalog import Catalog\n')
            new = replace_once(new, function(old, 'sync_verified_models'), function(current, 'sync_verified_models'))
        elif name == 'display_pricing.py':
            new = old
            for name_ in ('estimate_expressions', 'estimate_summary', 'detail_estimates'):
                new = replace_once(new, function(old, name_), function(current, name_))
            new = replace_once(new, 'def estimate_expressions(', function(current, 'usage_scope') + '\n\n\ndef estimate_expressions(')
        elif name == 'rate_card.py':
            new = replace_once(old, function(old, 'estimate_args'), function(current, 'estimate_args'))
        else:
            new = replace_once(old, '        yield session', '        session.info["settings"] = settings  # Request-local provenance; no database read/write.\n        yield session')
        ast.parse(new)
        patch = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='cm3s/' + name, tofile='chatfix/' + name))
        write('hunks/' + name + '.patch', patch)
        transforms[name] = {'before': sha(old.encode()), 'after': sha(new.encode()), 'patch_sha256': sha(patch.encode())}
        # Delete only files in this new exclusively owned staging directory.
        for folder in ('context', 'native'):
            target = HOME / folder / API / name
            if target.exists():
                target.unlink()
            write(folder + '/' + API + name, new)
    docker = f'FROM {b.HOST}/aiflux-api@sha256:{PIN}\nWORKDIR /app\n'
    for name in MODULES:
        for dest in ('/app/' + API, '/usr/local/lib/python3.11/site-packages/aiflux/'):
            docker += f'COPY --chown=10001:10001 {API}{name} {dest}{name}\n'
    write('context/ChatFix.Dockerfile', docker)
    for name in ('test_foundry_eight_chatfix.py', 'test_foundry_eight_sync.py'):
        target = HOME / 'native/tests/unit' / name
        if target.exists():
            target.unlink()
        write('native/tests/unit/' + name, (ROOT / 'tests/unit' / name).read_bytes())
    write('composition.json', {'at': b.now(), 'actual_base_image': b.HOST + '/aiflux-api@sha256:' + PIN,
        'base_context_freeze_sha256': sha((OLD / 'context-freeze.json').read_bytes()), 'hunks': transforms,
        'context': b.files(HOME / 'context'), 'native': b.files(HOME / 'native'),
        'dirty_full_tree_copied': False, 'app_changes': 'existing_sync_handler_only'})
    print(json.dumps({'composed': True, 'home': str(HOME)}), flush=True)


def command(label, argv, cwd=None, env=None, timeout=1800):
    write('commands/' + label + '-intent.json', {'at': b.now(), 'pid': os.getpid(), 'argv': argv})
    child = subprocess.run(argv, cwd=cwd or ROOT, env=env or b.environment(), capture_output=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
    write('commands/' + label + '.stdout.txt', child.stdout)
    write('commands/' + label + '.stderr.txt', child.stderr)
    write('commands/' + label + '-result.json', {'at': b.now(), 'exit_code': child.returncode})
    print(child.stdout[-8000:], flush=True)
    require(child.returncode == 0, 'command_failed:' + label)
    return child.stdout


def tests(label):
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(HOME / 'native' / API).removesuffix('/aiflux/')}
    env['PYTHONPATH'] = str(HOME / 'native/services/control-plane/src')
    names = ('test_foundry_eight_chatfix.py', 'test_foundry_eight_sync.py', 'test_foundry_eight_pricing.py',
             'test_foundry_eight_catalog.py', 'test_rate_card.py', 'test_display_pricing.py',
             'test_usage_rankings.py', 'test_usage_filters.py', 'test_usage_series.py', 'test_finops_ingestion.py')
    command(label, [sys.executable, '-X', 'utf8', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        *['tests/unit/' + n for n in names], '--junitxml=' + str(HOME / (label + '.xml'))], cwd=HOME / 'native', env=env)


def correct_fixtures():
    # Historical tests deliberately synthesize the eight additions onto old13.
    # Their cwd is NOT the production context, which keeps accepted21 unchanged.
    require(not (HOME / 'fixture-correction.json').exists(), 'fixture_correction_once')
    shutil.copytree(OLD / 'validation/api/validation/gateway', HOME / 'native/gateway', dirs_exist_ok=True)
    for name in ('test_foundry_eight_chatfix.py', 'test_foundry_eight_sync.py'):
        target = HOME / 'native/tests/unit' / name
        target.unlink()
        write('native/tests/unit/' + name, (ROOT / 'tests/unit' / name).read_bytes())
    write('fixture-correction.json', {'at': b.now(), 'reason': 'historical_old13_test_cwd_not_accepted21_runtime',
        'context_unchanged': b.files(HOME / 'context') == load(HOME / 'composition.json')['context'],
        'native': b.files(HOME / 'native')})


def build():
    import xml.etree.ElementTree as ET
    root = ET.parse(HOME / 'focused-green.xml').getroot()
    require(not any(int(e.get('failures', 0)) or int(e.get('errors', 0)) for e in root.iter('testsuite')), 'focused_target_green')
    require(b.files(HOME / 'context') == load(HOME / 'composition.json')['context'], 'frozen_build_context')
    tag = 'approved8-chatfix-20261031'
    # Original CLI failed its LOCAL Dockerfile existence check before upload.
    # Preserve that receipt; this uniquely named correction fixes cwd only.
    require((HOME / 'commands/api-build-once.stderr.txt').read_text().strip() == "ERROR: Unable to find 'ChatFix.Dockerfile'.",
            'original_local_preupload_error_exact')
    write('local-path-correction.json', {'at': b.now(), 'original': 'api-build-once',
        'failure': 'local_Dockerfile_existence_check_before_upload_or_run_submission', 'original_cloud_builds': 0,
        'fix': 'cwd_is_frozen_context_and_context_argument_dot', 'new_exclusive_command': 'api-build-cwd-corrected-once'})
    raw = command('api-build-cwd-corrected-once', b.CLI + ['acr', 'build', '--registry', b.REGISTRY, '--subscription', b.SUB,
        '--platform', 'linux/amd64', '--timeout', '1800', '--image', 'aiflux-api:' + tag, '--file', 'ChatFix.Dockerfile',
        '--no-logs', '--only-show-errors', '-o', 'json', '.'], cwd=HOME / 'context')
    run = json.loads(raw)
    write('build-submission.json', run)
    require(run['status'] == 'Succeeded', 'api_build_not_succeeded_no_retry')
    outputs = run['outputImages']
    require(len(outputs) == 1 and outputs[0]['repository'] == 'aiflux-api' and outputs[0]['tag'] == tag, 'sole_api_output')
    digest = outputs[0]['digest']
    require(digest.startswith('sha256:') and len(digest) == 71, 'immutable_api_digest')
    write('build-result.json', {'at': b.now(), 'run_id': run['runId'], 'digest': digest,
        'image': b.HOST + '/aiflux-api@' + digest, 'context_sha256': sha((HOME / 'composition.json').read_bytes()),
        'status': run['status'], 'other_image_builds': 0, 'applies': 0})
    print(json.dumps(load(HOME / 'build-result.json')), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('compose', 'tests', 'build', 'correct-fixtures'))
    parser.add_argument('--label', default='focused-green')
    args = parser.parse_args()
    if args.action == 'compose':
        compose()
    elif args.action == 'tests':
        tests(args.label)
    elif args.action == 'correct-fixtures':
        correct_fixtures()
    else:
        build()


if __name__ == '__main__':
    main()