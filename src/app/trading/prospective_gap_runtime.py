from __future__ import annotations

"""End-to-end authority runtime for the prospective Top-10 gap experiment.

The runtime owns machine-readable persistence and phase transitions. External
schedulers may still discover/research catalysts, but they submit typed evidence
to this boundary instead of independently reconstructing forecast, confirmation,
outcome, or portfolio state in Markdown.
"""

import hashlib
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal, Sequence
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .gapper_dataset import GapperCandidate
from .prospective_gap_repository import (
    ProspectiveGapRepository,
    ProspectiveGapSessionLedger,
    default_prospective_gap_repository,
)
from .prospective_prediction_evidence import (
    BinaryForecastMetrics,
    BinaryForecastObservation,
    ConfidenceRiskFactors,
    FrozenForecast,
    FrozenPortfolio,
    PortfolioScore,
    PremarketEvidenceSnapshot,
    evaluate_binary_forecasts,
    freeze_research_portfolios,
    score_frozen_portfolio,
)
from .prospective_prediction_operational import (
    CashPreservingShadowPortfolio,
    FormalOutcomeBundle,
    OperationalConfirmationEvaluation,
    OperationalPremarketState,
    build_cash_preserving_shadow_portfolio,
    evaluate_operational_confirmation,
    load_operational_formal_outcome,
    load_operational_premarket_state,
)
from .prospective_prediction_v41 import DEFAULT_V41_SPEC
from .prospective_prediction_v42 import (
    DEFAULT_V42_SPEC,
    V42Forecast,
    V42ForecastAttempt,
    V42ReturnMetrics,
    V42ReturnObservation,
    evaluate_v42_return_metrics,
    freeze_v42_forecast,
    session_eligible_for_v42_forward_validation,
)
from .prospective_prediction_v42_action import (
    DEFAULT_V42_ACTION_POLICY,
    PortfolioF,
    V42ActionPolicy,
    V42ActionSnapshot,
    V42AuthorizationReceipt,
    V42WatchDecision,
    authorize_v42_action,
    build_portfolio_f,
    classify_v42_watch,
    evaluate_v42_post_open_action,
)
from .prospective_prediction_v4 import (
    ActionabilityDecision,
    CalibratorArtifact,
    CatalystDecomposition,
    ConfirmationState,
    ConfirmationTransitionReceipt,
    ExecutionCostInput,
    ExtensionExhaustionRisk,
    FinvizFrozenCohort,
    FrozenForecastV4,
    GrossReturnDistribution,
    MechanismRiskScores,
    PairedForecastMetrics,
    PairedForecastObservation,
    PredictionEvidenceQuality,
    RegimeTag,
    TradeAuthorizationReceipt,
    V4ForecastAttempt,
    authorize_trade,
    derive_extension_exhaustion_risk,
    evaluate_paired_v3_v4,
    extension_components_from_market_state,
    freeze_v4_forecast,
)
from .service import TradingMarketDataService, default_market_data_service
from .strategies.models import GapPullbackConfig


