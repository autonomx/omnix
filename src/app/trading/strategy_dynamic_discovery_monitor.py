from __future__ import annotations

import asyncio
import hashlib
import os
from contextlib import suppress
from datetime import datetime, time, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .strategy_discovery_acquisition import (
    CausalMarketObservation,
    capture_discovery_observations,
    install_default_discovery_sources,
)
from .strategy_dynamic_discovery import (
    AttributionStage,
    DiscoveryEvent,
    DiscoveryTriggerType,
    DynamicCandidate,
    INTERDAY_TRADING_STRATEGY_ID,
    advance_candidate_lifecycle,
    apply_strategy_rankings,
    build_attribution_event,
    build_opportunity_characterization,
    catalyst_discovery_event,
    market_attention_score,
    market_discovery_event,
    merge_discovery_event,
    tier_candidates,
)
from .strategy_dynamic_discovery_repository import DynamicDiscoveryEventRepository
from .strategy_repository import TradingStrategyRepository, default_strategy_repository
from .trade_logging import trade_log

_ET = ZoneInfo("America/New_York")
_STATE_KEY = "_omnix_interday_dynamic_discovery_monitor"


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def dynamic_discovery_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_DYNAMIC_DISCOVERY_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_DYNAMIC_DISCOVERY", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_DYNAMIC_DISCOVERY_INTERVAL_SECONDS", "300"))
    except ValueError:
        value = 300.0
    return max(60.0, value)


def _inside_discovery_window(now: datetime) -> bool:
    local = now.astimezone(_ET)
    if local.weekday() >= 5:
        return False
    clock = local.time().replace(tzinfo=None)
    return time(4, 0) <= clock <= time(16, 5)


def _event_id(observation: CausalMarketObservation, trigger: DiscoveryTriggerType) -> str:
    raw = "|".join((observation.instrument_id, trigger.value, observation.observed_at.isoformat(), observation.source))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _with_source_candidate(event: DiscoveryEvent, observation: CausalMarketObservation) -> DiscoveryEvent:
    if observation.candidate_payload is None:
        return event
    return event.model_copy(
        update={
            "payload": {
                **event.payload,
                "candidate": observation.candidate_payload,
            }
        }
    )


def _source_leader_event(observation: CausalMarketObservation) -> DiscoveryEvent | None:
    """Finviz membership is itself causal market-attention evidence."""

    if observation.market is None or observation.source != "finviz_live_leaders":
        return None
    if abs(observation.market.gap_pct) < 5.0:
        return None
    score = max(35.0, market_attention_score(observation.market))
    event = DiscoveryEvent(
        event_id=_event_id(observation, DiscoveryTriggerType.MARKET_ANOMALY),
        session_date=observation.session_date,
        instrument_id=observation.instrument_id,
        discovered_at=observation.observed_at,
        trigger_type=DiscoveryTriggerType.MARKET_ANOMALY,
        source=observation.source,
        source_locator=observation.source_locator,
        causal_as_of=observation.observed_at,
        attention_score=score,
        unexplained_attention=not observation.catalyst_known,
        payload={
            "leaderboard_membership": True,
            "features": observation.market.model_dump(mode="json"),
        },
    )
    return _with_source_candidate(event, observation)


def _event_from_observation(observation: CausalMarketObservation) -> tuple[DiscoveryEvent, ...]:
    values: list[DiscoveryEvent] = []
    if observation.market is not None:
        market = market_discovery_event(
            observation.instrument_id,
            observation.market,
            session_date=observation.session_date,
            source=observation.source,
            source_locator=observation.source_locator,
            catalyst_known=observation.catalyst_known,
        )
        if market is None:
            market = _source_leader_event(observation)
        elif observation.candidate_payload is not None:
            market = _with_source_candidate(market, observation)
        if market is not None:
            values.append(market)
    if observation.catalyst_payload is not None:
        catalyst = catalyst_discovery_event(
            observation.instrument_id,
            SimpleNamespace(**observation.catalyst_payload),
            session_date=observation.session_date,
            observed_at=observation.observed_at,
            source=observation.source,
            source_locator=observation.source_locator,
        )
        if catalyst is not None:
            values.append(catalyst)
    return tuple(values)


def _execution_quality(observation: CausalMarketObservation | None) -> float:
    if observation is None or observation.market is None or observation.market.spread_bps is None:
        return 50.0
    spread = max(0.0, observation.market.spread_bps)
    return max(0.0, min(100.0, 100.0 - spread / 2.0))


def _characterize(candidate: DynamicCandidate, observation: CausalMarketObservation | None) -> DynamicCandidate:
    catalyst = SimpleNamespace(
        catalyst_strength=candidate.catalyst_score,
        expected_attention_duration="uncertain",
        intraday_persistence_class="mixed",
        fundamental_materiality=candidate.catalyst_score,
        materiality_to_company_size=candidate.catalyst_score,
        event_certainty=candidate.catalyst_score,
        supply_pressure=0,
        promotional_risk=0,
    ) if candidate.catalyst_score > 0 else None
    structure = SimpleNamespace(confirmation_score=candidate.attention_score / 100.0)
    characterization = build_opportunity_characterization(
        candidate,
        observed_at=candidate.last_observed_at,
        catalyst=catalyst,
        market_structure=structure,
        execution_quality=_execution_quality(observation),
    )
    return candidate.model_copy(update={"characterization": characterization})


