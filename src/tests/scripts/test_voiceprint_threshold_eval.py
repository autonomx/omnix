"""The voiceprint threshold measurement (companion 2.3), with a fake speaker model in place of TitaNet."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "voiceprint_threshold_eval.py"
spec = importlib.util.spec_from_file_location("voiceprint_threshold_eval_test_target", SCRIPT)
assert spec is not None and spec.loader is not None
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)


def wav(samples: np.ndarray, *, rate: int = 16_000, channels: int = 1) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    if channels > 1:
        pcm = np.repeat(pcm, channels)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


def tone(frequency: float, seconds: float, *, rate: int = 16_000, level: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (level * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def fake_embed(payload: bytes, _filename: str) -> list[float]:
    """A "voice" is the tone's dominant frequency band: same band, same direction."""
    samples = target.read_wav_16k(payload)
    spectrum = np.abs(np.fft.rfft(samples, n=16_000))[:4096]
    bands = spectrum.reshape(64, -1).sum(axis=1)
    return list(bands / (np.linalg.norm(bands) or 1.0))


def test_wavs_of_any_rate_and_channels_become_16k_mono() -> None:
    stereo_48k = target.read_wav_16k(wav(tone(200, 1.0, rate=48_000), rate=48_000, channels=2))
    assert len(stereo_48k) == 16_000
    assert target.read_wav_16k(wav(tone(200, 0.5))).shape == (8_000,)


def test_segments_drop_short_tails_and_silence() -> None:
    audio = np.concatenate([tone(200, 4.0), np.zeros(32_000, dtype=np.float32), tone(200, 1.0), tone(200, 0.5)])
    # 4 s of voice is two pieces, the 2 s of silence is dropped, then a 1.5 s tail (kept: over 0.8 s).
    assert [len(piece) for piece in target.segments(audio, 2.0)] == [32_000, 32_000, 24_000]
    # A 0.5 s tail is under the live socket's minimum.
    assert [len(piece) for piece in target.segments(tone(200, 2.5), 2.0)] == [32_000]


def test_threshold_keeps_false_rejects_at_one_percent() -> None:
    assert target.choose_threshold([0.9] * 98 + [0.2, 0.3]) == 0.3  # one reject of 100 allowed: the 0.2
    assert target.choose_threshold([0.9] * 198 + [0.2, 0.3]) == 0.9  # two of 200: both
    assert target.choose_threshold([0.7, 0.8]) == 0.7
    assert target.choose_threshold([]) is None


def test_evaluate_reports_false_accepts_and_warns_on_small_samples() -> None:
    report = target.evaluate(np.ones(4) / 2, {"owner": [0.8, 0.9, 0.7], "owner_over_tv": [0.6], "tv": [0.1, 0.65]})

    assert report["threshold"] == 0.6
    assert report["labels"]["tv"]["false_accept"] == 0.5
    assert report["labels"]["owner"]["accepted"] == 1.0
    assert report["owner_segments"] == 4
    assert any("100+" in warning for warning in report["warnings"])


def test_evaluate_without_other_voices_says_so() -> None:
    report = target.evaluate(np.ones(4) / 2, {"owner": [0.8] * 120})
    assert report["warnings"] == ["no other voices: record the TV and another person so false accepts can be measured"]


def test_main_scores_folders_against_the_enrolled_print(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    enrol, clips = tmp_path / "enrol", tmp_path / "clips"
    enrol.mkdir()
    for index in range(3):
        (enrol / f"p{index}.wav").write_bytes(wav(tone(220 + index, 5.0)))
    for label, frequency in (("owner", 221), ("tv", 1_800)):
        (clips / label).mkdir(parents=True)
        (clips / label / "a.wav").write_bytes(wav(tone(frequency, 6.0)))
    output = tmp_path / "report.json"

    code = target.main(["--enrol", str(enrol), "--clips", str(clips), "--output", str(output)], embed=fake_embed)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert json.loads(capsys.readouterr().out) == report
    assert report["labels"]["owner"]["count"] == 3
    assert report["labels"]["owner"]["min"] > 0.9
    assert report["labels"]["tv"]["max"] < 0.2
    assert report["labels"]["tv"]["false_accept"] == 0.0


def test_main_fails_without_owner_clips(tmp_path: Path) -> None:
    enrol, clips = tmp_path / "enrol", tmp_path / "clips"
    enrol.mkdir()
    (clips / "tv").mkdir(parents=True)
    for index in range(2):
        (enrol / f"p{index}.wav").write_bytes(wav(tone(220, 4.0)))
    (clips / "tv" / "a.wav").write_bytes(wav(tone(1_800, 3.0)))

    assert target.main(["--enrol", str(enrol), "--clips", str(clips)], embed=fake_embed) == 1
