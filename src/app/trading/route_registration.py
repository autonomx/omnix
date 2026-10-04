"""Trading router composition and scheduler-owned monitor tasks."""
from __future__ import annotations

from collections.abc import Callable
import inspect

from fastapi import APIRouter

from app.runtime.features import FeatureContext
from app.runtime.scheduler import ScheduledTaskSpec, TaskContext


def create_trading_router(context: FeatureContext) -> APIRouter:
    """Compose the Trading HTTP surface without patching the gateway class."""
    from app.trading.alerts_api import create_trading_alert_router
    from app.trading.api import create_trading_router as create_trading_base_router
    from app.trading.catalyst_api import create_trading_catalyst_router
    from app.trading.execution_api import create_trading_execution_router
    from app.trading.hermes_research_api import create_trading_hermes_research_router
    from app.trading.market_data_api import create_trading_market_data_router
    from app.trading.metric_api import create_trading_metric_router
    from app.trading.model_api import create_trading_model_router
    from app.trading.paper_analytics_api import create_trading_paper_analytics_router
    from app.trading.paper_api import create_trading_paper_router
    from app.trading.prospective_gap_api import create_trading_prospective_gap_router
    from app.trading.replay_api import create_trading_replay_router
    from app.trading.research_api import create_trading_research_router
    from app.trading.scanner_api import create_trading_scanner_router
    from app.trading.strategy_api import create_trading_strategy_router
    from app.trading.strategy_operations_api import create_trading_strategy_operations_router
    from app.trading.strategy_prospective_economic_api import (
        create_trading_strategy_prospective_economic_router,
    )
    from app.trading.strategy_solana_ai_monitor import create_trading_solana_ai_control_router

    router = APIRouter()
    for factory in (
        create_trading_base_router,
        create_trading_metric_router,
        create_trading_execution_router,
        create_trading_alert_router,
        create_trading_scanner_router,
        create_trading_replay_router,
        create_trading_paper_router,
        create_trading_paper_analytics_router,
        create_trading_prospective_gap_router,
        create_trading_research_router,
        create_trading_hermes_research_router,
        create_trading_strategy_router,
        create_trading_strategy_prospective_economic_router,
        create_trading_strategy_operations_router,
        create_trading_solana_ai_control_router,
        create_trading_catalyst_router,
        create_trading_model_router,
        create_trading_market_data_router,
    ):
        if factory is create_trading_strategy_router:
            router.include_router(
                factory(job_store_factory=lambda: context.services.jobs)
            )
        else:
            router.include_router(factory())
    return router


