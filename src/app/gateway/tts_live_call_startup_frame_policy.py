"""Runtime startup-frame policy for low-latency live-call TTS playback."""
from __future__ import annotations

from . import tts_live_call_websocket

# The adaptive browser policy starts normal playback after 3,840 samples
# (160 ms at 24 kHz). A 2,400-sample websocket frame therefore always needs a
# second event-loop handoff before speech can start. Qwen's current first raw
# block contains 7,680 samples, so handing off 4,800 samples at once crosses the
# browser threshold without waiting for another provider decode iteration.
TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES = 4_800


def install_tts_live_call_startup_frame_policy() -> int:
    """Use one 200 ms PCM frame for live-call transport and return the old size."""
    previous = int(tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES)
    tts_live_call_websocket.TTS_PCM_FRAME_SAMPLES = TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES
    return previous
