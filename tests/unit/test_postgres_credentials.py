from types import SimpleNamespace

import pytest

from aiflux import db


def test_passwordless_postgres_uses_default_credential_and_refreshes(monkeypatch):
    calls = []

    class Credential:
        def get_token(self, scope, **kwargs):
            calls.append(scope)
            return SimpleNamespace(token=f"token-{len(calls)}")

    monkeypatch.setattr(db, "DefaultAzureCredential", Credential)
    db.engine_for.cache_clear()
    engine = db.engine_for(
        "postgresql://api-identity@private.postgres.database.azure.com/turnstile?sslmode=require"
    )
    try:
        for expected in ("token-1", "token-2"):
            params = {}
            for callback in engine.dialect.dispatch.do_connect:
                callback(engine.dialect, None, [], params)
            assert params.get("password") == expected
        assert calls == ["https://ossrdbms-aad.database.windows.net/.default"] * 2
    finally:
        engine.dispose()
        db.engine_for.cache_clear()


@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg"])
def test_password_postgres_does_not_construct_azure_credential(monkeypatch, scheme):
    def forbidden():
        pytest.fail("Password-based development connections must not request Azure credentials")

    monkeypatch.setattr(db, "DefaultAzureCredential", forbidden)
    db.engine_for.cache_clear()
    engine = db.engine_for(f"{scheme}://developer:local-password@localhost/turnstile")
    try:
        assert list(engine.dialect.dispatch.do_connect) == []
    finally:
        engine.dispose()
        db.engine_for.cache_clear()