#!/usr/bin/env python3
"""How well the voiceprint tells the owner from the TV and other voices (companion 2.3).

Before "Only respond to me" can be trusted, its threshold has to come from the owner's own recordings, not a guess.
This scores labelled recordings against a print and reports each label's similarity distribution and the highest
threshold that rejects at most 1% of the owner's segments, with how much of every other label that threshold lets in.

    python scripts/voiceprint_threshold_eval.py --enrol DIR --clips DIR [--segment-seconds 2.0] [--output FILE]

``--enrol`` holds two to five read passages (as "Learn my voice" records them), ``--clips`` one folder per label:
``owner`` and ``owner_over_tv`` (any label that starts with ``owner`` is the owner speaking), and ``tv``, ``other``
or any other name for a voice that is not. WAVs of any rate and channel count are mixed to mono and resampled to
16 kHz, then cut into segments as long as a call's short utterances. Embeddings come from the speech service's
``/speaker/embedding`` route, the same TitaNet the live socket scores with, so the speech service must be running.
Nothing is stored and no audio leaves this machine.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import wave
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SAMPLE_RATE = 16_000
# The live socket scores nothing shorter (``MIN_SCORED_SEGMENT_SECONDS``), so neither does this.
MIN_SEGMENT_SECONDS = 0.8
DEFAULT_SEGMENT_SECONDS = 2.0
MAX_FALSE_REJECT = 0.01
# Under this many owner segments, "1% false rejects" is not a measurement.
MIN_OWNER_SEGMENTS = 100
# A segment quieter than this is a pause, not a voice; the call would not have sent it as a final.
MIN_SEGMENT_RMS = 0.004

Embed = Callable[[bytes, str], Sequence[float]]


def is_owner_label(label: str) -> bool:
    return label.lower().startswith("owner")


def read_wav_16k(payload: bytes) -> np.ndarray:
    """A WAV's samples as 16 kHz mono floats in -1..1 (mixed down and linearly resampled when needed)."""
    with wave.open(io.BytesIO(payload), "rb") as source:
        channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
        frames = source.readframes(source.getnframes())
    if width != 2:
        raise ValueError(f"only 16-bit WAV is supported, not {8 * width}-bit")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples[: len(samples) - len(samples) % channels].reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE and len(samples):
        count = max(1, round(len(samples) * SAMPLE_RATE / rate))
        samples = np.interp(np.linspace(0, len(samples) - 1, count), np.arange(len(samples)), samples)
    return samples.astype(np.float32)


def segments(samples: np.ndarray, seconds: float) -> list[np.ndarray]:
    """Consecutive pieces of ``seconds``; a tail of at least ``MIN_SEGMENT_SECONDS`` is kept, silent pieces dropped."""
    size = max(int(MIN_SEGMENT_SECONDS * SAMPLE_RATE), int(seconds * SAMPLE_RATE))
    pieces = []
    for start in range(0, len(samples), size):
        piece = samples[start:start + size]
        if len(piece) < MIN_SEGMENT_SECONDS * SAMPLE_RATE:
            continue
        if float(np.sqrt(np.mean(piece * piece))) < MIN_SEGMENT_RMS:
            continue
        pieces.append(piece)
    return pieces


def wav_bytes(samples: np.ndarray) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm)
    return buffer.getvalue()


def unit(vector: Sequence[float]) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float64).ravel()
    norm = float(np.linalg.norm(array))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("the speaker model returned no embedding")
    return array / norm


def summarise(scores: Sequence[float]) -> dict[str, Any]:
    if not scores:
        return {"count": 0}
    values = np.asarray(scores, dtype=np.float64)
    quantile = lambda q: round(float(np.quantile(values, q)), 4)  # noqa: E731
    return {"count": len(values), "min": round(float(values.min()), 4), "p01": quantile(0.01),
            "p05": quantile(0.05), "median": quantile(0.5), "p95": quantile(0.95), "p99": quantile(0.99),
            "max": round(float(values.max()), 4)}


