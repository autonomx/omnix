"""Phase 12.10 — Background worker runner for visual processing."""
from __future__ import annotations

import threading
import time
from typing import Callable


class VisualWorkerRunner:
    """Background worker that periodically processes visual requests."""

    def __init__(self, tick_fn: Callable[[], None], interval_sec: float = 5.0):
        self._tick_fn = tick_fn
        self._interval_sec = max(1.0, float(interval_sec))
        self._thread = None
        self._stop = False

    def start(self) -> None:
        """Start the background worker thread."""
        if self._thread and self._thread.is_alive():
            return

        self._stop = False

        def _run():
            while not self._stop:
                try:
                    self._tick_fn()
                except Exception:
                    pass
                time.sleep(self._interval_sec)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the background worker to stop."""
        self._stop = True