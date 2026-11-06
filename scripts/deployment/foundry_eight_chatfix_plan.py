"""ONE new source-bound API-only saved plan. NO apply/build/SQL/inference API."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from scripts.deployment import foundry_eight_chatfix_prepare as fix
from scripts.deployment import foundry_eight_runtime_plan as p
from scripts.deployment import foundry_eight_runtime_apply as a

HOME = fix.HOME / 'api-only-plan'
ROOT = HOME / 'infra/terraform'
PLAN = HOME / 'api-only.tfplan'
PREVIOUS = p.rt.HOME / 'foundry-eight-runtime-apply-20261031-successor01'
TARGET = 'azurerm_linux_web_app.main["api"]'
LINEAGE = 'b05cbf70-2d31-0e6e-34b7-c97e8f617ed6'
require, sha, load, now = p.require, p.sha, p.load, p.now
rebound = p.gateway.rebound


def write(name, value):
    path = HOME / name
    require(path.resolve().is_relative_to(HOME.resolve()), 'owned_output_only')
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (value.encode() if isinstance(value, str) else
        (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
    with path.open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def execute(label, argv, stdin=None, timeout=1800):
    write('commands/' + label + '-intent.json', {'at': now(), 'pid': os.getpid(), 'argv': argv,
          'stdin_sha256': sha(stdin.encode()) if stdin else None})
    child = subprocess.run(argv, cwd=p.rt.ROOT, env=p.rt.ENV, input=stdin, capture_output=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
    write('commands/' + label + '.stdout.txt', child.stdout)
    write('commands/' + label + '.stderr.txt', child.stderr)
    write('commands/' + label + '-result.json', {'at': now(), 'exit_code': child.returncode})
    require(child.returncode == 0, 'command_failed_private_receipt:' + label)
    print(json.dumps({'at': now(), 'command': label, 'exit_code': 0}), flush=True)
    return child.stdout


def terraform(label, *args, stdin=None):
    require(args and args[0] in ('init', 'workspace', 'state', 'validate', 'fmt', 'plan', 'show', 'console'), 'NO_APPLY')
    require(args[0] != 'state' or args[1:] == ('pull',), 'state_read_only')
    require(args[0] != 'workspace' or args[1:] == ('show',), 'existing_workspace_only')
    require(not any(k.startswith('TF_CLI_ARGS') for k in os.environ) and
            not any(k.startswith('TF_CLI_ARGS') for k in p.rt.ENV), 'no_hidden_cli_arguments')
    if args[0] == 'plan':
        require(label == 'plan-once' and not PLAN.exists() and load(HOME / 'plan-intent.json')['max_plans'] == 1, 'ONE_NEW_PLAN')
    return execute(label, [p.rt.TF, '-chdir=' + str(ROOT), *args], stdin)


class ReadOnly(a.ReadOnly):
    request = rebound(p.gateway.AttemptReader.request, exclusive=write)
    cli = rebound(p.gateway.AttemptReader.cli, exclusive=write)
    __init__ = rebound(a.ReadOnly.__init__, write=write)


def capture(label):
    operation = rebound(p.gateway_apply.capture, ReadOnly=ReadOnly, write=write)
    snapshot, policy, backends = operation(label)
    previous = load(PREVIOUS / 'postapply-snapshot.json')
    require(snapshot == previous, 'full_actual_current_four_pins_and_protected_state_exact')
    require(policy.encode() == (PREVIOUS / 'postapply-policy.xml').read_bytes(), 'gateway21_policy_exact')
    require({v['name']: sha(v) for v in backends['value']} == load(PREVIOUS / 'postapply-backend-hashes.json'), 'all_backends_exact')
    require(sha(p.gateway.OWNER.read_bytes()) == load(p.GATEWAY / 'verified.json')['state']['sha256'], 'gateway_separate_state_exact')
    return snapshot


def source_files():
    return {f.relative_to(p.rt.ROOT).as_posix(): sha(f.read_bytes()) for base in (HOME / 'infra', HOME / 'gateway')
            for f in base.rglob('*') if f.is_file() and '.terraform' not in f.parts} | {
        (HOME / 'inputs.tfvars.json').relative_to(p.rt.ROOT).as_posix(): sha((HOME / 'inputs.tfvars.json').read_bytes())}


def compose():
    previous = load(PREVIOUS / 'final-report.json')
    require(previous['status'] == 'APPLIED_ONCE_INDEPENDENT_LOCAL_AUDIT_PASS' and previous['state_serial'] == 118,
            'current_applied118_receipt')
    require(sha(p.PLAN.read_bytes()) == previous['plan_sha256'], 'actual_applied_four_image_archive')
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(p.PLAN) as archive:
        for name in archive.namelist():
            if name.startswith('tfconfig/m-/'):
                leaf = name.removeprefix('tfconfig/m-/')
                require('/' not in leaf and leaf.endswith(('.tf', '.tf.json')), 'actual_root_config_only')
                require(archive.read(name) == (p.ROOT / leaf).read_bytes(), 'applied_archived_source_exact')
                write('infra/terraform/' + leaf, archive.read(name))
        write('infra/terraform/.terraform.lock.hcl', archive.read('.terraform.lock.hcl'))
    for folder in ('infra/models', 'gateway'):
        for file in (p.HOME / folder).rglob('*'):
            if file.is_file():
                write(file.relative_to(p.HOME).as_posix(), file.read_bytes())
    variables = load(p.HOME / 'inputs.tfvars.json')
    image = load(fix.HOME / 'build-result.json')['image']
    require(variables['apps']['api']['image'] == 'aiflux-api@sha256:' + fix.PIN, 'current_api_input_pin')
    variables['apps']['api']['image'] = image.split('/', 1)[1]
    write('inputs.tfvars.json', variables)
    write('source-composition.json', {'at': now(), 'origin_applied_plan_sha256': previous['plan_sha256'],
        'source': 'actual_applied_four_image_archive_plus_API_input_pin_only', 'dirty_tree_copied': False,
        'unchanged_other_images': {k: v for k, v in previous['current_pins'].items() if k != 'api'},
        'build_receipt_sha256': sha((fix.HOME / 'build-result.json').read_bytes())})


def module(path):
    spec = importlib.util.spec_from_file_location('retained_predicate_parser', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def console_proof(data):
    parser = module(p.HOME / 'validation-continuation-01/guard.py')
    predicates = parser.predicates(ROOT)
    validations = [r for r in predicates if r['kind'] == 'validation']
    bindings = []
    for key in sorted(data['variables']):
        saved = data['variables'][key]['value']
        encoded = base64.b64encode(json.dumps(saved, separators=(',', ':')).encode()).decode()
        if key == 'local_auth':
            optional = ['bootstrap_admin_password_uri', 'bootstrap_customer_password_uri', 'bootstrap_admin_email',
                        'bootstrap_customer_email', 'bootstrap_customer_org']
            require(set(saved) == {'jwt_secret_uri'}, 'saved_local_auth_required_field_only')
            expression = ('length(keys(var.local_auth))==6 && alltrue([for k in ' + json.dumps(optional) +
                ' : contains(keys(var.local_auth),k) && var.local_auth[k]==null]) && ' +
                'jsonencode({jwt_secret_uri=var.local_auth.jwt_secret_uri})==jsonencode(jsondecode(base64decode("' + encoded + '")))')
        else:
            expression = 'jsonencode(var.' + key + ')==jsonencode(jsondecode(base64decode("' + encoded + '")))'
        bindings.append(json.dumps(key) + '=(' + expression + ')')
    inactive = {'azapi_resource.dev_anthropic_backend': 'var.dev_unified_inference_enabled ? 1 : 0',
        'azapi_resource.gateway_settings': 'length(local.gateway_settings_scopes)',
        'azurerm_api_management_api.dev_unified': 'var.dev_unified_inference_enabled ? 1 : 0',
        'terraform_data.dev_openai_gate': 'var.dev_openai_inference_enabled ? 1 : 0',
        'terraform_data.sql_firewall_gate': 'local.public_edge_stage && !var.hybrid_private_data_enabled ? 1 : 0'}
    expression = ('nonsensitive(jsonencode({conditions=[' + ','.join('(' + r['expression'] + ')' for r in validations) +
        '],bindings={' + ','.join(bindings) + '},inactive_counts={' +
        ','.join(json.dumps(k) + '=(' + v + ')' for k, v in inactive.items()) + '}}))')
    require('\n' not in expression and '\r' not in expression, 'single_line_console')
    raw = terraform('exact-input-console', 'console', '-lock=false', '-no-color', '-var-file=' + str(HOME / 'inputs.tfvars.json'), stdin=expression + '\n')
    payload = [line for line in raw.splitlines() if line.startswith('"{')]
    require(len(payload) == 1, 'sole_json_console_payload')
    value = json.loads(json.loads(payload[0]))
    require(value['conditions'] == [True] * len(validations) and all(v is True for v in value['bindings'].values())
            and set(value['bindings']) == set(data['variables']) and value['inactive_counts'] == {k: 0 for k in inactive},
            'all_actual_predicates_inputs_and_inactive_counts_proven')
    proof = {**value, 'at': now(), 'plan_json_sha256': sha((HOME / 'plan.json').read_bytes()),
        'all_conditions_true': True, 'local_auth': 'exact_required_value_plus_five_typed_nulls_no_extra_keys'}
    write('input-proof.json', proof)
    write('predicate-inventory.json', predicates)
    return proof


def guard(data, image, proof):
    require(data.get('applyable') is True and not data.get('errored') and not data.get('deferred_changes')
            and not data.get('resource_drift'), 'resolved_no_drift_plan')
    changes, noops = [], []
    for row in data.get('resource_changes', []):
        c = row['change']
        require(not row.get('deposed') and not c.get('importing') and not c.get('generated_config') and
                not c.get('replace_paths') and not c.get('after_unknown'), 'no_import_replace_or_unknown')
        if c['actions'] == ['no-op']:
            require(c['before'] == c['after'], 'dependency_exact')
            noops.append(row['address'])
            continue
        require(row['mode'] == 'managed' and row['address'] == TARGET and c['actions'] == ['update'] and not changes,
                'EXACT_ONE_API_UPDATE_ONLY')
        old, new = deepcopy(c['before']), deepcopy(c['after'])
        rid = p.rt.RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-api'
        require(old['id'] == new['id'] == rid and old['name'] == new['name'] == 'poc-ids-token-ex-api', 'existing_api_id')
        require(len(old['site_config']) == len(new['site_config']) == 1, 'single_config')
        x, y = old['site_config'][0]['application_stack'], new['site_config'][0]['application_stack']
        require(len(x) == len(y) == 1 and x[0]['docker_image_name'] == 'aiflux-api@sha256:' + fix.PIN and
                y[0]['docker_image_name'] == image.split('/', 1)[1] and
                y[0]['docker_registry_url'] == 'https://' + fix.b.HOST, 'exact_predecessor_target_API_digest')
        y[0]['docker_image_name'] = x[0]['docker_image_name']
        require(old == new and c['before'] != c['after'], 'all_nonimage_leaves_equal')
        changes.append({'address': TARGET, 'only_changed_leaf': 'site_config[0].application_stack[0].docker_image_name',
            'before': fix.b.HOST + '/aiflux-api@sha256:' + fix.PIN, 'after': image})
    require(len(changes) == 1, 'ONE_API_PIN_REQUIRED')
    require(all(v['actions'] == ['no-op'] and v.get('before') == v.get('after') and not v.get('after_unknown')
                for v in data.get('output_changes', {}).values()), 'outputs_unchanged')
    checks = []
    for c in data.get('checks', []):
        require(c['status'] in ('pass', 'unknown') and all(i['status'] == 'pass' for i in c.get('instances', [])), 'no_failed_checks')
        address = c['address']['to_display']
        disposition = 'native_pass'
        if c['status'] == 'unknown':
            if c['address']['kind'] == 'var':
                require(proof['all_conditions_true'], 'actual_input_predicates_required')
                disposition = 'archived_predicates_true_exact_saved_inputs'
            else:
                require(address in proof['inactive_counts'] and proof['inactive_counts'][address] == 0 and not c.get('instances'),
                        'unknown_resource_must_be_proven_zero_instances')
                disposition = 'not_evaluated_zero_instances_NOT_claimed_pass'
        checks.append({'address': address, 'saved_status': c['status'], 'disposition': disposition})
    require(checks, 'checks_required')
    return {'changes': changes, 'counts': {'create': 0, 'update': 1, 'delete': 0, 'replace': 0, 'no_op': len(noops)},
            'checks': checks, 'unchanged_dependencies': noops}


def normalized(value):
    value = deepcopy(value)
    if value.get('check_results') is not None:
        require(len({(v['object_kind'], v['config_addr']) for v in value['check_results']}) == len(value['check_results']), 'unique_checks')
        value['check_results'] = sorted(value['check_results'], key=lambda v: (v['object_kind'], v['config_addr']))
    return value


def plan():
    require(not HOME.exists(), 'new_plan_stage_exclusive_never_replay')
    p.fs.protect(HOME)
    write('run-intent.json', {'at': now(), 'pid': os.getpid(), 'max_plans': 1, 'applies': 0,
        'authorization': 'user_API_only_saved_plan_prepare_NOT_APPLY', 'controller_sha256': sha(Path(__file__).read_bytes())})
    write('workers-before.json', p.gateway.worker_gate())
    account = json.loads(execute('account', p.rt.CLI + ['account', 'show', '--subscription', p.rt.SUB, '-o', 'json']))
    require(account['id'] == p.rt.SUB and account['tenantId'] == p.rt.TENANT and account['state'] == 'Enabled', 'account_scope')
    build = load(fix.HOME / 'build-result.json')
    run = json.loads(execute('acr-original-build', p.rt.CLI + ['acr', 'task', 'show-run', '--registry', fix.b.REGISTRY,
        '--subscription', p.rt.SUB, '--run-id', build['run_id'], '-o', 'json']))
    metadata = json.loads(execute('acr-digest', p.rt.CLI + ['acr', 'manifest', 'show-metadata', '--registry', fix.b.REGISTRY,
        '--subscription', p.rt.SUB, '--name', 'aiflux-api@' + build['digest'], '-o', 'json']))
    require(run['status'] == 'Succeeded' and run['platform']['os'] == 'linux' and metadata['digest'] == build['digest']
            and run['outputImages'][0]['digest'] == build['digest'], 'actual_registry_build_source_binding')
    before = capture('preplan')
    compose()
    terraform('init', 'init', '-input=false', '-lockfile=readonly', '-no-color', '-backend-config=' + str(p.rt.ROOT / 'infra/terraform/backend.hcl'))
    require(terraform('workspace', 'workspace', 'show').strip() == 'default', 'existing_default_workspace')
    backend = load(ROOT / '.terraform/terraform.tfstate')['backend']
    cfg = backend['config']
    require(backend['type'] == 'azurerm' and cfg['key'] == 'poc-ids-token-ex/main.tfstate' and
            cfg['storage_account_name'] == 'projpoctokenex' and cfg['container_name'] == 'tfstate' and
            cfg['use_azuread_auth'] is True, 'existing_main_state_owner')
    before_state = json.loads(terraform('state-before', 'state', 'pull'))
    require(before_state['serial'] == 118 and before_state['lineage'] == LINEAGE, 'actual_current118_main_lineage')
    terraform('fmt', 'fmt', '-check', '-no-color')
    valid = json.loads(terraform('validate', 'validate', '-json'))
    require(valid['valid'] and valid['error_count'] == 0, 'actual_validate')
    context = source_files()
    write('plan-context.json', context)
    write('plan-intent.json', {'at': now(), 'max_plans': 1, 'max_applies': 0, 'target': TARGET,
        'context_sha256': sha(context), 'state_serial': 118, 'state_lineage': LINEAGE, 'image': build['image']})
    terraform('plan-once', 'plan', '-input=false', '-no-color', '-lock-timeout=60s', '-parallelism=1',
        '-var-file=' + str(HOME / 'inputs.tfvars.json'), '-target=' + TARGET, '-out=' + str(PLAN))
    raw = terraform('show-plan', 'show', '-json', str(PLAN))
    write('plan.json', raw)
    data = json.loads(raw)
    proof = console_proof(data)
    report = guard(data, build['image'], proof)
    after_state = json.loads(terraform('state-after', 'state', 'pull'))
    require(normalized(before_state) == normalized(after_state), 'all_remote_state_fields_unchanged_only_check_order_normalized')
    require(capture('postplan') == before, 'all_protected_state_unchanged')
    require(source_files() == context, 'exact_source_bound_context')
    write('review.json', {**report, 'at': now(), 'status': 'ONE_API_PIN_SAVED_NOT_APPLIED_PARENT_AUDIT_PENDING',
        'plan_sha256': sha(PLAN.read_bytes()), 'plan_json_sha256': sha((HOME / 'plan.json').read_bytes()),
        'context_sha256': sha(context), 'controller_sha256': sha(Path(__file__).read_bytes()),
        'state_serial': 118, 'state_lineage': LINEAGE, 'image': build['image'], 'applies': 0, 'DB_sync': 0,
        'inference': 0, 'other_image_builds': 0, 'Auto': 'HOLD', 'protected_snapshot_unchanged': True,
        'remote_state_unchanged': True, 'source_composition_sha256': sha((HOME / 'source-composition.json').read_bytes())})
    print(json.dumps(load(HOME / 'review.json')), flush=True)


def audit():
    review = load(HOME / 'review.json')
    require(sha(PLAN.read_bytes()) == review['plan_sha256'] and sha((HOME / 'plan.json').read_bytes()) == review['plan_json_sha256'], 'saved_hashes_exact')
    require(source_files() == load(HOME / 'plan-context.json'), 'source_context_exact')
    data = load(HOME / 'plan.json')
    report = guard(data, load(fix.HOME / 'build-result.json')['image'], load(HOME / 'input-proof.json'))
    require(report['changes'] == review['changes'], 'actual_saved_onepin_review')
    with zipfile.ZipFile(PLAN) as archive:
        sources = {'tfconfig/m-/' + f.name: f.read_bytes() for f in ROOT.iterdir() if f.is_file() and f.name.endswith(('.tf', '.tf.json'))}
        require({n for n in archive.namelist() if n.startswith('tfconfig/m-/')} == set(sources) and
                all(archive.read(n) == v for n, v in sources.items()) and
                archive.read('.terraform.lock.hcl') == (ROOT / '.terraform.lock.hcl').read_bytes(), 'embedded_actual_source_and_lock')
        state = json.loads(archive.read('tfstate'))
        require(state['serial'] == 118 and state['lineage'] == LINEAGE, 'embedded118_owner')
    write('audit.json', {'at': now(), 'passed': True, 'plan_sha256': review['plan_sha256'],
        'one_API_pin_only': True, 'embedded_source_exact': True, 'applies': 0})
    print(json.dumps(review), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'audit'))
    args = parser.parse_args()
    try:
        plan() if args.action == 'plan' else audit()
    except Exception as exc:
        if HOME.exists():
            write('failure-' + now().replace(':', '').replace('.', '') + '.json', {'at': now(),
                'type': type(exc).__name__, 'reason': str(exc) if isinstance(exc, RuntimeError) else 'private_receipt',
                'replay': False, 'applies': 0})
        raise


if __name__ == '__main__':
    main()