"""The live portrait's hop scheduler (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, "Streaming method").

One ``PortraitStream`` serves one call. TTS audio arrives phrase by phrase (``phrase_start``, PCM blocks with
their sample offsets, ``phrase_done``); the phrases of an output are one continuous audio timeline at 16 kHz,
25 video frames per second. FLOAT generates motion over 50-frame windows conditioned on a 10-frame carry, so
the scheduler slides a window by a hop and commits only the frames whose audio has ``lookahead`` frames of
real audio after them. Held frames at the end of a phrase are committed (with padding) when the next phrase's
audio arrives, when their play-time deadline comes, or at ``output_end``.

Every committed frame is decoded in micro-batches and stamped with the segment (phrase) it falls in and its
offset in that segment's own samples, which is what the browser's audio clock counts. Between micro-batches
the stream checks for cancellation and the TTS priority pause.

This module holds no model: a ``MotionSession`` (``services.portrait.float_runtime``) runs the passes and
decodes, so the planning here is tested without a GPU.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)

FPS = 25
SAMPLE_RATE = 16_000
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS  # 640


@dataclass(frozen=True)
class StreamSettings:
    """Phase 0's chosen settings (portrait-spike-optimized-2026-10-29, portrait-lipsync-2026-10-29)."""

    window: int = 50
    carry: int = 10
    first_hop: int = 8
    hop: int = 20
    lookahead: int = 5
    context: int = 50
    decode_batch: int = 4
    # How long one pass may take, and the transport margin, both taken off a held frame's play time.
    pass_seconds: float = 0.04
    margin_seconds: float = 0.25
    # The browser starts an output once this much speech is buffered, and holds it at most this long
    # for the first frames (D-5); before its first play-position report, that is the play estimate.
    start_buffer_seconds: float = 0.4
    start_hold_seconds: float = 0.25


@dataclass(frozen=True)
class PassPlan:
    """One window pass: generate frames [start, start + window) and keep [start, start + commit)."""

    start: int
    commit: int
    # Real audio in the pass's buffer, in frames: [buffer_start, buffer_end); beyond it is padding.
    buffer_start: int
    buffer_end: int
    # The carry: the committed frames [carry_start, start).
    carry_start: int
    padded: bool


class MotionSession(Protocol):
    """What the scheduler needs from the model, for one output."""

    level: int  # the call's quality level (``QUALITY_LEVELS``), which ``decode`` encodes at

    def run_pass(self, audio: np.ndarray, plan: PassPlan, seed: int) -> None:
        """Generate the window from ``audio`` (16 kHz, the plan's buffer) and commit its first frames."""

    def decode(self, start: int, stop: int) -> list[bytes | None]:
        """JPEG frames for committed frames [start, stop); None for a frame the quality level does not send."""

    def reset(self) -> None:
        """Forget the output's frames; the next output starts from the rest pose."""


@dataclass(frozen=True)
class Frame:
    output_id: str
    epoch: int
    segment_id: str
    offset: int
    jpeg: bytes


def plan_pass(settings: StreamSettings, committed: int, available: int, flush_to: int | None) -> PassPlan | None:
    """The next pass, or None while more audio is needed.

    ``committed`` frames are done; ``available`` frames of audio have arrived; ``flush_to`` (when set) asks for
    every frame up to it to be committed now, with padding where audio is missing.
    """
    if flush_to is not None and committed < flush_to:
        commit = min(settings.hop, flush_to - committed)
        padded = True
    else:
        hop = settings.first_hop if committed == 0 else settings.hop
        ready = available - settings.lookahead - committed
        if ready < hop:
            return None
        commit = hop
        padded = False
    return PassPlan(
        start=committed,
        commit=commit,
        buffer_start=max(0, committed - settings.context),
        buffer_end=min(available, committed + settings.window),
        carry_start=max(0, committed - settings.carry),
        padded=padded,
    )


