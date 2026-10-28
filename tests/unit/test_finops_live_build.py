"""Build-only scope and source binding, without Azure calls."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.deployment import finops_live_build as build


def test_current_source_binding_rejects_changed_component(monkeypatch):
    manifest = build.release.source_manifest()
    build.check_current(manifest)
    changed = deepcopy(manifest)
    changed["components"]["api"]["source_sha256"] = "0" * 64
    with pytest.raises(RuntimeError):
        build.check_current(changed)


def test_builder_has_no_application_or_database_write_path():
    text = Path(build.__file__).read_text()
    assert '"acr", "build"' in text and '"--platform", "linux/amd64"' in text
    assert 'for kind in components' in text
    assert 'submissions": 1' in text and 'submission_intent_at_utc' in text
    assert 'run.get("outputImages")' in text
    for forbidden in ('"apply"', '"appsettings"', '"webapp"', '"functionapp"', 'psycopg.connect', 'engine_for('):
        assert forbidden not in text


def test_ingestion_only_submits_one_native_build_without_other_contexts(tmp_path, monkeypatch):
    manifest = {'components': {}}
    for kind in build.release.COMPONENTS:
        path = tmp_path / (kind + '.txt')
        path.write_text(kind)
        entry = {'path': path.name, 'sha256': build.release.digest(path.read_bytes())}
        manifest['components'][kind] = {'entries': [entry], 'source_sha256': entry['sha256']}
    monkeypatch.setattr(build.rt, 'ROOT', tmp_path)
    monkeypatch.setattr(build.rt, 'HOME', tmp_path / '.deployment')
    monkeypatch.setattr(build.release, 'source_manifest', lambda: manifest)
    pin = 'sha256:' + 'b' * 64
    output = {'digest': pin, 'registry': build.release.REGISTRY, 'repository': 'aiflux-ingestion'}
    submissions = []

    def cli(args):
        if args == ['account', 'show']:
            return {'id': build.rt.SUB, 'tenantId': build.rt.TENANT}
        if args[:2] == ['acr', 'task']:
            tag = submissions[0][submissions[0].index('--image') + 1].split(':')[1]
            return {'status': 'Succeeded', 'platform': {'os': 'linux'},
                    'outputImages': [{**output, 'tag': tag}], 'startTime': 'start', 'finishTime': 'finish'}
        assert args[:2] == ['acr', 'manifest']
        return {'digest': pin}

    def submit(args, **kwargs):
        submissions.append(args)
        return SimpleNamespace(returncode=0, stdout='Run ID: test1', stderr='')

    monkeypatch.setattr(build.rt, 'cli', cli)
    monkeypatch.setattr(build.subprocess, 'run', submit)
    assert build.build(('ingestion',)) == 0
    assert len(submissions) == 1
    args = submissions[0]
    assert args[args.index('--platform') + 1] == 'linux/amd64'
    assert Path(args[args.index('--file') + 1]).as_posix().endswith('services/usage-ingestion/Dockerfile')
    assert args[args.index('--image') + 1].startswith('aiflux-ingestion:')
    context = Path(args[-1])
    assert {p.name for p in context.iterdir()} == {'ingestion.txt'}
    report = json.loads((context.parent / 'results.json').read_text())
    assert report['requested_components'] == ['ingestion']
    assert set(report['components']) == {'ingestion'}
    assert report['components']['ingestion']['image'].endswith('@' + pin)
    assert report['application_deployment'] is False
    assert report['settings_writes'] == report['database_writes'] == 0


def test_unsupported_partial_build_scope_rejected_before_cloud_calls(monkeypatch):
    monkeypatch.setattr(build.rt, 'cli', lambda *_: pytest.fail('unexpected cloud call'))
    with pytest.raises(RuntimeError, match='unsupported_build_scope'):
        build.build(('api',))