from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.persistence.errors import RevisionConflict

from .catalyst_discovery import discover_yahoo_catalyst_headlines
from .catalyst_evidence import CatalystShadowClassification
from .catalyst_repository import TradingCatalystRepository, default_catalyst_repository
from .catalyst_shadow import generate_catalyst_shadow_classification
from .gapper_dataset import GapperCandidate, GapperUniverseSnapshot, freeze_gapper_universe
from .gapper_discovery import discover_yahoo_gappers
from .models import MarketBar
from .paper import PaperExecutionPolicy
from .strategies.gap_pullback import evaluate_gap_pullback
from .strategies.models import GapPullbackConfig, GapPullbackResult, StrategyRiskProfile
from .strategy_backtest import GapPullbackBacktestResult, freeze_backtest_session, run_gap_pullback_backtest
from .strategy_repository import (
    StrategyEvent,
    StrategyProtection,
    TradingStrategyConfigDocument,
    TradingStrategyRepository,
    default_strategy_repository,
)


class StrategyConfigListResponse(BaseModel):
    strategies: list[TradingStrategyConfigDocument]


class StrategyEventListResponse(BaseModel):
    events: list[StrategyEvent]


class StrategyProtectionListResponse(BaseModel):
    protections: list[StrategyProtection]


class StrategyEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: dict[str, object]
    bars: list[MarketBar] = Field(default_factory=list, max_length=1000)
    config: GapPullbackConfig = Field(default_factory=GapPullbackConfig)


class GapperUniverseFreezeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    universe_id: str = Field(min_length=1, max_length=200)
    session_date: date
    evaluation_time: datetime
    discovery_source: Literal["manual", "import", "scanner", "provider"] = "import"
    candidates: list[GapperCandidate] = Field(min_length=1, max_length=2_000)


class YahooGapperDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    universe_id: str = Field(min_length=1, max_length=200)
    evaluation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    count: int = Field(default=30, ge=1, le=100)
    minimum_gap_pct: Decimal = Field(default=Decimal("20"), ge=0, le=1000)
    minimum_price: Decimal = Field(default=Decimal("0.50"), gt=0)
    maximum_price: Decimal = Field(default=Decimal("20"), gt=0)


class GapPullbackBacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_date: date
    universe: GapperUniverseSnapshot
    bars_by_instrument: dict[str, list[MarketBar]]
    config: GapPullbackConfig = Field(default_factory=GapPullbackConfig)
    execution_policy: PaperExecutionPolicy = Field(
        default_factory=lambda: PaperExecutionPolicy(max_volume_participation_pct=Decimal("1"))
    )
    risk_profile: StrategyRiskProfile = Field(default_factory=StrategyRiskProfile)
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    assumed_spread_bps: Decimal = Field(default=Decimal("40"), ge=0, le=10_000)
    max_hold_minutes: int = Field(default=90, ge=1, le=390)
    max_concurrent_positions: int = Field(default=3, ge=1, le=50)


class StrategyResearchReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str | None = Field(default=None, max_length=200)


class StrategyResearchReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    instrument_id: str
    status: Literal["reviewed", "missing_evidence", "error"]
    classification: CatalystShadowClassification | None = None
    detail: str | None = None


class StrategyResearchReviewResponse(BaseModel):
    strategy_id: str
    universe_id: str
    shadow_only: Literal[True] = True
    reviews: list[StrategyResearchReview]


class StrategyCatalystCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lookback_hours: int = Field(default=72, ge=1, le=168)
    max_items_per_candidate: int = Field(default=8, ge=1, le=25)


class StrategyCatalystCaptureResponse(BaseModel):
    strategy: TradingStrategyConfigDocument
    universe: GapperUniverseSnapshot
    evidence_count: int = Field(ge=0)
    candidates_with_evidence: int = Field(ge=0)
    errors: dict[str, str] = Field(default_factory=dict)


RepositoryFactory = Callable[[], TradingStrategyRepository]
CatalystRepositoryFactory = Callable[[], TradingCatalystRepository]


