"""Lossless span-to-chapter timeline and one chapter-level loudness pass."""
from __future__ import annotations

import io
import math
import wave
from array import array
from dataclasses import asdict, dataclass
from typing import Sequence

from .hashing import bytes_hash, object_hash


ASSEMBLY_VERSION = "audiobook-assembly-v1"


@dataclass(frozen=True, slots=True)
class PausePolicy:
    same_speaker_ms: int = 250
    speaker_change_ms: int = 500
    paragraph_ms: int = 700


@dataclass(frozen=True, slots=True)
class AudioSpan:
    render_id: str
    render_key: str
    speaker_id: str
    source_text: str
    wav_bytes: bytes


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    render_id: str
    start_seconds: float
    end_seconds: float
    pause_before_seconds: float


@dataclass(frozen=True, slots=True)
class AssembledChapter:
    wav_bytes: bytes
    duration_seconds: float
    sample_rate: int
    timeline: tuple[TimelineEntry, ...]
    assembly_key: str
    measured_rms_dbfs: float
    applied_gain_db: float
    peak_dbfs: float


def _pcm16(wav_bytes: bytes) -> tuple[bytes, int]:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as reader:
            if reader.getnchannels() != 1 or reader.getsampwidth() != 2 or reader.getcomptype() != "NONE":
                raise ValueError("assembly requires mono PCM16 WAV renders")
            frames = reader.readframes(reader.getnframes())
            if not frames:
                raise ValueError("assembly cannot use empty audio")
            return frames, reader.getframerate()
    except (wave.Error, EOFError) as exc:
        raise ValueError("render is not valid WAV audio") from exc


def assemble_chapter(
    spans: Sequence[AudioSpan], *, policy: PausePolicy = PausePolicy(),
    target_rms_dbfs: float = -20.0,
) -> AssembledChapter:
    if not spans:
        raise ValueError("chapter has no rendered audio")
    if not -35 <= target_rms_dbfs <= -10:
        raise ValueError("chapter loudness target is out of range")
    if min(asdict(policy).values()) < 0:
        raise ValueError("pause durations must be non-negative")
    sample_rate: int | None = None
    raw_parts: list[bytes] = []
    timeline: list[TimelineEntry] = []
    speech_squared = 0
    speech_samples = 0
    peak = 0
    total_frames = 0
    previous: AudioSpan | None = None
    for span in spans:
        frames, rate = _pcm16(span.wav_bytes)
        if sample_rate is None:
            sample_rate = rate
        elif rate != sample_rate:
            raise ValueError("chapter renders use different sample rates")
        if rate <= 0:
            raise ValueError("invalid audio sample rate")
        pause_ms = 0
        if previous is not None:
            pause_ms = policy.speaker_change_ms if previous.speaker_id != span.speaker_id else policy.same_speaker_ms
            if previous.source_text.endswith("\n\n") or span.source_text.startswith("\n\n"):
                pause_ms = max(pause_ms, policy.paragraph_ms)
        pause_frames = round(rate * pause_ms / 1000)
        raw_parts.append(b"\x00\x00" * pause_frames)
        total_frames += pause_frames
        start = total_frames / rate
        samples = array("h")
        samples.frombytes(frames)
        speech_squared += sum(sample * sample for sample in samples)
        speech_samples += len(samples)
        peak = max(peak, max(abs(sample) for sample in samples))
        raw_parts.append(frames)
        total_frames += len(samples)
        timeline.append(TimelineEntry(span.render_id, start, total_frames / rate, pause_frames / rate))
        previous = span
    if not speech_samples or speech_squared == 0:
        raise ValueError("chapter speech audio is silent")
    rms = math.sqrt(speech_squared / speech_samples)
    measured_dbfs = 20 * math.log10(rms / 32768)
    requested_gain = 10 ** ((target_rms_dbfs - measured_dbfs) / 20)
    peak_limited_gain = (32768 * 10 ** (-1 / 20)) / peak
    gain = min(requested_gain, peak_limited_gain)
    mastered = array("h")
    for part in raw_parts:
        samples = array("h")
        samples.frombytes(part)
        mastered.extend(max(-32768, min(32767, round(sample * gain))) for sample in samples)
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(mastered.tobytes())
    key = object_hash({
        "version": ASSEMBLY_VERSION,
        "render_keys": [span.render_key for span in spans],
        "audio_checksums": [bytes_hash(span.wav_bytes) for span in spans],
        "pause_policy": asdict(policy), "target_rms_dbfs": target_rms_dbfs,
    })
    return AssembledChapter(
        output.getvalue(), total_frames / sample_rate, sample_rate,
        tuple(timeline), key, measured_dbfs, 20 * math.log10(gain),
        20 * math.log10(min(32767, peak * gain) / 32768),
    )
