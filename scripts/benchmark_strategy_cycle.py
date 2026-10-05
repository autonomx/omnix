"""Measure the CPU work of one trading strategy cycle at 50 and 200 symbols (WP-7.5).

Each cycle the strategy monitor evaluates every candidate in the active
universe on its finalized one-minute bars: resampling to the structure
interval, the gap-pullback v1 and v2 state machines, the 5m Stoch RSI
strategy and the Stoch trend-capture arm. This script runs exactly those
evaluators on deterministic synthetic sessions (pre-market plus the regular
session up to the measured time) and reports wall and CPU time per cycle.
Database reads, provider calls and event writes are I/O and are measured by
the gateway benchmarks, not here.

    python scripts/benchmark_strategy_cycle.py --symbols 50 200 --cycles 5
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.trading.gapper_dataset import GapperCandidate  # noqa: E402
from app.trading.models import MarketBar  # noqa: E402
from app.trading.strategies.failed_selloff_v2 import evaluate_gap_pullback_v2  # noqa: E402
from app.trading.strategies.gap_pullback import evaluate_gap_pullback  # noqa: E402
from app.trading.strategies.models import GapPullbackConfig, StochRsi5mConfig  # noqa: E402
from app.trading.strategy_stoch_rsi_5m import evaluate_stoch_rsi_5m  # noqa: E402
from app.trading.strategy_stoch_trend_capture import evaluate_stoch_trend_capture  # noqa: E402
from app.trading.strategy_timeframes import resample_final_bars  # noqa: E402
from app.trading.us_equity_calendar import EASTERN  # noqa: E402

SESSION = date(2026, 9, 29)
RECEIVED = datetime(2026, 9, 29, 21, 0, tzinfo=timezone.utc)


def synthetic_session(instrument_id: str, *, until_minute: int, seed: int) -> tuple[GapperCandidate, list[MarketBar]]:
    """A gapper: 04:00-09:30 pre-market then regular bars up to ``until_minute`` after the open."""
    rng = random.Random(seed)
    previous_close = Decimal(str(round(rng.uniform(2, 40), 2)))
    price = float(previous_close) * rng.uniform(1.15, 1.6)
    start = datetime.combine(SESSION, datetime.min.time(), tzinfo=EASTERN).replace(hour=4)
    total = 330 + until_minute
    bars: list[MarketBar] = []
    for minute in range(total):
        opened = start + timedelta(minutes=minute)
        drift = rng.gauss(0, 0.004)
        close = max(0.5, price * (1 + drift))
        high = max(price, close) * (1 + abs(rng.gauss(0, 0.002)))
        low = min(price, close) * (1 - abs(rng.gauss(0, 0.002)))
        regular = minute >= 330
        bars.append(MarketBar(
            instrument_id=instrument_id,
            interval="1m",
            start_time=opened.astimezone(timezone.utc),
            end_time=(opened + timedelta(minutes=1)).astimezone(timezone.utc),
            open=Decimal(f"{price:.4f}"),
            high=Decimal(f"{high:.4f}"),
            low=Decimal(f"{low:.4f}"),
            close=Decimal(f"{close:.4f}"),
            volume=Decimal(rng.randint(5_000, 400_000) if regular else rng.randint(200, 40_000)),
            session="regular" if regular else "extended_pre",
            provider="benchmark",
            received_at=RECEIVED,
        ))
        price = close
    premarket = bars[329].close
    candidate = GapperCandidate(
        instrument_id=instrument_id,
        observed_at=datetime.combine(SESSION, datetime.min.time(), tzinfo=EASTERN).replace(hour=9, minute=25),
        previous_close=previous_close,
        premarket_price=premarket,
        gap_pct=(premarket / previous_close - 1) * 100,
        premarket_volume=Decimal("2500000"),
        premarket_dollar_volume=premarket * Decimal("2500000"),
        tod_rvol=Decimal("4"),
        spread_bps=Decimal("20"),
    )
    return candidate, bars


def evaluate_symbol(candidate: GapperCandidate, bars: list[MarketBar], gap: GapPullbackConfig, stoch: StochRsi5mConfig) -> None:
    structure = resample_final_bars(bars, gap.structure_interval)
    evaluate_gap_pullback(candidate, structure, gap)
    evaluate_gap_pullback_v2(candidate, structure, gap)
    evaluate_stoch_rsi_5m(bars, stoch)
    evaluate_stoch_trend_capture(bars)


def measure(symbols: int, cycles: int, until_minute: int) -> dict[str, object]:
    gap, stoch = GapPullbackConfig(), StochRsi5mConfig()
    sessions = [synthetic_session(f"equity:BENCH{index:03d}", until_minute=until_minute, seed=index) for index in range(symbols)]
    wall: list[float] = []
    cpu: list[float] = []
    for _ in range(cycles):
        started_wall, started_cpu = time.perf_counter(), time.process_time()
        for candidate, bars in sessions:
            evaluate_symbol(candidate, bars, gap, stoch)
        wall.append(time.perf_counter() - started_wall)
        cpu.append(time.process_time() - started_cpu)
    ordered = sorted(wall)
    return {
        "symbols": symbols,
        "regular_minutes": until_minute,
        "bars_per_symbol": 330 + until_minute,
        "cycles": cycles,
        "wall_p50_seconds": round(statistics.median(wall), 3),
        "wall_p95_seconds": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 3),
        "cpu_mean_seconds": round(statistics.fmean(cpu), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", type=int, nargs="+", default=[50, 200])
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--regular-minutes", type=int, nargs="+", default=[60, 390],
                        help="minutes after the open the session has reached (390 = the close)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = [measure(count, args.cycles, minutes) for minutes in args.regular_minutes for count in args.symbols]
    report = json.dumps({"measurements": rows}, indent=2)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