def _validate_catalyst_provenance(snapshot: GapperUniverseSnapshot, catalyst_repository: TradingCatalystRepository) -> None:
    evaluation = snapshot.evaluation_time.astimezone(timezone.utc)
    for candidate in snapshot.candidates:
        if not candidate.catalyst_evidence_ids:
            continue
        evidence = catalyst_repository.evidence_by_ids(candidate.instrument_id, candidate.catalyst_evidence_ids)
        for item in evidence:
            if item.published_at > evaluation or item.captured_at > evaluation:
                raise ValueError(
                    "catalyst_evidence_after_universe_freeze:"
                    f"{candidate.instrument_id}:{item.evidence_id}"
                )


def _research_event(
    *,
    strategy_id: str,
    instrument_id: str,
    universe_id: str,
    observed_at: datetime,
    state: str,
    reason_code: str,
    payload: dict[str, object],
) -> StrategyEvent:
    raw = "|".join((strategy_id, instrument_id, universe_id, observed_at.astimezone(timezone.utc).isoformat(), state, reason_code))
    idem = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return StrategyEvent(
        strategy_id=strategy_id,
        event_id=idem[:32],
        instrument_id=instrument_id,
        event_type="research_llm",
        state=state,
        reason_code=reason_code,
        observed_at=observed_at,
        idempotency_key=idem,
        payload={"universe_id": universe_id, "shadow_only": True, **payload},
    )


def _research_universe_id(source_id: str, observed_at: datetime) -> str:
    suffix = f"-research-{observed_at.strftime('%H%M%S')}"
    return source_id[: 200 - len(suffix)] + suffix


