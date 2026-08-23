from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one match in {path}, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Alpaca historical stock bars are timestamped at BAR START. A 09:20 1m bar
# contains 09:20-09:21 information and therefore is not causally available to a
# 09:20 universe scan. Require every candidate/TOD bar to be complete by scan.
replace_once(
    "src/app/trading/historical_gapper_reconstruction.py",
    """            local = observed.astimezone(_ET)\n            if local.date() != session_date or local.timetz().replace(tzinfo=None) > scan_time:\n                continue\n""",
    """            local = observed.astimezone(_ET)\n            completed = local + timedelta(minutes=1)\n            if local.date() != session_date or completed.timetz().replace(tzinfo=None) > scan_time:\n                continue\n""",
)
replace_once(
    "src/app/trading/historical_gapper_reconstruction.py",
    """        clock = local.timetz().replace(tzinfo=None)\n        if clock < _PREMARKET_OPEN or clock > scan_time:\n            continue\n""",
    """        clock = local.timetz().replace(tzinfo=None)\n        completed_clock = (local + timedelta(minutes=1)).timetz().replace(tzinfo=None)\n        if clock < _PREMARKET_OPEN or completed_clock > scan_time:\n            continue\n""",
)
# The API end is exclusive for our causal purpose: do not request the bar that
# starts at the scan timestamp in either seed or deeper premarket history.
replace_once(
    "src/app/trading/historical_gapper_reconstruction.py",
    """            end=scan_at + timedelta(minutes=1),\n            chunk_size=200,\n""",
    """            end=scan_at,\n            chunk_size=200,\n""",
)
replace_once(
    "src/app/trading/historical_gapper_reconstruction.py",
    """            end=scan_at + timedelta(minutes=1),\n            chunk_size=25,\n""",
    """            end=scan_at,\n            chunk_size=25,\n""",
)

# Old frozen dataset caches include the 09:20-starting bar in reconstructed
# candidate features. Bump the namespace so those datasets can never be silently
# reused after the causality fix.
replace_once(
    "scripts/run_trading_strategy_liquidity_sweep.py",
    '_DATASET_CACHE_VERSION = "liquidity-sweep-dataset-v1"',
    '_DATASET_CACHE_VERSION = "liquidity-sweep-dataset-v2-causal-scan"',
)

# Regression: a huge 09:20 bar must not change the 09:20 candidate snapshot.
replace_once(
    "src/tests/trading/test_trading_historical_gapper_reconstruction.py",
    """                bars.append({\"t\": f\"{prior.isoformat()}T13:20:00Z\", \"c\": 8, \"v\": 100})\n        bars.append({\"t\": f\"{self.session_date.isoformat()}T13:20:00Z\", \"c\": 10.4, \"v\": 600})\n""",
    """                bars.append({\"t\": f\"{prior.isoformat()}T13:19:00Z\", \"c\": 8, \"v\": 100})\n        bars.append({\"t\": f\"{self.session_date.isoformat()}T13:19:00Z\", \"c\": 10.4, \"v\": 600})\n        # Alpaca timestamps minute bars at their start. This 09:20 ET bar is\n        # not complete at a 09:20 scan and must be causally invisible.\n        bars.append({\"t\": f\"{self.session_date.isoformat()}T13:20:00Z\", \"c\": 99, \"v\": 999999})\n""",
)
replace_once(
    "src/tests/trading/test_trading_historical_gapper_reconstruction.py",
    """    assert candidate.gap_pct == Decimal(\"30.0\")\n    assert candidate.spread_bps == Decimal(\"40\")\n""",
    """    assert candidate.gap_pct == Decimal(\"30.0\")\n    assert candidate.premarket_price == Decimal(\"10.4\")\n    assert candidate.premarket_volume == Decimal(\"600\")\n    assert candidate.tod_rvol == Decimal(\"6\")\n    assert candidate.spread_bps == Decimal(\"40\")\n""",
)

exploration = r'''from __future__ import annotations

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

    if dev_meta["missing_sessions"] or val_meta["missing_sessions"]:
        # Missing provider sessions are never silently turned into no-trade days.
        print(json.dumps({"development": dev_meta, "validation": val_meta}, indent=2))
        raise SystemExit(2)

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
'''
Path("scripts/run_trading_strategy_v2_extended_exploration.py").write_text(exploration, encoding="utf-8")