def choose_threshold(owner_scores: Sequence[float], max_false_reject: float = MAX_FALSE_REJECT) -> float | None:
    """The highest threshold under which at most ``max_false_reject`` of the owner's segments fall."""
    if not owner_scores:
        return None
    ordered = sorted(owner_scores)
    allowed = math.floor(max_false_reject * len(ordered))
    return round(float(ordered[allowed]), 4)


def evaluate(profile: np.ndarray, scores_by_label: Mapping[str, Sequence[float]],
             max_false_reject: float = MAX_FALSE_REJECT) -> dict[str, Any]:
    owner = [score for label, values in scores_by_label.items() if is_owner_label(label) for score in values]
    threshold = choose_threshold(owner, max_false_reject)
    labels: dict[str, Any] = {}
    for label, values in sorted(scores_by_label.items()):
        entry = summarise(values)
        if threshold is not None and values:
            passed = sum(1 for score in values if score >= threshold)
            key = "accepted" if is_owner_label(label) else "false_accept"
            entry[key] = round(passed / len(values), 4)
        labels[label] = entry
    warnings = []
    if not owner:
        warnings.append("no owner segments: record a folder whose name starts with 'owner'")
    elif len(owner) < MIN_OWNER_SEGMENTS:
        warnings.append(f"only {len(owner)} owner segments; {MIN_OWNER_SEGMENTS}+ are needed for a 1% "
                        "false-reject rate to mean anything")
    if not any(not is_owner_label(label) and values for label, values in scores_by_label.items()):
        warnings.append("no other voices: record the TV and another person so false accepts can be measured")
    return {"profile_dimensions": int(profile.shape[0]), "max_false_reject": max_false_reject,
            "threshold": threshold, "owner_segments": len(owner), "labels": labels, "warnings": warnings}


def score_clips(profile: np.ndarray, clips: Path, embed: Embed, segment_seconds: float) -> dict[str, list[float]]:
    scores: dict[str, list[float]] = {}
    for folder in sorted(path for path in clips.iterdir() if path.is_dir()):
        values = scores.setdefault(folder.name, [])
        for path in sorted(folder.glob("*.wav")):
            for index, piece in enumerate(segments(read_wav_16k(path.read_bytes()), segment_seconds)):
                vector = unit(embed(wav_bytes(piece), f"{path.stem}-{index + 1}.wav"))
                if vector.shape != profile.shape:
                    raise ValueError("the clips and the print were embedded by different models")
                values.append(round(float(vector @ profile), 4))
    return scores


def enrol_profile(enrol: Path, embed: Embed) -> np.ndarray:
    from app.platform.voice.voiceprint import build_voiceprint

    passages = [wav_bytes(read_wav_16k(path.read_bytes())) for path in sorted(enrol.glob("*.wav"))]
    return unit(build_voiceprint(passages, embed=embed).embedding)


def main(argv: Sequence[str] | None = None, *, embed: Embed | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--enrol", type=Path, required=True, help="folder of 2-5 read passages (WAV)")
    parser.add_argument("--clips", type=Path, required=True, help="one folder of WAVs per label")
    parser.add_argument("--segment-seconds", type=float, default=DEFAULT_SEGMENT_SECONDS)
    parser.add_argument("--max-false-reject", type=float, default=MAX_FALSE_REJECT)
    parser.add_argument("--output", type=Path, help="also write the report here as JSON")
    args = parser.parse_args(argv)
    if embed is None:
        from app.platform.voice.voiceprint import speaker_embedding

        embed = speaker_embedding
    profile = enrol_profile(args.enrol, embed)
    report = evaluate(profile, score_clips(profile, args.clips, embed, args.segment_seconds), args.max_false_reject)
    report["segment_seconds"] = args.segment_seconds
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["threshold"] is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
