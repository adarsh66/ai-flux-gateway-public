"""Local-only retained-envelope search. Never creates a transport."""
import json
from pathlib import Path

from scripts.deployment import auto_resume11_parent as prior


def main():
    hits = []
    for path in (prior.ROOT / '.deployment').rglob('*.json'):
        if any(part in ('node_modules', 'context', '.terraform') for part in path.parts):
            continue
        try:
            if path.stat().st_size > 4 * 1024 * 1024:
                continue
            raw = path.read_bytes()
            if b'/backends' not in raw and b'"backends"' not in raw:
                continue
            value = json.loads(raw)
        except (ValueError, OSError):
            continue

        def walk(item, location=''):
            if isinstance(item, dict):
                if isinstance(item.get('value'), list) and set(item) - {'value', 'nextLink'}:
                    hits.append({'path': str(path), 'location': location,
                        'file_sha256': prior.sha(raw), 'keys': sorted(item),
                        'types': {k: type(v).__name__ for k, v in item.items()},
                        'row_count': len(item['value']),
                        'safe_metadata': {k: v for k, v in item.items() if k in ('count', 'id', 'type', 'name')
                                          and isinstance(v, (str, int, float, type(None)))}})
                for key, child in item.items():
                    walk(child, location + '/' + key)
            elif isinstance(item, list):
                for i, child in enumerate(item):
                    walk(child, location + '/' + str(i))
        walk(value)
    prior.put(prior.ROOT / '.deployment/auto-resume12', 'retained-envelope-search.json', hits)
    print(json.dumps(hits, indent=2), flush=True)


if __name__ == '__main__':
    main()