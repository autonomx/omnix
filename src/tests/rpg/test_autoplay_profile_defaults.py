from types import SimpleNamespace


def test_smoke_100_profile_forces_100_turns():
    from tests.rpg.autoplay_llm_campaign import _apply_autoplay_profile_defaults

    args = SimpleNamespace(
        autoplay_profile="smoke_100",
        turns=None,
        checkpoint_every=None,
        transcript_detail="auto",
    )

    result = _apply_autoplay_profile_defaults(args)

    assert result.turns == 100
    assert result.checkpoint_every == 25


def test_custom_profile_defaults_to_25_turns():
    from tests.rpg.autoplay_llm_campaign import _apply_autoplay_profile_defaults

    args = SimpleNamespace(
        autoplay_profile="custom",
        turns=None,
        checkpoint_every=None,
        transcript_detail="auto",
    )

    result = _apply_autoplay_profile_defaults(args)

    assert result.turns == 25