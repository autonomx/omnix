from __future__ import annotations

from decimal import Decimal

from app.trading.strategy_ai_shadow_v2 import AIShadowV2AlphaDecision
from app.trading.strategy_ai_shadow_v2_hardening import (
    _OBSERVED_SPREAD_BPS,
    _risk_geometry_with_observed_spread,
)


INSTRUMENT = "equity:NASDAQ:TEST"


def _decision() -> AIShadowV2AlphaDecision:
    return AIShadowV2AlphaDecision(
        instrument_id=INSTRUMENT,
        setup_family="trend_continuation",
        state="enter",
        quality_score=80,
        invalidation_price=Decimal("9.50"),
        target_1=Decimal("11.05"),
        extension_risk="low",
        thesis_changed=True,
        thesis="Fixture continuation entry.",
    )


def test_observed_spread_replaces_worst_case_cost_without_lowering_two_r_threshold() -> None:
    fallback = _risk_geometry_with_observed_spread(
        _decision(),
        entry_reference=Decimal("10"),
        estimated_cost_bps=Decimal("160"),
        minimum_net_r=Decimal("2"),
    )
    assert fallback.valid is False
    assert fallback.estimated_cost_bps == Decimal("160")

    token = _OBSERVED_SPREAD_BPS.set({INSTRUMENT: Decimal("20")})
    try:
        observed = _risk_geometry_with_observed_spread(
            _decision(),
            entry_reference=Decimal("10"),
            estimated_cost_bps=Decimal("160"),
            minimum_net_r=Decimal("2"),
        )
    finally:
        _OBSERVED_SPREAD_BPS.reset(token)

    assert observed.estimated_cost_bps == Decimal("30")
    assert observed.net_r is not None and observed.net_r >= Decimal("2")
    assert observed.valid is True
