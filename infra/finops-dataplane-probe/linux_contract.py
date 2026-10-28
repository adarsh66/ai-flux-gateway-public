"""Native SDK synthetic-transport contract. No cloud requests or credentials."""
import base64
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(*, native_required=True):
    assert not native_required or sys.platform == 'linux'
    def forbidden(*args, **kwargs):
        raise AssertionError('contract_network_forbidden')
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    probe, supervisor = load('finops_private_probe'), load('entrypoint')
    from azure.core.credentials import AccessToken
    from azure.core.pipeline.transport import HttpResponse, HttpTransport
    from azure.monitor.query import LogsQueryClient
    from azure.storage.blob import BlobServiceClient
    from azure.storage.queue import QueueServiceClient
    from azure.data.tables import TableServiceClient
    def token(audience):
        value = {'tid': probe.TENANT, 'oid': probe.OBJECT, 'aud': audience, 'exp': int(time.time()) + 3600}
        return 'eyJhbGciOiJSUzI1NiJ9.' + base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=') + '.c3R1Yg'
    class Credential:
        def get_token(self, scope, **kwargs):
            return AccessToken(token(scope.removesuffix('/.default')), int(time.time()) + 3600)
    class Response(HttpResponse):
        def __init__(self, request):
            super().__init__(request, None)
            self.status_code = 200
            if '.blob.' in request.url:
                self.content_type = 'application/xml'
                self.data = b'<?xml version="1.0"?><EnumerationResults><Containers/><NextMarker/></EnumerationResults>'
            elif '.queue.' in request.url:
                self.content_type = 'application/xml'
                self.data = b'<?xml version="1.0"?><EnumerationResults><Queues/><NextMarker/></EnumerationResults>'
            else:
                self.content_type = 'application/json'
                self.data = json.dumps({'value': []} if '.table.' in request.url else
                    {'tables': [{'name': 'PrimaryResult', 'columns': [{'name': 'ingestion_probe', 'type': 'long'}], 'rows': [[1]]}]}).encode()
            self.headers = {'Content-Type': self.content_type, 'content-type': self.content_type, 'x-ms-version': '2020-12-06'}
        def body(self): return self.data
        @property
        def content(self): return self.data
        def json(self): return json.loads(self.data)
    class Transport(HttpTransport):
        def __init__(self): self.requests = []
        def open(self): pass
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send(self, request, **kwargs):
            self.requests.append(request)
            assert request.method in {'GET', 'POST'}
            if request.method == 'POST':
                assert request.url.startswith('https://api.loganalytics.io/')
                body = request.body
                assert json.loads(body)['query'] == 'print ingestion_probe=1'
            assert 'Bearer ' in request.headers['Authorization']
            return Response(request)
    credential = Credential()
    for service, cls, target in [('monitor', LogsQueryClient, 'azure.monitor.query.LogsQueryClient'),
            ('blob', BlobServiceClient, 'azure.storage.blob.BlobServiceClient'),
            ('queue', QueueServiceClient, 'azure.storage.queue.QueueServiceClient'),
            ('table', TableServiceClient, 'azure.data.tables.TableServiceClient')]:
        transport = Transport()
        with patch(target, side_effect=lambda *a, _cls=cls, **kw: _cls(*a, transport=transport, **kw)), \
                patch.object(probe, 'private_dns', return_value=None):
            operation = (lambda p: probe.monitor(credential, p)) if service == 'monitor' else \
                        (lambda p: probe.storage(service, credential, p))
            def observed(progress):
                try:
                    return operation(progress)
                except Exception as exc:
                    import traceback
                    print(json.dumps({'contract_service': service, 'exception_type': type(exc).__name__,
                        'synthetic_attribute': exc.name if isinstance(exc, AttributeError) else None,
                        'source_frames': [{'file': Path(f.filename).name, 'line': f.lineno} for f in traceback.extract_tb(exc.__traceback__)]}), flush=True)
                    raise
            result = probe.outcome(service, observed)
            assert result['status'] == 'passed', (service, result)
            assert result['http_status'] == 200 and result['claims_verified']
            assert len(transport.requests) == 1
    for bad in ('https://management.azure.com', 'https://storage.azure.com/wrong'):
        try: probe.claims(token(bad), 'https://storage.azure.com')
        except probe.Blocked: pass
        else: raise AssertionError('wrong_audience_accepted')
    print('FINOPS_DATAPLANE_NATIVE_SDK_CONTRACT_PASSED', flush=True)


if __name__ == '__main__':
    main()