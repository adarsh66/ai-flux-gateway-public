from scripts.deployment import install_glm_secret
from scripts.deployment import glm_apim_secret as secret_store
import pytest


def test_secret_installer_rejects_arguments_without_prompt(monkeypatch, capsys):
    monkeypatch.setattr(install_glm_secret.sys, "argv", ["installer", "not-a-supported-argument"])
    monkeypatch.setattr(install_glm_secret.getpass, "getpass", lambda *_: (_ for _ in ()).throw(AssertionError("No prompt allowed")))
    assert install_glm_secret.main() == 1
    assert "not-a-supported-argument" not in capsys.readouterr().out


def test_secret_installer_refuses_captured_stdin(monkeypatch, capsys):
    monkeypatch.setattr(install_glm_secret.sys, "argv", ["installer"])
    monkeypatch.setattr(install_glm_secret.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(install_glm_secret.getpass, "getpass", lambda *_: (_ for _ in ()).throw(AssertionError("No prompt allowed")))
    assert install_glm_secret.main() == 1
    assert "interactive terminal" in capsys.readouterr().out


@pytest.fixture
def masked_console(monkeypatch):
    monkeypatch.setattr(install_glm_secret.sys, "argv", ["installer"])
    monkeypatch.setattr(install_glm_secret.sys.stdin, "isatty", lambda: True)


@pytest.mark.parametrize("value", ["", "contains whitespace", "x" * 4097])
def test_invalid_entry_never_written(masked_console, monkeypatch, capsys, value):
    class Store:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def inspect(self): return None, None
        def install(self, *_args, **_kwargs): pytest.fail("Invalid input must not be written")
    monkeypatch.setattr(secret_store, "ArmSecretStore", Store)
    monkeypatch.setattr(install_glm_secret.getpass, "getpass", lambda *_: value)
    assert install_glm_secret.main() == 1
    assert "invalid credential format" in capsys.readouterr().out


def test_masked_installer_writes_only_in_memory_and_checks_metadata(masked_console, monkeypatch, capsys):
    evidence = secret_store.metadata({"id": secret_store.RESOURCE_ID, "properties": {
        "displayName": secret_store.NAME, "secret": True}})
    calls = []
    class Store:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def inspect(self): return (evidence, '"etag"') if calls else (None, None)
        def install(self, value, **kwargs): calls.append((value, kwargs))
    monkeypatch.setattr(secret_store, "ArmSecretStore", Store)
    monkeypatch.setattr(install_glm_secret.getpass, "getpass", lambda *_: "synthetic-test-only")
    assert install_glm_secret.main() == 0
    assert calls == [("synthetic-test-only", {"exists": False, "etag": None})]
    assert "synthetic-test-only" not in capsys.readouterr().out


def test_installer_suppresses_sensitive_exception(masked_console, monkeypatch, capsys):
    class Store:
        def __enter__(self): raise RuntimeError("synthetic-sensitive-error")
        def __exit__(self, *_): pass
    monkeypatch.setattr(secret_store, "ArmSecretStore", Store)
    assert install_glm_secret.main() == 1
    captured = capsys.readouterr()
    assert "synthetic-sensitive-error" not in captured.out + captured.err


def test_metadata_projection_discards_values_and_rejects_vault():
    evidence = secret_store.metadata({"id": secret_store.RESOURCE_ID, "properties": {
        "displayName": secret_store.NAME, "secret": True, "value": "synthetic-test-only"}})
    assert secret_store.internal_ready(evidence)
    assert "value" not in evidence and "synthetic-test-only" not in str(evidence)
    for key_vault in ({}, {"secretIdentifier": "https://example.invalid"}):
        assert not secret_store.internal_ready(secret_store.metadata({"id": secret_store.RESOURCE_ID,
            "properties": {"displayName": secret_store.NAME, "secret": True, "keyVault": key_vault}}))


def test_transport_sends_secret_only_as_json_body(monkeypatch):
    from types import SimpleNamespace
    calls = []
    class Response:
        status_code = 200
        def close(self): pass
        def json(self): pytest.fail("Secret PUT response must never be parsed")
    class Session:
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return Response()
    store = secret_store.ArmSecretStore()
    store.session = Session()
    store.credential = SimpleNamespace(get_token=lambda *_: SimpleNamespace(token="synthetic-arm-token"))
    store.install("synthetic-test-only", exists=False, etag=None)
    method, url, kwargs = calls[0]
    assert method == "PUT" and "listSecrets" not in url
    assert "synthetic-test-only" not in url + str(kwargs["headers"])
    assert kwargs["json"]["properties"] == {"displayName": secret_store.NAME, "secret": True,
        "value": "synthetic-test-only", "tags": ["aiflux", "external-glm", "out-of-band-secret"]}
    assert kwargs["allow_redirects"] is False and kwargs["headers"]["If-None-Match"] == "*"
    with pytest.raises(secret_store.SecretOperationBlocked):
        store.install("synthetic-test-only", exists=True, etag=None)


def test_metadata_get_never_invokes_secret_action():
    calls = []
    class Response:
        status_code = 404
        def close(self): pass
        def json(self): pytest.fail("404 must not parse body")
    store = secret_store.ArmSecretStore()
    store._request = lambda method: (calls.append(method) or Response())
    assert store.inspect() == (None, None)
    assert calls == ["GET"]