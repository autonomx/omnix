from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.gateway.rpg_foreground_turn_record import (
    FOREGROUND_TURN_RECORD_MAX_BYTES,
    build_foreground_turn_record,
)
from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    InMemoryNarrativeResponseRepository,
    NarrativeBlock,
    ValidationReport,
)
from app.rpg.narrative_replay import (
    CanonicalNarrativeReplayError,
    hydrate_canonical_narrative_replay,
)
from app.rpg.presentation.turn_response_budget import encoded_size_bytes


ROOT = Path(__file__).resolve().parents[4]


def _response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:phase35",
        request_id="request:phase35",
        turn_id="turn:phase35",
        campaign_id="campaign:phase35",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="block:phase35",
                beat_id="beat:phase35",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="Rain taps against the shutters.",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="phase35_fixture"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_foreground_record_preserves_bounded_canonical_reference() -> None:
    response = _response()
    record = build_foreground_turn_record(
        {
            "ok": True,
            "turn_id": response.turn_id,
            "narration": "Rain " * 20_000,
            "canonical_narrative_response": response.as_dict(),
        },
        session_id=response.campaign_id,
        submission_id="submission:phase35",
        command="Listen to the rain.",
    )

    reference = record["canonical_narrative"]
    assert reference["response_id"] == response.response_id
    assert reference["content_hash"] == response.content_hash
    assert reference["campaign_id"] == response.campaign_id
    assert reference["turn_id"] == response.turn_id
    assert encoded_size_bytes(record) <= FOREGROUND_TURN_RECORD_MAX_BYTES


def test_idempotent_record_hydrates_exact_persisted_canon() -> None:
    response = _response()
    repository = InMemoryNarrativeResponseRepository()
    repository.save(response)
    record = build_foreground_turn_record(
        {
            "ok": True,
            "turn_id": response.turn_id,
            "narration": "Rain taps against the shutters.",
            "canonical_narrative_response": response.as_dict(),
        },
        session_id=response.campaign_id,
        submission_id="submission:phase35",
        command="Listen to the rain.",
    )
    record["idempotent_replay"] = True

    hydrated = hydrate_canonical_narrative_replay(
        record,
        campaign_id=response.campaign_id,
        repository=repository,
    )

    assert hydrated["canonical_narrative_response"] == response.as_dict()
    assert hydrated["canonical_narrative_replay"]["hydrated"] is True
    assert hydrated["canonical_narrative_source"] == "durable_submission_replay_v1"


def test_replay_hash_mismatch_fails_closed() -> None:
    response = _response()
    repository = InMemoryNarrativeResponseRepository()
    repository.save(response)
    record = build_foreground_turn_record(
        {
            "ok": True,
            "turn_id": response.turn_id,
            "narration": "Rain taps against the shutters.",
            "canonical_narrative_response": response.as_dict(),
        },
        session_id=response.campaign_id,
        submission_id="submission:phase35",
        command="Listen to the rain.",
    )
    record["canonical_narrative"]["content_hash"] = "wrong"
    record["idempotent_replay"] = True

    with pytest.raises(CanonicalNarrativeReplayError, match="content hash mismatch"):
        hydrate_canonical_narrative_replay(
            record,
            campaign_id=response.campaign_id,
            repository=repository,
        )


def test_repository_response_identity_mismatch_fails_closed() -> None:
    response = _response()
    wrong = replace(response, response_id="response:other").with_content_hash()

    class _Repository:
        def get_for_turn(self, campaign_id, turn_id):
            return wrong

        def get(self, response_id):
            return wrong

    record = {
        "ok": True,
        "idempotent_replay": True,
        "canonical_narrative": {
            "response_id": response.response_id,
            "content_hash": response.content_hash,
            "campaign_id": response.campaign_id,
            "turn_id": response.turn_id,
        },
    }
    with pytest.raises(CanonicalNarrativeReplayError, match="response identity mismatch"):
        hydrate_canonical_narrative_replay(
            record,
            campaign_id=response.campaign_id,
            repository=_Repository(),
        )


def test_gateway_hydrates_replay_before_any_canonical_generation() -> None:
    source = (ROOT / "src/app/gateway/rpg_turn_pipeline.py").read_text(
        encoding="utf-8"
    )
    hydration = source.index("hydrate_canonical_narrative_replay(")
    assert hydration < source.index("canonicalize_scene_turn_result(")
    assert hydration < source.index("canonicalize_resolved_turn_result(")
    assert 'rpg_pipeline_span("turn.narrative_replay_hydration")' in source
