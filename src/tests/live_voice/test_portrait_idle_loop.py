"""Choosing the portrait's idle loop from a silent render (roadmap Phase 3, "Rest pose and idle loop")."""
from __future__ import annotations

import numpy as np
import pytest

from services.portrait.idle_loop import EYELID_CLOSED, choose_loop, eye_region_mask, eyes_shut


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


def test_shut_eyes_move_only_the_eyelid_coordinate_of_every_frame() -> None:
    latents = _render(frames=40)
    eyelid = np.zeros(8)
    eyelid[3] = 1.0  # a unit direction, as the decoder's are
    shut = eyes_shut(latents, eyelid)
    assert np.allclose(shut @ eyelid, EYELID_CLOSED)
    assert np.allclose(np.delete(shut, 3, axis=1), np.delete(latents, 3, axis=1))  # the rest of the motion kept
    assert np.allclose(latents, _render(frames=40))  # the loop given is untouched


def _face_change(eyes_row: int = 215, eyes_column: int = 255, size: int = 512) -> np.ndarray:
    """What the eyelid direction changes, as measured on a real portrait: both eyes, then the mouth as much, the
    hairline and the jaw."""
    change = np.zeros((size, size), dtype=np.float32)
    change[eyes_row - 20:eyes_row + 20, eyes_column - 95:eyes_column - 25] = 30.0
    change[eyes_row - 20:eyes_row + 20, eyes_column + 25:eyes_column + 95] = 30.0
    change[310:370, 190:320] = 30.0  # the mouth
    change[20:60, 140:360] = 30.0  # the hairline
    change[:, 125:130] = 30.0  # the side of the head
    return change


def test_a_blink_takes_only_the_area_around_the_eyes() -> None:
    mask = eye_region_mask(_face_change())
    assert mask.shape == (512, 512) and mask.dtype == np.float32
    assert mask[215, 255 - 60] == pytest.approx(1.0, abs=0.05) and mask[215, 255 + 60] == pytest.approx(1.0, abs=0.05)
    assert mask[310:, :].max() == 0.0  # the mouth stays as the loop's frame has it
    assert mask[:120, :].max() == 0.0  # and the hairline


def test_the_blink_area_has_a_soft_edge() -> None:
    mask = eye_region_mask(_face_change())
    down_the_middle = mask[215:300, 255]
    assert np.all(np.diff(down_the_middle) <= 0)
    assert np.count_nonzero((down_the_middle > 0.02) & (down_the_middle < 0.98)) >= 8


def test_the_blink_area_follows_the_face() -> None:
    mask = eye_region_mask(_face_change(eyes_row=180, eyes_column=230))
    rows, columns = np.nonzero(mask > 0.5)
    assert abs(rows.mean() - 180) < 12 and abs(columns.mean() - 230) < 12


def test_a_render_that_did_not_change_still_gives_a_mask() -> None:
    assert eye_region_mask(np.zeros((64, 64), dtype=np.float32)).max() == pytest.approx(1.0, abs=0.05)
