from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.companion_activity.initiative import (
    InitiativeAcquireRequest,
    PostgresCompanionInitiativeAuthority,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

NOW = datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc)


def database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=6,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-companion-initiative-tests",
        )
    )


def request(session_id: str, intent_id: str, *, owner: str = "desktop") -> InitiativeAcquireRequest:
    return InitiativeAcquireRequest(
        session_id=session_id,
        generation="session",
        owner=owner,
        intent_id=intent_id,
        channel="text",
        urgency="normal",
        interruptibility="idle_only",
        requested_at=NOW,
        ttl_seconds=30.0,
        minimum_spacing_seconds=25.0,
    )


def test_two_authority_instances_share_one_transactional_session_lease() -> None:
    db = database()
    try:
        apply_migrations(db)
        session_id = f"chat:{uuid4().hex}"
        first = PostgresCompanionInitiativeAuthority(db)
        second = PostgresCompanionInitiativeAuthority(db)
        first.register_generation(session_id, "session")

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(first.acquire, request(session_id, "intent:a", owner="desktop"))
            future_b = pool.submit(second.acquire, request(session_id, "intent:b", owner="social"))
            decisions = (future_a.result(), future_b.result())

        accepted = [item for item in decisions if item.accepted]
        blocked = [item for item in decisions if not item.accepted]
        assert len(accepted) == 1
        assert len(blocked) == 1
        assert blocked[0].reason == "initiative_active"
        lease = accepted[0].lease
        assert lease is not None

        bound = second.bind_intent(
            session_id=session_id,
            lease_id=lease.lease_id,
            intent_id="turn:shared",
            bound_at=NOW + timedelta(seconds=1),
        )
        assert bound is not None
        assert bound.intent_id == "turn:shared"
        assert first.snapshot(session_id, now=NOW + timedelta(seconds=1)).active_lease == bound

        assert first.finish_intent(
            session_id=session_id,
            intent_id="turn:other",
            finished_at=NOW + timedelta(seconds=2),
            delivered=True,
        ) is False
        assert second.finish_intent(
            session_id=session_id,
            intent_id="turn:shared",
            finished_at=NOW + timedelta(seconds=2),
            delivered=True,
        ) is True

        spaced = first.acquire(
            request(session_id, "intent:after", owner="memory").model_copy(
                update={"requested_at": NOW + timedelta(seconds=3)}
            )
        )
        assert spaced.accepted is False
        assert spaced.reason == "initiative_spacing"
    finally:
        db.close()


def test_critical_cross_worker_preemption_invalidates_old_lease() -> None:
    db = database()
    try:
        apply_migrations(db)
        session_id = f"chat:{uuid4().hex}"
        first = PostgresCompanionInitiativeAuthority(db)
        second = PostgresCompanionInitiativeAuthority(db)
        first.register_generation(session_id, "session")
        normal = first.acquire(request(session_id, "intent:normal"))
        assert normal.lease is not None

        critical = second.acquire(
            InitiativeAcquireRequest(
                session_id=session_id,
                generation="session",
                owner="desktop",
                intent_id="intent:critical",
                channel="text",
                urgency="critical",
                interruptibility="interrupt",
                requested_at=NOW + timedelta(milliseconds=100),
                ttl_seconds=30.0,
                minimum_spacing_seconds=0.0,
            )
        )

        assert critical.accepted is True
        assert critical.reason == "preempted_by_critical_interrupt"
        assert first.authorizes(
            normal.lease,
            now=NOW + timedelta(milliseconds=200),
        ) is False
        assert critical.lease is not None
        assert second.authorizes(
            critical.lease,
            now=NOW + timedelta(milliseconds=200),
        ) is True
    finally:
        db.close()
