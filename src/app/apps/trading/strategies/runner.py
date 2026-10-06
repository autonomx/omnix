"""The generic strategy runner (WP-8.3).

One scheduled task evaluates every enabled, non-archived configuration whose
kind is a registered ``Strategy``: it fetches the finalized bars the strategy
declares, calls ``evaluate`` once, and records each proposal as a
``proposal`` strategy event. Runner strategies are shadow-only: proposals are
evidence and never reach the order gateway from here.
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .contract import Proposal, Strategy, StrategyContext
from .registrations import STRATEGY_REGISTRY
from .registry import StrategyRegistry

logger = logging.getLogger(__name__)

TASK_ID = "trading.strategy_runner"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StrategyRunner:
    def __init__(
        self,
        *,
        strategy_repository_factory: Callable[[], Any],
        market_service_factory: Callable[[], Any],
        registry: StrategyRegistry = STRATEGY_REGISTRY,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.strategy_repository_factory = strategy_repository_factory
        self.market_service_factory = market_service_factory
        self.registry = registry
        self.clock = clock

    def run_once(self) -> int:
        """Evaluate every runnable configuration; return the proposals recorded."""
        strategies = {strategy.kind: strategy for strategy in self.registry.runner_strategies()}
        if not strategies:
            return 0
        repository = self.strategy_repository_factory()
        market = self.market_service_factory()
        recorded = 0
        for config in repository.list_configs(active_only=True):
            strategy = strategies.get(config.strategy_kind)
            if strategy is None or not config.enabled or config.archived_at is not None or config.mode == "off":
                continue
            recorded += self._run_config(strategy, config, repository, market)
        return recorded

    def _instruments(self, strategy: Strategy, config, repository) -> tuple[str, ...]:
        if config.active_universe_id:
            universe = repository.get_universe(config.active_universe_id)
            return tuple(candidate.instrument_id for candidate in universe.candidates)
        return strategy.data_requirements.instruments

    def _run_config(self, strategy: Strategy, config, repository, market) -> int:
        observed_at = self.clock()
        requirements = strategy.data_requirements
        bars = {}
        for instrument_id in self._instruments(strategy, config, repository):
            try:
                response = market.bars(instrument_id, requirements.interval, requirements.lookback_bars)
            except Exception as exc:
                logger.warning("strategy %s: bars for %s unavailable: %s", config.strategy_id, instrument_id, exc)
                continue
            # Only bars that had closed by the evaluation time.
            bars[instrument_id] = tuple(
                bar for bar in response.bars if bar.is_final and bar.end_time <= observed_at
            )
        context = StrategyContext(
            strategy_id=config.strategy_id,
            config=config.config,
            risk=config.risk,
            observed_at=observed_at,
            bars=bars,
        )
        recorded = 0
        for proposal in strategy.evaluate(context):
            recorded += bool(repository.append_event(_proposal_event(strategy, config, proposal, observed_at)))
        return recorded


def _proposal_event(strategy: Strategy, config, proposal: Proposal, observed_at: datetime):
    from ..strategy_repository import StrategyEvent

    # One proposal per strategy, instrument, reason and minute.
    minute = observed_at.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
    key = hashlib.sha256(
        "|".join((config.strategy_id, strategy.kind, proposal.instrument_id, proposal.reason_code, minute)).encode()
    ).hexdigest()
    return StrategyEvent(
        strategy_id=config.strategy_id,
        event_id=key[:32],
        instrument_id=proposal.instrument_id,
        event_type="proposal",
        state="proposed",
        reason_code=proposal.reason_code,
        observed_at=observed_at,
        idempotency_key=key,
        payload={
            "proposal": proposal.model_dump(mode="json"),
            "strategy_kind": strategy.kind,
            "strategy_version": strategy.version,
            "execution_authority": False,
        },
    )


def strategy_runner_task(context) -> Any:
    """The runner's scheduled task, or None while no runner strategy is registered."""
    if not STRATEGY_REGISTRY.runner_strategies():
        return None
    from app.runtime.scheduler import ScheduledTaskSpec

    from ..service import default_market_data_service
    from ..strategy_repository import default_strategy_repository

    runner = StrategyRunner(
        strategy_repository_factory=default_strategy_repository,
        market_service_factory=default_market_data_service,
    )
    return ScheduledTaskSpec(
        task_id=TASK_ID,
        run=lambda _task_context: runner.run_once(),
        interval_seconds=60.0,
        jitter_seconds=3.0,
        timeout_seconds=120.0,
        executor="thread",
    )
