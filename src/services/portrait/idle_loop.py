"""The portrait's idle loop: which stretch of a silent render loops best (roadmap Phase 3, "Rest pose and idle loop").

FLOAT cannot be told to end on a chosen pose, so the idle loop is cut from a longer render of silence that starts
at the rest pose (motion latent zero: the source portrait itself). Of that render the loop keeps the least-moving
span (the one whose frames stay closest to the rest pose) and, inside it, the stretch between the two frames
whose motion latents are closest, so the jump from its last frame back to its first is the smallest available.
A reply's motion starts from the loop's first frame (the browser holds the loop there once the user stops speaking),
and a reply ends with rendered frames back to it, so the browser never blends two different poses.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from app.conversation.portrait_stream_contract import QUALITY_LEVELS

# About 12 s of silence rendered, a ~6 s span kept, and a loop of at least 4 s (25 frames a second).
IDLE_RENDER_FRAMES = 300
IDLE_SPAN_FRAMES = 150
IDLE_MIN_LOOP_FRAMES = 100
# Frames sent for the idle loop are stamped with this segment; their offset is the frame's index in the loop.
IDLE_OUTPUT_ID = "idle"
IDLE_SEGMENT_ID = "idle"
# FLOAT's own motion never blinks (none in 12 s of rendered silence or in 140 s of a recorded call, 2026-10-31), so
# the idle face blinks along the motion decoder's eyelid direction: the 15th of its 20 orthonormal directions (a
# model property, the same for every face). Its coordinate at -4 nearly shuts the eyes, at -6.5 closes them on the
# faces tried, and past -8 distorts the face.
EYELID_DIRECTION = 14
EYELID_CLOSED = -6.5
# A blink's closure frame by frame at 25 frames a second (about 280 ms): shut fast, open slower.
BLINK_ENVELOPE = (0.35, 0.8, 1.0, 0.95, 0.7, 0.4, 0.15)
# A blink at the loop's first frame, sent after the loop: the browser plays it while it holds the face near there.
BLINK_OUTPUT_ID = "blink"


def blink(latents: Any, eyelid: Any, center: int) -> Any:
    """``latents`` (frames x dim, a tensor or an array) with a blink fullest at ``center``.

    Each frame's eyelid coordinate moves toward closed by the envelope's weight; the rest of its motion is kept.
    """
    out = latents.clone() if hasattr(latents, "clone") else latents.copy()
    first = center - BLINK_ENVELOPE.index(1.0)
    for offset, weight in enumerate(BLINK_ENVELOPE):
        index = first + offset
        if 0 <= index < out.shape[0]:
            out[index] = out[index] + weight * (EYELID_CLOSED - float(out[index] @ eyelid)) * eyelid
    return out


def loop_blink_center(frames: int, step: int) -> int:
    """Where the loop blinks: near its middle, away from the first frames the browser sways over and from the wrap,
    on a frame every quality level sends (a multiple of the largest idle frame step)."""
    return (frames // (2 * step)) * step


def idle_frame_step(level: int) -> int:
    """How many rendered frames each idle frame covers: half the level's frame rate.

    Idle motion is slow, and the loop goes out in one burst at the start of a call.
    """
    return 2 * QUALITY_LEVELS[level][1]


def choose_loop(latents: np.ndarray, *, span: int = IDLE_SPAN_FRAMES,
                min_loop: int = IDLE_MIN_LOOP_FRAMES) -> tuple[int, int]:
    """The loop ``[start, stop)`` in ``latents`` (frames x dim); frame ``stop`` is the one closest to ``start``."""
    frames = int(latents.shape[0])
    if frames < 2:
        return 0, frames
    span = max(2, min(span, frames))
    min_loop = max(1, min(min_loop, span - 1))
    distances = np.linalg.norm(latents, axis=1)
    # The least-moving span: the smallest largest distance from the rest pose (earliest on ties).
    worst = [float(distances[start:start + span].max()) for start in range(frames - span + 1)]
    base = int(np.argmin(worst))
    window = latents[base:base + span]
    best: tuple[float, int, int] | None = None
    for start in range(span - min_loop):
        gaps = np.linalg.norm(window[start + min_loop:] - window[start], axis=1)
        nearest = int(np.argmin(gaps))
        if best is None or float(gaps[nearest]) < best[0]:
            best = (float(gaps[nearest]), start, start + min_loop + nearest)
    assert best is not None
    return base + best[1], base + best[2]


__all__ = ["BLINK_ENVELOPE", "BLINK_OUTPUT_ID", "EYELID_CLOSED", "EYELID_DIRECTION", "IDLE_MIN_LOOP_FRAMES",
           "IDLE_OUTPUT_ID", "IDLE_RENDER_FRAMES", "IDLE_SEGMENT_ID", "IDLE_SPAN_FRAMES", "blink", "choose_loop",
           "idle_frame_step", "loop_blink_center"]
