"""Scene talk attempts (companion 6.2): closure, start backoff and the per-account cap, in memory and in PG."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.platform.companion_activity.initiative import (
    CompanionInitiativeAuthority,
    InitiativeAcquireRequest,
    PostgresCompanionInitiativeAuthority,
    SceneTalkAttemptRequest,
)

NOW = datetime(2026, 11, 16, 20, 0, tzinfo=timezone.utc)


def _pg_authority():
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.migrations import apply_migrations

    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=6, connect_timeout_seconds=10,
        statement_timeout_ms=60_000, lock_timeout_ms=30_000, application_name="omnix-scene-talk-tests",
    ))
    apply_migrations(database)
    return PostgresCompanionInitiativeAuthority(database)


@pytest.fixture(params=["memory", "postgres"])
def authority(request):
    if request.param == "memory":
        return CompanionInitiativeAuthority()
    if not os.environ.get("OMNIX_TEST_DATABASE_URL"):
        pytest.skip("OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return _pg_authority()


def _ask(session_id: str, *, user_id: str, anchor: str, kind: str = "line", cap: int = 12,
         at: datetime = NOW, counted: bool = True) -> InitiativeAcquireRequest:
    return InitiativeAcquireRequest(
        session_id=session_id, generation="session", owner="scene", intent_id=f"proactive:pending:{uuid4().hex}",
        channel="voice", urgency="normal", interruptibility="idle_only", requested_at=at, ttl_seconds=90.0,
        minimum_spacing_seconds=0.0,
        scene_talk=SceneTalkAttemptRequest(user_id=user_id, anchor_message_id=anchor, kind=kind,
                                           attempts_per_hour=cap, counted=counted),
    )


def _ids() -> tuple[str, str]:
    return f"chat:{uuid4().hex}", f"user:{uuid4().hex}"


def test_one_attempt_per_lease_and_its_outcome_is_set_once(authority) -> None:
    session_id, user_id = _ids()
    decision = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a"))
    assert decision.accepted and decision.lease is not None
    attempt = authority.active_scene_attempt(session_id, now=NOW)
    assert attempt is not None and attempt.attempt_id == decision.lease.lease_id and attempt.outcome is None

    recorded = authority.record_scene_attempt(attempt_id=attempt.attempt_id, outcome="streamed",
                                              finished_at=NOW, streamed_text="x" * 300)
    assert recorded is not None and recorded.streamed_text == "x" * 240
    assert authority.record_scene_attempt(attempt_id=attempt.attempt_id, outcome="failed", finished_at=NOW) is None
    assert authority.active_scene_attempt(session_id, now=NOW, intent_id="other") is None
    assert authority.active_scene_attempt(session_id, now=NOW).streamed_text == "x" * 240


def test_a_declined_line_closes_its_anchor(authority) -> None:
    session_id, user_id = _ids()
    lease = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a", kind="reaction")).lease
    authority.record_scene_attempt(attempt_id=lease.lease_id, outcome="declined", finished_at=NOW)
    authority.finish(session_id=session_id, lease_id=lease.lease_id, finished_at=NOW, delivered=False)

    again = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a"))
    assert (again.accepted, again.reason) == (False, "scene_talk_closed")
    assert authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:b")).accepted


def test_a_skipped_line_may_be_asked_once_more_and_a_second_skip_closes_the_anchor(authority) -> None:
    # C1 (2026-11-23): the call asks once more without the member who said SKIP; a second SKIP ends it.
    session_id, user_id = _ids()
    for attempt in range(2):
        decision = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a", kind="line"))
        assert decision.accepted, attempt
        authority.record_scene_attempt(attempt_id=decision.lease.lease_id, outcome="skipped", finished_at=NOW)
        authority.finish(session_id=session_id, lease_id=decision.lease.lease_id, finished_at=NOW, delivered=False)

    again = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a", kind="reaction"))
    assert (again.accepted, again.reason) == (False, "scene_talk_closed")
    # A failed attempt does not count as a skip.
    other = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:b"))
    authority.record_scene_attempt(attempt_id=other.lease.lease_id, outcome="failed", finished_at=NOW)
    authority.finish(session_id=session_id, lease_id=other.lease.lease_id, finished_at=NOW, delivered=False)
    skipped = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:b"))
    authority.record_scene_attempt(attempt_id=skipped.lease.lease_id, outcome="skipped", finished_at=NOW)
    authority.finish(session_id=session_id, lease_id=skipped.lease.lease_id, finished_at=NOW, delivered=False)
    assert authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:b")).accepted


def test_a_declined_start_backs_off_until_it_expires(authority) -> None:
    session_id, user_id = _ids()
    lease = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a", kind="start")).lease
    authority.record_scene_attempt(attempt_id=lease.lease_id, outcome="skipped", finished_at=NOW,
                                   start_backoff_seconds=90.0)
    authority.finish(session_id=session_id, lease_id=lease.lease_id, finished_at=NOW, delivered=False)

    later = NOW + timedelta(seconds=30)
    held = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a", kind="start", at=later))
    assert (held.accepted, held.reason, held.eligible_in_ms) == (False, "scene_talk_backoff", 60_000)
    # A line is not a start: the backoff does not hold it.
    assert authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a", kind="line", at=later)).accepted


def test_the_cap_counts_an_accounts_attempts_across_chats(authority) -> None:
    (first, user_id), (second, _) = _ids(), _ids()
    for index in range(2):
        chat = first if index == 0 else second
        lease = authority.acquire(_ask(chat, user_id=user_id, anchor=f"msg:{index}", cap=2)).lease
        authority.finish(session_id=chat, lease_id=lease.lease_id, finished_at=NOW, delivered=True)
    # A reaction does not count and is not capped.
    reaction = authority.acquire(_ask(first, user_id=user_id, anchor="msg:r", kind="reaction", cap=2))
    assert reaction.accepted
    authority.finish(session_id=first, lease_id=reaction.lease.lease_id, finished_at=NOW, delivered=True)

    capped = authority.acquire(_ask(second, user_id=user_id, anchor="msg:9", kind="start", cap=2,
                                    at=NOW + timedelta(minutes=10)))
    assert (capped.accepted, capped.reason, capped.eligible_in_ms) == (False, "scene_talk_cap", 50 * 60_000)
    other_account = authority.acquire(_ask(second, user_id=f"user:{uuid4().hex}", anchor="msg:9", cap=2))
    assert other_account.accepted
    assert authority.acquire(_ask(first, user_id=user_id, anchor="msg:9", cap=2,
                                  at=NOW + timedelta(minutes=61))).accepted


def test_lines_answering_the_person_are_neither_capped_nor_counted(authority) -> None:
    # Group calls (owner 2026-11-19): the thread's line limit and a SKIP bound them, not the hourly cap.
    (chat, user_id) = _ids()
    for index in range(3):
        lease = authority.acquire(_ask(chat, user_id=user_id, anchor=f"msg:{index}", cap=1, counted=False)).lease
        assert lease is not None
        authority.finish(session_id=chat, lease_id=lease.lease_id, finished_at=NOW, delivered=True)
    counted = authority.acquire(_ask(chat, user_id=user_id, anchor="msg:c", cap=1))
    assert counted.accepted
    authority.finish(session_id=chat, lease_id=counted.lease.lease_id, finished_at=NOW, delivered=True)
    capped = authority.acquire(_ask(chat, user_id=user_id, anchor="msg:s", kind="start", cap=1))
    assert (capped.accepted, capped.reason) == (False, "scene_talk_cap")
    # A declined line still closes its anchor, counted or not.
    lease = authority.acquire(_ask(chat, user_id=user_id, anchor="msg:d", counted=False)).lease
    authority.record_scene_attempt(attempt_id=lease.lease_id, outcome="declined", finished_at=NOW)
    authority.finish(session_id=chat, lease_id=lease.lease_id, finished_at=NOW, delivered=False)
    again = authority.acquire(_ask(chat, user_id=user_id, anchor="msg:d", counted=False))
    assert (again.accepted, again.reason) == (False, "scene_talk_closed")


def test_two_chats_of_one_account_cannot_both_pass_the_cap_at_once(authority) -> None:
    (first, user_id), (second, _) = _ids(), _ids()
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(
            authority.acquire,
            [_ask(first, user_id=user_id, anchor="msg:a", cap=1), _ask(second, user_id=user_id, anchor="msg:b", cap=1)],
        ))
    assert sorted(decision.reason for decision in decisions) == ["initiative_acquired", "scene_talk_cap"]


def test_two_asks_for_the_same_line_give_one_line(authority) -> None:
    session_id, user_id = _ids()
    with ThreadPoolExecutor(max_workers=2) as pool:
        decisions = list(pool.map(
            authority.acquire,
            [_ask(session_id, user_id=user_id, anchor="msg:a"), _ask(session_id, user_id=user_id, anchor="msg:a")],
        ))
    assert sorted(decision.accepted for decision in decisions) == [False, True]
    accepted = next(decision for decision in decisions if decision.accepted)
    assert authority.active_scene_attempt(session_id, now=NOW).attempt_id == accepted.lease.lease_id


def test_the_person_taking_the_floor_finishes_only_a_scene_lease(authority) -> None:
    session_id, user_id = _ids()
    lease = authority.acquire(_ask(session_id, user_id=user_id, anchor="msg:a")).lease
    assert authority.finish_owner(session_id=session_id, owner="social", finished_at=NOW) is False
    assert authority.finish_owner(session_id=session_id, owner="scene", finished_at=NOW) is True
    assert authority.authorizes(lease, now=NOW) is False
    assert authority.active_scene_attempt(session_id, now=NOW) is None
    assert authority.finish_owner(session_id=session_id, owner="scene", finished_at=NOW) is False
