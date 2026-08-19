from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from .gapper_dataset import GapperCandidate, GapperUniverseSnapshot
from .models import AdjustmentMode, MarketBar
from .paper import PaperExecutionPolicy
from .providers.errors import ProviderContractError, ProviderDataUnavailableError
from .providers.http_runtime import ProviderHttpRuntime
from .strategy_backtest import GapPullbackBacktestResult, freeze_backtest_session, run_gap_pullback_backtest
from .strategy_repository import TradingStrategyConfigDocument
from .us_equity_calendar import early_close_time, regular_holidays


_ET = ZoneInfo("America/New_York")
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class StrategyRangeBacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    assumed_spread_bps: Decimal = Field(default=Decimal("40"), ge=0, le=10_000)
    max_hold_minutes: int = Field(default=90, ge=1, le=390)
    universe_cutoff_et: time | None = None
    max_sessions: int = Field(default=60, ge=1, le=252)


class StrategyRangeBacktestDay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    status: Literal["backtested", "missing_universe", "data_unavailable", "error"]
    universe_id: str | None = None
    universe_evaluation_time: datetime | None = None
    candidate_count: int = 0
    starting_cash: Decimal
    ending_cash: Decimal
    pnl: Decimal = Decimal("0")
    trigger_count: int = 0
    trade_count: int = 0
    detail: str | None = None
    result: GapPullbackBacktestResult | None = None


class StrategyRangeBacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    strategy_kind: str
    strategy_version: str
    start_date: date
    end_date: date
    universe_cutoff_et: time
    initial_cash: Decimal
    ending_cash: Decimal
    pnl: Decimal
    return_pct: Decimal
    requested_trading_sessions: int
    covered_sessions: int
    missing_universe_sessions: int
    data_unavailable_sessions: int
    error_sessions: int
    candidate_count: int
    trigger_count: int
    trade_count: int
    win_count: int
    loss_count: int
    expectancy_r: Decimal
    days: tuple[StrategyRangeBacktestDay, ...]
    point_in_time_universes_required: Literal[True] = True


