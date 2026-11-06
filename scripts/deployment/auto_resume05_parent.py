"""Current diagnostic-only parent. No cloud transport is registered in this release.

localcheck is usable offline. prepare/run-reviewed-window are real integration
APIs but refuse missing capabilities BEFORE creating a package or wire intent.
No production Auto/chat release is implemented or implied.
"""
import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import re
import time

from scripts.deployment import auto_resume05_render as r
from scripts.deployment import auto_resume_current_adapter as a

ROOT = Path(__file__).resolve().parents[2]
STAGES = tuple(a.contract()['stages'])
OWNED = '/apis/aiflux-dev-unified;rev=2'
SOURCES = ('scripts/deployment/auto_resume05_render.py', 'scripts/deployment/auto_resume05_parent.py',
    'tests/unit/test_auto_resume05.py', '.deployment/auto-resume05/current-fixture.json')


def load(path):
    return json.loads(path.read_bytes())


def capture_digest(value):
    # Policy wire bytes are not silently decoded or omitted from source binding.
    if isinstance(value, bytes):
        return {'wire_bytes_sha256': r.sha(value)}
    if isinstance(value, dict):
        return {key: capture_digest(item) for key, item in value.items()}
    if isinstance(value, list):
        return [capture_digest(item) for item in value]
    return value


def exclusive(path, value):
    require_safe(path)
    raw = json.dumps(value, sort_keys=True).encode()
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def require_safe(path):
    a.require(not any(p.is_symlink() for p in (path, *path.parents)), 'no_symlink_artifacts')


def strong_etag(value):
    a.require(isinstance(value, str) and re.fullmatch(r'"[\x21\x23-\x7e]+"', value)
              and value != '"*"', 'actual_strong_ETag')
    return value


def sources():
    fixture = load(ROOT / '.deployment/auto-resume05/current-fixture.json')
    mapping = dict(fixture['sources'])
    mapping.update({name: r.sha((ROOT / name).read_bytes()) for name in SOURCES})
    for name, digest in mapping.items():
        require_safe(ROOT / name)
        a.require(r.sha((ROOT / name).read_bytes()) == digest, 'source_drift:' + name)
    return mapping


def retained():
    """Retained evidence only, explicitly NOT a fresh collection or live package."""
    folder = ROOT / '.deployment/auto-resume04'
    fixture = load(ROOT / '.deployment/auto-resume05/current-fixture.json')
    for name, digest in fixture['evidence'].items():
        a.require(r.sha((folder / name).read_bytes()) == digest, 'current_fixture_evidence_drift')
    frozen = load(folder / 'successor-offline-freeze.json')
    return folder, frozen


def localcheck():
    mapping = sources()
    folder, frozen = retained()
    a.require(len(frozen['full22_deployments']['value']) == 22, 'full22')
    a.require(len(frozen['current280_sources']) == 280, 'original280')
    a.require(len(frozen['current_snapshot']['baseline']['settings_hashes']) == 4, 'four_settings')
    return {'status': 'LOCAL_CHECK_ONLY_NOT_FRESH_NOT_READY', 'sources': mapping,
        'provenance': 'RETAINED_RESUME04', 'cloud_mutations': 0, 'paid_calls': 0,
        'missing_capabilities': ['current_full_capture_transport', 'independent_native_source_review',
            'exact_package_native_audit', 'actual_browser_preflight_and_handoff', 'bounded_one_wire_transport'],
        'Auto': 'OFF_PENDING_VALIDATION', 'task_complete': False}


@dataclass(frozen=True)
class Capabilities:
    """Dependency injection only; never inferred from module globals/old clones.

    Parent must supply independently audited implementations, not boolean claims.
    The shipped CLI supplies none and cannot perform any network operation.
    """
    capture: object = None
    native_review: object = None
    browser: object = None
    send_once: object = None

    def require_all(self):
        a.require(all(callable(value) for value in (
            self.capture, self.native_review, self.browser, self.send_once)), 'missing_actual_capabilities_NO_ACTION')


