"""Fresh, bounded additive Fireworks release. Never read credentials or old applies."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import xml.etree.ElementTree as ET

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.project_route_product_access import ProductRun, sha, any_unknown
from scripts.deployment.project_route_demo import policy_structure
from scripts.deployment.project_route_models import POLICY

FAILED_HOME = rt.HOME / 'fireworks-models-20261028'
HOME = rt.HOME / 'fireworks-models-20261028-formatted'
ROOT = rt.ROOT
MANIFEST = ROOT / 'gateway/catalog/fireworks-candidate-routes.json'
BACKEND = 'azapi_resource.fireworks_backend[0]'
URL = 'https://poc-ids-token-ex-foundry.services.ai.azure.com/openai/v1'
NEW = {'FW-GLM-5.3': ('2', 'GlobalStandard'), 'FW-MiniMax-M3': ('1', 'DataZoneStandard')}


def manifest_guard(candidate, previous):
    expected = deepcopy(candidate)
    for alias, (version, _) in NEW.items():
        value = expected['routes'].pop(alias)
        rt.require(value == {'version': version, 'provider': 'Fireworks', 'token_parameter': 'max_tokens',
                            'upstream_url': URL, 'model_name': alias}, 'exact_new_route_contract')
    rt.require(expected == previous, 'original_manifest_must_remain_exact')


def guard(plan, before, expected):
    rt.require(plan.get('applyable') is True and not plan.get('errored') and not plan.get('deferred_changes'), 'resolved_plan_required')
    writes = {r['address']: r['change'] for r in plan.get('resource_changes', [])
              if r['change']['actions'] not in (['no-op'], ['read'])}
    rt.require(set(writes) == {BACKEND, POLICY}, 'exact_backend_and_policy_only')
    backend, policy = writes[BACKEND], writes[POLICY]
    rt.require(backend['actions'] == ['create'] and policy['actions'] == ['update'], 'additive_actions_only')
    from scripts.deployment.apim_route_repair import APIM
    rt.require(backend['after']['name'] == 'aiflux-project-fireworks'
               and backend['after']['parent_id'] == APIM
               and backend['after']['type'] == 'Microsoft.ApiManagement/service/backends@2024-05-01'
               and backend['after']['body'] == {'properties': {'protocol': 'http', 'url': URL,
                   'tls': {'validateCertificateChain': True, 'validateCertificateName': True}}}, 'exact_tls_backend')
    rt.require(policy_structure(policy['before']['body']['properties']['value']) == policy_structure(before), 'live_predecessor_required')
    rt.require(policy['after']['body'] == {'properties': {'format': 'rawxml', 'value': expected}}, 'exact_render_required')
    old, new = deepcopy(policy['before']), deepcopy(policy['after'])
    new['body'], new['output'] = old['body'], old.get('output')
    rt.require(old == new, 'policy_attributes_changed')
    for change in writes.values():
        rt.require(not any(any_unknown(v) for k, v in change.get('after_unknown', {}).items()
                           if k not in ('output', 'id')), 'unknown_writable_input')
    oldtree, tree = ET.fromstring(before), ET.fromstring(expected)
    for tag in ('cors', 'quota-by-key', 'rate-limit-by-key', 'llm-token-limit', 'llm-content-safety',
                'send-request', 'forward-request', 'include-fragment'):
        structural = lambda t: [policy_structure(ET.tostring(n, encoding='unicode')) for n in t.findall('.//' + tag)]
        rt.require(structural(oldtree) == structural(tree), 'protected_policy_changed:' + tag)
    rt.require(not tree.findall('.//retry') and len(tree.findall('.//forward-request')) == 1
               and len(tree.findall('.//llm-content-safety')) == 3
               and 'pii_inspection_unavailable' in expected, 'mandatory_safety')
    rt.require(not tree.findall('.//include-fragment'), 'optional_controls_stay_off')
    auth = [n.attrib for n in tree.findall('.//authentication-managed-identity')]
    previous_auth = [n.attrib for n in oldtree.findall('.//authentication-managed-identity')]
    added = {'resource': 'https://ai.azure.com', 'client-id': '5792b72e-1605-4dce-a594-4c430a5af619', 'ignore-error': 'false'}
    rt.require(auth.count(added) == 1, 'exact_new_audience')
    auth.remove(added)
    rt.require(auth == previous_auth, 'old_identity_contract_changed')
    dispatch = {n.get('condition'): n.find('set-backend-service').get('backend-id')
                for n in tree.findall('.//when') if n.find('set-backend-service') is not None}
    for alias in NEW:
        rt.require(dispatch.get('@((string)context.Variables["aiflux-model"] == "' + alias + '")') == 'aiflux-project-fireworks', 'new_backend_dispatch')
    values = {k: v['value'] for k, v in plan['variables'].items()}
    from scripts.deployment.project_route_persistent import APPROVED
    rt.require(all(values.get(k) == v for k, v in APPROVED.items())
               and values.get('poc_controls_enabled') is False
               and values.get('allow_product_subscriptions') is True
               and values.get('glm_enabled') is True and values.get('excluded_routes') == []
               and values.get('route_manifest_path') == MANIFEST.as_posix(), 'protected_profile')


class Release(ProductRun):
    def terraform(self, *args, text=None):
        import subprocess
        result = subprocess.run([rt.TF, '-chdir=' + str(ROOT / 'infra/project-route'), *args],
                                input=text, env=rt.ENV, capture_output=True, text=True,
                                encoding='utf-8', timeout=600)
        if result.returncode:
            (HOME / ('terraform-' + args[0] + '-failure.log')).write_bytes((result.stdout + result.stderr).encode('utf-8'))
            import re
            diagnostics = re.findall(r'^Error: ([^\r\n]+)', result.stdout + result.stderr, re.M)
            raise RuntimeError('terraform_' + args[0] + '_failed:' + ','.join(diagnostics))
        return result.stdout

    def sources(self):
        paths = [* (ROOT / 'infra/project-route').glob('*.tf'),
                 ROOT / 'infra/project-route/.terraform.lock.hcl',
                 ROOT / 'gateway/policies/dev-openai.xml.tftpl', MANIFEST,
                 ROOT / 'gateway/catalog/project-routes.json',
                 ROOT / 'scripts/deployment/fireworks_release.py', HOME / 'inputs.tfvars.json']
        return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in paths}

    def render(self, path):
        output = self.terraform('console', '-no-color', '-var-file=' + str(path), text='jsonencode(local.policy)\n')
        return json.loads(json.loads(output[output.find('"'):].strip()))

    def preflight(self):
        from scripts.deployment.run_private_sql import protect_directory
        protect_directory(HOME)
        rt.require(not (FAILED_HOME / 'apply-intent.json').exists(), 'prior_attempt_requires_reconciliation')
        rt.require(not (rt.HOME / 'fireworks-models-20261028-sku-corrected/apply-intent.json').exists(), 'sku_attempt_requires_reconciliation')
        rt.require(not (HOME / 'apply-intent.json').exists(), 'attempt_exists_reconcile_only')
        account = rt.cli(['account', 'show'])
        rt.require(account['id'] == rt.SUB and account['tenantId'] == rt.TENANT
                   and account['user']['name'].lower() == 'xv.puneet.devadiga@singtel.com', 'account_scope')
        manifest_guard(json.loads(MANIFEST.read_text()), json.loads((ROOT / 'gateway/catalog/project-routes.json').read_text()))
        account_id = rt.RG + '/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry'
        deployments = rt.cli(['rest', '--method', 'get', '--url', 'https://management.azure.com' + account_id + '/deployments?api-version=2025-06-01'])
        rt.require(not deployments.get('nextLink'), 'deployment_pagination')
        checked = []
        for alias, (version, sku) in NEW.items():
            d = next(d for d in deployments['value'] if d['name'] == alias)
            p = d['properties']
            rt.require(p['model']['name'] == alias and p['model']['version'] == version
                       and p['model']['format'] == 'Fireworks' and p['provisioningState'] == 'Succeeded'
                       and p['capabilities']['chatCompletion'] == 'true'
                       and d['sku']['name'] == sku and d['sku']['capacity'] == 250
                       and p.get('raiPolicyName') == 'Microsoft.Nil', 'fresh_model_contract:' + alias)
            checked.append({'alias': alias, 'model': p['model'], 'sku': d['sku'], 'raiPolicyName': p['raiPolicyName'],
                            'state': p['provisioningState'], 'native_safety_verified': False})
        baseline = self.protected()
        from scripts.deployment.finops_function_stage import current_settings
        settings = current_settings()['api']
        rt.require(settings.get('AIFLUX_GATEWAY_CONTROLS_POC_ENABLED', 'false').lower() == 'false'
                   and settings.get('AIFLUX_GATEWAY_CONTROLS_V2_ENABLED', 'false').lower() == 'false'
                   and json.loads(settings.get('AIFLUX_GATEWAY_SETTINGS_SCOPES', '[]')) == [], 'optional_controls_off')
        before = self.policy()
        original_inputs = rt.HOME / 'product-subscription-access-20261027/inputs.tfvars.json'
        inputs = json.loads(original_inputs.read_text())
        rt.save(HOME / 'predecessor-inputs.tfvars.json', inputs)
        rt.require(policy_structure(self.render(HOME / 'predecessor-inputs.tfvars.json')) == policy_structure(before), 'renderer_predecessor_drift')
        inputs['route_manifest_path'] = MANIFEST.as_posix()
        rt.save(HOME / 'inputs.tfvars.json', inputs)
        (HOME / 'rollback-policy.xml').write_bytes(before.encode('utf-8'))
        rt.save(HOME / 'baseline.json', baseline)
        rt.save(HOME / 'backends.json', self.arm('/backends'))
        external = json.loads((ROOT / 'gateway/catalog/external-inventory.json').read_text())['routes'][0]
        age = (datetime.now(UTC) - datetime.fromisoformat(external['verified_at'])).total_seconds()
        proof = {'at_utc': datetime.now(UTC).isoformat(), 'deployments': checked,
                 'protected_sha256': sha(json.dumps(baseline, sort_keys=True)), 'policy_sha256': sha(before),
                 'external_probe_at': external['verified_at'], 'external_evidence_age_seconds': age,
                 'api_promotion_blocked_external_expired': age > 86400,
                 'cloud_writes': 0, 'inference_requests': 0, 'optional_controls_enabled': False}
        rt.save(HOME / 'preflight.json', proof)
        rt.save(ROOT / 'gateway/validation/fireworks-preflight-20261028.json', proof)
        print(json.dumps(proof), flush=True)

    def plan(self):
        rt.require(not (HOME / 'plan-intent.json').exists() and not (HOME / 'apply-intent.json').exists(), 'new_plan_only')
        proof = json.loads((HOME / 'preflight.json').read_text())
        rt.require(datetime.now(UTC) - datetime.fromisoformat(proof['at_utc']) < timedelta(hours=1), 'fresh_preflight_required')
        before = (HOME / 'rollback-policy.xml').read_bytes().decode('utf-8')
        current = self.protected()
        saved = json.loads((HOME / 'baseline.json').read_text())
        if current != saved:
            differences = []
            def compare(old, new, path=''):
                if isinstance(old, dict) and isinstance(new, dict):
                    for key in old.keys() | new.keys():
                        compare(old.get(key), new.get(key), path + '/' + key)
                elif old != new:
                    differences.append(path)
            compare(saved, current)
            rt.save(HOME / 'baseline-drift.json', {'at_utc': datetime.now(UTC).isoformat(), 'changed_paths': sorted(differences)})
            raise RuntimeError('baseline_drift:' + ','.join(sorted(differences)))
        rt.require(policy_structure(self.policy()) == policy_structure(before), 'policy_predecessor_drift')
        rt.require(self.terraform('workspace', 'show').strip() == 'default', 'workspace')
        self.terraform('validate', '-no-color')
        with (HOME / 'plan-intent.json').open('x') as f:
            json.dump({'at_utc': datetime.now(UTC).isoformat()}, f)
        self.terraform('plan', '-input=false', '-no-color', '-lock-timeout=30s',
                       '-var-file=' + str(HOME / 'inputs.tfvars.json'), '-out=' + str(HOME / 'gateway.tfplan'))
        plan = json.loads(self.terraform('show', '-json', str(HOME / 'gateway.tfplan')))
        expected = self.render(HOME / 'inputs.tfvars.json')
        guard(plan, before, expected)
        review = {'at_utc': datetime.now(UTC).isoformat(), 'plan_sha256': sha((HOME / 'gateway.tfplan').read_bytes()),
                  'sources': self.sources(), 'before_policy_sha256': sha(before), 'after_policy_sha256': sha(expected),
                  'scope': {BACKEND: ['create'], POLICY: ['update']}, 'guard_verified': True}
        rt.save(HOME / 'review.json', review)
        rt.save(ROOT / 'gateway/validation/fireworks-gateway-review-20261028.json', review)
        print(json.dumps(review), flush=True)

    def inspect(self):
        plan = json.loads(self.terraform('show', '-json', str(HOME / 'gateway.tfplan')))
        result = {'applyable': plan.get('applyable'), 'errored': plan.get('errored'),
                  'changes': [{'address': r['address'], 'actions': r['change']['actions']}
                              for r in plan.get('resource_changes', [])
                              if r['change']['actions'] not in (['no-op'], ['read'])],
                  'checks': [{'address': c['address'].get('to_display'), 'status': c.get('status')}
                             for c in plan.get('checks', [])]}
        # Failed-plan diagnostics remain private; emit known structural errors only.
        log = HOME / 'terraform-plan-failure.log'
        if log.exists():
            import re
            result['diagnostics'] = re.findall(r'^Error: ([^\r\n]+)', log.read_text(encoding='utf-8', errors='replace'), re.M)
        print(json.dumps(result), flush=True)

    def check(self, live=True):
        review = json.loads((HOME / 'review.json').read_text())
        rt.require(review['sources'] == self.sources(), 'source_input_drift')
        rt.require(review['plan_sha256'] == sha((HOME / 'gateway.tfplan').read_bytes()), 'plan_bytes_changed')
        if live:
            rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(review['at_utc']) < timedelta(hours=1), 'plan_expired')
        before = (HOME / 'rollback-policy.xml').read_bytes().decode('utf-8')
        rt.require(sha(before) == review['before_policy_sha256'], 'rollback_changed')
        plan = json.loads(self.terraform('show', '-json', str(HOME / 'gateway.tfplan')))
        expected = self.render(HOME / 'inputs.tfvars.json')
        guard(plan, before, expected)
        rt.require(sha(expected) == review['after_policy_sha256'], 'target_changed')
        if live:
            rt.require(self.protected() == json.loads((HOME / 'baseline.json').read_text()), 'protected_baseline_drift')
            rt.require(policy_structure(self.policy()) == policy_structure(before), 'live_policy_drift')
            self.metadata()
        return review, expected

    def apply(self):
        rt.require(not (HOME / 'apply-intent.json').exists(), 'apply_attempt_exists_reconcile_only')
        review, _ = self.check()
        proof = json.loads((HOME / 'validation.json').read_text())
        rt.require(proof['checks_passed'] is True and proof['plan_sha256'] == review['plan_sha256']
                   and proof['sources'] == review['sources'], 'exact_validation_required')
        rt.require(json.loads((ROOT / '.azure/validate-status.json').read_text())['completedStep'] == 'UpdateStatus', 'workflow_incomplete')
        doc = (ROOT / '.azure/deployment-plan.md').read_text(encoding='utf-8')
        rt.require('Fireworks gateway status: Validated' in doc and review['plan_sha256'] in doc, 'current_validation_proof_required')
        with (HOME / 'apply-intent.json').open('x') as handle:
            json.dump({'at_utc': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256']}, handle)
        self.terraform('apply', '-input=false', '-no-color', str(HOME / 'gateway.tfplan'))
        rt.save(HOME / 'applied.json', {'at_utc': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256']})
        self.verify()

    def verify(self):
        review, expected = self.check(live=False)
        rt.require((HOME / 'applied.json').exists(), 'applied_proof_required')
        live = self.policy()
        rt.require(policy_structure(live) == policy_structure(expected), 'target_readback_mismatch')
        previous = json.loads((HOME / 'backends.json').read_text())
        current = self.arm('/backends')
        added = [v for v in current['value'] if v['name'] == 'aiflux-project-fireworks']
        rt.require(len(added) == 1 and added[0]['properties']['url'] == URL
                   and added[0]['properties']['protocol'] == 'http'
                   and added[0]['properties']['tls'] == {'validateCertificateChain': True, 'validateCertificateName': True}, 'backend_readback')
        remaining = deepcopy(current)
        remaining['value'] = [v for v in current['value'] if v['name'] != 'aiflux-project-fireworks']
        rt.require(remaining == previous, 'old_backends_changed')
        protected = self.protected()
        from scripts.deployment.finops_function_stage import sha as object_sha
        rt.require(protected['apim']['backends'] == object_sha(current), 'backend_collection_race')
        protected['apim']['backends'] = object_sha(previous)
        rt.require(protected == json.loads((HOME / 'baseline.json').read_text()), 'protected_readback_mismatch')
        self.metadata()
        result = {'at_utc': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256'],
                  'gateway_stage': 'applied_verified', 'protected_baseline_equal_except_new_backend': True,
                  'old_backends_exact': True, 'policy_normalized_equal': True, 'apply_attempts': 1,
                  'runtime_images_unchanged': True, 'rbac_writes': 0, 'network_writes': 0,
                  'inference_requests': 0, 'catalog_promoted': False}
        rt.save(HOME / 'verified.json', result)
        rt.save(ROOT / 'gateway/validation/fireworks-gateway-verified-20261028.json', result)
        print(json.dumps(result), flush=True)

    def reconcile(self):
        """Finite read-only checkpoint and allowlisted effective inventory settings."""
        from scripts.deployment.finops_function_stage import current_settings
        settings = current_settings()['api']
        allowed = {k: v for k, v in settings.items() if k in {
            'AIFLUX_FOUNDRY_INVENTORY_PATH', 'AIFLUX_EXTERNAL_INVENTORY_PATH',
            'AIFLUX_FOUNDRY_INVENTORY_MAX_AGE_SECONDS'}}
        markers = {name: (HOME / name).exists() for name in (
            'plan-intent.json', 'gateway.tfplan', 'review.json', 'validation.json',
            'apply-intent.json', 'applied.json', 'verified.json')}
        result = {'at_utc': datetime.now(UTC).isoformat(), 'markers': markers,
                  'inventory_effective_settings': allowed, 'protected': self.protected(),
                  'cloud_writes_this_action': 0, 'inference_requests_this_action': 0}
        rt.save(HOME / 'reconcile.json', result)
        print(json.dumps({'at_utc': result['at_utc'], 'markers': markers, 'inventory_effective_settings': allowed}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'plan', 'inspect', 'apply', 'verify', 'reconcile'])
    args = parser.parse_args()
    getattr(Release(), args.action)()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'blocked': type(exc).__name__, 'reason': str(exc) if isinstance(exc, RuntimeError)
                          else 'Sensitive diagnostics suppressed; inspect structural evidence.'}), flush=True)
        raise SystemExit(1)