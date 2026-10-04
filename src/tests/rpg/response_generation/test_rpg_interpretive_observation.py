from __future__ import annotations

from app.rpg.session.interpretive_adjudication import (
    build_interpretive_adjudication_result,
)


def test_look_around_uses_published_scene_narration_without_fabricated_npc() -> None:
    result = build_interpretive_adjudication_result(
        session={
            "state": {
                "current_location_name": "Tidebreak Docks",
                "summary": "Cargo rigs move beneath the seawall cranes.",
                "narrative_affordances": {
                    "opening_story": {
                        "summary": "Black rain beads across the Tidebreak cargo rigs."
                    }
                },
            }
        },
        simulation_state={},
        runtime_state={},
        player_input="I look around",
        selection={"reason": "missing_visible_response_text"},
    )

    assert result["result"]["interpretive_intent"] == "observation_request"
    assert result["result"]["semantic_family"] == "observation"
    assert result["visible_response"]["npc"] == {}
    assert result["npc"] == {}
    assert result["narration"] == (
        "Black rain beads across the Tidebreak cargo rigs."
    )
