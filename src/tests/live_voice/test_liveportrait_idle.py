"""LivePortrait idle loops: the idle motion's file and loop, and FlashHead's choice of idle loop."""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from services.portrait import liveportrait_idle as idle
from services.portrait.liveportrait_idle import IdleMotion, IdleMotionError


def _motion(frames: int = 276, *, amplitude: float = 1.0) -> IdleMotion:
    """A slow sway in every part of the motion, back to its first frame at frame 220 (and 110)."""
    phase = np.sin(np.linspace(0, 2.5 * np.pi, frames, dtype=np.float32))[:, None]
    return IdleMotion(pose=np.repeat(phase * amplitude, 3, axis=1),
                      exp=np.repeat(phase[:, :, None] * 0.01 * amplitude, idle.KEYPOINTS, axis=1).repeat(3, axis=2),
                      t=np.repeat(phase * 0.002 * amplitude, 2, axis=1), scale=phase * 0.002 * amplitude)


def test_a_tracked_motion_is_each_frames_change_from_the_first() -> None:
    frames = 12
    pose = np.full((frames, 3), 4.0, dtype=np.float32)
    pose[6:, 1] += 2.0
    exp = np.full((frames, idle.KEYPOINTS, 3), 0.1, dtype=np.float32)
    t = np.tile(np.array([[0.1, 0.2, 0.7]], dtype=np.float32), (frames, 1))
    scale = np.full((frames, 1), 2.0, dtype=np.float32)
    scale[-1] = 2.2
    motion = idle.relative_motion(pose, exp, t, scale)
    assert motion.pose[0].tolist() == [0.0, 0.0, 0.0] and motion.pose[-1, 1] == pytest.approx(2.0)
    assert motion.t.shape == (frames, 2) and np.allclose(motion.t, 0)  # only x and y; no depth
    assert np.allclose(motion.exp, 0)
    assert motion.scale[-1, 0] == pytest.approx(0.1 / idle.SMOOTH_FRAMES * 3, abs=1e-6)  # 10% larger, smoothed


def test_smoothing_keeps_the_length_and_a_still_motion() -> None:
    still = np.full((9, 2), 3.0, dtype=np.float32)
    assert np.allclose(idle.smooth(still, 5), still)
    step = np.r_[np.zeros(5), np.ones(5)].astype(np.float32)
    smoothed = idle.smooth(step, 5)
    assert smoothed.shape == step.shape and smoothed[0] == 0 and smoothed[-1] == 1 and 0 < smoothed[5] < 1


def test_the_loop_ends_where_the_motion_comes_back_to_its_first_frame() -> None:
    motion = _motion(276)
    loop = idle.close_loop(motion)
    assert loop.frames == 220
    for name in ("pose", "exp", "t", "scale"):
        values = getattr(loop, name)
        assert np.allclose(values[0], 0)  # the portrait's own pose
        # The last frame is one step from the first: no jump when the loop starts again.
        assert np.abs(values[-1]).max() <= np.abs(np.diff(values, axis=0)).max() + 1e-6


def test_the_loop_ignores_the_lips_and_ramps_out_what_is_left() -> None:
    motion = _motion(276)
    lips = list(idle.LIP_KEYPOINTS)
    motion.exp[:, lips] = 0.5  # held lips never decide the loop
    offset = motion.pose.copy()
    offset[:, 0] += np.linspace(0, 0.33, 276, dtype=np.float32)  # a drift: the loop's end is not quite its first frame
    loop = idle.close_loop(IdleMotion(pose=offset, exp=motion.exp, t=motion.t, scale=motion.scale))
    end = loop.frames
    assert 215 <= end <= 225  # near the full cycle, whatever the lips hold
    ramp = np.arange(end, dtype=np.float32) / end
    assert np.allclose(loop.pose[:, 0], offset[:end, 0] - ramp * offset[end, 0], atol=1e-5)
    assert np.allclose(loop.exp[:, lips], 0.5 * (1 - ramp)[:, None, None], atol=1e-5)


