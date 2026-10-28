"""No cloud operations: exact reconciliation, adoption and replay boundaries."""
from copy import deepcopy
from datetime import UTC, datetime
import json
from types import SimpleNamespace
import zipfile

import pytest

from scripts.deployment import fireworks_gateway_stage as stage
from scripts.deployment import fireworks_release as release
from scripts.deployment.apim_route_repair import APIM


def backend():
    return {'id': APIM + '/backends/aiflux-project-fireworks', 'name': 'aiflux-project-fireworks',
            'properties': {'url': release.URL, 'protocol': 'http',
                           'tls': {'validateCertificateChain': True, 'validateCertificateName': True}}}


def collections():
    old = {'count': 1, 'value': [{'name': 'old', 'properties': {'url': 'https://old.invalid'}}], 'nextLink': None}
    new = deepcopy(old)
    new['count'] = 2
    new['value'].append(backend())
    return old, new


def test_derived_count_exact_increment_and_inputs_not_mutated():
    old, new = collections()
    preserved = deepcopy((old, new))
    assert stage.check_backend_delta(old, new) == backend()
    assert (old, new) == preserved


@pytest.mark.parametrize('defect', ['old_value', 'count', 'count_type', 'missing_count', 'nextLink',
                                  'url', 'protocol', 'tls', 'id', 'duplicate', 'credentials', 'proxy',
                                  'circuitBreaker', 'pool', 'metadata'])
def test_backend_delta_rejects_every_unapproved_change(defect):
    old, new = collections()
    if defect == 'old_value':
        new['value'][0]['properties']['url'] = 'https://changed.invalid'
    elif defect == 'count':
        new['count'] = 3
    elif defect == 'count_type':
        new['count'] = '2'
    elif defect == 'missing_count':
        new.pop('count')
    elif defect == 'nextLink':
        new['nextLink'] = 'https://more.invalid'
    elif defect in ('url', 'protocol', 'tls'):
        new['value'][-1]['properties'][defect] = 'invalid'
    elif defect == 'id':
        new['value'][-1]['id'] = APIM + '/backends/other'
    elif defect == 'duplicate':
        new['value'].append(backend())
        new['count'] += 1
    elif defect in ('credentials', 'proxy', 'circuitBreaker', 'pool'):
        new['value'][-1]['properties'][defect] = {'unexpected': True}
    else:
        new['extra'] = 'unapproved'
    with pytest.raises(RuntimeError):
        stage.check_backend_delta(old, new)


def test_count_absent_on_both_is_not_fabricated():
    old, new = collections()
    old.pop('count')
    new.pop('count')
    assert stage.check_backend_delta(old, new) == backend()


@pytest.mark.parametrize('marker', ['apply-intent.json', 'applied.json'])
def test_any_sibling_attempt_blocks_adoption_before_reads(tmp_path, monkeypatch, marker):
    monkeypatch.setattr(stage.rt, 'HOME', tmp_path)
    home = tmp_path / 'fireworks-models-20261028'
    sibling = tmp_path / 'fireworks-models-20261028-formatted'
    home.mkdir()
    sibling.mkdir()
    (sibling / marker).write_text('{}')
    with pytest.raises(RuntimeError, match='readonly_reconciliation'):
        stage.adopt(SimpleNamespace(), home)
    assert not (home / 'review.json').exists()
    assert (sibling / marker).read_text() == '{}'


def test_existing_review_cannot_be_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, 'attempted_directories', lambda: [])
    (tmp_path / 'plan-intent.json').write_text('{}')
    (tmp_path / 'review.json').write_text('preserve')
    with pytest.raises(RuntimeError, match='do_not_overwrite'):
        stage.require_unattempted(tmp_path)
    assert (tmp_path / 'review.json').read_text() == 'preserve'


