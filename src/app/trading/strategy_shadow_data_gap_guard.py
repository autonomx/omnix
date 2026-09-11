from __future__ import annotations

"""Fail-closed normalization for expected SHADOW one-minute data gaps.

A missing or non-contiguous research feed is an unavailable observation, not a
strategy exception. This policy keeps the strict contiguous-coverage contract,
but converts expected SHADOW gap/fallback failures into an empty causal prefix
so research monitors wait instead of logging thousands of evaluation errors.
It also fixes the opening-minute boundary: the 09:30 bar cannot be expected
until it is complete at 09:31 ET.
"""

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from . import strategy_evaluability as evaluability
from . import strategy_runtime_reliability_fixes as runtime_fixes

_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_INSTALLED = False
_ORIGINAL_EXPECTED_LATEST_START = None
_ORIGINAL_PROXY_BARS = None


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


def _fail_closed_shadow_bars(
    self,
    instrument_id,
    interval,
    limit=500,
    binding_id=None,
    cancellation=None,
):
    assert _ORIGINAL_PROXY_BARS is not None
    if interval != "1m":
        return _ORIGINAL_PROXY_BARS(
            self,
            instrument_id,
            interval,
            limit,
            binding_id,
            cancellation,
        )
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
        # This proxy is installed only on SHADOW research monitor paths. An
        # unavailable primary+fallback feed must not turn into usable evidence.
        return _empty_response(None)

    bars = list(getattr(response, "bars", ()) or ())
    assessment = evaluability.assess_bar_coverage(
        bars,
        session_date=self._session_date,
        observed_at=self._observed_at,
        provider="shadow_runtime_guard",
    )
    if assessment.ready or "CURRENT_SESSION_NOT_STARTED" in assessment.reason_codes:
        return response

    # Preserve strict evidence semantics. We intentionally do not forward a
    # partial/gappy prefix to a setup evaluator, because doing so could create a
    # false signal. Monitors see an empty prefix and remain in a waiting state.
    return _empty_response(response)


def install_shadow_data_gap_guard() -> None:
    global _INSTALLED, _ORIGINAL_EXPECTED_LATEST_START, _ORIGINAL_PROXY_BARS
    if _INSTALLED:
        return
    _ORIGINAL_EXPECTED_LATEST_START = evaluability._expected_latest_start
    _ORIGINAL_PROXY_BARS = runtime_fixes._CurrentShadowSessionProxy.bars
    evaluability._expected_latest_start = _expected_latest_start_completed_only
    runtime_fixes._CurrentShadowSessionProxy.bars = _fail_closed_shadow_bars
    _INSTALLED = True


__all__ = ["install_shadow_data_gap_guard"]
