"""Trend continuation T1: the TREND-1 rule as a deterministic SHADOW policy.

The rule PREREG_TREND1 tested (research cache, 2026-10-20; it failed that holdout
and PREREG_TREND2's conditioned variants failed theirs; it runs here only to
collect forward evidence, such as real spreads):

- 5m bars are built from the finalized regular-session 1m bars in buckets from
  09:30; a bucket without trades is absent, so trade-free minutes never block
  evaluation.
- A stock qualifies at a completed 5m bar when its close is >= +10% over the
  prior close and its regular-session dollar volume (1m close x volume) is
  >= $1M.
- Signal on a completed 5m bar ending 10:00-15:00 ET: qualified, close above
  session VWAP (typical price) and above the session open, EMA9 > EMA20 of 5m
  closes, and a new high of the session.
- Entry at the open of the next 5m bar (starting by 15:00); exit at the next
  5m open after the first 5m close below VWAP, else at the 15:55 force-flat.
  One trade per stock per session.

Evaluation is causal on whatever prefix of the session it is given. Research
evidence only: no orders, no execution authority.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .models import MarketBar
from .us_equity_calendar import EASTERN as _ET
from .us_equity_calendar import regular_close_time

TREND_T1_VERSION = "trend-continuation-t1-v1"
MIN_GAIN = Decimal("0.10")
MIN_DOLLARS = Decimal("1000000")
SIGNAL_START_ET = time(10, 0)
LAST_ENTRY_ET = time(15, 0)
FORCE_FLAT_ET = time(15, 55)

TrendT1State = Literal["waiting_session", "waiting_signal", "long_active", "exited", "force_flat"]


class TrendT1Signal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_time: datetime
    gain_pct: Decimal
    close: Decimal
    vwap: Decimal
    vwap_extension_pct: Decimal
    bar_range_pct: Decimal
    dollar_volume: Decimal
    open_gap_pct: Decimal


class TrendT1Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["trend-continuation-t1-v1"] = TREND_T1_VERSION
    state: TrendT1State
    reason_code: str
    session_date: str | None = None
    as_of: datetime | None = None
    five_minute_bar_count: int = 0
    signal: TrendT1Signal | None = None
    entry_time: datetime | None = None
    entry_price: Decimal | None = None
    exit_time: datetime | None = None
    exit_price: Decimal | None = None
    exit_reason_code: str | None = None
    return_pct: Decimal | None = None
    execution_authority: Literal[False] = False


class _Bucket:
    __slots__ = ("start", "end", "open", "high", "low", "close", "vwap", "dollars", "ema9", "ema20", "new_high")

    def __init__(self, start: datetime, bars: list[MarketBar], vwap: Decimal, dollars: Decimal) -> None:
        self.start = start
        self.end = start + timedelta(minutes=5)
        self.open = bars[0].open
        self.high = max(bar.high for bar in bars)
        self.low = min(bar.low for bar in bars)
        self.close = bars[-1].close
        self.vwap = vwap
        self.dollars = dollars
        self.ema9 = self.ema20 = self.close
        self.new_high = False


def _buckets(regular: list[MarketBar]) -> list[_Bucket]:
    grouped: dict[datetime, list[MarketBar]] = {}
    for bar in regular:
        local = bar.start_time.astimezone(_ET)
        key = local.replace(minute=local.minute - local.minute % 5, second=0, microsecond=0)
        grouped.setdefault(key, []).append(bar)
    out: list[_Bucket] = []
    cum_pv = cum_v = cum_dollars = Decimal("0")
    for key in sorted(grouped):
        bars = grouped[key]
        for bar in bars:
            cum_pv += (bar.high + bar.low + bar.close) / 3 * bar.volume
            cum_v += bar.volume
            cum_dollars += bar.close * bar.volume
        out.append(_Bucket(key, bars, cum_pv / cum_v if cum_v else bars[-1].close, cum_dollars))
    alpha9, alpha20 = Decimal(2) / 10, Decimal(2) / 21
    running_high = Decimal("0")
    for index, bucket in enumerate(out):
        if index:
            previous = out[index - 1]
            bucket.ema9 = alpha9 * bucket.close + (1 - alpha9) * previous.ema9
            bucket.ema20 = alpha20 * bucket.close + (1 - alpha20) * previous.ema20
        bucket.new_high = bucket.high > running_high
        running_high = max(running_high, bucket.high)
    return out


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator / denominator - 1) * 100 if denominator else Decimal("0")


def evaluate_trend_t1(
    bars: list[MarketBar] | tuple[MarketBar, ...],
    *,
    prior_close: Decimal,
    last_entry_et: time = LAST_ENTRY_ET,
    force_flat_et: time = FORCE_FLAT_ET,
) -> TrendT1Snapshot:
    """Replay T1 over the finalized regular-session 1m bars available so far."""

    regular = sorted(
        (bar for bar in bars if bar.is_final and bar.session == "regular"),
        key=lambda bar: bar.start_time,
    )
    if not regular or prior_close <= 0:
        return TrendT1Snapshot(state="waiting_session", reason_code="TREND_T1_WAITING_SESSION")
    session: date = regular[-1].start_time.astimezone(_ET).date()
    regular = [bar for bar in regular if bar.start_time.astimezone(_ET).date() == session]
    close_at = regular_close_time(session)
    flat_at = min(force_flat_et, (datetime.combine(session, close_at) - timedelta(minutes=5)).time())
    entry_end = min(last_entry_et, (datetime.combine(session, close_at) - timedelta(minutes=60)).time())
    regular = [bar for bar in regular if bar.start_time.astimezone(_ET).time() < close_at]
    buckets = _buckets(regular)
    session_open = regular[0].open
    base = {
        "session_date": session.isoformat(),
        "as_of": regular[-1].end_time,
        "five_minute_bar_count": len(buckets),
    }

    def flat_fill() -> tuple[datetime, Decimal] | None:
        for bar in regular:
            if bar.start_time.astimezone(_ET).time() >= flat_at:
                return bar.start_time, bar.open
        return None

    for index, bucket in enumerate(buckets[:-1]):
        end_et = bucket.end.time()
        if end_et < SIGNAL_START_ET or end_et > entry_end:
            continue
        if bucket.end > regular[-1].end_time:
            break
        qualified = bucket.close >= prior_close * (1 + MIN_GAIN) and bucket.dollars >= MIN_DOLLARS
        if not (qualified and bucket.close > bucket.vwap and bucket.close > session_open
                and bucket.ema9 > bucket.ema20 and bucket.new_high):
            continue
        entry_bucket = buckets[index + 1]
        if entry_bucket.start.time() > entry_end or entry_bucket.start.time() >= flat_at:
            break
        signal = TrendT1Signal(
            signal_time=bucket.end,
            gain_pct=_pct(bucket.close, prior_close),
            close=bucket.close,
            vwap=bucket.vwap,
            vwap_extension_pct=_pct(bucket.close, bucket.vwap),
            bar_range_pct=_pct(bucket.high, bucket.low),
            dollar_volume=bucket.dollars,
            open_gap_pct=_pct(session_open, prior_close),
        )
        entry = {"signal": signal, "entry_time": entry_bucket.start, "entry_price": entry_bucket.open}
        for later in range(index + 1, len(buckets)):
            current = buckets[later]
            if current.start.time() >= flat_at or current.end > regular[-1].end_time:
                break
            if current.close < current.vwap:
                if later + 1 < len(buckets) and buckets[later + 1].start.time() < flat_at:
                    exit_bucket = buckets[later + 1]
                    return TrendT1Snapshot(
                        state="exited", reason_code="TREND_T1_CLOSE_BELOW_VWAP", **base, **entry,
                        exit_time=exit_bucket.start, exit_price=exit_bucket.open,
                        exit_reason_code="TREND_T1_CLOSE_BELOW_VWAP",
                        return_pct=_pct(exit_bucket.open, entry_bucket.open),
                    )
                break
        filled = flat_fill()
        if filled is not None:
            return TrendT1Snapshot(
                state="force_flat", reason_code="TREND_T1_FORCE_FLAT", **base, **entry,
                exit_time=filled[0], exit_price=filled[1], exit_reason_code="TREND_T1_FORCE_FLAT",
                return_pct=_pct(filled[1], entry_bucket.open),
            )
        return TrendT1Snapshot(state="long_active", reason_code="TREND_T1_LONG_ACTIVE", **base, **entry)
    return TrendT1Snapshot(state="waiting_signal", reason_code="TREND_T1_WAITING_SIGNAL", **base)


__all__ = [
    "TREND_T1_VERSION",
    "TrendT1Signal",
    "TrendT1Snapshot",
    "evaluate_trend_t1",
]
