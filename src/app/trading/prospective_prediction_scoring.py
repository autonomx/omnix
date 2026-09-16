from __future__ import annotations

"""Formal 5-minute scoring entry point for the scheduled prediction experiment."""

from typing import Sequence

from .models import AdjustmentMode, MarketBar
from .prospective_prediction_evidence import (
    AnalysisSessionPrices,
    OutcomeMeasurementsV1,
    VersionedOutcomeLabels,
    build_outcome_measurements,
    derive_outcome_labels,
)

FORMAL_OUTCOME_BAR_INTERVAL = "5m"


def build_formal_outcome_measurements(
    *,
    prices: AnalysisSessionPrices,
    bars: Sequence[MarketBar],
) -> OutcomeMeasurementsV1:
    """Build formal v1 outcomes from finalized RAW regular-session 5m bars only.

    The lower-level measurement function is intentionally reusable, but the
    scheduled prediction experiment has an immutable 5-minute label contract.
    Mixed 1m/daily bars are ignored here so they cannot silently alter the formal
    persistent-uptrend label.
    """

    five_minute = [
        bar
        for bar in bars
        if bar.interval == FORMAL_OUTCOME_BAR_INTERVAL
        and bar.is_final
        and bar.session == "regular"
        and bar.adjustment_mode == AdjustmentMode.RAW
    ]
    if not five_minute:
        raise ValueError("formal_prediction_scoring_requires_raw_final_5m_bars")
    return build_outcome_measurements(prices=prices, bars=five_minute)


def build_formal_outcome_labels(
    *,
    prices: AnalysisSessionPrices,
    bars: Sequence[MarketBar],
) -> tuple[OutcomeMeasurementsV1, VersionedOutcomeLabels]:
    measurements = build_formal_outcome_measurements(prices=prices, bars=bars)
    return measurements, derive_outcome_labels(measurements)
