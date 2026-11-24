"""Whether a rendered take holds its words: TTS engines sometimes render a line as near-silence.

The same measure as the live speech check (``live_voice/speech/phrase_speech_check.py``), calibrated there on real
takes scored by transcription (2026-11-04): 80 ms frames, a frame is voiced at RMS 0.015 or more, and speech is
rarely faster than 29 characters per voiced second, so a take with less voiced time than that lost words. Studio
renders (podcasts, Voice Studio, audiobooks) use it to render a silent take again.
"""
from __future__ import annotations

import io
import wave

FRAME_SECONDS = 0.08
QUIET_RMS = 0.015
FASTEST_VOICED_CHARS_PER_SECOND = 29.0


def voiced_seconds(wav_bytes: bytes) -> float:
    """Seconds of 80 ms frames loud enough to be speech, in a 16-bit PCM WAV (channels averaged)."""
    import numpy as np

    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
        frames = source.readframes(source.getnframes())
    if width != 2 or not rate:
        return 0.0
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples[: samples.size - samples.size % channels].reshape(-1, channels).mean(axis=1)
    frame = max(1, int(rate * FRAME_SECONDS))
    count = samples.size // frame
    if not count:
        return 0.0
    levels = np.sqrt((samples[: count * frame].reshape(count, frame) ** 2).mean(axis=1))
    return float((levels >= QUIET_RMS).sum()) * frame / rate


def lacks_speech(wav_bytes: bytes, text: str, *, speed: float = 1.0) -> bool:
    """True when the take has too little voiced time for its text; a faster speed setting shortens what is needed."""
    chars = len(" ".join(text.split()))
    if not chars:
        return False
    try:
        voiced = voiced_seconds(wav_bytes)
    except (wave.Error, EOFError, ValueError):
        return False  # not a WAV we can read: the render's own checks decide
    return voiced < chars / FASTEST_VOICED_CHARS_PER_SECOND / max(speed, 0.25)