@dataclass
class _Segment:
    segment_id: str
    sample_rate: int
    blocks: dict[int, np.ndarray] = field(default_factory=dict)
    samples: int = 0  # contiguous source samples from offset 0
    done: bool = False
    start_16k: int = 0  # where the segment starts on the output's 16 kHz timeline
    resampled: np.ndarray | None = None

    def add(self, offset: int, block: np.ndarray) -> None:
        if offset < self.samples or offset in self.blocks:
            return  # a repeat of audio already placed
        self.blocks[offset] = block
        while self.samples in self.blocks:
            self.samples += len(self.blocks[self.samples])
        self.resampled = None

    def source(self) -> np.ndarray:
        parts, cursor = [], 0
        for offset in sorted(self.blocks):
            if offset != cursor:
                break
            parts.append(self.blocks[offset])
            cursor += len(self.blocks[offset])
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    @property
    def length_16k(self) -> int:
        return int(round(self.samples * SAMPLE_RATE / self.sample_rate))


Resampler = Callable[[np.ndarray, int], np.ndarray]


def linear_resample(audio: np.ndarray, rate: int) -> np.ndarray:
    """A plain resampler for tests and for 16 kHz input; the runtime passes a filtered one."""
    if rate == SAMPLE_RATE or len(audio) == 0:
        return audio.astype(np.float32, copy=False)
    count = int(round(len(audio) * SAMPLE_RATE / rate))
    positions = np.arange(count) * (rate / SAMPLE_RATE)
    return np.interp(positions, np.arange(len(audio)), audio).astype(np.float32)


class Output:
    """One output's audio timeline, committed frames and play-position estimate."""

    def __init__(self, output_id: str, epoch: int, settings: StreamSettings, resample: Resampler,
                 opened_at: float) -> None:
        self.output_id = output_id
        self.epoch = epoch
        self.settings = settings
        self.resample = resample
        self.segments: list[_Segment] = []
        self.committed = 0
        self.decoded = 0
        self.ended = False
        self.cancelled = False
        self.first_audio_at: float | None = None
        self.start_buffered_at: float | None = None
        self.opened_at = opened_at
        # (output seconds, wall time) of the latest play-position report.
        self.play_anchor: tuple[float, float] | None = None

    def segment(self, segment_id: str) -> _Segment | None:
        return next((item for item in self.segments if item.segment_id == segment_id), None)

    def start_segment(self, segment_id: str, sample_rate: int) -> None:
        existing = self.segment(segment_id)
        if existing is not None:
            existing.sample_rate = sample_rate  # a format change within the phrase
            return
        start = self.segments[-1].start_16k + self.segments[-1].length_16k if self.segments else 0
        self.segments.append(_Segment(segment_id, sample_rate, start_16k=start))

    def add_pcm(self, segment_id: str, offset: int, block: np.ndarray, now: float) -> None:
        segment = self.segment(segment_id)
        if segment is None or segment.done:
            return
        segment.add(offset, block)
        if self.first_audio_at is None:
            self.first_audio_at = now
        self._restack()
        if self.start_buffered_at is None and self.samples_16k >= self.settings.start_buffer_seconds * SAMPLE_RATE:
            self.start_buffered_at = now

    def finish_segment(self, segment_id: str) -> None:
        segment = self.segment(segment_id)
        if segment is not None:
            segment.done = True

    def _restack(self) -> None:
        cursor = 0
        for segment in self.segments:
            segment.start_16k = cursor
            cursor += segment.length_16k

    @property
    def samples_16k(self) -> int:
        """Contiguous audio on the timeline: segments in order, up to the first that is still incomplete."""
        total = 0
        for segment in self.segments:
            total += segment.length_16k
            if not segment.done:
                break
        return total

    @property
    def available_frames(self) -> int:
        return self.samples_16k // SAMPLES_PER_FRAME

    @property
    def total_frames(self) -> int:
        return math.ceil(self.samples_16k / SAMPLES_PER_FRAME)

    def audio(self, start_frame: int, stop_frame: int) -> np.ndarray:
        """16 kHz audio for frames [start_frame, stop_frame), padded with the last sample past the end."""
        pieces = []
        for segment in self.segments:
            if segment.resampled is None:
                segment.resampled = self.resample(segment.source(), segment.sample_rate)
            pieces.append(segment.resampled[: segment.length_16k])
        timeline = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
        start, stop = start_frame * SAMPLES_PER_FRAME, stop_frame * SAMPLES_PER_FRAME
        clip = timeline[start:stop]
        if len(clip) < stop - start:
            pad_value = clip[-1] if len(clip) else 0.0
            clip = np.concatenate([clip, np.full(stop - start - len(clip), pad_value, dtype=np.float32)])
        return clip.astype(np.float32, copy=False)

    def stamp(self, frame: int) -> tuple[str, int]:
        """The segment a frame starts in, and its offset in that segment's own samples."""
        at = frame * SAMPLES_PER_FRAME
        chosen = self.segments[-1]
        for segment in self.segments:
            if at < segment.start_16k + segment.length_16k:
                chosen = segment
                break
        offset = max(0, at - chosen.start_16k)
        return chosen.segment_id, int(round(offset * chosen.sample_rate / SAMPLE_RATE))

    def output_seconds(self, segment_id: str, offset: int) -> float | None:
        segment = self.segment(segment_id)
        if segment is None:
            return None
        return segment.start_16k / SAMPLE_RATE + offset / segment.sample_rate

    def play_time(self, frame: int) -> float | None:
        """When a frame is expected to be heard, from the latest play-position report.

        Before the first report: the browser starts once ``start_buffer_seconds`` of speech is buffered and
        holds the start at most ``start_hold_seconds`` for the first frames, so frame 0 plays by then.
        """
        seconds = frame / FPS
        if self.play_anchor is not None:
            anchor_seconds, anchor_wall = self.play_anchor
            return anchor_wall + (seconds - anchor_seconds)
        if self.start_buffered_at is None:
            return None
        return self.start_buffered_at + self.settings.start_hold_seconds + seconds

    def flush_target(self, now: float, extra_margin: float) -> int | None:
        """Frames to commit with padding now: all of them at the end, or held frames whose deadline came.

        The transport margin applies once play positions arrive over the network; before that the
        estimate is local and only the pass time is allowed for.
        """
        if self.ended:
            return self.total_frames
        held_from = self.committed
        if held_from >= self.available_frames:
            return None
        play = self.play_time(held_from)
        if play is None:
            return None
        margin = self.settings.pass_seconds
        if self.play_anchor is not None:
            margin += self.settings.margin_seconds + extra_margin
        return self.available_frames if now >= play - margin else None


