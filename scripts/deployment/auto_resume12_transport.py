"""Successor12-only capture copy; endpoint-scoped envelopes, unchanged row projection.

No live action on import. Only observed backends count metadata is accepted;
all unknown fields remain fail-closed. Rows are preserved whole.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
import math
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request
import time

from scripts.deployment import auto_resume06_transport as six
from scripts.deployment import auto_resume11_parent as eleven

old, a, p, OWNED = six.old, six.a, six.p, six.OWNED


def canonical_sha(value):
    """Use bytes explicitly, independent of adapter JSON-hash overloads."""
    return a.sha(six.canonical(value))


def collection_kind(url):
    parsed = urlsplit(url)
    a.require(parsed.scheme == 'https' and parsed.netloc == 'management.azure.com'
              and not parsed.fragment and not parsed.username, 'ARM_only')
    apim = old.APIM
    paths = {apim + suffix: 'apim' for suffix in (
        '/backends', '/subscriptions', '/products', '/policyFragments', '/products/aiflux/apis',
        '/apis/aiflux-dev-unified/operations', '/apis/aiflux-dev-unified/products',
        '/apis/aiflux-dev-unified/revisions',
        '/apis/aiflux-dev-unified;rev=1/operations', '/apis/aiflux-dev-unified;rev=1/products',
        '/apis/aiflux-dev-unified;rev=2/operations', '/apis/aiflux-dev-unified;rev=2/products')}
    paths[apim + '/backends'] = 'backends'
    paths[old.RG + '/providers/Microsoft.DBforPostgreSQL/flexibleServers/poc-ids-token-ex-pg/firewallRules'] = 'postgres'
    paths[old.RG + '/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry/deployments'] = 'deployments'
    paths['/subscriptions/' + old.SUB + '/providers/Microsoft.Authorization/roleDefinitions'] = 'roles'
    a.require(parsed.path in paths, 'finite_collection_endpoint')
    version = {'postgres': '2024-08-01', 'deployments': '2025-06-01',
               'roles': '2022-04-01'}.get(paths[parsed.path], '2024-05-01')
    query = parse_qsl(parsed.query, keep_blank_values=True)
    a.require([v for k, v in query if k == 'api-version'] == [version], 'collection_api_version')
    return paths[parsed.path]


def validate_envelope(page, kind):
    a.require(isinstance(page, dict) and isinstance(page.get('value'), list), 'complete_known_collection_envelope')
    # envelope02 observed exactly count:int and value:list. Permit the existing
    # scoped pagination contract, not arbitrary ARM metadata or resource fields.
    allowed = {'value', 'nextLink', 'count'} if kind == 'backends' else {'value', 'nextLink'}
    a.require(set(page) <= allowed, 'complete_known_collection_envelope')
    if 'count' in page:
        count = page['count']
        a.require(type(count) is int and 0 <= count <= 2147483647,
              'known_nonnegative_integral_count')
        # Count may be total across pages: never compare blindly to this page.
    link = page.get('nextLink')
    a.require(link is None or isinstance(link, str), 'known_nextLink_type')
    a.require(all(isinstance(row, dict) for row in page['value']), 'whole_object_rows')


def collection(reader, url, write):
    initial, visited, rows, identities = urlsplit(url), set(), [], set()
    kind = collection_kind(url)
    original = url
    while url:
        parsed = urlsplit(url)
        a.require(parsed.scheme == initial.scheme and parsed.netloc == initial.netloc
            and parsed.path == initial.path and url not in visited and len(visited) < 30,
            'complete_scoped_pages')
        a.require(collection_kind(url) == kind, 'same_collection_kind')
        visited.add(url)
        page = reader.get(url)
        validate_envelope(page, kind)
        link = page.get('nextLink')
        if link:
            following = urlsplit(link)
            a.require((following.scheme, following.netloc, following.path) ==
                      (initial.scheme, initial.netloc, initial.path) and link not in visited,
                      'complete_scoped_pages')
            a.require(collection_kind(link) == kind, 'same_collection_kind')
        metadata = {k: v for k, v in page.items() if k != 'value'}
        # Exact safe metadata is distinct from the original protected row-only
        # projection. Never serialize resource rows, settings or response bodies.
        receipt_name = 'collections/' + a.sha(original.encode())[:16] + '-' + str(len(visited)).zfill(2) + '.json'
        receipt = {
            'url': url,
            'metadata': metadata,
            'metadata_sha256': canonical_sha(metadata),
            'key_types': {k: type(v).__name__ for k, v in page.items()},
            'row_count': len(page['value']),
            'whole_rows_sha256': canonical_sha(page['value']),
        }
        if not hasattr(reader, 'collection_receipts'):
            reader.collection_receipts = {}
        if receipt_name in reader.collection_receipts:
            a.require(reader.collection_receipts[receipt_name] == receipt, 'cached_collection_exact')
        else:
            write(receipt_name, receipt)
            reader.collection_receipts[receipt_name] = receipt
        for row in page['value']:
            identity = row.get('id')
            if identity is not None:
                a.require(isinstance(identity, str) and bool(identity.strip()), 'row_resource_identity')
            identity = ('id', identity.casefold()) if identity is not None else ('whole', canonical_sha(row))
            a.require(identity not in identities, 'duplicate_resource_identity')
            identities.add(identity)
        rows.extend(page['value'])
        url = page.get('nextLink')
    return {'value': rows}


class Transport(eleven.Transport):
    def capture(self, cleanup: bool = False) -> dict:
        from scripts.deployment import restore22_successor as projections
        self.capture_number += 1
        prefix = 'capture-' + str(self.capture_number).zfill(3) + '/'
        def write(name, value):
            return self.write(prefix + name, value)
        token, claims = self.credentials.get(a.ARM, cleanup)
        def command(label, argv, secret=False):
            a.require(not secret and argv[:len(old.CLI)] == old.CLI, 'read_command_only')
            args = argv[len(old.CLI):]
            a.require(args[-3:] == ['--only-show-errors', '-o', 'json'], 'exact_cli_suffix')
            write('commands/' + label + '-intent.json', {'argv': args, 'attempts': 1})
            value = self.command(args[:-3])
            write('commands/' + label + '-result.json', {'sha256': a.sha(value), 'exit_code': 0})
            return value
        rebound = projections.g.rebound
        namespace = dict(write=write, command=command, HOME=None)
        class Reader(old.Reads):
            def __init__(reader):
                reader.token, reader.claims = token, claims
                reader.cache, reader.records, reader.count = {}, {}, 0
                reader.deadline = time.monotonic() + 180
                reader.opener = self.http
            request = rebound(old.Reads.request, **namespace)
            cli = rebound(old.Reads.cli, **namespace)
            def collection(reader, url):
                return collection(reader, url, write)
        reader = Reader()
        storage, storage_claims = self.credentials.get(a.STORAGE, cleanup)
        def root_read():
            a.token_claims(storage_claims, a.STORAGE, time.time())
            headers = {'Authorization': 'Bearer ' + storage, 'x-ms-version': '2023-11-03',
                'x-ms-date': datetime.now(UTC).strftime('%a, %d %b %Y %H:%M:%S GMT')}
            with self.http.open(Request(old.BLOB, method='HEAD', headers=headers), timeout=30) as response:
                a.require(response.status == 200 and response.geturl() == old.BLOB
                    and response.headers.get('x-ms-lease-state') == 'available'
                    and response.headers.get('x-ms-lease-status') == 'unlocked', 'unlocked_root_HEAD')
                etag = p.strong_etag(response.headers.get('ETag'))
            with self.http.open(Request(old.BLOB, headers={**headers, 'If-Match': etag}), timeout=30) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
                a.require(response.status == 200 and response.geturl() == old.BLOB
                    and response.headers.get('ETag') == etag and len(raw) <= 16 * 1024 * 1024,
                    'root_conditional_whole_GET')
            return json.loads(raw), etag
        root, root_etag = root_read()
        snapshot, active, _ = rebound(projections.old.capture,
            ReadOnly=lambda label: reader, write=write)('protected')
        def get(suffix):
            return reader.get(a.ARM.rstrip('/') + old.APIM + suffix)
        revisions = reader.collection(a.ARM.rstrip('/') + old.APIM +
            '/apis/aiflux-dev-unified/revisions?api-version=2024-05-01')['value']
        owned = get(p.OWNED + '?api-version=2024-05-01')
        inheritance = {}
        for revision in ('1', '2'):
            suffix = '/apis/aiflux-dev-unified;rev=' + revision
            detail = get(suffix + '?api-version=2024-05-01')
            if revision != '2':
                inheritance[suffix] = detail
            for kind in ('operations', 'products'):
                path = suffix + '/' + kind
                rows = reader.collection(a.ARM.rstrip('/') + old.APIM + path + '?api-version=2024-05-01')
                inheritance[path] = rows
                for row in rows['value']:
                    policy_path = (suffix + '/operations/' if kind == 'operations' else '/products/') + row['name']
                    inheritance[policy_path] = reader.get(a.ARM.rstrip('/') + old.APIM + policy_path +
                        '/policies/policy?format=xml&api-version=2024-05-01', optional=True)
        policies, etags = {}, {}
        for name, suffix, slot in (('global', '', 'global'), ('owned', p.OWNED, 'policy'),
                                   ('active', '/apis/aiflux-dev-unified', None)):
            url = a.ARM.rstrip('/') + old.APIM + suffix + '/policies/policy?format=xml&api-version=2024-05-01'
            value = reader.get(url)
            policies[name] = value['properties']['value'].encode()
            if slot:
                etags[slot] = p.strong_etag(reader.records[url]['etag'])
        etags['api'] = p.strong_etag(reader.records[a.ARM.rstrip('/') + OWNED + '?api-version=2024-05-01']['etag'])
        deployments = reader.collection(a.ARM.rstrip('/') + old.RG +
            '/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry/deployments?api-version=2025-06-01')
        child_raw = (old.ROOT / 'infra/project-route/terraform.tfstate').read_bytes()
        child = json.loads(child_raw)
        a.require(child['serial'] == 191 and a.sha(child_raw) ==
            p.load(old.ROOT / '.deployment/auto-resume03/state-owner-proof.json')['child_sha256'], 'exact_local_child191')
        closing, closing_etag = root_read()
        a.require(root_etag == closing_etag and a.state_equal(root, closing), 'coherent_root_capture')
        raw_global = get('/policies/policy?format=rawxml&api-version=2024-05-01')['properties']['value'].encode()
        from scripts.deployment import auto_resume05_render as renderer
        a.require(snapshot['baseline']['apim']['global'] == renderer.sha(raw_global)
            and renderer.flatten(renderer.tree(raw_global)) == renderer.flatten(renderer.tree(policies['global'], True)),
            'raw_projection_bound_to_actual_XML_export')
        snapshot['baseline']['apim']['global'] = renderer.sha(policies['global'])
        a.require(time.monotonic() < reader.deadline, 'finite_capture_deadline')
        return {'snapshot': snapshot, 'deployments': deployments, 'root': root,
            'child': child, 'roles': snapshot['baseline']['runtime']['roleAssignments'],
            'inheritance': inheritance, 'revisions': revisions, 'owned': owned,
            'policies': policies, 'etags': etags, 'sources': self.sources()}