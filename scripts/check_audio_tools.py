"""Phase 4 real-model check for Voice Studio's audio tools (run in the omnix-audio environment).

- Isolation: a clean voice mixed with a synthetic music bed (chords, bass and
  noise-burst percussion) at 0 dB; SI-SDR of the separated vocals against the
  clean voice, minus SI-SDR of the mix. Exit: a gain of at least 10 dB.
- Watermarking: AudioSeal detection on marked speech, after MP3 V2 and Opus
  export (``render_export``), and after the effects chain; and on unmarked
  speech. Exit: at least 0.95 marked, at most 0.05 unmarked.

    python scripts/check_audio_tools.py --voice SPEECH.wav [--seconds 30]
"""
import argparse
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from app.platform.voice.effects import master_take  # noqa: E402
from app.platform.voice.export import render_export  # noqa: E402
from services.audio import audio_server as audio  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--voice", type=Path, required=True)
parser.add_argument("--seconds", type=float, default=30.0)
args = parser.parse_args()
RATE = 44_100


def si_sdr(estimate: np.ndarray, reference: np.ndarray) -> float:
    length = min(len(estimate), len(reference))
    estimate, reference = estimate[:length] - estimate[:length].mean(), reference[:length] - reference[:length].mean()
    target = (estimate @ reference) / (reference @ reference + 1e-12) * reference
    noise = estimate - target
    return 10 * np.log10((target @ target) / (noise @ noise + 1e-12))


def music_bed(seconds: float, rate: int) -> np.ndarray:
    rng = np.random.default_rng(5)
    time_axis = np.arange(int(seconds * rate)) / rate
    bed = np.zeros_like(time_axis)
    chords = [(220.0, 277.2, 329.6), (196.0, 246.9, 293.7), (174.6, 220.0, 261.6), (196.0, 246.9, 329.6)]
    for index, chord in enumerate(chords * int(seconds // 8 + 1)):
        start, end = index * 2.0, (index + 1) * 2.0
        span = (time_axis >= start) & (time_axis < end)
        for note in chord:
            for harmonic, weight in ((1, 1.0), (2, 0.4), (3, 0.2)):
                bed[span] += weight * np.sin(2 * np.pi * note * harmonic * time_axis[span])
        bed[span] += 0.8 * np.sin(2 * np.pi * chord[0] / 2 * time_axis[span])
    for beat in np.arange(0, seconds, 0.5):
        start = int(beat * rate)
        burst = rng.standard_normal(int(0.08 * rate)) * np.exp(-np.linspace(0, 8, int(0.08 * rate)))
        bed[start:start + len(burst)] += 1.5 * burst[: len(bed) - start]
    return bed / np.max(np.abs(bed))


def wav(samples: np.ndarray, rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.clip(samples, -1, 1), rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


voice, rate = sf.read(str(args.voice), dtype="float32", always_2d=True)
voice = audio.resample(voice.mean(axis=1), rate, RATE)[: int(args.seconds * RATE)]
voice = 0.5 * voice / np.max(np.abs(voice))
bed = music_bed(len(voice) / RATE, RATE)
bed = bed * np.sqrt(np.mean(voice ** 2) / np.mean(bed ** 2))  # 0 dB speech-to-music
mix = voice + bed
mix = mix / max(1.0, float(np.max(np.abs(mix))) / 0.95)
print(f"mix: {len(voice) / RATE:.1f}s, input SI-SDR {si_sdr(mix, voice):.2f} dB")
for model in ("roformer", "demucs"):
    started = time.perf_counter()
    stems = audio.isolate(wav(mix, RATE), "mix.wav", model)
    estimate, est_rate = sf.read(io.BytesIO(__import__("base64").b64decode(stems["vocals"])), dtype="float32", always_2d=True)
    estimate = audio.resample(estimate.mean(axis=1), est_rate, RATE)
    gain = si_sdr(estimate, voice) - si_sdr(mix, voice)
    print(f"{stems['model']}: vocals SI-SDR {si_sdr(estimate, voice):.2f} dB, gain {gain:.2f} dB "
          f"(exit >= 10) in {time.perf_counter() - started:.1f}s")
    audio.SEPARATORS[model].model = None  # one separator on the GPU at a time

speech = wav(voice[: 20 * RATE], RATE)
marked_payload = audio.watermark(speech, 1234)
marked = __import__("base64").b64decode(marked_payload["audio"])
checks = {"marked": marked, "unmarked": speech}
for fmt in ("mp3", "opus"):
    encoded, _details = render_export(marked, fmt=fmt, sample_rate=48_000 if fmt == "opus" else 44_100, loudness="none")
    decoded, decoded_rate = sf.read(io.BytesIO(encoded), dtype="float32", always_2d=True)
    checks[f"marked -> {fmt.upper()}"] = wav(decoded.mean(axis=1), decoded_rate)
effected, _applied = master_take(marked, ["eq", "deesser", "compressor", "reverb"], volume_db=-3.0)
checks["marked -> effects"] = effected
for name, payload in checks.items():
    result = audio.detect(payload)
    print(f"{name}: probability {result['probability']:.3f}, message {result['message']}")

# Enhancement (no exit number; a smoke check): speech with white noise at 5 dB SNR.
noise = np.random.default_rng(9).standard_normal(len(voice)).astype(np.float32)
noise *= np.sqrt(np.mean(voice ** 2) / np.mean(noise ** 2) / 10 ** (5 / 10))
enhanced_payload = audio.enhance(wav(voice + noise, RATE))
cleaned, cleaned_rate = sf.read(io.BytesIO(__import__("base64").b64decode(enhanced_payload["audio"])), dtype="float32")
clean_16k = audio.resample(voice, RATE, cleaned_rate)
noisy_16k = audio.resample(voice + noise, RATE, cleaned_rate)
print(f"enhance ({enhanced_payload['model']}, {cleaned_rate} Hz): SI-SDR {si_sdr(noisy_16k, clean_16k):.2f} -> "
      f"{si_sdr(cleaned, clean_16k):.2f} dB")
