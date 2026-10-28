"""Read-only final checkpoint for the bounded new-ingester repair, no retries."""
import json
from datetime import UTC, datetime

from scripts.deployment import finops_ingestion_image_repair as repair
from scripts.deployment import finops_function_stage as fs
from scripts.deployment import portal_fix as portals
from scripts.deployment import runtime_rollout as rt


def collect(tag):
    build = repair.build_proof(tag)
    folder = rt.HOME / 'finops' / tag / 'ingestion-image-only'
    prep = repair.load(folder / 'preparation.json')
    current, settings = portals.baseline(), fs.current_settings()
    hashes = {k: fs.sha(v) for k, v in settings.items()}
    unchanged = current == repair.load(folder / 'baseline.json') and hashes == prep['settings_hashes']
    rt.require(unchanged, 'unexpected_configuration_change_during_build_and_plan')
    security = repair.safety(current)
    plan = folder / 'image-only.tfplan'
    plan_hash = repair.release.digest(plan.read_bytes()) if plan.exists() else None
    rt.require(plan_hash == prep.get('plan_sha256'), 'saved_plan_evidence_incomplete')
    rt.require(not (folder / 'apply-intent.json').exists() and not (folder / 'applied.json').exists(),
               'unexpected_apply_marker')
    previous = repair.load(repair.catalog.HOME / 'host/applied.json')
    report = {'at_utc': fs.stamp(), 'status': prep['status'], 'reason': prep.get('reason'),
              'build': build, 'source_fixed': True, 'new_immutable_image_applied': False,
              'plan_sha256': plan_hash, 'plan_managed_changes': prep.get('managed_changes'),
              'actual_guard_exit': 2 if prep['status'] == 'blocked' else 0,
              'scanner': prep['scanner'], 'current_pins': {k: v['image'] for k, v in current['sites'].items()},
              'protected_baseline_unchanged': unchanged, 'complete_settings_hashes': hashes,
              'complete_settings_unchanged': hashes == prep['settings_hashes'], 'security': security,
              'host_enabled': current['sites']['ingestion']['protected']['enabled'],
              'timer_disabled': settings['ingestion']['AzureWebJobs.ingest_usage.Disabled'],
              'catalog_configured': settings['ingestion']['AIFLUX_CATALOG_CONFIGURED'],
              'cutoff_present': bool(settings['ingestion'].get('AIFLUX_INGESTION_START_AT')),
              'previous_host_plan_applied_at': previous['at_utc'],
              'previous_host_plan_sha256': previous['plan_sha256'],
              'configuration_writes_this_continuation': 0, 'database_writes': 0,
              'new_runners': 0, 'host_or_timer_activation_this_continuation': False,
              'prior_apply_replayed': False, 'live_ingestion_healthy': False,
              'workflow_completed_step': repair.load(rt.ROOT / '.azure/validate-status.json')['completedStep'],
              'next_stage': {'image_repair_controller': 'scripts/deployment/finops_ingestion_image_repair.py',
                             'image_repair_options': ['plan', 'validate', 'apply', 'verify', '--tag'],
                             'activation_controller': 'scripts/deployment/finops_catalog_repair.py',
                             'activation_options': ['plan', 'validate', 'apply', 'verify', '--stage', 'host', 'timer'],
                             'activation_executed': False,
                             'warning': 'Do not replay already-applied host/catalog stages or run timer. '
                                        'Parent must reconcile actual activation baseline and scanner findings first.'}}
    path = rt.ROOT / 'gateway/validation' / ('finops-ingestion-image-only-checkpoint-' +
           datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '.json')
    rt.save(path, report)
    print(json.dumps({'evidence': path.relative_to(rt.ROOT).as_posix(), **report}), flush=True)
    return 0


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    try:
        raise SystemExit(collect(args.tag))
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'exception_type': type(exc).__name__,
                          'reason': str(exc) if isinstance(exc, RuntimeError) else 'readback_failed'}), flush=True)
        raise SystemExit(2)