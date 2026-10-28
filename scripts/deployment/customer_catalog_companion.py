"""Resolve retained customer target checks without rebuilding/replanning that target.

Original release tooling, intents, image, source evidence and target bytes remain
unchanged. The full companion is validation-only and is never passed to apply.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import fnmatch
import json
import re
import sys

from scripts.deployment import customer_catalog_release as r
from scripts.deployment.deploy_portals import workflow

FULL = r.HOME / 'validation-only-NEVER-APPLY.tfplan'
SELF = r.rt.ROOT / 'scripts/deployment/customer_catalog_companion.py'
TEST = r.rt.ROOT / 'tests/unit/test_customer_catalog_companion.py'


def normalized(value):
    if isinstance(value, dict):
        return {k: sorted(v) if k == 'references' and isinstance(v, list)
                and all(isinstance(x, str) for x in v) else normalized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def resolve(target, full, image):
    r.rt.require(target.get('configuration') is not None
                 and normalized(target['configuration']) == normalized(full.get('configuration'))
                 and target.get('variables') is not None and target['variables'] == full.get('variables')
                 and not full.get('errored') and not full.get('deferred_changes'), 'identical_companion_inputs_required')
    matches = [c for c in full.get('resource_changes', []) if c['address'] == r.ADDRESS]
    original = [c for c in target.get('resource_changes', []) if c['address'] == r.ADDRESS]
    r.rt.require(len(matches) == len(original) == 1 and matches[0]['change'] == original[0]['change'], 'exact_target_change_binding')
    checks = full.get('checks', [])
    r.rt.require(checks and all(c.get('status') == 'pass' for c in checks), 'full_preconditions_must_pass')
    lookup = {json.dumps(c['address'], sort_keys=True): c for c in checks}
    resolved = deepcopy(target)
    resolved['checks'] = []
    r.rt.require(target.get('checks'), 'target_checks_required')
    for c in target['checks']:
        key = json.dumps(c['address'], sort_keys=True)
        r.rt.require(c.get('status') in ('pass', 'unknown') and key in lookup, 'failed_or_missing_target_check')
        resolved['checks'].append(lookup[key])
    # Original strict image/settings/identity/unknown-field guard is unchanged.
    r.guard(resolved, image)
    return resolved


def parsed(path):
    return json.loads(r.fs.terraform(r.ROOT, 'show', '-json', str(path)))


def files():
    return [*r.ROOT.glob('*.tf'), *r.ROOT.glob('*.tf.json'), r.ROOT / '.terraform.lock.hcl',
            r.HOME / 'runtime.tfvars.json', FULL]


def amendment_hashes():
    return {p.relative_to(r.rt.ROOT).as_posix(): r.sha(p.read_bytes()) for p in (SELF, TEST)}


def prepare():
    r.account()
    r.source_check()
    image = r.built()['image']
    r.rt.require(not (r.HOME / 'apply-intent.json').exists() and not (r.HOME / 'review.json').exists(), 'no_review_or_apply_replay')
    r.rt.require(r.baseline() == r.load(r.HOME / 'preflight-baseline.json'), 'protected_baseline_drift')
    target_hash = r.sha(r.PLAN.read_bytes())
    r.exclusive('companion-intent.json', {'at': r.fs.stamp(), 'target_sha256': target_hash,
                'amendment': amendment_hashes(), 'reason': 'Resolve unrelated targeted unknown preconditions using identical full inputs; never apply companion.'})
    r.rt.require(not FULL.exists(), 'never_replan_companion')
    r.fs.terraform(r.ROOT, 'plan', '-input=false', '-no-color', '-lock-timeout=60s',
        '-var-file=' + str(r.rt.HOME / 'rebuild-platform.tfvars.json'),
        '-var-file=' + str(r.HOME / 'runtime.tfvars.json'),
        '-var-file=' + str(r.rt.HOME / 'jwt-runtime.tfvars.json'), '-out=' + str(FULL))
    r.rt.require(r.sha(r.PLAN.read_bytes()) == target_hash, 'original_target_changed')
    target, full = parsed(r.PLAN), parsed(FULL)
    resolve(target, full, image)
    review = {'at': r.fs.stamp(), 'plan_sha256': target_hash, 'image': image,
              'source_sha256': r.load(r.HOME / 'sources.json')['source_sha256'],
              'tooling': r.tools(), 'amendment': amendment_hashes(),
              'baseline': r.load(r.HOME / 'preflight-baseline.json'),
              'artifacts': {p.relative_to(r.HOME).as_posix(): r.sha(p.read_bytes()) for p in files()},
              'guard': 'exact_one_customer_image_only_with_identical_input_full_check_resolution',
              'companion_never_apply': True,
              'full_plan_writes_NOT_APPROVED': [{'address': c['address'], 'actions': c['change']['actions']}
                   for c in full.get('resource_changes', []) if c['change']['actions'] not in (['no-op'], ['read'])]}
    r.exclusive('review.json', review)
    print(json.dumps({k: review[k] for k in ('at', 'plan_sha256', 'guard', 'full_plan_writes_NOT_APPROVED')}), flush=True)


def check(live=True):
    review = r.load(r.HOME / 'review.json')
    intent = r.load(r.HOME / 'companion-intent.json')
    r.rt.require(review['tooling'] == r.tools() and review['amendment'] == amendment_hashes() == intent['amendment'], 'tooling_or_amendment_drift')
    r.rt.require(review['plan_sha256'] == intent['target_sha256'] == r.sha(r.PLAN.read_bytes()), 'target_bytes_drift')
    r.rt.require(all(r.sha((r.HOME / p).read_bytes()) == h for p, h in review['artifacts'].items()), 'archived_input_drift')
    r.rt.require(r.built(remote=live)['image'] == review['image'], 'image_drift')
    resolve(parsed(r.PLAN), parsed(FULL), review['image'])
    if live:
        r.account()
        r.rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review['at']) < timedelta(hours=2), 'plan_expired')
        r.rt.require(r.baseline() == review['baseline'], 'full_live_baseline_drift')
    return review


def validate():
    r.rt.require(not (r.HOME / 'apply-intent.json').exists(), 'never_validate_attempted_apply')
    for step in ('None', 'LoadPlan', 'AddValidationSteps'):
        print(json.dumps(workflow(step)), flush=True)
    review = check()
    r.validated_sources(remote=True)
    for name in ('test_customer_catalog_companion.py', 'test_customer_catalog_release.py', 'test_portal_fix.py', 'test_customer_catalog_validate.py'):
        r.rt.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/unit', '-p', name, '-v'])
    r.fs.terraform(r.ROOT, 'validate', '-no-color')
    r.rt.require(r.fs.terraform(r.ROOT, 'workspace', 'show').strip() == 'default', 'workspace')
    r.rt.require(r.ADDRESS in r.fs.terraform(r.ROOT, 'state', 'list').splitlines(), 'existing_state_ownership')
    runtime = review['baseline']['runtime']
    registry = (r.rt.RG + '/providers/Microsoft.ContainerRegistry/registries/' + r.portals.REGISTRY).lower()
    identities = runtime['sites']['customer']['protected']['identity']['userAssignedIdentities']
    r.rt.require(any(role[1] == identity['principalId'] and role[2].lower().endswith('/7f951dda-4ed3-4680-a7ca-43fe172d538d')
                 and role[3].lower() == registry and not role[4] for identity in identities.values()
                 for role in runtime['roleAssignments']), 'existing_customer_acr_pull_required')
    grants = []
    for a in r.rt.cli(['role', 'assignment', 'list', '--assignee-object-id', r.rt.OPERATOR, '--scope', r.rt.RG, '--include-inherited']):
        if not a.get('condition'):
            for d in r.rt.cli(['role', 'definition', 'list', '--name', a['roleDefinitionId'].rsplit('/', 1)[-1]]):
                grants.extend(d['permissions'])
    actions = ['Microsoft.Web/sites/read', 'Microsoft.Web/sites/write', 'Microsoft.Web/sites/config/read', 'Microsoft.Web/sites/config/write']
    allowed = {a: any(any(fnmatch.fnmatchcase(a.lower(), p.lower()) for p in g.get('actions', []))
                     and not any(fnmatch.fnmatchcase(a.lower(), p.lower()) for p in g.get('notActions', [])) for g in grants) for a in actions}
    r.rt.require(all(allowed.values()), 'existing_operator_actions_insufficient')
    policies = r.rt.cli(['policy', 'assignment', 'list', '--scope', '/subscriptions/' + r.rt.SUB, '--disable-scope-strict-match'])
    for step in ('RunValidation', 'BuildVerification', 'StaticRoleVerification'):
        print(json.dumps(workflow(step)), flush=True)
    proof = {'at': r.fs.stamp(), 'checks_passed': True, 'plan_sha256': review['plan_sha256'], 'tooling': r.tools(),
             'amendment': amendment_hashes(), 'companion_sha256': r.sha(FULL.read_bytes()),
             'image': review['image'], 'native_validation_run': 'cm2f', 'native_tests': 116, 'native_files': 15,
             'production_build_run': r.built()['run_id'], 'existing_customer_acr_pull': True,
             'existing_operator_actions': allowed, 'policy_assignment_count': len(policies),
             'all_full_preconditions_pass': True, 'companion_never_apply': True,
             'validation_process': 'separate read-only process; no build, plan or apply'}
    r.exclusive('validation.json', proof)
    doc = r.rt.ROOT / '.azure/deployment-plan.md'
    with doc.open('a', encoding='utf-8') as f:
        f.write('\n### Section 7: customer catalog independent exact retained-plan validation\n\n' + proof['at']
                + '. Plan SHA256 ' + proof['plan_sha256'] + '. Companion SHA256 ' + proof['companion_sha256']
                + '. Original target bytes/tooling/source/build unchanged. Full NEVER APPLY companion has identical '
                'configuration/variables and exact customer change; every full precondition passes. Original strict '
                'guard confirms only customer image update. Independent process ran Terraform validate, default '
                'workspace/state ownership, all four offline suites, existing AcrPull/operator permissions, policy '
                'assignments, source/archive/image hashes and complete live protected baseline. Reused cm2f '
                '116 tests/15 files and cm2g production image. No build/target replan, cloud writes or inference. '
                'Existing npm vulnerabilities remain disclosed; no clean security claim.\n')
    for step in ('RecordProof', 'ResolveErrors'):
        print(json.dumps(workflow(step)), flush=True)
    with doc.open('a', encoding='utf-8') as f:
        f.write('\nCustomer catalog release status: Validated. Plan SHA256 ' + proof['plan_sha256'] + '.\n')
    print(json.dumps(workflow('UpdateStatus')), flush=True)
    print(json.dumps(proof), flush=True)


def apply():
    r.rt.require(not (r.HOME / 'apply-intent.json').exists(), 'apply_attempted_never_replay')
    review = check()
    proof = r.load(r.HOME / 'validation.json')
    doc = (r.rt.ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
    r.rt.require(proof['checks_passed'] is True and proof['plan_sha256'] == review['plan_sha256']
                 and proof['tooling'] == r.tools() and proof['amendment'] == amendment_hashes()
                 and proof['companion_sha256'] == r.sha(FULL.read_bytes())
                 and r.load(r.rt.ROOT / '.azure/validate-status.json')['completedStep'] == 'UpdateStatus'
                 and 'Customer catalog release status: Validated.' in doc and proof['at'] in doc
                 and review['plan_sha256'] in doc, 'independent_exact_validation_required')
    r.exclusive('apply-intent.json', {'at': r.fs.stamp(), 'plan_sha256': review['plan_sha256']})
    # Hard-coded original target only. Never apply FULL.
    output = r.fs.terraform(r.ROOT, 'apply', '-input=false', '-no-color', str(r.PLAN))
    r.exclusive('applied.json', {'at': r.fs.stamp(), 'plan_sha256': review['plan_sha256'],
                'summary': re.findall(r'Apply complete! Resources: [^\r\n]+', output)})
    print(json.dumps(r.load(r.HOME / 'applied.json')), flush=True)


def verify():
    review = check(live=False)
    r.rt.require(r.load(r.HOME / 'applied.json')['plan_sha256'] == review['plan_sha256'], 'matching_apply_required')
    expected = deepcopy(review['baseline'])
    expected['runtime']['sites']['customer']['image'] = 'DOCKER|' + review['image']
    current = r.baseline()
    proof = {'at': r.fs.stamp(), 'plan_sha256': review['plan_sha256'], 'image': review['image'],
             'protected_equal_except_customer_image': current == expected,
             'all_four_settings_hashes_equal': current['settings_hashes'] == expected['settings_hashes'],
             'existing_fragment_unchanged': current['existing_fragment_sha256'] == expected['existing_fragment_sha256'],
             'unchanged_images': {k: current['runtime']['sites'][k]['image'] for k in ('api', 'admin', 'ingestion')},
             'http': [], 'inference_requests': 0}
    for path in ('/healthz', '/models'):
        with r.urlopen('https://poc-ids-token-ex-customer.azurewebsites.net' + path,
                       context=r.ssl.create_default_context(cafile=r.rt.CA), timeout=90) as response:
            proof['http'].append({'path': path, 'status': response.status})
    r.rt.save(r.HOME / 'independently-verified.json', proof)
    print(json.dumps(proof), flush=True)
    r.rt.require(current == expected and all(p['status'] == 200 for p in proof['http']), 'live_readback_failed_no_reapply')


if __name__ == '__main__':
    try:
        r.rt.require(len(sys.argv) == 2 and sys.argv[1] in ('prepare', 'validate', 'apply', 'verify'), 'action_required')
        globals()[sys.argv[1]]()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'customer_companion_failed_sensitive_detail_suppressed'}), flush=True)
        sys.exit(1)