"""OFFLINE successor source design. Deliberately no live/prepare entrypoint.

Current full policy/runtime freeze and original Auto candidates are separate.
Parent must assign native exact-source review and subsequent package audit.
Historical r5 initial/prepare remains historical, never reinterpreted here.
"""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

from scripts.deployment import auto_resume_current_adapter as a

ROOT = Path(__file__).resolve().parents[2]
AUTO_FILES = (
    'services/control-plane/src/aiflux/pricing/auto-routing-defaults.json',
    'gateway/policies/auto-resolve.xml.tftpl',
    'gateway/policies/auto-metadata.xml', 'gateway/policies/auto-error.xml',
)
INTERFACES = (
    'scripts/deployment/auto_path_oct30_successor_r5.py',
    'scripts/deployment/auto_path_oct30_successor_r5_reads.py',
    'scripts/deployment/auto_path_oct30_parent.py',
    'scripts/deployment/auto_path_diagnostic_oct30.py',
    'scripts/deployment/auto_path_diagnostic_release.py',
)


def freeze(current_snapshot, full_deployments, explicit_xml, global_xml,
           original_defaults, auto_fragments, source_hashes, formats_etags):
    """Pure construction: full22 is never projected down to historical13."""
    a.require(len(current_snapshot['baseline']) == 13
              and len(current_snapshot['baseline']['settings_hashes']) == 4,
              'complete_current_full13_four_settings')
    rows = full_deployments['value']
    identities = [row['id'].casefold() for row in rows]
    a.require(len(rows) == 22 and len(identities) == len(set(identities)), 'current_full22_deployments')
    candidates = original_defaults['candidates']
    a.require(isinstance(candidates, list) and candidates and len(set(candidates)) == len(candidates), 'original_Auto_candidates')
    a.auto_references({'explicit_policy': explicit_xml, 'global_policy': global_xml},
                      {'original_defaults': original_defaults, 'fragments': auto_fragments})
    a.require('infra/project-route/main.tf' in source_hashes and len(source_hashes) == 280, 'current280_including_original_main')
    for row in formats_etags:
        a.require(row['format'] == 'xml' and row.get('actual_wire', {}).get('status') == 200, 'actual_same_format_policy_binding')
        a.etag(row['etag'])
    a.require({'active', 'global', 'revision-2'} <= {row['scope'] for row in formats_etags}, 'current_global_active_owned_ETags')
    return {'schema': 1, 'contract': a.contract(), 'current_snapshot': deepcopy(current_snapshot),
        'full22_deployments': deepcopy(full_deployments),
        'current_explicit_xml_sha256': a.sha(explicit_xml.encode()),
        'restore_current_global_xml': global_xml, 'restore_global_sha256': a.sha(global_xml.encode()),
        'original_Auto_defaults': deepcopy(original_defaults), 'original_Auto_candidates': list(candidates),
        'original_Auto_fragments_sha256': {name: a.sha(text.encode()) for name, text in auto_fragments.items()},
        'current280_sources': dict(source_hashes), 'actual_policy_ETags': deepcopy(formats_etags),
        'historical_r5_replayed': False, 'live_adapter_implemented': False,
        'native_exact_source_review': 'PARENT_PENDING', 'later_package_audit': 'PARENT_PENDING'}


def unchanged(frozen, snapshot, deployments, source_hashes):
    """Whole equality including new9 metadata, original fields and current images."""
    a.require(snapshot == frozen['current_snapshot'], 'current_full_protected_drift')
    a.require(deployments == frozen['full22_deployments'], 'current_full22_metadata_drift')
    a.require(source_hashes == frozen['current280_sources'], 'current_source_drift')
    return True


def cleanup_plan(frozen, revision_id, revision_etag, global_etag):
    """Data only, no request. Parent finally must use actual current ETags."""
    a.require(revision_id.endswith('/apis/aiflux-dev-unified;rev=2'), 'exact_owned_revision2')
    return {'finally_armed_before_activation': True, 'retry_budget': 0,
        'offline': {'resource_id': revision_id, 'if_match': a.etag(revision_etag),
                    'body': {'properties': {'isOnline': False}}},
        'restore_global': {'if_match': a.etag(global_etag),
                          'value': frozen['restore_current_global_xml'],
                          'sha256': frozen['restore_global_sha256']},
        'after_cleanup': 'actual_complete_current_baseline_and_exact_revision_offline_readback_required',
        'execute_now': False}


def readiness(frozen, native_review=False, package_audit=False):
    return {'source_design_constructed': True,
        'diagnostic_ready': False, 'Auto': 'OFF_PENDING_VALIDATION', 'task_complete': False,
        'remaining': ['current-base_renderer_and_finite_delta_proof',
            'current-base_guarded_collector_and_parent_finally_integration',
            *([] if native_review else ['independent_native_exact_source_review']),
            *([] if package_audit else ['later_exact_package_audit']),
            'fresh_window_package_browser_preflight_actual_gateway_MI_proof'],
        'APIM_IP_preproof_required': False,
        'budget_untouched': {'isolated_score': 1, 'Auto_chat_requests': 2},
        'frozen_contract': deepcopy(frozen['contract'])}