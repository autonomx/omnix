from __future__ import annotations

"""Shared-recovery boundary for SHADOW market-data consumers.

The original guard normalized incomplete one-minute history to an empty tape.
That fail-closed behavior is retained for consumers that have not declared a
rolling dependency, but recovery is now attempted through the shared market-data
service first and works for every requested intraday interval.

Coarser strategy evaluators receive factual partial tapes after recovery so they
can apply their own explicit dependency contract (for example, a rolling 50-bar
warmup after an old gap). No synthetic OHLCV values are introduced here.
"""

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from . import strategy_evaluability as evaluability
from . import strategy_runtime_reliability_fixes as runtime_fixes
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


def _recovered_response(recovered):
    response = recovered.primary_response
    if response is not None:
        return runtime_fixes._copy_response_with_bars(response, list(recovered.bars))
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
        as_of=(recovered.bars[-1].end_time if recovered.bars else report.as_of),
        received_at=report.as_of,
        cached=False,
        history_complete=not report.unresolved_gaps,
    )
    return SimpleNamespace(bars=list(recovered.bars), provenance=provenance)


def _alpaca_indicator_missing_bars_is_empty(self, *args, **kwargs):
    """Normalize Alpaca's explicit missing-bars payload to an empty series."""

    assert _ORIGINAL_ALPACA_INDICATOR_BARS is not None
    try:
        return _ORIGINAL_ALPACA_INDICATOR_BARS(self, *args, **kwargs)
    except ProviderContractError as exc:
        if str(exc) == "Alpaca IEX historical-bars response has no bars list":
            return []
        raise


def _recovering_shadow_bars(
    self,
    instrument_id,
    interval,
    limit=500,
    binding_id=None,
    cancellation=None,
):
    assert _ORIGINAL_PROXY_BARS is not None

    recovery = getattr(self._delegate, "recovered_bars", None)
    if callable(recovery):
        try:
            recovered = recovery(
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
            recovered = None
        if recovered is not None:
            response = _recovered_response(recovered)
            if interval != "1m":
                # Coarser evaluators own their dependency semantics. Returning the
                # factual partial tape lets a rolling evaluator reset/warm after an
                # old gap while a session-anchored evaluator can still reject it.
                return response

            bars = list(recovered.bars)
            assessment = evaluability.assess_bar_coverage(
                bars,
                session_date=self._session_date,
                observed_at=self._observed_at,
                provider="shared_market_data_recovery",
                fallback_provider=recovered.report.fallback_provider,
            )
            if assessment.ready or "CURRENT_SESSION_NOT_STARTED" in assessment.reason_codes:
                return response
            # One-minute consumers without an explicit rolling contract keep the
            # legacy fail-closed safety boundary.
            return _empty_response(response)

    # Compatibility path for test doubles / alternate services that do not yet
    # expose the shared recovery API.
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

    if interval != "1m":
        return response
    bars = list(getattr(response, "bars", ()) or ())
    assessment = evaluability.assess_bar_coverage(
        bars,
        session_date=self._session_date,
        observed_at=self._observed_at,
        provider="shadow_runtime_guard",
    )
    if assessment.ready or "CURRENT_SESSION_NOT_STARTED" in assessment.reason_codes:
        return response
    return _empty_response(response)


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
    alpaca_iex.AlpacaIexExecutionProvider.indicator_bars_as_of = _alpaca_indicator_missing_bars_is_empty
    _INSTALLED = True


__all__ = ["install_shadow_data_gap_guard"]