_ET = ZoneInfo("America/New_York")
RUNTIME_VERSION = "prospective-gap-runtime-v1"
PORTFOLIO_E_POLICY_VERSION = "prospective-gap-portfolio-e-v1"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("prospective runtime timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


class PortfolioEPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["prospective-gap-portfolio-e-v1"] = PORTFOLIO_E_POLICY_VERSION
    starting_equity: Decimal = Field(default=Decimal("1000"), gt=0)
    max_positions: int = Field(default=3, ge=1, le=10)
    max_position_fraction: Decimal = Field(default=Decimal("0.20"), gt=0, le=1)
    minimum_bullish_probability: Decimal = Field(default=Decimal("0.50"), ge=0, le=1)
    minimum_net_expected_return: Decimal = Decimal("0")
    minimum_net_q10: Decimal = Decimal("-0.10")
    estimated_entry_slippage_bps: Decimal = Field(default=Decimal("25"), ge=0)
    estimated_entry_impact_bps: Decimal = Field(default=Decimal("10"), ge=0)
    estimated_exit_slippage_bps: Decimal = Field(default=Decimal("25"), ge=0)
    estimated_exit_impact_bps: Decimal = Field(default=Decimal("10"), ge=0)
    estimated_round_trip_commission_bps: Decimal = Field(default=Decimal("0"), ge=0)


class PremarketInstrumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: GapperCandidate
    v3_forecast: FrozenForecast
    catalyst: CatalystDecomposition
    mechanisms: MechanismRiskScores
    calibrator: CalibratorArtifact
    evidence_snapshot_id: str
    evidence_snapshot: PremarketEvidenceSnapshot | None = None
    first_catalyst_at: datetime | None = None
    prior_1d_return_pct: Decimal | None = None
    prior_3d_return_pct: Decimal | None = None
    regime_tags: tuple[RegimeTag, ...] = ()
    regime_primary: RegimeTag | None = None
    regime_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    uncertainty: Literal["low", "moderate", "high"] = "high"
    economic_distribution: GrossReturnDistribution | None = None

    @field_validator("first_catalyst_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    @model_validator(mode="after")
    def instrument_alignment(self):
        if self.v3_forecast.instrument_id != self.candidate.instrument_id:
            raise ValueError("v3_forecast_candidate_instrument_mismatch")
        if self.regime_primary is not None and self.regime_primary not in self.regime_tags:
            raise ValueError("regime_primary_must_be_in_regime_tags")
        if self.evidence_snapshot is not None:
            if self.evidence_snapshot.snapshot_id != self.evidence_snapshot_id:
                raise ValueError("evidence_snapshot_id_mismatch")
            if self.evidence_snapshot.session_date != self.v3_forecast.frozen_at.astimezone(_ET).date():
                raise ValueError("evidence_snapshot_session_mismatch")
        return self


class PremarketFreezeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cohort: FinvizFrozenCohort
    frozen_at: datetime
    instruments: tuple[PremarketInstrumentInput, ...]
    risk_factors: dict[str, ConfidenceRiskFactors] = Field(default_factory=dict)
    frozen_climatology_probability: Decimal | None = Field(default=None, ge=0, le=1)
    confirmation_strategy_config: GapPullbackConfig = Field(default_factory=GapPullbackConfig)
    portfolio_e_policy: PortfolioEPolicy = Field(default_factory=PortfolioEPolicy)
    run_id: str | None = None

    @field_validator("frozen_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def causal_and_cohort_alignment(self):
        if self.frozen_at > self.cohort.discovery_cutoff_at:
            raise ValueError("premarket_runtime_freeze_after_prediction_cutoff")
        symbols = set(self.cohort.symbols)
        if len(self.instruments) != len(self.cohort.symbols):
            raise ValueError("premarket_runtime_requires_one_input_per_cohort_symbol")
        seen: set[str] = set()
        for row in self.instruments:
            instrument_id = row.candidate.instrument_id
            symbol = instrument_id.rsplit(":", 1)[-1]
            if instrument_id in seen:
                raise ValueError("duplicate_premarket_runtime_instrument")
            seen.add(instrument_id)
            if symbol not in symbols and instrument_id not in symbols:
                raise ValueError(f"candidate_not_in_frozen_cohort:{instrument_id}")
            if row.v3_forecast.frozen_at > self.cohort.discovery_cutoff_at:
                raise ValueError(f"v3_forecast_after_cutoff:{instrument_id}")
        return self


class ProspectiveSessionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_version: Literal["prospective-gap-runtime-v1"] = RUNTIME_VERSION
    session_date: date
    cohort: FinvizFrozenCohort
    frozen_at: datetime
    candidates: tuple[GapperCandidate, ...]
    confirmation_strategy_config: GapPullbackConfig
    portfolio_e_policy: PortfolioEPolicy
    frozen_climatology_probability: Decimal | None = None
    run_id: str | None = None


class V42ForecastRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    forecast: V42Forecast


class V42ComparisonMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    n: int
    brier_delta_v42_minus_v3: Decimal | None = None
    log_loss_delta_v42_minus_v3: Decimal | None = None
    accuracy_delta_v42_minus_v3: Decimal | None = None


class V4ForecastRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    forecast: FrozenForecastV4
    catalyst: CatalystDecomposition
    extension_risk: ExtensionExhaustionRisk
    calibrator: CalibratorArtifact
    economic_distribution: GrossReturnDistribution | None = None


class LegacyPortfolioBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    portfolios: tuple[FrozenPortfolio, FrozenPortfolio, FrozenPortfolio, FrozenPortfolio]


class LegacyPortfolioScoreBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scores: tuple[PortfolioScore, PortfolioScore, PortfolioScore, PortfolioScore]


class PremarketInstrumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    market_state: OperationalPremarketState
    v3_forecast: FrozenForecast
    v4_forecast: FrozenForecastV4 | None = None
    v4_failure_reason: str | None = None
    v42_forecast: V42Forecast | None = None
    v42_failure_reason: str | None = None


class PremarketFreezeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    cohort_id: str
    results: tuple[PremarketInstrumentResult, ...]
    legacy_portfolios: LegacyPortfolioBundle


class ConfirmationRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    evaluated_at: datetime
    evaluated_count: int
    new_confirmation_receipt_count: int
    new_authorization_count: int
    terminal_count: int
    portfolio_e: CashPreservingShadowPortfolio


class PortfolioEPositionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    allocation: Decimal
    reference_entry_price: Decimal
    close_price: Decimal
    raw_return: Decimal
    cost_adjusted_return: Decimal
    pnl: Decimal


class PortfolioEPerformance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_version: str
    starting_equity: Decimal
    ending_equity: Decimal
    pnl: Decimal
    return_pct: Decimal
    cash: Decimal
    position_outcomes: tuple[PortfolioEPositionOutcome, ...] = ()


class DailyProspectiveScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_version: Literal["prospective-gap-runtime-v1"] = RUNTIME_VERSION
    session_date: date
    cohort_id: str
    complete_evidence_count: int = Field(ge=0)
    degraded_evidence_count: int = Field(ge=0)
    insufficient_evidence_count: int = Field(ge=0)
    unresolved_premarket_bar_count: int = Field(ge=0)
    v3_metrics: BinaryForecastMetrics
    v4_metrics: BinaryForecastMetrics
    paired_metrics: PairedForecastMetrics
    v42_metrics: BinaryForecastMetrics = Field(
        default_factory=lambda: BinaryForecastMetrics(n=0)
    )
    v42_comparison: V42ComparisonMetrics = Field(
        default_factory=lambda: V42ComparisonMetrics(n=0)
    )
    v42_return_metrics: V42ReturnMetrics = Field(
        default_factory=lambda: V42ReturnMetrics(n=0)
    )
    legacy_portfolio_scores: LegacyPortfolioScoreBundle | None = None
    confirmation_receipt_count: int = Field(ge=0)
    confirmed_long_count: int = Field(ge=0)
    authorization_long_count: int = Field(ge=0)
    authorization_no_trade_count: int = Field(ge=0)
    portfolio_e_performance: PortfolioEPerformance | None = None


class PostcloseRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_date: date
    outcomes: tuple[FormalOutcomeBundle, ...]
    scorecard: DailyProspectiveScorecard


class ProspectiveGapRuntime:
    def __init__(
        self,
        *,
        repository: ProspectiveGapRepository | None = None,
        market_service: TradingMarketDataService | None = None,
    ) -> None:
        self.repository = repository or default_prospective_gap_repository()
        self.market_service = market_service or default_market_data_service()

    def freeze_premarket_file(self, path: str | Path) -> PremarketFreezeResult:
        """Ingest one scheduler-authored machine-readable freeze request.

        The file is only a transport envelope. The same causal validation and
        durable StrategyEvent authority used by the API applies after parsing.
        """

        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        request = PremarketFreezeRequest.model_validate(payload)
        return self.freeze_premarket(request)

    def try_freeze_scheduler_inbox(
        self,
        session_date: date,
        *,
        inbox_root: str | Path = "resources/trading/prospective_gap_inbox",
    ) -> PremarketFreezeResult | None:
        """Freeze today's scheduler handoff exactly once when it is locally visible."""

        ledger = self.repository.session(session_date)
        if ledger.latest(kind="session_manifest", instrument_id="__session__") is not None:
            return None
        path = Path(inbox_root) / f"{session_date.isoformat()}.json"
        if not path.exists():
            return None
        result = self.freeze_premarket_file(path)
        if result.session_date != session_date:
            raise ValueError("scheduler_handoff_session_date_mismatch")
        return result

    def freeze_premarket(self, request: PremarketFreezeRequest) -> PremarketFreezeResult:
        session_date = request.cohort.session_date
        manifest = ProspectiveSessionManifest(
            session_date=session_date,
            cohort=request.cohort,
            frozen_at=request.frozen_at,
            candidates=tuple(row.candidate for row in request.instruments),
            confirmation_strategy_config=request.confirmation_strategy_config,
            portfolio_e_policy=request.portfolio_e_policy,
            frozen_climatology_probability=request.frozen_climatology_probability,
            run_id=request.run_id,
        )
        self.repository.append(
            session_date=session_date,
            cohort_id=request.cohort.cohort_id,
            instrument_id="__session__",
            kind="session_manifest",
            observed_at=request.frozen_at,
            payload=manifest,
            run_id=request.run_id,
        )
        self.repository.append(
            session_date=session_date,
            cohort_id=request.cohort.cohort_id,
            instrument_id="__research_spec__",
            kind="v41_shadow_spec",
            observed_at=request.frozen_at,
            payload=DEFAULT_V41_SPEC,
            state=DEFAULT_V41_SPEC.activation_state,
            run_id=request.run_id,
            idempotency_suffix=DEFAULT_V41_SPEC.implementation_fingerprint,
        )
        self.repository.append(
            session_date=session_date,
            cohort_id=request.cohort.cohort_id,
            instrument_id="__research_spec_v42__",
            kind="v42_shadow_spec",
            observed_at=request.frozen_at,
            payload=DEFAULT_V42_SPEC,
            state=DEFAULT_V42_SPEC.activation_state,
            run_id=request.run_id,
            idempotency_suffix=DEFAULT_V42_SPEC.implementation_fingerprint,
        )

        results: list[PremarketInstrumentResult] = []
        v3_forecasts: list[FrozenForecast] = []
        for row in request.instruments:
            candidate = row.candidate
            self.repository.append(
                session_date=session_date,
                cohort_id=request.cohort.cohort_id,
                instrument_id=candidate.instrument_id,
                kind="premarket_input",
                observed_at=request.frozen_at,
                payload=row,
                run_id=request.run_id,
            )
            if row.evidence_snapshot is not None:
                self.repository.append(
                    session_date=session_date,
                    cohort_id=request.cohort.cohort_id,
                    instrument_id=candidate.instrument_id,
                    kind="premarket_evidence",
                    observed_at=row.evidence_snapshot.frozen_at,
                    payload=row.evidence_snapshot,
                    run_id=request.run_id,
                )

            state = load_operational_premarket_state(
                market_service=self.market_service,
                cohort=request.cohort,
                candidate=candidate,
                snapshot_id=f"{request.cohort.cohort_id}:{candidate.instrument_id}:market-state",
                prediction_cutoff_at=request.cohort.discovery_cutoff_at,
                frozen_at=request.frozen_at,
                first_catalyst_at=row.first_catalyst_at,
                prior_1d_return_pct=row.prior_1d_return_pct,
                prior_3d_return_pct=row.prior_3d_return_pct,
            )
            self.repository.append(
                session_date=session_date,
                cohort_id=request.cohort.cohort_id,
                instrument_id=candidate.instrument_id,
                kind="premarket_state",
                observed_at=request.frozen_at,
                payload=state,
                run_id=request.run_id,
            )
            self.repository.append(
                session_date=session_date,
                cohort_id=request.cohort.cohort_id,
                instrument_id=candidate.instrument_id,
                kind="v3_forecast",
                observed_at=row.v3_forecast.frozen_at,
                payload=row.v3_forecast,
                run_id=request.run_id,
            )
            v3_forecasts.append(row.v3_forecast)

            v4: FrozenForecastV4 | None = None
            failure: str | None = None
            extension: ExtensionExhaustionRisk | None = None
            try:
                extension = derive_extension_exhaustion_risk(
                    extension_components_from_market_state(state.market_state)
                )
                feature_fingerprint = _hash(
                    {
                        "market_state": state.market_state.live_feature_fingerprint,
                        "catalyst": row.catalyst.model_dump(mode="json"),
                        "mechanisms": row.mechanisms.model_dump(mode="json"),
                        "extension": extension.model_dump(mode="json"),
                    }
                )
                distribution = row.economic_distribution
                v4 = freeze_v4_forecast(
                    instrument_id=candidate.instrument_id,
                    session_date=session_date,
                    cohort=request.cohort,
                    evidence_snapshot_id=row.evidence_snapshot_id,
                    market_state=state.market_state,
                    evidence_quality=state.evidence_quality,
                    catalyst=row.catalyst,
                    extension_risk=extension,
                    mechanisms=row.mechanisms,
                    calibrator=row.calibrator,
                    feature_vector_fingerprint=feature_fingerprint,
                    frozen_at=request.frozen_at,
                    regime_tags=row.regime_tags,
                    regime_primary=row.regime_primary,
                    regime_confidence=row.regime_confidence,
                    uncertainty=row.uncertainty,
                    return_q10=distribution.q10 if distribution is not None else None,
                    return_q50=distribution.q50 if distribution is not None else None,
                    return_q90=distribution.q90 if distribution is not None else None,
                    p_return_gt_2pct=distribution.p_return_gt_2pct if distribution is not None else None,
                    p_return_lt_minus_5pct=distribution.p_return_lt_minus_5pct if distribution is not None else None,
                )
                self.repository.append(
                    session_date=session_date,
                    cohort_id=request.cohort.cohort_id,
                    instrument_id=candidate.instrument_id,
                    kind="v4_forecast",
                    observed_at=request.frozen_at,
                    payload=V4ForecastRecord(
                        forecast=v4,
                        catalyst=row.catalyst,
                        extension_risk=extension,
                        calibrator=row.calibrator,
                        economic_distribution=distribution,
                    ),
                    run_id=request.run_id,
                )
                attempt = V4ForecastAttempt(
                    instrument_id=candidate.instrument_id,
                    session_date=session_date,
                    attempted_at=request.frozen_at,
                    model_state="PRODUCED",
                    evidence_quality=state.evidence_quality.quality,
                    forecast_fingerprint=v4.immutable_fingerprint,
                )
            except Exception as exc:
                failure = f"{type(exc).__name__}:{exc}"
                if state.evidence_quality.quality == "INSUFFICIENT":
                    attempt = V4ForecastAttempt(
                        instrument_id=candidate.instrument_id,
                        session_date=session_date,
                        attempted_at=request.frozen_at,
                        model_state="NOT_APPLICABLE",
                        evidence_quality="INSUFFICIENT",
                    )
                else:
                    attempt = V4ForecastAttempt(
                        instrument_id=candidate.instrument_id,
                        session_date=session_date,
                        attempted_at=request.frozen_at,
                        model_state="FAILED",
                        evidence_quality=state.evidence_quality.quality,
                        failure_reason=failure,
                    )

            self.repository.append(
                session_date=session_date,
                cohort_id=request.cohort.cohort_id,
                instrument_id=candidate.instrument_id,
                kind="v4_attempt",
                observed_at=request.frozen_at,
                payload=attempt,
                state=attempt.model_state,
                reason_code=attempt.failure_reason,
                run_id=request.run_id,
            )

            v42: V42Forecast | None = None
            v42_failure: str | None = None
            if not session_eligible_for_v42_forward_validation(session_date):
                v42_attempt = V42ForecastAttempt(
                    instrument_id=candidate.instrument_id,
                    session_date=session_date,
                    attempted_at=request.frozen_at,
                    model_state="NOT_APPLICABLE",
                    failure_reason="V42_SESSION_NOT_FORWARD_ELIGIBLE",
                )
            elif (
                state.source_mode != "CANONICAL_RAW_1M"
                or state.coverage_ratio is None
                or state.coverage_ratio < DEFAULT_V42_SPEC.minimum_premarket_coverage
                or state.unresolved_gap_count > 0
                or state.raw_bar_count < DEFAULT_V42_SPEC.minimum_total_premarket_bars
                or state.late_window_bar_count < DEFAULT_V42_SPEC.minimum_late_window_bars
                or state.latest_bar_lag_seconds is None
                or state.latest_bar_lag_seconds > DEFAULT_V42_SPEC.maximum_latest_bar_lag_seconds
            ):
                v42_failure = "V42_COMPLETE_PREMARKET_TAPE_REQUIRED"
                v42_attempt = V42ForecastAttempt(
                    instrument_id=candidate.instrument_id,
                    session_date=session_date,
                    attempted_at=request.frozen_at,
                    model_state="NOT_APPLICABLE",
                    failure_reason=v42_failure,
                )
            elif extension is None:
                v42_failure = "V42_EXTENSION_RISK_UNAVAILABLE"
                v42_attempt = V42ForecastAttempt(
                    instrument_id=candidate.instrument_id,
                    session_date=session_date,
                    attempted_at=request.frozen_at,
                    model_state="FAILED",
                    failure_reason=v42_failure,
                )
            else:
                try:
                    v42 = freeze_v42_forecast(
                        candidate=candidate,
                        session_date=session_date,
                        cohort_id=request.cohort.cohort_id,
                        cohort_fingerprint=request.cohort.cohort_fingerprint,
                        market_state=state.market_state,
                        catalyst=row.catalyst,
                        v4_mechanisms=row.mechanisms,
                        extension_risk=extension,
                        regime_tags=row.regime_tags,
                        frozen_at=request.frozen_at,
                    )
                    self.repository.append(
                        session_date=session_date,
                        cohort_id=request.cohort.cohort_id,
                        instrument_id=candidate.instrument_id,
                        kind="v42_forecast",
                        observed_at=request.frozen_at,
                        payload=V42ForecastRecord(forecast=v42),
                        state="PRODUCED",
                        run_id=request.run_id,
                    )
                    watch = classify_v42_watch(
                        v42,
                        policy=DEFAULT_V42_ACTION_POLICY,
                    )
                    self.repository.append(
                        session_date=session_date,
                        cohort_id=request.cohort.cohort_id,
                        instrument_id=candidate.instrument_id,
                        kind="v42_watch",
                        observed_at=request.frozen_at,
                        payload=watch,
                        state=watch.classification,
                        reason_code=watch.reasons[0] if watch.reasons else None,
                        run_id=request.run_id,
                        idempotency_suffix=watch.forecast_fingerprint,
                    )
                    v42_attempt = V42ForecastAttempt(
                        instrument_id=candidate.instrument_id,
                        session_date=session_date,
                        attempted_at=request.frozen_at,
                        model_state="PRODUCED",
                        forecast_fingerprint=v42.immutable_fingerprint,
                    )
                except Exception as exc:
                    v42_failure = f"{type(exc).__name__}:{exc}"
                    state_name: Literal["FAILED", "NOT_APPLICABLE"] = (
                        "NOT_APPLICABLE"
                        if "missing_complete_demand_evidence" in str(exc)
                        else "FAILED"
                    )
                    v42_attempt = V42ForecastAttempt(
                        instrument_id=candidate.instrument_id,
                        session_date=session_date,
                        attempted_at=request.frozen_at,
                        model_state=state_name,
                        failure_reason=v42_failure,
                    )
            self.repository.append(
                session_date=session_date,
                cohort_id=request.cohort.cohort_id,
                instrument_id=candidate.instrument_id,
                kind="v42_attempt",
                observed_at=request.frozen_at,
                payload=v42_attempt,
                state=v42_attempt.model_state,
                reason_code=v42_attempt.failure_reason,
                run_id=request.run_id,
            )
            results.append(
                PremarketInstrumentResult(
                    instrument_id=candidate.instrument_id,
                    market_state=state,
                    v3_forecast=row.v3_forecast,
                    v4_forecast=v4,
                    v4_failure_reason=failure,
                    v42_forecast=v42,
                    v42_failure_reason=v42_failure,
                )
            )

        legacy = LegacyPortfolioBundle(
            portfolios=freeze_research_portfolios(
                v3_forecasts,
                frozen_at=request.frozen_at,
                risk_factors=request.risk_factors,
                starting_equity=request.portfolio_e_policy.starting_equity,
            )
        )
        self.repository.append(
            session_date=session_date,
            cohort_id=request.cohort.cohort_id,
            instrument_id="__portfolio__",
            kind="legacy_portfolios",
            observed_at=request.frozen_at,
            payload=legacy,
            run_id=request.run_id,
        )
        return PremarketFreezeResult(
            session_date=session_date,
            cohort_id=request.cohort.cohort_id,
            results=tuple(results),
            legacy_portfolios=legacy,
        )

    def _manifest(self, session_date: date) -> ProspectiveSessionManifest:
        record = self.repository.session(session_date).latest(
            kind="session_manifest",
            instrument_id="__session__",
        )
        if record is None:
            raise ValueError("prospective_session_not_frozen")
        return ProspectiveSessionManifest.model_validate(record.payload)

    def _v4_record(
        self,
        ledger: ProspectiveGapSessionLedger,
        instrument_id: str,
    ) -> V4ForecastRecord | None:
        record = ledger.latest(kind="v4_forecast", instrument_id=instrument_id)
        return V4ForecastRecord.model_validate(record.payload) if record is not None else None

    def _v42_record(
        self,
        ledger: ProspectiveGapSessionLedger,
        instrument_id: str,
    ) -> V42ForecastRecord | None:
        record = ledger.latest(kind="v42_forecast", instrument_id=instrument_id)
        return V42ForecastRecord.model_validate(record.payload) if record is not None else None

    def _v42_watch(
        self,
        ledger: ProspectiveGapSessionLedger,
        instrument_id: str,
    ) -> V42WatchDecision | None:
        record = ledger.latest(kind="v42_watch", instrument_id=instrument_id)
        return V42WatchDecision.model_validate(record.payload) if record is not None else None

    def _latest_confirmation_state(
        self,
        ledger: ProspectiveGapSessionLedger,
        instrument_id: str,
    ) -> ConfirmationState:
        record = ledger.latest(kind="confirmation", instrument_id=instrument_id)
        if record is None:
            return "WAIT_OPEN"
        return ConfirmationTransitionReceipt.model_validate(record.payload).new_state

    def _latest_authorization(
        self,
        ledger: ProspectiveGapSessionLedger,
        instrument_id: str,
    ) -> TradeAuthorizationReceipt | None:
        record = ledger.latest(kind="authorization", instrument_id=instrument_id)
        return (
            TradeAuthorizationReceipt.model_validate(record.payload)
            if record is not None
            else None
        )

    def _latest_confirmation(
        self,
        ledger: ProspectiveGapSessionLedger,
        instrument_id: str,
    ) -> ConfirmationTransitionReceipt | None:
        record = ledger.latest(kind="confirmation", instrument_id=instrument_id)
        return (
            ConfirmationTransitionReceipt.model_validate(record.payload)
            if record is not None
            else None
        )

    def _execution_cost(
        self,
        *,
        candidate: GapperCandidate,
        policy: PortfolioEPolicy | V42ActionPolicy,
        decision_at: datetime,
    ) -> ExecutionCostInput | None:
        try:
            observation = self.market_service.execution_observation(candidate.instrument_id)
        except Exception:
            return None
        if (
            not observation.paper_fill_eligible
            or observation.bid is None
            or observation.ask is None
            or observation.midpoint is None
        ):
            return None
        return ExecutionCostInput(
            symbol=candidate.instrument_id.rsplit(":", 1)[-1],
            decision_at=decision_at,
            notional=policy.starting_equity * policy.max_position_fraction,
            reference_price=observation.midpoint,
            observed_bid=observation.bid,
            observed_ask=observation.ask,
            estimated_slippage_bps=policy.estimated_entry_slippage_bps,
            estimated_impact_bps=policy.estimated_entry_impact_bps,
            expected_exit_slippage_bps=policy.estimated_exit_slippage_bps,
            expected_exit_impact_bps=policy.estimated_exit_impact_bps,
            estimated_round_trip_commission_bps=policy.estimated_round_trip_commission_bps,
        )

    def run_confirmation(
        self,
        *,
        session_date: date,
        evaluated_at: datetime,
    ) -> ConfirmationRunResult:
        evaluated_at = _utc(evaluated_at)
        manifest = self._manifest(session_date)
        ledger = self.repository.session(session_date)
        new_receipts = 0
        new_authorizations = 0
        terminal = 0

        for candidate in manifest.candidates:
            v4_record = self._v4_record(ledger, candidate.instrument_id)
            previous = self._latest_confirmation_state(ledger, candidate.instrument_id)
            if previous == "CONFIRMED_LONG":
                terminal += 1
                if (
                    v4_record is not None
                    and self._latest_authorization(ledger, candidate.instrument_id) is None
                ):
                    confirmation = self._latest_confirmation(ledger, candidate.instrument_id)
                    if confirmation is not None:
                        actionability = ActionabilityDecision(
                            instrument_id=candidate.instrument_id,
                            decision_at=confirmation.transition_at,
                            actionability="ABSTAIN",
                            reasons=("AUTHORIZATION_WINDOW_MISSED_AFTER_CONFIRMATION",),
                        )
                        evidence_fingerprint = _hash(
                            {
                                "confirmation": confirmation.model_dump(mode="json"),
                                "recovery": "fail_closed_no_late_market_evidence",
                            }
                        )
                        authorization = authorize_trade(
                            forecast=v4_record.forecast,
                            confirmation=confirmation,
                            actionability=actionability,
                            gross=None,
                            cost=None,
                            evidence_fingerprint=evidence_fingerprint,
                            max_positive_alpha_notional=Decimal("0"),
                            minimum_net_expected_return=manifest.portfolio_e_policy.minimum_net_expected_return,
                            minimum_net_q10=manifest.portfolio_e_policy.minimum_net_q10,
                        )
                        inserted = self.repository.append(
                            session_date=session_date,
                            cohort_id=manifest.cohort.cohort_id,
                            instrument_id=candidate.instrument_id,
                            kind="authorization",
                            observed_at=authorization.decision_at,
                            payload=authorization,
                            state=authorization.decision,
                            reason_code=authorization.reasons[0] if authorization.reasons else None,
                            run_id=manifest.run_id,
                            idempotency_suffix=authorization.confirmation_receipt_fingerprint,
                        )
                        new_authorizations += int(inserted)
                continue
            if previous in {"INVALIDATED", "EXPIRED"}:
                terminal += 1
                continue

            bars: Sequence[object] = ()
            data_quality_ok = False
            data_quality_reason: str | None = None
            recovered = getattr(self.market_service, "recovered_bars", None)
            try:
                if callable(recovered):
                    recovered_result = recovered(
                        candidate.instrument_id,
                        "1m",
                        500,
                        candidate.binding_id,
                        session_date=session_date,
                        as_of=evaluated_at,
                        knowledge_mode="live",
                        knowledge_cutoff=evaluated_at,
                    )
                    bars = recovered_result.bars
                    data_quality_ok = not recovered_result.report.unresolved_gaps
                    if not data_quality_ok:
                        data_quality_reason = "CURRENT_SESSION_DEPENDENCY_GAP"
                else:
                    response = self.market_service.bars(
                        candidate.instrument_id,
                        "1m",
                        500,
                        candidate.binding_id,
                    )
                    bars = tuple(getattr(response, "bars", ()) or ())
                    data_quality_ok = bool(bars)
                    if not data_quality_ok:
                        data_quality_reason = "CURRENT_TAPE_UNAVAILABLE"
            except Exception as exc:
                data_quality_reason = f"CURRENT_TAPE_FETCH_FAILED:{type(exc).__name__}"

            evaluation = evaluate_operational_confirmation(
                candidate=candidate,
                bars=bars,  # type: ignore[arg-type]
                observed_at=evaluated_at,
                previous_state=previous,
                config=manifest.confirmation_strategy_config,
                data_quality_ok=data_quality_ok,
                data_quality_reason=data_quality_reason,
            )
            for receipt in evaluation.receipts:
                inserted = self.repository.append(
                    session_date=session_date,
                    cohort_id=manifest.cohort.cohort_id,
                    instrument_id=candidate.instrument_id,
                    kind="confirmation",
                    observed_at=receipt.transition_at,
                    payload=receipt,
                    state=receipt.new_state,
                    reason_code=receipt.trigger,
                    run_id=manifest.run_id,
                    idempotency_suffix=_hash(receipt.model_dump(mode="json")),
                )
                new_receipts += int(inserted)

            if evaluation.final_confirmation_state != "CONFIRMED_LONG" or not evaluation.receipts:
                continue
            confirmation = evaluation.receipts[-1]
            if confirmation.new_state != "CONFIRMED_LONG":
                continue
            if v4_record is None:
                continue

            actionability = ActionabilityDecision(
                instrument_id=candidate.instrument_id,
                decision_at=evaluated_at,
                actionability=(
                    "ACT"
                    if v4_record.forecast.calibrated_p_close_above_open
                    > manifest.portfolio_e_policy.minimum_bullish_probability
                    else "ABSTAIN"
                ),
                reasons=(
                    ()
                    if v4_record.forecast.calibrated_p_close_above_open
                    > manifest.portfolio_e_policy.minimum_bullish_probability
                    else ("PREMARKET_FORECAST_NOT_BULLISH",)
                ),
            )
            cost = self._execution_cost(
                candidate=candidate,
                policy=manifest.portfolio_e_policy,
                decision_at=evaluated_at,
            )
            evidence_fingerprint = _hash(
                {
                    "confirmation": confirmation.model_dump(mode="json"),
                    "cost": cost.model_dump(mode="json") if cost is not None else None,
                }
            )
            authorization = authorize_trade(
                forecast=v4_record.forecast,
                confirmation=confirmation,
                actionability=actionability,
                gross=v4_record.economic_distribution,
                cost=cost,
                evidence_fingerprint=evidence_fingerprint,
                max_positive_alpha_notional=(
                    manifest.portfolio_e_policy.starting_equity
                    * manifest.portfolio_e_policy.max_position_fraction
                ),
                minimum_net_expected_return=manifest.portfolio_e_policy.minimum_net_expected_return,
                minimum_net_q10=manifest.portfolio_e_policy.minimum_net_q10,
            )
            inserted = self.repository.append(
                session_date=session_date,
                cohort_id=manifest.cohort.cohort_id,
                instrument_id=candidate.instrument_id,
                kind="authorization",
                observed_at=authorization.decision_at,
                payload=authorization,
                state=authorization.decision,
                reason_code=authorization.reasons[0] if authorization.reasons else None,
                run_id=manifest.run_id,
                idempotency_suffix=authorization.confirmation_receipt_fingerprint,
            )
            new_authorizations += int(inserted)

        refreshed = self.repository.session(session_date)
        authorization_by_instrument: dict[str, TradeAuthorizationReceipt] = {}
        for record in refreshed.records_of_kind("authorization"):
            receipt = TradeAuthorizationReceipt.model_validate(record.payload)
            prior = authorization_by_instrument.get(receipt.instrument_id)
            if prior is None or receipt.decision_at > prior.decision_at:
                authorization_by_instrument[receipt.instrument_id] = receipt
        portfolio_e = build_cash_preserving_shadow_portfolio(
            tuple(authorization_by_instrument.values()),
            starting_equity=manifest.portfolio_e_policy.starting_equity,
            max_positions=manifest.portfolio_e_policy.max_positions,
            max_position_fraction=manifest.portfolio_e_policy.max_position_fraction,
        )
        self.repository.append(
            session_date=session_date,
            cohort_id=manifest.cohort.cohort_id,
            instrument_id="__portfolio_e__",
            kind="portfolio_e",
            observed_at=evaluated_at,
            payload=portfolio_e,
            state="frozen",
            run_id=manifest.run_id,
            idempotency_suffix=_hash(portfolio_e.model_dump(mode="json")),
        )
        terminal_count = sum(
            self._latest_confirmation_state(refreshed, candidate.instrument_id)
            in {"CONFIRMED_LONG", "INVALIDATED", "EXPIRED"}
            for candidate in manifest.candidates
        )

        # v4.2 remains an independent shadow action experiment. It does not
        # alter Portfolio E or the legacy v4 confirmation authority.
        v42_action_snapshot_count = 0
        v42_authorization_count = 0
        v42_terminal_count = 0
        v42_ledger = self.repository.session(session_date)
        for candidate in manifest.candidates:
            v42_record = self._v42_record(v42_ledger, candidate.instrument_id)
            watch = self._v42_watch(v42_ledger, candidate.instrument_id)
            if v42_record is None or watch is None:
                continue

            existing_v42_authorizations = [
                V42AuthorizationReceipt.model_validate(row.payload)
                for row in v42_ledger.records_of_kind("v42_authorization")
                if row.instrument_id == candidate.instrument_id
            ]
            if any(row.decision == "LONG" for row in existing_v42_authorizations):
                v42_terminal_count += 1
                continue
            prior_action_record = v42_ledger.latest(
                kind="v42_action",
                instrument_id=candidate.instrument_id,
            )
            if prior_action_record is not None:
                prior_action = V42ActionSnapshot.model_validate(prior_action_record.payload)
                if prior_action.state in {"INVALIDATED", "EXPIRED"}:
                    v42_terminal_count += 1
                    continue

            v42_bars: Sequence[object] = ()
            v42_data_quality_ok = False
            v42_data_quality_reasons: list[str] = []
            recovered = getattr(self.market_service, "recovered_bars", None)
            try:
                if callable(recovered):
                    recovered_result = recovered(
                        candidate.instrument_id,
                        "1m",
                        500,
                        candidate.binding_id,
                        session_date=session_date,
                        as_of=evaluated_at,
                        knowledge_mode="live",
                        knowledge_cutoff=evaluated_at,
                    )
                    v42_bars = recovered_result.bars
                    v42_data_quality_ok = not recovered_result.report.unresolved_gaps
                    if not v42_data_quality_ok:
                        v42_data_quality_reasons.append("CURRENT_SESSION_DEPENDENCY_GAP")
                else:
                    response = self.market_service.bars(
                        candidate.instrument_id,
                        "1m",
                        500,
                        candidate.binding_id,
                    )
                    v42_bars = tuple(getattr(response, "bars", ()) or ())
                    v42_data_quality_ok = bool(v42_bars)
                    if not v42_data_quality_ok:
                        v42_data_quality_reasons.append("CURRENT_TAPE_UNAVAILABLE")
            except Exception as exc:
                v42_data_quality_reasons.append(
                    f"CURRENT_TAPE_FETCH_FAILED:{type(exc).__name__}"
                )

            v42_cost = self._execution_cost(
                candidate=candidate,
                policy=DEFAULT_V42_ACTION_POLICY,
                decision_at=evaluated_at,
            )
            snapshot = evaluate_v42_post_open_action(
                forecast=v42_record.forecast,
                watch=watch,
                bars=v42_bars,  # type: ignore[arg-type]
                evaluated_at=evaluated_at,
                data_quality_ok=v42_data_quality_ok,
                execution_cost=v42_cost,
                policy=DEFAULT_V42_ACTION_POLICY,
                data_quality_reasons=tuple(v42_data_quality_reasons),
            )
            inserted = self.repository.append(
                session_date=session_date,
                cohort_id=manifest.cohort.cohort_id,
                instrument_id=candidate.instrument_id,
                kind="v42_action",
                observed_at=evaluated_at,
                payload=snapshot,
                state=snapshot.state,
                reason_code=snapshot.reasons[0] if snapshot.reasons else None,
                run_id=manifest.run_id,
                idempotency_suffix=_hash(snapshot.model_dump(mode="json")),
            )
            v42_action_snapshot_count += int(inserted)

            if snapshot.state in {"STRUCTURE_CONFIRMED", "INVALIDATED", "EXPIRED"}:
                authorization = authorize_v42_action(
                    forecast=v42_record.forecast,
                    watch=watch,
                    snapshot=snapshot,
                    execution_cost=v42_cost,
                    policy=DEFAULT_V42_ACTION_POLICY,
                )
                inserted_auth = self.repository.append(
                    session_date=session_date,
                    cohort_id=manifest.cohort.cohort_id,
                    instrument_id=candidate.instrument_id,
                    kind="v42_authorization",
                    observed_at=authorization.decision_at,
                    payload=authorization,
                    state=authorization.decision,
                    reason_code=authorization.reasons[0] if authorization.reasons else None,
                    run_id=manifest.run_id,
                    idempotency_suffix=_hash(
                        {
                            "snapshot": snapshot.model_dump(mode="json"),
                            "authorization": authorization.model_dump(mode="json"),
                        }
                    ),
                )
                v42_authorization_count += int(inserted_auth)
                if authorization.decision == "LONG" or snapshot.state in {"INVALIDATED", "EXPIRED"}:
                    v42_terminal_count += 1

        refreshed_v42 = self.repository.session(session_date)
        portfolio_f = build_portfolio_f(
            tuple(
                V42AuthorizationReceipt.model_validate(row.payload)
                for row in refreshed_v42.records_of_kind("v42_authorization")
            ),
            policy=DEFAULT_V42_ACTION_POLICY,
        )
        self.repository.append(
            session_date=session_date,
            cohort_id=manifest.cohort.cohort_id,
            instrument_id="__portfolio_f__",
            kind="portfolio_f",
            observed_at=evaluated_at,
            payload=portfolio_f,
            state="frozen",
            run_id=manifest.run_id,
            idempotency_suffix=_hash(portfolio_f.model_dump(mode="json")),
        )
        return ConfirmationRunResult(
            session_date=session_date,
            evaluated_at=evaluated_at,
            evaluated_count=len(manifest.candidates),
            new_confirmation_receipt_count=new_receipts,
            new_authorization_count=new_authorizations,
            terminal_count=terminal_count,
            portfolio_e=portfolio_e,
        )

    def _portfolio_e_performance(
        self,
        *,
        ledger: ProspectiveGapSessionLedger,
        outcomes: dict[str, FormalOutcomeBundle],
    ) -> PortfolioEPerformance | None:
        record = ledger.latest(kind="portfolio_e", instrument_id="__portfolio_e__")
        if record is None:
            return None
        portfolio = CashPreservingShadowPortfolio.model_validate(record.payload)
        authorizations: dict[str, TradeAuthorizationReceipt] = {}
        for row in ledger.records_of_kind("authorization"):
            receipt = TradeAuthorizationReceipt.model_validate(row.payload)
            prior = authorizations.get(receipt.instrument_id)
            if prior is None or receipt.decision_at > prior.decision_at:
                authorizations[receipt.instrument_id] = receipt

        ending = portfolio.cash
        rows: list[PortfolioEPositionOutcome] = []
        for position in portfolio.positions:
            outcome = outcomes.get(position.instrument_id)
            receipt = authorizations.get(position.instrument_id)
            if outcome is None or receipt is None or receipt.reference_price is None:
                continue
            entry = receipt.reference_price
            close = outcome.prices.close_price
            raw_return = close / entry - Decimal("1")
            cost_return = (receipt.total_cost_bps or Decimal("0")) / Decimal("10000")
            net_return = raw_return - cost_return
            value = position.allocation * (Decimal("1") + net_return)
            pnl = value - position.allocation
            ending += value
            rows.append(
                PortfolioEPositionOutcome(
                    instrument_id=position.instrument_id,
                    allocation=position.allocation,
                    reference_entry_price=entry,
                    close_price=close,
                    raw_return=raw_return,
                    cost_adjusted_return=net_return,
                    pnl=pnl,
                )
            )
        pnl = ending - portfolio.starting_equity
        return PortfolioEPerformance(
            rule_version=portfolio.rule_version,
            starting_equity=portfolio.starting_equity,
            ending_equity=ending,
            pnl=pnl,
            return_pct=pnl / portfolio.starting_equity,
            cash=portfolio.cash,
            position_outcomes=tuple(rows),
        )

    def _portfolio_f_performance(
        self,
        *,
        ledger: ProspectiveGapSessionLedger,
        outcomes: dict[str, FormalOutcomeBundle],
    ) -> PortfolioEPerformance | None:
        record = ledger.latest(kind="portfolio_f", instrument_id="__portfolio_f__")
        if record is None:
            return None
        portfolio = PortfolioF.model_validate(record.payload)
        ending = portfolio.cash
        rows: list[PortfolioEPositionOutcome] = []
        for position in portfolio.positions:
            outcome = outcomes.get(position.instrument_id)
            if outcome is None:
                continue
            entry = position.reference_price
            close = outcome.prices.close_price
            raw_return = close / entry - Decimal("1")
            cost_return = position.total_cost_bps / Decimal("10000")
            net_return = raw_return - cost_return
            value = position.allocation * (Decimal("1") + net_return)
            pnl = value - position.allocation
            ending += value
            rows.append(
                PortfolioEPositionOutcome(
                    instrument_id=position.instrument_id,
                    allocation=position.allocation,
                    reference_entry_price=entry,
                    close_price=close,
                    raw_return=raw_return,
                    cost_adjusted_return=net_return,
                    pnl=pnl,
                )
            )
        pnl = ending - portfolio.starting_equity
        return PortfolioEPerformance(
            rule_version=portfolio.version,
            starting_equity=portfolio.starting_equity,
            ending_equity=ending,
            pnl=pnl,
            return_pct=pnl / portfolio.starting_equity,
            cash=portfolio.cash,
            position_outcomes=tuple(rows),
        )

    def finalize_postclose(
        self,
        *,
        session_date: date,
        evaluated_at: datetime,
    ) -> PostcloseRunResult:
        evaluated_at = _utc(evaluated_at)
        manifest = self._manifest(session_date)
        ledger = self.repository.session(session_date)
        outcomes: list[FormalOutcomeBundle] = []
        outcome_by_instrument: dict[str, FormalOutcomeBundle] = {}
        for candidate in manifest.candidates:
            bundle = load_operational_formal_outcome(
                market_service=self.market_service,
                candidate=candidate,
                session_date=session_date,
            )
            outcomes.append(bundle)
            outcome_by_instrument[candidate.instrument_id] = bundle
            self.repository.append(
                session_date=session_date,
                cohort_id=manifest.cohort.cohort_id,
                instrument_id=candidate.instrument_id,
                kind="formal_outcome",
                observed_at=evaluated_at,
                payload=bundle,
                state="FINAL",
                run_id=manifest.run_id,
            )

        refreshed = self.repository.session(session_date)
        v3_obs: list[BinaryForecastObservation] = []
        v4_obs: list[BinaryForecastObservation] = []
        v42_obs: list[BinaryForecastObservation] = []
        v42_matched_v3_obs: list[BinaryForecastObservation] = []
        v42_matched_obs: list[BinaryForecastObservation] = []
        v42_return_obs: list[V42ReturnObservation] = []
        paired: list[PairedForecastObservation] = []
        complete = degraded = insufficient = unresolved = 0

        for candidate in manifest.candidates:
            outcome = outcome_by_instrument[candidate.instrument_id]
            outcome_value = outcome.labels.close_above_open

            state_record = refreshed.latest(kind="premarket_state", instrument_id=candidate.instrument_id)
            if state_record is not None:
                state = OperationalPremarketState.model_validate(state_record.payload)
                unresolved += state.unresolved_gap_count
                if state.evidence_quality.quality == "COMPLETE":
                    complete += 1
                elif state.evidence_quality.quality == "DEGRADED":
                    degraded += 1
                else:
                    insufficient += 1

            v3_record = refreshed.latest(kind="v3_forecast", instrument_id=candidate.instrument_id)
            v4_record = refreshed.latest(kind="v4_forecast", instrument_id=candidate.instrument_id)
            v3 = FrozenForecast.model_validate(v3_record.payload) if v3_record is not None else None
            v4 = (
                V4ForecastRecord.model_validate(v4_record.payload).forecast
                if v4_record is not None
                else None
            )
            v42_record = refreshed.latest(kind="v42_forecast", instrument_id=candidate.instrument_id)
            v42 = (
                V42ForecastRecord.model_validate(v42_record.payload).forecast
                if v42_record is not None
                else None
            )
            if v3 is not None:
                v3_obs.append(
                    BinaryForecastObservation(
                        instrument_id=candidate.instrument_id,
                        probability=v3.p_close_above_open,
                        outcome=outcome_value,
                    )
                )
            if v4 is not None:
                v4_obs.append(
                    BinaryForecastObservation(
                        instrument_id=candidate.instrument_id,
                        probability=v4.calibrated_p_close_above_open,
                        outcome=outcome_value,
                    )
                )
            if v42 is not None:
                v42_observation = BinaryForecastObservation(
                    instrument_id=candidate.instrument_id,
                    probability=v42.p_close_above_open,
                    outcome=outcome_value,
                )
                v42_obs.append(v42_observation)
                if v3 is not None:
                    v42_matched_v3_obs.append(
                        BinaryForecastObservation(
                            instrument_id=candidate.instrument_id,
                            probability=v3.p_close_above_open,
                            outcome=outcome_value,
                        )
                    )
                    v42_matched_obs.append(v42_observation)
                v42_return_obs.append(
                    V42ReturnObservation(
                        instrument_id=candidate.instrument_id,
                        forecast=v42,
                        realized_return=outcome.measurements.open_to_close_return,
                    )
                )
            if v3 is not None and v4 is not None:
                paired.append(
                    PairedForecastObservation(
                        session_date=session_date,
                        cohort_fingerprint=manifest.cohort.cohort_fingerprint,
                        instrument_id=candidate.instrument_id,
                        v3_probability=v3.p_close_above_open,
                        v4_probability=v4.calibrated_p_close_above_open,
                        outcome=outcome_value,
                    )
                )

        legacy_score_bundle: LegacyPortfolioScoreBundle | None = None
        legacy_record = refreshed.latest(
            kind="legacy_portfolios",
            instrument_id="__portfolio__",
        )
        if legacy_record is not None:
            legacy = LegacyPortfolioBundle.model_validate(legacy_record.payload)
            prices_by_instrument = {
                instrument_id: outcome.prices
                for instrument_id, outcome in outcome_by_instrument.items()
            }
            legacy_score_bundle = LegacyPortfolioScoreBundle(
                scores=tuple(
                    score_frozen_portfolio(portfolio, prices_by_instrument)
                    for portfolio in legacy.portfolios
                )
            )
            self.repository.append(
                session_date=session_date,
                cohort_id=manifest.cohort.cohort_id,
                instrument_id="__portfolio__",
                kind="legacy_portfolio_scores",
                observed_at=evaluated_at,
                payload=legacy_score_bundle,
                state="FINAL",
                run_id=manifest.run_id,
            )

        confirmation_rows = refreshed.records_of_kind("confirmation")
        authorization_rows = refreshed.records_of_kind("authorization")
        confirmations = [
            ConfirmationTransitionReceipt.model_validate(row.payload)
            for row in confirmation_rows
        ]
        authorizations = [
            TradeAuthorizationReceipt.model_validate(row.payload)
            for row in authorization_rows
        ]
        v42_actions = [
            V42ActionSnapshot.model_validate(row.payload)
            for row in refreshed.records_of_kind("v42_action")
        ]
        v42_authorizations = [
            V42AuthorizationReceipt.model_validate(row.payload)
            for row in refreshed.records_of_kind("v42_authorization")
        ]
        portfolio_e_performance = self._portfolio_e_performance(
            ledger=refreshed,
            outcomes=outcome_by_instrument,
        )
        portfolio_f_performance = self._portfolio_f_performance(
            ledger=refreshed,
            outcomes=outcome_by_instrument,
        )
        if portfolio_f_performance is not None:
            self.repository.append(
                session_date=session_date,
                cohort_id=manifest.cohort.cohort_id,
                instrument_id="__portfolio_f__",
                kind="portfolio_f_score",
                observed_at=evaluated_at,
                payload=portfolio_f_performance,
                state="FINAL",
                run_id=manifest.run_id,
                idempotency_suffix=_hash(
                    portfolio_f_performance.model_dump(mode="json")
                ),
            )
        v3_metrics = evaluate_binary_forecasts(
            v3_obs,
            frozen_climatology_probability=manifest.frozen_climatology_probability,
        )
        v42_metrics = evaluate_binary_forecasts(
            v42_obs,
            frozen_climatology_probability=manifest.frozen_climatology_probability,
        )
        matched_v3_metrics = evaluate_binary_forecasts(v42_matched_v3_obs)
        matched_v42_metrics = evaluate_binary_forecasts(v42_matched_obs)
        v42_comparison = V42ComparisonMetrics(
            n=matched_v42_metrics.n,
            brier_delta_v42_minus_v3=(
                matched_v42_metrics.brier_score - matched_v3_metrics.brier_score
                if (
                    matched_v42_metrics.brier_score is not None
                    and matched_v3_metrics.brier_score is not None
                )
                else None
            ),
            log_loss_delta_v42_minus_v3=(
                matched_v42_metrics.log_loss - matched_v3_metrics.log_loss
                if (
                    matched_v42_metrics.log_loss is not None
                    and matched_v3_metrics.log_loss is not None
                )
                else None
            ),
            accuracy_delta_v42_minus_v3=(
                matched_v42_metrics.accuracy - matched_v3_metrics.accuracy
                if (
                    matched_v42_metrics.accuracy is not None
                    and matched_v3_metrics.accuracy is not None
                )
                else None
            ),
        )
        scorecard = DailyProspectiveScorecard(
            session_date=session_date,
            cohort_id=manifest.cohort.cohort_id,
            complete_evidence_count=complete,
            degraded_evidence_count=degraded,
            insufficient_evidence_count=insufficient,
            unresolved_premarket_bar_count=unresolved,
            v3_metrics=v3_metrics,
            v4_metrics=evaluate_binary_forecasts(
                v4_obs,
                frozen_climatology_probability=manifest.frozen_climatology_probability,
            ),
            paired_metrics=evaluate_paired_v3_v4(paired),
            v42_metrics=v42_metrics,
            v42_comparison=v42_comparison,
            v42_return_metrics=evaluate_v42_return_metrics(v42_return_obs),
            legacy_portfolio_scores=legacy_score_bundle,
            confirmation_receipt_count=len(confirmations),
            confirmed_long_count=sum(row.new_state == "CONFIRMED_LONG" for row in confirmations),
            authorization_long_count=sum(row.decision == "LONG" for row in authorizations),
            authorization_no_trade_count=sum(row.decision == "NO_TRADE" for row in authorizations),
            portfolio_e_performance=portfolio_e_performance,
        )
        self.repository.append(
            session_date=session_date,
            cohort_id=manifest.cohort.cohort_id,
            instrument_id="__scorecard__",
            kind="daily_scorecard",
            observed_at=evaluated_at,
            payload=scorecard,
            state="FINAL",
            run_id=manifest.run_id,
        )
        return PostcloseRunResult(
            session_date=session_date,
            outcomes=tuple(outcomes),
            scorecard=scorecard,
        )

    def session_ledger(self, session_date: date) -> ProspectiveGapSessionLedger:
        return self.repository.session(session_date)

    def render_markdown(self, session_date: date) -> str:
        manifest = self._manifest(session_date)
        ledger = self.repository.session(session_date)
        score_record = ledger.latest(kind="daily_scorecard", instrument_id="__scorecard__")
        lines = [
            f"# Omnix Prospective Gap Runtime — {session_date.isoformat()}",
            "",
            f"- Runtime: `{RUNTIME_VERSION}`",
            f"- Cohort: `{manifest.cohort.cohort_id}`",
            f"- Cohort fingerprint: `{manifest.cohort.cohort_fingerprint}`",
            f"- Prediction cutoff: {manifest.cohort.discovery_cutoff_at.isoformat()}",
            f"- Frozen at: {manifest.frozen_at.isoformat()}",
            "",
            "## Machine-readable authority",
            "",
            "This document is a projection of the prospective-gap StrategyEvent ledger. "
            "The ledger, not this Markdown, is forecast/action/outcome authority.",
            "",
        ]
        if score_record is None:
            lines.extend([
                "Post-close scorecard is not final yet.",
                "",
            ])
            return "\n".join(lines)
        score = DailyProspectiveScorecard.model_validate(score_record.payload)
        lines.extend([
            "## Daily scorecard",
            "",
            f"- Evidence: {score.complete_evidence_count} COMPLETE / "
            f"{score.degraded_evidence_count} DEGRADED / "
            f"{score.insufficient_evidence_count} INSUFFICIENT",
            f"- Unresolved premarket one-minute bars: {score.unresolved_premarket_bar_count}",
            f"- V3 Brier: {score.v3_metrics.brier_score}",
            f"- V4 Brier: {score.v4_metrics.brier_score}",
            f"- Paired ΔBrier (v4-v3): {score.paired_metrics.mean_delta_brier_v4_minus_v3}",
            f"- V4.2 Brier: {score.v42_metrics.brier_score}",
            f"- V4.2 ΔBrier vs v3: {score.v42_comparison.brier_delta_v42_minus_v3}",
            f"- V4.2 expected-return MAE: {score.v42_return_metrics.expected_return_mae}",
            f"- V4.2 downside-tail Brier P(return<-5%): {score.v42_return_metrics.p_lt_minus_5_brier}",
            f"- V4.2 q10 breach rate: {score.v42_return_metrics.q10_breach_rate}",
            f"- Confirmation receipts: {score.confirmation_receipt_count}",
            f"- Confirmed longs: {score.confirmed_long_count}",
            f"- Authorized longs: {score.authorization_long_count}",
            f"- NO_TRADE authorizations: {score.authorization_no_trade_count}",
        ])
        if score.legacy_portfolio_scores is not None:
            for index, portfolio_score in enumerate(
                score.legacy_portfolio_scores.scores,
                start=1,
            ):
                label = ("A", "B", "C", "D")[index - 1]
                lines.append(
                    f"- Portfolio {label} ({portfolio_score.rule_version}) return: "
                    f"{portfolio_score.return_pct * Decimal('100')}%"
                )
        if score.portfolio_e_performance is not None:
            lines.append(
                f"- Portfolio E return: {score.portfolio_e_performance.return_pct * Decimal('100')}%"
            )
        v42_action_rows = ledger.records_of_kind("v42_action")
        v42_authorization_rows = ledger.records_of_kind("v42_authorization")
        if v42_action_rows or v42_authorization_rows:
            v42_actions = [
                V42ActionSnapshot.model_validate(row.payload)
                for row in v42_action_rows
            ]
            v42_authorizations = [
                V42AuthorizationReceipt.model_validate(row.payload)
                for row in v42_authorization_rows
            ]
            lines.extend([
                f"- V4.2 action snapshots: {len(v42_actions)}",
                f"- V4.2 structure confirmations: "
                f"{sum(row.state == 'STRUCTURE_CONFIRMED' for row in v42_actions)}",
                f"- V4.2 authorized longs: "
                f"{sum(row.decision == 'LONG' for row in v42_authorizations)}",
                f"- V4.2 NO_TRADE authorizations: "
                f"{sum(row.decision == 'NO_TRADE' for row in v42_authorizations)}",
            ])
        portfolio_f_score_record = ledger.latest(
            kind="portfolio_f_score",
            instrument_id="__portfolio_f__",
        )
        if portfolio_f_score_record is not None:
            portfolio_f_score = PortfolioEPerformance.model_validate(
                portfolio_f_score_record.payload
            )
            lines.append(
                f"- Portfolio F (v4.2 timed confirmation) return: "
                f"{portfolio_f_score.return_pct * Decimal('100')}%"
            )
        lines.append("")
        return "\n".join(lines)


_default_runtime: ProspectiveGapRuntime | None = None


def default_prospective_gap_runtime() -> ProspectiveGapRuntime:
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ProspectiveGapRuntime()
    return _default_runtime


__all__ = [
    "DailyProspectiveScorecard",
    "LegacyPortfolioBundle",
    "LegacyPortfolioScoreBundle",
    "PORTFOLIO_E_POLICY_VERSION",
    "PortfolioEPerformance",
    "PortfolioEPolicy",
    "PostcloseRunResult",
    "PremarketFreezeRequest",
    "PremarketFreezeResult",
    "PremarketInstrumentInput",
    "ProspectiveGapRuntime",
    "ProspectiveSessionManifest",
    "RUNTIME_VERSION",
    "V4ForecastRecord",
    "V42ComparisonMetrics",
    "V42ForecastRecord",
    "default_prospective_gap_runtime",
]
