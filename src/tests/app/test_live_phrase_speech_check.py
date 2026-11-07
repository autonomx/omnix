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
    # Real takes with every word, spoken quickly: these used to be retried for nothing.
    (1.60, 1.52, 40, 70, None),
    (1.20, 1.04, 30, 59, None),
    # Real takes that lost words, the first just over the line: "or you're lost. Which is it?" heard as "or you are lost".
    (1.60, 0.96, 28, 56, "too_little_speech"),
    (3.20, 0.80, 62, 96, "too_little_speech"),
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


def test_a_take_with_some_of_its_words_gets_two_retries_and_the_last_runs_to_its_end() -> None:
    a_little = _take((0.3, 0.1), (2.6, 0.001))
    produced, logged, requested = _checked([a_little])

    assert requested == [0, 1, 2]
    assert [entry["stopped_early"] for entry in logged] == [True, True, False]
    assert sum(len(chunk[0]) for chunk in produced) == sum(len(part[0]) for part in a_little)


def test_a_silent_take_is_tried_longer_than_a_partial_one_and_never_plays_to_its_end() -> None:
    # Real: three silent takes in a row, and the last played as 3.9 s of silence with a sentence lost.
    long_silence = _take(*[(0.32, 0.001)] * 12)
    produced, logged, requested = _checked([long_silence])

    assert requested == [0, 1, 2, 3, 4]
    assert [entry["stopped_early"] for entry in logged] == [True] * 5
    assert sum(len(chunk[0]) for chunk in produced) / RATE < 1.5


def test_a_fifth_take_that_speaks_is_the_one_heard() -> None:
    long_silence = _take(*[(0.32, 0.001)] * 12)
    produced, logged, requested = _checked([long_silence, long_silence, long_silence, long_silence, SPOKEN])

    assert requested == [0, 1, 2, 3, 4]
    assert logged[-1]["missing"] is None
    assert [len(chunk[0]) for chunk in produced] == [len(SPOKEN[0][0])]


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


def _short_of_time(takes: list[Any]) -> tuple[list[Any], list[dict[str, Any]]]:
    """The phrase is held (enough queued audio at the start), then there is no time for a retry by the book."""
    answers = iter([60.0])
    logged: list[dict[str, Any]] = []
    source = iter(takes)
    produced = list(speech_checked_audio(
        lambda: iter(next(source)), text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda: next(answers, 0.0),
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **fields: logged.append(fields),
    ))
    return produced, logged


def test_a_take_with_some_of_its_words_is_kept_when_there_is_no_time_for_another() -> None:
    partial = _take((0.4, 0.1), (2.5, 0.001))
    produced, logged = _short_of_time([partial, SPOKEN])

    assert [entry["stopped_early"] for entry in logged] == [False]
    assert [len(chunk[0]) for chunk in produced] == [len(part[0]) for part in partial]


def test_a_silent_take_is_never_played_for_lack_of_time() -> None:
    # A real call: 4 s of silence and a lost sentence, because a retry fell 0.12 s short of its margin.
    produced, logged = _short_of_time([SILENT, SPOKEN])

    assert [len(chunk[0]) for chunk in produced] == [len(SPOKEN[0][0])]
    assert logged[0]["missing"] == "too_little_speech"
    assert logged[1] == {"attempt": 1, "streamed": True}


def test_the_retry_of_a_silent_take_goes_out_as_it_is_made() -> None:
    order: list[str] = []

    def speaking():
        for chunk in SPOKEN + SPOKEN:
            order.append("generated")
            yield chunk

    takes = iter([lambda: iter(SILENT), speaking])
    answers = iter([60.0])
    for _chunk in speech_checked_audio(
        lambda: next(takes)(), text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda: next(answers, 0.0),
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **_fields: None,
    ):
        order.append("sent")

    assert order == ["generated", "sent", "generated", "sent"]


def test_a_failed_retry_of_a_silent_take_still_sends_what_it_has() -> None:
    def refused():
        raise RuntimeError("engine busy")

    attempts = iter([lambda: iter(SILENT), refused])
    answers = iter([60.0])
    logged: list[dict[str, Any]] = []
    produced = list(speech_checked_audio(
        lambda: next(attempts)(), text_chars=15, max_new_tokens=41, to_pcm=_pcm, runway_seconds=lambda: next(answers, 0.0),
        stopped=lambda: False, is_cached=lambda _timing: False, on_take=lambda **fields: logged.append(fields),
    ))

    assert len(produced) == 1  # never nothing: the phrase's slot in the reply is kept
    assert logged[1]["streamed"] is True


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


def test_a_cached_speculation_that_speaks_is_passed_straight_through() -> None:
    cached = _take((0.2, 0.1), (0.2, 0.1), timing={"cached": True})
    produced, logged, requested = _checked([cached])

    assert requested == [0]
    assert len(produced) == 2
    assert logged == []


def test_a_cached_speculation_with_no_words_is_replaced_unheard() -> None:
    # Real: "Yeah, well," a reply's first phrase from the cache, played as 2.7 s of silence.
    cached = _take(*[(0.32, 0.001)] * 8, timing={"cached": True})
    produced, logged, requested = _checked([cached, SPOKEN], runway=0.0, text_chars=11)

    assert requested == [0, 1]
    assert [len(chunk[0]) for chunk in produced] == [len(SPOKEN[0][0])]
    assert logged[0]["missing"] == "too_little_speech"


