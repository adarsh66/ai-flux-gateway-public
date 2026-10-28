"""Finite read-only rollout/renewal facts. Never fetch secrets or invoke models."""
from datetime import UTC, datetime
import json

from scripts.deployment import runtime_rollout as rt
from scripts.deployment.project_route_product_access import ProductRun, sha

HOME = rt.HOME / 'fireworks-live-20261028'


def main():
    HOME.mkdir(parents=True, exist_ok=True)
    account = rt.cli(['account', 'show'])
    rt.require(account['id'] == rt.SUB and account['tenantId'] == rt.TENANT,
               'account_scope')
    run = ProductRun()
    policy = run.policy()
    from scripts.deployment.glm_apim_secret import NAME, metadata, internal_ready
    internal = metadata(run.arm('/namedValues/' + NAME))
    rt.require(internal_ready(internal), 'existing_internal_reference_not_ready')
    # Named-value GET returns reference/resolution metadata; listValue is forbidden.
    values = run.arm('/namedValues')['value']
    references = []
    for item in values:
        props = item.get('properties', {})
        if props.get('keyVault'):
            kv = props['keyVault']
            status = kv.get('lastStatus', {})
            references.append({'name': item['name'],
                               'secret_identifier_sha256': sha(kv.get('secretIdentifier', '')),
                               'identity_client_id': kv.get('identityClientId'),
                               'resolution_code': status.get('code'),
                               'resolution_at': status.get('timeStamp'),
                               'secret': props.get('secret')})
    parent = rt.RG + '/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry'
    metadata = {}
    for label, suffix in [('account', ''), ('project', '/projects/poc-ids-token-ex-foundry-project'),
                          ('connections', '/projects/poc-ids-token-ex-foundry-project/connections'),
                          ('deployments', '/deployments')]:
        metadata[label] = rt.cli(['rest', '--method', 'get', '--url',
            'https://management.azure.com' + parent + suffix + '?api-version=2025-06-01',
            '--subscription', rt.SUB])
    rt.require(not metadata['connections'].get('nextLink') and
               not metadata['deployments'].get('nextLink'), 'pagination')
    rt.save(HOME / 'foundry-metadata.json', metadata)
    protected = run.protected()
    from scripts.deployment.finops_function_stage import current_settings
    settings = current_settings()
    config = {kind: {k: v for k, v in settings[kind].items() if k in {
        'AIFLUX_CATALOG_PATH', 'AIFLUX_CATALOG_CONFIGURED', 'AIFLUX_FOUNDRY_INVENTORY_PATH',
        'AIFLUX_EXTERNAL_INVENTORY_PATH', 'AIFLUX_GATEWAY_CONTROLS_POC_ENABLED',
        'AIFLUX_GATEWAY_CONTROLS_V2_ENABLED', 'AIFLUX_GATEWAY_SETTINGS_SCOPES'}}
        for kind in ('api', 'ingestion')}
    rt.save(HOME / 'baseline.json', protected)
    (HOME / 'policy.xml').write_bytes(policy.encode('utf-8'))
    result = {'at_utc': datetime.now(UTC).isoformat(), 'policy_sha256': sha(policy),
              'external_internal_reference': internal,
              'external_internal_reference_is_not_current_credential_health': True,
              'references': references, 'protected_sha256': sha(json.dumps(protected, sort_keys=True)),
              'inventory_settings': config,
              'images': {k: v['image'] for k, v in protected['runtime']['sites'].items()},
              'cloud_writes': 0, 'secret_value_reads': 0, 'inference_requests': 0}
    rt.save(HOME / 'readback.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__,
                          'reason': str(error) if isinstance(error, RuntimeError)
                          else 'readback_failed_sensitive_detail_suppressed'}), flush=True)
        raise SystemExit(1)