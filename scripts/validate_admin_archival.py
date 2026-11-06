"""Source-only pytest runner: block external sockets, DNS and Azure credentials.

TestClient needs numeric loopback / socketpair; no PostgreSQL or cloud tests
are enabled here. Do not use this runner for deployment controllers.
"""
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/control-plane/src"))
sys.path.insert(0, str(ROOT / "services/usage-ingestion"))
os.environ.pop("AIFLUX_ARCHIVAL_TEST_POSTGRES_URL", None)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def allowed(sock, address):
    return sock.family == getattr(socket, "AF_UNIX", object()) or (
        isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}
    )


def connect(sock, address):
    if not allowed(sock, address):
        raise RuntimeError("External network forbidden by source-only validation")
    return _connect(sock, address)


def connect_ex(sock, address):
    if not allowed(sock, address):
        raise RuntimeError("External network forbidden by source-only validation")
    return _connect_ex(sock, address)


def getaddrinfo(host, *args, **kwargs):
    if host not in {None, "127.0.0.1", "::1"}:
        raise RuntimeError("DNS forbidden by source-only validation")
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = getaddrinfo

from azure.identity import DefaultAzureCredential


def deny_credentials(*args, **kwargs):
    raise RuntimeError("Azure credential acquisition forbidden by source-only validation")


DefaultAzureCredential.get_token = deny_credentials

if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main(sys.argv[1:] or [
        "-q", "tests/unit/test_admin_archival.py", "tests/unit/test_admin_archival_postgres.py",
    ]))