def test_a_first_phrase_with_no_words_is_replaced_before_anyone_hears_it() -> None:
    silent = _take(*[(0.32, 0.001)] * 8)
    produced, logged, requested = _checked([silent, silent, SPOKEN], runway=0.0)

    assert requested == [0, 1, 2]
    assert [len(chunk[0]) for chunk in produced] == [len(SPOKEN[0][0])]
    assert [entry["streamed"] for entry in logged] == [True, True]


def test_a_first_phrase_starts_at_its_first_voice_keeping_one_quiet_chunk_for_a_soft_first_sound() -> None:
    leading = _take((0.16, 0.001), (0.16, 0.001), (0.16, 0.002), (0.3, 0.1), (0.3, 0.1))
    produced, logged, requested = _checked([leading], runway=0.0)

    assert requested == [0]
    assert [float(np.asarray(chunk[0])[0]) for chunk in produced] == pytest.approx([0.002, 0.1, 0.1])
    assert logged == []


def test_a_cached_speculation_keeps_its_lead_in_because_its_portrait_has_a_copy() -> None:
    cached = _take((0.16, 0.001), (0.16, 0.001), (0.3, 0.1), timing={"cached": True})
    produced, _logged, requested = _checked([cached], runway=0.0)

    assert requested == [0]
    assert len(produced) == 3


def test_a_first_phrase_that_never_speaks_gives_up_and_stays_short() -> None:
    silent = _take(*[(0.32, 0.001)] * 12)
    produced, logged, requested = _checked([silent], runway=0.0)

    assert requested == [0, 1, 2, 3, 4]
    assert sum(len(chunk[0]) for chunk in produced) / RATE < 1.5


def test_a_first_phrase_that_ends_without_speaking_is_tried_again() -> None:
    too_short = _take((0.3, 0.001))
    produced, _logged, requested = _checked([too_short, SPOKEN], runway=0.0)

    assert requested == [0, 1]
    assert [len(chunk[0]) for chunk in produced] == [len(SPOKEN[0][0])]


@pytest.mark.parametrize("take", [_take((0.1, 0.1)), _take((0.008, 0.1))])
def test_a_first_phrase_too_short_to_reach_the_bar_is_not_thrown_away(take) -> None:
    produced, logged, requested = _checked([take, SPOKEN], runway=0.0)

    assert requested == [0]
    assert len(produced) == 1
    assert logged == []


def test_a_first_phrase_interrupted_while_waiting_for_voice_sends_nothing() -> None:
    produced, _logged, _requested = _checked([SILENT], runway=0.0, stopped=lambda: True)

    assert produced == []


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


def _chunked(*parts: tuple[float, float]) -> list[tuple[np.ndarray, int, dict[str, Any]]]:
    """A take as the engine streams it, in 80 ms chunks, so a silence can be noticed as it happens."""
    chunks = []
    for seconds, level in parts:
        for _ in range(round(seconds / 0.08)):
            chunks.append((_audio(0.08, level), RATE, {}))
    return chunks


def _played_seconds(produced: list[Any]) -> float:
    return sum(len(chunk[0]) for chunk in produced) / RATE


def test_a_take_that_starts_speaking_and_loses_its_words_is_said_again_whole() -> None:
    # 2026-11-06: "Right. No. Not really. I had one once," with no runway played "Right." and then near-silence.
    lost = _chunked((0.4, 0.1), (4.5, 0.001))
    whole = _chunked((2.4, 0.1))
    produced, logged, requested = _checked([lost, whole], runway=0.0, text_chars=38)

    assert len(requested) == 2
    assert any(entry.get("missing") == "went_silent_midway" for entry in logged)
    # The start that was heard, at most 1.2 s of the quiet before it was noticed, then the whole phrase again.
    assert 2.4 + 0.4 <= _played_seconds(produced) <= 2.4 + 0.4 + 1.3


def test_a_second_loss_is_cut_short_instead_of_played() -> None:
    lost = _chunked((0.4, 0.1), (4.5, 0.001))
    produced, logged, requested = _checked([lost, lost, _chunked((2.4, 0.1))], runway=0.0, text_chars=38)

    assert len(requested) == 2  # one replay, never a third take of the same words
    assert _played_seconds(produced) <= 2 * (0.4 + 1.3)


def test_a_take_that_keeps_speaking_plays_whole_once() -> None:
    speaking = _chunked((0.4, 0.1), (0.3, 0.001), (2.0, 0.1))
    produced, logged, requested = _checked([speaking], runway=0.0, text_chars=38)

    assert len(requested) == 1
    assert not any(entry.get("missing") for entry in logged)
    assert _played_seconds(produced) == pytest.approx(2.72, abs=0.01)


def test_a_cached_speculation_still_goes_out_as_made() -> None:
    cached = [(chunk, rate, {"cached": True}) for chunk, rate, _timing in _chunked((0.4, 0.1), (4.5, 0.001))]
    produced, logged, requested = _checked([cached], runway=0.0, text_chars=38)

    assert len(requested) == 1  # its portrait has a copy of it
    assert _played_seconds(produced) == pytest.approx(4.88, abs=0.01)
