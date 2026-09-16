from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.companion_activity.persistence import (
    PostgresCompanionActivityCheckpointStore,
    build_activity_checkpoint,
)
from app.companion_activity.state import (
    ActivityField,
    ActivityTransitionCandidate,
    empty_activity_state,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

NOW = datetime(2026, 9, 15, 11, 30, tzinfo=timezone.utc)


def database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=4,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-companion-activity-checkpoint-tests",
        )
    )


def test_postgres_checkpoint_round_trip_is_sensitive_and_drops_pending_jitter() -> None:
    db = database()
    try:
        apply_migrations(db)
        token = uuid4().hex
        state = empty_activity_state(
            activity_id=f"activity:{token}",
            session_id=f"chat:{token}",
            character_id="sofia",
            generation="generation:1",
            started_at=NOW,
        )
        objective = ActivityField(
            value="beat Malenia",
            authority_source="user_explicit",
            confidence=1.0,
            proposition_ids=(f"user:{token}",),
            stable_since=NOW,
            updated_at=NOW,
            revision=1,
            last_transition_reason="field_initialized:user_explicit",
        )
        pending = ActivityTransitionCandidate(
            field_name="strategy",
            value="bleed build",
            authority_source="single_perception",
            confidence=0.8,
            proposition_ids=(f"screen:{token}",),
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        state = state.model_copy(
            update={
                "revision": 1,
                "fields": {"current_objective": objective},
                "pending_transitions": (pending,),
            }
        )
        checkpoint = build_activity_checkpoint(
            state=state,
            reason="objective_established",
            created_at=NOW,
            source_proposition_ids=(f"user:{token}",),
        )
        store = PostgresCompanionActivityCheckpointStore(db)

        saved = store.save(checkpoint)
        loaded = store.latest(state.session_id, activity_id=state.activity_id)

        assert saved.checkpoint_id == checkpoint.checkpoint_id
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint.checkpoint_id
        assert loaded.sensitivity == "sensitive"
        assert loaded.state.field("current_objective").value == "beat Malenia"
        assert loaded.state.pending_transitions == ()
        assert loaded.source_proposition_ids == (f"user:{token}",)
    finally:
        db.close()
