from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.rpg.narrative_engine.shadow import (
    attach_shadow_report,
    build_shadow_report,
    shadow_selected,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


def _result() -> dict:
    return {
        "ok": True,
        "turn_id": "turn:shadow:1",
        "state_revision": 1,
        "resolved_result": {
            "response_mode": "dialogue",
            "allowed_claim_refs": [],
        },
        "scene": {
            "location_name": "The Rusty Flagon",
            "summary": "Rain taps the shutters beside the low hearth.",
        },
        "npc": {
            "speaker": "Bran",
            "line": "The road is muddy, but passable.",
        },
        "narration": "Bran looks toward the rain-streaked shutters.",
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "npc_context": {
                    "addressed_npcs": [
                        {
                            "name": "Bran",
                            "biography": "Keeper of the Rusty Flagon.",
                            "personality_profile": {"summary": "Practical and observant."},
                        }
                    ]
                }
            }
        },
    }


def test_shadow_sampling_is_deterministic() -> None:
    assert shadow_selected("turn:1", 1.0) is True
    assert shadow_selected("turn:1", 0.0) is False
    assert shadow_selected("turn:stable", 0.25) == shadow_selected("turn:stable", 0.25)


def test_shadow_report_compares_without_mutating_authoritative_input() -> None:
    result = _result()
    before = deepcopy(result)
    report = build_shadow_report(
        result,
        session_id="campaign:shadow",
        player_input="How is the road?",
        sample_rate=1.0,
    )
    assert result == before
    assert report["selected"] is True
    assert report["ok"] is True
    assert report["response_id"] == "shadow-response:campaign:shadow:turn:shadow:1"
    assert report["evidence_ids"]
    assert report["beat_purposes"][:2] == ["physical_reaction", "direct_answer"]
    assert report["authoritative_state_unchanged"] is True


def test_shadow_attachment_is_diagnostic_only() -> None:
    result = _result()
    attached = attach_shadow_report(
        result,
        session_id="campaign:shadow",
        player_input="How is the road?",
    )
    assert attached is result
    assert attached["narrative_engine_shadow"]["source"] == "narrative_engine_shadow_v1"
    assert attached["resolved_result"]["response_mode"] == "dialogue"


def test_foreground_pipeline_publishes_shadow_diagnostics_not_shadow_prose() -> None:
    source = (REPO_ROOT / "src/app/gateway/rpg_turn_pipeline.py").read_text(encoding="utf-8")
    assert "attach_shadow_report" in source
    assert 'payload["narrative_engine_shadow"]' in source
    assert "canonical_text" not in source.replace('payload["narrative_engine_shadow"]', "")
