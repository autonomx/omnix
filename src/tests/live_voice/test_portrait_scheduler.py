"""The live portrait's hop scheduler, against a fake model (roadmap: docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md)."""
from __future__ import annotations

import threading
import time

import numpy as np

from services.portrait.scheduler import (
    SAMPLES_PER_FRAME,
    Frame,
    PassPlan,
    PortraitStream,
    StreamSettings,
    plan_pass,
)

SETTINGS = StreamSettings()


class FakeSession:
    def __init__(self) -> None:
        self.plans: list[PassPlan] = []
        self.audio_lengths: list[int] = []
        self.resets = 0

    def run_pass(self, audio: np.ndarray, plan: PassPlan, seed: int) -> None:
        self.plans.append(plan)
        self.audio_lengths.append(len(audio))

    def decode(self, start: int, stop: int) -> list[bytes]:
        return [f"frame-{index}".encode() for index in range(start, stop)]

    def reset(self) -> None:
        self.resets += 1


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _stream(clock: Clock | None = None) -> tuple[PortraitStream, FakeSession, list[Frame]]:
    session, frames = FakeSession(), []
    stream = PortraitStream(session, frames.append, clock=clock or Clock())
    return stream, session, frames


def _pcm(seconds: float, rate: int) -> np.ndarray:
    return (np.sin(np.arange(int(seconds * rate)) / 7.0) * 8000).astype(np.int16)


def _feed(stream: PortraitStream, segment_id: str, audio: np.ndarray, block: int) -> None:
    for offset in range(0, len(audio), block):
        stream.pcm(segment_id, offset, audio[offset:offset + block])
        stream.pump()


def test_the_first_pass_waits_for_its_hop_plus_lookahead_then_hops_by_twenty() -> None:
    assert plan_pass(SETTINGS, committed=0, available=12, flush_to=None) is None
    first = plan_pass(SETTINGS, committed=0, available=13, flush_to=None)
    assert first == PassPlan(start=0, commit=8, buffer_start=0, buffer_end=13, carry_start=0, padded=False)
    assert plan_pass(SETTINGS, committed=8, available=32, flush_to=None) is None
    second = plan_pass(SETTINGS, committed=8, available=33, flush_to=None)
    assert second is not None and (second.commit, second.carry_start, second.buffer_end) == (20, 0, 33)
    later = plan_pass(SETTINGS, committed=108, available=400, flush_to=None)
    assert later is not None
    # The carry is the 10 committed frames before the window; wav2vec2 sees 50 frames of context before it.
    assert (later.carry_start, later.buffer_start, later.buffer_end) == (98, 58, 158)


def test_a_flush_commits_held_frames_with_padding_a_hop_at_a_time() -> None:
    plan = plan_pass(SETTINGS, committed=40, available=60, flush_to=60)
    assert plan is not None and plan.padded and (plan.start, plan.commit) == (40, 20)
    assert plan_pass(SETTINGS, committed=60, available=60, flush_to=60) is None


def test_every_frame_of_an_output_is_sent_once_in_order_stamped_in_source_samples() -> None:
    stream, _session, frames = _stream()
    stream.phrase_start("out-1", 1, "seg-a", 24_000)
    audio = _pcm(2.03, 24_000)
    _feed(stream, "seg-a", audio, 2_400)
    stream.phrase_done("seg-a")
    stream.output_end("out-1", 1)
    stream.pump()

    expected = int(np.ceil(len(audio) * 16_000 / 24_000 / SAMPLES_PER_FRAME))
    assert len(frames) == expected
    assert [frame.jpeg for frame in frames] == [f"frame-{index}".encode() for index in range(expected)]
    # One video frame is 640 samples at 16 kHz: 960 of the phrase's own 24 kHz samples.
    assert [frame.offset for frame in frames[:4]] == [0, 960, 1920, 2880]
    assert {frame.segment_id for frame in frames} == {"seg-a"} and stream.finished


def test_phrases_form_one_timeline_and_frames_carry_their_own_segment_and_rate() -> None:
    stream, session, frames = _stream()
    stream.phrase_start("out-1", 1, "seg-a", 24_000)
    _feed(stream, "seg-a", _pcm(1.0, 24_000), 4_800)
    stream.phrase_done("seg-a")
    stream.phrase_start("out-1", 1, "seg-b", 16_000)
    _feed(stream, "seg-b", _pcm(1.0, 16_000), 3_200)
    stream.phrase_done("seg-b")
    stream.output_end("out-1", 1)
    stream.pump()

    assert len(frames) == 50
    assert [frame.segment_id for frame in frames[24:26]] == ["seg-a", "seg-b"]
    assert frames[25].offset == 0 and frames[26].offset == 640
    # The second phrase continues the first's motion: one reset for the output, carries reach back across the join.
    assert session.resets == 1
    assert any(plan.carry_start < 25 <= plan.start for plan in session.plans)


