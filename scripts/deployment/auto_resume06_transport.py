"""Finite current transport. Constructed only by explicit resume06 CLI actions.

No old run/prepare method is called. Only resume04 read projections are reused,
privately rebound to this instance's output/auth dependencies; no module mutation.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import ssl
import subprocess
import time
from typing import Any, Callable
from urllib.request import HTTPSHandler, Request, build_opener

from scripts.deployment import auto_resume_current_readonly as old
from scripts.deployment import auto_resume_current_adapter as a
from scripts.deployment import auto_resume05_parent as p

JSON = dict[str, Any]
Write = Callable[[str, Any], str]
OWNED = old.APIM + p.OWNED
POLICY = '/policies/policy?api-version=2024-05-01'
URLS = {
    'install-global': a.ARM.rstrip('/') + old.APIM + POLICY,
    'restore-global': a.ARM.rstrip('/') + old.APIM + POLICY,
    'install-revision': a.ARM.rstrip('/') + OWNED + POLICY,
    'online': a.ARM.rstrip('/') + OWNED + '?api-version=2024-05-01',
    'offline': a.ARM.rstrip('/') + OWNED + '?api-version=2024-05-01',
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class Credentials:
    """Normal installed Profile acquisition, private pipe; no secret persistence.

    Cleanup may acquire a new token BEFORE an operation when TTL is insufficient.
    This is not a retry of an HTTP mutation (401/403 never causes a resend).
    """
    def __init__(self) -> None:
        self.tokens: dict[str, tuple[str, JSON]] = {}

    def get(self, audience: str, cleanup: bool = False) -> tuple[str, JSON]:
        existing = self.tokens.get(audience)
        if existing and existing[1]['exp'] - time.time() > 600:
            a.token_claims(existing[1], audience, time.time())
            return existing
        a.require(existing is None or cleanup, 'launch_token_expiring_NO_REFRESH_RETRY')
        child = subprocess.run([old.CLI[0], '-B', str(Path(old.__file__).with_name(
            'auto_resume_current_credentials.py')), old.SUB, a.TENANT, audience],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=120, env=old.environment())
        a.require(child.returncode == 0, 'private_credential_acquisition_failed')
        value = json.loads(child.stdout)
        token = value['access_token']
        part = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        a.token_claims(claims, audience, time.time())
        self.tokens[audience] = token, claims
        return token, claims


def opener():
    a.require(a.sha(old.CA.read_bytes()) ==
        'e747e9880a4e63c73f55af589941139d0a4f90ceec5df745cfd6fee5bbe257dc', 'pinned_CA')
    context = ssl.create_default_context(cafile=str(old.CA))
    a.require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, 'strict_TLS')
    return build_opener(HTTPSHandler(context=context), old.NoRedirect())


class Transport:
    def __init__(self, write: Write, sources: Callable[[], dict[str, str]],
                 credentials: Credentials | None = None) -> None:
        self.write, self.sources = write, sources
        self.credentials = credentials or Credentials()
        self.http = opener()
        self.capture_number = 0

    def command(self, args: list[str]) -> Any:
        a.require(args == ['account', 'show'] or args == ['role', 'assignment', 'list',
            '--subscription', old.SUB, '--all', '--include-inherited'], 'finite_read_CLI')
        result = subprocess.run(old.CLI + args + ['--only-show-errors', '-o', 'json'],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=120, env=old.environment())
        a.require(result.returncode == 0, 'read_CLI_failed_NO_RETRY')
        value = json.loads(result.stdout)
        if args[0] == 'account':
            a.require(value['id'] == old.SUB and value['tenantId'] == a.TENANT
                and value['state'] == 'Enabled', 'account_identity')
        return value

    def capture(self, cleanup: bool = False) -> JSON:
        from scripts.deployment import restore22_successor as projections
        self.capture_number += 1
        prefix = 'capture-' + str(self.capture_number).zfill(3) + '/'
        def write(name: str, value: Any) -> str:
            return self.write(prefix + name, value)
        token, claims = self.credentials.get(a.ARM, cleanup)
        # All original methods close over an instance-local writer; commands and
        # cached collection receipts never touch the consumed resume04 directory.
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
                from urllib.parse import urlsplit
                initial, visited, rows, envelope = urlsplit(url), set(), [], None
                while url:
                    parsed = urlsplit(url)
                    a.require(parsed.scheme == initial.scheme and parsed.netloc == initial.netloc
                        and parsed.path == initial.path and url not in visited and len(visited) < 30,
                        'complete_scoped_pages')
                    visited.add(url)
                    page = reader.get(url)
                    a.require(isinstance(page.get('value'), list) and set(page) <= {'value', 'nextLink'},
                        'complete_known_collection_envelope')
                    envelope = envelope or page
                    rows.extend(page['value'])
                    url = page.get('nextLink')
                return {'value': rows}
        reader = Reader()
        storage, storage_claims = self.credentials.get(a.STORAGE, cleanup)
        def root_read() -> tuple[JSON, str]:
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
        # Both revision details and all owned-operation/product inheritance are
        # retained, not merely a hash of the active API's policy.
        inheritance: JSON = {}
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
        # Explicit sole representation projection after exact whole-tree proof.
        snapshot['baseline']['apim']['global'] = renderer.sha(policies['global'])
        a.require(time.monotonic() < reader.deadline, 'finite_capture_deadline')
        return {'snapshot': snapshot, 'deployments': deployments, 'root': root,
            'child': child, 'roles': snapshot['baseline']['runtime']['roleAssignments'],
            'inheritance': inheritance, 'revisions': revisions, 'owned': owned,
            'policies': policies, 'etags': etags, 'sources': self.sources()}

    def send(self, stage: str, body: bytes, etag: str, timeout: float,
             cleanup: bool = False) -> JSON:
        """Exactly one open. Any timeout/error is UNKNOWN until fresh reconciliation."""
        a.require(stage in URLS and 0 < timeout <= 45, 'finite_target_timeout')
        p.strong_etag(etag)
        value = json.loads(body)
        if stage in ('online', 'offline'):
            a.require(value == {'properties': {'isOnline': stage == 'online'}}, 'exact_API_patch')
        else:
            a.require(set(value) == {'properties'} and set(value['properties']) == {'format', 'value'}
                and value['properties']['format'] == 'xml', 'exact_policy_PUT_format')
        token, _ = self.credentials.get(a.ARM, cleanup)
        request = Request(URLS[stage], method='PATCH' if stage in ('online', 'offline') else 'PUT',
            data=body, headers={'Authorization': 'Bearer ' + token, 'If-Match': etag,
                'Content-Type': 'application/json', 'Accept': 'application/json'})
        with self.http.open(request, timeout=timeout) as response:
            a.require(response.geturl() == URLS[stage] and response.status in (200, 201), 'actual_HTTP200_201')
            result = {'http_status': response.status, 'etag': p.strong_etag(response.headers.get('ETag'))}
            # Do not log a service response body or authentication headers.
            return result