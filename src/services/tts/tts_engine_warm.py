"""The TTS engine warms itself when the service starts, so nobody's first call pays for it."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from app.persistence.device_permits import device_permit_slot
from app.providers.voice_debug import voice_debug_log

logger = logging.getLogger(__name__)

# It waits its turn for the GPU, behind live speech in the permit queue.
ENGINE_WARM_PERMIT_SECONDS = 30.0


def warm_loaded_engine(provider: Any, *, begin: Callable[[], None], end: Callable[[], None]) -> None:
    """Build what the engine's first generation would otherwise build during someone's first call.

    The service warms itself because it owns the model: the launcher starts the gateway first, so the gateway's own
    warm-up finds no service to ask and gives up. ``begin`` and ``end`` count it as a generation in progress.
    """
    from app.platform.voice.tts_runtime_actions import warmup_speaker
    from app.platform.voice.tts_runtime_state import startup_warmup_enabled

    if not hasattr(provider, "warm_voice") or not startup_warmup_enabled():
        return
    started = time.perf_counter()
    begun = False
    try:
        speaker = warmup_speaker(provider)
        if not speaker:
            voice_debug_log("tts", "tts_engine_warm_skipped", reason="no_voice")
            return
        begin()
        begun = True
        with device_permit_slot("tts", priority="interactive", timeout_seconds=ENGINE_WARM_PERMIT_SECONDS):
            provider.warm_voice(speaker, device_permit_held=True)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
        logger.info("TTS engine warmed in %.1f s", elapsed_ms / 1000.0)
        voice_debug_log("tts", "tts_engine_warmed", speaker=speaker, elapsed_ms=elapsed_ms)
    except Exception as exc:  # noqa: BLE001 - a first call then warms it, as it always could
        logger.warning("The TTS engine could not be warmed at startup", exc_info=True)
        voice_debug_log("tts", "tts_engine_warm_failed", error=type(exc).__name__)
    finally:
        if begun:
            end()
