from __future__ import annotations

from dataclasses import replace

import pytest

from app.persistence.rpg_narrative_response_repository import (
    NarrativeResponsePersistenceConflict,
)
from app.rpg.narrative_engine import (
    DeliveryMode,
    EvidenceBroker,
    InMemoryNarrativeResponseRepository,
    NarrativeBlock,
    NarrativeEngineService,
    NarrativeResponseConflict,
    NarrativeTurnIdentityConflict,
    TurnPresentationRequest,
    WriterResult,
)
from app.rpg.narrative_repository import PostgresNarrativeResponseRepositoryAdapter


class _CountingWriter:
    def __init__(self) -> None:
        self.calls = 0

    def write(self, request, plan, evidence):
        self.calls += 1
        return WriterResult(
            blocks=tuple(
                NarrativeBlock(
                    block_id=f"block:{beat.sequence}",
                    beat_id=beat.beat_id,
                    sequence=beat.sequence,
                    kind=beat.kind,
                    purpose=beat.purpose,
                    speaker_id=beat.speaker_id,
                    evidence_refs=beat.evidence_refs,
                    claim_refs=beat.required_claim_refs,
                    text=f"{beat.purpose.value.replace('_', ' ').capitalize()} remains grounded.",
                )
                for beat in plan.beats
            ),
            source="phase32_counting_writer",
        )


def _request(
    *,
    request_id: str = "request:phase32",
    delivery_mode: DeliveryMode = DeliveryMode.BLOCKING,
) -> TurnPresentationRequest:
    return TurnPresentationRequest(
        request_id=request_id,
        turn_id="turn:phase32",
        campaign_id="campaign:phase32",
        player_input="Check the old road.",
        authoritative_outcome={
            "response_mode": "action",
            "mechanic_resolved": True,
            "allowed_claim_refs": [],
        },
        delivery_mode=delivery_mode,
        metadata={"response_mode": "action"},
    )


def test_same_turn_replays_persisted_canon_without_second_writer_call() -> None:
    writer = _CountingWriter()
    repository = InMemoryNarrativeResponseRepository()
    service = NarrativeEngineService(
        evidence_broker=EvidenceBroker([]),
        writer=writer,
        repository=repository,
    )

    first = service.generate(_request())
    replay = service.generate(_request(delivery_mode=DeliveryMode.DEFERRED))

    assert writer.calls == 1
    assert replay.response.response_id == first.response.response_id
    assert replay.response.content_hash == first.response.content_hash
    assert replay.response.blocks == first.response.blocks
    assert replay.response.delivery.mode is DeliveryMode.DEFERRED
    assert replay.response.metadata["idempotent_replay"] is True
    assert replay.writer_result.writer_result.source == "persisted_canonical_replay"
    assert replay.writer_result.writer_result.attempt_count == 0


def test_same_turn_with_different_request_identity_fails_closed() -> None:
    service = NarrativeEngineService(
        evidence_broker=EvidenceBroker([]),
        writer=_CountingWriter(),
        repository=InMemoryNarrativeResponseRepository(),
    )
    service.generate(_request())

    with pytest.raises(NarrativeTurnIdentityConflict):
        service.generate(_request(request_id="request:different"))


class _RaceRepository:
    def __init__(self, winner) -> None:
        self.winner = winner
        self.lookups = 0

    def get_for_turn(self, campaign_id, turn_id):
        self.lookups += 1
        return None if self.lookups == 1 else self.winner

    def get(self, response_id):
        return self.winner if response_id == self.winner.response_id else None

    def save(self, response):
        raise NarrativeResponseConflict("another worker persisted the turn first")


def test_concurrent_generation_loser_adopts_repository_winner() -> None:
    seed_service = NarrativeEngineService(
        evidence_broker=EvidenceBroker([]),
        writer=_CountingWriter(),
        repository=InMemoryNarrativeResponseRepository(),
    )
    winner = seed_service.generate(_request()).response
    writer = _CountingWriter()
    service = NarrativeEngineService(
        evidence_broker=EvidenceBroker([]),
        writer=writer,
        repository=_RaceRepository(winner),
    )

    replay = service.generate(_request())

    assert writer.calls == 1
    assert replay.response.content_hash == winner.content_hash
    assert replay.response.metadata["idempotent_replay"] is True


class _FailingStore:
    def save(self, context, response):
        raise NarrativeResponsePersistenceConflict("postgres turn identity conflict")


class _FailingWork:
    def __init__(self) -> None:
        self.narrative_responses = _FailingStore()
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def rollback(self):
        self.rolled_back = True

    def commit(self):
        raise AssertionError("conflicted work must not commit")


class _FailingFactory:
    def __init__(self) -> None:
        self.work = _FailingWork()

    def __call__(self, database):
        return self.work


def test_postgres_conflict_is_normalized_to_engine_repository_conflict() -> None:
    seed_service = NarrativeEngineService(
        evidence_broker=EvidenceBroker([]),
        writer=_CountingWriter(),
        repository=InMemoryNarrativeResponseRepository(),
    )
    response = seed_service.generate(_request()).response
    factory = _FailingFactory()
    adapter = PostgresNarrativeResponseRepositoryAdapter(
        object(),
        context_provider=lambda database: object(),
        unit_of_work_factory=factory,
    )

    with pytest.raises(NarrativeResponseConflict):
        adapter.save(replace(response, response_id="response:postgres-conflict"))

    assert factory.work.rolled_back is True
