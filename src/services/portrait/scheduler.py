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

Speculative frames (roadmap Phase 3, "Keeping the hold near zero"): while the LLM's reply is still being decided,
the gateway copies speculative TTS audio in under its generation id (``spec_start``, PCM for segment
``spec:<generation_id>``). Each speculative output renders only its first two passes, on its own motion session,
and keeps the frames. When a reply's phrase replays that audio, ``spec_bind`` relabels the output with the
phrase's output, epoch and segment, and its frames go out at once; ``spec_prefix_end`` says how many samples the
replay was, and the phrase's fresh audio continues from there. A prefix shorter than what arrived is cut, a longer
one is filled with silence (its copy was dropped on the way), so the timeline stays the browser's. ``spec_drop``
forgets an output that will never be claimed. The bound segment keeps the speculation's timeline, which starts
``trim`` samples (leading silence the browser never got) before the browser's: frames are stamped ``trim`` earlier,
and frames in that silence are not sent.

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
SPEC_PREFIX = "spec:"
MAX_SPECULATIVE_OUTPUTS = 4


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

    def spawn(self) -> MotionSession:
        """A fresh session for the same portrait, emotion and level (a speculative output's own motion)."""

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
    # Source samples at the segment's start that the browser never got: its offsets count from here.
    origin: int = 0

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

    def fit(self, samples: int) -> None:
        """Make the segment exactly ``samples`` long from offset 0: cut what is past it, fill a gap with silence."""
        audio = self.source()[:samples]
        if len(audio) < samples:
            audio = np.concatenate([audio, np.zeros(samples - len(audio), dtype=np.float32)])
        self.blocks = {0: audio.astype(np.float32, copy=False)} if samples else {}
        self.samples = samples
        self.resampled = None


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
        # A speculative output keeps its frames (frame index, JPEG) until a phrase claims it.
        self.held: list[tuple[int, bytes]] | None = None

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
        self.restack()
        if self.start_buffered_at is None and self.samples_16k >= self.settings.start_buffer_seconds * SAMPLE_RATE:
            self.start_buffered_at = now

    def finish_segment(self, segment_id: str) -> None:
        segment = self.segment(segment_id)
        if segment is not None:
            segment.done = True

    def restack(self) -> None:
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
        """The segment a frame starts in, and its offset in the browser's samples of that segment.

        Negative for a frame in leading silence the browser never got (a bound speculation's trim).
        """
        at = frame * SAMPLES_PER_FRAME
        chosen = self.segments[-1]
        for segment in self.segments:
            if at < segment.start_16k + segment.length_16k:
                chosen = segment
                break
        offset = max(0, at - chosen.start_16k)
        return chosen.segment_id, int(round(offset * chosen.sample_rate / SAMPLE_RATE)) - chosen.origin

    def output_seconds(self, segment_id: str, offset: int) -> float | None:
        segment = self.segment(segment_id)
        if segment is None:
            return None
        return segment.start_16k / SAMPLE_RATE + (offset + segment.origin) / segment.sample_rate

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
        if self.held is not None:  # speculative: nothing plays until a phrase claims it
            return None
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
        # Speculative outputs by generation id (oldest first), each with its own session.
        self.speculative: dict[str, tuple[Output, MotionSession]] = {}
        # Bound generations: the segment their speculative audio continues into, until the prefix ends.
        self.bound: dict[str, str] = {}

    # --- messages ------------------------------------------------------------------------------------

    def phrase_start(self, output_id: str, epoch: int, segment_id: str, sample_rate: int) -> None:
        if (output_id, epoch) in self.cancel_requested:
            return
        if self.output is None or (self.output.output_id, self.output.epoch) != (output_id, epoch):
            self._open(output_id, epoch)
        assert self.output is not None
        self.output.start_segment(segment_id, int(sample_rate))

    def pcm(self, segment_id: str, offset: int, samples: np.ndarray) -> None:
        block = samples.astype(np.float32) / 32768.0 if samples.dtype == np.int16 else samples.astype(np.float32)
        if segment_id.startswith(SPEC_PREFIX):
            generation_id = segment_id[len(SPEC_PREFIX):]
            if generation_id in self.bound and self.output is not None:
                self.output.add_pcm(self.bound[generation_id], int(offset), block, self.clock())
            elif generation_id in self.speculative:
                self.speculative[generation_id][0].add_pcm(segment_id, int(offset), block, self.clock())
            return
        if self.output is not None:
            self.output.add_pcm(segment_id, int(offset), block, self.clock())

    # --- speculation ---------------------------------------------------------------------------------

    def spec_start(self, generation_id: str, sample_rate: int) -> None:
        if generation_id in self.speculative or generation_id in self.bound:
            return
        output = Output(SPEC_PREFIX + generation_id, -1, self.settings, self.resample, self.clock())
        output.start_segment(SPEC_PREFIX + generation_id, int(sample_rate))
        output.held = []
        self.speculative[generation_id] = (output, self.session.spawn())
        while len(self.speculative) > MAX_SPECULATIVE_OUTPUTS:
            self.speculative.pop(next(iter(self.speculative)))

    def spec_drop(self, generation_id: str) -> None:
        self.speculative.pop(generation_id, None)

    def spec_bind(self, generation_id: str, output_id: str, epoch: int, segment_id: str, trim: int = 0) -> None:
        """A phrase replays this speculation: its output becomes the phrase's, and its frames go out now.

        A generation this stream never received (its copy was dropped, or never made) leaves the phrase as it
        is; ``spec_prefix_end`` then fills the replayed stretch with silence.
        """
        if (output_id, epoch) in self.cancel_requested:
            return
        claimed = self.speculative.pop(generation_id, None)
        if claimed is None:
            return
        output, session = claimed
        current = self.output
        same_output = current is not None and (current.output_id, current.epoch) == (output_id, epoch)
        if same_output and current is not None and any(
                item.segment_id != segment_id and item.samples for item in current.segments):
            # A later phrase of a reply already under way: its audio joins the reply's own motion; the
            # speculative frames, made from the rest pose, would not continue it.
            target = current.segment(segment_id)
            if target is not None:
                target.origin = max(0, int(trim))
                for offset, block in sorted(output.segments[0].blocks.items()):
                    current.add_pcm(segment_id, offset, block, self.clock())
            self.bound[generation_id] = segment_id
            return
        existing = current.segment(segment_id) if same_output and current is not None else None
        output.output_id, output.epoch = output_id, epoch
        output.segments[0].segment_id = segment_id
        output.segments[0].origin = max(0, int(trim))
        if existing is not None:
            output.segments[0].sample_rate = existing.sample_rate
        held, output.held = output.held or [], None
        # Its audio starts playing now (the replay goes to the browser at once).
        now = self.clock()
        output.first_audio_at = now
        threshold = self.settings.start_buffer_seconds * SAMPLE_RATE
        output.start_buffered_at = now if output.samples_16k >= threshold else None
        self.output, self.session = output, session
        self.bound[generation_id] = segment_id
        for index, jpeg in held:
            stamp_segment, offset = output.stamp(index)
            if offset >= 0:
                self.emit(Frame(output_id, epoch, stamp_segment, offset, jpeg))

    def spec_prefix_end(self, generation_id: str, segment_id: str, samples: int) -> None:
        """The replayed prefix was ``samples`` long: fit the segment to it; fresh audio follows from there."""
        self.bound.pop(generation_id, None)
        segment = self.output.segment(segment_id) if self.output is not None else None
        if segment is None:
            return
        if segment.samples != samples:
            logger.info("portrait: speculative prefix %s was %d samples, %d arrived", generation_id, samples,
                        segment.samples)
        segment.fit(int(samples))
        assert self.output is not None
        self.output.restack()

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

    def play_position(self, segment_id: str, offset: int, round_trip_seconds: float = 0.0,
                      received_at: float | None = None) -> None:
        """The browser heard ``offset`` of ``segment_id`` (reported at ``received_at``, give or take the round trip).

        ``received_at`` is when the report arrived; it may be applied later, after the passes queued before it.
        """
        self.round_trip_seconds = max(0.0, float(round_trip_seconds))
        if self.output is None:
            return
        seconds = self.output.output_seconds(segment_id, int(offset))
        if seconds is not None:
            arrived = received_at if received_at is not None else self.clock()
            self.output.play_anchor = (seconds, arrived - self.round_trip_seconds / 2)

    # --- work ----------------------------------------------------------------------------------------

    def pump(self) -> int:
        """Run every pass the audio allows now and send its frames; returns the frames sent.

        Speculative outputs get their first passes only when the call's own output has nothing to do.
        """
        output = self.output
        if output is None or output.cancelled:
            self._pump_speculative()
            return 0
        sent = self._pump_output(output, self.session)
        if not sent:
            self._pump_speculative()
        return sent

    def _pump_speculative(self) -> None:
        limit = self.settings.first_hop + self.settings.hop
        for output, session in list(self.speculative.values()):
            if output.committed < limit:
                self._pump_output(output, session, limit=limit)

    def _pump_output(self, output: Output, session: MotionSession, limit: int | None = None) -> int:
        sent = 0
        while not output.cancelled and (limit is None or output.committed < limit):
            flush_to = output.flush_target(self.clock(), self.round_trip_seconds)
            plan = plan_pass(self.settings, output.committed, output.available_frames, flush_to)
            if plan is None:
                break
            self._wait_for_priority(output)
            if output.cancelled:
                break
            began = time.perf_counter()
            audio = output.audio(plan.buffer_start, max(plan.buffer_end, plan.start + 1))
            session.run_pass(audio, plan, self.seed + self.passes)
            self.passes += 1
            output.committed = plan.start + plan.commit
            if output.decoded == 0:
                logger.info("portrait %s: first pass %.0f ms after its first audio, took %.1f ms",
                            output.output_id, (self.clock() - (output.first_audio_at or self.clock())) * 1000,
                            (time.perf_counter() - began) * 1000)
            first_frame = output.decoded == 0
            sent += self._decode_committed(output, session)
            if first_frame and output.decoded:
                logger.info("portrait %s: first frames out %.0f ms after its first audio", output.output_id,
                            (self.clock() - (output.first_audio_at or self.clock())) * 1000)
            if output.ended and output.committed >= output.total_frames:
                break
        return sent

    def _decode_committed(self, output: Output, session: MotionSession) -> int:
        sent = 0
        while output.decoded < output.committed:
            self._wait_for_priority(output)
            if output.cancelled:
                return sent
            stop = min(output.committed, output.decoded + self.settings.decode_batch)
            jpegs = session.decode(output.decoded, stop)
            for index, jpeg in enumerate(jpegs):
                if jpeg is None:
                    continue
                if output.held is not None:  # speculative: kept until a phrase claims it
                    output.held.append((output.decoded + index, jpeg))
                    continue
                segment_id, offset = output.stamp(output.decoded + index)
                if offset < 0:
                    continue  # leading silence the browser never got
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
        self.bound.clear()

    @property
    def finished(self) -> bool:
        output = self.output
        return output is None or output.cancelled or (output.ended and output.decoded >= output.total_frames)

    def stats(self) -> dict[str, Any]:
        output = self.output
        return {"passes": self.passes, "output_id": output.output_id if output else None,
                "committed": output.committed if output else 0, "decoded": output.decoded if output else 0}


__all__ = [
    "FPS", "Frame", "MAX_SPECULATIVE_OUTPUTS", "MotionSession", "Output", "PassPlan", "PortraitStream",
    "SAMPLES_PER_FRAME", "SAMPLE_RATE", "SPEC_PREFIX", "StreamSettings", "linear_resample", "plan_pass",
]