@pytest.mark.parametrize('defect', [None, 'tf', 'lock', 'extra'])
def test_saved_archive_binds_exact_current_module_bytes(tmp_path, monkeypatch, defect):
    monkeypatch.setattr(stage.rt, 'ROOT', tmp_path)
    root = tmp_path / 'infra/project-route'
    root.mkdir(parents=True)
    (root / 'main.tf').write_bytes(b'variable "enabled" {}\n')
    (root / '.terraform.lock.hcl').write_bytes(b'locked')
    with zipfile.ZipFile(tmp_path / 'gateway.tfplan', 'w') as archive:
        archive.writestr('tfconfig/m-/main.tf', b'other' if defect == 'tf' else (root / 'main.tf').read_bytes())
        archive.writestr('.terraform.lock.hcl', b'other' if defect == 'lock' else b'locked')
        if defect == 'extra':
            archive.writestr('tfconfig/m-/foreign.tf', b'')
    if defect:
        with pytest.raises(RuntimeError):
            stage.bind_plan_sources(tmp_path)
    else:
        assert len(stage.bind_plan_sources(tmp_path)) == 2


@pytest.mark.parametrize('defect', [None, 'input', 'default', 'variable_set'])
def test_all_variables_bound_not_just_explicit_inputs(tmp_path, monkeypatch, defect):
    monkeypatch.setattr(stage.rt, 'ROOT', tmp_path)
    root = tmp_path / 'infra/project-route'
    root.mkdir(parents=True)
    (root / 'main.tf').write_text('variable "enabled" {}\nvariable "defaulted" {}\n')
    (tmp_path / 'inputs.tfvars.json').write_text(json.dumps({'enabled': defect != 'input'}))
    values = {'enabled': True, 'defaulted': 'expected'}
    plan = {'variables': {k: {'value': v} for k, v in values.items()}}
    if defect == 'variable_set':
        plan['variables'].pop('defaulted')
    rendered = {**values, 'defaulted': 'changed'} if defect == 'default' else values
    run = SimpleNamespace(terraform=lambda *a, **k: json.dumps(json.dumps(rendered)))
    if defect:
        with pytest.raises(RuntimeError):
            stage.bind_saved_inputs(run, tmp_path, plan)
    else:
        assert stage.bind_saved_inputs(run, tmp_path, plan) == stage.object_sha(values)


@pytest.fixture
def applied(tmp_path, monkeypatch):
    monkeypatch.setattr(stage.rt, 'ROOT', tmp_path)
    monkeypatch.setattr(stage, 'attempted_directories', lambda: [tmp_path])
    now = datetime.now(UTC).isoformat()
    review = {'plan_sha256': 'digest', 'sources': {'source': 'hash'}}
    proof = {**review, 'checks_passed': True, 'validated_at_utc': now, 'all_plan_checks_pass': True,
             'operator_actions': {'Microsoft.ApiManagement/service/' + suffix: True for suffix in
                                  ('backends/read', 'backends/write', 'apis/policies/read', 'apis/policies/write')}}
    for name, value in {'validation.json': proof, 'apply-intent.json': {'plan_sha256': 'digest', 'at_utc': now},
                        'applied.json': {'plan_sha256': 'digest', 'at_utc': now}}.items():
        (tmp_path / name).write_text(json.dumps(value))
    azure = tmp_path / '.azure'
    azure.mkdir()
    (azure / 'validate-status.json').write_text('{"completedStep":"UpdateStatus"}')
    (azure / 'deployment-plan.md').write_text('Fireworks gateway status: Validated digest ' + now)
    old, new = collections()
    (tmp_path / 'backends.json').write_text(json.dumps(old))
    baseline = {'apim': {'backends': stage.object_sha(old)}, 'settings': 'preserved'}
    (tmp_path / 'baseline.json').write_text(json.dumps(baseline))
    monkeypatch.setattr(release, 'FAILED_HOME', tmp_path)
    (tmp_path / 'gateway-stage-tests.xml').write_text('<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"/></testsuites>')
    run = SimpleNamespace(check=lambda live: (review, '<policies/>'), policy=lambda: '<policies/>',
                          arm=lambda suffix: new, metadata=lambda: {'active': True},
                          protected=lambda: {**baseline, 'apim': {'backends': stage.object_sha(new)}})
    return tmp_path, run


def test_independent_verification_authenticates_proofs_without_apply(applied):
    home, run = applied
    result = stage.verify_applied(run, home)
    assert result['gateway_stage'] == 'applied_verified'
    assert result['apply_attempts_this_subtask'] == 0
    assert result['catalog_promoted'] is False