async def run_dynamic_discovery_once(
    *,
    now: datetime | None = None,
    repository: TradingStrategyRepository | None = None,
    observations: tuple[CausalMarketObservation, ...] | None = None,
) -> tuple[DynamicCandidate, ...]:
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    repo = repository or default_strategy_repository()
    try:
        parent = await asyncio.to_thread(repo.get_config, INTERDAY_TRADING_STRATEGY_ID)
    except ValueError:
        return ()
    if not parent.enabled or parent.archived_at is not None:
        return ()
    if observations is None:
        if not _inside_discovery_window(observed_at):
            return ()
        observations = await asyncio.to_thread(capture_discovery_observations, observed_at=observed_at)
    if not observations:
        return ()

    session_date = observations[0].session_date
    event_repo = DynamicDiscoveryEventRepository(repo)
    current = await asyncio.to_thread(event_repo.latest_candidates, session_date)
    latest_observation: dict[str, CausalMarketObservation] = {}
    emitted_by_symbol: dict[str, list[DiscoveryEvent]] = {}

    for observation in sorted(observations, key=lambda row: (row.observed_at, row.source, row.instrument_id)):
        if observation.session_date != session_date:
            continue
        latest_observation[observation.instrument_id] = observation
        for event in _event_from_observation(observation):
            if event.discovered_at > observed_at:
                raise ValueError("live_discovery_event_cannot_be_future_dated")
            await asyncio.to_thread(event_repo.persist_discovery, event)
            current[event.instrument_id] = merge_discovery_event(current.get(event.instrument_id), event)
            emitted_by_symbol.setdefault(event.instrument_id, []).append(event)

    observed_symbols = set(latest_observation)
    for instrument_id, candidate in tuple(current.items()):
        if instrument_id not in observed_symbols:
            current[instrument_id] = advance_candidate_lifecycle(
                candidate,
                observed_at=observed_at,
                current_priority=candidate.common_priority,
            )

    ranked = tier_candidates(tuple(current.values()))
    characterized = tuple(_characterize(row, latest_observation.get(row.instrument_id)) for row in ranked)
    ranked_by_strategy = apply_strategy_rankings(characterized)

    for candidate in ranked_by_strategy:
        await asyncio.to_thread(event_repo.persist_candidate, candidate)
        attribution = build_attribution_event(
            session_date=candidate.session_date,
            instrument_id=candidate.instrument_id,
            stage=AttributionStage.DISCOVERED,
            observed_at=candidate.discovered_at,
            payload={
                "trigger_types": [item.value for item in candidate.trigger_types],
                "experiment_arms": [item.value for item in candidate.experiment_arms],
            },
        )
        await asyncio.to_thread(event_repo.persist_attribution, attribution)
        if any(event.trigger_type == DiscoveryTriggerType.CATALYST_DISCOVERY_EVENT for event in emitted_by_symbol.get(candidate.instrument_id, ())):
            await asyncio.to_thread(
                event_repo.persist_attribution,
                build_attribution_event(
                    session_date=candidate.session_date,
                    instrument_id=candidate.instrument_id,
                    stage=AttributionStage.RESEARCHED,
                    observed_at=candidate.last_observed_at,
                    payload={"catalyst_score": candidate.catalyst_score},
                ),
            )
        await asyncio.to_thread(
            event_repo.persist_attribution,
            build_attribution_event(
                session_date=candidate.session_date,
                instrument_id=candidate.instrument_id,
                stage=AttributionStage.CHARACTERIZED,
                observed_at=candidate.last_observed_at,
                payload={"characterization": candidate.characterization.model_dump(mode="json") if candidate.characterization else None},
            ),
        )
        await asyncio.to_thread(
            event_repo.persist_attribution,
            build_attribution_event(
                session_date=candidate.session_date,
                instrument_id=candidate.instrument_id,
                stage=AttributionStage.RANKED,
                observed_at=candidate.last_observed_at,
                payload={"tier": candidate.tier.value, "strategy_ranks": candidate.strategy_ranks},
            ),
        )
    return ranked_by_strategy


class InterdayDynamicDiscoveryMonitor:
    """Continuously rediscover market leadership without changing order authority."""

    def __init__(self, *, interval_seconds: float | None = None) -> None:
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.candidate_count = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def run_once(self) -> int:
        candidates = await run_dynamic_discovery_once()
        self.candidate_count = len(candidates)
        self.last_run_at = datetime.now(timezone.utc)
        self.last_error = None
        return len(candidates)

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                trade_log(
                    "auto_trading",
                    "interday_dynamic_discovery_error",
                    strategy_id=INTERDAY_TRADING_STRATEGY_ID,
                    observed_at=datetime.now(timezone.utc),
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    research_only=True,
                    execution_authority=False,
                )
            await asyncio.sleep(self.interval_seconds)


def register_interday_dynamic_discovery_monitor(gateway: FastAPI) -> InterdayDynamicDiscoveryMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, InterdayDynamicDiscoveryMonitor):
        return existing
    install_default_discovery_sources()
    monitor = InterdayDynamicDiscoveryMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if dynamic_discovery_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


__all__ = [
    "InterdayDynamicDiscoveryMonitor",
    "dynamic_discovery_monitor_enabled",
    "register_interday_dynamic_discovery_monitor",
    "run_dynamic_discovery_once",
]
