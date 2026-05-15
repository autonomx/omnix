from tests.rpg.autoplay_llm_campaign import (
    _apply_turn_action_consistency_gate,
    _build_turn_action_consistency_summary,
)


def test_mechanics_forced_action_does_not_become_canonical():
    row = {
        "turn_index": 4,
        "player_action": "I turn to Mira and ask what she saw near the side door.",
        "mechanics_forced_action": {
            "forced": True,
            "mechanic": "buying",
            "action": "I buy two rations from Bran.",
        },
        "progress_quality": {
            "player_action": "I turn to Mira and ask what she saw near the side door.",
        },
    }

    repaired = _apply_turn_action_consistency_gate(
        row,
        canonical_turn_action="I turn to Mira and ask what she saw near the side door.",
    )

    consistency = repaired.get("turn_action_consistency", {})
    assert consistency.get("canonical_turn_action") == "I turn to Mira and ask what she saw near the side door."
    assert repaired["player_action"] == "I turn to Mira and ask what she saw near the side door."


def test_turn_action_summary_fails_if_forced_override_present():
    summary = _build_turn_action_consistency_summary(
        transcript=[
            {
                "turn_index": 4,
                "canonical_turn_action": "I turn to Mira and ask what she saw near the side door.",
                "player_action": "I turn to Mira and ask what she saw near the side door.",
                "mechanics_forced_action": {
                    "forced": True,
                    "mechanic": "buying",
                    "action": "I buy two rations from Bran.",
                },
            }
        ]
    )

    assert summary["forced_override_count"] == 1
    assert summary["ok"] is False