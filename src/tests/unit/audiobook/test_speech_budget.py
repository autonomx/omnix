import pytest

from app.apps.audiobook.speech_budget import (
    CODEC_STEPS_PER_SECOND,
    exhausted_speech_budget,
    has_speakable_text,
    speech_token_budget,
)


@pytest.mark.parametrize("text,speakable", [
    ("—", False), ("“…”", False), (" … ", False), ("", False),
    ("Phew…", True), ("“Yeah…”", True), ("٣", True), ("人", True), ("Wh-whoooa!", True),
])
def test_only_text_with_a_letter_or_digit_is_speakable(text, speakable):
    assert has_speakable_text(text) is speakable


def test_budget_grows_with_the_text_and_never_exceeds_the_configured_cap():
    short, long = speech_token_budget("he began."), speech_token_budget("word " * 400)
    # 4 s of slack plus 9 characters at six a second, in 80 ms codec steps.
    assert short == 69
    assert long == 2048 and speech_token_budget("word " * 400, 1000) == 1000
    assert speech_token_budget("a\t\t\tb") == speech_token_budget("a b")


def test_audio_that_ran_out_its_budget_is_a_runaway():
    assert exhausted_speech_budget(162.9, 2048)
    assert exhausted_speech_budget(7.1, speech_token_budget("he began."))
    assert not exhausted_speech_budget(0.8, speech_token_budget("he began."))
    # The slowest finished passage in rendered books used 61% of its budget.
    budget = speech_token_budget("“U-um…”")
    assert not exhausted_speech_budget(0.61 * budget / CODEC_STEPS_PER_SECOND, budget)


def test_budget_and_runaway_check_follow_the_engine_codec_rate():
    qwen, fish = speech_token_budget("he began."), speech_token_budget("he began.", steps_per_second=21.5)
    # The same allowance in seconds, counted in the faster codec's frames.
    assert fish == 119 and qwen == 69
    assert not exhausted_speech_budget(5.0, fish, 21.5)
    assert exhausted_speech_budget(5.3, fish, 21.5)
