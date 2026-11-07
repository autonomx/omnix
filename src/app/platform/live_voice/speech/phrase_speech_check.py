"""Generate a live phrase again when the engine rendered its length without its words.

Qwen sometimes emits near-silence for a phrase instead of speaking it, often running on until its token budget stops
it. It is random: the same phrase speaks on another take. Real takes of a cloned voice came out silent in 16% of
renders and 5% after one retry, with 7 of 127 good takes retried needlessly.

A phrase can only be judged once it is complete or has clearly gone silent, so it is held back whole only while audio
already sent covers the wait. Generation is several times faster than playback, so after a reply's first phrases there
is usually plenty. Before that, or when the check would risk an audible gap, the phrase streams from its first voice:
nothing is sent until a take has started speaking, so a silent one is replaced before anyone hears it, which costs only
the moments it takes to tell. A cached speculation goes the same way: it was made by the same engine.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Generator, Iterable, Iterator
from dataclasses import dataclass
from itertools import chain
from typing import Any

logger = logging.getLogger(__name__)

CODEC_STEPS_PER_SECOND = 12.5
# Generating a second of speech took 0.37 s on real takes; live phrases share the service, so assume worse.
CAUTIOUS_GENERATION_SECONDS_PER_AUDIO_SECOND = 0.6
# Normal speech; slower takes run long, but the token budget would overstate the wait and hold back too few phrases.
EXPECTED_CHARS_PER_SECOND = 12.0
MAX_RETRIES = 2
# A take with no words is worth nothing, and telling takes about 0.5 s. Real calls: 13% of first takes came out silent,
# 28% of retries, and three in a row lost a sentence to 3.9 s of silence (2026-11-04).
MAX_SILENT_RETRIES = 4
# A portrait renders about this far ahead of playback (StreamSettings.render_ahead_seconds), and a phrase's held end
# frames commit with padding just before their play time unless the next phrase has arrived. Holding a phrase is safe
# for it only when the phrase still arrives this far ahead.
PORTRAIT_RENDER_LEAD_SECONDS = 1.0

_FRAME_SECONDS = 0.08
# The level the browser's mouth treats as closed. Speech stays above it between words only briefly.
_QUIET_RMS = 0.015
# Speech is rarely faster than this, so less voiced time than this means words are missing. Real takes scored by
# transcribing them, 70 per voice (2026-11-04): whole takes reached 28.85 on the faster voice, and a take that had lost
# its last three words was 29.17 on the slower one. At 25, 18 of the faster voice's 25 flagged takes had every word.
_FASTEST_VOICED_CHARS_PER_SECOND = 29.0
# Under this share of that time a take is worth nothing to the listener: a retry goes ahead however little audio is
# queued. (A real take: 28 characters, 4.08 s, nothing voiced, retry refused 0.12 s short of its margin, 2026-11-04.)
_HARDLY_SPOKEN_SHARE = 0.5
# Audio this close to its budget ran into the cap instead of ending on its own.
_RAN_TO_BUDGET_FRACTION = 0.88
# On real takes this stops 35 of 37 silent ones about 1.7 s early, and 17 of 368 good ones, which costs only a retry.
_GONE_SILENT_SECONDS = 1.2
# Takes in the right voice score about 0.7 against its clip, and another person's voice 0.22 at most. By ear, real takes
# at 0.05 and 0.41 sounded like someone else and those at 0.50 and 0.55 did not; 3 of 258 spoken takes fall below this.
# With less speech than the next line the score is unreliable; just above it about 1 good take in 10 scores low, which
# costs only a retry.
_DIFFERENT_VOICE_SCORE = 0.45
_LIKENESS_MIN_VOICED_SECONDS = 1.2
# Enough voice to tell a take has started speaking, and not just clicked. A frame alone is not enough for this.
_FIRST_VOICE_SECONDS = 2 * _FRAME_SECONDS


@dataclass(frozen=True)
class SpeechTake:
    seconds: float
    voiced_seconds: float


class PlaybackRunway:
    """How much audio sent to the browser for a reply has yet to play, in seconds."""

    def __init__(self) -> None:
        self._generation_epoch: int | None = None
        self._started_at = 0.0
        self._sent_seconds = 0.0

    def record(self, generation_epoch: int, samples: int, sample_rate: int, now: float) -> None:
        if generation_epoch != self._generation_epoch:
            self._generation_epoch = generation_epoch
            self._started_at = now
            self._sent_seconds = 0.0
        self._sent_seconds += samples / max(1, sample_rate)

    def seconds(self, generation_epoch: int, now: float) -> float:
        # Another generation's queue was cancelled with it.
        if generation_epoch != self._generation_epoch:
            return 0.0
        return max(0.0, self._sent_seconds - (now - self._started_at))


class TakeWatch:
    """A take's audible time and current quiet stretch, as its audio arrives."""

    def __init__(self, sample_rate: int) -> None:
        self._rate = max(1, sample_rate)
        self._frame_samples = max(1, int(self._rate * _FRAME_SECONDS))
        self._pending = b""
        self._samples = 0
        self._voiced_frames = 0
        self._quiet_run_frames = 0

    def add(self, pcm: bytes) -> None:
        self._samples += len(pcm) // 2
        self._pending += pcm
        count = len(self._pending) // (self._frame_samples * 2)
        if not count:
            return
        # Loaded with the first take: the gateway starts without numpy.
        import numpy as np

        used = count * self._frame_samples * 2
        samples = np.frombuffer(self._pending[:used], dtype="<i2").astype(np.float32) / 32768.0
        self._pending = self._pending[used:]
        levels = np.sqrt((samples.reshape(count, self._frame_samples) ** 2).mean(axis=1))
        for level in levels:
            if level >= _QUIET_RMS:
                self._voiced_frames += 1
                self._quiet_run_frames = 0
            else:
                self._quiet_run_frames += 1

    @property
    def take(self) -> SpeechTake:
        return SpeechTake(self._samples / self._rate, self._voiced_frames * self._frame_samples / self._rate)

    def gone_silent(self, text_chars: int) -> bool:
        """Quiet for a long while with too little said for the text: on real takes this is the words being lost."""
        quiet_seconds = self._quiet_run_frames * self._frame_samples / self._rate
        return quiet_seconds >= _GONE_SILENT_SECONDS and self.take.voiced_seconds < text_chars / _FASTEST_VOICED_CHARS_PER_SECOND


