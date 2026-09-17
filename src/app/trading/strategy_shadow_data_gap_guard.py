from __future__ import annotations

"""Shared-recovery boundary for SHADOW market-data consumers.

Recovery belongs to the shared market-data layer, not to an individual strategy
or timeframe.  This guard therefore has two responsibilities only:

* the ordinary ``bars`` surface remains fail-closed for *every* intraday
  interval when an unresolved gap is still inside a session-anchored dependency;
* strategies that intentionally support post-gap restart may opt in through
  ``bars_for_requirement`` with an explicit :class:`StrategyDataRequirement`.

This prevents the market-data guard from guessing that (for example) every 5m
consumer is rolling-safe.  A strategy must prove its own dependency window and
warmup before it can receive a post-gap suffix.  No synthetic OHLCV values are
introduced here.
"""

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from . import strategy_evaluability as evaluability
from . import strategy_runtime_reliability_fixes as runtime_fixes
from .market_data_recovery import (
    StrategyDataRequirement,
    assess_data_requirement,
    latest_clean_bars,
)
from .providers import alpaca_iex
from .providers.errors import ProviderContractError

_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_INSTALLED = False
_ORIGINAL_EXPECTED_LATEST_START = None
_ORIGINAL_PROXY_BARS = None
_ORIGINAL_ALPACA_INDICATOR_BARS = None


def _expected_latest_start_completed_only(observed_at, session_date):
    """Do not require the 09:30 minute before its 09:31 close is knowable."""

    observed_et = observed_at.astimezone(_ET)
    opening = datetime.combine(session_date, _REGULAR_OPEN, tzinfo=_ET)
    if observed_et.date() != session_date or observed_et < opening + timedelta(minutes=1):
        return None
    floor = observed_et.replace(second=0, microsecond=0)
    expected = floor - timedelta(minutes=1)
    close = datetime.combine(session_date, time(16, 0), tzinfo=_ET)
    return min(max(expected, opening), close - timedelta(minutes=1)).astimezone(timezone.utc)


def _empty_response(response):
    if response is None:
        return SimpleNamespace(bars=[], provenance=None)
    return runtime_fixes._copy_response_with_bars(response, [])


def _recovered_response(recovered, *, bars=None):
    selected = list(recovered.bars if bars is None else bars)
    response = recovered.primary_response
    if response is not None:
        return runtime_fixes._copy_response_with_bars(response, selected)
    report = recovered.report
    provenance = SimpleNamespace(
        requested_binding=report.requested_binding,
        resolved_binding=report.resolved_binding,
        fallback_reason=(
            "shared_market_data_recovery"
            if report.recovered_bar_count
            else report.primary_error
        ),
        dataset_fingerprint=report.dataset_fingerprint,
        freshness_mode="fallback" if report.recovered_bar_count else "polled",
        as_of=(selected[-1].end_time if selected else report.as_of),
        received_at=report.as_of,
        cached=False,
        history_complete=not report.unresolved_gaps,
    )
    return SimpleNamespace(bars=selected, provenance=provenance)


def _alpaca_indicator_missing_bars_is_empty(self, *args, **kwargs):
    """Normalize Alpaca's explicit missing-bars payload to an empty series."""

    assert _ORIGINAL_ALPACA_INDICATOR_BARS is not None
    try:
        return _ORIGINAL_ALPACA_INDICATOR_BARS(self, *args, **kwargs)
    except ProviderContractError as exc:
        if str(exc) == "Alpaca IEX historical-bars response has no bars list":
            return []
        raise


def _shared_recovery(
    self,
    instrument_id,
    interval,
    limit,
    binding_id,
    cancellation,
):
    recovery = getattr(self._delegate, "recovered_bars", None)
    if not callable(recovery):
        return None
    try:
        return recovery(
            instrument_id,
            interval,
            limit,
            binding_id,
            session_date=self._session_date,
            as_of=self._observed_at,
            max_primary_attempts=2,
            cancellation=cancellation,
        )
    except Exception:
        return None


