import json

from tests.rpg.autoplay.player_agent import (
    build_player_agent_prompt,
    choose_fallback_player_action,
    parse_player_agent_response,
    validate_player_action_against_context,
)


def test_parse_player_agent_response_accepts_json():
    parsed = parse_player_agent_response(
        json.dumps(
            {
                "format_version": "rpg_player_action_v1",
                "intent": "ask Bran",
                "action": "I ask Bran about the witness.",
                "reason": "Nearby NPC may know something.",
                "risk": "low",
                "goal_id": "milestone:find_witness",
            }
        )
    )

    assert parsed["ok"] is True
    assert parsed["action"] == "I ask Bran about the witness."


def test_fallback_uses_top_suggested_action():
    context = {
        "suggested_actions": [
            {
                "action_id": "objective:001",
                "command": "I look for the witness.",
                "label": "Find witness",
                "objective_id": "milestone:find_witness",
            }
        ]
    }

    selected = choose_fallback_player_action(player_action_context=context)

    assert selected["ok"] is True
    assert selected["fallback"] is True
    assert selected["action"] == "I look for the witness."


def test_fallback_avoids_recently_repeated_top_action():
    context = {
        "suggested_actions": [
            {
                "action_id": "objective:001",
                "command": "I look for the witness.",
                "label": "Find witness",
                "objective_id": "milestone:find_witness",
            },
            {
                "action_id": "social:001",
                "command": "I talk to Bran and ask what he knows.",
                "label": "Talk to Bran",
            },
        ]
    }
    recent = [{"player_action": "I look for the witness."} for _ in range(5)]

    selected = choose_fallback_player_action(
        player_action_context=context,
        recent_transcript=recent,
    )

    assert selected["action"] == "I talk to Bran and ask what he knows."


def test_player_agent_prompt_includes_schema_and_context():
    prompt = build_player_agent_prompt(
        player_action_context={
            "format_version": "player_action_context_v1",
            "suggested_actions": [{"command": "I observe."}],
        },
        recent_transcript=[],
    )

    assert "rpg_player_action_v1" in prompt
    assert "player_action_context_v1" in prompt
    assert "Do not narrate the outcome" in prompt


def test_validate_player_action_rejects_outcome_claims():
    result = validate_player_action_against_context(
        player_action={"action": "I complete the quest and receive 100 gold."},
        player_action_context={},
    )

    assert result["ok"] is False
    assert result["reason"] == "player_action_appears_to_decide_outcome"