def guard(before, actual, global_xml, revision_xml, online):
    """Exact whole protected equality except the independently bound global slot.

    Capture contract has no remote-child assertion: child is local ownership only.
    The adapter must supply full root keyed49, full22 metadata, all original roles,
    four settings, full inheritance, all revision details and actual policy ETags.
    """
    required = {'snapshot', 'deployments', 'root', 'child', 'roles', 'inheritance',
        'revisions', 'owned', 'policies', 'etags', 'sources'}
    a.require(set(before) == set(actual) == required, 'complete_current_capture_contract')
    a.require(actual['sources'] == before['sources'] == sources(), 'full_source_binding')
    for name in ('deployments', 'child', 'roles', 'inheritance'):
        a.require(actual[name] == before[name], 'whole_protected_drift:' + name)
    a.require(len(actual['deployments']['value']) == 22 and len(actual['root']['check_results']) == 49
        and a.state_equal(before['root'], actual['root']), 'whole_root49_full22')
    left, right = deepcopy(before['snapshot']), deepcopy(actual['snapshot'])
    a.require(len(right['baseline']) == 13 and len(right['baseline']['settings_hashes']) == 4, 'whole_current_baseline')
    # Explicit, sole global projection; its exact XML and actual digest are checked.
    for capture, snapshot in ((before, left), (actual, right)):
        a.require(snapshot['baseline']['apim']['global'] == r.sha(capture['policies']['global']), 'global_projection_binding')
    right['baseline']['apim']['global'] = left['baseline']['apim']['global']
    a.require(right == left, 'whole_snapshot_except_proven_global')
    a.require(set(actual['policies']) == {'global', 'owned', 'active'}
        and actual['policies']['global'] == global_xml
        and actual['policies']['owned'] == revision_xml
        and actual['policies']['active'] == before['policies']['active'], 'exact_policy_wire_readback')
    rows = deepcopy(before['revisions'])
    a.require(len(rows) == 2 and {row['apiRevision'] for row in rows} == {'1', '2'}, 'all_revision_rows')
    for row in rows:
        a.require(row['isCurrent'] is (row['apiRevision'] == '1'), 'revision2_never_current')
        if row['apiRevision'] == '2':
            row['isOnline'] = online
    a.require(actual['revisions'] == rows, 'all_revision_flags_exact')
    owned = deepcopy(before['owned'])
    a.require(owned['id'].endswith(OWNED) and owned['properties']['apiRevision'] == '2'
        and owned['properties']['path'] == 'dev/llm/v1'
        and owned['properties']['subscriptionRequired'] is True
        and owned['properties']['apiRevisionDescription'].startswith('Auto offline stage owner='), 'exact_owned_metadata')
    owned['properties']['isOnline'] = online
    a.require(actual['owned'] == owned, 'whole_owned_metadata_exact')
    a.require(set(actual['etags']) == {'global', 'policy', 'api'}, 'three_actual_ETags')
    for value in actual['etags'].values():
        strong_etag(value)
    return actual


def prepare(folder, capabilities=None, clock=lambda: datetime.now(UTC)):
    """Future explicit API: fails closed now; never restamp retained as fresh."""
    capabilities = capabilities or Capabilities()
    capabilities.require_all()
    a.require(not folder.exists(), 'package_never_refresh')
    localcheck()
    # The current capture transport and source audit are intentionally required
    # before freezing any start/end. No historical collector fallback is allowed.
    evidence = capabilities.native_review('source', sources())
    a.require(evidence is not None, 'independent_native_source_audit_required')
    raise ValueError('prepare_transport_freshness_and_package_audit_adapter_NOT_REGISTERED_NO_PACKAGE')


