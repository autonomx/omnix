from __future__ import annotations

from datetime import time
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.trading.gapper_dataset import GapperCandidate
from app.trading.models import MarketBar

from .models import (
    GapPullbackConfig,
    GapPullbackFeatures,
    GapPullbackResult,
    GapPullbackState,
    StrategySignal,
)


_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)


def _regular_bars(bars: list[MarketBar] | tuple[MarketBar, ...]) -> list[MarketBar]:
    if not bars:
        return []
    latest_date = bars[-1].start_time.astimezone(_ET).date()
    result: list[MarketBar] = []
    for bar in bars:
        local = bar.start_time.astimezone(_ET)
        if local.date() != latest_date:
            continue
        if _REGULAR_OPEN <= local.time() < _REGULAR_CLOSE:
            result.append(bar)
    return result


def session_vwap(bars: list[MarketBar] | tuple[MarketBar, ...]) -> Decimal | None:
    """Regular-session VWAP reset at 09:30 America/New_York."""
    regular = _regular_bars(bars)
    total_volume = sum((bar.volume for bar in regular), Decimal("0"))
    if total_volume <= 0:
        return None
    numerator = sum(
        (((bar.high + bar.low + bar.close) / Decimal("3")) * bar.volume for bar in regular),
        Decimal("0"),
    )
    return numerator / total_volume


def _confirmed_pivots(
    bars: list[MarketBar],
    *,
    left: int,
    right: int,
    low: bool,
) -> list[int]:
    """Return only pivots knowable from the supplied prefix.

    A candidate at j is not emitted until j + right exists, preventing future-bar
    leakage when the same function is called incrementally.
    """
    output: list[int] = []
    for j in range(left, len(bars) - right):
        value = bars[j].low if low else bars[j].high
        neighborhood = bars[j - left : j + right + 1]
        values = [item.low if low else item.high for item in neighborhood]
        if low and value == min(values):
            output.append(j)
        elif not low and value == max(values):
            output.append(j)
    return output


def _result(
    candidate: GapperCandidate,
    state: GapPullbackState,
    reason: str,
    transitions: list[GapPullbackState],
    features: GapPullbackFeatures,
    bars: list[MarketBar],
    signal: StrategySignal | None = None,
) -> GapPullbackResult:
    return GapPullbackResult(
        instrument_id=candidate.instrument_id,
        state=state,
        reason_code=reason,
        features=features,
        transitions=tuple(transitions),
        signal=signal,
        evaluated_bar_count=len(bars),
    )


