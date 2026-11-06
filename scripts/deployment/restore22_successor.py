"""Successor22: source-bound read-only capture and ONE saved policy-only plan.

No apply, inference, build, database or replay entrypoint. Existing controllers
are imported only as read-only projections, with private output bindings.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request
import zipfile

from scripts.deployment import foundry_eight_gateway_apply as old
from scripts.deployment import foundry_eight_runtime_apply as runtime

g = old.reader
rt = g.rt
HOME = rt.HOME / 'restore22-successor-20261031'
CONTEXT = HOME / 'context'
TFROOT = CONTEXT / 'infra/project-route'
PLAN = HOME / 'gateway.tfplan'
NINTH = 'mistral-medium-3-5'
PROFILE = 'foundry-successor22'
MANIFEST = 'gateway/catalog/foundry-successor22-candidate-routes.json'
POLICY = g.POLICY
require, load, digest, now = g.require, g.load, g.digest, g.now


def write(name, value):
    path = HOME / name
    require(path.resolve().is_relative_to(HOME.resolve()), 'owned_output_only')
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + '\n').encode()
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return digest(raw)


def state():
    raw = g.OWNER.read_bytes()
    value = json.loads(raw)
    require(value['lineage'] == '8b19b704-7224-db80-7600-ef2a0cbeef10', 'existing_child_state_owner')
    return {'path': g.OWNER.as_posix(), 'sha256': digest(raw),
            'lineage': value['lineage'], 'serial': value['serial']}


def protected_sources():
    paths = list((rt.ROOT / 'gateway/catalog').glob('*.json'))
    paths += list((rt.ROOT / 'gateway/catalog/acceptance-evidence').rglob('*'))
    paths += [rt.ROOT / 'infra/project-route' / name for name in
              ('auto-routing.tf', 'auto-staging.tf', 'external.tf', 'fireworks.tf', 'poc-controls.tf',
               'tests/foundry-eight.tftest.hcl')]
    paths += [rt.ROOT / 'services/control-plane/src/aiflux' / name for name in
              ('auto_snapshot.py', 'decision_router.py', 'pricing/rates-20261027.json',
               'pricing/rates-foundry-eight-20261030.json', 'pricing/default-estimates-20261030.json')]
    paths += [rt.ROOT / 'services/usage-ingestion/approved_catalog.py']
    paths += list((rt.ROOT / 'gateway/policies').glob('auto*'))
    paths += list((rt.ROOT / '.deployment/restore22-original13-20261031').glob('*'))
    return g.hashes(p for p in paths if p.is_file())


class ReadOnly(runtime.ReadOnly):
    __init__ = g.rebound(runtime.ReadOnly.__init__, write=write)

    def request(self, url, method='GET', optional=False):
        prefix = 'https://management.azure.com' + rt.RG + '/providers/'
        require(url.startswith(prefix) or url.startswith('https://management.azure.com/subscriptions/'
                + rt.SUB + '/providers/Microsoft.Authorization/roleAssignments?'), 'read_scope')
        settings = re.fullmatch(re.escape('https://management.azure.com' + rt.RG)
            + r'/providers/Microsoft.Web/sites/poc-ids-token-ex-(api|admin|customer|ingestion)/config/appsettings/list\?api-version=2024-04-01', url)
        require(method == 'GET' or method == 'POST' and settings is not None, 'semantic_read_only')
        require(not re.search(r'listSecrets|listKeys|regenerate|/secrets/', url, re.I), 'no_secret_read')
        key = (method, url)
        if key in self.cache:
            return deepcopy(self.cache[key])
        self.count += 1
        stem = f'reads/{self.label}-{self.count:03d}'
        write(stem + '-intent.json', {'at': now(), 'pid': os.getpid(), 'method': method,
              'url': url, 'max_invocations': 1})
        try:
            require(time.monotonic() < self.deadline, 'snapshot_deadline')
            request = Request(url, method=method, headers={'Authorization': 'Bearer ' + self.token})
            with self.opener.open(request, timeout=180) as response:
                require(response.status == 200 and response.geturl() == url, 'exact_http_no_redirect')
                raw = response.read(16 * 1024 * 1024 + 1)
                require(len(raw) <= 16 * 1024 * 1024, 'bounded_read')
                value = json.loads(raw)
                write(stem + '-result.json', {'at': now(), 'status': response.status,
                      'body_sha256': digest(raw), 'request_id': response.headers.get('x-ms-request-id')})
                self.cache[key] = value
                return deepcopy(value)
        except HTTPError as exc:
            write(stem + '-result.json', {'at': now(), 'status': exc.code,
                  'request_id': exc.headers.get('x-ms-request-id')})
            if optional and exc.code == 404:
                self.cache[key] = {'absent': True, 'status': 404}
                return deepcopy(self.cache[key])
            raise RuntimeError('readonly_http:' + str(exc.code)) from None

    cli = g.rebound(g.AttemptReader.cli, exclusive=write)


def capture(label):
    """Existing five-IP/settings/security projections; no settings serialization."""
    return g.rebound(old.capture, ReadOnly=ReadOnly, write=write)(label)


def baseline():
    require(not HOME.exists(), 'existing_release_reconcile_only')
    gate = g.worker_gate()
    g.rate.r.fs.protect(HOME)
    write('baseline-intent.json', {'at': now(), 'pid': os.getpid(), 'scope': 'source_tests_plan_only',
          'worker_gate': gate, 'state': state(), 'applies': 0, 'inference': 0, 'builds': 0,
          'protected_sources': protected_sources()})
    g.account()
    baseline_reads()


def baseline_continue01():
    """Original failed locally before transport creation; no capture replay."""
    require(len(list(HOME.glob('baseline-failure-*.json'))) == 1
            and not (HOME / 'reads').exists() and not (HOME / 'current-intent.json').exists(),
            'only_original_pretransport_filename_collision')
    g.worker_gate()
    write('baseline-continuation01-intent.json', {'at': now(), 'pid': os.getpid(),
          'reason': 'local_output_name_collision_before_transport_creation', 'prior_arm_calls': 0,
          'max_captures': 1, 'applies': 0, 'inference': 0})
    baseline_reads()


def baseline_reads():
    snapshot, policy, backends = capture('current')
    require(g.advertised(g.xml_node(policy, exported=True)) == expected21(), 'restored_gateway21_exactset')
    require({v['name'] for v in backends['value']} >= {v[0] for v in g.BACKENDS.values()}, 'reuse_existing_backends')
    transport = ReadOnly('ninth-metadata')
    metadata = transport.get('https://management.azure.com' + rt.RG
        + '/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry/deployments/'
        + NINTH + '?api-version=2025-06-01')
    properties = metadata['properties']
    require(metadata['name'] == NINTH and properties['model'] ==
            {'format': 'Mistral AI', 'name': NINTH, 'version': '1'}
            and metadata['sku']['name'] == 'GlobalStandard' and metadata['sku']['capacity'] == 5000
            and properties['currentCapacity'] == 5000 and properties['provisioningState'] == 'Succeeded'
            and properties['capabilities']['chatCompletion'] == 'true'
            and properties['raiPolicyName'] == 'Microsoft.DefaultV2', 'fresh_exact_ninth_contract')
    write('ninth-metadata.json', metadata)
    write('baseline-complete.json', {'at': now(), 'state': state(), 'snapshot_sha256': digest(snapshot),
          'metadata_sha256': digest(metadata), 'advertised': sorted(expected21()),
          'applies': 0, 'inference': 0, 'builds': 0})
    print(json.dumps({'status': 'FRESH_BASELINE_CAPTURED', 'state': state(), 'metadata_verified': True}), flush=True)


def expected21():
    return set(load(rt.ROOT / 'gateway/catalog/foundry-eight-candidate-routes.json')['routes']) | {'glm-5.3'}


def assert_protected():
    before = load(HOME / 'baseline-intent.json')['protected_sources']
    require(all(digest((rt.ROOT / p).read_bytes()) == h for p, h in before.items()), 'historical_or_held_source_changed')


def execute(label, args, stdin=None):
    require(args[0] in ('fmt', 'validate', 'workspace', 'console', 'plan', 'show', 'version', 'state'), 'NO_APPLY')
    require(args[0] != 'workspace' or args[1:] == ['show'], 'existing_workspace_only')
    require(args[0] != 'state' or args[1:] == ['list'], 'state_read_only')
    argv = [rt.TF, '-chdir=' + str(TFROOT), *args]
    write('commands/' + label + '-intent.json', {'at': now(), 'pid': os.getpid(), 'argv': argv,
          'max_invocations': 1, 'stdin_sha256': digest(stdin.encode()) if stdin else None})
    env = {k: v for k, v in rt.ENV.items() if not k.startswith(('TF_CLI_ARGS', 'TF_LOG', 'ARM_')) and k != 'TF_DATA_DIR'}
    env.update(TF_IN_AUTOMATION='1', CHECKPOINT_DISABLE='1')
    with (HOME / ('commands/' + label + '.stdout.txt')).open('xb') as out, (HOME / ('commands/' + label + '.stderr.txt')).open('xb') as err:
        child = subprocess.Popen(argv, cwd=rt.ROOT, env=env, stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                 stdout=out, stderr=err)
        write('commands/' + label + '-started.json', {'at': now(), 'pid': child.pid, 'controller_pid': os.getpid()})
        child.communicate(stdin.encode() if stdin else None)
    write('commands/' + label + '-result.json', {'at': now(), 'exit_code': child.returncode})
    require(child.returncode == 0, 'command_failed:' + label)
    return (HOME / ('commands/' + label + '.stdout.txt')).read_bytes().decode('utf-8')


def render(label, inputs):
    raw = execute(label, ['console', '-no-color', '-var-file=' + str(inputs)], 'jsonencode(local.policy)\n')
    lines = [line for line in raw.splitlines() if line.startswith('"')]
    require(len(lines) == 1, 'one_console_value')
    return json.loads(json.loads(lines[0]))


def compose():
    require(not CONTEXT.exists(), 'compose_consumed_no_replay')
    assert_protected()
    require(state() == load(HOME / 'baseline-complete.json')['state'], 'current_child_state_exact')
    source = g.HOME / 'context'
    applied = load(old.EVIDENCE / 'verified.json')
    require(digest(old.PLAN.read_bytes()) == old.APPROVED, 'actual_applied_gateway_archive')
    with zipfile.ZipFile(old.PLAN) as archive:
        for name in archive.namelist():
            if name.startswith('tfconfig/m-/'):
                leaf = name.removeprefix('tfconfig/m-/')
                require('/' not in leaf and leaf.endswith('.tf'), 'root_module_only')
                raw = archive.read(name)
                require(raw == (g.TFROOT / leaf).read_bytes(), 'retained_applied_source_exact')
                write('context/infra/project-route/' + leaf, raw)
        write('context/infra/project-route/.terraform.lock.hcl', archive.read('.terraform.lock.hcl'))
    for folder in ('gateway/catalog', 'gateway/policies'):
        for path in (source / folder).rglob('*'):
            if path.is_file():
                write('context/' + path.relative_to(source).as_posix(), path.read_bytes())
    # Apply ONLY reviewed successor hunks to the actual applied source. Pending
    # Auto files/variables/templates are neither copied nor evaluated.
    for leaf in ('main.tf', 'foundry-eight.tf'):
        current = (rt.ROOT / 'infra/project-route' / leaf).read_bytes().decode()
        if leaf == 'main.tf':
            for tag, count in (('rate-limit-by-key', 3), ('llm-token-limit', 2)):
                anchor = f'length(regexall("<{tag}", local.policy)) == (var.auto_routing_enabled ? {count} : 1)'
                require(current.count(anchor) == 1, 'known_held_main_hunk')
                current = current.replace(anchor, f'length(regexall("<{tag}", local.policy)) == 1')
        else:
            require(current.count('!var.auto_routing_enabled && ') == 1 and current.count('local.auto_policy') == 1, 'known_held_profile_hunk')
            current = current.replace('!var.auto_routing_enabled && ', '').replace('local.auto_policy', 'local.glm_policy')
        (TFROOT / leaf).write_bytes(current.encode())
    successor = (rt.ROOT / 'infra/project-route/foundry-successor22.tf').read_bytes()
    require(successor.count(b'!var.auto_routing_enabled && ') == 1, 'successor_explicit_hold_guard')
    write('context/infra/project-route/foundry-successor22.tf', successor.replace(b'!var.auto_routing_enabled && ', b''))
    write('context/' + MANIFEST, (rt.ROOT / MANIFEST).read_bytes())
    require(not any(b'local.auto_' in p.read_bytes() or b'var.auto_' in p.read_bytes() for p in TFROOT.glob('*.tf')), 'NO_AUTO_BINDINGS')
    require(not list(CONTEXT.rglob('*auto*')), 'NO_AUTO_FILES')
    installed = rt.ROOT / 'infra/project-route/.terraform/providers'
    shutil.copytree(installed, TFROOT / '.terraform/providers')
    variables = load(g.HOME / 'inputs.tfvars.json')
    variables['route_manifest_path'] = (CONTEXT / 'gateway/catalog/foundry-eight-candidate-routes.json').as_posix()
    write('historical-inputs.tfvars.json', variables)
    variables = deepcopy(variables)
    variables['route_manifest_path'] = (CONTEXT / MANIFEST).as_posix()
    write('inputs.tfvars.json', variables)
    write('source-composition.json', {'at': now(), 'actual_applied_gateway_plan_sha256': old.APPROVED,
          'retained_applied_verification_sha256': digest((old.EVIDENCE / 'verified.json').read_bytes()),
          'origin': 'actual_applied_gateway21_context_plus_explicit_successor_hunks', 'dirty_auto_copied': False,
          'context': context_hashes()})
    finish_compose('')


def compose_continue01():
    require(load(HOME / 'commands/fmt-result.json')['exit_code'] == 3
            and not (HOME / 'commands/validate-intent.json').exists()
            and not (HOME / 'plan-intent.json').exists(), 'original_only_formatter_failed')
    write('compose-continuation01-intent.json', {'at': now(), 'pid': os.getpid(),
          'reason': 'two_reviewed_formatter_only_source_corrections', 'new_plans': 0,
          'applies': 0, 'inference': 0, 'recompositions': 0})
    finish_compose('continuation01-')


def finish_compose(prefix):
    execute(prefix + 'fmt', ['fmt', '-check', '-no-color'])
    execute(prefix + 'validate', ['validate', '-json'])
    require(execute(prefix + 'workspace', ['workspace', 'show']).strip() == 'default', 'default_workspace')
    historical = render(prefix + 'historical-render', HOME / 'historical-inputs.tfvars.json')
    active = (HOME / 'current-policy.xml').read_bytes().decode()
    require(g.structural(g.xml_node(historical)) == g.structural(g.xml_node(active, exported=True)), 'whole_actual_gateway21_predecessor')
    desired = render(prefix + 'candidate-render', HOME / 'inputs.tfvars.json')
    write('candidate-policy.xml', desired.encode())
    review = policy_guard(active, desired)
    write('prepared.json', {'at': now(), 'status': 'PREPARED_NO_APPLY_NO_INFERENCE', 'state': state(),
          'context': context_hashes(), 'sources': source_hashes(), 'policy_review': review})
    print(json.dumps({'status': 'PREPARED', 'policy_review': review}), flush=True)


def context_hashes():
    return g.hashes(p for p in CONTEXT.rglob('*') if p.is_file() and '.terraform' not in p.parts)


def source_hashes():
    paths = [Path(__file__), rt.ROOT / MANIFEST, rt.ROOT / 'infra/project-route/main.tf',
             rt.ROOT / 'infra/project-route/foundry-eight.tf', rt.ROOT / 'infra/project-route/foundry-successor22.tf']
    paths += list((rt.ROOT / 'services/usage-ingestion').glob('*successor*.py'))
    paths += [rt.ROOT / 'services/usage-ingestion/accepted_catalog_profile.py']
    paths += list((rt.ROOT / 'tests').rglob('*successor22*'))
    return g.hashes(p for p in paths if p.is_file())


def policy_guard(previous, desired):
    before, after = g.xml_node(previous, exported=True), g.xml_node(desired)
    require(g.advertised(before) == expected21() and g.advertised(after) == expected21() | {NINTH}, 'exact_21_to_22_sets')
    for tag in ('cors', 'quota-by-key', 'rate-limit-by-key', 'llm-token-limit', 'llm-content-safety',
                'send-request', 'forward-request', 'include-fragment', 'authentication-managed-identity'):
        require([g.structural(n) for n in before.findall('.//' + tag)] ==
                [g.structural(n) for n in after.findall('.//' + tag)], 'protected_policy_nodes:' + tag)
    for alias in expected21() - {'glm-5.3'}:
        condition = '@((string)context.Variables["aiflux-model"] == "' + alias + '")'
        old_branches = [g.structural(n) for n in before.findall('./inbound//when') if n.get('condition') == condition]
        new_branches = [g.structural(n) for n in after.findall('./inbound//when') if n.get('condition') == condition]
        require(old_branches and old_branches == new_branches, 'old_dispatch_changed:' + alias)
    # Normalize only the new alias's additive catalog, allowlist, limit and
    # dispatch hunks; the remaining whole policy must be structurally identical.
    projection = re.sub(r'<when condition=\'@\(\(string\)context.Variables\["aiflux-model"\] == "mistral-medium-3-5"\)\'>.*?</when>', '', desired, flags=re.S)
    # Full byte delta is retained for independent parent inspection as well.
    require(len(after.findall('.//forward-request')) == 1 and not after.findall('.//retry')
            and not after.findall('.//include-fragment'), 'one_forward_no_retry_no_fragment')
    branch = [n for n in after.findall('./inbound//when') if n.get('condition') ==
        '@((string)context.Variables["aiflux-model"] == "' + NINTH + '")' and n.find('set-backend-service') is not None]
    require(len(branch) == 1 and branch[0].find('set-backend-service').get('backend-id') ==
            'aiflux-project-foundry-eight-mistral', 'reuse_exact_current_mistral_backend')
    require(('if ((string)request["model"] == "' + NINTH + '") { request["max_tokens"] = request["max_completion_tokens"]; request.Remove("max_completion_tokens"); }') in desired, 'ninth_max_tokens_conversion')
    for selector in ('.//set-body[@id="aiflux-anthropic-normalization"]', './/set-variable[@name="aiflux-finops-usage"]'):
        require([g.structural(n) for n in before.findall(selector)] == [g.structural(n) for n in after.findall(selector)], 'normalizer_or_usage_changed')
    require([g.structural(n) for n in before.findall('.//set-header')] ==
            [g.structural(n) for n in after.findall('.//set-header')], 'credential_header_contract_changed')
    return {'old21_preserved': True, 'expected_aliases': sorted(expected21() | {NINTH}),
            'ninth_backend_reused': True, 'new_backends': 0, 'forwards': 1, 'retries': 0,
            'safety_PII_auth_CORS_counters_exact': True, 'accepted_ninth': False}


def plan_guard(data, previous, desired):
    require(data.get('applyable') and not data.get('errored') and not data.get('deferred_changes'), 'usable_saved_plan')
    variables = {k: v['value'] for k, v in data['variables'].items()}
    explicit = load(HOME / 'inputs.tfvars.json')
    require(all(variables[k] == v for k, v in explicit.items()) and not any('auto_' in k for k in variables), 'exact_inputs_no_auto')
    writes = [r for r in data['resource_changes'] if r['change']['actions'] not in (['no-op'], ['read'])]
    require(len(writes) == 1 and writes[0]['address'] == POLICY and writes[0]['mode'] == 'managed'
            and writes[0]['change']['actions'] == ['update'], 'ONLY_EXISTING_APIM_POLICY_UPDATE')
    change = writes[0]['change']
    before, after = deepcopy(change['before']), deepcopy(change['after'])
    props = before['body']['properties']
    require(props.get('format') in ('xml', 'rawxml'), 'known_export_format')
    require((props['value'] == previous if props['format'] == 'xml' else
        g.structural(g.xml_node(props['value'])) == g.structural(g.xml_node(previous, exported=True))), 'fresh_saved_predecessor')
    require(after['body'] == {'properties': {'format': 'rawxml', 'value': desired}}, 'exact_candidate_policy_body')
    require(not any(g.unknown(v) for k, v in change.get('after_unknown', {}).items() if k not in ('output', 'id')), 'no_unknown_writes')
    after['body'], after['output'] = before['body'], before.get('output')
    require(before == after, 'no_nonpolicy_attribute_change')
    require(all(r['mode'] == 'data' for r in data['resource_changes'] if r['change']['actions'] == ['read']), 'managed_read_rejected')
    require(not any('auto_stage' in r['address'] for r in data['resource_changes']), 'held_auto_not_in_graph')
    policy_guard(previous, desired)
    return [{'address': POLICY, 'actions': ['update']}]


def plan():
    assert_protected()
    prepared = load(HOME / 'prepared.json')
    require(source_hashes() == prepared['sources'] and context_hashes() == prepared['context']
            and state() == prepared['state'], 'source_context_state_binding')
    g.worker_gate()
    current, previous, _ = capture('preplan')
    require(current == load(HOME / 'current-snapshot.json'), 'fresh_current_baseline_exact')
    write('plan-intent.json', {'at': now(), 'pid': os.getpid(), 'state': state(), 'max_plans': 1,
          'targets': [POLICY], 'applies': 0, 'inference': 0, 'builds': 0})
    execute('plan-once', ['plan', '-input=false', '-no-color', '-lock-timeout=30s',
        '-state=' + str(g.OWNER), '-var-file=' + str(HOME / 'inputs.tfvars.json'),
        '-target=' + POLICY, '-out=' + str(PLAN)])
    data = json.loads(execute('show', ['show', '-json', str(PLAN)]))
    write('plan.json', data)
    changes = plan_guard(data, previous, (HOME / 'candidate-policy.xml').read_bytes().decode())
    with zipfile.ZipFile(PLAN) as archive:
        expected = {'tfconfig/m-/' + p.name: p.read_bytes() for p in TFROOT.glob('*.tf')}
        require({n for n in archive.namelist() if n.startswith('tfconfig/m-/')} == set(expected)
                and all(archive.read(k) == v for k, v in expected.items()), 'saved_source_exact')
    after, _, _ = capture('postplan')
    require(after == current and state() == prepared['state'] and source_hashes() == prepared['sources']
            and context_hashes() == prepared['context'], 'postplan_all_bindings_exact')
    assert_protected()
    write('review.json', {'at': now(), 'status': 'SAVED_POLICY_ONLY_PLAN_PENDING_OFFICIAL_VALIDATION',
          'plan_sha256': digest(PLAN.read_bytes()), 'plan_json_sha256': digest((HOME / 'plan.json').read_bytes()),
          'state': state(), 'changes': changes, 'change_counts': {'create': 0, 'update': 1, 'delete': 0},
          'sources': prepared['sources'], 'context': prepared['context'], 'protected_baseline_equal': True,
          'checks': data.get('checks'), 'applies': 0, 'inference': 0, 'builds': 0,
          'independent_parent_review_performed': False, 'accepted_ninth': False})
    print(json.dumps({'status': 'SAVED_POLICY_ONLY_PLAN', 'plan_sha256': digest(PLAN.read_bytes()), 'changes': changes}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('baseline', 'baseline_continue01', 'compose', 'compose_continue01', 'plan'))
    args = parser.parse_args()
    try:
        globals()[args.stage]()
    except Exception as exc:
        if HOME.exists():
            write(args.stage + '-failure-' + str(os.getpid()) + '.json', {'at': now(), 'pid': os.getpid(),
                  'error_type': type(exc).__name__, 'reason': str(exc)[:300], 'replay_permitted': False})
        raise


if __name__ == '__main__':
    main()