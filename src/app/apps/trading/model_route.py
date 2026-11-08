"""Which provider and model trading's research calls use: the "Trading model" setting, or the default provider.

Settings store it as a task-routing override under ``TRADING_ROUTE_KEY`` (``global.routing.taskOverrides``):
``{"providerId": ..., "modelId": ...}``, both optional. No provider means the default LLM provider; no model means that
provider's configured model. Research only: which model answers grants nothing, and execution stays deterministic.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.providers.catalog import LOADED_MODEL, LOCAL_DEVICE, THINKING_OFF, provider_supports

logger = logging.getLogger(__name__)

TRADING_ROUTE_KEY = "trading-research"


@dataclass(frozen=True)
class TradingModel:
    provider_id: str | None = None  # None: the default LLM provider
    model_id: str | None = None  # None: that provider's configured model


def trading_model() -> TradingModel:
    """The Trading model setting; the default provider when it is unset or cannot be read."""
    try:
        from app.settings.effective_defaults import load_effective_profile, route_model_name, setting_text

        row = load_effective_profile().global_settings.routing.task_overrides.get(TRADING_ROUTE_KEY) or {}
        provider = setting_text(row.get("providerId") or row.get("provider_id")).removeprefix("llm:")
        model = route_model_name(row.get("modelId") or row.get("model_id"))
    except Exception:  # noqa: BLE001 - research keeps working on the default provider
        logger.warning("trading_model_setting_unreadable", exc_info=True)
        return TradingModel()
    return TradingModel(provider or None, model or None)


def trading_provider(default_lookup: Callable[[], Any] | None = None) -> Any:
    """The provider the Trading model setting names; unset, ``default_lookup`` (the default provider).

    A provider chosen without a model follows what it has loaded, so loading another model in LM Studio moves trading
    to it, rather than a stale configured model being loaded over it.
    """
    from app.providers import service as provider_service

    chosen = trading_model()
    if chosen.provider_id is None and chosen.model_id is None:
        return (default_lookup or provider_service.get_provider)()
    provider = provider_service.get_routed_provider(chosen.provider_id, chosen.model_id)
    if provider is not None and chosen.model_id is None and provider_supports(provider, LOADED_MODEL):
        loaded = provider.loaded_model_key()
        if loaded:
            return provider_service.get_routed_provider(chosen.provider_id, loaded)
    return provider


def trading_provider_is_local() -> bool:
    """Whether trading's calls run on this machine, so they spend no provider quota.

    Asked by the budget on every call, so it reads ids and never asks the provider what it has loaded.
    """
    try:
        from app.providers import service as provider_service

        return provider_supports(trading_model().provider_id or provider_service.get_provider(), LOCAL_DEVICE)
    except Exception:  # noqa: BLE001 - when unsure, the daily budget stays on
        logger.warning("trading_provider_locality_unknown", exc_info=True)
        return False


def no_thinking_options(provider: Any) -> dict[str, bool]:
    """Call options that stop a local model thinking first.

    Trading's output limits and 30-60 s deadlines are sized for an answer, not for a reasoning trace: on LM Studio,
    Qwen 3.8 27B spent the whole limit thinking and never answered. Hosted models keep their own behaviour.
    """
    if provider_supports(provider, LOCAL_DEVICE) and provider_supports(provider, THINKING_OFF):
        return {"thinking": False}
    return {}


__all__ = [
    "TRADING_ROUTE_KEY",
    "TradingModel",
    "no_thinking_options",
    "trading_model",
    "trading_provider",
    "trading_provider_is_local",
]
