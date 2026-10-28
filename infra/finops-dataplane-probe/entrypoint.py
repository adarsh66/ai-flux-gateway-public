"""Hash-bound, one-shot, finite-output supervisor. No arbitrary commands."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SERVICES = {'postgres', 'monitor', 'blob', 'queue', 'table'}
REASONS = {'verified', 'network_failure', 'identity_failure', 'claims_mismatch', 'dns_mismatch',
           'service_rejected', 'partial_query_rejected', 'unexpected_result', 'runtime_failure'}
ERRORS = {'AuthorizationPermissionMismatch', 'AuthorizationFailure', 'AuthenticationFailed',
    'InvalidAuthenticationInfo', 'InsufficientAccountPermissions', 'AccountIsDisabled',
    'InsufficientAccessError', 'UnauthorizedClient', 'Forbidden', 'InvalidToken',
    'InvalidAuthenticationToken', 'InvalidQuery', 'BadArgumentError', 'PartialError',
    'TableNotFound', 'ContainerNotFound', 'QueueNotFound', 'ServerBusy', 'OperationTimedOut'}
HTTP = {200, 201, 202, 204, 206, 400, 401, 403, 404, 408, 409, 429, 500, 502, 503, 504}


def failure():
    return {'status': 'data_plane_output_rejected', 'reason': 'finite_output_contract_failed'}


def sanitize(content, exit_code):
    try:
        assert type(content) is str and len(content) <= 16384 and type(exit_code) is int and exit_code in (0, 2)
        value = json.loads(content)
        assert set(value) == {'status', 'checks', 'database_writes', 'storage_writes', 'retries',
                             'storage_write_permission_proven', 'identity_source'}
        assert all(type(value[k]) is int and value[k] == 0 for k in ('database_writes', 'storage_writes', 'retries'))
        assert value['storage_write_permission_proven'] is False
        assert value['identity_source'] == 'explicit_ingestion_managed_identity'
        assert set(value['checks']) == SERVICES
        for item in value['checks'].values():
            assert set(item) == {'status', 'stage', 'http_status', 'azure_error_code', 'reason',
                                 'claims_verified', 'started_at_utc', 'finished_at_utc'}
            assert item['status'] in {'passed', 'failed'} and item['reason'] in REASONS
            assert item['stage'] in {'dns', 'identity_token', 'token_claims', 'select', 'query', 'list_metadata', 'complete'}
            assert type(item['claims_verified']) is bool
            assert item['http_status'] is None or (type(item['http_status']) is int and item['http_status'] in HTTP)
            assert item['azure_error_code'] is None or item['azure_error_code'] in ERRORS
            for k in ('started_at_utc', 'finished_at_utc'):
                assert type(item[k]) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?\+00:00', item[k])
                datetime.fromisoformat(item[k])
            if item['status'] == 'passed':
                assert item['claims_verified'] and item['stage'] == 'complete' and item['reason'] == 'verified'
        success = all(x['status'] == 'passed' for x in value['checks'].values())
        assert value['status'] == ('verified_data_plane' if success else 'data_plane_failed')
        return value
    except Exception:
        return failure()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-sha256', required=True)
    parser.add_argument('--identity', choices=['ingestion'], required=True)
    args = parser.parse_args()
    probe = Path(__file__).with_name('finops_private_probe.py')
    try:
        assert re.fullmatch('[0-9a-f]{64}', args.probe_sha256) and hashlib.sha256(probe.read_bytes()).hexdigest() == args.probe_sha256
        fd = os.open('/scratch/probe-started', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        child = subprocess.run([sys.executable, '-I', str(probe)], capture_output=True, text=True, timeout=590)
        result = sanitize(child.stdout, child.returncode)
    except Exception:
        result = failure()
    print(json.dumps(result), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())