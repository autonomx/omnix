"""Pure overnight-gap research logic for ``overnight-trading-strategy-shadow``.

Everything here is deterministic and provider-free: candidate features from
regular-session bars that ended by the data cutoff, per-arm selection, outcome
labelling from one-minute bars, and the per-session scorecard. The monitor in
``strategy_overnight_monitor`` fetches data and persists events; this module
never places, sizes or routes an order (SHADOW evidence only).
"""
from __future__ import annotations

import re
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .strategies.models import OvernightArmConfig, OvernightShadowConfig
from app.apps.trading.us_equity_calendar import EASTERN as _ET
from app.apps.trading.us_equity_calendar import regular_close_time

OVERNIGHT_TRADING_STRATEGY_ID = "overnight-trading-strategy-shadow"
OVERNIGHT_POPULATION_MIN_CHANGE = Decimal("0.10")
# Mid-cap research population (PREREG_OVERNIGHT5), recorded beside the small-cap one; no arm reads it.
MID_MIN_PRICE, MID_MAX_PRICE = Decimal("5"), Decimal("50")
MID_MIN_ADV_DOLLARS, MID_MAX_ADV_DOLLARS = Decimal("5000000"), Decimal("50000000")
MID_POPULATION_MIN_CHANGE = Decimal("0.05")
# Broad-market context recorded with each scan and scorecard (research only; no arm reads it).
OVERNIGHT_BENCHMARKS = ("SPY", "QQQ", "IWM", "DIA")
_EXIT_MISSING_RETURN = Decimal("-0.50")
_BIG_GAP = Decimal("0.20")


@dataclass(frozen=True, slots=True)
class OvernightBar:
    """A finalized SIP bar; ``start`` is timezone-aware."""

    start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class OvernightCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    instrument_id: str
    prior_close: Decimal
    price: Decimal
    change: Decimal
    high: Decimal
    low: Decimal
    close_location: Decimal
    volume: Decimal
    adv: Decimal | None
    volume_ratio: Decimal | None
    dollar_volume: Decimal
    # Research context from daily bars before the decision day (no arm reads it). Defaults keep
    # picks recorded before these fields existed valid when they are labelled.
    prior_return_5d: Decimal | None = None
    prior_up_days_5d: int | None = None
    prior_return_20d: Decimal | None = None
    # Prior close vs the highest daily high of the last year (population stocks only).
    off_52w_high: Decimal | None = None
    # 20-session average daily dollar volume (split-invariant), for the mid-cap population.
    adv_dollars: Decimal | None = None


class OvernightSocialMention(BaseModel):
    """Reddit mention counts for one ticker as seen at decision time (rolling 24 hours)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    rank: int
    mentions: int
    upvotes: int
    rank_24h_ago: int | None
    mentions_24h_ago: int | None


# Headline categories, frozen from the research study (research/float_news.py); PREREG_OVERNIGHT4
# refers to them by name, so they must not change without a new pre-registration.
NEWS_CATEGORIES: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.I) for name, pattern in {
        "offering": r"offering|priced|registered direct|private placement|at-the-market|\bATM\b|shelf|warrant (?:inducement|exercise)|securities purchase agreement",
        "reverse_split": r"reverse (?:stock )?split",
        "fda_clinical": r"\bFDA\b|clearance|approv|phase \d|clinical|trial|topline|patients",
        "deal": r"merger|acqui|definitive agreement|letter of intent|\bLOI\b|partnership|collaborat|contract|purchase order|\border\b|award|strategic",
        "earnings": r"earnings|results|revenue|quarter|fiscal|guidance",
        "theme": r"bitcoin|crypto|token|blockchain|\bAI\b|artificial intelligence|treasury|quantum|drone",
    }.items()
}
_NEWS_HEADLINES_KEPT = 5


class OvernightHeadline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    created_at: datetime
    headline: str


class OvernightNewsContext(BaseModel):
    """Headlines tagging one stock inside the news window (all of them counted and categorised)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    articles: int
    categories: list[str]
    headlines: list[OvernightHeadline]


