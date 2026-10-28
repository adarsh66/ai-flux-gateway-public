"""Read existing saved plan; emit field paths, never sensitive values or writes."""
from copy import deepcopy
import json

from scripts.deployment import fireworks_runtime as release
from scripts.deployment import runtime_rollout as rt


def differing_paths(a, b, path=''):
    if type(a) is not type(b):
        return [path]
    if isinstance(a, dict):
        return [p for k in a.keys() | b.keys()
                for p in differing_paths(a.get(k), b.get(k), path + '/' + str(k))]
    if isinstance(a, list):
        return [p for i in range(max(len(a), len(b)))
                for p in differing_paths(a[i] if i < len(a) else None,
                                         b[i] if i < len(b) else None, path + '/' + str(i))]
    return [] if a == b else [path]


def main():
    result = []
    for item in release.load_plan().get('resource_changes', []):
        change = item['change']
        if change['actions'] in (['no-op'], ['read']):
            continue
        before, after = deepcopy(change['before']), deepcopy(change['after'])
        for key in release.fs.COMPUTED:
            if rt.any_true((change.get('after_unknown') or {}).get(key)):
                after[key] = before.get(key)
        paths = differing_paths(before, after)
        safe = {p: {'before': before['site_config'][0].get(p.split('/')[-1]),
                    'after': after['site_config'][0].get(p.split('/')[-1])}
                for p in paths if p in {'/site_config/0/remote_debugging_version',
                    '/site_config/0/always_on', '/site_config/0/use_32_bit_worker'}}
        result.append({'address': item['address'], 'actions': change['actions'],
                       'differing_paths': paths, 'allowlisted_values': safe})
    rt.save(release.HOME / 'plan-field-diagnosis.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()