"""Build-only Linux native contract. Synthetic SDK transport; no network or DB."""
import base64
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import importlib.util
import json
import logging
import os
from pathlib import Path
import socket
import ssl
import sys
import time


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    assert sys.platform == "linux"
    logging.disable(logging.CRITICAL)
    def forbidden(*args, **kwargs):
        raise AssertionError("offline_network_forbidden")
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.getaddrinfo = forbidden
    for key in ("IDENTITY_ENDPOINT", "IDENTITY_HEADER", "MSI_ENDPOINT", "MSI_SECRET",
                "IMDS_ENDPOINT", "AZURE_POD_IDENTITY_AUTHORITY_HOST"):
        os.environ.pop(key, None)
    import azure.identity
    from azure.core.pipeline.transport import HttpResponse, HttpTransport
    import jwt
    import msal
    import psycopg
    from psycopg.types.bool import BoolLoader
    from psycopg.types.datetime import TimestamptzLoader
    from psycopg.types.numeric import IntLoader
    from psycopg.types.numeric import NumericLoader
    from psycopg.types.string import TextLoader
    import sqlalchemy
    assert (azure.identity.__version__, jwt.__version__, msal.__version__, psycopg.__version__, sqlalchemy.__version__) == (
        "1.23.0", "2.15.1", "1.39.0", "3.2.9", "2.0.41")
    assert psycopg.pq.__impl__ == "binary" and psycopg.pq.version() >= 120000
    ca = ssl.get_default_verify_paths().cafile
    assert ca and os.access(ca, os.R_OK) and Path(ca).stat().st_size > 0
    assert ssl.create_default_context(cafile=ca).get_ca_certs()
    probe, supervisor = load("finops_private_probe"), load("entrypoint")
    client, oid = supervisor.IDENTITIES["ingestion"]
    claims = {"tid": probe.TENANT, "oid": oid,
              "aud": "https://ossrdbms-aad.database.windows.net", "exp": int(time.time()) + 3600}
    encode = lambda v: base64.urlsafe_b64encode(json.dumps(v).encode()).decode().rstrip("=")
    token = encode({"alg": "RS256", "typ": "JWT"}) + "." + encode(claims) + ".c3ludGhldGlj"
    class Response(HttpResponse):
        def __init__(self, request):
            super().__init__(request, None)
            self.status_code = 200
            self.headers = {"Content-Type": "application/json"}
            self.content_type = "application/json"
        def body(self):
            return json.dumps({"access_token": token, "expires_in": 3600,
                "expires_on": str(claims["exp"]), "resource": claims["aud"], "token_type": "Bearer"}).encode()
    class Transport(HttpTransport):
        def open(self): pass
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
        def send(self, request, **kwargs):
            assert request.url.startswith("http://169.254.169.254/metadata/identity/oauth2/token?")
            assert "client_id=" + client in request.url and request.headers["Metadata"].lower() == "true"
            return Response(request)
    with azure.identity.ManagedIdentityCredential(client_id=client, transport=Transport()) as credential:
        access = credential.get_token(claims["aud"] + "/.default")
        assert access.token == token
        probe.verify_token(access.token, oid)
    role = "poc-ids-token-ex-ingestion-identity"
    options = probe.connection_options("postgresql://" + role + "@" + probe.HOST + "/turnstile?sslmode=verify-full", role)
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    parsed = conninfo_to_dict(make_conninfo(**options, hostaddr="10.240.3.12"))
    assert parsed["sslmode"] == "verify-full" and parsed["sslrootcert"] == ca
    assert "default_transaction_read_only=on" in parsed["options"]
    now = datetime.now(UTC)
    numeric = NumericLoader(1700).load
    integer = IntLoader(20).load
    boolean = BoolLoader(16).load
    name = TextLoader(19).load
    text = TextLoader(25).load
    timestamp = TimestamptzLoader(1184).load
    stamp = lambda value: timestamp(value.isoformat().encode())
    # Real binary driver's native numeric loader, not a coerced fake integer.
    assert type(numeric(b"11")) is Decimal
    class Database:
        def __init__(self, selected_role=role, empty=False):
            self.rolled_back = False
            self.statements = []
            # Match startup GUC spelling, not an invented pretty-printed SHOW.
            path = next(x.removeprefix("search_path=") for x in parsed["options"].split()
                        if x.startswith("search_path="))
            self.answers = [(name(b"turnstile"), name(selected_role.encode()), name(selected_role.encode()),
                name(b"public"), text(path.encode()), text(b"on")),
                (boolean(b"f"),) * 4, (boolean(b"f"),) * 3,
                     *((boolean(b"t"),
                         boolean(b"t" if table in probe.WRITABLE else b"f"),
                         boolean(b"t" if table in {"usage_records", "ingestion_state"} else b"f"),
                         boolean(b"f")) for table in probe.TABLES),
                (integer(b"2"), stamp(now - timedelta(days=2)), stamp(now - timedelta(days=1)), stamp(now)),
                (integer(b"2"), numeric(b"11"), numeric(b"107"), integer(b"1"), integer(b"2"), numeric(b"18")),
                (stamp(now - timedelta(minutes=10)), stamp(now)),
                (integer(b"1"), stamp(now), stamp(now), integer(b"1")),
                (integer(b"0"),), (integer(b"0"),) * 3]
            if empty:
                self.answers[-6] = (integer(b"0"), None, None, None)
                self.answers[-5] = (integer(b"0"),) * 6
                self.answers[-4] = None
                self.answers[-3] = (integer(b"0"), None, None, integer(b"0"))
        def cursor(self): return self
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, query, parameters=None):
            assert query.startswith(("SELECT ", "SET TRANSACTION "))
            assert parameters is None or type(parameters) is tuple
            if parameters:
                assert all(isinstance(value, (str, datetime)) for value in parameters)
            self.statements.append(query)
        def fetchone(self): return self.answers.pop(0)
        def rollback(self): self.rolled_back = True
    for selected_role in (role, "poc-ids-token-ex-api-identity"):
        for empty in (False, True):
            db = Database(selected_role, empty)
            report = probe.inspect_database(db, selected_role, now=now)
            assert db.rolled_back and not db.answers and len(db.statements) == 15
            assert type(report["window"]["known_input_tokens"]) is int
            assert report["database_writes"] == 0 and report["approved_activation_cutoff"] is None
            first = supervisor.sanitize(json.dumps(report, default=str), 0)
            assert first["status"] == "verified_read_only_snapshot"
            assert supervisor.sanitize(json.dumps(first), 0) == first
    for index, value, reason in (
        (0, "wrong", "database_session_database"),
        (1, "wrong", "database_session_session_user"),
        (2, "wrong", "database_session_current_user"),
        (3, None, "database_session_schema"),
        (4, "pg_catalog,public", "database_session_search_path"),
        (5, True, "database_session_read_only"),
    ):
        db = Database()
        row = list(db.answers[0])
        row[index] = value
        db.answers[0] = tuple(row)
        progress = {}
        try:
            probe.inspect_database(db, role, now=now, progress=progress)
        except probe.ProbeBlocked as exc:
            failure = probe.failure_report(exc, progress["stage"])
            assert failure["reason"] == reason and failure["stage"] == "database_session"
            assert db.rolled_back and len(db.statements) == 2
            assert supervisor.sanitize(json.dumps(supervisor.sanitize(json.dumps(failure), 2)), 0) == failure
        else:
            raise AssertionError("unsafe_session_accepted")
    for stage in probe.STAGES:
        failure = probe.failure_report(probe.ProbeBlocked("aggregate_integer_required"), stage)
        assert supervisor.sanitize(json.dumps(failure), 2) == failure
        assert supervisor.sanitize(json.dumps(failure), 0) == failure
    print("FINOPS_LINUX_NATIVE_CONTRACT_PASSED", flush=True)


if __name__ == "__main__":
    main()