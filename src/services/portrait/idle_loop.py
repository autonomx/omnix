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
# model property, the same for every face). Its coordinate at -4 nearly shuts the eyes, at -6.5 closes them hard on
# the faces tried, and past -8 distorts the face. -5 is a mild blink (rated too forced at -6.5, 2026-11-01).
EYELID_DIRECTION = 14
EYELID_CLOSED = -5.0
# Each idle frame with its eyes shut, sent after the loop: the browser blinks wherever the loop is by fading a frame
# into its shut twin and back.
BLINK_OUTPUT_ID = "blink"
# The direction also presses the lips and moves the jaw and hairline about as much as the eyelids (measured
# 2026-11-01), so a twin takes only the area around the eyes from the shut render. The area is found from where the
# render changes, inside these fractions of the frame (they hold the eyes and brows of FLOAT's face crop, not its
# hairline or mouth), and its edge fades out from EYE_REGION_SOLID of its radius.
EYE_SEARCH_ROWS = (0.25, 0.55)
EYE_SEARCH_COLUMNS = (0.25, 0.75)
EYE_REGION_HALF_WIDTH = 0.26
EYE_REGION_HALF_HEIGHT = 0.10
EYE_REGION_SOLID = 0.7


def eyes_shut(latents: Any, eyelid: Any) -> Any:
    """``latents`` (frames x dim, a tensor or an array) with each frame's eyelid coordinate set to closed; the rest of
    its motion is kept."""
    coordinates = latents @ eyelid
    return latents + (EYELID_CLOSED - coordinates)[:, None] * eyelid[None, :]


def eye_region_mask(change: np.ndarray) -> np.ndarray:
    """How much of the shut render each pixel takes (height x width, 0 to 1), from how much each pixel changed."""
    height, width = change.shape
    top, bottom = int(height * EYE_SEARCH_ROWS[0]), int(height * EYE_SEARCH_ROWS[1])
    left, right = int(width * EYE_SEARCH_COLUMNS[0]), int(width * EYE_SEARCH_COLUMNS[1])
    weights = change[top:bottom, left:right].astype(np.float64) ** 2
    total = float(weights.sum())
    if total > 0.0:
        centre_y = top + float((weights.sum(axis=1) * np.arange(bottom - top)).sum()) / total
        centre_x = left + float((weights.sum(axis=0) * np.arange(right - left)).sum()) / total
    else:
        centre_y, centre_x = (top + bottom) / 2, (left + right) / 2
    rows, columns = np.mgrid[:height, :width]
    radius = np.hypot((columns - centre_x) / (width * EYE_REGION_HALF_WIDTH),
                      (rows - centre_y) / (height * EYE_REGION_HALF_HEIGHT))
    fade = np.clip((1.0 - radius) / (1.0 - EYE_REGION_SOLID), 0.0, 1.0)
    return (fade * fade * (3.0 - 2.0 * fade)).astype(np.float32)


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


__all__ = ["BLINK_OUTPUT_ID", "EYELID_CLOSED", "EYELID_DIRECTION", "IDLE_MIN_LOOP_FRAMES", "IDLE_OUTPUT_ID",
           "IDLE_RENDER_FRAMES", "IDLE_SEGMENT_ID", "IDLE_SPAN_FRAMES", "choose_loop", "eye_region_mask", "eyes_shut",
           "idle_frame_step"]
