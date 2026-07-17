from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.worlds.contracts import WorldReleaseDocument, WorldRevisionDocument
from app.rpg.worlds.progressive_materialization_job_service import (
    materialization_job_telemetry,
    schedule_campaign_predictive_materialization,
)
from app.rpg.worlds.progressive_materialization_worker import (
    run_materialization_worker_once,
)
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
    resolve_campaign_binding,
)
from app.rpg.worlds.starter_bubble_service import promote_starter_bubble

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-progressive-materialization-jobs",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_world_generation_runs, "
            "omnix_rpg_campaign_map_events, omnix_rpg_campaign_map_instances, "
            "omnix_rpg_map_definitions, omnix_rpg_campaign_world_bindings, "
            "omnix_rpg_scenario_revisions, omnix_rpg_scenarios, "
            "omnix_rpg_world_releases, omnix_rpg_world_revisions, "
            "omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_job_attempts, "
            "omnix_job_events, omnix_jobs, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def _seed_campaign(
    database: PostgresDatabase,
    *,
    world_id: str,
    campaign_id: str,
) -> None:
    context = bootstrap_local_tenant(database)
    source_revision = compile_world_revision(
        world_id=world_id,
        revision=1,
        title=f"World {world_id}",
        canon={"campaign_template": "classic_fantasy"},
        entity_manifest={"locations": ["location:harbor"]},
        topology={"locations": ["location:harbor"], "routes": []},
    )
    source_release = compile_world_release(
        source_revision,
        release=1,
        certification={"launch_ready": True, "missing_requirements": []},
    )
    with unit_of_work(database) as work:
        work.world_scenarios.create_world(
            context,
            world_id=world_id,
            title=f"World {world_id}",
            source_mode="hybrid",
            genre="classic_fantasy",
            tone="heroic adventure",
            metadata={"starting_location": "location:harbor"},
        )
        work.world_scenarios.publish_world_revision(
            context,
            world_id=world_id,
            document=source_revision.model_dump(mode="json"),
            content_hash=source_revision.content_hash,
            expected_revision=0,
        )
        work.world_scenarios.publish_world_release(
            context,
            world_id=world_id,
            world_revision=1,
            document=source_release.model_dump(mode="json"),
            release_hash=source_release.release_hash,
        )
        work.commit()
    promote_starter_bubble(
        world_id=world_id,
        source_world_revision=1,
        starting_location_id="location:harbor",
        neighboring_location_id="location:old-road",
        database=database,
    )
    with unit_of_work(database) as work:
        revision_row = work.world_scenarios.get_world_revision(context, world_id, 2)
        release_row = work.world_scenarios.get_world_release(context, world_id, 2, 1)
        work.rollback()
    assert revision_row is not None
    assert release_row is not None
    revision = WorldRevisionDocument.model_validate(revision_row["document"])
    release = WorldReleaseDocument.model_validate(release_row["document"])
    scenario_id = f"scenario:{campaign_id}"
    scenario = compile_scenario_revision(
        scenario_id=scenario_id,
        revision=1,
        world_revision=revision,
        compatible_release=release.release,
        starting_location_id="location:harbor",
    )
    binding = resolve_campaign_binding(
        campaign_id=campaign_id,
        world_revision=revision,
        world_release=release,
        scenario_revision=scenario,
    )
    with unit_of_work(database) as work:
        work.world_scenarios.create_scenario(
            context,
            scenario_id=scenario_id,
            world_id=world_id,
            title="Starter Scenario",
            metadata={},
        )
        work.world_scenarios.publish_scenario_revision(
            context,
            scenario_id=scenario_id,
            world_id=world_id,
            world_revision=2,
            document=scenario.model_dump(mode="json"),
            content_hash=scenario.content_hash,
        )
        work.rpg.create_campaign(
            context,
            campaign_id=campaign_id,
            title=campaign_id,
            state={},
            engine_version="test",
            schema_version="test",
            seed="1",
            metadata={},
        )
        work.world_scenarios.bind_campaign(
            context,
            campaign_id=campaign_id,
            world_id=binding.world_id,
            world_revision=binding.world_revision,
            world_release=binding.world_release,
            scenario_id=binding.scenario_id,
            scenario_revision=binding.scenario_revision,
            binding=binding.model_dump(mode="json"),
        )
        work.commit()


