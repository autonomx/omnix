from __future__ import annotations

import pytest

from app.characters import CharacterProfileSnapshot, InteractionSelection, resolve_interaction_context


def _character(policy: dict[str, object]) -> CharacterProfileSnapshot:
    return CharacterProfileSnapshot(
        id="maya",
        display_name="Maya",
        personality_prompt="Be warm and easygoing.",
        identity_policy=policy,
    )


def test_character_prompt_contains_hard_ai_identity_disclosure(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    context = resolve_interaction_context(
        InteractionSelection(interaction_mode="character", character_id="maya"),
        character=_character({"disclosure_required": True}),
    )

    identity = "\n".join(context.assistant_identity)
    assert "AI character, not a human" in identity
    assert "Never claim human identity" in identity
    assert '"disclosure_required":true' in identity


@pytest.mark.parametrize(
    "policy,message",
    [
        ({"may_claim_to_be_human": True}, "human identity claims"),
        ({"may_claim_real_world_experiences": True}, "real-world experience claims"),
        ({"disclosure_required": False}, "cannot be disabled"),
    ],
)
def test_unsafe_identity_policy_is_rejected(monkeypatch, policy, message) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    with pytest.raises(ValueError, match=message):
        resolve_interaction_context(
            InteractionSelection(interaction_mode="character", character_id="maya"),
            character=_character(policy),
        )
