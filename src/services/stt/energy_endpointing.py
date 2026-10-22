"""End-of-utterance detection from audio energy, for STT models that do not report it (desktop roadmap §4.7, DT-8.2).

On Windows, live voice gets the end of an utterance from the Parakeet realtime EOU model. Parakeet-MLX on a Mac only
transcribes, so its service detects the end of an utterance here instead: once the speaker has spoken for a while,
a long enough silence after the speech is the end. The noise floor adapts to the room, so a fan or a quiet hiss does
not count as speech, and a pause shorter than ``silence_ms`` (a breath, a comma) does not end the turn. After an
endpoint, new speech re-arms it, as the EOU model re-arms after every token.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SAMPLE_RATE = 16_000
FRAME_MS = 20


@dataclass
class EnergyEndpointer:
    """Feed PCM16 mono 16 kHz audio in any chunk size; ``feed`` says when an utterance has ended."""

    silence_ms: int = 700
    min_speech_ms: int = 250
    # Speech is at least this far above the noise floor (as a ratio of RMS), and never below ``min_rms``.
    speech_ratio: float = 3.0
    min_rms: float = 0.008
    noise_floor: float = 0.002
    speech_ms: int = 0
    silence_run_ms: int = 0
    armed: bool = True
    _pending: bytes = field(default=b"", repr=False)

    @property
    def threshold(self) -> float:
        return max(self.min_rms, self.noise_floor * self.speech_ratio)

    def _frame(self, frame: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(np.square(frame)))) if frame.size else 0.0
        voiced = rms >= self.threshold
        if voiced:
            self.speech_ms += FRAME_MS
            self.silence_run_ms = 0
            if self.speech_ms >= self.min_speech_ms:
                self.armed = True
            return False
        # Silence: the floor follows the quiet parts of the room, slowly.
        self.noise_floor = 0.95 * self.noise_floor + 0.05 * rms
        self.silence_run_ms += FRAME_MS
        if self.armed and self.speech_ms >= self.min_speech_ms and self.silence_run_ms >= self.silence_ms:
            # An endpoint: wait for new speech before the next one.
            self.armed = False
            self.speech_ms = 0
            return True
        return False

    def feed(self, pcm16: bytes) -> bool:
        """True when this audio completes an utterance (speech, then ``silence_ms`` of quiet)."""
        data = self._pending + pcm16
        frame_bytes = SAMPLE_RATE * FRAME_MS // 1000 * 2
        usable = len(data) - len(data) % frame_bytes
        self._pending = data[usable:]
        ended = False
        samples = np.frombuffer(data[:usable], dtype="<i2").astype(np.float32) / 32768.0
        for start in range(0, samples.size, frame_bytes // 2):
            ended = self._frame(samples[start:start + frame_bytes // 2]) or ended
        return ended


__all__ = ["EnergyEndpointer", "SAMPLE_RATE"]
