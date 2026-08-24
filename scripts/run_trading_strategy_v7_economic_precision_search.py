from __future__ import annotations

"""Bounded V7 search using the directly economic +1R-before--1R label.

Search is intentionally limited to one- and two-predicate rules over causal
features visible at the frozen V3 watch signal. 2025 H1 is derivation; 2025 H2
and 2026 Q1 are mandatory internal temporal checks. Only temporally stable rules
are replayed through realistic paper execution. Mar/Apr 2026 remains reserved
for a separate one-shot holdout.
"""

import argparse
import itertools
import json
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

import app.trading.strategy_backtest as strategy_backtest
from app.trading.strategies.gap_pullback import _ET, _regular_bars
from app.trading.strategies.models import GapPullbackConfig, GapPullbackResult
from app.trading.strategy_v2_qualification import frozen_v2_config
from scripts.run_trading_strategy_backtest import strict_v11_strategy
from scripts.run_trading_strategy_liquidity_sweep import _cache_namespace
from scripts.run_trading_strategy_v2_extended_exploration import _load_block, _run_variant
import scripts.run_trading_strategy_v5_recovery_headroom as v5
import scripts.run_trading_strategy_v6_micro_acceptance as v6
import scripts.run_trading_strategy_v7_economic_label_census as census


@dataclass(frozen=True)
class Predicate:
    name: str
    feature: str
    op: str
    threshold: Decimal

    def matches(self, row: dict) -> bool:
        raw = row["features"].get(self.feature)
        if raw is None:
            return False
        value = Decimal(raw)
        if self.op == ">=":
            return value >= self.threshold
        if self.op == "<=":
            return value <= self.threshold
        raise ValueError(self.op)

    def matches_features(self, features: dict[str, Decimal | None]) -> bool:
        value = features.get(self.feature)
        if value is None:
            return False
        if self.op == ">=":
            return value >= self.threshold
        if self.op == "<=":
            return value <= self.threshold
        raise ValueError(self.op)

    def as_dict(self):
        return {"name": self.name, "feature": self.feature, "op": self.op, "threshold": str(self.threshold)}


_PREDICATES = tuple(
    [Predicate(f"vwap<={x}", "vwap_distance_pct", "<=", Decimal(str(x))) for x in (8, 10, 12)]
    + [Predicate(f"time<={x}", "minutes_since_open", "<=", Decimal(str(x))) for x in (30, 45, 60)]
    + [Predicate(f"vol5<={x}", "volume_ratio5", "<=", Decimal(str(x))) for x in (2.5, 3, 4)]
    + [Predicate(f"retrace<={x}", "retracement_pct", "<=", Decimal(str(x))) for x in (100, 110, 120)]
    + [Predicate(f"open_head>={x}", "opening_high_headroom_r", ">=", Decimal(str(x))) for x in (0, 0.25, 0.5)]
    + [Predicate(f"mom3>={x}", "recent_3bar_return_pct", ">=", Decimal(str(x))) for x in (5, 8, 10)]
    + [Predicate(f"tod_rvol>={x}", "tod_rvol", ">=", Decimal(str(x))) for x in (25, 50, 75, 100)]
)


def _args():
    p = argparse.ArgumentParser(description="V7 bounded economic precision search.")
    p.add_argument("--mode", choices=("development", "holdout"), required=True)
    p.add_argument("--dataset-cache-dir", default=".cache/trading-liquidity-datasets")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--initial-cash", default="100000")
    p.add_argument("--assumed-spread-bps", default="150")
    p.add_argument("--selector-source", default="/tmp/recovery_selector.py")
    p.add_argument("--selection-file", default="")
    p.add_argument("--rule-json", default="")
    p.add_argument("--minimum-coverage-ratio", default="0.98")
    p.add_argument("--minimum-covered-sessions", type=int, default=300)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def _segment(row):
    d = date.fromisoformat(row["session_date"])
    if d <= date(2025, 6, 30):
        return "2025_H1"
    if d <= date(2025, 12, 31):
        return "2025_H2"
    return "2026_Q1"


def _rule_key(rule):
    return " & ".join(p.name for p in rule)


def _binary_stats(rows, rule, segment=None):
    selected = [
        row for row in rows
        if (segment is None or _segment(row) == segment) and all(p.matches(row) for p in rule)
    ]
    wins = sum(bool(row["economic_label_1r_before_stop_60m"]) for row in selected)
    return {
        "signals": len(selected),
        "wins": wins,
        "win_rate": wins / len(selected) if selected else None,
    }