def measure_take(pcm_chunks: Iterable[bytes], sample_rate: int) -> SpeechTake:
    watch = TakeWatch(sample_rate)
    for pcm in pcm_chunks:
        watch.add(pcm)
    return watch.take


def budget_used(take: SpeechTake, max_new_tokens: int) -> float:
    return take.seconds * CODEC_STEPS_PER_SECOND / max(1, max_new_tokens)


def missing_speech_reason(take: SpeechTake, text_chars: int, max_new_tokens: int) -> str | None:
    """Why this take probably lacks its words, or None when it looks spoken."""
    if take.voiced_seconds < text_chars / _FASTEST_VOICED_CHARS_PER_SECOND:
        return "too_little_speech"
    if budget_used(take, max_new_tokens) >= _RAN_TO_BUDGET_FRACTION:
        return "ran_to_budget"
    return None


def _hardly_spoken(take: SpeechTake, text_chars: int) -> bool:
    return take.voiced_seconds < text_chars / _FASTEST_VOICED_CHARS_PER_SECOND * _HARDLY_SPOKEN_SHARE


def _rest_until_silent(
    pending: Iterator[tuple[Any, int, Any]],
    watch: TakeWatch,
    *,
    text_chars: int,
    to_pcm: Callable[[Any], bytes],
    stopped: Callable[[], bool],
) -> Generator[tuple[Any, int, Any], None, bool]:
    """The rest of a speaking take, until it goes silent with too little said for its text: then True, unplayed."""
    for chunk in pending:
        if stopped():
            return False
        watch.add(to_pcm(chunk[0]))
        if watch.gone_silent(text_chars):
            return True
        yield chunk
    return False