workflow = r'''name: Trading strategy extended dataset

on:
  workflow_dispatch:
    inputs:
      development_start:
        description: Development block start (YYYY-MM-DD)
        required: true
        default: "2026-01-02"
      development_end:
        description: Development block end (YYYY-MM-DD)
        required: true
        default: "2026-02-27"
      validation_start:
        description: One-shot validation block start (YYYY-MM-DD)
        required: true
        default: "2026-03-02"
      validation_end:
        description: One-shot validation block end (YYYY-MM-DD)
        required: true
        default: "2026-03-27"

permissions:
  contents: read

concurrency:
  group: trading-historical-alpaca-${{ github.repository }}
  cancel-in-progress: false

jobs:
  extend-frozen-dataset:
    runs-on: ubuntu-latest
    timeout-minutes: 180
    env:
      PYTHONPATH: "src:."
      OMNIX_PERSISTENCE_MODE: legacy_test
      OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE: "1"
      OMNIX_ALPACA_API_KEY_ID: ${{ secrets.OMNIX_ALPACA_API_KEY_ID }}
      OMNIX_ALPACA_API_SECRET_KEY: ${{ secrets.OMNIX_ALPACA_API_SECRET_KEY }}
    steps:
      - name: Check out exact workflow head
        uses: actions/checkout@v4
        with:
          ref: ${{ github.sha }}

      - name: Verify Alpaca historical-data credentials
        shell: bash
        run: |
          if [[ -z "${OMNIX_ALPACA_API_KEY_ID}" || -z "${OMNIX_ALPACA_API_SECRET_KEY}" ]]; then
            echo "::error::Both OMNIX_ALPACA_API_KEY_ID and OMNIX_ALPACA_API_SECRET_KEY are required for cache misses."
            exit 2
          fi

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install backtest dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install fastapi httpx pydantic requests python-multipart pillow websockets "psycopg[binary]>=3.2.1,<4" "psycopg-pool>=3.2.1,<4"

      - name: Build append-only causal cache key
        id: dataset-cache-key
        shell: bash
        run: |
          echo "key=trading-liquidity-datasets-v2-causal-${RUNNER_OS}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" >> "${GITHUB_OUTPUT}"

      - name: Restore causal frozen datasets
        uses: actions/cache/restore@v4
        with:
          path: .cache/trading-liquidity-datasets
          key: ${{ steps.dataset-cache-key.outputs.key }}
          restore-keys: |
            trading-liquidity-datasets-v2-causal-${{ runner.os }}-

      - name: Capture only missing development + validation sessions
        shell: bash
        run: |
          mkdir -p .cache/trading-liquidity-datasets
          python scripts/run_trading_strategy_liquidity_sweep_resilient.py \
            --start-date "${{ inputs.development_start }}" \
            --end-date "${{ inputs.validation_end }}" \
            --dataset-cache-dir .cache/trading-liquidity-datasets \
            --output-dir artifacts/v2-extended-cache-capture \
            --reconstruction-max-age-days 365 \
            --max-sessions 80 \
            --thresholds 100000 \
            --initial-cash 100000 \
            --assumed-spread-bps 150 \
            --require-covered-session

      - name: Explore frozen-V2 single-axis successors from cache only
        shell: bash
        run: |
          python scripts/run_trading_strategy_v2_extended_exploration.py \
            --dataset-cache-dir .cache/trading-liquidity-datasets \
            --development-start "${{ inputs.development_start }}" \
            --development-end "${{ inputs.development_end }}" \
            --validation-start "${{ inputs.validation_start }}" \
            --validation-end "${{ inputs.validation_end }}" \
            --initial-cash 100000 \
            --assumed-spread-bps 150 \
            --minimum-development-trades 5 \
            --finalists 3 \
            --output-dir artifacts/v2-extended-exploration

      - name: Save causal frozen datasets
        if: always()
        uses: actions/cache/save@v4
        with:
          path: .cache/trading-liquidity-datasets
          key: ${{ steps.dataset-cache-key.outputs.key }}

      - name: Publish summaries
        if: always()
        shell: bash
        run: |
          if [[ -f artifacts/v2-extended-cache-capture/summary.md ]]; then
            cat artifacts/v2-extended-cache-capture/summary.md >> "${GITHUB_STEP_SUMMARY}"
          fi
          if [[ -f artifacts/v2-extended-exploration/summary.md ]]; then
            cat artifacts/v2-extended-exploration/summary.md >> "${GITHUB_STEP_SUMMARY}"
          fi

      - name: Upload extension evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: trading-v2-extended-causal-evidence
          path: |
            artifacts/v2-extended-cache-capture
            artifacts/v2-extended-exploration
          if-no-files-found: warn
          retention-days: 30
'''
Path(".github/workflows/trading-strategy-extended-dataset.yml").write_text(workflow, encoding="utf-8")

print("Applied causal scan cutoff, cache v2 invalidation, regression coverage, cached V2 exploration, and extended workflow.")
