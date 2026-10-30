"""Choosing the portrait's idle loop from a silent render (roadmap Phase 3, "Rest pose and idle loop")."""
from __future__ import annotations

import numpy as np

from services.portrait.idle_loop import choose_loop


def _render(frames: int = 300, dim: int = 8) -> np.ndarray:
    """A slow sway near the rest pose, with a large head movement in frames 20-70."""
    time = np.arange(frames)[:, None]
    phases = np.linspace(0.0, 1.0, dim)[None, :]
    latents = 0.1 * np.sin(2 * np.pi * (time / 37.0 + phases))
    latents[20:70] += 2.0
    return latents


def test_the_loop_avoids_the_big_movement_and_closes_on_its_nearest_frame() -> None:
    latents = _render()
    start, stop = choose_loop(latents)
    assert start >= 70  # the least-moving span leaves out frames 20-70
    assert stop - start >= 100
    # The sway repeats every 37 frames, so the frame after the loop is (almost) its first.
    assert np.linalg.norm(latents[stop] - latents[start]) < 0.02
    assert stop < len(latents)


def test_short_renders_still_give_a_loop() -> None:
    latents = _render(frames=40)
    start, stop = choose_loop(latents)
    assert 0 <= start < stop <= len(latents)
    assert choose_loop(latents[:1]) == (0, 1)
