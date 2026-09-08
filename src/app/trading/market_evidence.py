from __future__ import annotations

"""Versioned evidence contracts for prospective equity trading.

These models deliberately separate source membership, frozen morning evidence,
provider availability and execution authorization. Missing inputs are represented
as typed gaps; they are never converted into synthetic executable observations.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MARKET_EVIDENCE_POLICY_VERSION = "market-evidence-v2"
MIN_TOD_RVOL_BASELINE_SESSIONS = 5


class MarketEvidencePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str = MARKET_EVIDENCE_POLICY_VERSION
    discovery_source: Literal["finviz"] = "finviz"
    premarket_provider: str = "alpaca_iex"
    premarket_feed: str = "iex"
    regular_bar_primary_provider: str = "yahoo"
    shadow_bar_fallback_provider: str = "alpaca_iex"
    execution_provider: str = "alpaca_iex"
    minimum_tod_rvol_baseline_sessions: int = Field(
        default=MIN_TOD_RVOL_BASELINE_SESSIONS,
        ge=2,
    )
    frozen_spread_is_authoritative: Literal[False] = False
    live_entry_spread_is_authoritative: Literal[True] = True


DEFAULT_MARKET_EVIDENCE_POLICY = MarketEvidencePolicy()


SourceMemberStatus = Literal[
    "materialized",
    "filtered_gap",
    "filtered_price",
    "unsupported_instrument",
    "enrichment_failed",
    "provider_unavailable",
]


class SourceMemberDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, max_length=32)
    source_rank: int = Field(ge=1)
    status: SourceMemberStatus
    reason_codes: tuple[str, ...] = ()
    instrument_id: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def materialized_has_instrument(self):
        if self.status == "materialized" and not self.instrument_id:
            raise ValueError("materialized source member requires instrument_id")
        return self


class PremarketLiquidityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str = MARKET_EVIDENCE_POLICY_VERSION
    provider: str
    feed: str
    observed_at: datetime
    current_premarket_volume: Decimal = Field(ge=0)
    current_premarket_dollar_volume: Decimal = Field(ge=0)
    tod_rvol: Decimal | None = Field(default=None, ge=0)
    tod_rvol_numerator: Decimal = Field(ge=0)
    tod_rvol_denominator_mean: Decimal | None = Field(default=None, ge=0)
    baseline_session_count: int = Field(ge=0)
    premarket_bar_count: int = Field(ge=0)
    nonzero_volume_bar_count: int = Field(ge=0)
    coverage_ratio: Decimal | None = Field(default=None, ge=0)
    ready: bool
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def readiness_consistent(self):
        if self.ready and self.reason_codes:
            raise ValueError("ready premarket evidence cannot have reason_codes")
        if self.ready and self.tod_rvol is None:
            raise ValueError("ready premarket evidence requires tod_rvol")
        return self


ProviderReadinessState = Literal[
    "READY",
    "NOT_CONFIGURED",
    "AUTH_FAILED",
    "RATE_LIMITED",
    "QUOTE_MISSING",
    "CONTRACT_ERROR",
    "STALE",
    "PROVIDER_UNAVAILABLE",
    "UNKNOWN_ERROR",
]


class ProviderReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    state: ProviderReadinessState
    ready: bool
    observed_at: datetime
    error_type: str | None = None
    detail: str | None = None


class ExecutionInputGap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    binding_id: str | None = None
    provider: str
    readiness: ProviderReadiness
    reason_code: str
    observed_at: datetime
    execution_authority: Literal[False] = False


class BarCoverageAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str | None = None
    provider: str | None = None
    fallback_provider: str | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    expected_latest_bar: datetime | None = None
    actual_latest_bar: datetime | None = None
    missing_minutes: tuple[datetime, ...] = ()
    latency_seconds: Decimal | None = Field(default=None, ge=0)
    opening_bar_present: bool = False
    latest_bar_present: bool = False
    contiguous: bool = False
    ready: bool = False
    reason_codes: tuple[str, ...] = ()


SessionEvaluabilityStatus = Literal[
    "complete",
    "completed_no_trigger",
    "zero_candidate_scan",
    "partial_data",
    "not_evaluable_data",
    "provider_unavailable",
]


class SessionEvaluabilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SessionEvaluabilityStatus
    source_member_count: int = Field(ge=0)
    accounted_source_member_count: int = Field(ge=0)
    materialized_candidate_count: int = Field(ge=0)
    evaluable_candidate_count: int = Field(ge=0)
    unevaluable_candidate_count: int = Field(ge=0)
    source_failure_count: int = Field(ge=0)
    reason_codes: tuple[str, ...] = ()
    qualification_eligible: bool = False


class TradeAuthorizationAssessment(BaseModel):
    """Final fail-closed gate immediately in front of a strategy entry order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["trade-authorization-v1"] = "trade-authorization-v1"
    strategy_id: str
    instrument_id: str
    trade_attempt_id: str
    universe_id: str
    strategy_profile_fingerprint: str
    market_evidence_policy_version: str
    source_member_valid: bool
    morning_evidence_eligible: bool
    bar_coverage_ready: bool
    strategy_entry_ready: bool
    execution_observation_present: bool
    execution_eligible: bool
    risk_sizing_valid: bool
    session_open: bool
    provider_ready: bool
    strategy_kill_switch_clear: bool
    qualification_authorized: bool
    profile_matches: bool
    evidence_policy_matches: bool
    reason_codes: tuple[str, ...] = ()
    authorized: bool

    @model_validator(mode="after")
    def authorization_is_conjunction(self):
        required = (
            self.source_member_valid,
            self.morning_evidence_eligible,
            self.bar_coverage_ready,
            self.strategy_entry_ready,
            self.execution_observation_present,
            self.execution_eligible,
            self.risk_sizing_valid,
            self.session_open,
            self.provider_ready,
            self.strategy_kill_switch_clear,
            self.qualification_authorized,
            self.profile_matches,
            self.evidence_policy_matches,
        )
        if self.authorized != all(required):
            raise ValueError("authorized must equal conjunction of authority predicates")
        if self.authorized and self.reason_codes:
            raise ValueError("authorized assessment cannot contain reason_codes")
        return self


