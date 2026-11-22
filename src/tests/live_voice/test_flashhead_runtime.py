"""FlashHead Lite's audio window: each pass hears the 8 s of speech ending with its new frames, padded at the start."""
from __future__ import annotations

import importlib
import sys
import types

import numpy as np
import pytest

from services.portrait.scheduler import plan_pass


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


def _speech(module, frames: int) -> np.ndarray:
    """Audio whose every sample names its frame (1-based, so padding reads 0)."""
    return np.repeat(np.arange(1, frames + 1, dtype=np.float32), module.SAMPLES_PER_FRAME)


def _frames(module, buffer: np.ndarray) -> list[int]:
    return [int(value) for value in buffer[:: module.SAMPLES_PER_FRAME]]


def test_a_pass_hears_exactly_the_model_audio_window(flashhead_runtime) -> None:
    module = flashhead_runtime
    settings = module.STREAM_SETTINGS

    assert settings.context + settings.window == module.AUDIO_FRAMES
    assert settings.window == module.NEW_FRAMES
    assert settings.carry == module.MOTION_FRAMES
    assert settings.lookahead == 0


def test_a_start_waits_for_the_video_to_be_a_whole_pass_ahead(flashhead_runtime) -> None:
    # The browser's start hold (PORTRAIT_START_RULES) follows the engine's passes: the first pass and the next.
    from app.conversation.portrait_stream_contract import PORTRAIT_START_RULES

    settings = flashhead_runtime.STREAM_SETTINGS
    hold_ms, lead_ms = PORTRAIT_START_RULES["flashhead-lite"]
    assert lead_ms == (settings.first_hop + settings.hop) * 40
    assert PORTRAIT_START_RULES["float"] == (250, 0)


def test_the_first_pass_pads_the_window_before_the_speech(flashhead_runtime) -> None:
    module = flashhead_runtime
    plan = plan_pass(module.STREAM_SETTINGS, committed=0, available=30, flush_to=None)
    speech = _speech(module, 30)

    frames = _frames(module, module.audio_buffer(speech[plan.buffer_start * module.SAMPLES_PER_FRAME:], plan))

    assert len(frames) == module.AUDIO_FRAMES
    assert frames[: module.AUDIO_FRAMES - module.NEW_FRAMES] == [0] * (module.AUDIO_FRAMES - module.NEW_FRAMES)
    assert frames[-module.NEW_FRAMES:] == list(range(1, module.NEW_FRAMES + 1))


def test_a_later_pass_hears_the_eight_seconds_ending_with_its_frames(flashhead_runtime) -> None:
    module = flashhead_runtime
    committed = 8 + 9 * module.NEW_FRAMES
    plan = plan_pass(module.STREAM_SETTINGS, committed=committed, available=committed + 40, flush_to=None)
    speech = _speech(module, committed + 40)

    frames = _frames(module, module.audio_buffer(speech[plan.buffer_start * module.SAMPLES_PER_FRAME:], plan))

    end = committed + module.NEW_FRAMES
    assert frames == list(range(end - module.AUDIO_FRAMES + 1, end + 1))


def test_a_flush_pads_the_missing_end_with_silence(flashhead_runtime) -> None:
    module = flashhead_runtime
    committed = 8 + 9 * module.NEW_FRAMES
    plan = plan_pass(module.STREAM_SETTINGS, committed=committed, available=committed + 5, flush_to=committed + 5)
    speech = _speech(module, committed + 5)

    frames = _frames(module, module.audio_buffer(speech[plan.buffer_start * module.SAMPLES_PER_FRAME:], plan))

    end = committed + module.NEW_FRAMES
    assert plan.padded
    assert frames[: module.AUDIO_FRAMES - module.NEW_FRAMES + 5] == list(range(end - module.AUDIO_FRAMES + 1,
                                                                              committed + 6))
    assert frames[-(module.NEW_FRAMES - 5):] == [0] * (module.NEW_FRAMES - 5)


def test_the_idle_loop_keeps_the_motion_not_the_stillest_stretch(flashhead_runtime) -> None:
    # Owner report 2026-11-21: cut where the render stayed nearest the picture, the loop was 4 s of a near-still face.
    # A render of 360 frames: still for its first pass, swaying from there, a blink at 150-155; the sway comes back to
    # its start every 100 frames.
    frames = np.arange(360)
    features = np.zeros((360, 4))
    features[24:, 0] = np.sin(2 * np.pi * (frames[24:] - 24) / 100)
    features[24:, 1] = np.cos(2 * np.pi * (frames[24:] - 24) / 100) - 1
    features[150:156, 2] = 5.0  # the blink
    start, stop = flashhead_runtime.idle_loop_bounds(features)
    assert start >= 24  # never the first pass, which is still the picture
    assert stop - start >= flashhead_runtime.IDLE_MIN_LOOP_FRAMES
    assert start <= 150 and stop >= 156  # long enough to hold a blink
    assert np.linalg.norm(features[stop] - features[start]) < 0.1  # and seamless
    # A render shorter than the loop asked for still gives a loop.
    assert flashhead_runtime.idle_loop_bounds(features[:40])[1] <= 40


def _render(frames: int = 360) -> np.ndarray:
    """A silent render's grey frames (frames x 256 x 256): a still face with a little noise on every frame."""
    rng = np.random.default_rng(7)
    face = rng.uniform(40, 200, (256, 256))
    return face + rng.normal(0, 1.5, (frames, 256, 256))


def _eye_bands(render: np.ndarray) -> np.ndarray:
    return render[:, 64:141, 64:192]  # the eye band's rows and columns of a 256 px frame


def test_the_blink_twin_comes_from_the_renders_own_brief_blink(flashhead_runtime) -> None:
    # Owner report 2026-11-21: FlashHead's idle loop looked like a still image; the browser's blinks showed nothing
    # because a FlashHead loop frame's eyes-shut twin was the frame itself.
    render = _render()
    render[:12, 80:120, 80:176] += 60  # the first pass settles from the picture: never the blink
    render[100:180] += 25  # a long change over the whole frame (light, a look away): not a blink
    render[249:254, 90:110, 80:176] -= 50  # the eyes shut for five frames
    render[251, 90:110, 80:176] -= 30  # most shut at the middle one
    assert flashhead_runtime.blink_frame(_eye_bands(render), render) == 251


def test_a_render_without_a_clear_blink_keeps_its_frames_as_their_own_twins(flashhead_runtime) -> None:
    render = _render()
    render[100:180, 90:110, 80:176] -= 50  # the eyes change for 3 s (a squint): too long for a blink
    render[352:, 90:110, 80:176] -= 50  # a change cut off by the render's end
    assert flashhead_runtime.blink_frame(_eye_bands(render), render) is None
    assert flashhead_runtime.blink_frame(_eye_bands(render[:30]), render[:30]) is None
