from __future__ import annotations

import base64
import io
import wave

import numpy as np
import pytest

from app.platform.voice import output_settings as controls

DEFAULTS = dict(controls.NEUTRAL)
RATE = 44_100


def _tone(frequency: float = 220.0, seconds: float = 2.0, amplitude: float = 0.5) -> np.ndarray:
    return amplitude * np.sin(2 * np.pi * frequency * np.arange(int(seconds * RATE)) / RATE)


def _wav(samples: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes((samples * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def _samples(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes)) as source:
        return np.frombuffer(source.readframes(source.getnframes()), dtype="<i2") / 32768.0


def _peak_hz(samples: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    return float(np.argmax(spectrum) * RATE / len(samples))


@pytest.mark.parametrize("engine", ["faster-qwen3-tts", "fish-s2-pro"])
def test_the_default_positions_change_nothing(engine):
    assert controls.sampling_overrides(engine, DEFAULTS) == {}
    assert controls.sampling_overrides(engine, {}) == {}
    assert controls.audio_adjustments(DEFAULTS) == {}
    audio = _wav(_tone())
    assert controls.adjust_wav(audio, controls.audio_adjustments(DEFAULTS)) is audio


def test_stability_and_style_steer_each_engines_own_sampling():
    assert controls.sampling_overrides("fish-s2-pro", {**DEFAULTS, "stability": 0.0, "style": 1.0}) == {
        "temperature": 1.0, "top_p": 0.95,
    }
    assert controls.sampling_overrides("fish-s2-pro", {**DEFAULTS, "stability": 1.0, "style": 0.0}) == {
        "temperature": 0.45, "top_p": 0.5,
    }
    assert controls.sampling_overrides("faster-qwen3-tts", {**DEFAULTS, "stability": 0.0, "style": 1.0}) == {
        "temperature": 1.1, "top_k": 100,
    }
    # Between the ends the mapping is continuous through each engine's default.
    assert controls.sampling_overrides("fish-s2-pro", {**DEFAULTS, "stability": 0.5})["temperature"] == pytest.approx(0.8)


def test_similarity_only_steers_qwen():
    assert controls.sampling_overrides("faster-qwen3-tts", {**DEFAULTS, "similarity": 0.3}) == {"xvec_only": True}
    assert controls.sampling_overrides("faster-qwen3-tts", {**DEFAULTS, "similarity": 0.6}) == {}
    assert controls.sampling_overrides("fish-s2-pro", {**DEFAULTS, "similarity": 0.3}) == {}
    assert controls.engine_controls("faster-qwen3-tts") == ["stability", "similarity", "style", "speed", "pitch", "volume"]
    assert controls.engine_controls("fish-s2-pro") == ["stability", "style", "speed", "pitch", "volume"]


@pytest.mark.parametrize("speed,semitones", [(1.5, 0), (0.75, 0), (1.0, 12), (1.0, -5), (1.25, 3)])
def test_speed_and_pitch_change_independently(speed, semitones):
    tone = _tone()

    changed = controls.change_speed_and_pitch(tone, RATE, speed, semitones)

    assert len(changed) / RATE == pytest.approx(2.0 / speed, abs=0.01)
    assert _peak_hz(changed) == pytest.approx(220 * 2 ** (semitones / 12), rel=0.01)
    # The waveform is spliced smoothly: no loss of level.
    assert np.sqrt(np.mean(changed ** 2)) == pytest.approx(0.5 / np.sqrt(2), rel=0.03)


def test_volume_is_a_gain_that_never_clips():
    quieter = _samples(controls.adjust_wav(_wav(_tone(amplitude=0.4)), {"volume": -6.0}))
    assert np.max(np.abs(quieter)) == pytest.approx(0.4 * 10 ** (-6 / 20), rel=0.01)

    louder = _samples(controls.adjust_wav(_wav(_tone(amplitude=0.8)), {"volume": 12.0}))
    assert np.max(np.abs(louder)) == pytest.approx(0.99, abs=0.01)


def test_out_of_range_values_are_clamped():
    assert controls.audio_adjustments({"speed": 0.0, "pitch": 40, "volume": "loud"}) == {"speed": 0.5, "pitch": 12.0}


def test_voice_studio_jobs_apply_the_sliders(monkeypatch):
    from app.platform.voice import jobs

    calls = []

    class FishEngine:
        provider_name = "fish-s2-pro"

        def generate_audio(self, text, **kwargs):
            calls.append(kwargs)
            audio = base64.b64encode(_wav(_tone(seconds=1.0))).decode("ascii")
            return {"success": True, "audio": audio, "sample_rate": RATE, "duration": 1.0}

    monkeypatch.setattr("app.providers.service.get_tts_provider", lambda name=None: FishEngine())
    settings = {**DEFAULTS, "stability": 1.0, "similarity": 0.1, "speed": 2.0, "volume": -6.0}

    wav_bytes, metadata = jobs._generate_audio_bytes("Hello.", speaker="voice-cloning:jinx",
                                                     payload={"output_settings": settings})

    assert calls[0]["temperature"] == 0.45
    assert "xvec_only" not in calls[0]  # Fish has no similarity control.
    assert metadata["duration"] == pytest.approx(0.5, abs=0.01)
    assert metadata["voice_controls"] == {"sampling": {"temperature": 0.45}, "audio": {"speed": 2.0, "volume": -6.0}}
    assert len(_samples(wav_bytes)) == pytest.approx(RATE / 2, abs=50)
