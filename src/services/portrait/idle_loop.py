"""The portrait's idle loop: which stretch of a silent render loops best (roadmap Phase 3, "Rest pose and idle loop").

FLOAT cannot be told to end on a chosen pose, so the idle loop is cut from a longer render of silence that starts
at the rest pose (motion latent zero: the source portrait itself). Of that render the loop keeps the least-moving
span (the one whose frames stay closest to the rest pose) and, inside it, the stretch between the two frames
whose motion latents are closest, so the jump from its last frame back to its first is the smallest available.
Speaking outputs also start from the rest pose, so the browser's crossfades between them and the loop move only a
small pose difference.
"""
from __future__ import annotations

import numpy as np

from app.conversation.portrait_stream_contract import QUALITY_LEVELS

# About 12 s of silence rendered, a ~6 s span kept, and a loop of at least 4 s (25 frames a second).
IDLE_RENDER_FRAMES = 300
IDLE_SPAN_FRAMES = 150
IDLE_MIN_LOOP_FRAMES = 100
# Frames sent for the idle loop are stamped with this segment; their offset is the frame's index in the loop.
IDLE_OUTPUT_ID = "idle"
IDLE_SEGMENT_ID = "idle"


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


__all__ = ["IDLE_MIN_LOOP_FRAMES", "IDLE_OUTPUT_ID", "IDLE_RENDER_FRAMES", "IDLE_SEGMENT_ID", "IDLE_SPAN_FRAMES",
           "choose_loop", "idle_frame_step"]
