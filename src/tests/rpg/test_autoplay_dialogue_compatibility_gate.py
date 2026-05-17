from tests.rpg.autoplay_llm_campaign import (
    _build_category_compatible_presentation_fallback,
    _dialogue_presentation_is_category_compatible,
)


def test_dialogue_compatibility_rejects_combat_text_for_economy_action_without_support():
    ok, diag = _dialogue_presentation_is_category_compatible(
        action_text="I buy two rations from Bran.",
        presentation_text="The bandit lunges with a blade and blood spills on the road.",
        row={"mechanics_covered_this_turn": ["buying", "currency_change"]},
    )

    assert ok is False
    assert diag["action_category"] == "economy"
    assert diag["presentation_category"] == "combat"


def test_dialogue_compatibility_allows_combat_text_when_combat_supported():
    ok, diag = _dialogue_presentation_is_category_compatible(
        action_text="I protect the wagon from the bandits.",
        presentation_text="The bandits attack and you drive them back.",
        row={"mechanics_covered_this_turn": ["combat_started", "combat_resolved"]},
    )

    assert ok is True
    assert diag["reason"] in {"category_match", "combat_supported_by_mechanics"}


def test_category_fallback_for_economy_action_is_safe():
    fallback = _build_category_compatible_presentation_fallback(
        {
            "player_action": "I buy two rations from Bran.",
            "canonical_turn_action": "I buy two rations from Bran.",
        }
    )

    assert "purchase" in fallback.lower()
    assert "authoritative" in fallback.lower()
