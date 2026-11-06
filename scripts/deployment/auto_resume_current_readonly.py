"""New resume04 read-only baseline; never invokes an old collector/prepare.

Only audited projection functions are reused, with this private transport.
No retries, credential export, scoring or cloud mutation entrypoint exists.
"""
import base64
from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

from scripts.deployment import auto_resume_current_adapter as a

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT/'.deployment/auto-resume04'
LATEST = ROOT/'.deployment/uv-apply01/remaining02'
SUB = 'aa28274d-fea0-46d4-b9c8-30f3ef0a0e52'
RG = '/subscriptions/'+SUB+'/resourceGroups/IDS-TOKEN-EXCHANGE-POC'
APIM = RG+'/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim'
BLOB = 'https://projpoctokenex.blob.core.windows.net/tfstate/poc-ids-token-ex/main.tfstate'
CA = Path('C:/Users/p4032099/.azure/ca-bundle-zscaler.pem')
CLI = ['C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe', '-X', 'utf8', '-IBm', 'azure.cli']
require, sha = a.require, a.sha


def now():
    return datetime.now(UTC).isoformat()


def load(path):
    return json.loads(path.read_bytes())


def write(name, value):
    path = HOME/name
    require(path.resolve().is_relative_to(HOME.resolve()), 'owned_output')
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2)+'\n').encode()
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return sha(raw)


def environment():
    return {**os.environ, 'REQUESTS_CA_BUNDLE': str(CA), 'SSL_CERT_FILE': str(CA)}


