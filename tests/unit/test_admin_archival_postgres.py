"""Opt-in REAL PostgreSQL tests, never a production/private cloud connection.

Set AIFLUX_ARCHIVAL_TEST_POSTGRES_URL to a loopback PostgreSQL database whose
name ends in _test. Uses a unique disposable schema. Not run unless explicitly
configured; SQLite success must never be reported as PG concurrency evidence.
No APIM network calls, credentials acquisition, or role/grant changes.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from aiflux import archival
from aiflux.auth import Principal
from aiflux.config import Settings
from aiflux.models import Base, LocalUser, Member, Organization, TeamSubscription
from aiflux.schemas import DeletionRequest, SubscriptionCreate
from aiflux.subscriptions import create_subscription, lock_organization, reconcile

HOME = "11111111-1111-4111-8111-111111111111"
ACTOR = "33333333-3333-4333-8333-333333333333"


@pytest.fixture
def pg():
    raw = os.environ.get("AIFLUX_ARCHIVAL_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Opt-in loopback PostgreSQL not configured; concurrency unverified")
    url = make_url(raw)
    if (url.get_backend_name() != "postgresql" or url.host not in {"localhost", "127.0.0.1", "::1"}
            or not (url.database or "").endswith("_test")):
        pytest.fail("Archive PG tests require loopback host and a database ending in _test")
    url = url.set(drivername="postgresql+psycopg")
    root = create_engine(url, connect_args={"connect_timeout": 3})
    schema = "archive_test_" + uuid4().hex
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={
        "connect_timeout": 3, "options": f"-c search_path={schema} -c lock_timeout=1500 -c statement_timeout=5000",
    })
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            home = Organization(name="IDS", tenant_id=HOME)
            org = Organization(name="Empty", tenant_id=str(uuid4()))
            db.add_all([home, org]); db.flush()
            db.add(Member(organization_id=home.id, object_id=ACTOR, role="ids_admin"))
            db.commit()
            principal = Principal(home.id, "IDS", HOME, ACTOR, "ids_admin")
            yield engine, org.id, principal
    finally:
        engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


def assert_locked(engine, oid):
    with Session(engine) as contender:
        with pytest.raises(OperationalError) as exc:
            contender.scalar(select(Organization).where(Organization.id == oid).with_for_update(nowait=True))
        assert getattr(exc.value.orig, "sqlstate", None) == "55P03"
        contender.rollback()


def test_real_pg_child_create_vs_archive_share_row_lock(pg):
    engine, oid, principal = pg
    settings = Settings(home_tenant_id=HOME)

    class Remote:
        def ensure(self, sid, name, state):
            assert_locked(engine, oid)

    with Session(engine) as writer:
        row = create_subscription(writer, principal, SubscriptionCreate(name="Child", team="Team"),
                                  uuid4(), Remote(), oid)
        sid = row.id
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc:
            archival.archive(db, settings, principal, "organization", oid,
                             DeletionRequest(confirmation="Empty", reason="test"), None)
        assert exc.value.status_code == 409
        db.rollback()
        assert db.get(TeamSubscription, sid).deleted_at is None
    # Reverse order: committed archive makes every subsequent create fail closed.
    with Session(engine) as db:
        org = Organization(name="Other", tenant_id=str(uuid4()))
        db.add(org); db.commit()
        other = org.id
        archival.archive(db, settings, principal, "organization", other,
                         DeletionRequest(confirmation="Other", reason="test"), None)
        with pytest.raises(HTTPException):
            create_subscription(db, principal, SubscriptionCreate(name="Denied", team="Team"),
                                uuid4(), Remote(), other)


def test_real_pg_pending_intent_visible_and_common_lock_held_through_readback(pg):
    engine, oid, principal = pg
    with Session(engine) as db:
        row = TeamSubscription(id=str(uuid4()), organization_id=oid, name="Key", team="Team",
                               state="active", desired_state="active", idempotency_key=str(uuid4()))
        db.add(row); db.commit()
        sid = row.id
    calls = []

    class Remote:
        state = "active"

        def subscription_state(self, value):
            assert value == sid
            assert_locked(engine, oid)
            with Session(engine) as observer:
                durable = observer.get(TeamSubscription, sid)
                assert durable.deletion_requested_at and durable.deleted_at is None
                assert durable.desired_state == "suspended"
            calls.append("GET")
            return self.state

        def set_state(self, value, state):
            assert_locked(engine, oid)
            self.state = state
            calls.append("PATCH")

        def ensure(self, *args):
            pytest.fail("No creation/activation during archive")

    remote = Remote()
    with Session(engine) as stale:
        old = stale.get(TeamSubscription, sid)
        with Session(engine) as db:
            assert archival.archive(db, Settings(home_tenant_id=HOME), principal, "subscription", sid,
                                    DeletionRequest(confirmation="Key", reason="test"), remote).status == "archived"
        with pytest.raises(HTTPException) as exc:
            reconcile(stale, old, remote, principal)
        assert exc.value.status_code == 409
    assert calls == ["GET", "PATCH", "GET"]


def test_real_pg_identity_mutex_serializes_cross_auth_admin_guards(pg):
    engine, _, principal = pg
    with Session(engine) as first:
        archival.lock_identity(first, principal)
        assert_locked(engine, principal.organization_id)
        current = first.scalar(select(Member).where(Member.object_id == ACTOR))
        assert archival.member_blockers(first, principal, current)
        first.rollback()
    with Session(engine) as second:
        # Mutex released only at transaction end, not by the guard query.
        lock_organization(second, principal.organization_id)


def test_real_pg_two_administrators_cannot_revoke_each_other_concurrently(pg):
    engine, _, first = pg
    second = Principal(first.organization_id, "IDS", HOME, str(uuid4()), "ids_admin")
    with Session(engine) as db:
        db.add(Member(organization_id=second.organization_id, object_id=second.object_id, role="ids_admin"))
        users = []
        for actor in (first, second):
            user = LocalUser(email=f"{actor.object_id}@test.invalid", password_hash="unused-test-hash",
                             display_name="Admin", organization_id=actor.organization_id,
                             object_id=actor.object_id, role="ids_admin")
            db.add(user); db.flush()
            users.append((user.id, user.email))
        db.commit()
    barrier = Barrier(2)

    def revoke(actor, target):
        with Session(engine) as db:
            barrier.wait(timeout=5)
            try:
                return archival.archive(db, Settings(home_tenant_id=HOME), actor, "local_user", target[0],
                                        DeletionRequest(confirmation=target[1], reason="test concurrency"), None).status
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(revoke, first, users[1])
        b = pool.submit(revoke, second, users[0])
        assert sorted([a.result(timeout=10), b.result(timeout=10)], key=str) == [403, "archived"]
    with Session(engine) as db:
        viable = db.scalars(select(Member).where(Member.enabled.is_(True), Member.deleted_at.is_(None))).all()
        assert len(viable) == 1


def test_real_pg_inflight_activation_then_archive_cannot_finish_active(pg):
    engine, oid, principal = pg
    entered, release, deleting = Event(), Event(), Event()
    with Session(engine) as db:
        row = TeamSubscription(id=str(uuid4()), organization_id=oid, name="Race", team="Team",
                               state="pending", desired_state="active", idempotency_key=str(uuid4()))
        db.add(row); db.commit()
        sid = row.id

    class Remote:
        state = "suspended"

        def ensure(self, value, name, state):
            assert_locked(engine, oid)
            entered.set()
            assert release.wait(timeout=5)
            self.state = state

        def subscription_state(self, value):
            assert_locked(engine, oid)
            return self.state

        def set_state(self, value, state):
            assert_locked(engine, oid)
            self.state = state

    remote = Remote()

    def activate():
        with Session(engine) as db:
            reconcile(db, db.get(TeamSubscription, sid), remote, principal)

    def remove():
        with Session(engine) as db:
            deleting.set()
            return archival.archive(db, Settings(home_tenant_id=HOME), principal, "subscription", sid,
                                    DeletionRequest(confirmation="Race", reason="test concurrency"), remote).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        active = pool.submit(activate)
        try:
            assert entered.wait(timeout=5)
            archived = pool.submit(remove)
            assert deleting.wait(timeout=5)
        finally:
            release.set()
        active.result(timeout=10)
        assert archived.result(timeout=10) == "archived"
    assert remote.state == "suspended"
    with Session(engine) as db:
        row = db.get(TeamSubscription, sid)
        assert row.deleted_at and row.state == row.desired_state == "suspended"