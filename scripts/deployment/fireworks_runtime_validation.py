"""Independent exact-plan validation; existing roles only, no deployment writes."""
from datetime import UTC, datetime
import fnmatch
import json

from scripts.deployment import fireworks_runtime as release
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.deploy_portals import workflow


def main():
    rt.require(not (release.HOME / 'apply-intent.json').exists(), 'no_postapply_validation')
    for step in ('None', 'LoadPlan', 'AddValidationSteps'):
        print(json.dumps(workflow(step)), flush=True)
    review = release.check()
    account = rt.cli(['account', 'show'])
    rt.require(account['id'] == rt.SUB and account['tenantId'] == rt.TENANT
               and account['user']['name'].lower() == 'xv.puneet.devadiga@singtel.com', 'operator_scope')
    release.fs.terraform(release.ROOT, 'validate', '-no-color')
    rt.require(release.fs.terraform(release.ROOT, 'workspace', 'show').strip() == 'default', 'workspace')
    parsed = release.load_plan()
    release.guard(parsed, review['images'])
    rt.require(all(c.get('status') == 'pass' for c in release.resolved_checks(parsed)), 'plan_preconditions')
    runtime = review['baseline']['protected']['runtime']
    scope = (rt.RG + '/providers/Microsoft.ContainerRegistry/registries/' + release.portals.REGISTRY).lower()
    for kind in release.KINDS:
        identities = runtime['sites'][kind]['protected']['identity']['userAssignedIdentities']
        rt.require(any(role[1] == identity['principalId'] and role[2].lower().endswith('/7f951dda-4ed3-4680-a7ca-43fe172d538d')
                       and role[3].lower() == scope and not role[4]
                       for identity in identities.values() for role in runtime['roleAssignments']), 'existing_acr_pull:' + kind)
    policies = rt.cli(['policy', 'assignment', 'list', '--scope', '/subscriptions/' + rt.SUB, '--disable-scope-strict-match'])
    assignments = rt.cli(['role', 'assignment', 'list', '--assignee-object-id', rt.OPERATOR,
                         '--scope', rt.RG, '--include-inherited'])
    grants = []
    for assignment in assignments:
        if not assignment.get('condition'):
            for definition in rt.cli(['role', 'definition', 'list', '--name', assignment['roleDefinitionId'].rsplit('/', 1)[-1]]):
                grants.extend(definition['permissions'])
    actions = ['Microsoft.Web/sites/read', 'Microsoft.Web/sites/write',
               'Microsoft.Web/sites/config/read', 'Microsoft.Web/sites/config/write']
    allowed = {action: any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get('actions', []))
                          and not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get('notActions', []))
                          for g in grants) for action in actions}
    rt.require(all(allowed.values()), 'existing_operator_web_permissions_insufficient')
    for step in ('RunValidation', 'BuildVerification', 'StaticRoleVerification'):
        print(json.dumps(workflow(step)), flush=True)
    proof = {'at': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256'],
             'sources': release.sources(), 'images': review['images'], 'tests': review['tests'],
             'checks_passed': True, 'all_plan_checks_pass': True,
             'targeted_checks_resolved_by_identical_input_never_apply_companion': True,
             'existing_acr_pull': list(release.KINDS),
             'existing_operator_web_actions': allowed,
             'policy_assignment_count': len(policies), 'rbac_writes': 0, 'network_writes': 0,
             'native_validation_run_id': release.load(release.HOME / 'native.json')['run_id']}
    rt.save(release.HOME / 'validation.json', proof)
    path = rt.ROOT / '.azure/deployment-plan.md'
    with path.open('a', encoding='utf-8') as handle:
        handle.write('\n### Section 7: Fireworks API + ingestion exact image validation\n\n'
                     + proof['at'] + '. Saved plan SHA256 ' + proof['plan_sha256']
                     + '. Independent source/plan/archive binding, all saved-plan preconditions, exact two image-only guard, '
                     'fresh complete protected baseline, actual clean tests, native Linux validation and production builds, '
                     'current account/default workspace/provider validation and existing API/ingestion AcrPull verified. '
                     'No gateway apply, roles, network, settings, controls activation, DB migration/backfill/cursor reset. '
                     'External historical smoke unchanged; metadata renewal is not current credential-health testing.\n')
    for step in ('RecordProof', 'ResolveErrors'):
        print(json.dumps(workflow(step)), flush=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write('\nFireworks runtime status: Validated. Plan SHA256 ' + proof['plan_sha256'] + '.\n')
    print(json.dumps(workflow('UpdateStatus')), flush=True)
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'independent_validation_failed_sensitive_detail_suppressed'}), flush=True)
        raise SystemExit(1)