"""Generate a live phrase again when the engine rendered its length without its words.

Qwen sometimes emits near-silence for a phrase instead of speaking it, often running on until its token budget stops
it. It is random: the same phrase speaks on another take. Real takes of a cloned voice came out silent in 16% of
renders and 5% after one retry, with 7 of 127 good takes retried needlessly.

A phrase can only be judged once it is complete or has clearly gone silent, so it is held back only while audio
already sent covers the wait.
Generation is several times faster than playback, so after a reply's first phrases there is usually plenty; before
that, or when the check would risk an audible gap, the phrase streams as it always did.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np

CODEC_STEPS_PER_SECOND = 12.5
# Generating a second of speech took 0.37 s on real takes; live phrases share the service, so assume worse.
CAUTIOUS_GENERATION_SECONDS_PER_AUDIO_SECOND = 0.6
# Normal speech; slower takes run long, but the token budget would overstate the wait and hold back too few phrases.
EXPECTED_CHARS_PER_SECOND = 12.0
MAX_RETRIES = 2
# A portrait renders about this far ahead of playback (StreamSettings.render_ahead_seconds), and a phrase's held end
# frames commit with padding just before their play time unless the next phrase has arrived. Holding a phrase is safe
# for it only when the phrase still arrives this far ahead.
PORTRAIT_RENDER_LEAD_SECONDS = 1.0

_FRAME_SECONDS = 0.08
# The level the browser's mouth treats as closed. Speech stays above it between words only briefly.
_QUIET_RMS = 0.015
# Speech is rarely faster than this, so less voiced time than this means words are missing.
_FASTEST_VOICED_CHARS_PER_SECOND = 25.0
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
        yield from generate()
        return

    on_hold()
    best: list[tuple[Any, int, Any]] | None = None
    best_rank: tuple[bool, bool, float, float] | None = None
    for attempt in range(MAX_RETRIES + 1):
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
                    yield chunk
                    yield from stream
                    return
                chunks.append(chunk)
                watch = watch or TakeWatch(chunk[1])
                pcm.append(to_pcm(chunk[0]))
                watch.add(pcm[-1])
                # The last attempt runs to its end, and so does any with no time for another: something real must go out.
                if attempt < MAX_RETRIES and watch.gone_silent(text_chars) and runway_seconds() >= expected_wait:
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
        if stopped() or runway_seconds() < expected_wait:
            break
    yield from best or ()
