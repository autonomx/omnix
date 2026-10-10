"""What an indicator needs besides its own bars, for alerts and the screener (TVP-1.3): the market's session hours and a
compare symbol's bars.

The chart gives each indicator its instrument's session calendar (``sessionForInstrument``) and loads a compare
symbol's bars on the chart's interval. The server does the same: the session comes from the catalog instrument, never
from the request, and compare bars come through the caller's own bar fetch.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from .catalog import instrument_by_id
from .indicators.registry import BarSeries, TradingSession, load_compare_bars, session_for_instrument

logger = logging.getLogger(__name__)

# A compare symbol's bars covering ``bars``: (symbol, bars) -> BarSeries, or None without data.
CompareBars = Callable[[str, BarSeries], "BarSeries | None"]
# The caller's bar fetch: (instrument id, limit) -> bars on the evaluation's interval.
FetchBars = Callable[[str, int], Sequence[Any]]


def instrument_session(instrument_id: str) -> TradingSession | None:
    """The instrument's session calendar, as the chart sets it; None (UTC days) for an instrument the catalog lacks."""
    instrument = instrument_by_id(instrument_id)
    if instrument is None:
        return None
    return session_for_instrument(
        instrument.asset_class.value, instrument.session_calendar, instrument.exchange_timezone, instrument.instrument_type.value
    )


def compare_bars_loader(fetch: FetchBars, *, max_bars: int = 1_000) -> CompareBars:
    """Loads a compare symbol's bars once per symbol and bar list; a failing fetch gives None (no value)."""
    cache: dict[tuple[str, int, Any], BarSeries | None] = {}

    def load(symbol: str, bars: BarSeries) -> BarSeries | None:
        key = (symbol, len(bars), bars.start_times[-1] if len(bars) else None)
        if key not in cache:
            try:
                cache[key] = load_compare_bars(fetch, symbol, bars, max_bars)
            except Exception:  # no data for this pass: the indicator has no value, as while warming up
                logger.warning("indicator_compare_bars_failed", exc_info=True)
                cache[key] = None
        return cache[key]

    return load


__all__ = ["CompareBars", "FetchBars", "compare_bars_loader", "instrument_session"]
