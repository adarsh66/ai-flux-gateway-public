"""Explicit real prepare/run-reviewed-window; importing never runs transport.

Diagnostic score only. Two later Auto chats and production release are NOT
implemented by this diagnostic entrypoint. Trust capabilities belong to an
independent parent; the CLI cannot select a reviewer, executable or browser.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any, Protocol

from scripts.deployment import auto_resume05_parent as old
from scripts.deployment import auto_resume05_render as render
from scripts.deployment import auto_resume_current_adapter as a
from scripts.deployment import auto_resume06_review as review
from scripts.deployment.auto_resume06_transport import Transport, canonical
from scripts.deployment.auto_resume06_review import ParentBrowser

ROOT = old.ROOT
HOME = ROOT / '.deployment/auto-resume06'
LEDGER = ROOT / '.deployment/auto-resume06-isolated-score-owner.json'
NEW = ('scripts/deployment/auto_resume06_parent.py', 'scripts/deployment/auto_resume06_transport.py',
    'scripts/deployment/auto_resume06_review.py', 'scripts/deployment/auto_resume06_browser.mjs',
    'scripts/deployment/auto_resume06_native.cs', 'scripts/deployment/auto_resume06_offline.py',
    'tests/unit/test_auto_resume06.py', 'tests/auto_resume06_browser.test.mjs')


def safe(path: Path) -> None:
    a.require(not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)), 'no_link_artifacts')


def exclusive(path: Path, value: Any) -> str:
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else canonical(value)
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return render.sha(raw)


def pack(value: Any) -> Any:
    if isinstance(value, bytes):
        return {'$bytes': value.decode('utf-8')}
    if isinstance(value, dict):
        return {key: pack(item) for key, item in value.items()}
    if isinstance(value, list):
        return [pack(item) for item in value]
    return value


def unpack(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {'$bytes'}:
            return value['$bytes'].encode()
        return {key: unpack(item) for key, item in value.items()}
    if isinstance(value, list):
        return [unpack(item) for item in value]
    return value


def sources() -> dict[str, str]:
    result = old.sources()
    # Bind the complete prior05 corpus, not just its three Python files.
    for path in (ROOT / '.deployment/auto-resume05').rglob('*'):
        if path.is_file():
            safe(path)
            result[path.relative_to(ROOT).as_posix()] = render.sha(path.read_bytes())
    # Existing read projection transitive imports are included, never inferred
    # from a caller's dictionary of claimed source hashes.
    paths = list((ROOT / 'scripts/deployment').glob('*.py'))
    paths += list((ROOT / 'scripts/deployment').glob('*.mjs'))
    paths += [ROOT / name for name in NEW]
    for path in paths:
        safe(path)
        result[path.relative_to(ROOT).as_posix()] = render.sha(path.read_bytes())
    return dict(sorted(result.items()))


def source_binding() -> dict[str, Any]:
    return {'sources': sources(), 'fixtures': old.load(ROOT / '.deployment/auto-resume05/current-fixture.json')['evidence'],
        'scope': 'one-isolated-score-zero-completions-no-retries', 'stages': list(old.STAGES)}


def auto_inputs() -> dict[str, Any]:
    _, frozen = old.retained()
    return {'defaults': frozen['original_Auto_defaults'], 'fragments': {
        name: (ROOT / name).read_text(encoding='utf-8') for name in frozen['original_Auto_fragments_sha256']}}


def initial(value: dict[str, Any]) -> None:
    a.require(value['sources'] == sources(), 'all_source_binding')
    a.require(value['root']['serial'] == 130 and len(value['root']['check_results']) == 49
        and value['child']['serial'] == 191 and len(value['roles']) == 79, 'root130_child191_roles79')
    a.require(len(value['deployments']['value']) == 22, 'full22')
    a.require(len(value['snapshot']['baseline']) == 13
        and len(value['snapshot']['baseline']['settings_hashes']) == 4, 'all_settings')
    # Compare every protected current projection to retained successful current
    # data, never substitute historical13 inventory or stale settings.
    _, frozen = old.retained()
    expected_snapshot = deepcopy(frozen['current_snapshot'])
    expected_snapshot['baseline']['apim']['global'] = render.sha(value['policies']['global'])
    a.require(value['snapshot'] == expected_snapshot
        and value['deployments'] == frozen['full22_deployments'], 'fresh_current_protected_baseline_drift')
    expected_root = old.load(ROOT / '.deployment/uv-apply01/remaining02/commands/state-after.stdout.txt')
    a.require(a.state_equal(value['root'], expected_root), 'whole_keyed_root49')
    guard_state(value, deepcopy(value), value['policies']['global'], value['policies']['owned'], False)


def policy_equal(actual: bytes, expected: bytes, exported: bool) -> bool:
    return render.flatten(render.tree(actual, True)) == render.flatten(render.tree(expected, exported))


def guard_state(before: dict, actual: dict, global_xml: bytes, revision_xml: bytes, online: bool) -> dict:
    """Complete resume05 guard, privately bound to resume06 sources.

    ARM's XML export adds an entity layer. Prove the entire decoded tree before
    passing its exact desired bytes to the old finite guard; never normalize C#.
    """
    a.require(actual['sources'] == before['sources'] == sources(), 'full_resume06_source_binding')
    right, left = deepcopy(actual), deepcopy(before)
    for name, desired in (('global', global_xml), ('owned', revision_xml)):
        is_before = desired == before['policies'][name]
        a.require(policy_equal(actual['policies'][name], desired, is_before), 'exact_decoded_policy:' + name)
        right['policies'][name] = desired
    a.require(actual['snapshot']['baseline']['apim']['global'] == render.sha(actual['policies']['global']),
        'actual_global_projection_binding')
    right['snapshot']['baseline']['apim']['global'] = render.sha(global_xml)
    # old.guard's other checks remain byte-for-byte unchanged and are evaluated
    # against the same whole dictionaries. Only its source provider is rebound.
    from types import FunctionType
    bound = FunctionType(old.guard.__code__, {**old.guard.__globals__, 'sources': sources})
    bound(left, right, global_xml, revision_xml, online)
    return actual


class Port(Protocol):
    def capture(self, cleanup: bool = False) -> dict[str, Any]: ...
    def send(self, stage: str, body: bytes, etag: str, timeout: float,
             cleanup: bool = False) -> dict[str, Any]: ...


def browser_source() -> bytes:
    import subprocess
    result = subprocess.run(['node', str(ROOT / 'scripts/deployment/auto_resume06_browser.mjs'), '--source'],
        capture_output=True, timeout=15)
    a.require(result.returncode == 0 and result.stdout, 'actual_native_bridge_source')
    return result.stdout


def prepare(folder: Path, port: Port, source_review, clock=lambda: datetime.now(UTC)) -> dict[str, Any]:
    """Fresh protected collection FIRST; freeze window only after complete reads."""
    safe(folder)
    a.require(not folder.exists(), 'new_package_never_refresh')
    source_review('nativeSourceReview', source_binding())
    folder.mkdir(parents=True, exist_ok=False)
    exclusive(folder / 'prepare-intent.json', {'sources': sources(), 'paid_calls': 0, 'mutations': 0})
    before = port.capture()
    initial(before)
    begin = clock().replace(microsecond=0)
    end = begin + timedelta(minutes=30)
    start_text, end_text = (v.strftime('%Y-%m-%dT%H:%M:%SZ') for v in (begin, end))
    nonce = secrets.token_hex(16)
    policies = before['policies']
    payloads = render.render(policies['global'], policies['owned'], policies['active'],
        {'global': render.sha(policies['global']), 'owned': render.sha(policies['owned']),
         'explicit': render.sha(policies['active'])}, start_text, end_text, nonce, auto_inputs())
    artifacts = {'before.json': exclusive(folder / 'before.json', pack(before)),
        'payloads.json': exclusive(folder / 'payloads.json', pack(payloads)),
        'browser-source.js': exclusive(folder / 'browser-source.js', browser_source())}
    manifest = {'schema': 6, 'start': start_text, 'end': end_text, 'nonce': nonce,
        'sources': sources(), 'artifacts': artifacts, 'stages': list(old.STAGES),
        'scoring_budget': 1, 'completion_budget': 0, 'retry_budget': 0,
        'IP': render.IP, 'cleanup_expiry_independent': True}
    exclusive(folder / 'manifest.json', manifest)
    return manifest


def checked(folder: Path, digest: str) -> tuple[dict, dict, dict]:
    safe(folder)
    a.require(render.sha((folder / 'manifest.json').read_bytes()) == digest, 'exact_manifest_hash')
    manifest = old.load(folder / 'manifest.json')
    a.require(manifest['sources'] == sources() and manifest['stages'] == list(old.STAGES)
        and (manifest['scoring_budget'], manifest['completion_budget'], manifest['retry_budget']) == (1, 0, 0)
        and manifest['IP'] == render.IP and manifest['cleanup_expiry_independent'] is True, 'manifest_contract')
    for name, expected in manifest['artifacts'].items():
        a.require(name in ('before.json', 'payloads.json', 'browser-source.js'), 'finite_package_artifacts')
        safe(folder / name)
        a.require(render.sha((folder / name).read_bytes()) == expected, 'package_artifact_hash')
    before, payloads = (unpack(old.load(folder / name)) for name in ('before.json', 'payloads.json'))
    initial(before)
    render.prove(payloads, before['policies']['global'], before['policies']['owned'], before['policies']['active'],
        {'global': render.sha(before['policies']['global']), 'owned': render.sha(before['policies']['owned']),
         'explicit': render.sha(before['policies']['active'])}, manifest['start'], manifest['end'], manifest['nonce'], auto_inputs())
    a.require((folder / 'browser-source.js').read_bytes() == browser_source(), 'native_browser_exact_source')
    return manifest, before, payloads


def observation(value: dict, manifest: dict, digest: str, now: datetime) -> None:
    a.require(value['manifest_sha256'] == digest
        and value['browser_source_sha256'] == manifest['artifacts']['browser-source.js']
        and value['IP'] == manifest['IP'] == render.IP
        and value['fixture'] is False and value['send_invoked'] is False
        and value['auth_inspected'] is False and value['system_empty'] is True
        and value['history_empty'] is True and value['safe_event'] == 'fill+End'
        and review.page_url(value['page_url'])
        and isinstance(value['page_id'], str) and len(value['page_id']) == 36,
        'actual_browser_manifest_bound_observation')
    a.require(0 <= (now - review.at(value['issued_at'])).total_seconds() < 30, 'fresh_browser_issued_time')


def stage_body(stage: str, payloads: dict) -> bytes:
    if stage in ('online', 'offline'):
        return canonical({'properties': {'isOnline': stage == 'online'}})
    name = {'install-global': 'global.xml', 'install-revision': 'revision.xml',
        'restore-global': 'restore-global.xml'}[stage]
    return canonical({'properties': {'format': 'xml', 'value': payloads[name].decode()}})


def run_reviewed_window(folder: Path, digest: str, port: Port, package_review,
                        browser, preflight: dict, ledger: Path = LEDGER,
                        clock=lambda: datetime.now(UTC), monotonic=time.monotonic) -> dict:
    manifest, before, payloads = checked(folder, digest)
    begin, finish = render.times(manifest['start'], manifest['end'])
    a.window(begin, finish, clock())
    deadline = monotonic() + (finish - clock()).total_seconds()
    binding = {'manifest_sha256': digest, 'sources': manifest['sources'],
        'artifacts': manifest['artifacts'], 'browser_observation_sha256': render.sha(canonical(preflight))}
    package_review('packageAudit', binding)
    a.require(isinstance(browser, ParentBrowser), 'parent_owned_browser_capability_required')
    browser.validate_preflight(preflight)
    observation(preflight, manifest, digest, clock())
    a.require(not any((folder / (s + '-intent.json')).exists() for s in (*old.STAGES, 'parent-window')),
        'existing_intent_NO_REPLAY')
    # Global, non-package ledger: exclusive across processes and fresh packages.
    owner_sha = exclusive(ledger, {'manifest_sha256': digest, 'score_attempts': 1,
        'completion_attempts': 0, 'retry_budget': 0, 'pid': os.getpid()})
    parent_sha = exclusive(folder / 'parent-window-intent.json', {'binding': binding, 'finally_armed': True})
    attempted: set[str] = set()
    expected_global, expected_revision, online = before['policies']['global'], before['policies']['owned'], False
    cleanup_errors: list[str] = []
    result: dict = {'task_complete': False}

    def launch_guard():
        a.window(begin, finish, clock())
        a.require(deadline - monotonic() >= 22 * 60, 'monotonic_inclusive22_reserve')

    def guard(current):
        return guard_state(before, current, expected_global, expected_revision, online)

    def send(stage, current, cleanup=False):
        slot = 'api' if stage in ('online', 'offline') else 'global' if 'global' in stage else 'policy'
        body = stage_body(stage, payloads)
        exclusive(folder / (stage + '-intent.json'), {'body_sha256': render.sha(body),
            'if_match': old.strong_etag(current['etags'][slot]), 'retry_budget': 0})
        attempted.add(stage)  # Armed BEFORE open, including timeout/unknown result.
        response = port.send(stage, body, current['etags'][slot], 45, cleanup)
        a.require(response['http_status'] in (200, 201), 'HTTP200_201_required')
        old.strong_etag(response['etag'])
        exclusive(folder / (stage + '-result.json'), response)
        return response['etag']

    def reconciled(stage):
        """Fresh slot-local proof. Never use foreign-slot bytes as write authority.

        The unchanged launch guard is intentionally NOT the cleanup guard.
        Only the slot being cleaned is projected into the frozen guard; unrelated
        drift is preserved, not repaired or represented as a successful restore.
        """
        current = port.capture(cleanup=True)
        projected = deepcopy(before)
        a.require(current['sources'] == before['sources'] == sources(), 'cleanup_source_binding')
        if stage == 'offline':
            candidates = [before['policies']['owned']]
            if 'install-revision' in attempted:
                candidates.append(payloads['revision.xml'])
            matches = [item for item in candidates if policy_equal(current['policies']['owned'], item,
                item == before['policies']['owned'])]
            a.require(matches, 'owned_policy_drift_NO_OVERWRITE')
            state = current['owned']['properties']['isOnline']
            a.require(type(state) is bool and (not state or 'online' in attempted), 'unowned_online_state')
            projected['owned'] = deepcopy(current['owned'])
            projected['revisions'] = deepcopy(current['revisions'])
            projected['policies']['owned'] = current['policies']['owned']
            projected['etags']['api'] = old.strong_etag(current['etags']['api'])
            projected['etags']['policy'] = old.strong_etag(current['etags']['policy'])
            guard_state(before, projected, before['policies']['global'], matches[0], state)
        else:
            candidates = [before['policies']['global']]
            if 'install-global' in attempted:
                candidates.append(payloads['global.xml'])
            matches = [item for item in candidates if policy_equal(current['policies']['global'], item,
                item == before['policies']['global'])]
            a.require(matches, 'global_drift_NO_OVERWRITE')
            projected['policies']['global'] = current['policies']['global']
            projected['snapshot']['baseline']['apim']['global'] = current['snapshot']['baseline']['apim']['global']
            projected['etags']['global'] = old.strong_etag(current['etags']['global'])
            guard_state(before, projected, matches[0], before['policies']['owned'], False)
        return current, matches[0]

    try:
        for stage in old.STAGES[:3]:
            launch_guard()
            current = guard(port.capture())
            launch_guard()  # Capture time counts against the inclusive reserve.
            returned_etag = send(stage, current)
            if stage == 'install-global':
                expected_global = payloads['global.xml']
            elif stage == 'install-revision':
                expected_revision = payloads['revision.xml']
            else:
                online = True
            actual = guard(port.capture())
            slot = 'api' if stage == 'online' else 'global' if stage == 'install-global' else 'policy'
            a.require(actual['etags'][slot] == returned_etag, 'response_readback_ETag_exact')
        launch_guard()
        guard(port.capture())
        launch_guard()
        observation(preflight, manifest, digest, clock())
        reservation = {'manifest_sha256': digest, 'end': manifest['end'], 'IP': render.IP,
            'nonce': manifest['nonce'], 'review_sha256': render.sha(canonical(binding)),
            'attempt_budget': 1, 'scoring_budget': 1, 'completion_budget': 0, 'retry_budget': 0,
            'fixed_text': 'Please greet me in one short sentence.', 'model': 'gpt-5.4-mini',
            'path': '/dev/llm/v1;rev=2/chat/completions',
            'browser_source_sha256': manifest['artifacts']['browser-source.js']}
        reservation_sha = exclusive(folder / 'reserve-intent.json', reservation)
        native_binding = {**preflight, 'scope': 'AUTO_PATH_DIAGNOSTIC_ONE_NEW_ATTEMPT',
            'correction_of': 'GLOBAL_ORIGINAL_PATH_CONJUNCTION', 'end': manifest['end'],
            'nonce': manifest['nonce'], 'review_sha256': reservation['review_sha256'],
            'claim_sha256': owner_sha, 'reservation': reservation, 'reservation_sha256': reservation_sha,
            'parent_disk_verified': True, 'parent_claim_durable': True,
            'prerequisite_offline_verified': True, 'parent_intent_sha256': parent_sha,
            'shared_owner_sha256': owner_sha, 'verified_at_utc': clock().isoformat()}
        exclusive(folder / 'browser-binding.json', native_binding)
        result = browser.score(native_binding, 30)
        a.require(result.get('manifest_sha256') == digest and result.get('keyboard_invocations') == 1
            and result.get('observed_posts') == 1 and result.get('forwarded') is True
            and result.get('auth_inspected') is False and result.get('raw_body_logged') is False,
            'one_native_POST_sanitized_evidence')
        exclusive(folder / 'browser-result.json', result)
    finally:
        if attempted:
            # NO launch guard or frozen auth TTL here. Each cleanup operation
            # independently reconciles whole state and uses a fresh actual ETag.
            for stage in ('offline', 'restore-global'):
                try:
                    current, matched = reconciled(stage)
                    if stage == 'offline' and not current['owned']['properties']['isOnline']:
                        exclusive(folder / 'offline-already-verified.json', {'offline': True})
                        continue
                    if stage == 'restore-global' and matched == before['policies']['global']:
                        exclusive(folder / 'restore-global-already-verified.json', {'original_global': True})
                        continue
                    returned_etag = send(stage, current, cleanup=True)
                    if stage == 'offline':
                        online = False
                    else:
                        expected_global = before['policies']['global']
                    actual, matched = reconciled(stage)
                    a.require((stage == 'offline' and actual['owned']['properties']['isOnline'] is False)
                        or (stage == 'restore-global' and matched == before['policies']['global']),
                        'cleanup_target_exact')
                    a.require(actual['etags']['api' if stage == 'offline' else 'global'] == returned_etag,
                        'cleanup_response_ETag_exact')
                    exclusive(folder / (stage + '-verified.json'), {'slot_ownership_target_ETag_exact': True})
                except Exception as error:
                    cleanup_errors.append({'stage': stage, 'error_type': type(error).__name__,
                        'reason': str(error) if isinstance(error, ValueError) else 'transport_or_receipt_failure'})
            if cleanup_errors:
                exclusive(folder / 'cleanup-RECONCILE.json', {'unresolved': cleanup_errors, 'retry_budget': 0})
                raise ValueError('cleanup_UNRESOLVED_NO_REPLAY')
    return {'diagnostic': result, 'task_complete': False, 'Auto': 'OFF_PENDING_VALIDATION',
        'later_Auto_chats_remaining': 2}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('source-binding', 'prepare', 'localcheck', 'run-reviewed-window'))
    parser.add_argument('--package', type=Path)
    parser.add_argument('--manifest-sha256')
    args = parser.parse_args(argv)
    if args.stage == 'source-binding':
        return source_binding()
    a.require(args.package is not None, 'package_required')
    folder = args.package.absolute()
    a.require(folder.parent == HOME / 'packages' and folder.name.startswith('auto_resume06-'), 'new_package_scope')
    if args.stage == 'localcheck':
        return checked(folder, args.manifest_sha256)[0]
    # Live APIs are composed by the actual trusted parent using existing tools.
    # No CLI argument or disk JSON can register trust/bridge capabilities.
    raise ValueError('parent_owned_review_and_browser_capabilities_required_NO_ACTION')


if __name__ == '__main__':
    try:
        print(json.dumps(main(), sort_keys=True))
    except Exception:
        print('{"status":"STOP_RECONCILE_NO_RETRY","task_complete":false}')
        raise SystemExit(2)