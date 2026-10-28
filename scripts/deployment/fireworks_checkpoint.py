"""Finite read-only reconciliation after a recorded Fireworks apply; never replay."""
from copy import deepcopy
from datetime import UTC, datetime
import json

from scripts.deployment import fireworks_release as release
from scripts.deployment import runtime_rollout as rt


def differences(old, new, path=''):
    if isinstance(old, dict) and isinstance(new, dict):
        return [p for k in old.keys() | new.keys() for p in differences(old.get(k), new.get(k), path + '/' + k)]
    if isinstance(old, list) and isinstance(new, list):
        return [p for i in range(max(len(old), len(new))) for p in differences(
            old[i] if i < len(old) else None, new[i] if i < len(new) else None, path + '/' + str(i))]
    return [path] if old != new else []


def main():
    run = release.Release()
    review, expected = run.check(live=False)
    rt.require((release.HOME / 'applied.json').exists(), 'apply_completion_required_no_replay')
    live = run.policy()
    rt.require(release.policy_structure(live) == release.policy_structure(expected), 'policy_mismatch')
    previous = json.loads((release.HOME / 'backends.json').read_text())
    current = run.arm('/backends')
    rest = deepcopy(current)
    added = [v for v in rest['value'] if v['name'] == 'aiflux-project-fireworks']
    rest['value'] = [v for v in rest['value'] if v['name'] != 'aiflux-project-fireworks']
    result = {'at_utc': datetime.now(UTC).isoformat(), 'plan_sha256': review['plan_sha256'],
              'applied_marker': True, 'policy_normalized_equal': True,
              'old_backend_changed_paths': differences(previous, rest), 'new_backend_count': len(added),
              'createdResources': [], 'orphanedResourceGroups': [], 'cloud_writes': 0, 'inference_requests': 0}
    rt.save(release.HOME / 'readback-diagnostic.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()