def test_a_motion_too_short_for_a_loop_is_refused() -> None:
    with pytest.raises(IdleMotionError, match="needs more than"):
        idle.close_loop(_motion(idle.MIN_LOOP_FRAMES))


def test_the_motion_file_round_trips(tmp_path: Path) -> None:
    loop = idle.close_loop(_motion(276))
    path = tmp_path / "motion" / idle.MOTION_FILE
    loop.save(path)
    loaded = IdleMotion.load(path)
    assert loaded.frames == loop.frames
    assert all(np.array_equal(getattr(loaded, name), getattr(loop, name)) for name in ("pose", "exp", "t", "scale"))


@pytest.mark.parametrize(("change", "message"), [
    (lambda m: IdleMotion(m.pose[:100], m.exp[:100], m.t[:100], m.scale[:100]), "frames"),
    (lambda m: IdleMotion(m.pose * 30, m.exp, m.t, m.scale), "pose moves more"),
    (lambda m: IdleMotion(m.pose, m.exp[:, :20], m.t, m.scale), "exp is"),
    (lambda m: IdleMotion(m.pose, m.exp, np.full_like(m.t, np.nan), m.scale), "not finite"),
])
def test_a_motion_that_does_not_sit_still_or_is_malformed_is_refused(tmp_path: Path, change, message) -> None:
    path = tmp_path / idle.MOTION_FILE
    change(idle.close_loop(_motion(276))).save(path)
    with pytest.raises(IdleMotionError, match=message):
        IdleMotion.load(path)


def test_a_motion_at_another_frame_rate_or_not_a_motion_is_refused(tmp_path: Path) -> None:
    loop = idle.close_loop(_motion(276))
    path = tmp_path / "other.npz"
    np.savez(path, pose=loop.pose, exp=loop.exp, t=loop.t, scale=loop.scale, fps=np.array(30))
    with pytest.raises(IdleMotionError, match="30 fps"):
        IdleMotion.load(path)
    (tmp_path / "text.npz").write_text("not a motion")
    with pytest.raises(IdleMotionError, match="cannot be read"):
        IdleMotion.load(tmp_path / "text.npz")


def test_the_motion_file_is_the_setting_then_the_users_own_then_the_shipped_one(monkeypatch, tmp_path: Path) -> None:
    own = tmp_path / "portrait" / idle.MOTION_FILE
    monkeypatch.setattr(idle, "user_motion_path", lambda: own)
    monkeypatch.delenv(idle.MOTION_ENV, raising=False)
    assert idle.motion_path() == idle.SHIPPED_MOTION
    idle.close_loop(_motion(276)).save(own)
    assert idle.motion_path() == own
    monkeypatch.setenv(idle.MOTION_ENV, str(tmp_path / "mine.npz"))
    assert idle.motion_path() == tmp_path / "mine.npz"


def test_the_shipped_motion_is_a_valid_closed_loop() -> None:
    motion = IdleMotion.load(idle.SHIPPED_MOTION)
    assert motion.frames > idle.MIN_LOOP_FRAMES
    for name in ("pose", "t", "scale"):  # it starts and ends within a step of the portrait's own pose
        values = getattr(motion, name)
        step = np.abs(np.diff(values, axis=0)).max()
        assert np.abs(values[0]).max() <= step and np.abs(values[-1]).max() <= step


# --- FlashHead's choice of idle loop ------------------------------------------------------------------------


