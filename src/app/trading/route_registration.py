"""Trading router composition and runtime-owned background workers."""
from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace

from fastapi import APIRouter

from app.runtime.background import BackgroundRegistry, BackgroundWorker
from app.runtime.features import FeatureContext


def create_trading_router(_context: FeatureContext) -> APIRouter:
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
        router.include_router(factory())
    return router


_TRADING_MONITOR_REGISTRARS = (
    ("app.trading.alerts_monitor", "register_trading_alert_monitor"),
    ("app.trading.execution_observation_monitor", "register_trading_execution_observation_monitor"),
    ("app.trading.ibkr_market_data_monitor", "register_trading_ibkr_market_data_monitor"),
    ("app.trading.metric_monitor", "register_trading_metric_monitor"),
    ("app.trading.paper_monitor", "register_trading_paper_monitor"),
    ("app.trading.prospective_gap_monitor", "register_prospective_gap_monitor"),
    ("app.trading.providers.alpaca_iex_status", "register_alpaca_iex_status_monitor"),
    ("app.trading.session_reconciliation_monitor", "register_trading_session_reconciliation_monitor"),
    ("app.trading.strategy_ai_shadow_monitor", "register_trading_ai_shadow_monitor"),
    ("app.trading.strategy_ai_shadow_v2_monitor", "register_trading_ai_shadow_v2_monitor"),
    ("app.trading.strategy_ai_shadow_v3_monitor", "register_trading_ai_shadow_v3_monitor"),
    ("app.trading.strategy_deep_recovery_monitor", "register_trading_strategy_deep_recovery_shadow_monitor"),
    ("app.trading.strategy_dynamic_discovery_monitor", "register_interday_dynamic_discovery_monitor"),
    ("app.trading.strategy_interday_learning_monitor", "register_interday_learning_monitor"),
    ("app.trading.strategy_monitor", "register_trading_strategy_monitor"),
    ("app.trading.strategy_prospective_economic_monitor", "register_trading_strategy_prospective_economic_monitor"),
    ("app.trading.strategy_research_monitor", "register_trading_strategy_research_monitor"),
    ("app.trading.strategy_research_outcome_monitor", "register_trading_strategy_research_outcome_monitor"),
    ("app.trading.strategy_solana_ai_monitor", "register_trading_solana_ai_monitor"),
    ("app.trading.strategy_universe_archive_monitor", "register_trading_strategy_universe_archive_monitor"),
    ("app.trading.strategy_v2_qualification_monitor", "register_trading_strategy_v2_qualification_monitor"),
    ("app.trading.yahoo_acquisition_monitor", "register_trading_yahoo_acquisition_monitor"),
)


class _WorkerCollector(BackgroundRegistry):
    def __init__(self) -> None:
        self.workers: list[BackgroundWorker] = []

    def register_worker(self, worker: BackgroundWorker) -> None:
        self.workers.append(worker)


class _FeatureStateProxy:
    def __init__(self, target, registry: BackgroundRegistry) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_registry", registry)

    def __getattr__(self, name: str):
        if name == "background_registry":
            return object.__getattribute__(self, "_registry")
        return getattr(object.__getattribute__(self, "_target"), name)

    def __setattr__(self, name: str, value) -> None:
        if name == "background_registry":
            object.__setattr__(self, "_registry", value)
            return
        setattr(object.__getattribute__(self, "_target"), name, value)


def _monitor_worker_factory(module_name: str, registrar_name: str):
    def build(context: FeatureContext) -> BackgroundWorker | None:
        collector = _WorkerCollector()
        state = _FeatureStateProxy(context.runtime_state, collector)
        registrar = getattr(import_module(module_name), registrar_name)
        result = registrar(SimpleNamespace(state=state))
        if not collector.workers and result is None:
            return None
        if len(collector.workers) != 1:
            raise RuntimeError(
                f"{module_name}.{registrar_name} must create exactly one BackgroundWorker"
            )
        return collector.workers[0]

    return build


def trading_background_worker_factories():
    return tuple(
        _monitor_worker_factory(module_name, registrar_name)
        for module_name, registrar_name in _TRADING_MONITOR_REGISTRARS
    )


__all__ = ["create_trading_router", "trading_background_worker_factories"]
