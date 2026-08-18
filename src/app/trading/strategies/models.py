from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


StrategyMode = Literal["off", "shadow", "auto_paper"]
GapPullbackState = Literal[
    "discovered",
    "qualified_gap",
    "opening_impulse",
    "first_pullback",
    "first_low_confirmed",
    "bounce_high_confirmed",
    "second_pullback",
    "higher_low_confirmed",
    "vwap_reclaim",
    "lower_high_break",
    "breakout_hold",
    "entry_ready",
    "rejected",
    "expired",
]
FloatPreferenceMode = Literal["ignore", "score", "require"]


class StrategyRiskProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_per_trade_pct: Decimal = Field(default=Decimal("0.35"), gt=0, le=5)
    max_daily_loss_pct: Decimal = Field(default=Decimal("1.5"), gt=0, le=20)
    max_open_risk_pct: Decimal = Field(default=Decimal("1.0"), gt=0, le=20)
    max_positions: int = Field(default=3, ge=1, le=50)
    max_trades_per_day: int = Field(default=5, ge=1, le=100)
    max_trade_value: Decimal = Field(default=Decimal("25000"), gt=0)
    one_trade_per_symbol_per_day: bool = True
    max_spread_bps: Decimal = Field(default=Decimal("150"), gt=0, le=10_000)
    entry_start_et: time = time(9, 35)
    last_entry_et: time = time(11, 30)
    force_flat_et: time = time(15, 55)
    kill_switch: bool = False


class GapPullbackConfig(BaseModel):
    """Fully configurable deterministic definition for gap_pullback_v1.

    LLM/model research may annotate candidates, but these fields remain the
    complete execution-authorizing contract for AUTO PAPER.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: Literal["gap_pullback_v1"] = "gap_pullback_v1"
    strategy_version: Literal["1.0.0", "1.1.0"] = "1.1.0"

    # Phase 1: discovery / liquidity
    minimum_gap_pct: Decimal = Field(default=Decimal("20"), ge=0)
    minimum_price: Decimal = Field(default=Decimal("0.50"), gt=0)
    maximum_price: Decimal = Field(default=Decimal("20"), gt=0)
    minimum_premarket_dollar_volume: Decimal = Field(default=Decimal("10000000"), ge=0)
    minimum_tod_rvol: Decimal = Field(default=Decimal("5"), ge=0)
    maximum_spread_bps: Decimal = Field(default=Decimal("150"), gt=0)
    preferred_float_min_shares: Decimal = Field(default=Decimal("2000000"), gt=0)
    preferred_float_max_shares: Decimal = Field(default=Decimal("30000000"), gt=0)
    float_preference_mode: FloatPreferenceMode = "score"

    # Phase 2: research / supply evidence
    require_catalyst_evidence: bool = True
    reject_dilution_flags: tuple[str, ...] = (
        "registered_offering",
        "atm",
        "warrants",
        "convertible",
        "equity_line",
    )

    # Phase 3: deterministic failed-selloff structure
    opening_impulse_min_pct: Decimal = Field(default=Decimal("8"), ge=0)
    pullback_min_pct: Decimal = Field(default=Decimal("15"), ge=0)
    pullback_max_pct: Decimal = Field(default=Decimal("55"), gt=0)
    pullback_volume_max_ratio: Decimal = Field(default=Decimal("0.70"), ge=0, le=5)
    higher_low_buffer_bps: Decimal = Field(default=Decimal("20"), ge=0)
    breakout_volume_ratio: Decimal = Field(default=Decimal("1.25"), gt=0)
    pivot_left_bars: int = Field(default=2, ge=1, le=10)
    pivot_right_bars: int = Field(default=2, ge=1, le=10)
    volume_lookback_bars: int = Field(default=10, ge=2, le=100)

    # Phase 4: breakout quality / daily selection
    require_breakout_hold: bool = True
    breakout_hold_bars: int = Field(default=1, ge=1, le=5)
    breakout_hold_tolerance_bps: Decimal = Field(default=Decimal("25"), ge=0, le=1000)
    minimum_quality_score: int = Field(default=7, ge=0, le=10)

    # Phase 5: execution / protection
    stop_buffer_bps: Decimal = Field(default=Decimal("15"), ge=0)
    reward_multiple: Decimal = Field(default=Decimal("2"), gt=0, le=10)
    entry_start_et: time = time(9, 35)
    last_entry_et: time = time(11, 30)

    @model_validator(mode="after")
    def validate_range(self):
        if self.maximum_price <= self.minimum_price:
            raise ValueError("maximum_price must exceed minimum_price")
        if self.pullback_max_pct <= self.pullback_min_pct:
            raise ValueError("pullback_max_pct must exceed pullback_min_pct")
        if self.preferred_float_max_shares <= self.preferred_float_min_shares:
            raise ValueError("preferred_float_max_shares must exceed preferred_float_min_shares")
        return self


class GapPullbackFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gap_pct: Decimal
    opening_impulse_pct: Decimal | None = None
    pullback_depth_pct: Decimal | None = None
    impulse_average_volume: Decimal | None = None
    pullback_selling_average_volume: Decimal | None = None
    pullback_volume_ratio: Decimal | None = None
    l1: Decimal | None = None
    b1: Decimal | None = None
    l2: Decimal | None = None
    session_vwap: Decimal | None = None
    vwap_distance_pct: Decimal | None = None
    breakout_volume_ratio: Decimal | None = None
    breakout_hold_bars: int | None = None
    spread_bps: Decimal | None = None
    tod_rvol: Decimal | None = None
    float_shares: Decimal | None = None
    catalyst_evidence_count: int = 0
    dilution_flags: tuple[str, ...] = ()
    catalyst_score: int = Field(default=0, ge=0, le=2)
    supply_score: int = Field(default=0, ge=0, le=2)
    opening_structure_score: int = Field(default=0, ge=0, le=2)
    pullback_quality_score: int = Field(default=0, ge=0, le=2)
    reclaim_break_score: int = Field(default=0, ge=0, le=2)
    quality_score: int = Field(default=0, ge=0, le=10)
    minutes_since_open: int | None = None


class StrategySignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    state: GapPullbackState
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    risk_per_share: Decimal
    reason_code: str
    quality_score: int = Field(default=0, ge=0, le=10)


class GapPullbackResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    state: GapPullbackState
    reason_code: str
    features: GapPullbackFeatures
    transitions: tuple[GapPullbackState, ...]
    signal: StrategySignal | None = None
    evaluated_bar_count: int = Field(ge=0)
