from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.errors import RevisionConflict
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.rpg_repository import (
    CompactTurnResponseTooLarge,
    StateHashConflict,
    state_hash,
)
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=8,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-persistence-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_participants, omnix_rpg_snapshots, "
            "omnix_rpg_interactions, omnix_rpg_turns, omnix_rpg_campaigns, "
            "omnix_rpg_foreground_submissions, omnix_outbox_events, "
            "omnix_dead_letters, omnix_job_events, omnix_job_attempts, omnix_jobs, "
            "omnix_chat_messages, omnix_chat_sessions, omnix_memory_snapshot_items, "
            "omnix_memory_snapshots, omnix_memory_candidates, omnix_memory_events, "
            "omnix_memory_records, omnix_conversation_segments, "
            "omnix_character_versions, omnix_characters, omnix_asset_versions, "
            "omnix_assets, omnix_settings, omnix_secret_references, "
            "omnix_audit_events, omnix_idempotency_keys, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def _initial_state() -> dict:
    return {
        "manifest": {"turn_count": 0},
        "state": {
            "scene": {"location_name": "The Rusty Flagon"},
            "player": {"level": 1, "hp": 10, "inventory": []},
        },
        "runtime_state": {"interaction_seq": 0, "state_revision": 0},
    }


def _next_state(turn_count: int) -> dict:
    return {
        "manifest": {"turn_count": turn_count},
        "state": {
            "scene": {"location_name": "The Rusty Flagon"},
            "player": {
                "level": 1,
                "hp": 10,
                "inventory": ["ration"] if turn_count else [],
            },
        },
        "runtime_state": {
            "interaction_seq": turn_count,
            "state_revision": turn_count,
        },
    }


def _create_campaign(work, context):
    return work.rpg.create_campaign(
        context,
        campaign_id="campaign:rusty-flagon",
        title="Rusty Flagon",
        state=_initial_state(),
        engine_version="rpg-engine-test",
        schema_version="rpg-session-v1",
        seed="seed:fixed",
    )


def test_campaign_creation_hash_and_participant() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            campaign = _create_campaign(work, context)
            work.commit()
        assert campaign["revision"] == 0
        assert campaign["state_hash"] == state_hash(_initial_state())
        with database.connection() as connection:
            participant = connection.execute(
                "SELECT role, permissions FROM omnix_rpg_participants "
                "WHERE campaign_id = 'campaign:rusty-flagon' AND user_id = %s",
                (context.user_id,),
            ).fetchone()
            outbox_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_outbox_events "
                    "WHERE event_type = 'rpg.campaign_created'"
                ).fetchone()[0]
            )
        assert participant[0] == "owner"
        assert set(participant[1]) == {"read", "write", "admin"}
        assert outbox_count == 1
    finally:
        database.close()


def test_turn_commit_is_atomic_revisioned_hashed_and_snapshot_backed() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_campaign(work, context)
            work.commit()

        next_state = _next_state(1)
        with unit_of_work(database) as work:
            result = work.rpg.commit_turn(
                context,
                campaign_id="campaign:rusty-flagon",
                turn_id="turn:1",
                submission_id="submission:1",
                interaction_id="interaction:1",
                expected_revision=0,
                command={"text": "I buy a ration."},
                next_state=next_state,
                canonical_effects={"inventory_added": ["ration"]},
                interaction_event={
                    "sequence": 1,
                    "interaction_id": "interaction:1",
                    "state_revision": 1,
                    "speaker": "Bran",
                },
                compact_response={
                    "ok": True,
                    "contract_version": "rpg_turn_response_v2",
                    "interaction_id": "interaction:1",
                    "response": "Bran: One ration, packed and ready.",
                },
                engine_version="rpg-engine-test",
                schema_version="rpg-session-v1",
                create_snapshot=True,
                snapshot_id="snapshot:1",
            )
            work.commit()

        assert result["idempotent_replay"] is False
        assert result["campaign"]["revision"] == 1
        assert result["campaign"]["state"] == next_state
        assert result["campaign"]["state_hash"] == state_hash(next_state)
        assert result["turn"]["state_hash_before"] == state_hash(_initial_state())
        assert result["turn"]["state_hash_after"] == state_hash(next_state)
        assert result["snapshot"]["revision"] == 1
        assert result["snapshot"]["state_hash"] == state_hash(next_state)

        with database.connection() as connection:
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM omnix_rpg_turns), "
                "(SELECT COUNT(*) FROM omnix_rpg_interactions), "
                "(SELECT COUNT(*) FROM omnix_rpg_snapshots), "
                "(SELECT COUNT(*) FROM omnix_outbox_events "
                " WHERE event_type = 'rpg.turn_committed')"
            ).fetchone()
        assert tuple(int(value) for value in counts) == (1, 1, 1, 1)
    finally:
        database.close()


