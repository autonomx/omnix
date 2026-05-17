from tests.rpg.autoplay_llm_campaign import (
    _presentation_has_combat_claim,
    _turn_has_combat_support,
)


def test_presentation_has_combat_claim_detects_bandit_attack():
    assert _presentation_has_combat_claim("A bandit strikes with a blade.") is True


def test_turn_has_combat_support_false_for_buying_turn():
    assert (
        _turn_has_combat_support(
            {
                "mechanics_covered_this_turn": [
                    "buying",
                    "inventory_change",
                    "currency_change",
                ]
            }
        )
        is False
    )


def test_turn_has_combat_support_true_for_direct_combat_completion():
    assert (
        _turn_has_combat_support(
            {
                "direct_graph_action_completion": {
                    "mechanics": ["combat_started", "combat_resolved"]
                }
            }
        )
        is True
    )
