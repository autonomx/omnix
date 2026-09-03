"""Trading route hook for the shared Omnix gateway."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI

_ROUTE_SENTINEL = "_omnix_trading_routes_registered"
_HOOK_SENTINEL = "_omnix_trading_route_hook_installed"


def register_trading_routes(gateway: FastAPI) -> None:
    """Register Trading only when the real Omnix web gateway is constructed.

    Keep Trading imports out of gateway package import time so lightweight apps
    such as the launcher/runtime-control dashboard can import gateway submodules
    without initializing the full Trading stack.
    """
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return

    from app.trading.alerts_api import create_trading_alert_router
    from app.trading.alerts_monitor import register_trading_alert_monitor
    from app.trading.api import create_trading_router
    from app.trading.catalyst_api import create_trading_catalyst_router
    from app.trading.execution_api import create_trading_execution_router
    from app.trading.hermes_research_api import create_trading_hermes_research_router
    from app.trading.metric_api import create_trading_metric_router
    from app.trading.metric_monitor import register_trading_metric_monitor
    from app.trading.model_api import create_trading_model_router
    from app.trading.market_data_api import create_trading_market_data_router
    from app.trading.paper_analytics_api import create_trading_paper_analytics_router
    from app.trading.paper_api import create_trading_paper_router
    from app.trading.paper_monitor import register_trading_paper_monitor
    from app.trading.providers.alpaca_iex_status import register_alpaca_iex_status_monitor
    from app.trading.replay_api import create_trading_replay_router
    from app.trading.research_api import create_trading_research_router
    from app.trading.scanner_api import create_trading_scanner_router
    from app.trading.strategy_ai_shadow_monitor import register_trading_ai_shadow_monitor
    from app.trading.strategy_api import create_trading_strategy_router
    from app.trading.strategy_deep_recovery_monitor import register_trading_strategy_deep_recovery_shadow_monitor
    from app.trading.strategy_monitor import register_trading_strategy_monitor
    from app.trading.strategy_operations_api import create_trading_strategy_operations_router
    from app.trading.strategy_prospective_economic_api import create_trading_strategy_prospective_economic_router
    from app.trading.strategy_prospective_economic_monitor import register_trading_strategy_prospective_economic_monitor
    from app.trading.strategy_research_monitor import register_trading_strategy_research_monitor
    from app.trading.strategy_research_outcome_monitor import register_trading_strategy_research_outcome_monitor
    from app.trading.strategy_universe_archive_monitor import register_trading_strategy_universe_archive_monitor
    from app.trading.strategy_v2_qualification_monitor import register_trading_strategy_v2_qualification_monitor

    gateway.include_router(create_trading_router())
    gateway.include_router(create_trading_metric_router())
    gateway.include_router(create_trading_execution_router())
    gateway.include_router(create_trading_alert_router())
    gateway.include_router(create_trading_scanner_router())
    gateway.include_router(create_trading_replay_router())
    gateway.include_router(create_trading_paper_router())
    gateway.include_router(create_trading_paper_analytics_router())
    gateway.include_router(create_trading_research_router())
    gateway.include_router(create_trading_hermes_research_router())
    gateway.include_router(create_trading_strategy_router())
    gateway.include_router(create_trading_strategy_prospective_economic_router())
    gateway.include_router(create_trading_strategy_operations_router())
    gateway.include_router(create_trading_catalyst_router())
    gateway.include_router(create_trading_model_router())
    gateway.include_router(create_trading_market_data_router())
    register_trading_metric_monitor(gateway)
    register_trading_alert_monitor(gateway)
    register_alpaca_iex_status_monitor(gateway)
    register_trading_paper_monitor(gateway)
    register_trading_strategy_monitor(gateway)
    register_trading_ai_shadow_monitor(gateway)
    register_trading_strategy_deep_recovery_shadow_monitor(gateway)
    register_trading_strategy_prospective_economic_monitor(gateway)
    register_trading_strategy_universe_archive_monitor(gateway)
    register_trading_strategy_v2_qualification_monitor(gateway)
    register_trading_strategy_research_monitor(gateway)
    register_trading_strategy_research_outcome_monitor(gateway)
    setattr(gateway.state, _ROUTE_SENTINEL, True)


def install_trading_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_trading_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