def evaluate_gap_pullback(
    candidate: GapperCandidate,
    bars: list[MarketBar] | tuple[MarketBar, ...],
    config: GapPullbackConfig | None = None,
) -> GapPullbackResult:
    """Evaluate the first failed sell-off as a causal state machine."""
    active = config or GapPullbackConfig()
    regular = _regular_bars(bars)
    transitions: list[GapPullbackState] = ["discovered"]
    base_features = GapPullbackFeatures(
        gap_pct=candidate.gap_pct,
        spread_bps=candidate.spread_bps,
        tod_rvol=candidate.tod_rvol,
    )

    rejection: str | None = None
    if candidate.gap_pct < active.minimum_gap_pct:
        rejection = "GAP_BELOW_MINIMUM"
    elif not active.minimum_price <= candidate.premarket_price <= active.maximum_price:
        rejection = "PRICE_OUT_OF_RANGE"
    elif candidate.premarket_dollar_volume < active.minimum_premarket_dollar_volume:
        rejection = "PREMARKET_DOLLAR_VOLUME_LOW"
    elif candidate.tod_rvol is None:
        rejection = "TOD_RVOL_MISSING"
    elif candidate.tod_rvol < active.minimum_tod_rvol:
        rejection = "TOD_RVOL_LOW"
    elif candidate.spread_bps is None:
        rejection = "SPREAD_MISSING"
    elif candidate.spread_bps > active.maximum_spread_bps:
        rejection = "SPREAD_TOO_WIDE"
    if rejection:
        transitions.append("rejected")
        return _result(candidate, "rejected", rejection, transitions, base_features, regular)

    transitions.append("qualified_gap")
    if not regular:
        return _result(candidate, "qualified_gap", "WAITING_FOR_REGULAR_SESSION", transitions, base_features, regular)

    current_et = regular[-1].end_time.astimezone(_ET)
    minutes_since_open = max(0, current_et.hour * 60 + current_et.minute - (9 * 60 + 30))
    if current_et.time() < active.entry_start_et:
        return _result(
            candidate,
            "qualified_gap",
            "ENTRY_WINDOW_NOT_OPEN",
            transitions,
            base_features.model_copy(update={"minutes_since_open": minutes_since_open}),
            regular,
        )

    opening_price = regular[0].open
    required_high = opening_price * (Decimal("1") + active.opening_impulse_min_pct / Decimal("100"))
    impulse_idx: int | None = None
    for index, bar in enumerate(regular):
        if bar.high >= required_high:
            impulse_idx = index
            break
    if impulse_idx is None:
        if current_et.time() > active.last_entry_et:
            transitions.append("expired")
            return _result(candidate, "expired", "NO_OPENING_IMPULSE", transitions, base_features, regular)
        return _result(candidate, "qualified_gap", "WAITING_FOR_OPENING_IMPULSE", transitions, base_features, regular)

    transitions.append("opening_impulse")
    impulse_high = max(bar.high for bar in regular[: impulse_idx + 1])
    impulse_pct = (impulse_high / opening_price - Decimal("1")) * Decimal("100")
    features = base_features.model_copy(
        update={"opening_impulse_pct": impulse_pct, "minutes_since_open": minutes_since_open}
    )

    lows = _confirmed_pivots(
        regular,
        left=active.pivot_left_bars,
        right=active.pivot_right_bars,
        low=True,
    )
    l1_idx = next((idx for idx in lows if idx > impulse_idx), None)
    if l1_idx is None:
        transitions.append("first_pullback")
        state: GapPullbackState = "first_pullback"
        if current_et.time() > active.last_entry_et:
            transitions.append("expired")
            state = "expired"
        return _result(candidate, state, "WAITING_FOR_FIRST_LOW_CONFIRMATION", transitions, features, regular)

    l1 = regular[l1_idx].low
    pre_l1_high = max(bar.high for bar in regular[: l1_idx + 1])
    pullback_depth = (pre_l1_high - l1) / pre_l1_high * Decimal("100")
    features = features.model_copy(update={"l1": l1, "pullback_depth_pct": pullback_depth})
    if not active.pullback_min_pct <= pullback_depth <= active.pullback_max_pct:
        transitions.append("rejected")
        return _result(candidate, "rejected", "PULLBACK_DEPTH_OUT_OF_RANGE", transitions, features, regular)
    transitions.extend(["first_pullback", "first_low_confirmed"])

    highs = _confirmed_pivots(
        regular,
        left=active.pivot_left_bars,
        right=active.pivot_right_bars,
        low=False,
    )
    b1_idx = next((idx for idx in highs if idx > l1_idx), None)
    if b1_idx is None:
        return _result(candidate, "first_low_confirmed", "WAITING_FOR_BOUNCE_HIGH", transitions, features, regular)
    b1 = regular[b1_idx].high
    features = features.model_copy(update={"b1": b1})
    transitions.append("bounce_high_confirmed")

    l2_idx = next((idx for idx in lows if idx > b1_idx), None)
    if l2_idx is None:
        transitions.append("second_pullback")
        state = "second_pullback"
        if current_et.time() > active.last_entry_et:
            transitions.append("expired")
            state = "expired"
        return _result(candidate, state, "WAITING_FOR_SECOND_LOW_CONFIRMATION", transitions, features, regular)

    l2 = regular[l2_idx].low
    features = features.model_copy(update={"l2": l2})
    transitions.append("second_pullback")
    minimum_higher_low = l1 * (Decimal("1") + active.higher_low_buffer_bps / Decimal("10000"))
    if l2 <= minimum_higher_low:
        transitions.append("rejected")
        return _result(candidate, "rejected", "SECOND_LOW_NOT_HIGHER", transitions, features, regular)
    transitions.append("higher_low_confirmed")

    vwap = session_vwap(regular)
    if vwap is None:
        return _result(candidate, "higher_low_confirmed", "VWAP_UNAVAILABLE", transitions, features, regular)
    current = regular[-1]
    vwap_distance = (current.close / vwap - Decimal("1")) * Decimal("100")
    lookback = regular[max(0, len(regular) - active.volume_lookback_bars - 1) : -1]
    average_volume = (
        sum((bar.volume for bar in lookback), Decimal("0")) / Decimal(len(lookback))
        if lookback
        else Decimal("0")
    )
    volume_ratio = current.volume / average_volume if average_volume > 0 else Decimal("0")
    features = features.model_copy(
        update={
            "session_vwap": vwap,
            "vwap_distance_pct": vwap_distance,
            "breakout_volume_ratio": volume_ratio,
        }
    )
    if current.close <= vwap:
        return _result(candidate, "higher_low_confirmed", "WAITING_FOR_VWAP_RECLAIM", transitions, features, regular)
    transitions.append("vwap_reclaim")
    if current.close <= b1:
        return _result(candidate, "vwap_reclaim", "WAITING_FOR_B1_BREAK", transitions, features, regular)
    transitions.append("lower_high_break")
    if volume_ratio < active.breakout_volume_ratio:
        return _result(candidate, "lower_high_break", "BREAKOUT_VOLUME_TOO_LOW", transitions, features, regular)
    if current_et.time() > active.last_entry_et:
        transitions.append("expired")
        return _result(candidate, "expired", "ENTRY_WINDOW_CLOSED", transitions, features, regular)

    stop = l2 * (Decimal("1") - active.stop_buffer_bps / Decimal("10000"))
    entry = current.close
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        transitions.append("rejected")
        return _result(candidate, "rejected", "NON_POSITIVE_RISK_DISTANCE", transitions, features, regular)
    target = entry + risk_per_share * active.reward_multiple
    transitions.append("entry_ready")
    signal = StrategySignal(
        instrument_id=candidate.instrument_id,
        state="entry_ready",
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        risk_per_share=risk_per_share,
        reason_code="FAILED_SELL_OFF_CONFIRMED",
    )
    return _result(candidate, "entry_ready", "FAILED_SELL_OFF_CONFIRMED", transitions, features, regular, signal)