def test_blocks_arriving_out_of_order_are_placed_by_their_offset() -> None:
    stream, _session, frames = _stream()
    stream.phrase_start("out-1", 1, "seg-a", 16_000)
    audio = _pcm(1.0, 16_000)
    for offset in (3_200, 0, 9_600, 6_400, 12_800, 0):
        stream.pcm("seg-a", offset, audio[offset:offset + 3_200])
    stream.phrase_done("seg-a")
    stream.output_end("out-1", 1)
    stream.pump()
    assert len(frames) == 25 and stream.output is not None and stream.output.segments[0].samples == 16_000


def test_held_frames_at_a_phrase_end_wait_for_the_next_phrase_until_their_deadline() -> None:
    clock = Clock()
    stream, session, frames = _stream(clock)
    stream.phrase_start("out-1", 1, "seg-a", 16_000)
    _feed(stream, "seg-a", _pcm(2.0, 16_000), 1_600)  # 50 frames
    stream.phrase_done("seg-a")
    stream.pump()
    assert len(frames) == 28 and not any(plan.padded for plan in session.plans)

    # The browser reports it is playing frame 0 now: held frame 28 plays 1.12 s from now, and its deadline
    # leaves one pass and the transport margin (0.29 s).
    stream.play_position("seg-a", 0)
    clock.now += 0.8
    stream.pump()
    assert len(frames) == 28
    clock.now += 0.05
    stream.pump()
    # One hop is committed with padding; frames 48 and 49 play later, so they keep waiting for the next phrase.
    assert len(frames) == 48 and session.plans[-1].padded
    clock.now += 0.8  # frame 48 plays at 1.92 s after the report; its deadline is 1.63 s (now 1.65 s)
    stream.pump()
    assert len(frames) == 50


def test_before_any_report_the_start_buffer_and_hold_set_the_deadline() -> None:
    clock = Clock()
    stream, session, frames = _stream(clock)
    stream.phrase_start("out-1", 1, "seg-a", 16_000)
    _feed(stream, "seg-a", _pcm(1.2, 16_000), 1_600)  # 30 frames, all at once
    stream.phrase_done("seg-a")
    # The first passes are never padded: playback cannot start before 0.4 s is buffered, plus the start hold.
    assert len(frames) == 8 and not any(plan.padded for plan in session.plans)
    clock.now += 0.5  # frame 8 plays at 0.25 + 0.32 s; its deadline is one pass earlier, at 0.53 s
    stream.pump()
    assert len(frames) == 8
    clock.now += 0.1
    stream.pump()
    assert len(frames) == 28 and session.plans[-1].padded

    # The next phrase arrives; a report from it moves the deadline of the frames now held out again.
    stream.phrase_start("out-1", 1, "seg-b", 16_000)
    _feed(stream, "seg-b", _pcm(1.2, 16_000), 1_600)
    stream.play_position("seg-b", 0)
    stream.pump()
    assert len(frames) == 48 and not session.plans[-1].padded


def test_cancel_stops_between_micro_batches_and_ignores_the_outputs_late_audio() -> None:
    session, frames = FakeSession(), []
    stream: PortraitStream

    def emit(frame: Frame) -> None:
        frames.append(frame)
        if len(frames) == 2:
            stream.cancel("out-1", 1)

    stream = PortraitStream(session, emit, clock=Clock())
    stream.phrase_start("out-1", 1, "seg-a", 16_000)
    stream.pcm("seg-a", 0, _pcm(2.0, 16_000))
    stream.pump()
    assert len(frames) == SETTINGS.decode_batch  # the micro-batch in hand finishes; the next never starts
    stream.phrase_start("out-1", 1, "seg-b", 16_000)
    stream.pcm("seg-b", 0, _pcm(1.0, 16_000))
    assert stream.pump() == 0
    # A new output starts fresh from the rest pose.
    stream.phrase_start("out-2", 2, "seg-c", 16_000)
    assert session.resets == 2 and stream.output is not None and stream.output.output_id == "out-2"


def test_the_tts_priority_pause_holds_work_until_released() -> None:
    stream, _session, frames = _stream()
    stream.phrase_start("out-1", 1, "seg-a", 16_000)
    stream.priority.set()
    stream.pcm("seg-a", 0, _pcm(1.0, 16_000))
    releaser = threading.Timer(0.05, stream.priority.clear)
    started = time.monotonic()
    releaser.start()
    stream.pump()
    assert time.monotonic() - started >= 0.04 and frames
