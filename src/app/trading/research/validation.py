from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .contracts import ResearchValidationReport, ValidationFeatureResult, fingerprint

_FEATURES = (
    "primary_catalyst_confirmed",
    "catalyst_same_day",
    "immediate_supply_risk",
    "unresolved_supply",
    "source_authority_sufficient",
)
_NEGATIVE_FEATURES = {"immediate_supply_risk", "unresolved_supply"}
_EXACT_MARKET = {"captured", "captured_point_in_time", "exact", "paper-execution-v2"}
_EXACT_RESEARCH = {"captured_exact", "exact"}


def _r(row: dict[str, Any]) -> Decimal | None:
    value = row.get("r_result")
    return Decimal(str(value)) if value is not None else None


def _mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _variance(values: list[Decimal]) -> float | None:
    if len(values) < 2:
        return None
    floats = [float(value) for value in values]
    mean = sum(floats) / len(floats)
    return sum((value - mean) ** 2 for value in floats) / (len(floats) - 1)


def _groups(rows: list[dict[str, Any]], key: str) -> tuple[list[Decimal], list[Decimal]]:
    yes = [_r(row) for row in rows if (row.get("features") or {}).get(key) is True]
    no = [_r(row) for row in rows if (row.get("features") or {}).get(key) is False]
    return ([value for value in yes if value is not None], [value for value in no if value is not None])


def _effect(rows: list[dict[str, Any]], key: str) -> Decimal | None:
    yes, no = _groups(rows, key)
    if not yes or not no:
        return None
    raw = (_mean(yes) or Decimal("0")) - (_mean(no) or Decimal("0"))
    return -raw if key in _NEGATIVE_FEATURES else raw


def _confidence_interval(rows: list[dict[str, Any]], key: str) -> tuple[Decimal | None, Decimal | None]:
    yes, no = _groups(rows, key)
    if len(yes) < 2 or len(no) < 2:
        return None, None
    yes_var = _variance(yes)
    no_var = _variance(no)
    if yes_var is None or no_var is None:
        return None, None
    effect = _effect(rows, key)
    if effect is None:
        return None, None
    se = math.sqrt(yes_var / len(yes) + no_var / len(no))
    margin = Decimal(str(1.96 * se))
    return effect - margin, effect + margin


def _two_r_probability_delta(rows: list[dict[str, Any]], key: str) -> Decimal | None:
    yes = [
        bool(row.get("two_r_before_minus_one_r"))
        for row in rows
        if (row.get("features") or {}).get(key) is True
        and row.get("two_r_before_minus_one_r") is not None
    ]
    no = [
        bool(row.get("two_r_before_minus_one_r"))
        for row in rows
        if (row.get("features") or {}).get(key) is False
        and row.get("two_r_before_minus_one_r") is not None
    ]
    if not yes or not no:
        return None
    raw = Decimal(sum(yes)) / Decimal(len(yes)) - Decimal(sum(no)) / Decimal(len(no))
    return -raw if key in _NEGATIVE_FEATURES else raw


def _symbol_stability(rows: list[dict[str, Any]], key: str) -> tuple[int, int]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row.get("instrument_id") or "")
        if symbol:
            by_symbol.setdefault(symbol, []).append(row)
    usable = 0
    positive = 0
    for values in by_symbol.values():
        effect = _effect(values, key)
        if effect is None:
            continue
        usable += 1
        positive += int(effect > 0)
    return positive, usable