def create_trading_strategy_router(
    repository_factory: RepositoryFactory = default_strategy_repository,
    catalyst_repository_factory: CatalystRepositoryFactory = default_catalyst_repository,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/strategies", tags=["trading-strategies"])

    @router.get("", response_model=StrategyConfigListResponse)
    async def list_strategies(active_only: bool = Query(default=False)):
        return StrategyConfigListResponse(
            strategies=await asyncio.to_thread(repository_factory().list_configs, active_only=active_only)
        )

    @router.post("", response_model=TradingStrategyConfigDocument, status_code=201)
    async def create_strategy(document: TradingStrategyConfigDocument):
        try:
            return await asyncio.to_thread(repository_factory().create_config, document)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/backtest/gap-pullback", response_model=GapPullbackBacktestResult)
    async def backtest_gap_pullback(request: GapPullbackBacktestRequest):
        try:
            _validate_catalyst_provenance(request.universe, catalyst_repository_factory())
            dataset = await asyncio.to_thread(
                freeze_backtest_session,
                session_date=request.session_date,
                universe=request.universe,
                bars_by_instrument=request.bars_by_instrument,
            )
            return await asyncio.to_thread(
                run_gap_pullback_backtest,
                dataset,
                request.config,
                request.execution_policy,
                assumed_spread_bps=request.assumed_spread_bps,
                max_hold_minutes=request.max_hold_minutes,
                max_concurrent_positions=request.max_concurrent_positions,
                risk_profile=request.risk_profile,
                initial_cash=request.initial_cash,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/universes/discover-yahoo", response_model=GapperUniverseSnapshot, status_code=201)
    async def discover_yahoo_universe(request: YahooGapperDiscoveryRequest):
        try:
            if request.maximum_price <= request.minimum_price:
                raise ValueError("maximum_price must exceed minimum_price")
            snapshot = await asyncio.to_thread(
                discover_yahoo_gappers,
                universe_id=request.universe_id,
                evaluation_time=request.evaluation_time,
                count=request.count,
                minimum_gap_pct=request.minimum_gap_pct,
                minimum_price=request.minimum_price,
                maximum_price=request.maximum_price,
            )
            return await asyncio.to_thread(repository_factory().save_universe, snapshot)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/universes/freeze", response_model=GapperUniverseSnapshot, status_code=201)
    async def freeze_universe(request: GapperUniverseFreezeRequest):
        try:
            snapshot = await asyncio.to_thread(
                freeze_gapper_universe,
                universe_id=request.universe_id,
                session_date=request.session_date,
                evaluation_time=request.evaluation_time,
                discovery_source=request.discovery_source,
                candidates=request.candidates,
            )
            _validate_catalyst_provenance(snapshot, catalyst_repository_factory())
            return await asyncio.to_thread(repository_factory().save_universe, snapshot)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/universes", response_model=GapperUniverseSnapshot, status_code=201)
    async def save_universe(snapshot: GapperUniverseSnapshot):
        try:
            validated = await asyncio.to_thread(
                freeze_gapper_universe,
                universe_id=snapshot.universe_id,
                session_date=snapshot.session_date,
                evaluation_time=snapshot.evaluation_time,
                discovery_source=snapshot.discovery_source,
                candidates=snapshot.candidates,
            )
            if validated.source_fingerprint != snapshot.source_fingerprint:
                raise ValueError("gapper_universe_fingerprint_mismatch")
            _validate_catalyst_provenance(snapshot, catalyst_repository_factory())
            return await asyncio.to_thread(repository_factory().save_universe, snapshot)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/universes/{universe_id}", response_model=GapperUniverseSnapshot)
    async def get_universe(universe_id: str):
        try:
            return await asyncio.to_thread(repository_factory().get_universe, universe_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/evaluate/gap-pullback", response_model=GapPullbackResult, include_in_schema=True)
    async def evaluate_strategy(request: StrategyEvaluationRequest):
        try:
            candidate = GapperCandidate.model_validate(request.candidate)
            return await asyncio.to_thread(evaluate_gap_pullback, candidate, request.bars, request.config)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{strategy_id}", response_model=TradingStrategyConfigDocument)
    async def get_strategy(strategy_id: str):
        try:
            return await asyncio.to_thread(repository_factory().get_config, strategy_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.put("/{strategy_id}", response_model=TradingStrategyConfigDocument)
    async def update_strategy(strategy_id: str, document: TradingStrategyConfigDocument, if_match: int = Header(alias="If-Match", ge=1)):
        try:
            return await asyncio.to_thread(
                repository_factory().update_config,
                strategy_id,
                document,
                expected_revision=if_match,
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/{strategy_id}/research/capture-yahoo", response_model=StrategyCatalystCaptureResponse)
    async def capture_yahoo_research(strategy_id: str, request: StrategyCatalystCaptureRequest):
        try:
            strategy_repository = repository_factory()
            config = await asyncio.to_thread(strategy_repository.get_config, strategy_id)
            if config.mode == "auto_paper":
                raise ValueError("pause_auto_paper_before_research_capture")
            if not config.active_universe_id:
                raise ValueError("strategy_has_no_active_universe")
            source = await asyncio.to_thread(strategy_repository.get_universe, config.active_universe_id)
            catalyst_repository = catalyst_repository_factory()
            capture_started_at = datetime.now(timezone.utc)
            evidence_count = 0
            errors: dict[str, str] = {}
            enriched: list[GapperCandidate] = []
            for candidate in source.candidates:
                symbol = candidate.instrument_id.split(":")[-1]
                try:
                    evidence = await asyncio.to_thread(
                        discover_yahoo_catalyst_headlines,
                        instrument_id=candidate.instrument_id,
                        symbol=symbol,
                        evaluation_time=capture_started_at,
                        lookback_hours=request.lookback_hours,
                        max_items=request.max_items_per_candidate,
                    )
                except Exception as exc:  # provider failure must not erase the candidate
                    errors[candidate.instrument_id] = f"{type(exc).__name__}: {exc}"
                    evidence = ()
                for item in evidence:
                    await asyncio.to_thread(catalyst_repository.save_evidence, item)
                evidence_count += len(evidence)
                ids = tuple(dict.fromkeys((*candidate.catalyst_evidence_ids, *(item.evidence_id for item in evidence))))
                flags = tuple(sorted(set(candidate.dilution_flags).union(*(set(item.dilution_flags) for item in evidence))))
                evidence_times = dict(candidate.evidence_observed_at)
                for item in evidence:
                    evidence_times[f"catalyst:{item.evidence_id}"] = item.captured_at
                enriched.append(
                    candidate.model_copy(
                        update={
                            "catalyst_evidence_ids": ids,
                            "dilution_flags": flags,
                            "evidence_observed_at": evidence_times,
                        }
                    )
                )

            freeze_time = datetime.now(timezone.utc)
            snapshot = freeze_gapper_universe(
                universe_id=_research_universe_id(source.universe_id, freeze_time),
                session_date=source.session_date,
                evaluation_time=freeze_time,
                discovery_source="import",
                candidates=enriched,
            )
            _validate_catalyst_provenance(snapshot, catalyst_repository)
            snapshot = await asyncio.to_thread(strategy_repository.save_universe, snapshot)
            updated_document = config.model_copy(update={"active_universe_id": snapshot.universe_id})
            updated = await asyncio.to_thread(
                strategy_repository.update_config,
                strategy_id,
                updated_document,
                expected_revision=config.revision,
            )
            return StrategyCatalystCaptureResponse(
                strategy=updated,
                universe=snapshot,
                evidence_count=evidence_count,
                candidates_with_evidence=sum(bool(item.catalyst_evidence_ids) for item in snapshot.candidates),
                errors=errors,
            )
        except RevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/{strategy_id}/research/llm-review", response_model=StrategyResearchReviewResponse)
    async def run_llm_research(strategy_id: str, request: StrategyResearchReviewRequest):
        try:
            repository = repository_factory()
            config = await asyncio.to_thread(repository.get_config, strategy_id)
            if not config.active_universe_id:
                raise ValueError("strategy_has_no_active_universe")
            universe = await asyncio.to_thread(repository.get_universe, config.active_universe_id)
            catalyst_repository = catalyst_repository_factory()
            reviews: list[StrategyResearchReview] = []
            for candidate in universe.candidates:
                observed_at = datetime.now(timezone.utc)
                if not candidate.catalyst_evidence_ids:
                    review = StrategyResearchReview(
                        instrument_id=candidate.instrument_id,
                        status="missing_evidence",
                        detail="No timestamped catalyst evidence attached to frozen candidate.",
                    )
                    await asyncio.to_thread(
                        repository.append_event,
                        _research_event(
                            strategy_id=strategy_id,
                            instrument_id=candidate.instrument_id,
                            universe_id=universe.universe_id,
                            observed_at=observed_at,
                            state="research_missing",
                            reason_code="CATALYST_EVIDENCE_MISSING",
                            payload={"detail": review.detail or ""},
                        ),
                    )
                    reviews.append(review)
                    continue
                try:
                    evidence = await asyncio.to_thread(
                        catalyst_repository.evidence_by_ids,
                        candidate.instrument_id,
                        candidate.catalyst_evidence_ids,
                    )
                    classification = await asyncio.to_thread(
                        generate_catalyst_shadow_classification,
                        evidence,
                        model=request.model,
                    )
                    await asyncio.to_thread(
                        repository.append_event,
                        _research_event(
                            strategy_id=strategy_id,
                            instrument_id=candidate.instrument_id,
                            universe_id=universe.universe_id,
                            observed_at=observed_at,
                            state="research_reviewed",
                            reason_code="LLM_SHADOW_REVIEW_COMPLETE",
                            payload={"classification": classification.model_dump(mode="json")},
                        ),
                    )
                    reviews.append(
                        StrategyResearchReview(
                            instrument_id=candidate.instrument_id,
                            status="reviewed",
                            classification=classification,
                        )
                    )
                except (RuntimeError, ValueError) as exc:
                    await asyncio.to_thread(
                        repository.append_event,
                        _research_event(
                            strategy_id=strategy_id,
                            instrument_id=candidate.instrument_id,
                            universe_id=universe.universe_id,
                            observed_at=observed_at,
                            state="research_error",
                            reason_code="LLM_SHADOW_REVIEW_ERROR",
                            payload={"detail": str(exc)},
                        ),
                    )
                    reviews.append(
                        StrategyResearchReview(
                            instrument_id=candidate.instrument_id,
                            status="error",
                            detail=str(exc),
                        )
                    )
            return StrategyResearchReviewResponse(
                strategy_id=strategy_id,
                universe_id=universe.universe_id,
                reviews=reviews,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/{strategy_id}/events", response_model=StrategyEventListResponse)
    async def recent_events(strategy_id: str, limit: int = Query(default=200, ge=1, le=1000)):
        try:
            await asyncio.to_thread(repository_factory().get_config, strategy_id)
            events = await asyncio.to_thread(repository_factory().recent_events, strategy_id, limit)
            return StrategyEventListResponse(events=events)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/{strategy_id}/protections", response_model=StrategyProtectionListResponse)
    async def protections(strategy_id: str, active_only: bool = Query(default=True)):
        try:
            await asyncio.to_thread(repository_factory().get_config, strategy_id)
            values = await asyncio.to_thread(repository_factory().list_protections, strategy_id, active_only=active_only)
            return StrategyProtectionListResponse(protections=values)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
