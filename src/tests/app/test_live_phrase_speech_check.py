"""A phrase the engine renders without its words is generated again while queued audio covers the wait."""
from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from app.platform.live_voice.speech.phrase_speech_check import (
    PlaybackRunway,
    measure_take,
    missing_speech_reason,
    speech_checked_audio,
)

RATE = 24_000


def _audio(seconds: float, level: float) -> np.ndarray:
    return np.full(int(seconds * RATE), level, dtype=np.float32)


def _take(*parts: tuple[float, float], timing: dict[str, Any] | None = None) -> list[tuple[np.ndarray, int, dict[str, Any]]]:
    return [(_audio(seconds, level), RATE, dict(timing or {})) for seconds, level in parts]


SILENT = _take((2.9, 0.001))
SPOKEN = _take((1.4, 0.1))


def _pcm(chunk: Any) -> bytes:
    return (np.asarray(chunk, dtype=np.float32) * 32767).astype("<i2").tobytes()


def _checked(takes: list[list[Any]], *, runway: float = 60.0, stopped=lambda: False, text_chars: int = 15, tokens: int = 41) -> tuple[list[Any], list[dict[str, Any]], list[int]]:
    logged: list[dict[str, Any]] = []
    requested: list[int] = []

    def generate():
        requested.append(len(requested))
        return iter(takes[min(requested[-1], len(takes) - 1)])

    produced = list(speech_checked_audio(
        generate, text_chars=text_chars, max_new_tokens=tokens, to_pcm=_pcm,
        runway_seconds=lambda: runway, stopped=stopped, is_cached=lambda timing: bool(timing.get("cached")),
        on_take=lambda **fields: logged.append(fields),
    ))
    return produced, logged, requested


def test_measuring_a_take_counts_only_audible_time() -> None:
    take = measure_take([_pcm(_audio(1.0, 0.1)), _pcm(_audio(2.0, 0.001))], RATE)
    assert take.seconds == pytest.approx(3.0, abs=0.01)
    assert take.voiced_seconds == pytest.approx(1.0, abs=0.09)


@pytest.mark.parametrize(("seconds", "voiced", "chars", "tokens", "reason"), [
    # Real takes: "can't complain." came out silent in the length of its budget.
    (2.96, 0.0, 15, 41, "too_little_speech"),
    (4.48, 0.08, 33, 62, "too_little_speech"),
    # Words at their usual pace, even a quiet-sounding short phrase, stay.
    (1.36, 0.72, 15, 41, None),
    (2.96, 1.92, 33, 62, None),
    # Audible but it never ended by itself: it ran into the cap.
    (4.48, 1.60, 33, 62, "ran_to_budget"),
])
def test_what_counts_as_missing_speech(seconds: float, voiced: float, chars: int, tokens: int, reason: str | None) -> None:
    from app.platform.live_voice.speech.phrase_speech_check import SpeechTake

    assert missing_speech_reason(SpeechTake(seconds, voiced), chars, tokens) == reason


def test_a_silent_take_is_replaced_before_anyone_hears_it() -> None:
    produced, logged, requested = _checked([SILENT, SPOKEN])

    assert requested == [0, 1]
    assert [len(chunk[0]) for chunk in produced] == [len(SPOKEN[0][0])]
    assert [entry["missing"] for entry in logged] == ["too_little_speech", None]


def test_a_good_take_goes_out_with_no_second_generation() -> None:
    produced, logged, requested = _checked([SPOKEN, SILENT])

    assert requested == [0]
    assert len(produced) == 1
    assert logged[0]["missing"] is None


def test_retries_are_bounded_and_the_last_attempt_always_runs_to_its_end() -> None:
    a_little = _take((2.9, 0.001), (0.3, 0.1))
    produced, logged, requested = _checked([SILENT, SILENT, a_little, SILENT])

    assert requested == [0, 1, 2]
    assert [entry["stopped_early"] for entry in logged] == [True, True, False]
    assert [len(chunk[0]) for chunk in produced] == [len(part[0]) for part in a_little]


def test_of_complete_takes_the_one_with_the_most_speech_is_kept() -> None:
    # Audible, but each ran into its token budget: nothing stops them early and none passes.
    fuller = _take((2.6, 0.1), (0.7, 0.001))
    thinner = _take((0.7, 0.1), (1.0, 0.1), (1.6, 0.001))
    produced, logged, _requested = _checked([thinner, fuller, thinner])

    assert [entry["missing"] for entry in logged] == ["ran_to_budget"] * 3
    assert [len(chunk[0]) for chunk in produced] == [len(part[0]) for part in fuller]


