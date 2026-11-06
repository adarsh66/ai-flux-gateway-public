"""Offline lifecycle tests. SQLite FK checks are NOT concurrency evidence."""
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from aiflux import archival
from aiflux.apim import ApimClient, ApimError
from aiflux.auth import Principal, hash_password, issue_local_jwt
from aiflux.config import Settings
from aiflux.models import (
    AuditEvent, Base, CreditBudget, LocalUser, Member, Organization,
    OrganizationMonthlyBudgetPolicy, OrganizationMonthlyBudgetRevision,
    Team, TeamSubscription, UsageRecord,
)
from aiflux.schemas import DeletionRequest
from aiflux.subscriptions import lock_organization, reconcile
from conftest import ADMIN_USER, CUSTOMER_USER, HOME
from test_control_plane import create_key


def delete(env, collection, entity_id, label, **extra):
    return env.client.request("DELETE", f"/api/admin/{collection}/{entity_id}", headers=env.admin,
                              json={"confirmation": label, "reason": "Retire test identity", **extra})


@pytest.fixture
def revoker(env, monkeypatch):
    """Existing fake remains unchanged; archive tests add exact resource reads."""
    state = {"value": "active", "read_fail": False, "stuck": False, "reads": 0}

    def read(sid):
        state["reads"] += 1
        env.apim.calls.append(("read", sid))
        if state["read_fail"]:
            raise ApimError(403)
        return state["value"]

    original = env.apim.set_state

    def suspend(sid, value):
        original(sid, value)
        if not state["stuck"]:
            state["value"] = value

    monkeypatch.setattr(env.apim, "subscription_state", read, raising=False)
    monkeypatch.setattr(env.apim, "set_state", suspend)
    return state


def local_user(env, oid=None, role="customer", org=None):
    oid = oid or str(uuid4())
    org = org or env.orgs["customer"]
    with Session(env.db_engine) as db:
        member = db.scalar(select(Member).where(Member.organization_id == org, Member.object_id == oid))
        if member is None:
            member = Member(organization_id=org, object_id=oid, role=role)
            db.add(member)
        user = LocalUser(email=f"{uuid4()}@test.invalid", password_hash=hash_password("test-password"),
                         display_name="Test User", organization_id=org, object_id=oid, role=role)
        db.add(user)
        db.commit()
        return user.id, user.email, member.id


def test_preview_exact_contract_and_disabled_dependencies(env):
    create_key(env)
    local_user(env)
    with Session(env.db_engine) as db:
        for model in (LocalUser, Member):
            for row in db.scalars(select(model).where(model.organization_id == env.orgs["customer"])):
                row.enabled = False
        db.commit()
    path = f"/api/admin/organizations/{env.orgs['customer']}/deletion-preview"
    result = env.client.get(path, headers=env.admin)
    assert result.status_code == 200
    body = result.json()
    assert set(body) == {"entity_type", "entity_id", "label", "can_delete", "blockers", "dependencies", "effect"}
    assert body["entity_type"] == "organization" and not body["can_delete"]
    assert body["dependencies"] == {"subscriptions": 1, "users": 1, "members": 2}
    denied = delete(env, "organizations", env.orgs["customer"], "Customer")
    assert denied.status_code == 409 and denied.json()["detail"]["dependencies"] == body["dependencies"]


def test_home_organization_and_self_protection(env):
    path = f"/api/admin/organizations/{env.orgs['admin']}/deletion-preview"
    assert not env.client.get(path, headers=env.admin).json()["can_delete"]
    assert delete(env, "organizations", env.orgs["admin"], "IDS").status_code == 409
    uid, email, _ = local_user(env, ADMIN_USER, "ids_admin", env.orgs["admin"])
    path = f"/api/admin/local-users/{uid}"
    assert not env.client.get(path + "/deletion-preview", headers=env.admin).json()["can_delete"]
    assert delete(env, "local-users", uid, email).status_code == 409
    assert env.client.put(path, headers=env.admin, json={"enabled": False}).status_code == 409


