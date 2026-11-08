"""Which provider and model memory's own calls use: the person's "Memory model" setting, or the default provider.

Settings store it as a task-routing override under the module's id (``global.routing.taskOverrides``,
``MEMORY_ROUTE_KEY``): ``{"providerId": ..., "modelId": ...}``. Both parts are optional. No provider means the default
LLM provider; no model means that provider's own choice for memory (``conversation_reading`` reads with Sonnet on
the Claude CLI, proposals use the provider's configured model). The ``OMNIX_MEMORY_*`` environment variables, when
set, still win: they are the operator's.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MEMORY_ROUTE_KEY = "assistant-memory"


@dataclass(frozen=True)
class MemoryModel:
    provider_id: str | None = None  # None: the default LLM provider
    model_id: str | None = None  # None: that provider's own choice


def memory_model() -> MemoryModel:
    """The Memory model setting; the default provider when it is unset or cannot be read."""
    try:
        from app.settings.effective_defaults import load_effective_profile, setting_text

        row = load_effective_profile().global_settings.routing.task_overrides.get(MEMORY_ROUTE_KEY) or {}
        provider = setting_text(row.get("providerId") or row.get("provider_id")).removeprefix("llm:")
        model = setting_text(row.get("modelId") or row.get("model_id"))
    except Exception:  # noqa: BLE001 - memory keeps working on the default provider
        logger.warning("memory_model_setting_unreadable", exc_info=True)
        return MemoryModel()
    return MemoryModel(provider or None, model or None)


def memory_route(environment_provider: str) -> tuple[str | None, str | None]:
    """The provider to ask for (None: the default) and the model the setting names (None: the provider's choice).

    A provider named in the environment overrides the setting as a whole, model included: a model belongs to its
    provider.
    """
    if environment_provider.strip():
        return environment_provider.strip(), None
    chosen = memory_model()
    return chosen.provider_id, chosen.model_id


__all__ = ["MEMORY_ROUTE_KEY", "MemoryModel", "memory_model", "memory_route"]