def run_reviewed_window(folder, before, payloads, start, end, capabilities=None,
                        clock=lambda: datetime.now(UTC), monotonic=time.monotonic):
    """Bounded parent-finally integration, diagnostic only; used with local mocks.

    No second executor/cleanup path. Ambiguous writes require retained ownership
    reconciliation; never retry. Cleanup reads are attempted once even after expiry.
    """
    cap = capabilities or Capabilities()
    cap.require_all()
    a.require(folder.is_dir(), 'new_reviewed_package_directory_required')
    require_safe(folder)
    begin, finish = r.times(start, end)
    remaining = a.window(begin, finish, clock())
    deadline = monotonic() + remaining
    # Never trust a caller's proof flag or render hash: regenerate the complete
    # finite delta from the independently retained current baseline and compare.
    retained_folder, frozen = retained()
    a.require(before['policies'] == {key: (retained_folder / name).read_bytes() for key, name in (
        ('global', 'global-actual.xml'), ('owned', 'revision-2-actual.xml'), ('active', 'active-actual.xml'))},
        'current_baseline_policies_not_substitutable')
    _, gate = r.parts(r.tree(payloads['revision.xml']))
    nonce = re.fullmatch(r'@\("auto-diagnostic:([a-f0-9]{32})"\)', gate.get('key'))
    a.require(nonce is not None, 'exact_counter_identity')
    auto = {'defaults': frozen['original_Auto_defaults'], 'fragments': {
        name: (ROOT / name).read_text(encoding='utf-8') for name in frozen['original_Auto_fragments_sha256']}}
    r.prove(payloads, before['policies']['global'], before['policies']['owned'], before['policies']['active'],
        {'global': r.sha(before['policies']['global']), 'owned': r.sha(before['policies']['owned']),
         'explicit': r.sha(before['policies']['active'])}, start, end, nonce[1], auto)
    # A real package verifier is not shipped; external adapter must verify the
    # exact immutable bytes plus actual native audit/preflight, not booleans.
    binding = {'sources': sources(), 'before': a.sha(capture_digest(before)),
        'payloads': {k: r.sha(v) for k, v in payloads.items() if isinstance(v, bytes)},
        'start': start, 'end': end, 'stages': list(STAGES)}
    a.require(cap.native_review('package-and-browser-preflight', binding) == binding,
              'actual_exact_native_package_review_preflight_required')
    a.require(not any((folder / (s + '-intent.json')).exists() for s in (*STAGES, 'parent-window')),
              'existing_intent_RECONCILE_NO_REPLAY')
    exclusive(folder / 'parent-window-intent.json', {'binding': binding, 'finally_armed': True})
    installed_global = before['policies']['global']
    installed_revision = before['policies']['owned']
    online = False
    attempted = False
    cleanup_errors = []

    def capture():
        return guard(before, cap.capture(), installed_global, installed_revision, online)

    def wire(stage, body, etag):
        nonlocal attempted
        strong_etag(etag)
        exclusive(folder / (stage + '-intent.json'), {'binding_sha256': a.sha(binding),
            'body_sha256': r.sha(body), 'if_match': etag, 'retry_budget': 0})
        if stage == 'install-global':
            attempted = True
        outcome = cap.send_once(stage, body, etag, min(60, max(1, deadline - monotonic())))
        a.require(isinstance(outcome, dict) and outcome == {'http_status': 200}, 'wire_unknown_or_failed_RECONCILE_NO_RETRY')

    try:
        # All guards and launch reserve repeat before each activation stage.
        for stage in STAGES[:3]:
            a.window(begin, finish, clock())
            a.require(deadline - monotonic() >= 22 * 60, 'monotonic_cleanup_reserve22')
            current = capture()
            if stage == 'install-global':
                wire(stage, payloads['global.xml'], current['etags']['global'])
                installed_global = payloads['global.xml']
            elif stage == 'install-revision':
                wire(stage, payloads['revision.xml'], current['etags']['policy'])
                installed_revision = payloads['revision.xml']
            else:
                wire(stage, b'{"properties":{"isOnline":true}}', current['etags']['api'])
                online = True
            capture()
        a.window(begin, finish, clock())
        a.require(deadline - monotonic() >= 22 * 60, 'monotonic_cleanup_reserve22')
        capture()
        exclusive(folder / 'reserve-intent.json', {'binding': binding, 'score': 1, 'completion': 0, 'retries': 0})
        return cap.browser(binding, min(30, max(0, deadline - monotonic() - 22 * 60)))
    finally:
        if attempted:
            # Per-stage fresh exact read and actual current ETag establish
            # ownership. A drift/ambiguous state is NOT overwritten.
            for stage in STAGES[4:]:
                try:
                    current = capture()
                    if stage == 'offline':
                        wire(stage, b'{"properties":{"isOnline":false}}', current['etags']['api'])
                        online = False
                    else:
                        wire(stage, payloads['restore-global.xml'], current['etags']['global'])
                        installed_global = payloads['restore-global.xml']
                    capture()
                    exclusive(folder / (stage + '-verified.json'), {'binding_sha256': a.sha(binding), 'whole_current_exact': True})
                except Exception:
                    cleanup_errors.append(stage)
            if cleanup_errors:
                exclusive(folder / 'cleanup-RECONCILE.json', {'failed_stages': cleanup_errors, 'no_retry': True})
                raise ValueError('cleanup_UNRESOLVED_RECONCILE_NO_REPLAY')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('localcheck', 'prepare', 'run-reviewed-window'))
    parser.add_argument('--package', type=Path)
    args = parser.parse_args(argv)
    if args.stage == 'localcheck':
        print(json.dumps(localcheck(), sort_keys=True))
        return 0
    # Capability gate precedes all package creation/capture/window activity.
    Capabilities().require_all()
    return 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"CAPABILITY_GATE_STOP_NO_ACTION","task_complete":false}')
        raise SystemExit(2)