def test_admin_only_confirmation_reason_and_missing(env):
    uid, email, _ = local_user(env)
    path = f"/api/admin/local-users/{uid}"
    assert env.client.get(path + "/deletion-preview", headers=env.customer).status_code == 403
    assert env.client.request("DELETE", path, headers=env.customer,
                              json={"confirmation": email, "reason": "test"}).status_code == 403
    assert delete(env, "local-users", uid, "wrong").status_code == 422
    assert delete(env, "local-users", uid, email, reason="   ").status_code == 422
    assert delete(env, "local-users", str(uuid4()), "missing").status_code == 404


def test_local_archive_atomic_exact_member_and_both_auth_paths(env, monkeypatch):
    monkeypatch.setattr("aiflux.turnstile_exchange.ensure_local_users_seeded", lambda *a: None)
    env.settings.local_auth_enabled = True
    uid, email, mid = local_user(env, CUSTOMER_USER)
    other_uid, _, other_mid = local_user(env)
    with Session(env.db_engine) as db:
        user = db.get(LocalUser, uid)
        token = issue_local_jwt(env.settings, user, db.get(Organization, user.organization_id))
    headers = {"Authorization": "Bearer " + token}
    assert env.client.get("/api/me", headers=headers).status_code == 200
    assert delete(env, "local-users", uid, email).json()["status"] == "archived"
    assert env.client.get("/api/me", headers=headers).status_code == 403
    assert env.client.get("/api/me", headers=env.customer).status_code == 403
    assert delete(env, "local-users", uid, email).json()["status"] == "archived"
    assert env.client.put(f"/api/admin/local-users/{uid}", headers=env.admin,
                          json={"enabled": True}).status_code == 409
    assert env.client.put(f"/api/admin/members/{mid}", headers=env.admin,
                          json={"enabled": True}).status_code == 409
    listed = env.client.get("/api/admin/local-users", headers=env.admin).json()["items"]
    assert uid not in {u["id"] for u in listed} and other_uid in {u["id"] for u in listed}
    assert env.client.post("/api/admin/local-users", headers=env.admin, json={
        "email": email.upper(), "password": "new-password", "display_name": "Reuse",
        "organization_id": env.orgs["customer"],
    }).status_code == 409
    with Session(env.db_engine) as db:
        assert db.get(Member, mid).deleted_at is not None
        assert db.get(Member, other_mid).deleted_at is None
        assert db.get(LocalUser, uid).deleted_by == ADMIN_USER
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "local_user.archived")).reason == "Retire test identity"


def test_local_archive_rolls_back_member_if_commit_fails(env, monkeypatch):
    uid, email, mid = local_user(env)
    with Session(env.db_engine) as db:
        principal = Principal(env.orgs["admin"], "IDS", HOME, ADMIN_USER, "ids_admin")
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("offline commit failure")))
        with pytest.raises(RuntimeError):
            archival.archive(db, env.settings, principal, "local_user", uid,
                             DeletionRequest(confirmation=email, reason="test"), env.apim)
        db.rollback()
    with Session(env.db_engine) as db:
        assert db.get(LocalUser, uid).deleted_at is None and db.get(Member, mid).deleted_at is None


def test_last_viable_guard_uses_member_not_local_role(env):
    uid, _, mid = local_user(env, role="customer", org=env.orgs["admin"])
    with Session(env.db_engine) as db:
        candidate = db.get(Member, mid)
        candidate.role = "ids_admin"
        actor = db.scalar(select(Member).where(Member.object_id == ADMIN_USER))
        actor.enabled = False
        db.commit()
        # Direct policy test simulates an already-authenticated actor waiting on
        # the mutex. Endpoint lock_identity separately rejects revoked actors.
        p = Principal(env.orgs["admin"], "IDS", HOME, ADMIN_USER, "ids_admin")
        assert "last viable" in " ".join(archival.member_blockers(db, p, candidate))