def _temporal_gate(stats):
    h1, h2, q1, full = stats["2025_H1"], stats["2025_H2"], stats["2026_Q1"], stats["full"]
    return (
        h1["signals"] >= 8 and (h1["win_rate"] or 0) >= 0.75
        and h2["signals"] >= 8 and (h2["win_rate"] or 0) >= 0.70
        and q1["signals"] >= 5 and (q1["win_rate"] or 0) >= 0.60
        and full["signals"] >= 25 and (full["win_rate"] or 0) >= 0.70
    )


def _signal_features(result: GapPullbackResult, regular, config: GapPullbackConfig):
    if len(regular) < 6:
        return None
    opening_high, trough = census._opening_geometry(regular)
    if opening_high is None or trough is None or trough <= 0 or opening_high <= trough:
        return None
    current = regular[-1]
    prior5 = regular[-5:]
    stop = min(bar.low for bar in prior5) * (Decimal("1") - config.stop_buffer_bps / Decimal("10000"))
    risk = current.close - stop
    if risk <= 0:
        return None
    prior_volumes = [bar.volume for bar in regular[-6:-1]]
    volume_ratio5 = current.volume / (sum(prior_volumes) / Decimal(len(prior_volumes))) if sum(prior_volumes) > 0 else None
    recent_3bar_return_pct = (current.close / regular[-4].close - Decimal("1")) * Decimal("100") if regular[-4].close > 0 else None
    return {
        "vwap_distance_pct": None if result.features.vwap_distance_pct is None else Decimal(result.features.vwap_distance_pct),
        "minutes_since_open": None if result.features.minutes_since_open is None else Decimal(result.features.minutes_since_open),
        "volume_ratio5": volume_ratio5,
        "retracement_pct": (current.close - trough) / (opening_high - trough) * Decimal("100"),
        "opening_high_headroom_r": (opening_high - current.close) / risk,
        "recent_3bar_return_pct": recent_3bar_return_pct,
        "tod_rvol": None if result.features.tod_rvol is None else Decimal(result.features.tod_rvol),
        "entry": current.close,
        "stop": stop,
        "risk": risk,
    }


def _filtered_evaluator(module, rule) -> Callable:
    base = module._evaluator_for(v5._watch_rule(module))
    terminal: dict[tuple[str, str], GapPullbackResult] = {}

    def evaluate(candidate, bars, config: GapPullbackConfig):
        regular = list(_regular_bars(bars))
        if not regular:
            return base(candidate, bars, config)
        key = (regular[0].end_time.astimezone(_ET).date().isoformat(), candidate.instrument_id)
        if key in terminal:
            return terminal[key]
        result = base(candidate, bars, config)
        if result.state != "entry_ready" or result.signal is None:
            return result
        features = _signal_features(result, regular, config)
        if features is None or not all(p.matches_features(features) for p in rule):
            rejected = v6._reject(result, regular, "V7_ECONOMIC_FILTER_FAIL")
            terminal[key] = rejected
            return rejected
        entry, stop, risk = features["entry"], features["stop"], features["risk"]
        signal = result.signal.model_copy(update={
            "entry_price": entry,
            "stop_price": stop,
            "risk_per_share": risk,
            "target_price": entry + risk,
            "reason_code": "ECONOMIC_PRECISION_V7_" + _rule_key(rule).replace(" ", "_"),
        })
        return result.model_copy(update={"signal": signal, "reason_code": signal.reason_code})

    return evaluate


def _trade_metrics(module, datasets, rule, config, initial_cash, spread):
    original_rsi = strategy_backtest.relative_strength_index
    strategy_backtest.relative_strength_index = lambda values, period: [Decimal("0")] * max(0, len(values) - int(period))
    try:
        with module._research_evaluator(_filtered_evaluator(module, rule)):
            run = _run_variant(datasets, config, initial_cash=initial_cash, spread=spread)
    finally:
        strategy_backtest.relative_strength_index = original_rsi
    return {**module._trade_metrics(run), "trades": run.get("trades")}


