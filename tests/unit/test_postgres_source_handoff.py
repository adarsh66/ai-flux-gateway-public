"""Portable bootstrap/seeding checks using only the checked-out source tree.

The synthetic release is for offline tests, not deployment approval or evidence
that the historical release can be reconstructed byte-for-byte.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from aiflux import models
from aiflux.auth import verify_password

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("handoff_seed", ROOT / "infra/sql/seed-postgres-users.py")
seed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed)
TENANT = "11111111-1111-4111-8111-111111111111"
ADMIN = "admin@example.test"
CUSTOMER = "customer@example.test"
PASSWORD = "synthetic-test-only-8G!483725"


@pytest.fixture
def source_release(tmp_path):
    context = tmp_path / "context"
    target = context / "services/control-plane"
    source = ROOT / "services/control-plane"
    target.mkdir(parents=True)
    for folder in ("src", "migrations"):
        shutil.copytree(source / folder, target / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(source / "alembic.ini", target / "alembic.ini")
    entries = [{"path": path.relative_to(context).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for path in sorted(context.rglob("*")) if path.is_file()]
    (tmp_path / "source-manifest.json").write_text(json.dumps({
        "tag": seed.load_bootstrap().RELEASE, "entries": entries,
    }), encoding="utf-8")
    return tmp_path


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def hashes(source_release):
    make_hash, check_hash = seed.password_functions(source_release)
    result = {ADMIN: make_hash(PASSWORD), CUSTOMER: make_hash(PASSWORD + "-customer")}
    assert check_hash(PASSWORD, result[ADMIN])
    assert verify_password(PASSWORD, result[ADMIN])
    assert not verify_password("incorrect", result[ADMIN])
    assert make_hash(PASSWORD) != result[ADMIN]
    return result


def seed_two(connection, hashes):
    return seed.seed_users(connection, models, TENANT, ADMIN, CUSTOMER, "Test Customer", hashes)


def test_source_only_release_validates_migration_graph_and_repeat(source_release):
    env = os.environ.copy()
    env.pop("AIFLUX_DATABASE_URL", None)
    result = subprocess.run([
        sys.executable, str(ROOT / "infra/sql/bootstrap-postgres.py"),
        "validate", "--release-dir", str(source_release),
    ], cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["head"] == "0003"
    assert report["sqlite_upgrade_and_repeat"] == "passed"
    assert report["postgresql_ddl_compile"] == "passed"
    assert report["seeding"] == "not_requested"
    assert "local_users" in report["tables"]


def test_source_only_hashes_seed_exact_memberships(database, hashes):
    with database.begin() as connection:
        result = seed_two(connection, hashes)
    assert result == [{"email": ADMIN, "role": "ids_admin"},
                      {"email": CUSTOMER, "role": "customer"}]
    with Session(database) as session:
        users = session.scalars(select(models.LocalUser)).all()
        assert len(users) == 2
        for user in users:
            member = session.scalar(select(models.Member).where(models.Member.object_id == user.object_id))
            assert member.organization_id == user.organization_id
            assert member.role == user.role and member.enabled and user.enabled
            assert user.password_hash == hashes[user.email]
        assert session.scalar(select(func.count()).select_from(models.TeamSubscription)) == 0
        assert session.scalar(select(func.count()).select_from(models.CreditBudget)) == 0
    assert PASSWORD not in json.dumps(result)


@pytest.mark.parametrize("uppercase", [False, True])
def test_source_only_repeat_never_resets_passwords(database, hashes, uppercase):
    with database.begin() as connection:
        seed_two(connection, hashes)
        if uppercase:
            connection.execute(models.LocalUser.__table__.update().where(
                models.LocalUser.email == ADMIN).values(email=ADMIN.upper()))
    with pytest.raises(RuntimeError, match="already exists"):
        with database.begin() as connection:
            seed_two(connection, {ADMIN: "replacement", CUSTOMER: "replacement"})
    with Session(database) as session:
        assert session.scalar(select(models.LocalUser.password_hash).where(
            func.lower(models.LocalUser.email) == ADMIN)) == hashes[ADMIN]


def test_source_only_failure_rolls_back_all_rows(database, hashes):
    with pytest.raises(KeyError):
        with database.begin() as connection:
            seed_two(connection, {ADMIN: hashes[ADMIN]})
    with Session(database) as session:
        for model in (models.Organization, models.Member, models.LocalUser):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("role,enabled", [("customer", True), ("ids_admin", False)])
def test_source_only_conflicting_membership_never_promoted(database, hashes, role, enabled):
    with Session(database) as session:
        org = models.Organization(name="Singtel IDS", tenant_id=TENANT, enabled=True)
        session.add(org)
        session.flush()
        session.add(models.Member(organization_id=org.id, object_id=seed.ADMIN_OBJECT,
                                  role=role, enabled=enabled))
        session.commit()
    with pytest.raises(RuntimeError, match="membership conflicts"):
        with database.begin() as connection:
            seed_two(connection, hashes)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(models.LocalUser)) == 0
        member = session.scalar(select(models.Member))
        assert member.role == role and member.enabled == enabled