def test_a_take_gone_silent_is_stopped_early_and_the_engine_released() -> None:
    closed: list[bool] = []
    generated: list[int] = []

    def silent_forever():
        try:
            for index in range(40):
                generated.append(index)
                yield _audio(0.1, 0.001), RATE, {}
        finally:
            closed.append(True)

    takes = iter([silent_forever, lambda: iter(SPOKEN)])
    logged: list[dict[str, Any]] = []
    produced = list(speech_checked_audio(
        lambda: next(takes)(), text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda: 60.0,
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **fields: logged.append(fields),
    ))

    assert closed == [True]
    assert len(generated) < 20  # stopped after about 1.2 s of the 4 s it would have made
    assert logged[0]["stopped_early"] is True
    assert logged[0]["missing"] == "too_little_speech"
    assert [len(chunk[0]) for chunk in produced] == [len(SPOKEN[0][0])]


def test_a_pause_after_enough_speech_is_never_stopped() -> None:
    # "after all the work stress," then a long pause: the words are out, so the take is kept.
    spoken_then_quiet = _take((1.2, 0.1), (1.0, 0.001))
    produced, logged, requested = _checked([spoken_then_quiet, SPOKEN], text_chars=26, tokens=54)

    assert requested == [0]
    assert logged[0]["stopped_early"] is False
    assert len(produced) == 2


def test_a_take_is_not_stopped_when_there_is_no_time_for_another() -> None:
    answers = iter([60.0])
    logged: list[dict[str, Any]] = []
    takes = iter([SILENT, SPOKEN])
    produced = list(speech_checked_audio(
        lambda: iter(next(takes)), text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda: next(answers, 0.0),
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **fields: logged.append(fields),
    ))

    assert [entry["stopped_early"] for entry in logged] == [False]
    assert [len(chunk[0]) for chunk in produced] == [len(SILENT[0][0])]


def test_without_enough_queued_audio_the_phrase_streams_as_it_always_did() -> None:
    order: list[str] = []

    def generate():
        for chunk in SPOKEN + SPOKEN:
            order.append("generated")
            yield chunk

    for _chunk in speech_checked_audio(
        generate, text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda: 0.2,
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **_fields: None,
    ):
        order.append("sent")

    assert order == ["generated", "sent", "generated", "sent"]


def _with_likeness(
    takes: list[list[Any]], scores: list[float | None], *, runway: float = 60.0, text_chars: int = 33,
) -> tuple[list[Any], list[dict[str, Any]], int]:
    logged: list[dict[str, Any]] = []
    source = iter(takes)
    answers = iter(scores)
    asked: list[int] = []

    def likeness(pcm: list[bytes], sample_rate: int) -> float | None:
        asked.append(sample_rate)
        assert all(isinstance(chunk, bytes) for chunk in pcm)
        return next(answers)

    produced = list(speech_checked_audio(
        lambda: iter(next(source)), text_chars=text_chars, max_new_tokens=120, to_pcm=_pcm, runway_seconds=lambda: runway,
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **fields: logged.append(fields), likeness=likeness,
    ))
    return produced, logged, len(asked)


LONG_A = _take((2.5, 0.1))
LONG_B = _take((3.0, 0.1))
LONG_C = _take((3.5, 0.1))


def test_a_take_in_another_voice_is_generated_again() -> None:
    produced, logged, asked = _with_likeness([LONG_A, LONG_B], [0.05, 0.71])

    assert asked == 2
    assert [entry["missing"] for entry in logged] == ["different_voice", None]
    assert [entry["likeness"] for entry in logged] == [0.05, 0.71]
    assert [len(chunk[0]) for chunk in produced] == [len(LONG_B[0][0])]


@pytest.mark.parametrize(("score", "heard_as_someone_else"), [(0.05, True), (0.41, True), (0.50, False), (0.55, False)])
def test_the_line_sits_where_the_voices_owner_heard_it(score: float, heard_as_someone_else: bool) -> None:
    # Real takes, judged by ear against the reference.
    _produced, logged, _asked = _with_likeness([LONG_A, LONG_B], [score, 0.71])

    assert (logged[0]["missing"] == "different_voice") is heard_as_someone_else


def test_when_every_take_is_in_another_voice_the_closest_goes_out() -> None:
    produced, logged, _asked = _with_likeness([LONG_A, LONG_B, LONG_C], [0.05, 0.33, 0.12])

    assert len(logged) == 3
    assert [len(chunk[0]) for chunk in produced] == [len(LONG_B[0][0])]


