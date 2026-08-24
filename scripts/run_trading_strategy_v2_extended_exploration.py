from __future__ import annotations

"""Disciplined cached-data exploration around the frozen gap-pullback V2 profile.

This utility never changes the frozen/prospective 2.0.0 profile. It evaluates a
predeclared family of SINGLE-AXIS sensitivity variants on a development block,
selects at most three by development-only metrics, and reveals the validation
block only for those finalists plus the frozen baseline. The intended output is
an experimental successor candidate (future V3), never a retroactive V2 retune.

All input sessions are immutable fingerprint-verified BacktestSessionDataset
files. No provider/API calls occur in this script.
"""

import argparse
import json
import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from app.trading.paper import PaperExecutionPolicy
from app.trading.strategies.models import GapPullbackConfig, StrategyRiskProfile
from app.trading.strategy_backtest import BacktestSessionDataset, run_gap_pullback_backtest
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from app.trading.us_equity_calendar import regular_holidays
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import (
    _cache_namespace,
    _dataset_cache_path,
    _load_cached_dataset,
    _load_no_candidate_marker,
    _no_candidate_cache_path,
)


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Explore V2 successor candidates using cached causal historical datasets only.")
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--development-start", default="2026-01-02")
    p.add_argument("--development-end", default="2026-02-27")
    p.add_argument("--validation-start", default="2026-03-02")
    p.add_argument("--validation-end", default="2026-03-27")
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--minimum-development-trades", type=int, default=5)
    p.add_argument("--finalists", type=int, default=3)
    p.add_argument("--output-dir", default="artifacts/v2-extended-exploration")
    return p.parse_args()


def _sessions(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end date precedes start date")
    holidays: set[date] = set()
    for year in range(start.year, end.year + 1):
        holidays.update(regular_holidays(year))
    rows: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in holidays:
            rows.append(cursor)
        cursor += timedelta(days=1)
    return rows


def _load_block(cache: Path, start: date, end: date) -> tuple[list[BacktestSessionDataset], dict[str, object]]:
    datasets: list[BacktestSessionDataset] = []
    no_candidates: list[str] = []
    missing: list[str] = []
    fingerprints: dict[str, str] = {}
    requested = _sessions(start, end)
    for session in requested:
        dataset_path = _dataset_cache_path(cache, session)
        empty_path = _no_candidate_cache_path(cache, session)
        if dataset_path.exists():
            dataset = _load_cached_dataset(dataset_path, session)
            datasets.append(dataset)
            fingerprints[session.isoformat()] = dataset.dataset_fingerprint
        elif empty_path.exists():
            _load_no_candidate_marker(empty_path, session)
            no_candidates.append(session.isoformat())
        else:
            missing.append(session.isoformat())
    meta = {
        "requested_sessions": len(requested),
        "dataset_sessions": len(datasets),
        "no_candidate_sessions": len(no_candidates),
        "covered_sessions": len(datasets) + len(no_candidates),
        "missing_sessions": missing,
        "dataset_fingerprints": fingerprints,
    }
    return sorted(datasets, key=lambda item: item.session_date), meta


def _lcb90(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values) - 1)
    stdev = Decimal(str(math.sqrt(float(variance))))
    stderr = stdev / Decimal(str(math.sqrt(len(values))))
    return mean - Decimal("1.2815515655446004") * stderr


def _max_drawdown_r(values: list[Decimal]) -> Decimal:
    equity = Decimal("0")
    peak = Decimal("0")
    drawdown = Decimal("0")
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _run_variant(
    datasets: list[BacktestSessionDataset],
    config: GapPullbackConfig,
    *,
    initial_cash: Decimal,
    spread: Decimal,
) -> dict[str, object]:
    risk = StrategyRiskProfile()
    policy = PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    current_cash = initial_cash
    trades = []
    candidate_count = 0
    trigger_count = 0
    for dataset in datasets:
        result = run_gap_pullback_backtest(
            dataset,
            config,
            policy,
            assumed_spread_bps=spread,
            max_hold_minutes=config.v2_max_hold_minutes,
            max_concurrent_positions=risk.max_positions,
            risk_profile=risk,
            initial_cash=current_cash,
        )
        pnl = sum((trade.pnl_per_share * trade.entry_fill_quantity for trade in result.trades), Decimal("0"))
        current_cash += pnl
        trades.extend(result.trades)
        candidate_count += result.summary.candidate_count
        trigger_count += result.summary.trigger_count
    r_values = [trade.r_multiple for trade in trades]
    expectancy = sum(r_values, Decimal("0")) / Decimal(len(r_values)) if r_values else None
    return {
        "profile_fingerprint": v2_profile_fingerprint(config),
        "candidate_count": candidate_count,
        "trigger_count": trigger_count,
        "trade_count": len(trades),
        "win_count": sum(value > 0 for value in r_values),
        "loss_count": sum(value < 0 for value in r_values),
        "expectancy_r": str(expectancy) if expectancy is not None else None,
        "one_sided_90_lcb_r": str(_lcb90(r_values)) if len(r_values) >= 2 else None,
        "max_drawdown_r": str(_max_drawdown_r(r_values)),
        "pnl": str(current_cash - initial_cash),
        "return_pct": str(((current_cash - initial_cash) / initial_cash) * Decimal("100")),
        "trades": [
            {
                "instrument_id": trade.instrument_id,
                "entry_time": trade.entry_time.isoformat(),
                "exit_time": trade.exit_time.isoformat(),
                "exit_reason": trade.exit_reason,
                "r_multiple": str(trade.r_multiple),
                "mfe_r": str(trade.mfe_r),
                "mae_r": str(trade.mae_r),
            }
            for trade in trades
        ],
    }