def _trading_dates(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise ValueError("backtest_end_date_precedes_start_date")
    output: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5 and cursor not in regular_holidays(cursor.year):
            output.append(cursor)
        cursor += timedelta(days=1)
    return output


def _cutoff(session_date: date, cutoff_time: time) -> datetime:
    return datetime.combine(session_date, cutoff_time, tzinfo=_ET).astimezone(timezone.utc)


def choose_causal_universe(
    universes: list[GapperUniverseSnapshot] | tuple[GapperUniverseSnapshot, ...],
    *,
    session_date: date,
    cutoff_time: time,
) -> GapperUniverseSnapshot | None:
    """Choose the freshest non-manually-selected snapshot available by cutoff.

    The range backtester intentionally does not use ``-selected-`` universes:
    strategy candidate selection must be reproduced by the deterministic strategy,
    not inherited from a later human/LLM inclusion decision. Research-enriched
    immutable snapshots are eligible only when they were frozen before cutoff.
    """

    cutoff = _cutoff(session_date, cutoff_time)
    eligible = [
        snapshot
        for snapshot in universes
        if snapshot.session_date == session_date
        and snapshot.evaluation_time.astimezone(timezone.utc) <= cutoff
        and "-selected-" not in snapshot.universe_id
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda snapshot: (snapshot.evaluation_time, snapshot.universe_id))
    return eligible[-1]


def _session_bounds(session_date: date) -> tuple[datetime, datetime]:
    close = early_close_time(session_date) or time(16, 0)
    start = datetime.combine(session_date, time(9, 30), tzinfo=_ET)
    end = datetime.combine(session_date, close, tzinfo=_ET)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def yahoo_historical_session_bars(
    candidate: GapperCandidate,
    session_date: date,
    *,
    runtime: ProviderHttpRuntime | None = None,
) -> list[MarketBar]:
    """Fetch regular-session 1m Yahoo bars for a known point-in-time candidate.

    Yahoo can supply historical chart bars only within provider retention limits;
    it is *not* used here to reconstruct the historical top-gainer universe.
    Missing/expired intraday history causes the entire day to fail closed rather
    than silently removing a candidate and biasing the strategy result.
    """

    active_runtime = runtime or ProviderHttpRuntime("yahoo_strategy_backtest", max_concurrency=2)
    symbol = candidate.instrument_id.split(":")[-1]
    session_start, session_end = _session_bounds(session_date)
    response = active_runtime.get(
        _YAHOO_CHART_URL.format(symbol=symbol),
        params={
            "period1": int(session_start.timestamp()),
            "period2": int((session_end + timedelta(minutes=1)).timestamp()),
            "interval": "1m",
            "includePrePost": "false",
            "events": "",
        },
        headers={"User-Agent": "Mozilla/5.0 Omnix local research"},
        timeout=20,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderContractError("Yahoo returned invalid historical strategy JSON") from exc
    chart = payload.get("chart") if isinstance(payload, dict) else None
    error = chart.get("error") if isinstance(chart, dict) else None
    if error:
        description = error.get("description") if isinstance(error, dict) else str(error)
        raise ProviderDataUnavailableError(f"Yahoo historical intraday data unavailable for {symbol}: {description}")
    result = ((chart or {}).get("result") or [None])[0] if isinstance(chart, dict) else None
    if not isinstance(result, dict):
        raise ProviderDataUnavailableError(f"Yahoo returned no historical strategy bars for {symbol}")
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    timestamps = result.get("timestamp") or []
    if not isinstance(quote, dict) or not isinstance(timestamps, list):
        raise ProviderContractError("Yahoo historical strategy payload is malformed")
    values = {field: quote.get(field) or [] for field in ("open", "high", "low", "close", "volume")}
    received_at = datetime.now(timezone.utc)
    bars: list[MarketBar] = []
    for index, raw_timestamp in enumerate(timestamps):
        if any(not isinstance(series, list) or index >= len(series) for series in values.values()):
            continue
        open_value = values["open"][index]
        high = values["high"][index]
        low = values["low"][index]
        close = values["close"][index]
        volume = values["volume"][index]
        if None in (open_value, high, low, close):
            continue
        start = datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc)
        local = start.astimezone(_ET)
        if local.date() != session_date or local.timetz().replace(tzinfo=None) < time(9, 30):
            continue
        if start >= session_end:
            continue
        bars.append(
            MarketBar(
                instrument_id=candidate.instrument_id,
                interval="1m",
                start_time=start,
                end_time=start + timedelta(minutes=1),
                open=Decimal(str(open_value)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=Decimal(str(volume or 0)),
                is_final=True,
                adjustment_mode=AdjustmentMode.RAW,
                session="regular",
                provider="yahoo",
                provider_event_id=str(raw_timestamp),
                received_at=received_at,
            )
        )
    if not bars:
        raise ProviderDataUnavailableError(f"Yahoo returned no regular-session 1m bars for {symbol} on {session_date}")
    return bars


def run_strategy_range_backtest(
    strategy: TradingStrategyConfigDocument,
    universes: list[GapperUniverseSnapshot] | tuple[GapperUniverseSnapshot, ...],
    request: StrategyRangeBacktestRequest,
) -> StrategyRangeBacktestResult:
    if strategy.strategy_kind != "gap_pullback_v1":
        raise ValueError("strategy_backtest_not_supported")
    sessions = _trading_dates(request.start_date, request.end_date)
    if len(sessions) > request.max_sessions:
        raise ValueError(f"backtest_session_limit_exceeded:{len(sessions)}>{request.max_sessions}")

    cutoff_time = request.universe_cutoff_et or strategy.config.entry_start_et
    current_cash = request.initial_cash
    days: list[StrategyRangeBacktestDay] = []
    runtime = ProviderHttpRuntime("yahoo_strategy_range_backtest", max_concurrency=2)

    grouped: dict[date, list[GapperUniverseSnapshot]] = defaultdict(list)
    for universe in universes:
        grouped[universe.session_date].append(universe)

    for session_date in sessions:
        starting_cash = current_cash
        universe = choose_causal_universe(
            grouped.get(session_date, []),
            session_date=session_date,
            cutoff_time=cutoff_time,
        )
        if universe is None:
            days.append(
                StrategyRangeBacktestDay(
                    session_date=session_date,
                    status="missing_universe",
                    starting_cash=starting_cash,
                    ending_cash=current_cash,
                    detail="No frozen point-in-time gapper/research universe existed before the backtest cutoff.",
                )
            )
            continue

        bars_by_instrument: dict[str, list[MarketBar]] = {}
        try:
            for candidate in universe.candidates:
                bars_by_instrument[candidate.instrument_id] = yahoo_historical_session_bars(
                    candidate,
                    session_date,
                    runtime=runtime,
                )
        except (ProviderContractError, ProviderDataUnavailableError, OSError) as exc:
            days.append(
                StrategyRangeBacktestDay(
                    session_date=session_date,
                    status="data_unavailable",
                    universe_id=universe.universe_id,
                    universe_evaluation_time=universe.evaluation_time,
                    candidate_count=len(universe.candidates),
                    starting_cash=starting_cash,
                    ending_cash=current_cash,
                    detail=str(exc),
                )
            )
            continue

        try:
            dataset = freeze_backtest_session(
                session_date=session_date,
                universe=universe,
                bars_by_instrument=bars_by_instrument,
            )
            result = run_gap_pullback_backtest(
                dataset,
                strategy.config,
                PaperExecutionPolicy(max_volume_participation_pct=Decimal("1")),
                assumed_spread_bps=request.assumed_spread_bps,
                max_hold_minutes=request.max_hold_minutes,
                max_concurrent_positions=strategy.risk.max_positions,
                risk_profile=strategy.risk,
                initial_cash=current_cash,
            )
            pnl = sum(
                (trade.pnl_per_share * trade.entry_fill_quantity for trade in result.trades),
                Decimal("0"),
            )
            current_cash += pnl
            days.append(
                StrategyRangeBacktestDay(
                    session_date=session_date,
                    status="backtested",
                    universe_id=universe.universe_id,
                    universe_evaluation_time=universe.evaluation_time,
                    candidate_count=result.summary.candidate_count,
                    starting_cash=starting_cash,
                    ending_cash=current_cash,
                    pnl=pnl,
                    trigger_count=result.summary.trigger_count,
                    trade_count=result.summary.trade_count,
                    result=result,
                )
            )
        except ValueError as exc:
            days.append(
                StrategyRangeBacktestDay(
                    session_date=session_date,
                    status="error",
                    universe_id=universe.universe_id,
                    universe_evaluation_time=universe.evaluation_time,
                    candidate_count=len(universe.candidates),
                    starting_cash=starting_cash,
                    ending_cash=current_cash,
                    detail=str(exc),
                )
            )

    trades = [trade for day in days if day.result is not None for trade in day.result.trades]
    total_pnl = current_cash - request.initial_cash
    divisor = Decimal(len(trades)) if trades else Decimal("1")
    return StrategyRangeBacktestResult(
        strategy_id=strategy.strategy_id,
        strategy_kind=strategy.strategy_kind,
        strategy_version=strategy.strategy_version,
        start_date=request.start_date,
        end_date=request.end_date,
        universe_cutoff_et=cutoff_time,
        initial_cash=request.initial_cash,
        ending_cash=current_cash,
        pnl=total_pnl,
        return_pct=(total_pnl / request.initial_cash) * Decimal("100"),
        requested_trading_sessions=len(sessions),
        covered_sessions=sum(day.status == "backtested" for day in days),
        missing_universe_sessions=sum(day.status == "missing_universe" for day in days),
        data_unavailable_sessions=sum(day.status == "data_unavailable" for day in days),
        error_sessions=sum(day.status == "error" for day in days),
        candidate_count=sum(day.candidate_count for day in days if day.status == "backtested"),
        trigger_count=sum(day.trigger_count for day in days),
        trade_count=len(trades),
        win_count=sum(trade.r_multiple > 0 for trade in trades),
        loss_count=sum(trade.r_multiple < 0 for trade in trades),
        expectancy_r=sum((trade.r_multiple for trade in trades), Decimal("0")) / divisor,
        days=tuple(days),
    )
