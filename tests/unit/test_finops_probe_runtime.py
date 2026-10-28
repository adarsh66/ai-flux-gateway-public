"""Offline dependency contracts; synthetic inputs only, never Azure/PG calls."""
import json
from decimal import Decimal
from pathlib import Path
import subprocess
import sys

from psycopg.types.numeric import NumericLoader

from tests.unit.test_finops_private_probe import Database, NOW, ROLE, probe
from tests.unit.test_finops_runner_preparation import entrypoint


def test_real_psycopg_numeric_aggregates_survive_both_sanitizers():
    db = Database()
    # PostgreSQL SUM(bigint) returns numeric (OID 1700), not bigint.
    load = NumericLoader(1700).load
    db.answers[9] = (2, load(b"11"), load(b"107"), 1, 2, load(b"18"))
    assert isinstance(db.answers[9][1], Decimal)
    report = probe.inspect_database(db, ROLE, now=NOW)
    for key in ("known_input_tokens", "known_output_tokens", "fully_measured_total_tokens"):
        assert type(report["window"][key]) is int
    rendered = json.dumps(report, default=str)
    supervisor = entrypoint()
    first = supervisor.sanitize(rendered, 0)
    assert first["status"] == "verified_read_only_snapshot"
    assert supervisor.sanitize(json.dumps(first), 0) == first
    assert db.rolled_back


def test_retained_identity_and_jwt_wheels_with_network_forbidden():
    """Use retained exact pure wheels; native Windows crypto is NOT Linux proof."""
    root = Path(__file__).resolve().parents[2]
    wheels = root / ".deployment/finops-runner/2f75015b55d1/image-context/wheels"
    assert wheels.is_dir(), "retained image dependency evidence is required"
    import hashlib
    manifest = json.loads((root / "gateway/validation/finops-runner-image-20261027.json").read_text())
    for path in wheels.glob("*.whl"):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["context_files_sha256"]["wheels/" + path.name]
    code = r'''
import sys, pathlib, socket, os, json, base64, time
wheels = pathlib.Path(sys.argv[1])
# Override pure dependencies with the actual retained image wheels; do not load
# Linux-native .so files into Windows or claim binary equivalence.
pure = [str(p) for p in wheels.glob('*.whl') if '-none-any.whl' in p.name]
sys.path[:0] = pure + [sys.argv[2]]
def forbidden(*args, **kwargs):
    raise AssertionError('offline network forbidden')
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.getaddrinfo = forbidden
for name in ('IDENTITY_ENDPOINT', 'IDENTITY_HEADER', 'MSI_ENDPOINT', 'MSI_SECRET',
             'IMDS_ENDPOINT', 'AZURE_POD_IDENTITY_AUTHORITY_HOST'):
    os.environ.pop(name, None)
from azure.identity import ManagedIdentityCredential
from azure.core.pipeline.transport import HttpTransport, HttpResponse
import jwt, msal
assert jwt.__version__ == '2.15.1' and msal.__version__ == '1.39.0'
client = 'e1d25c87-9df1-4225-9744-ce22121cf462'
claims = {'tid':'beb276ac-6e9f-498e-8e31-019ee666decd',
          'oid':'edbfc3e2-a8e5-4652-9bb0-311233756d42',
          'aud':'https://ossrdbms-aad.database.windows.net', 'exp':int(time.time())+3600}
enc = lambda v: base64.urlsafe_b64encode(json.dumps(v).encode()).decode().rstrip('=')
token = enc({'alg':'RS256','typ':'JWT'}) + '.' + enc(claims) + '.c3ludGhldGlj'
class Response(HttpResponse):
    def __init__(self, request):
        super().__init__(request, None)
        self.status_code = 200
        self.headers = {'Content-Type':'application/json'}
        self.content_type = 'application/json'
    def body(self):
        return json.dumps({'access_token':token,'expires_in':3600,
                           'expires_on':str(int(time.time())+3600),
                           'resource':claims['aud'],'token_type':'Bearer'}).encode()
class Transport(HttpTransport):
    def open(self): pass
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
    def send(self, request, **kwargs):
        assert request.url.startswith('http://169.254.169.254/metadata/identity/oauth2/token?')
        assert 'client_id='+client in request.url
        assert request.headers['Metadata'].lower() == 'true'
        return Response(request)
with ManagedIdentityCredential(client_id=client, transport=Transport()) as credential:
    access = credential.get_token(claims['aud']+'/.default')
    assert type(access.token) is str and access.token == token
spec = __import__('importlib.util', fromlist=['spec_from_file_location'])
module_spec = spec.spec_from_file_location('offline_probe', sys.argv[3])
module = spec.module_from_spec(module_spec)
module_spec.loader.exec_module(module)
module.verify_token(access.token, claims['oid'])
print('retained-pure-wheel-identity-jwt-contract-passed')
'''
    child = subprocess.run([sys.executable, "-I", "-c", code, str(wheels),
        str(root / ".venv/Lib/site-packages"), str(root / "scripts/deployment/finops_private_probe.py")],
        capture_output=True, text=True, timeout=30, check=False)
    # Inputs and transport are entirely synthetic; don't export dependency logs.
    assert child.returncode == 0, "offline retained-wheel contract failed"
    assert child.stdout.strip() == "retained-pure-wheel-identity-jwt-contract-passed"