def command(label, argv, secret=False):
    write('commands/'+label+'-intent.json', {'at': now(), 'argv': argv, 'max_invocations': 1})
    child = subprocess.Popen(argv, cwd=ROOT, env=environment(), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    write('commands/'+label+'-worker.json', {'pid': child.pid, 'parent_pid': os.getpid(), 'at': now()})
    try:
        out, err = child.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        write('commands/'+label+'-pending.json', {'original_pid': child.pid, 'no_retry': True, 'not_killed': True})
        raise ValueError('original_command_pending_no_replay') from None
    write('commands/'+label+'-result.json', {'exit_code': child.returncode, 'at': now(),
        'secret_material_not_persisted': secret, 'stderr_sha256': sha(err),
        'stdout_sha256': None if secret else sha(out)})
    require(child.returncode == 0, 'command_failed_no_retry:'+label)
    return json.loads(out)


def credential(audience, label):
    value = command(label, [CLI[0], '-B', str(Path(__file__).with_name('auto_resume_current_credentials.py')),
                            SUB, a.TENANT, audience], secret=True)
    token = value['access_token']
    part = token.split('.')[1]
    claims = json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
    metadata = a.token_claims(claims, audience, time.time())
    write(label+'-identity.json', {'at': now(), **metadata, 'acquisitions': 1, 'force_refresh': False})
    return token, claims


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Reads:
    def __init__(self, token, claims):
        self.token, self.claims = token, claims
        self.cache, self.records, self.count = {}, {}, 0
        self.deadline = time.monotonic()+900
        require(sha(CA.read_bytes()) == 'e747e9880a4e63c73f55af589941139d0a4f90ceec5df745cfd6fee5bbe257dc', 'pinned_CA')
        context = ssl.create_default_context(cafile=str(CA))
        require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, 'verified_TLS')
        self.opener = build_opener(HTTPSHandler(context=context), NoRedirect())

    def request(self, url, method='GET', optional=False):
        parsed = urlsplit(url)
        require(parsed.scheme == 'https' and parsed.netloc == 'management.azure.com'
                and not parsed.fragment and not parsed.username, 'ARM_only')
        require(url.startswith(a.ARM.rstrip('/')+RG+'/providers/') or url.startswith(a.ARM+'subscriptions/'+SUB+'/providers/Microsoft.Authorization/'), 'scope')
        require(not re.search('listKeys|listSecrets|/secrets/|regenerate', url, re.I), 'no_keys_secrets')
        settings = re.fullmatch(re.escape(a.ARM.rstrip('/')+RG)+r'/providers/Microsoft.Web/sites/poc-ids-token-ex-(api|admin|customer|ingestion)/config/appsettings/list\?api-version=2024-04-01', url)
        require(method == 'GET' or method == 'POST' and settings, 'semantic_read_only')
        key = (method, url)
        if key in self.cache:
            return deepcopy(self.cache[key])
        a.token_claims(self.claims, a.ARM, time.time())
        require(time.monotonic() < self.deadline and self.count < 180, 'bounded_capture')
        self.count += 1
        stem = 'reads/'+str(self.count).zfill(3)
        write(stem+'-intent.json', {'at': now(), 'method': method, 'url': url, 'max_invocations': 1})
        try:
            with self.opener.open(Request(url, method=method, headers={'Authorization': 'Bearer '+self.token}),
                                  timeout=min(90, max(1, self.deadline-time.monotonic()))) as response:
                raw = response.read(16*1024*1024+1)
                require(response.status == 200 and response.geturl() == url and len(raw) <= 16*1024*1024, 'bounded_exact_HTTP200')
                value = json.loads(raw)
                record = {'at': now(), 'status': 200, 'body_sha256': sha(raw),
                          'etag': response.headers.get('ETag'), 'request_id': response.headers.get('x-ms-request-id')}
                write(stem+'-result.json', record)
                self.records[url] = record
                self.cache[key] = value
                return deepcopy(value)
        except HTTPError as exc:
            write(stem+'-result.json', {'at': now(), 'status': exc.code, 'no_retry': True})
            if optional and exc.code == 404:
                self.cache[key] = {'absent': True, 'status': 404}
                return deepcopy(self.cache[key])
            raise ValueError('HTTP_'+str(exc.code)) from None

    def get(self, url, optional=False):
        return self.request(url, optional=optional)

    def arm(self, path, method='GET', raw=False):
        require(not raw, 'JSON_only')
        version = '2023-07-01' if '/Microsoft.KeyVault/' in path else '2024-08-01' if '/Microsoft.DBforPostgreSQL/' in path else '2024-04-01'
        return self.request(a.ARM.rstrip('/')+path+('&' if '?' in path else '?')+'api-version='+version, method)

    def collection(self, url):
        initial, visited, rows, pages = urlsplit(url), set(), [], []
        while url:
            parsed = urlsplit(url)
            require(parsed.scheme == initial.scheme and parsed.netloc == initial.netloc
                    and parsed.path == initial.path and url not in visited and len(visited) < 30, 'complete_scoped_pages')
            visited.add(url)
            page = self.get(url)
            require(isinstance(page.get('value'), list) and not any(k in page for k in ('error', 'partial', 'partialError', '@odata.nextLink')), 'complete_collection')
            pages.append(page)
            rows.extend(page['value'])
            url = page.get('nextLink')
        receipt = {'count': len(rows), 'pages': len(pages), 'whole_rows_sha256': sha(rows)}
        name = 'collections/'+sha(initial.path.encode())[:16]+'.json'
        if (HOME/name).exists():
            require(load(HOME/name) == receipt, 'cached_complete_collection_exact')
        else:
            write(name, receipt)
        return {k: v for k, v in pages[0].items() if k != 'nextLink'} | {'value': rows}

    def cli(self, args):
        if args[:4] == ['rest', '--method', 'get', '--url'] and len(args) == 5:
            return self.get(args[4])
        require(args == ['account', 'show'] or args == ['role', 'assignment', 'list', '--subscription', SUB, '--all', '--include-inherited'], 'exact_original_CLI_projection')
        key = ('CLI', tuple(args))
        if key not in self.cache:
            value = command('account' if args[0] == 'account' else 'full-inherited-roles', CLI+args+['--only-show-errors', '-o', 'json'])
            if args[0] == 'role':
                write('full-role-rows.json', value)
            else:
                require(value['id'] == SUB and value['tenantId'] == a.TENANT and value['state'] == 'Enabled', 'account_context')
            self.cache[key] = value
        return deepcopy(self.cache[key])


def source_gate():
    prior = load(ROOT/'.deployment/auto-resume03/current-source-baseline.json')['sources']
    changes = [name for name, digest in prior.items() if not (ROOT/name).is_file() or sha((ROOT/name).read_bytes()) != digest]
    write('source-base-proof.json', {'count': len(prior), 'changes': changes, 'sources': prior})
    require(len(prior) == 280 and not changes, 'current280_source_base_changed')
    return prior


