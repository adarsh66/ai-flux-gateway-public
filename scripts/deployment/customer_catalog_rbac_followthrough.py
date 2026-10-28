"""Fresh read-only RBAC facts; no builds, plans, role writes or key calls."""
from copy import deepcopy
import fnmatch
import json
import ssl
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.deployment import customer_catalog_release as r

PRINCIPAL = '4e7b70ed-9868-47ba-9b61-304f1e1fdd89'
ROLE = '16ca19f5-170e-4549-a223-d6f3381a6ccf'
APIM = r.rt.RG + '/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim'
ASSIGNMENT = APIM + '/providers/Microsoft.Authorization/roleAssignments/941a880c-ec30-47bc-bbe7-26adab3ed6cf'
ACTIONS = [
    'Microsoft.ApiManagement/service/read',
    'Microsoft.ApiManagement/service/products/read',
    'Microsoft.ApiManagement/service/subscriptions/read',
    'Microsoft.ApiManagement/service/subscriptions/write',
    'Microsoft.ApiManagement/service/subscriptions/listSecrets/action',
    'Microsoft.ApiManagement/service/subscriptions/regeneratePrimaryKey/action',
    'Microsoft.ApiManagement/service/subscriptions/regenerateSecondaryKey/action',
    'Microsoft.ApiManagement/service/policyFragments/read',
    'Microsoft.ApiManagement/service/policyFragments/write',
]


def get(path):
    token = r.rt.cli(['account', 'get-access-token', '--subscription', r.rt.SUB,
                      '--resource', 'https://management.azure.com/'])['accessToken']
    request = Request('https://management.azure.com' + path + '?api-version=2022-04-01',
                      headers={'Authorization': 'Bearer ' + token})
    try:
        with urlopen(request, context=ssl.create_default_context(cafile=r.rt.CA), timeout=90) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, None


def grants_action(permissions, action):
    return any(any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get('actions', []))
               and not any(fnmatch.fnmatchcase(action.lower(), p.lower()) for p in g.get('notActions', []))
               for g in permissions)


def main():
    r.account()
    r.source_check()
    markers = {n: (r.HOME / n).exists() for n in ('review.json', 'validation.json', 'apply-intent.json', 'applied.json')}
    r.rt.require(not markers['apply-intent.json'], 'apply_already_attempted_reconcile')
    status, _ = get(ASSIGNMENT)
    definition_status, definition = get('/subscriptions/' + r.rt.SUB + '/providers/Microsoft.Authorization/roleDefinitions/' + ROLE)
    r.rt.require(definition_status == 200, 'actual_role_definition_unresolved:' + str(definition_status))
    actual = definition['properties']
    assignments = r.rt.cli(['role', 'assignment', 'list', '--assignee-object-id', PRINCIPAL,
                            '--scope', APIM, '--include-inherited', '--include-groups',
                            '--subscription', r.rt.SUB])
    grants = []
    for assignment in assignments:
        scope = assignment['scope']
        if not (APIM.lower() == scope.lower() or APIM.lower().startswith(scope.lower().rstrip('/') + '/')):
            continue
        code, d = get(assignment['roleDefinitionId'])
        r.rt.require(code == 200, 'grant_definition_unresolved:' + str(code))
        grants.append({'id': assignment['id'], 'scope': scope, 'principal_id': assignment['principalId'],
                       'role_definition_id': assignment['roleDefinitionId'], 'role_name': d['properties']['roleName'],
                       'condition': assignment.get('condition'), 'permissions': d['properties']['permissions']})
    allowed = {action: [g['id'] for g in grants if not g['condition'] and grants_action(g['permissions'], action)]
               for action in ACTIONS}
    before = r.load(r.HOME / 'preflight-baseline.json')
    current = r.baseline()
    old_roles, roles = before['runtime']['roleAssignments'], current['runtime']['roleAssignments']
    expected = deepcopy(before)
    expected['runtime']['roleAssignments'] = roles
    proof = {'at': r.fs.stamp(), 'assignment_http_status': status,
             'assignment_id': ASSIGNMENT, 'actual_role_definition_http_status': definition_status,
             'actual_role': {'id': definition['id'], 'name': actual['roleName'], 'description': actual.get('description'),
                             'permissions': actual['permissions'], 'assignable_scopes': actual['assignableScopes']},
             'api_principal': PRINCIPAL, 'applicable_direct_inherited_and_group_grants': grants,
             'action_grant_coverage': allowed,
             'subscription_management_actions_covered': all(allowed[a] for a in ACTIONS[:7]),
             'removed_roles': [v for v in old_roles if v not in roles],
             'added_roles': [v for v in roles if v not in old_roles],
             'all_other_protected_fields_equal': current == expected,
             'original_baseline_sha256': r.fs.sha(before), 'current_baseline_sha256': r.fs.sha(current),
             'original_plan_sha256': r.sha(r.PLAN.read_bytes()), 'build': r.built(), 'markers': markers,
             'cloud_configuration_writes': 0, 'key_or_inference_calls': 0,
             'limits': 'RBAC metadata coverage, not runtime operation success; no key calls. No acceptance or baseline change performed.'}
    path = r.HOME / ('fresh-rbac-facts-' + r.fs.stamp().replace(':', '').replace('+', '_') + '.json')
    with path.open('x', encoding='utf-8') as handle:
        json.dump(proof, handle, indent=2)
    print(json.dumps({'evidence': path.relative_to(r.rt.ROOT).as_posix(), **proof}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'read_only_rbac_check_failed_detail_suppressed'}), flush=True)
        raise SystemExit(1)