def trading_scheduled_task_factories() -> tuple[Callable[[FeatureContext], ScheduledTaskSpec | None], ...]:
    """Build per-monitor tasks while preserving feature-owned enablement and cleanup."""
    from app.trading.alerts_monitor import (
        create_trading_alert_monitor_worker,
        trading_alert_monitor_enabled,
    )
    from app.trading.execution_observation_monitor import (
        create_trading_execution_observation_monitor_worker,
        execution_observation_monitor_enabled,
    )
    from app.trading.ibkr_market_data_monitor import (
        create_trading_ibkr_market_data_monitor_worker,
        ibkr_market_data_monitor_enabled,
    )
    from app.trading.metric_monitor import (
        create_trading_metric_monitor_worker,
        trading_liquidation_collector_enabled,
    )
    from app.trading.paper_monitor import (
        create_trading_paper_monitor_worker,
        trading_paper_monitor_enabled,
    )
    from app.trading.prospective_gap_monitor import (
        create_prospective_gap_monitor_worker,
        prospective_gap_monitor_enabled,
    )
    from app.trading.providers.alpaca_iex_status import (
        create_alpaca_iex_status_monitor_worker,
        alpaca_iex_status_monitor_enabled,
    )
    from app.trading.session_reconciliation_monitor import (
        create_trading_session_reconciliation_monitor_worker,
        session_reconciliation_monitor_enabled,
    )
    from app.trading.strategy_ai_shadow_monitor import (
        create_trading_ai_shadow_monitor_worker,
        ai_shadow_monitor_enabled,
    )
    from app.trading.strategy_ai_shadow_v2_monitor import (
        create_trading_ai_shadow_v2_monitor_worker,
        ai_shadow_v2_monitor_enabled,
    )
    from app.trading.strategy_ai_shadow_v3_monitor import (
        create_trading_ai_shadow_v3_monitor_worker,
        ai_shadow_v3_monitor_enabled,
    )
    from app.trading.strategy_deep_recovery_monitor import (
        create_trading_strategy_deep_recovery_shadow_monitor_worker,
        strategy_deep_recovery_shadow_monitor_enabled,
    )
    from app.trading.strategy_dynamic_discovery_monitor import (
        create_interday_dynamic_discovery_monitor_worker,
        dynamic_discovery_monitor_enabled,
    )
    from app.trading.strategy_interday_learning_monitor import (
        create_interday_learning_monitor_worker,
        interday_learning_monitor_enabled,
    )
    from app.trading.strategy_monitor import (
        create_trading_strategy_monitor_worker,
        prepare_trading_strategy_monitor_for_scheduled_execution,
        trading_strategy_monitor_enabled,
    )
    from app.trading.strategy_prospective_economic_monitor import (
        create_trading_strategy_prospective_economic_monitor_worker,
        strategy_prospective_economic_monitor_enabled,
    )
    from app.trading.strategy_research_monitor import (
        create_trading_strategy_research_monitor_worker,
        strategy_research_monitor_enabled,
    )
    from app.trading.strategy_research_outcome_monitor import (
        create_trading_strategy_research_outcome_monitor_worker,
        strategy_research_outcome_monitor_enabled,
    )
    from app.trading.strategy_solana_ai_monitor import (
        create_trading_solana_ai_monitor_worker,
        solana_ai_monitor_enabled,
    )
    from app.trading.strategy_universe_archive_monitor import (
        create_trading_strategy_universe_archive_monitor_worker,
        strategy_universe_archive_monitor_enabled,
    )
    from app.trading.strategy_v2_qualification_monitor import (
        create_trading_strategy_v2_qualification_monitor_worker,
        strategy_v2_qualification_monitor_enabled,
    )
    from app.trading.yahoo_acquisition_monitor import (
        create_trading_yahoo_acquisition_monitor_worker,
        yahoo_acquisition_monitor_enabled,
    )

    registrations = (
        (create_trading_alert_monitor_worker, trading_alert_monitor_enabled),
        (create_trading_execution_observation_monitor_worker, execution_observation_monitor_enabled),
        (create_trading_ibkr_market_data_monitor_worker, ibkr_market_data_monitor_enabled),
        (create_trading_metric_monitor_worker, trading_liquidation_collector_enabled),
        (create_trading_paper_monitor_worker, trading_paper_monitor_enabled),
        (create_prospective_gap_monitor_worker, prospective_gap_monitor_enabled),
        (create_alpaca_iex_status_monitor_worker, alpaca_iex_status_monitor_enabled),
        (create_trading_session_reconciliation_monitor_worker, session_reconciliation_monitor_enabled),
        (create_trading_ai_shadow_monitor_worker, ai_shadow_monitor_enabled),
        (create_trading_ai_shadow_v2_monitor_worker, ai_shadow_v2_monitor_enabled),
        (create_trading_ai_shadow_v3_monitor_worker, ai_shadow_v3_monitor_enabled),
        (create_trading_strategy_deep_recovery_shadow_monitor_worker, strategy_deep_recovery_shadow_monitor_enabled),
        (create_interday_dynamic_discovery_monitor_worker, dynamic_discovery_monitor_enabled),
        (create_interday_learning_monitor_worker, interday_learning_monitor_enabled),
        (create_trading_strategy_monitor_worker, trading_strategy_monitor_enabled),
        (create_trading_strategy_prospective_economic_monitor_worker, strategy_prospective_economic_monitor_enabled),
        (create_trading_strategy_research_monitor_worker, strategy_research_monitor_enabled),
        (create_trading_strategy_research_outcome_monitor_worker, strategy_research_outcome_monitor_enabled),
        (create_trading_solana_ai_monitor_worker, solana_ai_monitor_enabled),
        (create_trading_strategy_universe_archive_monitor_worker, strategy_universe_archive_monitor_enabled),
        (create_trading_strategy_v2_qualification_monitor_worker, strategy_v2_qualification_monitor_enabled),
        (create_trading_yahoo_acquisition_monitor_worker, yahoo_acquisition_monitor_enabled),
    )

    def factory_for(worker_factory, enabled):
        def create(context: FeatureContext) -> ScheduledTaskSpec | None:
            worker = worker_factory(context)
            if worker is None:
                return None
            monitor = worker.monitor
            run_once = getattr(monitor, "run_once", None)
            if not callable(run_once):
                raise TypeError(
                    f"Scheduled trading monitor {worker.name} must expose run_once()"
                )
            interval_seconds = getattr(monitor, "interval_seconds", 60.0)
            active_interval = getattr(monitor, "active_interval_seconds", None)
            if active_interval is not None:
                interval_seconds = min(interval_seconds, active_interval)

            if inspect.iscoroutinefunction(run_once):
                async def run(_task_context: TaskContext) -> None:
                    await run_once()

                executor = "async"
            else:
                def run(_task_context: TaskContext) -> None:
                    result = run_once()
                    if inspect.isawaitable(result):
                        raise TypeError(
                            f"Synchronous trading monitor {worker.name} returned an awaitable"
                        )

                executor = "thread"

            startup = getattr(monitor, "prepare_for_scheduled_execution", None)
            if startup is None and worker.name.endswith("metric_monitor"):
                startup_callbacks = worker.startup
            elif startup is None and worker.name.endswith(".strategy_monitor"):
                startup_callbacks = (
                    lambda: prepare_trading_strategy_monitor_for_scheduled_execution(
                        monitor
                    ),
                )
            else:
                startup_callbacks = (startup,) if callable(startup) else ()

            return ScheduledTaskSpec(
                task_id=worker.name,
                run=run,
                interval_seconds=max(0.25, float(interval_seconds)),
                jitter_seconds=min(1.0, max(0.0, float(interval_seconds) * 0.05)),
                timeout_seconds=max(60.0, float(interval_seconds)),
                executor=executor,
                enabled=enabled,
                on_startup=tuple(startup_callbacks),
                on_shutdown=worker.shutdown,
            )

        return create

    from app.trading.prospective_gap_inputs import handoff_import_task
    from app.trading.strategies.runner import strategy_runner_task

    return (
        *(factory_for(worker_factory, enabled) for worker_factory, enabled in registrations),
        # Registered strategies run through the generic runner (WP-8.3).
        strategy_runner_task,
        # Opt-in: import the premarket handoff from GitHub into PostgreSQL.
        handoff_import_task,
    )


__all__ = [
    "create_trading_router",
    "trading_scheduled_task_factories",
]