def _streamed_from_first_voice(
    generate: Callable[[], Iterator[tuple[Any, int, Any]]],
    *,
    text_chars: int,
    to_pcm: Callable[[Any], bytes],
    stopped: Callable[[], bool],
    is_cached: Callable[[Any], bool],
    on_take: Callable[..., None],
    attempt: int = 0,
    fallback: list[tuple[Any, int, Any]] | None = None,
    started: tuple[tuple[Any, int, Any], Iterator[tuple[Any, int, Any]]] | None = None,
) -> Iterator[tuple[Any, int, Any]]:
    """A take as it is made, from the moment it speaks; a take that does not speak is replaced unheard.

    ``started`` is a stream whose first chunk has already been read. When no take speaks, what there is goes out.
    """
    last: list[tuple[Any, int, Any]] = list(fallback or [])
    replayed = False
    while True:
        stream: Iterator[tuple[Any, int, Any]] | None = None
        chunks: list[tuple[Any, int, Any]] = []
        watch: TakeWatch | None = None
        first_voiced: int | None = None
        lost_midway = False
        try:
            if started is not None:
                first, stream = started
                started = None
                pending = chain([first], stream)
            else:
                try:
                    stream = pending = generate()
                except Exception:
                    if attempt == 0:
                        raise
                    logger.warning("A retry of a phrase with no speech failed", exc_info=True)
                    yield from last
                    return
            try:
                for chunk in pending:
                    if stopped():
                        return
                    chunks.append(chunk)
                    watch = watch or TakeWatch(chunk[1])
                    watch.add(to_pcm(chunk[0]))
                    if first_voiced is None and watch.take.voiced_seconds > 0:
                        first_voiced = len(chunks) - 1
                    if watch.take.voiced_seconds >= _FIRST_VOICE_SECONDS:
                        # The wait for a voice is won back by not playing the quiet it waited through. One chunk stays
                        # for a soft first sound. A cached speculation goes out whole: its portrait has a copy of it.
                        lead = 0 if is_cached(chunks[0][2]) else max(0, (first_voiced or 0) - 1)
                        yield from chunks[lead:]
                        if is_cached(chunks[0][2]):
                            yield from pending
                            return
                        # A take can start speaking and then lose its words: "Right." and then 4 s of near-silence
                        # where "No. Not really. I had one once," should be (2026-11-06). Its start has been heard,
                        # so the whole phrase is said again, once; a second loss is cut short instead of played.
                        went_silent = yield from _rest_until_silent(
                            pending, watch, text_chars=text_chars, to_pcm=to_pcm, stopped=stopped,
                        )
                        if not went_silent or replayed or stopped():
                            return
                        replayed = lost_midway = True
                        break
                    if watch.gone_silent(text_chars):
                        break
                else:
                    # It ended before it could reach the bar: only a take long enough to judge and with no voice is silent.
                    ended = watch.take if watch else SpeechTake(0.0, 0.0)
                    if ended.voiced_seconds > 0 or ended.seconds < _FRAME_SECONDS:
                        yield from chunks
                        return
            except Exception as exc:
                if attempt == 0 and not last:
                    raise
                # Nothing of this take has gone out, so what was already made still can.
                logger.warning("A retry of a phrase with no speech failed", exc_info=True)
                on_take(attempt=attempt, error=type(exc).__name__, streamed=True)
                yield from (chunks or last)
                return
        finally:
            # Frees the engine now rather than whenever the abandoned generator is collected.
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        take = watch.take if watch else SpeechTake(0.0, 0.0)
        if lost_midway:
            on_take(attempt=attempt, missing="went_silent_midway", streamed=True, seconds=round(take.seconds, 3),
                    voiced_seconds=round(take.voiced_seconds, 3))
            last = []  # what it did say has been heard: never play it again as a fallback
            if stopped():
                return
            attempt += 1
            continue
        on_take(attempt=attempt, missing="too_little_speech", streamed=True, seconds=round(take.seconds, 3),
                voiced_seconds=round(take.voiced_seconds, 3))
        last = chunks or last
        if stopped():
            return
        if attempt >= MAX_SILENT_RETRIES:
            yield from last
            return
        attempt += 1


