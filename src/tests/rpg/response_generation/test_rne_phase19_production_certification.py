from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBlock,
    ValidationReport,
)
from app.rpg.narrative_engine.consumer_publish import attach_canonical_consumer_bundle
from app.rpg.narrative_engine.production_path import (
    NarrativeProductionPathError,
    certify_production_narrative_result,
    enforce_production_narrative_result,
)
from app.rpg.narrative_engine.publisher_guard import publisher_guard


REPO_ROOT = Path(__file__).resolve().parents[4]


def _response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:phase19",
        request_id="request:phase19",
        turn_id="turn:phase19",
        campaign_id="campaign:phase19",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="block:reaction",
                beat_id="beat:reaction",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.PHYSICAL_REACTION,
                text="Bran rubs rainwater from the window latch.",
            ),
            NarrativeBlock(
                block_id="block:answer",
                beat_id="beat:answer",
                sequence=2,
                kind=BeatKind.DIALOGUE,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="The east bridge is open.",
                speaker_id="npc:bran",
            ),
        ),
        evidence_used=("evidence:window", "evidence:bridge"),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="fixture", beat_count=2),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def _result() -> dict:
    response = _response()
    return {
        "ok": True,
        "turn_id": response.turn_id,
        "canonical_narrative_response": response.as_dict(),
        "canonical_narrative_source": "unified_narrative_engine_v1",
        "narration": "legacy narration must be replaced",
        "summary": "legacy summary must be replaced",
        "npc": {"speaker": "Bran", "line": "legacy line"},
        "session": {
            "runtime_state": {
                "recent_interactions": [
                    {
                        "interaction_id": "interaction:phase19",
                        "turn_id": response.turn_id,
                        "visible_response": {"plain_text": "legacy"},
                    }
                ]
            }
        },
    }


def test_final_path_retires_legacy_ownership_and_certifies_every_invariant() -> None:
    publisher_guard.reset_for_tests()
    try:
        result = attach_canonical_consumer_bundle(_result())
        certified = enforce_production_narrative_result(result)
        report = certified["narrative_production_certification"]
        assert report["passed"] is True, report
        assert all(report["checks"].values())
        assert certified["legacy_presentation_ownership_retired"] is True
        assert certified["legacy_compatibility_fields_source"] == "canonical_projection_only"
        assert certified["narration"] == "Bran rubs rainwater from the window latch."
        assert certified["npc"] == {
            "speaker": "npc:bran",
            "line": "The east bridge is open.",
        }
        assert certified["visible_response"]["plain_text"].count("east bridge is open") == 1
        interaction = certified["session"]["runtime_state"]["recent_interactions"][0]
        assert interaction["narrative_response_id"] == "response:phase19"
        assert interaction["narrative_content_hash"] == report["content_hash"]
    finally:
        publisher_guard.reset_for_tests()


def test_final_path_fails_closed_when_publisher_telemetry_is_corrupted() -> None:
    publisher_guard.reset_for_tests()
    try:
        result = attach_canonical_consumer_bundle(_result())
        result["narrative_publisher_telemetry"] = {
            **result["narrative_publisher_telemetry"],
            "alternate_publish_count": 1,
            "zero_alternate_publishers": False,
        }
        report = certify_production_narrative_result(result)
        assert report.passed is False
        assert "zero_alternate_publishers" in report.violations
        with pytest.raises(NarrativeProductionPathError):
            enforce_production_narrative_result(result)
    finally:
        publisher_guard.reset_for_tests()


def test_gateway_enforces_certification_before_persistence_and_response_build() -> None:
    source = (REPO_ROOT / "src" / "app" / "gateway" / "rpg_turn_pipeline.py").read_text(
        encoding="utf-8"
    )
    certification_index = source.index("enforce_production_narrative_result")
    persistence_index = source.index('rpg_pipeline_span("turn.session_persist")')
    response_index = source.index('rpg_pipeline_span("turn.response_contract_build")')
    assert certification_index < persistence_index < response_index
    assert "rpg_narrative_production_certification_failed" in source
    assert 'payload["narrative_production_certification"]' in source
