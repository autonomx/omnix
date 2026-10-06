"""Memory suggestions follow chat's completed turns through the outbox (PA-3.4)."""
from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest

from app.platform.assistant_memory import jobs as memory_jobs
from app.platform.assistant_memory.jobs import MEMORY_SUGGEST_JOB_TYPE
from app.platform.assistant_memory.feature import FEATURE as MEMORY_FEATURE
from app.platform.assistant_memory.turn_reactions import suggest_memories_after_turn
from app.platform.chat.persistence.chat_runtime import PostgresChatSessionStore
from app.events.outbox_relay import OutboxConsumerRegistry, OutboxRelayWorker
from app.jobs import store as job_store_module
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.job_store import PostgresJobStoreAdapter
from app.persistence.transaction_binding import after_commit, share_transaction
from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

pytestmark = [
    pytest.mark.postgres,
    # The outbox relay tests claim every pending event.
    pytest.mark.xdist_group("outbox"),
    pytest.mark.skipif(not os.environ.get("OMNIX_TEST_DATABASE_URL"), reason="OMNIX_TEST_DATABASE_URL is required"),
]


@pytest.fixture
def database(monkeypatch):
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    monkeypatch.setattr(memory_jobs, "memory_suggestions_enabled", lambda: True)
    monkeypatch.setattr(job_store_module, "_DEFAULT_JOB_STORE_FACTORY", lambda: PostgresJobStoreAdapter(database))
    try:
        yield database
    finally:
        database.close()


def _store(database) -> SimpleNamespace:
    """What ``PostgresChatSessionStore._publish_turn_completed`` reads from the store."""
    return SimpleNamespace(_repository=SimpleNamespace(database=database, context=current_tenant()))


def _session(*, interaction_mode: str = "system", write_memory: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=f"chat:{uuid.uuid4().hex}", interaction_mode=interaction_mode, write_memory=write_memory)


def _events(database, session_id: str) -> list[tuple]:
    with database.connection() as connection:
        return connection.execute(
            "SELECT event_type, payload->>'user_message_id' FROM omnix_outbox_events WHERE aggregate_id = %s",
            (session_id,),
        ).fetchall()


def _suggestion_jobs(database, session_id: str) -> int:
    with database.connection() as connection:
        return connection.execute(
            "SELECT count(*) FROM omnix_jobs WHERE job_type = %s AND input_payload->>'session_id' = %s",
            (MEMORY_SUGGEST_JOB_TYPE, session_id),
        ).fetchone()[0]


def test_the_turn_event_is_published_after_the_turn_commits_and_only_once(database) -> None:
    session, message_id = _session(), f"msg:{uuid.uuid4().hex}"
    publish = lambda: PostgresChatSessionStore._publish_turn_completed(_store(database), session, message_id)  # noqa: E731

    with unit_of_work(database) as work, share_transaction(work):
        after_commit(database, publish)
        before_commit = _events(database, session.id)
        work.commit()
    publish()

    assert before_commit == []
    assert _events(database, session.id) == [("chat.turn.completed", message_id)]


def test_redelivering_a_turn_event_queues_one_suggestion_job(database) -> None:
    session, message_id = _session(), f"msg:{uuid.uuid4().hex}"
    PostgresChatSessionStore._publish_turn_completed(_store(database), session, message_id)
    with database.connection() as connection:
        workspace_id, payload = connection.execute(
            "SELECT workspace_id, payload FROM omnix_outbox_events WHERE aggregate_id = %s", (session.id,),
        ).fetchone()
    event = {"workspace_id": workspace_id, "payload": dict(payload)}

    first = suggest_memories_after_turn(None, event)
    second = suggest_memories_after_turn(None, event)

    assert first == second and "job_id" in first
    assert _suggestion_jobs(database, session.id) == 1


def test_the_relay_delivers_the_event_and_a_character_session_without_memory_writes_queues_nothing(database) -> None:
    allowed, private = _session(), _session(interaction_mode="character", write_memory=False)
    for session in (allowed, private):
        PostgresChatSessionStore._publish_turn_completed(_store(database), session, f"msg:{uuid.uuid4().hex}")

    report = OutboxRelayWorker(database, OutboxConsumerRegistry(MEMORY_FEATURE.outbox_consumers)).run_once()

    assert report.deliveries.get("assistant-memory.turn-suggestions", 0) >= 2
    assert (_suggestion_jobs(database, allowed.id), _suggestion_jobs(database, private.id)) == (1, 0)
