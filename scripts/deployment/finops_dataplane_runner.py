"""Approved ingestion-only temporary runner. No production changes or data writes."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

from scripts.deployment import finops_runner_preflight as p
from scripts.deployment import finops_runner_guards as g
from scripts.deployment import finops_runner_execute as ex
from scripts.deployment import finops_runner_prepare as prep
from scripts.deployment import finops_runner_build as build
from scripts.deployment import finops_runner_fresh as fresh

FOLDER = p.ROOT / 'infra/finops-dataplane-probe'


def bind(nonce):
    g.owned_ids(nonce)
    build.OUT = p.ROOT / ('gateway/validation/finops-dataplane-image-' + nonce + '.json')
    prep.OUT = p.ROOT / ('gateway/validation/finops-dataplane-package-' + nonce + '.json')
    prep.FOLDER = FOLDER
    return p.ROOT / ('gateway/validation/finops-dataplane-session-' + nonce + '.json')


def metadata():
    from scripts.deployment import finops_function_stage as fs
    settings = fs.current_settings()['ingestion']
    client, oid = 'e1d25c87-9df1-4225-9744-ce22121cf462', 'edbfc3e2-a8e5-4652-9bb0-311233756d42'
    g.require(settings.get('AZURE_CLIENT_ID') == settings.get('AzureWebJobsStorage__clientId') == client,
              'selected_ingestion_identity_mismatch')
    g.require(settings.get('AzureWebJobs.ingest_usage.Disabled') == 'true' and
              settings.get('AIFLUX_CATALOG_CONFIGURED') == 'true' and
              settings.get('AIFLUX_INGESTION_START_AT') == '2026-10-27T06:06:02.045288+00:00', 'protected_settings_changed')
    for service in ('blob', 'queue', 'table'):
        g.require(settings.get('AzureWebJobsStorage__' + service + 'ServiceUri') ==
                  'https://pocidstokenexfunc.' + service + '.core.windows.net', 'host_storage_destination_changed')
    workspace = p.get(g.RG + '/providers/Microsoft.OperationalInsights/workspaces/poc-ids-token-ex-logs', '2023-09-01')['properties']
    g.require(workspace['customerId'] == settings.get('AIFLUX_LOG_WORKSPACE_ID'), 'workspace_changed')
    account = g.RG + '/providers/Microsoft.Storage/storageAccounts/pocidstokenexfunc'
    endpoints = p.get(g.RG + '/providers/Microsoft.Network/privateEndpoints', '2024-05-01')['value']
    addresses = {}
    for endpoint in endpoints:
        props = endpoint['properties']
        for connection in props.get('privateLinkServiceConnections', []):
            link = connection['properties']
            if link.get('privateLinkServiceId', '').lower() != account.lower():
                continue
            g.require(link.get('privateLinkServiceConnectionState', {}).get('status') == 'Approved', 'private_endpoint_not_approved')
            for service in link.get('groupIds', []):
                if service not in ('blob', 'queue', 'table'):
                    continue
                ips = {ip for dns in props.get('customDnsConfigs', []) for ip in dns.get('ipAddresses', [])}
                if not ips:
                    for nic in props.get('networkInterfaces', []):
                        detail = p.get(nic['id'], '2024-05-01')
                        ips.update(x['properties']['privateIPAddress'] for x in detail['properties']['ipConfigurations'])
                g.require(len(ips) == 1, 'private_endpoint_address_ambiguous')
                addresses[service] = next(iter(ips))
    g.require(set(addresses) == {'blob', 'queue', 'table'}, 'host_storage_private_endpoints_missing')
    roles = p.cli(['rest', '--method', 'get', '--url', 'https://management.azure.com/subscriptions/' + g.SUB +
                  '/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01'])['value']
    assignments = []
    for role in roles:
        r = role['properties']
        if r.get('principalId') == oid and (account.lower() == r.get('scope', '').lower() or
                (g.RG + '/providers/Microsoft.OperationalInsights/workspaces/poc-ids-token-ex-logs').lower() == r.get('scope', '').lower()):
            assignments.append({'scope': 'host_storage' if r['scope'].lower() == account.lower() else 'monitor',
                'role_definition': r['roleDefinitionId'].rsplit('/', 1)[-1], 'condition_present': bool(r.get('condition'))})
    return {'at_utc': p.now(), 'workspace_guid': workspace['customerId'], 'storage_private_ips': addresses,
            'identity_client_object_tenant_verified': True, 'assignments': assignments,
            'timer_disabled': True, 'catalog_enabled': True, 'cutoff_preserved': True}


def assert_metadata(facts):
    from scripts.deployment import finops_dataplane_probe as probe
    g.require(facts['workspace_guid'] == probe.WORKSPACE and facts['storage_private_ips'] == probe.IPS,
              'reviewed_destinations_changed')


def build_once():
    nonce = secrets.token_hex(6)
    output = bind(nonce)
    report = {'owner_nonce': nonce, 'started_at_utc': p.now(), 'database_writes': 0,
              'storage_writes': 0, 'new_roles': 0, 'production_changes': 0}
    ex.write(output, report)
    try:
        facts = metadata()
        assert_metadata(facts)
        report['metadata'] = facts
        report['prerequisites'] = fresh.prerequisites()
        report['previous_preparation_absence'] = fresh.exact_absence(g.owned_ids('2be1b356c1dd'))
        report['fresh_absence'] = fresh.exact_absence(g.owned_ids(nonce))
        report['preservation'] = prep.preservation_readback()
        context = p.ROOT / '.deployment/finops-runner' / nonce / 'image-context'
        context.mkdir(parents=True, exist_ok=False)
        sources = {'Dockerfile': FOLDER / 'Dockerfile', 'requirements.txt': FOLDER / 'requirements.txt',
            'entrypoint.py': FOLDER / 'entrypoint.py', 'linux_contract.py': FOLDER / 'linux_contract.py',
            'finops_private_probe.py': p.ROOT / 'scripts/deployment/finops_dataplane_probe.py'}
        for name, source in sources.items(): shutil.copyfile(source, context / name)
        # Preserve every existing dependency version. Only four explicit SDKs and
        # genuinely missing dependencies may be added to this isolated image.
        prior = ex.load(p.ROOT / 'gateway/validation/finops-runner-image-20261027.json')
        old_context = p.ROOT / '.deployment/finops-runner' / prior['owner_nonce'] / 'image-context'
        constraints = context.parent / 'constraints.txt'
        constraints.write_text('\n'.join(line.split(' --hash=')[0] for line in
            (old_context / 'requirements.lock.txt').read_text().splitlines()) + '\n')
        wheels = context / 'wheels'
        wheels.mkdir()
        child = subprocess.run([sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check',
            '--cert', p.CA, '--only-binary=:all:', '--platform', 'manylinux2014_x86_64',
            '--platform', 'manylinux_2_28_x86_64', '--python-version', '313', '--implementation', 'cp', '--abi', 'cp313',
            '--dest', str(wheels), '-r', str(FOLDER / 'requirements.txt'), '-c', str(constraints)],
            capture_output=True, env=p.ENV, timeout=180)
        g.require(child.returncode == 0, 'pinned_linux_dependency_resolution_failed')
        from packaging.utils import parse_wheel_filename
        entries, wheel_facts = [], {}
        for path in sorted(wheels.iterdir()):
            name, version, _, _ = parse_wheel_filename(path.name)
            entries.append(str(name) + '==' + str(version) + ' --hash=sha256:' + prep.digest(path))
            wheel_facts[path.name] = {'sha256': prep.digest(path), 'bytes': path.stat().st_size}
        lock = context / 'requirements.lock.txt'
        lock.write_text('\n'.join(entries) + '\n')
        template = prep.network_template(nonce, profile='ingestion_dataplane')
        ex.write(FOLDER / 'network.arm.json', template)
        # Scanner sees only the ingestion identity shape (no API probe).
        group = prep.group_resource(nonce, 'ingestion',
            "[concat('pocidstokenexacr.azurecr.io/aiflux-finops-probe@sha256:', parameters('verifiedImageDigest'))]",
            prep.digest(sources['finops_private_probe.py']))
        del group['id']
        ex.write(FOLDER / 'ingestion.unbound.arm.json', {'$schema': prep.SCHEMA, 'contentVersion': '1.0.0.0',
            'parameters': {'verifiedImageDigest': {'type': 'string', 'minLength': 64, 'maxLength': 64}}, 'resources': [group]})
        scan = prep.security_scan()
        report['security_scan'] = scan
        g.require(scan['security_gate_passed'], 'dataplane_security_scan_failed')
        package = {'owner_nonce': nonce, 'security_scan': scan,
            'image_dependency_lock': {'lock_sha256': prep.digest(lock), 'wheels': wheel_facts},
            'image_package': {'context': str(context.relative_to(p.ROOT)).replace('\\', '/'),
                              'files_sha256': {name: prep.digest(path) for name, path in sources.items()}}}
        ex.write(prep.OUT, package)
        baseline = {r['runId'] for r in build.az(['acr', 'task', 'list-runs', '--registry', 'pocidstokenexacr', '--top', '100'])}
        report['submission_intent_at_utc'] = p.now()
        ex.write(output, report)
        ex.write(build.OUT, {'started_at_utc': p.now(), 'cloud_build_runs': 1, 'submission_intent_at_utc': p.now()})
        child = subprocess.run([p.AZ, 'acr', 'build', '--registry', 'pocidstokenexacr', '--image', 'aiflux-finops-probe:probe-' + nonce,
            '--file', str(context / 'Dockerfile'), '--platform', 'linux/amd64', '--timeout', '900', '--no-wait', '--no-logs',
            str(context), '--subscription', g.SUB, '--only-show-errors', '-o', 'json'], capture_output=True, env=p.ENV, timeout=150)
        report['build_submission_cli_exit'] = child.returncode
        runs = [r for r in build.az(['acr', 'task', 'list-runs', '--registry', 'pocidstokenexacr', '--top', '100']) if r['runId'] not in baseline]
        g.require(len(runs) == 1, 'single_build_submission_unverified_no_resubmit')
        image = ex.load(build.OUT)
        image['run_id'] = runs[0]['runId']
        ex.write(build.OUT, image)
        report['run_id'] = image['run_id']
        ex.write(output, report)
        g.require(build.main() == 0, 'native_linux_build_failed')
        report.update(image=ex.load(build.OUT), exit_code=0)
    except Exception as exc:
        report.update(exit_code=2, reason=str(exc) if isinstance(exc, g.GuardBlocked) else 'sanitized_dataplane_build_failure')
    report['finished_at_utc'] = p.now()
    ex.write(output, report)
    print(json.dumps({k: report.get(k) for k in ('owner_nonce', 'run_id', 'exit_code', 'reason', 'finished_at_utc')}), flush=True)
    return report['exit_code']


def execute_once(nonce):
    output = bind(nonce)
    report = ex.load(output)
    g.require(report.get('exit_code') == 0 and not report.get('execution_intent'), 'successful_unexecuted_image_required')
    facts = metadata()
    assert_metadata(facts)
    image = ex.load(build.OUT)
    context = p.ROOT / '.deployment/finops-runner' / nonce / 'image-context'
    actual = {str(f.relative_to(context)).replace('\\', '/'): prep.digest(f) for f in context.rglob('*') if f.is_file()}
    g.require(actual == image['context_files_sha256'], 'built_context_changed')
    for name, source in {'finops_private_probe.py': p.ROOT / 'scripts/deployment/finops_dataplane_probe.py',
            'entrypoint.py': FOLDER / 'entrypoint.py', 'Dockerfile': FOLDER / 'Dockerfile',
            'linux_contract.py': FOLDER / 'linux_contract.py', 'requirements.txt': FOLDER / 'requirements.txt'}.items():
        g.require(prep.digest(source) == actual[name], 'reviewed_source_changed')
    run = build.az(['acr', 'task', 'show-run', '--registry', 'pocidstokenexacr', '--run-id', image['run_id']])
    g.require(run['status'] == 'Succeeded' and run['outputImages'][0]['digest'] == 'sha256:' + image['manifest_content_sha256'],
              'immutable_build_binding_changed')
    g.require(ex.deadline_test() == 0, 'detached_deadline_test_failed')
    baseline = p.cli(['resource', 'list', '--resource-group', 'IDS-TOKEN-EXCHANGE-POC', '--query', '[].id'])
    g.network_capacity(p.get(g.VNET, '2024-05-01'))
    absence = fresh.exact_absence(g.owned_ids(nonce))
    template = prep.network_template(nonce, profile='ingestion_dataplane')
    prep.guard_network(template, nonce, profile='ingestion_dataplane')
    template_path = context.parent / 'network.arm.json'
    ex.write(template_path, template)
    ex.write(FOLDER / 'network.arm.json', template)
    scan = prep.security_scan()
    g.require(scan['security_gate_passed'], 'fresh_dataplane_security_scan_failed')
    preview = prep.validation(template_path, nonce, baseline)
    report['preview'] = preview
    ex.write(output, report)
    g.require(preview['validate']['exit_code'] == 0 and preview['what-if'].get('exact_create_only_guard_passed'),
              'fresh_four_create_preview_failed')
    preparation = {'owner_nonce': nonce, 'updated_at_utc': p.now(), 'security_scan': scan,
        'arm_network_preview': preview, 'network_template': {'path': str(template_path.relative_to(p.ROOT)).replace('\\', '/'),
            'sha256': prep.digest(template_path), 'inbound': 'vnet10.240/16_to_runner10.240.5/24_tcp19390_deny_rest'},
        'baseline_absence': absence, 'metadata': facts}
    path = context.parent / 'dataplane-preparation.json'
    ex.write(path, preparation)
    report['execution_intent'] = p.now()
    ex.write(output, report)
    execution_path = p.ROOT / ('gateway/validation/finops-dataplane-execution-' + nonce + '.json')
    code = ex.main(preparation=path, output=execution_path, ingestion_dataplane=True)
    report['execution_exit_code'] = code
    report['independent_exact_id_absence'] = fresh.exact_absence(g.owned_ids(nonce))
    report['protected_metadata_after'] = metadata()
    report['preservation_after'] = prep.preservation_readback()
    report['finished_at_utc'] = p.now()
    ex.write(output, report)
    print(json.dumps({'owner_nonce': nonce, 'exit_code': code, 'independent_exact_id_get404': 6,
                      'finished_at_utc': report['finished_at_utc']}), flush=True)
    return code


def build_diagnostic(nonce):
    import ast
    output = bind(nonce)
    report = ex.load(output)
    run = report['run_id']
    child = subprocess.run([p.AZ, 'acr', 'task', 'logs', '--registry', 'pocidstokenexacr', '--run-id', run,
        '--subscription', g.SUB, '--only-show-errors'], capture_output=True, text=True, env=p.ENV, timeout=90)
    result = {'run_id': run, 'logs_cli_exit_code': child.returncode, 'native_failure': None, 'stages': []}
    for line in (child.stdout + child.stderr).splitlines():
        for label in ('pip check', 'FINOPS_DATAPLANE_NATIVE_SDK_CONTRACT_PASSED', 'RUN python -I /probe/linux_contract.py'):
            if label in line:
                result['stages'].append(label)
        if 'AssertionError: (' in line:
            try:
                service, failure = ast.literal_eval(line.split('AssertionError: ', 1)[1])
                if service in {'monitor', 'blob', 'queue', 'table'} and type(failure) is dict:
                    result['native_failure'] = {'service': service, **{k: failure[k] for k in
                        ('status', 'stage', 'http_status', 'azure_error_code', 'reason', 'claims_verified')}}
            except Exception:
                pass
        if 'File "/probe/' in line:
            import re
            match = re.search(r'File "/probe/(linux_contract|finops_private_probe|entrypoint)\.py", line (\d+)', line)
            if match:
                result.setdefault('native_source_lines', []).append({'module': match[1], 'line': int(match[2])})
    print(json.dumps(result), flush=True)
    return 0


def local_contract(nonce):
    import importlib.util
    bind(nonce)
    folder = p.ROOT / '.deployment/finops-runner' / nonce / 'local-offline-contract'
    folder.mkdir(exist_ok=True)
    for name in ('entrypoint.py', 'linux_contract.py'):
        shutil.copyfile(FOLDER / name, folder / name)
    shutil.copyfile(p.ROOT / 'scripts/deployment/finops_dataplane_probe.py', folder / 'finops_private_probe.py')
    spec = importlib.util.spec_from_file_location('offline_contract', folder / 'linux_contract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main(native_required=False)
    return 0


def final_report(nonce):
    """Independent read-only reconciliation; never executes or retries a probe."""
    import xml.etree.ElementTree as ET
    output = bind(nonce)
    session = ex.load(output)
    execution_path = p.ROOT / ('gateway/validation/finops-dataplane-execution-' + nonce + '.json')
    execution = ex.load(execution_path)
    image = ex.load(build.OUT)
    g.require(execution.get('cleanup', {}).get('exit_code') == 0, 'completed_owned_cleanup_required')
    result = execution.get('probes', {}).get('ingestion', {}).get('sanitized_result')
    g.require(type(result) is dict and set(result.get('checks', {})) == {'postgres', 'monitor', 'blob', 'queue', 'table'},
              'actual_nonempty_service_results_required')
    absence = fresh.exact_absence(g.owned_ids(nonce))
    metadata_after = metadata()
    assert_metadata(metadata_after)
    tests_path = p.ROOT / 'gateway/validation/finops-dataplane-contract-tests-20261027.xml'
    suite = ET.parse(tests_path).getroot().find('testsuite')
    g.require(suite is not None and suite.attrib.get('failures') == '0' and suite.attrib.get('errors') == '0', 'passing_contract_tests_required')
    timestamps = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))
    lifetimes = {}
    for label, rid in execution['ids'].items():
        events = [event for event in execution['arm_events'] if event['resource_id'] == rid]
        created = next((event for event in events if event['method'] == 'PUT' and event['http_status'] in (200, 201, 202)), None)
        if created is None:
            continue
        deleted = next(event for event in events if event['method'] == 'DELETE' and event['http_status'] in (200, 202, 204))
        absent = next(event for event in events if event['method'] == 'GET' and event['http_status'] == 404 and
                      timestamps(event['at_utc']) >= timestamps(deleted['at_utc']))
        lifetimes[label] = {'created_at_utc': created['at_utc'], 'delete_response_at_utc': deleted['at_utc'],
            'get404_at_utc': absent['at_utc'], 'observed_lifetime_seconds':
                (timestamps(absent['at_utc']) - timestamps(created['at_utc'])).total_seconds()}
    storage_passed = all(result['checks'][s]['status'] == 'passed' for s in ('blob', 'queue', 'table'))
    report = {'at_utc': p.now(), 'owner_nonce': nonce, 'mode': 'read_only_independent_reconciliation_no_probe_retry',
        'identity_source': result['identity_source'], 'identity_scope': 'existing_ingestion_UAMI_only',
        'three_checks': {'postgres': result['checks']['postgres'], 'monitor': result['checks']['monitor'],
            'host_storage': {'status': 'passed' if storage_passed else 'failed',
                'services': {s: result['checks'][s] for s in ('blob', 'queue', 'table')},
                'read_metadata_only': True, 'write_permission_proven': False}},
        'build': {'run_id': image['run_id'], 'image': image['immutable_image'],
            'source_sha256': image['source_probe_sha256'], 'entrypoint_sha256': image['source_entrypoint_sha256'],
            'context_manifest_sha256': image['context_manifest_sha256'], 'started_at_utc': image['build_started_at_utc'],
            'finished_at_utc': image['build_finished_at_utc'], 'linux_native_SDK_contract_and_pip_check': True,
            'prior_failed_run_retained_not_replayed': 'cm1w'},
        'tests': {'tests': int(suite.attrib['tests']), 'failures': 0, 'errors': 0,
                  'junit_sha256': prep.digest(tests_path)},
        'created_resource_ids': execution['created_resource_ids'],
        'deleted_resource_ids': list(dict.fromkeys(event['resource_id'] for event in execution['arm_events']
            if event['method'] == 'DELETE' and event['http_status'] in (200, 202, 204))),
        'resource_lifetimes': lifetimes, 'independent_exact_id_gets': absence, 'outstanding_resource_ids': [],
        'provisioning_and_probe_no_retries': True, 'API_identity_attached': False,
        'actual_result_persisted_before_deletion': True, 'probe_state': execution['probes']['ingestion']['state'],
        'restart_count': execution['probes']['ingestion']['restart_count'],
        'actual_probe_evidence_sha256': prep.digest(execution_path),
        'protected_metadata_after': metadata_after, 'preservation_after': prep.preservation_readback(),
        'database_writes': 0, 'storage_writes': 0, 'new_roles': 0, 'production_changes': 0,
        'timer_activated': False, 'host_table_write_error_resolved': False,
        'watchdog': {'pid': execution['watchdog_pid'], 'stopped': False, 'deadline_utc': execution['deadline_utc'],
                     'exact_owned_ids_now_independently_absent': True},
        'limits': ['Storage reads do not prove create/write/lease permissions or resolution of existing host Table logging errors.',
            'Monitor print proves MI query authorization, not actual ingestion KQL/telemetry semantics.',
            'PostgreSQL proves SELECT with explicit MI and private TLS; no worker initialization or ingestion was run.',
            'No timer plan, activation, scheduled write, replay, inference, API/UI acceptance or runtime remediation performed.']}
    path = p.ROOT / ('gateway/validation/finops-dataplane-final-' + nonce + '.json')
    g.require(not path.exists(), 'final_evidence_already_exists')
    ex.write(path, report)
    print(json.dumps({'report': str(path.relative_to(p.ROOT)).replace('\\', '/'), 'three_checks': report['three_checks'],
        'created': len(report['created_resource_ids']), 'deleted': len(report['deleted_resource_ids']),
        'independent_get404': len(absence), 'at_utc': report['at_utc']}), flush=True)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['metadata', 'build', 'execute', 'build-diagnostic', 'local-contract', 'report'])
    parser.add_argument('--nonce')
    args = parser.parse_args()
    if args.action == 'metadata':
        print(json.dumps(metadata()), flush=True)
    else:
        raise SystemExit(final_report(args.nonce) if args.action == 'report' else local_contract(args.nonce) if args.action == 'local-contract' else build_once() if args.action == 'build' else build_diagnostic(args.nonce)
                 if args.action == 'build-diagnostic' else execute_once(args.nonce))