def classify_provider_exception(
    exc: BaseException,
    *,
    provider: str,
    observed_at: datetime,
) -> ProviderReadiness:
    """Classify an unavailable provider input without manufacturing an observation."""

    text = str(exc or "")
    lower = text.casefold()
    error_type = type(exc).__name__
    if "not configured" in lower or "credentials are not configured" in lower:
        state: ProviderReadinessState = "NOT_CONFIGURED"
    elif "401" in lower or "403" in lower or "unauthorized" in lower or "forbidden" in lower:
        state = "AUTH_FAILED"
    elif "429" in lower or "rate limit" in lower or "too many requests" in lower:
        state = "RATE_LIMITED"
    elif "no latest quote" in lower or "no latest trade" in lower or "quote" in lower and "missing" in lower:
        state = "QUOTE_MISSING"
    elif "contract" in error_type.casefold() or "malformed" in lower or "invalid" in lower:
        state = "CONTRACT_ERROR"
    elif "stale" in lower:
        state = "STALE"
    elif isinstance(exc, (ConnectionError, TimeoutError, OSError)) or "unavailable" in lower or "timeout" in lower:
        state = "PROVIDER_UNAVAILABLE"
    else:
        state = "UNKNOWN_ERROR"
    return ProviderReadiness(
        provider=provider,
        state=state,
        ready=False,
        observed_at=observed_at,
        error_type=error_type,
        detail=text,
    )


__all__ = [
    "BarCoverageAssessment",
    "DEFAULT_MARKET_EVIDENCE_POLICY",
    "ExecutionInputGap",
    "MARKET_EVIDENCE_POLICY_VERSION",
    "MIN_TOD_RVOL_BASELINE_SESSIONS",
    "MarketEvidencePolicy",
    "PremarketLiquidityEvidence",
    "ProviderReadiness",
    "SessionEvaluabilityAssessment",
    "SourceMemberDisposition",
    "TradeAuthorizationAssessment",
    "classify_provider_exception",
]