def build_validation_report(
    outcomes: list[dict[str, Any]],
    *,
    policy_version: str = "trading-research-1",
    minimum_sample: int = 100,
    minimum_exact_sample: int = 50,
) -> ResearchValidationReport:
    """Produce HTR-14 evidence without granting execution authority.

    The newest ~30% of the chronological dataset is held out. Effect direction is
    normalized so positive values always mean the feature/policy relationship is
    favorable (e.g. *absence* of immediate supply risk). Confidence intervals are
    approximate 95% independent-sample intervals and are reported as uncertainty,
    not as proof of causality.
    """
    chronological = sorted(
        outcomes,
        key=lambda row: (str(row.get("session_date") or ""), str(row.get("outcome_id") or "")),
    )
    cut = max(1, int(len(chronological) * 0.7)) if chronological else 0
    train = chronological[:cut]
    test = chronological[cut:]
    exact = [
        row for row in outcomes
        if row.get("market_fidelity") in _EXACT_MARKET
        and row.get("research_fidelity") in _EXACT_RESEARCH
    ]
    results: list[ValidationFeatureResult] = []
    for key in _FEATURES:
        ins = _effect(train, key)
        outs = _effect(test, key)
        exact_effect = _effect(exact, key)
        ci_low, ci_high = _confidence_interval(outcomes, key)
        two_r_delta = _two_r_probability_delta(outcomes, key)
        n = sum(1 for row in outcomes if key in (row.get("features") or {}))
        exact_n = sum(1 for row in exact if key in (row.get("features") or {}))
        positive_symbols, usable_symbols = _symbol_stability(exact, key)

        recommendation = "observe_only"
        reasons: list[str] = []
        if n < minimum_sample:
            reasons.append(f"sample {n} < required {minimum_sample}")
        if exact_n < minimum_exact_sample:
            reasons.append(f"exact sample {exact_n} < required {minimum_exact_sample}")
        if ins is None or outs is None:
            reasons.append("insufficient true/false observations in chronological train/holdout")
        elif ins <= Decimal("0.10") or outs <= Decimal("0.10"):
            reasons.append("expectancy effect is not >0.10R in both train and holdout")
        if exact_effect is None or exact_effect <= Decimal("0"):
            reasons.append("effect is not positive in the exact/captured subset")
        if ci_low is None:
            reasons.append("95% uncertainty interval unavailable")
        elif ci_low <= Decimal("0"):
            reasons.append("95% uncertainty interval crosses zero")
        if two_r_delta is None:
            reasons.append("2R-before--1R probability delta unavailable")
        elif two_r_delta <= Decimal("0"):
            reasons.append("2R-before--1R probability does not improve")
        if usable_symbols >= 3 and positive_symbols / usable_symbols < 0.6:
            reasons.append(f"symbol stability weak: {positive_symbols}/{usable_symbols} positive")

        if (
            n >= minimum_sample
            and exact_n >= minimum_exact_sample
            and ins is not None and outs is not None
            and ins > Decimal("0.10") and outs > Decimal("0.10")
            and exact_effect is not None and exact_effect > Decimal("0")
            and ci_low is not None and ci_low > Decimal("0")
            and two_r_delta is not None and two_r_delta > Decimal("0")
            and (usable_symbols < 3 or positive_symbols / usable_symbols >= 0.6)
        ):
            recommendation = "score_only"
            reasons = [
                "positive chronological in/out-of-sample expectancy",
                "positive exact/captured subset effect",
                "95% uncertainty interval above zero",
                "positive 2R-before--1R probability delta",
                f"symbol stability {positive_symbols}/{usable_symbols}" if usable_symbols else "symbol stability not yet estimable",
            ]

        results.append(ValidationFeatureResult(
            feature=key,
            sample_size=n,
            exact_sample_size=exact_n,
            in_sample_effect_r=ins,
            out_of_sample_effect_r=outs,
            win_probability_delta=two_r_delta,
            confidence_interval_low=ci_low,
            confidence_interval_high=ci_high,
            recommendation=recommendation,
            reason="; ".join(reasons) or "observe only",
        ))

    # HTR-14 is analysis-only. It can recommend score_only but can never create a
    # promotion artifact with execution authority. That requires explicit review.
    promotion = False
    generated = datetime.now(timezone.utc)
    payload = {
        "policy": policy_version,
        "sample": len(outcomes),
        "exact": len(exact),
        "results": [item.model_dump(mode="json") for item in results],
        "promotion": promotion,
    }
    fp = fingerprint(payload)
    return ResearchValidationReport(
        validation_id=f"rval-{hashlib.sha256(fp.encode()).hexdigest()[:24]}",
        policy_version=policy_version,
        generated_at=generated,
        sample_size=len(outcomes),
        exact_sample_size=len(exact),
        feature_results=tuple(results),
        promotion_allowed=promotion,
        notes=(
            "Automatic HTR-14 analysis cannot grant execution authority; explicit reviewed promotion is required.",
            "R outcomes use the backtest/paper execution models already applied by the originating run; no raw-price hindsight labels are injected.",
            "Chronological holdout, exact/captured subset, 2R probability, approximate 95% uncertainty, and per-symbol direction are evaluated where data exists.",
        ),
        immutable_fingerprint=fp,
    )
