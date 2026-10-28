"""Adopt a never-applied saved plan, or independently reconcile an existing apply.

No plan generation, marker removal, inference, or automatic apply is permitted.
Keep the historical release controller byte-identical to its validation proof.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

from scripts.deployment import fireworks_release as release
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.finops_function_stage import sha as object_sha

RESULT = release.FAILED_HOME / 'gateway-stage-result.json'


def attempted_directories():
    return sorted(p for p in rt.HOME.glob('fireworks-models-20261028*')
                  if (p / 'apply-intent.json').exists() or (p / 'applied.json').exists())


def require_unattempted(home):
    rt.require(not attempted_directories(), 'existing_apply_requires_readonly_reconciliation')
    rt.require((home / 'plan-intent.json').is_file(), 'existing_plan_intent_required')
    rt.require(not (home / 'review.json').exists(), 'review_exists_do_not_overwrite')


def check_backend_delta(previous, current):
    """Only value += one exact backend and count += 1; retain all other fields."""
    rt.require(not previous.get('nextLink') and not current.get('nextLink'), 'backend_pagination')
    rt.require(not any(v['name'] == 'aiflux-project-fireworks' for v in previous['value']),
               'backend_predecessor_must_not_contain_target')
    added = [v for v in current['value'] if v['name'] == 'aiflux-project-fireworks']
    rt.require(len(added) == 1, 'one_new_backend_required')
    from scripts.deployment.apim_route_repair import APIM
    rt.require(added[0]['id'].lower() == (APIM + '/backends/aiflux-project-fireworks').lower(),
               'exact_backend_id')
    props = added[0]['properties']
    rt.require(props['url'] == release.URL and props['protocol'] == 'http'
               and props['tls'] == {'validateCertificateChain': True, 'validateCertificateName': True}
               and not props.get('credentials') and not props.get('proxy')
               and not props.get('circuitBreaker') and not props.get('pool'), 'exact_backend_readback')
    remaining = deepcopy(current)
    remaining['value'] = [v for v in remaining['value'] if v['name'] != 'aiflux-project-fireworks']
    # APIM returns a derived collection count. Verify it; never drop it blindly.
    rt.require(('count' in previous) == ('count' in current), 'backend_count_shape_changed')
    if 'count' in previous:
        rt.require(type(previous['count']) is int and type(current['count']) is int
                   and previous['count'] == len(previous['value'])
                   and current['count'] == len(current['value'])
                   and current['count'] == previous['count'] + 1, 'exact_backend_count_increment')
        remaining['count'] = previous['count']
    rt.require(remaining == previous, 'old_backends_or_collection_metadata_changed')
    return added[0]


def bind_saved_inputs(run, home, plan):
    """Bind every default-expanded variable and actual current rendering, not a subset."""
    inputs = json.loads((home / 'inputs.tfvars.json').read_text())
    values = {k: v['value'] for k, v in plan['variables'].items()}
    rt.require(all(k in values and values[k] == v for k, v in inputs.items()), 'saved_input_variable_drift')
    names = set()
    for path in (rt.ROOT / 'infra/project-route').glob('*.tf'):
        names.update(re.findall(r'(?m)^variable\s+"([^"]+)"\s*\{', path.read_text()))
    rt.require(names == set(values), 'full_variable_set_changed')
    expression = 'jsonencode({' + ','.join(k + '=var.' + k for k in sorted(names)) + '})\n'
    rendered = run.terraform('console', '-no-color', '-var-file=' + str(home / 'inputs.tfvars.json'), text=expression)
    current = json.loads(json.loads(rendered[rendered.find('"'):].strip()))
    rt.require(current == values, 'default_expanded_variables_changed')
    return object_sha(values)


def bind_plan_sources(home):
    """Saved-plan archive contains the exact Terraform module/lock snapshot."""
    root = rt.ROOT / 'infra/project-route'
    with zipfile.ZipFile(home / 'gateway.tfplan') as archive:
        names = {n for n in archive.namelist() if n.startswith('tfconfig/m-/')}
        expected = {'tfconfig/m-/' + p.name for p in root.glob('*.tf')}
        rt.require(names == expected, 'saved_module_file_set_changed')
        hashes = {}
        for path in [*root.glob('*.tf'), root / '.terraform.lock.hcl']:
            member = '.terraform.lock.hcl' if path.name == '.terraform.lock.hcl' else 'tfconfig/m-/' + path.name
            data = path.read_bytes()
            rt.require(archive.read(member) == data, 'saved_module_or_lock_bytes_changed:' + path.name)
            hashes[path.relative_to(rt.ROOT).as_posix()] = release.sha(data)
        return hashes


def adopt(run, home):
    """Capture a review only after fresh baseline/predecessor/guard checks.

    A nonzero planner exit is not itself adoptable evidence. The actual saved
    plan must pass every check, match all variables and the current exact render.
    Subsequent independent validation and the real workflow remain mandatory.
    """
    require_unattempted(home)
    digest = release.sha((home / 'gateway.tfplan').read_bytes())
    baseline = json.loads((home / 'baseline.json').read_text())
    rt.require(run.protected() == baseline, 'protected_baseline_drift')
    before = (home / 'rollback-policy.xml').read_bytes().decode('utf-8')
    rt.require(release.policy_structure(run.policy()) == release.policy_structure(before), 'live_predecessor_drift')
    rt.require(run.arm('/backends') == json.loads((home / 'backends.json').read_text()), 'backend_predecessor_drift')
    release.manifest_guard(json.loads(release.MANIFEST.read_text()),
                           json.loads((rt.ROOT / 'gateway/catalog/project-routes.json').read_text()))
    rt.require(run.terraform('workspace', 'show').strip() == 'default', 'workspace')
    plan = json.loads(run.terraform('show', '-json', str(home / 'gateway.tfplan')))
    rt.require(plan.get('checks') and all(c.get('status') == 'pass' for c in plan['checks']), 'all_checks_required')
    archived_sources = bind_plan_sources(home)
    variables_sha = bind_saved_inputs(run, home, plan)
    expected = run.render(home / 'inputs.tfvars.json')
    release.guard(plan, before, expected)
    run.metadata()
    require_unattempted(home)
    rt.require(digest == release.sha((home / 'gateway.tfplan').read_bytes()), 'plan_changed_during_adoption')
    sources = run.sources()
    # Do not accidentally bind the later directory's input profile.
    sources.pop((release.HOME / 'inputs.tfvars.json').relative_to(rt.ROOT).as_posix(), None)
    sources[(home / 'inputs.tfvars.json').relative_to(rt.ROOT).as_posix()] = release.sha((home / 'inputs.tfvars.json').read_bytes())
    sources[Path(__file__).relative_to(rt.ROOT).as_posix()] = release.sha(Path(__file__).read_bytes())
    review = {'at_utc': datetime.now(UTC).isoformat(), 'plan_sha256': digest, 'sources': sources,
              'archived_module_source_sha256': archived_sources,
              'baseline_sha256': object_sha(baseline), 'variables_sha256': variables_sha,
              'before_policy_sha256': release.sha(before), 'after_policy_sha256': release.sha(expected),
              'scope': {release.BACKEND: ['create'], release.POLICY: ['update']},
              'guard_verified': True, 'adopted_existing_plan': True,
              'independent_validation_required': True, 'cloud_writes': 0}
    with (home / 'review.json').open('x', encoding='utf-8') as handle:
        json.dump(review, handle, indent=2)
    return review


def verify_applied(run, home):
    """Authenticate existing proof then compare the independently read live state."""
    review, expected = run.check(live=False)
    digest = review['plan_sha256']
    proof = json.loads((home / 'validation.json').read_text())
    rt.require(proof.get('checks_passed') is True and proof['plan_sha256'] == digest
               and proof['sources'] == review['sources'], 'existing_exact_validation_required')
    rt.require(proof.get('all_plan_checks_pass') is True
               and all(proof.get('operator_actions', {}).get('Microsoft.ApiManagement/service/' + suffix) is True
                       for suffix in ('backends/read', 'backends/write', 'apis/policies/read', 'apis/policies/write')),
               'existing_plan_checks_and_operator_validation_required')
    intent, applied = [json.loads((home / name).read_text()) for name in ('apply-intent.json', 'applied.json')]
    rt.require(intent['plan_sha256'] == applied['plan_sha256'] == digest, 'matching_attempt_and_completion_required')
    rt.require(datetime.fromisoformat(proof['validated_at_utc']) <= datetime.fromisoformat(intent['at_utc'])
               <= datetime.fromisoformat(applied['at_utc']), 'validation_must_precede_apply')
    workflow = json.loads((rt.ROOT / '.azure/validate-status.json').read_text())
    doc = (rt.ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
    rt.require(workflow['completedStep'] == 'UpdateStatus' and 'Fireworks gateway status: Validated' in doc
               and digest in doc and proof['validated_at_utc'] in doc, 'existing_workflow_and_section7_required')
    rt.require(release.policy_structure(run.policy()) == release.policy_structure(expected), 'target_policy_readback')
    previous = json.loads((home / 'backends.json').read_text())
    current = run.arm('/backends')
    added = check_backend_delta(previous, current)
    protected = run.protected()
    rt.require(protected['apim']['backends'] == object_sha(current), 'backend_collection_race')
    protected['apim']['backends'] = object_sha(previous)
    rt.require(protected == json.loads((home / 'baseline.json').read_text()), 'protected_baseline_readback')
    run.metadata()
    rt.require(attempted_directories() == [home], 'multiple_attempts_require_reconciliation')
    tests_path = release.FAILED_HOME / 'gateway-stage-tests.xml'
    suites = list(ET.parse(tests_path).getroot().iter('testsuite'))
    count = sum(int(s.get('tests', '0')) for s in suites)
    rt.require(count > 0 and all(int(s.get(k, '0')) == 0 for s in suites
               for k in ('failures', 'errors', 'skipped')), 'actual_scoped_regression_tests_required')
    return {'at_utc': datetime.now(UTC).isoformat(), 'gateway_stage': 'applied_verified',
            'plan_sha256': digest, 'applied_at_utc': applied['at_utc'],
            'applied_directory': home.relative_to(rt.ROOT).as_posix(),
            'existing_validation_authenticated': True, 'existing_workflow_complete': True,
            'existing_validation_at_utc': proof['validated_at_utc'],
            'existing_validation_sha256': release.sha((home / 'validation.json').read_bytes()),
            'independent_verifier_sha256': release.sha(Path(__file__).read_bytes()),
            'focused_tests': count, 'test_report_sha256': release.sha(tests_path.read_bytes()),
            'policy_normalized_equal': True, 'new_backend_id': added['id'],
            'old_backend_values_exact': True, 'collection_count_exact_increment': 1,
            'protected_baseline_equal_except_new_backend': True,
            'recorded_apply_attempts': 1, 'apply_attempts_this_subtask': 0,
            'original_plan_apply_blocked': True, 'original_plan_block_reason': 'later_plan_already_applied',
            'runtime_images_unchanged': True, 'catalog_promoted': False,
            'cloud_writes_this_subtask': 0, 'rbac_writes': 0, 'network_writes': 0,
            'inference_requests_this_subtask': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['adopt', 'verify'])
    args = parser.parse_args()
    result = {'at_utc': datetime.now(UTC).isoformat(), 'gateway_stage': 'blocked',
              'apply_attempts_this_subtask': 0, 'catalog_promoted': False, 'cloud_writes_this_subtask': 0}
    try:
        if args.action == 'adopt':
            result = adopt(release.Release(), release.FAILED_HOME)
        else:
            result = verify_applied(release.Release(), release.HOME)
            rt.save(release.HOME / 'independently-verified.json', result)
        rt.save(RESULT, result)
        print(json.dumps(result), flush=True)
        return 0
    except Exception as exc:
        result['blocked_type'] = type(exc).__name__
        result['reason'] = str(exc) if isinstance(exc, RuntimeError) else 'Protected diagnostic suppressed'
        result['recorded_attempt_directories'] = [p.relative_to(rt.ROOT).as_posix() for p in attempted_directories()]
        rt.save(RESULT, result)
        print(json.dumps(result), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())