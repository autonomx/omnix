from __future__ import annotations

from copy import deepcopy

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBlock,
    ValidationReport,
    canonical_consumer_bundle,
)
from app.rpg.narrative_engine.consumer_publish import attach_canonical_consumer_bundle


def _response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:consumer",
        request_id="request:consumer",
        turn_id="turn:consumer",
        campaign_id="campaign:consumer",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="block:reaction",
                beat_id="beat:reaction",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.PHYSICAL_REACTION,
                text="Bran sets the cup beneath the rain-streaked window.",
            ),
            NarrativeBlock(
                block_id="block:answer",
                beat_id="beat:answer",
                sequence=2,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="The road is muddy, but passable.",
                speaker_id="npc:bran",
            ),
        ),
        evidence_used=("evidence:bran", "evidence:rain"),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="fixture", beat_count=2),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_all_consumers_share_response_hash_and_ordered_block_identity() -> None:
    response = _response()
    bundle = canonical_consumer_bundle(response)
    assert bundle["response_id"] == response.response_id
    assert bundle["content_hash"] == response.content_hash
    assert [row["block_id"] for row in bundle["transcript"]] == [
        "block:reaction",
        "block:answer",
    ]
    assert [row["block_id"] for row in bundle["tts"]] == [
        "block:reaction",
        "block:answer",
    ]
    assert bundle["journal"]["block_ids"] == ["block:reaction", "block:answer"]
    assert bundle["replay"]["content_hash"] == response.content_hash
    assert bundle["report"]["content_hash"] == response.content_hash
    assert bundle["visible_response"]["messages"] == [
        {
            "kind": "npc",
            "speaker": "npc:bran",
            "speaker_id": "npc:bran",
            "text": "The road is muddy, but passable.",
            "block_id": "block:answer",
            "sequence": 2,
        }
    ]


def test_consumer_publication_patches_latest_interaction_without_regeneration() -> None:
    response = _response()
    result = {
        "ok": True,
        "turn_id": response.turn_id,
        "canonical_narrative_response": response.as_dict(),
        "session": {
            "runtime_state": {
                "recent_interactions": [
                    {
                        "interaction_id": "interaction:consumer",
                        "turn_id": response.turn_id,
                        "player_input": "How is the road?",
                        "visible_response": {"narration": "legacy duplicate"},
                    }
                ]
            }
        },
    }
    original = deepcopy(response.as_dict())
    published = attach_canonical_consumer_bundle(result)
    interaction = published["session"]["runtime_state"]["recent_interactions"][0]
    assert published["canonical_narrative_response"] == original
    assert interaction["narrative_response_id"] == response.response_id
    assert interaction["narrative_content_hash"] == response.content_hash
    assert interaction["visible_response"] == published["narrative_projections"]["visible_response"]
    assert interaction["visible_response"]["narration"].count("road is muddy") == 0
    assert len(interaction["visible_response"]["messages"]) == 1
    assert published["narrative_session_projection_patched"] is True


def test_foreground_pipeline_publishes_and_persists_consumer_bundle() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    source = (root / "app" / "gateway" / "rpg_turn_pipeline.py").read_text(encoding="utf-8")
    assert "attach_canonical_consumer_bundle" in source
    assert 'payload["narrative_projections"]' in source
    assert "narrative_session_projection_patched" in source
