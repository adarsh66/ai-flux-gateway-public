"""One-time interactive user seeding. No Key Vault, JWT, DDL, or Azure writes."""

import argparse
import ast
import getpass
import hashlib
import hmac
import importlib
import importlib.util
import json
import re
import secrets
import sys
import warnings
from pathlib import Path
from uuid import UUID

from azure.identity import AzureCliCredential
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

BOOTSTRAP_SHA256 = "91cd0d5414f5a7cdc2253b25fe599c0982a84b722b0487091ada3d139a8258bf"
CUSTOMER_TENANT = "00000000-0000-0000-0000-000000000002"
ADMIN_OBJECT = "00000000-0000-0000-0000-000000000101"
CUSTOMER_OBJECT = "00000000-0000-0000-0000-000000000202"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load_bootstrap():
    path = Path(__file__).with_name("bootstrap-postgres.py")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == BOOTSTRAP_SHA256,
            "Upload the reviewed bootstrap companion; checksum mismatch")
    spec = importlib.util.spec_from_file_location("reviewed_pg_bootstrap", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def password_functions(release_dir):
    # load_release verifies this file first. Compile ONLY the deployed hashing
    # functions/constant, avoiding auth/JWT imports and their runtime configuration.
    path = Path(release_dir) / "context/services/control-plane/src/aiflux/auth.py"
    tree = ast.parse(path.read_bytes())
    nodes = [node for node in tree.body if (
        isinstance(node, ast.FunctionDef) and node.name in {"hash_password", "verify_password"}
    ) or (isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "PBKDF2_ITERATIONS" for target in node.targets))]
    require(len(nodes) == 3, "Unexpected reviewed password-hashing implementation")
    namespace = {"hashlib": hashlib, "hmac": hmac, "secrets": secrets}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["hash_password"], namespace["verify_password"]


def prompt_password(label):
    # getpass normally falls back to echoing stdin when no TTY exists. Fail
    # instead: no redirected/piped passwords, CLI arguments or environment inputs.
    require(sys.stdin.isatty(), "Passwords require an interactive terminal")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass(f"{label} password (hidden): ")
        confirmation = getpass.getpass(f"Confirm {label} password (hidden): ")
    require(hmac.compare_digest(password.encode(), confirmation.encode()),
            "Passwords do not match; nothing was saved")
    require(16 <= len(password) <= 1024 and len(set(password)) >= 8 and
            not password.startswith("@Microsoft.KeyVault("),
            "Use a unique password of 16-1024 characters with at least 8 distinct characters")
    return password