def test_subscription_archive_readback_retry_and_no_revival(env, revoker):
    sid = create_key(env)["id"]
    path = f"/api/admin/subscriptions/{sid}"
    revoker["read_fail"] = True
    failure = delete(env, "subscriptions", sid, "Platform")
    assert failure.status_code == 502 and failure.json()["status"] == "failed"
    assert "403" not in failure.text
    admin = env.client.get("/api/admin/subscriptions", headers=env.admin).json()
    assert admin["items"][0]["deletion_status"] == "failed"
    assert env.client.get("/api/subscriptions", headers=env.customer).json()["total"] == 0
    assert env.client.get(path + "/deletion-preview", headers=env.admin).json()["can_delete"]
    for action in ("reveal", "rotate", "reconcile"):
        assert env.client.post(path + "/" + action, headers=env.admin, json={}).status_code == 409
    assert env.client.post(f"/api/subscriptions/{sid}/reveal", headers=env.customer, json={}).status_code == 409
    assert env.client.put(path + "/state", headers=env.admin, json={"state": "active"}).status_code == 409
    with Session(env.db_engine) as db:
        row = db.get(TeamSubscription, sid)
        idem, team = row.idempotency_key, row.team
        assert row.deletion_requested_at and row.deleted_at is None
    assert env.client.post("/api/admin/subscriptions", headers=env.admin | {"Idempotency-Key": idem}, json={
        "organization_id": env.orgs["customer"], "name": "Platform", "team": team,
    }).status_code == 409
    revoker["read_fail"] = False
    before = len(env.apim.calls)
    success = delete(env, "subscriptions", sid, "Platform")
    assert success.status_code == 200 and success.json()["status"] == "archived"
    assert [c[0] for c in env.apim.calls[before:]] == ["read", "state", "read"]
    assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "archived"
    assert env.client.get("/api/admin/subscriptions", headers=env.admin).json()["total"] == 0
    assert env.client.put(f"/api/admin/organizations/{env.orgs['customer']}", headers=env.admin,
                          json={"enabled": False}).status_code == 200
    assert env.client.put(f"/api/admin/organizations/{env.orgs['customer']}", headers=env.admin,
                          json={"enabled": True}).status_code == 200
    with Session(env.db_engine) as db:
        assert db.get(TeamSubscription, sid).desired_state == "suspended"
    assert not any(c[0] == "ensure" for c in env.apim.calls[before:])


@pytest.mark.parametrize("value", [None, "suspended"])
def test_already_suspended_or_proven_missing_never_creates(env, revoker, value):
    sid = create_key(env)["id"]
    revoker["value"] = value
    env.apim.calls.clear()
    assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "archived"
    assert [c[0] for c in env.apim.calls] == ["read", "read"]


def test_unverified_async_suspension_stays_pending(env, revoker):
    sid = create_key(env)["id"]
    revoker["stuck"] = True
    assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "pending"
    with Session(env.db_engine) as db:
        row = db.get(TeamSubscription, sid)
        assert row.deletion_status == "pending" and row.deleted_at is None


@pytest.mark.parametrize("stage", ["patch", "readback"])
def test_partial_remote_failures_remain_durable_and_retryable(env, revoker, monkeypatch, stage):
    sid = create_key(env)["id"]
    if stage == "patch":
        env.apim.fail = True
    else:
        original = env.apim.subscription_state

        def fail_readback(value):
            if revoker["reads"] == 1:
                raise ApimError()
            return original(value)

        monkeypatch.setattr(env.apim, "subscription_state", fail_readback)
    result = delete(env, "subscriptions", sid, "Platform")
    assert result.status_code == 502 and result.json()["status"] == "failed"
    with Session(env.db_engine) as db:
        row = db.get(TeamSubscription, sid)
        assert row.deleted_at is None and row.deletion_requested_at and row.deletion_status == "failed"


