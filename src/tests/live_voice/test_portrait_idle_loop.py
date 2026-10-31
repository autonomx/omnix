"""Choosing the portrait's idle loop from a silent render (roadmap Phase 3, "Rest pose and idle loop")."""
from __future__ import annotations

import numpy as np
import pytest

from services.portrait.idle_loop import BLINK_ENVELOPE, EYELID_CLOSED, blink, choose_loop, loop_blink_center


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


def test_a_blink_moves_only_the_eyelid_coordinate_closing_it_fully_at_its_centre() -> None:
    latents = _render(frames=40)
    eyelid = np.zeros(8)
    eyelid[3] = 1.0  # a unit direction, as the decoder's are
    blinked = blink(latents, eyelid, center=20)
    first = 20 - BLINK_ENVELOPE.index(1.0)
    changed = [index for index in range(40) if not np.allclose(blinked[index], latents[index])]
    assert changed == list(range(first, first + len(BLINK_ENVELOPE)))
    assert np.allclose(np.delete(blinked, 3, axis=1), np.delete(latents, 3, axis=1))  # the rest of the motion kept
    assert float(blinked[20] @ eyelid) == pytest.approx(EYELID_CLOSED)
    assert np.allclose(latents[20], _render(frames=40)[20])  # a copy: the loop given is untouched
    assert len(blink(latents, eyelid, center=0)) == 40  # a blink cut off by the start stays in range


def test_the_loop_blinks_mid_loop_on_a_frame_every_level_sends() -> None:
    assert loop_blink_center(115, 4) == 56 and 56 % 4 == 0
    assert loop_blink_center(100, 2) == 50
