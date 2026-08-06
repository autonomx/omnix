"""Runtime startup policy for low-latency live-call TTS playback."""
from __future__ import annotations

from collections.abc import Iterator
from functools import wraps
from typing import Any

from . import tts_live_call_websocket
from .tts_stream_contract import STREAM_INITIAL_FALLBACK_THRESHOLD

# The adaptive browser policy starts normal playback after 3,840 samples
# (160 ms at 24 kHz). A 2,400-sample websocket frame therefore always needs a
# second event-loop handoff before speech can start. Qwen's current first raw
# block contains 7,680 samples, so handing off 4,800 samples at once crosses the
# browser threshold without waiting for another provider decode iteration.
TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES = 4_800

# Generated TTS output is not microphone input. The transport-neutral scanner
# intentionally starts at a stricter 1% amplitude threshold, then falls back to
# this quiet-speech threshold after 400 ms. Live-call traces show that Qwen's
# first 320 ms chunk often already contains quiet speech, but the stricter gate
# waits for a second or third decoder chunk. Using the existing fallback
# threshold immediately for this route preserves silence rejection while
# removing that avoidable 90-290 ms wait.
TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD = STREAM_INITIAL_FALLBACK_THRESHOLD

_HOOK_SENTINEL = "_omnix_tts_live_call_startup_policy_installed"


def _install_live_call_onset_policy() -> None:
    if getattr(tts_live_call_websocket, _HOOK_SENTINEL, False):
        return
    original_streamer = tts_live_call_websocket._stream_pcm16_blocks

    @wraps(original_streamer)
    def live_call_streamer(
        chunks: Iterator[tuple[bytes, int, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Iterator[tuple[bytes, int, Any]]:
        kwargs.setdefault(
            "silence_threshold",
            TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD,
        )
        return original_streamer(chunks, *args, **kwargs)

    tts_live_call_websocket._stream_pcm16_blocks = live_call_streamer
    setattr(tts_live_call_websocket, _HOOK_SENTINEL, True)


def install_tts_live_call_startup_frame_policy() -> int:
    """Install the live-call frame and audible-onset policy, returning the old frame size."""
    previous = int(tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES)
    tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES = TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES
    _install_live_call_onset_policy()
    return previous