def speech_checked_audio(
    generate: Callable[[], Iterator[tuple[Any, int, Any]]],
    *,
    text_chars: int,
    max_new_tokens: int,
    to_pcm: Callable[[Any], bytes],
    runway_seconds: Callable[[], float],
    stopped: Callable[[], bool],
    is_cached: Callable[[Any], bool],
    on_take: Callable[..., None],
    on_hold: Callable[[], None] = lambda: None,
    likeness: Callable[[list[bytes], int], float | None] = lambda _pcm, _sample_rate: None,
) -> Iterator[tuple[Any, int, Any]]:
    """The phrase's audio chunks: checked and retried when queued audio allows, otherwise streamed untouched."""
    expected_wait = text_chars / EXPECTED_CHARS_PER_SECOND * CAUTIOUS_GENERATION_SECONDS_PER_AUDIO_SECOND
    if runway_seconds() < expected_wait:
        yield from _streamed_from_first_voice(
            generate, text_chars=text_chars, to_pcm=to_pcm, stopped=stopped, is_cached=is_cached, on_take=on_take,
        )
        return

    on_hold()
    best: list[tuple[Any, int, Any]] | None = None
    best_rank: tuple[bool, bool, float, float] | None = None
    for attempt in range(MAX_SILENT_RETRIES + 1):
        started_at = time.perf_counter()
        chunks: list[tuple[Any, int, Any]] = []
        pcm: list[bytes] = []
        watch: TakeWatch | None = None
        stopped_early = False
        stream = None
        try:
            stream = generate()
            for chunk in stream:
                if stopped():
                    return
                if not chunks and is_cached(chunk[2]):
                    # A promoted speculation: its portrait and startup runway depend on it arriving as made.
                    yield from _streamed_from_first_voice(
                        generate, text_chars=text_chars, to_pcm=to_pcm, stopped=stopped, is_cached=is_cached,
                        on_take=on_take, attempt=attempt, fallback=best, started=(chunk, stream),
                    )
                    return
                chunks.append(chunk)
                watch = watch or TakeWatch(chunk[1])
                pcm.append(to_pcm(chunk[0]))
                watch.add(pcm[-1])
                # A take with some of its words runs to its end when it is the last or there is no time for another.
                if watch.gone_silent(text_chars) and (
                    _hardly_spoken(watch.take, text_chars)
                    or (attempt < MAX_RETRIES and runway_seconds() >= expected_wait)
                ):
                    stopped_early = True
                    break
        except Exception as exc:
            if best is None:
                raise
            on_take(attempt=attempt, error=type(exc).__name__)
            break
        finally:
            # Frees the engine now rather than whenever the abandoned generator is collected.
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        take = watch.take if watch else SpeechTake(0.0, 0.0)
        reason = "too_little_speech" if stopped_early else missing_speech_reason(take, text_chars, max_new_tokens)
        judged = not stopped_early and take.voiced_seconds >= _LIKENESS_MIN_VOICED_SECONDS
        score = likeness(pcm, chunks[0][1]) if judged else None
        if reason is None and score is not None and score < _DIFFERENT_VOICE_SCORE:
            reason = "different_voice"
        on_take(
            attempt=attempt,
            missing=reason,
            likeness=score,
            stopped_early=stopped_early,
            seconds=round(take.seconds, 3),
            voiced_seconds=round(take.voiced_seconds, 3),
            budget_used=round(budget_used(take, max_new_tokens), 3),
            generation_ms=round((time.perf_counter() - started_at) * 1000, 3),
        )
        if reason is None:
            best = chunks
            break
        # A stopped take is cut short, so any complete one beats it; then the one with its words, in the closest voice.
        rank = (not stopped_early, judged, 1.0 if score is None else score, take.voiced_seconds)
        if best_rank is None or rank > best_rank:
            best, best_rank = chunks, rank
        hardly_spoken = _hardly_spoken(take, text_chars)
        if stopped() or attempt >= (MAX_SILENT_RETRIES if hardly_spoken else MAX_RETRIES):
            break
        if runway_seconds() >= expected_wait:
            continue
        if hardly_spoken:
            # Playing this take is seconds of silence and the words lost; waiting for another costs less at worst.
            # Nothing is held any longer: it goes out as it is made.
            on_take(attempt=attempt + 1, streamed=True)
            yield from _streamed_from_first_voice(
                generate, text_chars=text_chars, to_pcm=to_pcm, stopped=stopped, is_cached=is_cached,
                on_take=on_take, attempt=attempt + 1, fallback=best,
            )
            return
        break
    yield from best or ()