def test_builtin_master_uuid_is_protected_before_remote_calls(env, revoker):
    sid = "00000000-0000-0000-0000-000000000000"
    with Session(env.db_engine) as db:
        db.add(TeamSubscription(id=sid, organization_id=env.orgs["customer"], name="Master",
                                team="Reserved", idempotency_key=str(uuid4())))
        db.commit()
    before = len(env.apim.calls)
    info = env.client.get(f"/api/admin/subscriptions/{sid}/deletion-preview", headers=env.admin).json()
    assert not info["can_delete"]
    assert delete(env, "subscriptions", sid, "Master").status_code == 409
    assert len(env.apim.calls) == before


def test_apim_success_db_failure_recovered_without_recreation(env, revoker, monkeypatch):
    sid = create_key(env)["id"]
    principal = Principal(env.orgs["admin"], "IDS", HOME, ADMIN_USER, "ids_admin")
    with Session(env.db_engine) as db:
        commit, attempts = db.commit, []

        def fail_final_commit():
            attempts.append(1)
            if len(attempts) == 2:
                raise RuntimeError("synthetic final commit failure")
            commit()

        monkeypatch.setattr(db, "commit", fail_final_commit)
        with pytest.raises(RuntimeError):
            archival.archive(db, env.settings, principal, "subscription", sid,
                             DeletionRequest(confirmation="Platform", reason="test"), env.apim)
        db.rollback()
    assert revoker["value"] == "suspended"
    env.apim.calls.clear()
    assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "archived"
    assert [c[0] for c in env.apim.calls] == ["read", "read"]


def test_stale_reconcile_refreshes_lifecycle_before_network(env, revoker):
    sid = create_key(env)["id"]
    with Session(env.db_engine) as stale:
        row = stale.get(TeamSubscription, sid)
        assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "archived"
        before = len(env.apim.calls)
        with pytest.raises(HTTPException) as exc:
            reconcile(stale, row, env.apim, Principal(env.orgs["admin"], "IDS", HOME, ADMIN_USER, "ids_admin"))
        assert exc.value.status_code == 409 and len(env.apim.calls) == before


def test_organization_archive_reserves_tenant_and_blocks_child_writers(env):
    tenant = str(uuid4())
    org = env.client.post("/api/admin/organizations", headers=env.admin,
                          json={"name": "Empty Org", "tenant_id": tenant}).json()
    oid = org["id"]
    assert delete(env, "organizations", oid, "Empty Org").json()["status"] == "archived"
    assert delete(env, "organizations", oid, "Empty Org").json()["status"] == "archived"
    assert oid not in {o["id"] for o in env.client.get("/api/admin/organizations", headers=env.admin).json()["items"]}
    assert env.client.post("/api/admin/organizations", headers=env.admin,
                           json={"name": "Reuse", "tenant_id": tenant}).status_code == 409
    assert env.client.put(f"/api/admin/organizations/{oid}", headers=env.admin,
                          json={"enabled": True}).status_code == 409
    assert env.client.post("/api/admin/members", headers=env.admin,
                           json={"organization_id": oid, "object_id": str(uuid4())}).status_code == 403
    assert env.client.post("/api/admin/local-users", headers=env.admin, json={
        "organization_id": oid, "email": "new@test.invalid", "password": "new-password", "display_name": "New",
    }).status_code == 403
    assert env.client.post("/api/admin/subscriptions", headers=env.admin | {"Idempotency-Key": str(uuid4())},
                           json={"organization_id": oid, "name": "New", "team": "New"}).status_code == 403


