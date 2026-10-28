"""Opt-in SQL portal accounts. No credentials or signing keys are built in."""

import base64
import hashlib
import hmac
import json
import secrets
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux.models import Organization, PortalUser

if TYPE_CHECKING:
    from aiflux.config import Settings

PORTAL_ISSUER = "aiflux-sql-portal"
PASSWORD_ITERATIONS = 600_000
PORTAL_ROLES = {"customer", "ids_admin"}


class PortalLoginRequest(BaseModel):
    # Do not inherit Input: it strips whitespace, including from passwords.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128, repr=False)


class SeedUser(PortalLoginRequest):
    role: Literal["customer", "ids_admin"]
    organization_name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        if value != value.strip() or not value.isascii() or not all(
            c.isalnum() or c in "._@-" for c in value
        ):
            raise ValueError("Invalid seed username")
        return value

    @field_validator("password")
    @classmethod
    def secure_password(cls, value: str) -> str:
        if not (
            len(value) >= 12
            and any(c.isupper() for c in value)
            and any(c.islower() for c in value)
            and any(c.isdigit() for c in value)
            and any(not c.isalnum() and not c.isspace() for c in value)
            and len(set(value)) >= 8
        ):
            raise ValueError("Seed password does not meet security requirements")
        return value


def parse_seed_users(value: str) -> list[SeedUser]:
    if not value:
        return []
    try:
        raw = json.loads(value)
        if not isinstance(raw, list):
            raise ValueError
        users = [SeedUser.model_validate(item) for item in raw]
        # SQL Server commonly uses case-insensitive collations.
        if len({user.username.casefold() for user in users}) != len(users):
            raise ValueError
        return users
    except (ValueError, TypeError, ValidationError):
        # Never propagate JSON/Pydantic exceptions containing secret input.
        raise ValueError("portal_seed_users must be a JSON array of valid, unique seed accounts") from None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join((
        "pbkdf2_sha256", str(PASSWORD_ITERATIONS),
        base64.b64encode(salt).decode("ascii"), base64.b64encode(digest).decode("ascii"),
    ))


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, count, salt_text, digest_text = encoded.split("$")
        iterations = int(count)
        if scheme != "pbkdf2_sha256" or not PASSWORD_ITERATIONS <= iterations <= 2_000_000:
            return False
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(digest_text, validate=True)
        if len(salt) != 16 or len(expected) != 32:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def seed_portal_users(db: Session, settings: "Settings") -> None:
    """Insert explicitly configured accounts; never alter existing accounts or orgs."""
    users = parse_seed_users(settings.portal_seed_users)
    home_tenant = str(UUID(settings.home_tenant_id))
    for seed in users:
        if db.scalar(select(PortalUser).where(PortalUser.username == seed.username)) is not None:
            continue
        admin = seed.role == "ids_admin"
        tenant = home_tenant if admin else str(uuid5(UUID(home_tenant), "sql-portal:" + seed.username))
        org = db.scalar(select(Organization).where(Organization.tenant_id == tenant))
        if org is None:
            org = Organization(
                name=settings.home_organization_name if admin else seed.organization_name or seed.username,
                tenant_id=tenant,
            )
            db.add(org)
            db.flush()
        db.add(PortalUser(
            username=seed.username, password_hash=hash_password(seed.password), role=seed.role,
            organization_id=org.id, organization_name=org.name, tenant_id=org.tenant_id,
        ))
    db.commit()


def account_organization(db: Session, user: PortalUser, settings: "Settings") -> Organization | None:
    if not user.enabled or user.role not in PORTAL_ROLES:
        return None
    org = db.get(Organization, user.organization_id)
    if org is None or not org.enabled or org.tenant_id != user.tenant_id:
        return None
    if user.role == "ids_admin" and org.tenant_id != str(UUID(settings.home_tenant_id)):
        return None
    return org