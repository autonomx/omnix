from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.narrative_delivery import (
    deferred_public_turn_payload,
    prepare_canonical_result_delivery,
)
from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    InMemoryNarrativeDeliveryRepository,
    InMemoryNarrativeResponseRepository,
    NarrativeBlock,
    NarrativeDeliveryConflict,
    NarrativeDeliveryCoordinator,
    ValidationReport,
)


ROOT = Path(__file__).resolve().parents[4]


def _response(response_id: str = "response:phase40") -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id=response_id,
        request_id=f"request:{response_id}",
        turn_id=f"turn:{response_id}",
        campaign_id="campaign:phase40",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id=f"{response_id}:block:one",
                beat_id="beat:one",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.PHYSICAL_REACTION,
                text="Bran turns toward the rain-dark road.",
            ),
            NarrativeBlock(
                block_id=f"{response_id}:block:two",
                beat_id="beat:two",
                sequence=2,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="The bridge still holds.",
                speaker_id="npc:bran",
            ),
            NarrativeBlock(
                block_id=f"{response_id}:block:three",
                beat_id="beat:three",
                sequence=3,
                kind=BeatKind.CHOICE,
                purpose=BeatPurpose.CONTINUATION,
                text="The eastern road remains open.",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="phase40-fixture"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_deferred_delivery_preserves_identity_and_publishes_ordered_blocks() -> None:
    response = _response()
    repository = InMemoryNarrativeDeliveryRepository()
    coordinator = NarrativeDeliveryCoordinator()

    pending = coordinator.open(response, DeliveryMode.DEFERRED, repository)
    assert pending.response_id == response.response_id
    assert pending.semantic_hash == response.semantic_hash
    assert pending.delivery.status == "pending"
    assert pending.delivery.delivered_block_ids == ()

    events = []
    current = pending
    for _ in range(3):
        current, event = coordinator.publish_next(
            response,
            repository,
            expected_semantic_hash=response.semantic_hash,
        )
        assert event is not None
        events.append(event)

    assert [event.index for event in events] == [0, 1, 2]
    assert [event.block.block_id for event in events] == [
        block.block_id for block in response.blocks
    ]
    assert [event.block.text for event in events] == [
        block.text for block in response.blocks
    ]
    assert current.delivery.status == "complete"
    assert current.delivery.delivered_block_ids == tuple(
        block.block_id for block in response.blocks
    )
    assert current.semantic_hash == response.semantic_hash


def test_reconnect_replays_only_delivered_suffix_without_regeneration() -> None:
    response = _response()
    repository = InMemoryNarrativeDeliveryRepository()
    coordinator = NarrativeDeliveryCoordinator()
    coordinator.open(response, DeliveryMode.DEFERRED, repository)
    coordinator.publish_next(
        response,
        repository,
        expected_semantic_hash=response.semantic_hash,
    )
    coordinator.publish_next(
        response,
        repository,
        expected_semantic_hash=response.semantic_hash,
    )

    replayed = coordinator.resume(
        response,
        repository,
        expected_semantic_hash=response.semantic_hash,
        after_index=0,
    )
    assert len(replayed) == 1
    assert replayed[0].index == 1
    assert replayed[0].block.block_id == response.blocks[1].block_id
    assert replayed[0].response_id == response.response_id
    assert replayed[0].semantic_hash == response.semantic_hash


def test_hash_mismatch_and_post_publication_cancellation_fail_closed() -> None:
    response = _response()
    repository = InMemoryNarrativeDeliveryRepository()
    coordinator = NarrativeDeliveryCoordinator()
    coordinator.open(response, DeliveryMode.DEFERRED, repository)

    with pytest.raises(NarrativeDeliveryConflict, match="semantic hash mismatch"):
        coordinator.publish_next(
            response,
            repository,
            expected_semantic_hash="sha256:wrong",
        )

    coordinator.publish_next(
        response,
        repository,
        expected_semantic_hash=response.semantic_hash,
    )
    with pytest.raises(NarrativeDeliveryConflict, match="before first publication"):
        coordinator.cancel_before_publication(
            response,
            repository,
            expected_semantic_hash=response.semantic_hash,
        )


def test_cancellation_before_publication_and_blocking_upgrade_are_idempotent() -> None:
    response = _response("response:phase40:cancel")
    repository = InMemoryNarrativeDeliveryRepository()
    coordinator = NarrativeDeliveryCoordinator()
    coordinator.open(response, DeliveryMode.DEFERRED, repository)
    cancelled = coordinator.cancel_before_publication(
        response,
        repository,
        expected_semantic_hash=response.semantic_hash,
        reason="player_cancelled",
    )
    assert cancelled.delivery.status == "cancelled"
    assert cancelled.delivery.interruption_reason == "player_cancelled"
    assert cancelled.semantic_hash == response.semantic_hash

    upgrade = _response("response:phase40:upgrade")
    upgrade_repository = InMemoryNarrativeDeliveryRepository()
    coordinator.open(upgrade, DeliveryMode.DEFERRED, upgrade_repository)
    blocking = coordinator.open(
        upgrade,
        DeliveryMode.BLOCKING,
        upgrade_repository,
    )
    reopened = coordinator.open(
        upgrade,
        DeliveryMode.BLOCKING,
        upgrade_repository,
    )
    assert blocking.delivery.status == "complete"
    assert reopened.delivery.status == "complete"
    assert blocking.semantic_hash == upgrade.semantic_hash == reopened.semantic_hash
    assert blocking.delivery.delivered_block_ids == tuple(
        block.block_id for block in upgrade.blocks
    )


def test_result_adapter_persists_once_and_public_deferred_payload_contains_no_prose() -> None:
    response = _response("response:phase40:adapter")
    response_repository = InMemoryNarrativeResponseRepository()
    delivery_repository = InMemoryNarrativeDeliveryRepository()
    result = {
        "ok": True,
        "canonical_narrative_response": response.as_dict(),
        "narrative_projections": {"transcript": "must not leak"},
        "result": {"canonical_narrative_response": response.as_dict()},
    }

    prepared = prepare_canonical_result_delivery(
        result,
        DeliveryMode.DEFERRED,
        response_repository=response_repository,
        delivery_repository=delivery_repository,
    )
    public = deferred_public_turn_payload(
        {
            **prepared,
            "visible_response": {"plain_text": "must not leak"},
            "response": "must not leak",
            "content": "must not leak",
            "result": {
                "visible_response": {"plain_text": "must not leak"},
            },
        }
    )

    assert response_repository.get(response.response_id) is not None
    assert public["response"] == ""
    assert public["content"] == ""
    assert public["visible_response"]["plain_text"] == ""
    assert "narrative_projections" not in public
    envelope = public["canonical_narrative_response"]
    assert envelope["response_id"] == response.response_id
    assert envelope["semantic_hash"] == response.semantic_hash
    assert envelope["prose_deferred"] is True
    assert all("text" not in block for block in envelope["blocks"])
    delivery = public["deferred_narrative_delivery"]
    assert delivery["next_index"] == 0
    assert delivery["stream_path"].endswith(
        f"/{response.response_id}/stream"
    )


def test_phase40_source_guards_cover_persistence_streaming_and_gateway_cutover() -> None:
    migration = (
        ROOT
        / "src"
        / "app"
        / "persistence"
        / "migrations"
        / "0022_rpg_narrative_delivery.sql"
    ).read_text(encoding="utf-8")
    gateway = (
        ROOT / "src" / "app" / "gateway" / "rpg_turn_pipeline.py"
    ).read_text(encoding="utf-8")
    routes = (
        ROOT
        / "src"
        / "app"
        / "gateway"
        / "rpg_narrative_delivery_routes.py"
    ).read_text(encoding="utf-8")
    sessions = (
        ROOT / "src" / "app" / "gateway" / "rpg_session_routes.py"
    ).read_text(encoding="utf-8")

    assert "omnix_rpg_narrative_deliveries" in migration
    assert "semantic_hash" in migration
    assert "delivered_block_ids_jsonb" in migration
    assert "x-omnix-rpg-delivery-mode" in gateway
    assert "prepare_canonical_result_delivery" in gateway
    assert "deferred_public_turn_payload" in gateway
    assert "last-event-id" in routes
    assert "event: narrative_block" in routes
    assert "cancel_before_publication" in routes
    assert "register_rpg_narrative_delivery_routes(app)" in sessions
