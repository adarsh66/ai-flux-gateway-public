import hashlib
from contextlib import contextmanager

import jwt
import pytest
from aiflux.app import create_app
from aiflux.auth import LOCAL_ISSUER, PBKDF2_ITERATIONS
from aiflux.bootstrap import configure_bootstrap, main
from aiflux.config import Settings
from aiflux.db import get_db
from aiflux.models import Base, LocalUser, Member, Organization
from aiflux.turnstile_exchange import ensure_local_users_seeded
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

TEST_SIGNING_SECRET = "synthetic-test-signing-9G7b2K4v5H8n1T6s"


def production_settings(**overrides):
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql://api@private.postgres.database.azure.com/turnstile?sslmode=require",
        "entra_audience": "api://test",
        "home_tenant_id": "11111111-1111-4111-8111-111111111111",
        "local_auth_enabled": True,
    }
    return Settings(**(values | overrides))


def test_production_rejects_builtin_signing_secret():
    errors = production_settings().identity_errors()
    assert errors == ["production local authentication requires a resolved, strong JWT signing secret"]


@pytest.mark.parametrize("value", [
    "", "0123456789abcdef", "x" * 64,
    "@Microsoft.KeyVault(SecretUri=https://vault/secrets/jwt)",
])
def test_production_rejects_weak_or_unresolved_signing_secret(value):
    assert any("JWT signing" in error for error in production_settings(local_jwt_secret=value).identity_errors())


@pytest.mark.parametrize("passwords", [
    {},
    {"bootstrap_admin_password": "", "bootstrap_customer_password": ""},
    {"bootstrap_admin_password": "weak", "bootstrap_customer_password": "weak"},
    {
        "bootstrap_admin_password": "@Microsoft.KeyVault(SecretUri=https://vault/secrets/admin)",
        "bootstrap_customer_password": "@Microsoft.KeyVault(SecretUri=https://vault/secrets/customer)",
    },
])
def test_production_requires_only_strong_signing_not_bootstrap_passwords(passwords):
    settings = production_settings(
        local_jwt_secret=TEST_SIGNING_SECRET, **passwords,
    )
    assert settings.identity_errors() == []
    assert settings.local_jwt_secret not in repr(settings)


class UntouchableDatabase:
    def __getattr__(self, name):
        pytest.fail(f"Production seeding must not access the database: {name}")


def test_production_seeding_never_touches_database(monkeypatch):
    def forbidden_runtime_ddl(*args, **kwargs):
        pytest.fail("Production must use the separately migrated schema")

    monkeypatch.setattr(Base.metadata, "create_all", forbidden_runtime_ddl)
    settings = production_settings(local_jwt_secret=TEST_SIGNING_SECRET)
    ensure_local_users_seeded(UntouchableDatabase(), settings)
    ensure_local_users_seeded(UntouchableDatabase(), settings)