def test_an_unavailable_likeness_check_never_costs_a_phrase() -> None:
    produced, logged, asked = _with_likeness([LONG_A, LONG_B], [None])

    assert asked == 1
    assert logged[0]["missing"] is None
    assert logged[0]["likeness"] is None
    assert [len(chunk[0]) for chunk in produced] == [len(LONG_A[0][0])]


def test_too_little_speech_to_judge_a_voice_is_not_judged() -> None:
    # Scores on under 1.2 s of speech are unreliable: real takes of the right voice usually score low.
    short = _take((1.1, 0.1))
    produced, logged, asked = _with_likeness([short], [0.01], text_chars=20)

    assert asked == 0
    assert logged[0]["missing"] is None
    assert len(produced) == 1


def test_a_short_line_with_enough_speech_is_judged() -> None:
    # "so everyone gets their share." had 1.44 s of speech, and got by unjudged at the old 1.6 s minimum.
    short = _take((1.44, 0.1))
    produced, logged, asked = _with_likeness([short, LONG_A], [0.09, 0.71], text_chars=29)

    assert asked == 2
    assert [entry["missing"] for entry in logged] == ["different_voice", None]
    assert [len(chunk[0]) for chunk in produced] == [len(LONG_A[0][0])]


@pytest.mark.parametrize(("text_chars", "runway", "held"), [
    # A 46-character line takes about 2.3 s to generate, however large its token budget.
    (46, 2.4, True),
    (46, 2.2, False),
    (15, 0.8, True),
    (15, 0.7, False),
])
def test_a_phrase_is_held_on_the_time_it_should_really_take(text_chars: int, runway: float, held: bool) -> None:
    holds: list[bool] = []
    list(speech_checked_audio(
        lambda: iter(LONG_A), text_chars=text_chars, max_new_tokens=500, to_pcm=_pcm, runway_seconds=lambda: runway,
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **_fields: None, on_hold=lambda: holds.append(True),
    ))

    assert bool(holds) is held


def test_it_says_when_a_phrase_is_being_held_and_only_then() -> None:
    held: list[bool] = []
    for runway in (60.0, 0.2):
        list(speech_checked_audio(
            lambda: iter(SPOKEN), text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda seconds=runway: seconds,
            stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **_fields: None,
            on_hold=lambda seconds=runway: held.append(seconds),
        ))

    assert held == [60.0]


def test_a_cached_speculation_is_passed_straight_through() -> None:
    cached = _take((0.2, 0.001), (0.2, 0.001), timing={"cached": True})
    produced, logged, requested = _checked([cached])

    assert requested == [0]
    assert len(produced) == 2
    assert logged == []


def test_an_interrupted_phrase_stops_and_sends_nothing() -> None:
    produced, _logged, requested = _checked([SILENT, SPOKEN], stopped=lambda: True)

    assert produced == []
    assert requested == [0]


def test_a_failed_retry_keeps_the_take_already_made() -> None:
    def failing():
        raise RuntimeError("engine gone")
        yield  # pragma: no cover

    attempts = iter([lambda: iter(SILENT), failing])
    logged: list[dict[str, Any]] = []
    produced = list(speech_checked_audio(
        lambda: next(attempts)(), text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda: 60.0,
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **fields: logged.append(fields),
    ))

    assert [len(chunk[0]) for chunk in produced] == [len(SILENT[0][0])]


def test_the_first_attempts_failure_still_reaches_the_caller() -> None:
    def failing():
        raise RuntimeError("engine gone")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="engine gone"):
        list(speech_checked_audio(
            failing, text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda: 60.0,
            stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **_fields: None,
        ))


def test_the_runway_is_what_was_sent_less_what_has_played_since() -> None:
    runway = PlaybackRunway()
    assert runway.seconds(generation_epoch=3, now=100.0) == 0.0

    runway.record(generation_epoch=3, samples=RATE * 5, sample_rate=RATE, now=100.0)
    assert runway.seconds(generation_epoch=3, now=102.0) == pytest.approx(3.0)
    runway.record(generation_epoch=3, samples=RATE * 2, sample_rate=RATE, now=102.0)
    assert runway.seconds(generation_epoch=3, now=103.0) == pytest.approx(4.0)
    assert runway.seconds(generation_epoch=3, now=500.0) == 0.0
    # An interrupted reply's queue is gone: the next generation starts from nothing.
    assert runway.seconds(generation_epoch=4, now=103.0) == 0.0