def test_same_submission_returns_exact_committed_turn_without_second_effect() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_campaign(work, context)
            first = work.rpg.commit_turn(
                context,
                campaign_id="campaign:rusty-flagon",
                turn_id="turn:1",
                submission_id="submission:repeat",
                interaction_id="interaction:1",
                expected_revision=0,
                command={"text": "I ask Bran about business."},
                next_state=_next_state(1),
                canonical_effects={},
                interaction_event={"sequence": 1, "interaction_id": "interaction:1"},
                compact_response={"ok": True, "interaction_id": "interaction:1"},
                engine_version="rpg-engine-test",
                schema_version="rpg-session-v1",
            )
            work.commit()

        with unit_of_work(database) as work:
            replay = work.rpg.commit_turn(
                context,
                campaign_id="campaign:rusty-flagon",
                turn_id="turn:should-not-exist",
                submission_id="submission:repeat",
                interaction_id="interaction:should-not-exist",
                expected_revision=0,
                command={"text": "different ignored retry payload"},
                next_state=_next_state(99),
                canonical_effects={"should_not_apply": True},
                interaction_event={"sequence": 99},
                compact_response={"ok": False},
                engine_version="different",
                schema_version="different",
            )
            work.rollback()

        assert replay["idempotent_replay"] is True
        assert replay["turn"] == first["turn"]
        assert replay["campaign"]["revision"] == 1
        with database.connection() as connection:
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM omnix_rpg_turns), "
                "(SELECT COUNT(*) FROM omnix_rpg_interactions), "
                "(SELECT COUNT(*) FROM omnix_outbox_events "
                " WHERE event_type = 'rpg.turn_committed')"
            ).fetchone()
        assert tuple(int(value) for value in counts) == (1, 1, 1)
    finally:
        database.close()


def test_stale_revision_cannot_overwrite_campaign() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_campaign(work, context)
            work.rpg.commit_turn(
                context,
                campaign_id="campaign:rusty-flagon",
                turn_id="turn:1",
                submission_id="submission:1",
                interaction_id="interaction:1",
                expected_revision=0,
                command={"text": "First"},
                next_state=_next_state(1),
                canonical_effects={},
                interaction_event={"sequence": 1},
                compact_response={"ok": True},
                engine_version="rpg-engine-test",
                schema_version="rpg-session-v1",
            )
            work.commit()

        with unit_of_work(database) as work:
            with pytest.raises(RevisionConflict):
                work.rpg.commit_turn(
                    context,
                    campaign_id="campaign:rusty-flagon",
                    turn_id="turn:stale",
                    submission_id="submission:stale",
                    interaction_id="interaction:stale",
                    expected_revision=0,
                    command={"text": "Stale"},
                    next_state=_next_state(2),
                    canonical_effects={},
                    interaction_event={"sequence": 2},
                    compact_response={"ok": True},
                    engine_version="rpg-engine-test",
                    schema_version="rpg-session-v1",
                )
            work.rollback()
        with unit_of_work(database) as work:
            campaign = work.rpg.get_campaign(context, "campaign:rusty-flagon")
            work.rollback()
        assert campaign is not None
        assert campaign["revision"] == 1
        assert campaign["state"] == _next_state(1)
    finally:
        database.close()


def test_turn_transaction_rolls_back_ledger_state_interaction_and_outbox() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_campaign(work, context)
            work.commit()

        with pytest.raises(RuntimeError, match="abort after turn"):
            with unit_of_work(database) as work:
                work.rpg.commit_turn(
                    context,
                    campaign_id="campaign:rusty-flagon",
                    turn_id="turn:rollback",
                    submission_id="submission:rollback",
                    interaction_id="interaction:rollback",
                    expected_revision=0,
                    command={"text": "Rollback"},
                    next_state=_next_state(1),
                    canonical_effects={"rollback": True},
                    interaction_event={"sequence": 1},
                    compact_response={"ok": True},
                    engine_version="rpg-engine-test",
                    schema_version="rpg-session-v1",
                )
                raise RuntimeError("abort after turn")

        with unit_of_work(database) as work:
            campaign = work.rpg.get_campaign(context, "campaign:rusty-flagon")
            turn = work.rpg.get_turn_by_submission(
                context, "campaign:rusty-flagon", "submission:rollback"
            )
            work.rollback()
        assert campaign is not None and campaign["revision"] == 0
        assert turn is None
        with database.connection() as connection:
            interactions = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_rpg_interactions"
                ).fetchone()[0]
            )
            turn_events = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_outbox_events "
                    "WHERE event_type = 'rpg.turn_committed'"
                ).fetchone()[0]
            )
        assert interactions == 0
        assert turn_events == 0
    finally:
        database.close()


def test_compact_replay_record_has_hard_size_ceiling() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_campaign(work, context)
            with pytest.raises(CompactTurnResponseTooLarge):
                work.rpg.commit_turn(
                    context,
                    campaign_id="campaign:rusty-flagon",
                    turn_id="turn:large",
                    submission_id="submission:large",
                    interaction_id="interaction:large",
                    expected_revision=0,
                    command={"text": "Large"},
                    next_state=_next_state(1),
                    canonical_effects={},
                    interaction_event={"sequence": 1},
                    compact_response={"response": "x" * 20_001},
                    engine_version="rpg-engine-test",
                    schema_version="rpg-session-v1",
                )
            work.rollback()
    finally:
        database.close()


def test_snapshot_rejects_mismatched_state_hash() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            _create_campaign(work, context)
            with pytest.raises(StateHashConflict):
                work.rpg.create_snapshot(
                    context,
                    campaign_id="campaign:rusty-flagon",
                    snapshot_id="snapshot:bad",
                    revision=0,
                    state=_initial_state(),
                    state_hash_value="0" * 64,
                    engine_version="rpg-engine-test",
                    schema_version="rpg-session-v1",
                )
            work.rollback()
    finally:
        database.close()