def _variant_family() -> list[tuple[str, dict[str, object]]]:
    # Deliberately small, single-axis sensitivity family. No combinatorial search.
    return [
        ("frozen_v2_baseline", {}),
        ("liq_250k", {"minimum_premarket_dollar_volume": Decimal("250000")}),
        ("liq_500k", {"minimum_premarket_dollar_volume": Decimal("500000")}),
        ("liq_1m", {"minimum_premarket_dollar_volume": Decimal("1000000")}),
        ("rvol_4", {"minimum_tod_rvol": Decimal("4")}),
        ("rvol_5", {"minimum_tod_rvol": Decimal("5")}),
        ("gap_25", {"minimum_gap_pct": Decimal("25")}),
        ("gap_30", {"minimum_gap_pct": Decimal("30")}),
        ("recovery_7_5", {"v2_recovery_min_pct": Decimal("7.5")}),
        ("recovery_10", {"v2_recovery_min_pct": Decimal("10")}),
        ("second_pullback_3", {"v2_second_pullback_min_pct": Decimal("3")}),
        ("second_pullback_4", {"v2_second_pullback_min_pct": Decimal("4")}),
        ("l2_signal_6m", {"v2_maximum_l2_to_signal_minutes": 6}),
        ("l2_signal_10m", {"v2_maximum_l2_to_signal_minutes": 10}),
        ("reward_1_25r", {"reward_multiple": Decimal("1.25")}),
        ("reward_1_75r", {"reward_multiple": Decimal("1.75")}),
    ]


def _decimal_metric(row: dict[str, object], key: str, default: str) -> Decimal:
    value = row.get(key)
    return Decimal(str(value)) if value is not None else Decimal(default)