def test_foreign_keys_history_and_monthly_budget_survive_archival():
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        assert conn.scalar(text("PRAGMA foreign_keys")) == 1
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        home, org = Organization(name="IDS", tenant_id=HOME), Organization(name="History", tenant_id=str(uuid4()))
        db.add_all([home, org]); db.flush()
        db.add(Member(organization_id=home.id, object_id=ADMIN_USER, role="ids_admin")); db.flush()
        team = Team(id=str(uuid4()), organization_id=org.id, name="Retained")
        db.add(team); db.flush()
        sub = TeamSubscription(id=str(uuid4()), organization_id=org.id, team_id=team.id, name="Retained",
                               team="Retained", state="suspended", desired_state="suspended", idempotency_key=str(uuid4()))
        db.add(sub); db.flush()
        sub.deleted_at = datetime.now(UTC)
        budget = CreditBudget(organization_id=org.id, subscription_id=sub.id, monthly_budget_usd=321)
        db.add_all([budget, OrganizationMonthlyBudgetPolicy(organization_id=org.id, version=1)])
        db.flush()
        db.add(OrganizationMonthlyBudgetRevision(organization_id=org.id, version=1, allocated_usd=321,
                                                advisory_threshold_pct=80, reason="Retained", changed_by=ADMIN_USER))
        db.add(UsageRecord(id="history", organization_id=org.id, subscription_id=sub.id, model="retained",
                           provider="test", region="test", occurred_at=datetime.now(UTC), status_code=200,
                           completeness="complete"))
        db.commit()
        p = Principal(home.id, "IDS", HOME, ADMIN_USER, "ids_admin")
        assert archival.archive(db, Settings(home_tenant_id=HOME), p, "organization", org.id,
                                DeletionRequest(confirmation="History", reason="test"), None).status == "archived"
        assert db.get(Team, team.id) and db.get(UsageRecord, "history")
        assert db.get(CreditBudget, budget.id).monthly_budget_usd == 321
        assert db.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetRevision)) == 1
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()


@pytest.mark.parametrize("scope", ["/subscriptions/master", "/apis", "/products/wrong"])
def test_readback_rejects_unmanaged_scope_without_patch(monkeypatch, scope):
    settings = Settings(apim_resource_id="/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/test/providers/Microsoft.ApiManagement/service/test")
    client = ApimClient(settings)
    calls = []

    def send(method, url, body=None, etag=None):
        calls.append(method)
        return httpx.Response(200, json={"properties": {"scope": scope, "state": "active", "primaryKey": "never-export"}})

    monkeypatch.setattr(client, "_send", send)
    with pytest.raises(ApimError):
        client.subscription_state(str(uuid4()))
    assert calls == ["GET"]


def test_readback_only_404_is_absent_and_never_returns_keys(monkeypatch):
    client = ApimClient(Settings(apim_resource_id="/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/test/providers/Microsoft.ApiManagement/service/test"))
    sid = str(uuid4())
    for status in (401, 403, 429, 500):
        monkeypatch.setattr(client, "_request", lambda *a, **k: (_ for _ in ()).throw(ApimError(status)))
        with pytest.raises(ApimError):
            client.subscription_state(sid)
    monkeypatch.setattr(client, "_request", lambda *a, **k: (_ for _ in ()).throw(ApimError(404)))
    assert client.subscription_state(sid) is None
    scope = f"{client.settings.apim_resource_id}/products/{client.settings.apim_product_id}"
    monkeypatch.setattr(client, "_request", lambda *a, **k: {"properties": {"scope": scope, "state": "suspended", "primaryKey": "secret"}})
    assert client.subscription_state(sid) == "suspended"
    with pytest.raises(ApimError):
        client.subscription_state("00000000-0000-0000-0000-000000000000")


def test_postgres_lock_compiles_and_migration_follows_budget_not_feature2(env):
    with Session(env.db_engine) as db:
        statements = []
        original = db.scalar

        def capture(statement, *a, **kw):
            statements.append(str(statement.compile(dialect=postgresql.dialect())))
            return original(statement, *a, **kw)

        db.scalar = capture
        lock_organization(db, env.orgs["customer"])
        assert "FOR UPDATE" in statements[0]
    path = Path("services/control-plane/migrations/versions/0007_admin_archival.py")
    spec = importlib.util.spec_from_file_location("archival_revision", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.down_revision == "0006_monthly_advisory_budgets"
    assert "0005" not in module.down_revision


def test_additive_migration_existing_rows_null_and_no_budget_or_history_changes(monkeypatch):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    path = Path("services/control-plane/migrations/versions/0007_admin_archival.py")
    spec = importlib.util.spec_from_file_location("archival_revision_test", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for table in ("organizations", "members", "local_users", "team_subscriptions", "audit_events", "credit_budgets"):
            conn.execute(text(f"CREATE TABLE {table} (id VARCHAR(36) PRIMARY KEY)"))
            conn.execute(text(f"INSERT INTO {table} (id) VALUES ('retained')"))
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(conn)))
        module.upgrade()
        module.upgrade()  # Historical live-Base bootstrap must also be safe.
        for table in ("organizations", "members", "local_users", "team_subscriptions"):
            assert conn.execute(text(f"SELECT deleted_at, deleted_by, deletion_reason FROM {table}")).one() == (None, None, None)
        assert conn.execute(text("SELECT deletion_requested_at, deletion_status FROM team_subscriptions")).one() == (None, None)
        assert [c["name"] for c in inspect(conn).get_columns("credit_budgets")] == ["id"]
        assert conn.scalar(text("SELECT id FROM credit_budgets")) == "retained"
        with pytest.raises(RuntimeError, match="irreversible"):
            module.downgrade()
    engine.dispose()


