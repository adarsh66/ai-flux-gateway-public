import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from aiflux import models
from aiflux.auth import verify_password

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("seed_users", ROOT / "infra/sql/seed-postgres-users.py")
seed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed)
TENANT = "beb276ac-6e9f-498e-8e31-019ee666decd"
ADMIN = "admin@tokenx-ids.com"
CUSTOMER = "developer@caldova.com"
PASSWORD = "User-selected!Test-483725"


@pytest.fixture
def engine():
    value = create_engine("sqlite://")
    models.Base.metadata.create_all(value)
    yield value
    value.dispose()


@pytest.fixture
def hashes():
    directory = ROOT / ".deployment/image-build/local-20261023t074801z-939ccecd80d1"
    if not directory.exists():
        pytest.skip("Reviewed local release required for exact hashing compatibility")
    make_hash, check_hash = seed.password_functions(directory)
    result = {ADMIN: make_hash(PASSWORD), CUSTOMER: make_hash(PASSWORD + "Customer")}
    assert check_hash(PASSWORD, result[ADMIN])
    assert verify_password(PASSWORD, result[ADMIN])
    assert not verify_password("incorrect", result[ADMIN])
    assert result[ADMIN] != make_hash(PASSWORD)
    return result


def apply_seed(connection, hashes):
    return seed.seed_users(connection, models, TENANT, ADMIN, CUSTOMER, "Caldova", hashes)


def test_two_users_and_memberships_match_application(engine, hashes):
    with engine.begin() as connection:
        result = apply_seed(connection, hashes)
    assert result == [{"email": ADMIN, "role": "ids_admin"},
                      {"email": CUSTOMER, "role": "customer"}]
    with Session(engine) as session:
        users = session.scalars(select(models.LocalUser)).all()
        assert len(users) == 2
        assert session.scalar(select(func.count()).select_from(models.Organization)) == 2
        assert session.scalar(select(func.count()).select_from(models.Member)) == 2
        for user in users:
            assert user.password_hash == hashes[user.email] and user.enabled
            member = session.scalar(select(models.Member).where(
                models.Member.object_id == user.object_id))
            assert member.organization_id == user.organization_id
            assert member.role == user.role and member.enabled
        assert session.scalar(select(func.count()).select_from(models.TeamSubscription)) == 0
        assert session.scalar(select(func.count()).select_from(models.CreditBudget)) == 0
    assert PASSWORD not in json.dumps(result)


def test_repeat_does_not_reset_passwords(engine, hashes):
    with engine.begin() as connection:
        apply_seed(connection, hashes)
    with pytest.raises(RuntimeError, match="already exists"):
        with engine.begin() as connection:
            apply_seed(connection, {ADMIN: "replacement", CUSTOMER: "replacement"})
    with Session(engine) as session:
        assert session.scalar(select(models.LocalUser.password_hash).where(
            models.LocalUser.email == ADMIN)) == hashes[ADMIN]


def test_case_insensitive_existing_user_rejected_before_writes(engine, hashes):
    with engine.begin() as connection:
        apply_seed(connection, hashes)
        connection.execute(models.LocalUser.__table__.update().where(
            models.LocalUser.email == ADMIN).values(email=ADMIN.upper()))
    with pytest.raises(RuntimeError, match="already exists"):
        with engine.begin() as connection:
            apply_seed(connection, hashes)


def test_failure_rolls_back_first_user_and_organizations(engine, hashes):
    with pytest.raises(KeyError):
        with engine.begin() as connection:
            apply_seed(connection, {ADMIN: hashes[ADMIN]})
    with Session(engine) as session:
        for model in (models.Organization, models.Member, models.LocalUser):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("enabled,name", [(False, "Caldova"), (True, "Different Company")])
def test_conflicting_customer_org_refuses_all_changes(engine, hashes, enabled, name):
    with Session(engine) as session:
        session.add(models.Organization(name=name, tenant_id=seed.CUSTOMER_TENANT, enabled=enabled))
        session.commit()
    with pytest.raises(RuntimeError, match="organization"):
        with engine.begin() as connection:
            apply_seed(connection, hashes)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(models.LocalUser)) == 0
        assert session.scalar(select(func.count()).select_from(models.Organization)) == 1


def test_existing_matching_org_and_member_reused(engine, hashes):
    with Session(engine) as session:
        org = models.Organization(name="Singtel IDS", tenant_id=TENANT, enabled=True)
        session.add(org)
        session.flush()
        session.add(models.Member(organization_id=org.id, object_id=seed.ADMIN_OBJECT,
                                  role="ids_admin", enabled=True))
        session.commit()
    with engine.begin() as connection:
        apply_seed(connection, hashes)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(models.Member)) == 2


def test_different_role_membership_never_promoted(engine, hashes):
    with Session(engine) as session:
        org = models.Organization(name="Singtel IDS", tenant_id=TENANT, enabled=True)
        session.add(org)
        session.flush()
        session.add(models.Member(organization_id=org.id, object_id=seed.ADMIN_OBJECT,
                                  role="customer", enabled=True))
        session.commit()
    with pytest.raises(RuntimeError, match="membership conflicts"):
        with engine.begin() as connection:
            apply_seed(connection, hashes)
    with Session(engine) as session:
        assert session.scalar(select(models.Member.role)) == "customer"
        assert session.scalar(select(func.count()).select_from(models.LocalUser)) == 0


def test_hidden_password_prompt(monkeypatch):
    monkeypatch.setattr(seed.sys.stdin, "isatty", lambda: True)
    prompt = Mock(side_effect=[PASSWORD, PASSWORD])
    monkeypatch.setattr(seed.getpass, "getpass", prompt)
    assert seed.prompt_password("Admin") == PASSWORD
    assert prompt.call_count == 2


def test_no_terminal_never_reads_password(monkeypatch):
    monkeypatch.setattr(seed.sys.stdin, "isatty", lambda: False)
    prompt = Mock()
    monkeypatch.setattr(seed.getpass, "getpass", prompt)
    with pytest.raises(RuntimeError, match="interactive terminal"):
        seed.prompt_password("Admin")
    prompt.assert_not_called()


@pytest.mark.parametrize("values", [(PASSWORD, "different"), ("short", "short"), ("a" * 30, "a" * 30)])
def test_invalid_passwords_not_echoed_in_errors(monkeypatch, values):
    monkeypatch.setattr(seed.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(seed.getpass, "getpass", Mock(side_effect=values))
    with pytest.raises(RuntimeError) as error:
        seed.prompt_password("Admin")
    assert values[0] not in str(error.value)


def test_getpass_echo_fallback_fails(monkeypatch):
    monkeypatch.setattr(seed.sys.stdin, "isatty", lambda: True)
    def no_hidden_input(_):
        seed.warnings.warn("Cannot disable echo", seed.getpass.GetPassWarning)
    monkeypatch.setattr(seed.getpass, "getpass", no_hidden_input)
    with pytest.raises(seed.getpass.GetPassWarning):
        seed.prompt_password("Admin")


def test_reviewed_bootstrap_checksum():
    assert seed.load_bootstrap().RELEASE == "local-20261023t074801z-939ccecd80d1"


def test_cli_has_no_password_or_jwt_arguments():
    options = {option for action in seed.parser()._actions for option in action.option_strings}
    assert "--execute" in options
    assert not any("password" in option or "jwt" in option for option in options)