def head(reader, token, claims, label):
    a.token_claims(claims, a.STORAGE, time.time())
    write(label+'-intent.json', {'at': now(), 'method': 'HEAD', 'url': BLOB, 'max_invocations': 1})
    headers = {'Authorization': 'Bearer '+token, 'x-ms-version': '2023-11-03',
               'x-ms-date': datetime.now(UTC).strftime('%a, %d %b %Y %H:%M:%S GMT')}
    with reader.opener.open(Request(BLOB, method='HEAD', headers=headers), timeout=90) as response:
        require(response.geturl() == BLOB, 'exact_blob_no_redirect')
        result = {'at': now(), 'status': response.status, 'etag': response.headers.get('ETag'),
                  'lease_state': response.headers.get('x-ms-lease-state'), 'lease_status': response.headers.get('x-ms-lease-status')}
    write(label+'-result.json', result)
    require(result['status'] == 200 and result['lease_state'] == 'available' and result['lease_status'] == 'unlocked', 'unlocked_HEAD200')
    a.etag(result['etag'])
    return result


def run():
    write('baseline-intent.json', {'at': now(), 'pid': os.getpid(), 'read_only': True, 'retry_budget': 0,
        'reason': 'user_resumes_current_readonly_baseline_and_OFFLINE_successor', 'scoring': 0, 'cloud_mutation': 0})
    source_gate()
    old = load(ROOT/'.deployment/auto-resume03/immutable-before.json')
    old.update({p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in (ROOT/'.deployment/auto-resume03').rglob('*') if p.is_file()})
    write('immutable-before.json', old)
    # Only the existing local worker classifier is reused; no old wire function.
    spec = importlib.util.spec_from_file_location('resume04_local_worker_utilities', ROOT/'.deployment/auto-resume01/phase1.py')
    workers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(workers)
    workers.HOME = HOME
    require(not workers.workers('resume04')['blockers'], 'competing_worker')
    token, claims = credential(a.ARM, 'arm-auth')
    storage, storage_claims = credential(a.STORAGE, 'storage-auth')
    reader = Reads(token, claims)
    opening = head(reader, storage, storage_claims, 'closing-old-and-opening-current')
    retained_head = load(ROOT/'.deployment/auto-resume02/backend-open-result.json')
    write('old-closing-proof.json', {'same_retained_GET_etag': opening['etag'] == retained_head['etag'], 'head': opening})
    require(opening['etag'] == retained_head['etag'], 'old_root_ETag_changed')
    # Actual fresh root GET is conditional and remains only in memory.
    a.token_claims(storage_claims, a.STORAGE, time.time())
    write('root-GET-intent.json', {'method': 'GET', 'url': BLOB, 'if_match': opening['etag'], 'max_invocations': 1})
    with reader.opener.open(Request(BLOB, headers={'Authorization': 'Bearer '+storage,
        'x-ms-version': '2023-11-03', 'x-ms-date': datetime.now(UTC).strftime('%a, %d %b %Y %H:%M:%S GMT'),
        'If-Match': opening['etag']}), timeout=90) as response:
        raw = response.read(16*1024*1024+1)
        require(response.status == 200 and response.geturl() == BLOB and response.headers.get('ETag') == opening['etag']
                and len(raw) <= 16*1024*1024, 'conditional_root_read')
    state = json.loads(raw)
    equal = a.state_equal(load(LATEST/'commands/state-after.stdout.txt'), state)
    write('root-proof.json', {'at': now(), 'serial': state['serial'], 'lineage': state['lineage'], 'whole_keyed_equal': equal,
          'raw_sha256': sha(raw), 'etag': opening['etag'], 'check_count': len(state['check_results']), 'ignored_fields': []})
    require(state['serial'] == 130 and equal, 'current_root130_whole_equal')
    from scripts.deployment import restore22_successor as s
    snapshot, policy, backends = s.g.rebound(s.old.capture, ReadOnly=lambda label: reader, write=write)('protected')
    prior = load(LATEST/'postapply-snapshot.json')
    # Use EXACT original CLI inherited role projection, never REST flattening.
    def paths(before, after, path=''):
        if type(before) is not type(after):
            return [path]
        if isinstance(before, dict):
            return [p for key in sorted(before.keys() | after.keys()) for p in
                    (paths(before[key], after[key], path+'/'+key) if key in before and key in after else [path+'/'+key])]
        if isinstance(before, list):
            return [path] if len(before) != len(after) else [p for i, (x, y) in enumerate(zip(before, after)) for p in paths(x, y, path+'/'+str(i))]
        return [] if before == after else [path]
    differences = paths(prior, snapshot)
    write('complete-protected-comparison.json', {'at': now(), 'exact_difference_paths': differences,
        'whole_equal': not differences, 'roles_projection_equal': snapshot['baseline']['runtime']['roleAssignments'] == prior['baseline']['runtime']['roleAssignments']})
    require(not differences, 'complete_protected_snapshot_changed')
    require(policy.encode() == (LATEST/'postapply-policy.xml').read_bytes(), 'fresh_actual_XML_same_format_exact')
    require({row['name']: s.g.digest(row) for row in backends['value']} == load(LATEST/'postapply-backend-hashes.json'), 'complete_backend_bodies_equal')
    require(len(s.g.advertised(s.g.xml_node(policy, exported=True))) == 22, 'current_all22_routes')
    # Compare decoded XML expression trees independently; actual rawxml is optional,
    # not a reason to block when fresh actual same-format XML is byte-exact.
    require(a.xml_tree(policy, True) == a.xml_tree((LATEST/'postapply-policy.xml').read_bytes().decode(), True), 'exact_decoded_XML_expressions')
    formats = []
    revisions = reader.collection(a.ARM.rstrip('/')+APIM+'/apis/aiflux-dev-unified/revisions?api-version=2024-05-01')
    write('revisions-full.json', revisions)
    for suffix, label in [('', 'global'), ('/apis/aiflux-dev-unified', 'active')]+[
            ('/apis/aiflux-dev-unified;rev='+row['properties']['apiRevision'], 'revision-'+row['properties']['apiRevision']) for row in revisions['value']]:
        if label.startswith('revision-'):
            detail = reader.get(a.ARM.rstrip('/')+APIM+suffix+'?api-version=2024-05-01')
            write(label+'-detail.json', detail)
        url = a.ARM.rstrip('/')+APIM+suffix+'/policies/policy?format=xml&api-version=2024-05-01'
        value = reader.get(url, optional=True)
        # XML policy values only; keys/settings/tokens never written.
        if not value.get('absent'):
            write(label+'-actual.xml', value['properties']['value'].encode())
            formats.append({'scope': label, 'format': 'xml', 'value_sha256': sha(value['properties']['value'].encode()),
                            'etag': reader.records[url]['etag'], 'actual_wire': reader.records[url]})
    write('formats-etags.json', formats)
    child_raw = (ROOT/'infra/project-route/terraform.tfstate').read_bytes()
    child = json.loads(child_raw)
    require(child['serial'] == 191 and sha(child_raw) == load(ROOT/'.deployment/auto-resume03/state-owner-proof.json')['child_sha256'], 'child191_exact_local_owner')
    closing = head(reader, storage, storage_claims, 'current-close')
    require(opening['etag'] == closing['etag'] and time.monotonic() < reader.deadline, 'coherent_baseline_ETag_deadline')
    changed = [name for name, digest in old.items() if sha((ROOT/name).read_bytes()) != digest]
    write('preservation-proof.json', {'files': len(old), 'old890_included': True, 'changed': changed})
    require(not changed, 'old_evidence_changed')
    write('baseline-result.json', {'at': now(), 'complete_protected_snapshot_equal': True, 'full_roles_projection_equal': True,
        'fresh_actual_XML_byte_exact': True, 'decoded_expressions_exact': True, 'rawxml_optional_not_claimed': True,
        'root_serial': 130, 'child_serial': 191, 'child_remote_claim': False, 'root_etag_stable': True,
        'protected_reads': reader.count, 'Auto': 'OFF_PENDING_VALIDATION', 'task_complete': False,
        'budget_used': {'isolated_score': 0, 'Auto_chat': 0}, 'cloud_mutation': 0})


if __name__ == '__main__':
    require(sys.argv[1:] == ['baseline-once'], 'only_explicit_readonly_action')
    try:
        run()
    except Exception as exc:
        write('baseline-STOP.json', {'at': now(), 'type': type(exc).__name__,
            'reason': str(exc) if isinstance(exc, ValueError) else 'private_error_not_exported',
            'no_retry': True, 'task_complete': False, 'Auto': 'OFF_PENDING_VALIDATION'})
        print(json.dumps(load(HOME/'baseline-STOP.json')), flush=True)
        raise SystemExit(2)
    print(json.dumps(load(HOME/'baseline-result.json')), flush=True)