import json
import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from aiflux.app import create_app
from aiflux.config import Settings
from aiflux.db import engine_for
from aiflux.models import Organization, PortalUser
from aiflux.portal_auth import (
    PASSWORD_ITERATIONS,
    hash_password,
    parse_seed_users,
    seed_portal_users,
    verify_password,
)
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

HOME = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def portal(tmp_path):
    password = " " + secrets.token_urlsafe(18) + "aA1! "
    users = [
        {"username": username, "password": password, "role": role}
        for username, role in (
            ("customer1", "customer"), ("customer2", "customer"),
            ("customer3", "customer"), ("admin", "ids_admin"),
        )
    ]
    settings = Settings(
        _env_file=None, environment="testing",
        database_url=f"sqlite:///{tmp_path / 'portal.db'}", home_tenant_id=HOME,
        portal_login_enabled=True, portal_login_secret=secrets.token_urlsafe(48),
        portal_seed_users=json.dumps(users),
    )
    engine = engine_for(settings.database_url)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    app = create_app(settings)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, engine=engine, settings=settings, password=password, users=users)
    engine.dispose()


def login(portal, username="customer1", password=None):
    return portal.client.post("/api/auth/login", json={
        "username": username, "password": portal.password if password is None else password,
    })


def headers(portal, username="customer1"):
    result = login(portal, username)
    assert result.status_code == 200, result.text
    return {"Authorization": "Bearer " + result.json()["token"]}


def test_four_accounts_roles_and_real_isolated_orgs(portal):
    org_ids = []
    for username in ("customer1", "customer2", "customer3", "admin"):
        auth = headers(portal, username)
        me = portal.client.get("/api/me", headers=auth)
        assert me.status_code == 200
        identity = me.json()
        assert identity["role"] == ("ids_admin" if username == "admin" else "customer")
        org_ids.append(identity["organization_id"])
        expected = 200 if username == "admin" else 403
        assert portal.client.get("/api/admin/organizations", headers=auth).status_code == expected
        with Session(portal.engine) as db:
            org = db.get(Organization, identity["organization_id"])
            assert org is not None and org.enabled
            if username == "admin":
                assert org.tenant_id == HOME
    assert len(set(org_ids)) == 4


def test_password_is_exact_not_stripped_and_invalid_login(portal):
    assert login(portal).status_code == 200
    assert login(portal, password=portal.password.strip()).status_code == 401
    assert login(portal, password="incorrect").status_code == 401
    assert login(portal, username="missing").status_code == 401


@pytest.mark.parametrize("target", ["user", "organization", "deleted", "role", "tenant"])
def test_existing_tokens_revalidate_account_and_organization(portal, target):
    auth = headers(portal)
    with Session(portal.engine) as db:
        user = db.scalar(select(PortalUser).where(PortalUser.username == "customer1"))
        if target == "user":
            user.enabled = False
        elif target == "organization":
            db.get(Organization, user.organization_id).enabled = False
        elif target == "deleted":
            db.delete(user)
        elif target == "role":
            user.role = "ids_admin"
        else:
            user.tenant_id = HOME
        db.commit()
    assert portal.client.get("/api/me", headers=auth).status_code == 401
    assert login(portal).status_code == 401


