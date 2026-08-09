"""Runtime startup policy for low-latency live-call TTS playback."""
from __future__ import annotations

from collections.abc import Iterator
from functools import wraps
from itertools import chain
from typing import Any

from . import tts_live_call_websocket
from .tts_stream_contract import STREAM_INITIAL_FALLBACK_THRESHOLD

# Keep ordinary four-step Qwen phrases on the established 4,800-sample frame.
# The first accepted response phrase now uses a two-step decoder chunk, which
# materializes 3,840 samples. A 4,800-sample websocket frame forces that fast
# path to wait for another decoder chunk before any PCM can be handed off, so
# align only that raw-chunk shape with the browser's 160 ms startup reserve.
TTS_LIVE_CALL_FAST_START_FRAME_SAMPLES = 3_840
TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES = 4_800

# Generated TTS output is not microphone input. The transport-neutral scanner
# intentionally starts at a stricter 1% amplitude threshold, then falls back to
# this quiet-speech threshold after 400 ms. Live-call traces show that Qwen's
# first chunk often already contains quiet speech, but the stricter gate can
# wait for a later decoder chunk. Using the existing fallback threshold
# immediately for this route preserves silence rejection while removing that
# avoidable wait when signal is already present.
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
        chunk_iter = iter(chunks)
        try:
            first_chunk = next(chunk_iter)
        except StopIteration:
            return iter(())

        first_pcm_bytes = first_chunk[0]
        first_chunk_samples = len(first_pcm_bytes) // 2
        requested_block_samples = int(
            kwargs.get("block_samples", TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES)
        )
        if (
            first_chunk_samples == TTS_LIVE_CALL_FAST_START_FRAME_SAMPLES
            and requested_block_samples > TTS_LIVE_CALL_FAST_START_FRAME_SAMPLES
        ):
            kwargs["block_samples"] = TTS_LIVE_CALL_FAST_START_FRAME_SAMPLES

        return original_streamer(
            chain((first_chunk,), chunk_iter),
            *args,
            **kwargs,
        )

    tts_live_call_websocket._stream_pcm16_blocks = live_call_streamer
    setattr(tts_live_call_websocket, _HOOK_SENTINEL, True)


def install_tts_live_call_startup_frame_policy() -> int:
    """Install the live-call frame and audible-onset policy, returning the old frame size."""
    previous = int(tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES)
    tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES = TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES
    _install_live_call_onset_policy()
    return previous