def main() -> int:
    args = _args()
    dev_start = date.fromisoformat(args.development_start)
    dev_end = date.fromisoformat(args.development_end)
    val_start = date.fromisoformat(args.validation_start)
    val_end = date.fromisoformat(args.validation_end)
    if val_start <= dev_end:
        raise ValueError("validation block must start after development block")
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)

    # Dataset construction uses the same 20%/$0.50-$20/50-name reconstruction
    # envelope as frozen V2. Liquidity/RVOL and V2 geometry are evaluated later.
    cache_basis_strategy = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, basis = _cache_namespace(cache_basis_strategy, spread)
    cache = Path(args.dataset_cache_dir) / namespace
    dev_datasets, dev_meta = _load_block(cache, dev_start, dev_end)
    val_datasets, val_meta = _load_block(cache, val_start, val_end)

    def require_coverage(label: str, meta: dict[str, object], *, absolute_floor: int) -> None:
        requested = int(meta["requested_sessions"])
        covered = int(meta["covered_sessions"])
        required = max(absolute_floor, math.ceil(requested * 0.80))
        if covered < required:
            print(json.dumps({label: meta, "required_covered_sessions": required}, indent=2))
            raise SystemExit(2)

    # Missing provider sessions stay explicit/excluded. A block is usable only if
    # at least 80% is covered (and at least 20 dev / 10 validation sessions).
    require_coverage("development", dev_meta, absolute_floor=20)
    require_coverage("validation", val_meta, absolute_floor=10)

    frozen = frozen_v2_config()
    development: list[dict[str, object]] = []
    configs: dict[str, GapPullbackConfig] = {}
    for variant_id, updates in _variant_family():
        config = frozen.model_copy(update=updates)
        configs[variant_id] = config
        metrics = _run_variant(dev_datasets, config, initial_cash=initial_cash, spread=spread)
        development.append({"variant_id": variant_id, "updates": {k: str(v) for k, v in updates.items()}, **metrics})

    eligible = [row for row in development if int(row["trade_count"]) >= args.minimum_development_trades and row["expectancy_r"] is not None]
    eligible.sort(
        key=lambda row: (
            _decimal_metric(row, "expectancy_r", "-999"),
            -_decimal_metric(row, "max_drawdown_r", "999"),
            int(row["trade_count"]),
        ),
        reverse=True,
    )
    finalists = ["frozen_v2_baseline"]
    for row in eligible:
        variant_id = str(row["variant_id"])
        if variant_id not in finalists:
            finalists.append(variant_id)
        if len(finalists) >= 1 + max(0, args.finalists):
            break

    validation: list[dict[str, object]] = []
    for variant_id in finalists:
        metrics = _run_variant(val_datasets, configs[variant_id], initial_cash=initial_cash, spread=spread)
        validation.append({"variant_id": variant_id, **metrics})

    baseline_validation = next(row for row in validation if row["variant_id"] == "frozen_v2_baseline")
    baseline_exp = _decimal_metric(baseline_validation, "expectancy_r", "-999")
    successor_candidates = []
    for row in validation:
        if row["variant_id"] == "frozen_v2_baseline" or row["expectancy_r"] is None:
            continue
        exp = _decimal_metric(row, "expectancy_r", "-999")
        if int(row["trade_count"]) >= 3 and exp > 0 and exp > baseline_exp:
            successor_candidates.append(str(row["variant_id"]))

    payload = {
        "purpose": "experimental_successor_search_only",
        "frozen_v2_untouched": True,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "cache_namespace": namespace,
        "cache_basis": basis,
        "assumed_spread_bps": str(spread),
        "development_period": [dev_start.isoformat(), dev_end.isoformat()],
        "validation_period": [val_start.isoformat(), val_end.isoformat()],
        "development_coverage": dev_meta,
        "validation_coverage": val_meta,
        "selection_rule": f"development only; >= {args.minimum_development_trades} trades; rank expectancy, drawdown, trade count; reveal validation for baseline + top {args.finalists}",
        "development_results": development,
        "validation_finalists": validation,
        "successor_candidates": successor_candidates,
        "warning": "Historical reconstruction uses current listings and IEX partial-market data. These results may inform a separately versioned successor but cannot alter or qualify frozen V2.",
    }
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V2 extended cached-data exploration",
        "",
        "**Experimental successor search only. Frozen V2 is unchanged.**",
        "",
        f"- Cache: `{namespace}` (fingerprint-verified immutable datasets; no provider calls during exploration)",
        f"- Assumed spread: {spread} bps",
        f"- Development: {dev_start} through {dev_end} — {dev_meta['covered_sessions']}/{dev_meta['requested_sessions']} sessions covered",
        f"- Validation: {val_start} through {val_end} — {val_meta['covered_sessions']}/{val_meta['requested_sessions']} sessions covered",
        "",
        "## Development ranking",
        "",
        "| Variant | Trades | Expectancy | 90% LCB | DD (R) | P&L |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(development, key=lambda item: _decimal_metric(item, "expectancy_r", "-999"), reverse=True):
        lines.append(f"| {row['variant_id']} | {row['trade_count']} | {row['expectancy_r']} | {row['one_sided_90_lcb_r']} | {row['max_drawdown_r']} | {row['pnl']} |")
    lines.extend([
        "",
        "## One-shot validation (baseline + development finalists only)",
        "",
        "| Variant | Trades | Expectancy | 90% LCB | DD (R) | P&L |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in validation:
        lines.append(f"| {row['variant_id']} | {row['trade_count']} | {row['expectancy_r']} | {row['one_sided_90_lcb_r']} | {row['max_drawdown_r']} | {row['pnl']} |")
    lines.extend([
        "",
        "## Interpretation",
        "",
        f"- Successor candidates that beat frozen V2 on validation with positive expectancy and >=3 trades: {', '.join(successor_candidates) if successor_candidates else 'none'}.",
        "- Do not retune frozen V2 from this output. Any adopted change must become a separately versioned successor and receive fresh out-of-sample/prospective validation.",
        "- Reconstructed history remains approximate because current listings create survivorship/listing bias and IEX is not SIP/NBBO.",
    ])
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