def news_context(symbol: str, headlines: Iterable[OvernightHeadline]) -> OvernightNewsContext:
    """Count and categorise ``headlines`` for ``symbol``; keeps the newest few for later reading."""

    rows = sorted(headlines, key=lambda h: h.created_at)
    return OvernightNewsContext(
        symbol=symbol,
        articles=len(rows),
        categories=[name for name, pattern in NEWS_CATEGORIES.items() if any(pattern.search(h.headline) for h in rows)],
        headlines=rows[-_NEWS_HEADLINES_KEPT:],
    )


class OvernightPick(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arm_id: str
    rank: int
    candidate: OvernightCandidate


class OvernightOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arm_id: str
    symbol: str
    instrument_id: str
    session_date: date
    next_session_date: date
    entry_price: Decimal | None
    exit_open: Decimal | None
    premarket_0800: Decimal | None
    price_0945: Decimal | None
    gross_return: Decimal | None
    net_return: Decimal | None
    gap_return: Decimal | None
    status: Literal["labelled", "no_entry", "no_open"]
    # Next-session prices are as traded; returns multiply them by this factor when a split took
    # effect overnight (a 1-for-10 reverse split: 0.1). None: no split.
    split_factor: Decimal | None = None


class OvernightBenchmark(BaseModel):
    """Broad-market context known at decision time, from the same bars the candidates use."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    prior_close: Decimal
    prior_change: Decimal | None
    price: Decimal
    change: Decimal


class OvernightBenchmarkOutcome(BaseModel):
    """The benchmark over the picks' holding window: ``entry_et`` 1m open to the next 09:30 open."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    entry_price: Decimal | None
    exit_open: Decimal | None
    overnight_return: Decimal | None
    split_factor: Decimal | None = None


def half_spread(price: Decimal) -> Decimal:
    """Per-side cost proxy by price bucket (same model as the research backtests)."""

    if price < 3:
        return Decimal("0.015")
    if price < 10:
        return Decimal("0.01")
    return Decimal("0.005")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def split_factors(
    splits: Iterable[tuple[str, date, Decimal, Decimal]], session_date: date, next_session_date: date,
) -> dict[str, Decimal]:
    """Per symbol, what turns next-session prices into entry-session units.

    ``splits`` are ``(symbol, ex_date, old_rate, new_rate)``; only those taking effect after the
    entry session and by the next session count. Unadjusted bars otherwise show a 1-for-10 reverse
    split as a +900% overnight gap.
    """

    factors: dict[str, Decimal] = {}
    for symbol, ex_date, old_rate, new_rate in splits:
        if session_date < ex_date <= next_session_date and old_rate > 0 and new_rate > 0:
            factors[symbol] = factors.get(symbol, Decimal("1")) * new_rate / old_rate
    return factors


def _known_at_cutoff(
    bars: Sequence[OvernightBar], session_date: date, config: OvernightShadowConfig, bar_minutes: int,
) -> list[OvernightBar]:
    """Regular-session bars of ``session_date`` that ENDED by the data cutoff, oldest first."""

    cutoff = datetime.combine(session_date, config.data_cutoff_et, tzinfo=_ET)
    # A bar that has not ended by the cutoff is not known at decision time.
    return sorted(
        (
            bar for bar in bars
            if bar.start.astimezone(_ET).date() == session_date
            and bar.start.astimezone(_ET).time() >= time(9, 30)
            and bar.start + timedelta(minutes=bar_minutes) <= cutoff
        ),
        key=lambda bar: bar.start,
    )


def build_benchmark(
    *,
    symbol: str,
    daily: Sequence[OvernightBar],
    bars: Sequence[OvernightBar],
    session_date: date,
    config: OvernightShadowConfig,
    bar_minutes: int = 30,
) -> OvernightBenchmark | None:
    """Change to the data cutoff vs the prior close, and the prior session's own change.

    ``daily`` holds daily bars of sessions before ``session_date`` (later ones are ignored).
    """

    prior = sorted((b for b in daily if b.start.astimezone(_ET).date() < session_date), key=lambda b: b.start)
    regular = _known_at_cutoff(bars, session_date, config, bar_minutes)
    if not prior or not regular or prior[-1].close <= 0:
        return None
    prior_close = prior[-1].close
    before = prior[-2].close if len(prior) >= 2 and prior[-2].close > 0 else None
    return OvernightBenchmark(
        symbol=symbol,
        prior_close=prior_close,
        prior_change=_q(prior_close / before - 1) if before else None,
        price=regular[-1].close,
        change=_q(regular[-1].close / prior_close - 1),
    )


def build_candidate(
    *,
    symbol: str,
    instrument_id: str,
    prior_close: Decimal,
    bars: Sequence[OvernightBar],
    adv_volumes: Sequence[Decimal],
    session_date: date,
    config: OvernightShadowConfig,
    bar_minutes: int = 30,
    prior_closes: Sequence[Decimal] = (),
    adv_dollars: Decimal | None = None,
) -> OvernightCandidate | None:
    """Features from regular-session ``bar_minutes`` bars that ENDED by ``config.data_cutoff_et``.

    ``prior_closes`` are daily closes of sessions before ``session_date``, oldest first; the last
    six give the 5-session trend into the decision day, the last 21 the 20-session trend.
    """

    if prior_close <= 0:
        return None

    def closes(count: int) -> list[Decimal]:
        window = list(prior_closes)[-count:]
        return window if len(window) == count and all(close > 0 for close in window) else []

    trend, trend20 = closes(6), closes(21)
    regular = _known_at_cutoff(bars, session_date, config, bar_minutes)
    if not regular:
        return None
    price = regular[-1].close
    high = max(bar.high for bar in regular)
    low = min(bar.low for bar in regular)
    volume = sum((bar.volume for bar in regular), Decimal("0"))
    recent = list(adv_volumes)[-config.adv_sessions:]
    adv = (sum(recent, Decimal("0")) / len(recent)) if len(recent) >= config.min_adv_sessions else None
    return OvernightCandidate(
        symbol=symbol,
        instrument_id=instrument_id,
        prior_close=prior_close,
        price=price,
        change=_q(price / prior_close - 1),
        high=high,
        low=low,
        close_location=_q((price - low) / (high - low)) if high > low else Decimal("1"),
        volume=volume,
        adv=_q(adv) if adv is not None else None,
        volume_ratio=_q(volume / adv) if adv else None,
        dollar_volume=_q(sum((bar.close * bar.volume for bar in regular), Decimal("0"))),
        prior_return_5d=_q(trend[-1] / trend[0] - 1) if trend else None,
        prior_up_days_5d=sum(1 for a, b in zip(trend, trend[1:]) if b > a) if trend else None,
        prior_return_20d=_q(trend20[-1] / trend20[0] - 1) if trend20 else None,
        adv_dollars=_q(adv_dollars) if adv_dollars is not None else None,
    )


OFF_52W_MIN_SESSIONS = 200


def off_52w_high(candidate: OvernightCandidate, daily: Sequence[OvernightBar], session_date: date) -> Decimal | None:
    """Prior close vs the highest high of up to 250 split-adjusted daily bars before ``session_date``.

    None with fewer than ``OFF_52W_MIN_SESSIONS`` bars (recent listings have no year to compare).
    """

    prior = sorted((b for b in daily if b.start.astimezone(_ET).date() < session_date), key=lambda b: b.start)[-250:]
    if len(prior) < OFF_52W_MIN_SESSIONS:
        return None
    high = max(b.high for b in prior)
    return _q(candidate.prior_close / high - 1) if high > 0 else None


def _qualifies(candidate: OvernightCandidate, arm: OvernightArmConfig, config: OvernightShadowConfig) -> bool:
    if not (config.minimum_price <= candidate.price <= config.maximum_price):
        return False
    if candidate.change < arm.min_change:
        return False
    if arm.max_change is not None and candidate.change >= arm.max_change:
        return False
    if candidate.volume_ratio is None or candidate.volume_ratio < arm.min_volume_ratio:
        return False
    return candidate.close_location >= arm.min_close_location


def select_arm_picks(
    candidates: Iterable[OvernightCandidate],
    config: OvernightShadowConfig,
) -> dict[str, list[OvernightPick]]:
    """Top ``max_picks_per_arm`` qualifying candidates per enabled arm, by dollar volume then symbol."""

    pool = list(candidates)
    picks: dict[str, list[OvernightPick]] = {}
    for arm in config.arms:
        if not arm.enabled:
            continue
        qualified = sorted(
            (c for c in pool if _qualifies(c, arm, config)),
            key=lambda c: (-c.dollar_volume, c.symbol),
        )[: config.max_picks_per_arm]
        picks[arm.arm_id] = [
            OvernightPick(arm_id=arm.arm_id, rank=index + 1, candidate=c)
            for index, c in enumerate(qualified)
        ]
    return picks


def population(candidates: Iterable[OvernightCandidate], config: OvernightShadowConfig) -> list[OvernightCandidate]:
    """Baseline population: every in-band stock up >= 10% at decision time (no other rules)."""

    return sorted(
        (
            c for c in candidates
            if c.change >= OVERNIGHT_POPULATION_MIN_CHANGE
            and config.minimum_price <= c.price <= config.maximum_price
        ),
        key=lambda c: c.symbol,
    )


def mid_population(candidates: Iterable[OvernightCandidate]) -> list[OvernightCandidate]:
    """Mid-cap research population: price $5-$50, ADV $5M-$50M, up >= 5% at decision time."""

    return sorted(
        (
            c for c in candidates
            if c.change >= MID_POPULATION_MIN_CHANGE
            and MID_MIN_PRICE <= c.price <= MID_MAX_PRICE
            and c.adv_dollars is not None and MID_MIN_ADV_DOLLARS <= c.adv_dollars <= MID_MAX_ADV_DOLLARS
        ),
        key=lambda c: c.symbol,
    )


def _first_at_or_after(bars: Sequence[OvernightBar], moment: datetime, before: datetime) -> OvernightBar | None:
    return next((bar for bar in sorted(bars, key=lambda b: b.start) if moment <= bar.start < before), None)


def label_outcome(
    *,
    arm_id: str,
    candidate: OvernightCandidate,
    session_date: date,
    next_session_date: date,
    session_bars: Sequence[OvernightBar],
    next_bars: Sequence[OvernightBar],
    config: OvernightShadowConfig,
    session_close: time | None = None,
    next_close: time | None = None,
    split_factor: Decimal | None = None,
) -> OvernightOutcome:
    """Entry at the ``entry_et`` 1m open; primary exit at the next session's 09:30 open.

    ``split_factor`` (from :func:`split_factors`) puts next-session prices in entry-session units for
    the returns; the recorded prices stay as traded, and costs use the traded exit price.
    """

    session_close = session_close or regular_close_time(session_date)
    next_close = next_close or regular_close_time(next_session_date)
    entry_bar = _first_at_or_after(
        session_bars,
        datetime.combine(session_date, config.entry_et, tzinfo=_ET),
        datetime.combine(session_date, session_close, tzinfo=_ET),
    )
    open_at = datetime.combine(next_session_date, time(9, 30), tzinfo=_ET)
    flat_at = datetime.combine(next_session_date, next_close, tzinfo=_ET) - timedelta(minutes=5)
    open_bar = _first_at_or_after(next_bars, open_at, flat_at)
    premarket = [
        bar for bar in next_bars
        if bar.start.astimezone(_ET).date() == next_session_date
        and time(4, 0) <= bar.start.astimezone(_ET).time()
        and bar.start + timedelta(minutes=1) <= datetime.combine(next_session_date, time(8, 0), tzinfo=_ET)
    ]
    bar_0945 = _first_at_or_after(next_bars, datetime.combine(next_session_date, time(9, 45), tzinfo=_ET), flat_at)
    common = dict(
        arm_id=arm_id, symbol=candidate.symbol, instrument_id=candidate.instrument_id,
        session_date=session_date, next_session_date=next_session_date,
        premarket_0800=premarket[-1].close if premarket else None,
        price_0945=bar_0945.open if bar_0945 else None,
        split_factor=split_factor,
    )
    factor = split_factor or Decimal("1")
    if entry_bar is None:
        return OvernightOutcome(**common, entry_price=None, exit_open=None, gross_return=None,
                                net_return=None, gap_return=None, status="no_entry")
    entry = entry_bar.open
    if open_bar is None:
        return OvernightOutcome(**common, entry_price=entry, exit_open=None, gross_return=None,
                                net_return=_EXIT_MISSING_RETURN, gap_return=None, status="no_open")
    exit_price = open_bar.open
    gross = exit_price * factor / entry - 1
    net = exit_price * factor * (1 - half_spread(exit_price)) / (entry * (1 + half_spread(entry))) - 1
    return OvernightOutcome(
        **common, entry_price=entry, exit_open=exit_price, gross_return=_q(gross), net_return=_q(net),
        gap_return=_q(exit_price * factor / candidate.price - 1), status="labelled",
    )


def label_benchmark(
    *,
    symbol: str,
    session_date: date,
    next_session_date: date,
    session_bars: Sequence[OvernightBar],
    next_bars: Sequence[OvernightBar],
    config: OvernightShadowConfig,
    session_close: time | None = None,
    next_close: time | None = None,
    split_factor: Decimal | None = None,
) -> OvernightBenchmarkOutcome:
    """Same entry minute and 09:30 exit as the picks, without costs (market-adjusted scoring)."""

    session_close = session_close or regular_close_time(session_date)
    next_close = next_close or regular_close_time(next_session_date)
    entry_bar = _first_at_or_after(
        session_bars,
        datetime.combine(session_date, config.entry_et, tzinfo=_ET),
        datetime.combine(session_date, session_close, tzinfo=_ET),
    )
    open_bar = _first_at_or_after(
        next_bars,
        datetime.combine(next_session_date, time(9, 30), tzinfo=_ET),
        datetime.combine(next_session_date, next_close, tzinfo=_ET) - timedelta(minutes=5),
    )
    entry = entry_bar.open if entry_bar else None
    exit_price = open_bar.open if open_bar else None
    return OvernightBenchmarkOutcome(
        symbol=symbol, entry_price=entry, exit_open=exit_price, split_factor=split_factor,
        overnight_return=_q(exit_price * (split_factor or 1) / entry - 1) if entry and exit_price else None,
    )


class OvernightArmScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    arm_id: str
    picks: int
    labelled: int
    mean_net_return: Decimal | None
    median_net_return: Decimal | None
    winners: int
    big_gap_ups: int
    big_gap_downs: int


def score(arm_id: str, outcomes: Sequence[OvernightOutcome]) -> OvernightArmScore:
    """Equal-weight session score for one arm or population (``no_open`` counts as its -50%)."""

    nets = [o.net_return for o in outcomes if o.net_return is not None]
    gross = [o.gross_return for o in outcomes if o.gross_return is not None]
    return OvernightArmScore(
        arm_id=arm_id,
        picks=len(outcomes),
        labelled=len(nets),
        mean_net_return=_q(sum(nets, Decimal("0")) / len(nets)) if nets else None,
        median_net_return=_q(Decimal(statistics.median(nets))) if nets else None,
        winners=sum(1 for n in nets if n > 0),
        big_gap_ups=sum(1 for g in gross if g >= _BIG_GAP),
        big_gap_downs=sum(1 for g in gross if g <= -_BIG_GAP),
    )


__all__ = [
    "NEWS_CATEGORIES",
    "OVERNIGHT_BENCHMARKS",
    "OVERNIGHT_POPULATION_MIN_CHANGE",
    "OVERNIGHT_TRADING_STRATEGY_ID",
    "OvernightArmScore",
    "OvernightBar",
    "OvernightBenchmark",
    "OvernightBenchmarkOutcome",
    "OvernightCandidate",
    "OvernightHeadline",
    "OvernightNewsContext",
    "OvernightOutcome",
    "OvernightPick",
    "OvernightSocialMention",
    "build_benchmark",
    "build_candidate",
    "half_spread",
    "label_benchmark",
    "label_outcome",
    "mid_population",
    "news_context",
    "off_52w_high",
    "population",
    "score",
    "select_arm_picks",
    "split_factors",
]
