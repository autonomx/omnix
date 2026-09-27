from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.execution_repositories import JobClaimConflict
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.rpg.persistence.rpg_turn_service import persist_foreground_turn
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


def _prepare(
    database: PostgresDatabase,
    *,
    campaign_id: str,
    submission_id: str,
    lease_job: bool,
    record_only: bool = False,
) -> tuple[str, dict]:
    context = bootstrap_local_tenant(database)
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
        job = work.jobs.create_job(
            context,
            {
                "id": f"job:{campaign_id}",
                "module": "rpg",
                "job_type": "rpg.turn.foreground_record" if record_only else "rpg.turn",
                "resource_class": "cpu",
                "input_payload": {"submission_id": submission_id},
                "metadata": {
                    "compat_contract": {
                        "input_ref": {"session_id": campaign_id},
                        "compat": {"record_only": record_only},
                    }
                },
            },
        )
        credentials = {}
        if lease_job:
            leased = work.jobs.claim_next(
                context,
                worker_id="worker:test",
                resource_classes=["cpu"],
                lease_seconds=300,
            )
            assert leased is not None
            credentials = {"worker_id": leased["lease_owner"], "lease_token": leased["lease_token"]}
            work.jobs.mark_running(
                context,
                job_id=job["id"],
                worker_id=str(leased["lease_owner"]),
                lease_token=str(leased["lease_token"]),
            )
        claim = work.foreground_submissions.claim(
            context,
            session_id=campaign_id,
            submission_id=submission_id,
            lease_seconds=300,
        )
        assert claim["owner"] is True
        assert work.foreground_submissions.attach_job(
            context,
            session_id=campaign_id,
            submission_id=submission_id,
            claim_token=str(claim["claim_token"]),
            job_id=job["id"],
        )
        assert work.foreground_submissions.start_execution(
            context,
            session_id=campaign_id,
            submission_id=submission_id,
            claim_token=str(claim["claim_token"]),
        )
        work.commit()
    return job["id"], {"submission_claim_token": claim["claim_token"], **credentials}


