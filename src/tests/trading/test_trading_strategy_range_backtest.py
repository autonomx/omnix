from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

from app.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe
from app.trading.strategies.models import GapPullbackConfig, StrategyRiskProfile
from app.trading.strategy_range_backtest import (
    StrategyRangeBacktestRequest,
    choose_causal_universe,
    run_strategy_range_backtest,
)
from app.trading.strategy_repository import TradingStrategyConfigDocument


def candidate(symbol: str = "ABC", observed_at: datetime | None = None) -> GapperCandidate:
    return GapperCandidate(
        instrument_id=f"equity:NASDAQ:{symbol}",
        observed_at=observed_at,
        previous_close=Decimal("8"),
        premarket_price=Decimal("10.4"),
        gap_pct=Decimal("30"),
        premarket_volume=Decimal("1000000"),
        premarket_dollar_volume=Decimal("10400000"),
        tod_rvol=Decimal("6"),
        float_shares=Decimal("5000000"),
        spread_bps=Decimal("40"),
        discovery_rank=1,
    )


def universe(universe_id: str, observed: datetime):
    return freeze_gapper_universe(
        universe_id=universe_id,
        session_date=observed.date(),
        evaluation_time=observed,
        discovery_source="provider",
        candidates=[candidate(observed_at=observed)],
    )


def strategy() -> TradingStrategyConfigDocument:
    return TradingStrategyConfigDocument(
        strategy_id="range-test",
        account_id="paper-1",
        strategy_version="1.1.0",
        mode="off",
        config=GapPullbackConfig(
            strategy_version="1.1.0",
            entry_start_et=time(9, 35),
        ),
        risk=StrategyRiskProfile(),
    )


def test_choose_causal_universe_uses_latest_snapshot_before_cutoff_and_excludes_selected() -> None:
    early = universe("gappers-early", datetime(2026, 8, 18, 13, 10, tzinfo=timezone.utc))
    research = universe("gappers-early-research-091900", datetime(2026, 8, 18, 13, 19, tzinfo=timezone.utc))
    selected = universe("gappers-early-selected-092000", datetime(2026, 8, 18, 13, 20, tzinfo=timezone.utc))
    late = universe("gappers-late", datetime(2026, 8, 18, 13, 40, tzinfo=timezone.utc))

    chosen = choose_causal_universe(
        [early, research, selected, late],
        session_date=date(2026, 8, 18),
        cutoff_time=time(9, 35),
    )

    assert chosen is not None
    assert chosen.universe_id == research.universe_id


def test_range_backtest_reports_missing_universes_instead_of_treating_them_as_no_trade() -> None:
    request = StrategyRangeBacktestRequest(
        start_date=date(2026, 8, 17),
        end_date=date(2026, 8, 18),
        initial_cash=Decimal("100000"),
    )

    result = run_strategy_range_backtest(strategy(), [], request)

    assert result.requested_trading_sessions == 2
    assert result.covered_sessions == 0
    assert result.missing_universe_sessions == 2
    assert result.trade_count == 0
    assert result.ending_cash == Decimal("100000")
    assert all(day.status == "missing_universe" for day in result.days)
    assert result.point_in_time_universes_required is True