class PortraitStream:
    """One call's portrait: outputs in order, passes as their audio allows, frames out through ``emit``.

    Not thread-safe by itself: the service calls it from one worker thread. ``cancelled`` and ``paused``
    are read between micro-batches and may be set from other threads.
    """

    def __init__(self, session: MotionSession, emit: Callable[[Frame], None], *,
                 settings: StreamSettings | None = None, resample: Resampler = linear_resample,
                 clock: Callable[[], float] = time.monotonic, seed: int = 25) -> None:
        self.session = session
        self.emit = emit
        self.settings = settings or StreamSettings()
        self.resample = resample
        self.clock = clock
        self.seed = seed
        self.output: Output | None = None
        self.passes = 0
        self.round_trip_seconds = 0.0
        self.priority = threading.Event()  # set while accepted TTS has not produced its first chunk
        self.cancel_requested: dict[tuple[str, int], None] = {}  # oldest first

    # --- messages ------------------------------------------------------------------------------------

    def phrase_start(self, output_id: str, epoch: int, segment_id: str, sample_rate: int) -> None:
        if (output_id, epoch) in self.cancel_requested:
            return
        if self.output is None or (self.output.output_id, self.output.epoch) != (output_id, epoch):
            self._open(output_id, epoch)
        assert self.output is not None
        self.output.start_segment(segment_id, int(sample_rate))

    def pcm(self, segment_id: str, offset: int, samples: np.ndarray) -> None:
        if self.output is not None:
            block = samples.astype(np.float32) / 32768.0 if samples.dtype == np.int16 else samples.astype(np.float32)
            self.output.add_pcm(segment_id, int(offset), block, self.clock())

    def phrase_done(self, segment_id: str) -> None:
        if self.output is not None:
            self.output.finish_segment(segment_id)

    def output_end(self, output_id: str, epoch: int) -> None:
        if self.output is not None and (self.output.output_id, self.output.epoch) == (output_id, epoch):
            for segment in self.output.segments:
                segment.done = True
            self.output.ended = True

    def cancel(self, output_id: str, epoch: int) -> None:
        self.cancel_requested[(output_id, epoch)] = None
        if len(self.cancel_requested) > 64:  # only recent outputs can still send audio
            self.cancel_requested.pop(next(iter(self.cancel_requested)))
        if self.output is not None and (self.output.output_id, self.output.epoch) == (output_id, epoch):
            self.output.cancelled = True

    def play_position(self, segment_id: str, offset: int, round_trip_seconds: float = 0.0) -> None:
        """The browser heard ``offset`` of ``segment_id`` (reported now, give or take the round trip)."""
        self.round_trip_seconds = max(0.0, float(round_trip_seconds))
        if self.output is None:
            return
        seconds = self.output.output_seconds(segment_id, int(offset))
        if seconds is not None:
            self.output.play_anchor = (seconds, self.clock() - self.round_trip_seconds / 2)

    # --- work ----------------------------------------------------------------------------------------

    def pump(self) -> int:
        """Run every pass the audio allows now and send its frames; returns the frames sent."""
        output = self.output
        if output is None or output.cancelled:
            return 0
        sent = 0
        while not output.cancelled:
            flush_to = output.flush_target(self.clock(), self.round_trip_seconds)
            plan = plan_pass(self.settings, output.committed, output.available_frames, flush_to)
            if plan is None:
                break
            self._wait_for_priority(output)
            if output.cancelled:
                break
            began = time.perf_counter()
            audio = output.audio(plan.buffer_start, max(plan.buffer_end, plan.start + 1))
            self.session.run_pass(audio, plan, self.seed + self.passes)
            self.passes += 1
            output.committed = plan.start + plan.commit
            if output.decoded == 0:
                logger.info("portrait %s: first pass %.0f ms after its first audio, took %.1f ms",
                            output.output_id, (self.clock() - (output.first_audio_at or self.clock())) * 1000,
                            (time.perf_counter() - began) * 1000)
            first_frame = output.decoded == 0
            sent += self._decode_committed(output)
            if first_frame and output.decoded:
                logger.info("portrait %s: first frames out %.0f ms after its first audio", output.output_id,
                            (self.clock() - (output.first_audio_at or self.clock())) * 1000)
            if output.ended and output.committed >= output.total_frames:
                break
        return sent

    def _decode_committed(self, output: Output) -> int:
        sent = 0
        while output.decoded < output.committed:
            self._wait_for_priority(output)
            if output.cancelled:
                return sent
            stop = min(output.committed, output.decoded + self.settings.decode_batch)
            jpegs = self.session.decode(output.decoded, stop)
            for index, jpeg in enumerate(jpegs):
                if jpeg is None:
                    continue
                segment_id, offset = output.stamp(output.decoded + index)
                self.emit(Frame(output.output_id, output.epoch, segment_id, offset, jpeg))
                sent += 1
            output.decoded = stop
        return sent

    def _wait_for_priority(self, output: Output, limit_seconds: float = 2.0) -> None:
        """Give way to accepted TTS's first chunk; never wait past ``limit_seconds``."""
        deadline = time.monotonic() + limit_seconds
        while self.priority.is_set() and not output.cancelled and time.monotonic() < deadline:
            time.sleep(0.002)

    def _open(self, output_id: str, epoch: int) -> None:
        self.output = Output(output_id, epoch, self.settings, self.resample, self.clock())
        self.session.reset()

    @property
    def finished(self) -> bool:
        output = self.output
        return output is None or output.cancelled or (output.ended and output.decoded >= output.total_frames)

    def stats(self) -> dict[str, Any]:
        output = self.output
        return {"passes": self.passes, "output_id": output.output_id if output else None,
                "committed": output.committed if output else 0, "decoded": output.decoded if output else 0}


__all__ = [
    "FPS", "Frame", "MotionSession", "Output", "PassPlan", "PortraitStream", "SAMPLES_PER_FRAME", "SAMPLE_RATE",
    "StreamSettings", "linear_resample", "plan_pass",
]
