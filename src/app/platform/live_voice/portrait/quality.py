"""A call's portrait quality level, stepped by the browser's acks (roadmap Phase 3, "Remote quality", D-6).

``QUALITY_LEVELS`` (``app.conversation.portrait_stream_contract``) run from L0 (512 px, 25 frames a second, JPEG
85, about 8 Mbit/s) to L3 (384 px, 12.5 frames a second, about 1.5 Mbit/s). The service encodes only the call's
level. Starlette cannot report a socket's send backlog, so the gateway works out the frames in flight from what it
relayed and what the browser says it has received. Every ``frame_ack`` (each 250 ms) is a health sample:

- unhealthy when more than ``MAX_IN_FLIGHT`` frames are in flight, any frame came too late to draw, or decoding
  averaged over ``MAX_DECODE_MS``: the level steps down at once (and the healthy run restarts), then waits
  ``SETTLE_SECONDS`` before stepping again, while the frames already sent at the old level drain;
- after ``STEP_UP_SECONDS`` of healthy acks it steps back up, one level at a time.

Loopback clients start at L0, remote ones at L1.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.conversation.portrait_stream_contract import QUALITY_LEVELS

MAX_IN_FLIGHT = 12  # about half a second of frames at 25 a second
MAX_DECODE_MS = 30.0
STEP_UP_SECONDS = 5.0
SETTLE_SECONDS = 1.0
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def starting_level(client_host: str | None) -> int:
    return 0 if (client_host or "") in LOOPBACK_HOSTS else 1


@dataclass
class QualityController:
    level: int
    sent: int = 0
    healthy_since: float | None = None
    stepped_down_at: float | None = None

    @property
    def lowest(self) -> bool:
        return self.level >= len(QUALITY_LEVELS) - 1

    def relayed(self) -> None:
        """One frame went to the browser."""
        self.sent += 1

    def observe(self, now: float, *, received: int, late: int, decode_ms: float) -> int | None:
        """A frame_ack's health; the new level when it changes, else None."""
        in_flight = max(0, self.sent - max(0, received))
        if in_flight > MAX_IN_FLIGHT or late > 0 or decode_ms > MAX_DECODE_MS:
            self.healthy_since = None
            settling = self.stepped_down_at is not None and now - self.stepped_down_at < SETTLE_SECONDS
            if self.lowest or settling:
                return None
            self.level += 1
            self.stepped_down_at = now
            return self.level
        if self.healthy_since is None:
            self.healthy_since = now
            return None
        if self.level > 0 and now - self.healthy_since >= STEP_UP_SECONDS:
            self.level -= 1
            self.healthy_since = now
            return self.level
        return None


__all__ = ["MAX_DECODE_MS", "MAX_IN_FLIGHT", "QualityController", "SETTLE_SECONDS", "STEP_UP_SECONDS", "starting_level"]
