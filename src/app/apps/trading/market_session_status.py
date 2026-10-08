"""Market session status for an instrument's session calendar (TVP-2.5 chart legend).

The chart legend shows whether a market is open, in pre-market, in post-market or
closed. The U.S. equity rules live in ``us_equity_calendar``; this module maps a
session calendar onto them so the web never re-implements holiday rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from .us_equity_calendar import us_equity_session

MarketSessionStatus = Literal["open", "pre_market", "post_market", "closed", "unknown"]

# Calendars that follow the standard U.S. listed-equity session.
US_EQUITY_CALENDARS = frozenset({"XNYS", "XNAS", "XASE", "ARCX", "BATS", "US_EQUITY"})
ALWAYS_OPEN_CALENDARS = frozenset({"24x7"})

_US_EQUITY_STATUS: dict[str, MarketSessionStatus] = {
    "regular": "open",
    "extended_pre": "pre_market",
    "extended_post": "post_market",
    "closed": "closed",
}


def is_always_open(session_calendar: str, asset_class: str) -> bool:
    """Only crypto trades around the clock; other assets on a 24x7 calendar lack session rules."""
    return session_calendar.strip() in ALWAYS_OPEN_CALENDARS and asset_class == "crypto"


def market_session_status(
    session_calendar: str,
    asset_class: str,
    moment: datetime,
) -> MarketSessionStatus:
    """The session a market is in at an aware moment; ``unknown`` where Omnix has no session rules."""
    if moment.tzinfo is None:
        raise ValueError("market session status needs a timezone-aware moment")
    if is_always_open(session_calendar, asset_class):
        return "open"
    if session_calendar.strip().upper() in US_EQUITY_CALENDARS:
        return _US_EQUITY_STATUS.get(us_equity_session(moment), "unknown")
    return "unknown"