@pytest.mark.parametrize('defect', ['validation', 'intent', 'workflow', 'baseline', 'policy', 'multiple', 'tests', 'operator'])
def test_readback_cannot_bypass_validation_or_protected_state(applied, monkeypatch, defect):
    home, run = applied
    if defect == 'validation':
        (home / 'validation.json').write_text('{"checks_passed":false}')
    elif defect == 'intent':
        (home / 'apply-intent.json').write_text('{"plan_sha256":"foreign"}')
    elif defect == 'workflow':
        (home / '.azure/validate-status.json').write_text('{"completedStep":"RunValidation"}')
    elif defect == 'baseline':
        (home / 'baseline.json').write_text('{}')
    elif defect == 'policy':
        run.policy = lambda: '<policies><inbound/></policies>'
    elif defect == 'tests':
        (home / 'gateway-stage-tests.xml').write_text('<testsuites><testsuite tests="1" failures="1"/></testsuites>')
    elif defect == 'operator':
        path = home / 'validation.json'
        proof = json.loads(path.read_text())
        proof['operator_actions'] = {}
        path.write_text(json.dumps(proof))
    else:
        monkeypatch.setattr(stage, 'attempted_directories', lambda: [home, home / 'another'])
    with pytest.raises(RuntimeError):
        stage.verify_applied(run, home)


@pytest.mark.parametrize('defect', [None, 'baseline', 'predecessor', 'backends', 'checks', 'guard'])
def test_adoption_captures_review_only_after_every_gate(tmp_path, monkeypatch, defect):
    home = tmp_path / 'fireworks-models-20261028'
    home.mkdir()
    monkeypatch.setattr(stage, 'attempted_directories', lambda: [])
    monkeypatch.setattr(stage, 'bind_plan_sources', lambda h: {'module': 'hash'})
    monkeypatch.setattr(stage, 'bind_saved_inputs', lambda *args: 'variableshash')
    monkeypatch.setattr(release, 'manifest_guard', lambda *args: None)
    monkeypatch.setattr(release, 'guard', lambda *args: stage.rt.require(defect != 'guard', 'guard_rejected'))
    for name, value in {'plan-intent.json': {}, 'baseline.json': {'baseline': True},
                        'backends.json': {'value': []}, 'inputs.tfvars.json': {}}.items():
        (home / name).write_text(json.dumps(value))
    (home / 'rollback-policy.xml').write_text('<policies/>')
    (home / 'gateway.tfplan').write_bytes(b'immutable')
    plan = {'checks': [{'status': 'fail' if defect == 'checks' else 'pass'}]}
    run = SimpleNamespace(protected=lambda: {} if defect == 'baseline' else {'baseline': True},
                          policy=lambda: '<policies><inbound/></policies>' if defect == 'predecessor' else '<policies/>',
                          arm=lambda suffix: {'value': ['unexpected']} if defect == 'backends' else {'value': []},
                          terraform=lambda *a, **k: 'default' if a[0] == 'workspace' else json.dumps(plan),
                          render=lambda path: '<policies/>', metadata=lambda: {'active': True}, sources=lambda: {})
    if defect:
        with pytest.raises(RuntimeError):
            stage.adopt(run, home)
        assert not (home / 'review.json').exists()
    else:
        # Sources must be workspace-relative; put the fixture under the actual
        # root synthetically by substituting only the pure path serialization.
        monkeypatch.setattr(stage.rt, 'ROOT', tmp_path)
        monkeypatch.setattr(stage, '__file__', str(tmp_path / 'verifier.py'))
        (tmp_path / 'verifier.py').write_text('synthetic verifier')
        monkeypatch.setattr(release, 'HOME', tmp_path / 'later')
        # Candidate manifest inputs are read before manifest_guard is called.
        candidate = tmp_path / 'candidate.json'
        candidate.write_text('{}')
        monkeypatch.setattr(release, 'MANIFEST', candidate)
        catalog = tmp_path / 'gateway/catalog'
        catalog.mkdir(parents=True)
        (catalog / 'project-routes.json').write_text('{}')
        review = stage.adopt(run, home)
        assert review['adopted_existing_plan'] is True
        assert review['independent_validation_required'] is True
        assert review['variables_sha256'] == 'variableshash'
        assert json.loads((home / 'review.json').read_text()) == review
    assert (home / 'gateway.tfplan').read_bytes() == b'immutable'