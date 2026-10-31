"""The live portrait's hop scheduler, against a fake model (roadmap: docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md)."""
from __future__ import annotations

import threading
import time

import numpy as np

from services.portrait.scheduler import (
    SAMPLES_PER_FRAME,
    TRANSITION_OUTPUT_ID,
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
        self.rewinds: list[int] = []
        self.level = 0
        self.children: list[FakeSession] = []

    def run_pass(self, audio: np.ndarray, plan: PassPlan, seed: int) -> None:
        self.plans.append(plan)
        self.audio_lengths.append(len(audio))

    def decode(self, start: int, stop: int) -> list[bytes]:
        return [f"frame-{index}".encode() for index in range(start, stop)]

    def reset(self) -> None:
        self.resets += 1

    def rewind(self, frames: int) -> None:
        self.rewinds.append(frames)

    def transition(self) -> list[bytes]:
        return [f"transition-{index}".encode() for index in range(3)]

    def spawn(self) -> FakeSession:
        child = FakeSession()
        self.children.append(child)
        return child


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _stream(clock: Clock | None = None, *, transitions: bool = False) -> tuple[PortraitStream, FakeSession, list[Frame]]:
    """A stream on a fake model; its frames, without a finished reply's transition unless asked for."""
    session, frames = FakeSession(), []

    def emit(frame: Frame) -> None:
        if transitions or frame.output_id != TRANSITION_OUTPUT_ID:
            frames.append(frame)

    stream = PortraitStream(session, emit, clock=clock or Clock())
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


def _speculate(stream: PortraitStream, generation_id: str, seconds: float, rate: int = 24_000) -> np.ndarray:
    audio = _pcm(seconds, rate)
    stream.spec_start(generation_id, rate)
    _feed(stream, f"spec:{generation_id}", audio, 4_800)
    return audio


def test_speculative_audio_renders_its_first_passes_and_keeps_the_frames() -> None:
    stream, session, frames = _stream()
    _speculate(stream, "gen-1", 2.0)
    child = session.children[0]
    assert [plan.commit for plan in child.plans] == [8, 20]  # the first two passes only
    assert session.plans == [] and frames == []


def test_a_bound_speculation_sends_its_frames_at_once_and_the_phrase_continues_after_the_prefix() -> None:
    stream, session, frames = _stream()
    _speculate(stream, "gen-1", 2.0)
    stream.phrase_start("turn-1", 1, "seg-a", 24_000)
    stream.spec_bind("gen-1", "turn-1", 1, "seg-a")
    assert [(frame.output_id, frame.segment_id) for frame in frames] == [("turn-1", "seg-a")] * 28
    assert [frame.offset for frame in frames[:3]] == [0, 960, 1_920]
    stream.spec_prefix_end("gen-1", "seg-a", 48_000)
    _feed(stream, "seg-a", np.concatenate([np.zeros(48_000, np.int16), _pcm(1.0, 24_000)]), 4_800)
    stream.phrase_done("seg-a")
    stream.output_end("turn-1", 1)
    stream.pump()
    assert [frame.offset for frame in frames] == [index * 960 for index in range(75)]  # each frame once
    assert stream.session is session.children[0]  # the speculation's motion goes on


def test_a_prefix_longer_than_its_copy_is_filled_with_silence_and_a_shorter_one_cut() -> None:
    stream, _session, frames = _stream()
    _speculate(stream, "gen-1", 1.0)
    stream.phrase_start("turn-1", 1, "seg-a", 24_000)
    stream.spec_bind("gen-1", "turn-1", 1, "seg-a")
    stream.spec_prefix_end("gen-1", "seg-a", 36_000)  # half a second of the copy was dropped on the way
    assert stream.output is not None and stream.output.segment("seg-a").samples == 36_000
    stream.spec_prefix_end("gen-1", "seg-a", 12_000)
    assert stream.output.segment("seg-a").samples == 12_000


def test_frames_made_past_a_shorter_prefix_are_made_again_from_the_fresh_audio() -> None:
    # Review finding (2026-10-31): frames from speculative audio the phrase did not use stayed committed, and the
    # fresh audio in their stretch never got frames of its own.
    stream, session, frames = _stream()
    _speculate(stream, "gen-1", 2.0)  # 28 frames made from it
    stream.phrase_start("turn-1", 1, "seg-a", 24_000)
    stream.spec_bind("gen-1", "turn-1", 1, "seg-a")
    assert len(frames) == 28
    stream.spec_prefix_end("gen-1", "seg-a", 12_000)  # only half a second of it was the phrase's
    child = session.children[0]
    assert child.rewinds == [12] and stream.output is not None and stream.output.committed == 12
    _feed(stream, "seg-a", np.concatenate([np.zeros(12_000, np.int16), _pcm(1.0, 24_000)]), 6_000)
    stream.phrase_done("seg-a")
    stream.output_end("turn-1", 1)
    stream.pump()
    again = [frame.offset for frame in frames[28:]]
    assert again[0] == 12 * 960  # from the frame the prefix ends in, made again
    assert again == [index * 960 for index in range(12, 38)]


def test_a_cancel_that_lands_while_its_output_opens_still_cancels_it() -> None:
    # Review finding (2026-10-31): ``cancel`` (event loop) between phrase_start's check and the new output marked
    # the previous output, and the cancelled turn's frames went out.
    stream, _session, frames = _stream()
    stream.phrase_start("turn-1", 1, "seg-a", 16_000)
    stream.cancel("turn-2", 2)  # arrives while turn-2's phrase_start is past its check
    stream._open("turn-2", 2)
    stream.output.start_segment("seg-b", 16_000)  # type: ignore[union-attr]
    stream.pcm("seg-b", 0, _pcm(1.0, 16_000))
    assert stream.output is not None and stream.output.cancelled and stream.pump() == 0 and frames == []


def test_unknown_dropped_or_cancelled_speculation_changes_nothing() -> None:
    stream, _session, frames = _stream()
    stream.phrase_start("turn-1", 1, "seg-a", 24_000)
    stream.spec_bind("never-copied", "turn-1", 1, "seg-a")
    assert stream.output is not None and stream.output.output_id == "turn-1" and frames == []
    _speculate(stream, "gen-2", 2.0)
    stream.spec_drop("gen-2")
    assert stream.speculative == {}
    _speculate(stream, "gen-3", 2.0)
    stream.cancel("turn-2", 2)
    stream.spec_bind("gen-3", "turn-2", 2, "seg-b")
    assert frames == [] and "gen-3" in stream.speculative


def test_a_later_phrase_claiming_speculation_joins_the_replys_own_motion() -> None:
    stream, session, frames = _stream()
    stream.phrase_start("turn-1", 1, "seg-a", 24_000)
    _feed(stream, "seg-a", _pcm(1.0, 24_000), 4_800)
    stream.phrase_done("seg-a")
    sent_before = len(frames)
    _speculate(stream, "gen-1", 1.0)
    stream.phrase_start("turn-1", 1, "seg-b", 24_000)
    stream.spec_bind("gen-1", "turn-1", 1, "seg-b")
    assert len(frames) == sent_before and stream.session is session  # no speculative frames: they start at rest
    assert stream.output is not None and stream.output.segment("seg-b").samples == 24_000


def test_a_bound_speculation_with_trimmed_silence_stamps_frames_on_the_browsers_timeline() -> None:
    stream, _session, frames = _stream()
    _speculate(stream, "gen-1", 2.0)
    stream.phrase_start("turn-1", 1, "seg-a", 24_000)
    stream.spec_bind("gen-1", "turn-1", 1, "seg-a", trim=1_000)
    # Frames 0 and 1 (copy samples 0 and 960) are in silence the browser never got; frame 2 is browser 920.
    assert [frame.offset for frame in frames[:2]] == [1_920 - 1_000, 2_880 - 1_000]
    assert len(frames) == 26
    assert stream.output is not None
    assert stream.output.output_seconds("seg-a", 0) == 1_000 / 24_000


def test_a_play_position_counts_from_when_it_arrived() -> None:
    clock = Clock()
    stream, _session, _frames = _stream(clock)
    stream.phrase_start("turn-1", 1, "seg-a", 24_000)
    _feed(stream, "seg-a", _pcm(1.0, 24_000), 4_800)
    clock.now = 105.0
    stream.play_position("seg-a", 2_400, received_at=104.5)
    assert stream.output is not None and stream.output.play_anchor == (0.1, 104.5)


def test_a_finished_reply_sends_its_frames_back_to_the_idle_loop_once() -> None:
    stream, _session, frames = _stream(transitions=True)
    stream.phrase_start("turn-1", 1, "s1", 24_000)
    _feed(stream, "s1", _pcm(1.0, 24_000), 2_400)
    stream.phrase_done("s1")
    stream.output_end("turn-1", 1)
    stream.pump()
    stream.pump()
    transition = [frame for frame in frames if frame.output_id == TRANSITION_OUTPUT_ID]
    speech = [frame for frame in frames if frame.output_id != TRANSITION_OUTPUT_ID]
    assert [frame.jpeg for frame in transition] == [b"transition-0", b"transition-1", b"transition-2"]
    assert {(frame.epoch, frame.count, frame.frame_ms) for frame in transition} == {(1, 3, 40)}
    assert frames.index(transition[0]) > frames.index(speech[-1])  # after the reply's last frame


def test_a_cancelled_or_unfinished_reply_sends_no_transition() -> None:
    stream, _session, frames = _stream(transitions=True)
    stream.phrase_start("turn-1", 1, "s1", 24_000)
    _feed(stream, "s1", _pcm(1.0, 24_000), 2_400)
    stream.pump()
    assert not any(frame.output_id == TRANSITION_OUTPUT_ID for frame in frames)  # not ended yet
    stream.cancel("turn-1", 1)
    stream.output_end("turn-1", 1)
    stream.pump()
    assert not any(frame.output_id == TRANSITION_OUTPUT_ID for frame in frames)

