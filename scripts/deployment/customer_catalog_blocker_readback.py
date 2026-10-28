"""Read-only retained release blocker evidence. Never build, plan, grant or apply."""
from copy import deepcopy
import json
import re
from urllib.error import HTTPError
from urllib.request import Request

from scripts.deployment import customer_catalog_release as r


def main():
    r.account()
    before = r.load(r.HOME / 'preflight-baseline.json')
    current = r.baseline()
    old_roles = before['runtime']['roleAssignments']
    roles = current['runtime']['roleAssignments']
    removed = [v for v in old_roles if v not in roles]
    added = [v for v in roles if v not in old_roles]
    expected = deepcopy(before)
    expected['runtime']['roleAssignments'] = roles
    statuses = []
    for role in removed:
        try:
            token = r.rt.cli(['account', 'get-access-token', '--subscription', r.rt.SUB,
                              '--resource', 'https://management.azure.com/'])['accessToken']
            request = Request('https://management.azure.com' + role[0] + '?api-version=2022-04-01',
                              headers={'Authorization': 'Bearer ' + token})
            with r.urlopen(request, context=r.ssl.create_default_context(cafile=r.rt.CA),
                           timeout=90) as response:
                status = response.status
        except HTTPError as error:
            status = error.code
        statuses.append({'assignment_id': role[0], 'http_status': status})
    http, scripts = [], []
    for path in ('/healthz', '/models'):
        with r.urlopen('https://poc-ids-token-ex-customer.azurewebsites.net' + path,
                       context=r.ssl.create_default_context(cafile=r.rt.CA), timeout=90) as response:
            body = response.read()
            http.append({'path': path, 'status': response.status, 'body_sha256': r.sha(body)})
            if path == '/models':
                scripts = re.findall(r'<script[^>]+src="([^"]+)"', body.decode())
    proof = {'at': r.fs.stamp(), 'status': 'BLOCKED_NO_APPLY',
             'reason': 'protected_baseline_drift_removed_apim_role_assignment',
             'plan_sha256': r.sha(r.PLAN.read_bytes()), 'build': r.built(),
             'removed_roles': removed, 'added_roles': added,
             'exact_assignment_readback': statuses,
             'all_other_protected_fields_equal': current == expected,
             'current_customer_image': current['runtime']['sites']['customer']['image'],
             'http': http, 'served_script_paths': scripts,
             'markers': {n: (r.HOME / n).exists() for n in
                         ('companion-intent.json', 'review.json', 'validation.json',
                          'apply-intent.json', 'applied.json')},
             'cloud_configuration_writes': 0, 'inference_requests': 0}
    r.rt.save(r.HOME / 'blocked-live-proof.json', proof)
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    main()