@contextmanager
def forbid_database_writes(engine):
    def check_statement(connection, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith("SELECT"), statement

    def forbid_commit(connection):
        pytest.fail("Production initialization/login must not commit the caller transaction")

    event.listen(engine, "before_cursor_execute", check_statement)
    event.listen(engine, "commit", forbid_commit)
    try:
        yield
    finally:
        event.remove(engine, "before_cursor_execute", check_statement)
        event.remove(engine, "commit", forbid_commit)


def test_production_seeding_preserves_caller_transaction(env):
    settings = production_settings(local_jwt_secret=TEST_SIGNING_SECRET)
    with Session(env.db_engine) as session:
        org = session.get(Organization, env.orgs["admin"])
        deleted_member = session.scalar(select(Member).where(Member.organization_id == org.id))
        org.name = "Uncommitted caller edit"
        pending = Organization(name="Caller pending", tenant_id="55555555-5555-4555-8555-555555555555")
        session.add(pending)
        session.delete(deleted_member)
        transaction = session.get_transaction()
        new, dirty, deleted = set(session.new), set(session.dirty), set(session.deleted)
        with forbid_database_writes(env.db_engine):
            ensure_local_users_seeded(session, settings)
            ensure_local_users_seeded(session, settings)
            assert session.get_transaction() is transaction
            assert transaction.is_active
            assert set(session.new) == new
            assert set(session.dirty) == dirty
            assert set(session.deleted) == deleted
            assert pending.id is None
            assert org.name == "Uncommitted caller edit"
        session.rollback()
    with Session(env.db_engine) as session:
        assert session.get(Organization, env.orgs["admin"]).name == "IDS"
        assert session.scalar(select(func.count()).select_from(Organization)) == 2
        assert session.scalar(select(func.count()).select_from(Member)) == 2
        assert session.scalar(select(func.count()).select_from(LocalUser)) == 0


def test_production_seed_refuses_defaults_before_touching_database():
    with pytest.raises(ValueError, match="configuration is incomplete"):
        ensure_local_users_seeded(UntouchableDatabase(), production_settings())


@pytest.mark.parametrize("overrides", [
    {"database_url": ""},
    {"database_url": "sqlite://"},
    {"database_url": "postgresql://api:password@private/turnstile?sslmode=require"},
    {"database_url": "postgresql://api@private/turnstile?sslmode=disable"},
    {"entra_audience": ""},
    {"home_tenant_id": ""},
    {"home_tenant_id": "not-a-uuid"},
    {"entra_client_id": "not-a-uuid"},
])
def test_production_still_requires_valid_identity_before_touching_database(overrides):
    settings = production_settings(local_jwt_secret=TEST_SIGNING_SECRET, **overrides)
    assert settings.identity_errors()
    with pytest.raises(ValueError, match="configuration is incomplete"):
        ensure_local_users_seeded(UntouchableDatabase(), settings)


@pytest.mark.parametrize("bootstrap_object_id", ["", "33333333-3333-4333-8333-333333333333"])
def test_production_local_bootstrap_never_opens_session(env, monkeypatch, bootstrap_object_id):
    settings = production_settings(
        local_jwt_secret=TEST_SIGNING_SECRET, bootstrap_object_id=bootstrap_object_id,
    )

    def forbidden_session(*args, **kwargs):
        pytest.fail("Production local bootstrap must not open a database session")

    monkeypatch.setattr("aiflux.bootstrap.Session", forbidden_session)
    monkeypatch.setattr("aiflux.bootstrap.get_settings", lambda: settings)
    monkeypatch.setattr("aiflux.bootstrap.engine_for", lambda url: env.db_engine)
    with forbid_database_writes(env.db_engine):
        configure_bootstrap(settings, env.db_engine)
        main()


def test_production_local_bootstrap_rejects_invalid_identity(monkeypatch):
    settings = production_settings(local_jwt_secret=TEST_SIGNING_SECRET, home_tenant_id="")
    monkeypatch.setattr("aiflux.bootstrap.get_settings", lambda: settings)
    with pytest.raises(SystemExit):
        configure_bootstrap(settings, UntouchableDatabase())
    with pytest.raises(SystemExit):
        main()


def test_production_entra_bootstrap_preserves_membership_behavior(env):
    settings = production_settings(
        local_auth_enabled=False,
        bootstrap_object_id="66666666-6666-4666-8666-666666666666",
    )
    configure_bootstrap(settings, env.db_engine)
    configure_bootstrap(settings, env.db_engine)
    with Session(env.db_engine) as session:
        members = session.scalars(select(Member).where(Member.object_id == settings.bootstrap_object_id)).all()
        assert len(members) == 1
        assert members[0].role == "ids_admin" and members[0].enabled
        assert session.scalar(select(func.count()).select_from(Organization)) == 2
        assert session.scalar(select(func.count()).select_from(LocalUser)) == 0
    with pytest.raises(SystemExit):
        configure_bootstrap(production_settings(local_auth_enabled=False), UntouchableDatabase())


@pytest.fixture
def production_login(env):
    settings = production_settings(local_jwt_secret=TEST_SIGNING_SECRET)
    password = "synthetic-test-login-password"
    salt = "fixed-test-salt"
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    with Session(env.db_engine) as session:
        for name in ("admin", "customer"):
            member = session.scalar(select(Member).where(Member.organization_id == env.orgs[name]))
            session.add(LocalUser(
                email=f"{name}@example.test",
                password_hash=f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}",
                display_name=f"Seeded {name}", organization_id=member.organization_id,
                object_id=member.object_id, role=member.role, enabled=True,
            ))
        session.commit()
    app = create_app(settings)

    def database():
        with Session(env.db_engine) as session:
            yield session

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, settings, password


@pytest.mark.parametrize("name, role", [("admin", "ids_admin"), ("customer", "customer")])
def test_production_login_uses_seeded_users_and_verifies_token_without_writes(env, production_login, name, role):
    client, settings, password = production_login
    with forbid_database_writes(env.db_engine):
        response = client.post("/api/auth/login", json={"email": f"{name}@example.test", "password": password})
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        assert jwt.get_unverified_header(token)["alg"] == "HS256"
        claims = jwt.decode(
            token, TEST_SIGNING_SECRET, algorithms=["HS256"],
            audience=settings.entra_audience, issuer=LOCAL_ISSUER,
        )
        assert claims["exp"] - claims["iat"] == 12 * 60 * 60
        assert claims["role"] == role
        assert claims["scp"] == settings.required_scope
        me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json()["role"] == role
        assert me.json()["organization_id"] == env.orgs[name]
        parts = token.split(".")
        parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
        assert client.get("/api/me", headers={"Authorization": f"Bearer {'.'.join(parts)}"}).status_code == 401


@pytest.mark.parametrize("case, expected", [
    ("missing", 401), ("password", 401), ("disabled_user", 401), ("disabled_org", 403),
])
def test_production_login_fails_closed_without_writes(env, production_login, case, expected):
    client, settings, password = production_login
    if case in ("disabled_user", "disabled_org"):
        with Session(env.db_engine) as session:
            if case == "disabled_user":
                row = session.scalar(select(LocalUser).where(LocalUser.email == "admin@example.test"))
            else:
                row = session.get(Organization, env.orgs["admin"])
            row.enabled = False
            session.commit()
    with forbid_database_writes(env.db_engine):
        response = client.post("/api/auth/login", json={
            "email": "missing@example.test" if case == "missing" else "admin@example.test",
            "password": "wrong-password" if case == "password" else password,
        })
        assert response.status_code == expected, response.text


def test_production_local_auth_never_fabricates_identity_configuration():
    settings = production_settings(home_tenant_id="", entra_audience="")
    assert settings.home_tenant_id == ""
    assert settings.entra_audience == ""
    assert "home_tenant_id is required" in settings.identity_errors()
    assert "entra_audience is required" in settings.identity_errors()