def test_actual_alembic_budget_head_successor_never_creates_paused_feature2(tmp_path):
    from alembic import command
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import inspect
    engine = create_engine("sqlite:///" + (tmp_path / "archival.db").as_posix())
    cfg = Config("services/control-plane/alembic.ini")
    cfg.set_main_option("script_location", "services/control-plane/migrations")
    with engine.begin() as conn:
        for table in ("organizations", "members", "local_users", "team_subscriptions", "audit_events", "credit_budgets"):
            conn.execute(text(f"CREATE TABLE {table} (id VARCHAR(36) PRIMARY KEY)"))
            conn.execute(text(f"INSERT INTO {table} (id) VALUES ('retained')"))
        cfg.attributes["connection"] = conn
        command.stamp(cfg, "0006_monthly_advisory_budgets")
        command.upgrade(cfg, "0007_admin_archival")
        assert MigrationContext.configure(conn).get_current_heads() == ("0007_admin_archival",)
        names = set(inspect(conn).get_table_names())
        assert "organization_model_access" not in names and "model_access_publication" not in names
        assert conn.scalar(text("SELECT id FROM credit_budgets")) == "retained"
        assert conn.scalar(text("SELECT deleted_at FROM organizations")) is None
    engine.dispose()


def test_independent_members_archive_and_unblock_organization(env):
    mid = env.client.get("/api/admin/members", headers=env.admin,
                         params={"organization_id": env.orgs["customer"]}).json()["items"][0]["id"]
    path = f"/api/admin/members/{mid}"
    preview = env.client.get(path + "/deletion-preview", headers=env.admin).json()
    assert preview["entity_type"] == "member" and preview["label"] == CUSTOMER_USER
    assert env.client.get(path + "/deletion-preview", headers=env.customer).status_code == 403
    assert delete(env, "members", mid, CUSTOMER_USER).json()["status"] == "archived"
    assert env.client.get("/api/me", headers=env.customer).status_code == 403
    assert delete(env, "members", mid, CUSTOMER_USER).json()["status"] == "archived"
    assert env.client.put(path, headers=env.admin, json={"enabled": True}).status_code == 409
    assert env.client.post("/api/admin/members", headers=env.admin, json={
        "organization_id": env.orgs["customer"], "object_id": CUSTOMER_USER,
    }).status_code == 409
    assert delete(env, "organizations", env.orgs["customer"], "Customer").json()["status"] == "archived"


def test_member_link_and_self_cannot_be_archived_independently(env):
    uid, email, mid = local_user(env)
    info = env.client.get(f"/api/admin/members/{mid}/deletion-preview", headers=env.admin).json()
    assert not info["can_delete"] and info["dependencies"]["users"] == 1
    with Session(env.db_engine) as db:
        oid = db.get(Member, mid).object_id
        self_id = db.scalar(select(Member.id).where(Member.object_id == ADMIN_USER))
    assert delete(env, "members", mid, oid).status_code == 409
    assert delete(env, "members", self_id, ADMIN_USER).status_code == 409
    assert delete(env, "local-users", uid, email).json()["status"] == "archived"
    assert delete(env, "members", mid, oid).json()["status"] == "archived"


