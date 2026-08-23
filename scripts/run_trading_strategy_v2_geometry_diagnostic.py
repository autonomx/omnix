from __future__ import annotations

"""Cache-only development diagnostic for a possible post-V2 successor.

Frozen V2 is never modified here. The script restores the same immutable causal
BacktestSessionDataset namespace used by the January-March extended backtest,
examines where development candidates stop in the V2 state machine, and runs a
small predeclared family of single-axis geometry probes. March is deliberately
not loaded or evaluated by this diagnostic.
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from app.trading.strategies.failed_selloff_v2 import evaluate_gap_pullback_v2
from app.trading.strategies.models import GapPullbackConfig
from app.trading.strategy_v2_qualification import frozen_v2_config, v2_profile_fingerprint
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant


_ET = ZoneInfo("America/New_York")
_STAGE_ORDER = (
    "discovered",
    "qualified_gap",
    "first_pullback",
    "first_low_confirmed",
    "bounce_high_confirmed",
    "second_pullback",
    "higher_low_confirmed",
    "vwap_reclaim",
    "lower_high_break",
    "entry_ready",
)
_STAGE_RANK = {stage: index for index, stage in enumerate(_STAGE_ORDER)}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose V2 geometry from immutable cached development data only.")
    parser.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    parser.add_argument("--development-start", default="2026-01-02")
    parser.add_argument("--development-end", default="2026-02-27")
    parser.add_argument("--initial-cash", default="100000")
    parser.add_argument("--assumed-spread-bps", default="150")
    parser.add_argument("--minimum-coverage-ratio", default="0.80")
    parser.add_argument("--minimum-covered-sessions", type=int, default=20)
    parser.add_argument("--output-dir", default="artifacts/v2-geometry-diagnostic")
    return parser.parse_args()


def _deepest_stage(transitions: tuple[str, ...]) -> str:
    visible = [stage for stage in transitions if stage in _STAGE_RANK]
    return max(visible, key=lambda stage: _STAGE_RANK[stage]) if visible else "discovered"


def _feature_value(result, name: str) -> str | int | None:
    value = getattr(result.features, name)
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return int(value) if isinstance(value, int) else str(value)


def _distribution(values: list[Decimal]) -> dict[str, str] | None:
    if not values:
        return None
    ordered = sorted(values)

    def pick(fraction: Decimal) -> Decimal:
        index = int((Decimal(len(ordered) - 1) * fraction).to_integral_value(rounding="ROUND_HALF_UP"))
        return ordered[index]

    return {
        "count": str(len(ordered)),
        "min": str(ordered[0]),
        "p25": str(pick(Decimal("0.25"))),
        "median": str(pick(Decimal("0.50"))),
        "p75": str(pick(Decimal("0.75"))),
        "max": str(ordered[-1]),
    }


def _terminal_funnel(datasets, config: GapPullbackConfig) -> dict[str, object]:
    reason_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    stage_reason_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, object]]] = defaultdict(list)
    feature_values: dict[str, list[Decimal]] = defaultdict(list)
    evaluated = 0

    for dataset in datasets:
        for candidate in dataset.universe.candidates:
            source_bars = dataset.bars_by_instrument.get(candidate.instrument_id, ())
            bars = [
                bar
                for bar in source_bars
                if bar.end_time.astimezone(_ET).time() <= config.last_entry_et
            ]
            result = evaluate_gap_pullback_v2(candidate, bars, config)
            deepest = _deepest_stage(result.transitions)
            reason_counts[result.reason_code] += 1
            stage_counts[deepest] += 1
            stage_reason_counts[f"{deepest}:{result.reason_code}"] += 1
            evaluated += 1

            for name in (
                "pullback_depth_pct",
                "l1_to_b1_minutes",
                "second_pullback_depth_pct",
                "l2_to_signal_minutes",
                "tod_rvol",
            ):
                raw = getattr(result.features, name)
                if raw is not None:
                    feature_values[name].append(Decimal(str(raw)))

            if len(examples[result.reason_code]) < 4:
                examples[result.reason_code].append(
                    {
                        "session_date": dataset.session_date.isoformat(),
                        "instrument_id": candidate.instrument_id,
                        "deepest_stage": deepest,
                        "gap_pct": str(candidate.gap_pct),
                        "premarket_dollar_volume": str(candidate.premarket_dollar_volume),
                        "tod_rvol": None if candidate.tod_rvol is None else str(candidate.tod_rvol),
                        "pullback_depth_pct": _feature_value(result, "pullback_depth_pct"),
                        "l1_to_b1_minutes": _feature_value(result, "l1_to_b1_minutes"),
                        "second_pullback_depth_pct": _feature_value(result, "second_pullback_depth_pct"),
                        "l2_to_signal_minutes": _feature_value(result, "l2_to_signal_minutes"),
                    }
                )

    return {
        "candidate_count": evaluated,
        "reason_counts": dict(reason_counts.most_common()),
        "deepest_stage_counts": {
            stage: stage_counts.get(stage, 0) for stage in _STAGE_ORDER if stage_counts.get(stage, 0)
        },
        "stage_reason_counts": dict(stage_reason_counts.most_common()),
        "feature_distributions": {
            name: _distribution(values) for name, values in sorted(feature_values.items())
        },
        "examples_by_reason": dict(examples),
    }


def _probe_family() -> list[tuple[str, dict[str, object]]]:
    # Hypothesis-driven single-axis probes only. These are diagnostics for a
    # future successor and never alter the frozen prospective V2 fingerprint.
    return [
        ("frozen_v2_baseline", {}),
        ("recovery_7_5", {"v2_recovery_min_pct": Decimal("7.5")}),
        ("recovery_10", {"v2_recovery_min_pct": Decimal("10")}),
        ("recovery_12_5", {"v2_recovery_min_pct": Decimal("12.5")}),
        ("recovery_15", {"v2_recovery_min_pct": Decimal("15")}),
        ("l1_depth_min_5", {"pullback_min_pct": Decimal("5")}),
        ("l1_depth_min_6", {"pullback_min_pct": Decimal("6")}),
        ("l1_depth_min_10", {"pullback_min_pct": Decimal("10")}),
        ("l1_depth_max_20", {"pullback_max_pct": Decimal("20")}),
        ("l1_depth_max_30", {"pullback_max_pct": Decimal("30")}),
        ("l1_depth_max_35", {"pullback_max_pct": Decimal("35")}),
        ("base_min_2m", {"v2_minimum_l1_to_b1_minutes": 2}),
        ("base_min_3m", {"v2_minimum_l1_to_b1_minutes": 3}),
        ("base_min_5m", {"v2_minimum_l1_to_b1_minutes": 5}),
        ("base_min_6m", {"v2_minimum_l1_to_b1_minutes": 6}),
        ("higher_low_buffer_0", {"higher_low_buffer_bps": Decimal("0")}),
        ("higher_low_buffer_25", {"higher_low_buffer_bps": Decimal("25")}),
        ("higher_low_buffer_75", {"higher_low_buffer_bps": Decimal("75")}),
        ("second_pullback_1", {"v2_second_pullback_min_pct": Decimal("1")}),
        ("l2_signal_12m", {"v2_maximum_l2_to_signal_minutes": 12}),
        ("l2_signal_15m", {"v2_maximum_l2_to_signal_minutes": 15}),
    ]


def main() -> int:
    args = _args()
    start = date.fromisoformat(args.development_start)
    end = date.fromisoformat(args.development_end)
    spread = Decimal(args.assumed_spread_bps)
    initial_cash = Decimal(args.initial_cash)

    basis_strategy = strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000"))
    namespace, basis = _cache_namespace(basis_strategy, spread)
    cache = Path(args.dataset_cache_dir) / namespace
    datasets, coverage = _load_block(cache, start, end)

    requested = int(coverage["requested_sessions"])
    covered = int(coverage["covered_sessions"])
    required = max(
        args.minimum_covered_sessions,
        int((Decimal(requested) * Decimal(args.minimum_coverage_ratio)).to_integral_value(rounding="ROUND_CEILING")),
    )
    if covered < required:
        raise SystemExit(
            f"development cache coverage {covered}/{requested} is below required {required}; "
            "this diagnostic is cache-only and will not call a provider"
        )

    frozen = frozen_v2_config()
    funnel = _terminal_funnel(datasets, frozen)
    probes: list[dict[str, object]] = []
    for probe_id, updates in _probe_family():
        config = frozen.model_copy(update=updates)
        metrics = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
        probes.append(
            {
                "probe_id": probe_id,
                "updates": {key: str(value) for key, value in updates.items()},
                **metrics,
            }
        )

    probes.sort(
        key=lambda row: (
            -int(row["trade_count"]),
            -Decimal(str(row["expectancy_r"])) if row["expectancy_r"] is not None else Decimal("Infinity"),
            str(row["probe_id"]),
        )
    )
    output = {
        "purpose": "development-only rejection funnel and single-axis geometry diagnostics for a future post-V2 successor",
        "frozen_v2_untouched": True,
        "frozen_v2_profile_fingerprint": v2_profile_fingerprint(frozen),
        "period": [start.isoformat(), end.isoformat()],
        "cache_namespace": namespace,
        "cache_basis": basis,
        "coverage": coverage,
        "funnel": funnel,
        "probes": probes,
        "guardrail": "March holdout is not loaded or evaluated by this script.",
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# V2 cached geometry diagnostic",
        "",
        f"- Development period: {start} through {end}",
        f"- Coverage: {covered}/{requested} sessions (required >= {required})",
        f"- Frozen V2 fingerprint: `{output['frozen_v2_profile_fingerprint']}`",
        "- Provider calls: **none**; cache miss fails closed.",
        "- March holdout: **not evaluated**.",
        "",
        "## Frozen V2 terminal funnel",
        "",
        "| Deepest stage | Candidates |",
        "|---|---:|",
    ]
    for stage, count in funnel["deepest_stage_counts"].items():
        lines.append(f"| {stage} | {count} |")
    lines.extend(["", "### Top terminal reasons", "", "| Reason | Candidates |", "|---|---:|"])
    for reason, count in list(funnel["reason_counts"].items())[:15]:
        lines.append(f"| {reason} | {count} |")
    lines.extend(
        [
            "",
            "## Single-axis development probes",
            "",
            "| Probe | Trades | Triggers | Expectancy R | 90% LCB R | P&L |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in probes:
        lines.append(
            f"| {row['probe_id']} | {row['trade_count']} | {row['trigger_count']} | "
            f"{row['expectancy_r'] or 'N/A'} | {row['one_sided_90_lcb_r'] or 'N/A'} | {row['pnl']} |"
        )
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "This is diagnostic development evidence only. No probe changes the frozen 2.0.0 prospective profile, and no March result is inspected here.",
        ]
    )
    summary = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
