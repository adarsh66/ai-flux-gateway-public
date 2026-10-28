"""Read-only verification for a blocked portal rollout; never applies or builds."""
import json
import ssl
from urllib.error import HTTPError
from urllib.request import urlopen

from scripts.deployment import portal_fix as fix


def main():
    tag = 'local-20261023t173114z-571d75366033'
    folder = fix.HOME / tag
    manifest = fix.check_sources(folder)
    release = json.loads((folder / 'results.json').read_text())
    matches = {}
    for kind in fix.KINDS:
        metadata = fix.rt.cli(['acr', 'repository', 'show', '-n', fix.REGISTRY,
            '--image', f'aiflux-{kind}:{tag}', '--subscription', fix.rt.SUB])
        matches[kind] = metadata['digest'] == release['results'][kind]['digest']
        fix.rt.require(matches[kind], 'manifest_mismatch:' + kind)
    snapshot = fix.baseline()
    captured = fix.stamp()
    probes = {}
    for kind in fix.KINDS:
        probes[kind] = {}
        for path in ['/', '/healthz', '/api/me']:
            try:
                with urlopen(f'https://poc-ids-token-ex-{kind}.azurewebsites.net{path}',
                             context=ssl.create_default_context(cafile=fix.rt.CA),
                             timeout=60) as response:
                    status = response.status
            except HTTPError as error:
                status = error.code
            except Exception as error:
                status = type(error).__name__
            probes[kind][path] = status
    report = {'timestamp': fix.stamp(), 'baselineTimestamp': captured, 'tag': tag,
        'applied': False, 'sourceFilesVerified': len(manifest['entries']),
        'manifestMatches': matches, 'operatorTenantSubscriptionVerified': True,
        'apiPublicNetworkAccess': snapshot['sites']['api']['protected']['publicNetworkAccess'],
        'postgresPublicNetworkAccess': (snapshot['postgres'].get('network') or {}).get('publicNetworkAccess'),
        'postgresFirewallRuleCount': len(snapshot['postgresRules']),
        'jwtResolved': snapshot['jwt']['resolved'],
        'adminScmDefaultAction': snapshot['sites']['admin']['protected']['web']['scmIpSecurityRestrictionsDefaultAction'],
        'currentImages': {k: snapshot['sites'][k]['image'] for k in fix.KINDS},
        'probes': probes, 'passwordLoginVerified': False,
        'blockers': ['validation_workflow_ConstrainedLanguage',
                     'plan_guard_non_image_vnet_route_all_enabled']}
    fix.save(folder / 'blocked-checkpoint.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()