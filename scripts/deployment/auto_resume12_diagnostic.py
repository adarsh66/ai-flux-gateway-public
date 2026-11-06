"""Explicit parent-authorized scoped metadata GET; no prepare or link following."""
import json
import math
from urllib.parse import urlsplit
from urllib.request import Request

from scripts.deployment import auto_resume11_parent as prior
from scripts.deployment.auto_resume06_transport import Credentials, opener, a, canonical

HOME = prior.ROOT / '.deployment/auto-resume12'
RETAINED = prior.ROOT / '.deployment/auto-resume11/packages/successor11-live02/prepare-5719a3e1a8f57c42/capture-001/reads'


def main():
    folder = HOME / 'envelope02'
    folder.mkdir(parents=True, exist_ok=False)
    intent = prior.load(RETAINED / '021-intent.json')
    url = intent['url']
    expected = a.ARM.rstrip('/') + prior.old.APIM + '/backends?api-version=2024-05-01'
    prior.require(intent['method'] == 'GET' and url == expected, 'exact_retained_backends_URL')
    prior.require(prior.load(prior.ROOT / '.deployment/auto-live02/continuation03/result.json')['reason']
                  == 'complete_known_collection_envelope', 'actual_failure')
    # Verify the actual runtime helper BEFORE credentials or any HTTP operation.
    prior.require(isinstance(canonical({'count': 1}), bytes), 'canonical_bytes')
    prior.require(prior.sha(canonical({'count': 1})) == a.sha(canonical({'count': 1})), 'runtime_byte_hash')
    prior.put(folder, 'intent.json', {'url': url, 'method': 'GET', 'attempts': 1,
        'prepare_calls': 0, 'follow_nextLink': False, 'retained_intent_sha256': prior.sha((RETAINED / '021-intent.json').read_bytes())})
    try:
        token, _ = Credentials().get(a.ARM)
        with opener().open(Request(url, headers={'Authorization': 'Bearer ' + token}), timeout=30) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
            prior.require(response.status == 200 and response.geturl() == url and len(raw) <= 16 * 1024 * 1024,
                          'bounded_exact_HTTP200')
            page = json.loads(raw)
        prior.require(isinstance(page, dict), 'object_envelope')
        # Persist only key/type observations first; never persist resource bodies.
        prior.put(folder, 'observed.json', {'key_types': {k: type(v).__name__ for k, v in sorted(page.items())},
            'row_count': len(page['value']) if isinstance(page.get('value'), list) else None})
        metadata = {k: v for k, v in page.items() if k != 'value'}
        link = page.get('nextLink')
        parsed, initial = urlsplit(link or url), urlsplit(url)
        scoped = isinstance(link, (str, type(None))) and (not link or
            (parsed.scheme, parsed.netloc, parsed.path) == (initial.scheme, initial.netloc, initial.path))
        result = {'status': 'HTTP200_ENVELOPE_ONLY', 'url': url,
            'key_types': {k: type(v).__name__ for k, v in sorted(page.items())},
            'row_count': len(page['value']) if isinstance(page.get('value'), list) else None,
            'count': page.get('count') if type(page.get('count')) in (int, float) and math.isfinite(page['count']) else None,
            'nextLink_scoped': scoped, 'nextLink': link if scoped else None,
            'id_matches_collection_path': page.get('id') == initial.path,
            'type_matches_backend_collection': page.get('type') == 'Microsoft.ApiManagement/service/backends',
            'name_matches_backends': page.get('name') == 'backends',
            'metadata_sha256': prior.sha(canonical(metadata)), 'body_sha256': prior.sha(raw),
            'whole_rows_canonical_sha256': prior.sha(canonical(page['value'])),
            'rows_persisted': False, 'cloud_GETs': 1, 'prepare_calls': 0}
        prior.put(folder, 'result.json', result)
        print(json.dumps(result), flush=True)
    except Exception as error:
        prior.put(folder, 'STOP.json', {'type': type(error).__name__, 'no_automatic_retry': True})
        raise


if __name__ == '__main__':
    main()