def seed_users(connection, models, tenant, admin_email, customer_email,
               customer_org, hashes):
    """Caller owns the transaction. Never alter existing passwords or privileges."""
    Organization, Member, LocalUser = models.Organization, models.Member, models.LocalUser
    require(tenant.lower() != CUSTOMER_TENANT, "Home/customer tenants must differ")
    require(admin_email != customer_email, "Admin and customer emails must differ")
    accounts = [
        (admin_email, "ids_admin", tenant, ADMIN_OBJECT, "Singtel IDS", "IDS Platform Admin"),
        (customer_email, "customer", CUSTOMER_TENANT, CUSTOMER_OBJECT, customer_org, "Customer Developer"),
    ]
    # Session never commits the caller's transaction, and autoflush is disabled
    # while auditing both accounts. No privilege takeovers or password resets.
    with Session(bind=connection, autoflush=False) as session:
        require(not session.scalar(select(LocalUser.id).where(
            func.lower(LocalUser.email).in_([admin_email, customer_email]))),
            "A requested account already exists; refusing to overwrite or reset it")
        for _, _, _, oid, _, _ in accounts:
            require(not session.scalar(select(LocalUser.id).where(LocalUser.object_id == oid)),
                    "A bootstrap identity already has an account; manual review required")
        orgs = {}
        members = {}
        for email, role, tid, oid, name, _ in accounts:
            org = session.scalar(select(Organization).where(Organization.tenant_id == tid))
            if org is not None:
                require(org.enabled and org.name == name,
                        "Existing organization differs from approved seed configuration")
                member = session.scalar(select(Member).where(
                    Member.organization_id == org.id, Member.object_id == oid))
                require(member is None or (member.enabled and member.role == role),
                        "Existing bootstrap membership conflicts; refusing privilege changes")
                members[email] = member
            orgs[email] = org
        for email, role, tid, oid, name, display in accounts:
            org = orgs[email]
            if org is None:
                org = Organization(name=name, tenant_id=tid, enabled=True)
                session.add(org)
                session.flush()
            if members.get(email) is None:
                session.add(Member(organization_id=org.id, object_id=oid, role=role, enabled=True))
            session.add(LocalUser(email=email, password_hash=hashes[email], display_name=display,
                                  organization_id=org.id, object_id=oid, role=role, enabled=True))
        session.flush()
        require(len(session.scalars(select(LocalUser).where(
            func.lower(LocalUser.email).in_([admin_email, customer_email]))).all()) == 2,
            "Seed verification failed")
    return [{"email": email, "role": role} for email, role, *_ in accounts]


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--release-dir", required=True, type=Path)
    for flag in ("subscription", "tenant", "resource-group", "server", "admin-object-id"):
        result.add_argument("--" + flag, required=True)
    result.add_argument("--database", default="turnstile")
    result.add_argument("--approved-public-ip")
    result.add_argument("--cli-python", type=Path)
    result.add_argument("--admin-email", required=True)
    result.add_argument("--customer-email", required=True)
    result.add_argument("--customer-org", required=True)
    result.add_argument("--execute", action="store_true")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    require(args.execute, "Seeding requires explicit --execute")
    require(args.database != "postgres", "Do not seed application users into postgres")
    UUID(args.tenant)
    UUID(args.admin_object_id)
    for field in ("admin_email", "customer_email"):
        value = getattr(args, field).strip().lower()
        require(len(value) <= 255 and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value),
                "Provide valid account emails")
        setattr(args, field, value)
    require(args.admin_email != args.customer_email, "Admin and customer emails must differ")
    require(0 < len(args.customer_org.strip()) <= 100, "Provide a customer organization of 1-100 characters")
    args.customer_org = args.customer_org.strip()
    bootstrap = load_bootstrap()
    config, metadata, count = bootstrap.load_release(args.release_dir)
    bootstrap.validate_offline(config, metadata)
    hash_password, verify_password = password_functions(args.release_dir)
    models = importlib.import_module("aiflux.models")
    audit = bootstrap.audit_admin(args)
    bootstrap.verify_network(audit, args.approved_public_ip)
    print(json.dumps({"reviewed_files": count, "action": "seed_two_users",
                      "admin_email": args.admin_email, "customer_email": args.customer_email,
                      "customer_org": args.customer_org, "jwt_changes": False}), flush=True)
    with AzureCliCredential(tenant_id=args.tenant, process_timeout=60) as credential:
        identity_engine = bootstrap.admin_engine(audit, "postgres", credential)
        engine = bootstrap.admin_engine(audit, args.database, credential)
        try:
            # Confirm connectivity, identity and schema before asking for secrets.
            with identity_engine.connect() as identity, engine.connect() as connection:
                bootstrap.verify_connected_admin(identity, audit)
                bootstrap.verify_session_admin(connection, audit)
                bootstrap.verify_schema(connection, metadata)
            hashes = {}
            passwords = []
            try:
                for label, email in (("Admin", args.admin_email), ("Customer", args.customer_email)):
                    password = prompt_password(label)
                    require(not passwords or not hmac.compare_digest(
                        password.encode(), passwords[0].encode()), "Use different account passwords")
                    hashed = hash_password(password)
                    require(verify_password(password, hashed), "Application hash verification failed")
                    hashes[email] = hashed
                    passwords.append(password)
                password = None
            finally:
                passwords.clear()
            # One application transaction; no DDL/migrations/role changes.
            with engine.begin() as connection:
                bootstrap.verify_session_admin(connection, audit)
                connection.execute(text("SET LOCAL search_path TO public, pg_catalog"))
                connection.execute(text("SET LOCAL lock_timeout = '15s'"))
                connection.execute(text("SET LOCAL statement_timeout = '120s'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(184863, 5432)"))
                bootstrap.verify_schema(connection, metadata)
                users = seed_users(connection, models, args.tenant, args.admin_email,
                                   args.customer_email, args.customer_org, hashes)
            print(json.dumps({"database_step": "seed_users", "committed": True, "users": users,
                              "jwt_changes": False, "runtime_deployed": False}), flush=True)
        finally:
            engine.dispose()
            identity_engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        # Neither raw SQL/driver exceptions nor hashes/passwords are logged.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "detail": str(error) if type(error) is RuntimeError else
                          "Seeding stopped; no credentials or hashes logged"}), file=sys.stderr)
        sys.exit(1)