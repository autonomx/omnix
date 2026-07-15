from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.narrative_delivery import (
    PostgresNarrativeDeliveryRepositoryAdapter,
)
from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBlock,
    NarrativeDeliveryCoordinator,
    ValidationReport,
)
from app.rpg.narrative_repository import (
    PostgresNarrativeResponseRepositoryAdapter,
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
            application_name="omnix-rpg-narrative-delivery-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_narrative_deliveries, "
            "omnix_rpg_narrative_responses, omnix_rpg_hermes_research, "
            "omnix_rpg_world_forge_proposals, omnix_rpg_campaign_bible_revisions, "
            "omnix_rpg_campaign_bibles, omnix_rpg_participants, omnix_rpg_snapshots, "
            "omnix_rpg_interactions, omnix_rpg_turns, omnix_rpg_campaigns, "
            "omnix_outbox_events, omnix_audit_events, omnix_workspace_memberships, "
            "omnix_workspaces, omnix_users CASCADE"
        )


def _response(suffix: str) -> CanonicalNarrativeResponse:
    response_id = f"response:phase40:{suffix}"
    return CanonicalNarrativeResponse(
        response_id=response_id,
        request_id=f"request:phase40:{suffix}",
        turn_id=f"turn:phase40:{suffix}",
        campaign_id="campaign:phase40:integration",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id=f"{response_id}:one",
                beat_id="beat:one",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.PHYSICAL_REACTION,
                text="The rain ticks against the shutters.",
            ),
            NarrativeBlock(
                block_id=f"{response_id}:two",
                beat_id="beat:two",
                sequence=2,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="The bridge remains open.",
                speaker_id="npc:bran",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="phase40-integration"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_postgresql_delivery_cursor_resumes_cancels_and_upgrades_without_rewriting() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context,
                campaign_id="campaign:phase40:integration",
                title="Phase 40",
                state={"runtime_state": {"state_revision": 0}},
                engine_version="rne-phase40",
                schema_version="rpg-session-v1",
                seed="fixed",
            )
            work.commit()

        responses = PostgresNarrativeResponseRepositoryAdapter(
            database,
            context_provider=lambda value: context,
        )
        deliveries = PostgresNarrativeDeliveryRepositoryAdapter(
            database,
            context_provider=lambda value: context,
        )
        coordinator = NarrativeDeliveryCoordinator()

        deferred = responses.save(_response("deferred"))
        pending = coordinator.open(
            deferred,
            DeliveryMode.DEFERRED,
            deliveries,
        )
        assert pending.delivery.status == "pending"
        first, event = coordinator.publish_next(
            deferred,
            deliveries,
            expected_semantic_hash=deferred.semantic_hash,
        )
        assert event is not None and event.index == 0
        persisted = deliveries.get(deferred.response_id)
        assert persisted is not None
        assert persisted.next_index == 1
        assert persisted.delivered_block_ids == (deferred.blocks[0].block_id,)
        replayed = coordinator.resume(
            deferred,
            deliveries,
            expected_semantic_hash=deferred.semantic_hash,
            after_index=-1,
        )
        assert [row.index for row in replayed] == [0]
        completed, final_event = coordinator.publish_next(
            deferred,
            deliveries,
            expected_semantic_hash=deferred.semantic_hash,
        )
        assert final_event is not None and final_event.index == 1
        assert completed.delivery.status == "complete"
        assert completed.semantic_hash == deferred.semantic_hash == first.semantic_hash

        cancellable = responses.save(_response("cancel"))
        coordinator.open(cancellable, DeliveryMode.DEFERRED, deliveries)
        cancelled = coordinator.cancel_before_publication(
            cancellable,
            deliveries,
            expected_semantic_hash=cancellable.semantic_hash,
            reason="integration_cancel",
        )
        assert cancelled.delivery.status == "cancelled"
        assert cancelled.delivery.interruption_reason == "integration_cancel"

        upgradable = responses.save(_response("upgrade"))
        coordinator.open(upgradable, DeliveryMode.DEFERRED, deliveries)
        blocking = coordinator.open(
            upgradable,
            DeliveryMode.BLOCKING,
            deliveries,
        )
        assert blocking.delivery.status == "complete"
        assert blocking.semantic_hash == upgradable.semantic_hash
        assert blocking.delivery.delivered_block_ids == tuple(
            block.block_id for block in upgradable.blocks
        )
    finally:
        database.close()
