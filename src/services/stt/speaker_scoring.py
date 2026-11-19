"""How like the caller's voiceprint a live segment sounds, by TitaNet (companion 2.2).

The gateway sends the account's print at the start of a call (``speaker_profile``); the live socket asks this for
each final segment's cosine similarity with it. The model is held loaded for the call (``hold``/``release``), and
segments are scored one at a time on a thread of their own, never on the batch queue. Anything that goes wrong only
means no score: a segment is never lost or held up for one.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import numpy as np

from services.helper_models import HelperModel

logger = logging.getLogger(__name__)


class SpeakerScorer:
    def __init__(self, helper: HelperModel | None = None,
                 embed: Callable[[Any, np.ndarray], np.ndarray] | None = None) -> None:
        if helper is None or embed is None:
            from services.stt import timed_transcription

            helper = helper or timed_transcription.SPEAKERS
            embed = embed or timed_transcription._embedding
        self._helper = helper
        self._embed = embed
        self._lock = threading.Lock()

    def hold(self) -> None:
        """Keep the model loaded until ``release`` (cheap: call it on the event loop, paired with ``release``)."""
        self._helper.hold()

    def release(self) -> None:
        self._helper.release()

    def warm(self) -> bool:
        """Load the model now (blocking); False when it cannot load, so the call scores nothing."""
        try:
            with self._lock:
                self._helper.get()
            return True
        except Exception:  # noqa: BLE001 - no model means no scores, never a failed call
            logger.warning("live speaker scores are off for this call: %s could not load", self._helper.label,
                           exc_info=True)
            return False

    def similarity(self, pcm16: bytes, profile: np.ndarray) -> float | None:
        """Cosine similarity of the segment's voice to ``profile`` (a unit vector); None when there is no answer."""
        try:
            samples = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
            with self._lock:
                vector = np.asarray(self._embed(self._helper.get(), samples), dtype=np.float64).ravel()
            norm = float(np.linalg.norm(vector))
            if norm <= 0 or vector.shape != profile.shape:
                return None
            return round(float((vector / norm) @ profile), 4)
        except Exception:  # noqa: BLE001 - a score is a hint; its absence is today's behaviour
            logger.debug("live speaker score failed", exc_info=True)
            return None


__all__ = ["SpeakerScorer"]
