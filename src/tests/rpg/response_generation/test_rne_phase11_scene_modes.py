from __future__ import annotations

from pathlib import Path

from app.rpg.session.narrative_engine_bridge import canonicalize_scene_turn_result


REPO_ROOT = Path(__file__).resolve().parents[4]


def _base_result(mode: str) -> dict:
    return {
        "ok": True,
        "turn_id": f"turn:{mode}:1",
        "tick": 1,
        "state_revision": 1,
        "resolved_result": {
            "ok": True,
            "response_mode": mode,
            "allowed_claim_refs": [],
        },
        "scene": {
            "location_name": "The Old Quarry",
            "summary": "Rain beads on broken stone while a narrow path descends between abandoned cranes.",
        },
        "narration": "Legacy visible text.",
    }


def test_observation_publishes_one_grounded_canonical_answer() -> None:
    result = canonicalize_scene_turn_result(
        _base_result("observation"),
        session_id="campaign:scene",
        player_input="Look around the quarry.",
    )
    canonical = result["canonical_narrative_response"]
    assert result["source"] == "narrative_engine_scene_turn_v1"
    assert canonical["metadata"]["mode"] == "observation"
    assert [block["purpose"] for block in canonical["blocks"]] == ["direct_answer"]
    assert "Old Quarry" in result["narration"]


def test_travel_requires_scene_establishment_and_resolved_consequence() -> None:
    result = _base_result("travel")
    result["location_changed"] = True
    result["canonical_effects"] = {"location": {"from": "old_road", "to": "old_quarry"}}
    result = canonicalize_scene_turn_result(
        result,
        session_id="campaign:scene",
        player_input="Travel to the quarry.",
    )
    purposes = [block["purpose"] for block in result["canonical_narrative_response"]["blocks"]]
    assert purposes[:2] == ["scene_establishment", "meaningful_environmental_change"]
    assert "resolved_action" in purposes
    assert "consequence" in purposes
    assert result["canonical_narrative_response"]["validation"]["passed"] is True


def test_phase28_triggers_become_required_beats_not_separate_prose() -> None:
    result = _base_result("action")
    result["environmental_narration_report"] = {
        "should_generate": True,
        "triggers": ["new_game", "weather_changed"],
    }
    result = canonicalize_scene_turn_result(
        result,
        session_id="campaign:scene",
        player_input="Take in the room.",
    )
    purposes = [block["purpose"] for block in result["canonical_narrative_response"]["blocks"]]
    assert purposes[:2] == ["scene_establishment", "meaningful_environmental_change"]
    assert result["source"] == "narrative_engine_scene_turn_v1"


def test_gateway_runs_scene_cutover_before_shadow_comparison() -> None:
    source = (REPO_ROOT / "src/app/gateway/rpg_turn_pipeline.py").read_text(encoding="utf-8")
    assert source.index("canonicalize_scene_turn_result") < source.index("attach_shadow_report")
    assert 'rpg_pipeline_span("turn.narrative_scene_cutover")' in source