def _trade_gate(row):
    return (
        int(row.get("trade_count") or 0) >= 20
        and float(row.get("win_rate") or 0) >= 0.75
        and float(row.get("expectancy_r") or -999) >= 0.20
        and float(row.get("one_sided_90_lcb_r") or -999) > 0
        and float(row.get("max_drawdown_r") or 999) <= 5
    )


def _rule_from_json(payload):
    return tuple(Predicate(item["name"], item["feature"], item["op"], Decimal(item["threshold"])) for item in payload["predicates"])


def main():
    args = _args()
    start, end = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
    spread, initial_cash = Decimal(args.assumed_spread_bps), Decimal(args.initial_cash)
    namespace, cache_basis = _cache_namespace(
        strict_v11_strategy(minimum_premarket_dollar_volume=Decimal("100000")), spread
    )
    datasets, coverage = _load_block(Path(args.dataset_cache_dir) / namespace, start, end)
    requested, covered = int(coverage["requested_sessions"]), int(coverage["covered_sessions"])
    required = max(args.minimum_covered_sessions, math.ceil(requested * float(Decimal(args.minimum_coverage_ratio))))
    if covered < required:
        raise SystemExit(f"coverage {covered}/{requested} below frozen requirement {required}")

    module = v6._load_selector(args.selector_source)
    config = frozen_v2_config().model_copy(update={"reward_multiple": Decimal("1.0")})
    common = {
        "purpose": "select causal watch-signal filters against +1R-before--1R economic outcome",
        "research_only": True,
        "production_strategy_changed": False,
        "execution_authority": False,
        "period": [start.isoformat(), end.isoformat()],
        "coverage": coverage,
        "coverage_policy": {"minimum_ratio": args.minimum_coverage_ratio, "minimum_sessions": args.minimum_covered_sessions, "required_sessions": required},
        "cache_namespace": namespace,
        "cache_basis": cache_basis,
        "watch_rule": v5._watch_rule(module).key,
        "reward_multiple": "1.0",
        "rsi_exit": "disabled",
        "max_hold_minutes": 60,
    }

    if args.mode == "development":
        base_evaluator = module._evaluator_for(v5._watch_rule(module))
        rows = []
        for dataset in datasets:
            for candidate in dataset.universe.candidates:
                bars = tuple(dataset.bars_by_instrument[candidate.instrument_id])
                item = census._row(dataset, candidate, bars, base_evaluator, config)
                if item is not None:
                    rows.append(item)

        rules = [(p,) for p in _PREDICATES]
        rules += [pair for pair in itertools.combinations(_PREDICATES, 2) if pair[0].feature != pair[1].feature]
        candidates = []
        for rule in rules:
            stats = {
                "2025_H1": _binary_stats(rows, rule, "2025_H1"),
                "2025_H2": _binary_stats(rows, rule, "2025_H2"),
                "2026_Q1": _binary_stats(rows, rule, "2026_Q1"),
                "full": _binary_stats(rows, rule, None),
            }
            # Search/derivation happens on H1; other blocks are mandatory checks.
            if stats["2025_H1"]["signals"] < 8 or (stats["2025_H1"]["win_rate"] or 0) < 0.75:
                continue
            candidates.append({
                "rule": _rule_key(rule),
                "predicates": [p.as_dict() for p in rule],
                "binary_stats": stats,
                "temporal_gate_pass": _temporal_gate(stats),
            })

        temporal = [row for row in candidates if row["temporal_gate_pass"]]
        temporal.sort(key=lambda row: (
            min(row["binary_stats"][block]["win_rate"] or 0 for block in ("2025_H1", "2025_H2", "2026_Q1")),
            row["binary_stats"]["full"]["win_rate"] or 0,
            row["binary_stats"]["full"]["signals"],
        ), reverse=True)

        realistic = []
        for candidate_row in temporal[:5]:
            rule = _rule_from_json(candidate_row)
            trade = _trade_metrics(module, datasets, rule, config, initial_cash, spread)
            realistic_row = {**candidate_row, "trade_metrics": trade, "trade_gate_pass": _trade_gate(trade)}
            realistic.append(realistic_row)

        passing = [row for row in realistic if row["trade_gate_pass"]]
        passing.sort(key=lambda row: (
            float(row["trade_metrics"].get("expectancy_r") or -999),
            float(row["trade_metrics"].get("win_rate") or 0),
            -float(row["trade_metrics"].get("max_drawdown_r") or 999),
        ), reverse=True)
        selected = passing[0] if passing else None
        if selected is not None and args.selection_file:
            Path(args.selection_file).write_text(json.dumps({
                "rule": selected["rule"],
                "predicates": selected["predicates"],
            }, indent=2) + "\n", encoding="utf-8")

        payload = {
            **common,
            "mode": "development",
            "search_contract": {
                "max_predicates": 2,
                "same_feature_duplicate_predicates": False,
                "derivation": "2025_H1 only",
                "temporal_gate": {
                    "2025_H1": ">=8 signals and >=75% wins",
                    "2025_H2": ">=8 signals and >=70% wins",
                    "2026_Q1": ">=5 signals and >=60% wins",
                    "full": ">=25 signals and >=70% wins",
                },
                "realistic_trade_gate": ">=20 trades, >=75% wins, >=+0.20R expectancy, positive 90% LCB, <=5R DD",
                "maximum_realistic_replays": 5,
            },
            "predicate_catalog": [p.as_dict() for p in _PREDICATES],
            "derivation_candidates": candidates,
            "temporal_gate_pass_count": len(temporal),
            "realistic_replays": realistic,
            "selected_for_forward_holdout": None if selected is None else {
                "rule": selected["rule"],
                "predicates": selected["predicates"],
                "trade_metrics": {k: selected["trade_metrics"].get(k) for k in ("trade_count", "win_rate", "expectancy_r", "one_sided_90_lcb_r", "max_drawdown_r")},
            },
        }
        title = "# V7 economic precision development"
        verdict = f"Selected for forward holdout: **{selected['rule'] if selected else 'NONE'}**"
    else:
        if not args.rule_json:
            raise SystemExit("--rule-json required in holdout mode")
        selected_payload = json.loads(Path(args.rule_json).read_text(encoding="utf-8"))
        rule = _rule_from_json(selected_payload)
        trade = _trade_metrics(module, datasets, rule, config, initial_cash, spread)
        count, win, exp, dd = int(trade.get("trade_count") or 0), float(trade.get("win_rate") or 0), float(trade.get("expectancy_r") or -999), float(trade.get("max_drawdown_r") or 999)
        if count < 5:
            verdict_code = "UNDERPOWERED"
        elif win >= 0.75 and exp >= 0.20 and dd <= 3:
            verdict_code = "GOLD"
        elif win >= 0.60 and exp > 0 and dd <= 5:
            verdict_code = "ROBUST"
        else:
            verdict_code = "FAIL"
        payload = {**common, "mode": "one_shot_holdout", "no_parameter_search": True, "rule": _rule_key(rule), "predicates": [p.as_dict() for p in rule], "trade_metrics": trade, "holdout_verdict": verdict_code}
        title = "# V7 economic precision one-shot holdout"
        verdict = f"Holdout verdict: **{verdict_code}**"

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    lines = [title, "", f"- Period: **{start} through {end}**", f"- Coverage: **{covered}/{requested}**", "- Production strategy changed: **no**", "- Execution authority: **false**", ""]
    if args.mode == "development":
        lines.extend([
            f"- Derivation candidates clearing H1 gate: **{len(candidates)}**",
            f"- Rules clearing all temporal binary gates: **{len(temporal)}**",
            f"- Realistic replays: **{len(realistic)}**",
            "",
        ])
        if realistic:
            lines.extend(["| Rule | Trades | Win rate | Exp R | 90% LCB R | Max DD R | Trade gate |", "|---|---:|---:|---:|---:|---:|---:|"])
            for row in realistic:
                t = row["trade_metrics"]
                lines.append(f"| {row['rule']} | {t.get('trade_count')} | {t.get('win_rate')} | {t.get('expectancy_r')} | {t.get('one_sided_90_lcb_r')} | {t.get('max_drawdown_r')} | {row['trade_gate_pass']} |")
            lines.append("")
    else:
        t = payload["trade_metrics"]
        lines.extend([f"- Rule: **{payload['rule']}**", f"- Trades: **{t.get('trade_count')}**", f"- Win rate: **{t.get('win_rate')}**", f"- Expectancy: **{t.get('expectancy_r')}R**", f"- 90% LCB: **{t.get('one_sided_90_lcb_r')}R**", f"- Max drawdown: **{t.get('max_drawdown_r')}R**", ""])
    lines.extend([verdict, ""])
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
