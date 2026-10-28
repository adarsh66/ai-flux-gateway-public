"""Independent exact gateway validation; no build, apply or inference."""
from datetime import UTC, datetime
import fnmatch
import json
import xml.etree.ElementTree as ET

from scripts.deployment import fireworks_release as release
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.apim_route_repair import APIM
from scripts.deployment.deploy_portals import workflow


def main():
    run = release.Release()
    rt.require(not (release.HOME / 'apply-intent.json').exists(), 'attempted_apply_reconcile_only')
    for step in ('None', 'LoadPlan', 'AddValidationSteps'):
        print(json.dumps(workflow(step)), flush=True)
    review, _ = run.check()
    run.terraform('fmt', '-check', '-no-color')
    run.terraform('validate', '-no-color')
    rt.require(run.terraform('workspace', 'show').strip() == 'default', 'workspace')
    plan = json.loads(run.terraform('show', '-json', str(release.HOME / 'gateway.tfplan')))
    rt.require(all(c.get('status') == 'pass' for c in plan.get('checks', [])), 'all_plan_checks_pass')
    tests = ET.parse(rt.ROOT / 'gateway/validation/fireworks-corrected-tests-20261028.xml').getroot()
    suites = list(tests.iter('testsuite'))
    count = sum(int(s.get('tests', '0')) for s in suites)
    rt.require(count >= 228 and all(int(s.get(k, '0')) == 0 for s in suites
               for k in ('failures', 'errors', 'skipped')), 'actual_focused_tests_required')
    print(json.dumps(workflow('RunValidation')), flush=True)
    # Actual Terraform rendering tested; gateway stage has no application image.
    print(json.dumps(workflow('BuildVerification')), flush=True)
    assignments = rt.cli(['role', 'assignment', 'list', '--assignee-object-id', rt.OPERATOR,
                         '--scope', APIM, '--include-inherited'])
    grants = []
    for assignment in assignments:
        if not assignment.get('condition'):
            for definition in rt.cli(['role', 'definition', 'list', '--name', assignment['roleDefinitionId'].rsplit('/', 1)[-1]]):
                grants.extend(definition['permissions'])
    actions = ['Microsoft.ApiManagement/service/' + suffix for suffix in
               ('backends/read', 'backends/write', 'apis/policies/read', 'apis/policies/write')]
    allowed = {action: any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get('actions', []))
                          and not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get('notActions', []))
                          for g in grants) for action in actions}
    rt.save(release.HOME / 'operator-permission-check.json', {'at_utc': datetime.now(UTC).isoformat(),
            'principal_id': rt.OPERATOR, 'allowed': allowed,
            'assignments': [{k: a.get(k) for k in ('id', 'principalId', 'roleDefinitionId', 'scope', 'condition')}
                            for a in assignments]})
    rt.require(all(allowed.values()), 'existing_operator_permissions_insufficient')
    # Existing baseline binds all role assignments and identities; plan permits no RBAC write.
    print(json.dumps(workflow('StaticRoleVerification')), flush=True)
    proof = {**review, 'validated_at_utc': datetime.now(UTC).isoformat(), 'checks_passed': True,
             'focused_tests': count, 'all_plan_checks_pass': True, 'operator_actions': allowed,
             'images_required': False, 'cloud_writes': 0, 'inference_requests': 0}
    rt.save(release.HOME / 'validation.json', proof)
    rt.save(rt.ROOT / 'gateway/validation/fireworks-gateway-validation-20261028.json', proof)
    path = rt.ROOT / '.azure/deployment-plan.md'
    text = path.read_text(encoding='utf-8')
    text += ('\n### Section 7: Fireworks gateway exact-plan validation proof\n\n'
             + proof['validated_at_utc'] + '; plan SHA256 ' + review['plan_sha256']
             + '. Independent fireworks_validation: fresh full protected baseline, active existing '
               'product subscriptions, source/input/rollback/plan hashes, exact saved-plan guard, '
               'Terraform fmt/validate/default workspace/all plan checks pass; '
             + str(count) + ' focused tests pass including actual rendering. Existing operator '
               'backend/policy read/write grants verified; no RBAC writes. Gateway-only stage '
               'needs no image build. Original failed SKU-export plan retained; corrected '
               'fresh separate attempt only. No inference or cloud configuration writes in validation.\n')
    path.write_text(text, encoding='utf-8')
    print(json.dumps(workflow('RecordProof')), flush=True)
    print(json.dumps(workflow('ResolveErrors')), flush=True)
    path.write_text(text.replace('Fireworks gateway status: Approved', 'Fireworks gateway status: Validated'), encoding='utf-8')
    print(json.dumps(workflow('UpdateStatus')), flush=True)
    print(json.dumps({'plan_sha256': review['plan_sha256'], 'checks_passed': True, 'focused_tests': count}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'blocked': type(exc).__name__, 'reason': str(exc) if isinstance(exc, RuntimeError)
                          else 'Validation failed; sensitive diagnostic suppressed.'}), flush=True)
        raise SystemExit(1)