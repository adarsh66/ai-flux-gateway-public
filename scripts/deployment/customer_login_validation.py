"""Independent actual validator; cannot build, plan, apply or publish settings."""
import argparse
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.deployment import customer_login_release as s


def workflow(step):
    args = ['C:/Program Files/Git/bin/bash.exe', 'C:/Users/p4032099/.agents/skills/azure-validate/references/scripts/workflow.sh',
            '--workspace-path', str(s.rt.ROOT)]
    if step != 'None':
        args += ['--completed-step', step]
    output = s.rt.run(args)
    print(output, flush=True)


def validate(release):
    r = s.Release(release)
    s.rt.require(not (r.home / 'apply-intent.json').exists(), 'apply_attempted_reconcile_only')
    for step in ('None', 'LoadPlan', 'AddValidationSteps'):
        workflow(step)
    v = r.check()
    output = s.rt.run([sys.executable, '-X', 'utf8', '-m', 'pytest', '-q', 'tests/unit/test_customer_login_release.py',
                       'tests/unit/test_portal_fix.py', 'tests/unit/test_poc_fireworks_compatibility.py', '--junitxml=' + str(r.home / 'independent-tests.xml')])
    import xml.etree.ElementTree as ET
    suites = list(ET.parse(r.home / 'independent-tests.xml').getroot().iter('testsuite'))
    counts = {k: sum(int(n.get(k, '0')) for n in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    s.rt.require(counts['tests'] >= 10 and all(counts[k] == 0 for k in ('errors', 'failures', 'skipped')), 'actual_clean_tests')
    s.fs.terraform(r.root, 'fmt', '-check')
    s.fs.terraform(r.root, 'validate', '-no-color')
    s.rt.require(s.fs.terraform(r.root, 'workspace', 'show').strip() == 'default'
                 and s.ADDRESS in s.fs.terraform(r.root, 'state', 'list').splitlines(), 'existing_state_ownership')
    workflow('RunValidation')
    s.retained(remote=True)
    r.built()
    workflow('BuildVerification')
    runtime = v['baseline']['runtime']
    registry = (s.rt.RG + '/providers/Microsoft.ContainerRegistry/registries/' + s.portals.REGISTRY).lower()
    identities = runtime['sites']['customer']['protected']['identity']['userAssignedIdentities']
    s.rt.require(any(a[1] == i['principalId'] and a[2].lower().endswith('/7f951dda-4ed3-4680-a7ca-43fe172d538d')
                     and a[3].lower() == registry and not a[4] for i in identities.values() for a in runtime['roleAssignments']), 'customer_acrpull')
    grants = []
    for assignment in s.rt.cli(['role', 'assignment', 'list', '--assignee-object-id', s.rt.OPERATOR, '--scope', s.rt.RG, '--include-inherited']):
        if not assignment.get('condition'):
            definition = s.rt.cli(['rest', '--method', 'get', '--url', 'https://management.azure.com' + assignment['roleDefinitionId'] + '?api-version=2022-04-01'])
            grants.extend(definition['properties']['permissions'])
    actions = ['Microsoft.Web/sites/read', 'Microsoft.Web/sites/write', 'Microsoft.Web/sites/config/read', 'Microsoft.Web/sites/config/write']
    coverage = {a: any(any(fnmatch.fnmatchcase(a.lower(), p.lower()) for p in g.get('actions', []))
                    and not any(fnmatch.fnmatchcase(a.lower(), p.lower()) for p in g.get('notActions', [])) for g in grants) for a in actions}
    s.rt.require(all(coverage.values()), 'operator_permission_coverage')
    policies = s.rt.cli(['policy', 'assignment', 'list', '--scope', '/subscriptions/' + s.rt.SUB, '--disable-scope-strict-match'])
    workflow('StaticRoleVerification')
    s.rt.require(s.snapshot() == v['baseline'], 'independent_final_baseline')
    proof = {'at': s.fs.stamp(), 'checks_passed': True, 'plan_sha256': v['plan_sha256'], 'tooling': s.tooling(),
             'source_sha256': s.UI_HASH, 'image': v['image'], 'tests': counts, 'process_id': os.getpid(), 'ui_run': 'cm2x',
             'operator_coverage': coverage, 'policy_assignment_count': len(policies), 'companion_never_apply': True,
             'junit_sha256': s.sha((r.home / 'independent-tests.xml').read_bytes()), 'actual_official_workflow': True}
    r.write('validation.json', proof)
    print(output, flush=True)
    print(json.dumps({k: val for k, val in proof.items() if k != 'tooling'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True)
    args = parser.parse_args()
    validate(args.release)