def test_foreground_turn_commits_every_authoritative_record_together() -> None:
    database = _database()
    campaign_id = "campaign:atomic"
    submission_id = "submission:atomic"
    try:
        _reset(database)
        job_id, credentials = _prepare(
            database,
            campaign_id=campaign_id,
            submission_id=submission_id,
            lease_job=True,
        )
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
            job = connection.execute(
                "SELECT status FROM omnix_jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
            submission = connection.execute(
                "SELECT status, interaction_id, response FROM omnix_rpg_foreground_submissions "
                "WHERE session_id = %s AND submission_id = %s",
                (campaign_id, submission_id),
            ).fetchone()
        assert int(row[0]) == 1
        assert tuple(int(value) for value in counts[:3]) == (1, 1, 1)
        assert int(counts[3]) >= 2
        assert str(job[0]) == "completed"
        assert str(submission[0]) == "completed"
        assert str(submission[1]) == f"interaction:{campaign_id}:1"
        assert dict(submission[2])["interaction_id"] == "interaction:1"
    finally:
        database.close()


def test_job_completion_failure_rolls_back_turn_campaign_and_outbox() -> None:
    database = _database()
    campaign_id = "campaign:rollback"
    submission_id = "submission:rollback"
    try:
        _reset(database)
        job_id, credentials = _prepare(
            database,
            campaign_id=campaign_id,
            submission_id=submission_id,
            lease_job=False,
        )
        with pytest.raises(RuntimeError, match="no active lease"):
            persist_foreground_turn(
                **credentials,
                database=database,
                session_id=campaign_id,
                player_input="I buy a ration.",
                session=_next_session(campaign_id),
                result={"ok": True, "narration": "You buy a ration."},
                event=_event(submission_id),
                submission_id=submission_id,
            )

        with database.connection() as connection:
            campaign = connection.execute(
                "SELECT revision FROM omnix_rpg_campaigns WHERE id = %s",
                (campaign_id,),
            ).fetchone()
            turn_count = connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_turns WHERE campaign_id = %s",
                (campaign_id,),
            ).fetchone()[0]
            interaction_count = connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_interactions WHERE campaign_id = %s",
                (campaign_id,),
            ).fetchone()[0]
            job = connection.execute(
                "SELECT status FROM omnix_jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
            submission = connection.execute(
                "SELECT status FROM omnix_rpg_foreground_submissions "
                "WHERE session_id = %s AND submission_id = %s",
                (campaign_id, submission_id),
            ).fetchone()
        assert int(campaign[0]) == 0
        assert int(turn_count) == 0
        assert int(interaction_count) == 0
        assert str(job[0]) == "queued"
        assert str(submission[0]) == "claimed"
    finally:
        database.close()


def test_record_only_foreground_turn_commits_without_worker_lease() -> None:
    database = _database()
    campaign_id = "campaign:record-only"
    submission_id = "submission:record-only"
    try:
        _reset(database)
        job_id, credentials = _prepare(
            database,
            campaign_id=campaign_id,
            submission_id=submission_id,
            lease_job=False,
            record_only=True,
        )

        persisted = persist_foreground_turn(
            **credentials,
            database=database,
            session_id=campaign_id,
            player_input="I buy a ration.",
            session=_next_session(campaign_id),
            result={"ok": True, "narration": "You buy a ration."},
            event=_event(submission_id),
            submission_id=submission_id,
        )

        assert persisted["transaction"] == "postgresql_unit_of_work"
        assert persisted["turn"]["id"] == f"turn:{campaign_id}:1"
        assert persisted["interaction_record_id"] == f"interaction:{campaign_id}:1"
        with database.connection() as connection:
            job = connection.execute(
                "SELECT status, lease_token FROM omnix_jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
            revision = connection.execute(
                "SELECT revision FROM omnix_rpg_campaigns WHERE id = %s",
                (campaign_id,),
            ).fetchone()[0]
        assert str(job[0]) == "completed"
        assert job[1] is None
        assert int(revision) == 1
    finally:
        database.close()


@pytest.mark.parametrize("supplied_claim", [None, "wrong-claim"])
def test_foreground_transaction_cannot_borrow_an_existing_claim(supplied_claim) -> None:
    database = _database()
    campaign_id, submission_id = "campaign:claim-fence", "submission:claim-fence"
    try:
        _reset(database)
        job_id, _ = _prepare(database, campaign_id=campaign_id, submission_id=submission_id,
                             lease_job=False, record_only=True)
        with pytest.raises(JobClaimConflict, match="original claim"):
            persist_foreground_turn(
                database=database, session_id=campaign_id, player_input="I buy a ration.",
                session=_next_session(campaign_id), result={"ok": True},
                event=_event(submission_id), submission_id=submission_id,
                submission_claim_token=supplied_claim,
            )
        with database.connection() as connection:
            assert connection.execute("SELECT revision FROM omnix_rpg_campaigns WHERE id = %s", (campaign_id,)).fetchone()[0] == 0
            assert connection.execute("SELECT status FROM omnix_jobs WHERE id = %s", (job_id,)).fetchone()[0] == "queued"
            assert connection.execute("SELECT COUNT(*) FROM omnix_rpg_turns WHERE campaign_id = %s", (campaign_id,)).fetchone()[0] == 0
    finally:
        database.close()


@pytest.mark.parametrize("supplied_lease", [None, "stale-token"])
def test_foreground_transaction_cannot_borrow_a_workers_current_lease(supplied_lease) -> None:
    database = _database()
    campaign_id, submission_id = "campaign:worker-fence", "submission:worker-fence"
    try:
        _reset(database)
        job_id, credentials = _prepare(database, campaign_id=campaign_id,
                                       submission_id=submission_id, lease_job=True)
        credentials["lease_token"] = supplied_lease
        with pytest.raises((JobClaimConflict, RuntimeError)):
            persist_foreground_turn(
                **credentials, database=database, session_id=campaign_id,
                player_input="I buy a ration.", session=_next_session(campaign_id),
                result={"ok": True}, event=_event(submission_id), submission_id=submission_id,
            )
        with database.connection() as connection:
            assert connection.execute("SELECT revision FROM omnix_rpg_campaigns WHERE id = %s", (campaign_id,)).fetchone()[0] == 0
            assert connection.execute("SELECT status FROM omnix_jobs WHERE id = %s", (job_id,)).fetchone()[0] == "running"
            assert connection.execute("SELECT COUNT(*) FROM omnix_rpg_turns WHERE campaign_id = %s", (campaign_id,)).fetchone()[0] == 0
    finally:
        database.close()


def test_foreground_mirror_carries_original_claim_through_atomic_turn_and_replay(monkeypatch) -> None:
    from app.gateway.rpg_turn_job_mirror import _apply_turn_with_job_mirror
    from app.jobs.foreground_execution import current_foreground_execution
    from app.jobs import store as stores
    from app.persistence.job_runtime_compat import PostgresJobStoreAdapter

    database = _database()
    campaign_id, submission_id = "campaign:mirrored", "submission:mirrored"
    try:
        _reset(database)
        store = PostgresJobStoreAdapter(database)
        monkeypatch.setattr(stores, "default_job_store", lambda: store)
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                store.context, campaign_id=campaign_id, title="Scoped foreground",
                state=_initial_session(campaign_id), engine_version="test-engine",
                schema_version="test-schema", seed="seed",
            )
            work.commit()
        calls = []

        def apply_turn(session_id, command):
            execution = current_foreground_execution()
            assert execution is not None
            calls.append(execution)
            result = {"ok": True, "narration": "You buy a ration."}
            transaction = persist_foreground_turn(
                database=database, session_id=session_id, player_input=command,
                session=_next_session(session_id), result=result, event=_event(submission_id),
                submission_id=submission_id, submission_claim_token=execution.claim_token,
            )
            assert transaction["job"]["status"] == "completed"
            return result

        result = _apply_turn_with_job_mirror(
            apply_turn, campaign_id, "I buy a ration.", submission_id=submission_id,
        )
        replay = _apply_turn_with_job_mirror(
            apply_turn, campaign_id, "I buy a ration.", submission_id=submission_id,
        )
        assert result["ok"] is True
        assert replay["idempotent_replay"] is True
        assert len(calls) == 1
        assert current_foreground_execution() is None
        jobs = store.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].status.value == "completed"
        assert jobs[0].lease is None
    finally:
        database.close()