def test_deleted_user_never_archives_foreign_org_membership(env):
    uid, email, mid = local_user(env)
    with Session(env.db_engine) as db:
        oid = db.get(LocalUser, uid).object_id
        foreign = Member(organization_id=env.orgs["admin"], object_id=oid, role="customer")
        db.add(foreign); db.commit()
        foreign_id = foreign.id
    assert delete(env, "local-users", uid, email).json()["status"] == "archived"
    with Session(env.db_engine) as db:
        assert db.get(Member, mid).deleted_at is not None
        assert db.get(Member, foreign_id).deleted_at is None and db.get(Member, foreign_id).enabled


def test_pending_and_failed_children_still_block_org(env, revoker):
    sid = create_key(env)["id"]
    revoker["read_fail"] = True
    assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "failed"
    info = env.client.get(f"/api/admin/organizations/{env.orgs['customer']}/deletion-preview", headers=env.admin).json()
    assert not info["can_delete"] and info["dependencies"]["subscriptions"] == 1
    assert delete(env, "organizations", env.orgs["customer"], "Customer").status_code == 409


@pytest.mark.parametrize("operation", ["unknown", "in-progress"])
def test_unsettled_previous_activation_blocks_suspend_and_revoke_proof(env, revoker, monkeypatch, operation):
    sid = create_key(env)["id"]
    with Session(env.db_engine) as db:
        db.get(TeamSubscription, sid).apim_pending_operation = operation
        db.commit()
    def resolve(*args):
        raise ApimError(202)
    monkeypatch.setattr(env.apim, "resolve_subscription_operation", resolve, raising=False)
    before = len(env.apim.calls)
    assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "failed"
    assert len(env.apim.calls) == before and revoker["reads"] == 0
    with Session(env.db_engine) as db:
        row = db.get(TeamSubscription, sid)
        assert row.apim_pending_operation == operation and row.deleted_at is None
    monkeypatch.setattr(env.apim, "resolve_subscription_operation", lambda *a: None)
    assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "archived"


def test_async_activation_persists_barrier_then_retry_settles_before_revoke(env, revoker, monkeypatch):
    sid = create_key(env)["id"]
    def asynchronous(*args):
        raise ApimError(202, pending_operation="test-operation")
    monkeypatch.setattr(env.apim, "ensure", asynchronous)
    response = env.client.put(f"/api/admin/subscriptions/{sid}/state", headers=env.admin, json={"state": "active"})
    assert response.status_code == 502
    with Session(env.db_engine) as db:
        assert db.get(TeamSubscription, sid).apim_pending_operation == "test-operation"
    calls = []
    monkeypatch.setattr(env.apim, "resolve_subscription_operation", lambda *a: calls.append("settled"), raising=False)
    assert delete(env, "subscriptions", sid, "Platform").json()["status"] == "archived"
    assert calls == ["settled"] and revoker["value"] == "suspended"


@pytest.mark.parametrize("state", ["Updating", "InProgress", "Failed"])
def test_subscription_readback_rejects_unsettled_resource(monkeypatch, state):
    client = ApimClient(Settings(apim_resource_id="/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/test/providers/Microsoft.ApiManagement/service/test"))
    props = {"scope": client.settings.apim_resource_id + "/products/" + client.settings.apim_product_id,
             "state": "suspended", "provisioningState": state}
    monkeypatch.setattr(client, "_request", lambda *a, **k: {"properties": props})
    with pytest.raises(ApimError):
        client.subscription_state(str(uuid4()))


@pytest.mark.parametrize("header", ["https://attacker.invalid/collect", "https://management.azure.com/wrong", None])
def test_async_write_unknown_or_foreign_operation_never_followed(monkeypatch, header):
    client = ApimClient(Settings(apim_resource_id="/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/test/providers/Microsoft.ApiManagement/service/test"))
    calls = []
    def send(method, url, *args):
        calls.append(method)
        return httpx.Response(202, headers={"Azure-AsyncOperation": header} if header else {})
    monkeypatch.setattr(client, "_send", send)
    with pytest.raises(ApimError) as exc:
        client.ensure(str(uuid4()), "Test", "active")
    assert exc.value.pending_operation == "unknown" and calls == ["PUT"]