def _recovering_shadow_bars_for_requirement(
    self,
    instrument_id,
    interval,
    limit=500,
    binding_id=None,
    cancellation=None,
    *,
    requirement: StrategyDataRequirement,
):
    """Return only bars proven sufficient for one declared strategy dependency.

    Session-anchored requirements remain blocked by any unresolved historical
    gap.  Rolling requirements may receive only the latest contiguous suffix,
    and only after their independent warmup is complete.  Feed-equivalence
    checks (for example partial-market volume) are enforced by the shared
    requirement assessor.
    """

    if requirement.interval != interval:
        raise ValueError("strategy data requirement interval must match requested interval")

    recovered = _shared_recovery(
        self,
        instrument_id,
        interval,
        limit,
        binding_id,
        cancellation,
    )
    if recovered is None:
        # Compatibility path: callers still get the legacy factual response, but
        # never a post-gap relaxation when the shared recovery service is absent.
        try:
            response = _ORIGINAL_PROXY_BARS(
                self,
                instrument_id,
                interval,
                limit,
                binding_id,
                cancellation,
            )
        except Exception:
            return _empty_response(None)
        assessment = assess_data_requirement(
            list(getattr(response, "bars", ()) or ()),
            session_date=self._session_date,
            as_of=self._observed_at,
            requirement=requirement,
        )
        if not assessment.evaluable:
            return _empty_response(response)
        if requirement.continuity == "rolling" and assessment.reset_required:
            suffix = latest_clean_bars(
                list(getattr(response, "bars", ()) or ()),
                session_date=self._session_date,
                interval=interval,
                as_of=self._observed_at,
            )
            return runtime_fixes._copy_response_with_bars(response, suffix)
        return response

    assessment = assess_data_requirement(
        recovered.bars,
        session_date=self._session_date,
        as_of=self._observed_at,
        requirement=requirement,
        recovery_report=recovered.report,
    )
    if not assessment.evaluable:
        return _empty_response(_recovered_response(recovered))

    selected = list(recovered.bars)
    if requirement.continuity == "rolling" and assessment.reset_required:
        selected = latest_clean_bars(
            recovered.bars,
            session_date=self._session_date,
            interval=interval,
            as_of=self._observed_at,
        )
    return _recovered_response(recovered, bars=selected)


def _recovering_shadow_bars(
    self,
    instrument_id,
    interval,
    limit=500,
    binding_id=None,
    cancellation=None,
):
    """Default SHADOW history surface: strict session dependency for all intervals.

    The old implementation treated non-1m intervals as implicitly safe to pass
    through even when they contained gaps.  That was timeframe-based authority.
    The default is now conservative regardless of interval; rolling recovery is
    available only through ``bars_for_requirement`` above.
    """

    # Before the regular session, preserve the legacy current-session behavior;
    # there is no completed regular-session dependency to recover yet.
    if self._observed_at.astimezone(_ET).time() < _REGULAR_OPEN:
        try:
            return _ORIGINAL_PROXY_BARS(
                self,
                instrument_id,
                interval,
                limit,
                binding_id,
                cancellation,
            )
        except Exception:
            return _empty_response(None)

    return _recovering_shadow_bars_for_requirement(
        self,
        instrument_id,
        interval,
        limit,
        binding_id,
        cancellation,
        requirement=StrategyDataRequirement(
            interval=interval,
            continuity="session",
            minimum_clean_bars=1,
            required_fields=("ohlc", "volume"),
            reset_on_gap=False,
            allow_partial_market_price=False,
            allow_partial_market_volume=False,
        ),
    )


def install_shadow_data_gap_guard() -> None:
    global _INSTALLED, _ORIGINAL_EXPECTED_LATEST_START, _ORIGINAL_PROXY_BARS
    global _ORIGINAL_ALPACA_INDICATOR_BARS
    if _INSTALLED:
        return
    _ORIGINAL_EXPECTED_LATEST_START = evaluability._expected_latest_start
    _ORIGINAL_PROXY_BARS = runtime_fixes._CurrentShadowSessionProxy.bars
    _ORIGINAL_ALPACA_INDICATOR_BARS = alpaca_iex.AlpacaIexExecutionProvider.indicator_bars_as_of
    evaluability._expected_latest_start = _expected_latest_start_completed_only
    runtime_fixes._CurrentShadowSessionProxy.bars = _recovering_shadow_bars
    runtime_fixes._CurrentShadowSessionProxy.bars_for_requirement = (
        _recovering_shadow_bars_for_requirement
    )
    alpaca_iex.AlpacaIexExecutionProvider.indicator_bars_as_of = _alpaca_indicator_missing_bars_is_empty
    _INSTALLED = True


__all__ = [
    "_recovering_shadow_bars_for_requirement",
    "install_shadow_data_gap_guard",
]
