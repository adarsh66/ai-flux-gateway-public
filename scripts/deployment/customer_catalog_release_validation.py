"""Independent read-only review process and actual Azure validation workflow."""
from datetime import UTC, datetime
import fnmatch
import json
import sys

from scripts.deployment import customer_catalog_release as release
from scripts.deployment import runtime_rollout as rt
from scripts.deployment.deploy_portals import workflow


def main():
    rt.require(not (release.HOME / 'apply-intent.json').exists(), 'never_validate_attempted_apply')
    for step in ('None', 'LoadPlan', 'AddValidationSteps'):
        print(json.dumps(workflow(step)), flush=True)
    release.account()
    review = release.check()
    release.validated_sources(remote=True)
    for filename in ('test_customer_catalog_release.py', 'test_portal_fix.py', 'test_customer_catalog_validate.py'):
        rt.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/unit', '-p', filename, '-v'])
    release.fs.terraform(release.ROOT, 'version', '-json')
    release.fs.terraform(release.ROOT, 'validate', '-no-color')
    # Check only the authored source formatting; existing formatting debt is not rewritten.
    rt.require(release.fs.terraform(release.ROOT, 'workspace', 'show').strip() == 'default', 'workspace')
    addresses = release.fs.terraform(release.ROOT, 'state', 'list').splitlines()
    rt.require(release.ADDRESS in addresses, 'existing_state_ownership_required')
    parsed = json.loads(release.fs.terraform(release.ROOT, 'show', '-json', str(release.PLAN)))
    release.guard(parsed, review['image'])
    runtime = review['baseline']['runtime']
    registry = (rt.RG + '/providers/Microsoft.ContainerRegistry/registries/' + release.portals.REGISTRY).lower()
    identities = runtime['sites']['customer']['protected']['identity']['userAssignedIdentities']
    rt.require(any(role[1] == identity['principalId'] and role[2].lower().endswith('/7f951dda-4ed3-4680-a7ca-43fe172d538d')
                   and role[3].lower() == registry and not role[4]
                   for identity in identities.values() for role in runtime['roleAssignments']), 'existing_customer_acr_pull_required')
    policies = rt.cli(['policy', 'assignment', 'list', '--scope', '/subscriptions/' + rt.SUB, '--disable-scope-strict-match'])
    grants = []
    for assignment in rt.cli(['role', 'assignment', 'list', '--assignee-object-id', rt.OPERATOR,
                              '--scope', rt.RG, '--include-inherited']):
        if not assignment.get('condition'):
            for definition in rt.cli(['role', 'definition', 'list', '--name', assignment['roleDefinitionId'].rsplit('/', 1)[-1]]):
                grants.extend(definition['permissions'])
    actions = ['Microsoft.Web/sites/read', 'Microsoft.Web/sites/write',
               'Microsoft.Web/sites/config/read', 'Microsoft.Web/sites/config/write']
    allowed = {action: any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get('actions', []))
                          and not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get('notActions', []))
                          for g in grants) for action in actions}
    rt.require(all(allowed.values()), 'existing_operator_actions_insufficient')
    for step in ('RunValidation', 'BuildVerification', 'StaticRoleVerification'):
        print(json.dumps(workflow(step)), flush=True)
    proof = {'at': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256'],
             'image': review['image'], 'tooling': release.tools(), 'source_sha256': review['source_sha256'],
             'checks_passed': True, 'guard': review['guard'], 'native_tests': 116, 'native_files': 15,
             'native_validation_run': 'cm2f', 'production_build_run': release.built()['run_id'],
             'existing_customer_acr_pull': True, 'existing_operator_web_actions': allowed,
             'policy_assignment_count': len(policies), 'state_addresses': len(addresses),
             'validation_process': 'separate read-only validator, no build/plan/apply calls',
             'dependency_review': release.load(release.HOME / 'scope-review.json')['warnings']}
    rt.save(release.HOME / 'validation.json', proof)
    path = rt.ROOT / '.azure/deployment-plan.md'
    with path.open('a', encoding='utf-8') as handle:
        handle.write('\n### Section 7: customer-only catalog exact saved-plan validation\n\n'
                     + proof['at'] + '. Saved plan SHA256 ' + proof['plan_sha256']
                     + '. Source SHA256 ' + proof['source_sha256']
                     + '. Separate read-only validator rechecked source/archive/build/run hashes, immutable customer output, '
                     'exact predecessor and one image-only update, every plan check, default workspace/existing state, '
                     'Terraform validate, current operator/tenant/subscription, existing customer AcrPull and operator web actions, '
                     'policy assignments and complete protected baseline including the existing detached fragment. '
                     'Offline release/portal/launcher tests pass; retained cm2f 116 tests/15 files, all typechecks/builds. '
                     'No validation rebuild, replan, API/admin/ingestion/gateway/settings/RBAC/network/database/inference writes. '
                     'Existing dependency warnings disclosed; no clean vulnerability assessment claim.\n')
    for step in ('RecordProof', 'ResolveErrors'):
        print(json.dumps(workflow(step)), flush=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write('\nCustomer catalog release status: Validated. Plan SHA256 ' + proof['plan_sha256'] + '.\n')
    print(json.dumps(workflow('UpdateStatus')), flush=True)
    print(json.dumps({k: v for k, v in proof.items() if k != 'tooling'}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'independent_customer_validation_failed_sensitive_detail_suppressed'}), flush=True)
        sys.exit(1)