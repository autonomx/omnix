"""Production TTS adapter seams for live speech."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import requests

from .tts import AudioDelta, DeterministicSpeechSynthesizer, StreamingSpeechSynthesizer


@dataclass
class QwenServiceSpeechSynthesizer(StreamingSpeechSynthesizer):
    """Adapter for a Qwen-compatible TTS HTTP service.

    The adapter accepts either raw audio responses or JSON payloads containing
    base64 audio fields. It keeps the realtime protocol stable while production
    services evolve behind the same interface.
    """

    base_url: str = "http://127.0.0.1:5101"
    sample_rate: int = 24000
    timeout_seconds: float = 30.0
    _sequence: int = 0

    def synthesize(self, text: str, *, voice: str = "default", generation: int = 0) -> list[AudioDelta]:
        clean = text.strip()
        if not clean:
            return []
        payload = {"text": clean, "voice": voice, "sample_rate": self.sample_rate}
        try:
            response = requests.post(f"{self.base_url.rstrip('/')}/tts", json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            pcm = self._decode_response(response)
        except Exception:
            # Preserve this adapter's monotonic sequence when the service is
            # unavailable; callers use it to order audio across fallback frames.
            fallback = DeterministicSpeechSynthesizer(frame_samples=1200).synthesize(
                clean, voice=voice, generation=generation
            )
            for delta in fallback:
                delta.sequence = self._sequence
            self._sequence += len(fallback)
            return fallback
        if not pcm:
            return []
        delta = AudioDelta(pcm=pcm, sample_rate=self.sample_rate, sequence=self._sequence)
        self._sequence += 1
        return [delta]

    def _decode_response(self, response: requests.Response) -> bytes:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            payload: dict[str, Any] = response.json()
            audio_value = payload.get("audio") or payload.get("audio_b64") or payload.get("pcm") or ""
            if isinstance(audio_value, str):
                return base64.b64decode(audio_value)
            raise ValueError("tts json response did not include base64 audio")
        return response.content


def create_synthesizer_from_env() -> StreamingSpeechSynthesizer:
    provider = os.environ.get("LIVE_SPEECH_TTS_PROVIDER", "fake").strip().lower()
    if provider in {"qwen", "qwen3", "qwen_http", "real"}:
        return QwenServiceSpeechSynthesizer(base_url=os.environ.get("LIVE_SPEECH_TTS_URL", "http://127.0.0.1:5101"))
    return DeterministicSpeechSynthesizer()
