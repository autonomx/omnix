from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.execution_repositories import JobClaimConflict
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.apps.rpg.session.persistence.rpg_turn_service import persist_foreground_turn
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
            application_name="omnix-foreground-turn-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_legacy_import_items, omnix_legacy_import_runs, "
            "omnix_runtime_projections, omnix_module_records, omnix_reports, "
            "omnix_research_records, omnix_prompt_templates, "
            "omnix_provider_status_projections, omnix_provider_configs, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, "
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
        connection.execute(
            "UPDATE omnix_persistence_cutover "
            "SET mode = 'postgresql', authority_state = 'postgresql_stabilized', "
            "updated_at = CURRENT_TIMESTAMP WHERE singleton = TRUE"
        )


def _initial_session(campaign_id: str) -> dict:
    return {
        "manifest": {"session_id": campaign_id, "title": "Atomic campaign", "turn_count": 0},
        "state": {"scene": {"location_name": "The Rusty Flagon"}},
        "runtime_state": {"state_revision": 0, "interaction_seq": 0},
    }


def _next_session(campaign_id: str) -> dict:
    return {
        "manifest": {"session_id": campaign_id, "title": "Atomic campaign", "turn_count": 1},
        "state": {"scene": {"location_name": "The Rusty Flagon"}, "gold": 1},
        "runtime_state": {
            "state_revision": 1,
            "interaction_seq": 1,
            "interaction_timeline": {"last_sequence": 1, "state_revision": 1},
        },
    }


def _event(submission_id: str) -> dict:
    return {
        "format_version": "rpg_interaction_timeline_v1",
        "interaction_id": "interaction:1",
        "sequence": 1,
        "state_revision": 1,
        "submission_id": submission_id,
        "stateful": True,
        "player_input": "I buy a ration.",
        "visible_response": {"plain_text": "You buy a ration."},
    }


def _prepare(database: PostgresDatabase, *, campaign_id: str, submission_id: str) -> dict:
    """A campaign, and its submission claimed and started as the turn route claims it (F2: no job behind it)."""
    context = ensure_local_identity(database)
    with unit_of_work(database) as work:
        work.rpg.create_campaign(
            context,
            campaign_id=campaign_id,
            title="Atomic campaign",
            state=_initial_session(campaign_id),
            engine_version="test-engine",
            schema_version="test-schema",
            seed="seed",
        )
        claim = work.foreground_submissions.claim(
            context,
            session_id=campaign_id,
            submission_id=submission_id,
            lease_seconds=300,
        )
        assert claim["owner"] is True
        assert work.foreground_submissions.start_execution(
            context,
            session_id=campaign_id,
            submission_id=submission_id,
            claim_token=str(claim["claim_token"]),
        )
        work.commit()
    return {"submission_claim_token": claim["claim_token"]}


def test_foreground_turn_commits_every_authoritative_record_together() -> None:
    database = _database()
    campaign_id = "campaign:atomic"
    submission_id = "submission:atomic"
    try:
        _reset(database)
        credentials = _prepare(database, campaign_id=campaign_id, submission_id=submission_id)
        persisted = persist_foreground_turn(
            **credentials,
            database=database,
            session_id=campaign_id,
            player_input="I buy a ration.",
            session=_next_session(campaign_id),
            result={
                "ok": True,
                "narration": "You buy a ration.",
                "canonical_effects": {"gold_delta": -1, "item_added": "ration"},
            },
            event=_event(submission_id),
            submission_id=submission_id,
        )
        assert persisted["transaction"] == "postgresql_unit_of_work"

        with database.connection() as connection:
            row = connection.execute(
                "SELECT revision FROM omnix_rpg_campaigns WHERE id = %s",
                (campaign_id,),
            ).fetchone()
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM omnix_rpg_turns WHERE campaign_id = %s), "
                "(SELECT COUNT(*) FROM omnix_rpg_interactions WHERE campaign_id = %s), "
                "(SELECT COUNT(*) FROM omnix_rpg_snapshots WHERE campaign_id = %s), "
                "(SELECT COUNT(*) FROM omnix_outbox_events WHERE aggregate_id = %s) ",
                (campaign_id, campaign_id, campaign_id, campaign_id),
            ).fetchone()
            jobs = connection.execute("SELECT COUNT(*) FROM omnix_jobs").fetchone()[0]
            submission = connection.execute(
                "SELECT status, interaction_id, response FROM omnix_rpg_foreground_submissions "
                "WHERE session_id = %s AND submission_id = %s",
                (campaign_id, submission_id),
            ).fetchone()
        assert int(row[0]) == 1
        # Revision 1 writes no full snapshot: one is due every OMNIX_RPG_SNAPSHOT_EVERY revisions (WP-5.6).
        assert tuple(int(value) for value in counts[:3]) == (1, 1, 0)
        assert int(counts[3]) == 0  # RPG events have no outbox consumer (WP-5.3)
        assert int(jobs) == 0  # a foreground turn writes no job (F2)
        assert str(submission[0]) == "completed"
        assert str(submission[1]) == f"interaction:{campaign_id}:1"
        assert dict(submission[2])["interaction_id"] == "interaction:1"
    finally:
        database.close()


