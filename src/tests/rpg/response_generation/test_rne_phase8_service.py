from __future__ import annotations

import pytest

from app.rpg.narrative_engine import (
    DeliveryMode,
    EvidenceBroker,
    InMemoryEvidenceSource,
    InMemoryNarrativeResponseRepository,
    NarrativeDeliveryCoordinator,
    NarrativeEngineService,
    NarrativeResponseConflict,
    PresentationProfile,
    TurnPresentationRequest,
    bran_fixture_evidence,
)


def _service(repository=None) -> NarrativeEngineService:
    return NarrativeEngineService(
        evidence_broker=EvidenceBroker([InMemoryEvidenceSource(bran_fixture_evidence())]),
        repository=repository,
    )


def _request(mode: DeliveryMode = DeliveryMode.BLOCKING, *, text: str = "How is the road?"):
    return TurnPresentationRequest(
        request_id="request:phase8",
        turn_id="turn:phase8",
        campaign_id="campaign:phase8",
        player_input=text,
        actor_ids=("npc:bran",),
        target_actor_id="npc:bran",
        presentation_profile=PresentationProfile.FAST,
        delivery_mode=mode,
        metadata={"response_mode": "dialogue", "response_id": "response:phase8"},
    )


def test_engine_generates_validates_persists_and_delivers_one_response() -> None:
    repository = InMemoryNarrativeResponseRepository()
    result = _service(repository).generate(_request())
    assert result.response.response_id == "response:phase8"
    assert result.response.validation.passed is True
    assert result.response.delivery.status == "complete"
    assert repository.get("response:phase8") is not None
    assert repository.get_for_turn("campaign:phase8", "turn:phase8").content_hash == result.response.content_hash


def test_blocking_and_deferred_delivery_preserve_content_hash() -> None:
    blocking_repository = InMemoryNarrativeResponseRepository()
    deferred_repository = InMemoryNarrativeResponseRepository()
    blocking = _service(blocking_repository).generate(_request(DeliveryMode.BLOCKING)).response
    deferred = _service(deferred_repository).generate(_request(DeliveryMode.DEFERRED)).response
    assert blocking.content_hash == deferred.content_hash
    assert blocking.delivery.status == "complete"
    assert deferred.delivery.status == "pending"
    completed = NarrativeDeliveryCoordinator().complete_deferred(deferred)
    assert completed.content_hash == deferred.content_hash
    assert completed.delivery.status == "complete"


def test_repository_is_idempotent_for_same_turn_and_content() -> None:
    repository = InMemoryNarrativeResponseRepository()
    service = _service(repository)
    first = service.generate(_request()).response
    second = service.generate(_request()).response
    assert first.content_hash == second.content_hash
    assert len(repository.list_campaign("campaign:phase8")) == 1


def test_repository_rejects_different_canonical_content_for_same_turn() -> None:
    repository = InMemoryNarrativeResponseRepository()
    service = _service(repository)
    service.generate(_request())
    with pytest.raises(NarrativeResponseConflict):
        service.generate(_request(text="Tell me who you are."))