def test_predictive_jobs_are_idempotent_complete_and_report_telemetry() -> None:
    database = _database()
    try:
        _reset(database)
        _seed_campaign(
            database,
            world_id="world:materialization-success",
            campaign_id="campaign:materialization-success",
        )
        first = schedule_campaign_predictive_materialization(
            "campaign:materialization-success",
            current_location_id="location:harbor",
            route_intent_location_id="location:old-road:frontier",
            minimum_score=0.9,
            database=database,
            kick_worker=False,
        )
        repeated = schedule_campaign_predictive_materialization(
            "campaign:materialization-success",
            current_location_id="location:harbor",
            route_intent_location_id="location:old-road:frontier",
            minimum_score=0.9,
            database=database,
            kick_worker=False,
        )

        assert len(first["scheduled"]) == 1
        assert first["scheduled"][0]["created"] is True
        assert first["scheduled"][0]["priority"] == 95
        assert first["scheduled"][0]["trigger_reasons"] == ["route_intent"]
        assert repeated["scheduled"][0]["created"] is False
        assert repeated["scheduled"][0]["job_id"] == first["scheduled"][0]["job_id"]
        queued = materialization_job_telemetry(
            world_id="world:materialization-success",
            source_world_revision=2,
            database=database,
        )
        assert queued["counts"] == {"queued": 1}
        completed = run_materialization_worker_once(database=database)
        assert completed is not None and completed["ok"] is True
        assert completed["job"]["status"] == "completed"
        assert completed["result"]["materialization"]["world_revision"] == 3
        telemetry = materialization_job_telemetry(
            world_id="world:materialization-success",
            source_world_revision=2,
            database=database,
        )
        assert telemetry["counts"] == {"completed": 1}
        assert telemetry["attempts"] == 1
        assert telemetry["completed_location_ids"] == [
            "location:old-road:frontier"
        ]
    finally:
        database.close()


def test_materialization_worker_retries_then_dead_letters_terminal_failure() -> None:
    database = _database()
    try:
        _reset(database)
        _seed_campaign(
            database,
            world_id="world:materialization-failure",
            campaign_id="campaign:materialization-failure",
        )
        schedule_campaign_predictive_materialization(
            "campaign:materialization-failure",
            current_location_id="location:harbor",
            route_intent_location_id="location:old-road:frontier",
            minimum_score=0.9,
            database=database,
            kick_worker=False,
        )

        def fail_materialization(**_kwargs):
            raise RuntimeError("synthetic materialization failure")

        first = run_materialization_worker_once(
            database=database,
            materializer=fail_materialization,
            retry_delay_seconds=0,
        )
        second = run_materialization_worker_once(
            database=database,
            materializer=fail_materialization,
            retry_delay_seconds=0,
        )
        third = run_materialization_worker_once(
            database=database,
            materializer=fail_materialization,
            retry_delay_seconds=0,
        )
        assert first is not None and first["job"]["status"] == "retrying"
        assert second is not None and second["job"]["status"] == "retrying"
        assert third is not None and third["job"]["status"] == "failed"
        assert third["job"]["attempt_count"] == 3
        telemetry = materialization_job_telemetry(
            world_id="world:materialization-failure",
            source_world_revision=2,
            database=database,
        )
        assert telemetry["status"] == "failed"
        assert telemetry["counts"] == {"failed": 1}
        assert telemetry["attempts"] == 3
        assert telemetry["failed_location_ids"] == [
            "location:old-road:frontier"
        ]
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            attempts = work.connection.execute(
                "SELECT status FROM omnix_job_attempts ORDER BY attempt"
            ).fetchall()
            dead_letters = work.connection.execute(
                "SELECT reason FROM omnix_dead_letters"
            ).fetchall()
            work.rollback()
        assert [str(row[0]) for row in attempts] == [
            "retrying",
            "retrying",
            "failed",
        ]
        assert [str(row[0]) for row in dead_letters] == [
            "progressive_materialization_failed"
        ]
    finally:
        database.close()