def test_validated_operation_terminal_read_and_202_not_readback_proof(monkeypatch):
    client = ApimClient(Settings(apim_resource_id="/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/test/providers/Microsoft.ApiManagement/service/test"))
    sid = str(uuid4())
    operation = "https://management.azure.com" + client.settings.apim_resource_id + "/tenant/operationResults/test-operation"
    monkeypatch.setattr(client, "_send", lambda *a, **k: httpx.Response(202, headers={"Azure-AsyncOperation": operation}))
    with pytest.raises(ApimError) as exc:
        client.ensure(sid, "Test", "active")
    assert exc.value.pending_operation == operation
    with pytest.raises(ApimError):
        client.subscription_state(sid)
    for state in ("Accepted", "InProgress", "Invalid"):
        monkeypatch.setattr(client, "_send", lambda *a, **k: httpx.Response(200, json={"status": state}))
        with pytest.raises(ApimError):
            client.resolve_subscription_operation(sid, operation)
    for state in ("Succeeded", "Failed", "Canceled"):
        monkeypatch.setattr(client, "_send", lambda *a, **k: httpx.Response(200, json={"status": state}))
        assert client.resolve_subscription_operation(sid, operation) is None


def test_transport_unknown_write_distinct_from_credential_failure(monkeypatch):
    from types import SimpleNamespace
    client = ApimClient(Settings(apim_resource_id="/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/test/providers/Microsoft.ApiManagement/service/test"))
    client._credential = SimpleNamespace(get_token=lambda *a: SimpleNamespace(token="synthetic-test-token"))
    monkeypatch.setattr(httpx, "request", lambda *a, **k: (_ for _ in ()).throw(httpx.ReadTimeout("synthetic timeout")))
    with pytest.raises(ApimError) as exc:
        client.ensure(str(uuid4()), "Test", "active")
    assert exc.value.pending_operation == "unknown"
    from azure.core.exceptions import ClientAuthenticationError
    client._credential = SimpleNamespace(get_token=lambda *a: (_ for _ in ()).throw(ClientAuthenticationError("synthetic failure")))
    with pytest.raises(ApimError) as exc:
        client.ensure(str(uuid4()), "Test", "active")
    assert exc.value.pending_operation is None


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
def test_unacknowledged_put_server_errors_preserve_unknown_barrier(monkeypatch, status):
    from types import SimpleNamespace
    client = ApimClient(Settings(apim_resource_id="/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/test/providers/Microsoft.ApiManagement/service/test"))
    client._credential = SimpleNamespace(get_token=lambda *a: SimpleNamespace(token="synthetic"))
    monkeypatch.setattr(httpx, "request", lambda *a, **k: httpx.Response(status))
    with pytest.raises(ApimError) as exc:
        client.ensure(str(uuid4()), "Test", "active")
    assert exc.value.pending_operation == "unknown"


@pytest.mark.parametrize("tombstone", ["deleted_at", "deletion_requested_at", "apim_pending_operation"])
def test_atomic_readiness_finalization_cannot_restore_tombstones(env, tombstone):
    from aiflux.subscriptions import mark_subscription_ready
    sid = create_key(env)["id"]
    with Session(env.db_engine) as stale:
        row = stale.get(TeamSubscription, sid)
        assert row.state == "active"
        with Session(env.db_engine) as db:
            target = db.get(TeamSubscription, sid)
            target.state = "pending"
            setattr(target, tombstone, "unknown" if tombstone == "apim_pending_operation" else datetime.now(UTC))
            db.commit()
        assert mark_subscription_ready(stale, sid) == 0
        stale.commit()
    with Session(env.db_engine) as db:
        assert db.get(TeamSubscription, sid).state == "pending"