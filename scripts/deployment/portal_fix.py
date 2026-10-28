"""Strict admin-only or legacy two-portal release. Remote npm execution only.

Azure configuration writes are exclusively guarded Terraform saved-plan applies.
No appsettings/secret/publishing-credential reads, network writes or worker builds.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import ssl
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener

from scripts.deployment import runtime_rollout as rt

ROOT = rt.ROOT
HOME = rt.HOME / 'portal-fix'
REGISTRY = 'pocidstokenexacr'
HOST = REGISTRY + '.azurecr.io'
KINDS = ('admin', 'customer')
OLD = rt.HOME / 'image-build/local-20261023t151159z-c96420fbd5f5'
PINS = {'admin': 'sha256:a7e13ae5e89dc5bd1c5380213ba0beb7a8cef945d1d5c64a1188734c95d2d31f',
    'customer': 'sha256:d4891893d8d145acce36633eb7fb5029110a932f1130ee3da2bbcc1c7adbf242'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    rt.save(path, value)


def release_kinds(release):
    kinds = tuple(release.get('portals', KINDS))
    rt.require(kinds in {('admin',), ('customer',), KINDS}, 'invalid_portal_scope')
    return kinds


def source_files():
    exact = ['package.json', 'package-lock.json', 'tsconfig.base.json', 'vitest.config.ts']
    files = [ROOT / p for p in exact]
    for folder in ['apps/admin-portal', 'apps/customer-portal', 'packages/ui']:
        for p in (ROOT / folder).rglob('*'):
            relative = p.relative_to(ROOT / folder)
            if any(x in {'node_modules', 'dist', 'build', '.git'} or x.startswith('.') for x in relative.parts):
                continue
            if p.is_file() and (relative.parts[0] in {'src', 'public'} or
                    p.name in {'Dockerfile', 'package.json', 'tsconfig.json', 'vite.config.ts', 'index.html', 'nginx.conf.template'}):
                rt.require(not p.is_symlink(), 'source_symlink')
                rt.require(p.suffix.lower() not in {'.pem', '.key', '.pfx', '.env'}, 'source_secret_file')
                files.append(p)
    return sorted(set(files))


def baseline():
    account = rt.cli(['account', 'show'])
    rt.require(account['id'] == rt.SUB and account['tenantId'] == rt.TENANT
        and account['user']['name'].lower() == 'xv.puneet.devadiga@singtel.com', 'account_scope')
    result = {'sites': {}}
    for name in ['api', 'admin', 'customer', 'ingestion']:
        rid = rt.RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-' + name
        app = rt.arm(rid)
        props = app['properties']
        config = rt.arm(rid + '/config/web')['properties']
        # The web config endpoint returns null appSettings; never call appsettings/list.
        protected = {k: props.get(k) for k in ['publicNetworkAccess', 'virtualNetworkSubnetId',
            'keyVaultReferenceIdentity', 'httpsOnly', 'enabled', 'clientCertEnabled', 'clientCertMode',
            'outboundVnetRouting', 'vnetRouteAllEnabled']}
        protected['identity'] = app.get('identity')
        protected['web'] = {k: config.get(k) for k in [
            'acrUseManagedIdentityCreds', 'acrUserManagedIdentityID', 'alwaysOn',
            'appCommandLine', 'vnetRouteAllEnabled', 'publicNetworkAccess',
            'ipSecurityRestrictions', 'ipSecurityRestrictionsDefaultAction',
            'scmIpSecurityRestrictions', 'scmIpSecurityRestrictionsDefaultAction',
            'scmIpSecurityRestrictionsUseMain', 'minTlsVersion', 'scmMinTlsVersion',
            'ftpsState', 'healthCheckPath', 'httpLoggingEnabled', 'webJobsEnabled',
            'pythonVersion', 'remoteDebuggingEnabled']}
        result['sites'][name] = {'image': config.get('linuxFxVersion'), 'protected': protected}
    for key, path in {
        'vault': '/Microsoft.KeyVault/vaults/pocidstokenexkv',
        'postgres': '/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg',
    }.items():
        props = rt.arm(rt.RG + '/providers' + path)['properties']
        result[key] = {k: props.get(k) for k in ['network', 'authConfig', 'publicNetworkAccess',
            'networkAcls', 'privateEndpointConnections', 'enableRbacAuthorization']}
    result['postgresRules'] = rt.arm(rt.RG + '/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg/firewallRules')['value']
    roles = rt.cli(['role', 'assignment', 'list', '--subscription', rt.SUB, '--all', '--include-inherited'])
    result['roleAssignments'] = sorted([r['id'], r['principalId'], r['roleDefinitionId'], r['scope'],
                                       r.get('condition')] for r in roles)
    result['jwt'] = rt.reference_metadata(rt.arm(rt.RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-api/config/configreferences/appsettings'))
    return result


def check_sources(folder):
    manifest = json.loads((folder / 'source-manifest.json').read_text())
    rt.require(manifest['tag'] == folder.name, 'manifest_tag')
    rt.require(manifest['entries'] == [{'path': p.relative_to(ROOT).as_posix(),
        'sha256': digest(p.read_bytes())} for p in source_files()], 'source_inventory_changed')
    rt.require(manifest['sourceHash'] == digest(json.dumps(manifest['entries'], sort_keys=True).encode()), 'source_hash')
    for entry in manifest['entries']:
        rt.require(digest((ROOT / entry['path']).read_bytes()) == entry['sha256'], 'source_changed:' + entry['path'])
    return manifest


def verify_release(folder):
    manifest = check_sources(folder)
    release = json.loads((folder / 'results.json').read_text())
    rt.require(release['tag'] == folder.name and release['sourceHash'] == manifest['sourceHash'], 'release_source_hash')
    kinds = release_kinds(release)
    rt.require(tuple(manifest.get('portals', KINDS)) == kinds, 'manifest_scope_mismatch')
    rt.require(set(release['results']) == {'validation', *kinds}, 'unexpected_build_scope')
    pins = PINS
    if (folder / 'approved-images.json').exists():
        approval = json.loads((folder / 'approved-images.json').read_text())
        rt.require(approval['tag'] == folder.name and approval['sourceHash'] == manifest['sourceHash']
            and set(approval['pins']) == set(kinds), 'admin_approval_mismatch')
        pins = approval['pins']
    for kind in ['validation', *kinds]:
        result = release['results'][kind]
        rt.require(result['status'] == 'Succeeded', 'remote_validation_missing')
        run = rt.cli(['acr', 'task', 'show-run', '-r', REGISTRY, '--run-id', result['runId'], '--subscription', rt.SUB])
        rt.require(run['status'] == 'Succeeded' and run.get('finishTime') == result['finishedAt'], 'remote_run_changed')
        if kind in kinds:
            rt.require(re.fullmatch(r'sha256:[a-f0-9]{64}', pins[kind]), 'invalid_approved_digest')
            expected = HOST + f'/aiflux-{kind}@' + pins[kind]
            rt.require(result['digest'] == pins[kind] and result['image'] == expected, 'unapproved_image_pin')
            meta = rt.cli(['acr', 'repository', 'show', '-n', REGISTRY,
                '--image', f'aiflux-{kind}:{folder.name}', '--subscription', rt.SUB])
            rt.require(meta['digest'] == pins[kind], 'published_image_changed')
    if kinds == ('admin',):
        nginx_log = (folder / 'admin-build.log').read_text(encoding='utf-8')
        rt.require('syntax is ok' in nginx_log and 'test is successful' in nginx_log, 'nginx_validation_missing')
    log = (folder / 'validation-build.log').read_text(encoding='utf-8')
    rt.require(all(s in log for s in ['RUN npm run typecheck', 'RUN npm test',
        'RUN npm run build', 'Test Files', 'Tests', 'Successfully built']), 'remote_build_proof_missing')
    return release


def validation_inputs(folder):
    files = [ROOT / 'scripts/deployment/portal_fix.py', ROOT / 'scripts/deployment/deploy_portals.py',
             ROOT / 'scripts/deployment/runtime_rollout.py', ROOT / 'tests/unit/test_portal_fix.py',
             folder / 'source-manifest.json', folder / 'results.json', folder / 'validation-build.log',
             rt.HOME / 'rebuild-platform.tfvars.json', rt.HOME / 'jwt-runtime.tfvars.json',
             OLD / 'runtime-images.tfvars.json']
    files += sorted((ROOT / 'infra/terraform').glob('*.tf'))
    files += sorted((ROOT / 'infra/terraform').glob('*.tf.json'))
    files += [ROOT / 'infra/terraform/.terraform.lock.hcl']
    if (folder / 'approved-images.json').exists():
        files += [folder / 'approved-images.json', folder / 'admin-build.log']
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in files}


def require_validation(folder):
    proof = json.loads((folder / 'validation.json').read_text())
    status = json.loads((ROOT / '.azure/validate-status.json').read_text())
    doc = (ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
    rt.require(proof.get('tag') == folder.name and proof.get('checksPassed') is True
        and proof.get('guard') == 'passed' and proof.get('inputs') == validation_inputs(folder), 'current_validation_missing')
    label = 'Admin redirect fix status: Validated' if release_kinds(
        json.loads((folder / 'results.json').read_text())) == ('admin',) else 'Portal TLS/UI fix status: Validated'
    rt.require(status.get('completedStep') == 'UpdateStatus'
        and label in doc
        and proof['timestamp'] in doc, 'validation_workflow_incomplete')
    age = datetime.now(timezone.utc) - datetime.fromisoformat(proof['timestamp'])
    rt.require(0 <= age.total_seconds() <= 7200, 'validation_expired')


def validate(tag):
    from scripts.deployment.deploy_portals import workflow
    folder = HOME / tag
    for step in ['None', 'LoadPlan', 'AddValidationSteps']:
        print(json.dumps(workflow(step)), flush=True)
    release = verify_release(folder)
    kinds = release_kinds(release)
    rt.run(['C:/Program Files/Python313/python.exe', '-m', 'unittest', 'discover',
            '-s', 'tests/unit', '-p', 'test_portal_fix.py', '-v'])
    rt.tf(['version', '-json'])
    rt.cli(['version'])
    plan(tag)
    addresses = rt.tf(['state', 'list']).splitlines()
    workspace = rt.tf(['workspace', 'show']).strip()
    rt.require(workspace == 'default', 'terraform_workspace')
    current = baseline()
    registry_scope = rt.RG + '/providers/Microsoft.ContainerRegistry/registries/' + REGISTRY
    for kind in kinds:
        identities = current['sites'][kind]['protected']['identity']['userAssignedIdentities']
        rt.require(any(r[1] == identity['principalId'] and r[2].lower().endswith('/7f951dda-4ed3-4680-a7ca-43fe172d538d')
            and r[3].lower() == registry_scope.lower() and not r[4]
            for identity in identities.values() for r in current['roleAssignments']), 'missing_acr_pull:' + kind)
    policies = rt.cli(['policy', 'assignment', 'list', '--scope', '/subscriptions/' + rt.SUB, '--disable-scope-strict-match'])
    for path in (ROOT / 'infra/terraform').glob('*.tf*'):
        rt.require(not re.search(r'\{\{\s*\.Env\.', path.read_text(encoding='utf-8')), 'unresolved_template')
        if path.name.endswith('.json'):
            json.loads(path.read_text(encoding='utf-8'))
    for step in ['RunValidation', 'BuildVerification', 'StaticRoleVerification']:
        print(json.dumps(workflow(step)), flush=True)
    proof = {'timestamp': stamp(), 'tag': tag, 'checksPassed': True, 'guard': 'passed',
        'inputs': validation_inputs(folder), 'stateAddresses': len(addresses), 'workspace': workspace,
        'liveAcrPull': list(kinds), 'policyAssignmentsReviewed': len(policies),
        'staticRoles': 'central-handoff.tf: portal AcrPull at existing registry; central ownership; no role writes',
        'remoteBuild': 'existing ACR typecheck/test/build succeeded; source and pins verified; no rebuild',
        'terraform': 'init lockfile readonly, fmt check, validate, targeted saved plan guard, state, template scan passed'}
    save(folder / 'validation.json', proof)
    print(json.dumps(proof), flush=True)


def remote_build(admin_only=False):
    kinds = ('admin',) if admin_only else KINDS
    current = baseline()
    entries = [{'path': p.relative_to(ROOT).as_posix(), 'sha256': digest(p.read_bytes())} for p in source_files()]
    source_hash = digest(json.dumps(entries, sort_keys=True).encode())
    tag = 'local-' + datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz') + '-' + source_hash[:12]
    folder = HOME / tag
    context = folder / 'context'
    rt.require(not folder.exists(), 'release_exists')
    save(folder / 'baseline.json', {'timestamp': stamp(), 'snapshot': current})
    save(folder / 'source-manifest.json', {'tag': tag, 'sourceHash': source_hash, 'entries': entries,
        'portals': list(kinds)})
    for entry in entries:
        target = context / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / entry['path'], target)
    # This Dockerfile is a build artifact, not a deployed application change.
    validation = '''FROM node:22-alpine
WORKDIR /repo
COPY . .
RUN npm ci --workspaces --include-workspace-root
ENV VITE_AUTH_MODE=local VITE_CONTROL_API_URL=/api VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1
RUN npm run typecheck
RUN npm test -- --reporter=verbose
RUN npm run build
'''
    (context / 'PortalValidation.Dockerfile').write_text(validation, encoding='utf-8')
    if admin_only:
        admin_dockerfile = (context / 'apps/admin-portal/Dockerfile').read_text(encoding='utf-8')
        admin_dockerfile += ('\nRUN GATEWAY_ORIGIN=https://poc-ids-token-ex-apim.azure-api.net '
            'CONTROL_ORIGIN=https://poc-ids-token-ex-api.azurewebsites.net '
            '/docker-entrypoint.sh nginx -t\n')
        (context / 'AdminValidated.Dockerfile').write_text(admin_dockerfile, encoding='utf-8')
    print(json.dumps({'tag': tag, 'baselineCaptured': True, 'adminIngressPreservedAsObserved': current['sites']['admin']['protected']['web'].get('ipSecurityRestrictionsDefaultAction')}), flush=True)
    registry = rt.cli(['acr', 'show', '-n', REGISTRY, '--subscription', rt.SUB])
    rt.require(registry['loginServer'] == HOST and not registry['adminUserEnabled'], 'registry_security')
    results = {}
    for kind in ['validation', *kinds]:
        check_sources(folder)
        args = ['acr', 'build', '--registry', REGISTRY, '--subscription', rt.SUB,
                '--platform', 'linux/amd64', '--timeout', '3600',
                '--file', 'PortalValidation.Dockerfile' if kind == 'validation' else
                ('AdminValidated.Dockerfile' if admin_only else f'apps/{kind}-portal/Dockerfile')]
        if kind == 'validation':
            args += ['--no-push']
        else:
            args += ['--image', f'aiflux-{kind}:{tag}', '--build-arg', 'VITE_AUTH_MODE=local',
                     '--build-arg', 'VITE_CONTROL_API_URL=/api', '--build-arg',
                     'VITE_GATEWAY_URL=https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1']
        process = subprocess.run(rt.CLI + args + ['.'], cwd=context,
                                 env=rt.ENV, capture_output=True, text=True, encoding='utf-8', errors='replace')
        text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', process.stdout + process.stderr)
        (folder / f'{kind}-build.log').write_text(text, encoding='utf-8')
        run_ids = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
        rt.require(process.returncode == 0 and run_ids, 'remote_build_failed:' + kind)
        run_id = run_ids[-1]
        run = rt.cli(['acr', 'task', 'show-run', '-r', REGISTRY, '--run-id', run_id, '--subscription', rt.SUB])
        rt.require(run['status'] == 'Succeeded', 'acr_run_not_succeeded')
        results[kind] = {'runId': run_id, 'status': run['status'], 'finishedAt': run.get('finishTime')}
        if kind != 'validation':
            meta = rt.cli(['acr', 'repository', 'show', '-n', REGISTRY, '--image', f'aiflux-{kind}:{tag}', '--subscription', rt.SUB])
            rt.require(re.fullmatch(r'sha256:[a-f0-9]{64}', meta['digest']), 'manifest_digest')
            results[kind].update({'digest': meta['digest'], 'image': HOST + f'/aiflux-{kind}@' + meta['digest']})
        save(folder / 'results.json', {'tag': tag, 'sourceHash': source_hash,
            'portals': list(kinds), 'results': results})
        print(json.dumps({kind: results[kind]}), flush=True)
    # Bind this authorized release to its actual immutable remote build output;
    # historical releases without a manifest retain their historical fixed pins.
    save(folder / 'approved-images.json', {'tag': tag, 'sourceHash': source_hash,
        'pins': {kind: results[kind]['digest'] for kind in kinds}})
    return tag


def changed(before, after):
    return {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}


def guard(parsed, release):
    rt.require(not parsed.get('errored'), 'errored_plan')
    kinds = release_kinds(release)
    expected = {f'azurerm_linux_web_app.main["{k}"]': k for k in kinds}
    seen = set()
    # Only provider-computed outputs may become unknown, never writable inputs.
    computed = {'possible_outbound_ip_address_list', 'possible_outbound_ip_addresses',
                'outbound_ip_address_list', 'outbound_ip_addresses', 'custom_domain_verification_id'}
    for resource in parsed.get('resource_changes', []):
        c = resource['change']
        if resource['mode'] != 'managed' or c['actions'] == ['no-op']:
            continue
        address = resource['address']
        rt.require(address in expected and address not in seen and c['actions'] == ['update'], 'out_of_scope:' + address)
        seen.add(address)
        before, after = copy.deepcopy(c['before']), copy.deepcopy(c['after'])
        unknown = c.get('after_unknown') or {}
        rt.require(not any(rt.any_true(v) for k, v in unknown.items() if k not in computed), 'unknown_writable_values')
        for key in computed:
            if rt.any_true(unknown.get(key)):
                after[key] = before.get(key)
        rt.require(changed(before, after) == {'site_config'}, 'non_image_fields:' + ','.join(sorted(changed(before, after))))
        b, a = before['site_config'][0], after['site_config'][0]
        rt.require(changed(b, a) == {'application_stack'}, 'non_image_site_config:' + ','.join(sorted(changed(b, a))))
        bs, ass = b['application_stack'][0], a['application_stack'][0]
        rt.require(changed(bs, ass) == {'docker_image_name'}, 'non_image_stack')
        rt.require(ass['docker_registry_url'] == 'https://' + HOST and
                   ass['docker_image_name'] == release['results'][expected[address]]['image'].split('/', 1)[1], 'wrong_image_pin')
    label = 'expected_exactly_' + kinds[0] if len(kinds) == 1 else 'expected_exactly_two_portals'
    rt.require(seen == set(expected), label)


def runtime_variables(release, fresh):
    variables = json.loads((OLD / 'runtime-images.tfvars.json').read_text())
    kinds = release_kinds(release)
    if kinds == ('admin',) or 'sites' in fresh:
        # Never copy a historical customer/API pin into a new admin release.
        for kind, site in fresh['sites'].items():
            if kind in variables['apps']:
                image = site['image']
                rt.require(isinstance(image, str) and image.startswith('DOCKER|' + HOST + '/')
                    and re.search(r'@sha256:[a-f0-9]{64}$', image), 'baseline_image_not_immutable:' + kind)
                variables['apps'][kind]['image'] = image.removeprefix('DOCKER|' + HOST + '/')
    for kind in kinds:
        variables['apps'][kind]['image'] = release['results'][kind]['image'].split('/', 1)[1]
    return variables


def plan(tag, apply=False):
    folder = HOME / tag
    release = verify_release(folder)
    if apply:
        require_validation(folder)
    kinds = release_kinds(release)
    fresh = baseline()
    variables = runtime_variables(release, fresh)
    save(folder / 'runtime-images.tfvars.json', variables)
    save(folder / 'preplan-baseline.json', {'timestamp': stamp(), 'snapshot': fresh})
    rt.tf(['init', '-input=false', '-lockfile=readonly', '-no-color'])
    rt.tf(['fmt', '-check'])
    rt.tf(['validate', '-no-color'])
    with tempfile.TemporaryDirectory(prefix='aiflux-portal-fix-') as temp:
        sid = re.search(r'S-1-5-[0-9-]+', rt.run(['whoami', '/user', '/fo', 'csv', '/nh'])).group(0)
        rt.run(['icacls', temp, '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'])
        target = str(Path(temp) / 'portal.tfplan')
        rt.tf(['plan', '-input=false', '-no-color', '-lock-timeout=60s',
               '-var-file=' + str(rt.HOME / 'rebuild-platform.tfvars.json'),
               '-var-file=' + str(folder / 'runtime-images.tfvars.json'),
               '-var-file=' + str(rt.HOME / 'jwt-runtime.tfvars.json'),
               *['-target=azurerm_linux_web_app.main["' + k + '"]' for k in kinds], '-out=' + target])
        parsed = json.loads(rt.tf(['show', '-json', target]))
        summary = [{'address': r['address'], 'actions': r['change']['actions'],
                    'changedFields': sorted(changed(r['change'].get('before') or {}, r['change'].get('after') or {}))}
                   for r in parsed.get('resource_changes', []) if r['mode'] == 'managed' and r['change']['actions'] != ['no-op']]
        proof = {'timestamp': stamp(), 'tag': tag, 'portals': list(kinds), 'applied': False,
            'changes': summary, 'guard': 'pending'}
        try:
            guard(parsed, release)
            proof['guard'] = 'passed'
            proof['planSha256'] = digest(Path(target).read_bytes())
            if apply:
                require_validation(folder)
                verify_release(folder)
                rt.require(baseline() == fresh, 'live_baseline_drift')
                rt.require(digest(Path(target).read_bytes()) == proof['planSha256'], 'saved_plan_changed')
                proof['applyAttempted'] = True
                save(folder / 'apply-result.json', proof)
                output = rt.tf(['apply', '-input=false', '-no-color', target])
                proof['applied'] = True
                proof['applySummary'] = re.findall(r'Apply complete! Resources: [^\r\n]+', output)
                save(folder / 'apply-result.json', proof)
        except RuntimeError as error:
            proof.update({'guard': 'rejected', 'reason': str(error)})
            raise
        finally:
            save(folder / 'plan-summary.json', proof)
            if apply:
                save(folder / 'apply-result.json', proof)
            print(json.dumps(proof), flush=True)


def verify(tag):
    folder = HOME / tag
    release = verify_release(folder)
    kinds = release_kinds(release)
    before = json.loads((folder / 'preplan-baseline.json').read_text())['snapshot']
    current = baseline()
    expected = copy.deepcopy(before)
    for kind in kinds:
        expected['sites'][kind]['image'] = 'DOCKER|' + release['results'][kind]['image']
    report = {'timestamp': stamp(), 'tag': tag, 'securityBaselineEqualExceptPortalImages': current == expected,
        'portals': list(kinds), 'images': {k: current['sites'][k]['image'] for k in current['sites']},
        'customerAndApiImagesUnchanged': all(current['sites'][k]['image'] == before['sites'][k]['image']
            for k in ('customer', 'api')) if kinds == ('admin',) else None,
        'apiPrivate': current['sites']['api']['protected']['publicNetworkAccess'] == 'Disabled',
        'jwtResolved': current['jwt']['resolved'], 'passwordLoginVerified': False, 'probes': []}
    for kind in KINDS:
        for path, expected_status, payload in [('/healthz', 200, None), ('/api/me', 401, None),
            ('/api/auth/login', 401, {'email': 'rollout-probe@example.invalid', 'password': 'invalid-synthetic-probe-only'})]:
            record = {'portal': kind, 'path': path, 'expected': expected_status, 'timestamp': stamp()}
            request = Request(f'https://poc-ids-token-ex-{kind}.azurewebsites.net{path}',
                data=json.dumps(payload).encode() if payload else None, headers={'Content-Type': 'application/json'})
            try:
                with urlopen(request, context=ssl.create_default_context(cafile=rt.CA), timeout=90) as response:
                    record.update({'status': response.status, 'contentType': response.headers.get('Content-Type')})
            except HTTPError as error:
                record.update({'status': error.code, 'contentType': error.headers.get('Content-Type')})
            except Exception as error:
                record['errorType'] = type(error).__name__
            report['probes'].append(record)
            save(folder / 'verification.json', report)
    if kinds == ('admin',):
        report['redirect'] = redirect_probe()
    report['allProbesPassed'] = all(p.get('status') == p['expected'] for p in report['probes'])
    if kinds == ('admin',):
        report['allProbesPassed'] = report['allProbesPassed'] and report['redirect']['passed']
    history = folder / 'verification-history.json'
    rounds = json.loads(history.read_text()) if history.exists() else []
    save(history, [*rounds, report])
    save(folder / 'verification.json', report)
    print(json.dumps(report), flush=True)
    rt.require(report['securityBaselineEqualExceptPortalImages'], 'post_apply_security_drift')
    rt.require(report['allProbesPassed'], 'post_apply_probe_failed')


def redirect_probe():
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    base = 'https://poc-ids-token-ex-admin.azurewebsites.net'
    result = {'timestamp': stamp(), 'passed': False}
    context = ssl.create_default_context(cafile=rt.CA)
    opener = build_opener(HTTPSHandler(context=context), NoRedirect())
    try:
        try:
            with opener.open(base + '/', timeout=90) as response:
                result['status'] = response.status
        except HTTPError as error:
            result.update({'status': error.code, 'location': error.headers.get('Location')})
        rt.require(result.get('status') == 302 and result.get('location') in {'/admin/', base + '/admin/'},
            'unsafe_admin_redirect')
        with urlopen(base + '/', context=context, timeout=90) as response:
            result.update({'finalStatus': response.status, 'finalUrl': response.url})
        result['passed'] = result['finalStatus'] == 200 and result['finalUrl'] == base + '/admin/'
    except Exception as error:
        result['errorType'] = type(error).__name__
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['build', 'plan', 'validate', 'apply', 'verify'])
    parser.add_argument('--tag')
    parser.add_argument('--admin-only', action='store_true', help='Build only the admin runtime; test both portals remotely')
    args = parser.parse_args()
    if args.action == 'build':
        remote_build(admin_only=args.admin_only)
    else:
        rt.require(not args.admin_only, 'admin_only_build_flag_only_scope_is_manifest_bound')
        rt.require(args.tag and re.fullmatch(r'local-\d{8}t\d{6}z-[a-f0-9]{12}', args.tag), 'release_tag')
        if args.action == 'validate':
            validate(args.tag)
        elif args.action == 'verify':
            verify(args.tag)
        else:
            plan(args.tag, apply=args.action == 'apply')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'errorType': type(error).__name__, 'error': str(error) if isinstance(error, RuntimeError) else 'operation_failed_no_sensitive_output'}), flush=True)
        raise SystemExit(1)