@pytest.mark.parametrize("change", [
    {"exp": None}, {"iss": None}, {"sub": None}, {"role": None},
    {"exp": 1}, {"exp": "invalid"}, {"exp": True}, {"exp": float("nan")}, {"exp": float("inf")},
    {"iss": "wrong"}, {"sub": "bad"}, {"sub": str(uuid4())},
    {"sub": []}, {"role": "superadmin"}, {"role": []},
])
def test_malformed_missing_and_expired_claims(portal, change):
    token = login(portal).json()["token"]
    claims = jwt.decode(token, portal.settings.portal_login_secret, algorithms=["HS256"])
    for name, value in change.items():
        if value is None:
            claims.pop(name)
        else:
            claims[name] = value
    token = jwt.encode(claims, portal.settings.portal_login_secret, algorithm="HS256")
    assert portal.client.get("/api/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_sql_mode_never_uses_microsoft_identity_claims(portal):
    claims = {
        "tid": HOME, "oid": str(uuid4()), "iss": "https://login.microsoftonline.com/" + HOME + "/v2.0",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(claims, portal.settings.portal_login_secret, algorithm="HS256")
    for value in (token, "not.a.token"):
        assert portal.client.get("/api/me", headers={"Authorization": "Bearer " + value}).status_code == 401


def test_seed_idempotence_preserves_password_role_and_disabled_state(portal):
    with Session(portal.engine) as db:
        user = db.scalar(select(PortalUser).where(PortalUser.username == "customer1"))
        old_hash, org_id = user.password_hash, user.organization_id
        user.enabled = False
        user.role = "ids_admin"
        db.get(Organization, org_id).enabled = False
        db.commit()
    portal.users[0]["password"] = secrets.token_urlsafe(24) + "aA1!"
    portal.settings.portal_seed_users = json.dumps(portal.users)
    with Session(portal.engine) as db:
        seed_portal_users(db, portal.settings)
        user = db.scalar(select(PortalUser).where(PortalUser.username == "customer1"))
        assert user.password_hash == old_hash
        assert not user.enabled and user.role == "ids_admin"
        assert user.organization_id == org_id and not db.get(Organization, org_id).enabled
        assert len(db.scalars(select(PortalUser)).all()) == 4
        assert len(db.scalars(select(Organization)).all()) == 4


def test_organization_fk_is_enforced(portal):
    with Session(portal.engine) as db:
        user = db.scalar(select(PortalUser).limit(1))
        user.organization_id = str(uuid4())
        with pytest.raises(IntegrityError):
            db.commit()


def test_pbkdf2_salts_and_legacy_hashes():
    password = secrets.token_urlsafe(18) + "aA1! "
    first, second = hash_password(password), hash_password(password)
    assert first != second
    assert first.startswith(f"pbkdf2_sha256${PASSWORD_ITERATIONS}$")
    assert verify_password(password, first)
    assert not verify_password(password.strip(), first)
    for value in ("0" * 64, "invalid", first.replace("600000", "1"), "pbkdf2_sha256$x$$"):
        assert not verify_password(password, value)


@pytest.mark.parametrize("value", [
    "not json", "{}", '[{"username":"user","password":"short","role":"customer"}]',
    '[{"username":"user","password":"aA1!abcdefghijk","role":"owner"}]',
    '[{"username":"user","password":"aA1!abcdefghijk","role":"customer","enabled":true}]',
    '[{"username":"user","password":"aA1!abcdefghijk","role":"customer"},'
    '{"username":"USER","password":"aA1!abcdefghijk","role":"customer"}]',
])
def test_seed_secrets_validation_is_sanitized(value):
    with pytest.raises(ValueError) as exc:
        parse_seed_users(value)
    assert value not in str(exc.value)
    settings = Settings(_env_file=None, portal_login_enabled=True,
                        portal_login_secret=secrets.token_urlsafe(48), portal_seed_users=value)
    assert settings.portal_auth_errors()


@pytest.mark.parametrize("key", ["", "dev-sql-portal-secret", "x" * 64, "changeme" * 10])
def test_signing_key_validation(key):
    settings = Settings(_env_file=None, portal_login_enabled=True, portal_login_secret=key)
    assert settings.portal_auth_errors()
    with pytest.raises(ValueError):
        create_app(settings)
    assert key == "" or key not in repr(settings)


def test_production_sql_config_does_not_require_entra_audience():
    settings = Settings(
        _env_file=None, environment="production", portal_login_enabled=True,
        portal_login_secret=secrets.token_urlsafe(48), home_tenant_id=HOME,
        database_url="mssql+pyodbc://server/database?Encrypt=yes&TrustServerCertificate=no",
    )
    assert settings.identity_errors() == []
    settings.home_tenant_id = ""
    assert settings.identity_errors()
    settings.home_tenant_id = HOME
    settings.database_url = "sqlite:///:memory:"
    assert settings.identity_errors()


def test_portal_disabled_by_default_and_no_default_seeding(tmp_path):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path / 'disabled.db'}",
        home_tenant_id=HOME, entra_audience="api://test",
    )
    assert not settings.portal_login_enabled and not settings.portal_login_secret
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/auth/login", json={"username": "admin", "password": "invalid"}).status_code == 404
    with Session(engine_for(settings.database_url)) as db:
        assert db.scalars(select(PortalUser)).all() == []


def test_production_startup_has_no_runtime_ddl_or_default_seeding(tmp_path):
    settings = Settings(_env_file=None, environment="production", database_url=f"sqlite:///{tmp_path / 'prod.db'}")
    create_app(settings)
    assert inspect(engine_for(settings.database_url)).get_table_names() == []


def test_seed_requires_explicit_enable():
    settings = Settings(_env_file=None, portal_seed_users="[]")
    assert settings.portal_auth_errors()


def test_portal_migration_missing_table_and_legacy_orphans(tmp_path):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path("services/control-plane/migrations/versions/0003_portal_users.py")
    spec = importlib.util.spec_from_file_location("portal_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = engine_for(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        Organization.__table__.create(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()  # Live-metadata 0001 / already-created table is supported.
        assert inspect(connection).get_foreign_keys("portal_users")
        migration.downgrade()
        # Reconstruct the old portal table without the new ownership FK.
        connection.execute(text(
            "CREATE TABLE portal_users (id VARCHAR(36) PRIMARY KEY, username VARCHAR(80), "
            "password_hash VARCHAR(128), role VARCHAR(20), organization_id VARCHAR(36), "
            "organization_name VARCHAR(100), tenant_id VARCHAR(36), object_id VARCHAR(36), "
            "enabled BOOLEAN, created_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO portal_users VALUES (:id, 'legacy', 'oldhash', 'customer', 'portal-sql-poc', "
            "'old', :tenant, :object, 1, CURRENT_TIMESTAMP)"
        ), {"id": str(uuid4()), "tenant": HOME, "object": str(uuid4())})
        migration.upgrade()
        row = connection.execute(text(
            "SELECT u.enabled, o.enabled FROM portal_users u JOIN organizations o ON o.id=u.organization_id"
        )).one()
        assert not row[0] and not row[1]
        assert inspect(connection).get_foreign_keys("portal_users")