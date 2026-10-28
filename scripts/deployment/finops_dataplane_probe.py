"""Finite ingestion-MI SELECT, Monitor print, and storage metadata reads only.

No application import, seeding, entity/message/blob reads, writes or retries.
All endpoints are fixed and compared with current ARM metadata by the controller.
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
import logging
import socket
import ssl
import time

CLIENT = 'e1d25c87-9df1-4225-9744-ce22121cf462'
OBJECT = 'edbfc3e2-a8e5-4652-9bb0-311233756d42'
TENANT = 'beb276ac-6e9f-498e-8e31-019ee666decd'
WORKSPACE = '004a359b-dde6-40fb-843c-4d5651785e17'
STORAGE = 'pocidstokenexfunc'
IPS = {'blob': '10.240.3.6', 'queue': '10.240.3.7', 'table': '10.240.3.8'}
PG = 'poc-ids-token-ex-pg.postgres.database.azure.com'
ROLE = 'poc-ids-token-ex-ingestion-identity'
SERVICES = ('postgres', 'monitor', 'blob', 'queue', 'table')
STAGES = {'dns', 'identity_token', 'token_claims', 'select', 'query', 'list_metadata', 'complete'}
ERRORS = {'AuthorizationPermissionMismatch', 'AuthorizationFailure', 'AuthenticationFailed',
    'InvalidAuthenticationInfo', 'InsufficientAccountPermissions', 'AccountIsDisabled',
    'InsufficientAccessError', 'UnauthorizedClient', 'Forbidden', 'InvalidToken',
    'InvalidAuthenticationToken', 'InvalidQuery', 'BadArgumentError', 'PartialError',
    'TableNotFound', 'ContainerNotFound', 'QueueNotFound', 'ServerBusy', 'OperationTimedOut'}
HTTP = {200, 201, 202, 204, 206, 400, 401, 403, 404, 408, 409, 429, 500, 502, 503, 504}
REASONS = {'verified', 'network_failure', 'identity_failure', 'claims_mismatch', 'dns_mismatch',
           'service_rejected', 'partial_query_rejected', 'unexpected_result', 'runtime_failure'}


class Blocked(ValueError):
    pass


def require(value, label):
    if not value:
        raise Blocked(label)


def claims(token, audience):
    """In-memory consistency only; each actual service validates the signature."""
    try:
        part = token.split('.')[1]
        value = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        require(value.get('tid') == TENANT and value.get('oid') == OBJECT and
                value.get('aud', '').rstrip('/') == audience.rstrip('/') and
                type(value.get('exp')) in (int, float) and value['exp'] > time.time() + 30,
                'claims_mismatch')
    except Exception:
        raise Blocked('claims_mismatch') from None


def private_dns(host, expected):
    addresses = {a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    require(addresses == {expected}, 'dns_mismatch')


def outcome(service, operation):
    progress = {'stage': 'dns', 'http_status': None}
    started = datetime.now(UTC).isoformat()
    result = {'status': 'failed', 'stage': 'dns', 'http_status': None, 'azure_error_code': None,
              'reason': 'runtime_failure', 'claims_verified': False, 'started_at_utc': started}
    try:
        operation(progress)
        result.update(status='passed', stage='complete', reason='verified',
                      claims_verified=progress.get('claims_verified', False))
    except Exception as exc:
        status = getattr(exc, 'status_code', None)
        response = getattr(exc, 'response', None)
        if response is not None:
            status = getattr(response, 'status_code', status)
        code = getattr(exc, 'error_code', None)
        if code is None:
            code = getattr(getattr(exc, 'error', None), 'code', None)
        result.update(stage=progress['stage'], http_status=status if type(status) is int and status in HTTP else None,
            azure_error_code=code if isinstance(code, str) and code in ERRORS else None,
            claims_verified=progress.get('claims_verified', False))
        kind = type(exc).__name__
        result['reason'] = (str(exc) if type(exc) is Blocked and str(exc) in REASONS else
            'service_rejected' if result['http_status'] else
            'network_failure' if kind in {'ServiceRequestError', 'ServiceResponseError', 'gaierror', 'TimeoutError', 'SSLError'} else
            'identity_failure' if kind in {'ClientAuthenticationError', 'CredentialUnavailableError'} else 'runtime_failure')
    if result['http_status'] is None:
        result['http_status'] = progress['http_status'] if progress['http_status'] in HTTP else None
    result['finished_at_utc'] = datetime.now(UTC).isoformat()
    return result


def acquire(credential, audience, progress):
    progress['stage'] = 'identity_token'
    token = credential.get_token(audience + '/.default')
    progress['stage'] = 'token_claims'
    claims(token.token, audience)
    progress['claims_verified'] = True
    return token


def postgres(credential, progress):
    import psycopg
    private_dns(PG, '10.240.3.12')
    token = acquire(credential, 'https://ossrdbms-aad.database.windows.net', progress)
    progress['stage'] = 'select'
    # libpq startup enforces read-only before any SQL. No app initialization.
    with psycopg.connect(host=PG, hostaddr='10.240.3.12', dbname='turnstile', user=ROLE,
            password=token.token, sslmode='verify-full', sslrootcert=ssl.get_default_verify_paths().cafile,
            connect_timeout=8, options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000 -c search_path=public,pg_catalog') as db:
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT 1, current_database(), session_user, current_user, current_schema(), current_setting('transaction_read_only'), (SELECT count(*) FROM public.ingestion_state)")
                row = cursor.fetchone()
                require(row[:6] == (1, 'turnstile', ROLE, ROLE, 'public', 'on') and type(row[6]) is int,
                        'unexpected_result')
        finally:
            db.rollback()


def monitor(credential, progress):
    from azure.monitor.query import LogsQueryClient, LogsQueryStatus
    acquire(credential, 'https://api.loganalytics.io', progress)
    progress['stage'] = 'query'
    def hook(response):
        progress['http_status'] = response.http_response.status_code
    with LogsQueryClient(credential, retry_total=0, connection_timeout=8, read_timeout=20) as client:
        result = client.query_workspace(WORKSPACE, 'print ingestion_probe=1',
            timespan=timedelta(minutes=1), server_timeout=15, raw_response_hook=hook)
        require(result.status == LogsQueryStatus.SUCCESS, 'partial_query_rejected')
        require(len(result.tables) == 1 and [list(row) for row in result.tables[0].rows] == [[1]], 'unexpected_result')


def storage(service, credential, progress):
    host = STORAGE + '.' + service + '.core.windows.net'
    private_dns(host, IPS[service])
    acquire(credential, 'https://storage.azure.com', progress)
    progress['stage'] = 'list_metadata'
    def hook(response):
        progress['http_status'] = response.http_response.status_code
    options = dict(credential=credential, retry_total=0, connection_timeout=8, read_timeout=15)
    if service == 'blob':
        from azure.storage.blob import BlobServiceClient
        client = BlobServiceClient('https://' + host, **options)
        operation = lambda: client.list_containers(results_per_page=1, raw_response_hook=hook).by_page()
    elif service == 'queue':
        from azure.storage.queue import QueueServiceClient
        client = QueueServiceClient('https://' + host, **options)
        operation = lambda: client.list_queues(results_per_page=1, raw_response_hook=hook).by_page()
    else:
        from azure.data.tables import TableServiceClient
        client = TableServiceClient('https://' + host, **options)
        operation = lambda: client.list_tables(results_per_page=1, raw_response_hook=hook).by_page()
    with client:
        # One page only; names stay in memory, no entities/messages/blob content.
        page = next(operation())
        next(iter(page), None)


def main():
    logging.disable(logging.CRITICAL)
    from azure.identity import ManagedIdentityCredential
    with ManagedIdentityCredential(client_id=CLIENT, retry_total=0, connection_timeout=5, read_timeout=10) as credential:
        checks = {'postgres': outcome('postgres', lambda p: postgres(credential, p)),
                  'monitor': outcome('monitor', lambda p: monitor(credential, p))}
        for service in ('blob', 'queue', 'table'):
            checks[service] = outcome(service, lambda p, s=service: storage(s, credential, p))
    success = all(value['status'] == 'passed' for value in checks.values())
    print(json.dumps({'status': 'verified_data_plane' if success else 'data_plane_failed',
        'checks': checks, 'database_writes': 0, 'storage_writes': 0, 'retries': 0,
        'storage_write_permission_proven': False, 'identity_source': 'explicit_ingestion_managed_identity'}), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(main())