"""Real loopback PG archive/save races. Never accepts a production connection."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from aiflux import archival, monthly_budgets
from aiflux.config import Settings
from aiflux.models import AuditEvent, Organization, OrganizationMonthlyBudgetPolicy, OrganizationMonthlyBudgetRevision
from aiflux.schemas import DeletionRequest, MonthlyBudgetUpdate
from test_admin_archival_postgres import pg, HOME, assert_locked


def wait_for_lock(engine, pid):
    deadline = monotonic() + 4
    while monotonic() < deadline:
        with engine.connect() as observer:
            if observer.scalar(text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid}):
                return
        Event().wait(.02)
    pytest.fail("Contender never demonstrably waited on the actual PostgreSQL row lock")


def payload():
    return MonthlyBudgetUpdate(allocated_usd="25", expected_version=0, reason="Synthetic race")


def test_real_pg_archive_first_waiting_stale_save_rechecks_archive_before_cas(pg):
    engine, oid, principal = pg
    stale_ready, start_save, archive_held, release_archive, save_started = (Event() for _ in range(5))
    metadata = {}

    def save():
        with Session(engine, expire_on_commit=False) as db:
            old = db.get(Organization, oid)
            assert old.deleted_at is None
            metadata["pid"] = db.scalar(text("SELECT pg_backend_pid()"))
            stale_ready.set()
            assert start_save.wait(5)
            save_started.set()
            try:
                monthly_budgets.save(db, principal, oid, payload())
            except HTTPException as error:
                return error.status_code, error.detail
            pytest.fail("Archived organization budget save unexpectedly succeeded")

    def archive():
        with Session(engine) as db:
            def before_commit(session):
                assert_locked(engine, oid)
                archive_held.set()
                assert release_archive.wait(5)
            event.listen(db, "before_commit", before_commit)
            return archival.archive(db, Settings(home_tenant_id=HOME), principal, "organization", oid,
                                    DeletionRequest(confirmation="Empty", reason="Synthetic archive race"), None).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        saving = pool.submit(save)
        assert stale_ready.wait(5)
        archiving = pool.submit(archive)
        try:
            assert archive_held.wait(5)
            start_save.set()
            assert save_started.wait(5)
            wait_for_lock(engine, metadata["pid"])
        finally:
            release_archive.set()
            start_save.set()
        assert archiving.result(10) == "archived"
        code, detail = saving.result(10)
        assert code == 409 and "archived" in detail
    with Session(engine) as db:
        assert db.get(Organization, oid).deleted_at is not None
        assert db.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetPolicy)) == 0
        assert db.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetRevision)) == 0
        # Only the actual archive audit, no budget audit/revision.
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_real_pg_save_first_archive_waits_budget_history_retained(pg):
    engine, oid, principal = pg
    saved_held, release_save, archive_started = Event(), Event(), Event()
    metadata = {}

    def save():
        with Session(engine) as db:
            def before_commit(session):
                assert_locked(engine, oid)
                saved_held.set()
                assert release_save.wait(5)
            event.listen(db, "before_commit", before_commit)
            return monthly_budgets.save(db, principal, oid, payload())

    def archive():
        with Session(engine) as db:
            metadata["pid"] = db.scalar(text("SELECT pg_backend_pid()"))
            archive_started.set()
            return archival.archive(db, Settings(home_tenant_id=HOME), principal, "organization", oid,
                                    DeletionRequest(confirmation="Empty", reason="Synthetic archive after save"), None).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        saving = pool.submit(save)
        try:
            assert saved_held.wait(5)
            archiving = pool.submit(archive)
            assert archive_started.wait(5)
            wait_for_lock(engine, metadata["pid"])
        finally:
            release_save.set()
        assert saving.result(10).version == 1
        assert archiving.result(10) == "archived"
    with Session(engine) as db:
        assert monthly_budgets.admin_dashboard(db, oid).read_only
        assert monthly_budgets.history(db, oid)["total"] == 1
        assert db.scalar(select(OrganizationMonthlyBudgetPolicy.version)) == 1
        assert db.scalar(select(func.count()).select_from(OrganizationMonthlyBudgetRevision)) == 1
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 2