@pytest.mark.parametrize("supplied_claim", [None, "wrong-claim"])
def test_foreground_transaction_cannot_borrow_an_existing_claim(supplied_claim) -> None:
    database = _database()
    campaign_id, submission_id = "campaign:claim-fence", "submission:claim-fence"
    try:
        _reset(database)
        _prepare(database, campaign_id=campaign_id, submission_id=submission_id)
        with pytest.raises(JobClaimConflict, match="original claim"):
            persist_foreground_turn(
                database=database, session_id=campaign_id, player_input="I buy a ration.",
                session=_next_session(campaign_id), result={"ok": True},
                event=_event(submission_id), submission_id=submission_id,
                submission_claim_token=supplied_claim,
            )
        with database.connection() as connection:
            assert connection.execute("SELECT revision FROM omnix_rpg_campaigns WHERE id = %s", (campaign_id,)).fetchone()[0] == 0
            assert connection.execute(
                "SELECT status FROM omnix_rpg_foreground_submissions WHERE submission_id = %s", (submission_id,)
            ).fetchone()[0] == "claimed"
            assert connection.execute("SELECT COUNT(*) FROM omnix_rpg_turns WHERE campaign_id = %s", (campaign_id,)).fetchone()[0] == 0
    finally:
        database.close()


def test_foreground_turn_carries_its_claim_through_the_atomic_commit_and_replays(monkeypatch) -> None:
    from app.apps.rpg.foundation.persistence.foreground_submissions import PostgresForegroundSubmissionStoreAdapter
    from app.apps.rpg.session.jobs.foreground_context import current_foreground_claim
    from app.apps.rpg.session.jobs.foreground_turn import execute_foreground_turn

    database = _database()
    campaign_id, submission_id = "campaign:foreground", "submission:foreground"
    try:
        _reset(database)
        from app.persistence.startup import bootstrap_postgresql_runtime

        bootstrap_postgresql_runtime(database)
        context = ensure_local_identity(database)
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context, campaign_id=campaign_id, title="Scoped foreground",
                state=_initial_session(campaign_id), engine_version="test-engine",
                schema_version="test-schema", seed="seed",
            )
            work.commit()
        submissions = PostgresForegroundSubmissionStoreAdapter(database)
        calls = []

        def apply_turn(session_id, command):
            claim = current_foreground_claim()
            assert claim is not None and claim.submission_id == submission_id
            calls.append(claim)
            result = {"ok": True, "narration": "You buy a ration."}
            persist_foreground_turn(
                database=database, session_id=session_id, player_input=command,
                session=_next_session(session_id), result=result, event=_event(submission_id),
                submission_id=submission_id, submission_claim_token=claim.claim_token,
            )
            claim.mark_committed()
            return result

        result = execute_foreground_turn(apply_turn, campaign_id, "I buy a ration.", submission_id=submission_id,
                                         submissions=submissions)
        replay = execute_foreground_turn(apply_turn, campaign_id, "I buy a ration.", submission_id=submission_id,
                                         submissions=submissions)
        assert result["ok"] is True
        assert replay["idempotent_replay"] is True
        assert len(calls) == 1
        assert current_foreground_claim() is None
        with database.connection() as connection:
            assert connection.execute("SELECT COUNT(*) FROM omnix_jobs").fetchone()[0] == 0
            assert connection.execute(
                "SELECT status FROM omnix_rpg_foreground_submissions WHERE submission_id = %s", (submission_id,)
            ).fetchone()[0] == "completed"
    finally:
        database.close()
