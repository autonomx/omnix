"""Runtime status helpers for live speech."""
from __future__ import annotations

import os

from .compat import compatibility_payload


def live_speech_enabled() -> bool:
    return os.environ.get("LIVE_SPEECH_REALTIME_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def live_speech_status_payload() -> dict:
    return {
        "ok": True,
        "enabled": live_speech_enabled(),
        "socket_path": "/v1/realtime",
        "contract": compatibility_payload()["contract"],
        "providers": {
            "stt": os.environ.get("LIVE_SPEECH_STT_PROVIDER", "fake"),
            "tts": os.environ.get("LIVE_SPEECH_TTS_PROVIDER", "fake"),
            "llm": os.environ.get("LIVE_SPEECH_LLM_PROVIDER", "fake"),
            "vad": os.environ.get("LIVE_SPEECH_VAD_PROVIDER", "energy"),
        },
        "sample_rates": {
            "input_hz": int(os.environ.get("LIVE_SPEECH_INPUT_SAMPLE_RATE", "16000")),
            "output_hz": int(os.environ.get("LIVE_SPEECH_OUTPUT_SAMPLE_RATE", "24000")),
        },
    }
