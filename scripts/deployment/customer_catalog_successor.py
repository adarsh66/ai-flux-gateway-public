"""Explicitly approved optional-publisher reconciliation; fresh customer plan only.

No build, push or role mutation entry point. Original release remains untouched.
All original strict guards and full NEVER APPLY companion checks are reused.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import shutil
import sys

from scripts.deployment import customer_catalog_release as r
from scripts.deployment import customer_catalog_companion as c
from scripts.deployment import customer_catalog_rbac_followthrough as facts

ORIGINAL = r.HOME
HOME = r.rt.HOME / 'customer-catalog-successor-20261028'
OLD_SHA = '40fe1728720d6d4ece18faba097f6992533b3b7f1ef150d60153cec921ed463f'
IMAGE = 'sha256:d9d8b4b21283801feb2aff3ad12707155f5c38c59b6fc09091a4c22c35e71ea3'
SELF = r.rt.ROOT / 'scripts/deployment/customer_catalog_successor.py'
TEST = r.rt.ROOT / 'tests/unit/test_customer_catalog_successor.py'


def reconcile(before, current, proof):
    expected_role = [facts.ASSIGNMENT, facts.PRINCIPAL,
        '/subscriptions/' + r.rt.SUB + '/providers/Microsoft.Authorization/roleDefinitions/' + facts.ROLE,
        facts.APIM, None]
    removed = [v for v in before['runtime']['roleAssignments'] if v not in current['runtime']['roleAssignments']]
    added = [v for v in current['runtime']['roleAssignments'] if v not in before['runtime']['roleAssignments']]
    expected = deepcopy(before)
    expected['runtime']['roleAssignments'] = current['runtime']['roleAssignments']
    r.rt.require(removed == [expected_role] and not added and expected == current,
                 'only_exact_optional_publisher_removal_permitted')
    role = proof['actual_role']
    r.rt.require(proof['assignment_http_status'] == 404
        and proof['actual_role_definition_http_status'] == 200
        and role['id'].lower() == expected_role[2].lower()
        and role['name'] == 'poc-ids-scoped-APIM-read-write-role'
        and role['permissions'] == [{'actions': facts.ACTIONS[7:], 'notActions': [],
                                    'dataActions': [], 'notDataActions': []}]
        and proof['subscription_management_actions_covered'] is True
        and all(proof['action_grant_coverage'][a] for a in facts.ACTIONS[:7])
        and proof['removed_roles'] == removed and proof['added_roles'] == []
        and proof['all_other_protected_fields_equal'] is True
        and proof['original_baseline_sha256'] == r.fs.sha(before)
        and proof['current_baseline_sha256'] == r.fs.sha(current), 'verified_rbac_facts_required')
    return expected


def bind():
    return {p.relative_to(r.rt.ROOT).as_posix(): r.sha(p.read_bytes())
            for p in (SELF, TEST, r.rt.ROOT / 'scripts/deployment/customer_catalog_rbac_followthrough.py')}


def originals():
    r.rt.require(r.sha((ORIGINAL / 'customer-only.tfplan').read_bytes()) == OLD_SHA,
                 'original_plan_changed')
    r.rt.require(not any((ORIGINAL / n).exists() for n in ('review.json', 'validation.json',
        'apply-intent.json', 'applied.json', 'companion-intent.json')), 'original_stage_advanced_reconcile')


def configure():
    r.HOME, r.ROOT, r.PLAN = HOME, HOME / 'infra/terraform', HOME / 'customer-only.tfplan'
    c.FULL = HOME / 'validation-only-NEVER-APPLY.tfplan'


def prepare():
    originals()
    r.account()
    r.source_check()
    r.rt.require(not HOME.exists(), 'successor_exists_never_replay')
    paths = sorted(ORIGINAL.glob('fresh-rbac-facts-*.json'))
    r.rt.require(bool(paths), 'fresh_rbac_proof_required')
    proof = r.load(paths[-1])
    r.rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(proof['at']) < timedelta(hours=2),
                 'rbac_proof_expired')
    before, current = r.load(ORIGINAL / 'preflight-baseline.json'), r.baseline()
    accepted = reconcile(before, current, proof)
    r.require_pins(accepted)
    # Read effective settings internally; never print them or change attestations.
    settings = r.fs.current_settings()
    api = settings['api']
    r.rt.require(json.loads(api.get('AIFLUX_GATEWAY_SETTINGS_SCOPES', '[]')) == []
                 and api.get('AIFLUX_GATEWAY_CONTROLS_POC_ENABLED', 'false').lower() == 'false',
                 'optional_publishing_must_remain_off')
    built = r.built()
    r.rt.require(built['digest'] == IMAGE and built['run_id'] == 'cm2g', 'reuse_exact_cm2g_only')
    r.fs.protect(HOME)
    for name in ('sources.json', 'tooling.json', 'build.json', 'customer-build.log', 'scope-review.json'):
        shutil.copyfile(ORIGINAL / name, HOME / name)
    configure()
    r.exclusive('preflight-baseline.json', accepted)
    r.exclusive('rbac-facts.json', proof)
    r.exclusive('reconciliation.json', {'at': r.fs.stamp(),
        'authorization': '2026-10-28 user-approved safe external RBAC reconciliation; no role writes or guard weakening',
        'original_plan_sha256': OLD_SHA, 'original_plan_disposition': 'NEVER APPLY; superseded by fresh saved plan',
        'original_baseline_sha256': r.fs.sha(before), 'accepted_baseline_sha256': r.fs.sha(accepted),
        'removed_role': proof['removed_roles'], 'added_roles': [], 'other_fields_unchanged': True,
        'actual_missing_role': proof['actual_role'], 'subscription_actions_metadata_covered': True,
        'optional_publishing_off': True, 'runtime_key_operations_not_tested': True,
        'image': built['image'], 'source_sha256': built['source_sha256'], 'amendment': bind(),
        'manual_rbac_verified_input_not_changed': True, 'cloud_configuration_writes': 0})
    r.exclusive('release-intent.json', {'at': r.fs.stamp(), 'scope': ['customer'], 'builds': 0,
                                      'max_applies': 1, 'predecessor': r.PINS['customer']})
    print(json.dumps({'accepted_baseline_sha256': r.fs.sha(accepted), 'image': built['image'],
                      'original_plan': 'NEVER APPLY', 'cloud_configuration_writes': 0}), flush=True)


def check_binding():
    originals()
    record = r.load(HOME / 'reconciliation.json')
    r.rt.require(record['amendment'] == bind(), 'successor_amendment_drift')
    r.rt.require(record['accepted_baseline_sha256'] == r.fs.sha(r.load(HOME / 'preflight-baseline.json')),
                 'accepted_baseline_changed')
    r.rt.require(r.load(HOME / 'build.json') == r.load(ORIGINAL / 'build.json'), 'built_image_changed')


def plan():
    check_binding()
    # The original strict plan function may save a target with unrelated unknown
    # checks. It is not accepted until the identical full companion passes ALL.
    try:
        r.plan()
    except RuntimeError as e:
        if str(e) != 'all_plan_preconditions_must_pass':
            raise
        r.rt.require(r.PLAN.exists() and not (HOME / 'review.json').exists(), 'pending_target_required')
        r.exclusive('pending-target-checks.json', {'at': r.fs.stamp(),
            'plan_sha256': r.sha(r.PLAN.read_bytes()), 'status': 'NOT VALIDATED; requires full companion'})
        print(json.dumps({'target_saved': True, 'status': 'pending_full_companion_not_applyable_yet',
                          'plan_sha256': r.sha(r.PLAN.read_bytes())}), flush=True)


def main():
    action = sys.argv[1]
    r.rt.require(action in ('prepare', 'plan', 'companion', 'validate', 'apply', 'verify'), 'action_required')
    if action == 'prepare':
        prepare()
        return
    configure()
    check_binding()
    if action == 'plan':
        plan()
    elif action == 'companion':
        c.prepare()
    else:
        getattr(c, action)()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(json.dumps({'error_type': type(e).__name__, 'reason': str(e)
            if isinstance(e, RuntimeError) else 'successor_failed_sensitive_detail_suppressed'}), flush=True)
        raise SystemExit(1)