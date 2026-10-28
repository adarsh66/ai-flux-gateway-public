"""Guarded existing-runtime rollout; never emit settings, tokens or plan bodies."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile
import traceback
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / '.deployment'
TF = 'C:/Program Files/Terraform/terraform.exe'
CLI = ['C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe', '-X', 'utf8', '-IBm', 'azure.cli']
SUB = 'aa28274d-fea0-46d4-b9c8-30f3ef0a0e52'
TENANT = 'beb276ac-6e9f-498e-8e31-019ee666decd'
OPERATOR = 'dd928302-055b-4516-9b8e-b06ae823057b'
RG = f'/subscriptions/{SUB}/resourceGroups/IDS-TOKEN-EXCHANGE-POC'
CA = 'C:/Users/p4032099/AppData/Local/Temp/zscaler-login-7860c54ccee94b5d8fa181e004a50458/azure-cli-combined-ca.pem'
ENV = {**os.environ, 'REQUESTS_CA_BUNDLE': CA, 'SSL_CERT_FILE': CA,
       'TF_CLI_CONFIG_FILE': str(HOME / 'terraform.rc'),
       'PATH': 'C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin;' + os.environ.get('PATH', '')}
for key in list(ENV):
    if key.startswith('TF_LOG'):
        del ENV[key]


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def run(args):
    p = subprocess.run(args, cwd=ROOT, env=ENV, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', check=False)
    if p.returncode:
        codes = sorted(set(re.findall(r'AuthorizationFailure|AuthorizationFailed|ForbiddenByRbac|ForbiddenByFirewall|AADSTS\d+', p.stdout + p.stderr)))
        # Output only structural Terraform diagnostics, never nearby values.
        errors = re.findall(r'^Error: ([^\r\n]+)', p.stdout + p.stderr, re.M)
        if 'Error acquiring the state lock' in p.stderr or 'Error acquiring the state lock' in p.stdout:
            errors.append('state_lock_held')
        # HashiCorp's multierror uses a safe operation-level bullet after its header.
        for line in p.stderr.splitlines():
            if line.lstrip().startswith('* ') and not re.search(r'secret|password|token|connection', line, re.I):
                errors.append(re.sub(r'https://\S+', '[endpoint]', line.strip())[:400])
        raise RuntimeError('command_failed:' + str(p.returncode) + ':' + ','.join(codes + errors))
    return p.stdout


def cli(args):
    return json.loads(run(CLI + args + ['--only-show-errors', '-o', 'json']))


def arm(path, method='GET', raw=False):
    require(path.startswith(RG + '/providers/'), 'arm_scope')
    # These POSTs are documented reads, not configuration writes.
    logs_paths = {RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-' + name + '/containerlogs'
                  for name in ['api', 'customer']}
    require(method == 'GET' or (method == 'POST' and (path.endswith('/list') or path in logs_paths)), 'arm_method')
    token = cli(['account', 'get-access-token', '--subscription', SUB, '--resource', 'https://management.azure.com/'])['accessToken']
    part = token.split('.')[1]
    claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
    require(claims.get('tid') == TENANT and claims.get('oid') == OPERATOR, 'token_identity')
    version = '2024-08-01' if '/Microsoft.DBforPostgreSQL/' in path else '2024-04-01'
    if '/Microsoft.KeyVault/' in path:
        version = '2023-07-01'
    request = Request('https://management.azure.com' + path + '?api-version=' + version,
                      method=method, headers={'Authorization': 'Bearer ' + token})
    with urlopen(request, context=ssl.create_default_context(cafile=CA), timeout=90) as response:
        content = response.read(8 * 1024 * 1024 + 1)
        require(len(content) <= 8 * 1024 * 1024, 'arm_response_too_large')
        return content if raw else json.loads(content)


def reference_metadata(response):
    """Handle ARM maps and collections; never return reference/detail/value text."""
    found = []

    def visit(value, depth=0):
        if depth > 8:
            return
        if isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, dict):
            if 'AIFLUX_LOCAL_JWT_SECRET' in value:
                found.append(value['AIFLUX_LOCAL_JWT_SECRET'])
            if value.get('name') == 'AIFLUX_LOCAL_JWT_SECRET':
                found.append(value.get('properties', value))
            for key in ['value', 'properties', 'keyToReferenceStatuses']:
                if key in value:
                    visit(value[key], depth + 1)

    visit(response)
    require(len(found) <= 1, 'ambiguous_jwt_reference_metadata')
    jwt = found[0] if found and isinstance(found[0], dict) else {}
    if isinstance(jwt.get('properties'), dict):
        jwt = jwt['properties']
    result = {k: jwt.get(k) if isinstance(jwt.get(k), str) else None
              for k in ['status', 'vaultName', 'secretName', 'identityType']}
    result['resolved'] = result['status'] == 'Resolved'
    result['metadataFound'] = bool(jwt)
    result['detailCategories'] = diagnostic_categories(str(jwt.get('details', '')))
    return result


def diagnostic_categories(text):
    """Fixed labels only: no original lines, exception values, URLs or settings."""
    patterns = {
        'firewall': r'firewall|ForbiddenByFirewall',
        'rbac': r'ForbiddenByRbac|AuthorizationFailed|permission denied',
        'network': r'network|connection|resolve|dns',
        'dns_failure': r'name or service not known|name resolution|could not resolve|failed to resolve',
        'timeout': r'timed?\s*out|timeout',
        'secret_not_found': r'SecretNotFound',
        'secret_disabled': r'SecretDisabled|secret is disabled',
        'unresolved_jwt_reference': r'local_jwt_secret.{0,120}(?:Key.?Vault|unresolved)|must be resolved',
        'settings_validation': r'ValidationError|validation error for Settings',
        'import_failure': r'ModuleNotFoundError|ImportError',
        'database_error': r'OperationalError|psycopg|sqlalchemy.exc',
        'startup_failed': r'application startup failed|failed to start|exited|startup probe failed',
        'startup_complete': r'application startup complete|container.*ready|site startup probe succeeded',
        'image_pull_failed': r'image pull failed|failed to pull|ImagePullFailure',
        'listening': r'uvicorn running|listening on',
        'traceback': r'Traceback \(most recent call last\)',
        'container_exit': r'container.*(?:exited|exit code)|exit code',
        'startup_timeout': r'container.*(?:did not|didn.t).*respond|startup.*timeout',
        'port_8000': r'\b8000\b',
        'jwt_validation': r'local_jwt_secret',
        'site_start_failed': r'failed.*start.*site|site.*failed.*start',
        'network_access': r'network access',
        'private_endpoint': r'private endpoint',
        'vnet': r'virtual network|\bvnet\b',
        'vault_unreachable': r'unreachable|could not.*connect|cannot.*connect',
        'public_access': r'public network access|public access',
        'network_connectivity': r'network connectivity',
        'tls_failure': r'SSL_do_handshake|certificate verify failed|ssl.*(?:error|fail)|tls.*(?:error|fail)',
        'connection_refused': r'connection refused|connect\(\) failed',
        'upstream_error': r'upstream.*(?:failed|timed out|closed)|no live upstreams',
        'strong_jwt_required': r'resolved, strong JWT signing secret',
        'identity_configuration_error': r'identity configuration is invalid|invalid identity configuration',
    }
    return [label for label, pattern in patterns.items() if re.search(pattern, text, re.I)]


def log_summary(content):
    text = content.decode('utf-8', errors='replace')
    trace = []

    def visit(value):
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            for line in value.splitlines():
                categories = diagnostic_categories(line)
                if categories:
                    stamp = re.search(r'\b20\d{2}-\d{2}-\d{2}[T ][0-9:.]+Z?', line)
                    trace.append({'timestamp': stamp.group(0) if stamp else None,
                                  'categories': categories})

    try:
        parsed = json.loads(text)
        visit(parsed)
        kind = type(parsed).__name__
    except ValueError:
        visit(text)
        kind = 'text'
    return {'bytesRead': len(content), 'format': kind,
            'categories': diagnostic_categories(text), 'trace': trace[-40:]}


def diagnose():
    """No appsettings or secret data-plane requests; raw logs stay in memory."""
    rid = RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-api'
    report = {'jwtReference': reference_metadata(arm(rid + '/config/configreferences/appsettings'))}
    props = arm(rid)['properties']
    report['site'] = {k: props.get(k) for k in ['state', 'availabilityState', 'usageState']}
    instances = arm(rid + '/instances').get('value', [])
    report['instances'] = [{'state': item.get('properties', {}).get('state'),
                            'containerCount': len(item.get('properties', {}).get('containers') or {})}
                           for item in instances]
    config = arm(rid + '/config/web')['properties']
    vault = arm(RG + '/providers/Microsoft.KeyVault/vaults/pocidstokenexkv')['properties']
    report['network'] = {
        'apiSubnet': props.get('virtualNetworkSubnetId'),
        'apiRouteAll': config.get('vnetRouteAllEnabled'),
        'vaultPublicNetworkAccess': vault.get('publicNetworkAccess'),
        'vaultDefaultAction': vault.get('networkAcls', {}).get('defaultAction'),
        'vaultPrivateEndpoints': [p.get('properties', {}).get('privateLinkServiceConnectionState', {}).get('status')
                                  for p in vault.get('privateEndpointConnections', [])],
    }
    try:
        content = arm(rid + '/containerlogs', 'POST', raw=True)
        report['containerLogs'] = log_summary(content)
    except HTTPError as error:
        report['containerLogs'] = {'httpStatus': error.code}
    try:
        content = arm(RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-customer/containerlogs', 'POST', raw=True)
        report['customerContainerLogs'] = log_summary(content)
    except HTTPError as error:
        report['customerContainerLogs'] = {'httpStatus': error.code}
    save(HOME / 'runtime-readiness-diagnostics.json', report)
    print(json.dumps(report, indent=2), flush=True)


def tf(args):
    return run([TF, '-chdir=' + str(ROOT / 'infra/terraform')] + args)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def snapshot():
    account = cli(['account', 'show'])
    require(account['id'] == SUB and account['tenantId'] == TENANT, 'account_scope')
    sites = {}
    for name in ['api', 'admin', 'customer']:
        rid = RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-' + name
        site = arm(rid)['properties']
        config = arm(rid + '/config/web')['properties']
        settings = arm(rid + '/config/appsettings/list', 'POST')['properties']
        sites[name] = {
            'publicNetworkAccess': site.get('publicNetworkAccess'),
            'virtualNetworkSubnetId': site.get('virtualNetworkSubnetId'),
            'keyVaultReferenceIdentity': site.get('keyVaultReferenceIdentity'),
            'image': config.get('linuxFxVersion'),
            'restrictions': {k: config.get(k) for k in ['ipSecurityRestrictions', 'ipSecurityRestrictionsDefaultAction',
                'scmIpSecurityRestrictions', 'scmIpSecurityRestrictionsDefaultAction', 'scmIpSecurityRestrictionsUseMain']},
            'settingNames': sorted(settings),
            'jwtReferenceMatches': settings.get('AIFLUX_LOCAL_JWT_SECRET') == '@Microsoft.KeyVault(SecretUri=https://pocidstokenexkv.vault.azure.net/secrets/aiflux-local-jwt-signing-secret)',
            'localAuthEnabled': settings.get('AIFLUX_LOCAL_AUTH_ENABLED') == 'true',
            'production': settings.get('AIFLUX_ENVIRONMENT') == 'production',
            'postgresConfigured': str(settings.get('AIFLUX_DATABASE_URL', '')).startswith('postgresql'),
        }
    pg = RG + '/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg'
    server = arm(pg)['properties']
    rules = arm(pg + '/firewallRules')['value']
    vault = arm(RG + '/providers/Microsoft.KeyVault/vaults/pocidstokenexkv')['properties']
    return {'sites': sites, 'postgres': {'network': server.get('network'), 'authConfig': server.get('authConfig'),
            'rules': [{'name': r['name'], 'properties': r['properties']} for r in rules]},
            'vault': {k: vault.get(k) for k in ['publicNetworkAccess', 'networkAcls']}}


def guard(parsed, release):
    require(not parsed.get('errored'), 'errored_plan')
    expected = {f'azurerm_linux_web_app.main["{n}"]': n for n in ['api', 'admin', 'customer']}
    seen = set()
    for resource in parsed.get('resource_changes', []):
        c = resource['change']
        if resource['mode'] != 'managed' or c['actions'] == ['no-op']:
            continue
        address = resource['address']
        require(address in expected and c['actions'] == ['update'], 'unrelated_or_destructive_change:' + address)
        seen.add(address)
        b, a = c['before'], c['after']
        require({k for k in b.keys() | a.keys() if b.get(k) != a.get(k)} <= {'app_settings', 'site_config'}, 'non_runtime_change')
        bs, ass = b['site_config'][0], a['site_config'][0]
        require({k for k in bs.keys() | ass.keys() if bs.get(k) != ass.get(k)} <= {'application_stack'}, 'site_security_change')
        require(not any_true(c.get('after_unknown', {})), 'unknown_plan_values')
        name = expected[address]
        stack = ass['application_stack'][0]
        require(stack['docker_image_name'] == release['results'][name]['image'].split('/', 1)[1], 'image_mismatch')
        require(stack['docker_registry_url'] == 'https://pocidstokenexacr.azurecr.io', 'registry_mismatch')
        if name == 'api':
            settings = a['app_settings']
            require(settings.get('AIFLUX_LOCAL_JWT_SECRET') == '@Microsoft.KeyVault(SecretUri=https://pocidstokenexkv.vault.azure.net/secrets/aiflux-local-jwt-signing-secret)', 'jwt_not_versionless_reference')
            require(settings.get('AIFLUX_LOCAL_AUTH_ENABLED') == 'true' and settings.get('AIFLUX_ENVIRONMENT') == 'production', 'auth_not_production')
            require(settings.get('AIFLUX_DATABASE_URL', '').startswith('postgresql://poc-ids-token-ex-api-identity@poc-ids-token-ex-pg.postgres.database.azure.com:5432/turnstile?sslmode=require'), 'database_not_passwordless')
            require(not any('PASSWORD' in k or k == 'AIFLUX_PORTAL_LOGIN_SECRET' for k in settings), 'runtime_password_or_legacy_secret')
            for k in ['CONTROL_PLANE_ENABLED', 'GATEWAY_PUBLICATION_WORKER_ENABLED', 'GATEWAY_RELEASE_WORKER_ENABLED', 'GATEWAY_APPLICATION_PROVISIONING_ENABLED']:
                require(settings.get(k) == 'false', 'unsupported_worker_enabled')
    require(seen == set(expected), 'expected_three_app_updates')
    return True


def any_true(value):
    if isinstance(value, dict):
        return any(any_true(v) for v in value.values())
    if isinstance(value, list):
        return any(any_true(v) for v in value)
    return value is True


def plan(tag, apply=False):
    folder = HOME / 'image-build' / tag
    release = json.loads((folder / 'results.json').read_text())
    manifest = json.loads((folder / 'source-manifest.json').read_text())
    for entry in manifest['entries']:
        require(hashlib.sha256((ROOT / entry['path']).read_bytes()).hexdigest() == entry['sha256'], 'source_changed_since_build:' + entry['path'])
    tf(['validate', '-no-color'])
    with tempfile.TemporaryDirectory(prefix='aiflux-runtime-') as temp:
        sid = re.search(r'S-1-5-[0-9-]+', run(['whoami', '/user', '/fo', 'csv', '/nh'])).group(0)
        run(['icacls', temp, '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'])
        path = str(Path(temp) / 'rollout.tfplan')
        tf(['plan', '-input=false', '-no-color', '-lock-timeout=60s',
            '-var-file=' + str(HOME / 'rebuild-platform.tfvars.json'),
            '-var-file=' + str(folder / 'runtime-images.tfvars.json'),
            '-var-file=' + str(HOME / 'jwt-runtime.tfvars.json'),
            *['-target=azurerm_linux_web_app.main["' + n + '"]' for n in ['api', 'admin', 'customer']],
            '-out=' + path])
        parsed = json.loads(tf(['show', '-json', path]))
        changes = []
        for r in parsed.get('resource_changes', []):
            c = r['change']
            if r['mode'] != 'managed' or c['actions'] == ['no-op']:
                continue
            before, after = c.get('before') or {}, c.get('after') or {}
            fields = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
            record = {'address': r['address'], 'actions': c['actions'], 'changedFields': fields}
            if 'app_settings' in fields:
                b, a = before.get('app_settings') or {}, after.get('app_settings') or {}
                record['changedSettingNames'] = sorted(k for k in b.keys() | a.keys() if b.get(k) != a.get(k))
            if 'site_config' in fields and before.get('site_config') and after.get('site_config'):
                b, a = before['site_config'][0], after['site_config'][0]
                record['changedSiteConfigFields'] = sorted(k for k in b.keys() | a.keys() if b.get(k) != a.get(k))
            changes.append(record)
        guard(parsed, release)
        proof = {'changes': changes, 'guard': 'passed', 'applied': False, 'tag': tag}
        save(folder / 'rollout-plan-summary.json', proof)
        print(json.dumps(proof, indent=2), flush=True)
        if apply:
            status = json.loads((ROOT / '.azure/validate-status.json').read_text())
            doc = (ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
            require(status.get('completedStep') == 'UpdateStatus' and 'Runtime JWT rollout status: Validated' in doc, 'current_validation_missing')
            baseline = json.loads((HOME / 'runtime-live-baseline.json').read_text())
            fresh = snapshot()
            for name in ['api', 'admin', 'customer']:
                for key in ['publicNetworkAccess', 'virtualNetworkSubnetId', 'keyVaultReferenceIdentity', 'restrictions', 'image']:
                    require(fresh['sites'][name][key] == baseline['sites'][name][key], 'live_baseline_drift:' + name + ':' + key)
            require(fresh['vault'] == baseline['vault'], 'vault_baseline_drift')
            tf(['apply', '-input=false', '-no-color', path])
            proof['applied'] = True
            save(folder / 'rollout-apply-result.json', proof)
            print(json.dumps({'runtime_applied': True, 'tag': tag}), flush=True)


def verify(tag):
    current = snapshot()
    baseline = json.loads((HOME / 'runtime-live-baseline.json').read_text())
    release = json.loads((HOME / 'image-build' / tag / 'results.json').read_text())
    checks = {}
    for name in ['api', 'admin', 'customer']:
        site = current['sites'][name]
        require(site['image'] == 'DOCKER|' + release['results'][name]['image'], 'live_image_mismatch:' + name)
        for key in ['publicNetworkAccess', 'virtualNetworkSubnetId', 'keyVaultReferenceIdentity', 'restrictions']:
            require(site[key] == baseline['sites'][name][key], 'security_drift:' + name + ':' + key)
        checks[name] = {'image_verified': True, 'security_preserved': True}
    require(current['vault'] == baseline['vault'], 'vault_changed')
    require(all(current['sites']['api'][k] for k in ['jwtReferenceMatches', 'localAuthEnabled', 'production', 'postgresConfigured']), 'api_configuration_mismatch')
    reference_response = arm(RG + '/providers/Microsoft.Web/sites/poc-ids-token-ex-api/config/configreferences/appsettings')
    checks['jwtReference'] = reference_metadata(reference_response)
    probes = []
    for name in ['customer', 'admin']:
        for suffix, method, body in [('/healthz', 'GET', None), ('/api/me', 'GET', None),
                ('/api/auth/login', 'POST', {'email': 'admin@tokenx-ids.com', 'password': 'deliberately-invalid-rollout-probe-not-a-user-password'})]:
            url = 'https://poc-ids-token-ex-' + name + '.azurewebsites.net' + suffix
            request = Request(url, method=method, data=json.dumps(body).encode() if body else None,
                              headers={'Content-Type': 'application/json'})
            try:
                with urlopen(request, context=ssl.create_default_context(cafile=CA), timeout=90) as response:
                    status = response.status
            except HTTPError as error:
                status = error.code
            probes.append({'portal': name, 'path': suffix, 'status': status})
    checks['probes'] = probes
    checks['postgres'] = current['postgres']
    checks['password_login_verified'] = False
    save(HOME / 'runtime-rollout-verification.json', checks)
    print(json.dumps(checks, indent=2))


def guard_containment(parsed, server, rules):
    """Only exact-IP retirement plus public-network closure, with known values."""
    require(not parsed.get('errored'), 'errored_containment_plan')
    server_address = 'azurerm_postgresql_flexible_server.main[0]'
    rule_address = 'azurerm_postgresql_flexible_server_firewall_rule.bootstrap_retired["temporary-cloud-shell-bootstrap"]'
    server_id = RG + '/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg'
    expected = set()
    require(server['network']['publicNetworkAccess'] in ['Enabled', 'Disabled'], 'unknown_postgres_network')
    if server['network']['publicNetworkAccess'] == 'Enabled':
        expected.add(server_address)
    if rules:
        expected.add(rule_address)
    changes = []
    seen = set()
    for resource in parsed.get('resource_changes', []):
        change = resource['change']
        if resource['mode'] != 'managed' or change['actions'] == ['no-op']:
            continue
        address = resource['address']
        require(address not in seen and address in expected, 'containment_unrelated_change')
        require(not any_true(change.get('after_unknown', {})), 'containment_unknown_values')
        before, after = change.get('before') or {}, change.get('after') or {}
        if address == server_address:
            require(change['actions'] == ['update'], 'postgres_replacement')
            require(before.get('id', '').lower() == server_id.lower(), 'containment_wrong_server')
            require({k for k in before.keys() | after.keys() if before.get(k) != after.get(k)} == {'public_network_access_enabled'}
                    and before.get('public_network_access_enabled') is True
                    and after.get('public_network_access_enabled') is False, 'postgres_unrelated_change')
        else:
            require(change['actions'] == ['delete'] and change.get('after') is None, 'containment_rule_not_delete')
            require(before.get('server_id', '').lower() == server_id.lower()
                    and before.get('name') == 'temporary-cloud-shell-bootstrap', 'containment_wrong_rule_resource')
            require(before.get('start_ip_address') == before.get('end_ip_address') == '135.171.36.90', 'containment_wrong_rule')
        seen.add(address)
        changes.append({'address': address, 'actions': change['actions']})
    require(seen == expected, 'containment_missing_closure')
    return changes


def contain_postgres(apply=False):
    """State-adopt only the exact approved temporary rule, then close access."""
    server_id = RG + '/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg'
    server = arm(server_id)['properties']
    rules = arm(server_id + '/firewallRules')['value']
    require(server['authConfig']['activeDirectoryAuth'] == 'Enabled' and server['authConfig']['passwordAuth'] == 'Disabled', 'postgres_auth_drift')
    require(len(rules) <= 1, 'unexpected_postgres_rules')
    if rules:
        rule = rules[0]
        require(rule['name'] == 'temporary-cloud-shell-bootstrap' and rule['properties']['startIpAddress'] == rule['properties']['endIpAddress'] == '135.171.36.90', 'unapproved_postgres_rule')
    override_path = ROOT / 'infra/terraform/zz_runtime_rollout_override.tf.json'
    original = override_path.read_text(encoding='utf-8')
    override = json.loads(original)
    del override['resource']['azurerm_postgresql_flexible_server']
    address = 'azurerm_postgresql_flexible_server_firewall_rule.bootstrap_retired["temporary-cloud-shell-bootstrap"]'
    args = ['-var-file=' + str(HOME / 'rebuild-platform.tfvars.json'),
            '-var-file=' + str(HOME / 'postgres-bootstrap-containment.tfvars.json')]
    try:
        save(override_path, override)
        tf(['validate', '-no-color'])
        state = tf(['state', 'list']).splitlines()
        if rules and address not in state:
            tf(['import', '-input=false', '-no-color', *args,
                '-var=postgres_bootstrap_rules_to_retire=["temporary-cloud-shell-bootstrap"]',
                address, server_id + '/firewallRules/temporary-cloud-shell-bootstrap'])
        with tempfile.TemporaryDirectory(prefix='aiflux-pg-contain-') as temp:
            sid = re.search(r'S-1-5-[0-9-]+', run(['whoami', '/user', '/fo', 'csv', '/nh'])).group(0)
            run(['icacls', temp, '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'])
            path = str(Path(temp) / 'contain.tfplan')
            tf(['plan', '-input=false', '-no-color', *args, '-target=azurerm_postgresql_flexible_server.main[0]',
                '-target=azurerm_postgresql_flexible_server_firewall_rule.bootstrap_retired', '-out=' + path])
            parsed = json.loads(tf(['show', '-json', path]))
            changes = guard_containment(parsed, server, rules)
            proof = {'guard': 'passed', 'changes': changes, 'applied': False}
            save(HOME / 'runtime-postgres-containment-plan.json', proof)
            print(json.dumps(proof), flush=True)
            if apply and changes:
                require(arm(server_id)['properties'] == server
                        and arm(server_id + '/firewallRules')['value'] == rules, 'containment_live_drift')
                tf(['apply', '-input=false', '-no-color', path])
                proof['applied'] = True
            final = arm(server_id)['properties']
            final_rules = arm(server_id + '/firewallRules')['value']
            proof['publicNetworkAccess'] = final['network']['publicNetworkAccess']
            proof['firewallRuleCount'] = len(final_rules)
            if apply:
                require(proof['publicNetworkAccess'] == 'Disabled' and not final_rules, 'containment_readback_failed')
            save(HOME / 'runtime-postgres-containment-result.json', proof)
            print(json.dumps(proof), flush=True)
    finally:
        override_path.write_text(original, encoding='utf-8')


def preflight():
    from scripts.deployment.deploy_portals import workflow
    original = subprocess.run(['powershell.exe', '-NoProfile', '-File',
        'C:/Users/p4032099/.agents/skills/azure-validate/references/scripts/workflow.ps1',
        '-WorkspacePath', str(ROOT)], cwd=ROOT, env=ENV, capture_output=True, text=True, check=False)
    require(original.returncode == 0 or 'ConstrainedLanguage' in original.stderr or 'Cannot create type' in original.stderr,
            'unexpected_workflow_failure')
    for step in ['None', 'LoadPlan', 'AddValidationSteps']:
        print(json.dumps(workflow(step)), flush=True)
    tf(['init', '-input=false', '-lockfile=readonly', '-no-color'])
    tf(['fmt', '-check'])
    tf(['validate', '-no-color'])
    addresses = tf(['state', 'list']).splitlines()
    roles = cli(['role', 'assignment', 'list', '--subscription', SUB, '--all', '--include-inherited'])
    grants = []
    scope = RG + '/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr'
    for name in ['api', 'admin', 'customer']:
        identity = cli(['identity', 'show', '-g', 'IDS-TOKEN-EXCHANGE-POC', '-n', 'poc-ids-token-ex-' + name + '-identity'])
        present = any(r.get('principalId', '').lower() == identity['principalId'].lower() and r.get('roleDefinitionName') == 'AcrPull'
                      and (scope.lower() == r['scope'].lower() or scope.lower().startswith(r['scope'].lower() + '/')) for r in roles)
        require(present, 'missing_acr_pull:' + name)
        grants.append({'identity': name, 'AcrPull': present})
    policies = cli(['policy', 'assignment', 'list', '--scope', '/subscriptions/' + SUB, '--disable-scope-strict-match'])
    proof = {'terraform_init': 'passed', 'fmt': 'passed', 'validate': 'passed', 'state_addresses': len(addresses),
             'app_registry_roles': grants, 'policy_assignments_reviewed': len(policies),
             'policy_names': [p['name'] for p in policies], 'local_docker_available': shutil.which('docker') is not None,
             'original_workflow_exit': original.returncode}
    save(HOME / 'runtime-preflight.json', proof)
    print(json.dumps(proof, indent=2), flush=True)
    for step in ['RunValidation', 'BuildVerification', 'StaticRoleVerification', 'RecordProof', 'ResolveErrors']:
        print(json.dumps(workflow(step)), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['snapshot', 'plan', 'deploy', 'verify', 'diagnose', 'preflight', 'contain-plan', 'contain'])
    parser.add_argument('--tag', default='local-20261023t151159z-c96420fbd5f5')
    args = parser.parse_args()
    require(re.fullmatch(r'local-\d{8}t\d{6}z-[a-f0-9]{12}', args.tag), 'release_tag')
    if args.action == 'snapshot':
        value = snapshot()
        save(HOME / 'runtime-live-baseline.json', value)
        print(json.dumps(value, indent=2))
    elif args.action in ['contain-plan', 'contain']:
        contain_postgres(apply=args.action == 'contain')
    elif args.action == 'preflight':
        preflight()
    elif args.action == 'verify':
        verify(args.tag)
    elif args.action == 'diagnose':
        diagnose()
    else:
        plan(args.tag, apply=args.action == 'deploy')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'errorType': type(error).__name__, 'error': str(error) if type(error) is RuntimeError else 'operation_failed_no_sensitive_output',
                          'frames': [{'function': frame.name, 'line': frame.lineno} for frame in traceback.extract_tb(error.__traceback__)]}))
        raise SystemExit(1)