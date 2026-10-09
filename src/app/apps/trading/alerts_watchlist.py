"""Watchlist alerts (TVP-1.7): one alert on every symbol of a watchlist.

A watchlist alert's instrument is ``watchlist:<record id>``; its members are read from the watchlist document at
evaluation time, so adding or removing a symbol takes effect on the next pass. Each pass fetches one history per
member symbol, so the symbols evaluated are capped: by the alert's own limit (default 100), and by what each member's
provider can serve per pass within its request budget (``providers/request_budget.py``), so watchlist alerts never
spend more than half of a provider's budget between passes.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from .alerts import WATCHLIST_SYMBOL_DEFAULT, WATCHLIST_SYMBOL_MAX, TradingAlert, watchlist_symbols
from .providers.request_budget import DEFAULT_LIMITS, upstream_of

# The share of a provider's budget per pass watchlist alerts may spend.
WATCHLIST_BUDGET_SHARE = 0.5
# Request weight of one bars request, where a provider counts weight (Binance klines up to 100 bars weigh 2).
_BARS_REQUEST_WEIGHT = {"binance": 2.0}


def provider_symbol_cap(upstream: str, pass_seconds: float) -> int:
    """How many symbols one pass can fetch from ``upstream`` within its share of the budget; the maximum without one."""
    limit = DEFAULT_LIMITS.get(upstream)
    if limit is None:
        return WATCHLIST_SYMBOL_MAX
    per_pass = limit.weight / limit.per_seconds * max(1.0, pass_seconds) * WATCHLIST_BUDGET_SHARE
    return max(1, min(WATCHLIST_SYMBOL_MAX, math.floor(per_pass / _BARS_REQUEST_WEIGHT.get(upstream, 1.0))))


def watchlist_symbol_cap(symbols: Sequence[str], provider_of: Callable[[str], str | None], pass_seconds: float) -> int:
    """The most symbols of this list a pass evaluates: the strictest of their providers' caps."""
    caps = [WATCHLIST_SYMBOL_MAX]
    for upstream in {upstream_of(provider) for provider in (provider_of(symbol) for symbol in symbols) if provider}:
        caps.append(provider_symbol_cap(upstream, pass_seconds))
    return min(caps)


def watchlist_members(document: dict[str, Any] | None) -> list[str]:
    """The symbols of a watchlist document as the document repository returns it; none for a missing one."""
    if not document or document.get("status", "active") != "active":
        return []
    payload = document.get("payload")
    return watchlist_symbols(payload) if isinstance(payload, dict) else []


def evaluated_symbols(alert: TradingAlert, members: Sequence[str], cap: int) -> list[str]:
    """The members a pass evaluates for this alert, in list order: at most its limit and the providers' cap."""
    limit = alert.evaluation_policy.symbol_limit or WATCHLIST_SYMBOL_DEFAULT
    return list(members[: max(0, min(limit, cap))])
