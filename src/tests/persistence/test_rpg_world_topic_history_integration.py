from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.worlds.contracts import WorldProjectCreate
from app.rpg.worlds.generation_coordinator import start_world_generation
from app.rpg.worlds.generation_jobs import (
    WorldTopicGenerationSettings,
    canonical_hash,
)
from app.rpg.worlds.postgres_service import create_world_project
from app.rpg.worlds.topic_history import (
    list_world_topic_history,
    restore_world_topic_draft,
)

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
            application_name="omnix-rpg-world-topic-history",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_world_topic_history, "
            "omnix_rpg_world_generation_runs, omnix_rpg_campaign_map_events, "
            "omnix_rpg_campaign_map_instances, omnix_rpg_map_definitions, "
            "omnix_rpg_campaign_world_bindings, omnix_rpg_scenario_revisions, "
            "omnix_rpg_scenarios, omnix_rpg_world_releases, "
            "omnix_rpg_world_revisions, omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_job_attempts, "
            "omnix_job_events, omnix_jobs, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def _graph() -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="topic-history-test-v1",
        campaign_template="classic_fantasy",
        depth="quick",
        nodes=(
            CampaignTopicNode(
                topic_id="realm",
                title="Realm",
                category="lore",
                generator_role="realm_architect",
            ),
        ),
    )


def _settings() -> WorldTopicGenerationSettings:
    return WorldTopicGenerationSettings(
        generator_version="history-test-v1",
        prompt_version="history-test-v1",
        provider_route="deterministic",
        model="deterministic",
        seed=31,
    )


def _put_topic(
    database: PostgresDatabase,
    *,
    world_id: str,
    draft_revision: int,
    label: str,
) -> dict:
    context = bootstrap_local_tenant(database)
    content = {
        "topic_id": "realm",
        "documents": [],
        "entities": [],
        "facts": [],
        "label": label,
    }
    with unit_of_work(database) as work:
        stored = work.world_scenarios.put_topic(
            context,
            world_id=world_id,
            topic_id="realm",
            draft_revision=draft_revision,
            source="manual",
            status="ready",
            content=content,
            directives={"direction": label},
            dependency_hashes={},
            input_hash=canonical_hash({"label": label}),
            content_hash=canonical_hash(content),
            provenance={"author": "integration-test", "label": label},
        )
        work.commit()
    return stored


def _finish_run(
    database: PostgresDatabase,
    run_id: str,
) -> dict:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        completed = work.world_generation.update(
            context,
            run_id=run_id,
            status="ready",
            progress={"generation_complete": True, "percent": 100},
        )
        work.commit()
    return completed


def test_topic_drafts_are_preserved_restorable_and_link_generation_runs() -> None:
    database = _database()
    try:
        _reset(database)
        world_id = "world:topic-history"
        create_world_project(
            WorldProjectCreate(world_id=world_id, title="Topic History World"),
            database=database,
        )
        original = _put_topic(
            database,
            world_id=world_id,
            draft_revision=1,
            label="original",
        )
        run1 = start_world_generation(
            world_id=world_id,
            draft_revision=1,
            graph=_graph(),
            generation_context={"label": "original"},
            topic_directives={},
            entity_manifest_hash="sha256:manifest-1",
            settings=_settings(),
            database=database,
        )
        run1 = _finish_run(database, run1["run_id"])
        assert run1["parent_run_id"] is None
        assert run1["lineage"]["root_run_id"] == run1["run_id"]

        restored2 = restore_world_topic_draft(
            world_id,
            source_draft_revision=1,
            expected_current_draft_revision=1,
            database=database,
        )
        assert restored2["restored_draft_revision"] == 2
        assert restored2["topics"][0]["content"] == original["content"]
        changed = _put_topic(
            database,
            world_id=world_id,
            draft_revision=2,
            label="changed",
        )
        run2 = start_world_generation(
            world_id=world_id,
            draft_revision=2,
            graph=_graph(),
            generation_context={"label": "changed"},
            topic_directives={},
            entity_manifest_hash="sha256:manifest-2",
            settings=_settings(),
            database=database,
        )
        run2 = _finish_run(database, run2["run_id"])
        assert run2["parent_run_id"] == run1["run_id"]
        assert run2["lineage"] == {
            "root_run_id": run1["run_id"],
            "parent_run_id": run1["run_id"],
            "parent_draft_revision": 1,
            "draft_revision": 2,
        }

        restored3 = restore_world_topic_draft(
            world_id,
            source_draft_revision=1,
            expected_current_draft_revision=2,
            database=database,
        )
        assert restored3["restored_draft_revision"] == 3
        assert restored3["topics"][0]["content"]["label"] == "original"
        assert restored3["topics"][0]["provenance"]["draft_restore"] == {
            "source_draft_revision": 1,
            "source_history_sequence": 1,
            "target_draft_revision": 3,
        }
        run3 = start_world_generation(
            world_id=world_id,
            draft_revision=3,
            graph=_graph(),
            generation_context={"label": "restored"},
            topic_directives={},
            entity_manifest_hash="sha256:manifest-1",
            settings=_settings(),
            database=database,
        )
        assert run3["parent_run_id"] == run2["run_id"]
        assert run3["lineage"]["root_run_id"] == run1["run_id"]
        assert run3["lineage"]["parent_draft_revision"] == 2

        history1 = list_world_topic_history(
            world_id,
            draft_revision=1,
            latest_per_topic=True,
            database=database,
        )
        history2 = list_world_topic_history(
            world_id,
            draft_revision=2,
            latest_per_topic=True,
            database=database,
        )
        history3 = list_world_topic_history(
            world_id,
            draft_revision=3,
            latest_per_topic=True,
            database=database,
        )
        assert history1[0]["content"]["label"] == "original"
        assert history2[0]["content"]["label"] == "changed"
        assert history2[0]["content_hash"] == changed["content_hash"]
        assert history3[0]["content"]["label"] == "original"

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            current_world = work.world_scenarios.get_world(context, world_id)
            current_topics = work.world_generation.list_topics(
                context,
                world_id=world_id,
                draft_revision=3,
            )
            runs = work.world_library.list_generation_runs(
                context,
                world_id=world_id,
            )
            work.rollback()
        assert current_world is not None
        assert current_world["draft_revision"] == 3
        assert current_topics[0]["content"]["label"] == "original"
        assert [run["draft_revision"] for run in runs] == [3, 2, 1]
        assert runs[0]["parent_run_id"] == run2["run_id"]
    finally:
        database.close()