@pytest.fixture
def flashhead_runtime(monkeypatch):
    """``services.portrait.flashhead_runtime`` over a stand-in torch (the test interpreter has none)."""
    torch = types.ModuleType("torch")
    nn = types.ModuleType("torch.nn")
    nn.Module = type("Module", (), {})
    functional = types.ModuleType("torch.nn.functional")
    nn.functional = functional
    torch.nn = nn
    torch.bfloat16 = "bfloat16"
    torch.no_grad = lambda: (lambda function: function)
    for name, module in {"torch": torch, "torch.nn": nn, "torch.nn.functional": functional}.items():
        monkeypatch.setitem(sys.modules, name, module)
    for name in ("services.portrait.float_runtime", "services.portrait.flashhead_runtime"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    yield importlib.import_module("services.portrait.flashhead_runtime")
    for name in ("services.portrait.float_runtime", "services.portrait.flashhead_runtime"):
        sys.modules.pop(name, None)


def _installed(monkeypatch, tmp_path: Path, *, models: bool = True, motion: bool = True) -> None:
    path = tmp_path / idle.MOTION_FILE
    if motion:
        idle.close_loop(_motion(276)).save(path)
    monkeypatch.setenv(idle.MOTION_ENV, str(path))
    found = {model_id: tmp_path / model_id for model_id in idle.MODELS}
    monkeypatch.setattr(idle, "folders", lambda: found if models else None)


@pytest.mark.parametrize(("models", "motion"), [(False, True), (True, False)])
def test_without_liveportrait_or_a_motion_the_idle_loop_is_flashheads_own(flashhead_runtime, monkeypatch,
                                                                         tmp_path: Path, models, motion) -> None:
    _installed(monkeypatch, tmp_path, models=models, motion=motion)
    monkeypatch.setattr(idle, "LivePortrait", lambda folders: pytest.fail("LivePortrait must not load"))
    assert flashhead_runtime.load_liveportrait() == (None, None)


def test_liveportrait_that_fails_to_load_leaves_flashheads_own_loop(flashhead_runtime, monkeypatch,
                                                                    tmp_path: Path) -> None:
    _installed(monkeypatch, tmp_path)

    def broken(folders):
        raise RuntimeError("code file changed")

    monkeypatch.setattr(idle, "LivePortrait", broken)
    assert flashhead_runtime.load_liveportrait() == (None, None)


def test_installed_liveportrait_and_motion_make_the_idle_loop(flashhead_runtime, monkeypatch, tmp_path: Path) -> None:
    _installed(monkeypatch, tmp_path)
    monkeypatch.setattr(idle, "LivePortrait", lambda folders: ("networks", sorted(folders)))
    networks, motion = flashhead_runtime.load_liveportrait()
    assert networks == ("networks", sorted(idle.MODELS))
    assert motion.frames == 220


def test_liveportraits_twins_replace_the_blink_search(flashhead_runtime) -> None:
    runtime = types.SimpleNamespace(idle_pixels=lambda portrait: None,
                                    silent_render=lambda portrait, seed: pytest.fail("no blink search"))
    portrait = types.SimpleNamespace(blink_searched=False, twins=object(), shut=None)
    flashhead_runtime.FlashHeadRuntime.find_blink(runtime, portrait)
    assert portrait.blink_searched is False


def test_the_loops_twins_are_liveportraits_when_it_made_the_loop(flashhead_runtime, monkeypatch) -> None:
    class Frames:
        def __init__(self, values: list[int]) -> None:
            self.values = values

        def __getitem__(self, index: slice) -> Frames:
            return Frames(self.values[index])

        def cuda(self) -> Frames:
            return self

    monkeypatch.setattr(flashhead_runtime, "encode_jpegs", lambda frames, level: [f"{v}" for v in frames.values])
    portrait = types.SimpleNamespace(blink_jpegs={}, idle_jpegs={}, twins=Frames([1, 2, 3, 4]), shut=None,
                                     opened=None)
    runtime = types.SimpleNamespace(idle_pixels=lambda portrait: Frames([0, 0, 0, 0]))
    level = next(index for index in range(8) if importlib.import_module(
        "services.portrait.idle_loop").idle_frame_step(index) == 2)
    assert flashhead_runtime.FlashHeadRuntime.blink_frames(runtime, portrait, level) == ["1", "3"]
