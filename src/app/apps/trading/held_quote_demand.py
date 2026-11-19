"""Stocks the research arms hold or have an order on: their live quote lines come first.

A held position or a pending order fills only from a quote that arrives after the decision. When a stock had no live
line, nothing arrived: exits waited for many minutes and a reduce never filled (TTEC, 2026-11-10). The AI monitors
and the Stoch arm (while armed or holding) name these stocks on every pass; the IBKR monitor admits them before any other demand. A name lapses after a while
unless a monitor names it again, so a closed position frees its line. Research only: nothing here places an order.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from threading import Lock

HOLD_FOR = timedelta(minutes=15)


class HeldQuoteDemand:
    def __init__(self, *, hold_for: timedelta = HOLD_FOR) -> None:
        self.hold_for = hold_for
        self._until: dict[str, datetime] = {}
        self._lock = Lock()

    def hold(self, instrument_ids: Iterable[str], *, now: datetime) -> None:
        until = now.astimezone(timezone.utc) + self.hold_for
        with self._lock:
            for instrument_id in instrument_ids:
                self._until[str(instrument_id)] = until

    def current(self, *, now: datetime) -> set[str]:
        moment = now.astimezone(timezone.utc)
        with self._lock:
            for instrument_id in [key for key, until in self._until.items() if until <= moment]:
                del self._until[instrument_id]
            return set(self._until)


_DEFAULT = HeldQuoteDemand()


def default_held_quote_demand() -> HeldQuoteDemand:
    return _DEFAULT


__all__ = ["HOLD_FOR", "HeldQuoteDemand", "default_held_quote_demand"]
