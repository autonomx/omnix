"""Exempt helper models for the model services (Voice Studio Phase 1 section 6).

A helper (batch transcription, diarization, vocal separation, enhancement,
watermarking) loads beside the resident models when free VRAM allows, fails
fast with a message naming what to free when it does not, and unloads after a
while without work. It is never swapped: the swap controller only moves TTS
engines.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class HelperUnavailable(RuntimeError):
    """A helper model is missing or does not fit; the message says what to do."""


def free_vram_gb() -> float | None:
    """Free memory on the CUDA device in GB, or None without CUDA."""
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        free, _total = torch.cuda.mem_get_info()
        return free / 1024 ** 3
    except Exception:
        logger.debug("CUDA memory query failed", exc_info=True)
        return None


class HelperModel:
    """A lazily loaded model that unloads itself after a while without work.

    ``load`` builds the model (raising ``HelperUnavailable`` when its weights are
    missing); ``vram_gb`` is checked against free VRAM first, unless the helper
    runs on the CPU (``vram_gb`` 0).
    """

    unavailable: type[HelperUnavailable] = HelperUnavailable

    def __init__(self, label: str, vram_gb: float, load: Callable[[], Any]) -> None:
        self.label = label
        self.vram_gb = vram_gb
        self.load = load
        self.model: Any = None
        self.last_used = 0.0
        self._lock = threading.Lock()

    def get(self) -> Any:
        with self._lock:
            self.last_used = time.monotonic()
            if self.model is not None:
                return self.model
            free = free_vram_gb()
            if self.vram_gb and free is not None and free < self.vram_gb:
                raise self.unavailable(
                    f"{self.label} needs about {self.vram_gb:.1f} GB of VRAM but {free:.1f} GB is free; "
                    "unload the local LLM model or wait for a voice tool to finish")
            self.model = self.load()
            return self.model

    def unload_if_idle(self, idle_seconds: float) -> bool:
        with self._lock:
            if self.model is None or time.monotonic() - self.last_used < idle_seconds:
                return False
            self.model = None
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            logger.debug("CUDA cache release skipped", exc_info=True)
        return True

    @property
    def loaded(self) -> bool:
        return self.model is not None


__all__ = ["HelperModel", "HelperUnavailable", "free_vram_gb"]
